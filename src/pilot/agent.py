"""The decision agent: one short pydantic-ai run per blocker ("episode"), with game tools,
corpus consultation, and learning tools. Provider-agnostic; images are trimmed from history."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent, ModelSettings, RunContext, Tool, ToolReturn
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart, UserPromptPart
from pydantic_ai.usage import UsageLimits

TRANSIENT_HTTP = {429, 500, 502, 503, 504}


def transient(e: BaseException) -> bool:
    """Worth retrying: overloaded / rate limited / gateway errors, and requests that timed out."""
    if isinstance(e, ModelHTTPError):
        return e.status_code in TRANSIENT_HTTP
    return isinstance(e, (httpx.TimeoutException, TimeoutError))


def run_with_retry(fn, delays: tuple[float, ...], on_retry=None):
    """Call `fn`; on a transient provider error (overloaded, rate limited, gateway, timed out) wait
    and try again, once per delay. The game is paused while a decision is made, so waiting costs nothing."""
    for i, delay in enumerate((*delays, None)):
        try:
            return fn()
        except (ModelHTTPError, httpx.TimeoutException, TimeoutError) as e:
            if not transient(e) or delay is None:
                raise
            if on_retry:
                on_retry(e, delay, i + 1)
            time.sleep(delay)
    return None  # unreachable

from . import coords
from .config import Settings
from .events import EventLog
from .game import Game, ToolResult
from .learning import FORBIDDEN_KEYS, Journal, LearnedStore, LearningRejected, ScreenAction

GENERIC_INSTRUCTIONS = """You are an autonomous player of a turn-based strategy game, acting only through tools.
A verified autopilot plays routine turns; you are called when it stops on something that needs judgement.
{coord_rule}
Every action tool returns a fresh screenshot; compare it with what you expected before acting again.
Keep actions minimal and deliberate. If an action did not work twice, try another way or finish with resolved=false.
Human instructions, when present in the briefing, override the rules below."""

IMAGE_STUB = "[older screenshot omitted to save context]"


class EpisodeResult(BaseModel):
    situation: str = Field(description="Short name of what blocked the turn, e.g. 'Event: Frontier Shrine' or 'Research complete'")
    decision: str = Field(description="What you did, in one sentence")
    game_date: str = Field(default="", description="In-game date from the HUD, e.g. 'Oct 4, 2333'")
    resolved: bool = Field(description="True if the blocker is cleared and the autopilot can continue")


@dataclass
class Deps:
    game: Game
    store: LearnedStore
    journal: Journal
    log: EventLog
    settings: Settings
    human: HumanChannel
    frame: bytes | None = None
    actions: int = 0
    notes: list[str] = field(default_factory=list)


class HumanChannel:
    """Notes from the dashboard (used at the next decision) and answers to questions, kept apart:
    a note sent while a question is open must never count as its answer."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._pending: list[str] = []
        self._answers: list[str] = []
        self.question = ""

    def push(self, text: str) -> None:
        with self._cond:
            self._pending.append(text)

    def answer(self, text: str) -> None:
        with self._cond:
            self._answers.append(text)
            self._cond.notify_all()

    def take_all(self) -> list[str]:
        with self._cond:
            out, self._pending = self._pending, []
            return out

    def ask(self, question: str, timeout: float) -> str | None:
        with self._cond:
            self._answers = []                    # stale answers never apply to a new question
            self.question = question
            got = self._cond.wait_for(lambda: bool(self._answers), timeout=timeout)
            self.question = ""
            if got:
                out, self._answers = self._answers, []
                return " / ".join(out)
            return None


def image_metadata(s: Settings) -> dict | None:
    """Per-image provider metadata. Gemini: media resolution trades image tokens for detail."""
    detail = {"low": "MEDIA_RESOLUTION_LOW", "medium": "MEDIA_RESOLUTION_MEDIUM",
              "high": "MEDIA_RESOLUTION_HIGH"}.get(s.image_detail)
    if detail and s.provider.startswith("google"):
        return {"media_resolution": {"level": detail}}   # google-genai PartMediaResolution
    return None


def frame_content(s: Settings, jpeg: bytes) -> BinaryContent:
    return BinaryContent(data=jpeg, media_type="image/jpeg", vendor_metadata=image_metadata(s))


def _image(ctx: RunContext[Deps], jpeg: bytes | None) -> list:
    if not jpeg:
        return []
    ctx.deps.frame = jpeg
    ctx.deps.store.remember_frame(jpeg)
    ctx.deps.log.frame(jpeg)
    return [frame_content(ctx.deps.settings, jpeg)]


def _act(ctx: RunContext[Deps], label: str, r: ToolResult) -> ToolReturn:
    ctx.deps.actions += 1
    ctx.deps.log.emit("action", action=label, result=r.text[:300], error=r.is_error)
    return ToolReturn(return_value=("ERROR: " if r.is_error else "") + r.text[:500], content=_image(ctx, r.image))


# -- tools ------------------------------------------------------------------------------------

def look(ctx: RunContext[Deps]) -> ToolReturn:
    """Take a fresh screenshot of the game."""
    r = ctx.deps.game.screenshot()
    return ToolReturn(return_value="current screen attached", content=_image(ctx, r.image))


def click(ctx: RunContext[Deps], x: float, y: float, button: str = "left", double: bool = False) -> ToolReturn:
    """Click at (x, y) on the screenshot. button: left | right. double=True double-clicks."""
    px, py = coords.to_image(x, y, ctx.deps.settings.coord_space)
    return _act(ctx, f"click {button}{' x2' if double else ''} ({px},{py})",
                ctx.deps.game.click(px, py, button, 2 if double else 1))


def drag(ctx: RunContext[Deps], x1: float, y1: float, x2: float, y2: float) -> ToolReturn:
    """Drag from (x1, y1) to (x2, y2) on the screenshot (e.g. a policy onto a slot)."""
    s = ctx.deps.settings.coord_space
    a, b = coords.to_image(x1, y1, s), coords.to_image(x2, y2, s)
    return _act(ctx, f"drag {a}->{b}", ctx.deps.game.drag(*a, *b))


def key(ctx: RunContext[Deps], combo: str) -> ToolReturn:
    """Press a key or combo, e.g. 'tab', 'esc', 'n', 'o', 'ctrl+s'."""
    if combo.lower().replace(" ", "") in FORBIDDEN_KEYS:
        return ToolReturn(return_value=f"refused: {combo!r} is not allowed")
    return _act(ctx, f"key {combo}", ctx.deps.game.key(combo))


def hover(ctx: RunContext[Deps], x: float, y: float) -> ToolReturn:
    """Move the mouse to (x, y) without clicking, to read a tooltip."""
    px, py = coords.to_image(x, y, ctx.deps.settings.coord_space)
    return _act(ctx, f"hover ({px},{py})", ctx.deps.game.hover(px, py))


def consult(ctx: RunContext[Deps], situation: str) -> str:
    """Look up game data, past decisions and learned rules for a situation (event title, tech, building...)."""
    game, store = ctx.deps.game, ctx.deps.store
    parts = []
    hits = game.corpus("corpus_search", query=situation, limit=5)
    parts.append("GAME DATA SEARCH:\n" + hits)
    first = next((ln.split("`")[1] for ln in hits.splitlines() if ln.startswith("- `") and "`" in ln[3:]), None)
    if first and not first.startswith(("doc:", "strategy")):
        parts.append("TOP RECORD:\n" + game.corpus("corpus_get", id=first))
    past = store.recall(situation)
    if past:
        lines = [f"- {e.get('date') or e['t'][:10]}: {e['situation']} -> {e['decision']} ({e['outcome']})" for e in past]
        parts.append("PAST DECISIONS:\n" + "\n".join(lines))
        same = store.repeated(situation)
        if same >= 2:
            parts.append(f"You have resolved exactly '{situation}' {same} times before. If the correct response is always "
                         "the same single click/key and the screen has a static title or icon, call learn_screen now.")
    ctx.deps.log.emit("consult", situation=situation, past=len(past))
    return "\n\n".join(parts)


def get_record(ctx: RunContext[Deps], record_id: str) -> str:
    """Fetch one corpus record or doc chunk by id, e.g. 'tech:hyperwave_radio'."""
    return ctx.deps.game.corpus("corpus_get", id=record_id)


def note(ctx: RunContext[Deps], text: str, game_date: str = "") -> str:
    """Add one line to the game journal (notable events, new colonies, wars)."""
    ctx.deps.journal.note(text, game_date)
    ctx.deps.log.emit("journal", text=text)
    return "noted"


def remember_rule(ctx: RunContext[Deps], rule: str, why: str) -> str:
    """Record a decision rule you applied (situation -> choice) for future decisions."""
    return _learn(ctx, "rules", lambda: ctx.deps.store.add_rule(rule, why), rule=rule)


def remember_control(ctx: RunContext[Deps], control: str, how_verified: str) -> str:
    """Record a UI behaviour or hotkey you verified in play."""
    return _learn(ctx, "controls", lambda: ctx.deps.store.add_control(control, how_verified), control=control)


def learn_screen(ctx: RunContext[Deps], name: str, x0: float, y0: float, x1: float, y1: float, description: str,
                 click_x: float | None = None, click_y: float | None = None, key: str | None = None) -> str:
    """Teach the autopilot to handle a recurring screen by itself. Box (x0,y0)-(x1,y1) tightly covers a
    STATIC title/label/icon unique to the screen, on the CURRENT screenshot. Give either click_x/click_y
    (the always-correct button) or key. name: snake_case."""
    if ctx.deps.frame is None:
        return "rejected: take a screenshot first (look)"
    s = ctx.deps.settings.coord_space
    a, b = coords.to_image(x0, y0, s), coords.to_image(x1, y1, s)
    action = ScreenAction(click=coords.to_image(click_x, click_y, s) if click_x is not None and click_y is not None else None,
                          key=key)
    return _learn(ctx, "screens", lambda: ctx.deps.store.add_screen(
        name, ctx.deps.frame, (a[0], a[1], b[0], b[1]), action, description, evidence=f"episode {ctx.deps.log.state.episodes}"),
        screen=name)


def ask_human(ctx: RunContext[Deps], question: str) -> str:
    """Ask the human watching the dashboard. Play continues with your best judgement if nobody answers."""
    ctx.deps.log.state.pending_question = question
    ctx.deps.log.emit("question", question=question)
    answer = ctx.deps.human.ask(question, ctx.deps.settings.ask_human_timeout_s)
    ctx.deps.log.state.pending_question = ""
    ctx.deps.log.emit("answer", answer=answer or "(no answer)")
    return answer or "No answer yet; proceed with your best judgement and avoid irreversible actions."


def _learn(ctx: RunContext[Deps], kind: str, fn, **info) -> str:
    try:
        msg = fn()
    except LearningRejected as e:
        ctx.deps.log.emit("learn_rejected", category=kind, reason=str(e), **info)
        return f"rejected: {e}"
    ctx.deps.log.state.learned[kind] = ctx.deps.log.state.learned.get(kind, 0) + 1
    ctx.deps.log.emit("learned", category=kind, message=msg, **info)
    return msg


# -- history ------------------------------------------------------------------------------------

def trim_images(keep: int):
    """History processor: keep only the newest `keep` screenshots; replace older ones with a stub."""

    def process(messages: list[ModelMessage]) -> list[ModelMessage]:
        seen = 0
        for msg in reversed(messages):
            if not isinstance(msg, ModelRequest):
                continue
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                    new = []
                    for item in reversed(part.content):
                        if isinstance(item, BinaryContent) and item.is_image:
                            seen += 1
                            new.append(item if seen <= keep else IMAGE_STUB)
                        else:
                            new.append(item)
                    part.content = list(reversed(new))
                elif isinstance(part, ToolReturnPart) and isinstance(part.content, list):
                    for i in range(len(part.content) - 1, -1, -1):
                        if isinstance(part.content[i], BinaryContent) and part.content[i].is_image:
                            seen += 1
                            if seen > keep:
                                part.content[i] = IMAGE_STUB
        return messages

    return process


# -- agent ----------------------------------------------------------------------------------------

def model_settings(s: Settings) -> ModelSettings:
    # Every request has a timeout: a Gemini call once never answered and held the run (game paused)
    # until it was restarted. A timeout is retried like a 503 (run_with_retry).
    base = ModelSettings(timeout=s.model_timeout_s)
    if s.thinking == "off":
        return base
    if s.provider.startswith("google"):
        # include_thoughts: Gemini returns thought summaries, shown in the dashboard's decision traces.
        return ModelSettings(**base, google_thinking_config={"thinking_level": s.thinking, "include_thoughts": True})  # type: ignore[typeddict-unknown-key]
    if s.provider.startswith("openai"):
        return ModelSettings(**base, openai_reasoning_effort=s.thinking)  # type: ignore[typeddict-unknown-key]
    return base


def build_agent(s: Settings, game_briefing: str, model=None) -> Agent[Deps, EpisodeResult]:
    instructions = GENERIC_INSTRUCTIONS.format(coord_rule=coords.describe(s.coord_space)) + "\n\n" + game_briefing
    tools = [Tool(f) for f in (look, click, drag, key, hover, consult, get_record, note,
                               remember_rule, remember_control, learn_screen, ask_human)]
    return Agent(model or s.model, deps_type=Deps, output_type=EpisodeResult, instructions=instructions,
                 tools=tools, model_settings=model_settings(s), retries=2,
                 capabilities=[ProcessHistory(trim_images(s.images_in_context))])


def run_episode(agent: Agent[Deps, EpisodeResult], deps: Deps, stop_text: str, frame: bytes | None,
                extra: list[str]) -> tuple[EpisodeResult, object, list]:
    briefing = [f"The autopilot stopped: {stop_text}"]
    if extra:
        briefing.append("HUMAN INSTRUCTIONS (follow these): " + " | ".join(extra))
    briefing.append("Current screen attached. Resolve the blocker, then return the result.")
    content: list = ["\n".join(briefing)]
    if frame:
        deps.frame = frame
        deps.store.remember_frame(frame)
        content.append(frame_content(deps.settings, frame))
    def on_retry(e, delay, attempt):
        deps.log.emit("model_retry", error=f"model {e.model_name} answered {e.status_code}", delay=delay, attempt=attempt)

    result = run_with_retry(lambda: agent.run_sync(content, deps=deps,
                                                   usage_limits=UsageLimits(request_limit=deps.settings.max_requests_per_episode)),
                            deps.settings.retry_delays, on_retry)
    return result.output, result.usage, result.all_messages()

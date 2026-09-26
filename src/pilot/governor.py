"""Stellaris governor loop: the native AI plays the empire in observer mode; the model reads a
briefing from the autosave every few in-game months (or when something urgent happens) and picks
one standing directive. The game is paused while the model decides, so any game speed is safe.

    pause → briefing → decision → (apply directive) → resume at the chosen speed
          → poll autosave briefings until the next decision date, a new war or a new deficit → …
"""

from __future__ import annotations

import html
import json
import queue
import re
import threading
import time
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from .agent import HumanChannel, model_settings, run_with_retry
from .config import Settings
from .events import EventLog
from .learning import Journal, LearnedStore, LearningRejected
from .trace import serialize

DIRECTIVES = ("expand", "consolidate_economy", "tech_rush", "prepare_war", "defend", "diplomacy_first")
NEEDS_HUMAN = {"prepare_war"}      # strategy.md: only after the human confirmed the target

INSTRUCTIONS = """You are the governor of a Stellaris empire. The game's own AI runs the empire day to day;
you steer it by choosing ONE standing directive, which the harness applies (policies and a flag the
AI keeps). The game is paused while you decide. Answer with `keep` unless the situation changed
materially or the current directive's "leave when" condition holds.
The prompt already holds what you normally need: the briefing (resources, standing against the other
empires, expansion room), the campaign plan, earlier directive changes and their outcomes, and the
directives table below. Call a tool only for a specific fact that is missing (e.g. what an event
option does: consult), and at most twice; then answer.
Human instructions, when present, override the rules below."""


class GovernorDecision(BaseModel):
    directive: Literal["keep", "expand", "consolidate_economy", "tech_rush", "prepare_war", "defend",
                       "diplomacy_first"] = Field(description="The directive to hold from now on, or 'keep'")
    reason: str = Field(description="One or two sentences citing the briefing numbers that decided it")
    note: str = Field(default="", description="Optional one line for the game journal (war, first colony, crisis...)")
    plan: str = Field(default="", description="The full rewritten campaign plan (goals, milestones with in-game target "
                      "dates, current focus), ONLY when the plan should change; otherwise empty")


class Retrospective(BaseModel):
    assessment: str = Field(description="What worked and what did not since the last review, citing numbers")
    rules: list[str] = Field(default_factory=list, description="0-3 general rules learned (situation -> choice), "
                             "each a full sentence; only what the evidence supports")
    plan: str = Field(description="The revised campaign plan: goals, milestones with in-game target dates, current focus")


RETRO_INSTRUCTIONS = """You review how a Stellaris empire has been governed. The game's own AI plays it; a governor
picks one standing directive at a time. Compare the campaign plan with what happened: the decisions,
their outcomes 12 months later, and the empire's standing against the other empires. Be concrete and
brief, cite numbers, and propose only rules the evidence supports."""


class StellarisGame(Protocol):
    def briefing(self) -> dict: ...
    def briefing_text(self) -> str: ...
    def set_paused(self, paused: bool) -> str: ...
    def set_speed(self, speed: str) -> str: ...
    def directive(self, name: str) -> str: ...
    def log_tail(self, lines: int = 30) -> str: ...
    def take_control(self) -> str: ...
    def screenshot(self): ...
    def corpus(self, tool: str, **args) -> str: ...
    def close(self) -> None: ...


@dataclass
class GovDeps:
    game: StellarisGame
    store: LearnedStore
    log: EventLog


def months(date: str) -> int:
    """'2204.09.01' → months since year 0."""
    y, m, *_ = (int(x) for x in date.split("."))
    return y * 12 + m - 1


def current_directive(b: dict) -> str | None:
    for f in b.get("flags", []):
        if f.startswith("governor_directive_"):
            return f.removeprefix("governor_directive_")
    return None


def metrics(b: dict) -> dict:
    """Compact numbers from a briefing for the dashboard's charts."""
    return {"date": b["date"], "stockpile": b.get("stockpile", {}), "net": b.get("net", {}),
            "military_power": b.get("military_power"), "economy_power": b.get("economy_power"),
            "tech_power": b.get("tech_power"), "pops": b.get("pops"), "planets": len(b.get("planets", [])),
            "systems": b.get("systems"),
            "peers": {k: {"median": v.get("median"), "rank": v.get("rank")} for k, v in (b.get("peers") or {}).get("stats", {}).items()},
            "peer_count": (b.get("peers") or {}).get("empires"), "behind": (b.get("peers") or {}).get("behind", []),
            "room": (b.get("expansion") or {}).get("reach_unclaimed"),
            "room_surveyed": (b.get("expansion") or {}).get("reach_unclaimed_surveyed"),
            "construction_ships": (b.get("expansion") or {}).get("construction_ships"),
            "techs_known": b.get("techs_known"), "wars": len(b.get("wars", [])), "directive": current_directive(b)}


def _num(v) -> str:
    """Readable number for reasons: 405.92577500000004 -> '406', 1.0 -> '1', 12.34 -> '12.3'."""
    if not isinstance(v, (int, float)):
        return str(v)
    return f"{v:.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:.1f}"


def urgent_changes(before: dict, now: dict) -> list[str]:
    """Reasons to decide before the scheduled date: a new war, or a resource turning negative."""
    out = []
    old_wars = {w["name"] for w in before.get("wars", [])}
    for w in now.get("wars", []):
        if w["name"] not in old_wars:
            out.append(f"new war: {w['name']} (we are {'attacker' if w.get('attacker') else 'defender'})")
    for res, net in now.get("net", {}).items():
        if net < 0 <= before.get("net", {}).get(res, 0):
            out.append(f"{res} net turned negative ({net:+.1f}/month)")
    was_behind = set((before.get("peers") or {}).get("behind", []))
    for m in (now.get("peers") or {}).get("behind", []):
        if m not in was_behind:
            st = now["peers"]["stats"].get(m, {})
            out.append(f"falling behind other empires in {m} ({_num(st.get('ours'))} vs median {_num(st.get('median'))})")
    return out


# -- tools ------------------------------------------------------------------------------------

def consult(ctx: RunContext[GovDeps], query: str) -> str:
    """Search the Stellaris reference docs and playbook (costs, requirements, mechanics)."""
    ctx.deps.log.emit("consult", situation=query, past=0)
    return ctx.deps.game.corpus("corpus_search", query=query, limit=5)


def get_doc(ctx: RunContext[GovDeps], record_id: str) -> str:
    """Fetch one record or doc chunk by the id a consult result shows, e.g. 'doc:policies#0' or 'event:distar.311'."""
    got = ctx.deps.game.corpus("corpus_get", id=record_id)
    if got.startswith("No corpus item") and record_id.startswith("doc:strategy"):
        got = ctx.deps.game.corpus("corpus_get", id=record_id.removeprefix("doc:"))   # models add "doc:" to strategy ids
    return got


def recent_log(ctx: RunContext[GovDeps], lines: int = 20) -> str:
    """Last lines of the game's log (script log lines carry the in-game date)."""
    return ctx.deps.game.log_tail(min(lines, 100))


def past_outcomes(ctx: RunContext[GovDeps]) -> str:
    """Earlier directive changes in this campaign and how the empire changed 12 in-game months later
    (planets, pops, techs, military/economy/tech power, deficits). Use it to avoid repeating what failed."""
    tel, cid = ctx.deps.log.telemetry, ctx.deps.log.campaign_id
    if tel is None or cid is None:
        return "No telemetry for this run."
    try:
        return tel.past_outcomes(cid)
    except Exception as e:  # noqa: BLE001
        return f"Telemetry unavailable: {e}"


def remember_rule(ctx: RunContext[GovDeps], rule: str, why: str) -> str:
    """Record a directive rule that worked (or failed), with the numbers that justified it."""
    try:
        msg = ctx.deps.store.add_rule(rule, why)
    except LearningRejected as e:
        ctx.deps.log.emit("learn_rejected", category="rules", reason=str(e), rule=rule)
        return f"rejected: {e}"
    ctx.deps.log.state.learned["rules"] = ctx.deps.log.state.learned.get("rules", 0) + 1
    ctx.deps.log.emit("learned", category="rules", message=msg, rule=rule)
    return msg


def governor_settings(s: Settings):
    """Model settings for governor decisions: the governor's own thinking level."""
    return model_settings(replace(s, thinking=s.governor_thinking))


def strategy_core(strategy: str) -> str:
    """The part of strategy.md every decision needs (the directives section), plus a table of contents
    for the rest, which the model reads with `consult` when a topic comes up. Keeps the fixed
    instructions short (and identical between calls, so providers can cache them)."""
    parts = re.split(r"(?m)^(?=## )", strategy)
    head, sections = parts[0], parts[1:]
    core = [s for s in sections if "directive" in s.splitlines()[0].lower()]
    toc = [s.splitlines()[0].lstrip("# ").strip() for s in sections if s not in core]
    out = head.split("---")[0].strip()
    if toc:
        out += "\n\nMore in the playbook (use consult, e.g. consult(\"crisis preparation\")): " + "; ".join(toc) + "."
    return out + "\n\n" + "\n".join(core)


def build_governor(s: Settings, briefing: str, model=None) -> Agent[GovDeps, GovernorDecision]:
    return Agent(model or s.model, deps_type=GovDeps, output_type=GovernorDecision,
                 instructions=INSTRUCTIONS + "\n\n" + briefing,
                 tools=[Tool(f) for f in (consult, get_doc, recent_log, remember_rule)],   # outcomes are in the prompt
                 model_settings=governor_settings(s), retries=2)


# -- loop -------------------------------------------------------------------------------------

@dataclass
class Control:
    paused: bool = False
    stopping: bool = False


CHAT_INSTRUCTIONS = """You are the governor of a Stellaris empire, talking with the human who oversees you.
Answer their questions about the empire and your decisions plainly and briefly, citing briefing numbers.
You cannot act in this conversation: directives are only chosen at decision points. If the human wants
something done, tell them to use "Decide now", a standing order, or an override on the dashboard."""


class Governor:
    def __init__(self, settings: Settings, game: StellarisGame, log: EventLog, model=None):
        self.s = settings
        self.game = game
        self.log = log
        self.control = Control()
        self.human = HumanChannel()
        self.store = LearnedStore(settings.corpus_dir, settings.model, log.state.run_id)
        self.journal = Journal(settings.journal, settings.model)
        text = (settings.corpus_dir / "pilot.md").read_text(encoding="utf-8")
        text += "\n\n" + strategy_core((settings.corpus_dir / "strategy.md").read_text(encoding="utf-8"))
        learned = settings.corpus_dir / "learned" / "strategy.md"
        if learned.exists():
            text += "\n\n## Rules learned in play\n" + learned.read_text(encoding="utf-8")
        self._text = text
        self._model_obj = model                  # a Model instance (tests); None = settings.model
        self._build_agents()
        self.chat_exchanges: list[list] = []      # whole exchanges, so history never starts mid-exchange
        self._chat_lock = threading.Lock()
        self.last_change: int | None = None       # month of the last directive change
        self.last_briefing = ""                   # text of the latest briefing given to the model
        self.plan = ""                            # the campaign plan (goals, milestones), per campaign
        self._since_retro = 0
        self.orders: list[str] = []               # standing orders, saved per campaign
        self.requests: queue.Queue[tuple[str, str]] = queue.Queue()   # ("decide", msg) | ("override", name)
        log.state.info["controls"] = ["instruct", "chat", "order_add", "order_remove", "decide_now", "override",
                                      "set_model", "set_speed", "set_months"]
        log.state.info["thinking"] = settings.governor_thinking
        log.state.info["directives"] = list(DIRECTIVES)

    def _build_agents(self) -> None:
        """(Re)build the decision, chat and retrospective agents for the current model settings."""
        m, s, text = self._model_obj or self.s.model, self.s, self._text
        self.agent = build_governor(s, text, model=m)
        self.chat_agent: Agent[GovDeps, str] = Agent(
            m, deps_type=GovDeps, output_type=str, instructions=CHAT_INSTRUCTIONS + "\n\n" + text,
            tools=[Tool(f) for f in (consult, get_doc, recent_log, past_outcomes)],   # read-only
            model_settings=governor_settings(s), retries=2)
        self.retro_agent: Agent[GovDeps, Retrospective] = Agent(
            m, deps_type=GovDeps, output_type=Retrospective, instructions=RETRO_INSTRUCTIONS + "\n\n" + text,
            tools=[Tool(f) for f in (consult, get_doc)],    # outcomes are already in its prompt
            model_settings=governor_settings(s), retries=2)

    def set_model(self, model: str, thinking: str | None = None) -> None:
        """Switch model (and thinking level) from the next model call on."""
        from .models import THINKING, valid_model
        if not valid_model(model):
            raise ValueError(f"not a model name: {model!r} (expected provider:name)")
        if thinking is not None and thinking not in THINKING:
            raise ValueError(f"thinking must be one of {', '.join(THINKING)}")
        self.s = replace(self.s, model=model, governor_thinking=thinking or self.s.governor_thinking)
        self._model_obj = None
        self._build_agents()
        self.log.state.model = model
        self.log.state.info["thinking"] = self.s.governor_thinking
        self.log.emit("model", model=model, thinking=self.s.governor_thinking)

    # dashboard controls (same surface as Pilot)
    def pause(self) -> None:
        self.control.paused = True
        self._status("paused")

    def resume(self) -> None:
        self.control.paused = False
        self._status("playing")

    def stop(self) -> None:
        self.control.stopping = True
        self.control.paused = False

    def instruct(self, text: str) -> None:
        """A note for the next decision only."""
        self.human.push(text)
        self.log.emit("instruction", text=text)

    def answer(self, text: str) -> None:
        """Answer the model's open question (e.g. yes/no for prepare_war)."""
        self.human.answer(text)

    # -- directing the model (dashboard) ------------------------------------------------------

    def _orders_file(self):
        cid = self.log.campaign_id or "no-campaign"
        return self.s.runs_dir / "orders" / (re.sub(r"[^A-Za-z0-9_.-]", "_", cid) + ".json")

    def _save_orders(self) -> None:
        f = self._orders_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(self.orders, ensure_ascii=False, indent=1), encoding="utf-8")
        self.log.state.info["orders"] = list(self.orders)
        self.log.emit("orders", orders=list(self.orders))

    def order_add(self, text: str) -> None:
        """A standing order: included in every decision until removed."""
        self.orders.append(text.strip())
        self._save_orders()

    def order_remove(self, index: int) -> None:
        if 0 <= index < len(self.orders):
            self.orders.pop(index)
            self._save_orders()

    def decide_now(self, text: str = "") -> None:
        """Pause the game and have the model decide immediately (with an optional message)."""
        self.requests.put(("decide", text.strip()))
        self.log.emit("instruction", text=f"Decide now{': ' + text.strip() if text.strip() else ''}")

    def set_speed(self, speed: str) -> None:
        """Change the game speed; applied by the loop (never two things sending keys at once)."""
        from .models import SPEEDS
        if speed not in SPEEDS:
            raise ValueError(f"speed must be one of {', '.join(SPEEDS)}")
        self.requests.put(("speed", speed))
        self.log.emit("instruction", text=f"Speed: {speed}")

    def set_months(self, months: int) -> None:
        """Change how many in-game months pass between scheduled decisions; applies at once."""
        if not isinstance(months, int) or not 1 <= months <= 120:
            raise ValueError("months must be a whole number from 1 to 120")
        self.s = replace(self.s, decide_every_months=months)
        self.log.state.info["every_months"] = months
        self.log.emit("pace", every_months=months)

    def override(self, directive: str) -> None:
        """Apply a directive chosen by the human (recorded as a human decision)."""
        if directive not in DIRECTIVES:
            raise ValueError(f"unknown directive {directive!r}")
        self.requests.put(("override", directive))
        self.log.emit("instruction", text=f"Override: {directive}")

    def chat(self, text: str) -> None:
        """Ask the model something; it answers in the feed without acting on the game."""
        self.log.emit("chat", role="human", text=text)
        threading.Thread(target=self._chat, args=(text,), daemon=True, name="chat").start()

    def _chat(self, text: str) -> None:
        with self._chat_lock:
            ctx = [f"Standing orders: {'; '.join(self.orders) or 'none'}.",
                   f"Latest briefing:\n{self.last_briefing or '(no decision yet)'}",
                   f"Last decision: {self.log.state.last_decision or 'none'}", f"The human asks: {text}"]
            try:
                result = self.chat_agent.run_sync("\n\n".join(ctx), deps=GovDeps(self.game, self.store, self.log),
                                                  message_history=self._chat_history() or None,
                                                  usage_limits=UsageLimits(request_limit=8))
            except Exception as e:  # noqa: BLE001
                self.log.emit("chat", role="model", text=f"(could not answer: {type(e).__name__}: {e})"[:500])
                return
            self.chat_exchanges = (self.chat_exchanges + [result.new_messages()])[-6:]
            u = result.usage
            self.log.state.tokens_in += u.input_tokens or 0
            self.log.state.tokens_out += u.output_tokens or 0
            self.log.emit("chat", role="model", text=result.output, steps=serialize(result.new_messages()))

    def _chat_history(self) -> list:
        return [m for ex in self.chat_exchanges for m in ex]

    def _status(self, status: str) -> None:
        self.log.state.status = status
        self.log.emit("status", status=status)

    def _on_retry(self, e, delay, attempt) -> None:
        self.log.emit("model_retry", error=f"model {e.model_name} answered {e.status_code}", delay=delay, attempt=attempt)

    def _needs_attention(self, why: str) -> None:
        """Stop acting and wait for the human (dashboard Resume) instead of crashing the run."""
        self.control.paused = True
        self.log.state.status = "needs_attention"
        try:
            shot = self.game.screenshot()
            if getattr(shot, "image", None):
                self.log.frame(shot.image)
        except Exception:  # noqa: BLE001, S110 - the frame is only a convenience here
            pass
        self.log.emit("needs_attention", reason=why[:500])

    def run(self, max_decisions: int | None = None) -> None:
        self.log.state.info.update(game=self.s.game, speed=self.s.speed, every_months=self.s.decide_every_months)
        self.log.emit("run_start", model=self.s.model, game=self.s.game, speed=self.s.speed,
                      every_months=self.s.decide_every_months)
        try:
            b = self._start()
            while b is not None and not self.control.stopping:
                if max_decisions is not None and self.log.state.episodes >= max_decisions:
                    break
                try:
                    if self.control.paused:
                        if self.log.state.status != "needs_attention":
                            self.game.set_paused(True)
                        while self.control.paused and not self.control.stopping and self.requests.empty():
                            time.sleep(0.5)
                        if not self.requests.empty():
                            req = self.requests.get_nowait()      # consumed even if it fails below
                            b = self._handle_request(req, self.game.briefing())
                        continue
                    b, reason = self._run_until_next_decision(b)
                    if b is None:
                        break
                    if reason == "request":
                        b = self._handle_request(self.requests.get_nowait(), b)
                    elif reason:
                        self._decide(b, reason)
                except Exception as e:  # noqa: BLE001 - any game-control failure (agent down, focus lost, a panel open)
                    self._needs_attention(f"game control failed: {type(e).__name__}: {e}. "
                                          "Fix the game screen or the agent, then press Resume.")
                    time.sleep(1.0)           # back off: never retry in a tight loop
        finally:
            try:
                self.game.set_paused(True)
            except Exception as e:  # noqa: BLE001 - best effort on the way out
                self.log.emit("episode_error", error=f"could not pause on exit: {e}"[:300])
            self._status("stopped")
            self.log.emit("run_end", decisions=self.log.state.episodes)

    def _start(self) -> dict | None:
        """Pause, set the speed, hand the empire to the AI, first briefing and decision. On failure,
        wait for the human (dashboard Resume) and try again; None if stopped meanwhile."""
        while not self.control.stopping:
            try:
                self.game.set_paused(True)
                self.game.set_speed(self.s.speed)
                # the game's AI must play the empire (human_ai), not observer mode (no expansion)
                self.log.emit("journal", text="taking control: " + self.game.take_control().replace("\n", "; "))
                b = self.game.briefing()
                self._set_campaign(b)
                self._decide(b, "start of run")
                return b
            except Exception as e:  # noqa: BLE001
                self._needs_attention(f"could not start: {type(e).__name__}: {e}. Fix the game or the agent, "
                                      "then press Resume to try again.")
                while self.control.paused and not self.control.stopping:
                    time.sleep(0.5)
        return None

    def _handle_request(self, req: tuple[str, str], b: dict) -> dict:
        """Run one human request (already taken from the queue; the game is paused)."""
        kind, arg = req
        if kind == "decide":
            if arg:
                self.human.push(arg)
            self._decide(b, "human request" + (f": {arg}" if arg else ""))
        elif kind == "override":
            self._override(b, arg)
        elif kind == "speed":
            self.game.set_speed(arg)
            self.s = replace(self.s, speed=arg)
            self.log.state.info["speed"] = arg
            self.log.emit("pace", speed=arg)
        return b

    def _override(self, b: dict, directive: str) -> None:
        self.log.state.episodes += 1
        n = self.log.state.episodes
        current = current_directive(b)
        try:
            self.game.directive(directive)
            outcome = "applied"
            self.last_change = months(b["date"])
            self.log.state.info["directive"] = directive
        except Exception as e:  # noqa: BLE001
            outcome = f"FAILED: {e}"[:200]
        reason = "Directive chosen by the human on the dashboard."
        self.log.state.last_decision = f"{b['date']}: {directive} ({outcome}) — human override"
        self.log.emit("episode", situation="human override", decision=f"{directive}: {reason}", date=b["date"],
                      resolved=outcome == "applied", actions=1, seconds=0, tokens_in=0, tokens_out=0)
        self.log.save_trace(n, {"episode": n, "model": "human", "game": self.s.game, "date": b["date"],
                                "trigger": "human override", "current": current, "decision": directive,
                                "reason": reason, "outcome": outcome, "seconds": 0, "tokens_in": 0, "tokens_out": 0,
                                "steps": [{"type": "text", "text": reason}]})
        self.journal.note(f"{directive} ({outcome}) — human override", b["date"])

    @staticmethod
    def _save_folder(b: dict) -> str | None:
        parts = str(b.get("source", "")).split("/")
        return parts[1] if len(parts) >= 3 else None

    def _set_campaign(self, b: dict) -> None:
        """Campaign = the save folder ('save games/<empire>_<id>/…'), or PILOT_CAMPAIGN."""
        self._folder = self._save_folder(b)
        name = self.s.campaign or self._folder or (b.get("name") or "unknown").replace(" ", "_").lower()
        self.log.set_campaign(self.s.game, name, b.get("name") or "")
        f = self._orders_file()
        if f.exists():
            try:
                self.orders = [str(x) for x in json.loads(f.read_text(encoding="utf-8"))]
            except ValueError:
                self.orders = []
        self.log.state.info["orders"] = list(self.orders)
        if self.log.telemetry is not None:
            try:
                self.plan = self.log.telemetry.latest_plan(self.log.campaign_id or "")
            except Exception as e:  # noqa: BLE001
                self.log.emit("briefing_error", error=f"loading the plan: {e}"[:200])
        self.log.state.info["plan"] = self.plan

    def _run_until_next_decision(self, last: dict) -> tuple[dict | None, str]:
        start = months(last["date"])          # the interval can change mid-wait (dashboard)
        self._status("playing")
        self.game.set_paused(False)
        while True:
            if self.control.stopping:
                return None, "stop"
            if self.control.paused:
                return last, ""                     # the main loop pauses the game; no decision
            if not self.requests.empty():
                self.game.set_paused(True)
                return self.game.briefing(), "request"
            time.sleep(self.s.poll_s)
            try:
                b = self.game.briefing()
            except Exception as e:  # noqa: BLE001 - a save being rotated; try again next poll
                self.log.emit("briefing_error", error=str(e)[:200])
                continue
            folder = self._save_folder(b)
            if folder and getattr(self, "_folder", None) and folder != self._folder:
                # another game was loaded: never act on an empire this run was not started for
                self.game.set_paused(True)
                self._needs_attention(f"the game changed: newest autosave is from {folder!r}, this run governs "
                                      f"{self._folder!r}. Load that game again and press Resume, or stop this run "
                                      "and start a new one for the new game.")
                return last, ""
            if b["date"] != last["date"]:
                self.log.emit("metrics", **metrics(b))
                self.log.state.game_date = b["date"]
                self.log.state.turns_advanced = months(b["date"]) - months(last["date"]) + self.log.state.turns_advanced
            urgent = urgent_changes(last, b)
            if urgent:
                self.game.set_paused(True)
                return b, "urgent: " + "; ".join(urgent)
            if months(b["date"]) >= start + self.s.decide_every_months:
                self.game.set_paused(True)
                return b, f"scheduled ({self.s.decide_every_months} months)"
            last = b

    def _decide(self, b: dict, reason: str) -> None:
        self._status("deciding")
        self.log.state.episodes += 1
        self.log.state.game_date = b["date"]
        self.log.emit("metrics", **metrics(b))
        if self.log.telemetry is not None and self.log.campaign_id:
            try:
                self.log.telemetry.score(self.log.campaign_id)
            except Exception as e:  # noqa: BLE001 - scoring is advisory; never stop play for it
                self.log.emit("briefing_error", error=f"outcome scoring: {e}"[:200])
        try:
            shot = self.game.screenshot()
            if getattr(shot, "image", None):
                self.log.frame(shot.image)
        except Exception as e:  # noqa: BLE001 - the frame is only for the dashboard
            self.log.emit("briefing_error", error=f"screenshot: {e}"[:200])
        current = current_directive(b)
        self.log.state.info["directive"] = current or ""
        held = "" if self.last_change is None else f" (held {months(b['date']) - self.last_change} months)"
        extra = self.human.take_all()
        self.last_briefing = self.game.briefing_text()
        prompt = [f"Decision point: {reason}.",
                  f"Current directive: {current or 'none'}{held}.",
                  "Campaign plan:\n" + (self.plan or "(none yet: write one in `plan`)"),
                  "Briefing from the latest autosave:", self.last_briefing]
        if self.log.telemetry is not None and self.log.campaign_id:
            try:   # given up front, so the model rarely needs a second call for it
                prompt.append("Earlier directive changes in this campaign and what followed 12 months later:\n"
                              + self.log.telemetry.past_outcomes(self.log.campaign_id, limit=6))
            except Exception as e:  # noqa: BLE001
                self.log.emit("briefing_error", error=f"past outcomes: {e}"[:200])
        if self.orders:
            prompt.append("STANDING ORDERS from the human (always follow these): "
                          + " | ".join(f"{i + 1}. {o}" for i, o in enumerate(self.orders)))
        if extra:
            prompt.append("HUMAN INSTRUCTIONS (follow these): " + " | ".join(extra))
        started = time.time()
        deps = GovDeps(self.game, self.store, self.log)
        n = self.log.state.episodes
        base = {"episode": n, "model": self.s.model, "game": self.s.game, "date": b["date"], "trigger": reason,
                "current": current}
        try:
            result = run_with_retry(
                lambda: self.agent.run_sync("\n".join(prompt), deps=deps,
                                            usage_limits=UsageLimits(request_limit=self.s.governor_max_requests)),
                self.s.retry_delays, self._on_retry)
        except Exception as e:  # noqa: BLE001 - keep playing with the current directive
            if isinstance(e, UsageLimitExceeded):
                e = RuntimeError(f"no answer within {self.s.governor_max_requests} model calls; "
                                 f"the current directive ({current or 'none'}) stays")
            self.log.emit("episode_error", error=f"{type(e).__name__}: {e}"[:500])
            self.log.save_trace(n, {**base, "outcome": "error", "error": f"{type(e).__name__}: {e}"[:2000],
                                    "seconds": round(time.time() - started, 1),
                                    "steps": [{"type": "prompt", "text": "\n".join(prompt)}]})
            return
        d, usage = result.output, result.usage
        st = self.log.state
        st.tokens_in += usage.input_tokens or 0
        st.tokens_out += usage.output_tokens or 0
        st.requests += usage.requests or 0
        chosen = d.directive
        applied = "kept"
        if chosen != "keep" and chosen != current:
            if chosen in NEEDS_HUMAN:
                q = f"Apply '{chosen}'? {d.reason}"
                st.pending_question = q
                self.log.emit("question", question=q)
                answer = self.human.ask(q, self.s.ask_human_timeout_s) or ""
                st.pending_question = ""
                self.log.emit("answer", answer=answer or "(no answer)")
                if answer.strip().lower() not in ("y", "yes"):
                    chosen, applied = "keep", f"not applied ({chosen} needs a human yes)"
            if chosen != "keep":
                try:
                    self.game.directive(chosen)
                    applied = "applied"
                    self.last_change = months(b["date"])
                    self.log.state.info["directive"] = chosen
                except Exception as e:  # noqa: BLE001
                    applied = f"FAILED: {e}"[:200]
                    self.log.emit("episode_error", error=f"directive {chosen}: {e}"[:300])
        st.last_decision = f"{b['date']}: {d.directive} ({applied}) — {d.reason}"
        self.log.emit("episode", situation=reason, decision=f"{d.directive}: {d.reason}", date=b["date"],
                      resolved=not applied.startswith("FAILED"), actions=int(applied == "applied"),
                      seconds=round(time.time() - started, 1),
                      tokens_in=usage.input_tokens, tokens_out=usage.output_tokens)
        self.log.save_trace(n, {**base, "decision": d.directive, "reason": d.reason, "outcome": applied,
                                "seconds": round(time.time() - started, 1), "tokens_in": usage.input_tokens,
                                "tokens_out": usage.output_tokens, "steps": serialize(result.all_messages())})
        self.store.add_episode(reason, f"{d.directive} ({applied}): {d.reason}", applied, b["date"])
        self.journal.note(f"{d.directive} ({applied}) — {d.reason}", b["date"])
        if d.note:
            self.journal.note(d.note, b["date"])
        if d.plan.strip():
            self._set_plan(d.plan.strip(), b["date"], "decision")
        self._since_retro += 1
        if self.s.retro_every and self._since_retro >= self.s.retro_every:
            self._retrospective(b)

    def _set_plan(self, text: str, date: str, source: str) -> None:
        text = html.unescape(text)            # models sometimes write "&amp;"; the dashboard escapes on display
        self.plan = text
        self.log.state.info["plan"] = text
        self.log.emit("plan", date=date, source=source, text=text)

    def _retrospective(self, b: dict) -> None:
        """Review plan vs outcomes and standing; revise the plan and record rules learned."""
        self._since_retro = 0
        self._status("deciding")
        self.log.state.episodes += 1
        n = self.log.state.episodes
        tel, cid = self.log.telemetry, self.log.campaign_id
        outcomes = tel.past_outcomes(cid) if tel is not None and cid else "(no telemetry)"
        recent = [e for e in list(self.log.recent) if e["kind"] == "episode"][-10:]
        prompt = ["Retrospective.", "Campaign plan:\n" + (self.plan or "(none)"),
                  "Recent decisions:\n" + "\n".join(f"- {e.get('date')}: {e.get('decision')}" for e in recent),
                  "Directive changes and what followed:\n" + outcomes,
                  "Latest briefing:\n" + self.last_briefing]
        started = time.time()
        base = {"episode": n, "model": self.s.model, "game": self.s.game, "date": b["date"],
                "trigger": f"retrospective after {self.s.retro_every} decisions", "current": current_directive(b)}
        try:
            result = run_with_retry(
                lambda: self.retro_agent.run_sync("\n\n".join(prompt), deps=GovDeps(self.game, self.store, self.log),
                                                  usage_limits=UsageLimits(request_limit=self.s.max_requests_per_episode)),
                self.s.retry_delays, self._on_retry)
        except Exception as e:  # noqa: BLE001 - a failed review never stops play
            self.log.emit("episode_error", error=f"retrospective: {type(e).__name__}: {e}"[:500])
            return
        r, usage = result.output, result.usage
        st = self.log.state
        st.tokens_in += usage.input_tokens or 0
        st.tokens_out += usage.output_tokens or 0
        st.requests += usage.requests or 0
        learned = []
        for rule in r.rules[:3]:
            try:
                self.store.add_rule(rule, f"retrospective {b['date']}")
                learned.append(rule)
                st.learned["rules"] = st.learned.get("rules", 0) + 1
                self.log.emit("learned", category="rules", message="retrospective rule", rule=rule)
            except LearningRejected as e:
                self.log.emit("learn_rejected", category="rules", reason=str(e), rule=rule)
        if r.plan.strip():
            self._set_plan(r.plan.strip(), b["date"], "retrospective")
        self.log.save_trace(n, {**base, "decision": "retrospective", "reason": r.assessment,
                                "outcome": f"{len(learned)} rules learned", "seconds": round(time.time() - started, 1),
                                "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens,
                                "steps": serialize(result.all_messages())})
        self.journal.note(f"Retrospective: {r.assessment}", b["date"])
        self._status("playing")

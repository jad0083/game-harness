"""Stellaris governor loop: the native AI plays the empire in observer mode; the model reads a
briefing from the autosave every few in-game months (or when something urgent happens) and picks
one standing directive. The game is paused while the model decides, so any game speed is safe.

    pause → briefing → decision → (apply directive) → resume at the chosen speed
          → poll autosave briefings until the next decision date, a new war or a new deficit → …
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.usage import UsageLimits

from .agent import HumanChannel, model_settings
from .config import Settings
from .events import EventLog
from .learning import Journal, LearnedStore, LearningRejected
from .trace import serialize

DIRECTIVES = ("expand", "consolidate_economy", "tech_rush", "prepare_war", "defend", "diplomacy_first")
NEEDS_HUMAN = {"prepare_war"}      # strategy.md: only after the human confirmed the target

INSTRUCTIONS = """You are the governor of a Stellaris empire. The game's own AI runs the empire day to day;
you steer it by choosing ONE standing directive, which the harness applies (policies and a flag the
AI keeps). The game is paused while you decide. Answer with `keep` unless the situation changed
materially or the current directive's "leave when" condition holds. Use `consult` for game facts.
Human instructions, when present, override the rules below."""


class GovernorDecision(BaseModel):
    directive: Literal["keep", "expand", "consolidate_economy", "tech_rush", "prepare_war", "defend",
                       "diplomacy_first"] = Field(description="The directive to hold from now on, or 'keep'")
    reason: str = Field(description="One or two sentences citing the briefing numbers that decided it")
    note: str = Field(default="", description="Optional one line for the game journal (war, first colony, crisis...)")


class StellarisGame(Protocol):
    def briefing(self) -> dict: ...
    def briefing_text(self) -> str: ...
    def set_paused(self, paused: bool) -> str: ...
    def set_speed(self, speed: str) -> str: ...
    def directive(self, name: str) -> str: ...
    def log_tail(self, lines: int = 30) -> str: ...
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
            "techs_known": b.get("techs_known"), "wars": len(b.get("wars", [])), "directive": current_directive(b)}


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
    return out


# -- tools ------------------------------------------------------------------------------------

def consult(ctx: RunContext[GovDeps], query: str) -> str:
    """Search the Stellaris reference docs and playbook (costs, requirements, mechanics)."""
    ctx.deps.log.emit("consult", situation=query, past=0)
    return ctx.deps.game.corpus("corpus_search", query=query, limit=5)


def get_doc(ctx: RunContext[GovDeps], record_id: str) -> str:
    """Fetch one doc chunk by id from a consult result, e.g. 'doc:policies#0'."""
    return ctx.deps.game.corpus("corpus_get", id=record_id)


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
        ctx.deps.log.emit("learn_rejected", kind="rules", reason=str(e), rule=rule)
        return f"rejected: {e}"
    ctx.deps.log.state.learned["rules"] = ctx.deps.log.state.learned.get("rules", 0) + 1
    ctx.deps.log.emit("learned", kind="rules", message=msg, rule=rule)
    return msg


def build_governor(s: Settings, briefing: str, model=None) -> Agent[GovDeps, GovernorDecision]:
    return Agent(model or s.model, deps_type=GovDeps, output_type=GovernorDecision,
                 instructions=INSTRUCTIONS + "\n\n" + briefing,
                 tools=[Tool(f) for f in (consult, get_doc, recent_log, past_outcomes, remember_rule)],
                 model_settings=model_settings(s), retries=2)


# -- loop -------------------------------------------------------------------------------------

@dataclass
class Control:
    paused: bool = False
    stopping: bool = False


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
        text += "\n\n" + (settings.corpus_dir / "strategy.md").read_text(encoding="utf-8")
        learned = settings.corpus_dir / "learned" / "strategy.md"
        if learned.exists():
            text += "\n\n## Rules learned in play\n" + learned.read_text(encoding="utf-8")
        self.agent = build_governor(settings, text, model=model)
        self.last_change: int | None = None       # month of the last directive change

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
        self.human.push(text)
        self.log.emit("instruction", text=text)

    def _status(self, status: str) -> None:
        self.log.state.status = status
        self.log.emit("status", status=status)

    def run(self, max_decisions: int | None = None) -> None:
        self.log.state.info.update(game=self.s.game, speed=self.s.speed, every_months=self.s.decide_every_months)
        self.log.emit("run_start", model=self.s.model, game=self.s.game, speed=self.s.speed,
                      every_months=self.s.decide_every_months)
        try:
            self.game.set_paused(True)
            self.game.set_speed(self.s.speed)
            b = self.game.briefing()
            self._set_campaign(b)
            self._decide(b, "start of run")
            while not self.control.stopping:
                if max_decisions is not None and self.log.state.episodes >= max_decisions:
                    break
                if self.control.paused:
                    self.game.set_paused(True)
                    while self.control.paused and not self.control.stopping:
                        time.sleep(0.5)
                    continue
                b, reason = self._run_until_next_decision(b)
                if b is None:
                    break
                self._decide(b, reason)
        finally:
            try:
                self.game.set_paused(True)
            except Exception as e:  # noqa: BLE001 - best effort on the way out
                self.log.emit("episode_error", error=f"could not pause on exit: {e}"[:300])
            self._status("stopped")
            self.log.emit("run_end", decisions=self.log.state.episodes)

    def _set_campaign(self, b: dict) -> None:
        """Campaign = the save folder ('save games/<empire>_<id>/…'), or PILOT_CAMPAIGN."""
        name = self.s.campaign
        if not name:
            parts = str(b.get("source", "")).split("/")
            name = parts[1] if len(parts) >= 3 else (b.get("name") or "unknown").replace(" ", "_").lower()
        self.log.set_campaign(self.s.game, name)

    def _run_until_next_decision(self, last: dict) -> tuple[dict | None, str]:
        due = months(last["date"]) + self.s.decide_every_months
        self._status("playing")
        self.game.set_paused(False)
        while True:
            if self.control.stopping:
                return None, "stop"
            if self.control.paused:
                return last, "paused by the human"
            time.sleep(self.s.poll_s)
            try:
                b = self.game.briefing()
            except Exception as e:  # noqa: BLE001 - a save being rotated; try again next poll
                self.log.emit("briefing_error", error=str(e)[:200])
                continue
            if b["date"] != last["date"]:
                self.log.emit("metrics", **metrics(b))
                self.log.state.game_date = b["date"]
                self.log.state.turns_advanced = months(b["date"]) - months(last["date"]) + self.log.state.turns_advanced
            urgent = urgent_changes(last, b)
            if urgent:
                self.game.set_paused(True)
                return b, "urgent: " + "; ".join(urgent)
            if months(b["date"]) >= due:
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
        prompt = [f"Decision point: {reason}.",
                  f"Current directive: {current or 'none'}{held}.",
                  "Briefing from the latest autosave:", self.game.briefing_text()]
        if extra:
            prompt.append("HUMAN INSTRUCTIONS (follow these): " + " | ".join(extra))
        started = time.time()
        deps = GovDeps(self.game, self.store, self.log)
        n = self.log.state.episodes
        base = {"episode": n, "model": self.s.model, "game": self.s.game, "date": b["date"], "trigger": reason,
                "current": current}
        try:
            result = self.agent.run_sync("\n".join(prompt), deps=deps,
                                         usage_limits=UsageLimits(request_limit=self.s.max_requests_per_episode))
        except Exception as e:  # noqa: BLE001 - keep playing with the current directive
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
                if not answer.strip().lower().startswith("y"):
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

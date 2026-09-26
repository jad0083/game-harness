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
from pydantic_ai.messages import ModelResponse
from pydantic_ai.usage import UsageLimits

from .agent import HumanChannel, model_settings, run_with_retry
from .config import Settings
from .events import EventLog
from .learning import Journal, LearnedStore, LearningRejected
from .strategy import Strategy, keep_pinned, milestone_status, validate
from .trace import serialize

DIRECTIVES = ("expand", "consolidate_economy", "tech_rush", "prepare_war", "defend", "diplomacy_first")
NEEDS_HUMAN = {"prepare_war"}      # strategy.md: only after the human confirmed the target

# Big-event triggers: an urgent decision whose reason contains one of these, or a set
# review_requested (a failed review pending retry, or an off-frame decision), starts a strategy
# review (capped at one per 12 in-game months unless it is a retry or no strategy exists yet).
EVENT_TRIGGERS = ("new war", "war ended", "crisis", "colony lost", "boxed in", "milestone missed",
                  "off-frame", "military fell")

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


class StrategyReview(BaseModel):
    change: bool = Field(description="false when the current strategy should stay as it is")
    strategy: Strategy | None = Field(default=None, description="the full new strategy when change is true")
    assessment: str = Field(description="what worked and what did not since the last review, citing numbers")
    rules: list[str] = Field(default_factory=list, description="0-3 general rules learned (situation -> choice)")


STRATEGY_INSTRUCTIONS = """You are the Strategist: you set the empire's top-down strategy, one entry per pillar
(economy, expansion, technology, diplomacy, defence, government, society). Each pillar: a unique priority
(1 = first), a stance of one or two sentences, 1-3 goals, milestones on the briefing's measures
(systems, colonies, pops, techs_known, military_power, economy_power, tech_power, rank:<measure>) with a
target and an in-game date, and only for technology `prefer_techs` (tech ids to pick when offered; at most 6)
and only for economy `market` (at most 2 small monthly orders; sell only a resource the briefing lists as
IDLE, at most 20% of its monthly income). Priorities decide which directives the governor prefers.
Everything must be achievable through directives, tech picks or market orders: the game's AI builds,
designs ships and moves fleets. Never change a pillar marked pinned: the human set it. If nothing
material changed, answer change=false. Build on the empire's species, ethics, civics and origin.
While at war, the defence stance must name its exit condition (peace, war exhaustion, or planets retaken). When a hostile neighbour's military is twice ours or more, a defence goal is two shipyards in different systems and alloy production on two or more planets; never reason from a naval-capacity cap the briefing does not show."""


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
            "techs_known": b.get("techs_known"), "wars": len(b.get("wars", [])), "directive": current_directive(b),
            "neighbours": [{"name": n.get("name"), "military": n.get("military"), "economy": n.get("economy"),
                            "tech": n.get("tech"), "systems": n.get("systems"), "opinion": n.get("opinion_theirs"),
                            "status": n.get("status", [])} for n in b.get("neighbours", [])]}


def served_model(result) -> str:
    """The model version(s) that answered, as the provider reported them: an alias such as
    gemini-pro-latest comes back as the release it points to (e.g. gemini-3.1-pro-preview)."""
    names = []
    for m in result.all_messages():
        name = getattr(m, "model_name", None) if isinstance(m, ModelResponse) else None
        if name and name not in names:
            names.append(name)
    return ", ".join(names)


def trends(old: dict | None, now: dict) -> str:
    """One line comparing two metrics snapshots (about 12 months apart), for the decision prompt.

    Flags alloys piling up while military stays flat, and military falling by half or more. The
    save has no naval-capacity maximum, so neither flag names a cause it cannot show."""
    if not old:
        return ""
    span = months(now["date"]) - months(old["date"])
    def d(key: str) -> float:
        return (now.get(key) or 0) - (old.get(key) or 0)
    med = lambda m, key: ((m.get("peers") or {}).get(key) or {}).get("median") or 0
    parts = [f"systems {d('systems'):+.0f}", f"pops {d('pops'):+.0f}",
             f"military {d('military_power'):+.0f} (the others' median {med(now, 'military_power') - med(old, 'military_power'):+.0f})",
             f"tech power {d('tech_power'):+.0f}"]
    a_old, a_now = (old.get("stockpile") or {}).get("alloys", 0), (now.get("stockpile") or {}).get("alloys", 0)
    parts.append(f"alloy stock {a_now - a_old:+.0f}")
    line = f"Change since {old['date']} ({span} months): " + ", ".join(parts) + "."
    mil_old = old.get("military_power") or 0
    if a_now > 1000 and a_now > 1.5 * max(a_old, 1) and d("military_power") < 0.1 * max(mil_old, 1):
        line += (" ALLOYS PILING UP while military is flat: the AI is not converting alloys into ships."
                 " Causes include lost or occupied shipyards, ship losses, and the fleet cap; the save has"
                 " no naval-capacity maximum, so do not assume the cap.")
    if mil_old > 0 and d("military_power") <= -0.5 * mil_old:
        line += (f" MILITARY FELL {-d('military_power') / mil_old:.0%}: ships were lost (battles, monsters)"
                 " or could not be rebuilt (occupied shipyards, alloy income); this is not a capacity cap.")
    return line


def _num(v) -> str:
    """Readable number for reasons: 405.92577500000004 -> '406', 1.0 -> '1', 12.34 -> '12.3'."""
    if not isinstance(v, (int, float)):
        return str(v)
    return f"{v:.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:.1f}"


def idle_resources(b: dict) -> set[str]:
    """Resources the briefing would flag IDLE: large stock, positive net, over 10 years of income (trade: > 15,000)."""
    out = set()
    for k, v in (b.get("stockpile") or {}).items():
        n = (b.get("net") or {}).get(k, 0)
        if (k == "trade" and v > 15000 and n > 0) or (v > 5000 and n > 0 and v > n * 120):
            out.add(k)
    return out


def urgent_changes(before: dict, now: dict) -> list[str]:
    """Reasons to decide before the scheduled date: a new war, or a resource turning negative."""
    out = []
    old_wars = {w["name"] for w in before.get("wars", [])}
    new_wars = {w["name"] for w in now.get("wars", [])}
    for w in now.get("wars", []):
        if w["name"] not in old_wars:
            out.append(f"new war: {w['name']} (we are {'attacker' if w.get('attacker') else 'defender'})")
    for name in sorted(old_wars - new_wars):
        out.append(f"war ended: {name}")
    old_crises = {c[1] for c in (before.get("galaxy") or {}).get("crises", [])}
    for kind, name, *_ in (now.get("galaxy") or {}).get("crises", []):
        if name not in old_crises:
            out.append(f"crisis: {name} ({kind}) appeared")
    old_planets, new_planets = len(before.get("planets", [])), len(now.get("planets", []))
    if new_planets < old_planets:
        out.append(f"colony lost: {old_planets} -> {new_planets}")
    old_room = (before.get("expansion") or {}).get("reach_unclaimed")
    new_room = (now.get("expansion") or {}).get("reach_unclaimed")
    if old_room is not None and old_room > 0 and new_room == 0:
        out.append("boxed in")
    mil_before, mil_now = before.get("military_power") or 0, now.get("military_power")
    if mil_before > 0 and mil_now is not None and mil_now <= 0.5 * mil_before:
        out.append(f"military fell: {round(mil_before)} -> {round(mil_now)}")
    for res, net in now.get("net", {}).items():
        if net < 0 <= before.get("net", {}).get(res, 0):
            out.append(f"{res} net turned negative ({net:+.1f}/month)")
    was_behind = set((before.get("peers") or {}).get("behind", []))
    for m in (now.get("peers") or {}).get("behind", []):
        if m not in was_behind:
            st = now["peers"]["stats"].get(m, {})
            out.append(f"falling behind other empires in {m} ({_num(st.get('ours'))} vs median {_num(st.get('median'))})")
    return out


def frame_text(strategy: Strategy | None, milestones: str) -> str:
    """The strategy frame shown to a decision: the pillar ranking, focus, stances and any
    at-risk/missed milestones, replacing the old free-text campaign plan."""
    if strategy is None:
        return ""
    lines = ["STRATEGY FRAME (from the Strategist; choose within it):",
             f"Directive ranking: {' > '.join(strategy.ranking())}", f"Focus: {strategy.focus}"]
    for name, pl in sorted(strategy.pillars.items(), key=lambda kv: kv[1].priority):
        lines.append(f"{pl.priority}. {name}{' (pinned by the human)' if pl.pinned else ''}: {pl.stance}")
    at_risk = [m for m in milestones.splitlines() if m.endswith(("at_risk", "missed"))]
    if at_risk:
        lines.append("Milestones at risk or missed:\n" + "\n".join(at_risk))
    lines.append("Pick the highest-ranked directive that fits the briefing, or keep. Choose a directive outside "
                 "this ranking only for an urgent line (new war, deficit, crisis) and say so in the reason.")
    return "\n".join(lines)


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


# Playbook sections every decision needs (matched in the `## ` heading); the rest are consulted.
CORE_SECTIONS = ("directive", "lessons from play", "identity")


def strategy_core(strategy: str) -> str:
    """The part of strategy.md every decision needs (the directives section), plus a table of contents
    for the rest, which the model reads with `consult` when a topic comes up. Keeps the fixed
    instructions short (and identical between calls, so providers can cache them)."""
    parts = re.split(r"(?m)^(?=## )", strategy)
    head, sections = parts[0], parts[1:]
    core = [s for s in sections if any(w in s.splitlines()[0].lower() for w in CORE_SECTIONS)]
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
    def __init__(self, settings: Settings, game: StellarisGame, log: EventLog, model=None, fallback=None,
                 role_models: dict | None = None):
        self.s = settings
        # tried once when the main model is still overloaded after the retries (503 high demand)
        self._fallback_obj = fallback
        self._role_objs = dict(role_models or {})     # role -> Model instance (tests)
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
        self.strategy: Strategy | None = None     # the pillar strategy (Strategist), per campaign
        self.review_requested: str | None = None  # pending review trigger after a failed strategy call
        self._since_retro = 0
        self._strategy_trace_n = 0                # negative episode ids for strategy review traces (see _review_strategy)
        self.orders: list[str] = []               # standing orders, saved per campaign
        self.requests: queue.Queue[tuple[str, str]] = queue.Queue()   # ("decide", msg) | ("override", name)
        log.state.info["controls"] = ["instruct", "chat", "order_add", "order_remove", "decide_now", "override",
                                      "set_model", "set_models", "set_roles", "set_fallback", "set_speed", "set_months"]
        log.state.info["thinking"] = settings.governor_thinking
        log.state.info["pool"] = settings.pool()
        log.state.info["rotate"] = settings.rotate
        log.state.info["roles"] = dict(settings.roles or {})
        log.state.info["directives"] = list(DIRECTIVES)

    # ---- model pool ----------------------------------------------------------------------------

    def _pool(self, role: str = "decisions") -> list[dict]:
        """A role's models in order ({"model", "thinking", "obj"}); roles without their own use the
        decision models. `obj` is a Model instance in tests."""
        if role != "decisions":
            if role in self._role_objs:
                obj = self._role_objs[role]
                return [{"model": getattr(obj, "model_name", role), "thinking": self.s.governor_thinking, "obj": obj}]
            own = (self.s.roles or {}).get(role)
            if own and own.get("models"):
                return [dict(m) for m in own["models"]]
        pool = self.s.pool()
        if self._model_obj is not None:
            pool[0] = {**pool[0], "obj": self._model_obj}
        if self._fallback_obj is not None:
            pool = [pool[0], {"model": getattr(self._fallback_obj, "model_name", "fallback"),
                              "thinking": pool[0]["thinking"], "obj": self._fallback_obj}]
        return pool

    def _rotates(self, role: str) -> bool:
        own = (self.s.roles or {}).get(role) if role != "decisions" else None
        return bool(own["rotate"]) if own and own.get("models") else bool(self.s.rotate)

    def _build(self, role: str, settings: Settings, model):
        text = self._text
        if role == "strategy":
            return Agent(model, deps_type=GovDeps, output_type=StrategyReview, instructions=STRATEGY_INSTRUCTIONS + "\n\n" + text,
                         tools=[Tool(f) for f in (consult, get_doc)], model_settings=governor_settings(settings), retries=2)
        if role == "chat":
            return Agent(model, deps_type=GovDeps, output_type=str, instructions=CHAT_INSTRUCTIONS + "\n\n" + text,
                         tools=[Tool(f) for f in (consult, get_doc, recent_log, past_outcomes)],   # read-only
                         model_settings=governor_settings(settings), retries=2)
        return build_governor(settings, text, model=model)

    def _agent_for(self, entry: dict, role: str = "decisions"):
        """The agent for one role and model entry, built once per (role, model, thinking)."""
        key = (role, entry.get("obj") and id(entry["obj"]), entry["model"], entry["thinking"])
        cache = self.__dict__.setdefault("_agents", {})
        if key not in cache:
            model = entry.get("obj") or entry["model"]
            settings = replace(self.s, governor_thinking=entry["thinking"],
                               model=entry["model"] if isinstance(model, str) else self.s.model)
            cache[key] = self._build(role, settings, model)
        return cache[key]

    def _order(self, role: str = "decisions") -> list[dict]:
        """This call's models: the role's list as given, or one further on each time (take turns)."""
        pool = self._pool(role)
        if not self._rotates(role) or len(pool) < 2:
            return pool
        turns = self.__dict__.setdefault("_turns", {})
        turn = turns.get(role, 0)
        turns[role] = turn + 1
        i = turn % len(pool)
        return pool[i:] + pool[:i]

    def _call(self, role: str, ask, on_try=None):
        """Run `ask(agent)` on the role's models in order. Overload (503/429/timeouts) is retried on
        the first model; any failure (overload after the retries, a bad key, a missing model, an
        unusable answer) moves on to the next model. A model that failed sits behind the others for
        `model_cooldown_s`, so a sustained outage does not cost the retry waits every time.
        Returns (result, entry used)."""
        failed = self.__dict__.setdefault("_failed_at", {})
        now = time.time()
        cooling = lambda e: now - failed.get(e["model"], 0) < self.s.model_cooldown_s
        order = sorted(self._order(role), key=cooling)       # stable: the configured order otherwise
        for i, entry in enumerate(order):
            if on_try:
                on_try(entry)
            agent = self._agent_for(entry, role)
            try:
                result = (run_with_retry(lambda agent=agent: ask(agent), self.s.retry_delays, self._on_retry)
                          if i == 0 and not cooling(entry) else ask(agent))
                failed.pop(entry["model"], None)
                return result, entry
            except Exception as e:
                failed[entry["model"]] = time.time()
                if i == len(order) - 1:
                    raise
                self.log.emit("model_fallback", role=role, model=entry["model"],
                              error=f"{type(e).__name__}: {e}"[:300], fallback=order[i + 1]["model"])
        raise RuntimeError(f"no models for {role}")

    def set_roles(self, roles: dict) -> None:
        """Give roles their own models ({role: {"models", "rotate"}}); None = use the decision models."""
        from .models import check_roles
        merged = {**(self.s.roles or {}), **{k: v for k, v in roles.items()}}
        clean = check_roles({k: v for k, v in merged.items() if v})
        check_roles({k: v for k, v in roles.items() if v})      # reject unknown roles in the request
        self.s = replace(self.s, roles=clean)
        self.__dict__.pop("_agents", None)
        self.log.state.info["roles"] = clean
        self.log.emit("roles", roles=clean)

    def set_models(self, models: list[dict], rotate: bool | None = None) -> None:
        """Replace the model pool (each with its thinking level) and whether they take turns."""
        from .models import check_pool
        pool = check_pool(models)
        self.s = replace(self.s, models=tuple(pool), model=pool[0]["model"], governor_thinking=pool[0]["thinking"],
                         rotate=self.s.rotate if rotate is None else bool(rotate))
        self._model_obj = self._fallback_obj = None
        self.__dict__.pop("_agents", None)
        self._build_agents()
        self.log.state.model = pool[0]["model"]
        self.log.state.info.update(pool=pool, rotate=self.s.rotate, thinking=pool[0]["thinking"])
        self.log.emit("models", models=pool, rotate=self.s.rotate)

    def set_fallback(self, model: str | None) -> None:
        """Older control: the pool becomes the first model plus this one ("none": the first alone)."""
        first = self.s.pool()[0]
        pool = [first] if model in (None, "", "none") else [first, {"model": model, "thinking": first["thinking"]}]
        self.set_models(pool)

    def _build_agents(self) -> None:
        """(Re)build the decision and chat agents for the current model settings."""
        m, s, text = self._model_obj or self.s.model, self.s, self._text
        self.agent = build_governor(s, text, model=m)
        self.chat_agent: Agent[GovDeps, str] = Agent(
            m, deps_type=GovDeps, output_type=str, instructions=CHAT_INSTRUCTIONS + "\n\n" + text,
            tools=[Tool(f) for f in (consult, get_doc, recent_log, past_outcomes)],   # read-only
            model_settings=governor_settings(s), retries=2)

    def set_model(self, model: str, thinking: str | None = None) -> None:
        """Older control: replace the first model of the pool (the others stay)."""
        from .models import THINKING, valid_model
        if not valid_model(model):
            raise ValueError(f"not a model name: {model!r} (expected provider:name)")
        if thinking is not None and thinking not in THINKING:
            raise ValueError(f"thinking must be one of {', '.join(THINKING)}")
        pool = self.s.pool()
        pool[0] = {"model": model, "thinking": thinking or pool[0]["thinking"]}
        self.set_models(pool)
        self.log.emit("model", model=model, thinking=pool[0]["thinking"])

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
                result, _ = self._call("chat", lambda agent: agent.run_sync(
                    "\n\n".join(ctx), deps=GovDeps(self.game, self.store, self.log),
                    message_history=self._chat_history() or None, usage_limits=UsageLimits(request_limit=8)))
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
        what = (f"model {e.model_name} answered {e.status_code}" if hasattr(e, "status_code")
                else f"model request timed out after {self.s.model_timeout_s:.0f} s ({type(e).__name__})")
        self.log.emit("model_retry", error=what, delay=delay, attempt=attempt)

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
                        # a review already pending (a failed review, or an earlier off-frame tag) is a
                        # retry; a freshly off-frame-tagged decision waits for the *next* decision point
                        # instead of reviewing inline, so its own trace/choice is not re-litigated at once
                        pending = self.review_requested is not None
                        self._decide(b, reason)
                        if pending or (reason.startswith("urgent:") and any(t in reason for t in EVENT_TRIGGERS)):
                            self._maybe_event_review(b, self.review_requested or reason, retry=pending)
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

    def _fresh_briefing(self) -> dict:
        """The newest autosave, made fresh if it is old: a new or just-loaded game has none of its own
        yet, so the newest save may belong to another campaign. Then play until the game writes one
        (at most `fresh_save_wait_s`), so the first decision never acts on the wrong briefing."""
        b = self.game.briefing()
        modified = b.get("source_modified")
        if not isinstance(modified, (int, float)) or time.time() - modified < self.s.stale_save_s:
            return b
        self.log.emit("journal", text=f"newest autosave is {(time.time() - modified) / 60:.0f} minutes old "
                                      "(a new or just-loaded game?): playing until a fresh autosave is written")
        self.game.set_paused(False)
        deadline = time.time() + self.s.fresh_save_wait_s
        try:
            while time.time() < deadline and not self.control.stopping:
                time.sleep(self.s.poll_s)
                nb = self.game.briefing()
                if nb.get("source") != b.get("source"):
                    return nb
        finally:
            self.game.set_paused(True)
        raise RuntimeError("no fresh autosave appeared; is the game running and unpaused?")

    def _start(self) -> dict | None:
        """Pause, set the speed, hand the empire to the AI, first briefing and decision. On failure,
        wait for the human (dashboard Resume) and try again; None if stopped meanwhile."""
        while not self.control.stopping:
            try:
                self.game.set_paused(True)
                self.game.set_speed(self.s.speed)
                # the game's AI must play the empire (human_ai), not observer mode (no expansion)
                self.log.emit("journal", text="taking control: " + self.game.take_control().replace("\n", "; "))
                b = self._fresh_briefing()
                self._set_campaign(b)
                reviewed = self.strategy is None
                if reviewed:
                    self._review_strategy(b, "start of run")
                self._decide(b, "start of run", reviewed_at_start=reviewed)
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
            try:
                raw = self.log.telemetry.latest_strategy(self.log.campaign_id or "")
                self.strategy = Strategy.model_validate(raw) if raw else None
            except Exception as e:  # noqa: BLE001
                self.log.emit("briefing_error", error=f"loading the strategy: {e}"[:200])
        self.log.state.info["plan"] = self.plan
        self.log.state.info["strategy"] = self.strategy.model_dump() if self.strategy else None

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

    def _trend(self, b: dict) -> str:
        """Compare with this campaign's metrics from about 12 months ago (telemetry)."""
        if self.log.telemetry is None or not self.log.campaign_id:
            return ""
        try:
            rows = self.log.telemetry.query(
                "SELECT data FROM metrics WHERE campaign_id=? AND month IS NOT NULL AND month <= ? ORDER BY month DESC LIMIT 1",
                (self.log.campaign_id, months(b["date"]) - 12))
            return trends(json.loads(rows[0]["data"]) if rows else None, metrics(b))
        except Exception as e:  # noqa: BLE001 - trends are advisory
            self.log.emit("briefing_error", error=f"trends: {e}"[:200])
            return ""

    def _decide(self, b: dict, reason: str, reviewed_at_start: bool = False) -> None:
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
                  frame_text(self.strategy, self._milestones_text()) or "No strategy yet.",
                  "Briefing from the latest autosave:", self.last_briefing]
        trend = self._trend(b)
        if trend:
            prompt.append(trend)
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
        base = {"episode": n, "model": self.s.model, "thinking_level": self.s.governor_thinking, "game": self.s.game,
                "date": b["date"], "trigger": reason, "current": current}
        def ask(agent):
            return agent.run_sync("\n".join(prompt), deps=deps,
                                  usage_limits=UsageLimits(request_limit=self.s.governor_max_requests))
        try:
            result, _ = self._call("decisions", ask,
                                   on_try=lambda e: base.update(model=e["model"], thinking_level=e["thinking"]))
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
        base["model_version"] = served_model(result)
        st = self.log.state
        st.tokens_in += usage.input_tokens or 0
        st.tokens_out += usage.output_tokens or 0
        st.requests += usage.requests or 0
        chosen = d.directive
        ranked = self.strategy.ranking() if self.strategy else []
        off_frame = bool(ranked) and chosen not in ("keep", current) and chosen not in ranked[:2]
        if off_frame:
            self.review_requested = f"off-frame decision: {chosen} ({reason})"
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
                                "off_frame": off_frame, "seconds": round(time.time() - started, 1),
                                "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens,
                                "steps": serialize(result.all_messages())})
        self.store.add_episode(reason, f"{d.directive} ({applied}): {d.reason}", applied, b["date"])
        self.journal.note(f"{d.directive} ({applied}) — {d.reason}", b["date"])
        if d.note:
            self.journal.note(d.note, b["date"])
        if not (reason == "start of run" and reviewed_at_start):   # a review just ran for this decision point
            self._since_retro += 1
            if self.s.retro_every and self._since_retro >= self.s.retro_every:
                self._review_strategy(b, f"scheduled after {self.s.retro_every} decisions")

    def _maybe_event_review(self, b: dict, trigger: str, retry: bool = False) -> bool:
        """Run a strategy review for a big event, at most once per 12 in-game months. `retry`
        (a failed review pending retry) and having no strategy yet both bypass the cap and never
        move its last-review month: only event-triggered reviews count toward it."""
        bypass = retry or self.strategy is None
        last = getattr(self, "_last_event_review_month", None)
        now = months(b["date"])
        if not bypass and last is not None and now - last < 12:
            return False
        if not bypass:
            self._last_event_review_month = now
        self._review_strategy(b, trigger)
        return True

    def _set_plan(self, text: str, date: str, source: str) -> None:
        text = html.unescape(text)            # models sometimes write "&amp;"; the dashboard escapes on display
        self.plan = text
        self.log.state.info["plan"] = text
        self.log.emit("plan", date=date, source=source, text=text)

    def _milestones_text(self) -> str:
        if not self.strategy or self.log.telemetry is None or not self.log.campaign_id:
            return "(none)"
        try:
            rows = self.log.telemetry.metrics_rows(self.log.campaign_id)
        except Exception as e:  # noqa: BLE001 - telemetry is advisory; never block a review
            self.log.emit("briefing_error", error=f"milestones: {e}"[:200])
            return "(none)"
        today = rows[-1]["date"] if rows else "2200.01.01"
        out = []
        for name, pl in sorted(self.strategy.pillars.items(), key=lambda kv: kv[1].priority):
            for m in pl.milestones:
                out.append(f"- {name}: {m.metric} {m.op} {m.target:g} by {m.by}: {milestone_status(m, rows, today)}")
        return "\n".join(out) or "(none)"

    def _past_outcomes_text(self) -> str:
        if self.log.telemetry is None or not self.log.campaign_id:
            return "(none)"
        try:
            return self.log.telemetry.past_outcomes(self.log.campaign_id)
        except Exception as e:  # noqa: BLE001 - telemetry is advisory; never block a review
            self.log.emit("briefing_error", error=f"strategy review outcomes: {e}"[:200])
            return "(none)"

    def _review_strategy(self, b: dict, trigger: str, retried: bool = False, errors: list[str] | None = None) -> None:
        """Strategist review: may keep the strategy or write a new version (pinned pillars stay). An invalid
        answer (including change=true with no strategy) is retried once with the reasons; still invalid →
        no change. Never raises and never pauses the game: any failure past the model call is logged and
        the current strategy stays, exactly like a failed model call."""
        self._since_retro = 0
        self.review_requested = None
        started = time.time()
        current = self.strategy.model_dump_json(indent=1) if self.strategy else "(none yet: write the first strategy)"
        prompt = [f"Strategy review, trigger: {trigger}.", "Current strategy:\n" + current,
                  "Milestones (status computed from the recorded numbers):\n" + self._milestones_text(),
                  "Directive changes and what followed:\n" + self._past_outcomes_text(),
                  "Latest briefing:\n" + (self.last_briefing or self.game.briefing_text())]
        if errors:
            prompt.insert(0, "Your previous answer was rejected: " + "; ".join(errors) + ". Fix exactly these problems.")
        trend = self._trend(b)
        if trend:
            prompt.append(trend)
        deps = GovDeps(self.game, self.store, self.log)
        base = {"model": self.s.model, "thinking_level": self.s.governor_thinking, "game": self.s.game,
                "date": b["date"], "trigger": trigger, "current": current_directive(b)}
        ask = lambda agent: agent.run_sync("\n\n".join(prompt), deps=deps,
                                           usage_limits=UsageLimits(request_limit=self.s.max_requests_per_episode))
        try:
            result, _entry = self._call("strategy", ask,
                                        on_try=lambda e: base.update(model=e["model"], thinking_level=e["thinking"]))
        except Exception as e:  # noqa: BLE001 - a failed review never stops play; retried at the next decision
            self.review_requested = trigger
            self.log.emit("episode_error", error=f"strategy review: {type(e).__name__}: {e}"[:500])
            return
        retry_errors: list[str] | None = None
        try:
            r: StrategyReview = result.output
            usage = result.usage
            base["model_version"] = served_model(result)
            st = self.log.state
            st.tokens_in += usage.input_tokens or 0
            st.tokens_out += usage.output_tokens or 0
            st.requests += usage.requests or 0
            for rule in r.rules[:3]:
                try:
                    self.store.add_rule(rule, f"strategy review {b['date']}")
                    st.learned["rules"] = st.learned.get("rules", 0) + 1
                    self.log.emit("learned", category="rules", message="strategy review rule", rule=rule)
                except LearningRejected as e:
                    self.log.emit("learn_rejected", category="rules", reason=str(e), rule=rule)

            new: Strategy | None = None
            if r.change and r.strategy is None:
                errs = ["change=true but no strategy given"]
            elif r.change and r.strategy is not None:
                new = keep_pinned(r.strategy, self.strategy)
                errs = validate(new, previous=self.strategy, tech_ids=self._tech_ids(), idle=idle_resources(b),
                                income=b.get("net", {}))
            else:
                errs = []
            accepted = bool(r.change and new is not None and not errs)

            # Negative, strictly decreasing "episode" (file traces/-0001.json, ...): it can never collide with a
            # real decision's own (positive) episode number in the same run. Readers that mean "directive
            # decisions" (past_outcomes, score, the dashboard's campaign/decisions APIs) filter this row out by
            # `decision == 'strategy_review'`; only a lookup by exact (run_id, episode) is expected to see it.
            self._strategy_trace_n -= 1
            n = self._strategy_trace_n
            outcome = "accepted" if accepted else (("rejected: " + "; ".join(errs))[:300] if errs else "no change")
            self.log.save_trace(n, {**base, "episode": n, "decision": "strategy_review", "reason": r.assessment,
                                    "outcome": outcome, "seconds": round(time.time() - started, 1),
                                    "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens,
                                    "steps": serialize(result.all_messages())})
            self.log.emit("strategy_review", date=b["date"], trigger=trigger, change=r.change, accepted=accepted,
                          assessment=r.assessment[:2000], model=base.get("model"))
            self.journal.note(f"Strategy review ({trigger}): {outcome} — {r.assessment}", b["date"])

            if errs and not retried:
                retry_errors = errs             # one corrective retry: the model sees exactly what was wrong
            elif errs:
                self.log.emit("strategy_rejected", date=b["date"], errors=errs[:10])
            elif accepted:
                self._set_strategy(new, b["date"], trigger, base.get("model", ""))
        except Exception as e:  # noqa: BLE001 - a failed review never stops play or pauses the game
            self.review_requested = trigger
            self.log.emit("episode_error", error=f"strategy review: {type(e).__name__}: {e}"[:500])
            return
        if retry_errors is not None:
            self._review_strategy(b, trigger, retried=True, errors=retry_errors)

    def _set_strategy(self, s: Strategy, date: str, trigger: str, model: str) -> None:
        self.strategy = s
        self.log.state.info["strategy"] = s.model_dump()
        self.log.emit("strategy", date=date, trigger=trigger, model=model, reason=s.reason, strategy=s.model_dump())

    def _tech_ids(self) -> set[str]:
        """Tech ids from the corpus (for validating preferred techs); cached once a read succeeds
        (a failed read is logged and retried on the next call, never cached as empty)."""
        if getattr(self, "_techs", None) is not None:
            return self._techs
        import json as _json
        path = self.s.corpus_dir / "data" / "tech.json"
        try:
            techs = {r["id"].split(":", 1)[1] for r in _json.loads(path.read_text(encoding="utf-8"))}
        except (OSError, ValueError, KeyError) as e:
            self.log.emit("briefing_error", error=f"tech ids: {e}"[:200])
            return set()
        self._techs = techs
        return techs

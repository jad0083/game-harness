"""Stellaris governor loop: the native AI plays the empire in observer mode; the model reads a
briefing from the autosave every few in-game months (or when something urgent happens) and picks
one standing directive. The game is paused while the model decides, so any game speed is safe.

    pause → briefing → decision → (apply directive) → resume at the chosen speed
          → poll autosave briefings until the next decision date, a new war or a new deficit → …
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import queue
import re
import statistics
import threading
import time
import tomllib
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse
from pydantic_ai.usage import UsageLimits

from .agent import HumanChannel, model_settings, run_with_retry
from .claude_code import resolve_model
from .config import Settings
from .events import EventLog
from .learning import Journal, LearnedStore, LearningRejected
from .pillars import ACTION_KINDS, OrdersSpec, PillarsError, PillarSpec, load_pillars
from .stellaris_record import (
    NO_OP_PREFIX,
    OPEN,
    action_record,
    action_record_text,
    directive_action,
    judge,
    market_action,
    market_suspended,
    outcome_row,
    parse_directive_reply,
    posture_action,
    review_outcome,
    supersede,
    tech_action,
)
from .strategy import (
    Strategy,
    apply_aliases,
    directive_pressure,
    directive_record,
    keep_pinned,
    market_briefing_errors,
    milestone_status,
    pinned_misfits,
    pressures,
    rebalance,
    review_model,
    shares,
    strategist_instructions,
    strategy_for_prompt,
    suggestion,
    to_strategy,
    validate,
)
from .trace import serialize

DIRECTIVES = ("expand", "consolidate_economy", "tech_rush", "prepare_war", "defend", "diplomacy_first")
NEEDS_HUMAN = {"prepare_war"}      # strategy.md: only after the human confirmed the target

# Big-event triggers: an urgent decision whose reason contains one of these, or a pending
# review_requested (an off-frame decision, or a failed review awaiting retry), starts a strategy
# review, capped at one per 12 in-game months; only a failed review's own retry, or a review while
# no strategy exists yet, bypasses that cap.
EVENT_TRIGGERS = ("new war", "war ended", "crisis", "colony lost", "boxed in", "milestone missed",
                  "off-frame", "military fell")

# The tool's own reply names the tech it actually picked ("picked <id> in <field>", or "clicked
# <id> in <field> (option n); unverified until the next autosave …"); a reply that matches neither
# form (e.g. "nothing to pick: …") leaves no tech to watch.
TECH_PICK_RE = re.compile(r"^(?:picked|clicked) (\S+) in (\w+)")
# stellaris_market_sync names each add it refused for want of a measured start amount (alloys and
# sr_* until live check L2) as "not added (start amount not measured): buy alloys 5, sell sr_zro 1";
# removals and the other adds went ahead, except a current order of a refused side and resource,
# which it kept at its amount ("kept (start amount not measured): buy alloys 7"; see _kept_for).
MARKET_REFUSED_RE = re.compile(r"not added \(start amount not measured\): ([^;]+)")

# The action record (docs/design/2026-09-27-stellaris-levers-design.md, rulings 2-6): heading of its
# section in the decision prompt and the Strategist's review.
ACTION_RECORD_HEADING = ("Action record in this campaign (each directive, tech pick, market order and posture followed in "
                         "the saves until it resolves):")


def market_calibration(corpus_dir: Path) -> str:
    """A hash of the `[ui.market]` positions the controller clicks with (the manifest's table, and
    `res/<W>x<H>.toml`'s under GAME_RESOLUTION): a market suspension holds only while it is the same
    (ruling 6), so a recalibration commit lifts it."""
    table: dict = {}
    try:
        table = dict(tomllib.loads((Path(corpus_dir) / "manifest.toml").read_text(encoding="utf-8"))
                     .get("ui", {}).get("market") or {})
        res = os.environ.get("GAME_RESOLUTION", "").strip()
        over = Path(corpus_dir) / "res" / f"{res}.toml"
        if res and over.exists():
            table.update((tomllib.loads(over.read_text(encoding="utf-8")).get("ui") or {}).get("market") or {})
    except (OSError, ValueError, AttributeError):
        pass
    return hashlib.sha256(json.dumps(table, sort_keys=True, default=str).encode()).hexdigest()[:12]


# Action kind -> the game method that carries it out. A game whose object lacks the method has no
# hook for that kind: a pillar declaring it is logged "not supported" once and skipped.
ACTION_METHODS = {"tech": "pick_tech", "market": "market_sync"}


def action_hooks(game) -> dict[str, Callable]:
    out = {}
    for kind, method in ACTION_METHODS.items():
        fn = getattr(game, method, None)
        if callable(fn):
            out[kind] = fn
    return out


INSTRUCTIONS = """You are the governor of a Stellaris empire. The game's own AI runs the empire day to day;
you steer it by choosing ONE standing directive, which the harness applies (policies and a flag the
AI keeps). The game is paused while you decide. Answer with `keep` unless the situation changed
materially or the current directive's "leave when" condition holds.
The prompt already holds what you normally need: the briefing (resources, standing against the other
empires, expansion room), the strategy frame (pillar ranking, stances, milestones at risk), earlier directive changes and their outcomes, and the
directives table below. Call a tool only for a specific fact that is missing (e.g. what an event
option does: consult), and at most twice; then answer.
Human instructions, when present, override the rules below."""


class GovernorDecision(BaseModel):
    directive: Literal["keep", "expand", "consolidate_economy", "tech_rush", "prepare_war", "defend",
                       "diplomacy_first"] = Field(description="The directive to hold from now on, or 'keep'")
    reason: str = Field(description="One or two sentences citing the briefing numbers that decided it")
    note: str = Field(default="", description="Optional one line for the game journal (war, first colony, crisis...)")
    serves: str = Field(default="", description="The pillar and milestone this choice works toward, "
                                                "e.g. 'economy: economy_power >= 1080 by 2250.01.01'")


# Reviews that always have to show the strategy is built on our species (the user's rule): the first
# strategy of a run and a review the human asked for.
IDENTITY_TRIGGERS = ("start of run", "requested from the dashboard")


def species_terms(b: dict) -> tuple[str, list[str]]:
    """Our species' name and its traits in readable form ("trait_pc_desert_preference" -> "desert
    preference"), from the briefing's identity; empty when the save has none."""
    sp = ((b.get("identity") or {}).get("species") or {})
    traits = [t.removeprefix("trait_").removeprefix("pc_").replace("_", " ") for t in sp.get("traits") or []]
    return sp.get("name") or "", [t for t in traits if t]


def identity_errors(identity: str, traits: list[str]) -> list[str]:
    """The identity statement must name at least two of our traits (one if we have only one)."""
    if not traits:
        return []
    named = [t for t in traits if t.lower() in identity.lower()]
    need = min(2, len(traits))
    if len(named) >= need:
        return []
    return [(f"identity: say how our species' traits shape the strategy, naming at least {need} of them "
             f"(ours: {', '.join(traits)})")]


class StellarisGame(Protocol):
    def briefing(self) -> dict: ...
    def briefing_text(self) -> str: ...
    def set_paused(self, paused: bool) -> str: ...
    def set_speed(self, speed: str) -> str: ...
    def directive(self, name: str) -> str: ...
    def log_tail(self, lines: int = 30) -> str: ...
    def take_control(self) -> str: ...
    def pick_tech(self, prefer: list[str]) -> str: ...
    def market_sync(self, orders: list[dict]) -> str: ...
    def screenshot(self): ...
    def corpus(self, tool: str, **args) -> str: ...
    def close(self) -> None: ...


@dataclass
class GovDeps:
    game: StellarisGame
    store: LearnedStore
    log: EventLog


def months(date: str) -> int:
    """'2204.09.01' → months since year 0; 'T12' (a turn-based game) → 12."""
    if date[:1] == "T" and date[1:].isdigit():
        return int(date[1:])
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


EXPAND_BLOCKED = "expand cannot claim here: no surveyed room; influence is not the limit"


def expand_blocked(rows: list[dict]) -> str:
    """EXPAND_BLOCKED when the newest metrics row counts unclaimed systems within 2 jumps (`room` > 0)
    but none surveyed (`room_surveyed` 0) and the influence stock stayed at 950 or more through the
    last 12 months, else "" (levers design ruling 7, E12: Gaea held expand 41 years at the influence
    cap with 8-14 unclaimed systems in reach and at most 1 surveyed; the stall rule saw only "slow").
    A boxed-in empire (`room` 0: nothing to survey either; "boxed in" is its own urgent reason) gets
    no hint. Rows oldest first; a row without the fields (older telemetry) gives none."""
    dated = [r for r in rows if r.get("date")]
    if not dated or dated[-1].get("room_surveyed") != 0 or not (dated[-1].get("room") or 0) > 0:
        return ""
    now = months(dated[-1]["date"])
    if not any(now - months(r["date"]) >= 12 for r in dated):
        return ""
    year = [r for r in dated if now - months(r["date"]) <= 12]
    influence = [(r.get("stockpile") or {}).get("influence") for r in year]
    if all(isinstance(v, (int, float)) and v >= 950 for v in influence):
        return EXPAND_BLOCKED
    return ""


def _num(v) -> str:
    """Readable number for reasons: 405.92577500000004 -> '406', 1.0 -> '1', 12.34 -> '12.3'."""
    if not isinstance(v, (int, float)):
        return str(v)
    return f"{v:.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:.1f}"


IDLE_CHECKED = ("energy", "minerals", "food", "alloys", "consumer_goods")   # as the briefing (stellaris.rs)


def idle_resources(b: dict) -> set[str]:
    """Exactly the resources the briefing flags IDLE (stellaris.rs): energy, minerals, food, alloys
    or consumer goods with a stock over 5,000, positive net and over 10 years of income; trade over
    15,000 and still growing. Strategic resources are never flagged."""
    stock, net = b.get("stockpile") or {}, b.get("net") or {}
    out = set()
    for k in IDLE_CHECKED:
        v, n = stock.get(k), net.get(k)
        if v is not None and n is not None and v > 5000 and n > 0 and v > n * 120:
            out.add(k)
    v, n = stock.get("trade"), net.get("trade")
    if v is not None and n is not None and v > 15000 and n > 0:
        out.add("trade")
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


def frame_text(strategy: Strategy | None, spec: PillarSpec, milestones: str, press: dict | None = None,
               current: str | None = None) -> str:
    """The strategy frame shown to a decision: pressure (weight x milestone need) per directive with a
    suggestion (exclusive mode) or each pillar's share of effort (share mode), focus, stances and any
    at-risk/missed milestones. `press` is `strategy.pressures(...)`; None means no metrics yet, so
    pressure = weight."""
    if strategy is None:
        return ""
    lines = ["STRATEGY FRAME (from the Strategist; choose within it):", f"Focus: {strategy.focus}"]
    if press is None:
        press = pressures(strategy, spec, lambda _n, _m: "")
        lines.append("(no metrics yet: pressure = weight)")

    def why(pillar: str) -> str:
        p = press[pillar]
        status = p["status"] or ("no data" if strategy.pillars[pillar].milestones else "no milestones")
        text = f"{pillar} {p['weight']} x {status} {p['need']:g}"
        if p.get("efficacy", 1.0) < 1.0:
            r = p["record"]
            text += (f" x not working here {p['efficacy']:g}: {r['metric']}{' ÷ median' if r.get('relative') else ''} "
                     f"{r['held_rate']:+g}/yr over {r['held_years']:g} y held vs {r['other_rate']:+g}/yr otherwise")
        return text
    if spec.weights.mode == "share":
        sh = shares(press)
        lines.append("Share of effort (weight x milestone need): " + ", ".join(f"{n} {sh[n]}%" for n in press))
    else:
        ranked = directive_pressure(press, spec)
        lines.append("Directive pressure (weight x milestone need): "
                     + " > ".join(f"{d} {p:g} ({why(pl)})" for d, p, pl in ranked))
        sug = suggestion(ranked, current, spec.weights.switch_margin)
        lines.append(f"Suggested: {'keep ' + current if sug == 'keep' and current else sug}")
    for name, p in press.items():
        if p.get("hint"):       # e.g. expand blocked by unsurveyed space (levers ruling 7)
            lines.append(p["hint"])
    for name, pl in strategy.sorted_pillars():
        lines.append(f"{name} (weight {pl.weight}{', pinned by the human' if pl.pinned else ''}): {pl.stance}")
    at_risk = [m for m in milestones.splitlines() if m.endswith(("at_risk", "missed"))]
    if at_risk:
        lines.append("Milestones at risk or missed:\n" + "\n".join(at_risk))
    lines.append("Take the suggestion unless the briefing gives a reason not to (a new war, a deficit, a crisis); "
                 "then say why in the reason. Name the pillar and milestone your choice works toward in `serves`.")
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
    return Agent(resolve_model(model or s.model), deps_type=GovDeps, output_type=GovernorDecision,
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
    event_triggers: ClassVar[tuple[str, ...]] = EVENT_TRIGGERS    # urgent reasons that start a strategy review
    human_paused: bool = False       # paused from the dashboard: only the human's Resume ends it
    # date-stall watchdog (Stellaris; levers design ruling 23): the autosave date unchanged for
    # max(stall_floor_s, 10 x the median real seconds per month of this run's last stall_months)
    # while running means a stall: a screenshot and needs attention, with no input to the game
    stall_floor_s: ClassVar[float] = 300.0
    stall_months: ClassVar[int] = 24

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
        # the game's strategy guardrails; a missing or invalid file turns the strategy layer off
        # (decisions as before the layer) with one clear error naming the file and key
        self.pillars: PillarSpec | None = None
        self.pillars_error = ""
        try:
            self.pillars = load_pillars(settings.corpus_dir)
            self._review_type = review_model(self.pillars)
        except Exception as e:  # noqa: BLE001 - any failure building the layer (file or schema) turns it off, never the run
            self.pillars = None
            self.pillars_error = str(e) if isinstance(e, PillarsError) else f"{type(e).__name__}: {e}"
            log.emit("strategy_disabled", error=self.pillars_error[:500])
        log.state.info["pillars"] = self.pillars.public() if self.pillars else None
        self._unsupported: set[str] = set()       # action kinds already logged as "not supported"
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
        self._strategy_lock = threading.Lock()    # guards every read-modify-write of self.strategy
        self._last_b: dict | None = None          # the last structured briefing read for a decision/review
        self.review_requested: str | None = None  # pending review trigger (off-frame, or after a failed call)
        self._review_retry: bool = False          # review_requested was set by a failed review call (bypasses the cap)
        self._decision_military: float | None = None   # military_power as of the last decision (military-fell baseline)
        self._tech_misses: dict[str, int] = {}    # tech id -> misses this review (>=1: not retried until the next)
        self._tech_sync_date: str | None = None   # briefing date of the last pick_tech attempt (at most one per date)
        self._market_sync_date: str | None = None  # briefing date of the last market_sync attempt (ditto)
        self._market_unmeasured: set[str] = set()   # resources the controller refused to add (no measured start)
        # the action record (levers design rulings 2-6): every directive, tech pick, market order and
        # posture sent is followed on each new save until it resolves into an order_outcome row
        self._actions: list[dict] = []            # sent, not resolved yet (stellaris_record action dicts)
        self._action_rows: list[dict] = []        # every order_outcome row of the campaign
        self._followed_date: str | None = None    # the save date the actions were last judged on
        self._now_date: str | None = None
        self._tech_noops = 0                      # "nothing to pick" replies since the last review
        self._market_cal = market_calibration(settings.corpus_dir)   # [ui.market] hash (market suspension)
        self._since_retro = 0
        self._strategy_trace_n = 0                # negative episode ids for strategy review traces (see _review_strategy)
        self._clock: Callable[[], float] = time.monotonic   # the watchdog's wall clock (tests inject one)
        self._month_secs: deque[float] = deque(maxlen=self.stall_months)   # real seconds per in-game month
        self._date_seen_at = 0.0                  # clock when the autosave date last changed (or the wait began)
        self.orders: list[str] = []               # standing orders, saved per campaign
        # ("decide", msg) | ("override", name) | ("speed", speed) | ("review", trigger)
        self.requests: queue.Queue[tuple[str, str]] = queue.Queue()
        self._reviews_run = 0                     # strategy reviews started (one review per decision point)
        log.state.info["controls"] = ["instruct", "chat", "order_add", "order_remove", "decide_now", "override",
                                      "set_model", "set_models", "set_roles", "set_fallback", "set_speed", "set_months",
                                      "edit_pillar", "unpin_pillar", "review_strategy"]
        log.state.info["thinking"] = settings.governor_thinking
        log.state.info["pool"] = settings.pool()
        log.state.info["rotate"] = settings.rotate
        log.state.info["roles"] = dict(settings.roles or {})
        log.state.info["directives"] = list(DIRECTIVES)

    def _spec(self) -> PillarSpec:
        """The pillars spec, or ValueError (a 400 on the dashboard) while the strategy layer is off."""
        if self.pillars is None:
            raise ValueError(f"the strategy layer is off: {self.pillars_error}")
        return self.pillars

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
        model = resolve_model(model)
        if role == "strategy":
            return Agent(model, deps_type=GovDeps, output_type=self._review_type,
                         instructions=strategist_instructions(self.pillars) + "\n\n" + text,
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
        m, s, text = resolve_model(self._model_obj or self.s.model), self.s, self._text
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
        self.human_paused = True
        self.control.paused = True
        self._status("paused")

    def resume(self) -> None:
        self.human_paused = False
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

    _GENERIC_FIELDS: ClassVar[set[str]] = {"stance", "goals", "milestones", "priority", "weight"}

    def edit_pillar(self, name: str, fields: dict) -> None:
        """The human's edit: validated like a model strategy under the game's spec (against the last
        briefing this governor read: tech ids, idle resources and real monthly income), then pinned
        and recorded as a new version. Editable: stance, goals, milestones and the action fields the
        pillar declares in pillars.toml, and `weight` (the other unpinned pillars are rescaled so the
        weights still sum to 100); `priority` is derived from the weights and never editable. The
        milestone rule is for model reviews only. The read-modify-write is atomic (locked)."""
        from .strategy import Pillar
        spec = self._spec()
        if name not in spec.pillars:
            raise ValueError(f"unknown pillar {name!r}")
        if not isinstance(fields, dict):
            # ValueError, not TypeError: the dashboard's control() turns ValueError into a 400
            raise ValueError(f"fields must be an object, got {type(fields).__name__}")  # noqa: TRY004
        unknown = sorted(set(fields) - self._GENERIC_FIELDS - set(ACTION_KINDS.values()))
        if unknown:
            raise ValueError(f"unknown field(s): {', '.join(unknown)}")
        own = {spec.actions[k].field for k in spec.pillars[name].actions if k in spec.actions}
        for kind, fld in ACTION_KINDS.items():
            if fld in fields and fld not in own:
                owners = spec.owners(kind)
                raise ValueError(f"{name}: only the {' / '.join(owners)} pillar may set {fld}" if owners
                                 else f"{name}: {fld} is not an action in this game")
        editable = (self._GENERIC_FIELDS - {"priority"}) | own
        with self._strategy_lock:
            if self.strategy is None:
                raise ValueError("no strategy yet")
            cur = self.strategy.pillars[name].model_dump()
            new = Pillar.model_validate({**cur, **{k: v for k, v in fields.items() if k in editable},
                                         "pinned": True, "edited_by": "human"})
            trigger = f"edited by human: {name}"
            pillars = {**self.strategy.pillars, name: new}
            if "weight" in fields:
                pillars = rebalance(pillars, name)
            s = apply_aliases(Strategy(**{**self.strategy.model_dump(), "pillars": pillars, "reason": trigger}), spec)
            b = self._last_b
            if s.pillars[name].market and b is None:
                raise ValueError("no briefing yet: market orders can be edited after the first save is read")
            errs = validate(s, spec, previous=None, tech_ids=self._tech_ids(), ids=self._action_ids(), idle=idle_resources(b or {}),
                            income=(b or {}).get("net", {}), briefing_checked={name}, require_milestones=False)
            if errs:
                raise ValueError("; ".join(errs))
            self.strategy = s
        self._publish_strategy(s, self.log.state.game_date or "", trigger, "human")

    def unpin_pillar(self, name: str) -> None:
        with self._strategy_lock:
            if self.strategy is None or name not in self.strategy.pillars:
                raise ValueError(f"unknown pillar {name!r}")
            p = self.strategy.pillars[name].model_copy(update={"pinned": False})
            trigger = f"unpinned: {name}"
            s = self.strategy.model_copy(update={"pillars": {**self.strategy.pillars, name: p}, "reason": trigger})
            self.strategy = s
        self._publish_strategy(s, self.log.state.game_date or "", trigger, "human")

    def request_review(self) -> None:
        """Run a strategy review now (between scheduled decisions, like decide_now). A human request
        is never held back by the 12-month event-review cap and does not count toward it."""
        self._spec()
        self.requests.put(("review", "requested from the dashboard"))
        self.log.emit("instruction", text="Strategy review requested")

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

    recover_every_s: float = 30.0     # how often a transient failure probes the agent again

    @staticmethod
    def _transient(e: BaseException) -> bool:
        """A network hiccup (agent timed out or refused the connection), not a game-screen problem."""
        import socket
        import urllib.error
        return isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError, socket.timeout)) \
            or "timed out" in str(e).lower()

    def _needs_attention(self, why: str, *, auto_recover: bool = False) -> None:
        """Stop acting and wait for the human (dashboard Resume) instead of crashing the run. With
        `auto_recover` (a transient network failure) the wait also probes the agent every
        `recover_every_s` by pausing the game, and carries on by itself once that works."""
        self._auto_recover = auto_recover
        self._next_probe = time.time() + self.recover_every_s
        self.control.paused = True
        self.log.state.status = "needs_attention"
        try:
            shot = self.game.screenshot()
            if getattr(shot, "image", None):
                self.log.frame(shot.image)
        except Exception:  # noqa: BLE001, S110 - the frame is only a convenience here
            pass
        self.log.emit("needs_attention", reason=why[:500])

    def _probe_recovered(self) -> bool:
        """While waiting after a transient failure: try to pause the game; if the agent answers, the
        game is paused and the governor carries on (a `recovered` event)."""
        if not getattr(self, "_auto_recover", False) or self.log.state.status != "needs_attention" \
                or time.time() < self._next_probe:
            return False
        self._next_probe = time.time() + self.recover_every_s
        try:
            self.game.set_paused(True)
        except Exception as e:  # noqa: BLE001 - still unreachable: keep waiting
            self.log.emit("recover_probe", error=f"{type(e).__name__}: {e}"[:200])
            return False
        self._auto_recover = False
        self.control.paused = self.human_paused          # never lift a pause the human asked for
        self._status("paused" if self.human_paused else "playing")
        self.log.emit("recovered", reason="the agent answers again")
        return True

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
                            if self._probe_recovered():
                                break
                            time.sleep(0.5 if self.recover_every_s else 0.01)
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
                        # a review already pending (a failed review, or an earlier off-frame tag) is
                        # picked up here; a freshly off-frame-tagged decision waits for the *next*
                        # decision point instead of reviewing inline, so its own trace/choice is not
                        # re-litigated at once. `retry` (cap bypass) is only for a failed review's own
                        # retry or no strategy yet — an off-frame request goes through the normal cap.
                        # At most one review per decision point: a review that already ran inside
                        # _decide (the scheduled one) covers any event trigger at this point too.
                        pending = self.review_requested is not None
                        reviews_before = self._reviews_run
                        self._decide(b, reason)
                        still_pending = pending and self.review_requested is not None
                        event = reason.startswith("urgent:") and any(t in reason for t in self.event_triggers)
                        if self._reviews_run == reviews_before and (still_pending or event) and self.pillars is not None:
                            self._maybe_event_review(b, self.review_requested or reason, retry=self._review_retry)
                except Exception as e:  # noqa: BLE001 - any game-control failure (agent down, focus lost, a panel open)
                    transient = self._transient(e)
                    self._needs_attention(f"game control failed: {type(e).__name__}: {e}. "
                                          + ("Retrying by itself while the agent does not answer; Resume also works."
                                             if transient else "Fix the game screen or the agent, then press Resume."),
                                          auto_recover=transient)
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
                reviewed = self.strategy is None and self.pillars is not None
                if reviewed:
                    self._review_strategy(b, "start of run")
                self._decide(b, "start of run", reviewed_at_start=reviewed)
                return b
            except Exception as e:  # noqa: BLE001
                self._needs_attention(f"could not start: {type(e).__name__}: {e}. Fix the game or the agent, "
                                      "then press Resume to try again.", auto_recover=self._transient(e))
                self._wait_for_resume()
        return None

    def _wait_for_resume(self) -> None:
        """Wait for the human's Resume, or, after a transient failure, for the agent to answer again."""
        while self.control.paused and not self.control.stopping:
            if self._probe_recovered():
                return
            time.sleep(0.5 if self.recover_every_s else 0.01)

    def _handle_request(self, req: tuple[str, str], b: dict) -> dict:
        """Run one human request (already taken from the queue; the game is paused)."""
        kind, arg = req
        if kind == "decide":
            if arg:
                self.human.push(arg)
            self._decide(b, "human request" + (f": {arg}" if arg else ""))
        elif kind == "override":
            self._override(b, arg)
        elif kind == "review":
            self._review_strategy(b, arg)
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
        self._follow(b)
        try:
            reply = self.game.directive(directive)
            outcome = "applied"
            self.last_change = months(b["date"])
            self.log.state.info["directive"] = directive
            self._directive_sent(directive, reply, b)
        except Exception as e:  # noqa: BLE001
            outcome = f"FAILED: {e}"[:200]
            self._directive_failed(directive, e, b)
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
        self._load_campaign_state()
        self._load_action_record()

    def _load_campaign_state(self) -> None:
        """Standing orders, plan and strategy saved for the campaign just named."""
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
                stored = Strategy.model_validate(raw) if raw else None
                if stored is not None and (self.pillars is None or set(stored.pillars) != set(self.pillars.ids)):
                    if self.pillars is not None:
                        # treated as no strategy: _start reviews at once (its only caller)
                        self.log.emit("strategy_mismatch", stored=sorted(stored.pillars), spec=list(self.pillars.ids))
                    stored = None
                self.strategy = stored
            except Exception as e:  # noqa: BLE001
                self.log.emit("briefing_error", error=f"loading the strategy: {e}"[:200])
        self.log.state.info["plan"] = self.plan
        self.log.state.info["strategy"] = self.strategy.model_dump() if self.strategy else None

    def _run_until_next_decision(self, last: dict) -> tuple[dict | None, str]:
        start = months(last["date"])          # the interval can change mid-wait (dashboard)
        self._status("playing")
        self.game.set_paused(False)
        self._date_seen_at = self._clock()
        unread_since: float | None = None      # clock of the first failed read in a row
        blind = False                          # reads failed for a stall limit: flagged, clears by itself
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
            except Exception as e:  # noqa: BLE001 - a save being rotated, or the agent away; try again next poll
                self.log.emit("briefing_error", error=str(e)[:200])
                unread_since = self._clock() if unread_since is None else unread_since
                if not blind:
                    blind = self._unread_too_long(unread_since, e)
                continue
            folder = self._save_folder(b)
            if folder and getattr(self, "_folder", None) and folder != self._folder:
                # another game was loaded: never act on an empire this run was not started for
                self.game.set_paused(True)
                self._needs_attention(f"the game changed: newest autosave is from {folder!r}, this run governs "
                                      f"{self._folder!r}. Load that game again and press Resume, or stop this run "
                                      "and start a new one for the new game.")
                return last, ""
            if blind:
                blind = False
                if self.log.state.status == "needs_attention":
                    self._status("playing")
                self.log.emit("recovered", reason="the newest autosave of this campaign reads again")
            if b["date"] != last["date"]:
                self._date_moved(months(b["date"]) - months(last["date"]))
                self.log.emit("metrics", **metrics(b))
                self._follow(b)
                self.log.state.game_date = b["date"]
                self.log.state.turns_advanced = months(b["date"]) - months(last["date"]) + self.log.state.turns_advanced
            else:
                if unread_since is not None:
                    # the time without a reading proves no stall (the PC may have slept): left out
                    self._date_seen_at += self._clock() - unread_since
                if self._stalled(b["date"]):
                    return last, ""
            unread_since = None
            urgent = urgent_changes(last, b)
            if b["date"] != last["date"]:
                urgent += self._newly_missed_milestones(last["date"], b["date"])
            mil_base, mil_now = self._decision_military, b.get("military_power")
            if mil_base and mil_now is not None and mil_now <= 0.5 * mil_base and not any(u.startswith("military fell") for u in urgent):
                urgent.append(f"military fell: {round(mil_base)} -> {round(mil_now)}")
            if urgent:
                self.game.set_paused(True)
                return b, "urgent: " + "; ".join(urgent)
            if months(b["date"]) >= start + self.s.decide_every_months:
                self.game.set_paused(True)
                return b, f"scheduled ({self.s.decide_every_months} months)"
            last = b

    def _date_moved(self, n: int) -> None:
        """The autosave date moved `n` months: record the real time per month, restart the stall timer."""
        now = self._clock()
        if n > 0:
            self._month_secs.extend([(now - self._date_seen_at) / n] * min(n, self.stall_months))
        self._date_seen_at = now

    def _stall_limit(self) -> float:
        """Seconds without a new date that count as a stall: 10 x the median real month of this run's
        last `stall_months`, at least `stall_floor_s` (above every month seen live, 247 s max)."""
        median = statistics.median(self._month_secs) if self._month_secs else 0.0
        return max(self.stall_floor_s, 10 * median)

    def _stalled(self, date: str) -> bool:
        """The date-stall watchdog, run on every poll whose date did not move while the game should
        be running. A popup that autopauses, the launcher or a crash can hold the date for good, and
        nothing else notices. After `_stall_limit()`: a screenshot, a `stall` event and needs
        attention, and True so the wait returns. It sends no input and brings no window forward: the
        human may have loaded another campaign (it writes no autosave at first, so the governed save
        still looks newest), or after a crash the only window titled Stellaris may be the launcher or
        a browser tab, and nothing read-only proves the governed game is the one in front. So only the
        human resumes (dashboard Resume). A dashboard pause never reaches here."""
        if self.human_paused or self.control.paused:
            return False
        held, limit = self._clock() - self._date_seen_at, self._stall_limit()
        if held < limit:
            return False
        frame = self._frame()
        self.log.emit("stall", date=date, seconds=round(held), limit=round(limit), frame=frame)
        self._needs_attention(f"the game date has not advanced for {round(held)} s (still {date}): a popup that paused "
                              "the game, another game loaded, the launcher or a crash may hold it. Nothing was sent to "
                              f"the game. Screenshot at the stall: {frame or 'none'}. Check the PC, then press Resume.")
        return True

    def _unread_too_long(self, since: float, e: BaseException) -> bool:
        """Reads of the newest autosave have failed since `since` (the agent away: the PC asleep, the
        network down, the agent reinstalled; or a save that cannot be read). That time is no date
        stall. After `_stall_limit()` of it: needs attention in the status and a `needs_attention`
        event, and True. The run is not paused and nothing is sent to the game: the wait keeps
        reading, which is the probe, and clears the flag by itself once a save of this campaign reads
        again (a `recovered` event); only a stall seen after that waits for the human."""
        if self.human_paused or self.control.paused:
            return False
        held, limit = self._clock() - since, self._stall_limit()
        if held < limit:
            return False
        self.log.state.status = "needs_attention"
        self.log.emit("needs_attention", reason=(
            f"the newest autosave could not be read for {round(held)} s ({type(e).__name__}: {e})"[:300]
            + ": the agent may be away (the PC asleep, the network down, the agent reinstalled) or the save "
            "unreadable. Nothing was sent to the game, which runs on without the governor. The run carries "
            "on by itself as soon as a save of this campaign reads again; Resume also works."))
        return True

    def _frame(self) -> str:
        """A screenshot saved with the run ('' if none could be taken)."""
        try:
            return self.log.frame(getattr(self.game.screenshot(), "image", None))
        except Exception as e:  # noqa: BLE001 - the frame is only evidence
            self.log.emit("briefing_error", error=f"screenshot: {e}"[:200])
            return ""

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
        self._last_b = b     # cached for edit_pillar's market-order validation (idle resources, income)
        self._decision_military = b.get("military_power")   # baseline for "military fell" until the next decision
        self.log.state.episodes += 1
        self.log.state.game_date = b["date"]
        self.log.emit("metrics", **metrics(b))
        self._follow(b)
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
        press = self._pressures() if self.strategy and self.pillars else None
        self.last_briefing = self.game.briefing_text()
        prompt = [f"Decision point: {reason}.",
                  f"Current directive: {current or 'none'}{held}.",
                  (frame_text(self.strategy, self.pillars, self._milestones_text(), press, current)
                   if self.pillars else "")
                  or "No strategy yet.",
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
        record = self._action_record_section()
        if record:
            prompt.append(record)
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
        if self.strategy and self.pillars:
            by_pressure = press or pressures(self.strategy, self.pillars, lambda _n, _m: "")
            ranked = [r[0] for r in directive_pressure(by_pressure, self.pillars)]
        else:
            ranked = []
        off_frame = bool(ranked) and chosen not in ("keep", current) and chosen not in ranked[:2]
        if off_frame and self.review_requested is None:   # keep the first pending request's trigger text
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
                    reply = self.game.directive(chosen)
                    applied = "applied"
                    self.last_change = months(b["date"])
                    self.log.state.info["directive"] = chosen
                    self._directive_sent(chosen, reply, b)
                except Exception as e:  # noqa: BLE001
                    applied = f"FAILED: {e}"[:200]
                    self.log.emit("episode_error", error=f"directive {chosen}: {e}"[:300])
                    self._directive_failed(chosen, e, b)
        st.last_decision = f"{b['date']}: {d.directive} ({applied}) — {d.reason}"
        self.log.emit("episode", situation=reason, decision=f"{d.directive}: {d.reason}", date=b["date"],
                      resolved=not applied.startswith("FAILED"), actions=int(applied == "applied"),
                      seconds=round(time.time() - started, 1),
                      tokens_in=usage.input_tokens, tokens_out=usage.output_tokens)
        self.log.save_trace(n, {**base, "decision": d.directive, "reason": d.reason, "outcome": applied,
                                "off_frame": off_frame, "serves": d.serves, "seconds": round(time.time() - started, 1),
                                "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens,
                                "steps": serialize(result.all_messages())})
        self.store.add_episode(reason, f"{d.directive} ({applied}): {d.reason}", applied, b["date"])
        self.journal.note(f"{d.directive} ({applied}) — {d.reason}", b["date"])
        if d.note:
            self.journal.note(d.note, b["date"])
        self._carry_out_actions(b)
        if not (reason == "start of run" and reviewed_at_start):   # a review just ran for this decision point
            self._since_retro += 1
            if self.s.retro_every and self._since_retro >= self.s.retro_every and self.pillars is not None:
                self._review_strategy(b, f"scheduled after {self.s.retro_every} decisions")

    @staticmethod
    def _same_orders(a: list[dict], b: list[dict]) -> bool:
        """Market orders compare order-insensitively (side, resource, amount)."""
        key = lambda o: (o.get("side"), o.get("resource"), o.get("amount"))
        return sorted(map(key, a)) == sorted(map(key, b))

    def _log_action(self, action: str, result: str) -> None:
        self.log.emit("strategy_action", action=action, result=result)

    def _carry_out_actions(self, b: dict) -> None:
        """The strategy's player actions, per the game's spec: each action kind a pillar declares runs
        through the game's hook for it (ACTION_METHODS); a kind without a hook is logged "not
        supported" once and skipped. Each tool acts at most once per briefing date (the result stays
        stale until the next autosave). Nothing here ever raises out of this call, pauses the game,
        or undoes the decision already applied — any failure is logged as a strategy_action event.
        What was sent before is judged on this save first (the action record, `_follow`)."""
        self._follow(b)
        if not self.strategy or self.pillars is None:
            return
        hooks = action_hooks(self.game)
        runners = {"tech": self._carry_out_tech_actions, "market": self._carry_out_market_actions}
        for kind in self.pillars.actions:
            if not self.pillars.owners(kind):
                continue
            hook = hooks.get(kind)
            if hook is None:
                if kind not in self._unsupported:
                    self._unsupported.add(kind)
                    self._log_action(kind, "not supported by this game; skipped")
                continue
            try:
                runners[kind](b, hook)
            except Exception as e:  # noqa: BLE001 - nothing here may stop play
                self._log_action("error", f"failed: {e}"[:300])

    def _declared(self, kind: str) -> list:
        """The items of action `kind` across the pillars that declare it, in priority order."""
        owners = set(self.pillars.owners(kind))
        fld = self.pillars.actions[kind].field
        return [x for name, pl in self.strategy.sorted_pillars() if name in owners for x in getattr(pl, fld)]

    def _carry_out_tech_actions(self, b: dict, pick_tech: Callable[[list[str]], str]) -> None:
        """Pick the first preferred tech on offer (stellaris_pick_tech). A pick is followed until it is
        researched, did not stick (then skipped until the next review) or is held; a "nothing to
        pick" reply is a no-op, counted for the next review (ruling 6)."""
        date = b.get("date")
        limit = self.pillars.actions["tech"].max_items
        prefer = [t for t in dict.fromkeys(self._declared("tech")) if self._tech_misses.get(t, 0) < 1][:limit]
        fields = (b.get("research") or {}).values()
        researching = {((r or {}).get("current") or [None])[0] for r in fields}
        if prefer and not researching & set(prefer) and date != self._tech_sync_date:
            self._tech_sync_date = date
            try:
                res = pick_tech(prefer)
            except Exception as e:  # noqa: BLE001 - actions never stop play
                self._log_action("tech", f"failed: {e}"[:300])
                self._resolve_action(tech_action(", ".join(prefer), "", date), "failed", None, f"{e}", date)
                return
            self._log_action("tech", res)
            m = TECH_PICK_RE.match(res)
            if m and not any(a["kind"] == "tech" and a["id"] == m.group(1) for a in self._actions):
                self._open_action(tech_action(m.group(1), m.group(2), date))
            elif res.startswith(NO_OP_PREFIX):
                self._tech_noops += 1
                self._resolve_action(tech_action(", ".join(prefer), "", date), "no_op", None, res, date)

    def _carry_out_market_actions(self, b: dict, market_sync: Callable[[list[dict]], str]) -> None:
        """Sync the declared monthly trades (stellaris_market_sync). Each side and resource the sync
        changes is followed in the next saves (ruling 2); one that did not take twice in a row with
        today's `[ui.market]` calibration is suspended until a recalibration (ruling 6), keeping any
        order of it the save already holds, as for a resource whose start amount is not measured."""
        date = b.get("date")
        current = b.get("market_orders") or []
        later = date != self._market_sync_date
        limits = self.pillars.actions["market"]
        idle, income = idle_resources(b), b.get("net") or {}
        desired = []
        for o in self._declared("market"):
            errs = market_briefing_errors(o, limits, idle, income)
            if errs:     # a sell that no longer fits today's briefing (e.g. a pinned or older order)
                if later:
                    self._log_action("market", f"skipped sell {o.resource}: {'; '.join(errs)}"[:300])
                continue
            blocked = ("start amount not measured (the controller refuses to add it)"
                       if o.resource in self._market_unmeasured else self._market_suspension(o.side, o.resource))
            if blocked and not any(self._same_orders([o.model_dump()], [c]) for c in current):
                # an order of that side and resource already in the save is kept at its amount (as
                # the controller keeps an unmeasured one) while that amount passes the checks the
                # declared order passed
                held = [h for h in self._kept_for([o.model_dump()], current)
                        if not market_briefing_errors(o.model_copy(update={"amount": h.get("amount")}), limits, idle, income)]
                if later:
                    what = (", ".join(f"kept {h['side']} {h['resource']} {h['amount']}" for h in held)
                            + f" ({o.amount} wanted)" if held else f"skipped {o.side} {o.resource} {o.amount}")
                    self._log_action("market", f"{what}: {blocked}")
                desired += held
                continue
            desired.append(o.model_dump())
        if self._same_orders(desired, current) or not later:
            return
        self._market_sync_date = date
        changes = self._market_changes(desired, current)
        try:
            res = market_sync(desired)
        except Exception as e:  # noqa: BLE001 - actions never stop play
            self._log_action("market", f"failed: {e}"[:300])
            for c in changes:       # failed, not did_not_take: an agent timeout never suspends a resource
                self._resolve_action(market_action(c, date, self._market_cal), "failed", None, f"{e}", date)
            return
        self._log_action("market", res)
        refused = self._refused_orders(res)
        self._market_unmeasured |= {o["resource"] for o in refused}
        # what the controller left out is not waited for in the next save; the order it kept in its
        # place is
        wanted = [o for o in desired if not any(self._same_orders([o], [r]) for r in refused)] \
            + self._kept_for(refused, current)
        for c in self._market_changes(wanted, current):
            for a in [a for a in self._actions if a["kind"] == "market"
                      and (a["expect"]["side"], a["expect"]["resource"]) == (c["side"], c["resource"])]:
                self._resolve_action(a, *self._superseded(a), date)
            self._open_action(market_action(c, date, self._market_cal))

    @staticmethod
    def _market_changes(wanted: list[dict], current: list[dict]) -> list[dict]:
        """Each side and resource whose amount a sync to `wanted` changes (amount 0: removed)."""
        want = {(o.get("side"), o.get("resource")): int(o.get("amount") or 0) for o in wanted}
        have = {(o.get("side"), o.get("resource")): int(o.get("amount") or 0) for o in current}
        return [{"side": k[0], "resource": k[1], "amount": want.get(k, 0)}
                for k in sorted(set(want) | set(have), key=str) if want.get(k, 0) != have.get(k, 0)]

    def _market_suspension(self, side: str, resource: str) -> str | None:
        if market_suspended(self._action_rows, side, resource, self._market_cal):
            return ("suspended after 2 did not take in a row with this [ui.market] calibration; a recalibration "
                    "lifts it")
        return None

    @staticmethod
    def _kept_for(refused: list[dict], current: list[dict]) -> list[dict]:
        """The save's orders the controller keeps for refused adds: same side and resource, any amount
        (stellaris.rs market_plan)."""
        return [c for c in current if any((c.get("side"), c.get("resource")) == (r.get("side"), r.get("resource"))
                                          for r in refused)]

    @staticmethod
    def _refused_orders(reply: str) -> list[dict]:
        """The orders a market_sync reply says it did not add (MARKET_REFUSED_RE)."""
        m = MARKET_REFUSED_RE.search(reply or "")
        out = []
        for part in (m.group(1).split(",") if m else []):
            words = part.split()
            if len(words) == 3 and words[2].isdigit():
                out.append({"side": words[0], "resource": words[1], "amount": int(words[2])})
        return out

    # ---- the action record (docs/design/2026-09-27-stellaris-levers-design.md, rulings 2-6) --------

    @property
    def _pending_pick(self) -> str | None:
        """The picked tech still followed (not yet researched, dropped or held)."""
        return next((a["id"] for a in self._actions if a["kind"] == "tech"), None)

    def _orders_spec(self) -> OrdersSpec:
        """The record's settings (`[orders]` in pillars.toml, in months); defaults without one."""
        return (self.pillars.orders if self.pillars is not None and self.pillars.orders is not None
                else OrdersSpec())

    def _now_month(self) -> int:
        dates = [d for d in (self._now_date, self.log.state.game_date) if d and d[:1] != "T"]
        return max([months(d) for d in dates] + [r.get("turn") or 0 for r in self._action_rows] + [0])

    def _open_action(self, a: dict) -> None:
        """Follow `a` from now on; the `order_followed` event lets a restart carry on following it."""
        self._actions.append(a)
        self.log.emit("order_followed", ref=a["ref"], action=a)

    def _resolve_action(self, a: dict, result: str, by: str | None, detail: str, date: str) -> None:
        """`a` resolved on the save of `date`: one order_outcome row (the Civ VI shape). Advisory: a
        row that cannot be built (a malformed date) is logged and the action dropped."""
        self._actions = [x for x in self._actions if x.get("ref") != a.get("ref")]
        try:
            row = outcome_row(a, result, by, detail, date)
        except Exception as e:  # noqa: BLE001 - the record never stops play
            self.log.emit("briefing_error", error=f"action record ({a.get('key')}): {type(e).__name__}: {e}"[:200])
            return
        self._action_rows.append(row)
        self.log.emit("order_outcome", **row)
        if a["kind"] == "tech" and result == "did_not_stick":
            self._tech_misses[a["id"]] = self._tech_misses.get(a["id"], 0) + 1
        self._publish_actions()

    @staticmethod
    def _superseded(a: dict) -> tuple[str, None, str]:
        result, detail = supersede(a)
        return result, None, detail

    def _follow(self, b: dict) -> None:
        """Judge every followed action on save `b`, once per save date (ruling 4): each one that
        resolves writes its row; a tech or market resolution is also logged as a strategy_action.
        Advisory: a malformed save is logged and never stops play."""
        date = str(b.get("date") or "")
        if not date or date == self._followed_date or date[:1] == "T":
            return
        self._followed_date = self._now_date = date
        spec = self._orders_spec()
        for a in list(self._actions):
            state = a.get("state")
            try:
                result, by, detail = judge(a, b, spec.open_cap_turns, spec.open_grace_turns)
            except Exception as e:  # noqa: BLE001 - the record is advisory
                self.log.emit("briefing_error", error=f"action record ({a.get('key')}): {type(e).__name__}: {e}"[:200])
                continue
            if result == OPEN:
                if a.get("state") != state:
                    self.log.emit("order_followed", ref=a["ref"], action=a)   # seen in force: kept across restarts
                continue
            self._resolve_action(a, result, by, detail, date)
            if a["kind"] == "tech":
                self._log_action("tech", {"did_not_stick": f"{a['id']} did not stick; skipped until the next review",
                                          "researched": f"researched {a['id']}"}.get(result, f"{a['id']} {result}"))
            elif a["kind"] == "market":
                self._log_action("market", f"market order {a['id']} {result.replace('_', ' ')}: {detail}"[:300])

    def _directive_sent(self, name: str, reply, b: dict) -> None:
        """A directive was applied on save `b`: the one before it (and the postures it set) resolve as
        held or superseded, and this one is followed with the policies the game reported set and the
        postures its console lines set (ruling 3)."""
        try:
            date = b["date"]
            for a in [a for a in self._actions if a["kind"] == "directive" or a.get("from") == "directive"]:
                self._resolve_action(a, *self._superseded(a), date)
            info = parse_directive_reply(str(reply or ""))
            self._open_action(directive_action(name, date, info))
            for posture in info["postures"]:
                self._open_action({**posture_action(posture, True, date), "from": "directive"})
        except Exception as e:  # noqa: BLE001 - the record is advisory
            self.log.emit("briefing_error", error=f"action record (directive {name}): {type(e).__name__}: {e}"[:200])

    def _directive_failed(self, name: str, e: BaseException, b: dict) -> None:
        self._resolve_action(directive_action(name, b["date"], {}), "failed", None, f"{type(e).__name__}: {e}", b["date"])

    def _settle_at_review(self, b: dict) -> None:
        """At a strategy review: judge on this save, then a picked tech still researched is held."""
        if not self._actions:
            return
        self._follow(b)
        for a in list(self._actions):
            verdict = review_outcome(a)
            if verdict:
                self._resolve_action(a, verdict[0], None, verdict[1], str(b.get("date") or a.get("ordered") or ""))

    def _load_action_record(self) -> None:
        """The campaign's action record from earlier runs (ruling 4): its order_outcome rows and the
        actions still followed (the newest `order_followed` event of each one without an outcome).
        Advisory: a failed read keeps what is in memory."""
        tel, cid = self.log.telemetry, self.log.campaign_id
        if tel is not None and cid:
            try:
                rows = [r for r in tel.campaign_events(cid, "order_outcome") if r.get("key")]
                done = {r.get("ref") for r in rows if r.get("ref")}
                followed: dict[str, dict] = {}
                for f in tel.campaign_events(cid, "order_followed"):
                    if isinstance(f.get("action"), dict) and f.get("ref") and f["ref"] not in done:
                        followed[f["ref"]] = f["action"]
                self._action_rows, self._actions = rows, list(followed.values())
            except Exception as e:  # noqa: BLE001 - the record is advisory
                self.log.emit("briefing_error", error=f"loading the action record: {e}"[:200])
        self._publish_actions()

    def _publish_actions(self) -> None:
        """The record for the dashboard, in the Civ VI order record's key and shape."""
        self.log.state.info["order_record"] = action_record(self._action_rows, self._now_month(), self._orders_spec())

    def _action_record_text(self) -> str:
        """One line per key (stick rate), each market order suspended, and how often the preferred
        techs met the offer (ruling 6); empty while nothing resolved."""
        rows = self._action_rows
        if not rows:
            return ""
        lines = [action_record_text(action_record(rows, self._now_month(), self._orders_spec()))]
        markets = sorted({tuple(r["key"].split(" ")[1:3]) for r in rows if str(r.get("key", "")).startswith("market ")})
        for side, res in (m for m in markets if len(m) == 2):
            if self._market_suspension(side, res):
                lines.append(f"- market {side} {res}: suspended after 2 did not take in a row with this [ui.market] "
                             "calibration; a recalibration lifts it")
        noops = sum(1 for r in rows if r.get("key") == "tech" and r.get("result") == "no_op")
        if noops:
            picks = sum(1 for r in rows if r.get("key") == "tech" and r.get("result") not in ("no_op", "failed")) \
                + sum(1 for a in self._actions if a["kind"] == "tech")
            lines.append(f"- tech picks: your preferred techs matched the offer {picks} times in {picks + noops} chances")
        return "\n".join(x for x in lines if x)

    def _action_record_section(self, b: dict | None = None, noops: int = 0) -> str:
        """The record's prompt section, or "" when there is nothing in it (a Civ VI governor never
        fills it). At a review after 3 or more no-op tech syncs (`noops`), it also lists what `b`
        offers per field and asks prefer_techs to name one of them."""
        try:
            lines = [x for x in (self._action_record_text(), self._tech_advice(b, noops)) if x]
        except Exception as e:  # noqa: BLE001 - the record is advisory
            self.log.emit("briefing_error", error=f"action record: {type(e).__name__}: {e}"[:200])
            return ""
        return ACTION_RECORD_HEADING + "\n" + "\n".join(lines) if lines else ""

    @staticmethod
    def _tech_advice(b: dict | None, noops: int) -> str:
        research = (b or {}).get("research")
        if noops < 3 or not isinstance(research, dict):
            return ""
        offers = "; ".join(f"{fld}: {', '.join(r['alternatives'])}" for fld, r in sorted(research.items())
                           if isinstance(r, dict) and r.get("alternatives"))
        if not offers:
            return ""
        return (f"- tech picks: {noops} tech syncs since the last review found none of the preferred techs where it "
                f"could pick; offered now: {offers}. Name at least one of them in prefer_techs.")

    def _maybe_event_review(self, b: dict, trigger: str, retry: bool = False) -> bool:
        """Run a strategy review for a big event, at most once per 12 in-game months. `retry`
        (a failed review pending retry) and having no strategy yet both bypass the cap and never
        move its last-review month: only event-triggered and off-frame reviews count toward it.
        A refused request is logged and, if it was a pending one (off-frame), dropped
        (review_requested cleared) so it does not keep re-firing every decision until the cap opens."""
        bypass = retry or self.strategy is None
        last = getattr(self, "_last_event_review_month", None)
        now = months(b["date"])
        if not bypass and last is not None and now - last < 12:
            self.log.emit("strategy_review_skipped", trigger=trigger, reason="within 12 months of the last event review")
            if self.review_requested == trigger:
                self.review_requested = None
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

    def _metrics_rows(self) -> list[dict] | None:
        """This campaign's metrics rows (oldest first), or None when there is no telemetry or the
        read failed (logged): milestones are advisory and never block play or a review."""
        if not self.strategy or self.log.telemetry is None or not self.log.campaign_id:
            return None
        try:
            return self.log.telemetry.metrics_rows(self.log.campaign_id)
        except Exception as e:  # noqa: BLE001 - telemetry is advisory; never block a review
            self.log.emit("briefing_error", error=f"milestones: {e}"[:200])
            return None

    def _pressures(self) -> dict | None:
        """Pressure per pillar from this campaign's metrics rows, or None without rows (the frame then
        uses pressure = weight). Never raises: it runs before every decision."""
        rows = self._metrics_rows()
        if not rows or self.strategy is None or self.pillars is None:
            return None
        today = rows[-1]["date"]
        try:
            spec = self.pillars
            press = pressures(self.strategy, spec, lambda _n, m: milestone_status(m, rows, today, spec.row_keys),
                              record_of=lambda name, metric: (directive_record(rows, d, metric, spec.row_keys, spec.peer_keys)
                                                              if (d := spec.directive_of(name)) else None))
            hint = expand_blocked(rows)
            for name in press:
                if hint and spec.directive_of(name) == "expand":
                    press[name]["hint"] = hint
            return press
        except Exception as e:  # noqa: BLE001 - advisory; the decision still runs on weights
            self.log.emit("briefing_error", error=f"pressure: {type(e).__name__}: {e}"[:200])
            return None

    def _directive_records_text(self) -> str:
        """One line per directive: how its pillar's milestone metric grew while it was held versus the
        rest of the campaign, marked when it does not work here (pillars.toml stall rule)."""
        rows, spec = self._metrics_rows(), self.pillars
        if not rows or self.strategy is None or spec is None:
            return "(no data yet)"
        w, out = spec.weights, []
        for name, pl in self.strategy.sorted_pillars():
            d = spec.directive_of(name)
            if not d or not pl.milestones:
                continue
            metric = pl.milestones[0].metric
            r = directive_record(rows, d, metric, spec.row_keys, spec.peer_keys)
            if r is None:
                out.append(f"- {d} ({name}, {metric}): not held long enough to judge")
                continue
            verdict = (" — does not work here" if w.stall_years and r["held_years"] >= w.stall_years
                       and r["held_rate"] <= r["other_rate"] else "")
            label = f"{metric} ÷ median" if r.get("relative") else metric
            out.append(f"- {d} ({name}, {label}): {r['held_rate']:+g}/yr over {r['held_years']:g} y held vs "
                       f"{r['other_rate']:+g}/yr otherwise{verdict}")
        return "\n".join(out) or "(no data yet)"

    def _records_section(self) -> str:
        """The Strategist's record of what its levers did: here each directive's record; a game with
        other levers (Civ VI orders) gives its own."""
        return ("Directive record in this campaign (its pillar's first milestone metric, per in-game year):\n"
                + self._directive_records_text())

    def _milestones_text(self) -> str:
        rows = self._metrics_rows()
        if rows is None:
            return "(none)"
        today = rows[-1]["date"] if rows else "2200.01.01"
        out = []
        for name, pl in self.strategy.sorted_pillars():
            for m in pl.milestones:
                out.append(f"- {name}: {m.metric} {m.op} {m.target:g} by {m.by}: "
                          f"{milestone_status(m, rows, today, self.pillars.row_keys)}")
        return "\n".join(out) or "(none)"

    def _newly_missed_milestones(self, before: str, today: str) -> list[str]:
        """Urgent reasons for milestones that are `missed` on `today` but were not on `before` (the
        previous check's save date): each fires once, when its date passes unmet."""
        strategy, rows = self.strategy, self._metrics_rows()
        if strategy is None or rows is None:
            return []
        try:
            return [f"milestone missed: {name} {m.metric}" for name, pl in strategy.sorted_pillars() for m in pl.milestones
                    if milestone_status(m, rows, today, self.pillars.row_keys) == "missed"
                    and milestone_status(m, rows, before, self.pillars.row_keys) != "missed"]
        except Exception as e:  # noqa: BLE001 - runs in the poll loop; raising would pause the governor
            self.log.emit("briefing_error", error=f"milestone check: {type(e).__name__}: {e}"[:200])
            return []

    def _past_outcomes_text(self) -> str:
        if self.log.telemetry is None or not self.log.campaign_id:
            return "(none)"
        try:
            return self.log.telemetry.past_outcomes(self.log.campaign_id)
        except Exception as e:  # noqa: BLE001 - telemetry is advisory; never block a review
            self.log.emit("briefing_error", error=f"strategy review outcomes: {e}"[:200])
            return "(none)"

    def _review_strategy(self, b: dict, trigger: str, retried: bool = False, errors: list[str] | None = None,
                         rejected: str | None = None) -> None:
        """Strategist review: may keep the strategy or write a new version (pinned pillars stay). An invalid
        answer (including change=true with no strategy) is retried once with the reasons; still invalid →
        no change. Never raises and never pauses the game: any failure (reading the game for the prompt,
        the model call, or after it) is logged, the current strategy stays, and the review is retried
        at the next decision."""
        if self.pillars is None:
            self.log.emit("strategy_review_skipped", trigger=trigger, reason=f"strategy layer off: {self.pillars_error}"[:300])
            return
        self._last_b = b     # cached for edit_pillar's market-order validation (idle resources, income)
        self._reviews_run += 1
        self._since_retro = 0
        self.review_requested = None
        self._review_retry = False
        self._tech_misses = {}
        self._settle_at_review(b)
        noops, self._tech_noops = self._tech_noops, 0
        started = time.time()
        retry_errors: list[str] | None = None
        retry_rejected: str | None = None
        try:     # building the prompt reads the game (briefing text): inside, so it never raises out
            # shown in the answer's own shape, so a model that echoes it (change=true) validates
            current = (strategy_for_prompt(self.strategy, self.pillars) if self.strategy
                       else "(none yet: write the first strategy)")
            pinned = [name for name, pl in self.strategy.sorted_pillars() if pl.pinned] if self.strategy else []
            prompt = [f"Strategy review, trigger: {trigger}.", "Current strategy:\n" + current,
                      "Milestones (status computed from the recorded numbers):\n" + self._milestones_text(),
                      "Directive changes and what followed:\n" + self._past_outcomes_text(),
                      *[x for x in (self._action_record_section(b, noops),) if x],
                      self._records_section(),
                      "Latest briefing:\n" + (self.last_briefing or self.game.briefing_text())]
            sp_name, sp_traits = species_terms(b)
            if sp_name or sp_traits:
                prompt.insert(1, f"Our species: {sp_name}; traits: {', '.join(sp_traits) or 'none listed'}. "
                                 "The strategy must be built on them (fill `identity`).")
            misfits = pinned_misfits(self.strategy, self.pillars, idle=idle_resources(b),
                                     income=b.get("net") or {}) if self.strategy else []
            if pinned:      # pinned/edited_by are not in the shown shape; the pins are named here
                prompt.insert(2, "Pinned by the human (kept exactly as shown, whatever you answer): "
                                 + ", ".join(pinned) + ".")
            if misfits:     # kept as the human set them; the Strategist should plan around them
                prompt.insert(2, "Warnings:\n" + "\n".join(misfits))
            if errors:
                prompt.insert(0, "Your previous answer was rejected: " + "; ".join(errors) + ". Fix exactly these problems"
                                 " and return the whole strategy again.\nYour rejected answer:\n" + (rejected or "(none given)"))
            trend = self._trend(b)
            if trend:
                prompt.append(trend)
            deps = GovDeps(self.game, self.store, self.log)
            base = {"model": self.s.model, "thinking_level": self.s.governor_thinking, "game": self.s.game,
                    "date": b["date"], "trigger": trigger, "current": current_directive(b)}
            ask = lambda agent: agent.run_sync("\n\n".join(prompt), deps=deps,
                                               usage_limits=UsageLimits(request_limit=self.s.max_requests_per_episode))
            result, _entry = self._call("strategy", ask,
                                        on_try=lambda e: base.update(model=e["model"], thinking_level=e["thinking"]))
            r = result.output
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
                new = keep_pinned(to_strategy(r.strategy, self.pillars), self.strategy)
                errs = validate(new, self.pillars, previous=self.strategy, tech_ids=self._tech_ids(), ids=self._action_ids(),
                                idle=idle_resources(b), income=b.get("net", {}))
            else:
                errs = []
            if r.change or trigger in IDENTITY_TRIGGERS:     # a new strategy, or one the human asked for
                errs = errs + identity_errors(r.identity, sp_traits)
            if new is not None and r.identity:
                new = new.model_copy(update={"identity": r.identity})
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
                retry_rejected = (strategy_for_prompt(to_strategy(r.strategy, self.pillars), self.pillars)
                                  if r.strategy else None)       # and the answer to fix, in the output shape
            elif errs:
                self.log.emit("strategy_rejected", date=b["date"], errors=errs[:10])
            elif accepted:
                # `new` was computed from a `self.strategy` snapshot taken before/around the model
                # call (and before the rule-learning, trace-saving and journal I/O just above); a
                # human edit or pin landed via the dashboard in that window must not be discarded,
                # so it is re-applied against the *live* strategy atomically with the commit.
                with self._strategy_lock:
                    new = keep_pinned(new, self.strategy)
                    self.strategy = new
                self._publish_strategy(new, b["date"], trigger, base.get("model", ""))
        except Exception as e:  # noqa: BLE001 - a failed review never stops play or pauses the game; retried at the next decision
            self.review_requested = trigger
            self._review_retry = True
            self.log.emit("episode_error", error=f"strategy review: {type(e).__name__}: {e}"[:500])
            return
        if retry_errors is not None:
            self._review_strategy(b, trigger, retried=True, errors=retry_errors, rejected=retry_rejected)

    def _set_strategy(self, s: Strategy, date: str, trigger: str, model: str) -> None:
        with self._strategy_lock:
            self.strategy = s
        self._publish_strategy(s, date, trigger, model)

    def _publish_strategy(self, s: Strategy, date: str, trigger: str, model: str) -> None:
        """Record `s` (already assigned to `self.strategy`) as a new version. Pure I/O: never called
        while holding `_strategy_lock`."""
        dumped = s.model_dump()
        self.log.state.info["strategy"] = dumped
        self.log.emit("strategy", date=date, trigger=trigger, model=model, reason=s.reason, strategy=dumped)

    def _tech_ids(self) -> set[str]:
        """Ids for preferred techs (the spec's tech action); see `_action_ids`."""
        return self._action_ids().get("tech", set())

    def _action_ids(self) -> dict[str, set[str]]:
        """Known ids per id-list action kind, from `data/<ids_from_corpus>.json` of the corpus (bare ids,
        or "<kind>:<id>" with `full_ids`); cached once every read succeeds (a failed read is logged and
        retried, never cached)."""
        if getattr(self, "_ids", None) is not None:
            return self._ids
        out: dict[str, set[str]] = {}
        ok = True
        for kind, a in (self.pillars.actions.items() if self.pillars else ()):
            if not a.corpus_files:
                continue
            ids: set[str] = set()
            for f in a.corpus_files:
                path = self.s.corpus_dir / "data" / f"{f}.json"
                try:
                    recs = json.loads(path.read_text(encoding="utf-8"))
                    ids |= {r["id"] if a.full_ids else r["id"].split(":", 1)[1] for r in recs}
                except (OSError, ValueError, KeyError, IndexError) as e:
                    self.log.emit("briefing_error", error=f"{kind} ids: {e}"[:200])
                    ok = False
            out[kind] = ids
        if ok:
            self._ids = out
        return out

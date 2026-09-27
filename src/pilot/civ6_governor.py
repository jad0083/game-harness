"""Civilization VI governor (docs/design/2026-09-26-civ6-governor-design.md, ruling 4): the game's AI
plays our civilization through AutoplayManager; the model gives macro orders between stretches.

    snapshot → decide (at decision points) → apply orders → read back
             → N x (autoplay one turn → wait for the hand-back → snapshot; stop early on an urgent change) → …

It reuses the Stellaris governor's structure (model pool, strategy reviews, pressure frame in share
mode, dashboard controls, telemetry); what differs is the game access (`civ6.Civ6Game`), the decision
(structured orders instead of a directive) and the clock (turns, dates "T<turn>")."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, replace

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from .civ6 import (
    ORDER_ACTION,
    UNKNOWN,
    Checked,
    Civ6Decision,
    Civ6Order,
    CorpusIndex,
    GameRefused,
    briefing_text,
    check_orders,
    held_outcome,
    idle_counts,
    metrics,
    order_base,
    order_key,
    order_record,
    order_record_text,
    order_situation,
    order_window,
    read_back,
    record_key,
    urgent_changes,
)
from .claude_code import resolve_model
from .governor import (
    EVENT_TRIGGERS,
    GovDeps,
    Governor,
    consult,
    frame_text,
    get_doc,
    governor_settings,
    remember_rule,
    served_model,
)
from .trace import serialize

ORDER_RECORD_HEADING = "Order record in this campaign (held until done / replaced by the AI):"

INSTRUCTIONS = """You are the governor of a Civilization VI civilization. The game's own AI plays it turn by
turn (units, tiles, city management, district and wonder placement, diplomacy) during stretches of
autoplay; between them you give macro orders that the harness carries out and checks: research, civic,
policies, production, purchase. Give an order only when it changes something the strategy needs: the
AI keeps playing whatever you leave alone, and may change your choices while it plays (the next
briefing says what held). Orders name corpus ids exactly as the briefing shows them.
The prompt already holds the briefing, the strategy frame (each pillar's share of effort), what your
last orders did, and the limits. Call a tool only for a specific missing fact (consult: game records;
price: the live price of an item in a city), at most twice; then answer.
Human instructions, when present, override the rules below."""

CHAT_INSTRUCTIONS = """You are the governor of a Civilization VI civilization, talking with the human who
oversees you. Answer their questions about the game and your decisions plainly and briefly, citing
briefing numbers. You cannot act in this conversation: orders are only given at decision points. If
the human wants something done, tell them to use "Decide now" or a standing order on the dashboard."""

def autoplay_turns(snapshot: dict, *, chunk: int, left: int) -> int:
    """Turns for the next autoplay call: `chunk` in peace (longer calls let the AI finish its
    multi-turn plans; one-turn calls stalled a Settler and the pantheon live), a single turn at war or
    with a threatened or besieged city (checks between every turn), never past the decision point."""
    danger = bool(snapshot.get("wars")) or any(c.get("threatened") or c.get("under_siege")
                                                for c in snapshot.get("cities", []))
    return max(1, min(1 if danger else chunk, left))


EVENT_TRIGGERS_CIV6 = (*EVENT_TRIGGERS, "city lost", "city threatened", "new era", "race lost")


def price(ctx: RunContext[GovDeps], city: str, item: str, currency: str = "gold") -> str:
    """The live price of a unit or building (corpus id, e.g. unit:warrior) in one of our cities, in
    gold or faith, and whether the game allows buying it now."""
    return json.dumps(ctx.deps.game.order({"kind": "price", "city": city, "id": item,
                                           "currency": "faith" if currency == "faith" else "gold"}))


class Civ6Stuck(RuntimeError):
    """The game did not play or hand back a turn in time, or stopped answering between turns."""


class _NotStarted(Civ6Stuck):
    """Autoplay still reads inactive after the start grace (and the turn has not moved)."""


@dataclass
class Tracked:
    """An order that took, followed on every snapshot until it resolves (ruling 13)."""
    c: Checked
    row: dict            # the order_outcome row so far (what, where, when ordered)
    base: dict           # `order_base`: turn, turns left, unit count once it took
    window: int          # turns it is followed (`order_window`)


class Civ6Governor(Governor):
    event_triggers = EVENT_TRIGGERS_CIV6
    status_poll_s = 1.0              # autoplay-status polls while the AI plays a turn (a tiny call)
    turn_deadline_s = 600.0          # one AI turn; late-game turns take minutes and polls go unanswered
    start_grace_s = 20.0             # autoplay must show as running (or the turn advance) by then
    snapshot_tries = 3               # snapshots between turns before the run waits for the human
    start_retries = 2                # an autoplay start whose reply was lost and that did not run is sent again

    def __init__(self, settings, game, log, **kw):
        super().__init__(settings, game, log, **kw)
        self.index = CorpusIndex.load(settings.corpus_dir)
        self._wonders = frozenset(self.index.key_of[i] for i in self.index.ids("wonder"))
        text = (settings.corpus_dir / "pilot.md").read_text(encoding="utf-8")
        text += "\n\n" + (settings.corpus_dir / "strategy.md").read_text(encoding="utf-8")
        learned = settings.corpus_dir / "learned" / "strategy.md"
        if learned.exists():
            text += "\n\n## Rules learned in play\n" + learned.read_text(encoding="utf-8")
        self._text = text
        self.__dict__.pop("_agents", None)
        self._failed_last: set[str] = set()      # order keys that did not take at the last decision
        self._report: list[str] = []             # what the last decision's orders did, for the next prompt
        self._tracking: list[Tracked] = []       # orders that took and have not resolved yet (ruling 13)
        self._resolved: list[tuple[dict, str]] = []   # (row, order text) resolved since the last decision
        self._order_rows: list[dict] = []        # every order_outcome row of the campaign (ruling 14)
        self._seen_idle: dict[int, list[str]] = {}   # turn -> kinds with nothing in progress (ruling 16)
        self._tracked_turn: int | None = None
        self._after_orders: dict | None = None    # the snapshot read back after the last orders
        log.state.info["directives"] = []
        log.state.info["decide_turns"] = settings.decide_every_turns
        log.state.info["controls"] = [c for c in log.state.info.get("controls", []) if c not in ("override", "set_speed")]

    # ---- agents -------------------------------------------------------------------------------------

    def _build_agents(self) -> None:
        """Agents are built per role on first use (`_build`)."""
        self.agent = None

    def _build(self, role: str, settings, model):
        if role in ("strategy",):
            return super()._build(role, settings, model)
        model = resolve_model(model)
        if role == "chat":
            return Agent(model, deps_type=GovDeps, output_type=str, instructions=CHAT_INSTRUCTIONS + "\n\n" + self._text,
                         tools=[Tool(f) for f in (consult, get_doc)], model_settings=governor_settings(settings), retries=2)
        return Agent(model, deps_type=GovDeps, output_type=Civ6Decision, instructions=INSTRUCTIONS + "\n\n" + self._text,
                     tools=[Tool(f) for f in (consult, get_doc, price, remember_rule)],
                     model_settings=governor_settings(settings), retries=2)

    # ---- dashboard controls that differ ----------------------------------------------------------

    def override(self, directive: str) -> None:
        raise ValueError("Civilization VI has no directives: give a standing order or use Decide now")

    def set_speed(self, speed: str) -> None:
        raise ValueError("Civilization VI runs at the game's own autoplay pace")

    def set_months(self, months: int) -> None:
        """The dashboard's pace control: turns of autoplay between decisions here."""
        if not isinstance(months, int) or not 1 <= months <= 50:
            raise ValueError("turns must be a whole number from 1 to 50")
        self.s = replace(self.s, decide_every_turns=months)
        self.log.state.info["decide_turns"] = months
        self.log.emit("pace", decide_turns=months)

    # ---- campaign, briefing ------------------------------------------------------------------------

    def _gold_reserve(self) -> int:
        a = self.pillars.actions.get("purchase") if self.pillars else None
        return a.gold_reserve if a else 0

    def _briefing(self, b: dict) -> str:
        return briefing_text(b, self.index, self._gold_reserve())

    def _set_campaign(self, b: dict) -> None:
        """Campaign = civ6/<leader>_<map seed> (ruling 7), or PILOT_CAMPAIGN."""
        leader = re.sub(r"^LEADER_", "", str(b.get("leader") or "unknown")).lower()
        name = self.s.campaign or f"{leader}_{b.get('map_seed') or 'noseed'}"
        self._campaign_key = (b.get("leader"), b.get("map_seed"))
        self.log.set_campaign(self.s.game, name, f"{b.get('civ_name') or ''} — {b.get('leader_name') or ''}")
        self._load_campaign_state()
        self._load_order_record()

    def _load_order_record(self) -> None:
        """The campaign's order record from earlier runs (ruling 13): its order_outcome rows, and which
        turns had nothing in progress (metrics rows). Advisory: a failed read leaves it empty."""
        tel, cid = self.log.telemetry, self.log.campaign_id
        if tel is None or not cid:
            return
        try:
            self._order_rows = tel.campaign_events(cid, "order_outcome")
            self._seen_idle = {int(r["turn"]): list(r["idle"]) for r in tel.metrics_rows(cid)
                               if isinstance(r.get("turn"), int) and isinstance(r.get("idle"), list)}
        except Exception as e:  # noqa: BLE001 - the record is advisory
            self.log.emit("briefing_error", error=f"loading the order record: {e}"[:200])
        self._publish_record()

    def _trend(self, b: dict) -> str:
        return ""

    # ---- the loop ----------------------------------------------------------------------------------

    def _start(self) -> dict | None:
        while not self.control.stopping:
            try:
                self._stop_autoplay()                  # never decide while the AI is playing
                b = self.game.snapshot()
                if (b.get("autoplay") or {}).get("active"):
                    raise Civ6Stuck("autoplay is still running and did not stop")
                self._set_campaign(b)
                self.last_briefing = self._briefing(b)
                self.log.state.game_date = b["date"]
                reviewed = self.strategy is None and self.pillars is not None
                if reviewed:
                    self._review_strategy(b, "start of run")
                self._decide(b, "start of run", reviewed_at_start=reviewed)
                return self._after_orders or b
            except Exception as e:  # noqa: BLE001
                self._needs_attention(f"could not start: {type(e).__name__}: {e}. Load the game (with the tuner "
                                      "enabled) and press Resume to try again.")
                while self.control.paused and not self.control.stopping:
                    time.sleep(0.5)
        return None

    def _handle_request(self, req: tuple[str, str], b: dict) -> dict:
        kind = req[0]
        if kind in ("override", "speed"):
            self.log.emit("episode_error", error=f"{kind} is not available for Civilization VI")
            return b
        return super()._handle_request(req, b)

    def _stop_autoplay(self) -> None:
        try:
            self.game.autoplay_stop()
        except Exception as e:  # noqa: BLE001 - one-turn stretches end by themselves
            self.log.emit("briefing_error", error=f"autoplay stop: {e}"[:200])

    def _run_until_next_decision(self, last: dict) -> tuple[dict | None, str]:
        """The AI plays one turn at a time (or `autoplay_chunk` turns) until `decide_every_turns` have
        passed or something urgent happened. Between turns the game is idle and answers at once: the
        snapshot, urgent checks, human requests and orders all happen there, and stopping early is
        simply not starting the next turn. A turn that does not end (or never starts) within its deadline, or a game that
        stops answering between turns, waits for the human (needs attention)."""
        last = self._after_orders or last
        self._after_orders = None
        target = last["turn"] + self.s.decide_every_turns
        self._status("playing")
        while True:
            if self.control.stopping:
                return None, "stop"
            if self.control.paused:
                return last, ""
            if not self.requests.empty():
                return last, "request"
            try:
                self._play_turns(last["turn"], autoplay_turns(last, chunk=self.s.autoplay_chunk,
                                                              left=target - last["turn"]))
                b = self._snapshot_between_turns()
            except Civ6Stuck as e:
                self._needs_attention(f"{e}. Check the game (a dialog, a crash, the main menu), then press Resume.")
                return last, ""
            if getattr(self, "_campaign_key", None) and (b.get("leader"), b.get("map_seed")) != self._campaign_key:
                self._needs_attention(f"the game changed: {b.get('leader')} on map {b.get('map_seed')}, this run governs "
                                      f"{self._campaign_key[0]} on map {self._campaign_key[1]}. Load that game again and "
                                      "press Resume, or start a new run.")
                return last, ""
            self.log.emit("metrics", **metrics(b))
            self._track(b)
            self.log.state.game_date = b["date"]
            self.log.state.turns_advanced += b["turn"] - last["turn"]
            urgent = urgent_changes(last, b, self._gold_reserve(), self._wonders)
            urgent += self._newly_missed_milestones(last["date"], b["date"])
            if urgent:
                return b, "urgent: " + "; ".join(urgent)
            if b["turn"] >= target:
                return b, f"scheduled ({self.s.decide_every_turns} turns)"
            last = b

    def _play_turns(self, turn: int, n: int) -> None:
        """Autoplay `n` turns (the chunk; 1 by default) and wait until the game hands them back (turn
        advanced by `n`, autoplay off). Status polls may go unanswered while the AI plays (the tuner
        is silent then); only the deadline (per turn) counts. A lost reply to the autoplay call is not
        a failure: the polls tell whether it started; a refusal is. A start whose reply was lost and
        that never ran (the tuner timed out, seen live at T57, T99, T117 and T120; Resume then
        started it at once) is sent again, `start_retries` times, before the run waits for the human."""
        for attempt in range(self.start_retries + 1):
            started = time.time()
            lost = False
            try:
                self.game.autoplay(n)
            except GameRefused as e:
                raise Civ6Stuck(f"autoplay did not start at T{turn}: {e}"[:400]) from e
            except Exception as e:  # noqa: BLE001 - no reply: it may have started; the polls tell
                lost = True
                self.log.emit("briefing_error", error=f"autoplay at T{turn}: {e}"[:200])
            try:
                self._wait_turns(turn, n, started)
                return
            except _NotStarted as e:
                if not lost or attempt == self.start_retries:
                    raise
                self.log.emit("briefing_error", error=f"{e}; its reply was lost, so it is sent again "
                                                      f"({attempt + 1} of {self.start_retries})"[:300])

    def _wait_turns(self, turn: int, n: int, started: float) -> None:
        seen_active, misses, deadline = False, 0, self.turn_deadline_s * n
        idle_since: tuple[float, int] | None = None
        while True:
            time.sleep(self.status_poll_s)
            try:
                st = self.game.autoplay_status()
            except Exception:  # noqa: BLE001 - the game is busy with the AI's turn
                st, misses = None, misses + 1
            elapsed = time.time() - started
            if st is not None:
                if st.get("turn", turn) >= turn + n and not st.get("active"):
                    self.log.emit("turn", turn=st["turn"], turns=n, seconds=round(elapsed, 1), unanswered_polls=misses)
                    return
                seen_active = seen_active or bool(st.get("active")) or st.get("turn", turn) > turn
                if not seen_active and elapsed > self.start_grace_s:
                    raise _NotStarted(f"autoplay did not start at T{turn} (still inactive after {elapsed:.0f} s)")
                # Autoplay reads inactive (turns 0) before its last turn ends (seen live), so an early
                # end counts only when the turn stays unchanged for the start grace.
                if seen_active and not st.get("active"):
                    if idle_since is None or idle_since[1] != st.get("turn"):
                        idle_since = (time.time(), st.get("turn"))
                    elif time.time() - idle_since[0] > self.start_grace_s:
                        self.log.emit("turn", turn=st["turn"], turns=st["turn"] - turn, seconds=round(elapsed, 1),
                                      unanswered_polls=misses, note="autoplay ended early")
                        return
                else:
                    idle_since = None
            if elapsed > deadline:
                self._stop_autoplay()
                raise Civ6Stuck(f"T{turn} did not end within {deadline:.0f} s ({misses} status polls unanswered)")

    def _snapshot_between_turns(self) -> dict:
        err: Exception | None = None
        for i in range(self.snapshot_tries):
            try:
                return self.game.snapshot()
            except Exception as e:  # noqa: BLE001
                err = e
                self.log.emit("briefing_error", error=f"snapshot: {e}"[:200])
                if i + 1 < self.snapshot_tries:
                    time.sleep(self.status_poll_s)
        raise Civ6Stuck(f"no snapshot after {self.snapshot_tries} tries: {err}"[:400])

    # ---- a decision ----------------------------------------------------------------------------------

    def _limits_text(self) -> str:
        if not self.pillars:
            return ""
        acts = self.pillars.actions
        per = ", ".join(f"{o} {acts[a].max_orders}" for o, a in ORDER_ACTION.items() if a in acts)
        text = f"Orders per decision at most: {per}."
        buy = acts.get("purchase")
        if buy:
            text += (f" Purchases keep {buy.gold_reserve} gold and {buy.faith_reserve} faith in reserve and cost at most "
                     f"{buy.treasury_share:.0%} of the balance"
                     + (f" ({buy.threatened_share:.0%} for a threatened city, down to the reserve)" if buy.threatened_share else "")
                     + ".")
        return text

    # ---- the order record (docs/design/2026-09-27-civ6-levers-design.md, rulings 12-16) -------------

    def _track(self, b: dict) -> None:
        """Follow every open order on this snapshot (once per turn): resolved ones emit their row."""
        turn = b.get("turn")
        if not isinstance(turn, int) or turn == self._tracked_turn:
            return
        self._tracked_turn = turn
        self._seen_idle[turn] = [k for k in ("research", "civic") if not b.get(k)]
        still = []
        for t in self._tracking:
            result, by = held_outcome(t.c, t.base, b, t.window)
            if result == "open":
                still.append(t)
            else:
                self._resolve(t, result, by, b)
        self._tracking = still
        self._publish_record()

    def _resolve(self, t: Tracked, result: str, by: str | None, b: dict, detail: str = "") -> None:
        row = {**t.row, "result": result, "by": self.index.cid(by) if by else None,
               "turns": (b.get("turn") or 0) - (t.base.get("turn") or 0), "date": b.get("date") or f"T{b.get('turn')}",
               "turn": b.get("turn"), "detail": detail}
        self._resolved.append((row, _describe(t.c.order)))
        self._emit_row(row)

    def _emit_row(self, row: dict) -> None:
        self._order_rows.append(row)
        self.log.emit("order_outcome", **row)

    def _order_row(self, c: Checked, b: dict, situation: str | None) -> dict:
        """An order's row before its outcome: what, where, when ordered (`order_kind`, since an
        event's own `kind` is order_outcome)."""
        o = c.order
        oid = ", ".join(o.get("ids") or []) if o.get("kind") == "policies" else o.get("id")
        return {"order_kind": o.get("kind"), "key": record_key(o, situation),
                "item_kind": "policy" if o.get("kind") == "policies" else self.index.kind_of.get(o.get("id") or ""),
                "id": oid, "city": (c.wire or {}).get("city") or o.get("city") or "",
                "currency": o.get("currency") if o.get("kind") == "purchase" else None, "situation": situation,
                "ordered": b.get("date") or f"T{b.get('turn')}", "top3_hit": None}

    def _now_turn(self) -> int:
        return self._tracked_turn or max([r.get("turn") or 0 for r in self._order_rows] + [0])

    def _record(self) -> dict:
        spec = self.pillars.orders if self.pillars else None
        return order_record(self._order_rows, self._now_turn(), spec) if spec else {}

    def _record_text(self) -> str:
        spec = self.pillars.orders if self.pillars else None
        if spec is None:
            return ""
        return order_record_text(self._record(), idle_counts(self._seen_idle, self._now_turn(), spec.window_turns),
                                 spec.window_turns)

    def _publish_record(self) -> None:
        self.log.state.info["order_record"] = self._record()

    def _records_section(self) -> str:
        """The Strategist sees the order record, not a directive record (ruling 15)."""
        return ORDER_RECORD_HEADING + "\n" + (self._record_text() or "(no orders judged yet)")

    def _held_report(self, b: dict) -> list[str]:
        """What happened to earlier orders since the last decision: completed, replaced by the AI
        with X, or still in force."""
        out = []
        for r, what in self._resolved:
            fate = {"completed": f"completed by {r['date']}",
                    "held": f"held through its window ({r['ordered']}-{r['date']})",
                    "overridden": f"replaced by the AI with {r.get('by') or 'nothing'} by {r['date']}",
                    "invalidated": f"no longer available at {r['date']}"
                                   + (f" (the city builds {r['by']})" if r.get("by") else ""),
                    "unknown": f"cannot be told at {r['date']}"
                               + (f" (the city builds {r['by']}: completed and lost, or replaced)" if r.get("by") else ""),
                    }.get(r["result"])
            if fate:
                out.append(f"{what}: {fate}")
        for t in self._tracking:
            out.append(f"{_describe(t.c.order)}: in force at T{b.get('turn')} "
                       f"({(b.get('turn') or 0) - (t.base.get('turn') or 0)} of {t.window} turns followed)")
        self._resolved = []
        return out

    def _idle_without_order(self, b: dict, d: Civ6Decision) -> list[str]:
        """Research or civic with nothing in progress (and something to choose) that the answer gives
        no valid order for (ruling 16)."""
        opts = b.get("options") or {}
        valid = {c.order["kind"] for c in check_orders(d.orders, b, self.pillars, self.index, self._failed_last)
                 if not c.error}
        return [kind for kind, offered in (("research", "techs"), ("civic", "civics"))
                if not b.get(kind) and opts.get(offered) and kind not in valid]

    def _fill(self, b: dict, kind: str) -> Civ6Order | None:
        """The governor's own choice for an idle research or civic: the first item of the strategy's
        preferred list that the game offers, else the first item offered."""
        offered = [self.index.cid(k) for k in (b.get("options") or {}).get("techs" if kind == "research" else "civics") or []]
        field_ = "prefer_techs" if kind == "research" else "prefer_civics"
        preferred = ([i for _, pl in self.strategy.sorted_pillars() for i in getattr(pl, field_, None) or []]
                     if self.strategy else [])
        for i in [*preferred, *offered]:
            o = Civ6Order(kind=kind, id=i)
            if i in offered and order_key(o.model_dump()) not in self._failed_last:
                return o
        return None

    def _decide(self, b: dict, reason: str, reviewed_at_start: bool = False) -> None:
        self._status("deciding")
        self._last_b = b
        self.log.state.episodes += 1
        self.log.state.game_date = b["date"]
        self.log.emit("metrics", **metrics(b))
        if self.log.telemetry is not None and self.log.campaign_id:
            try:
                self.log.telemetry.score(self.log.campaign_id)
            except Exception as e:  # noqa: BLE001 - advisory
                self.log.emit("briefing_error", error=f"outcome scoring: {e}"[:200])
        self._track(b)
        held = self._held_report(b)
        extra = self.human.take_all()
        press = self._pressures() if self.strategy and self.pillars else None
        self.last_briefing = self._briefing(b)
        prompt = [f"Decision point: {reason}.",
                  (frame_text(self.strategy, self.pillars, self._milestones_text(), press) if self.pillars else "")
                  or "No strategy yet.",
                  "Briefing (live snapshot):", self.last_briefing, self._limits_text()]
        if self._report or held:
            prompt.append("What your last orders did:\n" + "\n".join(f"- {x}" for x in self._report + held))
        record = self._record_text()
        if record:
            prompt.append(ORDER_RECORD_HEADING + "\n" + record)
        if self.orders:
            prompt.append("STANDING ORDERS from the human (always follow these): "
                          + " | ".join(f"{i + 1}. {o}" for i, o in enumerate(self.orders)))
        if extra:
            prompt.append("HUMAN INSTRUCTIONS (follow these): " + " | ".join(extra))
        started = time.time()
        deps = GovDeps(self.game, self.store, self.log)
        n = self.log.state.episodes
        base = {"episode": n, "model": self.s.model, "thinking_level": self.s.governor_thinking, "game": self.s.game,
                "date": b["date"], "trigger": reason, "current": None}

        def ask(agent):
            return agent.run_sync("\n".join(p for p in prompt if p), deps=deps,
                                  usage_limits=UsageLimits(request_limit=self.s.governor_max_requests))
        try:
            result, _ = self._call("decisions", ask,
                                   on_try=lambda e: base.update(model=e["model"], thinking_level=e["thinking"]))
        except Exception as e:  # noqa: BLE001 - keep playing: the AI carries on with the current choices
            if isinstance(e, UsageLimitExceeded):
                e = RuntimeError(f"no answer within {self.s.governor_max_requests} model calls; no orders given")
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
        tokens_in, tokens_out = usage.input_tokens or 0, usage.output_tokens or 0

        idle = self._idle_without_order(b, d)
        if idle:        # ruling 16: one corrective retry, as for the Strategist's validation
            opts = b.get("options") or {}
            ask_again = "; ".join(
                f"nothing is being {'researched' if k == 'research' else 'progressed'} and your answer gives no valid "
                f"{k} order (options: {', '.join(self.index.cid(x) for x in opts.get('techs' if k == 'research' else 'civics') or [])})"
                for k in idle)
            corrective = (f"Your answer was incomplete: {ask_again}. Return your whole decision again with "
                          f"{' and '.join(f'a {k} order' for k in idle)} added; otherwise the governor fills it from "
                          "the strategy's preferred list.")
            try:
                again, _ = self._call("decisions", lambda agent: agent.run_sync(
                    corrective, deps=deps, message_history=result.all_messages(),
                    usage_limits=UsageLimits(request_limit=self.s.governor_max_requests)))
                u2 = again.usage
                st.tokens_in += u2.input_tokens or 0
                st.tokens_out += u2.output_tokens or 0
                st.requests += u2.requests or 0
                tokens_in, tokens_out = tokens_in + (u2.input_tokens or 0), tokens_out + (u2.output_tokens or 0)
                result, d = again, again.output
            except Exception as e:  # noqa: BLE001 - the governor fills the blocker below
                self.log.emit("briefing_error", error=f"blocker retry: {type(e).__name__}: {e}"[:200])
        filled: set[str] = set()
        for kind in self._idle_without_order(b, d) if idle else []:
            o = self._fill(b, kind)
            if o is not None:
                d.orders.append(o)
                filled.add(order_key(o.model_dump()))

        outcomes, applied = self._apply(d, b, filled)
        summary = "; ".join(f"{o['order']}: {o['outcome']}" for o in outcomes) or "no orders"
        decision = "orders" if d.orders else "keep"
        st.last_decision = f"{b['date']}: {summary} — {d.reason}"
        self.log.emit("episode", situation=reason, decision=f"{summary}: {d.reason}", date=b["date"],
                      resolved=all(o["outcome"] == "stuck" for o in outcomes), actions=applied,
                      seconds=round(time.time() - started, 1), tokens_in=tokens_in, tokens_out=tokens_out)
        self.log.save_trace(n, {**base, "decision": decision, "reason": d.reason, "outcome": summary[:2000],
                                "orders": outcomes, "serves": d.serves, "seconds": round(time.time() - started, 1),
                                "tokens_in": tokens_in, "tokens_out": tokens_out, "retried_for": idle or None,
                                "steps": serialize(result.all_messages())})
        self.store.add_episode(reason, f"{summary}: {d.reason}", "applied" if applied else "kept", b["date"])
        self.journal.note(f"{summary} — {d.reason}", b["date"])
        if d.note:
            self.journal.note(d.note, b["date"])
        if not (reason == "start of run" and reviewed_at_start):
            self._since_retro += 1
            if self.s.retro_every and self._since_retro >= self.s.retro_every and self.pillars is not None:
                self._review_strategy(self._after_orders or b, f"scheduled after {self.s.retro_every} decisions")

    def _apply(self, d: Civ6Decision, b: dict, filled: set[str] = frozenset()) -> tuple[list[dict], int]:
        """Check, carry out and read back the decision's orders. Returns one outcome per order and how
        many took. Never raises: a failure is an outcome, reported at the next decision. Only a game
        refusal or a read-back that contradicts the order counts as "did not stick" (refused if
        repeated unchanged); an order whose effect cannot be told (no reply, no read-back) is
        "unknown". Orders that took are followed until they resolve (the order record); refused,
        lost and bought ones get their row at once. `filled`: order keys the governor added."""
        checked = check_orders(d.orders, b, self.pillars, self.index, self._failed_last)
        results: list[tuple[Checked, str, bool]] = []      # (order, outcome, counts as did-not-stick)
        sent: list[tuple[Checked, dict]] = []
        for c in checked:
            if c.error:
                results.append((c, f"refused: {c.error}", False))
                continue
            try:
                reply = self.game.order(c.wire)
            except Exception as e:  # noqa: BLE001
                reply = {"ok": False, "transport": True, "error": f"{type(e).__name__}: {e}"}
            if reply.get("ok") or reply.get("transport"):
                sent.append((c, reply))                     # a lost reply may still have run: read it back
            else:
                results.append((c, f"refused by the game: {reply.get('error')}", True))
        totals: dict[str, float] = {}
        for c, reply in sent:
            if "spend" in c.expect:
                totals[c.expect["spend"]] = totals.get(c.expect["spend"], 0.0) + float(reply.get("cost") or 0)
        for c, _ in sent:
            if "spend" in c.expect:
                c.expect["total"] = totals[c.expect["spend"]]
        after = None
        if sent:
            try:
                after = self.game.snapshot()
            except Exception as e:  # noqa: BLE001
                self.log.emit("briefing_error", error=f"read-back: {e}"[:200])
        for c, reply in sent:
            if after is None:
                results.append((c, f"{UNKNOWN}: not read back (no snapshot)", False))
                continue
            status = read_back(c, reply, after)
            if reply.get("transport") and status != "stuck":
                status = f"{UNKNOWN}: no reply ({reply.get('error')}); {status}"
            results.append((c, status, status != "stuck" and not status.startswith(UNKNOWN)))
        position = {id(c): i for i, c in enumerate(checked)}
        results.sort(key=lambda r: position[id(r[0])])          # outcomes in the model's order
        self._failed_last = {order_key(c.order) for c, _, failed in results if failed}
        outcomes = []
        for c, status, _ in results:
            by_governor = order_key(c.order) in filled
            outcomes.append({"order": _describe(c.order) + (" (filled by the governor)" if by_governor else ""),
                             "outcome": status, "kind": c.order.get("kind"),
                             "id": c.order.get("id") or ", ".join(c.order.get("ids") or []),
                             "city": (c.wire or {}).get("city") or c.order.get("city") or "",
                             **({"by": "governor"} if by_governor else {})})
            self._record_order(c, status, b, after)
        failed = {id(c) for c, _, f in results if f}
        self._report = []
        for (c, status, _), o in zip(results, outcomes, strict=True):
            if status == "stuck":
                self._report.append(f"{o['order']}: carried out and read back")
            elif id(c) in failed:
                self._report.append(f"{o['order']}: {status} (did not stick; not retried blindly)")
            else:
                self._report.append(f"{o['order']}: {status}")
        for o in outcomes:
            self.log.emit("strategy_action", action="order", result=f"{o['order']}: {o['outcome']}"[:300])
        self._after_orders = after
        self._publish_record()
        return outcomes, sum(1 for o in outcomes if o["outcome"] == "stuck")

    def _record_order(self, c: Checked, status: str, b: dict, after: dict | None) -> None:
        """The order record at apply time (ruling 13): an order that took (or may have: no reply) ends
        the following of our older order of the same kind and city (superseded); one that took is
        followed from now on, except a purchase, which completed at once; refused and lost orders
        get their row now."""
        o = c.order
        situation = order_situation(b, c.expect["producing"], c.expect["city"]) if "producing" in c.expect else None
        row = self._order_row(c, b, situation)
        now = after or b
        if status == "stuck" or status.startswith(UNKNOWN):
            city = row["city"].lower()
            same = [t for t in self._tracking if t.c.order.get("kind") == o.get("kind")
                    and (t.row.get("city") or "").lower() == city]
            for t in same:
                self._resolve(t, "superseded", None, now, detail=f"replaced by our own order {_describe(o)}")
            self._tracking = [t for t in self._tracking if t not in same]
        if status == "stuck" and o.get("kind") != "purchase":
            spec = self.pillars.orders if self.pillars and self.pillars.orders else None
            base = order_base(c, after or b)
            window = order_window(o["kind"], base.get("turns_left"), *((spec.open_cap_turns, spec.open_grace_turns)
                                                                        if spec else ()))
            self._tracking.append(Tracked(c, row, base, window))
            return
        if status == "stuck":
            result, detail = "completed", ""
        elif status.startswith(f"{UNKNOWN}: no reply"):
            result, detail = "lost", status
        elif status.startswith(UNKNOWN):
            result, detail = "unknown", status
        else:
            result, detail = "refused", status
        self._emit_row({**row, "result": result, "by": None, "turns": 0, "date": now.get("date") or f"T{now.get('turn')}",
                        "turn": now.get("turn"), "detail": detail[:300]})


def _describe(o: dict) -> str:
    if o.get("kind") == "policies":
        return f"policies {', '.join(o.get('ids') or [])}"
    where = f" in {o['city']}" if o.get("city") else ""
    cur = f" with {o['currency']}" if o.get("kind") == "purchase" else ""
    return f"{o.get('kind')} {o.get('id')}{where}{cur}"

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
import uuid
from dataclasses import dataclass, replace

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.usage import UsageLimits

from .civ6 import (
    ORDER_ACTION,
    STAND_KEYS,
    UNKNOWN,
    Checked,
    Civ6Decision,
    Civ6Order,
    CorpusIndex,
    GameRefused,
    _actor_id,
    _ls_unit,
    about_to_fall,
    ai_strategy_states,
    briefing_text,
    check_orders,
    faith_reserve_now,
    gold_reserve_now,
    held_outcome,
    idle_counts,
    in_danger,
    is_defender,
    metrics,
    order_base,
    order_key,
    order_record,
    order_record_text,
    order_situation,
    order_window,
    read_back,
    record_key,
    stand_verdict,
    top3_hits,
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
    multi-turn plans; one-turn calls stalled a Settler and the pantheon live), a single turn at war
    with a major or with a city in danger (`in_danger`) or about to fall (`about_to_fall`: one
    capturer next to it and a burst that would take the garrison is not "in danger"), so the checks
    run between every turn; never past the decision point. Amendment A1 of
    docs/design/2026-09-27-civ6-levers-design.md: "threatened" (any enemy within 3 tiles) held in 93%
    of city snapshots, so the chunk almost never ran."""
    war = any(w.get("major", True) for w in snapshot.get("wars") or [])
    danger = war or any(in_danger(c) or about_to_fall(c) for c in snapshot.get("cities", []))
    return max(1, min(1 if danger else chunk, left))


EVENT_TRIGGERS_CIV6 = (*EVENT_TRIGGERS, "city lost", "city threatened", "new era", "race lost")


def price(ctx: RunContext[GovDeps], city: str, item: str, currency: str = "both") -> str:
    """The live price of a unit or building (corpus id, e.g. unit:warrior) in one of our cities, in
    gold and in faith (or only `currency`), and whether the game allows buying it now."""
    ask = lambda cur: ctx.deps.game.order({"kind": "price", "city": city, "id": item, "currency": cur})
    if currency in ("gold", "faith"):
        return json.dumps(ask(currency))
    return json.dumps({cur: ask(cur) for cur in ("gold", "faith")})


def prices_seen(messages) -> dict[tuple[str, str, str], dict]:
    """The `price` tool's answers in a decision, by (city lowercased, corpus id, currency): a known
    price over a purchase's cap is refused before sending (ruling 19)."""
    calls, out = {}, {}
    for m in messages:
        for part in getattr(m, "parts", []):
            if isinstance(part, ToolCallPart) and part.tool_name == "price":
                calls[part.tool_call_id] = part.args_as_dict()
            elif isinstance(part, ToolReturnPart) and part.tool_name == "price" and part.tool_call_id in calls:
                args = calls[part.tool_call_id]
                try:
                    reply = json.loads(part.content) if isinstance(part.content, str) else part.content
                except ValueError:
                    continue
                if not isinstance(reply, dict):
                    continue
                cur = args.get("currency") if args.get("currency") in ("gold", "faith") else None
                answers = {cur: reply} if cur else {k: reply.get(k) for k in ("gold", "faith")}
                for k, r in answers.items():
                    if isinstance(r, dict) and r.get("ok") is not False and isinstance(r.get("cost"), (int, float)):
                        out[(str(args.get("city", "")).strip().lower(), str(args.get("item", "")), k)] = {
                            "cost": r["cost"], "allowed": bool(r.get("allowed"))}
    return out


# turn-ready's reasons that mean the game may still be playing a turn (a start whose reply was lost
# may be running): autoplay on, the turn over or sent, or one of those unreadable. A popup does not
# stop autoplay (E11) and a busy engine settles; neither means a turn is being played.
_PLAYING = ("autoplay active", "not our turn", "turn already sent")


def playing_reasons(why) -> list[str]:
    return [str(w) for w in why or [] if str(w) in _PLAYING or str(w).startswith("cannot check")]


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
    # the last stand's safety limits (docs/design/2026-09-27-civ6-levers-design.md, ruling 24)
    stand_max_actions = 8            # actions per stand (a city plus 2-4 nearby units, with margin)
    stand_budget_s = 90.0            # wall-clock per stand
    stand_pause_s = 1.5              # between an action and its GameCore read-back
    stand_idle_polls = 5             # turn-ready polls before the hand-back...
    stand_idle_poll_s = 1.0          # ...this far apart

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
        self._stand_streak: dict[str, int] = {}   # city -> last stands in a row (ruling 22)
        self._stand_capped: set[str] = set()      # cities whose cap the journal already noted
        self._stand_first_fails = 0               # stands whose first action did not take (ruling 26)
        self._stand_off = ""                      # why the stand turned itself off for this run
        self._pinned: list[dict] = []             # units the last stand pinned, checked at the next snapshot
        self._ai_log_next = 0                     # where the next read of the AI's strategy log starts (ruling 29)
        self._ai_rows: list = []                  # our player's rows of that log: [turn, strategy, status]
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

    def _buy_limits(self):
        return self.pillars.actions.get("purchase") if self.pillars else None

    def _gold_reserve(self, b: dict) -> int:
        """Today's gold reserve (ruling 18): it grows with a deficit."""
        return gold_reserve_now(b, self._buy_limits())

    def _briefing(self, b: dict) -> str:
        return briefing_text(b, self.index, limits=self._buy_limits(), strategies=ai_strategy_states(self._ai_rows))

    def _read_ai_strategies(self, b: dict) -> None:
        """The AI's own strategies for our player (ruling 29): at most one read of its log per
        decision, from where the last one ended. Advisory: a failed read keeps what is known."""
        read = getattr(self.game, "ai_strategies", None)
        if read is None:
            return
        try:
            r = read(self._ai_log_next, int(b.get("player") or 0))
        except Exception as e:  # noqa: BLE001 - advisory
            self.log.emit("briefing_error", error=f"AI strategy log: {e}"[:200])
            return
        if r.get("restarted"):
            self._ai_rows = []
        self._ai_rows += [list(x) for x in r.get("rows") or []]
        self._ai_log_next = int(r.get("next") or 0)

    def _set_campaign(self, b: dict) -> None:
        """Campaign = civ6/<leader>_<map seed> (ruling 7), or PILOT_CAMPAIGN."""
        leader = re.sub(r"^LEADER_", "", str(b.get("leader") or "unknown")).lower()
        name = self.s.campaign or f"{leader}_{b.get('map_seed') or 'noseed'}"
        self._campaign_key = (b.get("leader"), b.get("map_seed"))
        self.log.set_campaign(self.s.game, name, f"{b.get('civ_name') or ''} — {b.get('leader_name') or ''}")
        self._load_campaign_state()
        self._load_order_record()

    def _load_order_record(self) -> None:
        """The campaign's order record from earlier runs (ruling 13): its order_outcome rows, the
        orders still being followed (`order_followed` events with no outcome yet), and which turns had
        nothing in progress (metrics rows). Advisory: a failed read leaves it empty."""
        tel, cid = self.log.telemetry, self.log.campaign_id
        if tel is None or not cid:
            return
        try:
            self._order_rows = tel.campaign_events(cid, "order_outcome")
            done = {r.get("ref") for r in self._order_rows if r.get("ref")}
            mine = {t.row.get("ref") for t in self._tracking}
            for f in tel.campaign_events(cid, "order_followed"):
                if f.get("ref") and f["ref"] not in done and f["ref"] not in mine:
                    c = Checked(order=f["order"], wire=f.get("wire"), expect=f["expect"])
                    self._tracking.append(Tracked(c, {**f["row"], "ref": f["ref"]}, f["base"], int(f["window"])))
                    mine.add(f["ref"])
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
                falling = self._stand_city(last)
                if falling is not None:
                    self._last_stand(last, falling)            # ends with a one-turn hand-back
                else:
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
            self._check_pins(b)
            self.log.state.game_date = b["date"]
            self.log.state.turns_advanced += b["turn"] - last["turn"]
            urgent = urgent_changes(last, b, self._gold_reserve(b), self._wonders)
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
        started it at once) is sent again, `start_retries` times, before the run waits for the human,
        but only once turn-ready shows nothing running (`_after_lost_start`): an inactive status
        reading may come from a start that runs (autoplay reads inactive before its last turn ends)."""
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
                # a lost reply waits twice the grace before sending again: a slow start must show first
                self._wait_turns(turn, n, started, self.start_grace_s * (2 if lost else 1))
                return
            except _NotStarted as e:
                if not lost or attempt == self.start_retries:
                    raise
                state, seen = self._after_lost_start(turn)
                if isinstance(state, int):
                    self.log.emit("turn", turn=state, turns=state - turn, seconds=round(time.time() - started, 1),
                                  note="read by turn-ready after a lost start reply")
                    return
                if state == "wait":
                    self.log.emit("briefing_error", error=f"{e}; its reply was lost and turn-ready reads {seen}: it may "
                                                          "be running, so it is waited for, not sent again"[:300])
                    self._wait_turns(turn, n, started, float("inf"))
                    return
                self.log.emit("briefing_error", error=f"{e}; its reply was lost and turn-ready reads the game idle at "
                                                      f"T{turn}, so it is sent again ({attempt + 1} of "
                                                      f"{self.start_retries})"[:300])

    def _after_lost_start(self, turn: int) -> tuple[str | int, str]:
        """After a start whose reply was lost reads as not started: 'resend' only when turn-ready reads
        the game idle at `turn` (autoplay off, our turn, not sent, engine idle; a popup does not count)
        on every answered poll for `start_grace_s` (autoplay reads inactive before its last turn ends);
        the later turn when it reads the turn handed back; else 'wait' (a start may be running: it is
        never sent again). Returns it with what turn-ready last said."""
        idle_since, seen = None, "nothing (no answer)"
        deadline = time.time() + 3 * self.start_grace_s
        while True:
            try:
                r = self.game.turn_ready()
            except Exception as e:  # noqa: BLE001 - no answer: the AI may be playing
                r, seen = None, f"no answer ({type(e).__name__})"
            if r is not None:
                why, now_turn = [str(w) for w in r.get("why") or []], r.get("turn")
                seen = ", ".join(why) or "ready"
                if playing_reasons(why) or not isinstance(now_turn, int):
                    return "wait", seen
                busy = [w for w in why if not w.startswith("on screen: ")]
                if busy:
                    idle_since = None                   # the engine is busy: not idle yet
                elif now_turn != turn:
                    return now_turn, seen
                elif idle_since is None:
                    idle_since = time.time()
                elif time.time() - idle_since >= self.start_grace_s:
                    return "resend", seen
            else:
                idle_since = None
            if time.time() > deadline:
                return "wait", seen
            time.sleep(max(self.status_poll_s, self.start_grace_s / 5))

    def _wait_turns(self, turn: int, n: int, started: float, grace: float) -> None:
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
                if not seen_active and elapsed > grace:
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

    # ---- the last stand (docs/design/2026-09-27-civ6-levers-design.md, rulings 22-27) ------------
    #
    # At a hand-back turn, a city about to fall gets scripted actions before the AI plays the turn:
    # one action per call (InGame), each read back in GameCore before the next, then pins, then the
    # hand-back by one-turn autoplay. Off by default (PILOT_LAST_STAND). Nothing is ever resent, and
    # every stop still hands the turn back.

    def _now(self) -> float:
        return time.monotonic()

    def _stand_city(self, b: dict) -> dict | None:
        """The city a last stand runs for at this hand-back, or None: the stand is on and not turned
        off, a city is about to fall, and it has had fewer than `last_stand_max` stands in a row (the
        most worn-down city first). A city that stopped falling starts its count again."""
        falling = [c for c in b.get("cities") or [] if about_to_fall(c)]
        names = {c.get("name") for c in falling}
        for name in [n for n in self._stand_streak if n not in names]:
            self._stand_streak.pop(name)
            self._stand_capped.discard(name)
        if not self.s.last_stand or self._stand_off or not falling:
            return None
        ranked = sorted(falling, key=lambda c: (c["defense"]["garrison_hp"] / c["defense"]["garrison_max"],
                                                -(c.get("incoming") or 0)))
        for c in ranked:
            n = self._stand_streak.get(c["name"], 0)
            if n < self.s.last_stand_max:
                return c
            if c["name"] not in self._stand_capped:
                self._stand_capped.add(c["name"])
                self.journal.note(f"Last stand: {c['name']} has had {n} stands in a row (the limit); the AI defends "
                                  "it alone until it stops falling.", b.get("date", ""))
                self.log.emit("journal", text=f"last stand limit reached for {c['name']} ({n} in a row)")
        return None

    def _not_ready(self) -> str:
        """Why the game is not ready for a scripted action ('' when it is): autoplay on, not our turn,
        the turn sent, the engine busy, a popup or diplomacy screen (read-only, InGame)."""
        try:
            r = self.game.turn_ready()
        except Exception as e:  # noqa: BLE001 - no answer: not ready
            return f"turn-ready failed: {type(e).__name__}: {e}"[:200]
        return "" if r.get("ready") else ", ".join(r.get("why") or ["not ready"])

    def _ls_read(self, city_id: int) -> dict | None:
        try:
            return self.game.ls_state(city_id)
        except Exception as e:  # noqa: BLE001 - a failed read-back stops the stand
            self.log.emit("briefing_error", error=f"ls-state: {e}"[:200])
            return None

    def _last_stand(self, b: dict, city: dict) -> None:
        """Scripted actions for a falling city (rulings 23-26), then the hand-back (ruling 25). Emits
        `last_stand` with the report and one `order_outcome` per action; never raises before the
        hand-back. Only a stand that reached the game (a step answered with an action or `done`, or
        lost) counts toward `last_stand_max`: one stopped before its first step ran nothing."""
        name = city["name"]
        self._status("last stand")
        report = {"city": name, "city_id": city.get("id"), "turn": b["turn"], "date": b["date"],
                  "in_a_row": self._stand_streak.get(name, 0), "ran": False, "actions": [], "pins": [], "stopped": ""}
        try:
            report["stopped"] = self._stand_actions(b, city, report)
        except Exception as e:  # noqa: BLE001 - a stand never keeps the turn from being handed back
            report["stopped"] = f"error: {type(e).__name__}: {e}"[:300]
        if report["ran"]:
            report["in_a_row"] = self._stand_streak[name] = self._stand_streak.get(name, 0) + 1
        self._stand_breaker(report, b)
        self.log.emit("last_stand", **report)
        acts = "; ".join(f"{a['action']} {a['result'].replace('_', ' ')} ({a['detail']})" for a in report["actions"])
        counted = (f"stand {report['in_a_row']} in a row" if report["ran"]
                   else "not counted toward the limit: nothing ran")
        self.journal.note(f"Last stand for {name} ({counted}): {acts or 'no action'}"
                          + (f"; {len(report['pins'])} unit(s) pinned" if report["pins"] else "")
                          + f"; stopped: {report['stopped']}.", b["date"])
        self._status("playing")
        self._hand_back(b["turn"])

    def _stand_actions(self, b: dict, city: dict, report: dict) -> str:
        """The action loop; returns why it stopped. Every action is read back in GameCore: `did_not_take`
        or `unknown` stops the stand at once, as do a lost reply (never resent), a refused step, the
        game not being ready and the turn changing. Only a stand that ended by itself (`done`) or at
        `stand_max_actions` pins its units; `stand_budget_s` bounds actions and pins together."""
        started, cid = self._now(), city["id"]
        why = self._not_ready()
        if why:
            return f"not ready: {why}; nothing sent"
        state = self._ls_read(cid)
        if state is None:
            return "no GameCore read before the first action: nothing sent"
        me, skip, acted = state.get("me", 0), [], []
        stop = f"{self.stand_max_actions} actions (the limit)"
        for n in range(self.stand_max_actions):
            if self._now() - started > self.stand_budget_s:
                return f"the {self.stand_budget_s:.0f} s budget ran out"
            damage = {f"{u['owner']}:{u['id']}": min(1000, max(0, int(u.get("damage") or 0)))
                      for u in state.get("units") or [] if u.get("owner") != me}
            try:
                reply = self.game.last_stand_step(cid, damage, list(skip))
            except Exception as e:  # noqa: BLE001 - no reply: it may have run; read it back, never resend
                reply = {"ok": False, "transport": True, "error": f"{type(e).__name__}: {e}"}
            lost = bool(reply.get("transport"))
            if not lost and reply.get("ok") is False:
                return f"step refused: {reply.get('error')}"[:300]
            report["ran"] = True                        # the game ran the step (or may have: a lost reply)
            if not lost and reply.get("done"):
                stop = f"done: {reply.get('reason')}"
                break
            time.sleep(self.stand_pause_s)
            after = self._ls_read(cid)
            verdict, detail = stand_verdict(None if lost else reply, state, after)
            action = "lost reply" if lost else str(reply.get("action"))
            self._stand_row(b, city, action, reply, verdict, detail, report, first=n == 0)
            if lost:
                return f"the reply was lost ({reply.get('error')}): not sent again"[:300]
            if verdict != "took":
                return f"{action} {verdict.replace('_', ' ')}: {detail}"
            if re.fullmatch(r"(city|unit):\d{1,12}", str(reply.get("actor"))):
                skip.append(str(reply.get("actor")))
            if _actor_id(reply) is not None:
                acted.append(_actor_id(reply))
            state = after
            if after.get("turn") != b["turn"]:
                return "the turn changed"
            why = self._not_ready()
            if why:
                return f"not ready: {why}"
        return stop + self._stand_pins(b, city, state, me, acted, report, started)

    def _stand_pins(self, b: dict, city: dict, state: dict, me: int, acted: list[int], report: dict,
                    started: float) -> str:
        """Pin every unit the stand used that still has moves (GameCore FinishMoves), so the
        hand-back's AI cannot walk it back; the reply's moves are the read-back."""
        for uid in dict.fromkeys(acted):
            u = _ls_unit(state, me, uid)
            if not u or not u.get("moves"):
                continue
            if self._now() - started > self.stand_budget_s:
                return "; pins stopped by the budget"
            try:
                r = self.game.finish_moves(uid)
                verdict, detail = ("took", "no moves left") if r.get("moves") == 0 else \
                    ("did_not_take", f"{r.get('moves')} moves left")
            except GameRefused as e:
                verdict, detail = "did_not_take", str(e)[:200]
            except Exception as e:  # noqa: BLE001 - lost: never resent
                verdict, detail = "unknown", f"{type(e).__name__}: {e}"[:200]
            self._stand_row(b, city, "pin", {"actor": f"unit:{uid}"}, verdict, detail, report)
            if verdict != "took":
                return f"; pin {verdict.replace('_', ' ')}: {detail}"
            report["pins"].append({"id": uid, "x": u.get("x"), "y": u.get("y")})
            self._pinned.append({"id": uid, "x": u.get("x"), "y": u.get("y"), "turn": b["turn"], "city": city["name"]})
        return ""

    def _stand_row(self, b: dict, city: dict, action: str, reply: dict, verdict: str, detail: str, report: dict,
                   first: bool = False) -> None:
        """An action (or pin) in the report and the order record (key `stand <action>`), with what was
        predicted and what the read-back showed."""
        report["actions"].append({"action": action, "actor": reply.get("actor"), "unit": reply.get("unit"),
                                  "target": reply.get("target"), "to": reply.get("to"),
                                  "predicted_damage": reply.get("predicted_damage"),
                                  "predicted_kill": reply.get("predicted_kill"), "result": verdict, "detail": detail,
                                  "first": first})
        self._emit_row({"order_kind": "stand", "key": STAND_KEYS.get(action, f"stand {action}"), "item_kind": "stand",
                        "id": reply.get("unit") or reply.get("actor"), "city": city["name"], "currency": None,
                        "situation": None, "ordered": b["date"], "top3_hit": None, "result": verdict, "by": None,
                        "turns": 0, "date": b["date"], "turn": b["turn"], "detail": detail[:300],
                        "predicted": {"damage": reply.get("predicted_damage"), "kill": reply.get("predicted_kill")},
                        "target": reply.get("target")})

    def _stand_breaker(self, report: dict, b: dict) -> None:
        """Ruling 26: when the first action of two stands in this run does not take, the channel is
        taken as dead and the stand turns itself off for the run (autoplay carries on)."""
        first = next((a for a in report["actions"] if a["first"]), None)
        if first is None or first["result"] == "took":
            return
        self._stand_first_fails += 1
        if self._stand_first_fails >= 2 and not self._stand_off:
            self._stand_off = (f"the first action of {self._stand_first_fails} stands did not take "
                               f"(last: {first['action']} {first['result'].replace('_', ' ')}: {first['detail']})")[:300]
            self.log.emit("last_stand_off", reason=self._stand_off)
            self.journal.note(f"Last stand turned off for this run: {self._stand_off}. Autoplay defends alone; a restart "
                              "turns it on again.", b["date"])

    def _hand_back(self, turn: int) -> None:
        """Ruling 25: once turn-ready shows the engine idle (a few polls at most; a popup does not
        stop autoplay), one-turn autoplay: the AI plays the rest of turn T, ends it and hands back at
        T+1."""
        for i in range(self.stand_idle_polls):
            if not self._not_ready():
                break
            if i + 1 < self.stand_idle_polls:
                time.sleep(self.stand_idle_poll_s)
        self._play_turns(turn, 1)

    def _check_pins(self, b: dict) -> None:
        """At the next snapshot: did the hand-back's AI move a pinned unit? The snapshot lists our units
        near threatened cities (`defenders`); a unit not listed cannot be told."""
        if not self._pinned:
            return
        seen = {d.get("id"): d for c in b.get("cities") or [] for d in c.get("defenders") or []}
        results = []
        for p in self._pinned:
            d = seen.get(p["id"])
            state = "unknown" if d is None else "held" if (d.get("x"), d.get("y")) == (p["x"], p["y"]) else "moved"
            results.append({**p, "result": state, **({"now": {"x": d.get("x"), "y": d.get("y")}} if d else {})})
        self._pinned = []
        self.log.emit("last_stand_check", pins=results, date=b.get("date"))
        moved = [r for r in results if r["result"] == "moved"]
        if moved:
            self.journal.note("Last stand: the hand-back moved pinned unit(s) "
                              + ", ".join(f"{r['id']} ({r['x']},{r['y']} → {r['now']['x']},{r['now']['y']})" for r in moved)
                              + ": pins do not hold (ruling 25's manual end turn is the next step).", b.get("date", ""))

    # ---- a decision ----------------------------------------------------------------------------------

    def _limits_text(self, b: dict) -> str:
        if not self.pillars:
            return ""
        acts = self.pillars.actions
        per = ", ".join(f"{o} {acts[a].max_orders}" for o, a in ORDER_ACTION.items() if a in acts)
        text = f"Orders per decision at most: {per}."
        buy = acts.get("purchase")
        if buy:
            faith, why = faith_reserve_now(b, buy)
            text += (f" Purchases keep {gold_reserve_now(b, buy)} gold"
                     + (f" ({buy.gold_reserve} + {buy.gold_reserve_per_deficit:g} per gold of deficit per turn)"
                        if buy.gold_reserve_per_deficit else "")
                     + f" and {faith} faith" + (f" ({why.removeprefix('keeps ')})" if why and faith else "")
                     + f" in reserve and cost at most {buy.treasury_share:.0%} of the balance"
                     + (f" ({buy.threatened_share:.0%} for a city IN DANGER, down to the reserve)" if buy.threatened_share else "")
                     + ".")
            rules = []
            if buy.skip_turns_left:
                rules.append(f"never what the city finishes within {buy.skip_turns_left} turns anyway (refused)")
            if buy.defence_first:
                rules.append("a city in danger with no unit on its tile gets a defender before any other purchase (unless it "
                             "finishes one of its own within 2 turns), and a production order for a defender there is bought "
                             "instead when a listed price fits")
            if buy.defender_classes:
                rules.append("a defender bought with gold is bought with faith when the game allows it and the faith fits")
            rules.append("one land unit per city tile (a second one is refused)")
            if buy.defence_cooldown_turns:
                rules.append(f"one defender purchase per city per {buy.defence_cooldown_turns} turns")
            rules.append("a known price over the cap is refused before it is sent; walls cannot be bought")
            text += " Purchase rules: " + "; ".join(rules) + "."
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
        top3 = t.row.get("top3")
        if result == "overridden" and by and top3 is not None:
            t.row["top3_hit"] = self.index.cid(by) in top3      # ruling 29: did the AI follow its own plan?
        row = {**t.row, "result": result, "by": self.index.cid(by) if by else None,
               "turns": (b.get("turn") or 0) - (t.base.get("turn") or 0), "date": b.get("date") or f"T{b.get('turn')}",
               "turn": b.get("turn"), "detail": detail}
        self._resolved.append((row, _describe(t.c.order)))
        self._emit_row(row)

    def _emit_row(self, row: dict) -> None:
        self._order_rows.append(row)
        self.log.emit("order_outcome", **row)

    def _defender_buys(self) -> dict[str, int]:
        """The turn of each city's last defender purchase (lowercased name), from the record, so the
        cooldown (ruling 19) holds across decisions and restarts."""
        buy, out = self._buy_limits(), {}
        for r in self._order_rows:
            if r.get("order_kind") == "purchase" and r.get("result") == "completed" and isinstance(r.get("turn"), int) \
                    and is_defender(r.get("id"), self.index, buy):
                city = str(r.get("city") or "").lower()
                out[city] = max(out.get(city, r["turn"]), r["turn"])
        return out

    def _order_row(self, c: Checked, b: dict, situation: str | None) -> dict:
        """An order's row before its outcome: what, where, when ordered (`order_kind`, since an
        event's own `kind` is order_outcome). What was sent counts: a production order bought
        instead is a purchase, a purchase switched to faith a faith purchase."""
        o = c.wire or c.order
        oid = ", ".join(o.get("ids") or []) if o.get("kind") == "policies" else o.get("id")
        city = (c.wire or {}).get("city") or o.get("city") or ""
        recs = (_city_of(b, city) or {}).get("recommend") if o.get("kind") == "production" else None
        return {"order_kind": o.get("kind"), "key": record_key(o, situation),
                "item_kind": "policy" if o.get("kind") == "policies" else self.index.kind_of.get(o.get("id") or ""),
                "id": oid, "city": city,
                "currency": o.get("currency") if o.get("kind") == "purchase" else None, "situation": situation,
                "ordered": b.get("date") or f"T{b.get('turn')}", "top3_hit": None,
                # the city's own top 3 builds when ordered (ruling 29), for top3_hit
                "top3": [self.index.cid(r.get("type")) for r in recs] if isinstance(recs, list) and recs else None}

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
                                 spec.window_turns, top3_hits(self._order_rows))

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
        self._read_ai_strategies(b)
        held = self._held_report(b)
        extra = self.human.take_all()
        press = self._pressures() if self.strategy and self.pillars else None
        self.last_briefing = self._briefing(b)
        prompt = [f"Decision point: {reason}.",
                  (frame_text(self.strategy, self.pillars, self._milestones_text(), press) if self.pillars else "")
                  or "No strategy yet.",
                  "Briefing (live snapshot):", self.last_briefing, self._limits_text(b)]
        if self._report or held:
            prompt.append("What your last orders did:\n" + "\n".join(f"- {x}" for x in self._report + held))
        record = self._record_text()
        if record:
            if (self._record().get("production replace") or {}).get("weak"):
                record += ("\nThe AI replaced most production orders that replaced its own choice: buy what must exist "
                           "now; queue only into empty queues.")
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

        outcomes, applied = self._apply(d, b, filled, prices_seen(result.all_messages()))
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

    def _apply(self, d: Civ6Decision, b: dict, filled: set[str] = frozenset(),
               prices: dict | None = None) -> tuple[list[dict], int]:
        """Check, carry out and read back the decision's orders. Returns one outcome per order and how
        many took. Never raises: a failure is an outcome, reported at the next decision. Only a game
        refusal or a read-back that contradicts the order counts as "did not stick" (refused if
        repeated unchanged); an order whose effect cannot be told (no reply, no read-back) is
        "unknown". Orders that took are followed until they resolve (the order record); refused,
        lost and bought ones get their row at once. `filled`: order keys the governor added;
        `prices`: the `price` tool's answers in this decision."""
        checked = check_orders(d.orders, b, self.pillars, self.index, self._failed_last, prices=prices,
                               defender_buys=self._defender_buys())
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
            outcomes.append({"order": _describe(c.order) + (" (filled by the governor)" if by_governor else "")
                             + (f" ({c.note})" if c.note else ""),
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
        get their row now. A production order for what the city already builds changes nothing and
        stays out of the record."""
        o = c.wire or c.order
        situation = order_situation(b, c.expect["producing"], c.expect["city"]) if "producing" in c.expect else None
        if situation == "current":
            return          # the city already built it: nothing changed, so nothing to follow or supersede
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
            ref = uuid.uuid4().hex[:12]
            row["ref"] = ref
            self._tracking.append(Tracked(c, row, base, window))
            # followed across restarts: reloaded until an order_outcome with this ref exists
            self.log.emit("order_followed", ref=ref, row=row, order=c.order, wire=c.wire, expect=c.expect,
                          base=base, window=window)
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


def _city_of(snapshot: dict, name: str) -> dict | None:
    want = str(name).strip().lower()
    return next((c for c in snapshot.get("cities") or [] if str(c.get("name", "")).lower() == want), None)


def _describe(o: dict) -> str:
    if o.get("kind") == "policies":
        return f"policies {', '.join(o.get('ids') or [])}"
    where = f" in {o['city']}" if o.get("city") else ""
    cur = f" with {o['currency']}" if o.get("kind") == "purchase" else ""
    return f"{o.get('kind')} {o.get('id')}{where}{cur}"

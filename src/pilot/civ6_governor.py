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
from dataclasses import replace

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from .civ6 import (
    ORDER_ACTION,
    UNKNOWN,
    Checked,
    Civ6Decision,
    CorpusIndex,
    GameRefused,
    briefing_text,
    check_orders,
    metrics,
    order_key,
    read_back,
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

EVENT_TRIGGERS_CIV6 = (*EVENT_TRIGGERS, "city lost", "city threatened", "new era", "race lost")


def price(ctx: RunContext[GovDeps], city: str, item: str, currency: str = "gold") -> str:
    """The live price of a unit or building (corpus id, e.g. unit:warrior) in one of our cities, in
    gold or faith, and whether the game allows buying it now."""
    return json.dumps(ctx.deps.game.order({"kind": "price", "city": city, "id": item,
                                           "currency": "faith" if currency == "faith" else "gold"}))


class Civ6Stuck(RuntimeError):
    """The game did not play or hand back a turn in time, or stopped answering between turns."""


class Civ6Governor(Governor):
    event_triggers = EVENT_TRIGGERS_CIV6
    status_poll_s = 1.0              # autoplay-status polls while the AI plays a turn (a tiny call)
    turn_deadline_s = 600.0          # one AI turn; late-game turns take minutes and polls go unanswered
    start_grace_s = 20.0             # autoplay must show as running (or the turn advance) by then
    snapshot_tries = 3               # snapshots between turns before the run waits for the human

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
        self._held: list[tuple[Checked, dict]] = []   # orders that took, checked again after autoplay
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
                self._play_turns(last["turn"], max(1, min(self.s.autoplay_chunk, target - last["turn"])))
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
        a failure: the polls tell whether it started; a refusal is."""
        started = time.time()
        try:
            self.game.autoplay(n)
        except GameRefused as e:
            raise Civ6Stuck(f"autoplay did not start at T{turn}: {e}"[:400]) from e
        except Exception as e:  # noqa: BLE001 - no reply: it may have started; the polls tell
            self.log.emit("briefing_error", error=f"autoplay at T{turn}: {e}"[:200])
        seen_active, misses, deadline = False, 0, self.turn_deadline_s * n
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
                    raise Civ6Stuck(f"autoplay did not start at T{turn} (still inactive after {elapsed:.0f} s)")
                if seen_active and not st.get("active") and st.get("turn", turn) > turn:
                    self.log.emit("turn", turn=st["turn"], turns=st["turn"] - turn, seconds=round(elapsed, 1),
                                  unanswered_polls=misses, note="autoplay ended early")
                    return
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

    def _held_report(self, b: dict) -> list[str]:
        """Orders that took at the last decision, checked on today's snapshot after autoplay."""
        out = []
        for c, reply in self._held:
            status = read_back(c, reply, b)
            what = _describe(c.order)
            if status == "stuck":
                out.append(f"{what}: still in force at T{b['turn']}")
            elif "research" in c.expect or "civic" in c.expect or "producing" in c.expect:
                out.append(f"{what}: no longer current at T{b['turn']} ({status}; completed, or changed by the AI)")
            elif "policies" in c.expect:
                out.append(f"{what}: changed during autoplay ({status})")
        self._held = []
        return out

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

        outcomes, applied = self._apply(d, b)
        summary = "; ".join(f"{o['order']}: {o['outcome']}" for o in outcomes) or "no orders"
        decision = "orders" if d.orders else "keep"
        st.last_decision = f"{b['date']}: {summary} — {d.reason}"
        self.log.emit("episode", situation=reason, decision=f"{summary}: {d.reason}", date=b["date"],
                      resolved=all(o["outcome"] == "stuck" for o in outcomes), actions=applied,
                      seconds=round(time.time() - started, 1),
                      tokens_in=usage.input_tokens, tokens_out=usage.output_tokens)
        self.log.save_trace(n, {**base, "decision": decision, "reason": d.reason, "outcome": summary[:2000],
                                "orders": outcomes, "serves": d.serves, "seconds": round(time.time() - started, 1),
                                "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens,
                                "steps": serialize(result.all_messages())})
        self.store.add_episode(reason, f"{summary}: {d.reason}", "applied" if applied else "kept", b["date"])
        self.journal.note(f"{summary} — {d.reason}", b["date"])
        if d.note:
            self.journal.note(d.note, b["date"])
        if not (reason == "start of run" and reviewed_at_start):
            self._since_retro += 1
            if self.s.retro_every and self._since_retro >= self.s.retro_every and self.pillars is not None:
                self._review_strategy(self._after_orders or b, f"scheduled after {self.s.retro_every} decisions")

    def _apply(self, d: Civ6Decision, b: dict) -> tuple[list[dict], int]:
        """Check, carry out and read back the decision's orders. Returns one outcome per order and how
        many took. Never raises: a failure is an outcome, reported at the next decision. Only a game
        refusal or a read-back that contradicts the order counts as "did not stick" (refused if
        repeated unchanged); an order whose effect cannot be told (no reply, no read-back) is
        "unknown"."""
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
        self._held = []
        for c, reply in sent:
            if after is None:
                results.append((c, f"{UNKNOWN}: not read back (no snapshot)", False))
                continue
            status = read_back(c, reply, after)
            if reply.get("transport") and status != "stuck":
                status = f"{UNKNOWN}: no reply ({reply.get('error')}); {status}"
            results.append((c, status, status != "stuck" and not status.startswith(UNKNOWN)))
            if status == "stuck":
                self._held.append((c, reply))
        position = {id(c): i for i, c in enumerate(checked)}
        results.sort(key=lambda r: position[id(r[0])])          # outcomes in the model's order
        self._failed_last = {order_key(c.order) for c, _, failed in results if failed}
        outcomes = [{"order": _describe(c.order), "outcome": status} for c, status, _ in results]
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
        return outcomes, sum(1 for o in outcomes if o["outcome"] == "stuck")


def _describe(o: dict) -> str:
    if o.get("kind") == "policies":
        return f"policies {', '.join(o.get('ids') or [])}"
    where = f" in {o['city']}" if o.get("city") else ""
    cur = f" with {o['currency']}" if o.get("kind") == "purchase" else ""
    return f"{o.get('kind')} {o.get('id')}{where}{cur}"

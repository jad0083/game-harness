"""Civilization VI governor (docs/design/2026-09-26-civ6-governor-design.md, ruling 4): the game's AI
plays our civilization through AutoplayManager; the model gives macro orders between stretches.

    snapshot → decide (at decision points) → apply orders → read back → autoplay N turns
             → poll a snapshot each turn: stop early on an urgent change → snapshot → …

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
    Checked,
    Civ6Decision,
    CorpusIndex,
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


class Civ6Governor(Governor):
    min_poll_s = 3.0                 # at most one snapshot every 3 s while the AI plays (shared agent)
    start_grace_polls = 3            # polls without autoplay running before the stretch counts as over

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
                self.game.autoplay_stop()          # never decide while the AI is playing
                b = self.game.snapshot()
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
        except Exception as e:  # noqa: BLE001 - the next poll or the exit stops it again
            self.log.emit("briefing_error", error=f"autoplay stop: {e}"[:200])

    def _run_until_next_decision(self, last: dict) -> tuple[dict | None, str]:
        last = self._after_orders or last
        self._after_orders = None
        start, turns = last["turn"], self.s.decide_every_turns
        self._status("playing")
        self.game.autoplay(turns)
        self.log.emit("autoplay", turn=start, turns=turns)
        idle = 0
        while True:
            if self.control.stopping:
                self._stop_autoplay()
                return None, "stop"
            if self.control.paused:
                return last, ""                     # the main loop stops autoplay (set_paused)
            if not self.requests.empty():
                self._stop_autoplay()
                return self.game.snapshot(), "request"
            time.sleep(max(self.s.poll_s, self.min_poll_s))
            try:
                b = self.game.snapshot()
            except Exception as e:  # noqa: BLE001 - a busy turn change; try again next poll
                self.log.emit("briefing_error", error=str(e)[:200])
                continue
            if getattr(self, "_campaign_key", None) and (b.get("leader"), b.get("map_seed")) != self._campaign_key:
                self._stop_autoplay()
                self._needs_attention(f"the game changed: {b.get('leader')} on map {b.get('map_seed')}, this run governs "
                                      f"{self._campaign_key[0]} on map {self._campaign_key[1]}. Load that game again and "
                                      "press Resume, or start a new run.")
                return last, ""
            if b["turn"] != last["turn"]:
                self.log.emit("metrics", **metrics(b))
                self.log.state.game_date = b["date"]
                self.log.state.turns_advanced += b["turn"] - last["turn"]
            urgent = urgent_changes(last, b, self._gold_reserve(), self._wonders)
            if b["turn"] != last["turn"]:
                urgent += self._newly_missed_milestones(last["date"], b["date"])
            active = (b.get("autoplay") or {}).get("active")
            if urgent:
                self._stop_autoplay()
                return self._fresh(b), "urgent: " + "; ".join(urgent)
            if not active:
                idle += 1
                if b["turn"] >= start + turns or (b["turn"] > start and idle >= 2) or idle >= self.start_grace_polls:
                    how = f"scheduled ({turns} turns)" if b["turn"] >= start + turns else \
                        f"autoplay ended after {b['turn'] - start} of {turns} turns"
                    return b, how
            else:
                idle = 0
            last = b

    def _fresh(self, b: dict) -> dict:
        """A snapshot taken after autoplay stopped (the one that triggered may be mid-turn)."""
        try:
            return self.game.snapshot()
        except Exception:  # noqa: BLE001 - decide on the one we have
            return b

    def _maybe_event_review(self, b: dict, trigger: str, retry: bool = False) -> bool:
        if not any(t in trigger for t in EVENT_TRIGGERS_CIV6) and not retry and self.review_requested is None:
            return False
        return super()._maybe_event_review(b, trigger, retry)

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
        many took. Never raises: a failure is an outcome, reported at the next decision; an order that
        did not take is refused if repeated at the next decision (not retried blindly)."""
        checked = check_orders(d.orders, b, self.pillars, self.index, self._failed_last)
        results: list[tuple[Checked, str]] = []
        sent: list[tuple[Checked, dict]] = []
        for c in checked:
            if c.error:
                results.append((c, f"refused: {c.error}"))
                continue
            try:
                reply = self.game.order(c.wire)
            except Exception as e:  # noqa: BLE001
                reply = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            if reply.get("ok"):
                sent.append((c, reply))
            else:
                results.append((c, f"refused by the game: {reply.get('error')}"))
        after = None
        if sent:
            try:
                after = self.game.snapshot()
            except Exception as e:  # noqa: BLE001
                self.log.emit("briefing_error", error=f"read-back: {e}"[:200])
        self._held = []
        for c, reply in sent:
            status = read_back(c, reply, after) if after is not None else "not read back (no snapshot)"
            results.append((c, status))
            if status == "stuck":
                self._held.append((c, reply))
        position = {id(c): i for i, c in enumerate(checked)}
        results.sort(key=lambda r: position[id(r[0])])          # outcomes in the model's order
        self._failed_last = {order_key(c.order) for c, status in results if status != "stuck"}
        outcomes = [{"order": _describe(c.order), "outcome": status} for c, status in results]
        self._report = [f"{o['order']}: carried out and read back" if o["outcome"] == "stuck"
                        else f"{o['order']}: {o['outcome']} (did not stick; not retried blindly)" for o in outcomes]
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

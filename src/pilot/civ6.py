"""Civilization VI for the governor (docs/design/2026-09-26-civ6-governor-design.md): game access
through the controller's `civ6` commands, a scripted fake for tests, and the pure pieces the
governor needs (corpus index, briefing text, metrics rows, order checks, read-back, urgent changes).

The game's AI plays our civ through AutoplayManager; the governor reads one JSON snapshot per
decision, gives structured orders that name corpus ids, reads them back, and lets the AI play the
next stretch of turns."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Literal, Protocol

from pydantic import BaseModel, Field

# ---- game access ---------------------------------------------------------------------------------


class Civ6Game(Protocol):
    def snapshot(self) -> dict: ...
    def order(self, order: dict) -> dict: ...
    def autoplay(self, turns: int) -> dict: ...
    def autoplay_stop(self) -> dict: ...
    def autoplay_status(self) -> dict: ...
    def corpus(self, tool: str, **args) -> str: ...
    def close(self) -> None: ...


class GameRefused(RuntimeError):
    """The game (or the controller's check) answered and refused: `{"ok": false}`."""


class ControllerCiv6:
    """The real game: `game-controller --corpus corpora/civ6 civ6 …` per call (one short HTTP
    exchange with the agent each). A snapshot gains `date` = "T<turn>" for the governor's clock.
    A reply `{"ok": false}` or a failed call raises, except for `order`, whose reply says why."""

    def __init__(self, controller: Path, corpus: Path, agent_url: str, cwd: Path, token: str | None = None,
                 timeout_s: float = 90.0):
        self.base = [str(controller), "--corpus", str(corpus)]
        self.env = {"GAME_AGENT_URL": agent_url, "PATH": "/usr/bin:/bin"}
        tok = token or os.environ.get("GAME_AGENT_TOKEN")
        if tok:
            self.env["GAME_AGENT_TOKEN"] = tok
        self.cwd = cwd
        self.timeout_s = timeout_s

    def _run(self, *args: str) -> tuple[int, str, str]:
        r = subprocess.run([*self.base, *args], cwd=self.cwd, env=self.env, capture_output=True, text=True,
                           timeout=self.timeout_s, check=False)
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    def _json(self, *args: str) -> dict:
        code, out, err = self._run(*args)
        what = f"game-controller {' '.join(args[:2])}"
        try:
            reply = json.loads(out.splitlines()[-1])
        except (ValueError, IndexError):
            raise RuntimeError(f"{what} failed (exit {code}): {(err or out)[:400]}") from None
        if code != 0 or reply.get("ok") is False:
            raise GameRefused(f"{what} refused: {reply.get('error') or (err or out)[:400]}")
        return reply

    def snapshot(self) -> dict:
        s = self._json("civ6", "snapshot")
        s["date"] = f"T{s['turn']}"
        return s

    briefing = snapshot

    def order(self, order: dict) -> dict:
        """The game's reply; exit 2 with JSON = refused (by the controller's check or the game). No
        JSON at all (a tuner timeout, the agent unreachable) is marked `transport`: the order may
        or may not have run."""
        code, out, err = self._run("civ6", "order", json.dumps(order))
        try:
            return json.loads(out.splitlines()[-1])
        except (ValueError, IndexError):
            return {"ok": False, "transport": True, "error": (err or out or f"exit {code}")[:400]}

    def autoplay(self, turns: int) -> dict:
        return self._json("civ6", "autoplay", str(turns))

    def autoplay_stop(self) -> dict:
        return self._json("civ6", "autoplay-stop")

    def autoplay_status(self) -> dict:
        return self._json("civ6", "autoplay-status")

    def corpus(self, tool: str, **args) -> str:
        if tool == "corpus_search":
            _, out, err = self._run("corpus", "search", str(args.get("query", "")), "--limit", str(args.get("limit", 5)))
        elif tool == "corpus_get":
            _, out, err = self._run("corpus", "get", str(args.get("id", "")))
        else:
            return f"unknown corpus tool {tool}"
        return out or err

    # the Governor base class pauses the game on errors and on exit: here that means stop autoplay
    def set_paused(self, paused: bool) -> str:
        if paused:
            self.autoplay_stop()
        return "ok"

    def screenshot(self):
        return None

    def close(self) -> None:
        pass


class GameBusy(TimeoutError):
    """FakeCiv6's stand-in for a tuner call that timed out while the AI plays its turn."""


class FakeCiv6:
    """Civ VI for tests: one game state (a snapshot dict). Autoplay advances one turn per call made
    while it is active (snapshot, autoplay_status or order): the call that finds it active plays a
    turn. `events[turn](state)` changes the state when that turn is reached (a war, a lost city);
    `ai(state)` runs on every autoplayed turn (the AI changing our choices). Orders are recorded;
    `replies[kind]` answers one (default ok) and an accepted order changes the state unless `sticks`
    is False. `prices[(city, id)]` is an item's live price (default 100).
    Failure modes: `busy` (every call made while autoplay is active times out, like the real tuner
    during the AI's turn processing), `start_fails` (autoplay answers ok: false), `never_starts`
    (autoplay answers ok but no turn is played), `stop_raises`, `readback_fails` (the snapshot after
    orders fails), `transport` (orders time out after they ran), `lost_start_reply` (the first
    autoplay call times out but runs)."""

    def __init__(self, base: dict, events: dict | None = None, replies: dict | None = None,
                 prices: dict | None = None, sticks: bool = True, index: CorpusIndex | None = None, ai=None,
                 busy: bool = False, start_fails: bool = False, never_starts: bool = False,
                 stop_raises: bool = False, readback_fails: bool = False, transport: bool = False,
                 lost_start_reply: bool = False):
        self.state = copy.deepcopy(base)
        self.events = dict(events or {})
        self.replies = dict(replies or {})
        self.prices = dict(prices or {})
        self.sticks = sticks
        self.index = index
        self.ai = ai
        self.busy, self.start_fails, self.never_starts = busy, start_fails, never_starts
        self.stop_raises, self.readback_fails, self.transport = stop_raises, readback_fails, transport
        self.lost_start_reply = lost_start_reply
        self.actions: list[tuple] = []
        self.active = False
        self.remaining = 0
        self.calls_while_active = 0
        self._ordered = False

    def _tick(self, what: str) -> None:
        """A call reaching the game: while autoplay runs it plays a turn (and, when busy, times out)."""
        if not self.active:
            return
        self.calls_while_active += 1
        self.state["turn"] += 1
        self.remaining -= 1
        if self.ai:
            self.ai(self.state)
        if self.state["turn"] in self.events:
            self.events[self.state["turn"]](self.state)
        if self.remaining <= 0:
            self.active = False
        if self.busy:
            raise GameBusy(f"{what}: no reply from the game (busy with the AI's turn)")

    def snapshot(self) -> dict:
        self._tick("snapshot")
        if self.readback_fails and self._ordered:           # once: the read-back after the first orders
            self._ordered = self.readback_fails = False
            raise TimeoutError("snapshot: no reply")
        s = copy.deepcopy(self.state)
        s["date"] = f"T{s['turn']}"
        s["autoplay"] = {"active": self.active, "turns": self.remaining}
        return s

    briefing = snapshot

    def autoplay_status(self) -> dict:
        self._tick("autoplay_status")
        return {"ok": True, "active": self.active, "turns": self.remaining, "turn": self.state["turn"]}

    def order(self, order: dict) -> dict:
        self.actions.append(("order", dict(order), self.active))
        self._tick("order")
        if order["kind"] == "price":
            return {"ok": True, "cost": self.prices.get((order["city"], order["id"]), 100), "allowed": True}
        self._ordered = True
        cost = None
        if order["kind"] == "purchase":
            cost = self.prices.get((order["city"], order["id"]), 100)
            if order.get("max_cost") is not None and cost > order["max_cost"]:
                return {"ok": False, "error": f"costs {cost}, over the allowed {order['max_cost']}"}
        reply = dict(self.replies.get(order["kind"], {"ok": True, "requested": order.get("id")}))
        if reply.get("ok") and cost is not None:
            reply["cost"] = cost
        if reply.get("ok") and self.sticks:
            key_of = self.index.key_of if self.index else {}
            _apply_fake(self.state, {**order, "cost": cost, "type_key": key_of.get(order.get("id", "")),
                                     "type_keys": [key_of.get(i) for i in order.get("ids", [])]})
        if self.transport:
            return {"ok": False, "transport": True, "error": "operation timed out"}
        return reply

    def autoplay(self, turns: int) -> dict:
        self.actions.append(("autoplay", turns, self.active))
        if self.start_fails:
            raise GameRefused("game-controller civ6 autoplay refused: AutoplayManager missing")
        if self.lost_start_reply:
            self.lost_start_reply = False
            self.active, self.remaining = True, turns
            raise TimeoutError("autoplay: no reply (it ran anyway)")
        if not self.never_starts:
            self.active, self.remaining = True, turns
        return {"ok": True, "active": False, "turns": turns, "turn": self.state["turn"]}

    def autoplay_stop(self) -> dict:
        self.actions.append(("autoplay_stop",))
        if self.stop_raises:
            raise TimeoutError("autoplay-stop: no reply")
        self.active, self.remaining = False, 0
        return {"ok": True, "active": False}

    def corpus(self, tool: str, **args) -> str:
        self.actions.append(("corpus", tool, args))
        return "- `tech:writing` [tech] Writing — Ancient Era, cost 50."

    def set_paused(self, paused: bool) -> str:
        if paused and self.active:
            self.autoplay_stop()
        return "ok"

    def screenshot(self):
        return None

    def close(self) -> None:
        pass


def _apply_fake(s: dict, o: dict) -> None:
    key = o.get("type_key")
    if o["kind"] == "research":
        s["research"] = {"tech": key, "turns_left": 5}
    elif o["kind"] == "civic":
        s["civic"] = {"civic": key, "turns_left": 5}
    elif o["kind"] == "production":
        for c in s["cities"]:
            if c["name"].lower() == str(o["city"]).lower():
                c["producing"], c["turns_left"] = key, 4
    elif o["kind"] == "policies":
        keys = list(o.get("type_keys", []))
        for slot in s["policy_slots"]:
            if keys:
                slot["policy"] = keys.pop(0)
    elif o["kind"] == "purchase":
        s["gold" if o.get("currency", "gold") == "gold" else "faith"] -= o.get("cost") or 0


# ---- the corpus: game type keys <-> corpus ids ---------------------------------------------------

ORDER_FILES = ("tech", "civic", "policy", "unit", "building", "district", "project", "wonder", "government",
               "civ", "leader", "era")


@dataclass
class CorpusIndex:
    """`TECH_POTTERY` <-> `tech:pottery` (records' `aliases[0]` is the game's type key)."""
    by_key: dict[str, str] = field(default_factory=dict)       # type key -> corpus id
    key_of: dict[str, str] = field(default_factory=dict)       # corpus id -> type key
    name_of: dict[str, str] = field(default_factory=dict)      # corpus id -> English name
    kind_of: dict[str, str] = field(default_factory=dict)      # corpus id -> kind (file stem)
    purchase: dict[str, str] = field(default_factory=dict)     # corpus id -> gold | faith | none

    @classmethod
    def load(cls, corpus: Path) -> CorpusIndex:
        idx = cls()
        for kind in ORDER_FILES:
            path = corpus / "data" / f"{kind}.json"
            if not path.exists():
                continue
            for r in json.loads(path.read_text(encoding="utf-8")):
                aliases = r.get("aliases") or []
                if not aliases:
                    continue
                idx.by_key.setdefault(aliases[0], r["id"])
                idx.key_of[r["id"]] = aliases[0]
                idx.name_of[r["id"]] = r.get("name", r["id"])
                idx.kind_of[r["id"]] = kind
                p = (r.get("fields") or {}).get("purchase")
                if p:
                    idx.purchase[r["id"]] = p
        return idx

    def cid(self, key: str | None) -> str:
        """The corpus id of a type key (the key itself when unknown)."""
        return self.by_key.get(key or "", key or "none")

    def ids(self, *kinds: str) -> set[str]:
        return {i for i, k in self.kind_of.items() if k in kinds}


# ---- decisions -----------------------------------------------------------------------------------

ORDER_ACTION = {"research": "tech", "civic": "civic", "policies": "policy", "production": "production",
                "purchase": "purchase"}      # order kind -> pillars.toml action kind
ORDER_KINDS_OF = {"research": ("tech",), "civic": ("civic",), "policies": ("policy",),
                  "production": ("unit", "building", "district", "project"), "purchase": ("unit", "building")}


class Civ6Order(BaseModel):
    kind: Literal["research", "civic", "policies", "production", "purchase"]
    id: str = Field(default="", description="corpus id: tech:… for research, civic:…, unit:/building:/district:/"
                                            "project:… for production, unit:/building:… for purchase")
    ids: list[str] = Field(default_factory=list, description="policies: every policy:… id to have slotted")
    city: str = Field(default="", description="production and purchase: the city's name as in the briefing")
    currency: Literal["gold", "faith"] = "gold"


class Civ6Decision(BaseModel):
    orders: list[Civ6Order] = Field(default_factory=list, description="macro orders for now; [] keeps everything as it is")
    reason: str = Field(description="One or two sentences citing the briefing numbers that decided it")
    note: str = Field(default="", description="Optional one line for the game journal")
    serves: str = Field(default="", description="The pillar and milestone this works toward, e.g. 'expansion: cities >= 3 by T60'")


@dataclass
class Checked:
    """An order ready for the controller (`wire`), or the reason it was refused."""
    order: dict
    wire: dict | None = None
    error: str = ""
    expect: dict = field(default_factory=dict)    # what the read-back looks for


def _city(snapshot: dict, name: str) -> dict | None:
    want = name.strip().lower()
    return next((c for c in snapshot.get("cities", []) if str(c.get("name", "")).lower() == want), None)


def purchase_cap(snapshot: dict, city: dict, currency: str, limits, committed: float = 0.0) -> int:
    """The most one purchase may cost: the balance above the reserve, and at most the treasury share
    of the balance (the threatened share when the city is threatened). `committed` is what earlier
    purchases of the same decision may already spend, so together they never go below the reserve."""
    balance = float(snapshot.get("faith" if currency == "faith" else "gold") or 0) - committed
    reserve = limits.faith_reserve if currency == "faith" else limits.gold_reserve
    share = (limits.threatened_share if city.get("threatened") and limits.threatened_share else limits.treasury_share) or 1.0
    return int(max(0.0, min(balance - reserve, share * balance)))


def check_orders(orders: list[Civ6Order], snapshot: dict, spec, index: CorpusIndex,
                 failed_last: set[str] | None = None) -> list[Checked]:
    """Each order checked against the corpus, the pillars' limits and the snapshot. `failed_last`
    holds orders (as `order_key`) that did not stick at the previous decision: not retried blindly.
    Without a pillars spec (a broken file) each kind gets one order and purchases are refused."""
    out: list[Checked] = []
    counts: dict[str, int] = {}
    committed: dict[str, float] = {"gold": 0.0, "faith": 0.0}      # purchase caps already handed out
    cities_ordered: set[str] = set()
    options = snapshot.get("options") or {}
    for o in orders:
        d = o.model_dump()
        c = Checked(order=d)
        out.append(c)
        action = ORDER_ACTION[o.kind]
        limits = spec.actions.get(action) if spec else None
        if spec is not None and limits is None:
            c.error = f"{o.kind} orders are not enabled in pillars.toml"
            continue
        if limits is None and o.kind == "purchase":
            c.error = "purchases need the limits of pillars.toml, which did not load"
            continue
        quota = limits.max_orders if limits is not None else 1
        if counts.get(action, 0) >= quota:
            c.error = f"at most {quota} {o.kind} order(s) per decision"
            continue
        if failed_last and order_key(d) in failed_last:
            c.error = "did not stick at the last decision; not retried until something changes (say why to retry)"
            continue
        if not _check_one(c, o, snapshot, index, limits, options, committed, cities_ordered):
            continue
        counts[action] = counts.get(action, 0) + 1      # only valid orders use the quota
    return out


def _check_one(c: Checked, o: Civ6Order, snapshot: dict, index: CorpusIndex, limits, options: dict,
               committed: dict[str, float], cities_ordered: set[str]) -> bool:
    """Fill `c.wire`/`c.expect`, or `c.error`; True when the order is valid."""
    kinds = ORDER_KINDS_OF[o.kind]
    if o.kind == "policies":
        bad = [p for p in o.ids if index.kind_of.get(p) != "policy"]
        if not o.ids or bad:
            c.error = f"unknown policy ids {bad}" if bad else "policies needs ids"
            return False
        c.wire = {"kind": "policies", "ids": list(o.ids)}
        c.expect = {"policies": [index.key_of[p] for p in o.ids]}
        return True
    kind = index.kind_of.get(o.id)
    if kind == "wonder" and o.kind == "production":
        c.error = f"{o.id}: wonders need a tile; placement is not supported yet"
        return False
    if kind not in kinds:
        c.error = (f"unknown id {o.id!r}" if kind is None
                   else f"{o.id} is a {kind}; {o.kind} takes {' / '.join(kinds)}")
        return False
    key = index.key_of[o.id]
    if o.kind == "research":
        if options.get("techs") is not None and key not in options["techs"]:
            c.error = f"{o.id} cannot be researched now (options: {', '.join(index.cid(k) for k in options['techs'])})"
            return False
        c.wire, c.expect = {"kind": "research", "id": o.id}, {"research": key}
        return True
    if o.kind == "civic":
        if options.get("civics") is not None and key not in options["civics"] \
                and (snapshot.get("civic") or {}).get("civic") != key:
            c.error = f"{o.id} cannot be progressed now (options: {', '.join(index.cid(k) for k in options['civics'])})"
            return False
        c.wire, c.expect = {"kind": "civic", "id": o.id}, {"civic": key}
        return True
    city = _city(snapshot, o.city)
    if city is None:
        c.error = f"no city of ours named {o.city!r} (ours: {', '.join(x['name'] for x in snapshot.get('cities', []))})"
        return False
    if o.kind == "production":
        if city["name"] in cities_ordered:
            c.error = f"{city['name']} already has a production order in this decision (one per city)"
            return False
        if city.get("can_build") is not None and key not in city["can_build"]:
            c.error = f"{city['name']} cannot build {o.id} now"
            return False
        cities_ordered.add(city["name"])
        c.wire = {"kind": "production", "city": city["name"], "id": o.id}
        c.expect = {"city": city["name"], "producing": key}
        return True
    if index.purchase.get(o.id) == "none":
        c.error = f"{o.id} cannot be bought"
        return False
    cap = purchase_cap(snapshot, city, o.currency, limits, committed[o.currency])
    if cap <= 0:
        reserve = limits.faith_reserve if o.currency == "faith" else limits.gold_reserve
        c.error = (f"{o.currency} {snapshot.get(o.currency)} (less {committed[o.currency]:.0f} for earlier purchases) "
                   f"is at or below the reserve {reserve}")
        return False
    committed[o.currency] += cap
    c.wire = {"kind": "purchase", "city": city["name"], "id": o.id, "currency": o.currency, "max_cost": cap}
    c.expect = {"spend": o.currency, "before": snapshot.get(o.currency)}
    return True


def order_key(d: dict) -> str:
    return json.dumps({k: d.get(k) for k in ("kind", "id", "ids", "city", "currency")}, sort_keys=True)


UNKNOWN = "unknown"      # neither confirmed nor refuted: never counted as "did not stick"


def read_back(c: Checked, reply: dict, snapshot: dict) -> str:
    """'stuck' when the snapshot shows the order took effect, 'unknown: …' when it cannot tell,
    else why not. A purchase compares the balance's drop with `expect["total"]`, the cost of every
    purchase of the decision in that currency (set by the governor; default this one's cost)."""
    e = c.expect
    if "research" in e:
        now = (snapshot.get("research") or {}).get("tech")
        return "stuck" if now == e["research"] else f"research is {now}"
    if "civic" in e:
        now = (snapshot.get("civic") or {}).get("civic")
        return "stuck" if now == e["civic"] else f"civic is {now}"
    if "producing" in e:
        city = _city(snapshot, e["city"])
        now = city and city.get("producing")
        return "stuck" if now == e["producing"] else f"{e['city']} builds {now}"
    if "policies" in e:
        slotted = {s.get("policy") for s in snapshot.get("policy_slots", [])}
        missing = [k for k in e["policies"] if k not in slotted]
        return "stuck" if not missing else f"not slotted: {', '.join(missing)}"
    if "spend" in e:
        cost = float(reply.get("cost") or 0)
        total = float(e.get("total") or cost)
        spent = float(e["before"] or 0) - float(snapshot.get(e["spend"]) or 0)
        moved = f"{e['spend']} went from {e['before']} to {snapshot.get(e['spend'])}"
        if total and spent >= 0.9 * total:
            return "stuck"
        if spent < 0.1 * (cost or total or 1):
            return moved
        return f"{UNKNOWN}: {moved}, less than every purchase together ({total:.0f})"
    return "stuck"


# ---- measures, urgency, briefing -----------------------------------------------------------------

RANKED = {"score": "score", "military": "military", "techs": "techs", "civics": "civics", "cities": "cities"}


def metrics(s: dict) -> dict:
    """A metrics row (telemetry, milestones, charts) from a snapshot; rank:<m> via `peers`."""
    y = s.get("yields") or {}
    cities = s.get("cities") or []
    ours = {"score": s.get("score"), "military": s.get("military"), "techs": s.get("techs_known"),
            "civics": s.get("civics_known"), "cities": len(cities)}
    peers = {}
    majors = s.get("majors") or []
    for m, field_ in RANKED.items():
        theirs = [x.get(field_) for x in majors if isinstance(x.get(field_), (int, float))]
        mine = ours[m]
        if mine is None:
            continue
        peers[m] = {"rank": 1 + sum(1 for v in theirs if v > mine), "median": median(theirs) if theirs else None,
                    "ours": mine}
    return {"date": s.get("date") or f"T{s.get('turn')}", "turn": s.get("turn"),
            "science": y.get("science"), "culture": y.get("culture"), "faith_yield": y.get("faith"),
            "gold_yield": y.get("gold"), "production": y.get("production"), "food": y.get("food"),
            "gold": s.get("gold"), "faith": s.get("faith"), "cities": len(cities),
            "pop": sum(c.get("pop") or 0 for c in cities), "techs_known": s.get("techs_known"),
            "civics_known": s.get("civics_known"), "military": s.get("military"), "score": s.get("score"),
            "era_score": s.get("era_score"), "era": s.get("era"), "wars": len(s.get("wars") or []),
            "peers": peers, "peer_count": len(majors),
            "neighbours": [{"name": m.get("civ"), "military": m.get("military"), "score": m.get("score"),
                            "cities": m.get("cities"), "at_war": m.get("at_war")} for m in majors]}


def urgent_changes(before: dict, now: dict, gold_reserve: int = 0, wonders: frozenset[str] | set[str] = frozenset()) -> list[str]:
    """Reasons to stop autoplay and decide now (ruling 4). `wonders`: the wonders' type keys."""
    out = []
    old_wars = {w.get("id") for w in before.get("wars") or []}
    for w in now.get("wars") or []:
        if w.get("id") not in old_wars:
            out.append(f"new war: {w.get('civ')} is at war with us")
    old_cities = {c["name"] for c in before.get("cities") or []}
    new_cities = {c["name"] for c in now.get("cities") or []}
    for name in sorted(old_cities - new_cities):
        out.append(f"city lost: {name}")
    was = {c["name"]: c for c in before.get("cities") or []}
    for c in now.get("cities") or []:
        prev = was.get(c["name"]) or {}
        besieged = c.get("under_siege") or c.get("damaged") or (c.get("enemies_near") or 0) >= 2
        was_besieged = prev.get("under_siege") or prev.get("damaged") or (prev.get("enemies_near") or 0) >= 2
        if besieged and not was_besieged:
            out.append(f"city threatened: {c['name']} ({c.get('enemies_near', 0)} enemy units near"
                       f"{', under siege' if c.get('under_siege') else ''}{', damaged' if c.get('damaged') else ''})")
        w = prev.get("producing")
        elsewhere = now.get("wonders_elsewhere")      # built by another player: a lost race, not the AI's switch
        if w and w in wonders and w != c.get("producing") and w not in (c.get("wonders") or []) \
                and (elsewhere is None or w in elsewhere):
            out.append(f"wonder race lost: {w} in {c['name']}")
    if (now.get("era_index") or 0) > (before.get("era_index") or 0):
        out.append(f"new era: {now.get('era')}")
    gp_before, gp_now = before.get("great_people") or {}, now.get("great_people") or {}
    if (gp_now.get("recruited") or 0) > (gp_before.get("recruited") or 0):
        ours = {g.get("class"): g for g in gp_before.get("current") or []}
        for g in (gp_now.get("past") or [])[-((gp_now.get("recruited") or 0) - (gp_before.get("recruited") or 0)):]:
            mine = ours.get(g.get("class")) or {}
            if g.get("claimant") != now.get("player") and mine.get("cost") and (mine.get("ours") or 0) >= 0.5 * mine["cost"]:
                out.append(f"great person race lost: {g.get('class')}")
    if gold_reserve and (now.get("gold") or 0) < gold_reserve <= (before.get("gold") or 0):
        out.append(f"gold below the reserve: {now.get('gold')} < {gold_reserve}")
    return out


def _n(v) -> str:
    if isinstance(v, float):
        return f"{v:.0f}" if abs(v) >= 100 or v.is_integer() else f"{v:.1f}"
    return str(v)


def briefing_text(s: dict, index: CorpusIndex, gold_reserve: int = 0) -> str:
    """The snapshot as a compact briefing; every item is named by its corpus id."""
    cid = index.cid
    y = s.get("yields") or {}
    lines = [(f"Turn {s.get('turn')}, {cid(s.get('era'))} (era score {s.get('era_score')}; dark age below "
              f"{s.get('dark_age_threshold')}, golden age from {s.get('golden_age_threshold')}). "
              f"{s.get('civ_name')} ({cid(s.get('civ'))}), led by {s.get('leader_name')} ({cid(s.get('leader'))})."),
             "Per turn: " + ", ".join(f"{k} {_n(y.get(k))}" for k in ("science", "culture", "faith", "gold", "production", "food")
                                      if y.get(k) is not None)
             + f". Treasury {_n(s.get('gold'))} gold (reserve {gold_reserve}), {_n(s.get('faith'))} faith.",
             (f"Score {s.get('score')}, military strength {s.get('military')}, techs {s.get('techs_known')}, "
              f"civics {s.get('civics_known')}.")]
    r, c = s.get("research") or {}, s.get("civic") or {}
    research = f"{cid(r.get('tech'))} ({r.get('turns_left')} turns)" if r else "none"
    civic = f"{cid(c.get('civic'))} ({c.get('turns_left')} turns)" if c else "none"
    lines.append(f"Research: {research}. Civic: {civic}.")
    opt = s.get("options") or {}
    if opt:
        lines.append("Can research: " + (", ".join(cid(k) for k in opt.get("techs") or []) or "none")
                     + ". Can progress: " + (", ".join(cid(k) for k in opt.get("civics") or []) or "none")
                     + ". Unlocked policies not slotted: " + (", ".join(cid(k) for k in opt.get("policies") or []) or "none") + ".")
    slots = "; ".join(f"{x.get('type')}: {cid(x.get('policy')) if x.get('policy') else 'empty'}" for x in s.get("policy_slots") or [])
    cost = s.get("policies_unlock_cost") or 0
    lines.append(f"Government: {cid(s.get('government'))}; policy slots: {slots or 'none'}"
                 + (f" (changing them now costs {cost} gold: the order is refused until a civic completes)" if cost else
                    " (can be changed now)") + ".")
    cities = s.get("cities") or []
    lines.append(f"Cities ({len(cities)}):")
    for x in cities:
        threat = []
        if x.get("threatened"):
            threat = [f"THREATENED: {x.get('enemies_near', 0)} enemy units within 3 tiles"
                      + (", under siege" if x.get("under_siege") else "") + (", damaged" if x.get("damaged") else "")]
        dist = ", ".join(cid(d.split(" ")[0]) + (" (building)" if "(building)" in d else "") for d in x.get("districts") or [])
        lines.append(f"- {x.get('name')}{' (capital)' if x.get('capital') else ''}: pop {x.get('pop')}, "
                     f"builds {cid(x.get('producing')) if x.get('producing') else 'NOTHING'}"
                     + (f" ({x.get('turns_left')} turns)" if x.get("producing") else "")
                     + f", food {_n(x.get('food'))}, production {_n(x.get('production'))}, districts: {dist or 'none'}"
                     + (f", loyalty {x.get('loyalty')}" if (x.get("loyalty") or 100) < 100 else "")
                     + "".join(f"; {t}" for t in threat)
                     + (f". Can build: {', '.join(cid(k) for k in x.get('can_build') or [])}" if x.get("can_build") else ""))
    u = s.get("units") or {}
    lines.append(f"Units {u.get('total', 0)}: " + ", ".join(f"{cid(k)} {v}" for k, v in sorted((u.get("by_type") or {}).items())) + ".")
    majors = s.get("majors") or []
    if majors:
        lines.append("Civilizations met: " + "; ".join(
            f"{cid(m.get('civ'))} score {m.get('score')}, military {m.get('military')}, cities {m.get('cities')}, "
            f"techs {m.get('techs')}{', AT WAR' if m.get('at_war') else ''}" for m in majors) + ".")
    else:
        lines.append("Civilizations met: none yet.")
    wars = s.get("wars") or []
    lines.append("Wars: " + (", ".join(cid(w.get("civ")) for w in wars) if wars else "none") + ".")
    gp = s.get("great_people") or {}
    close = [f"{g.get('class', '').removeprefix('GREAT_PERSON_CLASS_').lower()} {g.get('ours')}/{g.get('cost')}"
             for g in gp.get("current") or [] if g.get("ours")]
    if close:
        lines.append("Great person points: " + ", ".join(close) + ".")
    if s.get("blocker"):
        lines.append(f"End-turn blocker now: {s['blocker']} (the AI clears it during autoplay).")
    return "\n".join(lines)

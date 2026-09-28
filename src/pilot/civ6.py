"""Civilization VI for the governor (docs/design/2026-09-26-civ6-governor-design.md): game access
through the controller's `civ6` commands, a scripted fake for tests, and the pure pieces the
governor needs (corpus index, briefing text, metrics rows, order checks, read-back, urgent changes).

The game's AI plays our civ through AutoplayManager; the governor reads one JSON snapshot per
decision, gives structured orders that name corpus ids, reads them back, and lets the AI play the
next stretch of turns."""

from __future__ import annotations

import copy
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from .record import EXCLUDED, FAILED, JUDGED, SUCCEEDED  # noqa: F401 - re-exported
from .record import order_record as _order_record
from .threat import relative_military, weakness, weakness_line

# ---- game access ---------------------------------------------------------------------------------


class Civ6Game(Protocol):
    def snapshot(self) -> dict: ...
    def order(self, order: dict) -> dict: ...
    def autoplay(self, turns: int) -> dict: ...
    def autoplay_stop(self) -> dict: ...
    def autoplay_status(self) -> dict: ...
    # the last stand (docs/design/2026-09-27-civ6-levers-design.md, rulings 22-27): controller
    # subcommands, never model-facing orders
    def turn_ready(self) -> dict: ...
    def ls_state(self, city_id: int) -> dict: ...
    def last_stand_step(self, city_id: int, damage: dict[str, int], skip: list[str]) -> dict: ...
    def finish_moves(self, unit_id: int) -> dict: ...
    # the AI's own strategies (ruling 29): one read of its log per decision
    def ai_strategies(self, offset: int, player: int) -> dict: ...
    # a game log's complete lines (postmortem-fixes rulings 4, 6, 24): from `offset`, or its tail
    def log_tail(self, file: str, offset: int | None = None) -> dict: ...
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

    def turn_ready(self) -> dict:
        return self._json("civ6", "turn-ready")

    def ls_state(self, city_id: int) -> dict:
        return self._json("civ6", "ls-state", str(int(city_id)))

    def last_stand_step(self, city_id: int, damage: dict[str, int], skip: list[str]) -> dict:
        """The game's reply, like `order`: `{"ok": false}` when refused (not ready, no city), and
        `transport` when no JSON came back (the action may or may not have been requested)."""
        code, out, err = self._run("civ6", "last-stand-step", str(int(city_id)), "--damage", json.dumps(damage),
                                   "--skip", ",".join(skip))
        try:
            return json.loads(out.splitlines()[-1])
        except (ValueError, IndexError):
            return {"ok": False, "transport": True, "error": (err or out or f"exit {code}")[:400]}

    def finish_moves(self, unit_id: int) -> dict:
        return self._json("civ6", "finish-moves", str(int(unit_id)))

    def ai_strategies(self, offset: int, player: int) -> dict:
        return self._json("civ6", "ai-strategies", "--offset", str(int(offset)), "--player", str(int(player)))

    def log_tail(self, file: str, offset: int | None = None) -> dict:
        return self._json("civ6", "log-tail", file, *(("--offset", str(int(offset))) if offset is not None else ()))

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
    is False. `prices[(city, id, currency)]` or `prices[(city, id)]` is an item's live price (default
    100).
    Failure modes: `busy` (every call made while autoplay is active times out, like the real tuner
    during the AI's turn processing), `start_fails` (autoplay answers ok: false), `never_starts`
    (autoplay answers ok but no turn is played), `stop_raises`, `readback_fails` (the snapshot after
    orders fails), `transport` (orders time out after they ran), `lost_orders` (the first N orders
    time out and do not run), `lost_start_reply` (the first
    autoplay call times out but runs), `lost_start_not_run` (the first N autoplay calls time out
    and do not run, as seen live at T57), `blink` (autoplay reads inactive once before its last turn
    ends, as seen live).
    The last stand: `ls` is the world around the city ({"me": 0, "units": [{id, owner, x, y, damage,
    moves, attacks}]}) that `ls_state` reads; `stand` lists `last_stand_step`'s replies in order
    (then `done`); a requested action changes `ls` through `stand_effect(ls, reply)` (default: the
    target takes the predicted damage and dies at 100, the attacker spends its attack, a retreat
    moves the unit) unless `stand_ignored`; `stand_lost_reply` loses the step's reply after it ran;
    `ls_fails` fails that many `ls_state` reads first; `popup` makes `turn_ready` (and every step)
    not ready; `pin_ignored` leaves `finish_moves` without effect; `turn_ready_silent` makes every
    n-th `turn_ready` call time out (1: every call), as the tuner does right after hand-backs.
    The AI's strategy log: `ai_log` rows (turn, player, strategy, status); `ai_strategies` returns
    those from `offset` on (the offset counts rows here, bytes in the real log)."""

    def __init__(self, base: dict, events: dict | None = None, replies: dict | None = None,
                 prices: dict | None = None, sticks: bool = True, index: CorpusIndex | None = None, ai=None,
                 busy: bool = False, start_fails: bool = False, never_starts: bool = False,
                 stop_raises: bool = False, readback_fails: bool = False, transport: bool = False,
                 lost_start_reply: bool = False, blink: bool = False, lost_start_not_run: int = 0,
                 ls: dict | None = None, stand: list[dict] | None = None, stand_effect=None,
                 stand_ignored: bool = False, stand_lost_reply: bool = False, ls_fails: int = 0,
                 popup: bool = False, pin_ignored: bool = False, ai_log: list[tuple] | None = None,
                 turn_ready_silent: int = 0, logs: dict[str, list[str]] | None = None, lost_orders: int = 0):
        self.state = copy.deepcopy(base)
        self.events = dict(events or {})
        self.replies = dict(replies or {})
        self.prices = dict(prices or {})
        self.sticks = sticks
        self.index = index
        self.ai = ai
        self.busy, self.start_fails, self.never_starts = busy, start_fails, never_starts
        self.stop_raises, self.readback_fails, self.transport = stop_raises, readback_fails, transport
        self.lost_orders = lost_orders
        self.lost_start_reply = lost_start_reply
        self.lost_start_not_run = lost_start_not_run
        self.blink, self._blinked = blink, False
        self.ls = copy.deepcopy(ls or {"me": 0, "units": []})
        self.stand = list(stand or [])
        self.stand_effect = stand_effect or _stand_apply
        self.stand_ignored, self.stand_lost_reply, self.ls_fails = stand_ignored, stand_lost_reply, ls_fails
        self.popup, self.pin_ignored = popup, pin_ignored
        self.turn_ready_silent, self._turn_ready_calls = turn_ready_silent, 0
        self.ai_log = list(ai_log or [])
        self.logs = {k: list(v) for k, v in (logs or {}).items()}     # log-tail: file -> its lines
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
        if self.blink and self.active and self.remaining == 1 and not self._blinked:
            # like the real game: before the last turn ends, autoplay already reads inactive
            self._blinked = True
            return {"ok": True, "active": False, "turns": 0, "turn": self.state["turn"]}
        self._tick("autoplay_status")
        return {"ok": True, "active": self.active, "turns": self.remaining, "turn": self.state["turn"]}

    def order(self, order: dict) -> dict:
        self.actions.append(("order", dict(order), self.active))
        self._tick("order")
        if order["kind"] == "price":
            return {"ok": True, "cost": self._price(order), "allowed": True, "currency": order.get("currency")}
        self._ordered = True
        if self.lost_orders > 0:                      # no reply, and it never ran
            self.lost_orders -= 1
            return {"ok": False, "transport": True, "error": "operation timed out"}
        cost = None
        if order["kind"] == "purchase":
            cost = self._price(order)
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

    def _price(self, order: dict):
        return self.prices.get((order["city"], order["id"], order.get("currency", "gold")),
                               self.prices.get((order["city"], order["id"]), 100))

    def autoplay(self, turns: int) -> dict:
        self.actions.append(("autoplay", turns, self.active))
        if self.start_fails:
            raise GameRefused("game-controller civ6 autoplay refused: AutoplayManager missing")
        if self.lost_start_not_run > 0:
            self.lost_start_not_run -= 1
            raise TimeoutError("autoplay: no reply (and it did not run)")
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

    def turn_ready(self) -> dict:
        self.actions.append(("turn_ready", self.active))
        self._tick("turn_ready")
        self._turn_ready_calls += 1
        if self.turn_ready_silent and self._turn_ready_calls % self.turn_ready_silent == 0:
            raise TimeoutError("turn-ready: no reply")
        why = (["autoplay active"] if self.active else []) + (["on screen: TechCivicCompletedPopup"] if self.popup else [])
        return {"ok": True, "ready": not why, "why": why, "turn": self.state["turn"]}

    def ls_state(self, city_id: int) -> dict:
        self.actions.append(("ls_state", city_id, self.active))
        self._tick("ls_state")
        if self.ls_fails > 0:
            self.ls_fails -= 1
            raise TimeoutError("ls-state: no reply")
        return {"ok": True, "turn": self.state["turn"], **copy.deepcopy(self.ls)}

    def last_stand_step(self, city_id: int, damage: dict[str, int], skip: list[str]) -> dict:
        reply = dict(self.stand.pop(0)) if self.stand else {"done": True, "reason": "nothing left to do"}
        self.actions.append(("stand", city_id, reply.get("action") or "done", self.active))
        self._tick("last_stand_step")
        if self.popup:
            return {"ok": False, "error": "not ready: on screen: TechCivicCompletedPopup"}
        if reply.get("action") and not self.stand_ignored:
            self.stand_effect(self.ls, reply)
        if reply.get("action") and self.stand_lost_reply:
            raise TimeoutError("last-stand-step: no reply")
        return {"ok": True, **reply}

    def finish_moves(self, unit_id: int) -> dict:
        self.actions.append(("finish_moves", unit_id, self.active))
        self._tick("finish_moves")
        unit = next((u for u in self.ls["units"] if u["id"] == unit_id and u["owner"] == self.ls.get("me", 0)), None)
        if unit is None:
            return {"ok": False, "error": f"no unit of ours with ID {unit_id}"}
        before = unit["moves"]
        if not self.pin_ignored:
            unit["moves"] = 0
        return {"ok": True, "unit": unit_id, "moves_before": before, "moves": unit["moves"]}

    def ai_strategies(self, offset: int, player: int) -> dict:
        self.actions.append(("ai_strategies", offset, self.active))
        rows = [[turn, name, status] for turn, who, name, status in self.ai_log[offset:] if who == player]
        return {"ok": True, "size": len(self.ai_log), "offset": offset, "next": len(self.ai_log), "restarted": False,
                "rows": rows}

    def log_tail(self, file: str, offset: int | None = None) -> dict:
        """The lines from `offset` (counted in lines here, bytes in the real log), or all of them."""
        self.actions.append(("log_tail", file, offset, self.active))
        lines = self.logs.get(file, [])
        start = 0 if offset is None else offset
        return {"ok": True, "file": file, "size": len(lines), "offset": start, "next": len(lines),
                "restarted": start > len(lines), "lines": lines[start:]}

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
        if key and key.startswith("UNIT_"):
            by_type = s.setdefault("units", {}).setdefault("by_type", {})
            by_type[key] = by_type.get(key, 0) + 1


def _stand_apply(ls: dict, reply: dict) -> None:
    """FakeCiv6's default effect of a last-stand action on the world `ls`."""
    me = ls.get("me", 0)
    actor = str(reply.get("actor") or "")
    mover = next((u for u in ls["units"] if actor == f"unit:{u['id']}" and u["owner"] == me), None)
    if reply.get("action") == "retreat" and mover:
        mover["x"], mover["y"] = reply["to"]["x"], reply["to"]["y"]
        mover["moves"] = max(0, mover["moves"] - 1)
        return
    t = reply.get("target") or {}
    target = next((u for u in ls["units"] if u["id"] == t.get("id") and u["owner"] == t.get("owner")), None)
    if target:
        target["damage"] += reply.get("predicted_damage") or 0
        if target["damage"] >= 100:
            ls["units"].remove(target)
    if mover:
        mover["attacks"] = 0


# ---- the corpus: game type keys <-> corpus ids ---------------------------------------------------

ORDER_FILES = ("tech", "civic", "policy", "unit", "building", "district", "project", "wonder", "government",
               "civ", "leader", "era", "belief")


@dataclass
class CorpusIndex:
    """`TECH_POTTERY` <-> `tech:pottery` (records' `aliases[0]` is the game's type key)."""
    by_key: dict[str, str] = field(default_factory=dict)       # type key -> corpus id
    key_of: dict[str, str] = field(default_factory=dict)       # corpus id -> type key
    name_of: dict[str, str] = field(default_factory=dict)      # corpus id -> English name
    kind_of: dict[str, str] = field(default_factory=dict)      # corpus id -> kind (file stem)
    purchase: dict[str, str] = field(default_factory=dict)     # corpus id -> gold | faith | none
    unit_class: dict[str, str] = field(default_factory=dict)   # unit id -> class (Melee, Ranged, Siege...)
    unit_domain: dict[str, str] = field(default_factory=dict)  # unit id -> land | sea | air
    resource_cost: dict[str, tuple[int, str]] = field(default_factory=dict)   # unit id -> (1, "Oil")
    maintenance: dict[str, float] = field(default_factory=dict)  # unit id -> gold per turn
    strength: dict[str, float] = field(default_factory=dict)     # unit id -> max(combat, ranged)
    build_cost: dict[str, float] = field(default_factory=dict)   # unit id -> production cost

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
                f = r.get("fields") or {}
                if f.get("purchase"):
                    idx.purchase[r["id"]] = f["purchase"]
                if kind == "unit" and f.get("class"):
                    idx.unit_class[r["id"]] = f["class"]
                    idx.unit_domain[r["id"]] = f.get("domain") or "land"
                if kind == "unit":
                    need = re.fullmatch(r"\s*(\d+)\s+(.+?)\s*", str(f.get("resource_cost") or ""))
                    if need:
                        idx.resource_cost[r["id"]] = (int(need.group(1)), need.group(2))
                    if isinstance(f.get("maintenance"), (int, float)):
                        idx.maintenance[r["id"]] = float(f["maintenance"])
                    idx.strength[r["id"]] = float(max(f.get("combat") or 0, f.get("ranged") or 0))
                    if isinstance(f.get("cost"), (int, float)):
                        idx.build_cost[r["id"]] = float(f["cost"])
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
    """An order ready for the controller (`wire`), or the reason it was refused. `note` says what the
    governor changed (faith instead of gold; bought instead of queued)."""
    order: dict
    wire: dict | None = None
    error: str = ""
    expect: dict = field(default_factory=dict)    # what the read-back looks for
    note: str = ""


def _city(snapshot: dict, name: str) -> dict | None:
    want = name.strip().lower()
    return next((c for c in snapshot.get("cities", []) if str(c.get("name", "")).lower() == want), None)


# ---- danger and buy-outs (docs/design/2026-09-27-civ6-levers-design.md, rulings 17-21) ----------

# Land units that stand on a city tile: only one fits there (the game refuses a second purchase).
LAND_COMBAT_CLASSES = frozenset({"Melee", "Ranged", "Anti Cavalry", "Light Cavalry", "Heavy Cavalry", "Siege",
                                 "Recon", "Warrior Monk", "Nihang", "GDR"})


def has_defence_fields(city: dict) -> bool:
    """Whether the snapshot has ruling 11's defence fields for this city (else the old rules apply)."""
    return any(k in city for k in ("garrison", "defense", "capture_adjacent"))


def in_danger(city: dict) -> bool:
    """A city that needs defending now (ruling 17): under siege, its garrison damaged, two enemies that
    can capture it next to it, or two enemies near an empty tile. Being merely threatened (any enemy
    within 3 tiles) held in 93% of the Kublai campaign's city snapshots, so it no longer counts.
    Without the ruling-11 fields: under siege, damaged or two enemies near (today's urgent test)."""
    if not has_defence_fields(city):
        return bool(city.get("under_siege") or city.get("damaged") or (city.get("enemies_near") or 0) >= 2)
    d = city.get("defense") or {}
    hp, top = d.get("garrison_hp"), d.get("garrison_max")
    damaged = hp < top if isinstance(hp, (int, float)) and isinstance(top, (int, float)) else bool(city.get("damaged"))
    return bool(city.get("under_siege") or damaged or (city.get("capture_adjacent") or 0) >= 2
                or ((city.get("enemies_near") or 0) >= 2 and not city.get("garrison")))


def gold_reserve_now(snapshot: dict, limits) -> int:
    """The gold kept back (ruling 18): `gold_reserve`, plus `gold_reserve_per_deficit` per gold per
    turn of deficit (30 at +1.4 per turn, 46 at -1.6)."""
    if limits is None:
        return 0
    net = (snapshot.get("yields") or {}).get("gold")
    deficit = max(0.0, -float(net)) if isinstance(net, (int, float)) else 0.0
    return math.ceil(round(limits.gold_reserve + limits.gold_reserve_per_deficit * deficit, 6))


def faith_reserve_now(snapshot: dict, limits) -> tuple[int, str]:
    """The faith kept back and why (ruling 18): the static `faith_reserve`; until a pantheon is founded,
    at least its live price (unless the game refuses one we could pay for); while a Great Prophet of our own is within reach,
    `prophet_faith_reserve`. Without the snapshot's `religion` block only the static reserve holds."""
    if limits is None:
        return 0, ""
    reserve = limits.faith_reserve
    why = f"keeps {reserve} faith in reserve" if reserve else ""
    rel = snapshot.get("religion")
    if not isinstance(rel, dict):
        return reserve, why
    cost = rel.get("pantheon_cost")
    # off only when the game refuses a pantheon we could pay for (none left to found)
    unavailable = rel.get("can_create_pantheon") is False and float(snapshot.get("faith") or 0) >= (cost or 0)
    if limits.pantheon_reserve and not rel.get("pantheon") and not unavailable \
            and isinstance(cost, (int, float)) and cost > reserve:
        reserve, why = int(cost), f"keeps {int(cost)} faith for the pantheon"
    points, price = rel.get("prophet_points"), rel.get("prophet_cost")
    if limits.prophet_faith_reserve > reserve and not rel.get("religion") \
            and (rel.get("religions_founded") or 0) < (rel.get("religions_max") or 0) \
            and isinstance(points, (int, float)) and isinstance(price, (int, float)) and price > 0 and points >= 0.5 * price:
        reserve, why = limits.prophet_faith_reserve, f"keeps {limits.prophet_faith_reserve} faith for a Great Prophet"
    return reserve, why


def _reserve(snapshot: dict, currency: str, limits) -> tuple[int, str]:
    if currency == "faith":
        return faith_reserve_now(snapshot, limits)
    r = gold_reserve_now(snapshot, limits)
    extra = r - limits.gold_reserve if limits else 0
    return r, (f"keeps {r} gold in reserve" + (f" ({limits.gold_reserve} + {extra} for the deficit)" if extra else ""))


def defender_spends_down(snapshot: dict, city: dict, limits, weak: list[dict] | None = None) -> str:
    """Why a defender purchase in `city` may spend down to the reserve (the threatened share;
    postmortem-fixes design, ruling 2), or "": the city is in danger, or the weakness test (ruling 1)
    holds, in every city. The cap was the only block on a defender the game allowed at T365, T475,
    T496, T504 and T538, and refused T544 and T553 in the war."""
    if limits is None or not limits.threatened_share:
        return ""
    if in_danger(city):
        return "the city is in danger"
    clauses = weakness(snapshot, limits) if weak is None else weak
    return "; ".join(c["text"] for c in clauses) if clauses else ""


def _share(snapshot: dict, city: dict, limits, defender: bool, weak: list[dict] | None) -> float:
    if defender and defender_spends_down(snapshot, city, limits, weak):
        return limits.threatened_share
    return limits.treasury_share or 1.0


def purchase_cap(snapshot: dict, city: dict, currency: str, limits, committed: float = 0.0, *,
                 defender: bool = False, weak: list[dict] | None = None) -> int:
    """The most one purchase may cost: the balance above the reserve, and at most the treasury share
    of the balance; a defender (`defender`) gets the threatened share (down to the reserve) in a city
    in danger or while the weakness test holds (ruling 2; `weak`: its clauses when already computed).
    Buildings and other units (a Rock Band, a Settler) keep the treasury share everywhere. `committed`
    is what earlier purchases of the same decision may already spend, so together they never go below
    the reserve."""
    balance = float(snapshot.get("faith" if currency == "faith" else "gold") or 0) - committed
    reserve = _reserve(snapshot, currency, limits)[0]
    share = _share(snapshot, city, limits, defender, weak)
    return int(max(0.0, min(balance - reserve, share * balance)))


def cap_binding(snapshot: dict, city: dict, currency: str, limits, committed: float = 0.0, *,
                defender: bool = False, weak: list[dict] | None = None) -> str:
    """Which limit sets `purchase_cap`: the reserve (named, with the clause that let a defender spend
    down to it) or the share of the balance."""
    balance = float(snapshot.get("faith" if currency == "faith" else "gold") or 0) - committed
    reserve, why = _reserve(snapshot, currency, limits)
    down = defender_spends_down(snapshot, city, limits, weak) if defender else ""
    share = limits.threatened_share if down else (limits.treasury_share or 1.0)
    if balance - reserve <= share * balance:
        text = why or f"keeps {reserve} {currency} in reserve"
        return f"{text} (a defender may spend down to the reserve: {down})" if down else text
    return (f"one purchase takes at most {share:.0%} of the {currency} balance"
            + ("" if down or not limits.threatened_share
               else f" (a defender: {limits.threatened_share:.0%} in a city in danger or under military weakness)"))


def is_defender(item: str | None, index: CorpusIndex, limits) -> bool:
    """A unit whose class (data/unit.json fields.class) is one of the pillars' defender classes."""
    return bool(item and limits is not None and index.kind_of.get(item) == "unit"
                and index.unit_class.get(item) in limits.defender_classes and index.unit_domain.get(item) == "land")


def resource_key(name: str) -> str:
    """The snapshot's key for a strategic resource the corpus names: "Oil" -> RESOURCE_OIL."""
    return "RESOURCE_" + re.sub(r"\W+", "_", name.strip()).upper()


def refusal(p: dict, currency: str, snapshot: dict, index: CorpusIndex) -> tuple[str, str] | None:
    """Why the game refuses to sell a `defence_prices` entry in `currency` (postmortem-fixes design,
    ruling 7), as (class, text), or None when it sells it. `resource`: the corpus `resource_cost`
    against the snapshot's strategic stock ("needs 1 Oil, have 0"; "stock unknown" without one, unless
    the library named another cause); `stacking`: a unit is on the tile; `balance`: the price is over
    the balance; `game`: any other refusal of the game."""
    if p.get(f"{currency}_allowed"):
        return None
    why = p.get(f"{currency}_why")
    need = index.resource_cost.get(index.cid(p.get("unit")))
    if need:
        stock = snapshot.get("resources")
        have = stock.get(resource_key(need[1]), 0) if isinstance(stock, dict) else None
        if have is not None and have < need[0]:
            return "resource", f"needs {need[0]} {need[1]}, have {_n(have)}"
        if have is None and why not in ("stacking", "balance"):
            return "resource", f"needs {need[0]} {need[1]}, stock unknown"
    if why == "stacking":
        return "stacking", "a unit is on the tile"
    if why == "balance":
        return "balance", f"costs {_n(p.get(currency))} {currency}, over the balance of {_n(snapshot.get(currency))}"
    return "game", "the game refuses it"


def defender_entries(city: dict, index: CorpusIndex, limits) -> list[dict]:
    """The city's `defence_prices` entries for units of the pillars' defender classes (all of them
    without limits)."""
    return [p for p in city.get("defence_prices") or []
            if limits is None or is_defender(index.cid(p.get("unit")), index, limits)]


def is_land_combat(item: str | None, index: CorpusIndex) -> bool:
    return bool(item and index.unit_class.get(item) in LAND_COMBAT_CLASSES and index.unit_domain.get(item) == "land")


def known_prices(snapshot: dict, index: CorpusIndex, seen: dict | None = None) -> dict[tuple[str, str, str], dict]:
    """Prices known in this decision, by (city name lowercased, corpus id, currency): each in-danger
    city's `defence_prices` from the snapshot, and the `price` tool's answers (`seen`, which win)."""
    out: dict[tuple[str, str, str], dict] = {}
    for c in snapshot.get("cities") or []:
        for p in c.get("defence_prices") or []:
            for cur in ("gold", "faith"):
                if isinstance(p.get(cur), (int, float)):
                    out[(str(c.get("name", "")).lower(), index.cid(p.get("unit")), cur)] = {
                        "cost": p[cur], "allowed": bool(p.get(f"{cur}_allowed"))}
    out.update(seen or {})
    return out


@dataclass
class _Checks:
    """What earlier orders of one decision already use."""
    counts: dict[str, int] = field(default_factory=dict)
    committed: dict[str, float] = field(default_factory=lambda: {"gold": 0.0, "faith": 0.0})
    cities_ordered: set[str] = field(default_factory=set)      # production: one order per city
    land_bought: set[str] = field(default_factory=set)         # a land unit bought onto the city tile
    defended: set[str] = field(default_factory=set)            # cities that get a defender now
    defence_tried: set[str] = field(default_factory=set)       # cities a defender purchase was checked for
    known: dict = field(default_factory=dict)
    defender_buys: dict[str, int] = field(default_factory=dict)
    weak: list[dict] = field(default_factory=list)             # the weakness test's clauses (ruling 1)


def check_orders(orders: list[Civ6Order], snapshot: dict, spec, index: CorpusIndex,
                 failed_last: set[str] | None = None, *, prices: dict | None = None,
                 defender_buys: dict[str, int] | None = None, queue_only=frozenset()) -> list[Checked]:
    """Each order checked against the corpus, the pillars' limits and the snapshot. `failed_last`
    holds orders (as `order_key`) that did not stick at the previous decision: not retried blindly.
    Without a pillars spec (a broken file) each kind gets one order and purchases are refused.
    Other orders are checked in the model's order, then purchases, a defender for a city in danger
    first (ruling 19); a production order for a defender of an ungarrisoned city in danger becomes
    a purchase when a known price fits (ruling 20). `prices`: the `price` tool's answers in this
    decision; `defender_buys`: the turn of each city's last defender purchase (lowercased name);
    `queue_only`: order keys (`order_key`) of production orders that are never bought instead: the
    governor's own fills (postmortem-fixes ruling 3), so a purchase is only ever the model's order or
    ruling 3's single rule buy with its upkeep and cooldown checks."""
    out = [Checked(order=o.model_dump()) for o in orders]
    buy = spec.actions.get("purchase") if spec else None
    st = _Checks(known=known_prices(snapshot, index, prices), defender_buys=dict(defender_buys or {}),
                 weak=weakness(snapshot, buy) if buy is not None else [])
    purchases: list[tuple[Civ6Order, Checked, Civ6Order | None]] = []
    for o, c in zip(orders, out, strict=True):
        if o.kind == "purchase":
            purchases.append((o, c, None))
            continue
        convert = o.kind == "production" and order_key(o.model_dump()) not in queue_only
        instead = _must_have(o, snapshot, index, buy, st) if convert else None
        if instead is not None:
            purchases.append((instead, c, o))
            continue
        _check(c, o, snapshot, spec, index, failed_last, st)

    def defence_first(item):
        city = _city(snapshot, item[0].city) or {}
        return 0 if is_defender(item[0].id, index, buy) and in_danger(city) else 1
    for o, c, queued in sorted(purchases, key=defence_first):       # stable: the model's order otherwise
        city = _city(snapshot, o.city or "")
        if city is not None and is_defender(o.id, index, buy):
            st.defence_tried.add(city["name"])                       # tried, whatever the checks answer
        if _check(c, o, snapshot, spec, index, failed_last, st) or queued is None:
            if queued is not None:
                p = st.known.get((c.wire["city"].lower(), o.id, c.wire["currency"])) or {}
                c.note = f"bought instead of queued (in danger): {p.get('cost', '?')} {c.wire['currency']}"
            continue
        c.error, c.note = "", ""                                     # the purchase did not fit: queue it
        _check(c, queued, snapshot, spec, index, failed_last, st)
    return out


def _must_have(o: Civ6Order, snapshot: dict, index: CorpusIndex, buy, st: _Checks) -> Civ6Order | None:
    """A production order carried out as a purchase instead (ruling 20): a defender, for a city in
    danger with no unit on its tile that is not about to finish a defender itself, when a known
    price (faith first) fits the cap. None: queue it as ordered."""
    if buy is None or not is_defender(o.id, index, buy):
        return None
    city = _city(snapshot, o.city)
    if city is None or "garrison" not in city or city.get("garrison") or not in_danger(city):
        return None
    if _finishes_defender(city, index, buy):
        return None
    for currency in ("faith", "gold"):
        p = st.known.get((city["name"].lower(), o.id, currency))
        if p and p.get("allowed") and p["cost"] <= purchase_cap(snapshot, city, currency, buy, st.committed[currency],
                                                                 defender=True, weak=st.weak):
            return Civ6Order(kind="purchase", id=o.id, city=city["name"], currency=currency)
    return None


def _check(c: Checked, o: Civ6Order, snapshot: dict, spec, index: CorpusIndex, failed_last, st: _Checks) -> bool:
    action = ORDER_ACTION[o.kind]
    limits = spec.actions.get(action) if spec else None
    if spec is not None and limits is None:
        c.error = f"{o.kind} orders are not enabled in pillars.toml"
        return False
    if limits is None and o.kind == "purchase":
        c.error = "purchases need the limits of pillars.toml, which did not load"
        return False
    quota = limits.max_orders if limits is not None else 1
    # ruling 2: while the weakness test holds, defender purchases in different cities do not count
    # toward the quota (one defender per city per decision still holds)
    free = o.kind == "purchase" and bool(st.weak) and is_defender(o.id, index, limits)
    if not free and st.counts.get(action, 0) >= quota:
        c.error = f"at most {quota} {o.kind} order(s) per decision"
        return False
    if failed_last and order_key(c.order) in failed_last:
        c.error = "did not stick at the last decision; not retried until something changes (say why to retry)"
        return False
    if not _check_one(c, o, snapshot, index, limits, snapshot.get("options") or {}, st):
        return False
    if not free:
        st.counts[action] = st.counts.get(action, 0) + 1  # only valid orders use the quota
    return True


WALLS = ("building:walls", "building:castle", "building:star_fort")


def _finishes_defender(city: dict, index: CorpusIndex, limits) -> bool:
    """The city's own build is a defender it finishes within the skip window (ruling 20: at most
    `skip_turns_left`, and 2 turns), so buying one there is refused or pointless."""
    now, left = city.get("producing"), city.get("turns_left")
    return bool(now and is_defender(index.cid(now), index, limits) and isinstance(left, int)
                and left <= max(limits.skip_turns_left, 2))


def _needs_defender_first(city: dict, snapshot: dict, index: CorpusIndex, limits, st: _Checks) -> bool:
    """Whether an ungarrisoned city in danger holds back other purchases (ruling 19): not once a
    defender purchase for it was tried in this decision (whatever the checks answered), while it
    finishes a defender of its own within the skip window, while its cooldown runs, or when its
    listed defenders (those of the pillars' classes) are none allowed and affordable."""
    name = city.get("name")
    if not (in_danger(city) and "garrison" in city and not city.get("garrison")):
        return False
    if name in st.defended or name in st.defence_tried or _finishes_defender(city, index, limits):
        return False
    last, turn, wait = st.defender_buys.get(str(name).lower()), snapshot.get("turn"), limits.defence_cooldown_turns
    if wait and isinstance(last, int) and isinstance(turn, int) and turn - last < wait:
        return False
    if city.get("defence_prices") is None:
        return True                                 # prices unknown: the model can price one
    return any(p.get(f"{cur}_allowed") and isinstance(p.get(cur), (int, float))
               and p[cur] <= purchase_cap(snapshot, city, cur, limits, st.committed[cur], defender=True, weak=st.weak)
               for p in city["defence_prices"] if is_defender(index.cid(p.get("unit")), index, limits)
               for cur in ("gold", "faith"))


def _check_one(c: Checked, o: Civ6Order, snapshot: dict, index: CorpusIndex, limits, options: dict,
               st: _Checks) -> bool:
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
        if city["name"] in st.cities_ordered:
            c.error = f"{city['name']} already has a production order in this decision (one per city)"
            return False
        if city.get("can_build") is not None and key not in city["can_build"]:
            c.error = f"{city['name']} cannot build {o.id} now"
            return False
        st.cities_ordered.add(city["name"])
        c.wire = {"kind": "production", "city": city["name"], "id": o.id}
        c.expect = {"city": city["name"], "producing": key}
        return True
    return _check_purchase(c, o, key, city, snapshot, index, limits, st)


def _check_purchase(c: Checked, o: Civ6Order, key: str, city: dict, snapshot: dict, index: CorpusIndex, limits,
                    st: _Checks) -> bool:
    """A purchase within the buy-out rules (rulings 18-21); `c.note` when the governor switched it to
    faith."""
    name = city["name"]
    if index.purchase.get(o.id) == "none":
        c.error = f"{o.id} cannot be bought" + (": walls come from production" if o.id in WALLS else "")
        return False
    if index.kind_of.get(o.id) == "building" and city.get("can_build") is not None and key not in city["can_build"]:
        c.error = f"{name} cannot build {o.id} now"
        return False
    defender = is_defender(o.id, index, limits)
    now, left = city.get("producing"), city.get("turns_left")
    if limits.skip_turns_left and now and isinstance(left, int) and left <= limits.skip_turns_left:
        now_id = index.cid(now)
        if now == key or (defender and is_defender(now_id, index, limits)
                          and index.unit_class.get(now_id) == index.unit_class.get(o.id)):
            c.error = f"{name} finishes {now_id} in {left} turn{'' if left == 1 else 's'} anyway"
            return False
    land = is_land_combat(o.id, index)
    if land and "garrison" in city and (city.get("garrison") or name in st.land_bought):
        holder = index.cid(city["garrison"]) if city.get("garrison") else "the unit bought before this one"
        c.error = f"{name} already has {holder} on its tile: the game refuses a second land unit there"
        return False
    if defender and st.weak and name in st.defended:     # ruling 2: outside the quota, one per city
        c.error = f"{name} already gets a defender in this decision (one per city)"
        return False
    if limits.defence_first and not defender:
        for other in snapshot.get("cities") or []:
            if _needs_defender_first(other, snapshot, index, limits, st):
                c.error = f"{other['name']} is in danger with no defender on its tile: buy a defender there first"
                return False
    last, turn, wait = st.defender_buys.get(name.lower()), snapshot.get("turn"), limits.defence_cooldown_turns
    if defender and wait and isinstance(last, int) and isinstance(turn, int) and turn - last < wait:
        c.error = f"{name} got a defender at T{last}: the next defender purchase there waits until T{last + wait}"
        return False
    currency = o.currency
    if defender and currency == "gold":
        faith, gold = st.known.get((name.lower(), o.id, "faith")), st.known.get((name.lower(), o.id, "gold"))
        if faith and faith.get("allowed") and faith["cost"] <= purchase_cap(snapshot, city, "faith", limits,
                                                                           st.committed["faith"], defender=True,
                                                                           weak=st.weak):
            currency = "faith"
            c.note = f"bought with faith instead of gold: {faith['cost']} faith" + (
                f" rather than {gold['cost']} gold" if gold else "")
    cap = purchase_cap(snapshot, city, currency, limits, st.committed[currency], defender=defender, weak=st.weak)
    if cap <= 0:
        reserve, why = _reserve(snapshot, currency, limits)
        c.error = (f"{currency} {snapshot.get(currency)} (less {st.committed[currency]:.0f} for earlier purchases"
                   + (f", the defender for {', '.join(sorted(st.defended))} first" if st.defended else "")
                   + f") is at or below the reserve {reserve}" + (f" ({why})" if why else ""))
        return False
    price = st.known.get((name.lower(), o.id, currency))
    if price and isinstance(price.get("cost"), (int, float)) and price["cost"] > cap:
        c.error = (f"{o.id} costs {price['cost']:g} {currency} in {name}, over the {cap} allowed: "
                   + cap_binding(snapshot, city, currency, limits, st.committed[currency], defender=defender, weak=st.weak))
        return False
    st.committed[currency] += price["cost"] if price and isinstance(price.get("cost"), (int, float)) else cap
    if defender:
        st.defended.add(name)
    if land:
        st.land_bought.add(name)
    c.wire = {"kind": "purchase", "city": name, "id": o.id, "currency": currency, "max_cost": cap}
    c.expect = {"spend": currency, "before": snapshot.get(currency)}
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


def lost_proof(c: Checked, before: dict, after: dict | None, index: CorpusIndex) -> str | None:
    """Proof that a purchase whose reply was lost never ran (postmortem-fixes design, ruling 5): the
    read-back of the same turn shows the balance within 1 of its value before and the item's count
    unchanged (a unit's `units.by_type`, a building in the city's `buildings`). "nothing spent (proved)",
    or None when the read-back failed, the turn changed, the balance moved or the count cannot be read
    (it may have run: never sent again)."""
    w = c.wire or {}
    if w.get("kind") != "purchase" or after is None or after.get("turn") != before.get("turn"):
        return None
    cur = w.get("currency") or "gold"
    was, now = c.expect.get("before", before.get(cur)), after.get(cur)
    if not isinstance(was, (int, float)) or not isinstance(now, (int, float)) or abs(now - was) > 1:
        return None
    key = index.key_of.get(w.get("id") or "")
    if not key:
        return None
    if key.startswith("UNIT_"):
        counts = [((s.get("units") or {}).get("by_type")) for s in (before, after)]
        if not all(isinstance(x, dict) for x in counts) or counts[0].get(key, 0) != counts[1].get(key, 0):
            return None
    else:
        held = [(_city(s, str(w.get("city") or "")) or {}).get("buildings") for s in (before, after)]
        if not all(isinstance(x, list) for x in held) or (key in held[0]) != (key in held[1]):
            return None
    return "nothing spent (proved)"


# ---- the rule-based defender (docs/design/2026-09-27-postmortem-fixes-design.md, ruling 3) -----------

def _free_of_resources(uid: str, index: CorpusIndex) -> bool:
    return uid not in index.resource_cost


def rule_buy_order(snapshot: dict, index: CorpusIndex, limits, defender_buys: dict[str, int] | None = None,
                   weak: list[dict] | None = None) -> tuple[Civ6Order | None, str]:
    """The governor's own defender purchase before a multi-turn stretch while the weakness test holds
    (ruling 3): the first ungarrisoned city (in danger, then threatened, then without walls, then the
    capital, then by name) whose `defence_prices` list a defender the game allows, of a defender class,
    needing no strategic resource, within the defender cap, past the city's defender cooldown, whose
    upkeep leaves gold per turn at 0 or above; the strongest by corpus max(combat, ranged), then the
    cheaper, faith tried first (the AI's own purchases drained it). (order, "") or (None, why none)."""
    if limits is None:
        return None, "no purchase limits"
    turn, wait = snapshot.get("turn"), limits.defence_cooldown_turns
    gold_yield = (snapshot.get("yields") or {}).get("gold")
    cities = [c for c in snapshot.get("cities") or [] if "garrison" in c and not c.get("garrison")]
    if not cities:
        return None, "every city has a unit on its tile"
    rank = lambda c: (not in_danger(c), not c.get("threatened"), bool((c.get("defense") or {}).get("walls_max")),
                      not c.get("capital"), str(c.get("name")))
    why, upkept = "no city lists a defender it can buy now", ""
    for c in sorted(cities, key=rank):
        last = (defender_buys or {}).get(str(c.get("name", "")).lower())
        if wait and isinstance(last, int) and isinstance(turn, int) and turn - last < wait:
            why = f"{c.get('name')} got a defender at T{last}"
            continue
        for cur in ("faith", "gold"):
            cap = purchase_cap(snapshot, c, cur, limits, defender=True, weak=weak)
            fits = []
            for p in defender_entries(c, index, limits):
                uid = index.cid(p.get("unit"))
                upkeep = index.maintenance.get(uid, 0.0)
                if not (p.get(f"{cur}_allowed") and isinstance(p.get(cur), (int, float)) and p[cur] <= cap
                        and _free_of_resources(uid, index)):
                    continue
                if isinstance(gold_yield, (int, float)) and gold_yield - upkeep < 0:
                    upkept = upkept or (f"upkeep: {uid} in {c.get('name')} costs {upkeep:g} gold a turn and gold per "
                                        f"turn is {gold_yield:+g}")
                    continue
                fits.append((-index.strength.get(uid, 0.0), p[cur], uid))
            if fits:
                _s, _cost, uid = min(fits)
                return Civ6Order(kind="purchase", id=uid, city=str(c.get("name")), currency=cur), ""
    return None, upkept or why


def defender_to_build(city: dict, index: CorpusIndex, limits) -> str | None:
    """The strongest defender (then the cheaper to build) that the city can build and that needs no
    strategic resource: the governor's fill of an empty queue under weakness (ruling 3, L15)."""
    can = [index.cid(k) for k in city.get("can_build") or []]
    options = [(-index.strength.get(u, 0.0), index.build_cost.get(u, 0.0), u) for u in can
               if is_defender(u, index, limits) and _free_of_resources(u, index)]
    return min(options)[2] if options else None


# ---- what the AI spent between decisions (postmortem-fixes design, ruling 4) ------------------------

AI_BUILD_LOG = "AI_CityBuild.csv"
AI_PURCHASE_KINDS = {"FAITH PURCHASE": "faith", "PURCHASE": "gold"}
_ITEM_RE = re.compile(r"^(?:UNIT|BUILDING|DISTRICT|PROJECT)_[A-Z0-9_]+$")


def ai_spent(before: dict, now: dict) -> dict[str, float]:
    """Per currency, what the game's AI spent between two snapshots (ruling 4): the balance before +
    the start snapshot's yield x the turns played - the balance now. Our own purchases are already in
    `before` (the read-back after our orders). T525 -> T528: 2,278 + 226 x 3 - 958 = 1,998 faith, the
    Rock Band the game logged at T526 (E10). A yield change inside the stretch reads as spending."""
    turns = max(0, int(now.get("turn") or 0) - int(before.get("turn") or 0))
    out = {}
    for cur in ("gold", "faith"):
        b0, b1, y = before.get(cur), now.get(cur), (before.get("yields") or {}).get(cur)
        if all(isinstance(v, (int, float)) for v in (b0, b1, y)):
            out[cur] = round(b0 + y * turns - b1, 1)
    return out


def spend_shown(spent: float, yield_total: float) -> bool:
    """A spend is worth a line at max(50, 10% of the yield over the interval): yields change mid-stretch."""
    return spent >= max(50.0, 0.1 * abs(yield_total))


def ai_purchases(lines: list[str], player: int) -> list[dict]:
    """Our player's purchases in AI_CityBuild.csv lines: [{"turn", "currency", "item"}]. The layout is
    unverified live: a row counts when its first two fields are the turn and the player, one field is
    FAITH PURCHASE or PURCHASE and one names an item type (UNIT_*, BUILDING_*...); others are skipped,
    so a changed layout gives "not named", never a wrong name."""
    out = []
    for line in lines:
        f = [x.strip() for x in str(line).split(",")]
        if len(f) < 4 or not f[0].isdigit() or f[1] != str(player):
            continue
        kind = next((AI_PURCHASE_KINDS[x.upper()] for x in f[2:] if x.upper() in AI_PURCHASE_KINDS), None)
        item = next((x for x in f[2:] if _ITEM_RE.match(x)), None)
        if kind and item:
            out.append({"turn": int(f[0]), "currency": kind, "item": item})
    return out


def ai_spent_text(since: int, spent: dict[str, float], yields: dict[str, float], bought: list[dict] | None) -> str:
    """The decision prompt's line (ruling 4), e.g. "Since T525 the AI spent 1,998 faith (UNIT_ROCK_BAND,
    T526) and 1,717 gold (not named)."; "" when no currency passes `spend_shown`. `bought`: the log's
    purchases in the interval (None: the log was not read)."""
    parts = []
    for cur in ("faith", "gold"):
        v = spent.get(cur) or 0.0
        if not spend_shown(v, yields.get(cur) or 0.0):
            continue
        items = [f"{x['item']}, T{x['turn']}" for x in bought or [] if x["currency"] == cur]
        parts.append(f"{v:,.0f} {cur} (" + ("; ".join(items) if items else "not named") + ")")
    if not parts:
        return ""
    return (f"Since T{since} the AI spent " + " and ".join(parts) + " between our decisions (balance before + "
            "yield x turns - balance now; the game's AI buys with our treasury while it plays).")


# ---- price changes between decisions (postmortem-fixes design, ruling 6) ------------------------------

WORLD_CONGRESS_LOG = "World_Congress.csv"
PRICE_CHANGE = 0.25          # a defender's price that moved this much between decisions, within one era
WC_LOOKBACK = 30             # turns of World Congress decisions named as a cause (sessions come about every 30)
_WC_RES_RE = re.compile(r"^WC_RES_[A-Z0-9_]+$")


def defender_prices(s: dict) -> dict:
    """The snapshot's defender prices by (unit type key, currency), the lowest over the cities listing
    it, with the era and turn they were read in."""
    out: dict[tuple[str, str], float] = {}
    for c in s.get("cities") or []:
        for p in c.get("defence_prices") or []:
            for cur in ("gold", "faith"):
                v = p.get(cur)
                if isinstance(v, (int, float)) and v > 0 and p.get("unit"):
                    k = (p["unit"], cur)
                    out[k] = min(out.get(k, v), v)
    return {"era": s.get("era"), "turn": s.get("turn"), "prices": out}


def world_congress_decided(lines: list[str], after: int, upto: int) -> list[dict]:
    """World_Congress.csv rows "542, RESOLUTION DECIDED, WC_RES_MERCENARY_COMPANIES, , 2, 2" (read offline
    for the post-mortem; the live layout is unverified: a row that does not parse names nothing) with
    after < turn <= upto: [{"turn", "resolution"}], oldest first."""
    out = []
    for line in lines:
        f = [x.strip() for x in str(line).split(",")]
        if not f or not f[0].isdigit() or not any(x.upper() == "RESOLUTION DECIDED" for x in f[1:]):
            continue
        res = next((x for x in f[1:] if _WC_RES_RE.match(x)), None)
        if res and after < int(f[0]) <= upto:
            out.append({"turn": int(f[0]), "resolution": res})
    return out


def _moved(old: float, new: float) -> str:
    r = new / old
    if 0.45 <= r <= 0.55:
        return "halved"
    if 1.8 <= r <= 2.2:
        return "doubled"
    return f"fell {1 - r:.0%}" if r < 1 else f"rose {r - 1:.0%}"


def price_change_text(since, before: dict | None, now: dict, index: CorpusIndex, decided: list[dict] | None) -> str:
    """Ruling 6's prompt line, "" without a change of `PRICE_CHANGE` or more within one era: e.g.
    "Price change: gold unit prices halved since T543 (unit:modern_at 2,320 → 1,160); World Congress:
    WC_RES_MERCENARY_COMPANIES (T542); this may end at the next World Congress session." `decided`: the
    World Congress decisions of the window (None: not read); the session calendar is not read
    (unverified), hence "may end". Mercenary Companies halved gold unit prices T544-T571, and 1,626-1,676
    gold was stranded when it ended at T572 (treasury-8)."""
    if not before or before.get("era") != now.get("era"):
        return ""
    parts = []
    for cur in ("gold", "faith"):
        moved = sorted(((abs(new / old - 1), k[0], old, new) for k, new in now["prices"].items()
                        if k[1] == cur and (old := before["prices"].get(k)) and abs(new / old - 1) >= PRICE_CHANGE),
                       reverse=True)
        if moved:
            examples = ", ".join(f"{index.cid(u)} {old:,.0f} → {new:,.0f}" for _, u, old, new in moved[:2])
            parts.append(f"{cur} unit prices {_moved(moved[0][2], moved[0][3])} since T{since} ({examples})")
    if not parts:
        return ""
    text = "Price change: " + "; ".join(parts)
    if decided:
        text += "; World Congress: " + ", ".join(f"{d['resolution']} (T{d['turn']})" for d in decided[-3:]) \
            + "; this may end at the next World Congress session"
    return text + "."


# ---- the order record (docs/design/2026-09-27-civ6-levers-design.md, rulings 12-16) --------------
#
# Acceptance is not the outcome: an order that took may still be replaced by the AI during autoplay.
# Every order that took is followed on each snapshot until it resolves; its outcome row feeds the
# stick rate per kind of order.

# the outcomes and the stick rate are shared with Stellaris (record.py)
# last-stand actions (ruling 26): the step's action name -> the record's key
STAND_KEYS = {"city_strike": "stand city_strike", "ranged_attack": "stand ranged", "retreat": "stand retreat",
              "pin": "stand pin"}
# purchases by item class and currency (postmortem-fixes design, ruling 9): "faith purchases held 8 of 8"
# came from cheap buildings while no faith unit purchase was sent from T385 to T541
PURCHASE_CLASSES = ("unit", "building")
RECORD_KEYS = ("research", "civic", "policies", "production fill", "production replace",
               *(f"purchase {k} {cur}" for k in PURCHASE_CLASSES for cur in ("gold", "faith")), *STAND_KEYS.values())
LEGACY_PURCHASE_KEYS = {"purchase gold": "gold", "purchase faith": "faith"}     # rows written before ruling 9


def order_situation(before: dict, key: str, city_name: str) -> str:
    """A production order 'fill's the city's queue when it was empty or the AI's item had one turn or
    less left (ruling 14); it is 'current' when the city already built this item (a no-op, kept out
    of the record); otherwise it 'replace's the AI's choice."""
    city = _city(before, city_name) or {}
    now = city.get("producing")
    if now and now == key:
        return "current"
    if not now or (city.get("turns_left") is not None and city["turns_left"] <= 1):
        return "fill"
    return "replace"


def purchase_class(item: str | None) -> str:
    """A purchase's item class from its corpus id: unit, else building (the only other kind bought)."""
    return "unit" if str(item or "").startswith("unit:") else "building"


def record_key(order: dict, situation: str | None = None) -> str:
    """The order record's key: research, civic, policies, production fill|replace, purchase
    unit|building gold|faith (ruling 9)."""
    kind = order.get("kind")
    if kind == "production":
        return f"production {situation or 'replace'}"
    if kind == "purchase":
        return f"purchase {purchase_class(order.get('id'))} {order.get('currency') or 'gold'}"
    return str(kind)


def rekey_purchases(rows: list[dict], index: CorpusIndex) -> list[dict]:
    """Rows written before ruling 9 (`purchase gold`, `purchase faith`) keyed by the corpus kind of
    their id, so a campaign's record spans the change."""
    out = []
    for r in rows:
        cur = LEGACY_PURCHASE_KEYS.get(r.get("key"))
        if cur:
            kind = index.kind_of.get(r.get("id") or "") or purchase_class(r.get("id"))
            r = {**r, "key": f"purchase {'unit' if kind == 'unit' else 'building'} {cur}"}
        out.append(r)
    return out


# Why a purchase was refused (ruling 9): (text in the harness's refusal, class). The game's own
# refusals are `game`, or `resource` / `stacking` when the snapshot shows the cause.
_HARNESS_REFUSALS = (("allowed:", "cap"), ("at or below the reserve", "reserve"),
                     ("buy a defender there first", "defence_first"), ("on its tile", "stacking"),
                     ("purchase there waits", "cooldown"), ("anyway", "skip"), ("per decision", "quota"),
                     ("one per city", "quota"))
REFUSAL_LABELS = {"defence_first": "defence first"}


def purchase_refusal(status: str, order: dict, snapshot: dict | None, index: CorpusIndex) -> dict:
    """A refused purchase's class (ruling 9): {"refusal", "refused_by": harness | game[, "resource"]}.
    The harness refuses by the cap, the reserve, a unit on the tile, the defender cooldown, the skip rule,
    defence first, the order quota (or `other`: an unknown id or city, a repeat); a price over our cap
    that the library refused is the cap too. The game's refusal is `resource` when the unit needs a
    strategic resource our stock lacks (or the stock is unknown), `stacking` when our land unit stands
    on the tile, else `game`."""
    text = str(status)
    if text.startswith("refused by the game"):
        if "over the allowed" in text:
            return {"refusal": "cap", "refused_by": "harness"}       # the library checked our cap on the live price
        item = str(order.get("id") or "")
        need = index.resource_cost.get(item)
        stock = (snapshot or {}).get("resources")
        have = stock.get(resource_key(need[1]), 0) if need and isinstance(stock, dict) else None
        if need and (have is None or have < need[0]):
            return {"refusal": "resource", "refused_by": "game", "resource": need[1]}
        city = _city(snapshot or {}, str(order.get("city") or "")) or {}
        if city.get("garrison") and is_land_combat(item, index):
            return {"refusal": "stacking", "refused_by": "game"}
        return {"refusal": "game", "refused_by": "game"}
    cls = next((c for needle, c in _HARNESS_REFUSALS if needle in text), "other")
    return {"refusal": cls, "refused_by": "harness"}


def _refusal_of(r: dict) -> tuple[str, str]:
    """(who, label) of a refused row: its `refusal`, or (rows before ruling 9) its detail's text."""
    if r.get("refusal"):
        by, cls = r.get("refused_by") or "harness", r["refusal"]
    else:
        got = purchase_refusal(str(r.get("detail") or ""), {}, None, CorpusIndex())
        by, cls = got["refused_by"], "game" if got["refused_by"] == "game" else got["refusal"]
    if cls == "resource":
        return by, str(r.get("resource") or "resource")
    return by, REFUSAL_LABELS.get(cls, cls)


def purchase_counts(rows: list[dict], now_turn: int, window: int) -> dict[str, dict] | None:
    """Purchases of the last `window` turns by item class (ruling 9): bought per currency, refused by
    the harness and by the game (by class), lost and unknown. Counts only: a purchase read back as done
    is completed by construction, so a rate would say nothing. None before the campaign's first purchase."""
    mine = [r for r in rows if str(r.get("key") or "").startswith("purchase ")]
    if not mine:
        return None
    recent = [r for r in mine if isinstance(r.get("turn"), int) and now_turn - window < r["turn"] <= now_turn]
    out: dict[str, dict] = {}
    for cls in PURCHASE_CLASSES:
        rs = [r for r in recent if r["key"].split(" ")[1] == cls]
        c = {"bought": {}, "harness": {}, "game": {}, "lost": 0, "unknown": 0}
        for r in rs:
            res = r.get("result")
            if res == "completed":
                cur = r["key"].split(" ")[-1]
                c["bought"][cur] = c["bought"].get(cur, 0) + 1
            elif res == "refused":
                by, label = _refusal_of(r)
                c[by][label] = c[by].get(label, 0) + 1
            elif res in ("lost", "unknown"):
                c[res] += 1
        out[cls] = c
    return out


def _counted(d: dict[str, int]) -> str:
    return ", ".join(f"{k} {n}" for k, n in sorted(d.items()))


def purchase_counts_text(counts: dict[str, dict] | None, window: int) -> str:
    """The record's purchase block (ruling 9), e.g. "  - unit purchases: 7 bought (faith 5, gold 2), 2
    refused by the harness (cap 2), 2 refused by the game (Oil 1, stacking 1), 2 lost"."""
    if not counts:
        return ""
    lines = [f"- purchases in the last {window} turns (counts only: a purchase read back as done is bought at once):"]
    for cls in PURCHASE_CLASSES:
        c = counts.get(cls) or {"bought": {}, "harness": {}, "game": {}, "lost": 0, "unknown": 0}
        bought, harness, game = sum(c["bought"].values()), sum(c["harness"].values()), sum(c["game"].values())
        sent = bought + game + c["lost"] + c["unknown"]
        parts = [f"{bought} bought ({_counted(c['bought'])})" if bought else ""]
        if game:
            parts.append(f"{game} refused by the game ({_counted(c['game'])})")
        for res in ("lost", "unknown"):
            if c[res]:
                parts.append(f"{c[res]} {res}")
        refused = f"{harness} refused by the harness ({_counted(c['harness'])})" if harness else ""
        if not sent:
            text = "0 sent" + (f"; {refused}" if refused else "")
        else:
            shown = [p for p in parts if p]
            if refused:
                shown.insert(1 if bought else 0, refused)
            text = ", ".join(shown)
        lines.append(f"  - {cls} purchases: {text}")
    return "\n".join(lines)


def order_window(kind: str, turns_left, cap: int = 20, grace: int = 3) -> int:
    """Turns an order is followed: its turns left plus `grace`, at least `grace`, at most `cap`
    (policies: `cap`; they never complete)."""
    if kind == "policies":
        return cap
    left = int(turns_left) if isinstance(turns_left, (int, float)) else 0
    return min(cap, max(grace, left + grace))


def order_base(c: Checked, after: dict) -> dict:
    """What later snapshots are compared with: the turn, the item's turns left, for a unit how many
    of its type we had once the order took and, for policies, the cards slotted then."""
    e = c.expect
    base: dict = {"turn": after.get("turn")}
    if "policies" in e and isinstance(after.get("policy_slots"), list):
        base["slots"] = [s.get("policy") for s in after["policy_slots"]]
    if "research" in e:
        base["turns_left"] = (after.get("research") or {}).get("turns_left")
    elif "civic" in e:
        base["turns_left"] = (after.get("civic") or {}).get("turns_left")
    elif "producing" in e:
        city = _city(after, e["city"]) or {}
        base["turns_left"] = city.get("turns_left")
        base["count"] = ((after.get("units") or {}).get("by_type") or {}).get(e["producing"], 0)
        # other cities of ours building the same unit: their units raise the same count
        base["others"] = sum(1 for x in after.get("cities") or [] if x is not city and x.get("producing") == e["producing"])
    return base


def held_outcome(c: Checked, base: dict, now: dict, window: int) -> tuple[str, str | None]:
    """Where a followed order stands in snapshot `now` (ruling 12): ('open', None) while undecided,
    else ('completed' | 'held' | 'overridden' | 'invalidated' | 'unknown', the type key now in its
    place or None).
    - completed: a tech or civic left the options; a unit's count rose; a building or district
      appeared in the city.
    - held: still current when its window (`order_window`) ends.
    - overridden: the AI switched while our item was still available (production: before our
      item's turns had elapsed, else it may have completed and been lost: unknown).
    - invalidated: the item is no longer available (Slinger after Archery; an obsolete policy).
    - unknown: the snapshot cannot tell (no options, the city gone)."""
    e = c.expect
    elapsed = (now.get("turn") or 0) - (base.get("turn") or 0)
    current = ("held", None) if elapsed >= window else ("open", None)
    options = now.get("options")
    for kind, fld, offered in (("research", "tech", "techs"), ("civic", "civic", "civics")):
        if kind in e:
            key, cur = e[kind], (now.get(kind) or {}).get(fld)
            if cur == key:
                return current
            listed = (options or {}).get(offered)
            if listed is None:
                return "unknown", cur
            return ("completed", None) if key not in listed else ("overridden", cur)
    if "policies" in e:
        slotted = {s.get("policy") for s in now.get("policy_slots") or []}
        missing = [k for k in e["policies"] if k not in slotted]
        if not missing:
            return current
        unlocked = (options or {}).get("policies")
        if unlocked is None:
            return "unknown", None                          # an obsolete card swapped out, or the AI's choice
        if not any(k in unlocked for k in missing):
            return "invalidated", None
        # the AI's cards are those slotted since the order took (base "slots"; a row followed from
        # before it was kept names every other slotted card)
        instead = sorted(k for k in slotted if k and k not in e["policies"] and k not in (base.get("slots") or []))
        return "overridden", ", ".join(instead) or None
    if "producing" in e:
        key = e["producing"]
        city = _city(now, e["city"])
        if city is None:
            return "unknown", None                          # lost or renamed
        producing, can = city.get("producing"), city.get("can_build")
        gain = ((now.get("units") or {}).get("by_type") or {}).get(key, 0) - (base.get("count") or 0)
        needed = 1 + (base.get("others") or 0)             # every other city building it may add one too
        if key.startswith("UNIT_") and gain >= needed and (producing != key or elapsed >= (base.get("turns_left") or 0)):
            return "completed", None                        # (built, and the AI may have queued another)
        if key.startswith("UNIT_") and 0 < gain < needed and producing != key:
            return "unknown", producing                     # the new unit may be another city's
        if key.startswith("BUILDING_") and key in (city.get("buildings") or []):
            return "completed", None
        if key.startswith("DISTRICT_") and key in (city.get("districts") or []):     # no longer "(building)"
            return "completed", None
        if producing == key:
            return current
        if key.startswith("PROJECT_"):
            return "overridden", producing                  # repeatable: held or overridden only
        if key.startswith("BUILDING_") and city.get("buildings") is None and can is not None and key not in can:
            return "completed", None                        # an older snapshot: built, so no longer offered
        if can is not None and key not in can:
            return "invalidated", producing
        if elapsed < (base.get("turns_left") or 0):
            return "overridden", producing
        return "unknown", producing                         # switched after its turns: completed and lost, or replaced
    return "unknown", None


def order_record(rows: list[dict], now_turn: int, spec) -> dict[str, dict]:
    """`record.order_record` with Civ VI's keys in their fixed order (RECORD_KEYS). Purchase keys are
    counts only (ruling 9): a purchase read back as done is completed by construction."""
    rec = _order_record(rows, now_turn, spec, key_order=RECORD_KEYS)
    for key, r in rec.items():
        if key.startswith("purchase "):
            r.update(rate=None, weak=False, counts_only=True)
    return rec


_DESCRIBED = re.compile(r"^(?P<kind>research|civic|production|purchase) (?P<id>\S*)(?: in (?P<city>.+?))?"
                        r"(?: with (?P<currency>gold|faith))?$")


def backfill_rows(decisions: list[dict]) -> list[dict]:
    """order_outcome rows recovered from decision traces written before the order record (ruling 13):
    apply-time outcomes only. A purchase that took completed at once; refused, lost (no reply) and
    unknown orders keep their outcome; any other order that took is skipped, since whether it held
    or the AI replaced it exists only as prose. `decisions`: [{"date": "T43", "orders": trace
    orders}] oldest first; traces whose orders carry `kind` (written by the record) are skipped.
    Production rows get the situation "unknown" (the snapshot before the order is not kept)."""
    rows = []
    for d in decisions:
        date = str(d.get("date") or "")
        turn = int(date[1:]) if date[:1] == "T" and date[1:].isdigit() else None
        for o in d.get("orders") or []:
            if "kind" in o:
                continue
            text, outcome = str(o.get("order") or ""), str(o.get("outcome") or "")
            if text.startswith("policies "):
                kind, oid, city, currency = "policies", text.removeprefix("policies "), "", None
            else:
                m = _DESCRIBED.match(text)
                if not m:
                    continue
                kind, oid, city, currency = m["kind"], m["id"], m["city"] or "", m["currency"]
            if outcome == "stuck":
                if kind != "purchase":
                    continue
                result = "completed"
            elif outcome.startswith(f"{UNKNOWN}: no reply"):
                result = "lost"
            elif outcome.startswith(UNKNOWN):
                result = "unknown"
            else:
                result = "refused"
            situation = "unknown" if kind == "production" else None
            order = {"kind": kind, "id": oid, "currency": currency or "gold"}
            rows.append({"order_kind": kind, "key": record_key(order, situation), "item_kind": None, "id": oid,
                         "city": city, "currency": currency if kind == "purchase" else None, "situation": situation,
                         "ordered": date, "top3_hit": None, "result": result, "by": None, "turns": 0, "date": date,
                         "turn": turn, "detail": outcome[:300], "backfilled": True})
    return rows


def idle_counts(seen: dict[int, list[str]], now_turn: int, window: int) -> dict[str, tuple[int, int]]:
    """Per kind (research, civic): at how many of the snapshots seen in the last `window` turns
    nothing was in progress, of how many."""
    turns = [t for t in seen if now_turn - window < t <= now_turn]
    return {k: (sum(1 for t in turns if k in seen[t]), len(turns)) for k in ("research", "civic")}


def top3_hits(rows: list[dict]) -> tuple[int, int]:
    """Of the AI's replacements of our production orders whose city's top 3 was known at order time,
    how many were in that top 3 (ruling 29): (hits, known)."""
    known = [r for r in rows if r.get("result") == "overridden" and r.get("top3_hit") is not None]
    return sum(1 for r in known if r["top3_hit"]), len(known)


def order_record_text(rec: dict[str, dict], idle: dict[str, tuple[int, int]] | None = None,
                      window: int = 30, top3: tuple[int, int] | None = None, *,
                      purchases: dict[str, dict] | None = None) -> str:
    """One line per key for the decision prompt and the Strategist, e.g. `- production replace: 5
    judged; 2 completed, 3 replaced by the AI (last: unit:slinger → unit:trader in Chengdu, T41);
    held 40% — does not stick here`; `top3` (`top3_hits`) adds how often the AI's replacement was in
    the city's own top 3. Purchases show as counts by item class (`purchase_counts`, ruling 9)
    instead of their keys' lines."""
    lines = []
    for key, r in rec.items():
        if key.startswith("purchase "):
            continue
        parts = [f"{r['completed']} completed"] if r["completed"] else []
        if r["held"]:
            parts.append(f"{r['held']} held through their window")
        if r["overridden"]:
            last = r.get("last_override") or {}
            where = f" in {last['city']}" if last.get("city") else ""
            parts.append(f"{r['overridden']} replaced by the AI"
                         + (f" (last: {last.get('id')} → {last.get('by') or 'nothing'}{where}, {last.get('date')})"
                            if last else ""))
        if r.get("took"):
            parts.append(f"{r['took']} took")
        if r.get("did_not_take"):
            parts.append(f"{r['did_not_take']} did not take")
        line = f"- {key}: {r['judged']} judged" + (f"; {', '.join(parts)}" if parts else "")
        other = ", ".join(f"{n} {res}" for res, n in r["excluded"].items() if n)
        if other:
            line += f" (not judged: {other})"
        if r["rate"] is not None:
            line += f"; held {r['rate']:.0%}" + (" — does not stick here" if r["weak"] else "")
        elif r["judged"]:
            line += f" (a rate needs {r['min_samples']})"
        lines.append(line)
    block = purchase_counts_text(purchases, window)
    if block:
        lines.append(block)
    for kind, (n, of) in (idle or {}).items():
        if n:
            lines.append(f"- {kind} idle at {n} of {of} snapshots in the last {window} turns")
    if top3 and top3[1]:
        lines.append(f"- the AI's replacement was in the city's own top 3 builds (at order time) {top3[0]} of "
                     f"{top3[1]} times")
    return "\n".join(lines)


# ---- the last stand (docs/design/2026-09-27-civ6-levers-design.md, rulings 22-27) ---------------
#
# A city about to fall gets scripted actions before the AI plays the turn: a city strike, ranged
# attacks, the retreat of hurt units, then pins. Off by default (PILOT_LAST_STAND); each action is
# one call, read back in GameCore before the next.

FALL_CAPTURE_ADJACENT = 1     # units next to the city that can take it: one is enough
FALL_GARRISON_SHARE = 0.5     # worn down: the garrison at or below this share of its hit points
FALL_BARE_RANGE = 2           # no garrison and no walls left: an enemy this close is enough


def enemy_within(city: dict, tiles: int) -> bool:
    """An enemy listed within `tiles` of the city (the snapshot lists the nearest few), or one next to
    it that can take it."""
    return (city.get("capture_adjacent") or 0) >= 1 or any(
        isinstance(e.get("dist"), (int, float)) and e["dist"] <= tiles for e in city.get("enemies") or [])


def about_to_fall(city: dict) -> bool:
    """A city the next enemy turn can take (ruling 22): a unit that can capture it stands next to
    it (the library counts melee, cavalry and any unit the game lets capture that is not ranged or
    siege by class, such as the Giant Death Robot; postmortem-fixes ruling 26), no walls stand, and the
    garrison is worn down to half or one attack from each enemy in range would take what is left
    (`incoming`); or nothing is left: garrison 0 and walls 0 with an enemy within 2 tiles (Beijing at
    T545 fell that way with no capturer next to it). Without the ruling-11 fields: False. Beijing at
    T61 (200 of 200, two capturers adjacent) is not falling."""
    d = city.get("defense") or {}
    hp, top, walls = d.get("garrison_hp"), d.get("garrison_max"), d.get("walls_hp")
    if not all(isinstance(v, (int, float)) for v in (hp, top, walls)) or not top:
        return False
    if hp <= 0 and walls <= 0 and enemy_within(city, FALL_BARE_RANGE):
        return True
    if (city.get("capture_adjacent") or 0) < FALL_CAPTURE_ADJACENT or walls > 0:
        return False
    incoming = city.get("incoming")
    return hp <= FALL_GARRISON_SHARE * top or (isinstance(incoming, (int, float)) and incoming >= hp)


def _ls_unit(state: dict, owner, uid) -> dict | None:
    return next((u for u in state.get("units") or [] if u.get("owner") == owner and u.get("id") == uid), None)


def _actor_id(reply: dict) -> int | None:
    kind, _, uid = str(reply.get("actor") or "").partition(":")
    return int(uid) if kind == "unit" and uid.isdigit() else None


def stand_verdict(reply: dict | None, before: dict, after: dict | None) -> tuple[str, str]:
    """Whether a last-stand action took (ruling 26), from the GameCore reads before and after it:
    ('took' | 'did_not_take' | 'unknown', why). A strike took when its target's damage rose or the
    target is gone; a ranged attack also needs the attacker's attacks or moves to drop; a retreat,
    the unit on its destination. `reply` None (the reply was lost): took when anything changed.
    `after` None (no read-back): unknown."""
    if after is None:
        return "unknown", "no read-back"
    me = before.get("me", 0)
    if reply is None:
        key = lambda u: (u.get("owner"), u.get("id"))
        now = {key(u): u for u in after.get("units") or []}
        changed = [u for u in before.get("units") or [] if key(u) not in now or any(
            now[key(u)].get(f) != u.get(f) for f in ("x", "y", "damage", "moves", "attacks"))]
        return ("took", f"{len(changed)} unit(s) changed") if changed else ("did_not_take", "nothing changed")
    uid = _actor_id(reply)
    if reply.get("action") == "retreat":
        u, to = _ls_unit(after, me, uid), reply.get("to") or {}
        if u and (u.get("x"), u.get("y")) == (to.get("x"), to.get("y")):
            return "took", f"on {to.get('x')},{to.get('y')}"
        return "did_not_take", "not on its destination" + (f" (at {u.get('x')},{u.get('y')})" if u else " (gone)")
    t = reply.get("target") or {}
    was, now = _ls_unit(before, t.get("owner"), t.get("id")), _ls_unit(after, t.get("owner"), t.get("id"))
    hit = was is not None and (now is None or (now.get("damage") or 0) > (was.get("damage") or 0))
    what = ("killed" if now is None else f"{(now.get('damage') or 0) - (was.get('damage') or 0)} damage") if hit \
        else "no damage"
    predicted = f" (predicted {reply.get('predicted_damage')})" if reply.get("predicted_damage") is not None else ""
    if reply.get("action") == "ranged_attack":
        a0, a1 = _ls_unit(before, me, uid), _ls_unit(after, me, uid)
        spent = a0 is not None and a1 is not None and (
            (a1.get("attacks") or 0) < (a0.get("attacks") or 0) or (a1.get("moves") or 0) < (a0.get("moves") or 0))
        if not spent:
            return "did_not_take", f"the attacker kept its attack; target: {what}{predicted}"
    return ("took" if hit else "did_not_take"), f"target: {what}{predicted}"


# ---- the AI's intent (docs/design/2026-09-27-civ6-levers-design.md, ruling 29) ------------------


def ai_strategy_states(rows: list) -> dict[str, dict]:
    """Each strategy's state from the AI's log rows ([turn, strategy, status], oldest first): its
    last status, the turn its current run started (`since`) and, once stopped, the turn it stopped."""
    out: dict[str, dict] = {}
    for turn, name, status in rows:
        s = out.setdefault(str(name), {"status": None, "since": None, "stopped": None})
        if status == "Following":
            if s["status"] != "Following":
                s["since"], s["stopped"] = turn, None
            s["status"] = "Following"
        elif status == "Stopped":
            s["status"], s["stopped"] = "Stopped", turn
    return out


def _strategy_name(key: str) -> str:
    return key.removeprefix("VICTORY_STRATEGY_").removeprefix("STRATEGY_").lower().replace("_", " ")


def ai_plan_text(s: dict, index: CorpusIndex, strategies: dict[str, dict] | None = None, window: int = 30) -> str:
    """The AI's own plan (ruling 29): each city's top 3 builds and our player's strategies that run,
    or stopped within the last `window` turns. The AI's scores are on their own scale, and how well
    they predict what it builds is measured by the order record (`top3_hit`)."""
    cid, now = index.cid, s.get("turn") or 0
    # the era strategies (STRATEGY_<ERA>_CHANGES) keep "Following" once started: only the latest says anything
    eras = [(st["since"] or 0, k) for k, st in (strategies or {}).items() if k.endswith("_CHANGES") and st["status"] == "Following"]
    stale = {k for _, k in sorted(eras)[:-1]}
    cities = [f"{c.get('name')} → " + ", ".join(cid(r.get("type")) for r in c["recommend"])
              for c in s.get("cities") or [] if c.get("recommend")]
    shown = []
    for key, st in sorted((strategies or {}).items(), key=lambda kv: (not kv[0].startswith("VICTORY_"), kv[0])):
        if key in stale:
            continue
        if st["status"] == "Following":
            shown.append(f"{_strategy_name(key)} (since T{st['since']})" if st["since"] is not None else _strategy_name(key))
        elif st["status"] == "Stopped" and st["stopped"] is not None and now - st["stopped"] <= window:
            since = f"since T{st['since']}, " if st["since"] is not None else ""
            shown.append(f"{_strategy_name(key)} ({since}stopped T{st['stopped']})")
    parts = ["; ".join(cities)] if cities else []
    if shown:
        parts.append("strategies: " + ", ".join(shown))
    return ("The AI's own plan: " + "; ".join(parts) + ".") if parts else ""


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
            "idle": [k for k in ("research", "civic") if not s.get(k)],      # nothing in progress (ruling 16)
            "peers": peers, "peer_count": len(majors),
            **relative_military(s),       # ours / the met majors' median and / the strongest non-ally (ruling 18)
            "neighbours": [{"name": m.get("civ"), "military": m.get("military"), "score": m.get("score"),
                            "cities": m.get("cities"), "at_war": m.get("at_war"),
                            **({"allied": m["allied"]} if "allied" in m else {})} for m in majors]}


# ---- who declared a war (postmortem-fixes design, ruling 24) -------------------------------------------

DIPLOMACY_LOG = "DiplomacySummary.csv"
_TEAM_RE = re.compile(r"^Team (\d+)$")


def new_wars(before: dict, now: dict) -> list[dict]:
    old = {w.get("id") for w in before.get("wars") or []}
    return [w for w in now.get("wars") or [] if w.get("id") not in old]


def war_declarations(lines: list[str]) -> list[dict]:
    """The war declarations in DiplomacySummary.csv lines: [{"turn", "player" (who declared), "team"
    (on whom), "kind" (the casus belli: Surprise, Formal, Defensive Pact...)}]. The columns are "Game
    Turn, Initiator, Recipient, Action, Details, Mayhem, Visibility" and the rows look like "539, 5,
    Team 0, Individual Declaring War on Team START, Surprise, 2950.5" (read offline for the
    post-mortem; the live layout is unverified): the casus belli is Details, never the Mayhem number
    after it. A row that does not parse is skipped, so a changed layout names nobody, never a wrong
    declarer. A team is taken as its player's id."""
    out = []
    for line in lines:
        f = [x.strip() for x in str(line).split(",")]
        if len(f) < 5 or not f[0].isdigit() or not f[1].isdigit() or "Declaring War" not in f[3]:
            continue
        team = _TEAM_RE.match(f[2])
        if team:
            out.append({"turn": int(f[0]), "player": int(f[1]), "team": int(team.group(1)), "kind": f[4]})
    return out


def _war_kind(kind: str) -> str:
    k = kind.strip().lower()
    return {"surprise": "a surprise war", "formal": "a formal war"}.get(k, f"war ({kind.strip()})")


def war_text(war: dict, me, declarations: list[dict], majors: list[dict] | None = None) -> str:
    """The "new war" reason naming who declared (ruling 24), from the declarations of this stretch:
    "new war: CIVILIZATION_AUSTRALIA declared a surprise war on us", "new war: our AI declared war on
    CIVILIZATION_AUSTRALIA (a surprise war)", "new war: CIVILIZATION_MALI joined through its defensive
    pact"; a major that joined the enemy's side against it by its defensive pact is named after it.
    With no declaration found: "(who declared is not known)"; it never guesses. China's own autoplay
    AI declared the T121 war, and the model recorded it as Australia's."""
    civ, enemy = war.get("civ"), war.get("id")
    name = {m.get("id"): m.get("civ") for m in majors or []}
    theirs = [d for d in declarations if d["player"] == enemy and d["team"] == me]
    ours = [d for d in declarations if d["player"] == me and d["team"] == enemy]
    if theirs:
        kind = theirs[-1]["kind"]
        text = (f"new war: {civ} joined through its defensive pact" if "defensive pact" in kind.lower()
                else f"new war: {civ} declared {_war_kind(kind)} on us")
    elif ours:
        text = f"new war: our AI declared war on {civ} ({_war_kind(ours[-1]['kind'])})"
    else:
        return f"new war: at war with {civ} (who declared is not known)"
    joined = [name.get(d["player"], f"player {d['player']}") for d in declarations
              if d["team"] == enemy and d["player"] not in (me, enemy) and "defensive pact" in d["kind"].lower()]
    if joined:
        text += " (" + ", ".join(f"{j} joined against it through its defensive pact" for j in dict.fromkeys(joined)) + ")"
    return text


def urgent_changes(before: dict, now: dict, gold_reserve: int = 0, wonders: frozenset[str] | set[str] = frozenset(),
                   declared: dict | None = None) -> list[str]:
    """Reasons to stop autoplay and decide now (ruling 4). `wonders`: the wonders' type keys;
    `declared`: each new war's reason by the enemy's player id (`war_text`), else who declared is not
    known (postmortem-fixes ruling 24)."""
    out = []
    for w in new_wars(before, now):
        out.append((declared or {}).get(w.get("id")) or f"new war: at war with {w.get('civ')} (who declared is not known)")
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
        if about_to_fall(c) and not about_to_fall(prev):         # ruling 22: the model decides first
            d = c.get("defense") or {}
            near = (f"{c.get('capture_adjacent')} unit(s) next to it that can take it" if c.get("capture_adjacent")
                    else f"an enemy within {FALL_BARE_RANGE} tiles")
            out.append(f"city falling: {c['name']} (garrison {d.get('garrison_hp')}/{d.get('garrison_max')}, no walls, "
                       f"{near}" + (f", about {c['incoming']} damage incoming" if c.get("incoming") else "") + ")")
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
    g0, g1 = (before.get("yields") or {}).get("gold"), (now.get("yields") or {}).get("gold")
    if isinstance(g0, (int, float)) and isinstance(g1, (int, float)) and g1 < 0 <= g0:
        # postmortem-fixes ruling 12: -6.8 to -12.6 a turn over T289-T304 while the stance said +12.4
        out.append(f"gold per turn negative: {g1:.1f}")
    return out


def standing_danger(snapshot: dict, index: CorpusIndex, limits, defender_buys: dict[str, int] | None = None) -> str:
    """Ruling 14 of the postmortem-fixes design: while at war with a major, a hand-back decides when a
    city is in danger, has no unit on its tile and its `defence_prices` list a defender the game allows
    within the purchase cap (faith first, then the cheaper), and its defender cooldown has run out:
    urgent checks fire only on a change, so T559-T562, T571-T574 and T576-T582 had no decision while
    cities stayed in danger. The most worn-down such city, e.g. "city still in danger: Longxi (walls
    0/400, garrison 80/200; unit:modern_at 1160 faith allowed)"; "" when none (as in T576-T582, when
    nothing could be bought)."""
    if limits is None or not any(w.get("major", True) for w in snapshot.get("wars") or []):
        return ""
    turn, wait = snapshot.get("turn"), limits.defence_cooldown_turns
    found = []
    for c in snapshot.get("cities") or []:
        if not (in_danger(c) and "garrison" in c and not c.get("garrison")):
            continue
        last = (defender_buys or {}).get(str(c.get("name", "")).lower())
        if wait and isinstance(last, int) and isinstance(turn, int) and turn - last < wait:
            continue
        offers = sorted(((cur != "faith", p[cur], cur, p) for p in defender_entries(c, index, limits)
                         for cur in ("faith", "gold")
                         if p.get(f"{cur}_allowed") and isinstance(p.get(cur), (int, float))
                         and p[cur] <= purchase_cap(snapshot, c, cur, limits, defender=True)), key=lambda x: x[:2])
        if offers:
            d = c.get("defense") or {}
            share = (d.get("garrison_hp") or 0) / (d.get("garrison_max") or 1)
            found.append((share, c, offers[0]))
    if not found:
        return ""
    _, c, (_f, cost, cur, p) = min(found, key=lambda x: x[0])
    d = c.get("defense") or {}
    return (f"city still in danger: {c.get('name')} (walls {d.get('walls_hp')}/{d.get('walls_max')}, garrison "
            f"{d.get('garrison_hp')}/{d.get('garrison_max')}; {index.cid(p.get('unit'))} {_n(cost)} {cur} allowed)")


def _n(v) -> str:
    if isinstance(v, float):
        return f"{v:.0f}" if abs(v) >= 100 or v.is_integer() else f"{v:.1f}"
    return str(v)


def _danger_text(x: dict, cid, index: CorpusIndex | None = None, limits=None, snapshot: dict | None = None) -> str:
    """A city in danger (ruling 17): what can take it, its defence, the unit on its tile and what a
    defender costs (ruling 19), with why the game refuses one (postmortem-fixes ruling 7); without
    walls it cannot strike (ruling 21)."""
    d = x.get("defense") or {}
    parts = [f"{'ABOUT TO FALL' if about_to_fall(x) else 'IN DANGER'}: {x.get('enemies_near', 0)} enemy units within 3 tiles"
             + (f", {x['capture_adjacent']} next to it that can take it" if x.get("capture_adjacent") else "")
             + (", under siege" if x.get("under_siege") else "")]
    if d:
        parts.append(f"garrison {d.get('garrison_hp')}/{d.get('garrison_max')}, walls {d.get('walls_hp')}/{d.get('walls_max')}"
                     + (" (no walls: this city cannot strike; walls come from production)" if not d.get("walls_max") else ""))
    if isinstance(x.get("incoming"), (int, float)) and x["incoming"]:
        parts.append(f"one attack from each enemy in range: about {x['incoming']} damage")
    if "garrison" in x:
        parts.append(f"on its tile: {cid(x['garrison']) if x.get('garrison') else 'no unit'}")
    prices = [p for p in x.get("defence_prices") or []
              if limits is None or index is None or is_defender(cid(p.get("unit")), index, limits)]
    if prices and index is not None:
        parts.append(defenders_text(x, prices, index, snapshot or {}))
    return "; ".join(parts)


def _tile_text(x: dict, cid, index: CorpusIndex, limits, snapshot: dict) -> str:
    """A city not in danger under military weakness: the unit on its tile, or what defender it can buy
    (ruling 7); a unit on the tile blocks any other, so its prices are left out."""
    if x.get("garrison"):
        return f"on its tile: {cid(x['garrison'])}"
    prices = defender_entries(x, index, limits)
    return "on its tile: no unit" + (f"; {defenders_text(x, prices, index, snapshot)}" if prices else "")


def defenders_text(city: dict, prices: list[dict], index: CorpusIndex, snapshot: dict) -> str:
    """What the city can buy for its defence (ruling 7): each listed defender's prices, a refused one
    with why; a city with nothing to buy says so, e.g. "no defender can be bought now (unit:modern_at:
    a unit is on the tile; unit:infantry: needs 1 Oil, have 0)"."""
    cid = index.cid

    def price(p, cur):
        why = refusal(p, cur, snapshot, index)
        return f"{_n(p.get(cur))} {cur}" + (f" (refused: {why[1]})" if why else "")
    if not any(p.get("gold_allowed") or p.get("faith_allowed") for p in prices):
        reasons = []
        for p in prices:
            texts = list(dict.fromkeys(w[1] for cur in ("gold", "faith") if (w := refusal(p, cur, snapshot, index))))
            reasons.append(f"{cid(p.get('unit'))}: {' / '.join(texts)}")
        return f"no defender can be bought now ({'; '.join(reasons)})"
    return "defenders to buy: " + ", ".join(f"{cid(p.get('unit'))} {price(p, 'gold')} / {price(p, 'faith')}" for p in prices)


def _religion_text(s: dict, cid, limits) -> str:
    rel = s.get("religion")
    if not isinstance(rel, dict):
        return ("Pantheon and religion: not in this snapshot (the pantheon reserve is off)."
                if limits is not None and limits.pantheon_reserve else "")
    why = faith_reserve_now(s, limits)[1] if limits is not None else ""
    pantheon = (cid(rel["pantheon"]) if rel.get("pantheon") else
                f"none (founding one costs {rel.get('pantheon_cost')} faith" + (f"; purchases {why}" if why else "") + ")")
    text = f"Pantheon: {pantheon}. Religion: {rel.get('religion') or 'none'}"
    if rel.get("religions_max"):
        text += f" ({rel.get('religions_founded')} of {rel['religions_max']} religions founded)"
    if rel.get("prophet_cost"):
        text += f"; Great Prophet points {rel.get('prophet_points')}/{rel['prophet_cost']}"
    return text + "."


# ---- the diplomacy auto-reply (issues.md T240, T342) --------------------------------------------
# corpora/civ6/lua/harness.lua answers an AI leader's statement during autoplay from its own table and
# logs the last 20 in the snapshot's `diplomacy` ({"handler": bool, "log": [...]}): each entry has
# n, turn, from, civ, session, kind, sub, and once answered reply (POSITIVE, EXIT or REFUSE), why and
# at (the turn answered); `late` when it waited for autoplay, `err` when the game's call failed
# (`closed` when Goodbye then went through instead). why 'sweep' is the Goodbye the library sent when
# autoplay started to a session its answer had left open (no follow-up closed it).

DIPLOMACY_REPLIES = {"POSITIVE": "the conciliatory reply (a promise)", "EXIT": "Goodbye", "REFUSE": "refused"}
DIPLOMACY_WHY = {"unknown": "an unknown statement", "guard": "the promise was not offered safely by the game's data"}
DIPLOMACY_SHOWN = 6            # log entries in the briefing line...
DIPLOMACY_RECENT = 10          # ...from the last this many turns (one still waiting is always shown)
DIPLOMACY_RECORD = 8           # the campaign's last answers in the order record (Strategist, published)
DIPLOMACY_RECORD_HEADING = (f"Diplomacy answered for us in this campaign (the harness's auto-reply during autoplay; "
                            f"the last {DIPLOMACY_RECORD}):")
DIPLOMACY_RECORD_KEYS = ("turn", "at", "civ", "from", "statement", "subtype", "reply", "why", "text")


def diplomacy_key(e: dict) -> str:
    """One answer's identity across snapshots and restarts (the library's counter restarts on a load)."""
    return f"{e.get('turn')}:{e.get('from')}:{e.get('session')}:{e.get('n')}"


def diplomacy_answered(s: dict) -> list[dict]:
    """The snapshot's logged statements that were answered, oldest first."""
    d = s.get("diplomacy")
    log = d.get("log") if isinstance(d, dict) else None
    return [e for e in log or [] if isinstance(e, dict) and e.get("reply")]


def diplomacy_reply_text(e: dict) -> str:
    """What was answered, or why nothing was: "Goodbye (at T14, when autoplay started)"."""
    if not e.get("reply"):
        return {"gone": "closed before an answer",
                "no session": "not answered (its session could not be read)"}.get(e.get("why"),
                                                                                "waiting for the next autoplay")
    notes = [DIPLOMACY_WHY[e["why"]]] if e.get("why") in DIPLOMACY_WHY else []
    if e.get("why") == "sweep":
        notes = [f"the session our answer left open, closed at T{e.get('at')} when autoplay started"]
    if e.get("late"):
        notes.append(f"at T{e.get('at')}, when autoplay started")
    if e.get("err"):
        notes.append(f"failed: {e['err']}"[:120])
    if e.get("closed"):
        notes.append("Goodbye sent instead")
    text = DIPLOMACY_REPLIES.get(e["reply"], str(e["reply"]))
    return text + (f" ({'; '.join(notes)})" if notes else "")


def _statement_words(kind, sub) -> str:
    """`warning too many troops near me (positive follow-up)`."""
    sub = str(sub or "NONE")
    return str(kind or "unnamed statement").lower().replace("_", " ") \
        + (f" ({sub.lower().replace('_', ' ')} follow-up)" if sub != "NONE" else "")


def _statement_text(e: dict, cid) -> str:
    who = cid(e.get("civ")) if e.get("civ") else "player " + str(e.get("from"))
    return f"T{e.get('turn')} {who} {_statement_words(e.get('kind'), e.get('sub'))}"


def diplomacy_record_text(rows: list[dict]) -> str:
    """The order record's diplomacy lines from the campaign's `diplomacy_reply` events (oldest first):
    the last DIPLOMACY_RECORD, one per answer, e.g. `- T13 civ:australia warning too many troops near
    me: the conciliatory reply (a promise)`; "" when none."""
    return "\n".join(f"- T{r.get('turn')} {r.get('civ') or 'player ' + str(r.get('from'))} "
                     f"{_statement_words(r.get('statement'), r.get('subtype'))}: {r.get('text') or r.get('reply')}"
                     for r in rows[-DIPLOMACY_RECORD:])


def diplomacy_text(s: dict, cid) -> str:
    """The briefing's diplomacy line: the last statements the library answered (or holds) for us."""
    d = s.get("diplomacy")
    if not isinstance(d, dict):
        return ""                                  # a library without the auto-reply
    if not d.get("handler"):
        return ("Diplomacy: the auto-reply is not installed in this game, so the leader screen is kept: an AI "
                "leader's statement holds the autoplay turn until a human answers it on screen.")
    now = s.get("turn") or 0
    log = [e for e in d.get("log") or [] if isinstance(e, dict)
           and (e.get("why") == "waiting" or (e.get("at") or e.get("turn") or 0) >= now - DIPLOMACY_RECENT)]
    if not log:
        return ""
    return ("Diplomacy answered for us while the AI played (never war, no deal accepted; a promise to a warning, "
            "Goodbye to proposals): " + "; ".join(f"{_statement_text(e, cid)}: {diplomacy_reply_text(e)}"
                                                  for e in log[-DIPLOMACY_SHOWN:]) + ".")


def briefing_text(s: dict, index: CorpusIndex, gold_reserve: int = 0, limits=None,
                  strategies: dict[str, dict] | None = None) -> str:
    """The snapshot as a compact briefing; every item is named by its corpus id. With the purchase
    `limits`, the reserves are today's (the gold reserve grows with a deficit; faith keeps the
    pantheon's price) and the religion line says what faith is kept for. `strategies`: the AI's own
    (`ai_strategy_states`), shown with each city's top 3 builds."""
    cid = index.cid
    y = s.get("yields") or {}
    if limits is not None:
        gold_reserve = gold_reserve_now(s, limits)
    faith_kept = faith_reserve_now(s, limits)[0] if limits is not None else 0
    lines = [(f"Turn {s.get('turn')}, {cid(s.get('era'))} (era score {s.get('era_score')}; dark age below "
              f"{s.get('dark_age_threshold')}, golden age from {s.get('golden_age_threshold')}). "
              f"{s.get('civ_name')} ({cid(s.get('civ'))}), led by {s.get('leader_name')} ({cid(s.get('leader'))})."),
             "Per turn: " + ", ".join(f"{k} {_n(y.get(k))}" for k in ("science", "culture", "faith", "gold", "production", "food")
                                      if y.get(k) is not None)
             + f". Treasury {_n(s.get('gold'))} gold (reserve {gold_reserve}), {_n(s.get('faith'))} faith"
             + (f" (reserve {faith_kept})" if faith_kept else "") + ".",
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
    # under military weakness a defender may be bought in any city (postmortem-fixes rulings 2 and 7), so
    # every city says what the game sells it now, not only a city in danger
    weak = bool(weakness(s, limits)) if limits is not None else False
    for x in cities:
        threat = []
        if (in_danger(x) or about_to_fall(x)) and has_defence_fields(x):
            threat = [_danger_text(x, cid, index, limits, s)]
        elif x.get("threatened"):
            threat = [f"THREATENED: {x.get('enemies_near', 0)} enemy units within 3 tiles"
                      + (", under siege" if x.get("under_siege") else "") + (", damaged" if x.get("damaged") else "")]
        if weak and not (in_danger(x) or about_to_fall(x)) and "garrison" in x:
            threat.append(_tile_text(x, cid, index, limits, s))
        dist = ", ".join(cid(d.split(" ")[0]) + (" (building)" if "(building)" in d else "") for d in x.get("districts") or [])
        lines.append(f"- {x.get('name')}{' (capital)' if x.get('capital') else ''}: pop {x.get('pop')}, "
                     f"builds {cid(x.get('producing')) if x.get('producing') else 'NOTHING'}"
                     + (f" ({x.get('turns_left')} turns)" if x.get("producing") else "")
                     + f", food {_n(x.get('food'))}, production {_n(x.get('production'))}, districts: {dist or 'none'}"
                     + (f", loyalty {x.get('loyalty')}" if (x.get("loyalty") or 100) < 100 else "")
                     + "".join(f"; {t}" for t in threat)
                     + (f". Can build: {', '.join(cid(k) for k in x.get('can_build') or [])}" if x.get("can_build") else ""))
    plan = ai_plan_text(s, index, strategies)
    if plan:
        lines.append(plan)
    u = s.get("units") or {}
    lines.append(f"Units {u.get('total', 0)}: " + ", ".join(f"{cid(k)} {v}" for k, v in sorted((u.get("by_type") or {}).items())) + ".")
    majors = s.get("majors") or []
    rel = relative_military(s)
    if majors and rel["military_vs_median"] is not None:
        mil = [m.get("military") for m in majors if isinstance(m.get("military"), (int, float))]
        lines.append(f"Military standing (peers are the {len(majors)} majors we have met): ours {_n(s.get('military'))} "
                     f"is {rel['military_vs_median']:g} x their median {_n(float(median(mil)))}"
                     + (f" and {rel['military_vs_strongest']:g} x the strongest that is not our ally"
                        if rel["military_vs_strongest"] is not None else "")
                     + f"; rank {1 + sum(1 for v in mil if v > s['military'])} of {len(majors) + 1}.")
    if limits is not None:
        weak = weakness_line(s, limits)
        if weak:
            lines.append(weak + " (defenders may spend down to the reserve in any city).")
    stock = s.get("resources")
    lines.append("Strategic stock: " + (", ".join(f"{k.removeprefix('RESOURCE_').replace('_', ' ').title()} {_n(v)}"
                                                  for k, v in stock.items()) if isinstance(stock, dict) else "unknown")
                 + " (units that need a resource we lack cannot be bought or built).")
    if majors:
        lines.append("Civilizations met: " + "; ".join(
            f"{cid(m.get('civ'))} score {m.get('score')}, military {m.get('military')}, cities {m.get('cities')}, "
            f"techs {m.get('techs')}{', AT WAR' if m.get('at_war') else ''}{', ALLIED' if m.get('allied') else ''}"
            for m in majors) + ".")
    else:
        lines.append("Civilizations met: none yet.")
    wars = s.get("wars") or []
    lines.append("Wars: " + (", ".join(cid(w.get("civ")) for w in wars) if wars else "none") + ".")
    diplomacy = diplomacy_text(s, cid)
    if diplomacy:
        lines.append(diplomacy)
    gp = s.get("great_people") or {}
    close = [f"{g.get('class', '').removeprefix('GREAT_PERSON_CLASS_').lower()} {g.get('ours')}/{g.get('cost')}"
             for g in gp.get("current") or [] if g.get("ours")]
    if close:
        lines.append("Great person points: " + ", ".join(close) + ".")
    religion = _religion_text(s, cid, limits)
    if religion:
        lines.append(religion)
    blockers = s.get("blockers_all") or ([s["blocker"]] if s.get("blocker") else [])
    if blockers:
        lines.append(f"End-turn blockers now: {', '.join(blockers)} (the AI clears most during autoplay; an idle research "
                     "or civic needs your order).")
    return "\n".join(lines)

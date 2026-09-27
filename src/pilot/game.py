"""Game access for the pilot: the Rust controller's MCP server over stdio, plus a direct
agent call for hovering. The fake implementation drives the tests."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .coords import IMAGE_H, IMAGE_W

TURN_LINE = re.compile(r"^Advanced (\d+) turn")


@dataclass
class ToolResult:
    text: str
    image: bytes | None = None
    is_error: bool = False


@dataclass
class TurnReport:
    """Outcome of an autopilot run."""
    advanced: int
    stop: str          # "dialog" | "blocked" | "processing" | "limit" | "error"
    text: str
    frame: bytes | None


class Game(Protocol):
    def run_turns(self, n: int) -> TurnReport: ...
    def screenshot(self) -> ToolResult: ...
    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> ToolResult: ...
    def drag(self, x1: int, y1: int, x2: int, y2: int) -> ToolResult: ...
    def key(self, combo: str) -> ToolResult: ...
    def hover(self, x: int, y: int) -> ToolResult: ...
    def corpus(self, tool: str, **args) -> str: ...
    def reload(self) -> None: ...
    def close(self) -> None: ...


def classify_report(text: str) -> str:
    t = text.lower()
    if "a dialog is up" in t or "dialog detected" in t:
        return "dialog"
    if "still processing" in t:
        return "processing"
    if "did not advance" in t or "blocking end-turn" in t or "stopped at turn" in t:
        return "blocked"
    if t.startswith("error"):
        return "error"
    return "limit"


class McpGame:
    """Synchronous JSON-RPC client for `game-controller mcp` (line-delimited over stdio)."""

    def __init__(self, controller: Path, corpus: Path, agent_url: str, cwd: Path, token: str | None = None,
                 title: str = "Galactic Civilizations"):
        self.cmd = [str(controller), "--corpus", str(corpus), "mcp"]
        self.env = {"GAME_AGENT_URL": agent_url, "PATH": "/usr/bin:/bin"}
        token = token or os.environ.get("GAME_AGENT_TOKEN", "").strip() or None   # the PC's own token first
        if token:
            self.env["GAME_AGENT_TOKEN"] = token
        if os.environ.get("GAME_RESOLUTION"):      # the host's screen size selects res/<W>x<H>.toml
            self.env["GAME_RESOLUTION"] = os.environ["GAME_RESOLUTION"]
        self.cwd = cwd
        self.agent_url = agent_url.rstrip("/")
        self.GAME_TITLE = title
        self.token = token or (cwd / ".agent_token").read_text().strip()
        self._lock = threading.Lock()
        self._id = 0
        self._proc: subprocess.Popen | None = None
        self._start()

    def _start(self) -> None:
        self._proc = subprocess.Popen(self.cmd, cwd=self.cwd, env=self.env, stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                 "clientInfo": {"name": "pilot", "version": "1"}})

    def _rpc(self, method: str, params: dict) -> dict:
        with self._lock:
            assert self._proc and self._proc.stdin and self._proc.stdout
            self._id += 1
            self._proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}) + "\n")
            self._proc.stdin.flush()
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    raise RuntimeError("game-controller MCP server exited")
                msg = json.loads(line)
                if msg.get("id") == self._id:
                    if "error" in msg:
                        raise RuntimeError(f"MCP error: {msg['error']}")
                    return msg.get("result") or {}

    def call(self, tool: str, **args) -> ToolResult:
        res = self._rpc("tools/call", {"name": tool, "arguments": args})
        text, image = [], None
        for block in res.get("content", []):
            if block.get("type") == "text":
                text.append(block["text"])
            elif block.get("type") == "image":
                image = base64.b64decode(block["data"])
        return ToolResult("\n".join(text), image, bool(res.get("isError")))

    GAME_TITLE = "Galactic Civilizations"

    def ensure_foreground(self) -> None:
        """Input must only ever reach the game: bring its window to the front first."""
        health = json.loads(self._http("GET", "/health"))
        fg = health.get("foreground", "")
        # Stellaris's window is titled exactly "Stellaris"; a substring would accept "Stellaris Wiki - Chrome"
        ok = fg.strip() == self.GAME_TITLE if self.GAME_TITLE == "Stellaris" else self.GAME_TITLE.lower() in fg.lower()
        if not ok:
            r = self.call("focus", title=self.GAME_TITLE)
            if r.is_error:
                raise RuntimeError(f"cannot focus the game window: {r.text}")

    def run_turns(self, n: int) -> TurnReport:
        self.ensure_foreground()
        r = self.call("autopilot_turns", turns=n)
        m = TURN_LINE.match(r.text)
        advanced = int(m.group(1)) if m else 0
        return TurnReport(advanced, classify_report(r.text) if not r.is_error else "error", r.text, r.image)

    def screenshot(self) -> ToolResult:
        return self.call("screenshot")

    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> ToolResult:
        self.ensure_foreground()
        self.call("screenshot")  # establish the 1568x882 view the coordinates refer to
        return self.call("click", x=x, y=y, button=button, count=count, wait=1.0)

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> ToolResult:
        self.ensure_foreground()
        self.call("screenshot")
        return self.call("drag", x1=x1, y1=y1, x2=x2, y2=y2, wait=1.0)

    def key(self, combo: str) -> ToolResult:
        self.ensure_foreground()
        return self.call("key", combo=combo)

    def hover(self, x: int, y: int) -> ToolResult:
        self.ensure_foreground()
        health = json.loads(self._http("GET", "/health"))
        sw, sh = health["screen"]
        self._http("POST", "/move", {"x": round(x * sw / IMAGE_W), "y": round(y * sh / IMAGE_H)})
        import time
        time.sleep(1.2)
        return self.call("screenshot")

    def _http(self, method: str, path: str, body: dict | None = None) -> bytes:
        req = urllib.request.Request(self.agent_url + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read()

    def corpus(self, tool: str, **args) -> str:
        return self.call(tool, **args).text

    # -- Stellaris (governor over the native AI; tools exist only with the Stellaris corpus) ------

    def briefing(self) -> dict:
        """Structured briefing of the newest autosave."""
        r = self.call("stellaris_briefing", json=True)
        if r.is_error:
            raise RuntimeError(r.text)
        return json.loads(r.text)

    def briefing_text(self) -> str:
        r = self.call("stellaris_briefing")
        if r.is_error:
            raise RuntimeError(r.text)
        return r.text

    def set_paused(self, paused: bool) -> str:
        self.ensure_foreground()
        return self._checked(self.call("stellaris_pause", paused=paused))

    def set_speed(self, speed: str) -> str:
        self.ensure_foreground()
        return self._checked(self.call("stellaris_speed", speed=speed))

    def directive(self, name: str) -> str:
        self.ensure_foreground()
        return self._checked(self.call("stellaris_directive", name=name))

    def log_tail(self, lines: int = 30) -> str:
        return self.call("stellaris_log", lines=lines).text

    def take_control(self) -> str:
        self.ensure_foreground()
        return self._checked(self.call("stellaris_take_control"))

    def pick_tech(self, prefer: list[str]) -> str:
        self.ensure_foreground()
        return self._checked(self.call("stellaris_pick_tech", prefer=prefer))

    def market_sync(self, orders: list[dict]) -> str:
        self.ensure_foreground()
        return self._checked(self.call("stellaris_market_sync", orders=orders))

    def posture(self, name: str, on: bool) -> str:
        """Set or clear one Governor Bridge posture (levers ruling 18; the war crisis's `war_crisis`)."""
        self.ensure_foreground()
        return self._checked(self.call("stellaris_posture", name=name, on=on))

    @staticmethod
    def _checked(r: ToolResult) -> str:
        if r.is_error:
            raise RuntimeError(r.text)
        return r.text

    def reload(self) -> None:
        """Restart the MCP server so newly learned screens are loaded."""
        self.close()
        self._start()

    def close(self) -> None:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None


class FakeGame:
    """Scripted game for tests: a queue of autopilot reports and a record of actions."""

    def __init__(self, reports: list[TurnReport], frame: bytes = b"\xff\xd8fakejpeg"):
        self.reports = list(reports)
        self.frame = frame
        self.actions: list[tuple] = []
        self.reloads = 0

    def run_turns(self, n: int) -> TurnReport:
        self.actions.append(("run_turns", n))
        if self.reports:
            return self.reports.pop(0)
        return TurnReport(n, "limit", f"Advanced {n} turn(s)", self.frame)

    def screenshot(self) -> ToolResult:
        return ToolResult("Screenshot 1568x882", self.frame)

    def click(self, x, y, button="left", count=1) -> ToolResult:
        self.actions.append(("click", x, y, button, count))
        return ToolResult(f"Clicked at image ({x}, {y})", self.frame)

    def drag(self, x1, y1, x2, y2) -> ToolResult:
        self.actions.append(("drag", x1, y1, x2, y2))
        return ToolResult("Dragged", self.frame)

    def key(self, combo) -> ToolResult:
        self.actions.append(("key", combo))
        return ToolResult(f"Pressed {combo}", self.frame)

    def hover(self, x, y) -> ToolResult:
        self.actions.append(("hover", x, y))
        return ToolResult("hovered", self.frame)

    def corpus(self, tool, **args) -> str:
        self.actions.append(("corpus", tool, args))
        if tool == "corpus_search":
            return "- `event:space_creature_migration` [event] Space Creature Migration — …"
        if tool == "corpus_get":
            return "**Space Creature Migration** (event)\n- choices: 1. Protect the creatures -> +3 relations"
        return ""

    def reload(self) -> None:
        self.reloads += 1

    def close(self) -> None:
        pass


class FakeStellaris:
    """Scripted Stellaris for tests: each `briefing()` call returns the next briefing (the last one
    repeats); directives, speed and pause changes are recorded."""

    def __init__(self, briefings: list[dict], advance_only_when_running: bool = False,
                 self_pause_after: int | None = None, *, reverts: dict[str, str] | None = None,
                 locked: tuple[str, ...] = (), market_sticky: bool = True, pick_reply: str | None = None,
                 trades: dict | str | None = None):
        self.briefings = list(briefings)
        self.actions: list[tuple] = []
        self.paused = True
        self.flags: list[str] = []
        # a directive sets its policies (corpora/stellaris/directives.toml) as the controller does:
        # `locked` ones are refused, and `reverts` {policy: option} is the AI's own change of one of
        # them, shown from the second save dated after the directive
        self.policies: dict[str, str] = {}
        self.policy_dates: dict[str, str] = {}
        self.reverts = dict(reverts or {})
        self.locked = set(locked)
        self._reverting: dict[str, tuple[str, set[str]]] = {}
        # like the game: the next saves hold the synced market orders (False: the sync did not take)
        self.market_sticky = market_sticky
        self.market_orders: list[dict] | None = None
        # last month's monthly trades in `market.trades_net` (levers ruling 10): a dict as given, or
        # "orders": what the synced orders traded (a buy +amount, a sell -amount); None: as scripted
        self.trades = trades
        self.pick_reply = pick_reply          # pick_tech's reply ("{tech}" = prefer[0]); None: "ok"
        # like the real game: while paused, reading the save again returns the same save
        self.advance_only_when_running = advance_only_when_running
        # after this many reads the game pauses itself once (an event window that autopauses), so
        # the save holds until something resumes it
        self.self_pause_after = self_pause_after
        self.self_paused = False
        self.reads = 0
        self._last: dict | None = None

    def _current(self) -> dict:
        self.reads += 1
        if self.self_paused and self._last is not None:
            b = dict(self._last)
        else:
            hold = len(self.briefings) == 1 or (self.advance_only_when_running and self.paused)
            b = dict(self.briefings[0] if hold else self.briefings.pop(0))
            self._last = b
        if self.self_pause_after is not None and self.reads == self.self_pause_after:
            self.paused = self.self_paused = True
        b = dict(b)
        self._revert(str(b.get("date") or ""))
        b["flags"] = list(self.flags)
        if self.policies:
            b["policies"] = {**(b.get("policies") or {}), **self.policies}
            b["policy_dates"] = {**(b.get("policy_dates") or {}), **self.policy_dates}
        if self.market_orders is not None:
            b["market_orders"] = [dict(o) for o in self.market_orders]
        if self.trades is not None:
            traded = dict(self.trades) if isinstance(self.trades, dict) else {
                o["resource"]: float(o["amount"]) * (1 if o["side"] == "buy" else -1) for o in self.market_orders or []}
            b["market"] = {"kind": "galactic", "fluct": {}, "bought": {}, "sold": {},
                           **(b.get("market") or {}), "trades_net": traded}
        return b

    def _date(self) -> str:
        return str((self._last or self.briefings[0]).get("date") or "")

    def _revert(self, date: str) -> None:
        for policy, (since, seen) in list(self._reverting.items()):
            if date > since:
                seen.add(date)
            if len(seen) >= 2:
                self.policies[policy], self.policy_dates[policy] = self.reverts[policy], date
                del self._reverting[policy]

    def briefing(self) -> dict:
        return self._current()

    def briefing_text(self) -> str:
        b = self.briefings[0]
        return f"# {b['date']} — test empire\nGovernor flags: {', '.join(self.flags) or 'none'}\n"

    def set_paused(self, paused: bool) -> str:
        """Replies like the controller's `stellaris_pause`: whether the state changed."""
        self.actions.append(("paused", paused))
        changed = self.paused != paused
        self.paused = paused
        if not paused:
            self.self_paused = False
        return f"{'Paused' if paused else 'Running'} ({'changed' if changed else 'already'})."

    def set_speed(self, speed: str) -> str:
        self.actions.append(("speed", speed))
        return "ok"

    def directive(self, name: str) -> str:
        """Flags and policies as the controller sets them; replies in its words (stellaris.rs
        Applied::summary): other flags stay, an option already in force is not set again."""
        from .config import REPO
        from .pillars import load_directive_policies
        self.actions.append(("directive", name))
        self.flags = [f for f in self.flags if not f.startswith("governor_directive_")] + [f"governor_directive_{name}"]
        done: dict[str, dict[str, str]] = {"set": {}, "in_force": {}, "locked": {}}
        for policy, option in load_directive_policies(REPO / "corpora/stellaris").get(name, {}).items():
            if self.policies.get(policy) == option:
                done["in_force"][policy] = option
            elif policy in self.locked:
                done["locked"][policy] = option
            else:
                done["set"][policy] = option
                self.policies[policy], self.policy_dates[policy] = option, self._date()
                if policy in self.reverts:
                    self._reverting[policy] = (self._date(), set())
        text = lambda d: ", ".join(f"{p}={o}" for p, o in d.items()) or "none"
        already = (f"Already in force (not set again, so its 10-year lock is not restarted): {text(done['in_force'])}. "
                   if done["in_force"] else "")
        return (f"Directive {name} applied and confirmed in game.log. Policies set: {text(done['set'])}. {already}"
                "Policies locked (not set: the 10-year policy lock, a rule such as no stance change at war, or the "
                f"option is not valid now): {text(done['locked'])}.\nConsole lines:\n(fake)\nThe next monthly autosave "
                f"will list governor_directive_{name} under Governor flags.")

    def log_tail(self, lines: int = 30) -> str:
        return ""

    def take_control(self) -> str:
        self.actions.append(("take_control",))
        return "AI controls the empire"

    def pick_tech(self, prefer: list[str]) -> str:
        self.actions.append(("pick_tech", list(prefer)))
        return self.pick_reply.format(tech=prefer[0]) if self.pick_reply and prefer else "ok"

    def market_sync(self, orders: list[dict]) -> str:
        self.actions.append(("market_sync", list(orders)))
        if self.market_sticky:
            self.market_orders = [dict(o) for o in orders]
        return "ok"

    def posture(self, name: str, on: bool) -> str:
        """Sets or clears the posture flag, as the controller does (directive flags stay)."""
        self.actions.append(("posture", name, on))
        flag = f"governor_posture_{name}"
        self.flags = [f for f in self.flags if f != flag] + ([flag] if on else [])
        return f"Posture {name} {'set' if on else 'cleared'} and confirmed in game.log."

    def screenshot(self) -> ToolResult:
        return ToolResult("Screenshot", None)

    def corpus(self, tool: str, **args) -> str:
        self.actions.append(("corpus", tool, args))
        return "- `doc:policies#0` [doc] Policies — …"

    def reload(self) -> None:
        pass

    def close(self) -> None:
        pass


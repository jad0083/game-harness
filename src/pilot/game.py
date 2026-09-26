"""Game access for the pilot: the Rust controller's MCP server over stdio, plus a direct
agent call for hovering. The fake implementation drives the tests."""

from __future__ import annotations

import base64
import json
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
        if token:
            self.env["GAME_AGENT_TOKEN"] = token
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

    def __init__(self, briefings: list[dict]):
        self.briefings = list(briefings)
        self.actions: list[tuple] = []
        self.paused = True
        self.flags: list[str] = []

    def _current(self) -> dict:
        b = dict(self.briefings[0] if len(self.briefings) == 1 else self.briefings.pop(0))
        b["flags"] = list(self.flags)
        return b

    def briefing(self) -> dict:
        return self._current()

    def briefing_text(self) -> str:
        b = self.briefings[0]
        return f"# {b['date']} — test empire\nGovernor flags: {', '.join(self.flags) or 'none'}\n"

    def set_paused(self, paused: bool) -> str:
        self.actions.append(("paused", paused))
        self.paused = paused
        return "ok"

    def set_speed(self, speed: str) -> str:
        self.actions.append(("speed", speed))
        return "ok"

    def directive(self, name: str) -> str:
        self.actions.append(("directive", name))
        self.flags = [f"governor_directive_{name}"]
        return f"Directive {name} applied"

    def log_tail(self, lines: int = 30) -> str:
        return ""

    def take_control(self) -> str:
        self.actions.append(("take_control",))
        return "AI controls the empire"

    def pick_tech(self, prefer: list[str]) -> str:
        self.actions.append(("pick_tech", list(prefer)))
        return "ok"

    def market_sync(self, orders: list[dict]) -> str:
        self.actions.append(("market_sync", list(orders)))
        return "ok"

    def screenshot(self) -> ToolResult:
        return ToolResult("Screenshot", None)

    def corpus(self, tool: str, **args) -> str:
        self.actions.append(("corpus", tool, args))
        return "- `doc:policies#0` [doc] Policies — …"

    def reload(self) -> None:
        pass

    def close(self) -> None:
        pass


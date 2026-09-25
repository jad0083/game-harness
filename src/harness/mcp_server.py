"""MCP server exposing the Windows game as screenshot + input tools.

All x/y arguments are pixel coordinates in the MOST RECENT image returned by
any tool (full screenshot or zoom); the server maps them back to screen pixels.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer

from .client import AgentClient, AgentError
from .session import GAME_WINDOW, Session

INSTRUCTIONS = """Controls a Windows PC running Galactic Civilizations IV.
Loop: look (screenshot/zoom) -> act (click/key/drag/scroll) -> look at the returned image.
Coordinates are always pixels in the most recent image you were shown.
Use grid=true when you need precise coordinates; use zoom to read small text.
Hover (move) shows tooltips. See PLAYING.md for the game playbook."""

server = MCPServer("game-harness", instructions=INSTRUCTIONS)
_session: Session | None = None


def session() -> Session:
    global _session
    if _session is None:
        save = os.environ.get("GAME_SCREENSHOT_DIR")
        _session = Session(AgentClient(), save_dir=Path(save) if save else None)
    return _session


def _frame(note: str, wait: float | None = None, grid: bool = False) -> list:
    s = session()
    jpeg, view = s.settle_and_screenshot(wait, grid=grid) if wait != 0 else s.screenshot(grid=grid)
    return [f"{note}\nimage {view.width}x{view.height} (1 image px = {view.scale:.2f} screen px)",
            Image(data=jpeg, format="jpeg")]


def _guard(fn):
    """Turn agent/validation failures into readable tool errors instead of crashes."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (AgentError, ValueError) as e:
            return f"ERROR: {e}"
    wrapper.__name__, wrapper.__doc__ = fn.__name__, fn.__doc__
    wrapper.__annotations__ = fn.__annotations__
    wrapper.__wrapped__ = fn
    return wrapper


@server.tool(structured_output=False)
@_guard
def status() -> str:
    """Check the agent is reachable; reports screen size and foreground window."""
    h = session().client.health()
    return f"agent v{h['version']} screen {h['screen'][0]}x{h['screen'][1]} foreground={h['foreground']!r}"


@server.tool(structured_output=False)
@_guard
def screenshot(grid: bool = False) -> list:
    """Capture the full screen. grid=true overlays labelled gridlines every 100 image px."""
    return _frame("screenshot", wait=0, grid=grid)


@server.tool(structured_output=False)
@_guard
def zoom(x: int, y: int, width: int, height: int, grid: bool = False) -> list:
    """Capture a region (x, y, width, height in last-image coords) at higher detail, e.g. to read
    small text. Subsequent coordinates refer to the zoomed image until the next screenshot."""
    jpeg, view = session().zoom(x, y, width, height, grid=grid)
    return [f"zoom of screen region at ({view.left},{view.top}); image {view.width}x{view.height}",
            Image(data=jpeg, format="jpeg")]


@server.tool(structured_output=False)
@_guard
def click(x: int, y: int, button: str = "left", count: int = 1, wait: float = 0.6, screenshot: bool = True) -> list | str:
    """Click at (x, y) in last-image coords. button: left/right/middle; count=2 double-clicks.
    Returns a fresh full screenshot taken `wait` seconds later (or a short text confirmation if screenshot=False)."""
    sx, sy = session().click(x, y, button, count)
    note = f"clicked {button} x{count} at screen ({sx},{sy})"
    return _frame(note, wait) if screenshot else note


@server.tool(structured_output=False)
@_guard
def hover(x: int, y: int, wait: float = 1.0, screenshot: bool = True) -> list | str:
    """Move the mouse to (x, y) without clicking, to reveal tooltips. Returns a screenshot."""
    sx, sy = session().move(x, y)
    note = f"hovering at screen ({sx},{sy})"
    return _frame(note, wait) if screenshot else note


@server.tool(structured_output=False)
@_guard
def drag(x1: int, y1: int, x2: int, y2: int, button: str = "left", wait: float = 0.6, screenshot: bool = True) -> list | str:
    """Press at (x1, y1), move to (x2, y2), release. Use right button to pan in some games."""
    session().drag(x1, y1, x2, y2, button)
    note = f"dragged {button} ({x1},{y1})->({x2},{y2})"
    return _frame(note, wait) if screenshot else note


@server.tool(structured_output=False)
@_guard
def scroll(x: int, y: int, clicks: int, wait: float = 0.6, screenshot: bool = True) -> list | str:
    """Mouse-wheel at (x, y). Positive clicks scroll up / zoom in, negative down / zoom out."""
    session().scroll(x, y, clicks)
    note = f"scrolled {clicks} at ({x},{y})"
    return _frame(note, wait) if screenshot else note


@server.tool(structured_output=False)
@_guard
def key(combo: str, repeat: int = 1, wait: float = 0.6, screenshot: bool = True) -> list | str:
    """Press a key or combo, e.g. "enter", "esc", "ctrl+s", "f1", "shift+tab", "ctrl+plus"."""
    session().key(combo, repeat)
    note = f"pressed {combo} x{repeat}"
    return _frame(note, wait) if screenshot else note


@server.tool(structured_output=False)
@_guard
def type_text(text: str, wait: float = 0.3, screenshot: bool = True) -> list | str:
    """Type literal text into the focused field (click the field first)."""
    session().type_text(text)
    note = f"typed {len(text)} chars"
    return _frame(note, wait) if screenshot else note


@server.tool(structured_output=False)
@_guard
def batch(actions: list[dict], wait: float = 0.6, grid: bool = False, screenshot: bool = True) -> list | str:
    """Execute a list of actions in order, then take at most one screenshot at the end.
    Drastically reduces latency and token usage when issuing multiple commands.

    actions: list of dicts, supported actions:
      - {"action": "click", "x": 100, "y": 200, "button": "left", "count": 1}
      - {"action": "move", "x": 100, "y": 200}
      - {"action": "drag", "x1": 100, "y1": 200, "x2": 300, "y2": 400, "button": "left"}
      - {"action": "scroll", "x": 100, "y": 200, "clicks": -3}
      - {"action": "key", "combo": "enter", "repeat": 1}
      - {"action": "type", "text": "colony"}
      - {"action": "wait", "seconds": 0.5}
    Coordinates are in the last-image pixel space.
    """
    results = session().batch(actions)
    note = f"executed batch of {len(results)} actions"
    return _frame(note, wait, grid=grid) if screenshot else note


@server.tool(structured_output=False)
@_guard
def game_state() -> str:
    """Inspect Galactic Civilizations IV game state: running status, active window, turn counter, and autosaves."""
    st = session().game_state()
    running = st.get("game_running", False)
    title = st.get("window_title") or "None"
    fg = st.get("foreground", False)
    turn = st.get("turn")
    save = st.get("latest_save")
    stime = st.get("save_time")
    lines = [
        f"Game running: {running} (foreground={fg}, window={title!r})",
        f"Turn: {turn if turn is not None else 'Unknown'}",
        f"Latest save: {save or 'None'}" + (f" ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stime))})" if stime else ""),
    ]
    return "\n".join(lines)


@server.tool(structured_output=False)
@_guard
def end_turn(timeout: float = 60.0, grid: bool = False) -> list:
    """Send Enter (or click End Turn) and dynamically wait for the AI turn to finish processing
    (monitored via autosaves/game state), returning a fresh screenshot of the new turn."""
    s = session()
    s.key("enter")
    res = s.wait_for_turn(timeout=timeout)
    note = f"turn transition: {res}"
    return _frame(note, wait=0.5, grid=grid)


@server.tool(structured_output=False)
@_guard
def auto_idle_ships(count: int = 5, action: str = "auto_colonize", grid: bool = False) -> list:
    """Cycle through idle ships and assign automated orders in a single fast macro.
    action: "auto_colonize" (presses 'c'), "sleep" (presses 'f'), or "next" (just cycles tab).
    """
    key_map = {"auto_colonize": "c", "sleep": "f", "next": None}
    hotkey = key_map.get(action)
    acts = []
    for _ in range(count):
        acts.append({"action": "key", "combo": "tab", "repeat": 1})
        acts.append({"action": "wait", "seconds": 0.15})
        if hotkey:
            acts.append({"action": "key", "combo": hotkey, "repeat": 1})
            acts.append({"action": "wait", "seconds": 0.15})
    session().batch(acts)
    return _frame(f"cycled {count} idle ships with {action}", wait=0.5, grid=grid)


@server.tool(structured_output=False)
@_guard
def focus_game(title: str = GAME_WINDOW) -> list:
    """Bring the window whose title contains `title` to the foreground."""
    focused = session().focus_game(title)
    return _frame(f"focused {focused!r}", 1.0)


@server.tool(structured_output=False)
@_guard
def wait(seconds: float = 3.0) -> list:
    """Wait (e.g. for AI turns to process) then screenshot. Max 120s."""
    return _frame(f"waited {seconds}s", max(0.0, min(seconds, 120.0)))


@server.tool(structured_output=False)
@_guard
def list_windows() -> str:
    """List visible top-level windows on the PC."""
    return "\n".join(
        f"{'*' if w['foreground'] else ' '} {w['title']}  rect={w['rect']}" for w in session().client.windows()
    )


@server.tool(structured_output=False)
@_guard
def wait_settle(timeout: float = 30.0, threshold: float = 0.02, grid: bool = False) -> list:
    """Wait dynamically until on-screen motion/animations stabilize, then return screenshot."""
    res = session().wait_settle(timeout=timeout, threshold=threshold)
    elapsed = res.get("elapsed", 0.0)
    note = f"settled: {res.get('settled', True)} in {elapsed:.2f}s"
    return _frame(note, wait=0, grid=grid)


@server.tool(structured_output=False)
@_guard
def diff(threshold: int = 25, highlight: bool = True, grid: bool = False) -> list:
    """Take a screenshot, compare with previous screenshot, and optionally highlight changed regions."""
    s = session()
    jpeg, view, bbox = s.diff_and_screenshot(grid=grid, highlight=highlight, threshold=threshold)
    note = f"diff against previous frame: changed bbox {bbox}" if bbox else "diff against previous frame: no changes detected"
    return [f"{note}\nimage {view.width}x{view.height} (1 image px = {view.scale:.2f} screen px)",
            Image(data=jpeg, format="jpeg")]


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()

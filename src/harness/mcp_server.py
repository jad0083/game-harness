"""MCP server exposing the Windows game as screenshot + input tools.

All x/y arguments are pixel coordinates in the MOST RECENT image returned by
any tool (full screenshot or zoom); the server maps them back to screen pixels.
"""

from __future__ import annotations

import os
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
def click(x: int, y: int, button: str = "left", count: int = 1, wait: float = 0.6) -> list:
    """Click at (x, y) in last-image coords. button: left/right/middle; count=2 double-clicks.
    Returns a fresh full screenshot taken `wait` seconds later."""
    sx, sy = session().click(x, y, button, count)
    return _frame(f"clicked {button} x{count} at screen ({sx},{sy})", wait)


@server.tool(structured_output=False)
@_guard
def hover(x: int, y: int, wait: float = 1.0) -> list:
    """Move the mouse to (x, y) without clicking, to reveal tooltips. Returns a screenshot."""
    sx, sy = session().move(x, y)
    return _frame(f"hovering at screen ({sx},{sy})", wait)


@server.tool(structured_output=False)
@_guard
def drag(x1: int, y1: int, x2: int, y2: int, button: str = "left", wait: float = 0.6) -> list:
    """Press at (x1, y1), move to (x2, y2), release. Use right button to pan in some games."""
    session().drag(x1, y1, x2, y2, button)
    return _frame(f"dragged {button} ({x1},{y1})->({x2},{y2})", wait)


@server.tool(structured_output=False)
@_guard
def scroll(x: int, y: int, clicks: int, wait: float = 0.6) -> list:
    """Mouse-wheel at (x, y). Positive clicks scroll up / zoom in, negative down / zoom out."""
    session().scroll(x, y, clicks)
    return _frame(f"scrolled {clicks} at ({x},{y})", wait)


@server.tool(structured_output=False)
@_guard
def key(combo: str, repeat: int = 1, wait: float = 0.6) -> list:
    """Press a key or combo, e.g. "enter", "esc", "ctrl+s", "f1", "shift+tab", "ctrl+plus"."""
    session().key(combo, repeat)
    return _frame(f"pressed {combo} x{repeat}", wait)


@server.tool(structured_output=False)
@_guard
def type_text(text: str, wait: float = 0.3) -> list:
    """Type literal text into the focused field (click the field first)."""
    session().type_text(text)
    return _frame(f"typed {len(text)} chars", wait)


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


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()

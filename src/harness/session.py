"""Stateful game session: tracks the last image's coordinate space so actions
can be expressed in the pixel coordinates of what the model was just shown."""

from __future__ import annotations

import time
from pathlib import Path

from .client import AgentClient
from .imaging import View, render

GAME_WINDOW = "Galactic Civilizations"


class Session:
    def __init__(self, client: AgentClient, settle: float = 0.6, save_dir: Path | None = None) -> None:
        self.client = client
        self.settle = settle
        self.view: View | None = None
        self.save_dir = save_dir
        self.shots = 0

    def _keep(self, jpeg: bytes) -> None:
        if self.save_dir is None:
            return
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.shots += 1
        (self.save_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{self.shots:05d}.jpg").write_bytes(jpeg)

    def screenshot(self, grid: bool = False) -> tuple[bytes, View]:
        jpeg, self.view = render(self.client.screenshot(), grid=grid)
        self._keep(jpeg)
        return jpeg, self.view

    def zoom(self, x: float, y: float, w: float, h: float, grid: bool = False) -> tuple[bytes, View]:
        """Capture a region (given in last-image coordinates) at native or enlarged resolution."""
        sx, sy, sw, sh = self._view().rect_to_screen(x, y, w, h)
        png = self.client.screenshot(sx, sy, sw, sh)
        jpeg, self.view = render(png, left=sx, top=sy, max_upscale=3.0, grid=grid)
        self._keep(jpeg)
        return jpeg, self.view

    def _view(self) -> View:
        if self.view is None:
            self.screenshot()
        return self.view

    def point(self, x: float, y: float) -> tuple[int, int]:
        return self._view().to_screen(x, y)

    def click(self, x: float, y: float, button: str = "left", count: int = 1) -> tuple[int, int]:
        sx, sy = self.point(x, y)
        self.client.click(sx, sy, button, count)
        return sx, sy

    def move(self, x: float, y: float) -> tuple[int, int]:
        sx, sy = self.point(x, y)
        self.client.move(sx, sy)
        return sx, sy

    def drag(self, x1: float, y1: float, x2: float, y2: float, button: str = "left") -> None:
        a, b = self.point(x1, y1), self.point(x2, y2)
        self.client.drag(*a, *b, button=button)

    def scroll(self, x: float, y: float, clicks: int) -> None:
        self.client.scroll(*self.point(x, y), clicks)

    def key(self, combo: str, repeat: int = 1) -> None:
        self.client.key(combo, repeat)

    def type_text(self, text: str) -> None:
        self.client.type_text(text)

    def focus_game(self, title: str = GAME_WINDOW) -> str:
        return self.client.focus(title)["focused"]

    def settle_and_screenshot(self, wait: float | None = None, grid: bool = False) -> tuple[bytes, View]:
        time.sleep(self.settle if wait is None else wait)
        return self.screenshot(grid=grid)

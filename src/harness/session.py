"""Stateful game session: tracks the last image's coordinate space so actions
can be expressed in the pixel coordinates of what the model was just shown."""

from __future__ import annotations

import time
from pathlib import Path

from .client import AgentClient, AgentError
from .imaging import MAX_SIDE, View, crop_region, detect_change_bbox, highlight_changes, render

GAME_WINDOW = "Galactic Civilizations"


class Session:
    def __init__(self, client: AgentClient, settle: float = 0.6, save_dir: Path | None = None) -> None:
        self.client = client
        self.settle = settle
        self.view: View | None = None
        self.last_screenshot: bytes | None = None
        self.save_dir = save_dir
        self.shots = 0

    def _keep(self, jpeg: bytes) -> None:
        if self.save_dir is None:
            return
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.shots += 1
        (self.save_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{self.shots:05d}.jpg").write_bytes(jpeg)

    def screenshot(self, grid: bool = False, max_side: int | None = MAX_SIDE) -> tuple[bytes, View]:
        png = self.client.screenshot(max_side=max_side)
        headers = {k.lower(): v for k, v in getattr(self.client, "last_headers", {}).items()}
        orig_w = int(headers["x-width"]) if "x-width" in headers else None
        orig_h = int(headers["x-height"]) if "x-height" in headers else None
        jpeg, self.view = render(png, max_side=MAX_SIDE, grid=grid, orig_w=orig_w, orig_h=orig_h)
        self.last_screenshot = jpeg
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

    def _fallback_batch(self, actions: list[dict]) -> list[dict]:
        results = []
        for act in actions:
            kind = act["action"]
            if kind == "click":
                self.client.click(act["x"], act["y"], act.get("button", "left"), act.get("count", 1))
            elif kind == "move":
                self.client.move(act["x"], act["y"])
            elif kind == "drag":
                self.client.drag(act["x1"], act["y1"], act["x2"], act["y2"], act.get("button", "left"))
            elif kind == "scroll":
                self.client.scroll(act["x"], act["y"], act["clicks"])
            elif kind == "key":
                self.client.key(act["combo"], act.get("repeat", 1))
            elif kind == "type":
                self.client.type_text(act["text"])
            elif kind == "wait":
                time.sleep(act.get("seconds", 0.5))
            results.append({"action": kind, "ok": True})
        return results

    def batch(self, actions: list[dict]) -> list[dict]:
        converted = []
        for act in actions:
            item = dict(act)
            kind = item.get("action")
            if kind in ("click", "move"):
                item["x"], item["y"] = self.point(item["x"], item["y"])
            elif kind == "drag":
                item["x1"], item["y1"] = self.point(item["x1"], item["y1"])
                item["x2"], item["y2"] = self.point(item["x2"], item["y2"])
            elif kind == "scroll":
                item["x"], item["y"] = self.point(item["x"], item["y"])
            converted.append(item)

        try:
            return self.client.batch(converted).get("results", [])
        except AgentError as e:
            if "404" in str(e) or "no route" in str(e):
                return self._fallback_batch(converted)
            raise

    def game_state(self) -> dict:
        try:
            return self.client.state()
        except AgentError:
            try:
                wins = self.client.windows()
                gc = next((w for w in wins if "galactic civilizations" in w["title"].lower()), None)
                return {
                    "game_running": gc is not None,
                    "window_title": gc["title"] if gc else None,
                    "foreground": gc["foreground"] if gc else False,
                    "turn": None,
                    "latest_save": None,
                    "save_time": None,
                }
            except (AgentError, OSError, ValueError):
                return {"game_running": False}

    def wait_settle(self, timeout: float = 30.0, threshold: float = 0.02) -> dict:
        """Wait for the screen to visually stabilize using low-res frame differencing."""
        try:
            return self.client.settle(timeout=timeout, threshold=threshold)
        except AgentError:
            time.sleep(min(timeout, 1.5))
            return {"settled": True, "elapsed": 1.5, "fallback": True}

    def wait_for_turn(self, timeout: float = 60.0, poll_interval: float = 0.5) -> dict:
        """Wait for the AI turn to complete. First attempts visual settle detection;
        if not supported, falls back to polling save file/turn state."""
        time.sleep(0.5)  # brief grace period for turn change animation to start
        try:
            res = self.client.settle(timeout=timeout)
            return {"completed": res.get("settled", False), "elapsed": res.get("elapsed", 0.0), "visual": True}
        except AgentError:
            pass

        initial = self.game_state()
        init_turn = initial.get("turn")
        init_save = initial.get("latest_save")
        start = time.time()
        while time.time() - start < timeout:
            time.sleep(poll_interval)
            cur = self.game_state()
            if init_turn is not None and cur.get("turn") is not None and cur["turn"] > init_turn:
                return {"completed": True, "turn": cur["turn"], "elapsed": round(time.time() - start, 2)}
            if init_save is not None and cur.get("latest_save") and cur["latest_save"] != init_save:
                return {"completed": True, "turn": cur.get("turn"), "save": cur.get("latest_save"),
                        "elapsed": round(time.time() - start, 2)}
        return {"completed": False, "timeout": True, "elapsed": round(time.time() - start, 2)}

    def diff_and_screenshot(self, grid: bool = False, highlight: bool = True,
                            threshold: int = 25) -> tuple[bytes, View, tuple[int, int, int, int] | None]:
        """Take a screenshot, compare with previous screenshot, and optionally highlight changed bbox."""
        before = self.last_screenshot
        jpeg, view = self.screenshot(grid=grid)
        bbox = None
        if before is not None:
            bbox = detect_change_bbox(before, jpeg, threshold=threshold)
            if bbox and highlight:
                jpeg = highlight_changes(jpeg, bbox)
        return jpeg, view, bbox

    def settle_and_screenshot(self, wait: float | None = None, grid: bool = False) -> tuple[bytes, View]:
        time.sleep(self.settle if wait is None else wait)
        return self.screenshot(grid=grid)

    def crop(self, x: int, y: int, w: int, h: int) -> bytes:
        """Crop a sub-region (x, y, w, h) in last-image coordinates from the last screenshot."""
        if self.last_screenshot is None:
            self.screenshot()
        assert self.last_screenshot is not None
        return crop_region(self.last_screenshot, x, y, w, h)

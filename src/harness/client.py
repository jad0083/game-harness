"""HTTP client for the Windows game agent."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://192.168.1.77:8765"
TOKEN_FILE = Path(__file__).resolve().parents[2] / ".agent_token"


class AgentError(RuntimeError):
    pass


def default_token() -> str:
    token = os.environ.get("GAME_AGENT_TOKEN")
    if token:
        return token.strip()
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    raise AgentError(f"no agent token: set GAME_AGENT_TOKEN or write it to {TOKEN_FILE}")


class AgentClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = (base_url or os.environ.get("GAME_AGENT_URL") or DEFAULT_URL).rstrip("/")
        self.token = token if token is not None else default_token()
        self.timeout = timeout
        self.last_headers: dict = {}

    def _request(self, method: str, path: str, body: dict | None = None) -> tuple[bytes, dict]:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self.last_headers = dict(r.headers)
                return r.read(), self.last_headers
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            try:
                detail = json.loads(detail)["error"]
            except (ValueError, KeyError):
                pass
            raise AgentError(f"{method} {path} -> HTTP {e.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise AgentError(f"cannot reach agent at {self.base_url}: {e}") from None

    def _post(self, path: str, **body) -> dict:
        return json.loads(self._request("POST", path, body)[0])

    def health(self) -> dict:
        return json.loads(self._request("GET", "/health")[0])

    def screenshot(self, x: int | None = None, y: int | None = None,
                   w: int | None = None, h: int | None = None,
                   max_side: int | None = None) -> bytes:
        """PNG bytes of the whole primary screen, or of a region in screen pixels."""
        params = {k: v for k, v in (("x", x), ("y", y), ("w", w), ("h", h), ("max_side", max_side)) if v is not None}
        query = ("?" + "&".join(f"{k}={int(v)}" for k, v in params.items())) if params else ""
        return self._request("GET", "/screenshot" + query)[0]

    def windows(self) -> list[dict]:
        return json.loads(self._request("GET", "/windows")[0])["windows"]

    def state(self) -> dict:
        return json.loads(self._request("GET", "/state")[0])

    def settle(self, timeout: float = 30.0, threshold: float = 0.02) -> dict:
        """Wait for visual settling (animations/turns to complete) using frame differencing."""
        return json.loads(self._request("GET", f"/settle?timeout={timeout}&threshold={threshold}")[0])

    def batch(self, actions: list[dict]) -> dict:
        return self._post("/batch", actions=actions)

    def move(self, x: int, y: int) -> dict:
        return self._post("/move", x=x, y=y)

    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> dict:
        return self._post("/click", x=x, y=y, button=button, count=count)

    def drag(self, x1: int, y1: int, x2: int, y2: int, button: str = "left") -> dict:
        return self._post("/drag", x1=x1, y1=y1, x2=x2, y2=y2, button=button)

    def scroll(self, x: int, y: int, clicks: int) -> dict:
        return self._post("/scroll", x=x, y=y, clicks=clicks)

    def key(self, combo: str, repeat: int = 1) -> dict:
        return self._post("/key", combo=combo, repeat=repeat)

    def type_text(self, text: str) -> dict:
        return self._post("/type", text=text)

    def focus(self, title: str) -> dict:
        return self._post("/focus", title=title)

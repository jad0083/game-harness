import signal
import threading
from http.server import HTTPServer

import pytest

from windows_agent import agent

TEST_TIME_LIMIT_S = 60


class TestTimeLimitExceeded(BaseException):
    """BaseException, so the governor's broad `except Exception` loops cannot swallow it."""


@pytest.fixture(autouse=True)
def _time_limit():
    """Fail a test that runs past TEST_TIME_LIMIT_S instead of hanging the suite (a governor loop
    waiting on a fake game that never advances polls forever)."""
    def expired(*_):
        raise TestTimeLimitExceeded(f"test ran longer than {TEST_TIME_LIMIT_S} s")
    old = signal.signal(signal.SIGALRM, expired)
    signal.alarm(TEST_TIME_LIMIT_S)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


class FakeBackend:
    """Records input calls; serves a synthetic gradient screen."""

    def __init__(self, w=64, h=48):
        self.w, self.h = w, h
        self.calls = []

    def screen_size(self):
        return self.w, self.h

    def capture(self, x, y, w, h, target_w=None, target_h=None):
        tw = target_w or w
        th = target_h or h
        out = bytearray()
        for row in range(th):
            for col in range(tw):
                out += bytes([(x + col) % 256, (y + row) % 256, 200, 255])  # B, G, R, A
        return bytes(out)

    def foreground_title(self):
        return "Galactic Civilizations IV"

    def game_state(self):
        return {
            "game_running": True,
            "window_title": "Galactic Civilizations IV",
            "foreground": True,
            "turn": 1,
            "latest_save": "AutoSave_Turn_0001.sav",
            "save_time": 1700000000.0,
        }

    def move(self, x, y):
        self.calls.append(("move", x, y))

    def button(self, button, down):
        self.calls.append(("button", button, down))

    def scroll(self, clicks):
        self.calls.append(("scroll", clicks))

    def key(self, vk, down):
        self.calls.append(("key", vk, down))

    def type_text(self, text):
        self.calls.append(("type", text))

    def list_windows(self):
        return [{"title": "Galactic Civilizations IV", "foreground": True, "rect": [0, 0, self.w, self.h]}]

    def focus(self, title):
        if "galactic" not in title.lower():
            raise LookupError("no window")
        return "Galactic Civilizations IV"


@pytest.fixture
def agent_server(request):
    """A real agent HTTP server on localhost backed by FakeBackend(size)."""
    size = getattr(request, "param", (64, 48))
    backend = FakeBackend(*size)
    srv = HTTPServer(("127.0.0.1", 0), agent.make_handler(agent.Controller(backend, delay=0), "sekret"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", backend
    srv.shutdown()
    srv.server_close()

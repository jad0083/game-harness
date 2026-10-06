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


DASHBOARD_TEST_KEY = "test-dashboard-key"


@pytest.fixture
def clock():
    """An injectable wall clock for the sign-in tests (authkit.Clock); advance it with clock.t += s."""
    from authkit import Clock
    return Clock()


@pytest.fixture(autouse=True)
def _auth_db(tmp_path, monkeypatch):
    """Every dashboard's sign-in store lives in the test's temp dir (never runs/auth.sqlite), and no data
    directory comes from the shell or the repo's .env: Settings.from_env() would load <repo>/.env with
    setdefault after these variables were cleared, so a call without a path reads no file in tests."""
    monkeypatch.setenv("PILOT_AUTH_DB", str(tmp_path / "auth-store" / "auth.sqlite"))
    for var in ("PILOT_PUBLIC_URL", "PILOT_DASHBOARD_HOSTS", "PILOT_KEY_SIGNIN", "PILOT_ADD_DEVICE",
                "PILOT_DATA_DIR", "PILOT_RUNS_DIR"):
        monkeypatch.delenv(var, raising=False)
    from pilot import config
    real_load_dotenv = config.load_dotenv
    monkeypatch.setattr(config, "load_dotenv", lambda path=None: None if path is None else real_load_dotenv(path))


@pytest.fixture(autouse=True)
def _fresh_stores():
    """Each test opens its own pilot.db stores (open_store caches one per path per process)."""
    yield
    from pilot import store
    with store._OPEN_LOCK:
        for st in store._OPEN.values():
            st.close()
        store._OPEN.clear()


def journal_text(data_dir) -> str:
    """The pilot journal's lines in a test's data directory (the store's journal table), oldest first."""
    from pilot.store import open_store
    return "\n".join(r["text"] for r in open_store(data_dir).query("SELECT text FROM journal ORDER BY t, rowid"))


@pytest.fixture(autouse=True)
def _dashboard_key(monkeypatch):
    """Dashboards in tests use a fixed access key (never runs/secrets/dashboard.key), and aiohttp test
    clients send it unless a test passes its own `headers` (the security tests pass `{}`)."""
    from aiohttp import test_utils
    monkeypatch.setenv("PILOT_DASHBOARD_KEY", DASHBOARD_TEST_KEY)
    orig = test_utils.TestClient.__init__

    def init(self, server, *a, headers=None, **kw):
        orig(self, server, *a, headers={"X-Pilot-Key": DASHBOARD_TEST_KEY} if headers is None else headers, **kw)

    monkeypatch.setattr(test_utils.TestClient, "__init__", init)


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


@pytest.fixture(autouse=True)
def guard_waits(monkeypatch):
    """The model guard's retry and pacing waits take no real time in tests; each wait is recorded, and
    retry jitter takes its lower bound."""
    from pilot import modelguard
    waits: list[float] = []

    async def sleep(seconds):
        waits.append(seconds)
    monkeypatch.setattr(modelguard, "_sleep", sleep)
    monkeypatch.setattr(modelguard, "_uniform", lambda lo, hi: lo)
    return waits

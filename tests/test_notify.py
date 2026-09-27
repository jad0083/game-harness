"""The opt-in ntfy notice (docs/design/2026-09-27-dashboard-v2-design.md, ruling 8): off unless
PILOT_NOTIFY_URL names an http(s) topic; when the run needs you for 5 minutes, again at 30 minutes and 2
hours, and once when it no longer does; the message names the game, what stopped and for how long, clicks
through to the dashboard's plain address, and never carries a key."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from pilot.events import RunState
from pilot.notify import Notifier, duration, notifier_from_env, start_notifier

CORPORA = Path(__file__).resolve().parents[1] / "corpora"
T0 = 1_790_000_000.0
KEY = "a-dashboard-key-that-must-never-leave-0123456789"


class Posts:
    def __init__(self, fail: bool = False):
        self.sent: list[tuple[str, str, dict]] = []
        self.fail = fail

    def __call__(self, url: str, body: str, headers: dict) -> None:
        self.sent.append((url, body, headers))
        if self.fail:
            raise OSError("network down")


def stopped(since: float, category: str = "transient", game: str = "civ6", date: str = "T57") -> RunState:
    st = RunState(run_id="r1", model="m", status="needs_attention", game_date=date)
    st.info.update(game=game, attention={"reason": "autoplay did not start at T57 (still inactive after 21 s). Check the game.",
                                         "category": category, "since": since, "date": date})
    return st


def notifier(posts: Posts) -> Notifier:
    return Notifier("https://ntfy.example/game-pilot-7f3a", "http://192.168.1.76:8780", post=posts, corpora=CORPORA)


def test_off_unless_an_http_topic_is_set():
    assert notifier_from_env({}) is None
    assert notifier_from_env({"PILOT_NOTIFY_URL": ""}) is None
    assert notifier_from_env({"PILOT_NOTIFY_URL": "ftp://ntfy.example/t"}) is None
    assert notifier_from_env({"PILOT_NOTIFY_URL": "ntfy.example/t"}) is None
    n = notifier_from_env({"PILOT_NOTIFY_URL": "https://ntfy.example/t", "PILOT_PUBLIC_URL": "http://192.168.1.76:8780/"})
    assert n is not None and n.url == "https://ntfy.example/t" and n.dashboard_url == "http://192.168.1.76:8780"
    assert start_notifier(object(), env={}) is None                       # no thread when off


def test_notices_at_5_min_30_min_and_2_h_then_once_on_recovery():
    posts = Posts()
    n = notifier(posts)
    st = stopped(T0)
    for t in (T0 + 10, T0 + 299):
        assert n.check(st, now=t) is None
    assert n.check(st, now=T0 + 305) == "Game Pilot needs you: Civ VI, autoplay did not start at T57 (5 min)"
    assert n.check(st, now=T0 + 320) is None                              # once per mark
    assert n.check(st, now=T0 + 1800) == "Game Pilot needs you: Civ VI, autoplay did not start at T57 (30 min)"
    assert n.check(st, now=T0 + 7215) == "Game Pilot needs you: Civ VI, autoplay did not start at T57 (2 h)"
    assert n.check(st, now=T0 + 20000) is None                            # nothing after 2 h
    st.status = "playing"
    st.info.pop("attention")
    assert n.check(st, now=T0 + 20010) == "Game Pilot no longer needs you: Civ VI is playing again at T57 (after 5 h 33 min)"
    assert n.check(st, now=T0 + 20020) is None
    assert len(posts.sent) == 4
    url, body, headers = posts.sent[0]
    assert url == "https://ntfy.example/game-pilot-7f3a" and body == "Game Pilot needs you: Civ VI, autoplay did not start at T57 (5 min)"
    assert headers["Click"] == "http://192.168.1.76:8780" and headers["Title"] == "Game Pilot"
    assert all(h.isascii() for h in headers.values())


def test_a_short_stop_sends_nothing_and_a_new_stop_starts_over():
    posts = Posts()
    n = notifier(posts)
    st = stopped(T0)
    n.check(st, now=T0 + 100)
    st.status = "playing"
    assert n.check(st, now=T0 + 120) is None                             # resolved before 5 min: silent
    st2 = stopped(T0 + 1000, category="unreachable")
    assert n.check(st2, now=T0 + 1310) == "Game Pilot needs you: Civ VI, the game does not answer at T57 (5 min)"
    assert len(posts.sent) == 1


def test_a_late_look_sends_only_the_latest_mark():
    """A pilot that starts watching 40 minutes into a stop says so once, not three times."""
    posts = Posts()
    n = notifier(posts)
    assert n.check(stopped(T0), now=T0 + 2400) == "Game Pilot needs you: Civ VI, autoplay did not start at T57 (40 min)"
    assert n.check(stopped(T0), now=T0 + 2500) is None
    assert len(posts.sent) == 1


def test_an_older_stop_without_attention_and_other_games():
    posts = Posts()
    n = notifier(posts)
    st = RunState(run_id="r1", model="m", status="needs_attention", game_date="2288.08.01")
    st.info["game"] = "stellaris"
    assert n.check(st, now=T0) is None                                     # first seen now
    assert n.check(st, now=T0 + 300) == "Game Pilot needs you: Stellaris, the run stopped at 2288.08 (5 min)"
    st2 = stopped(T0 + 1, category="stall", game="stellaris", date="2288.08.01")     # another stop
    assert n.check(st2, now=T0 + 400) == "Game Pilot needs you: Stellaris, the game date stopped moving at 2288.08 (6 min)"
    st2.status = "stopped"
    assert n.check(st2, now=T0 + 500) == "Game Pilot no longer needs you: Stellaris, the run stopped at 2288.08 (after 8 min)"


def test_a_failed_post_never_raises_and_no_key_is_ever_sent(monkeypatch):
    monkeypatch.setenv("PILOT_DASHBOARD_KEY", KEY)
    posts = Posts(fail=True)
    n = notifier(posts)
    assert n.check(stopped(T0), now=T0 + 301) is not None                 # tried; the failure is logged
    for url, body, headers in posts.sent:
        assert KEY not in url + body + "".join(headers.values())
        assert "key=" not in url + body + headers["Click"]


def test_the_watch_thread_posts_from_the_live_state():
    posts = Posts()
    n = notifier(posts)

    class Log:
        state = stopped(time.time() - 400)

    stop = threading.Event()
    t = n.start(Log(), stop, every=0.01)
    deadline = time.time() + 5
    while not posts.sent and time.time() < deadline:
        time.sleep(0.02)
    stop.set()
    t.join(2)
    assert [b for _, b, _ in posts.sent] == ["Game Pilot needs you: Civ VI, autoplay did not start at T57 (6 min)"]


def test_duration_words():
    assert [duration(s) for s in (59, 300, 1800, 3600, 7200, 7260, 20000)] == [
        "less than a minute", "5 min", "30 min", "1 h", "2 h", "2 h 1 min", "5 h 33 min"]


def test_the_live_pilot_starts_the_notice_thread():
    """cli.run starts it next to the live dashboard; it is off unless PILOT_NOTIFY_URL is set."""
    import inspect

    from pilot import cli
    assert "start_notifier(log)" in inspect.getsource(cli.run)

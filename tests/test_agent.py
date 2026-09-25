import io
import json
import urllib.error
import urllib.request

import pytest
from conftest import FakeBackend
from PIL import Image

from windows_agent import agent

# -- pure helpers -------------------------------------------------------------


def test_encode_png_roundtrips_pixels():
    w, h = 5, 3
    bgra = FakeBackend(w, h).capture(0, 0, w, h)
    png = agent.encode_png(w, h, agent.bgra_to_rgb(bgra, w, h))
    img = Image.open(io.BytesIO(png)).convert("RGB")
    assert img.size == (5, 3)
    assert img.getpixel((4, 2)) == (200, 2, 4)  # R from 200, G=row, B=col


def test_parse_combo_modifiers_and_aliases():
    assert agent.parse_combo("ctrl+shift+s") == [0x11, 0x10, ord("S")]
    assert agent.parse_combo("Enter") == [0x0D]
    assert agent.parse_combo("F12") == [0x7B]
    assert agent.parse_combo("ctrl+plus") == [0x11, 0xBB]


@pytest.mark.parametrize("bad", ["", "ctrl+", "hyperkey", "ctrl++"])
def test_parse_combo_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        agent.parse_combo(bad)


def test_token_created_once(tmp_path):
    p = tmp_path / "agent_token.txt"
    t1 = agent.load_or_create_token(p)
    assert len(t1) >= 20
    assert agent.load_or_create_token(p) == t1


# -- controller ---------------------------------------------------------------


def make_controller():
    b = FakeBackend()
    return agent.Controller(b, delay=0), b


def test_click_moves_then_presses_and_releases():
    c, b = make_controller()
    c.click(10, 20, "right", count=2)
    assert b.calls == [
        ("move", 10, 20),
        ("button", "right", True), ("button", "right", False),
        ("button", "right", True), ("button", "right", False),
    ]


def test_click_outside_screen_rejected():
    c, b = make_controller()
    with pytest.raises(ValueError):
        c.click(64, 0)
    assert b.calls == []


def test_key_combo_releases_in_reverse_order():
    c, b = make_controller()
    c.key("ctrl+s")
    assert b.calls == [("key", 0x11, True), ("key", ord("S"), True), ("key", ord("S"), False), ("key", 0x11, False)]


def test_drag_always_releases_button():
    c, b = make_controller()
    c.drag(0, 0, 10, 10, steps=2)
    assert b.calls[0] == ("move", 0, 0)
    assert b.calls[1] == ("button", "left", True)
    assert b.calls[-1] == ("button", "left", False)
    assert ("move", 10, 10) in b.calls


def test_screenshot_region_validation():
    c, _ = make_controller()
    png, w, h = c.screenshot(10, 10, 20, 5)
    assert (w, h) == (20, 5)
    assert Image.open(io.BytesIO(png)).getpixel((0, 0))[1] == 10
    with pytest.raises(ValueError):
        c.screenshot(60, 0, 10, 10)


# -- HTTP ---------------------------------------------------------------------




def call(base, path, body=None, token="sekret"):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method="POST" if body is not None else "GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def test_http_requires_token(agent_server):
    base, b = agent_server
    assert call(base, "/health", token=None)[0] == 401
    assert call(base, "/click", {"x": 1, "y": 1}, token="wrong")[0] == 401
    assert b.calls == []


def test_http_health_and_screenshot(agent_server):
    base, _ = agent_server
    status, body, _ = call(base, "/health")
    assert status == 200
    assert json.loads(body)["screen"] == [64, 48]
    status, body, headers = call(base, "/screenshot?x=0&y=0&w=8&h=4")
    assert status == 200 and headers["Content-Type"] == "image/png"
    assert Image.open(io.BytesIO(body)).size == (8, 4)


def test_http_click_and_errors(agent_server):
    base, b = agent_server
    assert call(base, "/click", {"x": 3, "y": 4})[0] == 200
    assert b.calls[0] == ("move", 3, 4)
    status, body, _ = call(base, "/click", {"x": 999, "y": 4})
    assert status == 400 and "outside" in json.loads(body)["error"]
    assert call(base, "/key", {"combo": "nope"})[0] == 400
    assert call(base, "/nothing", {})[0] == 404


def test_http_focus(agent_server):
    base, _ = agent_server
    status, body, _ = call(base, "/focus", {"title": "galactic"})
    assert status == 200 and json.loads(body)["focused"] == "Galactic Civilizations IV"
    assert call(base, "/focus", {"title": "notepad"})[0] == 400


def test_http_screenshot_max_side(agent_server):
    base, _ = agent_server
    status, body, _headers = call(base, "/screenshot?max_side=32")
    assert status == 200
    img = Image.open(io.BytesIO(body))
    assert max(img.size) == 32


def test_http_batch(agent_server):
    base, b = agent_server
    actions = [
        {"action": "move", "x": 10, "y": 15},
        {"action": "click", "x": 20, "y": 25, "button": "left"},
        {"action": "key", "combo": "enter"},
        {"action": "wait", "seconds": 0.01},
    ]
    status, body, _ = call(base, "/batch", {"actions": actions})
    assert status == 200
    res = json.loads(body)["results"]
    assert len(res) == 4
    assert ("move", 10, 15) in b.calls
    assert ("move", 20, 25) in b.calls
    assert ("key", 0x0D, True) in b.calls


def test_http_state(agent_server):
    base, _ = agent_server
    status, body, _ = call(base, "/state")
    assert status == 200
    data = json.loads(body)
    assert data["game_running"] is True
    assert data["turn"] == 1


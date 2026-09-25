import asyncio
import io

import pytest
from PIL import Image

from harness import mcp_server
from harness.client import AgentClient, AgentError
from harness.imaging import View, render
from harness.session import Session


def png_of(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


# -- imaging ------------------------------------------------------------------


def test_render_downscales_to_max_side_and_maps_back():
    jpeg, view = render(png_of(1920, 1080))
    assert (view.width, view.height) == (1568, 882)
    assert Image.open(io.BytesIO(jpeg)).size == (1568, 882)
    assert view.to_screen(0, 0) == (0, 0)
    assert view.to_screen(784, 441) == (960, 540)


def test_render_small_image_not_upscaled_by_default():
    _, view = render(png_of(800, 600))
    assert (view.width, view.height, view.scale) == (800, 600, 1.0)


def test_render_zoom_upscales_with_offset():
    _, view = render(png_of(200, 100), left=500, top=300, max_upscale=3.0)
    assert (view.width, view.height) == (600, 300)
    assert view.to_screen(300, 150) == (600, 350)


def test_grid_keeps_size():
    jpeg, _ = render(png_of(400, 300), grid=True)
    assert Image.open(io.BytesIO(jpeg)).size == (400, 300)


def test_view_rejects_points_outside_image():
    v = View(0, 0, 1.0, 100, 50)
    with pytest.raises(ValueError):
        v.to_screen(100, 10)


def test_rect_to_screen_clamps_to_view():
    v = View(100, 100, 2.0, 50, 50)
    assert v.rect_to_screen(40, 40, 50, 50) == (180, 180, 20, 20)


# -- client + session against the real agent handler ---------------------------


def test_client_bad_token_raises(agent_server):
    base, _ = agent_server
    with pytest.raises(AgentError, match="401"):
        AgentClient(base, token="nope").health()


def test_client_unreachable_raises():
    with pytest.raises(AgentError, match="cannot reach"):
        AgentClient("http://127.0.0.1:9", token="x", timeout=1).health()


@pytest.mark.parametrize("agent_server", [(3136, 1764)], indirect=True)  # 2x MAX_SIDE
def test_session_click_maps_image_coords_to_screen(agent_server):
    base, backend = agent_server
    s = Session(AgentClient(base, token="sekret"), settle=0)
    _, view = s.screenshot()
    assert view.width == 1568 and view.scale == 2.0
    assert s.click(100, 50) == (200, 100)
    assert backend.calls[0] == ("move", 200, 100)


@pytest.mark.parametrize("agent_server", [(3136, 1764)], indirect=True)
def test_session_zoom_then_click_uses_zoomed_space(agent_server):
    base, _ = agent_server
    s = Session(AgentClient(base, token="sekret"), settle=0)
    s.screenshot()
    _, view = s.zoom(100, 100, 50, 25)  # screen region 200,200 100x50
    assert (view.left, view.top) == (200, 200)
    assert view.width == 300  # upscaled 3x
    assert s.click(150, 75) == (250, 225)


def test_session_saves_screenshots(agent_server, tmp_path):
    base, _ = agent_server
    s = Session(AgentClient(base, token="sekret"), settle=0, save_dir=tmp_path / "shots")
    s.screenshot()
    assert len(list((tmp_path / "shots").glob("*.jpg"))) == 1


# -- MCP layer ----------------------------------------------------------------


def test_mcp_tools_registered():
    tools = asyncio.run(mcp_server.server.list_tools())
    names = {t.name for t in tools}
    assert {"screenshot", "zoom", "click", "hover", "drag", "scroll", "key", "type_text",
            "focus_game", "wait", "status", "list_windows"} <= names
    click = next(t for t in tools if t.name == "click")
    assert set(click.input_schema["required"]) == {"x", "y"}


def test_mcp_click_returns_text_and_image(agent_server, monkeypatch):
    base, backend = agent_server
    monkeypatch.setattr(mcp_server, "_session", Session(AgentClient(base, token="sekret"), settle=0))
    result = asyncio.run(mcp_server.server.call_tool("click", {"x": 5, "y": 6, "wait": 0}))
    blocks = result.content if hasattr(result, "content") else result
    kinds = [b.type for b in blocks]
    assert kinds == ["text", "image"]
    assert ("move", 5, 6) in backend.calls


def test_mcp_errors_are_reported_not_raised(agent_server, monkeypatch):
    base, _ = agent_server
    monkeypatch.setattr(mcp_server, "_session", Session(AgentClient(base, token="sekret"), settle=0))
    result = asyncio.run(mcp_server.server.call_tool("key", {"combo": "hyperkey", "wait": 0}))
    blocks = result.content if hasattr(result, "content") else result
    assert "ERROR" in blocks[0].text and "unknown key" in blocks[0].text

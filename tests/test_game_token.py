"""The game clients use the PC's own token (GAME_AGENT_TOKEN, as set per host) before the shared file."""

from pathlib import Path

from pilot.game import McpGame
from pilot.models import GAMES


def test_mcp_game_takes_the_token_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(McpGame, "_start", lambda self: None)
    (tmp_path / ".agent_token").write_text("shared-token-not-for-this-pc\n")
    monkeypatch.setenv("GAME_AGENT_TOKEN", "own-token-of-this-pc")
    g = McpGame(Path("/bin/true"), tmp_path, "http://pc:8765", tmp_path)
    assert g.token == "own-token-of-this-pc" and g.env["GAME_AGENT_TOKEN"] == "own-token-of-this-pc"


def test_mcp_game_falls_back_to_the_shared_file(tmp_path, monkeypatch):
    monkeypatch.setattr(McpGame, "_start", lambda self: None)
    (tmp_path / ".agent_token").write_text("shared\n")
    monkeypatch.delenv("GAME_AGENT_TOKEN", raising=False)
    assert McpGame(Path("/bin/true"), tmp_path, "http://pc:8765", tmp_path).token == "shared"


def test_civ6_is_a_game_the_settings_accept():
    assert "civ6" in GAMES

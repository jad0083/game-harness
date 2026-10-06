"""The controller is started with the learned directory of the data directory (data platform, ruling 8)."""

from pathlib import Path

from pilot.civ6 import ControllerCiv6
from pilot.game import McpGame


def test_mcp_game_passes_learned_before_the_subcommand(monkeypatch, tmp_path):
    monkeypatch.setattr(McpGame, "_start", lambda self: None)
    g = McpGame(Path("/bin/ctl"), tmp_path / "corpus", "http://pc:8765", tmp_path, token="t",
                learned=tmp_path / "data/learned/galciv4")
    assert g.cmd == ["/bin/ctl", "--corpus", str(tmp_path / "corpus"),
                     "--learned", str(tmp_path / "data/learned/galciv4"), "mcp"]


def test_civ6_passes_learned_before_each_subcommand(tmp_path):
    g = ControllerCiv6(Path("/bin/ctl"), tmp_path / "corpus", "http://pc:8765", tmp_path, token="t" * 32,
                       learned=tmp_path / "data/learned/civ6")
    assert g.base == ["/bin/ctl", "--corpus", str(tmp_path / "corpus"),
                      "--learned", str(tmp_path / "data/learned/civ6")]


def test_without_learned_the_commands_are_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(McpGame, "_start", lambda self: None)
    assert McpGame(Path("/bin/ctl"), tmp_path, "http://pc:8765", tmp_path, token="t").cmd == [
        "/bin/ctl", "--corpus", str(tmp_path), "mcp"]
    assert ControllerCiv6(Path("/bin/ctl"), tmp_path, "http://pc:8765", tmp_path, token="t" * 32).base == [
        "/bin/ctl", "--corpus", str(tmp_path)]

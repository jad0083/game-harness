"""The controller is started with the learned directory of the data directory (data platform, ruling 8)."""

from pathlib import Path

import pytest

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


class _Started(Exception):
    """Raised by the fake game: the run stops where the controller would start."""


@pytest.mark.parametrize("game", ["galciv4", "stellaris", "civ6"])
def test_the_first_controller_of_a_run_starts_on_the_current_overlay(monkeypatch, tmp_path, game):
    """cli.run renders <data>/learned/<game>/ from the run's store before it constructs the game: McpGame
    starts `game-controller mcp` in its constructor, which read the overlay an earlier run left when only
    the Pilot or Governor (constructed after the game) rendered it."""
    from pilot import civ6, cli
    from pilot import game as game_module
    from pilot.config import Settings
    from pilot.store import open_store

    s = Settings(runs_dir=tmp_path / "data", game=game)
    open_store(s.runs_dir)._exec(
        "INSERT INTO learned_notes(game, kind, text, why, model, run_id, t) VALUES (?,?,?,?,?,?,?)",
        (game, "rule", "Take the artifact while the treasury is above 500.", "recurring", "m", "r0", "2026-10-05"))
    s.learned_dir.mkdir(parents=True)
    (s.learned_dir / "strategy.md").write_text("# Learned strategy rules\n\nstale, from an earlier run\n")
    seen = {}

    def fake_game(*_a, learned=None, **_kw):
        seen["learned"] = learned
        seen["manifest"] = (learned / "manifest.toml").exists()
        seen["strategy"] = (learned / "strategy.md").read_text()
        raise _Started

    if game == "civ6":
        monkeypatch.setattr(civ6, "ControllerCiv6", fake_game)
    else:
        monkeypatch.setattr(game_module, "McpGame", fake_game)
    with pytest.raises(_Started):
        cli.run(s, None)
    assert seen["learned"] == s.learned_dir
    assert seen["manifest"], "the overlay manifest exists before the controller starts"
    assert "Take the artifact" in seen["strategy"] and "stale" not in seen["strategy"]

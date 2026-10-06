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


CONTROLLER = Path(__file__).resolve().parents[1] / "target/release/game-controller"


@pytest.mark.skipif(not CONTROLLER.exists(), reason="controller not built: cargo build --release -p game-controller")
def test_the_built_controller_reads_an_overlay_the_pilot_wrote(tmp_path):
    """The overlay learned_files writes is read by the real controller with --learned: its TOML parses (a
    description with a quote and U+007F), its rule is a searchable note, and its screen joins the manifest."""
    import io
    import json
    import os
    import re
    import shutil
    import subprocess

    from PIL import Image

    from pilot.config import REPO
    from pilot.learned_files import write_learned_dir
    from pilot.learning import MATCH_THRESHOLD, ScreenAction
    from pilot.store import open_store

    corpus = tmp_path / "galciv4"
    shutil.copytree(REPO / "corpora/galciv4", corpus, ignore=shutil.ignore_patterns("learned"))
    st = open_store(tmp_path / "data")
    png = io.BytesIO()
    Image.new("RGB", (40, 12), (200, 30, 30)).save(png, "PNG")
    st._exec("INSERT INTO learned_screens(game, name, description, roi, threshold, auto_dismiss, action, png,"
             " learned_by, run_id, t, disabled_reason) VALUES (?,?,?,?,?,1,?,?,?,?,?,NULL)",
             ("galciv4", "quoted_popup", 'The "Zorblax" popup\x7f closes with c', "[0.4, 0.3, 0.0255, 0.0136]",
              MATCH_THRESHOLD, json.dumps(ScreenAction(key="c").stored()), png.getvalue(), "google:m", "r1",
              "2026-10-05T12:00:00"))
    st._exec("INSERT INTO learned_notes(game, kind, text, why, model, run_id, t) VALUES (?,?,?,?,?,?,?)",
             ("galciv4", "rule", "Sell the zorblax crystals before the quasar storm reaches the colony.",
              "recurring", "google:m", "r1", "2026-10-05"))
    learned = tmp_path / "data/learned/galciv4"
    write_learned_dir(st, "galciv4", learned)
    assert "\\u007f" in (learned / "manifest.toml").read_text() and (learned / "templates/quoted_popup.png").exists()
    env = {k: v for k, v in os.environ.items() if k != "GAME_RESOLUTION"}

    def controller(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(CONTROLLER), "--corpus", str(corpus), *args], env=env, capture_output=True,
                              text=True, timeout=60, check=False)

    found = controller("--learned", str(learned), "corpus", "search", "zorblax quasar storm")
    assert found.returncode == 0, found.stderr
    assert re.search(r"^learned:strategy#\d+ .*zorblax", found.stdout, re.MULTILINE | re.IGNORECASE), found.stdout
    with_overlay, without = controller("--learned", str(learned), "corpus"), controller("corpus")
    assert with_overlay.returncode == 0 and without.returncode == 0, with_overlay.stderr + without.stderr

    def screens(out: str) -> int:
        return int(re.search(r"(\d+) screens", out).group(1))
    assert screens(with_overlay.stdout) == screens(without.stdout) + 1, with_overlay.stdout

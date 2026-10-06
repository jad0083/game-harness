"""pilot export (data platform design, ruling 10): learned files and journals written to a directory."""

from __future__ import annotations

from pilot import cli
from pilot.config import Settings
from pilot.events import EventLog
from pilot.export import export
from pilot.learning import Journal, LearnedStore
from pilot.store import open_store


def _seed(tmp_path):
    corpus = tmp_path / "corpora/civ6"
    corpus.mkdir(parents=True)
    (corpus / "manifest.toml").write_text("")
    st = open_store(tmp_path / "data")
    LearnedStore(st, "civ6", corpus, tmp_path / "data/learned/civ6", "m", "r").add_rule(
        "When a city is threatened, buy a defender at once.", "T45 loss")
    Journal(st, "civ6", "m", campaign=lambda: "civ6/alexander_1").note("Settled Pella", "T5")
    return st


def test_export_writes_learned_files_and_journals(tmp_path):
    st = _seed(tmp_path)
    written = export(st, tmp_path / "out")
    assert (tmp_path / "out/civ6/learned/strategy.md").read_text().count("buy a defender") == 1
    assert (tmp_path / "out/civ6/learned/manifest.toml").exists()
    j = (tmp_path / "out/journals/civ6__alexander_1.md").read_text()
    assert "**T5**: Settled Pella" in j and j.startswith("# Journal: civ6/alexander_1")
    assert all(p.is_file() for p in written)


def test_the_export_subcommand_writes_the_files(tmp_path, monkeypatch, capsys):
    _seed(tmp_path)
    monkeypatch.setenv("PILOT_DATA_DIR", str(tmp_path / "data"))
    assert cli.main(["export", "--to", str(tmp_path / "out"), "--game", "civ6"]) == 0
    assert (tmp_path / "out/civ6/learned/manifest.toml").exists()
    assert "exported" in capsys.readouterr().out


def test_the_run_end_export_writes_when_a_directory_is_set(tmp_path):
    _seed(tmp_path)
    log = EventLog(tmp_path / "data", "r1", "m")
    cli._export_at_end(log, Settings(runs_dir=tmp_path / "data", game="civ6", export_dir=tmp_path / "out"))
    assert (tmp_path / "out/civ6/learned/manifest.toml").exists()


def test_no_export_directory_means_no_export(tmp_path):
    _seed(tmp_path)
    log = EventLog(tmp_path / "data", "r1", "m")
    cli._export_at_end(log, Settings(runs_dir=tmp_path / "data", game="civ6"))
    assert not (tmp_path / "out").exists()


def test_a_failed_run_end_export_is_reported_not_raised(tmp_path):
    _seed(tmp_path)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    log = EventLog(tmp_path / "data", "r1", "m")
    cli._export_at_end(log, Settings(runs_dir=tmp_path / "data", game="civ6", export_dir=blocker / "sub"))
    errs = [e for e in log.recent if e["kind"] == "briefing_error"]
    assert errs and "export failed" in errs[0]["error"]

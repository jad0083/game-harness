"""Settings, model usage and standing orders in the store (data platform design, ruling 4)."""

from __future__ import annotations

import time

from pilot import modelguard as G
from pilot.cli import main
from pilot.models import load_prefs, save_prefs
from pilot.store import open_store


def test_prefs_round_trip_through_the_settings_row(tmp_path):
    save_prefs(tmp_path, models=[{"model": "google:gemini-pro-latest", "thinking": "high"}], rotate=False, game="civ6")
    assert load_prefs(tmp_path)["game"] == "civ6" and load_prefs(tmp_path)["models"][0]["model"] == "google:gemini-pro-latest"
    assert not (tmp_path / "pilot-settings.json").exists()
    row = open_store(tmp_path).query("SELECT key FROM settings")
    assert row == [{"key": "prefs"}]


def test_prefs_row_that_is_not_a_json_object_counts_as_no_prefs(tmp_path):
    st = open_store(tmp_path)
    for bad in ("not json", "[1, 2]", "5"):
        st._exec("INSERT INTO settings(key, value, changed_by, t) VALUES ('prefs', ?, NULL, 0) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (bad,))
        assert load_prefs(tmp_path) == {}


def test_prefs_get_prints_only_the_value(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PILOT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PILOT_RUNS_DIR", raising=False)
    assert main(["prefs", "--get", "game"]) == 0
    assert capsys.readouterr().out == "\n"
    save_prefs(tmp_path, game="civ6")
    assert main(["prefs", "--get", "game"]) == 0
    assert capsys.readouterr().out == "civ6\n"


def test_prefs_get_without_a_store_prints_nothing_and_creates_none(tmp_path, monkeypatch, capsys):
    """A read for scripts: deploy-pilot.sh asks before any store exists, and a test once made the repo's runs/pilot.db."""
    monkeypatch.delenv("PILOT_RUNS_DIR", raising=False)
    for data in (tmp_path / "absent", tmp_path / "empty"):
        if data.name == "empty":
            data.mkdir()
        monkeypatch.setenv("PILOT_DATA_DIR", str(data))
        assert main(["prefs", "--get", "game"]) == 0
        assert capsys.readouterr().out == "\n"
        assert not (data / "pilot.db").exists()
    assert not (tmp_path / "absent").exists()


def test_model_usage_counts_live_in_the_store(tmp_path):
    st = open_store(tmp_path)
    h = G.ModelHealth(G.GuardConfig(usage_store=st))
    for _ in range(3):
        h.count("google:gemini-pro-latest")
    again = G.ModelHealth(G.GuardConfig(usage_store=st))
    assert again.today("google:gemini-pro-latest") == 3
    rows = st.query("SELECT model, count FROM model_usage")
    assert rows == [{"model": "google:gemini-pro-latest", "count": 3}]
    assert not (tmp_path / "model-usage.json").exists()


def test_usage_older_than_seven_days_is_dropped(tmp_path):
    st = open_store(tmp_path)
    st._exec("INSERT INTO model_usage(day, model, count) VALUES ('2020-01-01', 'm', 5)")
    G.ModelHealth(G.GuardConfig(usage_store=st), clock=time.time).count("m")
    assert st.query("SELECT count(*) AS n FROM model_usage WHERE day='2020-01-01'")[0]["n"] == 0


def test_two_processes_counting_the_same_model_keep_both_counts(tmp_path):
    st = open_store(tmp_path)
    a = G.ModelHealth(G.GuardConfig(usage_store=st))
    b = G.ModelHealth(G.GuardConfig(usage_store=st))      # a second process: its own memory, the same table
    for _ in range(5):
        a.count("x")
    b.count("y")
    b.count("x")
    rows = {r["model"]: r["count"] for r in st.query("SELECT model, count FROM model_usage")}
    assert rows == {"x": 6, "y": 1}
    assert b.today("x") == 6, "the store's value becomes the in-memory count"


def test_prefs_get_prints_json_for_values_that_are_not_strings(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PILOT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PILOT_RUNS_DIR", raising=False)
    save_prefs(tmp_path, months=12, rotate=True)
    assert main(["prefs", "--get", "months"]) == 0
    assert capsys.readouterr().out == "12\n"
    assert main(["prefs", "--get", "rotate"]) == 0
    assert capsys.readouterr().out == "true\n"


def test_save_prefs_reads_and_writes_in_one_transaction(tmp_path):
    save_prefs(tmp_path, game="civ6")
    st = open_store(tmp_path)
    seen = []
    real = st.transaction

    def spy():
        seen.append(1)
        return real()
    st.transaction = spy
    save_prefs(tmp_path, speed="fast")
    assert seen and load_prefs(tmp_path)["game"] == "civ6" and load_prefs(tmp_path)["speed"] == "fast"

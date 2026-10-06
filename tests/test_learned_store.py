"""Learned knowledge and journals in the store (data platform design, rulings 4, 7): the same
LearnedStore behaviour, the files the controller reads generated from the store, journals as rows."""

from __future__ import annotations

import io
import threading
import tomllib

from PIL import Image

from pilot.learned_files import write_learned_dir
from pilot.learning import Journal, LearnedStore, LearningRejected, ScreenAction
from pilot.store import open_store


def jpeg(color=(10, 20, 30), title: str | None = None) -> bytes:
    img = Image.new("RGB", (1568, 882), color)
    if title:
        for x in range(600, 980):
            for y in range(300, 330):
                img.putpixel((x, y), (250, 250, 250) if (x // 7 + y // 5) % 2 else (5, 5, 5))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=95)
    return b.getvalue()


def make(tmp_path, corpus=None):
    corpus = corpus or tmp_path / "corpora/galciv4"
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "manifest.toml").write_text("[screens.gnn_news]\ndescription = 'x'\n")
    st = open_store(tmp_path / "data")
    return st, LearnedStore(st, "galciv4", corpus, tmp_path / "data/learned/galciv4", "google:m", "run1")


def test_rules_and_controls_are_rows_and_render_as_before(tmp_path):
    _st, ls = make(tmp_path)
    ls.add_rule("When offered an artifact or 200 credits, take the artifact while rich.", "recurring")
    ls.add_control("Key n puts a warship on Sentry.", "tooltip")
    md = ls.rules_markdown()
    assert md.startswith("# Learned strategy rules") and "take the artifact" in md and "_why:_ recurring" in md
    out = tmp_path / "data/learned/galciv4"
    assert "take the artifact" in (out / "strategy.md").read_text() and "Sentry" in (out / "controls.md").read_text()
    with __import__("pytest").raises(LearningRejected):
        ls.add_rule("short", "x")


def test_a_learned_screen_is_a_row_with_its_png_and_the_overlay_follows(tmp_path):
    st, ls = make(tmp_path)
    ls.remember_frame(jpeg((10, 20, 30)))
    ls.add_screen("colony_prompt", jpeg(title="x"), (576, 290, 992, 330), ScreenAction(key="c"), "d", "e")
    row = st.query("SELECT name, auto_dismiss, length(png) AS n FROM learned_screens WHERE game='galciv4'")[0]
    assert row["name"] == "colony_prompt" and row["auto_dismiss"] == 1 and row["n"] > 100
    out = tmp_path / "data/learned/galciv4"
    man = tomllib.loads((out / "manifest.toml").read_text())
    assert man["screens"]["colony_prompt"]["template"] == "templates/colony_prompt.png"
    assert man["screens"]["colony_prompt"]["dismiss_key"] == "c" and (out / "templates/colony_prompt.png").exists()
    for _ in range(3):
        ls.record_dismissals(["colony_prompt"], advanced=False)
    man = tomllib.loads((out / "manifest.toml").read_text())
    assert man["screens"]["colony_prompt"]["auto_dismiss"] is False and "disabled_reason" in man["screens"]["colony_prompt"]


def test_episodes_recall_and_the_corpora_stay_untouched(tmp_path):
    corpus = tmp_path / "corpora/galciv4"
    _st, ls = make(tmp_path, corpus)
    ls.add_episode("Event: Space Creature Migration", "Protected the creatures", "resolved", "Jul 2333")
    ls.add_episode("Event: Space Creature Migration", "Protected the creatures", "resolved", "Jul 2334")
    assert ls.recall("space creature")[0]["decision"] == "Protected the creatures"
    assert ls.repeated("Event: Space Creature Migration") == 2
    assert not (corpus / "learned").exists(), "nothing is written into the corpora (ruling 3)"


def test_fresh_store_generates_an_empty_overlay(tmp_path):
    st = open_store(tmp_path / "data")
    write_learned_dir(st, "civ6", tmp_path / "data/learned/civ6")
    man = tomllib.loads((tmp_path / "data/learned/civ6/manifest.toml").read_text())
    assert man.get("screens", {}) == {}


def test_the_journal_is_rows_per_campaign(tmp_path):
    st = open_store(tmp_path / "data")
    j = Journal(st, "civ6", "google:m", campaign=lambda: "civ6/alexander_1")
    j.note("Settled Pella", "T5")
    rows = st.query("SELECT campaign_id, game, date, text FROM journal")
    assert rows == [{"campaign_id": "civ6/alexander_1", "game": "civ6", "date": "T5", "text": "Settled Pella"}]


def test_the_learned_dir_holds_only_what_the_store_has(tmp_path):
    """A regenerated learned directory holds only what the store has: a stale file goes, and no temporary
    temporary file is left behind (ruling 7)."""
    _st, ls = make(tmp_path)
    out = tmp_path / "data/learned/galciv4"
    (out / "templates").mkdir(exist_ok=True)
    (out / "templates/stale.png").write_bytes(b"x")
    ls.add_control("Key n puts a warship on Sentry.", "tooltip")
    assert not (out / "templates/stale.png").exists() and "Sentry" in (out / "controls.md").read_text()
    assert sorted(p.name for p in out.parent.iterdir()) == [".lock", "galciv4"]
    assert not list(out.rglob("*.tmp"))


def test_rules_learned_from_several_threads_all_reach_the_overlay(tmp_path):
    """The governor learns from its decision, review and chat threads: every swap of the directory
    completes and the last one holds every rule."""
    _st, ls = make(tmp_path)
    errors: list[Exception] = []

    def learn(i: int) -> None:
        try:
            ls.add_rule(f"Rule number {i}: when this happens, do that.", "threads")
        except Exception as e:  # noqa: BLE001 - collected for the assertion
            errors.append(e)

    threads = [threading.Thread(target=learn, args=(i,)) for i in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    out = tmp_path / "data/learned/galciv4"
    text = (out / "strategy.md").read_text()
    assert errors == [] and all(f"Rule number {i}:" in text for i in range(8))
    assert sorted(p.name for p in out.parent.iterdir()) == [".lock", "galciv4"]
    assert not list(out.rglob("*.tmp"))


def test_a_reader_never_sees_a_missing_or_dangling_manifest_during_rewrites(tmp_path):
    """The controller reads the directory while the pilot rewrites it (controller ruling R4)."""
    _st, ls = make(tmp_path)
    ls.remember_frame(jpeg((10, 20, 30)))
    out = tmp_path / "data/learned/galciv4"
    problems: list[str] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            try:
                man = tomllib.loads((out / "manifest.toml").read_text())
            except FileNotFoundError:
                problems.append("manifest missing")
                continue
            except tomllib.TOMLDecodeError as e:
                problems.append(f"manifest unparseable: {e}")
                continue
            for name, sc in man.get("screens", {}).items():
                if not (out / sc["template"]).is_file():
                    problems.append(f"{name}: template missing")

    t = threading.Thread(target=reader)
    t.start()
    try:
        ls.add_screen("colony_prompt", jpeg(title="x"), (576, 290, 992, 330), ScreenAction(key="c"), "d", "e")
        for i in range(50):
            ls.add_rule(f"Rule number {i}: when this happens, do that.", "poll")
    finally:
        stop.set()
        t.join()
    assert problems == []


def test_a_malformed_row_keeps_the_previous_manifest_and_names_the_game(tmp_path):
    import pytest
    st, ls = make(tmp_path)
    ls.add_control("Key n puts a warship on Sentry.", "tooltip")
    ls.remember_frame(jpeg((10, 20, 30)))
    ls.add_screen("colony_prompt", jpeg(title="x"), (576, 290, 992, 330), ScreenAction(key="c"), "d", "e")
    out = tmp_path / "data/learned/galciv4"
    before = (out / "manifest.toml").read_bytes()
    st._exec("UPDATE learned_screens SET threshold=NULL WHERE game='galciv4'")
    with pytest.raises(ValueError, match="galciv4"):
        write_learned_dir(st, "galciv4", out)
    assert (out / "manifest.toml").read_bytes() == before
    assert "Sentry" in (out / "controls.md").read_text() and (out / "templates/colony_prompt.png").exists()


def test_files_the_render_no_longer_produces_are_removed_and_others_left_alone(tmp_path):
    st, _ls = make(tmp_path)
    out = tmp_path / "data/learned/galciv4"
    (out / "templates").mkdir(parents=True, exist_ok=True)
    (out / "templates/gone.png").write_bytes(b"x")
    (out / "notes.txt").write_text("mine")
    write_learned_dir(st, "galciv4", out)
    assert not (out / "templates/gone.png").exists() and (out / "notes.txt").read_text() == "mine"

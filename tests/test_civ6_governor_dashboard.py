"""What the Civ VI governor publishes for the dashboard: a category per stop (ruling 7)."""

from __future__ import annotations

from test_civ6_governor import (  # noqa: F401 - setup is a fixture
    FIXTURE,
    INDEX,
    SHOT,
    T0,
    falls,
    governor,
    orders_model,
    run_until_attention,
    setup,
    stand_game,
    stand_governor,
)

from pilot.civ6 import FakeCiv6


def category(g) -> str:
    return (g.log.state.info.get("attention") or {}).get("category", "")


def stops(g) -> list[str]:
    return [e.get("category") for e in g.log.recent if e["kind"] == "needs_attention"]


def test_autoplay_that_was_refused_is_transient(setup):  # noqa: F811
    g = governor(setup, FakeCiv6(FIXTURE, index=INDEX, start_fails=True), orders_model([]))
    run_until_attention(g)
    assert stops(g)[0] == "transient"


def test_autoplay_that_never_ran_is_transient(setup):  # noqa: F811
    g = governor(setup, FakeCiv6(FIXTURE, index=INDEX, never_starts=True), orders_model([]))
    run_until_attention(g)
    assert stops(g)[0] == "transient"


def test_a_turn_that_never_ends_is_the_screen(setup):  # noqa: F811
    game = FakeCiv6(FIXTURE, index=INDEX)
    game.autoplay_status = lambda: {"ok": True, "active": True, "turn": FIXTURE["turn"]}
    g = governor(setup, game, orders_model([]))
    run_until_attention(g)
    assert stops(g)[0] == "screen"


def test_no_snapshot_between_turns_is_unreachable(setup):  # noqa: F811
    game = FakeCiv6(FIXTURE, index=INDEX)
    real, n = game.snapshot, {"calls": 0}

    def snapshot():
        n["calls"] += 1
        if n["calls"] > 2:
            raise TimeoutError("tuner did not answer")
        return real()
    game.snapshot = snapshot
    g = governor(setup, game, orders_model([]))
    run_until_attention(g)
    assert stops(g)[0] == "unreachable"


def test_another_game_loaded_is_game_changed(setup):  # noqa: F811
    game = FakeCiv6(FIXTURE, index=INDEX, events={FIXTURE["turn"] + 1: lambda st: st.update(map_seed=999)})
    g = governor(setup, game, orders_model([]))
    run_until_attention(g)
    assert stops(g)[0] == "game_changed"


def test_a_start_that_times_out_is_unreachable(setup):  # noqa: F811
    game = FakeCiv6(FIXTURE, index=INDEX)
    game.snapshot = lambda: (_ for _ in ()).throw(TimeoutError("timed out"))
    g = governor(setup, game, orders_model([]))
    run_until_attention(g)
    assert stops(g)[0] == "unreachable"


def test_a_start_the_game_refuses_is_control_failed(setup):  # noqa: F811
    game = FakeCiv6(FIXTURE, index=INDEX)
    game.snapshot = lambda: (_ for _ in ()).throw(RuntimeError("game-controller civ6 snapshot refused: no game loaded"))
    g = governor(setup, game, orders_model([]))
    run_until_attention(g)
    assert stops(g)[0] == "control_failed"


def test_the_civ6_screen_is_captured_through_the_controller(tmp_path):
    """Ruling 7: "Capture the game screen" and the attention card need Civ VI frames; the capture is the
    agent's screenshot (read-only: no input, no focus change), and a failure gives no frame."""
    from pilot.civ6 import ControllerCiv6
    stub = tmp_path / "game-controller"
    args = tmp_path / "args.txt"
    stub.write_text(f"""#!/bin/sh
printf '%s\\n' "$@" >> {args}
if [ "$3" = screenshot ] && [ "$4" = --out ]; then printf '\\377\\330jpeg' > "$5"; echo "Screenshot captured"; exit 0; fi
exit 1
""")
    stub.chmod(0o755)
    game = ControllerCiv6(stub, tmp_path / "civ6", "http://pc:8765", tmp_path, token="t" * 32)
    shot = game.screenshot()
    assert shot.image == b"\xff\xd8jpeg"
    assert args.read_text().splitlines()[2] == "screenshot"
    stub.write_text("#!/bin/sh\nexit 1\n")
    assert getattr(game.screenshot(), "image", None) is None


# ---- the Orders tab's data (rulings 12, 21, 22): reserves, the last stand's state, popups, game health ----



def test_the_governor_publishes_the_reserves_against_the_treasury(setup):  # noqa: F811
    """Ruling 21: gold and faith, what purchases keep back and why, at the snapshot's date."""
    game = FakeCiv6({**FIXTURE, "gold": 412, "faith": 90, "yields": {**FIXTURE["yields"], "gold": -1.6}}, index=INDEX)
    g = governor(setup, game, orders_model([]))
    g.run(max_decisions=1)
    r = g.log.state.info["reserves"]
    assert r["gold"] == 412 and r["gold_keep"] == 46 and "deficit" in r["gold_rule"]
    assert r["faith"] == 90 and isinstance(r["faith_keep"], int) and r["date"].startswith("T")
    assert r["in_danger"] == []


def test_the_last_stand_state_is_always_published(setup):  # noqa: F811
    """Ruling 22: armed or off, its maximum, the streak and why it turned itself off."""
    g = stand_governor(setup, stand_game(), on=False)
    assert g.log.state.info["last_stand"] == {"on": False, "max": 3, "in_a_row": 0, "off_reason": "", "active": None}
    g2 = stand_governor(setup, stand_game(events={T0 + 1: falls}, stand=[SHOT] * 5, stand_ignored=True), every=4)
    g2.run(max_decisions=3)
    ls = g2.log.state.info["last_stand"]
    assert ls["on"] is True and ls["off_reason"].startswith("the first action of 2 stands did not take")
    assert ls["active"] is None and ls["in_a_row"] >= 1


def test_popups_quieted_once_per_library_install(setup):  # noqa: F811
    """Ruling 22: the controller's reply lists the quieted popups once per load; the governor emits
    `popups_quieted` once with the entries and the turn, and game health carries it."""
    game = FakeCiv6(FIXTURE, index=INDEX)
    entries = ["WonderBuiltPopup.OnWonderCompleted QUIET", "NaturalWonderPopup.OnNaturalWonderRevealed QUIET",
               "ProjectBuiltPopup.OnProjectComplete failed: timed out"]
    game.popups_quieted = list(entries)
    g = governor(setup, game, orders_model([]))
    g.run(max_decisions=2)
    evs = [e for e in g.log.recent if e["kind"] == "popups_quieted"]
    assert len(evs) == 1 and evs[0]["entries"] == entries and evs[0]["turn"] == T0
    health = g.log.state.info["game_health"]
    assert health["popups"] == {"quieted": 2, "total": 3, "turn": T0, "failed": ["ProjectBuiltPopup.OnProjectComplete"]}


def test_game_health_counts_tuner_timeouts_and_the_last_turn(setup):  # noqa: F811
    game = FakeCiv6(FIXTURE, index=INDEX)
    game.recent_calls = [True, False, False, True, False]            # True: the call timed out
    g = governor(setup, game, orders_model([]))
    g.run(max_decisions=2)
    health = g.log.state.info["game_health"]
    assert (health["timeouts"], health["calls"]) == (2, 5)
    assert isinstance(health["last_turn_s"], (int, float))


def test_the_controller_counts_its_calls_and_keeps_the_quieted_popups(tmp_path):
    from pilot.civ6 import ControllerCiv6
    stub = tmp_path / "game-controller"
    stub.write_text("""#!/bin/sh
case "$4" in
  snapshot) echo '{"ok":true,"turn":7,"cities":[],"popups_quieted":["A.b QUIET"]}' ;;
  autoplay-status) echo 'Error: Failed /tuner/lua: operation timed out' >&2; exit 1 ;;
esac
""")
    stub.chmod(0o755)
    game = ControllerCiv6(stub, tmp_path / "civ6", "http://pc:8765", tmp_path, token="t" * 32)
    game.snapshot()
    assert game.popups_quieted == ["A.b QUIET"]
    try:
        game.autoplay_status()
    except RuntimeError:
        pass
    assert list(game.recent_calls) == [False, True]

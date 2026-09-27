"""What the Civ VI governor publishes for the dashboard: a category per stop (ruling 7)."""

from __future__ import annotations

from test_civ6_governor import FIXTURE, INDEX, governor, orders_model, run_until_attention, setup  # noqa: F401

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

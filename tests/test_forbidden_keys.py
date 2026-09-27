"""The pilot never presses the Windows key or combos that leave or close the game."""

import pytest


@pytest.mark.parametrize("combo", ["win", "win+r", "Win + X", "lwin+d", "rwin", "super+l", "ctrl+win+d",
                                   "alt+f4", "ALT+F4", "ctrl+alt+delete", "alt+ctrl+del", "ctrl+shift+esc",
                                   "alt+tab", "alt+shift+tab", "ctrl+esc", "alt+esc", "delete", "del"])
def test_forbidden_combos(combo):
    from pilot.learning import is_forbidden_key
    assert is_forbidden_key(combo)


@pytest.mark.parametrize("combo", ["tab", "esc", "ctrl+s", "n", "f1", "shift+tab", "alt+s", "space"])
def test_game_combos_allowed(combo):
    from pilot.learning import is_forbidden_key
    assert not is_forbidden_key(combo)

"""What the governors publish for the dashboard (docs/design/2026-09-27-dashboard-v2-design.md): the
fields the page reads from /status and the events it turns into sentences."""

from __future__ import annotations

from dataclasses import replace

from test_governor import _strategist, briefing, decisions, setup  # noqa: F401 - setup is a fixture

from pilot.game import FakeStellaris
from pilot.governor import Governor


def test_a_skipped_review_says_when_the_next_one_may_run(setup):  # noqa: F811
    """Ruling 16: skipped reviews are listed with the next eligible date in game units."""
    s, log = setup
    s2 = replace(s, decide_every_months=1, retro_every=0)
    s2.__class__ = s.__class__
    game = FakeStellaris([briefing(f"2200.{i:02d}.01") for i in range(1, 9)])
    choices = ("tech_rush", "expand", "diplomacy_first", "tech_rush", "expand", "diplomacy_first", "tech_rush", "expand")
    g = Governor(s2, game, log, model=decisions(*choices), role_models={"strategy": _strategist([])})
    g.run(max_decisions=8)
    skips = [e for e in log.recent if e["kind"] == "strategy_review_skipped"]
    assert skips
    for e in skips:
        assert e["date"].startswith("2200.") and e["next_after"] == g._last_event_review_month + 12

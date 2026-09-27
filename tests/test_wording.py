"""cause(): machine text cut to one line a person can act on (docs/design/2026-09-27-dashboard-v2-design.md,
ruling 30); the raw text stays one disclosure away on the page."""

from __future__ import annotations

import pytest

from pilot.wording import cause

TUNER_CHAIN = ("Error: Failed /tuner/lua\n\nCaused by:\n    0: error sending request for url "
               "(http://192.168.1.77:8765/tuner/lua)\n    1: operation timed out")


@pytest.mark.parametrize(("raw", "one_line"), [
    (TUNER_CHAIN, "the game's tuner did not answer (timed out)"),
    ("autoplay at T57: RuntimeError: game-controller civ6 autoplay failed (exit 1): " + TUNER_CHAIN,
     "the game's tuner did not answer (timed out)"),
    (("ModelHTTPError: status_code: 503, model_name: gemini-3.8-flash, body: {'error': {'code': 503, "
      "'message': 'This model is currently experiencing high demand.'}}"), "overloaded (503)"),
    ("model gemini-3.8-flash answered 503", "overloaded (503)"),
    ("ModelHTTPError: status_code: 429, model_name: m, body: RESOURCE_EXHAUSTED", "rate limited (429)"),
    ("ModelHTTPError: status_code: 400, body: Your credit balance is too low to access the Anthropic API",
     "billing: credit balance too low"),
    ("ModelHTTPError: status_code: 401, body: invalid x-api-key", "the provider refused the key (401)"),
    ("URLError: <urlopen error [Errno 111] Connection refused>", "the PC's agent refused the connection (is it running?)"),
    ("URLError: <urlopen error timed out>", "the PC's agent did not answer (timed out)"),
    ("Error: Failed /files/read\n\nCaused by:\n    0: status 404\n    1: no such save folder", "no such save folder"),
    ("RuntimeError: no answer within 4 model calls; no orders given", "no answer within 4 model calls; no orders given"),
    ("Civ6Stuck: autoplay did not start at T57 (still inactive after 21 s)",
     "autoplay did not start at T57 (still inactive after 21 s)"),
    ("value 405.92577500000004 out of range", "value 405.9 out of range"),
    ("", ""),
])
def test_cause_cuts_machine_text_to_one_line(raw, one_line):
    assert cause(raw) == one_line

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


# ---- triggers (ruling 28): the raw trigger becomes a category and a few words ---------------------------

from pilot.wording import fate, trigger

NAMES = {"GREAT_PERSON_CLASS_SCIENTIST": "Great Scientist", "BUILDING_PYRAMIDS": "Pyramids"}


@pytest.mark.parametrize(("raw", "category", "text"), [
    ("scheduled (5 turns)", "scheduled", "Scheduled"),
    ("scheduled (12 months)", "scheduled", "Scheduled"),
    ("start of run", "start", "Start of run"),
    ("urgent: city threatened: Chengdu (2 enemy units near, under siege)", "city threatened", "City threatened: Chengdu"),
    ("urgent: city falling: Chengdu (garrison 40/200, no walls, 1 unit(s) next to it that can take it)",
     "city threatened", "City falling: Chengdu"),
    ("urgent: city lost: Xian", "city lost", "City lost: Xian"),
    ("urgent: new war: Germany is at war with us", "war", "War: Germany"),
    ("urgent: new war: Tzynn Empire (we are defender)", "war", "War: Tzynn Empire"),
    ("urgent: great person race lost: GREAT_PERSON_CLASS_SCIENTIST", "race lost", "Great Scientist race lost"),
    ("urgent: wonder race lost: BUILDING_PYRAMIDS in Beijing", "race lost", "Pyramids race lost"),
    ("urgent: milestone missed: science techs_known", "milestone missed", "Milestone missed: science"),
    ("urgent: gold below the reserve: 12 < 30", "gold below reserve", "Gold below the reserve"),
    ("urgent: city threatened: Chengdu (2 enemy units near); gold below the reserve: 12 < 30", "city threatened",
     "City threatened: Chengdu, and 1 more"),
    ("urgent: military fell: 1000 -> 400", "military fell", "Military fell"),
    ("urgent: falling behind other empires in pops (90 vs median 200)", "falling behind", "Falling behind in pops"),
    ("urgent: energy net turned negative (-3.5/month)", "deficit", "Energy income negative"),
    ("human request: hold the line", "you", "Your request"),
    ("human override", "you", "Your override"),
    ("something new", "other", "Something new"),
])
def test_a_trigger_reads_as_a_category_in_words(raw, category, text):
    t = trigger(raw, NAMES.get)
    assert (t["category"], t["text"]) == (category, text)
    assert t["urgent"] is raw.startswith("urgent:")


# ---- order fates (ruling 28): symbols plus words, never colour alone ------------------------------------

@pytest.mark.parametrize(("apply_outcome", "result", "key", "symbol"), [
    ("stuck", None, "open", "⋯"),
    ("stuck", "completed", "held", "✓"),
    ("stuck", "held", "held", "✓"),
    ("stuck", "overridden", "replaced", "↺"),
    ("refused: over the 283 faith allowed", None, "refused", "✕"),
    ("refused by the game: not enough gold", None, "refused", "✕"),
    ("stuck", "refused", "refused", "✕"),
    ("unknown: no reply (TimeoutError); research tech:writing", None, "noreply", "?"),
    ("stuck", "lost", "noreply", "?"),
    ("stuck", "invalidated", "gone", "–"),
    ("stuck", "superseded", "gone", "–"),
])
def test_an_orders_fate_has_a_symbol_and_words(apply_outcome, result, key, symbol):
    f = fate(apply_outcome, result)
    assert (f["key"], f["symbol"]) == (key, symbol) and f["word"]


def test_a_purchase_that_took_is_complete_at_once():
    assert fate("stuck", None, kind="purchase")["key"] == "held"
    assert fate("refused: over the 283 faith allowed", None)["why"] == "over the 283 faith allowed"

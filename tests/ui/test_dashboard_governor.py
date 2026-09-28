"""The governor line, the needs-you card, the tab title and favicon, the bar's exits (U3; rulings 5-8,
10, 11, 17), against a live Civ VI fixture in each state."""

from __future__ import annotations

import pytest
from uikit import CONTEXTS, contrast_failures, open_context, pick_campaign, show

pytestmark = pytest.mark.ui


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", state="attached", timeout=15000)
    w.page.wait_for_timeout(800)


def no_overflow(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


@pytest.mark.parametrize("scenario", ["needs"])
@pytest.mark.parametrize("name", list(CONTEXTS))
def test_needs_you_card_has_reason_age_cost_steps_and_resume(browser, live_servers, name, tmp_path):
    w = open_context(browser, name, live_servers)
    load(w)
    page = w.page
    assert page.text_content("#gov-line") == "Needs you: autoplay did not start at T57."
    assert page.get_attribute("#gov", "data-state") == "needs" and page.is_visible("#gov-card")
    assert page.text_content("#gov-age") == "waiting 6 h 52 min"
    assert page.text_content("#gov-cost").startswith("The game is stopped at T57.")
    steps = page.eval_on_selector_all("#gov-steps li", "ls => ls.map(l => l.textContent)")
    assert steps[0] == "Press Resume. This cleared 14 of 15 such stops." and len(steps) == 2
    assert "1 error, raw text" in page.text_content("#gov-raw-sum")
    assert page.is_hidden("#gov-raw-body pre")                        # raw text one disclosure away
    page.focus("#gov-resume")
    assert page.evaluate("document.activeElement.id") == "gov-resume"
    assert page.title() == "Needs you – T57 – Game Pilot"
    assert page.get_attribute("#favicon", "href").startswith("data:image/svg+xml")
    assert page.get_attribute("#gov-announce", "role") == "alert"
    assert no_overflow(page)
    page.screenshot(path=str(tmp_path / f"needs-{name}.png"), full_page=True)
    assert contrast_failures(page, "#gov") == []
    assert w.errors == [] and w.failed == []
    w.context.close()


@pytest.mark.parametrize("scenario", ["needs"])
def test_resume_from_the_card_and_capture_the_screen(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    page.click("#gov-capture")
    page.wait_for_selector("#gov-frame:not([hidden])", timeout=5000)
    assert live_servers["log"].state.frame_path
    cap = next(e for e in live_servers["log"].recent if e["kind"] == "capture")
    assert cap["by"] == "Chrome on Windows"
    page.click("#gov-resume")
    page.wait_for_function("() => document.getElementById('gov').dataset.state === 'playing'", timeout=5000)
    assert "resume" in live_servers["pilot"].calls
    assert page.text_content("#toast") == "Resumed"
    assert page.title() == "T57 – Game Pilot"
    w.context.close()


def test_playing_says_what_the_ai_plays_and_when_the_next_decision_is(browser, live_servers):
    w = open_context(browser, "desktop-dark", live_servers)
    load(w)
    page = w.page
    assert page.text_content("#gov-line") == "The AI is playing T57."
    facts = page.text_content("#gov-facts")
    assert "Next decision at T60 (every 5 turns)." in facts and "Answered by Gemini 3.1 Pro." in facts
    page.click("#gov-facts [data-pace]")                              # the pace opens Settings > Game
    page.wait_for_selector("#settings-dialog[open]")
    assert page.is_visible("#pace-months")
    w.context.close()


@pytest.mark.parametrize("scenario", ["deciding"])
def test_deciding_ticks_and_names_the_model_and_its_fallback(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    line = page.text_content("#gov-line")
    assert line.startswith("Deciding T57: 1 min 1") and line.endswith("s.")
    page.wait_for_timeout(1100)
    assert page.text_content("#gov-line") != line                    # the elapsed time ticks
    assert page.get_attribute("#gov-line .tick", "aria-hidden") == "true"
    assert "Gemini 3.1 Pro, call 2 of 2, after Gemini 3.8 Flash was overloaded (503)." in page.text_content("#gov-facts")
    assert page.title() == "Deciding – T57 – Game Pilot"
    w.context.close()


@pytest.mark.parametrize("scenario", ["question"])
def test_a_question_waits_in_the_governor_line_with_its_deadline(browser, live_servers):
    w = open_context(browser, "phone-dark", live_servers)
    load(w)
    page = w.page
    assert page.text_content("#gov-line").startswith("Question for you: Apply 'prepare_war'?")
    assert "means: no." in page.text_content("#gov-facts")
    page.click('#gov-actions [data-answer="yes"]')
    page.wait_for_function("() => document.getElementById('gov').dataset.state !== 'question'", timeout=5000)
    assert ("answer", "yes") in live_servers["pilot"].calls
    assert no_overflow(page)
    w.context.close()


@pytest.mark.parametrize("scenario", ["paused"])
def test_paused_says_who_paused_and_offers_resume(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    assert page.text_content("#gov-line").startswith("Paused from Pixel phone at T57, ")
    assert page.is_visible('#gov-actions [data-act="resume"]')
    w.context.close()


def test_a_past_campaign_says_so_and_links_to_the_live_one(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    pick_campaign(page, "stellaris/theia")
    page.wait_for_function("() => document.getElementById('gov').dataset.state === 'history'")
    assert page.text_content("#gov-line").startswith("Viewing a past campaign: last played 2288.06")
    assert "Live now: Civ VI T57, Kublai Khan, China." in page.text_content("#gov-facts")
    assert page.title() == "Game Pilot"
    # ruling 4: the live run's controls are not offered for a past campaign (they would act on Civ VI
    # with Stellaris's words)
    assert page.is_hidden("#b-toggle") and page.is_hidden("#b-stop") and page.is_hidden("#m-toggle")
    show(page, "talk")
    assert page.is_hidden("#talk-controls") and page.is_visible("#talk-off")
    assert "past campaign" in page.text_content("#talk-off")
    page.click("#gov-facts [data-live]")
    page.wait_for_function("() => document.getElementById('gov').dataset.state === 'playing'")
    assert page.get_attribute("#campaign", "data-cid") == "civ6/kublai"
    assert page.is_visible("#b-toggle") and page.is_visible("#talk-controls") and page.is_hidden("#talk-off")
    w.context.close()


def test_an_empty_past_campaign_says_so_without_a_dash(browser, live_servers):
    """Absent means hidden (ruling 3): a campaign with nothing recorded (a failed start) has no date to name."""
    from pilot.events import EventLog
    empty = EventLog(live_servers["runs"], "20260925-080000", "m", telemetry=live_servers["tel"])
    empty.emit("run_start", game="galciv4", model="m")
    empty.set_campaign("galciv4", "untitled", "")
    empty.emit("run_end")
    empty.close()
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    page.click("#campaign")
    page.click("#camp-empty summary")
    page.click('#camp-dialog button[data-cid="galciv4/untitled"]')
    page.wait_for_function("() => document.getElementById('gov').dataset.state === 'history'")
    assert page.text_content("#gov-line") == "Viewing a past campaign with nothing recorded yet."
    assert "–" not in page.text_content("#gov")
    w.context.close()


def test_stop_confirms_in_the_games_words(browser, live_servers):
    w = open_context(browser, "desktop-dark", live_servers)
    load(w)
    page = w.page
    assert page.is_hidden("#b-stop")                                   # inside the ⋯ menu
    page.click("#b-more")
    page.click('#more-menu [data-act="stop"]')
    page.wait_for_selector("#stop-dialog[open]")
    assert page.text_content("#stop-text") == "The AI finishes this turn and the game stays at T57."
    page.click('#stop-dialog button[value="cancel"]')
    assert "stop" not in live_servers["pilot"].calls
    assert page.text_content("#pc") == "mini-rig2 · Civ VI in front · agent 1.6.1"
    w.context.close()


@pytest.mark.parametrize("scenario", ["needs_old"])
def test_an_older_pilot_without_attention_still_shows_the_card(browser, live_servers):
    """Every page change works against a pilot that lacks the new fields (Rollout's deploy rule)."""
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    assert page.text_content("#gov-line") == "Needs you at T57."
    assert page.text_content("#gov-cost").startswith("Game control failed: RuntimeError: the tuner is off.")
    assert page.text_content("#gov-age").startswith("waiting ")
    assert page.eval_on_selector_all("#gov-steps li", "ls => ls.length") == 2
    assert w.errors == []
    w.context.close()


@pytest.mark.parametrize("scenario", ["norun"])
@pytest.mark.parametrize("name", ["desktop-dark", "phone-light"])
def test_with_no_run_live_the_page_says_so_and_offers_start(browser, live_servers, name):
    """Ruling 6's "none" state: after the pilot stopped (and a failed start left an empty GalCiv
    campaign, now the newest), the hero says no run is playing, names the last one played, offers
    Start run, and the page shows that campaign, not the empty one (ruling 4 folds empty ones)."""
    w = open_context(browser, name, live_servers)
    load(w)
    page = w.page
    page.wait_for_function("() => document.getElementById('gov').dataset.state === 'none'", timeout=5000)
    assert page.text_content("#gov-line") == "No run is playing."
    facts = page.text_content("#gov-facts")
    assert facts.startswith("Last: Civ VI, Kublai Khan, China, T57, stopped ") and "Viewing" not in facts
    assert page.is_visible('#gov-actions [data-act="start"]')
    assert page.get_attribute("#campaign", "data-cid") == "civ6/kublai"
    page.click("#campaign")
    assert "Terran Alliance" not in page.text_content("#camp-list")
    assert "Show empty campaigns (1)" in page.text_content("#camp-empty-sum")
    page.click("#camp-close")
    pick_campaign(page, "stellaris/theia")                            # a deliberate look at the past
    page.wait_for_function("() => document.getElementById('gov').dataset.state === 'history'")
    assert w.errors == []
    w.context.close()

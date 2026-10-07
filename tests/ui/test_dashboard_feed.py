"""Activity (U6: rulings 18 and 29): every event reads as a sentence with its game date and wall time and
the raw event one disclosure away; repeats group; filters Problems, Orders, Model, You and All, with
Problems first while a stop is open; a past campaign shows its own events."""

from __future__ import annotations

import pytest
from uikit import open_context, pick_campaign, show

pytestmark = pytest.mark.ui

TUNER = "autoplay at T57: Error: Failed /tuner/lua\n\nCaused by:\n    0: operation timed out"


def load(w, tab=True):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", state="attached", timeout=15000)
    w.page.wait_for_timeout(800)
    if tab:
        show(w.page, "activity")
        w.page.wait_for_selector("#feed li.ev", timeout=5000)


def rows(page):
    return page.eval_on_selector_all("#feed li.ev", "els => els.map(e => e.querySelector('.ev-say').textContent.trim())")


@pytest.mark.parametrize("scenario", ["needs"])
def test_problems_first_while_a_stop_is_open_and_repeats_group(browser, live_servers, tmp_path):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page, log, live = w.page, live_servers["log"], live_servers["live"]
    assert page.get_attribute('#feed-filters [data-filter="problems"]', "aria-pressed") == "true"
    assert page.eval_on_selector_all("#feed li.ev", "els => els.every(e => e.classList.contains('problem'))")
    for turn in (55, 56, 57):               # the same failure, turn after turn
        live.call(log.emit, "briefing_error", error=TUNER.replace("T57", f"T{turn}"))
    page.wait_for_function("() => document.querySelector('#feed li.ev .ev-say').textContent.includes('3 times')", timeout=5000)
    first = rows(page)[0]
    assert first.startswith("Autoplay at T57 failed: the game's tuner did not answer (timed out)"), first
    page.click('#feed-filters [data-filter="all"]')
    page.wait_for_timeout(200)
    everything = rows(page)
    assert any(r.startswith("Run started: Civ VI") for r in everything), everything
    assert any(r.startswith("Needs you: autoplay did not start at T57") for r in everything)
    assert not [r for r in everything if r.startswith("{") or "Unrecognised" in r], everything
    page.screenshot(path=str(tmp_path / "activity-needs.png"), full_page=True)
    assert w.errors == []
    w.context.close()


def test_each_row_has_its_game_date_wall_time_and_raw_event(browser, live_servers):
    w = open_context(browser, "desktop-dark", live_servers)
    load(w)
    page, log, live = w.page, live_servers["log"], live_servers["live"]
    live.call(log.emit, "turn", turn=57, turns=2, seconds=126.0, note="autoplay ended early")
    live.call(log.emit, "mystery_kind", detail={"a": 1})
    page.wait_for_function("() => document.getElementById('feed').textContent.includes('Unrecognised event: mystery kind')", timeout=5000)
    texts = rows(page)
    assert "Played T55 → T57 in 2 min 6 s; autoplay ended early" in texts, texts
    li = page.locator("#feed li.ev").first
    assert li.locator(".ev-date").text_content().strip() == "T57"
    assert li.locator(".ev-time").text_content().strip()
    raw = li.locator("details.ev-raw pre")
    assert raw.is_hidden()
    li.locator("details.ev-raw summary").click()
    assert '"mystery_kind"' in raw.text_content()
    assert w.errors == []
    w.context.close()


def test_filters_sort_the_feed(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers, device="Pixel phone")
    load(w)
    page = w.page
    assert page.get_attribute('#feed-filters [data-filter="all"]', "aria-pressed") == "true"   # no stop open
    page.click("#b-toggle")                                                                   # Pause, from this browser
    page.wait_for_function("() => document.getElementById('feed').textContent.includes('Paused, from Pixel phone')", timeout=5000)
    page.click('#feed-filters [data-filter="you"]')
    page.wait_for_timeout(200)
    assert rows(page) == ["Paused, from Pixel phone"]
    page.click('#feed-filters [data-filter="orders"]')
    page.wait_for_timeout(200)
    assert any(r.startswith("Last stand in Chengdu at T54") for r in rows(page)), rows(page)
    page.click('#feed-filters [data-filter="model"]')
    page.wait_for_timeout(200)
    assert any(r.startswith("New strategy at T50") for r in rows(page)), rows(page)
    assert w.errors == []
    w.context.close()


def test_a_past_campaign_shows_its_own_events(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    pick_campaign(page, "stellaris/theia")
    page.wait_for_function("() => document.getElementById('feed').textContent.includes('Run started: Stellaris')", timeout=5000)
    feed = page.text_content("#feed")
    assert "Run ended" in feed and "Civ VI" not in feed and "Chengdu" not in feed
    dates = page.eval_on_selector_all("#feed .ev-date", "els => els.map(e => e.textContent.trim()).filter(Boolean)")
    assert dates and all(d.startswith("2288.") for d in dates), dates
    assert w.errors == []
    w.context.close()


@pytest.mark.parametrize("name", ["phone-light", "desktop-dark"])
def test_long_strings_wrap_in_the_feed(browser, live_servers, name):
    w = open_context(browser, name, live_servers)
    load(w)
    page, log, live = w.page, live_servers["log"], live_servers["live"]
    live.call(log.emit, "journal", text="x" * 400)
    page.wait_for_function("() => document.getElementById('feed').textContent.includes('xxxxxxxx')", timeout=5000)
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    assert w.errors == []
    w.context.close()


WAIT = {"role": "decisions", "models": ["google:gemini-pro-latest", "google:gemini-3.8-flash"], "seconds": 40,
        "waited_s": 45, "budget_s": 120, "reason": "every model is overloaded"}


def test_a_model_wait_reads_in_activity_and_counts_as_model_not_problem(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page, log, live = w.page, live_servers["log"], live_servers["live"]
    page.click('#feed-filters [data-filter="all"]')
    live.call(log.emit, "model_wait", **WAIT)
    live.call(log.emit, "model_wait", **{**WAIT, "role": "chat", "waited_s": 5, "reason": "a trial is running on google:gemini-pro-latest"})
    live.call(log.emit, "pool_exhausted", role="chat", causes=[{"model": "google:gemini-3.8-flash", "error": "overloaded (503)"},
                                                              {"model": "-", "error": "stopped while waiting"}])
    page.wait_for_function("() => document.getElementById('feed').textContent.includes('stopped while waiting')", timeout=5000)
    texts = rows(page)
    assert any(t.startswith("Waiting up to 1 min 15 s more for Gemini to recover (every model is overloaded), 45 s so far") for t in texts), texts
    chat = [t for t in texts if "so far (chat)" in t]
    assert chat and "a trial is running on gemini-pro-latest" in chat[0] and "google:" not in chat[0], texts
    stopped = [t for t in texts if t.startswith("No model could answer")]
    assert stopped and stopped[0].endswith("; stopped while waiting") and "- stopped" not in stopped[0], texts
    w.page.click('#feed-filters [data-filter="problems"]')
    page.wait_for_timeout(200)
    assert not [t for t in rows(page) if t.startswith("Waiting up to")]
    page.click('#feed-filters [data-filter="model"]')
    page.wait_for_timeout(200)
    assert [t for t in rows(page) if t.startswith("Waiting up to")]
    w.context.close()

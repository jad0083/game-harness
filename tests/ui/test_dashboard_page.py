"""The dashboard page on a live Civ VI run and a Stellaris history campaign (U0: truthful basics)."""

from __future__ import annotations

import pytest
from uikit import UI_KEY, open_context

pytestmark = pytest.mark.ui


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", timeout=15000)
    w.page.wait_for_timeout(1200)


@pytest.mark.parametrize("name", ["desktop-dark", "phone-light"])
def test_civ6_live_page_has_no_console_errors(browser, live_servers, name, tmp_path):
    w = open_context(browser, name, live_servers)
    load(w)
    log = live_servers["log"]
    live_servers["live"].call(log.emit, "metrics", date="T58", score=99, military=600, science=26.0)   # live chart update
    live_servers["live"].call(log.emit, "action", action="order")      # used to trigger a frame fetch
    w.page.wait_for_timeout(1500)
    w.page.screenshot(path=str(tmp_path / f"civ6-{name}.png"), full_page=True)
    assert w.errors == []
    assert w.failed == []
    assert not [u for u in w.requests if "frame.jpg" in u], "Civ VI records no frames: nothing to fetch"
    assert w.page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    w.context.close()


def test_civ6_readout_speaks_turns(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    assert "(every 5 turns)" in page.text_content("#gov-facts")
    assert "Directive" not in page.text_content("#figures")                 # Civ VI has none
    assert "Civ VI" in page.text_content("#pc")
    camp = page.eval_on_selector("#campaign", "s => [...s.options].map(o => o.textContent)")
    assert camp == ["Kublai Khan, China (live), 2 decisions", "Theian Union, 1 decision"]
    w.context.close()


def test_error_decision_reads_as_no_decision(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    page.click('#decisions button[data-i="1"]')
    page.wait_for_selector("#tab-reasoning .t-error")
    text = page.text_content("#tab-reasoning .t-error")
    assert text.startswith("No decision:") and "503" in text
    assert page.is_hidden("#tab-reasoning details.raw-error pre")        # raw text one disclosure away
    w.context.close()


def test_switching_campaign_clears_reasoning(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    page.wait_for_selector("#tab-reasoning .t-decision, #tab-reasoning .t-error")
    page.select_option("#campaign", "stellaris/theia")
    page.wait_for_timeout(300)
    assert page.text_content("#tab-reasoning").strip() in ("Pick a decision to read how it was made.", "Loading…") \
        or "Room to grow" in page.text_content("#tab-reasoning")
    assert "Chengdu" not in page.text_content("#tab-reasoning")
    assert w.errors == []
    w.context.close()


def test_a_revoked_browser_sees_the_signed_out_banner_and_stops(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers, device="Brave on Windows")
    load(w)
    page = w.page
    live_servers["auth"].store.revoke(w.device, "revoked", by="cli")
    page.wait_for_selector("#locked:not([hidden])", timeout=5000)
    text = page.text_content("#locked")
    assert "signed out" in text and "the controller" in text
    href = page.get_attribute("#locked a", "href")
    assert href.startswith("/pair?reason=revoked&next=")
    page.wait_for_timeout(300)
    before = len(w.requests)
    page.wait_for_timeout(3500)                    # longer than the 3 s status poll
    assert len(w.requests) == before, w.requests[before:]
    assert w.errors == [] or all("401" in e for e in w.errors)
    w.context.close()


def test_page_shows_the_carried_over_notice_once(browser, live_servers):
    """A browser whose old key cookie became a device is told once, and never again."""
    w = open_context(browser, "desktop-light", live_servers, signed_in=False)
    w.context.add_cookies([{"name": "pilot_key", "value": UI_KEY, "url": w.base}])
    load(w)
    w.page.wait_for_selector("#notices:not([hidden])", timeout=5000)
    assert "own sign-in" in w.page.text_content("#notices")
    w.page.click("#notices [data-dismiss]")
    w.page.reload()
    w.page.wait_for_selector("#decisions li button")
    w.page.wait_for_timeout(800)
    assert w.page.is_hidden("#notices")
    w.context.close()


def test_pause_is_attributed_to_the_browser_in_activity(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers, device="Pixel phone")
    load(w)
    page = w.page
    page.click("#b-toggle")
    page.click('.tabs button[data-tab="activity"]')
    page.wait_for_function("document.getElementById('feed').textContent.includes('Paused, from Pixel phone')", timeout=5000)
    assert live_servers["pilot"].calls == ["pause"]
    w.context.close()

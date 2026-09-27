"""The dashboard page on a live Civ VI run and a Stellaris history campaign (U0: truthful basics)."""

from __future__ import annotations

import pytest
from uikit import open_context

pytestmark = pytest.mark.ui


def load(w, base):
    w.page.goto(base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", timeout=15000)
    w.page.wait_for_timeout(1200)


@pytest.mark.parametrize("name", ["desktop-dark", "phone-light"])
def test_civ6_live_page_has_no_console_errors(browser, live_servers, name, tmp_path):
    base = live_servers["viewer"].url
    w = open_context(browser, name, base)
    load(w, base)
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
    base = live_servers["viewer"].url
    w = open_context(browser, "desktop-light", base)
    load(w, base)
    page = w.page
    assert page.text_content("#ro-pace-sub") == "a decision every 5 turns"
    assert page.is_hidden("#ro-directive") and page.is_hidden("#ro-standing")   # Civ VI has neither
    assert "Civ VI" in page.text_content("#pc")
    camp = page.eval_on_selector("#campaign", "s => [...s.options].map(o => o.textContent)")
    assert camp == ["Kublai Khan, China (live), 2 decisions", "Theian Union, 1 decision"]
    w.context.close()


def test_error_decision_reads_as_no_decision(browser, live_servers):
    base = live_servers["viewer"].url
    w = open_context(browser, "desktop-light", base)
    load(w, base)
    page = w.page
    page.click('#decisions button[data-i="1"]')
    page.wait_for_selector("#tab-reasoning .t-error")
    text = page.text_content("#tab-reasoning .t-error")
    assert text.startswith("No decision:") and "503" in text
    assert page.is_hidden("#tab-reasoning details.raw-error pre")        # raw text one disclosure away
    w.context.close()


def test_switching_campaign_clears_reasoning(browser, live_servers):
    base = live_servers["viewer"].url
    w = open_context(browser, "desktop-light", base)
    load(w, base)
    page = w.page
    page.wait_for_selector("#tab-reasoning .t-decision, #tab-reasoning .t-error")
    page.select_option("#campaign", "stellaris/theia")
    page.wait_for_timeout(300)
    assert page.text_content("#tab-reasoning").strip() in ("Pick a decision to read how it was made.", "Loading…") \
        or "Room to grow" in page.text_content("#tab-reasoning")
    assert "Chengdu" not in page.text_content("#tab-reasoning")
    assert w.errors == []
    w.context.close()

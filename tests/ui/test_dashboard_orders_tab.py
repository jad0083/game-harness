"""The levers tab (U5; rulings 1, 12, 15, 19-22, 31): Civ VI's Orders (buy-outs, the order record, every
order with its fate and filters, last stands), game health on Now, the last stand in the facts line,
and the reader tabs' keyboard."""

from __future__ import annotations

import pytest
from uikit import CONTEXTS, contrast_failures, open_context, pick_campaign, show

pytestmark = pytest.mark.ui


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", state="attached", timeout=15000)
    w.page.wait_for_timeout(600)


def test_the_reader_tabs_follow_the_game_and_take_arrow_keys(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    tabs = page.eval_on_selector_all(".tabs button:not([hidden])", "bs => bs.map(b => b.textContent.trim())")
    assert tabs == ["Reasoning", "Orders", "Strategy", "Talk", "Activity"]
    assert page.get_attribute("#tb-levers", "aria-controls") == "tab-levers"
    assert page.eval_on_selector_all(".tabs button:not([hidden])", "bs => bs.filter(b => b.tabIndex === 0).length") == 1
    page.focus("#tb-reasoning")
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.id") == "tb-levers" and page.is_visible("#tab-levers")
    page.keyboard.press("End")
    assert page.evaluate("document.activeElement.id") == "tb-activity" and page.is_visible("#stats")
    pick_campaign(page, "stellaris/theia")
    page.wait_for_function("() => document.querySelector('#tb-levers .tlabel').textContent === 'Actions'")
    w.context.close()


@pytest.mark.parametrize("name", list(CONTEXTS))
def test_the_orders_tab_shows_buy_outs_record_and_every_order(browser, live_servers, name, tmp_path):
    w = open_context(browser, name, live_servers)
    load(w)
    page = w.page
    show(page, "levers")
    page.wait_for_selector("#levers .rec li")
    text = page.text_content("#levers")
    assert "Gold 257, keeps 46 (30 + 10 for each gold of deficit a turn (1.6 now))" in text
    assert "Faith 117, keeps 25 for the pantheon" in text and "In danger: Chengdu" in text
    rec = page.eval_on_selector_all("#levers .rec li", "ls => ls.map(l => l.textContent.replace(/\\s+/g, ' ').trim())")
    assert any(r.startswith("Production, replace the AI's choice") and "0 held of 1, too few to judge" in r for r in rec)
    assert any(r.startswith("Purchase with faith") and "1 refused" in r for r in rec)
    assert "Last 30 turns; weak at 50% or less" in text
    assert "in force, 5 of 8 turns followed" in text                   # the open civic order, T52 -> T57
    assert "Chengdu, T54" in text and "City strike, predicted 28: took" in text
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    page.screenshot(path=str(tmp_path / f"orders-{name}.png"), full_page=True)
    assert contrast_failures(page, "#tab-levers") == []
    assert w.errors == []
    w.context.close()


def test_filters_narrow_the_log_and_a_row_opens_its_decision(browser, live_servers):
    w = open_context(browser, "desktop-dark", live_servers)
    load(w)
    page = w.page
    show(page, "levers")
    page.wait_for_selector("#levers .olog li")
    page.click('#levers [data-ofate="refused"]')
    rows = page.eval_on_selector_all("#levers .olog li", "ls => ls.map(l => l.textContent.replace(/\\s+/g, ' ').trim())")
    assert len(rows) == 1 and "Gurdwara, Beijing" in rows[0] and "380 faith, over the 283 allowed" in rows[0]
    page.click('#levers [data-ofate=""]')
    page.click('#levers [data-okind="production"]')
    page.click("#levers .olog li button")
    page.wait_for_selector("#tab-reasoning .t-decision")
    assert page.is_visible("#tab-reasoning") and page.text_content("#tab-reasoning .t-when").startswith("T52")
    w.context.close()


def test_game_health_and_the_last_stand_are_said_on_now(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    line = page.text_content("#game-health")
    assert page.is_visible("#game-health") and "warn" in page.get_attribute("#game-health", "class")
    assert "Popups quieted 5 of 6 at T50 (not: the project built popup)" in line      # ids become names
    assert "OnProjectComplete" not in line
    assert "tuner 3 timeouts in the last 40 calls" in line and "last turn 42 s" in line
    assert "Last stand armed (at most 3 in a row)." in page.text_content("#gov-facts")
    w.context.close()

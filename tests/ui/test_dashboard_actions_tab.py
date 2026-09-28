"""The Stellaris Actions tab and its levers (U10: rulings 23-26), rendered only when the pilot publishes
the data, in the shapes the governor publishes (uikit._seed_stellaris builds them with its own
functions): the action record with Stellaris keys and outcomes (a suspended market resource, the last
failure with its detail), the market per resource against its base price with the strategy's order,
the war crisis with its conditions in the bar, the governor line, Strategy and the chart, the
directive's postures, and a directive's policy report."""

from __future__ import annotations

import pytest
from uikit import CONTEXTS, contrast_failures, open_context, pick_campaign, show

pytestmark = pytest.mark.ui

CRISIS = "War crisis since 2291.03: a colony occupied (Arnvoss); lost 2 systems in 12 months."


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", state="attached", timeout=15000)
    w.page.wait_for_timeout(1000)


@pytest.mark.parametrize("scenario", ["stellaris"])
@pytest.mark.parametrize("name", list(CONTEXTS))
def test_the_actions_tab_shows_the_record_market_and_crisis(browser, live_servers, name, tmp_path):
    w = open_context(browser, name, live_servers)
    load(w)
    page = w.page
    show(page, "levers")
    page.wait_for_selector("#levers .rec li")
    text = page.text_content("#levers")
    assert CRISIS in text
    rec = page.eval_on_selector_all("#levers .rec li", "ls => ls.map(l => l.textContent.replace(/\\s+/g, ' ').trim())")
    assert any(r.startswith("Directive: Defend") and "67%" in r and "1 locked" in r
               and "last: overridden by the AI (economic policy → economic policy civilian on 2291.01.01), 2291.01" in r
               for r in rec), rec
    assert any(r.startswith("Market: buy alloys") and "Suspended until recalibrated" in r and "0 held of 2" in r for r in rec), rec
    assert any(r.startswith("Tech picks") and "80%" in r for r in rec), rec
    fill = page.eval_on_selector("#levers .rrate .meter", "m => m.querySelector('i').getBoundingClientRect().width / m.getBoundingClientRect().width")
    assert abs(fill - 0.67) < 0.03, fill                                  # the rate bar is drawn to its rate
    market = page.eval_on_selector_all("#levers .market li", "ls => ls.map(l => l.textContent.replace(/\\s+/g, ' ').trim())")
    assert any(r.startswith("Alloys") and "14% above base" in r and "+5 a month" in r and "buy 5 a month" in r
               and "Suspended until recalibrated" in r for r in market), market
    assert any(r.startswith("Energy") and "8% below base" in r and "−10 a month" in r for r in market), market
    assert "Galactic market at 2291.07" in text
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    page.screenshot(path=str(tmp_path / f"actions-{name}.png"), full_page=True)
    assert contrast_failures(page, "#tab-levers") == []
    assert w.errors == []
    w.context.close()


@pytest.mark.parametrize("scenario", ["stellaris"])
def test_the_crisis_postures_and_policy_report_show_where_they_belong(browser, live_servers):
    w = open_context(browser, "desktop-dark", live_servers)
    load(w)
    page = w.page
    assert page.is_visible("#bar-crisis") and page.text_content("#bar-crisis").strip() == "War crisis"
    assert CRISIS in page.text_content("#gov-facts")
    fig = page.locator("#figures .fig").first
    assert fig.locator("b").text_content() == "Defend"
    assert "postures: naval capacity on" in fig.text_content()             # set in the save
    off = fig.locator(".posture.off")                                       # defend's other posture, not enabled
    assert off.text_content().startswith("ship upgrades") and off.get_attribute("tabindex") == "0"
    off.focus()
    assert "not enabled" in page.evaluate("getComputedStyle(document.activeElement, '::after').content")
    row = page.text_content('#decisions button[data-i="0"]')
    assert "Applied; 1 policy locked (diplomatic stance)" in row
    page.click('#decisions button[data-i="0"]')
    page.wait_for_selector("#reasoning .t-pairs")
    pairs = dict(page.eval_on_selector_all("#reasoning .t-pairs div", "ds => ds.map(d => [d.querySelector('dt').textContent, d.querySelector('dd').textContent])"))
    assert pairs["Applied"] == "Applied; 1 policy locked (diplomatic stance)"
    show(page, "strategy")
    page.wait_for_selector("#strategy .pillar")
    assert CRISIS in page.text_content("#strategy")
    assert "need counted as missed while the war crisis lasts" in page.text_content('#strategy article[data-pillar="defence"]')
    bands = page.eval_on_selector_all("#chartwrap rect.crisis title", "ts => ts.map(t => t.textContent)")
    assert bands == ["War crisis"], bands
    assert "war crisis" in page.text_content("#legend")
    assert w.errors == []
    w.context.close()


def test_nothing_renders_without_the_data(browser, live_servers):
    """A Stellaris campaign whose pilot publishes none of it (today's): no record, market, crisis,
    postures or policy report, and no empty tables."""
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    pick_campaign(page, "stellaris/theia")
    page.wait_for_function("() => document.querySelector('#tb-levers .tlabel').textContent === 'Actions'")
    show(page, "levers")
    page.wait_for_timeout(300)
    assert page.query_selector_all("#levers .rec, #levers .market, #levers .o-alarm") == []
    assert page.is_hidden("#bar-crisis")
    assert "postures" not in page.text_content("#figures") and "Applied" not in page.text_content("#decisions")
    assert page.query_selector_all("#chartwrap rect.crisis") == []
    assert w.errors == []
    w.context.close()


@pytest.mark.parametrize("scenario", ["stellaris"])
def test_on_a_phone_the_crisis_mark_leaves_the_campaign_its_name(browser, live_servers):
    w = open_context(browser, "phone-light", live_servers)
    load(w)
    page = w.page
    assert page.is_visible("#bar-crisis") and page.text_content("#bar-crisis").strip() == "War crisis"
    assert page.eval_on_selector("#camp-name", "e => e.scrollWidth <= e.clientWidth"), page.text_content("#camp-name")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    w.context.close()

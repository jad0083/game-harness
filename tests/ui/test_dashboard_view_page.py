"""The page speaks each game's words from its view (corpora/<game>/dashboard.toml): figures, chart views,
rivals with readable names, the Strategy tab's share and exclusive modes, Settings per game (U2)."""

from __future__ import annotations

import pytest
from uikit import contrast_failures, open_context, pick_campaign, show

pytestmark = pytest.mark.ui


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", state="attached", timeout=15000)
    w.page.wait_for_selector("#figures .fig", timeout=5000)


def figures(page) -> dict[str, tuple[str, str]]:
    return {f["label"]: (f["value"], f["sub"]) for f in page.eval_on_selector_all("#figures .fig", """els => els.map(e => ({
        value: e.querySelector('b').textContent, label: e.querySelector('.fig-label').textContent,
        sub: (e.querySelector('.fig-sub') || {}).textContent || ''}))""")}


def test_civ6_figures_chart_and_rivals_come_from_its_view(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    figs = figures(page)
    assert figs["Score"] == ("#1 of 4", "median 80")
    assert figs["Techs"][0] == "39" and figs["Techs"][1].endswith("behind the median")
    assert page.is_visible("#figures .fig.behind")
    assert "Directive" not in figs and "Standing" not in figs          # Civ VI has neither: hidden, never "–"
    assert page.text_content("#h-chart") == "Yields over time"
    assert page.eval_on_selector_all("#chart-views button", "bs => bs.map(b => b.textContent)") == [
        "Yields", "Balances", "Rank", "Table"]
    assert "Faith per turn" in page.text_content("#legend")
    page.click('#chart-views [data-view="rank"]')
    assert page.text_content("#chartwrap svg").count("#1") >= 1
    assert page.text_content("#h-nb") == "Civilizations met"
    rows = page.eval_on_selector_all("#nb tbody tr", "rs => rs.map(r => r.querySelector('.who b').textContent)")
    assert rows == ["Germany", "Netherlands", "Australia"]
    assert "CIVILIZATION_" not in page.text_content("main")
    assert page.inner_text("#nb tbody tr:first-child").count("at war") == 1        # once as shown (a phone moves it)
    assert w.errors == []
    w.context.close()


def test_civ6_strategy_speaks_of_effort_not_pressure(browser, live_servers):
    w = open_context(browser, "desktop-dark", live_servers)
    load(w)
    page = w.page
    show(page, "strategy")
    page.wait_for_selector("#strategy .pillar")
    text = page.text_content("#strategy")
    assert "Where the effort goes" in text and "30% of effort" in text
    assert "pressure" not in text.lower() and "rank" not in text.lower()
    assert "Builds: Slinger" in text and "unit:" not in text           # corpus ids read as names
    assert page.is_visible("#s-summary-more")
    page.click("#s-summary-more")
    assert "Eureka" in page.text_content("#s-summary") and page.eval_on_selector("#s-summary li", "e => !!e")
    assert contrast_failures(page, "#tab-strategy") == []
    w.context.close()


def test_stellaris_history_speaks_months_and_directives(browser, live_servers):
    w = open_context(browser, "desktop-dark", live_servers)
    load(w)
    page = w.page
    pick_campaign(page, "stellaris/theia")
    page.wait_for_function("() => document.getElementById('h-chart').textContent === 'Empire over time'")
    page.wait_for_selector("#figures .fig")
    figs = figures(page)
    assert figs["Directive"] == ("Expand", "since 2288.03")
    assert figs["Standing"][0] == "#3 of 9" and figs["Standing"][1] == "falling behind in pops"
    assert page.eval_on_selector_all("#chart-views button", "bs => bs.map(b => b.textContent)") == [
        "Net income", "Stockpile", "Power", "Table"]
    assert page.text_content("#h-nb") == "Neighbours"
    assert "Tzynn Empire" in page.text_content("#nb") and "rival" in page.text_content("#nb")
    assert w.errors == []
    w.context.close()


def test_civ6_settings_follow_the_game(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    page.click("#b-settings")
    page.wait_for_selector("#settings-dialog[open]")
    roles = page.eval_on_selector_all("#roles button", "bs => bs.map(b => b.childNodes[0].textContent)")
    assert "GC4 blockers" not in roles
    assert "Civ VI governor" in page.text_content("#role-help")
    page.click('[data-stab="game"]')
    assert page.is_hidden("#pace-speed")                                 # Civ VI has no game speed
    assert page.is_visible("#pace-months") and page.input_value("#pace-months") == "5"
    assert page.text_content("#pace-unit") == "turns"
    w.context.close()


def test_a_streamed_turn_keeps_the_rivals_names(browser, live_servers):
    """A metrics row from the live stream carries raw ids (CIVILIZATION_GERMANY): the table must still
    read Germany after the next turn arrives, not until the next decision reloads the campaign."""
    from uikit import CIV6_METRICS
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    log = live_servers["log"]
    row = {**CIV6_METRICS[-1], "date": "T58", "turn": 58}
    live_servers["live"].call(log.emit, "metrics", **row)
    page.wait_for_function("() => document.getElementById('nb').textContent.includes('Germany')", timeout=5000)
    page.wait_for_timeout(2500)
    rows = page.eval_on_selector_all("#nb tbody tr", "rs => rs.map(r => r.querySelector('.who b').textContent)")
    assert rows == ["Germany", "Netherlands", "Australia"], rows
    assert "CIVILIZATION_" not in page.text_content("main")
    w.context.close()

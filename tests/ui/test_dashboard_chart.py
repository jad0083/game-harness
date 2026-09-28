"""The per-game chart (U8: rulings 12, 31, 33): the game's series each named at its line end, x ticks in the
game's unit, decisions as short ticks on the axis (urgent taller, a failed one in the alarm colour, full
height only for the selected, hovered or current one), strategy reviews in their own lane above the plot,
last stands as marks, and the whole chart one tab stop whose arrow keys move between decisions and whose
Enter opens one."""

from __future__ import annotations

from itertools import pairwise

import pytest
from uikit import contrast_failures, open_context, pick_campaign

pytestmark = pytest.mark.ui

TABBABLE = r"""(stop) => {
  const sel = "a[href], button, input, select, textarea, summary, [tabindex]";
  const out = [];
  for (const el of document.querySelectorAll(sel)) {
    if (el.tabIndex < 0 || el.disabled || !el.getClientRects().length) continue;
    if (getComputedStyle(el).visibility === "hidden" || el.closest("[hidden], dialog:not([open]), details:not([open]) > :not(summary)")) continue;
    if (stop && (el === stop || el.compareDocumentPosition(stop) & Node.DOCUMENT_POSITION_PRECEDING)) break;
    out.push(el.id || el.getAttribute("class") || el.tagName);
  }
  return out;
}"""


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#chartwrap svg .dmark", timeout=15000)
    w.page.wait_for_timeout(800)


def marks(page):
    return page.eval_on_selector_all("#chartwrap .dmark[data-i]", """gs => gs.map(g => {
      const t = g.querySelector('.dtick'), f = g.querySelector('.dfull');
      return {i: +g.dataset.i, len: +t.getAttribute('y2') - +t.getAttribute('y1'), stroke: getComputedStyle(t).stroke,
              full: getComputedStyle(f).visibility === 'visible'};
    })""")


def test_the_chart_is_one_tab_stop_and_its_arrows_move_between_decisions(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    inside = page.eval_on_selector_all("#chartwrap, #chartwrap *", "els => els.filter(e => e.tabIndex >= 0 || e.hasAttribute('tabindex') && e.getAttribute('tabindex') !== '-1').map(e => e.id || e.tagName)")
    assert inside == ["chartwrap"], inside
    assert page.get_attribute("#chartwrap", "role") == "group"
    before = page.evaluate(TABBABLE, page.query_selector("#decisions li button"))
    assert len(before) <= 20, before
    page.focus("#chartwrap")
    page.keyboard.press("End")
    assert "T55" in page.text_content("#chart-now")                     # the newest decision
    page.keyboard.press("ArrowLeft")
    assert page.text_content("#chart-now").startswith("T52")
    assert next(m for m in marks(page) if m["i"] == 0)["full"]            # the current mark runs full height
    page.keyboard.press("Enter")
    page.wait_for_selector("#tab-reasoning .t-decision")
    assert page.text_content("#reasoning .t-when").startswith("T52")
    assert page.evaluate("document.activeElement.id") == "chartwrap"     # the chart keeps the focus
    assert w.errors == []
    w.context.close()


def test_decisions_are_short_ticks_urgent_taller_failed_in_the_alarm_colour(browser, live_servers):
    w = open_context(browser, "desktop-dark", live_servers)
    load(w)
    page = w.page
    by = {m["i"]: m for m in marks(page)}
    assert by[0]["len"] <= 10 and by[1]["len"] > by[0]["len"], by       # T55 was urgent
    bad = page.evaluate("getComputedStyle(document.body).getPropertyValue('--bad').trim()")
    assert by[1]["stroke"] == page.evaluate(f"(() => {{ const d = document.createElement('i'); d.style.color = '{bad}'; document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c; }})()")
    selected = [m for m in by.values() if m["full"]]
    assert len(selected) == 1                                             # the selected one alone runs full height
    page.hover('#chartwrap .dmark[data-i="0"] .dhit')
    assert next(m for m in marks(page) if m["i"] == 0)["full"]
    stand = page.eval_on_selector_all("#chartwrap .lsmark", "ms => ms.map(m => m.querySelector('title').textContent)")
    assert stand == ["Last stand in Chengdu, T54"], stand
    ends = page.eval_on_selector_all("#chartwrap .end-label", "ts => ts.map(t => [t.textContent, +t.getAttribute('y')])")
    assert [t for t, _ in ends] == ["Science", "Culture", "Faith per turn", "Gold per turn", "Production"]
    ys = sorted(y for _, y in ends)
    assert all(b - a >= 12 for a, b in pairwise(ys)), ys               # labels never overlap
    assert contrast_failures(page, "#p-chart") == []
    assert w.errors == []
    w.context.close()


def test_reviews_have_their_own_lane_above_the_plot(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    pick_campaign(page, "stellaris/theia")
    page.wait_for_function("() => document.getElementById('h-chart').textContent === 'Empire over time'")
    page.wait_for_selector("#chartwrap .lane")
    lane = page.eval_on_selector("#chartwrap .lane", "r => [+r.getAttribute('y'), +r.getAttribute('y') + +r.getAttribute('height')]")
    plot_top = float(page.get_attribute("#chartwrap #hit", "y"))
    ticks = page.eval_on_selector_all("#chartwrap text.xtick", "ts => ts.map(t => t.textContent)")
    assert ticks and all(t.isdigit() and t.startswith("228") for t in ticks), ticks     # years for a months game
    assert lane[1] <= plot_top
    reviews = page.eval_on_selector_all("#chartwrap .rmark rect", "rs => rs.map(r => r.getBoundingClientRect().top)")
    if reviews:                                                           # the Stellaris fixture may have none
        lane_box = page.eval_on_selector("#chartwrap .lane", "r => r.getBoundingClientRect().bottom")
        assert all(y >= lane_box for y in reviews)
    w.context.close()


@pytest.mark.parametrize("name", ["phone-light", "desktop-dark"])
def test_civ6_reviews_sit_above_the_plot_and_the_chart_fits(browser, live_servers, name):
    w = open_context(browser, name, live_servers)
    load(w)
    page = w.page
    plot_top = float(page.get_attribute("#chartwrap #hit", "y"))
    review = page.eval_on_selector_all("#chartwrap .rmark rect", "rs => rs.map(r => +r.getAttribute('y') + +r.getAttribute('height'))")
    assert review and all(y <= plot_top for y in review), (review, plot_top)
    ticks = page.eval_on_selector_all("#chartwrap text.xtick", "ts => ts.map(t => t.textContent)")
    assert ticks and all(t.startswith("T") for t in ticks)
    page.click('#chart-views [data-view="table"]')
    assert page.eval_on_selector("#chartwrap .tablewrap", "e => getComputedStyle(e).overflow") == "auto"
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    assert w.errors == []
    w.context.close()


def test_every_last_stand_is_marked_on_the_chart(browser, live_servers):
    """The Orders tab shows the newest three stands; the chart marks all of them."""
    log = live_servers["log"]
    for turn in (50, 51, 52, 53):
        log.emit("last_stand", city="Xian", turn=turn, date=f"T{turn}", in_a_row=1, ran=True, stopped="done",
                 actions=[], pins=[])
    w = open_context(browser, "desktop-light", live_servers)
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#chartwrap .lsmark", state="attached", timeout=15000)
    w.page.wait_for_timeout(500)
    marks = w.page.eval_on_selector_all("#chartwrap .lsmark title", "ts => ts.map(t => t.textContent)")
    assert len(marks) == 5 and "Last stand in Xian, T50" in marks, marks
    w.context.close()

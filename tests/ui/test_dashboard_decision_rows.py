"""Decision rows and Reasoning lead with the model's reason (U4; rulings 14, 27, 28): rows stay short,
fates are symbols with words, errors read "No decision:" with their cause, Problems only filters."""

from __future__ import annotations

import pytest
from uikit import contrast_failures, open_context

pytestmark = pytest.mark.ui


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", timeout=15000)
    w.page.wait_for_timeout(600)


@pytest.mark.parametrize("name", ["desktop-light", "desktop-dark"])
def test_decision_rows_are_at_most_140px_on_desktop(browser, live_servers, name, tmp_path):
    w = open_context(browser, name, live_servers)
    load(w)
    page = w.page
    heights = page.eval_on_selector_all("#decisions li:not(.more) > button", "bs => bs.map(b => b.getBoundingClientRect().height)")
    assert heights and max(heights) <= 140, heights
    page.eval_on_selector("#p-dec", "e => e.scrollIntoView()")
    page.screenshot(path=str(tmp_path / f"decisions-{name}.png"))
    assert contrast_failures(page, "#p-dec") == []
    w.context.close()


def test_a_row_leads_with_the_reason_and_shows_fates(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    row = page.locator('#decisions button[data-i="0"]')
    assert row.locator(".d-trigger").text_content() == "Scheduled"
    assert row.locator(".reason").text_content().startswith("Chengdu is under siege")
    assert "Fraunces" in row.locator(".reason").evaluate("e => getComputedStyle(e).fontFamily")   # the model's voice
    chips = row.locator(".chips .fchip").all_text_contents()
    assert chips == ["⋯in force: Writing", "↺replaced by the AI: Chengdu: Slinger → Trader",
                     "✕refused: Beijing: Gurdwara", "+2"]
    assert row.locator(".fchip.f-refused").get_attribute("title") == "refused: 380 faith, over the 283 allowed"
    after = row.locator(".after").text_content()
    assert after.startswith("12 turns later:") and "military −226 ▲ watch" in after and "score +17" in after
    err = page.locator('#decisions button[data-i="1"]')
    assert err.locator(".reason").text_content() == "No decision: overloaded (503)"
    assert err.locator(".d-trigger").text_content() == "City threatened: Chengdu"
    assert err.locator(".d-urgent").text_content() == "urgent"
    assert "orders (" not in page.text_content("#decisions")            # machine text never leads
    w.context.close()


def test_reasoning_leads_with_the_decision_then_why_then_evidence(browser, live_servers):
    w = open_context(browser, "desktop-dark", live_servers)
    load(w)
    page = w.page
    page.click('#decisions button[data-i="0"]')
    page.wait_for_selector("#tab-reasoning .t-decision")
    assert page.text_content("#tab-reasoning .t-decision") == "Chengdu is under siege; buy a slinger with faith and keep science on Writing while the walls hold."
    pairs = dict(page.eval_on_selector_all("#tab-reasoning .t-pairs div", "ds => ds.map(d => [d.querySelector('dt').textContent, d.querySelector('dd').textContent])"))
    assert pairs["Trigger"] == "Scheduled" and pairs["Answered by"] == "Gemini 3.1 Pro, medium thinking"
    assert pairs["Took"] == "63 s · 41.0k tokens in, 1,200 out"
    orders = page.eval_on_selector_all("#tab-reasoning .t-orders li", "ls => ls.map(l => l.textContent.replace(/\\s+/g, ' ').trim())")
    assert any("bought with faith" in o and "refused: 380 faith" in o for o in orders)
    assert any(o.startswith("✓") and "Xian: Warrior" in o and "completed" in o for o in orders)
    page.click('#decisions button[data-i="1"]')
    page.wait_for_selector("#tab-reasoning .t-error")
    assert page.text_content("#tab-reasoning .t-error").startswith("No decision: overloaded (503).")
    assert page.is_hidden("#tab-reasoning details.raw-error pre")
    # the reader column is not a scroll box of its own: the page scrolls
    assert page.eval_on_selector("#tab-reasoning", "e => getComputedStyle(e).overflowY") == "visible"
    w.context.close()


def test_problems_only_keeps_errors_and_refusals(browser, live_servers):
    w = open_context(browser, "phone-light", live_servers)
    load(w)
    page = w.page
    assert page.is_hidden('#decisions button[data-i="0"] .chips')           # a phone counts fates instead
    counts = page.text_content('#decisions button[data-i="0"] .fcounts')
    assert "✓ 1" in counts and "↺ 1" in counts and "✕ 1" in counts
    page.click("#dec-problems")
    assert page.get_attribute("#dec-problems", "aria-pressed") == "true"
    assert len(page.query_selector_all("#decisions li > button[data-i]")) == 2     # both have a problem
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    w.context.close()

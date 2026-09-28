"""The dashboard's text is readable in both themes and on both widths (WCAG AA, measured on computed
colours), and a refused change is said in the page, never in a blocking alert()."""

from __future__ import annotations

import pytest
from uikit import CONTEXTS, contrast_failures, open_context, show

pytestmark = pytest.mark.ui


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", state="attached", timeout=15000)
    w.page.wait_for_timeout(1200)


@pytest.mark.parametrize("name", list(CONTEXTS))
def test_page_text_passes_contrast(browser, live_servers, name, tmp_path):
    w = open_context(browser, name, live_servers)
    load(w)
    w.page.screenshot(path=str(tmp_path / f"page-{name}.png"), full_page=True)
    assert contrast_failures(w.page) == []
    show(w.page, "strategy")
    show(w.page, "activity")
    assert contrast_failures(w.page) == []
    w.context.close()


@pytest.mark.parametrize("name", ["desktop-light", "desktop-dark"])
def test_settings_text_passes_contrast(browser, live_servers, name):
    w = open_context(browser, name, live_servers)
    load(w)
    w.page.click("#b-settings")
    w.page.wait_for_selector("#settings-dialog[open]")
    assert contrast_failures(w.page, "#settings-dialog") == []
    w.page.click('[data-stab="game"]')
    assert contrast_failures(w.page, "#settings-dialog") == []
    w.context.close()


def test_a_refused_control_is_a_message_in_the_page(browser, live_servers):
    """The live pilot refuses an action (400): the page says why in a toast, and nothing blocks."""
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    dialogs = []
    w.page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    w.page.evaluate("control({action: 'override', directive: 'expand'})")
    w.page.wait_for_selector("#toast:not([hidden])", timeout=5000)
    assert "action must be" in w.page.text_content("#toast")
    assert dialogs == []
    w.context.close()


SERIES_JS = r"""
() => {
  const parse = (c) => { const m = /rgba?\(([^)]*)\)/.exec(c); const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const over = (t, u) => [0, 1, 2].map((i) => t[i] * t[3] + u[i] * (1 - t[3]));
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  let bg = [255, 255, 255];
  const chain = [];
  for (let e = document.getElementById("chartwrap"); e && e.nodeType === 1; e = e.parentElement) chain.push(getComputedStyle(e).backgroundColor);
  for (const c of chain.reverse()) { const p = parse(c); if (p[3] > 0) bg = over(p, bg); }
  const probe = document.createElement("i");
  document.body.append(probe);
  const out = {};
  for (let i = 1; i <= 6; i++) { probe.style.color = `var(--s${i})`; out[`--s${i}`] = +ratio(parse(getComputedStyle(probe).color), bg).toFixed(2); }
  probe.remove();
  return out;
}
"""


@pytest.mark.parametrize("name", ["desktop-light", "desktop-dark"])
def test_chart_series_stand_out_from_the_plot(browser, live_servers, name):
    """Ruling 33: the series colours --s1..--s6 reach 3:1 against the chart's background (graphics),
    in both themes; the same colours fill the legend swatches and the effort bar."""
    w = open_context(browser, name, live_servers)
    load(w)
    ratios = w.page.evaluate(SERIES_JS)
    assert all(r >= 3.0 for r in ratios.values()), ratios
    w.context.close()

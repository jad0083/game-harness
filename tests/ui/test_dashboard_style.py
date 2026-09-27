"""The dashboard's text is readable in both themes and on both widths (WCAG AA, measured on computed
colours), and a refused change is said in the page, never in a blocking alert()."""

from __future__ import annotations

import pytest
from uikit import CONTEXTS, contrast_failures, open_context

pytestmark = pytest.mark.ui


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", timeout=15000)
    w.page.wait_for_timeout(1200)


@pytest.mark.parametrize("name", list(CONTEXTS))
def test_page_text_passes_contrast(browser, live_servers, name, tmp_path):
    w = open_context(browser, name, live_servers)
    load(w)
    w.page.screenshot(path=str(tmp_path / f"page-{name}.png"), full_page=True)
    assert contrast_failures(w.page) == []
    w.page.click('.tabs [data-tab="strategy"]')
    w.page.click('.tabs [data-tab="activity"]')
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

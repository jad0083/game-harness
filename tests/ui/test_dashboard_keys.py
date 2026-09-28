"""Keyboard behaviour of the dashboard's sheets (ruling 31): focus returns to the opener when a dialog
opened from the ⋯ menu closes."""

from __future__ import annotations

import pytest
from uikit import open_context

pytestmark = pytest.mark.ui


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", state="attached", timeout=15000)
    w.page.wait_for_timeout(600)


def from_menu(page, act: str) -> None:
    """Open ⋯ and choose an item with the keyboard."""
    page.focus("#b-more")
    page.keyboard.press("Enter")
    page.wait_for_selector("#more-menu:not([hidden])")
    page.focus(f'#more-menu [data-act="{act}"]')
    page.keyboard.press("Enter")


@pytest.mark.parametrize(("name", "act", "dialog", "close"), [
    ("desktop-light", "stop", "#stop-dialog", "Escape"),
    ("desktop-light", "add", "#add-dialog", "#add-cancel"),
    ("desktop-dark", "devices", "#settings-dialog", "Escape"),
    ("phone-light", "settings", "#settings-dialog", "Escape"),
    ("phone-dark", "start", "#start-dialog", "Escape"),
])
def test_focus_returns_to_the_menu_button_when_a_sheet_closes(browser, live_servers, name, act, dialog, close):
    w = open_context(browser, name, live_servers)
    load(w)
    page = w.page
    if act == "start":                                  # Start run is offered only with no run live
        live_servers["log"].state.status = "stopped"
        live_servers["live"].call(live_servers["log"].emit, "status", status="stopped")
        page.wait_for_function("() => !document.querySelector('#more-menu [data-act=start]').hidden", timeout=8000)
    from_menu(page, act)
    page.wait_for_selector(f"{dialog}[open]")
    if close.startswith("#"):
        page.click(close)
    else:
        page.keyboard.press(close)
    page.wait_for_selector(f"{dialog}:not([open])", state="attached")
    assert page.evaluate("document.activeElement && document.activeElement.id") == "b-more"
    w.context.close()

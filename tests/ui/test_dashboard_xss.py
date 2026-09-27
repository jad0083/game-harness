"""Names a device chose never become markup on the page (a device may name itself, and rename others,
up to 60 characters), and the page's CSP runs only its own inline script: an injected handler or a
script from another host does not run."""

from __future__ import annotations

import pytest
from uikit import open_context, show

pytestmark = pytest.mark.ui

PAYLOAD = '<img src=x onerror="window.__xss=1">'


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", state="attached", timeout=15000)
    w.page.wait_for_timeout(800)


@pytest.mark.parametrize("name", ["desktop-dark", "phone-light"])
def test_a_device_name_in_the_talk_thread_is_text(browser, live_servers, name):
    log = live_servers["log"]
    live_servers["live"].call(log.emit, "chat", role="human", text="why the trader?", by=PAYLOAD)
    w = open_context(browser, name, live_servers)
    load(w)
    show(w.page, "talk")
    w.page.wait_for_selector("#thread .msg.human")
    assert w.page.evaluate("window.__xss") is None
    assert w.page.query_selector("#thread img") is None
    assert f"You ({PAYLOAD})" in w.page.text_content("#thread .msg.human .who")
    w.context.close()


def test_the_page_runs_no_injected_handler_or_foreign_script(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    w.page.evaluate("""() => {
      document.body.insertAdjacentHTML("beforeend", '<img src="x" onerror="window.__csp=1">');
      const s = document.createElement("script"); s.textContent = "window.__csp2 = 1"; document.body.append(s);
    }""")
    w.page.wait_for_timeout(500)
    assert w.page.evaluate("window.__csp") is None and w.page.evaluate("window.__csp2") is None
    assert w.page.evaluate("typeof renderGovernor") == "function"        # the page's own script ran
    w.context.close()

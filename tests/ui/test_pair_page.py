"""The sign-in page (/pair) and Add a device in a real browser: the ported shell in four contexts and
its states, the in-app warning, signing a second browser in by link and by typed words, Copy link
without a clipboard API (plain HTTP), and a browser that does not keep the cookie."""

from __future__ import annotations

import re
import urllib.request

import pytest
from uikit import CONTEXTS, open_context

from pilot.auth import CODE_WORDS

pytestmark = pytest.mark.ui
WEBVIEW_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 7; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
              "Chrome/140.0.0.0 Mobile Safari/537.36")
NO_CLIPBOARD = """
Object.defineProperty(Navigator.prototype, 'clipboard', { get: () => undefined, configurable: true });
document.addEventListener('copy', () => {
  const el = document.activeElement;
  window.__copied = el && 'value' in el ? el.value.substring(el.selectionStart, el.selectionEnd) : String(getSelection());
});
"""


def no_overflow(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


def expected_only(errors: list[str]) -> list[str]:
    """Console lines other than the browser's own note on an HTTP error status we meant to get."""
    return [e for e in errors if not re.search(r"status of (401|409|410|429)", e)]


@pytest.mark.parametrize("name", list(CONTEXTS))
def test_pair_page_states_render_cleanly(browser, live_servers, name, tmp_path):
    auth = live_servers["auth"]
    auth.throttle.unlock()
    grant = auth.store.create_grant("cli", words=True)
    w = open_context(browser, name, live_servers, signed_in=False)
    page = w.page
    page.goto(w.base + "/")                                   # not signed in: to the sign-in page
    assert "/pair" in page.url and page.is_visible("#v-signin") and page.is_visible("#words")
    assert page.text_content("h1") == "Sign in this browser"
    assert no_overflow(page)
    page.screenshot(path=str(tmp_path / f"pair-{name}.png"))
    page.goto(w.base + "/pair?reason=old_link")
    assert "stopped working" in page.text_content("#state")
    page.goto(f"{w.base}/pair#c={grant['link']}")
    page.wait_for_selector("#v-confirm:not([hidden])")
    assert page.is_hidden("#v-signin") and page.input_value("#name")
    assert no_overflow(page)
    page.screenshot(path=str(tmp_path / f"confirm-{name}.png"))
    page.goto(w.base + "/pair")
    for i in range(6):
        page.fill("#words", " ".join(CODE_WORDS[3 + i:6 + i]))
        page.click("#submit")
        page.wait_for_load_state()
        if i == 0:
            assert "don't match" in page.text_content("#state") and no_overflow(page)
    assert "Too many tries" in page.text_content("#state")
    assert page.is_disabled("#submit") and re.fullmatch(r"\d+:\d\d", page.text_content("#count"))
    assert no_overflow(page)
    page.screenshot(path=str(tmp_path / f"locked-{name}.png"))
    assert expected_only(w.errors) == [] and not [f for f in w.failed if not re.search(r"^(401|429) ", f)]
    w.context.close()
    auth.throttle.unlock()


def test_in_app_browser_is_warned_and_keeps_the_code(browser, live_servers):
    grant = live_servers["auth"].store.create_grant("cli", words=True)
    w = open_context(browser, "phone-dark", live_servers, signed_in=False, user_agent=WEBVIEW_UA)
    w.page.goto(f"{w.base}/pair#c={grant['link']}")
    w.page.wait_for_selector("#inapp")
    assert "You opened this inside another app" in w.page.text_content("#inapp")
    assert w.page.input_value("#inapp-address").endswith("#c=" + grant["link"])
    assert live_servers["auth"].store.grant(grant["id"])["state"] == "waiting"
    assert no_overflow(w.page)
    w.context.close()


def open_add_sheet(w):
    page = w.page
    page.goto(w.base + "/")
    page.wait_for_selector("#decisions li button", state="attached")
    page.click("#b-more")
    page.click('#more-menu [data-act="add"]')
    page.wait_for_selector("#add-dialog[open]")
    page.wait_for_function("() => document.getElementById('add-link').value.includes('/pair#c=')")
    return page


def test_second_browser_signs_in_by_link(browser, live_servers, tmp_path):
    a = open_context(browser, "desktop-dark", live_servers, device="Chrome on Windows")
    page = open_add_sheet(a)
    assert re.fullmatch(r"[a-z]+\s· [a-z]+\s· [a-z]+", page.text_content("#add-words").strip())
    link = page.input_value("#add-link")
    page.screenshot(path=str(tmp_path / "add-sheet.png"))
    b = open_context(browser, "phone-light", live_servers, signed_in=False)
    b.page.goto(link.replace("http://" + link.split("/")[2], b.base))
    b.page.wait_for_selector("#v-confirm:not([hidden])")
    b.page.click("#confirm-go")
    b.page.wait_for_selector("#decisions li button", state="attached")
    assert "#c=" not in b.page.url
    page.wait_for_function("() => document.getElementById('add-status').textContent.startsWith('Signed in:')", timeout=6000)
    assert "Chrome on Android" in page.text_content("#add-status")
    assert expected_only(a.errors + b.errors) == []
    a.context.close()
    b.context.close()


def test_second_browser_signs_in_by_typed_prefixes(browser, live_servers):
    a = open_context(browser, "desktop-light", live_servers, device="Chrome on Windows")
    page = open_add_sheet(a)
    words = re.split(r"\s· ", page.text_content("#add-words"))
    b = open_context(browser, "desktop-light", live_servers, signed_in=False)
    b.page.goto(b.base + "/#tab=strategy")
    b.page.fill("#words", " ".join(x[:3].upper() for x in words))
    b.page.click("#submit")
    b.page.wait_for_selector("#decisions li button", state="attached")
    assert b.page.url.endswith("/#tab=strategy")
    a.context.close()
    b.context.close()


def test_copy_link_works_without_the_clipboard_api(browser, live_servers):
    a = open_context(browser, "desktop-light", live_servers)
    a.context.add_init_script(NO_CLIPBOARD)
    page = open_add_sheet(a)
    assert page.evaluate("navigator.clipboard === undefined")
    page.click("#add-copy")
    assert page.text_content("#add-copy") in ("Copied", "Press Ctrl+C")
    assert page.evaluate("window.__copied") == page.input_value("#add-link")
    a.context.close()


def test_a_browser_that_drops_the_cookie_sees_why(browser, live_servers):
    grant = live_servers["auth"].store.create_grant("cli", words=True)
    w = open_context(browser, "desktop-light", live_servers, signed_in=False)

    def strip_cookie(route):
        """Send the sign-in outside the browser (route.fetch would store the cookie in the context) and
        hand back the answer without its Set-Cookie, as a browser that blocks cookies would see it."""
        req = route.request
        if req.method != "POST":
            return route.continue_()
        hdrs = {k: v for k, v in req.all_headers().items() if not k.startswith(":") and k.lower() != "cookie"}
        fwd = urllib.request.Request(req.url, data=req.post_data_buffer, method="POST", headers=hdrs)
        with urllib.request.urlopen(fwd, timeout=10) as resp:
            body, status = resp.read(), resp.status
            headers = {k: v for k, v in resp.headers.items() if k.lower() != "set-cookie"}
        return route.fulfill(status=status, headers=headers, body=body)

    w.page.route("**/pair", strip_cookie)
    w.page.goto(f"{w.base}/pair#c={grant['link']}")
    w.page.click("#confirm-go")
    w.page.wait_for_selector("#state", timeout=5000)
    assert "did not keep the sign-in" in w.page.text_content("#state")
    w.context.close()


def test_devices_tab_lists_this_browser_and_signs_another_out(browser, live_servers):
    auth = live_servers["auth"]
    other, _ = auth.store.create_device("browser", name="Brave on Windows", created_via="cli", created_by="cli")
    auth.store.create_device("script", name="laptop watch", scope="read", created_via="cli", created_by="cli")
    a = open_context(browser, "desktop-light", live_servers, device="Chrome on Windows")
    page = a.page
    page.goto(a.base + "/")
    page.wait_for_selector("#decisions li button", state="attached")
    page.click("#b-more")
    page.click('#more-menu [data-act="devices"]')
    page.wait_for_selector('[data-spanel="devices"]:not([hidden]) #dev-list')
    assert "Chrome on Windows" in page.text_content("#dev-this")
    assert "Brave on Windows" in page.text_content("#dev-list")
    assert "laptop watch" in page.text_content("#dev-scripts") and "read only" in page.text_content("#dev-scripts")
    page.once("dialog", lambda d: d.accept())
    page.click(f'#dev-list [data-signout="{other["id"]}"]')
    page.wait_for_function(f"() => !document.querySelector('#dev-list [data-signout=\"{other['id']}\"]')")
    assert auth.store.device(other["id"])["revoked_at"]
    assert expected_only(a.errors) == []
    a.context.close()


@pytest.mark.parametrize("name", ["phone-light", "desktop-dark"])
def test_a_bad_link_says_the_link_does_not_work(browser, live_servers, name):
    """A mistyped or cut-off link is answered about the link, not about typed words."""
    w = open_context(browser, name, live_servers, signed_in=False)
    page = w.page
    page.goto(f"{w.base}/pair#c=0123456789.{'x' * 43}")
    page.wait_for_selector("#v-confirm:not([hidden])")
    page.click("#confirm-go")
    page.wait_for_selector("#confirm-error:not([hidden])")
    text = page.text_content("#confirm-error")
    assert text.startswith("This link doesn't work") and "words don't match" not in text
    assert page.is_visible("#type-instead") and no_overflow(page)
    w.context.close()

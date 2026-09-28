"""The phone layout and the campaign list (U7: rulings 1, 4, 5, 13, 31, 32): at 390 px the page is its own
layout (a 52 px bar with the campaign and a state dot, a bottom nav Now · Decisions · Orders · Strategy ·
Talk, Reasoning and the campaign list as full-screen sheets, Activity at the end of Now), with no sideways
scroll and no text under 13 px; the campaign control is a list with each campaign's state, empty ones
folded away."""

from __future__ import annotations

import pytest
from uikit import open_context, pick_campaign

from pilot.events import EventLog

pytestmark = pytest.mark.ui

NO_OVERFLOW = "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
# visible text under 13 px (ruling 32), ignoring screen-reader-only text
SMALL_TEXT = r"""() => {
  const out = [];
  for (const el of document.querySelectorAll("body *")) {
    if (el.closest(".sr, script, style, option, title, dialog:not([open]), details:not([open]) > :not(summary)")) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own || !el.getClientRects().length) continue;
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (r.width === 0 || cs.visibility === "hidden") continue;
    const size = parseFloat(cs.fontSize);
    if (size < 13) out.push(`${size}px <${el.tagName.toLowerCase()} class="${el.getAttribute("class") || ""}"> ${el.textContent.trim().slice(0, 30)}`);
  }
  return [...new Set(out)];
}"""


def load(w):
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#decisions li button", state="attached", timeout=15000)
    w.page.wait_for_timeout(1000)


def nav(page, view):
    page.click(f'#bottom-nav a[data-view="{view}"]')
    page.wait_for_timeout(250)


def add_empty_campaign(servers):
    empty = EventLog(servers["runs"], "20260925-080000", "m", telemetry=servers["tel"])
    empty.emit("run_start", game="galciv4", model="m")
    empty.set_campaign("galciv4", "untitled", "")
    empty.emit("run_end")
    empty.close()


@pytest.mark.parametrize("name", ["phone-light", "phone-dark"])
def test_every_phone_view_fits_and_is_one_tap_away(browser, live_servers, name, tmp_path):
    w = open_context(browser, name, live_servers)
    load(w)
    page = w.page
    bar = page.eval_on_selector(".bar", "e => e.getBoundingClientRect().height")
    assert bar <= 56, bar
    assert page.is_hidden("#b-toggle") and page.is_hidden("#b-settings") and page.is_hidden("#pc")
    assert page.is_visible("#state-dot")
    assert page.text_content("#campaign").replace("▾", "").split() == ["Kublai", "Khan", "T57"]
    links = page.eval_on_selector_all("#bottom-nav a", "as => as.filter(a => a.offsetParent).map(a => a.textContent.trim())")
    assert links == ["Now", "Decisions", "Orders", "Strategy", "Talk"]
    box = page.eval_on_selector("#bottom-nav", "e => { const r = e.getBoundingClientRect(); return [r.height, r.bottom, innerHeight]; }")
    assert box[0] >= 56 and abs(box[1] - box[2]) < 1, box
    assert page.get_attribute('#bottom-nav a[data-view="now"]', "aria-current") == "page"
    # Now: the figures, the chart and the recent problems, then all activity
    assert page.is_visible("#figures") and page.is_visible("#p-chart") and page.is_visible("#p-problems")
    assert page.is_hidden("#p-dec") and page.is_hidden("#msg")
    assert page.evaluate(NO_OVERFLOW)
    small = page.evaluate(SMALL_TEXT)
    assert small == [], small
    page.screenshot(path=str(tmp_path / f"now-{name}.png"), full_page=True)
    page.click("#all-activity")
    page.wait_for_selector("#feed li.ev")
    assert page.is_visible("#feed") and page.evaluate(NO_OVERFLOW)
    for view, visible in (("decisions", "#decisions"), ("levers", "#levers"), ("strategy", "#strategy"), ("talk", "#msg")):
        nav(page, view)
        assert page.is_visible(visible), view
        assert page.is_hidden("#p-chart") and page.is_hidden(".tabs"), view
        assert page.get_attribute(f'#bottom-nav a[data-view="{view}"]', "aria-current") == "page"
        assert page.evaluate(NO_OVERFLOW), view
        small = page.evaluate(SMALL_TEXT)
        assert small == [], (view, small)
        page.screenshot(path=str(tmp_path / f"{view}-{name}.png"), full_page=True)
    assert w.errors == []
    w.context.close()


def test_a_decision_opens_reasoning_as_a_sheet_and_back_returns(browser, live_servers):
    w = open_context(browser, "phone-dark", live_servers)
    load(w)
    page = w.page
    nav(page, "decisions")
    page.click('#decisions button[data-i="0"]')
    page.wait_for_selector("#tab-reasoning .t-decision")
    sheet = page.eval_on_selector("#tab-reasoning", "e => { const r = e.getBoundingClientRect(); return [r.top, r.left, r.width, r.height, getComputedStyle(e).position]; }")
    assert sheet[:3] == [0, 0, 390] and sheet[3] >= 844 - 1 and sheet[4] == "fixed", sheet
    assert page.is_visible("#reading-back")
    assert page.evaluate(NO_OVERFLOW) and page.evaluate(SMALL_TEXT) == []
    page.click("#reading-back")
    page.wait_for_timeout(300)
    assert page.is_hidden("#tab-reasoning") or page.eval_on_selector("#tab-reasoning", "e => getComputedStyle(e).position") != "fixed"
    assert page.is_visible("#decisions")
    assert page.evaluate("document.activeElement.dataset.i") == "0"          # focus back on the row
    page.click('#decisions button[data-i="1"]')                              # the browser's back closes it too
    page.wait_for_selector("#tab-reasoning .t-error")
    page.go_back()
    page.wait_for_timeout(300)
    assert page.is_visible("#decisions") and page.url.startswith(w.base)
    assert w.errors == []
    w.context.close()


def test_the_more_menu_holds_pause_and_settings_on_a_phone(browser, live_servers):
    w = open_context(browser, "phone-light", live_servers)
    load(w)
    page = w.page
    page.click("#b-more")
    items = page.eval_on_selector_all("#more-menu button", "bs => bs.filter(b => b.offsetParent).map(b => b.textContent.trim())")
    assert items[:2] == ["Pause", "Stop the run…"] and {"Settings", "Add a device", "Sign out"} <= set(items), items
    assert "mini-rig2" in page.text_content("#menu-pc")
    page.click('#more-menu [data-act="settings"]')
    page.wait_for_selector("#settings-dialog[open]")
    size = page.eval_on_selector("#settings-dialog", "e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }")
    assert size[0] >= 389 and size[1] >= 843, size                          # a full-screen sheet
    assert page.evaluate(NO_OVERFLOW)
    page.click('#settings-dialog button[value="close"]')
    page.click("#b-more")
    page.click('#more-menu [data-act="toggle"]')
    page.wait_for_timeout(500)
    assert live_servers["pilot"].calls == ["pause"]
    w.context.close()


@pytest.mark.parametrize("name", ["desktop-light", "phone-dark"])
def test_the_campaign_list_says_what_is_live_and_folds_empty_ones(browser, live_servers, name):
    add_empty_campaign(live_servers)
    w = open_context(browser, name, live_servers)
    load(w)
    page = w.page
    assert page.get_attribute("#campaign", "data-cid") == "civ6/kublai"
    page.click("#campaign")
    page.wait_for_selector("#camp-dialog[open]")
    rows = page.eval_on_selector_all("#camp-list button", "bs => bs.map(b => b.textContent.replace(/\\s+/g, ' ').trim())")
    assert len(rows) == 2 and rows[0].startswith("Kublai Khan, China") and "live" in rows[0], rows
    assert "Civ VI" in rows[0] and "T57" in rows[0] and "2 decisions" in rows[0]
    assert rows[1].startswith("Theian Union") and "stopped" in rows[1] and "2288.06" in rows[1]
    assert page.is_hidden("#camp-empty-list button")
    assert "1" in page.text_content("#camp-empty summary")
    assert page.get_attribute('#camp-list button[data-cid="civ6/kublai"]', "aria-current") == "true"
    if name.startswith("phone"):
        size = page.eval_on_selector("#camp-dialog", "e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }")
        assert size[0] >= 389 and size[1] >= 843, size
    page.click('#camp-list button[data-cid="stellaris/theia"]')
    page.wait_for_function("() => document.getElementById('gov').dataset.state === 'history'")
    assert page.get_attribute("#campaign", "data-cid") == "stellaris/theia"
    assert "Theian Union" in page.text_content("#campaign")
    assert page.evaluate(NO_OVERFLOW)
    assert w.errors == []
    w.context.close()


def test_pick_campaign_helper_and_desktop_bar(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    load(w)
    page = w.page
    assert page.is_hidden("#bottom-nav") and page.is_hidden("#state-dot") and page.is_hidden("#p-problems")
    assert page.text_content("#campaign").replace("▾", "").strip() == "Kublai Khan, China · T57"
    pick_campaign(page, "stellaris/theia")
    assert page.get_attribute("#campaign", "data-cid") == "stellaris/theia"
    w.context.close()


@pytest.mark.parametrize("scenario", ["needs"])
@pytest.mark.parametrize("name", ["phone-dark", "phone-light"])
def test_on_deploy_day_the_notices_leave_the_governor_line_first(browser, live_servers, name, tmp_path):
    """Deploy day as the runbook has it: Chrome and the phone carried over, Brave added from Chrome, and
    the run needs you. The governor line stays the first thing under the bar and Resume is on the first
    screen; the device notices come after it, folded into one line with one Review and one Dismiss."""
    from uikit import CONTEXTS
    auth = live_servers["auth"]
    chrome, _ = auth.store.create_device("browser", name="Chrome on Windows", created_via="legacy_cookie",
                                         created_by="legacy_link", ip="192.168.1.77", legacy=True)
    g = auth.store.create_grant(chrome["id"], words=True)
    auth.store.redeem("words", g["words"], ip="192.168.1.77", name="Brave on Windows")
    _, cred = auth.store.create_device("browser", name="Chrome on Android", created_via="legacy_cookie",
                                       created_by="legacy_link", ip="127.0.0.1", legacy=True)
    w = open_context(browser, name, live_servers, signed_in=False)
    w.context.add_cookies([{"name": "pilot_session", "value": cred, "url": w.base, "httpOnly": True, "sameSite": "Lax"}])
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#notices:not([hidden])", timeout=15000)
    w.page.wait_for_timeout(800)
    page = w.page
    w.page.screenshot(path=str(tmp_path / f"deployday-{name}.png"))
    gov, notes = page.locator("#gov").bounding_box(), page.locator("#notices").bounding_box()
    assert gov["y"] < 120, gov                                       # directly under the bar
    assert notes["y"] >= gov["y"] + gov["height"] - 1, (gov, notes)  # the notices come after the hero
    resume = page.locator("#gov-resume").bounding_box()
    nav = CONTEXTS[name]["viewport"]["height"] - 56
    assert resume["y"] + resume["height"] <= nav, (resume, nav)      # Resume on the first screen, above the nav
    assert page.locator("#notices .notice").count() == 1             # folded
    text = page.text_content("#notices")
    assert "own sign-in" in text and "Brave on Windows" in text and "Chrome on Windows signed in" not in text
    assert page.locator("#notices [data-dismiss]").count() == 1
    page.click("#notices [data-dismiss]")
    assert page.is_hidden("#notices")
    w.context.close()


@pytest.mark.parametrize("name", ["phone-light", "phone-dark"])
def test_rivals_are_two_line_cards_on_a_phone(browser, live_servers, name):
    """Ruling 32: tables become two-line cards on a phone. Civilizations met: the name with its tags (at
    war) on the first line, the other columns as labelled pairs on the second, all inside the screen; no
    sideways scroll inside the box (a phone shows no scrollbar to tell)."""
    w = open_context(browser, name, live_servers)
    load(w)
    page = w.page
    page.eval_on_selector("#p-nb", "e => e.scrollIntoView()")
    assert page.eval_on_selector(".nbwrap", "e => e.scrollWidth <= e.clientWidth + 1")
    right = page.evaluate("Math.max(...[...document.querySelectorAll('#nb td')].filter(t => t.offsetParent).map(t => t.getBoundingClientRect().right))")
    assert right <= 390 - 16 + 1, right
    first = page.locator("#nb tbody tr").first
    assert first.locator(".who").is_visible() and "at war" in first.locator(".who").text_content()
    cells = first.locator("td[data-label]").evaluate_all("ts => ts.filter(t => t.offsetParent).map(t => getComputedStyle(t, '::before').content)")
    assert any("Cities" in c for c in cells) and any("Score" in c for c in cells), cells
    w.context.close()


SMALL_TARGETS_JS = r"""
(root) => [...(root || document).querySelectorAll("button, summary, a[href], [role=tab], [role=menuitem], select, input[type=checkbox]")]
  .filter((e) => e.offsetParent && !e.closest("[hidden], .sr, svg") && getComputedStyle(e).visibility !== "hidden")
  .map((e) => e.type === "checkbox" && e.closest("label") ? e.closest("label") : e)        // its label is the target
  .map((e) => { const r = e.getBoundingClientRect(); return [e.id || e.className || e.tagName, (e.textContent || "").trim().slice(0, 24), Math.round(r.width), Math.round(r.height)]; })
  .filter(([, , w, h]) => h < 44 || w < 44)
"""


@pytest.mark.parametrize("scenario", ["needs"])
@pytest.mark.parametrize("name", ["phone-dark", "phone-light"])
def test_every_tap_target_is_at_least_44px_on_a_phone(browser, live_servers, name):
    """Ruling 31: collapsible headers (and every other control) are at least 44 px to tap on a phone:
    the Now view with the needs-you card, Orders with its filters, the ⋯ menu and Settings."""
    w = open_context(browser, name, live_servers)
    load(w)
    page = w.page
    assert page.evaluate(SMALL_TARGETS_JS) == []
    page.click('#bottom-nav a[data-view="levers"]')
    page.wait_for_timeout(500)
    assert page.evaluate(SMALL_TARGETS_JS) == []
    page.click('#bottom-nav a[data-view="now"]')
    page.click("#b-more")
    page.wait_for_selector("#more-menu:not([hidden])")
    assert page.evaluate(SMALL_TARGETS_JS, page.query_selector("#more-menu")) == []
    page.click('#more-menu [data-act="settings"]')
    page.wait_for_selector("#settings-dialog[open]")
    for tab in ("models", "game", "devices"):
        page.click(f'[data-stab="{tab}"]')
        page.wait_for_timeout(300)
        assert page.evaluate(SMALL_TARGETS_JS, page.query_selector("#settings-dialog")) == [], tab
    w.context.close()


@pytest.mark.parametrize("name", ["phone-dark", "phone-light"])
def test_the_sign_in_page_targets_are_at_least_44px(browser, live_servers, name):
    grant = live_servers["auth"].store.create_grant("cli", words=True)
    w = open_context(browser, name, live_servers, signed_in=False)
    w.page.goto(w.base + "/pair")
    assert w.page.evaluate(SMALL_TARGETS_JS) == []
    w.page.goto(f"{w.base}/pair#c={grant['link']}")
    w.page.wait_for_selector("#v-confirm:not([hidden])")
    assert w.page.evaluate(SMALL_TARGETS_JS) == []
    w.context.close()

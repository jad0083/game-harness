"""The sign-in UI speaks of "the computer that runs Game Pilot", never "the controller" or "cli" (the
redesign's word list), and the sign-in log reads as sentences with the device first ("Firefox on Linux
signed out by Chrome on Android"), never as two names in a row."""

from __future__ import annotations

import asyncio
import json
import re

from authkit import browser_cookie, client, origin, viewer

from pilot import auth as A

PAGE = (A.STATIC / "dashboard.html").read_text(encoding="utf-8")
PAIR = (A.STATIC / "pair.html").read_text(encoding="utf-8")


def _words(text: str) -> list[str]:
    return re.findall(r"\bcontroller\b|\(cli\)|\bcli\b", text)


def test_devices_notices_log_and_401s_name_no_controller(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    store = auth.store
    chrome, chrome_cookie = browser_cookie(auth, name="Chrome on Android")
    g = store.create_grant("cli", words=True)
    _, made = store.redeem("link", g["link"], ip="192.168.1.77", user_agent="Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0")
    firefox = made["device"]["id"]
    store.revoke(firefox, "revoked", by=chrome, ip="192.168.1.140")
    g2 = store.create_grant("cli", words=True)
    store.redeem("words", g2["words"], ip="192.168.1.77", name="Brave on Windows")
    old_id, old_cookie = browser_cookie(auth, name="Old phone")
    store.revoke(old_id, "revoked", by="cli")

    async def go():
        async with client(app, chrome_cookie) as c:
            me = await (await c.get("/api/auth/me")).json()
            devs = await (await c.get("/api/auth/devices")).json()
            log = await (await c.get("/api/auth/log")).json()
        async with client(app, old_cookie) as c:
            r = await c.get("/status")
            refused = await r.json()
        return me, devs, log, refused
    me, devs, log, refused = asyncio.run(go())
    texts = [n["text"] for n in me["notices"]] + [e["text"] for e in log["events"]]
    texts += [json.dumps([d["name"], d["created_by"], d["badges"]]) for d in devs["devices"]]    # what Devices shows
    texts += [refused["reason"], refused["fix"], str(refused["by"])]
    assert not [t for t in texts if _words(t)], texts
    assert "signed out from the computer that runs Game Pilot" in refused["reason"]
    assert any(t.startswith("Firefox on Linux signed out by Chrome on Android") for t in texts), texts
    assert any(t.startswith("Firefox on Linux signed in with a code from the computer that runs Game Pilot")
               for t in texts), texts
    assert any("New device signed in: Brave on Windows, added with a code from the computer that runs Game Pilot" in t
               for t in texts), texts


def test_pages_say_the_computer_that_runs_game_pilot():
    for page in (PAGE, PAIR):
        user_text = re.sub(r'"the controller"', "", page)     # the service principal's name, compared, never shown
        assert "on the controller" not in user_text and "from the controller" not in user_text
        assert "(cli)" not in user_text
    assert "the computer that runs Game Pilot" in PAGE


def test_signed_out_by_the_cli_on_the_pair_page(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    dev, cookie = browser_cookie(auth)
    auth.store.revoke(dev, "revoked", by="cli")

    async def go():
        async with client(app, cookie) as c:
            return await (await c.get("/pair?reason=revoked", headers=origin(c))).text()
    page = asyncio.run(go())
    assert "signed out from the computer that runs Game Pilot" in page and not _words(page.split("<main>")[1])

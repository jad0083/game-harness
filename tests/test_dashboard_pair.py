"""Signing a browser in (rulings 39-44, 47, 51): three words to type or a 256-bit link, one grant used
once within 10 minutes; throttles on the typed words only; a spent grant presented again signs out
the device it made; the sign-in page, Add a device, and the dashboard-link / dashboard-devices CLI."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import threading
from contextlib import redirect_stdout
from urllib.parse import quote

import pytest
from authkit import KEY, browser_cookie, client, origin, viewer

from pilot import auth as A
from pilot import cli

UA_CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
UA_WEBVIEW = ("Mozilla/5.0 (Linux; Android 14; Pixel 7; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
              "Chrome/140.0 Mobile Safari/537.36")
UA_INSTAGRAM = UA_WEBVIEW.replace("; wv)", ")") + " Instagram 350.0.0.0"


def link_of(grant: dict) -> str:
    return grant["link"]


def words_of(grant: dict) -> str:
    return grant["words"]


# ---------- the word list and normalisation ----------

def test_vendored_word_list_has_1296_unique_prefixes():
    assert len(A.WORDS) == 1296
    assert len({w[:3] for w in A.WORDS}) == 1296
    assert all(re.fullmatch(r"[a-z]{3,10}", w) for w in A.CODE_WORDS)
    assert A.WORDS[:2] == ["aardvark", "abandoned"] and set(A.WORDS) - set(A.CODE_WORDS) == {"yo-yo"}
    text = (A.WORDS_FILE).read_text(encoding="utf-8")
    assert "CC BY 3.0" in text and "Electronic Frontier Foundation" in text


def test_words_normalise_case_separators_and_prefixes():
    a, b, c = A.WORDS[100], A.WORDS[600], A.WORDS[1200]
    want = f"{a} {b} {c}"
    for typed in (want, want.upper(), f"{a}-{b.upper()}  {c}", f" {a[:3]}, {b[:3]}. {c[:3]} ", f"{a[:4]} {b} {c[:3]}"):
        assert A.canonical_words(typed) == want, typed
    for bad in (f"{a} {b}", f"{a} {b} {c} {a}", f"{a} {b} zzq", f"{a[:3]}x {b} {c}", f"{a[:2]} {b} {c}", "", "1 2 3"):
        assert A.canonical_words(bad) is None, bad


# ---------- grants ----------

def test_a_link_works_once_and_only_through_the_json_body(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    grant = auth.store.create_grant("cli", words=True)

    async def go():
        async with client(app, headers={"User-Agent": UA_CHROME}) as c:
            for path in (f"/pair?c={link_of(grant)}", "/pair", "/pair"):       # opening pages never spends anything
                r = await c.get(path)
                assert r.status == 200 and "Set-Cookie" not in r.headers
            assert auth.store.grant(grant["id"])["state"] == "waiting"
            r = await c.post("/pair", json={"link": link_of(grant), "name": "", "client": "Brave", "next": "/#tab=talk"},
                             headers=origin(c))
            assert r.status == 200
            j = await r.json()
            assert j["next"] == "/pair?check=1&next=" + quote("/#tab=talk", safe="")
            assert r.headers["Set-Cookie"].startswith("pilot_session=s1.")
            me = await (await c.get("/api/auth/me")).json()
            assert me["device"]["name"] == "Brave on Windows"
            r = await c.get(j["next"], allow_redirects=False)                     # the cookie stuck: on to next
            assert r.status == 303 and r.headers["Location"] == "/#tab=talk"
    asyncio.run(go())
    g = auth.store.grant(grant["id"])
    assert g["state"] == "used" and g["device_id"]
    dev = auth.store.device(g["device_id"])
    assert dev["created_via"] == "link" and dev["created_by"] == "cli" and dev["grant_id"] == grant["id"]


def test_typed_words_sign_in_and_a_code_expires_after_10_minutes(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    g1 = auth.store.create_grant("cli", words=True)
    g2 = auth.store.create_grant("cli", words=True)
    short = " ".join(w[:3].upper() for w in words_of(g1).split())

    async def go():
        async with client(app) as c:
            r = await c.post("/pair", json={"words": short, "next": "/"}, headers=origin(c))
            assert r.status == 200 and "pilot_session=" in r.headers["Set-Cookie"]
        clock.t += 601
        async with client(app) as c:
            r = await c.post("/pair", json={"words": words_of(g2)}, headers=origin(c))
            assert r.status == 410 and (await r.json())["error"] == "expired"
            r = await c.post("/pair", json={"link": link_of(g2)}, headers=origin(c))
            assert r.status == 410 and (await r.json())["error"] == "expired"
    asyncio.run(go())
    assert auth.store.device(auth.store.grant(g1["id"])["device_id"])["created_via"] == "words"


def test_malformed_words_are_refused_without_counting(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    auth.store.create_grant("cli", words=True)

    async def go():
        async with client(app) as c:
            for typed in ("one two", "a b c d", "zzq zzq zzq"):
                r = await c.post("/pair", json={"words": typed}, headers=origin(c))
                assert r.status == 400 and (await r.json())["error"] == "bad_words"
    asyncio.run(go())
    assert auth.throttle.failures(A.bucket_of("127.0.0.1")) == 0


def test_one_live_grant_per_browser_three_in_all_and_the_cli_exempt(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    cookies = [browser_cookie(auth, name=f"b{i}")[1] for i in range(4)]

    async def go():
        async with client(app, cookies[0]) as c:
            first = await (await c.post("/api/auth/grants", json={}, headers=origin(c))).json()
            second = await (await c.post("/api/auth/grants", json={}, headers=origin(c))).json()
            assert first["id"] != second["id"]
            assert auth.store.grant(first["id"])["state"] == "cancelled"
            assert len(second["words"].split()) == 3 and "/pair#c=" in second["link"]
        for ck in cookies[1:3]:
            async with client(app, ck) as c:
                assert (await c.post("/api/auth/grants", json={}, headers=origin(c))).status == 200
        async with client(app, cookies[3]) as c:
            r = await c.post("/api/auth/grants", json={}, headers=origin(c))
            assert r.status == 429 and (await r.json())["error"] == "too_many_codes"
    asyncio.run(go())
    assert auth.store.create_grant("cli", words=True)["id"]          # the CLI is never limited


def test_add_device_limited_to_the_cli(tmp_path, clock, monkeypatch):
    monkeypatch.setenv("PILOT_ADD_DEVICE", "cli")
    app, auth = viewer(tmp_path, clock)
    _, cookie = browser_cookie(auth)

    async def go():
        async with client(app, cookie) as c:
            r = await c.post("/api/auth/grants", json={}, headers=origin(c))
            assert r.status == 403 and "dashboard-link" in (await r.json())["fix"]
            assert (await (await c.get("/api/auth/me")).json())["add_device"] == "cli"
    asyncio.run(go())


def test_grant_status_is_visible_only_to_the_browser_that_made_it(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    _, mine = browser_cookie(auth, name="Chrome on Windows")
    _, other = browser_cookie(auth, name="Other")

    async def go():
        async with client(app, mine) as c:
            g = await (await c.post("/api/auth/grants", json={}, headers=origin(c))).json()
            st = await (await c.get(f"/api/auth/grants/{g['id']}")).json()
            assert st["state"] == "waiting" and st["device"] is None
        async with client(app, other) as c:
            assert (await c.get(f"/api/auth/grants/{g['id']}")).status == 404
        async with client(app, headers={"User-Agent": UA_CHROME.replace("Windows NT 10.0; Win64; x64", "Linux; Android 14")}) as c:
            r = await c.post("/pair", json={"link": g["link"].split("#c=")[1]}, headers=origin(c))
            assert r.status == 200
        async with client(app, mine) as c:
            st = await (await c.get(f"/api/auth/grants/{g['id']}")).json()
            assert st["state"] == "used" and st["device"]["name"] == "Chrome on Android" and st["device"]["ip"] == "127.0.0.1"
            me = await (await c.get("/api/auth/me")).json()
            assert any(n["kind"] == "new_device" and "Chrome on Android" in n["text"] and "Chrome on Windows" in n["text"]
                       for n in me["notices"])
            g2 = await (await c.post("/api/auth/grants", json={}, headers=origin(c))).json()
            assert (await c.post(f"/api/auth/grants/{g2['id']}/cancel", json={}, headers=origin(c))).status == 200
            assert auth.store.grant(g2["id"])["state"] == "cancelled"
    asyncio.run(go())


def test_a_signed_in_browser_opening_a_link_keeps_its_session_and_does_not_spend_it(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    _, cookie = browser_cookie(auth)
    g = auth.store.create_grant("cli", words=True)

    async def go():
        async with client(app, cookie) as c:
            r = await c.get("/pair?next=/%23tab%3Dtalk", allow_redirects=False)
            assert r.status == 303 and r.headers["Location"] == "/#tab=talk"
            r = await c.post("/pair", json={"link": link_of(g), "next": "/"}, headers=origin(c))
            assert r.status == 200 and (await r.json())["already"] is True and "Set-Cookie" not in r.headers
    asyncio.run(go())
    assert auth.store.grant(g["id"])["state"] == "waiting" and len(auth.store.list_devices()) == 1


# ---------- throttles ----------

def test_five_wrong_words_from_one_address_get_429(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    auth.store.create_grant("cli", words=True)
    wrong = " ".join(A.WORDS[:3])

    async def go():
        async with client(app) as c:
            for left in (4, 3, 2, 1, 0):
                r = await c.post("/pair", json={"words": wrong}, headers=origin(c))
                assert r.status == 401 and (await r.json())["error"] == "wrong_code"
            r = await c.post("/pair", json={"words": wrong}, headers=origin(c))
            assert r.status == 429 and int(r.headers["Retry-After"]) > 0
            assert (await r.json())["error"] == "too_many"
    asyncio.run(go())


def test_twenty_failures_across_addresses_lock_words_for_everyone_but_links_still_work(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    g = auth.store.create_grant("cli", words=True)
    for i in range(20):
        auth.throttle.fail(A.bucket_of(f"10.0.0.{i}"))

    async def go():
        async with client(app) as c:
            r = await c.post("/pair", json={"words": words_of(g)}, headers=origin(c))
            assert r.status == 429
            r = await c.post("/pair", json={"link": link_of(g)}, headers=origin(c))
            assert r.status == 200
    asyncio.run(go())


def test_a_valid_link_from_a_locked_address_works(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    g = auth.store.create_grant("cli", words=True)
    for _ in range(5):
        auth.throttle.fail(A.bucket_of("127.0.0.1"))

    async def go():
        async with client(app) as c:
            assert (await c.post("/pair", json={"words": words_of(g)}, headers=origin(c))).status == 429
            assert (await c.post("/pair", json={"link": link_of(g)}, headers=origin(c))).status == 200
    asyncio.run(go())


def test_five_wrong_words_in_all_switch_off_the_words_of_live_grants(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    _, cookie = browser_cookie(auth)
    wrong = " ".join(A.WORDS[3:6])

    async def go():
        async with client(app, cookie) as a:
            g = await (await a.post("/api/auth/grants", json={}, headers=origin(a))).json()
        for i in range(5):                    # five different addresses: no bucket is locked
            auth.throttle.refund(A.bucket_of("127.0.0.1"))
            async with client(app) as c:
                r = await c.post("/pair", json={"words": wrong}, headers=origin(c))
                assert r.status == 401, i
        auth.throttle.unlock()
        async with client(app) as c:
            r = await c.post("/pair", json={"words": g["words"]}, headers=origin(c))
            j = await r.json()
            assert r.status == 401 and j["words_off"] is True
            assert (await c.post("/pair", json={"link": g["link"].split("#c=")[1]}, headers=origin(c))).status == 200
        async with client(app, cookie) as a:
            st = await (await a.get(f"/api/auth/grants/{g['id']}")).json()
            assert st["words_off"] is True
    asyncio.run(go())
    assert any(r["event"] == "words_switched_off" for r in auth.store.audit_rows())


def test_twenty_parallel_wrong_tries_from_one_address_make_exactly_five_checks(tmp_path, clock, monkeypatch):
    app, auth = viewer(tmp_path, clock)
    auth.store.create_grant("cli", words=True)
    checks: list = []
    real = auth.store.grant_by_words
    monkeypatch.setattr(auth.store, "grant_by_words", lambda w: checks.append(w) or real(w))
    wrong = " ".join(A.WORDS[6:9])

    async def go():
        async with client(app) as c:
            rs = await asyncio.gather(*[c.post("/pair", json={"words": wrong}, headers=origin(c)) for _ in range(20)])
            assert sorted(r.status for r in rs) == [401] * 5 + [429] * 15
    asyncio.run(go())
    assert len(checks) == 5


def test_unlock_clears_every_bucket_and_needs_the_service_key(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    _, cookie = browser_cookie(auth)
    for i in range(30):
        auth.throttle.fail(A.bucket_of(f"10.0.1.{i}"))

    async def go():
        async with client(app, cookie) as c:
            assert (await c.post("/api/auth/unlock", json={}, headers=origin(c))).status == 403
        async with client(app) as c:
            r = await c.post("/api/auth/unlock", json={}, headers={"X-Pilot-Key": KEY})
            assert r.status == 200
    asyncio.run(go())
    assert auth.throttle.blocked(A.bucket_of("10.0.1.3")) == 0
    assert any(r["event"] == "unlock" for r in auth.store.audit_rows())


# ---------- a spent grant presented again ----------

def test_a_spent_grant_from_another_client_signs_out_the_device_it_made(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    _, watcher = browser_cookie(auth, name="Pixel phone")
    g = auth.store.create_grant("cli", words=True)

    async def go():
        async with client(app, headers={"User-Agent": UA_CHROME.replace("Chrome/140.0", "Chrome/140.0 Brave")}) as first:
            r = await first.post("/pair", json={"link": link_of(g), "client": "Brave"}, headers=origin(first))
            assert r.status == 200
            clock.t += 30
            async with client(app) as second:
                r = await second.post("/pair", json={"words": words_of(g)}, headers=origin(second))
                j = await r.json()
                assert r.status == 409 and j["error"] == "conflict"
                assert "Brave on Windows" in j["reason"] and "127.0.0.1" in j["reason"] and "30 s ago" in j["reason"]
            r = await first.get("/status")
            assert r.status == 401 and (await r.json())["error"] == "conflict"
        async with client(app, watcher) as w:
            me = await (await w.get("/api/auth/me")).json()
            assert any(n["kind"] == "conflict" and "Brave on Windows" in n["text"] for n in me["notices"])
    asyncio.run(go())
    assert auth.store.grant(g["id"])["state"] == "conflict"
    assert any(r["event"] == "grant_conflict" for r in auth.store.audit_rows())


def test_the_device_a_grant_made_may_present_it_again(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    g = auth.store.create_grant("cli", words=True)

    async def go():
        async with client(app) as c:
            assert (await c.post("/pair", json={"link": link_of(g)}, headers=origin(c))).status == 200
            r = await c.post("/pair", json={"link": link_of(g)}, headers=origin(c))      # a double tap
            assert r.status == 200 and (await r.json())["already"] is True
            assert (await c.get("/status")).status == 200
    asyncio.run(go())
    assert auth.store.grant(g["id"])["state"] == "used"


@pytest.mark.parametrize("how", ["revoke", "revoke_others", "cli_revoke_all", "store_only"])
@pytest.mark.parametrize("face", ["link", "words"])
def test_a_signed_out_device_leaves_no_code_behind(tmp_path, clock, monkeypatch, how, face):
    """A stolen session that keeps a code live (a new one every 9 minutes) gets nothing from it once
    that session is signed out: the code is cancelled with it, and a code whose maker is signed out
    is refused however it was signed out (store_only: a revoke that left the grant waiting)."""
    app, auth = viewer(tmp_path, clock)
    owner, _ = browser_cookie(auth, name="Owner's Chrome")
    thief, _ = browser_cookie(auth, name="Stolen session")
    g = auth.store.create_grant(thief, words=True)
    if how == "revoke":
        auth.store.revoke(thief, "revoked", by=owner)
    elif how == "revoke_others":
        auth.store.revoke_others(owner, by=owner)
    elif how == "cli_revoke_all":
        monkeypatch.setenv("PILOT_AUTH_DB", str(auth.store.path))
        with redirect_stdout(io.StringIO()):
            assert cli.main(["dashboard-devices", "revoke-all", "--except", owner]) == 0
    else:
        auth.store._x("UPDATE devices SET revoked_at=?, revoke_reason='revoked' WHERE id=?", (clock(), thief))
    if how != "store_only":
        assert auth.store.grant(g["id"])["state"] == "cancelled"

    async def go():
        async with client(app) as c:
            r = await c.post("/pair", json={face: link_of(g) if face == "link" else words_of(g)}, headers=origin(c))
            assert r.status == 410, await r.text()
            assert "pilot_session" not in r.headers.get("Set-Cookie", "")
    asyncio.run(go())
    live = [d for d in auth.store.list_devices() if d["kind"] == "browser"]
    assert [d["id"] for d in live] == [owner]


def test_a_wrong_link_token_counts_and_is_refused(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    g = auth.store.create_grant("cli", words=True)

    async def go():
        async with client(app) as c:
            bad = g["id"] + "." + "x" * 43
            r = await c.post("/pair", json={"link": bad}, headers=origin(c))
            assert r.status == 401 and (await r.json())["error"] == "wrong_code"
            r = await c.post("/pair", json={"link": "garbage"}, headers=origin(c))
            assert r.status == 401
    asyncio.run(go())
    assert auth.throttle.failures(A.bucket_of("127.0.0.1")) == 2
    assert auth.store.grant(g["id"])["state"] == "waiting"


# ---------- the form fallback (no script) ----------

def test_the_no_script_form_takes_words_only_with_a_matching_origin(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    g = auth.store.create_grant("cli", words=True)

    async def go():
        async with client(app) as c:
            form = {"words": words_of(g), "next": "/#tab=talk"}
            r = await c.post("/pair", data=form, allow_redirects=False)
            assert r.status == 403                                           # a form without Origin
            r = await c.post("/pair", data={"link": link_of(g)}, headers=origin(c), allow_redirects=False)
            assert r.status == 403                                           # a link never in a form body
            r = await c.post("/pair", data=form, headers=origin(c), allow_redirects=False)
            assert r.status == 303
            assert r.headers["Location"] == "/pair?check=1&next=" + quote("/#tab=talk", safe="")
            assert "pilot_session=" in r.headers["Set-Cookie"]
        async with client(app) as c:
            r = await c.post("/pair", data={"words": " ".join(A.WORDS[9:12])}, headers=origin(c), allow_redirects=False)
            assert r.status == 401 and "don't match" in await r.text()
    asyncio.run(go())


def test_check_shows_cookie_blocked_when_the_cookie_did_not_stick(tmp_path, clock):
    app, _ = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            r = await c.get("/pair?check=1&next=/", allow_redirects=False)
            assert r.status == 200 and "did not keep the sign-in" in await r.text()
    asyncio.run(go())


# ---------- the page ----------

def test_the_sign_in_page_shell_headers_and_form(tmp_path, clock):
    app, _ = viewer(tmp_path, clock)

    async def go():
        async with client(app, headers={"User-Agent": UA_CHROME}) as c:
            r = await c.get("/pair")
            return r.status, r.headers, await r.text()
    status, h, text = asyncio.run(go())
    assert status == 200
    csp = h["Content-Security-Policy"]
    for part in ("default-src 'none'", "script-src 'self'", "style-src 'unsafe-inline'", "img-src 'self' data:",
                 "connect-src 'self'", "form-action 'self'", "base-uri 'none'", "frame-ancestors 'none'"):
        assert part in csp, part
    assert h["Referrer-Policy"] == "same-origin" and h["Cache-Control"] == "no-store"   # no-referrer nulls Origin
    assert '<meta name="viewport"' in text and "prefers-color-scheme: dark" in text
    assert all('src="/static/signin.js"' in tag for tag in re.findall(r"<script[^>]*>", text))
    assert '<form method="post" action="/pair"' in text and 'name="words"' in text
    assert 'autocomplete="one-time-code"' in text and 'enterkeyhint="go"' in text and 'autocapitalize="none"' in text
    assert "Sign in this browser" in text and "python -m pilot dashboard-link" in text
    assert "not encrypted" in text and "Opened from another app?" in text
    assert "Instagram" not in text and 'id="inapp"' not in text


@pytest.mark.parametrize("ua,app_name", [(UA_WEBVIEW, "another app"), (UA_INSTAGRAM, "Instagram")])
def test_in_app_browsers_are_warned_without_script(tmp_path, clock, ua, app_name):
    app, _ = viewer(tmp_path, clock)

    async def go():
        async with client(app, headers={"User-Agent": ua}) as c:
            return await (await c.get("/pair")).text()
    text = asyncio.run(go())
    assert f"You opened this inside {app_name}" in text and "Open in browser" in text


def test_the_page_escapes_a_hostile_user_agent_and_next(tmp_path, clock):
    app, _ = viewer(tmp_path, clock)
    evil = '"><script>alert(1)</script>'

    async def go():
        async with client(app, headers={"User-Agent": UA_WEBVIEW + evil}) as c:
            return await (await c.get("/pair?next=" + quote("/" + evil) + "&reason=" + quote(evil))).text()
    text = asyncio.run(go())
    assert "<script>alert(1)</script>" not in text
    assert evil not in text


def test_states_come_from_a_fixed_set(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    dev, cookie = browser_cookie(auth, name="Brave on Windows")
    admin, _ = browser_cookie(auth, name="Pixel phone")
    auth.store.revoke(dev, "revoked", by=admin)

    async def go():
        async with client(app) as c:
            old = await (await c.get("/pair?reason=old_link")).text()
            unknown = await (await c.get("/pair?reason=Your+account+was+hacked")).text()
            out = await (await c.get("/pair?reason=signed_out")).text()
        async with client(app, cookie) as c:
            revoked = await (await c.get("/pair?reason=revoked")).text()
        return old, unknown, out, revoked
    old, unknown, out, revoked = asyncio.run(go())
    assert "Links with ?key= stopped working" in old
    assert "hacked" not in unknown
    assert "signed out" in out
    assert "signed out from Pixel phone at" in revoked


def test_signin_script_is_public_and_same_origin(tmp_path, clock):
    app, _ = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            r = await c.get("/static/signin.js")
            return r.status, r.headers["Content-Type"], await r.text()
    status, ctype, js = asyncio.run(go())
    assert status == 200 and "javascript" in ctype
    assert "replaceState" in js and "navigator.brave" in js and "#c=" in js


# ---------- the recovery-key form ----------

def test_recovery_key_form_is_off_by_default(tmp_path, clock, monkeypatch):
    app, _ = viewer(tmp_path, clock)
    compared: list = []
    real = A.hmac.compare_digest
    monkeypatch.setattr(A.hmac, "compare_digest", lambda a, b: compared.append(1) or real(a, b))

    async def go():
        async with client(app) as c:
            r = await c.post("/pair/key", data={"username": "pilot", "key": KEY, "next": "/"}, headers=origin(c),
                             allow_redirects=False)
            page = await (await c.get("/pair")).text()
            return r.status, page
    status, page = asyncio.run(go())
    assert status == 404 and not compared
    assert 'autocomplete="current-password"' not in page


def test_recovery_key_form_when_switched_on(tmp_path, clock, monkeypatch):
    monkeypatch.setenv("PILOT_KEY_SIGNIN", "1")
    app, auth = viewer(tmp_path, clock)

    async def go():
        async with client(app) as c:
            page = await (await c.get("/pair")).text()
            r = await c.post("/pair/key", data={"username": "pilot", "key": "wrong", "next": "/"}, headers=origin(c),
                             allow_redirects=False)
            assert r.status == 401
            assert (await c.post("/pair/key", data={"key": KEY}, allow_redirects=False)).status == 403   # no Origin
            r = await c.post("/pair/key", data={"username": "pilot", "key": KEY, "next": "/"}, headers=origin(c),
                             allow_redirects=False)
            assert r.status == 303 and r.headers["Location"].startswith("/pair?check=1")
            assert "pilot_session=" in r.headers["Set-Cookie"] and KEY not in r.headers["Set-Cookie"]
            return page
    page = asyncio.run(go())
    assert '<form method="post" action="/pair/key"' in page
    assert 'name="username"' in page and 'autocomplete="username"' in page
    assert 'type="password"' in page and 'autocomplete="current-password"' in page
    assert auth.throttle.failures(A.bucket_of("127.0.0.1")) == 1
    devs = auth.store.list_devices()
    assert len(devs) == 1 and devs[0]["created_via"] == "recovery_key"


# ---------- the audit and logs ----------

def test_a_hundred_bad_words_in_a_minute_are_one_audit_row(tmp_path, clock):
    app, auth = viewer(tmp_path, clock)
    auth.store.create_grant("cli", words=True)
    wrong = " ".join(A.WORDS[12:15])

    async def go():
        async with client(app) as c:
            for _ in range(100):
                await c.post("/pair", json={"words": wrong}, headers=origin(c))
    asyncio.run(go())
    rows = [r for r in auth.store.audit_rows() if r["event"] == "signin_failed"]
    assert len(rows) == 1 and rows[0]["count"] == 100


def test_no_code_or_session_reaches_a_log(tmp_path, clock, caplog):
    app, auth = viewer(tmp_path, clock)
    _, admin = browser_cookie(auth)
    secrets_seen: list[str] = []

    async def go():
        async with client(app, admin) as a:
            g1 = await (await a.post("/api/auth/grants", json={}, headers=origin(a))).json()
            g2 = await (await a.post("/api/auth/grants", json={}, headers=origin(a))).json()
            secrets_seen.extend([g1["link"].split("#c=")[1], g2["words"], g2["link"].split("#c=")[1]])
        async with client(app) as b:
            r = await b.post("/pair", json={"link": g1["link"].split("#c=")[1]}, headers=origin(b))
            assert r.status == 409 or r.status == 410 or r.status == 200
        async with client(app) as c:
            r = await c.post("/pair", json={"words": g2["words"]}, headers=origin(c))
            secrets_seen.append(r.headers.get("Set-Cookie", "").split(";")[0].split("=", 1)[-1])
            await c.post("/api/auth/devices", json={"action": "signout"}, headers=origin(c))
        async with client(app) as d:
            await d.post("/pair", json={"words": g2["words"]}, headers=origin(d))    # conflict
    with caplog.at_level(logging.DEBUG):
        asyncio.run(go())
    for s in secrets_seen:
        if s:
            assert s not in caplog.text, s
    assert "pgt_" not in caplog.text and KEY not in caplog.text


# ---------- the CLI ----------

def run_cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


def test_dashboard_link_prints_a_one_time_link_and_words_never_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("PILOT_PUBLIC_URL", "http://192.168.1.76:8780")
    code, out = run_cli("dashboard-link", "--port", "8781", "--no-qr")         # the viewer is not running
    assert code == 0
    assert "Sign in a browser (works once, for 10 minutes):" in out
    m = re.search(r"http://192\.168\.1\.76:8780/pair#c=([0-9a-f]{10})\.\S{40,}", out)
    assert m, out
    words = re.search(r"and type: ([a-z]+) ([a-z]+) ([a-z]+)", out)
    assert words and all(w in A.WORDS for w in words.groups())
    assert "key=" not in out and KEY not in out and "test-dashboard-key" not in out
    store = A.AuthStore(tmp_path / "auth-store" / "auth.sqlite")
    assert store.grant(m.group(1))["created_by"] == "cli"


def test_dashboard_link_prints_a_qr_code_when_segno_is_installed(tmp_path, monkeypatch):
    pytest.importorskip("segno")
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "runs"))
    _, out = run_cli("dashboard-link")
    assert "█" in out or "▀" in out


def test_dashboard_link_wait_reports_the_device(tmp_path, monkeypatch):
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(cli, "WAIT_POLL_S", 0.05)
    out = io.StringIO()
    result: dict = {}

    def run():
        with redirect_stdout(out):
            result["code"] = cli.main(["dashboard-link", "--no-qr", "--wait"])

    t = threading.Thread(target=run)
    t.start()
    store = A.AuthStore(tmp_path / "auth-store" / "auth.sqlite")
    for _ in range(100):
        grants = store.grants()
        if grants:
            break
        threading.Event().wait(0.05)
    gid = grants[0]["id"]
    link = re.search(rf"#c=({gid}\.\S+)", out.getvalue()).group(1)
    assert store.redeem("link", link, ip="192.168.1.140", user_agent=UA_CHROME.replace("Windows NT 10.0; Win64; x64",
                                                                                       "Linux; Android 14"))[0] == "ok"
    t.join(10)
    assert result["code"] == 0 and "Signed in: Chrome on Android" in out.getvalue()


def test_dashboard_devices_list_rename_revoke_and_log(tmp_path, monkeypatch):
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "runs"))
    store = A.AuthStore(tmp_path / "auth-store" / "auth.sqlite")
    a, _ = store.create_device("browser", name="Chrome on Windows", created_via="cli", created_by="cli")
    b, _ = store.create_device("browser", name="Chrome on Android", created_via="cli", created_by="cli")
    c, _ = store.create_device("script", name="laptop watch", scope="read", created_via="cli", created_by="cli")
    code, out = run_cli("dashboard-devices")
    assert code == 0 and "Chrome on Windows" in out and "laptop watch" in out and "read" in out and a["id"] in out
    assert run_cli("dashboard-devices", "rename", b["id"], "Pixel phone")[0] == 0
    assert store.device(b["id"])["name"] == "Pixel phone"
    assert run_cli("dashboard-devices", "revoke", b["id"])[0] == 0
    assert store.device(b["id"])["revoked_at"] and store.device(b["id"])["revoked_by"] == "cli"
    assert run_cli("dashboard-devices", "revoke", "0000000000")[0] == 1
    assert run_cli("dashboard-devices", "revoke-all", "--except", a["id"])[0] == 0
    assert not store.device(a["id"])["revoked_at"] and store.device(c["id"])["revoked_at"]
    code, out = run_cli("dashboard-devices", "log", "-n", "5")
    assert code == 0 and "Signed out by the controller, Pixel phone" in out


def test_dashboard_devices_unlock_calls_the_viewer_over_loopback(tmp_path, monkeypatch):
    monkeypatch.setenv("PILOT_RUNS_DIR", str(tmp_path / "runs"))
    calls: list = []

    class Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        calls.append((req.full_url, req.get_method(), dict(req.header_items())))
        return Resp(json.dumps({"ok": True}).encode())

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    code, out = run_cli("dashboard-devices", "unlock", "--port", "8781")
    assert code == 0 and "lifted" in out
    url, method, headers = calls[0]
    assert url == "http://127.0.0.1:8781/api/auth/unlock" and method == "POST"
    assert headers["X-pilot-key"] == "test-dashboard-key" and headers["Content-type"] == "application/json"


def test_link_base_uses_public_url_else_the_host_the_browser_used(tmp_path, clock, monkeypatch):
    app, auth = viewer(tmp_path, clock)
    _, cookie = browser_cookie(auth)

    async def go():
        async with client(app, cookie) as c:
            g = await (await c.post("/api/auth/grants", json={}, headers={**origin(c), "Host": "192.168.1.76:8780",
                                                                           "Origin": "http://192.168.1.76:8780"})).json()
            assert g["link"].startswith("http://192.168.1.76:8780/pair#c=")
            g = await (await c.post("/api/auth/grants", json={}, headers=origin(c))).json()      # loopback host
            assert not g["link"].startswith("http://127.0.0.1")
    asyncio.run(go())

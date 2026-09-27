"""Dashboard sign-in (docs/design/2026-09-27-dashboard-v2-design.md, rulings 34-52).

Every browser holds its own named, revocable session (cookie `pilot_session=s1.<id>.<secret>`). The
service key K (`PILOT_DASHBOARD_KEY` or `runs/dashboard.key`) works only as a header from the
controller itself (127.0.0.1 / ::1), never as a cookie, in a URL or in a log line. Scripts on other
machines use scoped tokens (`pgt_<id>.<secret>`, made by the CLI). The Host header must be one of
this machine's names or an IP literal (no DNS rebinding). The old key cookie (`pilot_key`) carries
over into a device for 72 hours after the first start of this code, or until K is rotated.

Store: `runs/auth.sqlite` (`PILOT_AUTH_DB`), 0600, WAL: devices (browsers and scripts), grants
(sign-in codes), an aggregated audit log and meta. Only hashes of secrets are stored. Throttles live
in memory. Only the viewer and the CLI open the store; the live pilot needs none.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import quote, urlsplit

from aiohttp import web

log = logging.getLogger(__name__)

SESSION_COOKIE = "pilot_session"
LEGACY_COOKIE = "pilot_key"              # the retired cookie whose value was K itself
KEY_HEADER = "X-Pilot-Key"
DEVICE_HEADER = "X-Pilot-Device"         # viewer -> live pilot: the device behind a request (with K only)
DEVICE_NAME_HEADER = "X-Pilot-Device-Name"   # its name, percent-encoded (headers are latin-1)
KEY_ENV, KEY_FILE = "PILOT_DASHBOARD_KEY", "dashboard.key"
PRINCIPAL = web.RequestKey("pilot_principal", object)     # the Principal of a request
COOKIES = web.RequestKey("pilot_cookies", list)          # cookie writes for on_response_prepare
AUTH_KEY = web.AppKey("pilot_auth", object)
RUNNER_KWARGS = {"access_log": None}     # request lines carry query strings (an old ?key=): never logged

DAY = 86400
COOKIE_MAX_AGE = 400 * DAY               # the longest lifetime browsers accept
COOKIE_RESEND_S = 7 * DAY                # re-sent at most weekly, so the 400 days slide with use
TOUCH_S = 300                            # last_seen written at most every 5 min (or on a new address)
IDLE_S = 180 * DAY                       # a browser unseen this long is signed out
PRUNE_S = 30 * DAY                       # ... and deleted this much later
TWO_ADDRESSES_S = 600
LEGACY_WINDOW_S = 72 * 3600
GRANT_TTL_S = 600
GRANT_KEEP_S = DAY                       # spent grants are kept this long (a second use is a conflict)
NOTICE_S = DAY
KEEPALIVE_S = 15.0
AUDIT_KEEP_S, AUDIT_MAX_ROWS = 90 * DAY, 10_000
NAME_MAX = 60
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PUBLIC_PATHS = {("GET", "/pair"), ("POST", "/pair"), ("GET", "/static/signin.js"), ("GET", "/favicon.svg")}
IN_APP = re.compile(r"; wv\)|FBAN|FBAV|Instagram|Line/|GSA/|LinkedInApp|Snapchat|Twitter|Slack|Teams/|MicroMessenger")
REALM = 'Bearer realm="Game Pilot"'
ID_RE = re.compile(r"[0-9a-f]{10}")

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('browser', 'script')),
  scope TEXT NOT NULL DEFAULT 'control' CHECK (scope IN ('read', 'control')),
  name TEXT NOT NULL,
  token_hash BLOB NOT NULL,
  created_at REAL NOT NULL, created_ip TEXT,
  created_via TEXT NOT NULL,
  created_by TEXT,
  grant_id TEXT,
  legacy INTEGER NOT NULL DEFAULT 0,
  user_agent TEXT,
  last_seen_at REAL, last_ip TEXT, prev_ip TEXT, prev_seen_at REAL,
  cookie_sent_at REAL,
  expires_at REAL,
  revoked_at REAL, revoked_by TEXT,
  revoke_reason TEXT
);
CREATE TABLE IF NOT EXISTS grants (
  id TEXT PRIMARY KEY,
  link_hash BLOB NOT NULL,
  words_hash BLOB UNIQUE,
  created_at REAL NOT NULL, expires_at REAL NOT NULL,
  created_by TEXT NOT NULL,
  state TEXT NOT NULL,
  used_at REAL, used_ip TEXT, device_id TEXT
);
CREATE TABLE IF NOT EXISTS auth_events (
  id INTEGER PRIMARY KEY, t REAL NOT NULL, event TEXT NOT NULL, ip TEXT, device_id TEXT,
  count INTEGER NOT NULL DEFAULT 1, detail TEXT
);
CREATE INDEX IF NOT EXISTS auth_events_t ON auth_events (t);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""
SCHEMA_VERSION = "1"


# ---------------------------------------------------------------- helpers

def digest(secret: str) -> bytes:
    return hashlib.sha256(secret.encode()).digest()


def fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def is_loopback(ip: str | None) -> bool:
    try:
        a = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a.is_loopback


def bucket_of(ip: str | None) -> str:
    """Throttle bucket: an exact IPv4 address (IPv4-mapped unwrapped) or an IPv6 /64."""
    try:
        a = ipaddress.ip_address(ip or "")
    except ValueError:
        return "ip:unknown"
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    if a.version == 6:
        return "ip6:" + str(ipaddress.ip_network(f"{a}/64", strict=False).network_address)
    return f"ip:{a}"


def host_name(host: str) -> str:
    h = (host or "").strip().lower()
    if h.startswith("["):
        return h[1:h.find("]")] if "]" in h else h
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def allowed_host(host: str, extra: frozenset[str] = frozenset()) -> bool:
    """IP literals cannot be DNS-rebound (a rebinding page's Host is its own name); names must be
    this machine's, or listed (PILOT_DASHBOARD_HOSTS, the host of PILOT_PUBLIC_URL)."""
    name = host_name(host)
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    me = socket.gethostname().lower()
    return name in {"localhost", me, f"{me}.local", socket.getfqdn().lower(), *extra}


def safe_next(v: str | None) -> str:
    """A same-origin path to go back to after signing in: never another host, a scheme, a control
    character, the sign-in page itself, or an old ?key= (its fragment is kept)."""
    v = v or "/"
    if not v.startswith("/") or v.startswith("//") or "\\" in v or any(ord(c) < 32 or ord(c) == 127 for c in v):
        return "/"
    if re.search(r"%(0[0-9a-f]|1[0-9a-f]|7f)", v, re.IGNORECASE):
        return "/"
    parts = urlsplit(v)
    if parts.scheme or parts.netloc or parts.path == "/pair" or parts.path.startswith("/pair/"):
        return "/"
    if re.search(r"(^|&)key=", parts.query):
        return parts.path + (f"#{parts.fragment}" if parts.fragment else "")
    return v


def device_name(ua: str | None, client: str = "") -> str:
    """'Brave on Windows', 'Chrome on Android', 'In-app browser on Android' (signin.js sends
    client=Brave from navigator.brave, which the user agent hides)."""
    ua = ua or ""
    osn = ("iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Android" if "Android" in ua
           else "Windows" if "Windows" in ua else "Mac" if "Macintosh" in ua else "Linux" if "Linux" in ua else "")
    br = ("Brave" if client == "Brave" else "Edge" if "Edg" in ua else "Samsung Internet" if "SamsungBrowser" in ua
          else "Firefox" if ("Firefox/" in ua or "FxiOS" in ua) else "Chrome" if ("Chrome/" in ua or "CriOS" in ua)
          else "Safari" if "Safari/" in ua else "curl" if ua.startswith("curl/") else "Browser")
    if IN_APP.search(ua):
        br = "In-app browser"
    return f"{br} on {osn}" if osn else br


def in_app_browser(ua: str | None) -> str:
    """The app whose embedded browser this is, '' when none is detected (iOS SFSafariViewController
    cannot be told from Safari)."""
    ua = ua or ""
    for pat, app in (("FBAN|FBAV", "Facebook"), ("Instagram", "Instagram"), ("Line/", "LINE"), ("GSA/", "the Google app"),
                     ("LinkedInApp", "LinkedIn"), ("Snapchat", "Snapchat"), ("Twitter", "X"), ("Slack", "Slack"),
                     ("Teams/", "Teams"), ("MicroMessenger", "WeChat"), (r"; wv\)", "another app")):
        if re.search(pat, ua):
            return app
    return ""


def json_error(status: int, error: str, reason: str, fix: str = "", **extra) -> web.Response:
    headers = extra.pop("headers", {})
    if status == 401:
        headers.setdefault("WWW-Authenticate", REALM)
    return web.json_response({"error": error, "reason": reason, "fix": fix, **extra}, status=status, headers=headers)


def cookie_header(name: str, value: str, *, secure: bool = False, delete: bool = False) -> str:
    """One Set-Cookie value: HttpOnly, SameSite=Lax (links opened from other apps arrive signed in;
    cross-site subrequests and frames do not carry it), Path=/, 400 days; Secure only under HTTPS."""
    c: SimpleCookie = SimpleCookie()
    c[name] = "" if delete else value
    m = c[name]
    m["path"] = "/"
    m["httponly"] = True
    m["samesite"] = "Lax"
    if delete:
        m["max-age"] = 0
        m["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    else:
        m["max-age"] = COOKIE_MAX_AGE
    if secure:
        m["secure"] = True
    return m.OutputString()


def see_other(location: str) -> web.Response:
    return web.Response(status=303, headers={"Location": location})


def clip_name(name: str | None, fallback: str = "Device") -> str:
    name = re.sub(r"[\x00-\x1f\x7f]", "", str(name or "")).strip()
    return name[:NAME_MAX] or fallback


def split_cred(value: str | None, prefix: str) -> tuple[str, str]:
    """'<prefix><id>.<secret>' -> (id, secret); ('', '') when malformed."""
    if not value or not value.startswith(prefix):
        return "", ""
    ident, _, secret = value[len(prefix):].partition(".")
    if not ID_RE.fullmatch(ident) or len(secret) < 32 or len(secret) > 128:
        return "", ""
    return ident, secret


def _bearer(request: web.Request) -> str | None:
    a = request.headers.get("Authorization", "")
    return a[7:].strip() if a[:7].lower() == "bearer " else None


def _ago(t: float | None, now: float) -> str:
    return time.strftime("%H:%M", time.localtime(t)) if t else ""


# ---------------------------------------------------------------- the service key

def _write_private(path: Path, text: str) -> None:
    """Atomic 0600 write: temp file, then os.replace (a new inode, so readers notice)."""
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def dashboard_key(runs_dir: Path) -> str:
    """K: $PILOT_DASHBOARD_KEY, else runs/dashboard.key (created once, mode 0600)."""
    env = os.environ.get(KEY_ENV, "").strip()
    if env:
        return env
    path = Path(runs_dir) / KEY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = path.read_text().strip()
        if not key:
            raise RuntimeError(f"{path} is empty: delete it to make a new dashboard key") from None
        return key
    key = secrets.token_urlsafe(32)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    return key


class KeySource:
    """K, re-read when the file's mtime or inode changes (a stat at most every 2 s), so a rotation
    reaches a running process without a restart. A fixed key (tests, `make_app(key=)`) or the
    environment variable wins over the file."""

    def __init__(self, runs_dir: Path | None = None, fixed: str | None = None, monotonic=time.monotonic):
        self.runs_dir = Path(runs_dir) if runs_dir is not None else None
        self.fixed = fixed
        self.monotonic = monotonic
        self._key = ""
        self._stamp: tuple | None = None
        self._checked = -1e18
        self._lock = threading.Lock()

    @property
    def from_env(self) -> bool:
        return self.fixed is None and bool(os.environ.get(KEY_ENV, "").strip())

    @property
    def path(self) -> Path | None:
        return self.runs_dir / KEY_FILE if self.runs_dir is not None else None

    def reload(self) -> None:
        """Read the file again on the next call, even when its stat looks unchanged (mtime has
        coarse granularity): used after the live pilot refused the key."""
        self._checked, self._stamp = -1e18, None

    def get(self) -> str:
        if self.fixed:
            return self.fixed
        env = os.environ.get(KEY_ENV, "").strip()
        if env:
            return env
        if self.runs_dir is None:
            raise RuntimeError("no dashboard key: set PILOT_DASHBOARD_KEY")
        with self._lock:
            now = self.monotonic()
            if now - self._checked >= 2 or not self._key:
                self._checked = now
                if not self.path.exists():
                    dashboard_key(self.runs_dir)
                st = self.path.stat()
                if (st.st_mtime_ns, st.st_ino, st.st_size) != self._stamp or not self._key:
                    key = self.path.read_text().strip()
                    if not key:
                        raise RuntimeError(f"{self.path} is empty: delete it to make a new dashboard key")
                    self._key, self._stamp = key, (st.st_mtime_ns, st.st_ino, st.st_size)
            return self._key

    def matches(self, given: str | None) -> bool:
        return bool(given) and hmac.compare_digest(given.encode(), self.get().encode())

    def rotate(self) -> str:
        """A new K, written atomically (0600). Refused when K comes from the environment."""
        if self.fixed or self.from_env:
            raise RuntimeError(f"the key comes from {KEY_ENV}: change the variable and restart both services")
        key = secrets.token_urlsafe(32)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _write_private(self.path, key + "\n")
        self.reload()
        return key


# ---------------------------------------------------------------- the store

class AuthStore:
    """runs/auth.sqlite: devices, grants, the audit and meta. Opened by the viewer and the CLI; the
    same file serves both, so a revoke from the CLI applies at the viewer's next request."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.time):
        self.path, self.now = Path(path), clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        try:
            self.db = self._open()
        except sqlite3.DatabaseError as e:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            log.error("auth store %s is corrupt (%s): moved aside to %s.corrupt-%s; browsers sign in again "
                      "(python -m pilot dashboard-link), scripts on the controller keep working with the key",
                      self.path, e, self.path.name, stamp)
            for suffix in ("", "-wal", "-shm"):
                p = Path(str(self.path) + suffix)
                if p.exists():
                    os.replace(p, Path(str(self.path) + f".corrupt-{stamp}" + suffix))
            self.db = self._open()

    def _open(self) -> sqlite3.Connection:
        if not self.path.exists():      # created 0600 before SQLite opens it, so -wal and -shm get the same mode
            os.close(os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=2)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=2000")
            db.execute("PRAGMA journal_mode=WAL")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("quick_check failed")
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
        except sqlite3.DatabaseError:
            db.close()
            raise
        return db

    def _x(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.db.execute(sql, args)

    def _rows(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    # -- meta
    def meta(self, key: str) -> str | None:
        rows = self._rows("SELECT value FROM meta WHERE key=?", (key,))
        return rows[0]["value"] if rows else None

    def set_meta(self, key: str, value: str) -> None:
        self._x("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))

    # -- audit: one row per (event, ip, minute), with a count; never a secret
    def audit(self, event: str, ip: str | None = None, device_id: str | None = None, detail: dict | None = None) -> None:
        now = self.now()
        minute = int(now // 60) * 60
        with self._lock:
            row = self.db.execute("SELECT id FROM auth_events WHERE event=? AND ip IS ? AND t>=? AND t<? "
                                  "AND device_id IS ? ORDER BY id DESC LIMIT 1",
                                  (event, ip, minute, minute + 60, device_id)).fetchone()
            if row:
                self.db.execute("UPDATE auth_events SET count=count+1 WHERE id=?", (row["id"],))
            else:
                self.db.execute("INSERT INTO auth_events (t, event, ip, device_id, detail) VALUES (?,?,?,?,?)",
                                (now, event, ip, device_id, json.dumps(detail, default=str) if detail else None))

    def audit_rows(self, n: int = 1000) -> list[dict]:
        return self._rows("SELECT * FROM auth_events ORDER BY t DESC, id DESC LIMIT ?", (n,))

    # -- devices (browsers and scripts)
    def create_device(self, kind: str, *, name: str, created_via: str, created_by: str | None = None,
                      ip: str | None = None, user_agent: str | None = None, scope: str = "control",
                      grant_id: str | None = None, legacy: bool = False,
                      expires_at: float | None = None) -> tuple[dict, str]:
        """A new device and its one-time credential: 's1.<id>.<secret>' (browser cookie) or
        'pgt_<id>.<secret>' (script header token). Only sha256(secret) is stored."""
        if kind not in ("browser", "script"):
            raise ValueError("kind must be browser or script")
        if scope not in ("read", "control"):
            raise ValueError("scope must be read or control")
        if kind == "browser":
            scope = "control"
        ident, secret = secrets.token_hex(5), secrets.token_urlsafe(32)
        now = self.now()
        self._x("INSERT INTO devices (id, kind, scope, name, token_hash, created_at, created_ip, created_via, created_by,"
                " grant_id, legacy, user_agent, last_seen_at, last_ip, cookie_sent_at, expires_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ident, kind, scope, clip_name(name), digest(secret), now, ip, created_via, created_by, grant_id,
                 int(legacy), (user_agent or "")[:200] or None, now if kind == "browser" else None,
                 ip if kind == "browser" else None, now if kind == "browser" else None, expires_at))
        self.audit("signin" if kind == "browser" else "token_created", ip, ident,
                   {"how": created_via, "by": created_by, "scope": scope if kind == "script" else None})
        cred = f"s1.{ident}.{secret}" if kind == "browser" else f"pgt_{ident}.{secret}"
        return self.device(ident), cred

    def device(self, ident: str) -> dict | None:
        rows = self._rows("SELECT * FROM devices WHERE id=?", (ident,))
        return rows[0] if rows else None

    def check(self, kind: str, cred: str | None) -> tuple[dict | None, str]:
        """(the live device, '') or (the device row or None, why not: sign_in_required | bad_token |
        revoked | idle | conflict | expired). Reads only; an idle browser is signed out here."""
        ident, secret = split_cred(cred, "s1." if kind == "browser" else "pgt_")
        miss = "sign_in_required" if kind == "browser" else "bad_token"
        row = self.device(ident) if ident else None
        if not row or row["kind"] != kind or not hmac.compare_digest(row["token_hash"], digest(secret)):
            return None, miss
        if row["revoked_at"]:
            return row, row["revoke_reason"] if row["revoke_reason"] in ("idle", "conflict") else "revoked"
        now = self.now()
        if kind == "script" and row["expires_at"] and now > row["expires_at"]:
            return row, "bad_token"
        if kind == "browser" and now - (row["last_seen_at"] or row["created_at"]) > IDLE_S:
            self.revoke(ident, "idle", by="idle")
            return self.device(ident), "idle"
        return row, ""

    def touch_due(self, row: dict, ip: str | None) -> bool:
        return (row.get("last_seen_at") is None or self.now() - row["last_seen_at"] >= TOUCH_S
                or (ip is not None and ip != row.get("last_ip")))

    def touch(self, ident: str, ip: str | None) -> None:
        """last_seen (time and address); a new address keeps the previous one for the badge."""
        now = self.now()
        with self._lock:
            row = self.db.execute("SELECT last_ip, last_seen_at FROM devices WHERE id=?", (ident,)).fetchone()
            if not row:
                return
            if ip is not None and row["last_ip"] and ip != row["last_ip"]:
                self.db.execute("UPDATE devices SET prev_ip=?, prev_seen_at=?, last_ip=?, last_seen_at=? WHERE id=?",
                                (row["last_ip"], row["last_seen_at"], ip, now, ident))
            else:
                self.db.execute("UPDATE devices SET last_seen_at=?, last_ip=COALESCE(?, last_ip) WHERE id=?",
                                (now, ip, ident))

    def cookie_due(self, row: dict) -> bool:
        return self.now() - (row.get("cookie_sent_at") or 0) >= COOKIE_RESEND_S

    def cookie_sent(self, ident: str) -> None:
        self._x("UPDATE devices SET cookie_sent_at=? WHERE id=?", (self.now(), ident))

    def revoke(self, ident: str, reason: str, by: str | None = None, ip: str | None = None) -> bool:
        cur = self._x("UPDATE devices SET revoked_at=?, revoked_by=?, revoke_reason=? WHERE id=? AND revoked_at IS NULL",
                      (self.now(), by, reason, ident))
        if cur.rowcount:
            self.audit({"signed_out": "signed_out", "idle": "idle"}.get(reason, "revoked"), ip, ident,
                       {"reason": reason, "by": by})
        return bool(cur.rowcount)

    def revoke_others(self, keep: str, by: str | None = None, ip: str | None = None) -> int:
        cur = self._x("UPDATE devices SET revoked_at=?, revoked_by=?, revoke_reason='revoke_others'"
                      " WHERE id != ? AND kind='browser' AND revoked_at IS NULL", (self.now(), by, keep))
        self.audit("revoke_others", ip, keep, {"count": cur.rowcount})
        return cur.rowcount

    def rename(self, ident: str, name: str) -> bool:
        return bool(self._x("UPDATE devices SET name=? WHERE id=? AND revoked_at IS NULL", (clip_name(name), ident)).rowcount)

    def list_devices(self, include_revoked: bool = False) -> list[dict]:
        rows = self._rows("SELECT * FROM devices" + ("" if include_revoked else " WHERE revoked_at IS NULL")
                          + " ORDER BY COALESCE(last_seen_at, created_at) DESC")
        for r in rows:
            r.pop("token_hash", None)
        return rows

    def two_addresses(self, row: dict) -> bool:
        return bool(row.get("prev_ip") and row.get("prev_seen_at") and row.get("last_seen_at")
                    and row["last_seen_at"] - row["prev_seen_at"] <= TWO_ADDRESSES_S)

    # -- grants (sign-in codes)
    def create_grant(self, created_by: str) -> dict:
        """A grant with a 256-bit link token (`<id>.<secret>`); the link face only (typed words come
        with the sign-in page). Expires in 10 minutes."""
        ident, secret = secrets.token_hex(5), secrets.token_urlsafe(32)
        now = self.now()
        self._x("INSERT INTO grants (id, link_hash, created_at, expires_at, created_by, state) VALUES (?,?,?,?,?,?)",
                (ident, digest(secret), now, now + GRANT_TTL_S, created_by, "waiting"))
        self.audit("grant_created", None, created_by if ID_RE.fullmatch(created_by or "") else None,
                   {"grant": ident, "by": created_by})
        return {"id": ident, "link": f"{ident}.{secret}", "expires_at": now + GRANT_TTL_S}

    def grant(self, ident: str) -> dict | None:
        rows = self._rows("SELECT * FROM grants WHERE id=?", (ident,))
        if rows:
            rows[0].pop("link_hash", None)
            rows[0].pop("words_hash", None)
        return rows[0] if rows else None

    def grants(self) -> list[dict]:
        rows = self._rows("SELECT * FROM grants ORDER BY created_at DESC")
        for r in rows:
            r.pop("link_hash", None)
            r.pop("words_hash", None)
        return rows

    # -- housekeeping (at start and hourly)
    def housekeeping(self) -> None:
        now = self.now()
        with self._lock:
            self.db.execute("UPDATE devices SET revoked_at=?, revoked_by='idle', revoke_reason='idle' WHERE kind='browser'"
                            " AND revoked_at IS NULL AND COALESCE(last_seen_at, created_at) < ?", (now, now - IDLE_S))
            self.db.execute("DELETE FROM devices WHERE revoke_reason='idle' AND revoked_at < ?", (now - PRUNE_S,))
            self.db.execute("DELETE FROM grants WHERE created_at < ?", (now - GRANT_KEEP_S,))
            self.db.execute("DELETE FROM auth_events WHERE t < ?", (now - AUDIT_KEEP_S,))
            self.db.execute("DELETE FROM auth_events WHERE id NOT IN (SELECT id FROM auth_events ORDER BY t DESC"
                            " LIMIT ?)", (AUDIT_MAX_ROWS,))


# ---------------------------------------------------------------- throttles (in memory)

class Throttle:
    """Failures per bucket (an IPv4 address or an IPv6 /64) and across all buckets, in a 10-minute
    window. Check-and-count is atomic: `reserve` runs before any await and takes the slot at once;
    a success gives it back (`refund`)."""

    WINDOW_S, PER_BUCKET, OVERALL = 600.0, 5, 20

    def __init__(self, clock: Callable[[], float] = time.time):
        self.now = clock
        self._buckets: dict[str, deque[float]] = {}
        self._all: deque[float] = deque()

    def _prune(self, q: deque) -> None:
        edge = self.now() - self.WINDOW_S
        while q and q[0] <= edge:
            q.popleft()

    def failures(self, bucket: str) -> int:
        q = self._buckets.get(bucket, deque())
        self._prune(q)
        return len(q)

    def blocked(self, bucket: str) -> float:
        """Seconds until this bucket may try again (0: now)."""
        q = self._buckets.setdefault(bucket, deque())
        self._prune(q)
        self._prune(self._all)
        waits = []
        if len(q) >= self.PER_BUCKET:
            waits.append(q[len(q) - self.PER_BUCKET] + self.WINDOW_S - self.now())
        if len(self._all) >= self.OVERALL:
            waits.append(self._all[len(self._all) - self.OVERALL] + self.WINDOW_S - self.now())
        return max(waits, default=0.0)

    def reserve(self, bucket: str) -> float:
        wait = self.blocked(bucket)
        if wait > 0:
            return wait
        self.fail(bucket)
        return 0.0

    def refund(self, bucket: str) -> None:
        q = self._buckets.get(bucket)
        if q:
            t = q.pop()
            with contextlib.suppress(ValueError):
                self._all.remove(t)

    def fail(self, bucket: str) -> None:
        t = self.now()
        self._buckets.setdefault(bucket, deque()).append(t)
        self._all.append(t)

    def unlock(self) -> None:
        self._buckets.clear()
        self._all.clear()


# ---------------------------------------------------------------- the guard

@dataclass
class Principal:
    kind: str                         # service | browser | script | legacy
    id: str                           # the device id; "service" or "legacy" otherwise
    name: str
    scope: str = "control"
    via: str = ""                     # service | cookie | header | legacy_cookie
    row: dict | None = None
    recheck: Callable[[], bool] = field(default=lambda: True, repr=False)

    @property
    def by_cookie(self) -> bool:
        return self.via in ("cookie", "legacy_cookie")


REASONS = {
    "sign_in_required": ("This browser is not signed in.",
                         ("Sign in at /pair with a code from a signed-in browser (the ⋯ menu, Add a device), or run "
                          "python -m pilot dashboard-link on the controller.")),
    "revoked": ("This browser was signed out.", "Sign in again at /pair."),
    "idle": ("This browser was signed out after 180 days without use.", "Sign in again at /pair."),
    "conflict": ("This browser's sign-in code was used again by another browser, so its sign-in was ended.",
                 "Sign in again with a new code; if that was not you, review Devices."),
    "service_key_loopback_only": (("The service key works only from the controller itself (127.0.0.1), and never "
                                   "through a proxy."),
                                  ("On another machine use a script token: python -m pilot dashboard-token create "
                                   "--name NAME --scope read")),
    "bad_token": ("The token is unknown, expired or revoked.",
                  "Create one with python -m pilot dashboard-token create --name NAME --scope read|control"),
}


def _config_from_env(public_url: str | None = None) -> dict:
    env = os.environ
    public = (public_url if public_url is not None else env.get("PILOT_PUBLIC_URL", "")).strip().rstrip("/")
    hosts = {h.strip().lower() for h in env.get("PILOT_DASHBOARD_HOSTS", "").split(",") if h.strip()}
    if public:
        hosts.add(host_name(urlsplit(public).netloc))
    return {"public_url": public, "extra_hosts": frozenset(hosts),
            "key_signin": env.get("PILOT_KEY_SIGNIN", "0").strip().lower() in ("1", "true", "yes", "on"),
            "add_device": "cli" if env.get("PILOT_ADD_DEVICE", "").strip().lower() == "cli" else "any"}


class Auth:
    """The viewer's sign-in state: K, the store, the throttles and the request guard."""

    def __init__(self, keys: KeySource, store: AuthStore, *, clock: Callable[[], float] = time.time,
                 keepalive_s: float = KEEPALIVE_S, public_url: str = "", extra_hosts: frozenset[str] = frozenset(),
                 key_signin: bool = False, add_device: str = "any"):
        self.keys, self.store, self.now = keys, store, clock
        self.throttle = Throttle(clock)
        self.keepalive_s = keepalive_s
        self.public_url, self.extra_hosts = public_url, extra_hosts
        self.key_signin, self.add_device = key_signin, add_device
        self._minting: dict[tuple, tuple[float, str, str]] = {}
        self._mint_locks: dict[int, asyncio.Lock] = {}

    @classmethod
    def from_env(cls, runs_dir: Path, key: str | None = None, clock: Callable[[], float] = time.time,
                 keepalive_s: float = KEEPALIVE_S, **overrides) -> Auth:
        db = Path(os.environ.get("PILOT_AUTH_DB") or Path(runs_dir) / "auth.sqlite")
        cfg = {**_config_from_env(), **overrides}
        auth = cls(KeySource(runs_dir, fixed=key), AuthStore(db, clock=clock), clock=clock, keepalive_s=keepalive_s, **cfg)
        auth.start()
        return auth

    def start(self) -> None:
        """First start of this code: open the 72-hour carry-over window for the current K."""
        if self.store.meta("legacy_key_fp") is None:
            self.store.set_meta("legacy_key_fp", fingerprint(self.keys.get()))
            self.store.set_meta("legacy_until", str(self.now() + LEGACY_WINDOW_S))
        self.store.housekeeping()

    # -- carry-over
    def legacy_open(self) -> bool:
        until = float(self.store.meta("legacy_until") or 0)
        return self.now() < until and self.store.meta("legacy_key_fp") == fingerprint(self.keys.get())

    # -- names
    def who(self, ident: str | None) -> str:
        if not ident:
            return ""
        if ident == "cli":
            return "the controller"
        if ident == "idle":
            return ""
        row = self.store.device(ident)
        return row["name"] if row else ident

    # -- cookies (written in on_response_prepare, so they also reach files, streams and raised errors)
    @staticmethod
    def set_session(request: web.Request, cred: str) -> None:
        request.setdefault(COOKIES, []).append(("set", SESSION_COOKIE, cred))

    @staticmethod
    def drop_cookie(request: web.Request, name: str) -> None:
        request.setdefault(COOKIES, []).append(("del", name, ""))

    async def on_prepare(self, request: web.Request, response: web.StreamResponse) -> None:
        h = response.headers
        h.setdefault("Cache-Control", "no-store")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "same-origin")
        # the hook runs after aiohttp has turned response.cookies into headers: add them as headers
        for op, name, value in request.get(COOKIES, []):
            h.add("Set-Cookie", cookie_header(name, value, secure=request.secure, delete=op == "del"))

    # -- the principal
    def _unauthorized(self, request: web.Request, error: str, row: dict | None = None) -> web.Response:
        reason, fix = REASONS[error]
        by = self.who(row.get("revoked_by")) if row and row.get("revoked_at") else ""
        at = row.get("revoked_at") if row else None
        if error == "revoked" and by:
            reason = f"This browser was signed out from {by} at {_ago(at, self.now())}."
        if self._wants_page(request):
            nxt = safe_next(request.path_qs)
            return see_other(f"/pair?next={quote(nxt, safe='')}&reason={error}")
        return json_error(401, error, reason, fix, by=by or None, at=at)

    @staticmethod
    def _wants_page(request: web.Request) -> bool:
        return request.method == "GET" and (request.path == "/" or "text/html" in request.headers.get("Accept", ""))

    def _principal(self, request: web.Request) -> tuple[Principal | None, web.Response | None]:
        ip = request.remote
        given = request.headers.get(KEY_HEADER) or _bearer(request)
        if given:                                          # a header: the service key or a script token
            if given.startswith("pgt_"):
                row, why = self.store.check("script", given)
                if why:
                    if not is_loopback(ip):
                        self.throttle.fail(bucket_of(ip))
                    return None, json_error(401, "bad_token", *REASONS["bad_token"])
                ident = row["id"]
                return Principal("script", ident, row["name"], row["scope"], "header", row,
                                 recheck=lambda: not self.store.check("script", given)[1]), None
            if self.keys.matches(given):
                forwarded = "Forwarded" in request.headers or "X-Forwarded-For" in request.headers
                if is_loopback(ip) and not forwarded:
                    return Principal("service", "service", "the controller", "control", "service",
                                     recheck=lambda: self.keys.matches(given)), None
                self.store.audit("service_key_refused_lan", ip, detail={"path": request.path})
                return None, json_error(401, "service_key_loopback_only", *REASONS["service_key_loopback_only"])
            if not is_loopback(ip):
                self.throttle.fail(bucket_of(ip))
            return None, json_error(401, "bad_token", *REASONS["bad_token"])
        cookie = request.cookies.get(SESSION_COOKIE)
        failed: tuple[str, dict | None] | None = None
        if cookie:
            row, why = self.store.check("browser", cookie)
            if not why:
                return Principal("browser", row["id"], row["name"], "control", "cookie", row,
                                 recheck=lambda: not self.store.check("browser", cookie)[1]), None
            failed = (why, row)
        old = request.cookies.get(LEGACY_COOKIE)
        if old is not None:
            if self.legacy_open() and self.keys.matches(old):
                return Principal("legacy", "legacy", "a browser with the old link", "control", "legacy_cookie",
                                 recheck=lambda: self.legacy_open() and self.keys.matches(old)), None
            self.drop_cookie(request, LEGACY_COOKIE)       # the window closed or K changed: deleted wherever seen
            if failed is None and self._wants_page(request):
                return None, see_other(f"/pair?next={quote(safe_next(request.path_qs), safe='')}&reason=old_link")
        why, row = failed or ("sign_in_required", None)
        return None, self._unauthorized(request, why, row)

    async def _old_key_link(self, request: web.Request) -> web.StreamResponse:
        """GET /?key=: inside the window a right K becomes a one-time grant (the confirm view of
        /pair, no cookie); a browser already signed in just loses the key from its address bar.
        After the window any value gets the same answer and is never compared."""
        principal, _ = self._principal(request)
        if principal is not None and principal.kind in ("browser", "legacy"):
            return see_other("/")
        if not self.legacy_open():
            return see_other("/pair?reason=old_link")
        if not self.keys.matches(request.query.get("key", "")):
            self.throttle.fail(bucket_of(request.remote))
            await asyncio.to_thread(self.store.audit, "signin_failed", request.remote, None, {"how": "legacy_link"})
            return see_other("/pair?reason=old_link")
        grant = await asyncio.to_thread(self.store.create_grant, "legacy_link")
        return see_other(f"/pair#c={grant['link']}")

    async def _carry_over(self, request: web.Request) -> Principal:
        """The old cookie on the page itself becomes a device (once per browser: parallel loads of
        one page reuse the device minted in the last 30 s for the same address and user agent)."""
        ua = request.headers.get("User-Agent", "")
        key = (request.remote, ua)
        lock = self._mint_locks.setdefault(id(asyncio.get_running_loop()), asyncio.Lock())
        async with lock:
            hit = self._minting.get(key)
            if hit and self.now() - hit[0] < 30:
                ident, cred = hit[1], hit[2]
            else:
                row, cred = await asyncio.to_thread(
                    self.store.create_device, "browser", name=device_name(ua), created_via="legacy_cookie",
                    created_by="legacy_link", ip=request.remote, user_agent=ua, legacy=True)
                ident = row["id"]
                self._minting = {k: v for k, v in self._minting.items() if self.now() - v[0] < 30}
                self._minting[key] = (self.now(), ident, cred)
        self.set_session(request, cred)
        self.drop_cookie(request, LEGACY_COOKIE)
        row = self.store.device(ident)
        return Principal("browser", ident, row["name"], "control", "cookie", row,
                         recheck=lambda: not self.store.check("browser", cred)[1])

    @web.middleware
    async def middleware(self, request: web.Request, handler):
        # 1. host allowlist, then the canonical host
        if not allowed_host(request.host or "", self.extra_hosts):
            await asyncio.to_thread(self.store.audit, "host_refused", request.remote, None,
                                    {"host": (request.host or "")[:100]})
            return web.Response(status=421, text="Unknown host name. Open the dashboard by the controller's address; "
                                                 "to allow a name, add it to PILOT_DASHBOARD_HOSTS.")
        if (self.public_url and request.method == "GET" and "text/html" in request.headers.get("Accept", "")
                and not is_loopback(request.remote)
                and (request.host or "").lower() != urlsplit(self.public_url).netloc.lower()):
            return web.Response(status=308, headers={"Location": self.public_url + request.path_qs})
        # 2. cross-site changes
        if request.method not in SAFE_METHODS:
            o = request.headers.get("Origin")
            if o is not None and (o == "null" or urlsplit(o).netloc.lower() != (request.host or "").lower()):
                return json_error(403, "cross_site", "This change came from another site.", "Use the dashboard itself.")
            sfs = request.headers.get("Sec-Fetch-Site")
            if sfs and sfs not in ("same-origin", "none"):
                return json_error(403, "cross_site", f"This change came from another site ({sfs}).",
                                  "Use the dashboard itself.")
        # 3. public routes
        if (request.method, request.path) in PUBLIC_PATHS or (self.key_signin and (request.method, request.path) == ("POST", "/pair/key")):
            return await handler(request)
        # an old ?key= link on the page
        if request.method == "GET" and request.path == "/" and "key" in request.query:
            return await self._old_key_link(request)
        # 4. who is asking
        principal, refusal = self._principal(request)
        if principal is None:
            return refusal
        if principal.kind == "legacy" and request.method == "GET" and request.path == "/" and self.legacy_open():
            principal = await self._carry_over(request)
        # 5. changes: JSON only; a cookie needs a matching Origin; read tokens only read
        if request.method not in SAFE_METHODS:
            if request.content_type != "application/json":
                return json_error(403, "json_only", "Requests that change something must be application/json.",
                                  "Send JSON with Content-Type: application/json.")
            if principal.by_cookie and request.headers.get("Origin") is None:
                return json_error(403, "origin_required", "This browser sent no Origin with a change.",
                                  "Use a current browser; changes from a page need its Origin.")
            if principal.scope != "control":
                return json_error(403, "read_only", f"The token '{principal.name}' can only read.",
                                  "Create a control token for changes.")
        if request.path.startswith("/api/auth/") and principal.kind == "script" and request.path != "/api/auth/me":
            return json_error(403, "browser_only", "Script tokens cannot manage devices or sign-ins.",
                              "Use a signed-in browser or the CLI on the controller.")
        # 6. the principal, for handlers and the forwarded X-Pilot-Device
        request[PRINCIPAL] = principal
        if principal.row is not None and principal.kind in ("browser", "script"):
            row = principal.row
            if self.store.touch_due(row, request.remote):
                await asyncio.to_thread(self.store.touch, row["id"], request.remote)
            if principal.kind == "browser" and principal.via == "cookie" and self.store.cookie_due(row) \
                    and not request.get(COOKIES):
                self.set_session(request, request.cookies.get(SESSION_COOKIE, ""))
                await asyncio.to_thread(self.store.cookie_sent, row["id"])
        return await handler(request)

    # -- what the viewer tells the live pilot about the device behind a request
    def device_headers(self, request: web.Request) -> dict[str, str]:
        p: Principal | None = request.get(PRINCIPAL)
        if p is None:
            return {}
        if p.kind == "service":         # a script on the controller may say whom it acts for
            return {k: request.headers[k] for k in (DEVICE_HEADER, DEVICE_NAME_HEADER) if k in request.headers}
        return {DEVICE_HEADER: p.id, DEVICE_NAME_HEADER: quote(p.name, safe="")}

    def still_valid(self, request: web.Request) -> bool:
        p: Principal | None = request.get(PRINCIPAL)
        return bool(p) and p.recheck()

    # -- routes: who am I, devices
    def notices(self, me: Principal) -> list[dict]:
        now = self.now()
        out = []
        if me.kind == "browser" and me.row and me.row.get("legacy") and now - me.row["created_at"] < NOTICE_S:
            out.append({"kind": "carried_over", "id": f"carried:{me.id}", "at": me.row["created_at"],
                        "text": "This browser now has its own sign-in. See Devices."})
        for d in self.store.list_devices():
            if d["kind"] == "browser" and self.store.two_addresses(d) and now - d["last_seen_at"] < NOTICE_S:
                out.append({"kind": "two_addresses", "id": f"two:{d['id']}:{int(d['last_seen_at'])}",
                            "at": d["last_seen_at"],
                            "text": f"{d['name']} was used from two addresses ({d['prev_ip']} and {d['last_ip']}) "
                                    "within 10 minutes. Review devices."})
        return out

    def device_view(self, d: dict, me: str, now: float) -> dict:
        badges = []
        if d.get("legacy"):
            badges.append("carried over from the old link")
        if self.store.two_addresses(d) and now - (d.get("last_seen_at") or 0) < NOTICE_S:
            badges.append("used from two addresses")
        if now - d["created_at"] < NOTICE_S:
            badges.append("new")
        keep = ("id", "kind", "scope", "name", "created_at", "created_ip", "created_via", "legacy", "last_seen_at",
                "last_ip", "expires_at")
        return {**{k: d.get(k) for k in keep}, "legacy": bool(d.get("legacy")), "created_by": self.who(d.get("created_by"))
                if d.get("created_by") not in (None, "legacy_link") else d.get("created_by"),
                "badges": badges, "current": d["id"] == me}

    def routes(self) -> list[web.RouteDef]:
        async def me(request):
            p: Principal = request[PRINCIPAL]
            dev = ({"id": p.id, "name": p.name, "kind": p.kind, "legacy": bool((p.row or {}).get("legacy"))}
                   if p.kind in ("browser", "script") else None)
            return web.json_response({"via": p.via, "device": dev, "notices": self.notices(p) if p.kind == "browser" else [],
                                      "add_device": self.add_device})

        def need_browser(request) -> Principal:
            p: Principal = request[PRINCIPAL]
            if p.kind != "browser":
                raise web.HTTPForbidden(text=json.dumps({"error": "browser_only", "reason": "Only a signed-in browser "
                                        "can do this.", "fix": "Use the CLI on the controller."}),
                                        content_type="application/json")
            return p

        async def devices(request):
            p = need_browser(request)
            now = self.now()
            rows = [self.device_view(d, p.id, now) for d in self.store.list_devices()]
            return web.json_response({"devices": [r for r in rows if r["kind"] == "browser"],
                                      "scripts": [r for r in rows if r["kind"] == "script"]})

        async def devices_post(request):
            p = need_browser(request)
            body = await request.json()
            act, ident = body.get("action"), str(body.get("id") or "")
            ip = request.remote
            if act == "signout":
                await asyncio.to_thread(self.store.revoke, p.id, "signed_out", p.id, ip)
                self.drop_cookie(request, SESSION_COOKIE)
                return web.json_response({"ok": True, "next": "/pair?reason=signed_out"})
            if act == "revoke":
                ok = await asyncio.to_thread(self.store.revoke, ident, "revoked", p.id, ip)
                if ident == p.id:
                    self.drop_cookie(request, SESSION_COOKIE)
                return web.json_response({"ok": ok, "self": ident == p.id})
            if act == "revoke_others":
                n = await asyncio.to_thread(self.store.revoke_others, p.id, p.id, ip)
                return web.json_response({"ok": True, "count": n})
            if act == "rename":
                ok = await asyncio.to_thread(self.store.rename, ident or p.id, str(body.get("name", "")))
                return web.json_response({"ok": ok})
            return json_error(400, "bad_action", "action must be signout, revoke, revoke_others or rename.")

        return [web.get("/api/auth/me", me), web.get("/api/auth/devices", devices),
                web.post("/api/auth/devices", devices_post)]

    def install(self, app: web.Application) -> None:
        """Routes, the response hook (headers, cookies) and hourly housekeeping on a viewer app."""
        app[AUTH_KEY] = self
        app.add_routes(self.routes())
        app.on_response_prepare.append(self.on_prepare)

        async def hourly(_app):
            async def loop():
                while True:
                    await asyncio.sleep(3600)
                    try:
                        await asyncio.to_thread(self.store.housekeeping)
                    except sqlite3.Error as e:
                        log.warning("auth housekeeping failed: %s", e)
            task = asyncio.get_running_loop().create_task(loop())
            yield
            task.cancel()
        app.cleanup_ctx.append(hourly)

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
import base64
import contextlib
import hashlib
import hmac
import html
import io
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
from typing import ClassVar
from urllib.parse import quote, unquote, urlsplit

from aiohttp import web

log = logging.getLogger(__name__)

SESSION_COOKIE = "pilot_session"
LEGACY_COOKIE = "pilot_key"              # the retired cookie whose value was K itself
KEY_HEADER = "X-Pilot-Key"
DEVICE_HEADER = "X-Pilot-Device"         # viewer -> live pilot: the device behind a request (with K only)
DEVICE_NAME_HEADER = "X-Pilot-Device-Name"   # its name, percent-encoded (headers are latin-1)
KEY_ENV, KEY_FILE = "PILOT_DASHBOARD_KEY", "dashboard.key"
CARRY_FILE = "dashboard.carryover"       # the carry-over window, next to the key: outlives a new store
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
RESUBMIT_S = 10                          # the same address and browser again this soon: a double submit
NOTICE_S = DAY
KEEPALIVE_S = 15.0
AUDIT_KEEP_S, AUDIT_MAX_ROWS = 90 * DAY, 10_000
AUDIT_PER_IP_HOUR = 10                   # rows one address's failures may add in an hour; later ones only count
NOISE_EVENTS = ("host_refused", "signin_failed", "throttled", "service_key_refused_lan")   # anyone on the LAN adds these
NAME_MAX = 60
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# public routes (POST /pair/key is answered only when PILOT_KEY_SIGNIN is on; otherwise it is a 404)
PUBLIC_PATHS = {("GET", "/pair"), ("POST", "/pair"), ("POST", "/pair/key"), ("GET", "/static/signin.js"),
                ("GET", "/favicon.svg")}
STATIC = Path(__file__).parent / "static"
WORDS_FILE = Path(__file__).with_name("pair_words.txt")
MAX_BROWSER_GRANTS = 3
WORDS_OFF_AFTER = 5                      # wrong words in all, while codes are live, switch typed words off
IN_APP = re.compile(r"; wv\)|FBAN|FBAV|Instagram|Line/|GSA/|LinkedInApp|Snapchat|Twitter|Slack|Teams/|MicroMessenger")
REALM = 'Bearer realm="Game Pilot"'
FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.5" '
           'fill="#f0b34a" stroke="#8a5a10" stroke-width="1.5"/></svg>')
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


# ---------------------------------------------------------------- three-word codes

def _load_words() -> list[str]:
    words = [w.strip() for w in WORDS_FILE.read_text(encoding="utf-8").splitlines()
             if w.strip() and not w.startswith("#")]
    assert len({w[:3] for w in words}) == len(words), "every 3-letter prefix must be unique"
    return words


WORDS = _load_words()
CODE_WORDS = [w for w in WORDS if w.isalpha()]   # "yo-yo" would split in two when typed: never drawn
_BY_PREFIX = {w[:3]: w for w in CODE_WORDS}


def canonical_words(text: str | None) -> str | None:
    """'Maple-ORBIT crane' or 'map orb cra' -> 'maple orbit crane'; None unless exactly three tokens
    (split on anything that is not a letter), each the prefix (3 letters or more) of a listed word."""
    tokens = re.findall(r"[a-z]+", (text or "").lower())
    if len(tokens) != 3:
        return None
    out = []
    for t in tokens:
        w = _BY_PREFIX.get(t[:3]) if len(t) >= 3 else None
        if not w or not w.startswith(t):
            return None
        out.append(w)
    return " ".join(out)


def lan_address() -> str:
    """This machine's LAN address (the outgoing interface), for links when no public URL is set."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("192.0.2.1", 9))       # sends nothing; picks the outgoing interface
            return sk.getsockname()[0]
    except OSError:
        return socket.gethostname()


def qr_svg(url: str) -> str | None:
    """The link as an inline SVG QR code (dark on white, quiet zone), or None without segno."""
    try:
        import segno
    except ImportError:
        return None
    return segno.make(url, error="m").svg_inline(scale=4, border=4, dark="#000", light="#fff", omitsize=True)


def qr_text(url: str) -> str | None:
    try:
        import segno
    except ImportError:
        return None
    buf = io.StringIO()
    segno.make(url, error="m").terminal(out=buf, compact=True)
    return buf.getvalue()


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


def carry_over_record(runs_dir: Path | None) -> dict | None:
    """The carry-over window as first opened ({fp, until}), kept next to the key so that a store moved
    aside as corrupt, deleted, or opened at another PILOT_AUTH_DB path neither reopens nor extends it."""
    if runs_dir is None:
        return None
    try:
        rec = json.loads((Path(runs_dir) / CARRY_FILE).read_text())
        return {"fp": str(rec["fp"]), "until": float(rec["until"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_carry_over(runs_dir: Path | None, fp: str, until: float) -> None:
    if runs_dir is not None:
        Path(runs_dir).mkdir(parents=True, exist_ok=True)
        _write_private(Path(runs_dir) / CARRY_FILE, json.dumps({"fp": fp, "until": until}) + "\n")


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
        self.recreated = False            # moved aside as corrupt: an empty store started
        try:
            self.db = self._open()
        except sqlite3.DatabaseError as e:
            self.recreated = True
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
        """One row per (event, ip, minute), with a count. Failures anyone on the network can cause add at
        most AUDIT_PER_IP_HOUR rows per address an hour; after that they only raise the newest row's
        count, so a flood cannot push real events out of the table."""
        now = self.now()
        minute = int(now // 60) * 60
        with self._lock:
            row = self.db.execute("SELECT id FROM auth_events WHERE event=? AND ip IS ? AND t>=? AND t<? "
                                  "AND device_id IS ? ORDER BY id DESC LIMIT 1",
                                  (event, ip, minute, minute + 60, device_id)).fetchone()
            if not row and event in NOISE_EVENTS and ip:
                marks = ",".join("?" * len(NOISE_EVENTS))
                recent = self.db.execute(f"SELECT COUNT(*) FROM auth_events WHERE ip=? AND t>? AND event IN ({marks})",
                                         (ip, now - 3600, *NOISE_EVENTS)).fetchone()[0]
                if recent >= AUDIT_PER_IP_HOUR:
                    row = self.db.execute("SELECT id FROM auth_events WHERE event=? AND ip=? ORDER BY id DESC LIMIT 1",
                                          (event, ip)).fetchone()
            if row:
                self.db.execute("UPDATE auth_events SET count=count+1 WHERE id=?", (row["id"],))
            else:
                self.db.execute("INSERT INTO auth_events (t, event, ip, device_id, detail) VALUES (?,?,?,?,?)",
                                (now, event, ip, device_id, json.dumps(detail, default=str) if detail else None))

    def audit_rows(self, n: int = 1000) -> list[dict]:
        return self._rows("SELECT * FROM auth_events ORDER BY t DESC, id DESC LIMIT ?", (n,))

    def audit_since(self, event: str, t: float) -> list[dict]:
        return self._rows("SELECT * FROM auth_events WHERE event=? AND t>? ORDER BY t DESC, id DESC", (event, t))

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
        row = self.device(ident)
        cur = self._x("UPDATE devices SET revoked_at=?, revoked_by=?, revoke_reason=? WHERE id=? AND revoked_at IS NULL",
                      (self.now(), by, reason, ident))
        if cur.rowcount:
            self._cancel_orphan_grants()
            event = ("token_revoked" if row and row["kind"] == "script" else
                     {"signed_out": "signed_out", "idle": "idle", "rotate_unkept": "legacy_revoked"}.get(reason, "revoked"))
            self.audit(event, ip, ident, {"reason": reason, "by": by})
        return bool(cur.rowcount)

    def _cancel_orphan_grants(self) -> int:
        """Codes whose maker is signed out are cancelled with it: a stolen session that kept one live
        must not sign a new device in after the owner signed it out."""
        return self._x("UPDATE grants SET state='cancelled' WHERE state='waiting' AND created_by IN "
                       "(SELECT id FROM devices WHERE revoked_at IS NOT NULL)").rowcount

    def end_carry_over(self) -> None:
        """The old key cookie stops working at once (a rotation ends the 72-hour window), and so do the
        one-time links old ?key= bookmarks made."""
        self.set_meta("legacy_until", "0")
        self._x("UPDATE grants SET state='cancelled' WHERE state='waiting' AND created_by='legacy_link'")

    def legacy_family(self) -> tuple[list[dict], dict[str, str]]:
        """The live browsers carried over from the old key and every browser added from one of them
        (directly or through another), roots first with each one's additions after it; and the
        maker of each addition. A rotation keeps only the ones the user names and their additions."""
        rows = [d for d in self.list_devices() if d["kind"] == "browser"]
        members = {d["id"] for d in rows if d["legacy"]}
        grown = True
        while grown:
            new = {d["id"] for d in rows if d["created_by"] in members and d["id"] not in members}
            members |= new
            grown = bool(new)
        parent = {d["id"]: d["created_by"] for d in rows if d["id"] in members and d["created_by"] in members}
        out: list[dict] = []

        def walk(ident: str) -> None:
            out.append(next(d for d in rows if d["id"] == ident))
            for d in sorted((d for d in rows if parent.get(d["id"]) == ident), key=lambda d: d["created_at"]):
                walk(d["id"])
        for d in sorted((d for d in rows if d["id"] in members and d["id"] not in parent), key=lambda d: d["created_at"]):
            walk(d["id"])
        return out, parent

    def revoke_others(self, keep: str, by: str | None = None, ip: str | None = None) -> int:
        cur = self._x("UPDATE devices SET revoked_at=?, revoked_by=?, revoke_reason='revoke_others'"
                      " WHERE id != ? AND kind='browser' AND revoked_at IS NULL", (self.now(), by, keep))
        self._cancel_orphan_grants()
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
    def create_grant(self, created_by: str, words: bool = False) -> dict:
        """A grant with two faces: a 256-bit link token (`<id>.<secret>`) and, with `words`, three
        words (only their sha256 is kept; redrawn on a clash). One grant, used once, within 10
        minutes. A browser holds one live grant (a new one cancels it) and browsers hold at most three
        in all (`GrantLimit`); the CLI and the old-link carry-over are not limited."""
        ident, secret = secrets.token_hex(5), secrets.token_urlsafe(32)
        now = self.now()
        by_browser = bool(ID_RE.fullmatch(created_by or ""))
        with self._lock:
            if by_browser:
                self.db.execute("UPDATE grants SET state='cancelled' WHERE created_by=? AND state='waiting'", (created_by,))
                live = self.db.execute("SELECT COUNT(*) FROM grants WHERE state='waiting' AND expires_at>? AND "
                                       "created_by NOT IN ('cli', 'legacy_link')", (now,)).fetchone()[0]
                if live >= MAX_BROWSER_GRANTS:
                    raise GrantLimit(f"{live} codes are open; cancel one or let it expire")
            for _ in range(20):
                typed = " ".join(secrets.choice(CODE_WORDS) for _ in range(3)) if words else None
                try:
                    self.db.execute("INSERT INTO grants (id, link_hash, words_hash, created_at, expires_at, created_by,"
                                    " state) VALUES (?,?,?,?,?,?,?)",
                                    (ident, digest(secret), digest(typed) if typed else None, now, now + GRANT_TTL_S,
                                     created_by, "waiting"))
                    break
                except sqlite3.IntegrityError:
                    continue                                # the same three words are in use: draw again
            else:
                raise RuntimeError("could not draw unused words")
        self.audit("grant_created", None, created_by if by_browser else None, {"grant": ident, "by": created_by})
        return {"id": ident, "link": f"{ident}.{secret}", "words": typed, "expires_at": now + GRANT_TTL_S}

    def grant_by_words(self, canonical: str) -> dict | None:
        rows = self._rows("SELECT * FROM grants WHERE words_hash=?", (digest(canonical),))
        return rows[0] if rows else None

    def grant_by_link(self, link: str | None) -> dict | None:
        ident, secret = split_cred(link, "")
        rows = self._rows("SELECT * FROM grants WHERE id=?", (ident,)) if ident else []
        if not rows or not hmac.compare_digest(rows[0]["link_hash"], digest(secret)):
            return None
        return rows[0]

    def redeem(self, kind: str, value: str, *, ip: str | None, user_agent: str = "", client: str = "",
               name: str = "", presenter: str | None = None, legacy_ok: bool = True) -> tuple[str, dict]:
        """Spend a grant by its words (canonical) or link: ('ok', {device, cred}) | ('already', {}) |
        ('wrong', {}) | ('expired', {}) | ('conflict', {device, used_ip, used_at}). A spent grant
        presented by anyone but the device it made signs that device out (ruling 42). An old-key link
        needs the carry-over window (`legacy_ok`); a device made through one, or through a code from a
        carried-over device, is carried over too (listed at rotation)."""
        g = self.grant_by_words(value) if kind == "words" else self.grant_by_link(value)
        if g is None:
            return "wrong", {}
        now = self.now()
        if g["state"] in ("used", "conflict"):
            if presenter and presenter == g["device_id"]:
                return "already", {}
            dev = self.device(g["device_id"]) if g["device_id"] else None
            if (g["state"] == "used" and dev and not dev["revoked_at"] and ip and ip == g["used_ip"]
                    and ((user_agent or "")[:200] or None) == dev["user_agent"] and now - (g["used_at"] or 0) <= RESUBMIT_S):
                return "already", {}        # a double submit before the first reply's cookie was stored
            if g["state"] == "used":
                self._x("UPDATE grants SET state='conflict' WHERE id=?", (g["id"],))
                if dev:
                    self.revoke(dev["id"], "conflict", by="conflict", ip=ip)
                self.audit("grant_conflict", ip, dev["id"] if dev else None,
                           {"grant": g["id"], "device": dev["name"] if dev else None, "how": kind})
            return "conflict", {"device": dev["name"] if dev else "a browser", "used_ip": g["used_ip"],
                                "used_at": g["used_at"]}
        maker = self.device(g["created_by"]) if ID_RE.fullmatch(g["created_by"] or "") else None
        if g["state"] == "waiting" and (
                (ID_RE.fullmatch(g["created_by"] or "") and (not maker or maker["revoked_at"]))   # its maker is signed out
                or (g["created_by"] == "legacy_link" and not legacy_ok)):                      # the window closed
            self._x("UPDATE grants SET state='cancelled' WHERE id=? AND state='waiting'", (g["id"],))
            return "expired", {}
        if g["state"] != "waiting" or now > g["expires_at"]:
            if g["state"] == "waiting":
                self._x("UPDATE grants SET state='expired' WHERE id=? AND state='waiting'", (g["id"],))
            return "expired", {}
        with self._lock:                  # spend and mint in one transaction: others see both or neither
            self.db.execute("BEGIN IMMEDIATE")
            try:
                spent = self.db.execute("UPDATE grants SET state='used', used_at=?, used_ip=? WHERE id=? AND "
                                        "state='waiting'", (now, ip, g["id"])).rowcount
                if spent:
                    row, cred = self.create_device("browser", name=clip_name(name, device_name(user_agent, client)),
                                                   created_via=kind, created_by=g["created_by"], ip=ip,
                                                   user_agent=user_agent, grant_id=g["id"],
                                                   legacy=g["created_by"] == "legacy_link" or bool(maker and maker["legacy"]))
                    self.db.execute("UPDATE grants SET device_id=? WHERE id=?", (row["id"], g["id"]))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        if not spent:                                       # another request spent it a moment ago
            return self.redeem(kind, value, ip=ip, user_agent=user_agent, client=client, name=name, presenter=presenter,
                               legacy_ok=legacy_ok)
        return "ok", {"device": row, "cred": cred}

    def switch_words_off(self) -> int:
        """Typed words stop working for every live grant; their links and QR codes keep working."""
        n = self._x("UPDATE grants SET words_hash=NULL WHERE state='waiting' AND expires_at>? AND "
                    "created_by != 'legacy_link'", (self.now(),)).rowcount
        self.audit("words_switched_off", None, None, {"grants": n})
        return n

    def live_grants(self) -> list[dict]:
        return self._rows("SELECT id, created_by, words_hash IS NULL AS words_off FROM grants WHERE state='waiting'"
                          " AND expires_at>?", (self.now(),))

    def cancel_grant(self, ident: str, by: str) -> bool:
        return bool(self._x("UPDATE grants SET state='cancelled' WHERE id=? AND created_by=? AND state='waiting'",
                            (ident, by)).rowcount)

    def grant(self, ident: str) -> dict | None:
        rows = self._rows("SELECT * FROM grants WHERE id=?", (ident,))
        if rows:
            rows[0].pop("link_hash", None)
            rows[0]["words_off"] = rows[0].pop("words_hash", None) is None and rows[0]["created_by"] != "legacy_link"
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
            self._cancel_orphan_grants()
            self.db.execute("DELETE FROM devices WHERE revoke_reason='idle' AND revoked_at < ?", (now - PRUNE_S,))
            self.db.execute("DELETE FROM grants WHERE created_at < ?", (now - GRANT_KEEP_S,))
            self.db.execute("DELETE FROM auth_events WHERE t < ?", (now - AUDIT_KEEP_S,))
            over = self.db.execute("SELECT COUNT(*) FROM auth_events").fetchone()[0] - AUDIT_MAX_ROWS
            if over > 0:                    # the network's noise goes first, oldest first
                marks = ",".join("?" * len(NOISE_EVENTS))
                self.db.execute(f"DELETE FROM auth_events WHERE id IN (SELECT id FROM auth_events WHERE event IN ({marks})"
                                " ORDER BY t, id LIMIT ?)", (*NOISE_EVENTS, over))
            self.db.execute("DELETE FROM auth_events WHERE id NOT IN (SELECT id FROM auth_events ORDER BY t DESC"
                            " LIMIT ?)", (AUDIT_MAX_ROWS,))


# ---------------------------------------------------------------- the audit in words

EVENT_WORDS = {
    "signin": "signed in", "signin_failed": "failed sign-in tries", "throttled": "sign-in tries paused",
    "words_switched_off": "typed words switched off", "grant_created": "sign-in code made",
    "grant_conflict": "a used sign-in code tried again", "signed_out": "signed out",
    "revoked": "signed out by another device", "revoke_others": "all other devices signed out",
    "idle": "signed out after 180 days unused", "service_key_refused_lan": "service key refused from the network",
    "host_refused": "unknown host name refused", "token_created": "script token made",
    "token_revoked": "script token revoked", "key_rotated": "service key rotated",
    "legacy_kept": "carried-over device kept", "legacy_revoked": "carried-over device signed out",
    "unlock": "sign-in pauses lifted", "control": "control"}
BAD_EVENTS = {"signin_failed", "throttled", "words_switched_off", "grant_conflict", "service_key_refused_lan",
              "host_refused"}


def name_of(store: AuthStore, ident: str | None) -> str:
    """A device id (or 'cli') as people read it."""
    if not ident or ident in ("idle", "conflict", "legacy_link", "recovery_key"):
        return ""
    if ident == "cli":
        return "the controller"
    row = store.device(ident)
    return row["name"] if row else ident


def audit_sentences(store: AuthStore, n: int = 20) -> list[dict]:
    """The newest audit rows as sentences ('Failed sign-in tries, 192.168.1.50 (100 times)')."""
    out = []
    for e in store.audit_rows(n):
        detail = json.loads(e["detail"] or "{}")
        what = EVENT_WORDS.get(e["event"], e["event"].replace("_", " "))
        if e["event"] == "signin" and detail.get("how"):
            what = f"signed in ({detail['how'].replace('_', ' ')})"
        if e["event"] == "control" and detail.get("action"):
            what = f"control: {detail['action']}"
        if e["event"] == "revoked" and detail.get("by"):
            what = f"signed out by {name_of(store, detail['by']) or detail['by']}"
        who = name_of(store, e["device_id"])
        text = (what[0].upper() + what[1:] + (f", {who}" if who else "") + (f", {e['ip']}" if e["ip"] else "")
                + (f" ({e['count']} times)" if e["count"] > 1 else ""))
        out.append({"t": e["t"], "event": e["event"], "ip": e["ip"], "count": e["count"], "text": text,
                    "bad": e["event"] in BAD_EVENTS})
    return out


class GrantLimit(Exception):
    """Browsers already hold the most live sign-in codes allowed."""


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

def security_headers(response: web.StreamResponse) -> None:
    """On every response: never cached, never framed, no sniffing, no Referer to other sites."""
    h = response.headers
    h.setdefault("Cache-Control", "no-store")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Referrer-Policy", "same-origin")


def page_policy(page: str) -> str:
    """The dashboard page's Content-Security-Policy: only its own inline script runs (named by its
    hash), so markup that slipped into the page (an unescaped device name) runs no handler and loads
    no script from elsewhere; no plugins, no <base>, never framed."""
    hashes = [f"'sha256-{base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()}'"
              for s in re.findall(r"<script>(.*?)</script>", page, re.DOTALL)]
    return f"script-src {' '.join(hashes) or chr(39) + 'none' + chr(39)}; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"


def cross_site(request: web.Request) -> web.Response | None:
    """A change from another site: Origin null or foreign, or Sec-Fetch-Site other than same-origin/none."""
    if request.method in SAFE_METHODS:
        return None
    o = request.headers.get("Origin")
    if o is not None and (o == "null" or urlsplit(o).netloc.lower() != (request.host or "").lower()):
        return json_error(403, "cross_site", "This change came from another site.", "Use the dashboard itself.")
    sfs = request.headers.get("Sec-Fetch-Site")
    if sfs and sfs not in ("same-origin", "none"):
        return json_error(403, "cross_site", f"This change came from another site ({sfs}).", "Use the dashboard itself.")
    return None

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
        self._wrong_words = 0                        # wrong typed words while codes are live (ruling 41)
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
        """First start of this code: open the 72-hour carry-over window for the current K, once. The
        window is also kept next to the key (runs/dashboard.carryover), so a new store (a corrupt one
        moved aside, a deleted file, another PILOT_AUTH_DB) takes it from there instead of opening a
        new one; a store recreated after corruption with no such record keeps the window shut."""
        runs = self.keys.runs_dir
        side = carry_over_record(runs)
        if self.store.meta("legacy_key_fp") is None:
            if side is not None:
                fp, until = side["fp"], side["until"]
            elif self.store.recreated:
                fp, until = fingerprint(self.keys.get()), 0.0
            else:
                fp, until = fingerprint(self.keys.get()), self.now() + LEGACY_WINDOW_S
            self.store.set_meta("legacy_key_fp", fp)
            self.store.set_meta("legacy_until", str(until))
        if side is None or side["until"] != float(self.store.meta("legacy_until") or 0):
            write_carry_over(runs, self.store.meta("legacy_key_fp") or "", float(self.store.meta("legacy_until") or 0))
        self.store.housekeeping()

    # -- carry-over
    def legacy_open(self) -> bool:
        until = float(self.store.meta("legacy_until") or 0)
        return self.now() < until and self.store.meta("legacy_key_fp") == fingerprint(self.keys.get())

    # -- names
    def who(self, ident: str | None) -> str:
        return name_of(self.store, ident)

    # -- cookies (written in on_response_prepare, so they also reach files, streams and raised errors)
    @staticmethod
    def set_session(request: web.Request, cred: str) -> None:
        request.setdefault(COOKIES, []).append(("set", SESSION_COOKIE, cred))

    @staticmethod
    def drop_cookie(request: web.Request, name: str) -> None:
        request.setdefault(COOKIES, []).append(("del", name, ""))

    async def on_prepare(self, request: web.Request, response: web.StreamResponse) -> None:
        security_headers(response)
        # the hook runs after aiohttp has turned response.cookies into headers: add them as headers
        for op, name, value in request.get(COOKIES, []):
            response.headers.add("Set-Cookie", cookie_header(name, value, secure=request.secure, delete=op == "del"))

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

    async def _carry_over(self, request: web.Request) -> Principal | None:
        """The old cookie on the page itself becomes a device (once per browser: parallel loads of
        one page reuse the device minted in the last 30 s for the same address and user agent)."""
        ua = request.headers.get("User-Agent", "")
        key = (request.remote, ua)
        lock = self._mint_locks.setdefault(id(asyncio.get_running_loop()), asyncio.Lock())
        async with lock:
            hit = self._minting.get(key)
            if hit and self.now() - hit[0] < 30:
                ident, cred = hit[1], hit[2]
            elif not self.legacy_open():                 # a rotation closed the window a moment ago
                return None
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
        if (refusal := cross_site(request)) is not None:
            return refusal
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
            if principal is None:
                self.drop_cookie(request, LEGACY_COOKIE)
                return see_other("/pair?reason=old_link")
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

    # -- notices, devices, the audit in words
    def notices(self, me: Principal) -> list[dict]:
        now = self.now()
        out = []
        if me.kind == "browser" and me.row and me.row.get("legacy") and now - me.row["created_at"] < NOTICE_S:
            out.append({"kind": "carried_over", "id": f"carried:{me.id}", "at": me.row["created_at"],
                        "text": "This browser now has its own sign-in. See Devices."})
        for d in self.store.list_devices():
            if d["kind"] != "browser":
                continue
            if d["id"] != me.id and now - d["created_at"] < NOTICE_S:
                how = ("carried over from the old link" if d.get("created_via") == "legacy_cookie"
                       else "signed in with the recovery key" if d.get("created_via") == "recovery_key"
                       else f"added from {self.who(d.get('created_by')) or 'a sign-in code'}")
                out.append({"kind": "new_device", "id": f"new:{d['id']}", "at": d["created_at"],
                            "text": f"New device signed in: {d['name']}, {how} at {_ago(d['created_at'], now)}"
                                    f"{', ' + d['created_ip'] if d.get('created_ip') else ''}. Review devices."})
            if self.store.two_addresses(d) and now - d["last_seen_at"] < NOTICE_S:
                out.append({"kind": "two_addresses", "id": f"two:{d['id']}:{int(d['last_seen_at'])}",
                            "at": d["last_seen_at"],
                            "text": f"{d['name']} was used from two addresses ({d['prev_ip']} and {d['last_ip']}) "
                                    "within 10 minutes. Review devices."})
        for e in self.store.audit_since("grant_conflict", now - NOTICE_S):   # 24 h, however much else was logged
            detail = json.loads(e["detail"] or "{}")
            out.append({"kind": "conflict", "id": f"conflict:{e['id']}", "at": e["t"],
                        "text": f"A used sign-in code was tried again from {e['ip'] or 'an unknown address'}. "
                                f"The browser it had signed in ({detail.get('device') or 'unknown'}) was signed out. "
                                "Review devices."})
        return out

    def device_view(self, d: dict, me: str, now: float) -> dict:
        badges = []
        if d.get("legacy"):
            badges.append("carried over from the old link")
        if d.get("created_via") == "recovery_key":
            badges.append("signed in with the recovery key")
        if self.store.two_addresses(d) and now - (d.get("last_seen_at") or 0) < NOTICE_S:
            badges.append("used from two addresses")
        if now - d["created_at"] < NOTICE_S:
            badges.append("new")
        keep = ("id", "kind", "scope", "name", "created_at", "created_ip", "created_via", "legacy", "last_seen_at",
                "last_ip", "expires_at")
        return {**{k: d.get(k) for k in keep}, "legacy": bool(d.get("legacy")), "created_by": self.who(d.get("created_by"))
                if d.get("created_by") not in (None, "legacy_link") else d.get("created_by"),
                "badges": badges, "current": d["id"] == me}

    def log_rows(self, n: int = 20) -> list[dict]:
        return audit_sentences(self.store, n)

    # -- links
    def link_base(self, request: web.Request | None = None, port: int = 8780) -> str:
        """The base of sign-in links: PILOT_PUBLIC_URL, else the host the creating browser used (when
        allowed and not loopback), else this machine's LAN address."""
        if self.public_url:
            return self.public_url
        if request is not None:
            h = request.host or ""
            name = host_name(h)
            if h and name != "localhost" and not is_loopback(name) and allowed_host(h, self.extra_hosts):
                return f"{request.scheme}://{h}"
            port = request.url.port or port
        return f"http://{lan_address()}:{port}"

    def session_device(self, request: web.Request) -> dict | None:
        row, why = self.store.check("browser", request.cookies.get(SESSION_COOKIE))
        return None if why else row

    # -- the sign-in page
    MESSAGES: ClassVar[dict[str, tuple[str, str]]] = {
        "signed_out": ("note", "You signed out of this browser."),
        "idle": ("note", "This browser was signed out after 180 days without use."),
        "conflict": ("err", ("This browser was signed out: its sign-in code was used again by another browser. "
                             "Make a new code on a browser that is signed in.")),
        "wrong": ("err", "Those words don't match a current code. Codes last 10 minutes and work once."),
        "words_off": ("err", ("Typed words were switched off after 5 wrong tries on your network. "
                              "Use the link or QR code instead.")),
        "expired": ("err", "This code has expired. Make a new one on the other device."),
        "used": ("err", "This code was already used."),
        "bad_words": ("err", "Type the three words of the code, separated by spaces."),
    }

    def _message(self, state: str, request: web.Request, **kw) -> tuple[str, str]:
        if state == "revoked":
            row, _ = self.store.check("browser", request.cookies.get(SESSION_COOKIE))
            if row and row.get("revoked_at") and row.get("revoke_reason") in ("revoked", "revoke_others"):
                by = self.who(row.get("revoked_by"))
                return "note", f"This browser was signed out{' from ' + by if by else ''} at {_ago(row['revoked_at'], 0)}."
            return "note", "This browser was signed out."
        if state == "old_link":
            until = float(self.store.meta("legacy_until") or 0)
            when = f" on {time.strftime('%-d %b', time.localtime(until))}" if until and until < self.now() else ""
            return "note", f"Links with ?key= stopped working{when}. Sign in with a code from a browser that is signed in."
        if state == "too_many":
            m, s = divmod(int(kw.get("wait", 60)), 60)
            return "err", (f"Too many tries from this network. Try again in <span class=\"count\" id=\"count\">"
                           f"{m}:{s:02d}</span>. Browsers already signed in keep working.")
        if state == "cookie_blocked":
            return "err", (f"This browser did not keep the sign-in. Allow cookies for "
                           f"{host_name(request.host or '') or 'this address'}, then use a new code.")
        if state == "conflict_used":
            return "err", kw.get("text", "")
        if state == "wrong":
            left = kw.get("left")
            tail = f" {left} more {'try' if left == 1 else 'tries'} before a short wait." if left is not None else ""
            return "err", self.MESSAGES["wrong"][1] + tail
        return self.MESSAGES.get(state, ("", ""))

    def render(self, request: web.Request, status: int = 200, state: str = "", nxt: str = "/", wait: int = 0,
               **kw) -> web.Response:
        cls, text = self._message(state, request, wait=wait, **kw)
        if state != "too_many":
            text = html.escape(text, quote=False)
        message = f'<p class="{cls}" id="state" role="alert">{text}</p>' if text else ""
        ua = request.headers.get("User-Agent", "")
        app = in_app_browser(ua)
        inapp = ""
        if app:
            inapp = (f'<div class="warn" id="inapp"><p>You opened this inside {html.escape(app)}. A sign-in here stays '
                     'inside that app. Open this page in your browser: menu &gt; Open in browser. The link isn\'t used '
                     'up until you press Sign in.</p><label class="field" for="inapp-address">This page\'s address'
                     f'<input type="text" id="inapp-address" readonly value="{html.escape(str(request.url))}"></label>'
                     '<button type="button" class="plain" id="inapp-copy">Copy the address</button></div>')
        keyform = ""
        if self.key_signin:
            keyform = ('<details id="keyform"><summary>Use the recovery key</summary>'
                       '<form method="post" action="/pair/key" autocomplete="on">'
                       '<input class="vh" type="text" name="username" value="pilot" autocomplete="username" '
                       'tabindex="-1" aria-hidden="true">'
                       f'<input type="hidden" name="next" value="{html.escape(nxt)}">'
                       '<label class="field" for="key">Recovery key<input type="password" id="key" name="key" '
                       'autocomplete="current-password" required></label>'
                       '<button class="primary" type="submit">Sign in with the key</button></form>'
                       '<p class="hint">Your password manager can keep it. It works from any computer on your network '
                       'and crosses it unencrypted.</p></details>')
        page = (STATIC / "pair.html").read_text(encoding="utf-8")
        values = {"state": html.escape(state), "wait": str(int(wait)), "next": html.escape(nxt), "message": message,
                  "inapp": inapp, "keyform": keyform, "name": html.escape(device_name(ua))}
        for k, v in values.items():
            page = page.replace("{{" + k + "}}", v)
        headers = {"Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; "
                   "img-src 'self' data:; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
                   # same-origin, not no-referrer: under no-referrer browsers send "Origin: null" on the page's own
                   # POSTs (Fetch: a POST's origin is serialised as null for that policy), and a sign-in needs a
                   # matching Origin; links to other sites still get no Referer, and a fragment is never in one
                   "Referrer-Policy": "same-origin"}
        if wait:
            headers["Retry-After"] = str(int(wait))
        return web.Response(status=status, text=page, content_type="text/html", headers=headers)

    def _signed_in(self, request: web.Request, cred: str, nxt: str, form: bool) -> web.Response:
        self.set_session(request, cred)
        check = "/pair?check=1&next=" + quote(nxt, safe="")
        return see_other(check) if form else web.json_response({"ok": True, "next": check})

    def _refused(self, request: web.Request, form: bool, status: int, error: str, state: str, nxt: str,
                 **kw) -> web.Response:
        if form:
            return self.render(request, status, state, nxt, **kw)
        _, text = self._message(state, request, **kw)
        text = re.sub(r"<[^>]+>", "", text)
        headers = {"Retry-After": str(int(kw["wait"]))} if kw.get("wait") else {}
        extra = {k: v for k, v in kw.items() if k in ("left", "words_off")}
        return web.json_response({"error": error, "reason": text, "fix": "", **extra}, status=status, headers=headers)

    async def pair_get(self, request: web.Request) -> web.StreamResponse:
        nxt = safe_next(request.query.get("next"))
        if self.session_device(request):
            return see_other(nxt)                   # signed in already (and the cookie stuck, after check=1)
        if request.query.get("check") == "1":
            return self.render(request, 200, "cookie_blocked", nxt)
        reason = request.query.get("reason", "")
        state = reason if reason in ("signed_out", "revoked", "idle", "old_link", "conflict") else ""
        return self.render(request, 200, state, nxt)

    async def pair_post(self, request: web.Request) -> web.StreamResponse:
        ip = request.remote
        bucket = bucket_of(ip)
        ctype = request.content_type
        form = ctype in ("application/x-www-form-urlencoded", "multipart/form-data")
        if form:
            if request.headers.get("Origin") is None:           # a form needs a matching Origin (checked earlier)
                return json_error(403, "origin_required", "A form sign-in needs its Origin.", "Use a current browser.")
            body = {k: str(v) for k, v in (await request.post()).items()}
            if body.get("link"):
                return json_error(403, "link_in_form", "A sign-in link is sent by the page's script, never in a form.",
                                  "Open the link in a browser with script on, or type the words.")
        elif ctype == "application/json":
            try:
                body = await request.json()
            except ValueError:
                body = None
            if not isinstance(body, dict):
                return json_error(400, "bad_request", "Send a JSON object.")
        else:
            return json_error(403, "json_only", "Send JSON (or the page's own form).")
        nxt = safe_next(body.get("next"))
        mine = self.session_device(request)
        link, typed = body.get("link"), body.get("words")
        ua = request.headers.get("User-Agent", "")
        opts = {"ip": ip, "user_agent": ua, "client": str(body.get("client") or "")[:20],
                "name": str(body.get("name") or ""), "presenter": mine["id"] if mine else None,
                "legacy_ok": self.legacy_open()}
        if link:
            if mine:                                             # signed in already: on to next, the code unspent
                return web.json_response({"ok": True, "already": True, "next": nxt})
            status, info = await asyncio.to_thread(self.store.redeem, "link", str(link), **opts)
            if status == "wrong":
                self.throttle.fail(bucket)
                await asyncio.to_thread(self.store.audit, "signin_failed", ip, None, {"how": "link"})
        elif typed is not None:
            words = canonical_words(str(typed))
            if words is None:
                return self._refused(request, form, 400, "bad_words", "bad_words", nxt)
            if mine:
                return web.json_response({"ok": True, "already": True, "next": nxt}) if not form else see_other(nxt)
            wait = self.throttle.reserve(bucket)                 # check-and-count before any await
            if wait > 0:
                await asyncio.to_thread(self.store.audit, "throttled", ip, None, {"how": "words"})
                await asyncio.to_thread(self.store.audit, "signin_failed", ip, None, {"how": "words"})
                return self._refused(request, form, 429, "too_many", "too_many", nxt, wait=max(1, int(wait + 0.999)))
            status, info = await asyncio.to_thread(self.store.redeem, "words", words, **opts)
            if status == "wrong":
                await asyncio.to_thread(self.store.audit, "signin_failed", ip, None, {"how": "words"})
                live = await asyncio.to_thread(self.store.live_grants)
                if live:
                    self._wrong_words += 1
                    if self._wrong_words >= WORDS_OFF_AFTER:
                        self._wrong_words = 0
                        await asyncio.to_thread(self.store.switch_words_off)
                    live = await asyncio.to_thread(self.store.live_grants)
                words_off = any(g["words_off"] and g["created_by"] != "legacy_link" for g in live)
                left = max(0, Throttle.PER_BUCKET - self.throttle.failures(bucket))
                if words_off:
                    return self._refused(request, form, 401, "wrong_code", "words_off", nxt, words_off=True, left=left)
                return self._refused(request, form, 401, "wrong_code", "wrong", nxt, left=left, words_off=False)
            self.throttle.refund(bucket)                        # the words matched a code: no guess
        else:
            return json_error(400, "bad_request", "Send the code's link or its three words.")
        if status == "ok":
            return self._signed_in(request, info["cred"], nxt, form)
        if status == "already":
            return see_other(nxt) if form else web.json_response({"ok": True, "already": True, "next": nxt})
        if status == "wrong":
            return self._refused(request, form, 401, "wrong_code", "wrong", nxt)
        if status == "expired":
            return self._refused(request, form, 410, "expired", "expired", nxt)
        ago = int(self.now() - (info.get("used_at") or self.now()))
        text = (f"This code was already used by another browser ({info.get('device')}, {info.get('used_ip') or 'unknown'},"
                f" {ago} s ago). For safety that sign-in was signed out. If both were you, make a new code; if not, "
                "someone on your network may be copying traffic.")
        return self._refused(request, form, 409, "conflict", "conflict_used", nxt, text=text)

    async def pair_key(self, request: web.Request) -> web.StreamResponse:
        """The recovery-key form (PILOT_KEY_SIGNIN=1 only): a password-manager-friendly form; throttled
        like the words; each use makes a device flagged 'signed in with the recovery key'."""
        if request.headers.get("Origin") is None or request.content_type not in (
                "application/x-www-form-urlencoded", "multipart/form-data"):
            return json_error(403, "origin_required", "The recovery form needs its Origin.", "Use a current browser.")
        body = {k: str(v) for k, v in (await request.post()).items()}
        nxt = safe_next(body.get("next"))
        bucket = bucket_of(request.remote)
        wait = self.throttle.reserve(bucket)
        if wait > 0:
            return self.render(request, 429, "too_many", nxt, wait=max(1, int(wait + 0.999)))
        if not self.keys.matches(body.get("key", "")):
            await asyncio.to_thread(self.store.audit, "signin_failed", request.remote, None, {"how": "recovery_key"})
            return self.render(request, 401, "wrong", nxt)
        self.throttle.refund(bucket)
        ua = request.headers.get("User-Agent", "")
        _, cred = await asyncio.to_thread(self.store.create_device, "browser", name=device_name(ua),
                                          created_via="recovery_key", created_by="recovery_key", ip=request.remote,
                                          user_agent=ua)
        return self._signed_in(request, cred, nxt, form=True)

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

        async def grants_post(request):
            p = need_browser(request)
            if self.add_device == "cli":
                return json_error(403, "cli_only", "Adding devices is limited to the computer that runs Game Pilot.",
                                  "On that computer run: python -m pilot dashboard-link")
            try:
                g = await asyncio.to_thread(self.store.create_grant, p.id, True)
            except GrantLimit as e:
                return json_error(429, "too_many_codes", f"Too many sign-in codes are open: {e}.",
                                  "Cancel a code on another browser, or wait 10 minutes.")
            url = f"{self.link_base(request)}/pair#c={g['link']}"
            return web.json_response({"id": g["id"], "words": g["words"], "link": url, "qr_svg": qr_svg(url),
                                      "expires_at": g["expires_at"], "ttl": GRANT_TTL_S})

        def own_grant(request, p: Principal) -> dict:
            g = self.store.grant(request.match_info["id"])
            if not g or g["created_by"] != p.id:
                raise web.HTTPNotFound(text=json.dumps({"error": "not_found", "reason": "No such code.", "fix": ""}),
                                       content_type="application/json")
            return g

        async def grant_get(request):
            p = need_browser(request)
            g = own_grant(request, p)
            state = "expired" if g["state"] == "waiting" and self.now() > g["expires_at"] else g["state"]
            dev = self.store.device(g["device_id"]) if g.get("device_id") else None
            return web.json_response({"state": state, "expires_at": g["expires_at"], "words_off": g["words_off"],
                                      "ttl": max(0, round(g["expires_at"] - self.now())),
                                      "device": {"id": dev["id"], "name": dev["name"], "ip": dev["created_ip"]} if dev else None})

        async def grant_cancel(request):
            p = need_browser(request)
            own_grant(request, p)
            ok = await asyncio.to_thread(self.store.cancel_grant, request.match_info["id"], p.id)
            return web.json_response({"ok": ok})

        async def log_get(request):
            need_browser(request)
            return web.json_response({"events": await asyncio.to_thread(self.log_rows, 20)})

        async def unlock(request):
            p: Principal = request[PRINCIPAL]
            if p.kind != "service":
                return json_error(403, "service_only", "Only the controller can lift sign-in pauses.",
                                  "On the controller run: python -m pilot dashboard-devices unlock")
            self.throttle.unlock()
            self._wrong_words = 0
            await asyncio.to_thread(self.store.audit, "unlock", request.remote)
            return web.json_response({"ok": True})

        async def signin_js(_):
            return web.FileResponse(STATIC / "signin.js", headers={"Content-Type": "application/javascript"})

        async def favicon(_):
            return web.Response(text=FAVICON, content_type="image/svg+xml")

        routes = [web.get("/pair", self.pair_get), web.post("/pair", self.pair_post),
                  web.get("/static/signin.js", signin_js), web.get("/favicon.svg", favicon),
                  web.get("/api/auth/me", me), web.get("/api/auth/devices", devices),
                  web.post("/api/auth/devices", devices_post), web.post("/api/auth/grants", grants_post),
                  web.get("/api/auth/grants/{id}", grant_get), web.post("/api/auth/grants/{id}/cancel", grant_cancel),
                  web.get("/api/auth/log", log_get), web.post("/api/auth/unlock", unlock)]
        if self.key_signin:
            routes.append(web.post("/pair/key", self.pair_key))
        return routes

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


# ---------------------------------------------------------------- the live pilot's guard

AUTH_VERSION = 1                          # reported in the live pilot's /status as info.auth_version
ACTOR_KEY = web.RequestKey("pilot_actor", tuple)


class ServiceAuth:
    """The live pilot's dashboard (ruling 36): only the service key, only as a header, only from
    loopback, never through a proxy header; no cookies, no sign-in routes, no store. The viewer
    forwards with K and names the device behind a request (X-Pilot-Device, X-Pilot-Device-Name),
    which is believed only alongside K from loopback; a script on the controller is "the controller"."""

    def __init__(self, keys: KeySource, keepalive_s: float = KEEPALIVE_S):
        self.keys, self.keepalive_s = keys, keepalive_s

    @web.middleware
    async def middleware(self, request: web.Request, handler):
        if not allowed_host(request.host or ""):
            return web.Response(status=421, text="Unknown host name.")
        if (refusal := cross_site(request)) is not None:
            return refusal
        given = request.headers.get(KEY_HEADER) or _bearer(request)
        if not given:
            return json_error(401, "sign_in_required", "The live pilot answers only the dashboard viewer and "
                              "scripts on the controller.", "Open the dashboard on port 8780.")
        if not self.keys.matches(given):
            return json_error(401, "bad_token", *REASONS["bad_token"])
        forwarded = "Forwarded" in request.headers or "X-Forwarded-For" in request.headers
        if not is_loopback(request.remote) or forwarded:
            return json_error(401, "service_key_loopback_only", *REASONS["service_key_loopback_only"])
        if request.method not in SAFE_METHODS and request.content_type != "application/json":
            return json_error(403, "json_only", "Requests that change something must be application/json.",
                              "Send JSON with Content-Type: application/json.")
        request[PRINCIPAL] = Principal("service", "service", "the controller", "control", "service",
                                       recheck=lambda: self.keys.matches(given))
        name = request.headers.get(DEVICE_NAME_HEADER)
        by = clip_name(unquote(name), "the controller") if name else "the controller"
        request[ACTOR_KEY] = (by, request.headers.get(DEVICE_HEADER) or None)
        return await handler(request)

    async def on_prepare(self, request: web.Request, response: web.StreamResponse) -> None:
        security_headers(response)

    def still_valid(self, request: web.Request) -> bool:
        p: Principal | None = request.get(PRINCIPAL)
        return bool(p) and p.recheck()

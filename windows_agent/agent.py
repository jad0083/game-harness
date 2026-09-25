"""Remote-control agent for playing a Windows game from another machine.

Runs in the interactive desktop session of the Windows PC and exposes a small
token-protected HTTP API for screenshots and mouse/keyboard input.

Standard library only: screen capture uses GDI via ctypes, input uses
SendInput, and PNG encoding is done with zlib. No pip installs required.

Usage:
    python agent.py [--host 0.0.0.0] [--port 8765] [--allow 192.168.1.10]

The token is read from agent_token.txt next to this file (created with a
random value on first run if missing). Clients send it as
"Authorization: Bearer <token>".
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import struct
import sys
import time
import zlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

VERSION = "0.1.0"
DEFAULT_PORT = 8765
TOKEN_FILE = Path(__file__).with_name("agent_token.txt")

# ---------------------------------------------------------------------------
# Platform-independent helpers (unit-tested on any OS)
# ---------------------------------------------------------------------------


def bgra_to_rgb(bgra: bytes, width: int, height: int) -> bytearray:
    """Convert a top-down 32-bit BGRA buffer into packed 24-bit RGB."""
    n = width * height
    rgb = bytearray(n * 3)
    rgb[0::3] = bgra[2::4]
    rgb[1::3] = bgra[1::4]
    rgb[2::3] = bgra[0::4]
    return rgb


def encode_png(width: int, height: int, rgb: bytes, level: int = 1) -> bytes:
    """Encode packed 8-bit RGB pixels as a PNG (filter type 0 on every row)."""
    stride = width * 3
    view = memoryview(rgb)
    raw = b"".join(b"\x00" + view[i * stride : (i + 1) * stride] for i in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, level))
        + chunk(b"IEND", b"")
    )


# Virtual-key codes. Names are lowercase; aliases share a code.
VK: dict[str, int] = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12, "menu": 0x12,
    "pause": 0x13, "capslock": 0x14, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "pageup": 0x21, "pgup": 0x21, "pagedown": 0x22, "pgdn": 0x22,
    "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "insert": 0x2D, "ins": 0x2D, "delete": 0x2E, "del": 0x2E,
    "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C, "apps": 0x5D,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62, "numpad3": 0x63,
    "numpad4": 0x64, "numpad5": 0x65, "numpad6": 0x66, "numpad7": 0x67,
    "numpad8": 0x68, "numpad9": 0x69, "multiply": 0x6A, "add": 0x6B,
    "subtract": 0x6D, "decimal": 0x6E, "divide": 0x6F,
    "lshift": 0xA0, "rshift": 0xA1, "lctrl": 0xA2, "rctrl": 0xA3, "lalt": 0xA4, "ralt": 0xA5,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF, "`": 0xC0,
    "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
    "plus": 0xBB, "minus": 0xBD, "comma": 0xBC, "period": 0xBE,
}
VK.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})
VK.update({str(d): 0x30 + d for d in range(10)})
VK.update({f"f{i}": 0x6F + i for i in range(1, 25)})

# Keys that need KEYEVENTF_EXTENDEDKEY when sent by scancode.
EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,
    0x5B, 0x5C, 0x5D, 0x6F, 0xA3, 0xA5, 0x2C,
}


def parse_combo(combo: str) -> list[int]:
    """Parse a combo like "ctrl+shift+s" into virtual-key codes, modifiers first.

    A literal "+" key can be written as "plus".
    """
    names = [p.strip().lower() for p in combo.split("+")]
    if not combo.strip() or any(not n for n in names):
        raise ValueError(f"malformed key combo: {combo!r}")
    codes = []
    for name in names:
        if name not in VK:
            raise ValueError(f"unknown key: {name!r}")
        codes.append(VK[name])
    return codes


def load_or_create_token(path: Path = TOKEN_FILE) -> str:
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    path.write_text(token + "\n", encoding="utf-8")
    return token


# ---------------------------------------------------------------------------
# Windows backend
# ---------------------------------------------------------------------------


class WindowsBackend:
    """Screen capture and input injection for the interactive desktop."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.ct = ctypes
        self.wt = wintypes
        self._set_dpi_awareness()

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32, self.gdi32, self.kernel32 = user32, gdi32, kernel32

        ulong_ptr = ctypes.c_size_t

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr),
            ]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

        class _U(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

        self.MOUSEINPUT, self.KEYBDINPUT, self.INPUT = MOUSEINPUT, KEYBDINPUT, INPUT
        self.BITMAPINFO = BITMAPINFO

        # Explicit signatures so 64-bit handles are not truncated to int.
        H = wintypes.HANDLE
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        user32.SendInput.restype = wintypes.UINT
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
        user32.MapVirtualKeyW.restype = wintypes.UINT
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.BringWindowToTop.argtypes = [wintypes.HWND]
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        gdi32.SelectObject.argtypes = [wintypes.HDC, H]
        gdi32.SelectObject.restype = H
        gdi32.BitBlt.argtypes = [wintypes.HDC] + [ctypes.c_int] * 4 + [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
        gdi32.GetDIBits.argtypes = [
            wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
            ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
        ]
        gdi32.DeleteObject.argtypes = [H]
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        kernel32.SetThreadExecutionState.argtypes = [wintypes.DWORD]

        self.WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [self.WNDENUMPROC, wintypes.LPARAM]

    def _set_dpi_awareness(self) -> None:
        # Physical pixels everywhere, so screenshots and clicks share one coordinate space.
        ct = self.ct
        try:
            ct.windll.user32.SetProcessDpiAwarenessContext(ct.c_void_p(-4))  # PER_MONITOR_AWARE_V2
            return
        except (AttributeError, OSError):  # pre-1703 Windows 10
            pass
        try:
            ct.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ct.windll.user32.SetProcessDPIAware()

    def keep_awake(self) -> None:
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2
        self.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)

    # -- screen -------------------------------------------------------------

    def screen_size(self) -> tuple[int, int]:
        return self.user32.GetSystemMetrics(0), self.user32.GetSystemMetrics(1)

    def capture(self, x: int, y: int, w: int, h: int) -> bytes:
        """Return top-down BGRA pixels for a region of the primary screen."""
        ct, u, g = self.ct, self.user32, self.gdi32
        SRCCOPY = 0x00CC0020
        screen_dc = u.GetDC(None)
        mem_dc = g.CreateCompatibleDC(screen_dc)
        bmp = g.CreateCompatibleBitmap(screen_dc, w, h)
        try:
            old = g.SelectObject(mem_dc, bmp)
            if not g.BitBlt(mem_dc, 0, 0, w, h, screen_dc, x, y, SRCCOPY):
                raise OSError(f"BitBlt failed: {ct.get_last_error()}")
            g.SelectObject(mem_dc, old)  # bitmap must be deselected before GetDIBits
            bmi = self.BITMAPINFO()
            hdr = bmi.bmiHeader
            hdr.biSize = ct.sizeof(hdr)
            hdr.biWidth, hdr.biHeight = w, -h  # negative height = top-down rows
            hdr.biPlanes, hdr.biBitCount, hdr.biCompression = 1, 32, 0
            buf = ct.create_string_buffer(w * h * 4)
            if g.GetDIBits(mem_dc, bmp, 0, h, buf, ct.byref(bmi), 0) != h:
                raise OSError(f"GetDIBits failed: {ct.get_last_error()}")
            return buf.raw
        finally:
            g.DeleteObject(bmp)
            g.DeleteDC(mem_dc)
            u.ReleaseDC(None, screen_dc)

    # -- input --------------------------------------------------------------

    def _send(self, *inputs) -> None:
        arr = (self.INPUT * len(inputs))(*inputs)
        sent = self.user32.SendInput(len(inputs), arr, self.ct.sizeof(self.INPUT))
        if sent != len(inputs):
            raise OSError(
                f"SendInput injected {sent}/{len(inputs)} events (error {self.ct.get_last_error()}); "
                "the target may be elevated or the desktop locked"
            )

    def _mouse(self, flags: int, dx: int = 0, dy: int = 0, data: int = 0):
        inp = self.INPUT(type=0)
        inp.mi = self.MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
        return inp

    def _key(self, vk: int, up: bool):
        KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8
        scan = self.user32.MapVirtualKeyW(vk, 0)
        flags = KEYEVENTF_SCANCODE if scan else 0
        if vk in EXTENDED_VKS:
            flags |= KEYEVENTF_EXTENDEDKEY
        if up:
            flags |= KEYEVENTF_KEYUP
        inp = self.INPUT(type=1)
        inp.ki = self.KEYBDINPUT(vk, scan, flags, 0, 0)
        return inp

    def move(self, x: int, y: int) -> None:
        MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE = 0x0001, 0x8000
        w, h = self.screen_size()
        nx = round(x * 65535 / max(w - 1, 1))
        ny = round(y * 65535 / max(h - 1, 1))
        # Absolute SendInput produces real move events (hover/raw input);
        # SetCursorPos then pins the exact pixel.
        self._send(self._mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, nx, ny))
        self.user32.SetCursorPos(x, y)

    BUTTONS: ClassVar[dict[str, tuple[int, int]]] = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}

    def button(self, button: str, down: bool) -> None:
        flags = self.BUTTONS[button][0 if down else 1]
        self._send(self._mouse(flags))

    def scroll(self, clicks: int) -> None:
        MOUSEEVENTF_WHEEL = 0x0800
        self._send(self._mouse(MOUSEEVENTF_WHEEL, data=120 * clicks))

    def key(self, vk: int, down: bool) -> None:
        self._send(self._key(vk, up=not down))

    def type_text(self, text: str) -> None:
        KEYEVENTF_UNICODE, KEYEVENTF_KEYUP = 0x4, 0x2
        units = struct.unpack(f"<{len(text.encode('utf-16-le')) // 2}H", text.encode("utf-16-le"))
        for unit in units:
            for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                inp = self.INPUT(type=1)
                inp.ki = self.KEYBDINPUT(0, unit, flags, 0, 0)
                self._send(inp)
            time.sleep(0.01)

    # -- windows ------------------------------------------------------------

    def _enum_windows(self) -> list[tuple[int, str]]:
        found: list[tuple[int, str]] = []
        u = self.user32

        def cb(hwnd, _lparam):
            if u.IsWindowVisible(hwnd):
                n = u.GetWindowTextLengthW(hwnd)
                if n:
                    buf = self.ct.create_unicode_buffer(n + 1)
                    u.GetWindowTextW(hwnd, buf, n + 1)
                    found.append((hwnd, buf.value))
            return True

        u.EnumWindows(self.WNDENUMPROC(cb), 0)
        return found

    def list_windows(self) -> list[dict]:
        fg = self.user32.GetForegroundWindow()
        out = []
        for hwnd, title in self._enum_windows():
            r = self.wt.RECT()
            self.user32.GetWindowRect(hwnd, self.ct.byref(r))
            out.append({
                "title": title, "foreground": hwnd == fg,
                "rect": [r.left, r.top, r.right - r.left, r.bottom - r.top],
            })
        return out

    def foreground_title(self) -> str:
        hwnd = self.user32.GetForegroundWindow()
        n = self.user32.GetWindowTextLengthW(hwnd)
        buf = self.ct.create_unicode_buffer(n + 1)
        self.user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def focus(self, title_substring: str) -> str:
        needle = title_substring.lower()
        matches = [(h, t) for h, t in self._enum_windows() if needle in t.lower()]
        if not matches:
            raise LookupError(f"no visible window title contains {title_substring!r}")
        hwnd, title = matches[0]
        u = self.user32
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 9)  # SW_RESTORE
        # Tapping Alt lifts Windows' foreground-lock so SetForegroundWindow is honoured.
        self.key(VK["alt"], True)
        self.key(VK["alt"], False)
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
        return title


# ---------------------------------------------------------------------------
# Controller: validated high-level actions on top of a backend
# ---------------------------------------------------------------------------


class Controller:
    def __init__(self, backend, delay: float = 0.05) -> None:
        self.b = backend
        self.delay = delay

    def _check_point(self, x: int, y: int) -> None:
        w, h = self.b.screen_size()
        if not (0 <= x < w and 0 <= y < h):
            raise ValueError(f"point ({x}, {y}) is outside the {w}x{h} screen")

    def health(self) -> dict:
        w, h = self.b.screen_size()
        return {"ok": True, "version": VERSION, "screen": [w, h], "foreground": self.b.foreground_title()}

    def screenshot(self, x: int = 0, y: int = 0, w: int | None = None, h: int | None = None) -> tuple[bytes, int, int]:
        sw, sh = self.b.screen_size()
        w = sw - x if w is None else w
        h = sh - y if h is None else h
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > sw or y + h > sh:
            raise ValueError(f"region {x},{y} {w}x{h} is outside the {sw}x{sh} screen")
        bgra = self.b.capture(x, y, w, h)
        return encode_png(w, h, bgra_to_rgb(bgra, w, h)), w, h

    def move(self, x: int, y: int) -> None:
        self._check_point(x, y)
        self.b.move(x, y)

    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> None:
        if button not in ("left", "right", "middle"):
            raise ValueError(f"unknown button: {button!r}")
        if not 1 <= count <= 3:
            raise ValueError("count must be 1-3")
        self.move(x, y)
        time.sleep(self.delay)
        for _ in range(count):
            self.b.button(button, True)
            time.sleep(self.delay)
            self.b.button(button, False)
            time.sleep(self.delay)

    def drag(self, x1: int, y1: int, x2: int, y2: int, button: str = "left", steps: int = 12) -> None:
        self._check_point(x1, y1)
        self._check_point(x2, y2)
        self.b.move(x1, y1)
        time.sleep(self.delay)
        self.b.button(button, True)
        try:
            for i in range(1, steps + 1):
                self.b.move(round(x1 + (x2 - x1) * i / steps), round(y1 + (y2 - y1) * i / steps))
                time.sleep(0.02)
            time.sleep(self.delay)
        finally:
            self.b.button(button, False)

    def scroll(self, x: int, y: int, clicks: int) -> None:
        self.move(x, y)
        time.sleep(self.delay)
        self.b.scroll(clicks)

    def key(self, combo: str, repeat: int = 1) -> None:
        codes = parse_combo(combo)
        if not 1 <= repeat <= 50:
            raise ValueError("repeat must be 1-50")
        for _ in range(repeat):
            pressed = []
            try:
                for vk in codes:
                    self.b.key(vk, True)
                    pressed.append(vk)
                    time.sleep(0.02)
                time.sleep(self.delay)
            finally:
                for vk in reversed(pressed):
                    self.b.key(vk, False)
                    time.sleep(0.02)
            time.sleep(self.delay)

    def type_text(self, text: str) -> None:
        if len(text) > 500:
            raise ValueError("text too long (max 500 chars)")
        self.b.type_text(text)

    def windows(self) -> list[dict]:
        return self.b.list_windows()

    def focus(self, title: str) -> str:
        return self.b.focus(title)


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


def make_handler(controller: Controller, token: str, allow: set[str] | None = None):
    def _int(body: dict, key: str, default=None) -> int:
        if key not in body:
            if default is None:
                raise ValueError(f"missing field: {key}")
            return default
        return int(body[key])

    posts = {
        "/move": lambda b: controller.move(_int(b, "x"), _int(b, "y")),
        "/click": lambda b: controller.click(_int(b, "x"), _int(b, "y"), b.get("button", "left"), _int(b, "count", 1)),
        "/drag": lambda b: controller.drag(
            _int(b, "x1"), _int(b, "y1"), _int(b, "x2"), _int(b, "y2"), b.get("button", "left")
        ),
        "/scroll": lambda b: controller.scroll(_int(b, "x"), _int(b, "y"), _int(b, "clicks")),
        "/key": lambda b: controller.key(str(b["combo"]), _int(b, "repeat", 1)),
        "/type": lambda b: controller.type_text(str(b["text"])),
        "/focus": lambda b: {"focused": controller.focus(str(b["title"]))},
    }

    class Handler(BaseHTTPRequestHandler):
        server_version = f"GameAgent/{VERSION}"

        def log_message(self, fmt, *args):  # quieter, single-line log
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} {self.client_address[0]} {fmt % args}\n")

        def _reply(self, status: int, payload: dict | None = None, body: bytes | None = None,
                   ctype: str = "application/json", headers: dict | None = None) -> None:
            if body is None:
                body = json.dumps(payload or {}).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (headers or {}).items():
                self.send_header(k, str(v))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if allow and self.client_address[0] not in allow:
                self._reply(403, {"error": "client address not allowed"})
                return False
            got = self.headers.get("Authorization", "")
            if not hmac.compare_digest(got.encode(), f"Bearer {token}".encode()):
                self._reply(401, {"error": "bad or missing token"})
                return False
            return True

        def _run(self, fn) -> None:
            try:
                fn()
            except (ValueError, KeyError, TypeError, LookupError) as e:
                self._reply(400, {"error": f"{type(e).__name__}: {e}"})
            except Exception as e:  # noqa: BLE001 - surface backend failures to the client
                self._reply(500, {"error": f"{type(e).__name__}: {e}"})

        def do_GET(self):
            if not self._authorized():
                return
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}

            def go():
                if url.path == "/health":
                    self._reply(200, controller.health())
                elif url.path == "/screenshot":
                    args = {k: int(q[k]) for k in ("x", "y", "w", "h") if k in q}
                    png, w, h = controller.screenshot(**args)
                    self._reply(200, body=png, ctype="image/png",
                                headers={"X-Width": w, "X-Height": h})
                elif url.path == "/windows":
                    self._reply(200, {"windows": controller.windows()})
                else:
                    self._reply(404, {"error": f"no route {url.path}"})

            self._run(go)

        def do_POST(self):
            if not self._authorized():
                return
            path = urlparse(self.path).path
            if path not in posts:
                self._reply(404, {"error": f"no route {path}"})
                return

            def go():
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise TypeError("body must be a JSON object")
                result = posts[path](body)
                self._reply(200, {"ok": True, **(result or {})})

            self._run(go)

    return Handler


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--allow", action="append", help="only accept these client IPs (repeatable)")
    args = ap.parse_args(argv)

    if sys.platform != "win32":
        sys.exit("agent.py must run on Windows, inside the logged-in desktop session")

    token = load_or_create_token()
    backend = WindowsBackend()
    backend.keep_awake()
    controller = Controller(backend)
    server = HTTPServer((args.host, args.port), make_handler(controller, token, set(args.allow or [])))
    w, h = backend.screen_size()
    print(f"game agent {VERSION} listening on {args.host}:{args.port} (screen {w}x{h})", flush=True)
    print(f"token file: {TOKEN_FILE}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    # pythonw has no console; keep a log next to the script instead.
    if sys.stderr is None or os.path.basename(sys.executable).lower() == "pythonw.exe":
        log = open(Path(__file__).with_name("agent.log"), "a", buffering=1, encoding="utf-8")  # noqa: SIM115 - lives for the process
        sys.stdout = sys.stderr = log
    main()

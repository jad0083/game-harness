"""Machine text cut to its cause, for the dashboard and the attention card (docs/design/
2026-09-27-dashboard-v2-design.md, ruling 30): an error chain becomes one line a person can act on,
and the raw text stays one disclosure away. Pure functions, no game or model calls."""

from __future__ import annotations

import re

_TYPE = re.compile(r"^(?:[\w.]+\.)?[A-Z]\w*(?:Error|Exception|Stuck|Timeout|Refused|Busy|Limit\w*)\s*:\s*")
_STATUS = re.compile(r"(?:status_code|status|answered|HTTP)\W{0,3}(\d{3})\b", re.IGNORECASE)
_CAUSED = re.compile(r"^\s*\d+:\s*(.+?)\s*$", re.MULTILINE)


def _first_line(text: str) -> str:
    line = next((x.strip() for x in text.splitlines() if x.strip()), "")
    line = _TYPE.sub("", line)
    line = re.sub(r"-?\d+\.\d{3,}", lambda m: f"{float(m.group()):.1f}", line)
    return line[:160].rstrip(" .;:,")


def cause(text) -> str:
    """One line for an error: "overloaded (503)", "the game's tuner did not answer (timed out)",
    "billing: credit balance too low"; an unknown chain gives its last "Caused by" line, anything
    else its first line without the exception's type."""
    t = str(text or "").strip()
    if not t:
        return ""
    low = t.lower()
    if "credit balance" in low:
        return "billing: credit balance too low"
    m = _STATUS.search(t)
    code = m.group(1) if m else ""
    if code == "503" or "high demand" in low or "overloaded" in low or "unavailable" in low and code == "":
        return "overloaded (503)"
    if code == "429" or "rate limit" in low or "resource_exhausted" in low or "quota" in low:
        return "rate limited (429)"
    if code in ("401", "403") or "api key" in low and ("invalid" in low or "not valid" in low):
        return f"the provider refused the key ({code or 401})"
    timed_out = "timed out" in low or "timeout" in low or "deadline exceeded" in low
    if "/tuner/" in low or "tuner" in low and timed_out:
        return "the game's tuner did not answer (timed out)" if timed_out else \
            "the game's tuner refused the call: " + (_CAUSED.findall(t) or [_first_line(t)])[-1][:120]
    if "connection refused" in low:
        return "the PC's agent refused the connection (is it running?)"
    if timed_out and ("urlopen" in low or "agent" in low or "8765" in low):
        return "the PC's agent did not answer (timed out)"
    caused = _CAUSED.findall(t) if "caused by" in low else []
    if caused:
        return caused[-1][:160].rstrip(" .")
    if timed_out and not _first_line(t):
        return "no answer in time (timed out)"
    return _first_line(t) or "no answer in time (timed out)"


ERROR_KINDS = ("briefing_error", "episode_error", "recover_probe", "model_fallback")


def attention(reason: str, category: str, recent, *, date: str = "", auto_recover: bool = False,
              next_probe_at: float | None = None, frame: str = "", now: float | None = None) -> dict:
    """`info.attention` for a run that needs the human (ruling 7): why (the governor's sentence), the
    category its recovery steps are looked up by (`view.CATEGORIES`, set at each call site; nothing
    parses the text), since when, the game date then, whether it retries by itself (and when next),
    and the last three errors of the quarter hour before it, cut to their cause, with their raw text."""
    import time
    now = time.time() if now is None else now
    raw = [str(e.get("error") or "")[:500] for e in recent
           if e.get("kind") in ERROR_KINDS and e.get("t", 0) >= now - 900 and e.get("error")][-3:]
    causes: list[str] = []
    for r in raw:
        c = cause(r)
        if c and c not in causes:
            causes.append(c)
    return {"reason": reason[:500], "category": category, "since": round(now, 1), "date": date, "date_now": date,
            "auto_recover": auto_recover, "next_probe_at": next_probe_at, "probes": 0, "errors": causes,
            "raw": raw, "frame": frame}

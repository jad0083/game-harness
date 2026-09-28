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
    if timed_out:
        return "no answer in time (timed out)"
    return _first_line(t)


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


# ---- triggers (ruling 28): war, city threatened, city lost, race lost, milestone missed, gold below
# the reserve, scheduled; raw ids become names -------------------------------------------------------

_TRIGGERS = [  # (pattern on one urgent reason, category, words; {1} = the first group, named)
    (r"^city (?:threatened): ([^(]+?)\s*(?:\(|$)", "city threatened", "City threatened: {1}"),
    (r"^city falling: ([^(]+?)\s*(?:\(|$)", "city threatened", "City falling: {1}"),
    (r"^city lost: (.+)$", "city lost", "City lost: {1}"),
    (r"^colony lost\b", "city lost", "Colony lost"),
    (r"^new war: (.+?)(?: is at war with us| \(we are \w+\))?$", "war", "War: {1}"),
    (r"^war ended: (.+)$", "war", "Peace: {1}"),
    (r"^great person race lost: (\S+)", "race lost", "{1} race lost"),
    (r"^wonder race lost: (\S+)", "race lost", "{1} race lost"),
    (r"^milestone missed: (\S+)", "milestone missed", "Milestone missed: {1}"),
    (r"^gold below the reserve\b", "gold below reserve", "Gold below the reserve"),
    (r"^military fell\b", "military fell", "Military fell"),
    (r"^falling behind other empires in (\S+)", "falling behind", "Falling behind in {1}"),
    (r"^(\w+) net turned negative\b", "deficit", "{1} income negative"),
    (r"^crisis: (.+?) \(", "crisis", "Crisis: {1}"),
    (r"^new era: (.+)$", "new era", "New era: {1}"),
    (r"^boxed in\b", "boxed in", "Boxed in"),
    (r"^off-frame decision\b", "off frame", "Off the strategy's frame"),
]


def trigger(raw, name=None) -> dict:
    """{category, text, urgent, more}: "urgent: city threatened: Chengdu (2 enemy units near); gold
    below the reserve: 12 < 30" -> city threatened, "City threatened: Chengdu, and 1 more". `name`
    turns an id into its name (GREAT_PERSON_CLASS_SCIENTIST -> Great Scientist)."""
    from .view import fallback_name
    text = str(raw or "").strip()
    urgent = text.startswith("urgent:")
    reasons = [r.strip() for r in text.removeprefix("urgent:").split(";") if r.strip()] if urgent else [text]
    first = reasons[0] if reasons else ""
    low = first.lower()
    if low.startswith("scheduled"):
        cat, words = "scheduled", "Scheduled"
    elif low.startswith("start of run"):
        cat, words = "start", "Start of run"
    elif low.startswith("human request"):
        cat, words = "you", "Your request"
    elif low.startswith("human override"):
        cat, words = "you", "Your override"
    else:
        cat, words = "other", first[:1].upper() + first[1:80]
        for pattern, c, w in _TRIGGERS:
            m = re.search(pattern, first, re.IGNORECASE)
            if m:
                arg = m.group(1).strip() if m.groups() else ""
                if re.fullmatch(r"[A-Z][A-Z0-9_]+", arg):
                    arg = (name(arg) if name else None) or fallback_name(arg)
                words = w.replace("{1}", arg)
                words = words[:1].upper() + words[1:]
                cat = c
                break
    more = len(reasons) - 1
    return {"category": cat, "text": words + (f", and {more} more" if more > 0 else ""), "urgent": urgent,
            "more": max(0, more), "reasons": reasons}


# ---- order fates (ruling 28): the only pills; a symbol and words, never colour alone -------------------

FATES = {  # key: (symbol, word)
    "held": ("✓", "held"), "replaced": ("↺", "replaced by the AI"), "refused": ("✕", "refused"),
    "noreply": ("?", "no reply"), "open": ("⋯", "in force"), "gone": ("–", "no longer in force"),
}
_RESULT = {"completed": ("held", "completed"), "held": ("held", "held"), "took": ("held", "took"),
           "overridden": ("replaced", "replaced by the AI"), "did_not_take": ("refused", "did not take"),
           "refused": ("refused", "refused"), "lost": ("noreply", "no reply"), "unknown": ("noreply", "cannot tell"),
           "invalidated": ("gone", "no longer available"), "superseded": ("gone", "replaced by our own order"),
           # Stellaris's action record (stellaris_record.py)
           "researched": ("held", "researched"), "did_not_stick": ("refused", "did not stick"),
           "failed": ("refused", "failed"), "removed": ("replaced", "removed by the AI"),
           "locked": ("gone", "locked by the game"), "no_op": ("gone", "nothing to do"), "done": ("held", "done")}


def fate(apply_outcome, result=None, *, kind: str = "", by: str = "", detail: str = "", followed: bool = True) -> dict:
    """An order's fate: {key, symbol, word, why}. `apply_outcome` is what the decision's trace says
    when the order was sent ("stuck", "refused: …", "unknown: no reply …"); `result` the order
    record's later outcome, if any (completed, held, overridden, refused, lost, unknown, ...);
    `followed` whether the record still follows it: a stuck order nobody follows (a trace from before
    the order record) took, and is not "in force" for ever."""
    out = str(apply_outcome or "")
    why = ""
    if result in _RESULT:
        key, word = _RESULT[result]
        if result == "overridden" and by:
            why = f"the AI chose {by}"
        elif result == "refused" and detail:
            why = re.sub(r"^refused(?: by the game)?:\s*", "", str(detail))
        elif detail:
            why = cause(detail)
    elif out == "stuck":
        key, word = (("held", "completed") if kind == "purchase" else ("open", "in force") if followed
                     else ("held", "took, not followed"))
    elif out.startswith("refused"):
        key, word, why = "refused", "refused", re.sub(r"^refused(?: by the game)?:\s*", "", out)
    elif out.startswith("unknown"):
        key, word = "noreply", ("no reply" if "no reply" in out else "cannot tell")
        why = cause(out.removeprefix("unknown:").strip()) if "no reply" in out else ""
    else:
        key, word, why = "refused", "did not stick", out
    return {"key": key, "symbol": FATES[key][0], "word": word, "why": why[:200],
            "by": by if result == "overridden" else ""}


_ORDER_TEXT = re.compile(r"^(?P<kind>research|civic|production|purchase|policies) (?P<id>.+?)(?: in (?P<city>.+?))?"
                         r"(?: with (?P<currency>gold|faith))?(?: \((?P<note>.*)\))?$")


def order_parts(o: dict) -> dict:
    """kind, id, city, currency of a decision's order: the trace's fields, or (traces written before
    the order record) parsed from its text ("purchase unit:slinger in Chengdu with faith")."""
    text = str(o.get("order") or "")
    m = _ORDER_TEXT.match(text.replace(" (filled by the governor)", ""))
    parsed = m.groupdict() if m else {}
    kind = o.get("kind") or parsed.get("kind") or ""
    ident = o.get("id") or parsed.get("id") or ""
    if kind == "policies" and not o.get("id"):
        ident = parsed.get("id") or ""
    return {"kind": kind, "id": ident, "city": o.get("city") or parsed.get("city") or "",
            "currency": parsed.get("currency") or ("faith" if " with faith" in text else "gold" if kind == "purchase" else ""),
            "filled": o.get("by") == "governor" or "(filled by the governor)" in text}


_RETRY_MODEL = re.compile(r"model (\S+) answered (\d{3})")


def attempts(events: list[dict]) -> list[dict]:
    """The model calls before an answer, from model_retry and model_fallback events: [{model, cause,
    times}] in order ("Gemini 3.8 Flash overloaded (503) x3, then 3.7 Flash overloaded")."""
    out: list[dict] = []
    for e in events:
        if e.get("kind") == "model_retry":
            m = _RETRY_MODEL.search(str(e.get("error") or ""))
            model, why = (m.group(1), cause(e.get("error"))) if m else ("", cause(e.get("error")))
        elif e.get("kind") == "model_fallback" and e.get("role", "decisions") == "decisions":
            model, why = str(e.get("model") or ""), cause(e.get("error"))
        else:
            continue
        last = out[-1] if out else None
        if last and (last["model"] == model or (not model or model.endswith(":" + last["model"]) or
                                                 last["model"].endswith(":" + model) or last["model"].endswith(model))) \
                and last["cause"] == why:
            last["times"] += 1
            if ":" in model:
                last["model"] = model
        else:
            out.append({"model": model, "cause": why, "times": 1})
    return out


# the order record's keys in words (ruling 19)
RECORD_LABELS = {"research": "Research", "civic": "Civics", "policies": "Policy cards",
                 "production fill": "Production, fill an empty queue", "production replace": "Production, replace the AI's choice",
                 "production unknown": "Production (from older decisions)", "purchase gold": "Purchase with gold",
                 "purchase faith": "Purchase with faith", "stand city_strike": "Last stand: city strike",
                 "stand ranged": "Last stand: ranged attack", "stand retreat": "Last stand: retreat",
                 "stand pin": "Last stand: hold in place"}


# Stellaris action-record keys (docs/design/2026-09-27-stellaris-levers-design.md, ruling 2): "directive
# <name>", "market buy|sell <resource>", "posture <name>", "crisis <step>", "tech"
POSTURE_WORDS = {"naval_cap": "naval capacity", "research_focus": "research focus", "ship_upgrades": "ship upgrades",
                 "war_crisis": "war crisis"}


def record_label(key: str) -> str:
    if key in RECORD_LABELS:
        return RECORD_LABELS[key]
    head, _, rest = key.partition(" ")
    words = rest.replace("_", " ")
    if head == "directive" and rest:
        return f"Directive: {words[:1].upper()}{words[1:]}"
    if head == "market" and rest:
        return f"Market: {words}"
    if head == "posture" and rest:
        return f"Posture: {POSTURE_WORDS.get(rest, words)}"
    if head == "crisis" and rest:
        return f"War crisis: {words}"
    if key == "tech":
        return "Tech picks"
    return key[:1].upper() + key[1:]

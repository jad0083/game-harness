"""The Stellaris action record (docs/design/2026-09-27-stellaris-levers-design.md, rulings 2-6).

Sending an order is not the outcome: every directive, tech pick, market order and posture the
governor sends is followed in the monthly autosaves until it resolves, and each resolution becomes
one `order_outcome` row (the Civ VI row shape, so both games share `record.order_record`).

| Key | Succeeded | Failed | Not judged |
|---|---|---|---|
| `directive <name>` | `took` (flag in the next save and nothing set to follow), `held` (every policy the game reported set still reads back at our next directive or after `open_cap_turns`) | `failed` (no flag in the next save), `overridden` (a reported policy reads back another option dated on or after our apply) | `superseded` (our next directive before a save), `locked` (the game set none of its policies) |
| `tech` | `researched` (gone from current and offered), `held` (still researched at the next review or after the cap) | `did_not_stick` (still offered, not researched), `failed` (the tool failed) | `no_op` ("nothing to pick") |
| `market <side> <resource>` | `took` (a removal gone in the next save; a buy in the list that trades nothing in 2 saves, by "not executing"), `held` (present at our next change or after the cap) | `did_not_take` (the next save differs), `removed` (gone later without our sync), `failed` (the tool failed) | `superseded` |
| `posture <name>` | `took` (flag as sent in the next save) | `did_not_take` | `superseded` |
| `crisis <step>` | a crisis `defend`, `posture` or `market` step as its kind | as its kind | `done` (review, need boost, cadence, status-quo question), `no_op` (skipped, with why) |

Pure: actions are plain dicts (persisted as `order_followed` events); `judge` updates an action's
`state` and says whether it resolved."""

from __future__ import annotations

import re
import uuid

from .record import order_record

SUCCEEDED = ("took", "held", "researched")
FAILED = ("overridden", "did_not_take", "failed", "did_not_stick", "removed")
JUDGED = SUCCEEDED + FAILED
EXCLUDED = ("superseded", "locked", "no_op", "done")    # done: a war crisis step with nothing to judge
KIND_ORDER = ("directive", "tech", "market", "posture", "crisis")
OPEN = "open"

LABELS = {"took": "took", "held": "held", "researched": "researched", "overridden": "overridden by the AI",
          "did_not_take": "did not take", "failed": "failed", "did_not_stick": "did not stick",
          "removed": "removed by the AI"}

# the controller's directive reply (stellaris.rs Applied::summary, mcp.rs stellaris_directive)
_SET_RE = re.compile(r"Policies set: ([^.\n]*)\.")
_IN_FORCE_RE = re.compile(r"Already in force \([^)]*\): ([^.\n]*)\.")
_LOCKED_RE = re.compile(r"Policies locked \([^)]*\): ([^.\n]*)\.")
_POSTURE_RE = re.compile(r"\bset_country_flag = governor_posture_([a-z0-9_]+)")
# stellaris_pick_tech's reply when no preferred tech was offered where it could click
NO_OP_PREFIX = "nothing to pick"


def _months(date: str) -> int:
    y, m, *_ = (int(x) for x in date.split("."))
    return y * 12 + m - 1


def _day(date: str) -> tuple[int, ...]:
    return tuple(int(x) for x in date.split("."))


def _pairs(m: re.Match | None) -> dict[str, str]:
    text = m.group(1).strip() if m else ""
    if not text or text == "none":
        return {}
    return dict(x.strip().split("=", 1) for x in text.split(",") if "=" in x)


def parse_directive_reply(reply: str) -> dict:
    """What a directive's reply says the game did: the policies it `set` (a GOVERNOR_POLICY marker),
    those already `in_force` (not sent), those `locked` (no marker), and the postures its console
    lines set. `reported` is False for a reply without the policy sentence (an older controller)."""
    m = _SET_RE.search(reply or "")
    return {"set": _pairs(m), "in_force": _pairs(_IN_FORCE_RE.search(reply or "")),
            "locked": _pairs(_LOCKED_RE.search(reply or "")), "reported": m is not None,
            "postures": list(dict.fromkeys(_POSTURE_RE.findall(reply or "")))}


def _action(kind: str, key: str, ident: str, date: str, expect: dict, **extra) -> dict:
    return {"ref": uuid.uuid4().hex[:16], "kind": kind, "key": key, "id": ident, "ordered": date, "state": "sent",
            "expect": expect, **extra}


def directive_action(name: str, date: str, info: dict) -> dict:
    """A directive applied on the save of `date`; `info` from `parse_directive_reply`."""
    return _action("directive", f"directive {name}", name, date,
                   {"flag": f"governor_directive_{name}", "set": dict(info.get("set") or {}),
                    "locked": dict(info.get("locked") or {}), "in_force": dict(info.get("in_force") or {})})


def tech_action(tech: str, field: str, date: str) -> dict:
    return _action("tech", "tech", tech, date, {"tech": tech, "field": field})


def market_action(order: dict, date: str, calibration: str, *, key: str | None = None, **extra) -> dict:
    """A monthly trade set to `order["amount"]` (0: removed) on the save of `date`; `calibration`
    is the hash of the `[ui.market]` positions it was clicked with (ruling 6). `key` names a war
    crisis step ("crisis market buy alloys"), judged as any market order; `extra` is kept with it
    (e.g. `auto`: the idle-trade fill)."""
    side, res, amount = order["side"], order["resource"], int(order.get("amount") or 0)
    return _action("market", key or f"market {side} {res}", f"{side} {res} {amount}", date,
                   {"side": side, "resource": res, "amount": amount}, calibration=calibration, **extra)


def crisis_action(step: str, date: str) -> dict:
    """A war crisis step with nothing to follow (the review, the need boost, the cadence, the
    status-quo question, or a step skipped with its reason): resolved at once."""
    return _action("crisis", f"crisis {step}", step, date, {})


def posture_action(name: str, on: bool, date: str) -> dict:
    return _action("posture", f"posture {name}", name, date, {"flag": f"governor_posture_{name}", "on": bool(on)})


def judge(a: dict, b: dict, cap: int, grace: int) -> tuple[str, str | None, str]:
    """Where action `a` stands in save `b`: (OPEN, None, "") while undecided, else (result, what the
    game shows instead, detail). Never judged on a save less than max(1, `grace`) months after the
    order; `held` once followed `cap` months. Updates `a["state"]` ("took" / "current" once seen)."""
    date = str(b.get("date") or "")
    if not date:
        return OPEN, None, ""
    elapsed = _months(date) - _months(a["ordered"])
    if elapsed < max(1, grace):
        return OPEN, None, ""
    verdict = {"directive": _judge_directive, "tech": _judge_tech, "market": _judge_market,
               "posture": _judge_posture}[a["kind"]](a, b, date)
    if verdict[0] != OPEN or a["state"] == "sent":
        return verdict
    if elapsed >= cap:
        return "held", None, f"followed {elapsed} months to {date}" + _last_trade(a)
    return verdict


def _judge_directive(a: dict, b: dict, date: str) -> tuple[str, str | None, str]:
    e = a["expect"]
    if a["state"] == "sent" and e["flag"] not in (b.get("flags") or []):
        return "failed", None, f"no {e['flag']} flag in the save of {date}"
    policies = b.get("policies")
    for p, o in e["set"].items() if isinstance(policies, dict) else ():
        now = policies.get(p)
        if now is None or now == o:
            continue
        when = (b.get("policy_dates") or {}).get(p)
        if when and _day(when) >= _day(a["ordered"]):
            return "overridden", now, f"{p} → {now} on {when}"
        if a["state"] == "sent":
            return "failed", now, f"{p} reads {now}, not {o}, in the save of {date}"
        return "overridden", now, f"{p} → {now} (no date)"
    if a["state"] == "sent":
        a["state"] = "took"
        if not e["set"]:          # nothing the AI could revert: the flag was all that was sent
            if e["locked"]:
                return "locked", None, "not set: " + ", ".join(f"{p}={o}" for p, o in e["locked"].items())
            return "took", None, f"flag in the save of {date}"
    return OPEN, None, ""


def _judge_tech(a: dict, b: dict, date: str) -> tuple[str, str | None, str]:
    research = b.get("research")
    if not isinstance(research, dict) or not research:
        return OPEN, None, ""                                   # cannot tell
    current: dict[str, str] = {}
    offered: dict[str, str] = {}
    for fld, r in research.items():
        cur = (r or {}).get("current")
        if isinstance(cur, (list, tuple)) and cur:
            current[str(cur[0])] = fld
        for t in (r or {}).get("alternatives") or []:
            offered[t] = fld
    tech = a["expect"]["tech"]
    if tech in current:
        a["state"] = "current"
        return OPEN, None, ""
    if tech in offered:
        fld = offered[tech]
        by = next((t for t, f in current.items() if f == fld), None)
        return "did_not_stick", by, f"{tech} still offered in {fld}, {by or 'nothing'} researched there ({date})"
    return "researched", None, f"{tech} researched by {date}"


def _judge_market(a: dict, b: dict, date: str) -> tuple[str, str | None, str]:
    orders = b.get("market_orders")
    if not isinstance(orders, list):
        return OPEN, None, ""
    e = a["expect"]
    side, res, want = e["side"], e["resource"], e["amount"]
    mine = [o for o in orders if (o.get("side"), o.get("resource")) == (side, res)]
    now = int(mine[0].get("amount") or 0) if mine else 0
    if a["state"] == "sent":
        if now != want:
            return ("did_not_take", str(now) if now else None,
                    f"wanted {side} {res} {want}, the save of {date} has {now or 'none'}")
        if want == 0:
            return "took", None, f"{side} {res} removed by {date}"
        a["state"] = "took"
        return OPEN, None, ""
    if now != want:
        return ("removed", str(now) if now else None,
                f"{side} {res} {want} {'gone' if not now else f'now {now}'} in the save of {date}")
    return _judge_trading(a, b, date)


# a buy in the order list with no trade in this many saves after the one that first showed it is
# recorded `took` by "not executing" (ruling 10)
DRY_SAVES = 2


def _judge_trading(a: dict, b: dict, date: str) -> tuple[str, str | None, str]:
    """Ruling 10: `net` leaves market trades out, so whether a buy in the order list trades shows only in
    `market.trades_net` (last month's monthly trades). A buy with none of its resource bought in
    DRY_SAVES saves after the one that first showed it resolves as `took` by "not executing"; without
    a market block the check is the order list alone."""
    e = a["expect"]
    market = b.get("market")
    trades = market.get("trades_net") if isinstance(market, dict) else None
    if e["side"] != "buy" or not e["amount"] or not isinstance(trades, dict) or a.get("traded_on") == date:
        return OPEN, None, ""       # the same save again (a restart reads it anew) is not a second save
    a["traded_on"] = date
    got = float(trades.get(e["resource"]) or 0.0)
    if got > 0:
        a["dry"] = 0
        a["last_trade"] = f"+{got:g} {e['resource']} for {max(0.0, -float(trades.get('trade') or 0.0)):g} trade"
        return OPEN, None, ""
    a["dry"] = a.get("dry", 0) + 1
    if a["dry"] >= DRY_SAVES:
        detail = (f"buy {e['resource']} {e['amount']} is in the order list but no {e['resource']} bought in the "
                  f"monthly trades of {a['dry']} saves to {date}")
        return "took", "not executing", detail
    return OPEN, None, ""


def _last_trade(a: dict) -> str:
    return f"; last month {a['last_trade']}" if a.get("last_trade") else ""


def _judge_posture(a: dict, b: dict, date: str) -> tuple[str, str | None, str]:
    e = a["expect"]
    present = e["flag"] in (b.get("flags") or [])
    if present == e["on"]:
        return "took", None, f"{e['flag']} {'set' if e['on'] else 'cleared'} in the save of {date}"
    return "did_not_take", None, f"{e['flag']} {'missing from' if e['on'] else 'still in'} the save of {date}"


def supersede(a: dict) -> tuple[str, str]:
    """Our own next order of the same kind replaced `a`: `held` once it was seen in force, else
    `superseded` (never judged)."""
    if a["state"] in ("took", "current"):
        return "held", "in force until our next order" + _last_trade(a)
    return "superseded", "our next order came before a save showed this one"


def review_outcome(a: dict) -> tuple[str, str] | None:
    """At a strategy review a picked tech still being researched counts as held (ruling 2)."""
    if a["kind"] == "tech" and a["state"] == "current":
        return "held", f"still researched in {a['expect']['field']} at the review"
    return None


def outcome_row(a: dict, result: str, by: str | None, detail: str, date: str) -> dict:
    """The `order_outcome` row of a resolved action (the Civ VI shape: `turn` is the month here)."""
    row = {"order_kind": a.get("kind"), "key": a["key"], "id": a.get("id"), "city": "", "ordered": a.get("ordered"),
           "result": result, "by": by, "detail": (detail or "")[:300],
           "turns": _months(date) - _months(a["ordered"]) if a.get("ordered") else 0,
           "date": date, "turn": _months(date), "ref": a.get("ref")}
    if "calibration" in a:
        row["calibration"] = a["calibration"]
    return row


def _key_order(keys) -> list[str]:
    rank = lambda k: (KIND_ORDER.index(k.split(" ", 1)[0]) if k.split(" ", 1)[0] in KIND_ORDER else len(KIND_ORDER), k)
    return sorted(keys, key=rank)


def action_record(rows: list[dict], now_month: int, spec) -> dict[str, dict]:
    """The stick rate per key over `spec` ([orders], months): (took + held + researched) / judged."""
    return order_record(rows, now_month, spec, _key_order({r.get("key") for r in rows if r.get("key")}),
                        succeeded=SUCCEEDED, failed=FAILED, excluded=EXCLUDED)


def action_record_text(rec: dict[str, dict]) -> str:
    """One line per key, e.g. `- directive tech_rush: 4 judged; 2 held, 2 overridden by the AI (last:
    economic_policy → economic_policy_balanced on 2272.01.01); stick rate 50% — does not stick here`."""
    lines = []
    for key, r in rec.items():
        parts = [f"{r[res]} {LABELS[res]}" for res in JUDGED if r.get(res)]
        line = f"- {key}: {r['judged']} judged" + (f"; {', '.join(parts)}" if parts else "")
        last = r.get("last_failure")
        if last and last.get("detail"):
            line += f" (last: {last['detail']})"
        other = ", ".join(f"{n} {res.replace('_', '-')}" for res, n in r["excluded"].items() if n)
        if other:
            line += f" (not judged: {other})"
        if r["rate"] is not None:
            line += f"; stick rate {r['rate']:.0%}" + (" — does not stick here" if r["weak"] else "")
        elif r["judged"]:
            line += f" (a rate needs {r['min_samples']})"
        lines.append(line)
    return "\n".join(lines)


def market_suspended(rows: list[dict], side: str, resource: str, calibration: str) -> bool:
    """Two `did_not_take` in a row for this side and resource, both clicked with today's `[ui.market]`
    calibration (ruling 6): its orders are suspended until a recalibration changes the hash. A
    `failed` sync (an agent timeout) or a success in between breaks the run."""
    keys = (f"market {side} {resource}", f"crisis market {side} {resource}")   # the same clicks either way
    mine = sorted((r for r in rows if r.get("key") in keys and r.get("result") in JUDGED),
                  key=lambda r: (r.get("turn") or 0, str(r.get("date") or "")))
    last = mine[-2:]
    return len(last) == 2 and all(r["result"] == "did_not_take" and r.get("calibration") == calibration for r in last)

"""The order record shared by the governors (docs/design/2026-09-27-civ6-levers-design.md, rulings
12-16; docs/design/2026-09-27-stellaris-levers-design.md, rulings 2-6).

Acceptance is not the outcome: each game follows what it ordered until it resolves and writes one
`order_outcome` row per resolution. From those rows this module computes the stick rate per key.
Pure: no game access."""

from __future__ import annotations

from collections.abc import Sequence

SUCCEEDED = ("completed", "held", "took")          # a last-stand action "took" (ruling 26)
FAILED = ("overridden", "did_not_take")
JUDGED = SUCCEEDED + FAILED                        # the outcomes a stick rate counts
EXCLUDED = ("invalidated", "superseded", "refused", "lost", "unknown")


def _key_rank(key: str, key_order: Sequence[str]) -> tuple[int, str]:
    return (key_order.index(key) if key in key_order else len(key_order), key)


def order_record(rows: list[dict], now_turn: int, spec, key_order: Sequence[str] = (), *,
                 succeeded: Sequence[str] = SUCCEEDED, failed: Sequence[str] = FAILED,
                 excluded: Sequence[str] = EXCLUDED) -> dict[str, dict]:
    """The stick rate per key (ruling 14) from order_outcome rows: judged orders (completed, held,
    overridden; a last-stand action took or did_not_take) resolved in the last `spec.window_turns`
    turns, widened back until `min_resolved` are judged (or to the first row). `rate` = (completed
    + held + took) / judged, None below the key's minimum samples; `weak` when a rate is at or
    below `weak_rate`. Keys come in `key_order`, then by name. A game with other outcomes names
    them (`succeeded`, `failed`, `excluded`; Stellaris: stellaris_record.py); `last_failure` is the
    newest judged failure of any kind, with its detail."""
    judged_results = (*succeeded, *failed)
    out: dict[str, dict] = {}
    for key in sorted({r.get("key") for r in rows if r.get("key")}, key=lambda k: _key_rank(k, key_order)):
        mine = sorted((r for r in rows if r.get("key") == key), key=lambda r: r.get("turn") or 0)
        judged = [r for r in mine if r.get("result") in judged_results]
        recent = [r for r in judged if (r.get("turn") or 0) >= now_turn - spec.window_turns]
        if len(recent) < spec.min_resolved:
            recent = judged[-spec.min_resolved:]
        since = min((recent[0].get("turn") or 0) if recent else now_turn, now_turn - spec.window_turns)
        counts = {res: sum(1 for r in recent if r.get("result") == res) for res in judged_results}
        n = len(recent)
        enough = n >= spec.min_samples_of(key)
        rate = sum(counts[res] for res in succeeded) / n if n else None
        last = next((r for r in reversed(recent) if r.get("result") == "overridden"), None)
        failure = next((r for r in reversed(recent) if r.get("result") in failed), None)
        others = {res: sum(1 for r in mine if r.get("result") == res and (r.get("turn") or 0) >= since)
                  for res in excluded}
        if not n and not any(others.values()):
            continue                                        # nothing left to say about this key
        out[key] = {
            "judged": n, **counts, "min_samples": spec.min_samples_of(key),
            "rate": round(rate, 2) if enough and rate is not None else None,
            "weak": bool(enough and rate is not None and rate <= spec.weak_rate),
            "excluded": others,
            "last_override": ({k: last.get(k) for k in ("id", "by", "city", "date")} if last else None),
            "last_failure": ({k: failure.get(k) for k in ("id", "by", "city", "date", "result", "detail")}
                             if failure else None),
        }
    return out

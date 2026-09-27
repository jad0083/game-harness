"""The order record shared by the governors (src/pilot/record.py): outcomes, stick rate per key."""

from pilot.config import REPO
from pilot.pillars import load_pillars

ORDERS = load_pillars(REPO / "corpora/civ6").orders


def _rows(key: str, results: list[str], start: int = 10) -> list[dict]:
    return [{"key": key, "result": r, "turn": start + 2 * i, "id": "x", "by": "y", "city": "", "date": f"T{start + 2 * i}"}
            for i, r in enumerate(results)]


def test_the_stick_rate_lives_in_one_module_that_civ6_reexports():
    from pilot import civ6, record
    assert (civ6.SUCCEEDED, civ6.FAILED, civ6.JUDGED, civ6.EXCLUDED) == \
        (record.SUCCEEDED, record.FAILED, record.JUDGED, record.EXCLUDED)
    rows = _rows("production replace", ["completed", "overridden", "completed"]) + _rows("research", ["held"]) \
        + _rows("zeta", ["completed"])
    assert civ6.order_record(rows, 30, ORDERS) == record.order_record(rows, 30, ORDERS, key_order=civ6.RECORD_KEYS)


def test_keys_come_in_the_order_given_then_by_name():
    from pilot.record import order_record
    rows = _rows("b", ["completed"]) + _rows("a", ["completed"]) + _rows("c", ["completed"]) + _rows("d", ["held"])
    assert list(order_record(rows, 30, ORDERS, key_order=("d", "c"))) == ["d", "c", "a", "b"]
    assert list(order_record(rows, 30, ORDERS)) == ["a", "b", "c", "d"]

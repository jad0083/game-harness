"""scripts/res-map.py translates the 4K UI points to another resolution: anchor + scale."""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("res_map", REPO / "scripts/res-map.py")
res_map = importlib.util.module_from_spec(spec)
spec.loader.exec_module(res_map)

# Measured live on mini-rig2 (2560x1440, UI scaling 1.0) on 2026-09-26.
MEASURED_1440 = {
    ("tech", "swap", "physics"): (275, 201), ("tech", "swap", "engineering"): (275, 397),
    ("market", "add"): (458, 187), ("market", "buy"): (841, 286), ("market", "sell"): (890, 286),
    ("market", "resources", "energy"): (827, 314), ("market", "resources", "minerals"): (848, 314),
    ("market", "resources", "alloys"): (827, 336), ("market", "plus"): (870, 377),
    ("market", "minus"): (826, 377), ("market", "confirm"): (880, 453), ("market", "remove"): (788, 453),
}


def test_the_map_reproduces_the_points_measured_at_1440p():
    ui = res_map.mapped_ui(REPO / "corpora/stellaris", "2560x1440")
    for path, (x, y) in MEASURED_1440.items():
        node = ui
        for k in path:
            node = node[k]
        assert abs(node[0] - x) <= 2 and abs(node[1] - y) <= 2, (path, node, (x, y))
    assert ui["tech"]["option_pitch"] == 74
    assert ui["tech"]["first_option"][1] == 127, "the header strip of the first card"


def test_an_unknown_resolution_is_refused():
    import pytest
    with pytest.raises(KeyError):
        res_map.mapped_ui(REPO / "corpora/stellaris", "1234x567")

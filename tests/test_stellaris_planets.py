"""The Stellaris planet check, stage A (docs/design/2026-09-27-stellaris-levers-design.md, ruling 22):
read-only flags for planets whose problem persists across 2 saves at least 2 months apart, with a
cause hint, two urgent reasons, and the amenity record per directive."""

import json

import pytest

from pilot.config import REPO
from pilot.stellaris_planets import (
    colony_codes,
    colony_row,
    low_stability,
    planet_issues,
    planet_line,
    planet_record,
    planet_record_text,
    planet_urgent,
    stability_loss,
)

FIXTURE = json.loads((REPO / "tests/fixtures/stellaris_planets.json").read_text(encoding="utf-8"))


def colony(pid=1, name="Arnvoss", *, pops=500, stability=70.0, amenities=10.0, housing=10.0, employable=None,
           unemployed=0, capital=False, occupied=False, queued=("district_city",), **extra) -> dict:
    return {"id": pid, "name": name, "pops": pops, "stability": stability, "free_amenities": amenities,
            "free_housing": housing, "employable": pops if employable is None else employable,
            "unemployed": unemployed, "capital": capital, "occupied": occupied, "queued": list(queued), **extra}


def save(date, *planets, minerals=5.0, directive="consolidate_economy") -> dict:
    return {"date": date, "net": {"minerals": minerals}, "planets": list(planets),
            "flags": [f"governor_directive_{directive}"]}


def play(saves: list[dict]) -> list[tuple[list[dict], list[str], dict]]:
    """Each save in turn, as the governor sees them: (flagged, urgent reasons, its metrics row)."""
    rows, out = [], []
    for b in saves:
        flagged, urgent = planet_issues(b, rows), planet_urgent(b, rows)
        row = {"date": b["date"], "directive": b["flags"][0].removeprefix("governor_directive_"),
               "colonies": colony_row(b, rows)}
        rows.append(row)
        out.append((flagged, urgent, row))
    return out


def test_each_threshold_is_a_problem_of_one_save():
    assert "s" in colony_codes(colony(stability=49.9)) and "s" not in colony_codes(colony(stability=50))
    assert "a" in colony_codes(colony(pops=300, amenities=-101))
    assert "a" not in colony_codes(colony(pops=299, amenities=-500)), "amenities count from 300 pops"
    assert "a" in colony_codes(colony(pops=109, employable=409, amenities=-271)), "working robots count as pops"
    assert "h" in colony_codes(colony(pops=1000, housing=-1)) and "h" not in colony_codes(colony(pops=999, housing=-300))
    assert "u" in colony_codes(colony(pops=1000, unemployed=50)) and "u" not in colony_codes(colony(pops=1000, unemployed=49))
    assert "o" in colony_codes(colony(occupied=True, occupier="Khell Zen"))
    assert {"s", "c"} <= set(colony_codes(colony(stability=24.9)))
    assert colony_codes(colony()) == {}


def test_the_capital_is_left_out_of_the_unemployment_check():
    assert "u" not in colony_codes(colony(pops=6000, unemployed=900, capital=True))


def test_an_issue_is_flagged_once_it_persists_across_2_saves_2_months_apart():
    low = lambda d: save(d, colony(stability=40))
    out = play([low("2250.01.01"), low("2250.02.01"), low("2250.03.01")])
    assert [len(f) for f, _, _ in out] == [0, 0, 1]
    assert out[2][0][0]["saves"] == 3 and out[2][0][0]["name"] == "Arnvoss"
    sparse = play([low("2250.01.01"), low("2250.03.01")])
    assert len(sparse[1][0]) == 1 and sparse[1][0][0]["saves"] == 2, "2 saves 2 months apart"
    broken = play([low("2250.01.01"), save("2250.02.01", colony()), low("2250.03.01"), low("2250.04.01")])
    assert [len(f) for f, _, _ in broken] == [0, 0, 0, 0], "the run restarts when the problem goes away"


def test_pops_down_20_percent_in_12_months_is_flagged_and_urgent_once_for_a_big_planet():
    big = lambda d, n: save(d, colony(pops=n, name="Theia", capital=True))
    out = play([big("2382.06.01", 1500), big("2382.12.01", 1400), big("2383.05.01", 1150), big("2383.06.01", 1100),
                big("2383.07.01", 1050)])
    assert "p" in out[2][2]["colonies"]["1"][3]
    assert out[2][1] == ["planet losing pops: Theia -23% in 12 months"]
    assert out[3][1] == [] and out[4][1] == [], "once, at the transition"
    assert any(code == "p" for code, _ in out[4][0][0]["issues"]), "persisted 2 months: flagged"
    small = play([save("2250.01.01", colony(pops=900)), save("2250.06.01", colony(pops=600))])
    assert "p" in small[1][2]["colonies"]["1"][3] and small[1][1] == [], "urgent only from 1,000 pops"
    old = play([save("2250.01.01", colony(pops=1500)), save("2251.06.01", colony(pops=1100))])
    assert "p" not in old[1][2]["colonies"]["1"][3], "the peak was over 12 months ago"


def test_planet_crisis_fires_once_below_25_on_2_saves_in_a_row():
    low = lambda d: save(d, colony(stability=18.4))
    out = play([low("2294.03.01"), low("2294.04.01"), low("2294.05.01")])
    assert [u for _, u, _ in out] == [[], ["planet crisis: Arnvoss stability 18"], []]
    rows = [r for _, _, r in out]
    assert low_stability(low("2294.06.01"), rows) == ["Arnvoss"]
    assert low_stability(low("2294.06.01"), rows[:0]) == [], "one save is not 2 in a row"
    recovered = save("2294.06.01", colony(stability=30))
    assert low_stability(recovered, rows) == []


def test_a_save_years_older_is_not_the_save_before():
    """A restart gap (the governor last saw the campaign in 2250, now it is 2255) is no evidence that a
    problem persisted: nothing was observed between (ruling 22's "2 saves in a row")."""
    low = lambda d: save(d, colony(stability=20))
    rows = [r for _, _, r in play([low("2249.12.01"), low("2250.01.01")])]
    now = low("2255.01.01")
    assert low_stability(now, rows) == [], "C6 needs the save before to be recent"
    assert planet_urgent(now, rows) == [] and planet_issues(now, rows) == []
    after = play([low("2249.12.01"), low("2250.01.01"), low("2255.01.01"), low("2255.02.01"), low("2255.03.01")])
    assert [u for _, u, _ in after][2:] == [[], ["planet crisis: Arnvoss stability 20"], []], \
        "the new run of saves fires once, at its own transition"
    assert [len(f) for f, _, _ in after][2:] == [0, 0, 1] and after[4][0][0]["saves"] == 3
    assert low_stability(low("2255.04.01"), [r for _, _, r in after]) == ["Arnvoss"]
    missed = play([low("2250.01.01"), low("2250.04.01")])
    assert missed[1][1] == ["planet crisis: Arnvoss stability 20"], "3 months apart: a poll missed saves"
    assert play([low("2250.01.01"), low("2250.05.01")])[1][1] == [], "4 months apart: not in a row"


def test_the_line_names_flagged_planets_only_with_a_cause_hint():
    bad = lambda d: save(d, colony(pops=1200, stability=18, amenities=-253, housing=-283, queued=()),
                         colony(2, "Balkenvoss"), minerals=-3.0)
    out = play([bad("2294.03.01"), bad("2294.04.01"), bad("2294.05.01")])
    assert planet_line(out[2][0]) == ("Planet check: Arnvoss stability 18 (3 saves), amenities -253, housing -283; "
                                      "nothing queued here, minerals net < 0")
    assert planet_line([]) == ""


def test_the_planet_record_measures_amenity_change_per_planet_year_on_deficit_planets():
    rows = [{"date": "2250.01.01", "directive": "consolidate_economy", "colonies": {"1": [800, -200, 60, "a"], "2": [800, 50, 70, ""]}},
            {"date": "2251.01.01", "directive": "defend", "colonies": {"1": [800, -190, 60, "a"], "2": [800, 40, 70, ""]}},
            {"date": "2252.01.01", "directive": "defend", "colonies": {"1": [800, -250, 50, "a"], "2": [800, 30, 70, ""]}},
            {"date": "2252.07.01", "directive": "defend", "colonies": {"1": [800, -280, 45, "sa"]}}]
    rec = planet_record(rows)
    assert rec["consolidate_economy"] == {"per_planet_year": 10.0, "planet_years": 1.0, "planets": 1}
    assert rec["defend"] == {"per_planet_year": pytest.approx(-60.0), "planet_years": 1.5, "planets": 1}
    text = planet_record_text(rec)
    assert "- consolidate_economy: amenities +10 per planet-year over 1 planet-year on 1 planet" in text
    assert "- defend: amenities -60 per planet-year over 1.5 planet-years on 1 planet" in text
    assert planet_record([{"date": "2250.01.01", "directive": "defend"}]) == {}, "rows before the check carry no colonies"


def test_the_stability_loss_estimate():
    b = save("2250.01.01", colony(pops=1000, stability=50), colony(2, "B", pops=1000, stability=80))
    assert stability_loss(b) == pytest.approx(7.5), "(1000 x 25 x 0.6%) / 2000 pops, in percent"
    assert stability_loss(save("2250.01.01")) is None


# ---- the local saves (read-only; trimmed planet blocks in tests/fixtures/stellaris_planets.json) -------

def test_arnvoss_in_the_theia_2272_save_carries_the_development_fields():
    arn = next(p for p in FIXTURE["theia_2272"]["planets"] if p["name"] == "Arnvoss")
    assert (arn["designation"], arn["pops"], arn["district_levels"], arn["unemployed"], arn["jobs_open"]) == (
        "mining", 272, {"city": 1, "mining": 1}, 0, 248)
    assert not any(p["occupied"] for p in FIXTURE["theia_2272"]["planets"]), \
        "bodies we own but another country controls are not colonies of ours"
    assert [p["name"] for p in FIXTURE["theia_2272"]["planets"]] == ["Theia", "Balkenvoss", "Arnvoss"]


@pytest.mark.parametrize("key, name, amenities", [("une2_2256", "Nueva Sonora", -271), ("theia_2393", "Wintered Stane", -326)])
def test_the_saves_amenity_deficits_are_flagged(key, name, amenities):
    b = FIXTURE[key]
    y, m, d = b["date"].split(".")
    earlier = {**b, "date": f"{int(y) - (int(m) <= 2)}.{(int(m) - 3) % 12 + 1:02d}.{d}"}     # 2 months before
    assert planet_issues(b, []) == [], "one save alone is not a lasting problem"
    flagged = planet_issues(b, [{"date": earlier["date"], "colonies": colony_row(earlier, [])}])
    mine = next(f for f in flagged if f["name"] == name)
    assert f"amenities {amenities}" in dict(mine["issues"])["a"]
    assert all(f["name"] == name for f in flagged), "only the planets with a problem are named"

"""Civilization VI district placement, stage A (docs/design/2026-09-27-civ6-levers-design.md, ruling 30):
read-only. Rates the plots where each district may go (the game's own list, `game-controller civ6
district-plots`) by its adjacency under the game's rules (`corpora/civ6/data/_adjacency.json`, from
`Adjacency_YieldChanges` and `District_Adjacencies`), the share of effort of the pillar it serves, the
tile it gives up, and the best plots of districts of heavier pillars; rates the districts the AI placed
the same way, as the baseline for the go criterion of stage B. Nothing is placed.

Adjacency follows the game's columns: each rule counts the neighbouring plots that match it and gives
`YieldChange` per `TilesRequired` of them; `AdjacentRiver` is the plot itself touching a river, `Self`
the district itself. Rules that need a tech or civic are left out (the snapshot does not list what is
known), rules that a tech or civic makes obsolete are kept."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# the pillar a district serves, by the yield of its adjacency (corpora/civ6/pillars.toml)
YIELD_PILLAR = {"YIELD_SCIENCE": "science", "YIELD_CULTURE": "culture", "YIELD_FAITH": "faith",
                "YIELD_GOLD": "economy", "YIELD_PRODUCTION": "economy", "YIELD_FOOD": "expansion"}
# what building on a plot gives up (initial weights, ruling 30)
LOST_TILE = {"resource": 3, "improvement": 2, "feature": 1}
# stage B goes ahead when our best plot beats the AI's by this much adjacency on average...
GO_MIN_GAIN = 1.0
# ...over at least this many districts the AI placed
GO_MIN_DISTRICTS = 4
PREFIX = {"t": "TERRAIN_", "f": "FEATURE_", "r": "RESOURCE_", "i": "IMPROVEMENT_", "d": "DISTRICT_", "w": "BUILDING_"}


def full(plot: dict, key: str) -> str | None:
    """A plot fact's full type key (district-plots drops the prefixes to keep its reply small)."""
    v = plot.get(key)
    return f"{PREFIX[key]}{v}" if v else None


@dataclass
class Rules:
    by_district: dict[str, list[dict]] = field(default_factory=dict)
    replaces: dict[str, str] = field(default_factory=dict)
    resource_class: dict[str, str] = field(default_factory=dict)
    natural_wonders: frozenset[str] = frozenset()
    districts: dict[str, dict] = field(default_factory=dict)       # placement flags (Coast, NoAdjacentCity, …)

    @classmethod
    def load(cls, corpus: Path) -> Rules:
        data = json.loads((corpus / "data" / "_adjacency.json").read_text(encoding="utf-8"))
        rows = {r["ID"]: r for r in data["Adjacency_YieldChanges"]}
        by: dict[str, list[dict]] = {}
        for link in data["District_Adjacencies"]:
            if link["YieldChangeId"] in rows:
                by.setdefault(link["DistrictType"], []).append(rows[link["YieldChangeId"]])
        return cls(by, dict(data.get("DistrictReplaces") or {}), dict(data.get("ResourceClasses") or {}),
                   frozenset(data.get("NaturalWonders") or ()), dict(data.get("Districts") or {}))

    def of(self, district: str) -> list[dict]:
        """A district's rules: its own, else those of the district it replaces."""
        return self.by_district.get(district) or self.by_district.get(self.replaces.get(district, ""), [])

    def pillar(self, district: str) -> str | None:
        ys = Counter(r.get("YieldType") for r in self.of(district))
        return YIELD_PILLAR.get(ys.most_common(1)[0][0]) if ys else None

    def is_district(self, key: str | None, wanted: str) -> bool:
        return bool(key) and (key == wanted or self.replaces.get(key) == wanted)


def _matches(rules: Rules, r: dict, q: dict) -> bool:
    """Whether neighbouring plot `q` counts for adjacency rule `r` (every criterion the rule names).
    A wonder counts once built (`built` on the plot: district-plots lists our built wonders; a plot
    shows its wonder while it is still being built)."""
    tests = []
    if r.get("OtherDistrictAdjacent"):
        tests.append(bool(q.get("d")) and q.get("d") != "WONDER")       # a wonder's plot is no district here
    if r.get("AdjacentTerrain"):
        tests.append(full(q, "t") == r["AdjacentTerrain"])
    if r.get("AdjacentFeature"):
        tests.append(full(q, "f") == r["AdjacentFeature"])
    if r.get("AdjacentWonder"):
        tests.append(bool(q.get("w")) and q.get("built", True))
    if r.get("AdjacentNaturalWonder"):
        tests.append(bool(q.get("nw")) or full(q, "f") in rules.natural_wonders)
    if r.get("AdjacentImprovement"):
        tests.append(full(q, "i") == r["AdjacentImprovement"])
    if r.get("AdjacentDistrict"):
        tests.append(rules.is_district(full(q, "d"), r["AdjacentDistrict"]))
    if r.get("AdjacentResource"):
        tests.append(bool(q.get("r")))
    if r.get("AdjacentSeaResource"):
        tests.append(bool(q.get("water")) and bool(q.get("r")))
    cls = r.get("AdjacentResourceClass")
    if cls and cls != "NO_RESOURCECLASS":
        tests.append(rules.resource_class.get(full(q, "r") or "") == cls)
    return bool(tests) and all(tests)


def adjacency(rules: Rules, district: str, idx: str, plots: dict[str, dict]) -> dict[str, int]:
    """The adjacency yields of `district` on plot `idx`, per yield type (only those above 0)."""
    p = plots[idx]
    near = [plots[str(n)] for n in p.get("adj") or [] if str(n) in plots]
    out: dict[str, int] = {}
    for r in rules.of(district):
        if r.get("PrereqTech") or r.get("PrereqCivic"):
            continue
        if r.get("Self"):
            n = 1
        elif r.get("AdjacentRiver"):
            n = 1 if p.get("river") else 0
        else:
            n = sum(1 for q in near if _matches(rules, r, q))
        bonus = int(r.get("YieldChange") or 0) * (n // max(1, int(r.get("TilesRequired") or 1)))
        if bonus:
            out[r["YieldType"]] = out.get(r["YieldType"], 0) + bonus
    return out


def lost_value(plot: dict) -> int:
    """What building on the plot gives up: a resource 3, an improvement 2, a feature 1."""
    return sum(v for k, v in (("r", LOST_TILE["resource"]), ("i", LOST_TILE["improvement"]),
                              ("f", LOST_TILE["feature"])) if plot.get(k))


def relative_shares(shares: dict[str, float], pillars: tuple[str, ...] = tuple(dict.fromkeys(YIELD_PILLAR.values()))
                    ) -> dict[str, float]:
    """Each pillar's share of effort relative to an even split (1.0 = its fair part); `shares` in any
    unit (weights, percents), normalised here. No shares: every pillar 1.0."""
    total = sum(v for v in shares.values() if v > 0)
    if not total:
        return dict.fromkeys(pillars, 1.0)
    n = len(shares)
    return {k: (v / total) * n for k, v in shares.items()}


@dataclass
class Rated:
    district: str
    plot: str
    x: int | None
    y: int | None
    adjacency: dict[str, int]
    score: float
    lost: int
    penalty: float = 0.0

    @property
    def total(self) -> int:
        return sum(self.adjacency.values())


def _rate(rules: Rules, district: str, idx: str, plots: dict, weight: float) -> Rated:
    adj = adjacency(rules, district, idx, plots)
    lost = lost_value(plots[idx])
    p = plots[idx]
    return Rated(district, idx, p.get("x"), p.get("y"), adj, sum(adj.values()) * weight - lost, lost)


def rate_candidates(city: dict, plots: dict[str, dict], rules: Rules, shares: dict[str, float]) -> dict[str, list[Rated]]:
    """Every district with adjacency rules the city could place, its plots ranked by score = adjacency
    x the relative share of its pillar - the tile given up - a reservation penalty where the plot is
    the best plot of a district of a heavier pillar (what that district would lose by moving to its
    next plot)."""
    rel = relative_shares(shares)
    rated: dict[str, list[Rated]] = {}
    for c in city.get("candidates") or []:
        if not rules.of(c["type"]):
            continue
        weight = rel.get(rules.pillar(c["type"]) or "", 0.0)
        rated[c["type"]] = sorted((_rate(rules, c["type"], str(i), plots, weight) for i in c.get("plots") or []
                                   if str(i) in plots), key=lambda r: -r.score)
    reserved = {d: (rows[0].plot, rows[0].score - (rows[1].score if len(rows) > 1 else 0.0))
                for d, rows in rated.items() if rows}
    for d, rows in rated.items():
        mine = rel.get(rules.pillar(d) or "", 0.0)
        for other, (plot, loss) in reserved.items():
            if other != d and rel.get(rules.pillar(other) or "", 0.0) > mine:
                for r in rows:
                    if r.plot == plot:
                        r.penalty += max(0.0, loss)
                        r.score -= max(0.0, loss)
        rows.sort(key=lambda r: -r.score)
    return rated


def plausible_plots(city: dict, plots: dict[str, dict], rules: Rules, district: str) -> list[str]:
    """Plots a placed district could have taken instead, for the baseline: the plots the game offers
    this city for any district now (its candidates' lists: the city's own free plots), water for a
    coastal district and land otherwise, not next to a city centre where the district forbids it.
    A city with nothing left to place offers none, and its districts gain nothing."""
    flags = rules.districts.get(district) or rules.districts.get(rules.replaces.get(district, "")) or {}
    offered = dict.fromkeys(str(i) for c in city.get("candidates") or [] for i in c.get("plots") or [])
    out = []
    for idx in offered:
        p = plots.get(idx) or {}
        if bool(p.get("water")) != bool(flags.get("Coast")) or p.get("d") or "adj" not in p:
            continue
        near = [plots.get(str(n)) or {} for n in p.get("adj") or []]
        if flags.get("NoAdjacentCity") and any(q.get("d") == "CITY_CENTER" for q in near):
            continue
        out.append(idx)
    return out


def rate_placed(city: dict, plots: dict[str, dict], rules: Rules) -> list[dict]:
    """The baseline: each district the AI placed that has adjacency rules, its adjacency where it
    stands, and the best adjacency it could have had on a plausible plot now (its own plot counted,
    and its own district taken off the map while others are tried)."""
    out = []
    by_xy = {(p.get("x"), p.get("y")): i for i, p in plots.items()}
    for d in city.get("placed") or []:
        idx = by_xy.get((d.get("x"), d.get("y")))
        if d["type"] == "DISTRICT_CITY_CENTER" or idx is None or not rules.of(d["type"]):
            continue
        ai = sum(adjacency(rules, d["type"], idx, plots).values())
        without = {**plots, idx: {**plots[idx], "d": None}}
        best, where = ai, idx
        for q in plausible_plots(city, without, rules, d["type"]):
            v = sum(adjacency(rules, d["type"], q, without).values())
            if v > best:
                best, where = v, q
        out.append({"city": city.get("name"), "district": d["type"], "x": d.get("x"), "y": d.get("y"), "ai": ai,
                    "best": best, "best_at": [plots[where].get("x"), plots[where].get("y")], "gain": best - ai,
                    "complete": d.get("complete")})
    return out


def go_verdict(placed: list[dict]) -> tuple[str, str]:
    """Stage B's go criterion: over at least GO_MIN_DISTRICTS districts the AI placed, our best plot
    beats the AI's by at least GO_MIN_GAIN adjacency on average."""
    n = len(placed)
    if n < GO_MIN_DISTRICTS:
        return "wait", f"{n} district(s) the AI placed can be rated; the criterion needs {GO_MIN_DISTRICTS}"
    mean = sum(p["gain"] for p in placed) / n
    if mean >= GO_MIN_GAIN:
        return "go", f"our best plot beats the AI's by {mean:+.2f} adjacency on average over {n} districts"
    return "no-go", (f"our best plot beats the AI's by only {mean:+.2f} adjacency on average over {n} districts: "
                     "the AI already places well; option 2 stops at stage A")


def report(data: dict, rules: Rules, shares: dict[str, float], cid=lambda k: k) -> dict:
    """The whole stage-A read: candidates per city (best plots first), the AI's placements rated, and
    the go verdict. `data` is `district-plots`' reply; `cid` names type keys (a corpus index's `cid`)."""
    plots = data.get("plots") or {}
    if isinstance(data.get("built"), list):
        built = set(data["built"])
        plots = {i: {**p, "built": p.get("w") in built} if p.get("w") else p for i, p in plots.items()}
    cities, placed = [], []
    for c in data.get("cities") or []:
        cands = rate_candidates(c, plots, rules, shares)
        cities.append({"name": c.get("name"), "candidates": {
            cid(d): [{"x": r.x, "y": r.y, "adjacency": r.adjacency, "score": round(r.score, 2), "lost": r.lost,
                      "penalty": round(r.penalty, 2)} for r in rows[:3]]
            for d, rows in cands.items() if rows},
            "errors": {cid(x["type"]): x["error"] for x in c.get("candidates") or [] if x.get("error")}})
        placed += rate_placed(c, plots, rules)
    verdict, why = go_verdict(placed)
    return {"turn": data.get("turn"), "cities": cities,
            "placed": [{**p, "district": cid(p["district"])} for p in placed], "verdict": verdict, "why": why}


def report_text(r: dict) -> str:
    def adj(a: dict) -> str:
        return ", ".join(f"+{v} {k.removeprefix('YIELD_').lower()}" for k, v in a.items()) or "+0"
    lines = [f"District placement, stage A (read-only), T{r.get('turn')}:"]
    for c in r["cities"]:
        best = [f"{d} at {rows[0]['x']},{rows[0]['y']} ({adj(rows[0]['adjacency'])}; score {rows[0]['score']:g})"
                for d, rows in c["candidates"].items()]
        lines.append(f"- {c['name']}: " + ("; ".join(best) if best else "no district with adjacency rules to place")
                     + ("" if not c["errors"] else f" (no plots read: {', '.join(c['errors'])})"))
    for p in r["placed"]:
        lines.append(f"- AI placed {p['district']} in {p['city']} at {p['x']},{p['y']}: adjacency {p['ai']}, "
                     f"best plausible {p['best']} at {p['best_at'][0]},{p['best_at'][1]} (gain {p['gain']:+d})")
    lines.append(f"Verdict: {r['verdict']} — {r['why']}.")
    return "\n".join(lines)

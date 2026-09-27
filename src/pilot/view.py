"""Each game's dashboard view and readable names for game ids (docs/design/2026-09-27-dashboard-v2-design.md,
rulings 2, 3, 29 and 30).

`corpora/<game>/dashboard.toml` says how the dashboard speaks about one game: its time unit and date
format, the cadence field, the decision noun, the levers tab, whether frames exist, the figures, the
chart views and their series, the outcome keys and window, the rivals table, and the recovery steps
per stop category. It is kept apart from `pillars.toml` because GalCiv has none and a broken
`pillars.toml` turns the strategy layer off; the view must survive both. A game without a file, or
with a broken one, gets `default_view` (and the error), so the page still renders.

`Names` turns ids into names through the game's corpus records (`CIVILIZATION_GERMANY`,
`civ:germany` -> "Germany"; `BUILDING_GURDWARA` -> "Gurdwara"), with prefix-strip and title-case
as the fallback; anything that does not look like an id (an empire's name, a city) is returned as is.
"""

from __future__ import annotations

import json
import re
import threading
import tomllib
from pathlib import Path
from typing import Any

TIME_UNITS = ("turn", "month")
LEVERS = ("orders", "actions", "screen")
COLUMN_KINDS = ("number", "ratio", "times", "flag", "trend")
FIGURE_KINDS = ("value", "rank", "directive", "standing")
# stop categories the governors set on `info.attention` (ruling 7); a recovery entry for another
# category would never be shown
CATEGORIES = ("transient", "screen", "unreachable", "game_changed", "stall", "control_failed")

GAME_KEYS = {  # [game] key: (type, default)
    "name": (str, ""), "short": (str, ""), "time_unit": (str, "month"), "cadence": (str, ""),
    "decision_noun": (str, "decisions"), "levers": (str, ""), "levers_label": (str, ""),
    "frames": (bool, False), "speed": (bool, False), "override": (bool, False),
    "chart_title": (str, "Over time"), "rivals_label": (str, ""), "talk_placeholder": (str, "Ask the governor"),
    "decide_now_help": (str, ""), "stop_confirm": (str, "The governor stops."), "review_window": (str, ""),
    "decisions_help": (str, ""),
}


class ViewError(ValueError):
    """dashboard.toml is not a valid view (the message says where)."""


def default_view(game: str, error: str = "") -> dict[str, Any]:
    """What the page shows for a game without a (valid) view file: names and dates only."""
    info = {k: d for k, (_, d) in GAME_KEYS.items()}
    info.update(name=game or "Game", short=game or "Game")
    return {"id": game, "known": False, "error": error, "game": info, "labels": {}, "figures": [], "chart": [],
            "outcomes": None, "rivals": None, "recovery": {}}


def _want(cond: bool, where: str, what: str) -> None:
    if not cond:
        raise ViewError(f"{where}: {what}")


def _strs(v: Any, where: str) -> list[str]:
    _want(isinstance(v, list) and all(isinstance(x, str) and x for x in v), where, "must be a list of names")
    return list(v)


def parse_view(game: str, raw: dict) -> dict[str, Any]:
    """A validated view with every default filled in; ViewError names the first problem."""
    view = default_view(game)
    view["known"] = True
    g = raw.get("game")
    _want(isinstance(g, dict), "[game]", "missing")
    for k, v in g.items():
        _want(k in GAME_KEYS, f"[game] {k}", "unknown key")
        _want(isinstance(v, GAME_KEYS[k][0]), f"[game] {k}", f"must be a {GAME_KEYS[k][0].__name__}")
        view["game"][k] = v
    _want(bool(view["game"]["name"]), "[game] name", "missing")
    view["game"]["short"] = view["game"]["short"] or view["game"]["name"]
    _want(view["game"]["time_unit"] in TIME_UNITS, "[game] time_unit", f"one of {', '.join(TIME_UNITS)}")
    _want(view["game"]["levers"] in ("", *LEVERS), "[game] levers", f"one of {', '.join(LEVERS)}")
    labels = raw.get("labels", {})
    _want(isinstance(labels, dict) and all(isinstance(v, str) for v in labels.values()), "[labels]", "names to words")
    view["labels"] = dict(labels)
    for i, f in enumerate(raw.get("figures", [])):
        where = f"[[figures]] {i + 1}"
        _want(isinstance(f, dict) and isinstance(f.get("key"), str) and f["key"], where, "needs a key")
        kind = f.get("kind", "rank" if f["key"].startswith("rank:") else "value")
        _want(kind in FIGURE_KINDS, where, f"kind one of {', '.join(FIGURE_KINDS)}")
        for opt in ("label", "rank", "keep", "sub"):
            _want(isinstance(f.get(opt, ""), str), where, f"{opt} must be text")
        view["figures"].append({"key": f["key"], "label": f.get("label") or view["labels"].get(f["key"], f["key"]),
                                "kind": kind, "rank": f.get("rank", ""), "keep": f.get("keep", ""), "sub": f.get("sub", "")})
    for cid, c in (raw.get("chart") or {}).items():
        where = f"[chart.{cid}]"
        _want(isinstance(c, dict), where, "must be a table")
        view["chart"].append({"id": cid, "label": str(c.get("label") or cid), "series": _strs(c.get("series"), where),
                              "invert": bool(c.get("invert", False))})
    if "outcomes" in raw:
        o = raw["outcomes"]
        watch = o.get("watch", {})
        _want(isinstance(watch, dict) and all(isinstance(v, (int, float)) and v < 0 for v in watch.values()),
              "[outcomes] watch", "each key's drop must be a negative number")
        _want(isinstance(o.get("window", ""), str) and "{n}" in o.get("window", "{n}"), "[outcomes] window",
              "text with {n}")
        view["outcomes"] = {"keys": _strs(o.get("keys"), "[outcomes] keys"),
                            "window": o.get("window", "{n} " + view["game"]["time_unit"] + "s later"),
                            "watch": dict(watch), "deficits": bool(o.get("deficits", False))}
    if "rivals" in raw:
        r = raw["rivals"]
        cols = []
        for i, c in enumerate(r.get("columns", [])):
            c = {"key": c} if isinstance(c, str) else c
            where = f"[rivals] column {i + 1}"
            _want(isinstance(c, dict) and isinstance(c.get("key"), str), where, "needs a key")
            kind = c.get("kind", "number")
            _want(kind in COLUMN_KINDS, where, f"kind one of {', '.join(COLUMN_KINDS)}")
            cols.append({"key": c["key"], "label": c.get("label") or view["labels"].get(c["key"], c["key"]),
                         "kind": kind, "ours": c.get("ours", ""), "title": c.get("title", ""),
                         "wide_only": bool(c.get("wide_only", False))})
        view["rivals"] = {"label": r.get("label") or view["game"]["rivals_label"] or "Rivals", "columns": cols,
                          "tags": r.get("tags", ""), "note": r.get("note", "")}
    for cat, entry in (raw.get("recovery") or {}).items():
        where = f"[recovery.{cat}]"
        _want(cat in CATEGORIES, where, f"category one of {', '.join(CATEGORIES)}")
        _want(isinstance(entry, dict) and isinstance(entry.get("title"), str), where, "needs a title")
        view["recovery"][cat] = {"title": entry["title"], "steps": _strs(entry.get("steps", []), where)}
    unknown = set(raw) - {"game", "labels", "figures", "chart", "outcomes", "rivals", "recovery"}
    _want(not unknown, "dashboard.toml", f"unknown tables {sorted(unknown)}")
    return view


def load_view(corpora: Path, game: str) -> dict[str, Any]:
    """The game's view, or `default_view` with the error when its file is missing or invalid."""
    if not re.fullmatch(r"[a-z0-9_]+", game or ""):
        return default_view(game or "")
    path = corpora / game / "dashboard.toml"
    if not path.exists():
        return default_view(game)
    try:
        return parse_view(game, tomllib.loads(path.read_text(encoding="utf-8")))
    except (ViewError, tomllib.TOMLDecodeError) as e:
        return default_view(game, f"{path.name}: {e}")


class Views:
    """`load_view` cached per game until the file changes."""

    def __init__(self, corpora: Path):
        self.corpora = corpora
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def get(self, game: str) -> dict[str, Any]:
        path = self.corpora / (game or "_") / "dashboard.toml"
        try:
            stamp = path.stat().st_mtime
        except OSError:
            stamp = -1.0
        with self._lock:
            hit = self._cache.get(game)
            if hit and hit[0] == stamp:
                return hit[1]
        view = load_view(self.corpora, game)
        with self._lock:
            self._cache[game] = (stamp, view)
        return view


# ---- readable names (ruling 30) ------------------------------------------------------------------

TYPE_KEY = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")          # CIVILIZATION_GERMANY
CORPUS_ID = re.compile(r"^[a-z][a-z_]*:[a-z0-9_]+$")              # unit:trader
PREFIXES = ("GREAT_PERSON_INDIVIDUAL_", "GREAT_PERSON_CLASS_", "CIVILIZATION_", "LEADER_", "BUILDING_", "UNIT_",
            "DISTRICT_", "IMPROVEMENT_", "TECH_", "CIVIC_", "POLICY_", "PROJECT_", "GOVERNMENT_", "BELIEF_", "ERA_",
            "FEATURE_", "RESOURCE_", "MINOR_CIV_", "WONDER_", "YIELD_")
SKIP_FILES = {"event", "random_event", "moment"}      # large and never named on the dashboard


def title_case(words: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in words.split())


def fallback_name(ident: str) -> str:
    """Prefix-strip and title-case: GREAT_PERSON_CLASS_SCIENTIST -> Great Scientist, unit:war_cart ->
    War Cart, BUILDING_STAVE_CHURCH -> Stave Church."""
    if CORPUS_ID.match(ident):
        return title_case(ident.split(":", 1)[1].replace("_", " "))
    for p in PREFIXES:
        if ident.startswith(p):
            rest = title_case(ident[len(p):].replace("_", " ").lower())
            return f"Great {rest}" if p == "GREAT_PERSON_CLASS_" else rest
    return title_case(ident.replace("_", " ").lower())


class Names:
    """Names of a game's ids from its corpus records (`id`, `name`, `aliases[0]` = the type key),
    loaded once per game."""

    def __init__(self, corpora: Path):
        self.corpora = corpora
        self._maps: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()

    def _map(self, game: str) -> dict[str, str]:
        with self._lock:
            if game in self._maps:
                return self._maps[game]
        out: dict[str, str] = {}
        data = self.corpora / game / "data"
        if re.fullmatch(r"[a-z0-9_]+", game or "") and data.is_dir():
            for path in sorted(data.glob("*.json")):
                if path.stem.startswith("_") or path.stem in SKIP_FILES:
                    continue
                try:
                    records = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                for r in records if isinstance(records, list) else []:
                    if not isinstance(r, dict) or not r.get("id") or not r.get("name"):
                        continue
                    out.setdefault(r["id"], r["name"])
                    for alias in (r.get("aliases") or [])[:1]:
                        out.setdefault(alias, r["name"])
        with self._lock:
            self._maps[game] = out
        return out

    def name(self, game: str, ident: Any) -> Any:
        """The readable name of an id; anything else unchanged."""
        if not isinstance(ident, str) or not (TYPE_KEY.match(ident) or CORPUS_ID.match(ident)):
            return ident
        return self._map(game).get(ident) or fallback_name(ident)

    def names(self, game: str, idents) -> dict[str, str]:
        """{id: name} for the ids among `idents`."""
        return {i: self.name(game, i) for i in idents
                if isinstance(i, str) and (TYPE_KEY.match(i) or CORPUS_ID.match(i))}

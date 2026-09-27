#!/usr/bin/env python3
"""Generate corpora/civ6/data/*.json from Civilization VI's own gameplay XML and en_US text.

    python3 scripts/extract-civ6.py incoming/civ6 --game-version 1.0.12.68

The input folder mirrors the install: `Base/Assets/Gameplay/Data/**`, `Base/Assets/Text/en_US/**`,
`DLC/<pack>/<pack>.modinfo`, `DLC/<pack>/Data/*.{xml,sql}` and `DLC/<pack>/Text/**`. The script
rebuilds the rules database the game builds when it loads a Gathering Storm game:

1. base schema (`01_GameplaySchema.sql`, `02_AddTriggers.sql`), then the base data files;
2. every installed DLC's `<UpdateDatabase>` actions whose `<ActionCriteria>` pass for the chosen
   ruleset (scenarios skipped; game modes only with `--modes`), ordered by `LoadOrder`, then by
   pack, with `<File Priority>` descending inside an action;
3. XML operations `Row` (insert), `Replace`, `InsertOrIgnore`, `Update` (Where/Set) and `Delete`
   (empty `Delete` clears the table), with deferred foreign keys so deletes cascade.

Text follows the same layering (`<UpdateText>` actions, en_US rows only). Records are then
rendered for a player-model: names, costs, prerequisites, adjacency, unique-item owners, and
effect text from the game's own descriptions (`LOC_*_DESCRIPTION`), `ModifierStrings` templates
filled from `ModifierArguments`, or, as a last resort, a compact `effect(args) on collection`.
The record contract is corpora/civ6/data/README.md.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sqlite3
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zlib
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "corpora/civ6/data"
RULESET = "RULESET_EXPANSION_2"

# Friendly names for DLC folders (the modinfo titles are LOC keys).
PACKS = {
    "Base": "Base game", "Expansion1": "Rise and Fall", "Expansion2": "Gathering Storm",
    "Aztec_Montezuma": "Aztec Civilization Pack", "Poland_Jadwiga": "Poland Civilization & Scenario Pack",
    "Australia": "Australia Civilization & Scenario Pack", "Macedonia_Persia": "Persia and Macedon Pack",
    "Nubia_Amanitore": "Nubia Civilization & Scenario Pack", "Indonesia_Khmer": "Khmer and Indonesia Pack",
    "VikingsLandmarks": "Vikings Scenario Pack", "GranColombia_Maya": "Maya & Gran Colombia Pack",
    "Ethiopia": "Ethiopia Pack", "Byzantium_Gaul": "Byzantium & Gaul Pack", "Babylon": "Babylon Pack",
    "KublaiKhan_Vietnam": "Vietnam & Kublai Khan Pack", "Portugal": "Portugal Pack",
    "GreatNegotiators": "Great Negotiators Pack", "GreatWarlords": "Great Warlords Pack",
    "RulersOfChina": "Rulers of China Pack", "RulersOfTheSahara": "Rulers of the Sahara Pack",
    "GreatBuilders": "Great Builders Pack", "RulersOfEngland": "Rulers of England Pack",
    "JuliusCaesar": "Julius Caesar", "TeddyRoosevelt": "Teddy Roosevelt persona pack",
    "CatherineDeMedici": "Catherine de Medici persona pack", "ScoutCat": "Scout Cat",
    "BarbarianClansMode": "Barbarian Clans mode", "TreeRandomizer": "Tech and Civic Shuffle mode",
}


def read_text(p: str | Path) -> str:
    return Path(p).read_bytes().decode("utf-8-sig", errors="replace")


def split_sql(txt: str):
    buf = ""
    for line in txt.splitlines(True):
        if line.strip().startswith("--"):
            continue
        buf += line
        if sqlite3.complete_statement(buf):
            yield buf
            buf = ""


def kv(el: ET.Element) -> dict:
    """A <Row>'s columns: attributes plus child elements (except Where/Set). Like the game, an
    element's text is trimmed and an empty element is NULL."""
    d = dict(el.attrib)
    for c in el:
        if isinstance(c.tag, str) and c.tag not in ("Where", "Set"):
            t = (c.text or "").strip()
            d[c.tag] = t if t else None
    return d


# -- modinfo layering ------------------------------------------------------------------------


class Mod:
    def __init__(self, path: Path, order: int):
        self.path = path
        self.dir = path.parent
        self.folder = self.dir.name
        self.order = order
        self.xml = ET.fromstring(read_text(path))
        self.id = (self.xml.get("id") or "").lower()
        self.criteria = {c.get("id"): c for c in self.xml.iter("Criteria")}

    def actions(self, tag: str):
        ig = self.xml.find("InGameActions")
        return [] if ig is None else [a for a in ig if a.tag == tag]


class Criteria:
    """Evaluates modinfo <Criteria> for one ruleset (GS: GameCore Expansion2)."""

    def __init__(self, ruleset: str, active_mods: set[str], modes: set[str]):
        self.ruleset = ruleset
        self.active = active_mods
        self.modes = modes
        self.gamecore = {"RULESET_EXPANSION_2": "Expansion2", "RULESET_EXPANSION_1": "Expansion1"}.get(ruleset, "Base")
        self.players = {"RULESET_EXPANSION_2": "Expansion2_Players",
                        "RULESET_EXPANSION_1": "Expansion1_Players"}.get(ruleset, "StandardPlayers")
        self.unknown: set[str] = set()

    def one(self, r: ET.Element) -> bool:
        txt = (r.text or "").strip()
        if r.tag == "RuleSetInUse":
            return self.ruleset in [x.strip() for x in txt.split(",")]
        if r.tag == "GameCoreInUse":
            return txt == self.gamecore
        if r.tag == "LeaderPlayable":
            # every owned leader is playable; the entry must name this ruleset's player list
            entries = [x.strip() for x in txt.split(",") if x.strip()]
            if self.players == "StandardPlayers":
                return any(e.startswith(("StandardPlayers::", "Players:StandardPlayers::")) for e in entries)
            return any(f":{self.players}::" in e or e.startswith(f"{self.players}::") for e in entries)
        if r.tag == "ConfigurationValueMatches":
            body = ET.tostring(r, encoding="unicode")
            return any(m and m.lower() in body.lower() for m in self.modes)
        if r.tag in ("ModInUse", "ModIsEnabled"):
            return txt.lower() in self.active
        self.unknown.add(r.tag)
        return False

    def __call__(self, c: ET.Element | None) -> bool:
        if c is None:
            return True
        res = [self.one(r) for r in c if isinstance(r.tag, str)]
        if not res:
            return True
        return any(res) if c.get("any") == "1" else all(res)


def ordered_files(mods: list[Mod], crit: Criteria, tag: str, warnings: list[str]) -> list[tuple[Mod, Path]]:
    """Files of every passing <tag> action, sorted by (LoadOrder, pack order), Priority desc."""
    acts = []
    for m in mods:
        for a in m.actions(tag):
            cid = a.get("criteria")
            if cid and cid not in m.criteria:
                warnings.append(f"{m.folder}: unknown criteria {cid}")
                continue
            if cid and not crit(m.criteria[cid]):
                continue
            lo = int(a.findtext("Properties/LoadOrder") or 0)
            files = [(int(f.get("Priority") or 0), i, (f.text or "").strip()) for i, f in enumerate(a.findall("File"))]
            files.sort(key=lambda t: (-t[0], t[1]))
            acts.append((lo, m.order, m, [f for _, _, f in files if f]))
    acts.sort(key=lambda t: (t[0], t[1]))
    out = []
    for _, _, m, files in acts:
        for f in files:
            out.append((m, m.dir / f))
    return out


def load_mods(root: Path, include_scenarios: bool = False) -> list[Mod]:
    mods = []
    for i, mi in enumerate(sorted(glob.glob(str(root / "DLC/*/*.modinfo")))):
        if not include_scenarios and "Scenario" in Path(mi).parent.name:
            continue
        mods.append(Mod(Path(mi), i))
    return mods


# -- rules database --------------------------------------------------------------------------


class RulesDb:
    """In-memory SQLite database built like the game builds its gameplay database."""

    def __init__(self) -> None:
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.create_function("Make_Hash", 1, lambda s: zlib.crc32(s.encode()) if s else 0)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("BEGIN")
        self.db.execute("PRAGMA defer_foreign_keys=ON")
        self.warnings: list[str] = []
        self.stats = defaultdict(int)
        self.type_source: dict[str, str] = {}      # Types.Type -> pack folder that added it
        self._cols: dict[str, dict[str, str]] = {}
        self.source = "Base"
        self.unknown_tables: set[str] = set()
        self.unknown_columns: set[str] = set()

    def cols(self, t: str) -> dict[str, str]:
        if t not in self._cols:
            self._cols[t] = {r[1].lower(): r[1] for r in self.db.execute(f'PRAGMA table_info("{t}")')}
        return self._cols[t]

    def run_sql(self, txt: str, name: str = "") -> None:
        for stmt in split_sql(txt):
            try:
                self.db.execute(stmt)
            except sqlite3.Error as e:
                self.warnings.append(f"SQL {name}: {e}: {stmt.strip()[:60]}")
        self._cols.clear()

    def _norm(self, t: str, d: dict) -> dict:
        c = self.cols(t)
        out = {}
        for k, v in d.items():
            kk = c.get(k.lower())
            if kk is None:
                self.stats["unknown_column"] += 1
                self.unknown_columns.add(f"{t}.{k}")
                continue
            if isinstance(v, str) and v.lower() in ("true", "false"):
                v = 1 if v.lower() == "true" else 0
            elif v == "":
                v = None          # the game stores an empty attribute as NULL
            out[kk] = v
        return out

    def run_xml(self, txt: str, name: str = "") -> None:
        try:
            root = ET.fromstring(txt)
        except ET.ParseError as e:
            self.warnings.append(f"XML {name}: {e}")
            return
        for table in root:
            t = table.tag
            if not isinstance(t, str):
                continue
            if t == "Table":
                self._create_table(table, name)
                continue
            if not self.cols(t):
                self.stats["unknown_table"] += 1
                self.unknown_tables.add(t)
                continue
            for op in table:
                if isinstance(op.tag, str):
                    self._op(t, op, name)

    def _create_table(self, el: ET.Element, name: str) -> None:
        """Schema XML (`<Table name=…><Column name= type= notnull= primarykey= default=/>`)."""
        tname = el.get("name")
        cols, pk = [], []
        for c in el.findall("Column"):
            cn = c.get("name")
            if not cn:
                continue
            d = f'"{cn}" {(c.get("type") or "text").upper()}'
            if (c.get("notnull") or "").lower() == "true":
                d += " NOT NULL"
            dv = c.get("default")
            if dv:                   # an empty default is no default (NULL), as in the game
                d += " DEFAULT " + (dv if re.fullmatch(r"-?\d+(\.\d+)?", dv) else "'" + dv.replace("'", "''") + "'")
            cols.append(d)
            if (c.get("primarykey") or "").lower() == "true":
                pk.append(f'"{cn}"')
        if not tname or not cols:
            self.warnings.append(f"XML {name}: <Table> without a name or columns")
            return
        if pk:
            cols.append(f"PRIMARY KEY({', '.join(pk)})")
        try:
            self.db.execute(f'CREATE TABLE IF NOT EXISTS "{tname}" ({", ".join(cols)})')
        except sqlite3.Error as e:
            self.warnings.append(f"XML {name}: table {tname}: {e}")
        self._cols.clear()

    def _op(self, t: str, op: ET.Element, name: str) -> None:
        q = '"{}"'.format
        try:
            if op.tag in ("Row", "Replace", "InsertOrIgnore"):
                d = self._norm(t, kv(op))
                if not d:
                    return
                verb = {"Row": "INSERT", "Replace": "INSERT OR REPLACE", "InsertOrIgnore": "INSERT OR IGNORE"}[op.tag]
                self.db.execute(f'{verb} INTO "{t}" ({",".join(map(q, d))}) VALUES ({",".join("?" * len(d))})',
                                list(d.values()))
                if t == "Types" and d.get("Type"):
                    self.type_source.setdefault(d["Type"], self.source)
            elif op.tag == "Update":
                w, s = op.find("Where"), op.find("Set")
                wd = self._norm(t, kv(w)) if w is not None else {}
                sd = self._norm(t, kv(s)) if s is not None else {}
                if not sd:
                    return
                ws = " WHERE " + " AND ".join(f"{q(k)}=?" for k in wd) if wd else ""
                self.db.execute(f'UPDATE "{t}" SET {",".join(q(k) + "=?" for k in sd)}{ws}',
                                list(sd.values()) + list(wd.values()))
            elif op.tag == "Delete":
                wd = self._norm(t, kv(op))
                ws = " WHERE " + " AND ".join(f"{q(k)}=?" for k in wd) if wd else ""
                self.db.execute(f'DELETE FROM "{t}"{ws}', list(wd.values()))
            else:
                return
            self.stats[op.tag] += 1
        except sqlite3.Error as e:
            self.stats["failed_ops"] += 1
            if len(self.warnings) < 400:
                self.warnings.append(f"{op.tag} {t} ({name}): {e}")

    def load(self, p: Path) -> None:
        s = p.suffix.lower()
        if s == ".sql":
            self.run_sql(read_text(p), p.name)
        elif s == ".xml":
            self.run_xml(read_text(p), p.name)

    def finish(self) -> list[tuple]:
        fk = self.db.execute("PRAGMA foreign_key_check").fetchall()
        self.db.execute("PRAGMA defer_foreign_keys=OFF")
        self.db.execute("COMMIT")
        self.db.execute("PRAGMA foreign_keys=OFF")
        self.db.row_factory = sqlite3.Row
        return fk


def build_db(root: Path, ruleset: str = RULESET, modes: set[str] | None = None,
             dlc: bool = True) -> tuple[RulesDb, list[Mod], Criteria]:
    rdb = RulesDb()
    base = root / "Base/Assets/Gameplay/Data"
    for sql in ("Schema/01_GameplaySchema.sql", "Schema/02_AddTriggers.sql"):
        rdb.load(base / sql)
    for f in sorted(base.glob("Schema/*.xml")):
        rdb.load(f)
    for f in sorted(base.glob("*.xml")):
        rdb.load(f)
    mods = load_mods(root) if dlc else []
    crit = Criteria(ruleset, {m.id for m in mods}, modes or set())
    for m, p in ordered_files(mods, crit, "UpdateDatabase", rdb.warnings):
        if not p.exists():
            rdb.warnings.append(f"missing file {m.folder}/{p.relative_to(m.dir)} (the game skips it too)")
            continue
        rdb.source = m.folder
        rdb.load(p)
    fk = rdb.finish()
    counts = defaultdict(int)
    for r in fk:
        counts[f"{r[0]}->{r[2]}"] += 1
    for k, n in sorted(counts.items()):
        rdb.warnings.append(f"foreign key {k}: {n} rows")
    if crit.unknown:
        rdb.warnings.append("unknown criteria: " + ", ".join(sorted(crit.unknown)))
    return rdb, mods, crit


# -- localisation ----------------------------------------------------------------------------

ICON_WORDS = {"bullet": "-", "techboosted": "", "civicboosted": "", "exclamation": "", "checkfail": "",
              "checksuccess": "", "powerright": "", "strength": "Combat Strength", "ranged": "Ranged Strength",
              "stat_grievance": "Grievances", "glory_golden_age": "Golden Age", "glory_dark_age": "Dark Age",
              "glory_normal_age": "Normal Age", "bolt": "", "turn": "turns", "visl imited": ""}
ICON = re.compile(r"\[ICON_([A-Za-z0-9_]+)\]\s*", re.IGNORECASE)
PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_]+)(?:\s*:\s*([^{}]*))?\}")


def icon_label(name: str) -> str:
    low = name.lower()
    if low in ICON_WORDS:
        return ICON_WORDS[low]
    for pre in ("resource_", "district_", "unit_", "building_"):
        if low.startswith(pre):
            name = name[len(pre):]
    name = name.replace("GreatWork_", "Great Work ")
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).replace("_", " ")
    return " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in name.split())


def _icon_sub(m: re.Match) -> str:
    label = icon_label(m.group(1))
    rest = m.string[m.end():]
    if not label:
        return "" if m.group(1).lower() != "bullet" else "- "
    ends = {label.split()[0].lower(), label.split()[-1].lower()}
    near = re.findall(r"[A-Za-z]+", rest[:30])[:3]
    if any(w.lower() in ends or any(len(e) > 4 and w.lower().startswith(e[:5]) for e in ends) for w in near):
        return ""        # "+2 [ICON_Science] Science", "[ICON_Favor] Diplomatic Favor": the word follows
    return label + " "


NUMERIC_SLOTS = {"num", "amount", "value", "turns", "tiles", "n", "count", "percent", "actualvalue"}


def unfilled(name: str) -> str:
    """A runtime placeholder the UI fills (`{1_CivName}`): keep it readable, never raw braces."""
    base = re.sub(r"^\d+_?", "", name)
    if not base or base.lower() in NUMERIC_SLOTS:
        return "N"
    return f"[{base}]"


def plural_pick(spec: str, value) -> str:
    """ICU-ish `plural 1?tile; other?tiles;` -> the form for value (or `other`)."""
    forms = dict(re.findall(r"(\w+)\?([^;]*);", spec))
    try:
        n = float(value)
        key = "1" if n == 1 else "other"
    except (TypeError, ValueError):
        key = "other"
    s = forms.get(key, forms.get("other", ""))
    return s.replace("#", str(value)) if value is not None else s.replace("#", "").strip()


def fmt_number(value, spec: str) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    s = str(int(n)) if n.is_integer() else f"{n:g}"
    return ("+" + s) if spec.lstrip().startswith("+") and n >= 0 else s


class Loc:
    """en_US text with the game's layering; returns cleaned, single-line text."""

    def __init__(self) -> None:
        self.raw: dict[str, str] = {}
        self.ops = defaultdict(int)
        self.warnings: list[str] = []

    def load_xml(self, txt: str, language: str = "en_US", name: str = "") -> None:
        try:
            root = ET.fromstring(txt)
        except ET.ParseError as e:
            self.warnings.append(f"text XML {name}: {e}")
            return
        for table in root:
            for op in table:
                if not isinstance(op.tag, str):
                    continue
                src = op.find("Where") if op.tag == "Update" else op
                if src is None:
                    continue
                d = kv(src)
                tag = d.get("Tag")
                if not tag or (d.get("Language") or op.get("Language") or language) != language:
                    continue
                if op.tag == "Delete":
                    self.raw.pop(tag, None)
                else:
                    s = op.find("Set") if op.tag == "Update" else op
                    text = kv(s).get("Text") if s is not None else None
                    if text is None:
                        continue
                    self.raw[tag] = text
                self.ops[op.tag] += 1

    def load_file(self, p: Path) -> None:
        self.load_xml(read_text(p), name=p.name)

    def has(self, key: str | None) -> bool:
        return bool(key) and key in self.raw

    def __call__(self, key: str | None, args: dict | None = None, names=None, depth: int = 0) -> str | None:
        if not key or key not in self.raw:
            return None
        return self.clean(self.raw[key], args, names, depth)

    def clean(self, s: str, args: dict | None = None, names=None, depth: int = 0) -> str:
        args = {k.lower(): v for k, v in (args or {}).items()}

        def ph(m: re.Match) -> str:
            name, spec = m.group(1), (m.group(2) or "").strip()
            if name.startswith("LOC_") and depth < 3:
                return self(name, args, names, depth + 1) or ""
            val = args.get(name.lower())
            if spec.startswith("plural"):
                return plural_pick(spec, val)
            if val is None:
                return unfilled(name)
            if spec.startswith("number"):
                return fmt_number(val, spec[6:])
            if names is not None and isinstance(val, str) and re.fullmatch(r"[A-Z0-9_]+", val):
                return names(val)
            return str(val)

        for _ in range(2):          # placeholders can nest one level ({1: plural ...{2}...})
            s = PLACEHOLDER.sub(ph, s)
        s = s.replace("[NEWLINE]", " ")
        s = ICON.sub(_icon_sub, s)
        s = re.sub(r"\[(?:COLOR[^\]]*|ENDCOLOR|SIZE_\d+|/?i|/?b|STYLE[^\]]*|ENDSTYLE)\]", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?) \1\b", r"\1", s)     # "Faith Faith" left by nested icons
        s = re.sub(r"\s+([.,;:)])", r"\1", s)
        s = re.sub(r"\(\s+", "(", s)
        return re.sub(r"\s{2,}", " ", s).strip()


def build_loc(root: Path, mods: list[Mod], crit: Criteria, warnings: list[str]) -> Loc:
    loc = Loc()
    for f in sorted((root / "Base/Assets/Text/en_US").glob("*.xml")):
        loc.load_file(f)
    missing = 0
    for m, p in ordered_files(mods, crit, "UpdateText", warnings):
        if not p.exists():
            missing += 1       # translations/other languages are not copied from the PC
            continue
        loc.load_file(p)
    if missing:
        warnings.append(f"{missing} UpdateText files not present (other languages / RemoveText outside en_US)")
    return loc


def problems(rdb: RulesDb, loc: Loc) -> list[str]:
    """Signs of a broken extract (a patch renamed a column, a file no longer parses): fatal unless --lenient."""
    out = []
    if rdb.stats.get("failed_ops"):
        out.append(f"{rdb.stats['failed_ops']} XML operations failed (see warnings)")
    if rdb.unknown_columns:
        out.append("unknown columns: " + ", ".join(sorted(rdb.unknown_columns)[:20]))
    if rdb.unknown_tables:
        out.append("unknown tables: " + ", ".join(sorted(rdb.unknown_tables)[:20]))
    out += [w for w in rdb.warnings if w.startswith(("XML ", "SQL "))]
    out += loc.warnings
    return out


# -- rendering helpers -----------------------------------------------------------------------

PREFIXES = ["GREAT_PERSON_INDIVIDUAL_", "GREAT_PERSON_CLASS_", "CIVILIZATION_", "GOVERNMENT_", "IMPROVEMENT_",
            "RANDOM_EVENT_", "COMMEMORATION_", "EMERGENCY_", "PROMOTION_", "BUILDING_", "DISTRICT_", "RESOURCE_",
            "GOVERNOR_", "FEATURE_", "TERRAIN_", "PROJECT_", "VICTORY_", "ALLIANCE_", "MOMENT_", "POLICY_",
            "BELIEF_", "LEADER_", "AGENDA_", "CIVIC_", "TECH_", "UNIT_", "ERA_", "WC_RES_", "SLOT_", "YIELD_"]


def slug(key: str) -> str:
    k = key
    for p in PREFIXES:
        if k.startswith(p):
            k = k[len(p):]
            break
    return re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_")


def pretty_key(key: str) -> str:
    """TRAIT_LEADER_EXPANSIONIST -> Expansionist (fallback when a key has no text)."""
    k = key
    for p in ("TRAIT_LEADER_", "TRAIT_", *PREFIXES):
        if k.startswith(p):
            k = k[len(p):]
            break
    return k.replace("_", " ").capitalize()


def first_sentences(s: str | None, limit: int = 240) -> str:
    if not s:
        return ""
    if len(s) <= limit:
        return s
    cut = s[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > 60 else cut.rstrip() + "…"


def era_label(era: str | None) -> str:
    """"Ancient Era" stays as is; "Ancient" becomes "Ancient era"."""
    if not era:
        return ""
    return era if era.lower().endswith("era") else f"{era} era"


COST_MODELS = {
    "COST_PROGRESSION_NUM_UNDER_AVG_PLUS_TECH": "rises with techs and civics completed; cheaper while you have fewer "
                                                "of these districts than the average civilization",
    "COST_PROGRESSION_GAME_PROGRESS": "rises with game progress (techs and civics completed)",
    "COST_PROGRESSION_PREVIOUS_COPIES": "rises with each copy you already have",
}


# Plain wording for the most common argument-only effects (civic/tech one-time grants).
EFFECT_PHRASES = {
    "ADJUST_PLAYER_GOVERNOR_POINTS": "+{delta} Governor Title",
    "GRANT_INFLUENCE_TOKEN": "+{amount} Envoy(s)",
    "GRANT_SPY": "+{amount} Spy capacity",
    "ADJUST_TRADE_ROUTE_CAPACITY": "+{amount} Trade Route capacity",
    "ADD_PLAYER_FAVOR": "+{amount} Diplomatic Favor",
    "ADJUST_PLAYER_DIPLOMATIC_VICTORY_POINTS": "+{amount} Diplomatic Victory Point(s)",
    "ADJUST_PLAYER_EMBARKED_UNIT_MOVEMENT": "+{amount} Movement for embarked units",
    "ADJUST_UNIT_SEA_MOVEMENT": "+{amount} Movement for naval units",
    "ADJUST_PLAYER_TOURISM": "+{amount}% Tourism",
}


def num(v):
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


class Extractor:
    def __init__(self, rdb: RulesDb, loc: Loc):
        self.db = rdb.db
        self.rdb = rdb
        self.loc = loc
        self.warnings: list[str] = []
        self._names: dict[str, str] = {}
        self._build_names()
        self._build_uniques()

    # -- basic lookups
    def q(self, sql: str, *args) -> list[sqlite3.Row]:
        return self.db.execute(sql, args).fetchall()

    def table_exists(self, t: str) -> bool:
        return bool(self.q("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", t))

    def rows(self, t: str, where: str = "", *args) -> list[sqlite3.Row]:
        if not self.table_exists(t):
            return []
        return self.q(f'SELECT * FROM "{t}"' + (f" WHERE {where}" if where else ""), *args)

    def text(self, key: str | None, args: dict | None = None) -> str:
        return self.loc(key, args, self.name) or ""

    def _build_names(self) -> None:
        tables = [("Technologies", "TechnologyType"), ("Civics", "CivicType"), ("Units", "UnitType"),
                  ("Buildings", "BuildingType"), ("Districts", "DistrictType"), ("Improvements", "ImprovementType"),
                  ("Policies", "PolicyType"), ("Governments", "GovernmentType"), ("Resources", "ResourceType"),
                  ("Features", "FeatureType"), ("Terrains", "TerrainType"), ("Projects", "ProjectType"),
                  ("Civilizations", "CivilizationType"), ("Leaders", "LeaderType"), ("Eras", "EraType"),
                  ("Yields", "YieldType"), ("GreatPersonClasses", "GreatPersonClassType"),
                  ("GreatPersonIndividuals", "GreatPersonIndividualType"), ("Beliefs", "BeliefType"),
                  ("Governors", "GovernorType"), ("GovernorPromotions", "GovernorPromotionType"),
                  ("UnitPromotions", "UnitPromotionType"), ("UnitPromotionClasses", "PromotionClassType"),
                  ("GovernmentSlots", "GovernmentSlotType"), ("BeliefClasses", "BeliefClassType"),
                  ("Agendas", "AgendaType"), ("Victories", "VictoryType"), ("RandomEvents", "RandomEventType"),
                  ("Alliances", "AllianceType"), ("Resolutions", "ResolutionType"), ("Traits", "TraitType"),
                  ("UnitAbilities", "UnitAbilityType")]
        for t, col in tables:
            for r in self.rows(t):
                n = r["Name"] if "Name" in set(r.keys()) else None
                if n and self.loc.has(n):
                    self._names[r[col]] = re.sub(r"\|.*$", "", self.loc(n) or "")

    def name(self, key: str | None) -> str:
        if not key:
            return ""
        return self._names.get(key) or pretty_key(key)

    def names(self, keys) -> list[str]:
        return [self.name(k) for k in keys if k]

    def _build_uniques(self) -> None:
        """TraitType -> owner label ("Rome", "Trajan (Rome)", "Kabul (city-state suzerain)")."""
        civ_level = {r["CivilizationType"]: r["StartingCivilizationLevelType"] for r in self.rows("Civilizations")}
        self.leader_civ: dict[str, list[str]] = defaultdict(list)
        for r in self.rows("CivilizationLeaders"):
            self.leader_civ[r["LeaderType"]].append(r["CivilizationType"])
        self.trait_owner: dict[str, str] = {}
        for r in self.rows("CivilizationTraits"):
            civ = r["CivilizationType"]
            label = self.name(civ)
            if civ_level.get(civ) == "CITY_STATE":
                label += " (city-state suzerain)"
            self.trait_owner.setdefault(r["TraitType"], label)
        for r in self.rows("LeaderTraits"):
            civs = self.leader_civ.get(r["LeaderType"], [])
            if civs and civ_level.get(civs[0]) == "CITY_STATE":
                label = f"{self.name(civs[0])} (city-state suzerain)"
            else:
                label = self.name(r["LeaderType"]) + (f" ({self.name(civs[0])})" if civs else "")
            self.trait_owner.setdefault(r["TraitType"], label)
        self.replaces: dict[str, str] = {}
        for t, a, b in (("UnitReplaces", "CivUniqueUnitType", "ReplacesUnitType"),
                        ("BuildingReplaces", "CivUniqueBuildingType", "ReplacesBuildingType"),
                        ("DistrictReplaces", "CivUniqueDistrictType", "ReplacesDistrictType")):
            for r in self.rows(t):
                self.replaces[r[a]] = r[b]
        # every unique item per trait (units, buildings, districts, improvements)
        self.trait_items: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for t, col, kind in (("Units", "UnitType", "unit"), ("Buildings", "BuildingType", "building"),
                             ("Districts", "DistrictType", "district"), ("Improvements", "ImprovementType", "improvement")):
            for r in self.rows(t, "TraitType IS NOT NULL"):
                self.trait_items[r["TraitType"]].append((kind, r[col]))

    def unique_label(self, key: str, trait: str | None) -> str:
        n = self.name(key)
        if trait and trait in self.trait_owner:
            return f"{n} (unique: {self.trait_owner[trait]})"
        return n

    def yields(self, rows, ycol="YieldType", vcol="YieldChange") -> str:
        parts = []
        for r in rows:
            v = num(r[vcol])
            if v:
                parts.append(f"{'+' if v > 0 else ''}{v} {self.name(r[ycol])}")
        return ", ".join(parts)

    # -- modifiers
    def mod_args(self, mid: str) -> dict:
        return {r["Name"]: r["Value"] for r in self.rows("ModifierArguments", "ModifierId=?", mid)}

    def req_text(self, rsid: str | None) -> str:
        if not rsid:
            return ""
        parts = []
        for r in self.q("SELECT q.RequirementId, q.RequirementType, q.Inverse FROM RequirementSetRequirements s "
                        "JOIN Requirements q ON q.RequirementId=s.RequirementId WHERE s.RequirementSetId=?", rsid):
            args = [self.name(a["Value"]) if re.fullmatch(r"[A-Z][A-Z0-9_]+", str(a["Value"])) else str(a["Value"])
                    for a in self.rows("RequirementArguments", "RequirementId=?", r["RequirementId"])]
            t = r["RequirementType"].removeprefix("REQUIREMENT_").lower().replace("_", " ")
            parts.append(("not " if r["Inverse"] else "") + t + (f" ({', '.join(args)})" if args else ""))
        return "; ".join(parts)

    def modifier_text(self, mid: str, compact_ok: bool = True) -> str:
        """ModifierStrings summary with its arguments filled in, else a compact effect line."""
        args = self.mod_args(mid)
        for r in self.rows("ModifierStrings", "ModifierId=? AND Context IN ('Summary','Preview') "
                           "ORDER BY Context='Preview'", mid):
            t = self.text(r["Text"], args)
            if t and not t[0].islower():          # skip fragments such as "from Emergency"
                return t
        if not compact_ok:
            return ""
        m = self.q("SELECT m.ModifierType, m.SubjectRequirementSetId, d.EffectType, d.CollectionType FROM Modifiers m "
                   "LEFT JOIN DynamicModifiers d ON d.ModifierType=m.ModifierType WHERE m.ModifierId=?", mid)
        if not m:
            return ""
        m = m[0]
        phrase = EFFECT_PHRASES.get((m["EffectType"] or "").removeprefix("EFFECT_"))
        if phrase and not m["SubjectRequirementSetId"]:
            try:
                return phrase.format(**{k.lower(): v for k, v in args.items()})
            except (KeyError, IndexError):
                pass
        eff = (m["EffectType"] or m["ModifierType"] or "").removeprefix("EFFECT_").lower().replace("_", " ")
        coll = (m["CollectionType"] or "").removeprefix("COLLECTION_").lower().replace("_", " ")
        a = ", ".join(f"{k} {self.name(v) if re.fullmatch(r'[A-Z][A-Z0-9_]+', str(v)) else v}" for k, v in args.items())
        s = f"{eff}({a})" + (f" on {coll}" if coll else "")
        cond = self.req_text(m["SubjectRequirementSetId"])
        if cond:
            s += f" [if {cond}]"
        return s if len(s) <= 200 else s[:199] + "…"

    def modifiers_text(self, mids, compact_ok=True) -> list[str]:
        out = []
        for mid in mids:
            t = self.modifier_text(mid, compact_ok)
            if t and t not in out:
                out.append(t)
        return out

    def trait_text(self, trait: str) -> str | None:
        """'Name: description' for a trait with text; None for unique-item or AI traits."""
        r = self.rows("Traits", "TraitType=?", trait)
        if not r:
            return None
        n, d = self.text(r[0]["Name"]), self.text(r[0]["Description"])
        if not n and not d:
            return None
        return f"{n}: {d}" if n and d else (n or d)

    def record(self, kind: str, key: str, name: str | None, summary: str, fields: dict, aliases=()) -> dict:
        name = name or pretty_key(key)
        al = sorted({a for a in (key, *aliases) if a and a != name})

        def keep(v):
            return v not in (None, "", [], {}, 0, False) or v is True

        return {"id": f"{kind}:{slug(key)}", "name": name, "aliases": al, "summary": summary,
                "fields": {k: v for k, v in fields.items() if keep(v) and v is not False}}

    # -- unlock index (what each tech / civic unlocks)
    def unlocks(self, col: str, key: str) -> list[str]:
        out = []
        for t, kcol, label in (("Units", "UnitType", "unit"), ("Buildings", "BuildingType", None),
                               ("Districts", "DistrictType", "district"), ("Improvements", "ImprovementType", "improvement"),
                               ("Projects", "ProjectType", "project"), ("Governments", "GovernmentType", "government"),
                               ("Policies", "PolicyType", "policy")):
            if not self.table_exists(t) or col.lower() not in self.cols(t):
                continue
            for r in self.q(f'SELECT * FROM "{t}" WHERE "{col}"=?', key):
                lab = label or ("wonder" if r["IsWonder"] else "building")
                trait = r["TraitType"] if "TraitType" in set(r.keys()) else None
                owner = self.trait_owner.get(trait) if trait else None
                out.append(f"{self.name(r[kcol])} ({lab}" + (f", unique: {owner}" if owner else "") + ")")
        if col == "PrereqTech":
            for r in self.rows("Resources", "PrereqTech=?", key):
                out.append(f"reveals {self.name(r['ResourceType'])}")
        return out

    def cols(self, t: str) -> dict:
        return self.rdb.cols(t)

    # -- kinds -------------------------------------------------------------------------------

    def _tree(self, kind, table, col, prereq_table, pcol, prcol, boost_col):
        prereqs = defaultdict(list)
        leads = defaultdict(list)
        for r in self.rows(prereq_table):
            prereqs[r[pcol]].append(r[prcol])
            leads[r[prcol]].append(r[pcol])
        boosts = {r[boost_col]: r for r in self.rows("Boosts") if r[boost_col]}
        mods = defaultdict(list)
        mt = {"tech": "TechnologyModifiers", "civic": "CivicModifiers"}[kind]
        for r in self.rows(mt):
            mods[r[col]].append(r["ModifierId"])
        pcolname = {"tech": "PrereqTech", "civic": "PrereqCivic"}[kind]
        obs_units = defaultdict(list)
        ocol = {"tech": "ObsoleteTech", "civic": "ObsoleteCivic"}[kind]
        for r in self.rows("Units", f"{ocol} IS NOT NULL"):
            obs_units[r[ocol]].append(self.name(r["UnitType"]))
        out = []
        for r in self.rows(table):
            k = r[col]
            b = boosts.get(k)
            boost = None
            if b:
                trig = self.text(b["TriggerDescription"])
                boost = f"{trig} ({b['Boost']}%)" if trig else None
            unl = self.unlocks(pcolname, k)
            effects = self.modifiers_text(mods.get(k, []))
            desc = self.text(r["Description"])
            fields = {"era": self.name(r["EraType"]), "cost": r["Cost"],
                      "prerequisites": self.names(prereqs.get(k, [])), "leads_to": self.names(leads.get(k, [])),
                      ("eureka" if kind == "tech" else "inspiration"): boost, "unlocks": unl,
                      "effects": effects, "obsoletes_units": obs_units.get(k), "description": desc,
                      "repeatable": bool(r["Repeatable"])}
            summ = f"{era_label(fields['era'])}, cost {r['Cost']}."
            if boost:
                summ += f" {'Eureka' if kind == 'tech' else 'Inspiration'}: {boost}."
            if unl:
                summ += " Unlocks " + ", ".join(unl[:6]) + ("…" if len(unl) > 6 else "") + "."
            out.append(self.record(kind, k, self.name(k), summ, fields))
        return out

    def tech(self):
        return self._tree("tech", "Technologies", "TechnologyType", "TechnologyPrereqs", "Technology", "PrereqTech",
                          "TechnologyType")

    def civic(self):
        return self._tree("civic", "Civics", "CivicType", "CivicPrereqs", "Civic", "PrereqCivic", "CivicType")

    def _requires(self, r) -> list[str]:
        out = []
        keys = r.keys()
        for c in ("PrereqTech", "PrereqCivic", "PrereqDistrict"):
            if c in keys and r[c]:
                out.append(self.name(r[c]))
        return out

    def unit(self):
        xp2 = {r["UnitType"]: r for r in self.rows("Units_XP2")}
        up = defaultdict(list)
        for r in self.rows("UnitUpgrades"):
            up[r["Unit"]].append(r["UpgradeUnit"])
        out = []
        for r in self.rows("Units"):
            k = r["UnitType"]
            x = xp2.get(k)
            res_cost = None
            if x is not None and x["ResourceCost"] and r["StrategicResource"]:
                res_cost = f"{x['ResourceCost']} {self.name(r['StrategicResource'])}"
            elif r["StrategicResource"]:
                res_cost = self.name(r["StrategicResource"])
            upkeep = None
            if x is not None and x["ResourceMaintenanceAmount"] and x["ResourceMaintenanceType"]:
                upkeep = f"{x['ResourceMaintenanceAmount']} {self.name(x['ResourceMaintenanceType'])}/turn"
            owner = self.trait_owner.get(r["TraitType"]) if r["TraitType"] else None
            buy = (r["PurchaseYield"] or "").removeprefix("YIELD_").lower() or "none"
            fields = {
                "unique_to": owner, "replaces": self.name(self.replaces.get(k)) if k in self.replaces else None,
                "class": self.name(r["PromotionClass"]) if r["PromotionClass"] else None,
                "domain": (r["Domain"] or "").removeprefix("DOMAIN_").lower(),
                "combat": r["Combat"], "ranged": r["RangedCombat"], "range": r["Range"], "bombard": r["Bombard"],
                "anti_air": r["AntiAirCombat"], "moves": r["BaseMoves"], "sight": r["BaseSightRange"],
                "cost": r["Cost"], "purchase": buy, "must_purchase": bool(r["MustPurchase"]),
                "maintenance": r["Maintenance"], "resource_cost": res_cost, "resource_upkeep": upkeep,
                "requires": self._requires(r), "upgrades_to": self.names(up.get(k, [])),
                "obsolete_with": self.names([r["ObsoleteTech"], r["ObsoleteCivic"]]),
                "can_train": "no" if not r["CanTrain"] else None,
                "charges": r["BuildCharges"] or r["SpreadCharges"] or None,
                "description": self.text(r["Description"]),
            }
            summ = self._unit_summary(r, owner, fields)
            out.append(self.record("unit", k, self.name(k), summ, fields))
        return out

    def _unit_summary(self, r, owner, f) -> str:
        bits = []
        if owner:
            bits.append(f"Unique to {owner}" + (f", replaces {f['replaces']}" if f["replaces"] else ""))
        stats = []
        if r["Combat"]:
            stats.append(f"{r['Combat']} strength")
        if r["RangedCombat"]:
            stats.append(f"{r['RangedCombat']} ranged")
        if r["Bombard"]:
            stats.append(f"{r['Bombard']} bombard")
        stats.append(f"{r['BaseMoves']} moves")
        stats.append(f"cost {r['Cost']}")
        bits.append(", ".join(stats))
        if f["requires"]:
            bits.append("requires " + ", ".join(f["requires"]))
        return "; ".join(bits) + "."

    def _building_rows(self, wonder: bool):
        yc = defaultdict(list)
        for r in self.rows("Building_YieldChanges"):
            yc[r["BuildingType"]].append(r)
        gpp = defaultdict(list)
        for r in self.rows("Building_GreatPersonPoints"):
            gpp[r["BuildingType"]].append(f"+{r['PointsPerTurn']} {self.name(r['GreatPersonClassType'])}")
        gw = defaultdict(list)
        for r in self.rows("Building_GreatWorks"):
            gw[r["BuildingType"]].append(f"{r['NumSlots']} {r['GreatWorkSlotType'].removeprefix('GREATWORKSLOT_').lower()}")
        pre = defaultdict(list)
        for r in self.rows("BuildingPrereqs"):
            pre[r["Building"]].append(r["PrereqBuilding"])
        excl = defaultdict(list)
        for r in self.rows("MutuallyExclusiveBuildings"):
            excl[r["Building"]].append(r["MutuallyExclusiveBuilding"])
        xp2 = {r["BuildingType"]: r for r in self.rows("Buildings_XP2")}
        terr = defaultdict(list)
        for r in self.rows("Building_ValidTerrains"):
            terr[r["BuildingType"]].append(r["TerrainType"])
        feat = defaultdict(list)
        for r in self.rows("Building_ValidFeatures"):
            feat[r["BuildingType"]].append(r["FeatureType"])
        return [(r, yc, gpp, gw, pre, excl, xp2, terr, feat) for r in self.rows("Buildings", "IsWonder=?", int(wonder))]

    def building(self):
        out = []
        for r, yc, gpp, gw, pre, excl, xp2, _, _ in self._building_rows(False):
            k = r["BuildingType"]
            owner = self.trait_owner.get(r["TraitType"]) if r["TraitType"] else None
            x = xp2.get(k)
            fields = {
                "unique_to": owner, "replaces": self.name(self.replaces.get(k)) if k in self.replaces else None,
                "district": self.name(r["PrereqDistrict"]), "cost": r["Cost"], "maintenance": r["Maintenance"],
                "yields": self.yields(yc.get(k, [])), "housing": r["Housing"], "amenities": r["Entertainment"],
                "citizen_slots": r["CitizenSlots"], "great_person_points": gpp.get(k),
                "great_work_slots": gw.get(k), "power_required": x["RequiredPower"] if x is not None else None,
                "requires": self.names([r["PrereqTech"], r["PrereqCivic"]]),
                "requires_buildings": self.names(pre.get(k, [])),
                "exclusive_with": self.names(excl.get(k, [])),
                "purchase": (r["PurchaseYield"] or "").removeprefix("YIELD_").lower() or "none",
                "must_purchase": bool(r["MustPurchase"]), "internal_only": bool(r["InternalOnly"]),
                "effect": self.text(r["Description"]),
            }
            summ = (f"Unique to {owner}. " if owner else "") + (f"{fields['district']} building, " if fields["district"] else "") + \
                f"cost {r['Cost']}" + (f"; {fields['yields']}" if fields["yields"] else "") + "."
            out.append(self.record("building", k, self.name(k), summ, fields))
        return out

    def wonder(self):
        out = []
        for r, yc, gpp, gw, pre, excl, xp2, terr, feat in self._building_rows(True):
            k = r["BuildingType"]
            era = None
            if r["PrereqTech"]:
                era = self.q("SELECT EraType FROM Technologies WHERE TechnologyType=?", r["PrereqTech"])
            elif r["PrereqCivic"]:
                era = self.q("SELECT EraType FROM Civics WHERE CivicType=?", r["PrereqCivic"])
            place = []
            if terr.get(k):
                place.append("on " + "/".join(self.names(terr[k])))
            if feat.get(k):
                place.append("on " + "/".join(self.names(feat[k])))
            if r["AdjacentDistrict"]:
                place.append("adjacent to " + self.name(r["AdjacentDistrict"]))
            if r["RequiresRiver"] or r["RequiresAdjacentRiver"]:
                place.append("next to a river")
            if r["Coast"]:
                place.append("on coast")
            if r["AdjacentToMountain"]:
                place.append("adjacent to a mountain")
            if r["AdjacentResource"]:
                place.append("adjacent to " + self.name(r["AdjacentResource"]))
            if r["AdjacentImprovement"]:
                place.append("adjacent to " + self.name(r["AdjacentImprovement"]))
            fields = {"era": self.name(era[0][0]) if era else None, "cost": r["Cost"],
                      "requires": self.names([r["PrereqTech"], r["PrereqCivic"]]),
                      "placement": "; ".join(place) or None, "district": self.name(r["PrereqDistrict"]) or None,
                      "yields": self.yields(yc.get(k, [])), "great_person_points": gpp.get(k),
                      "great_work_slots": gw.get(k), "housing": r["Housing"], "amenities": r["Entertainment"],
                      "effect": self.text(r["Description"])}
            summ = f"{era_label(fields['era'])} wonder, cost {r['Cost']}. " + first_sentences(fields["effect"], 200)
            out.append(self.record("wonder", k, self.name(k), summ.strip(), fields))
        return out

    def adjacency_lines(self, ids) -> list[str]:
        """Group Adjacency_YieldChanges rows into readable lines ("+1 Science per adjacent Mountain")."""
        groups: dict[tuple, list[str]] = {}
        for yid in ids:
            rr = self.rows("Adjacency_YieldChanges", "ID=?", yid)
            if not rr:
                continue
            r = rr[0]
            if r["OtherDistrictAdjacent"]:
                what = "district"
            elif r["AdjacentTerrain"]:
                what = self.name(r["AdjacentTerrain"])
                what = "Mountain" if "Mountain" in what else what
            elif r["AdjacentFeature"]:
                what = self.name(r["AdjacentFeature"])
            elif r["AdjacentRiver"]:
                what = "River"
            elif r["AdjacentNaturalWonder"]:
                what = "natural wonder"
            elif r["AdjacentWonder"]:
                what = "wonder"
            elif r["AdjacentDistrict"]:
                what = self.name(r["AdjacentDistrict"])
            elif r["AdjacentImprovement"]:
                what = self.name(r["AdjacentImprovement"])
            elif r["AdjacentResource"]:
                what = "resource"
            elif r["AdjacentSeaResource"]:
                what = "sea resource"
            elif r["AdjacentResourceClass"] and r["AdjacentResourceClass"] != "NO_RESOURCECLASS":
                what = r["AdjacentResourceClass"].removeprefix("RESOURCECLASS_").lower() + " resource"
            elif r["Self"]:
                what = "self"
            else:
                what = self.text(r["Description"]) or yid
            cond = []
            if r["PrereqTech"] or r["PrereqCivic"]:
                cond.append("with " + self.name(r["PrereqTech"] or r["PrereqCivic"]))
            if r["ObsoleteTech"] or r["ObsoleteCivic"]:
                cond.append("until " + self.name(r["ObsoleteTech"] or r["ObsoleteCivic"]))
            gk = (r["YieldType"], num(r["YieldChange"]), r["TilesRequired"], bool(r["Self"]), tuple(cond),
                  what if (r["TilesRequired"] or 1) > 1 else "")   # "per 2" counts each kind separately
            groups.setdefault(gk, [])
            if what not in groups[gk]:
                groups[gk].append(what)
        out = []
        for (y, amt, tiles, is_self, cond, _), whats in groups.items():
            yn = self.name(y)
            sign = "+" if amt >= 0 else ""
            w = " or ".join(whats)
            if is_self:
                line = f"{sign}{amt} {yn} ({w})"
            elif tiles and tiles > 1:
                unit = "districts" if w == "district" else f"{w} tiles"
                line = f"{sign}{amt} {yn} per {tiles} adjacent {unit}"
            else:
                line = f"{sign}{amt} {yn} per adjacent {w}"
            if cond:
                line += " (" + ", ".join(cond) + ")"
            out.append(line)
        return out

    def district(self):
        adj = defaultdict(list)
        for r in self.rows("District_Adjacencies"):
            adj[r["DistrictType"]].append(r["YieldChangeId"])
        gpp = defaultdict(list)
        for r in self.rows("District_GreatPersonPoints"):
            gpp[r["DistrictType"]].append(f"+{r['PointsPerTurn']} {self.name(r['GreatPersonClassType'])}")
        trade = defaultdict(list)
        for r in self.rows("District_TradeRouteYields"):
            parts = []
            for c, lab in (("YieldChangeAsOrigin", "origin"), ("YieldChangeAsDomesticDestination", "domestic dest."),
                           ("YieldChangeAsInternationalDestination", "international dest.")):
                if r[c]:
                    parts.append(f"+{num(r[c])} {lab}")
            if parts:
                trade[r["DistrictType"]].append(f"{self.name(r['YieldType'])}: " + ", ".join(parts))
        cit = defaultdict(list)
        for r in self.rows("District_CitizenYieldChanges"):
            cit[r["DistrictType"]].append(r)
        blds = defaultdict(list)
        for r in self.rows("Buildings", "IsWonder=0 AND PrereqDistrict IS NOT NULL"):
            blds[r["PrereqDistrict"]].append(self.unique_label(r["BuildingType"], r["TraitType"]))
        xp2 = {r["DistrictType"]: r for r in self.rows("Districts_XP2")}
        out = []
        for r in self.rows("Districts"):
            k = r["DistrictType"]
            owner = self.trait_owner.get(r["TraitType"]) if r["TraitType"] else None
            rep = self.replaces.get(k)
            ids = adj.get(k) or (adj.get(rep, []) if rep else [])
            x = xp2.get(k)
            prog = None
            if r["CostProgressionModel"] and r["CostProgressionModel"] != "NO_COST_PROGRESSION":
                prog = COST_MODELS.get(r["CostProgressionModel"],
                                       r["CostProgressionModel"].removeprefix("COST_PROGRESSION_").lower().replace("_", " "))
            fields = {
                "unique_to": owner, "replaces": self.name(rep) if rep else None, "cost": r["Cost"],
                "cost_progression": prog, "requires": self.names([r["PrereqTech"], r["PrereqCivic"]]),
                "requires_population": r["RequiresPopulation"] and "yes" or None,
                "adjacency": self.adjacency_lines(ids), "buildings": blds.get(k) or blds.get(rep),
                "housing": r["Housing"], "amenities": r["Entertainment"], "appeal": r["Appeal"],
                "great_person_points": gpp.get(k), "trade_route_yields": trade.get(k),
                "citizen_yields": self.yields(cit.get(k, [])), "one_per_city": bool(r["OnePerCity"]),
                "one_per_river": bool(x["OnePerRiver"]) if x is not None else None,
                "no_adjacent_city_center": bool(r["NoAdjacentCity"]), "coast": bool(r["Coast"]),
                "effect": self.text(r["Description"]),
            }
            summ = (f"Unique to {owner}, replaces {self.name(rep)}. " if owner and rep else "") + \
                f"Base cost {r['Cost']}" + (" (rises with game progress)" if prog else "") + "."
            if fields["adjacency"]:
                summ += " Adjacency: " + "; ".join(fields["adjacency"][:3]) + ("…" if len(fields["adjacency"]) > 3 else "") + "."
            out.append(self.record("district", k, self.name(k), summ, fields))
        return out

    def adjacency_data(self) -> dict:
        """The district adjacency rules as data, for a placement scorer (levers design, ruling 30):
        `Adjacency_YieldChanges` and `District_Adjacencies` rows with the game's own column names (NULL,
        0 and false columns left out), `DistrictReplaces`, each placed district's placement flags, and the
        facts the rules refer to (resource classes, natural wonder features). Written as
        `data/_adjacency.json`: not a record file."""
        def rows(table: str) -> list[dict]:
            return [dict(r) for r in self.rows(table)]      # sqlite3.Row's `in` tests values, a dict's keys

        def given(r: dict) -> dict:
            return {k: v for k, v in r.items() if v not in (None, 0, "")}
        districts = {}
        for r in rows("Districts"):
            if r.get("RequiresPlacement", 1):
                districts[r["DistrictType"]] = {k: True for k in ("Coast", "NoAdjacentCity", "Aqueduct", "AdjacentToLand",
                                                                  "OnePerCity", "CityCenter") if r.get(k)}
        return {
            "Adjacency_YieldChanges": [given(r) for r in sorted(rows("Adjacency_YieldChanges"), key=lambda r: r["ID"])],
            "District_Adjacencies": [given(r) for r in sorted(rows("District_Adjacencies"),
                                                              key=lambda r: (r["DistrictType"], r["YieldChangeId"]))],
            "DistrictReplaces": {r["CivUniqueDistrictType"]: r["ReplacesDistrictType"] for r in rows("DistrictReplaces")},
            "Districts": dict(sorted(districts.items())),
            "District_ValidTerrains": [given(r) for r in rows("District_ValidTerrains")],
            "ResourceClasses": {r["ResourceType"]: r["ResourceClassType"] for r in rows("Resources")
                                if r.get("ResourceClassType")},
            "NaturalWonders": sorted(r["FeatureType"] for r in rows("Features") if r.get("NaturalWonder")),
        }

    def improvement(self):
        yc = defaultdict(list)
        for r in self.rows("Improvement_YieldChanges"):
            yc[r["ImprovementType"]].append(r)
        adj = defaultdict(list)
        for r in self.rows("Improvement_Adjacencies"):
            adj[r["ImprovementType"]].append(r["YieldChangeId"])
        valid = defaultdict(list)
        for t, c in (("Improvement_ValidTerrains", "TerrainType"), ("Improvement_ValidFeatures", "FeatureType"),
                     ("Improvement_ValidResources", "ResourceType")):
            for r in self.rows(t):
                valid[r["ImprovementType"]].append(self.name(r[c]))
        units = defaultdict(list)
        for r in self.rows("Improvement_ValidBuildUnits"):
            units[r["ImprovementType"]].append(self.name(r["UnitType"]))
        bonus = defaultdict(list)
        for r in self.rows("Improvement_BonusYieldChanges"):
            bonus[r["ImprovementType"]].append(
                f"+{num(r['BonusYieldChange'])} {self.name(r['YieldType'])} with {self.name(r['PrereqTech'] or r['PrereqCivic'])}")
        tour = defaultdict(list)
        for r in self.rows("Improvement_Tourism"):
            tour[r["ImprovementType"]].append(
                r["TourismSource"].removeprefix("TOURISMSOURCE_").lower().replace("_", " ") +
                (f" with {self.name(r['PrereqTech'] or r['PrereqCivic'])}" if r["PrereqTech"] or r["PrereqCivic"] else ""))
        out = []
        for r in self.rows("Improvements"):
            k = r["ImprovementType"]
            owner = self.trait_owner.get(r["TraitType"]) if r["TraitType"] else None
            fields = {"unique_to": owner, "yields": self.yields(yc.get(k, [])),
                      "adjacency": self.adjacency_lines(adj.get(k, [])), "valid_on": valid.get(k),
                      "requires": self.names([r["PrereqTech"], r["PrereqCivic"]]),
                      "built_by": units.get(k), "bonus_yields": bonus.get(k), "tourism": tour.get(k),
                      "housing": r["Housing"], "appeal": r["Appeal"], "one_per_city": bool(r["OnePerCity"]),
                      "buildable": "no" if not r["Buildable"] else None,
                      "effect": self.text(r["Description"])}
            summ = (f"Unique to {owner}. " if owner else "") + \
                (f"{fields['yields']}." if fields["yields"] else first_sentences(fields["effect"], 160) or "No base yield.")
            if fields["adjacency"]:
                summ += " Adjacency: " + "; ".join(fields["adjacency"][:2]) + "."
            out.append(self.record("improvement", k, self.name(k), summ, fields))
        return out

    def policy(self):
        obs = defaultdict(list)
        for r in self.rows("ObsoletePolicies"):
            obs[r["PolicyType"]].append(r["ObsoletePolicy"])
        xp1 = {r["PolicyType"]: r for r in self.rows("Policies_XP1")}
        out = []
        for r in self.rows("Policies"):
            k = r["PolicyType"]
            x = xp1.get(k)
            age = None
            if x is not None:
                age = "Dark Age only" if x["RequiresDarkAge"] else ("Golden Age only" if x["RequiresGoldenAge"] else None)
            slot = self.name(r["GovernmentSlotType"])
            desc = self.text(r["Description"])
            fields = {"slot": slot, "requires": self.names([r["PrereqCivic"], r["PrereqTech"]]),
                      "obsoleted_by": self.names(obs.get(k, [])), "age": age, "effect": desc}
            out.append(self.record("policy", k, self.name(k), f"{slot} card. {desc}".strip(), fields))
        return out

    def government(self):
        slots = defaultdict(list)
        for r in self.rows("Government_SlotCounts"):
            if r["NumSlots"]:
                slots[r["GovernmentType"]].append(f"{r['NumSlots']} {self.name(r['GovernmentSlotType'])}")
        mods = defaultdict(list)
        for r in self.rows("GovernmentModifiers"):
            mods[r["GovernmentType"]].append(r["ModifierId"])
        out = []
        for r in self.rows("Governments"):
            k = r["GovernmentType"]
            fields = {"tier": (r["Tier"] or "").removeprefix("TIER_").lower() or None,
                      "requires": self.names([r["PrereqCivic"]]), "slots": slots.get(k),
                      "inherent_bonus": self.text(r["InherentBonusDesc"]),
                      "legacy_bonus": self.text(r["AccumulatedBonusDesc"]) or self.text(r["AccumulatedBonusShortDesc"])}
            summ = ", ".join(slots.get(k, [])) + (". " + fields["inherent_bonus"] if fields["inherent_bonus"] else "")
            out.append(self.record("government", k, self.name(k), summ.strip(), fields))
        return out

    def great_person(self):
        amods = defaultdict(list)
        for r in self.rows("GreatPersonIndividualActionModifiers"):
            amods[r["GreatPersonIndividualType"]].append(r["ModifierId"])
        bmods = defaultdict(list)
        for r in self.rows("GreatPersonIndividualBirthModifiers"):
            bmods[r["GreatPersonIndividualType"]].append(r["ModifierId"])
        works = defaultdict(list)
        for r in self.rows("GreatWorks", "GreatPersonIndividualType IS NOT NULL"):
            works[r["GreatPersonIndividualType"]].append(self.text(r["Name"]) or pretty_key(r["GreatWorkType"]))
        out = []
        for r in self.rows("GreatPersonIndividuals"):
            k = r["GreatPersonIndividualType"]
            action = self.text(r["ActionEffectTextOverride"]) if r["ActionEffectTextOverride"] else ""
            if not action:
                action = " ".join(self.modifiers_text(amods.get(k, []), compact_ok=False))
            if not action and works.get(k):
                action = ("Creates a Great Work: " if len(works[k]) == 1 else "Creates Great Works: ") + \
                    ", ".join(works[k]) + "."
            if not action:
                cu = self.q("SELECT u.Description FROM GreatPersonClasses c JOIN Units u ON u.UnitType=c.UnitType "
                            "WHERE c.GreatPersonClassType=?", r["GreatPersonClassType"])
                action = self.text(cu[0][0]) if cu and not amods.get(k) else ""
            compact = []
            if not action and amods.get(k):
                compact = self.modifiers_text(amods[k])
            passive = self.text(r["BirthEffectTextOverride"]) if r["BirthEffectTextOverride"] else ""
            if not passive and bmods.get(k):
                passive = " ".join(self.modifiers_text(bmods[k], compact_ok=False))
            req = []
            for c in list(r.keys()):
                if c.startswith("ActionRequires") and r[c] and c != "ActionRequiresGoldCost":
                    v = r[c]
                    lab = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", c.removeprefix("ActionRequires")).lower()
                    req.append(lab if v in (1, "1", True) else f"{lab}: {self.name(v) if isinstance(v, str) else v}")
            cls = self.name(r["GreatPersonClassType"])
            fields = {"class": cls, "era": self.name(r["EraType"]), "charges": r["ActionCharges"],
                      "action": action or None, "action_modifiers": compact or None, "passive": passive or None,
                      "action_requires": req or None, "great_works": works.get(k)}
            summ = f"{cls}, {era_label(fields['era'])}. " + first_sentences(action or passive or "; ".join(compact), 200)
            out.append(self.record("great_person", k, self.name(k), summ.strip(), fields))
        return out

    def belief(self):
        out = []
        for r in self.rows("Beliefs"):
            k = r["BeliefType"]
            cls = self.name(r["BeliefClassType"])
            d = self.text(r["Description"])
            out.append(self.record("belief", k, self.name(k), f"{cls}: {d}", {"class": cls, "effect": d}))
        return out

    def governor(self):
        promos = defaultdict(list)
        for r in self.rows("GovernorPromotionSets"):
            promos[r["GovernorType"]].append(r["GovernorPromotion"])
        pre = defaultdict(list)
        for r in self.rows("GovernorPromotionPrereqs"):
            pre[r["GovernorPromotionType"]].append(r["PrereqGovernorPromotion"])
        prow = {r["GovernorPromotionType"]: r for r in self.rows("GovernorPromotions")}
        out = []
        for r in self.rows("Governors"):
            k = r["GovernorType"]
            lines, base = [], None
            for p in sorted(promos.get(k, []), key=lambda p: (prow[p]["Level"], prow[p]["Column"]) if p in prow else (9, 9)):
                pr = prow.get(p)
                if pr is None:
                    continue
                t = f"{self.text(pr['Name'])}: {self.text(pr['Description'])}"
                if pr["BaseAbility"]:
                    base = t
                    continue
                req = self.names(pre.get(p, []))
                lines.append(f"Tier {pr['Level']} {t}" + (f" (after {' or '.join(req)})" if req else ""))
            title = self.text(r["Title"])
            fields = {"title": title, "base_ability": base, "promotions": lines,
                      "assign_to_city_state": bool(r["AssignCityState"]) or None,
                      "description": self.text(r["Description"])}
            n = self.name(k)
            out.append(self.record("governor", k, n, f"{title}. {base or ''}".strip(), fields, [title]))
        return out

    def promotion(self):
        pre = defaultdict(list)
        for r in self.rows("UnitPromotionPrereqs"):
            pre[r["UnitPromotion"]].append(r["PrereqUnitPromotion"])
        out = []
        for r in self.rows("UnitPromotions"):
            k = r["UnitPromotionType"]
            cls = self.name(r["PromotionClass"])
            d = self.text(r["Description"])
            fields = {"class": cls, "tier": r["Level"], "requires": self.names(pre.get(k, [])), "effect": d}
            out.append(self.record("promotion", k, self.name(k), f"{cls} tier {r['Level']}: {d}", fields))
        return out

    def resource(self):
        yc = defaultdict(list)
        for r in self.rows("Resource_YieldChanges"):
            yc[r["ResourceType"]].append(r)
        imp = defaultdict(list)
        for r in self.rows("Improvement_ValidResources"):
            imp[r["ResourceType"]].append(self.name(r["ImprovementType"]))
        harv = defaultdict(list)
        for r in self.rows("Resource_Harvests"):
            harv[r["ResourceType"]].append(f"{r['Amount']} {self.name(r['YieldType'])}" +
                                           (f" (with {self.name(r['PrereqTech'])})" if r["PrereqTech"] else ""))
        cons = {r["ResourceType"]: r for r in self.rows("Resource_Consumption")}
        out = []
        for r in self.rows("Resources"):
            k = r["ResourceType"]
            cls = (r["ResourceClassType"] or "").removeprefix("RESOURCECLASS_").lower()
            c = cons.get(k)
            acc = None
            if c is not None and c["Accumulate"]:
                acc = (f"+{c['ImprovedExtractionRate']} per turn per improved source" +
                       (f", +{c['BaseExtractionRate']} unimproved" if c["BaseExtractionRate"] else "") +
                       "; stockpile capped (cap rises by era)")
            fields = {"class": cls, "yields": self.yields(yc.get(k, [])), "improvement": imp.get(k),
                      "revealed_by": self.names([r["PrereqTech"], r["PrereqCivic"]]),
                      "amenities": r["Happiness"] if cls == "luxury" else None, "accumulation": acc,
                      "power": (f"{c['PowerProvided']} power per unit" if c is not None and c["PowerProvided"] else None),
                      "harvest": harv.get(k)}
            summ = f"{cls.capitalize()} resource" + (f": {fields['yields']}" if fields["yields"] else "") + \
                (f"; improved by {', '.join(imp[k])}" if imp.get(k) else "") + "."
            out.append(self.record("resource", k, self.name(k), summ, fields))
        return out

    def feature(self):
        yc = defaultdict(list)
        for r in self.rows("Feature_YieldChanges"):
            yc[r["FeatureType"]].append(r)
        ay = defaultdict(list)
        for r in self.rows("Feature_AdjacentYields"):
            ay[r["FeatureType"]].append(r)
        out = []
        for r in self.rows("Features"):
            k = r["FeatureType"]
            fields = {"natural_wonder": bool(r["NaturalWonder"]), "yields": self.yields(yc.get(k, [])),
                      "adjacent_yields": self.yields(ay.get(k, [])), "movement_cost": r["MovementChange"],
                      "defense": r["DefenseModifier"], "appeal": r["Appeal"], "impassable": bool(r["Impassable"]),
                      "removable": bool(r["Removable"]), "fresh_water": bool(r["AddsFreshWater"]),
                      "tiles": r["Tiles"] if r["NaturalWonder"] else None, "description": self.text(r["Description"])}
            summ = ("Natural wonder. " if r["NaturalWonder"] else "") + (fields["yields"] or "no yield change") + "."
            if fields["description"]:
                summ += " " + first_sentences(fields["description"], 160)
            out.append(self.record("feature", k, self.name(k), summ, fields))
        return out

    def terrain(self):
        yc = defaultdict(list)
        for r in self.rows("Terrain_YieldChanges"):
            yc[r["TerrainType"]].append(r)
        out = []
        for r in self.rows("Terrains"):
            k = r["TerrainType"]
            fields = {"yields": self.yields(yc.get(k, [])), "movement_cost": r["MovementCost"],
                      "defense": r["DefenseModifier"], "appeal": r["Appeal"], "hills": bool(r["Hills"]),
                      "mountain": bool(r["Mountain"]), "water": bool(r["Water"]), "impassable": bool(r["Impassable"])}
            out.append(self.record("terrain", k, self.name(k), (fields["yields"] or "no yield") + ".", fields))
        return out

    def project(self):
        conv = defaultdict(list)
        for r in self.rows("Project_YieldConversions"):
            conv[r["ProjectType"]].append(f"{r['PercentOfProductionRate']}% of production as {self.name(r['YieldType'])}")
        gpp = defaultdict(list)
        for r in self.rows("Project_GreatPersonPoints"):
            gpp[r["ProjectType"]].append(f"{r['Points']} {self.name(r['GreatPersonClassType'])}")
        mods = defaultdict(list)
        for r in self.rows("ProjectCompletionModifiers"):
            mods[r["ProjectType"]].append(r["ModifierId"])
        out = []
        for r in self.rows("Projects"):
            k = r["ProjectType"]
            d = self.text(r["Description"])
            fields = {"district": self.name(r["PrereqDistrict"]) or None, "cost": r["Cost"],
                      "requires": self.names([r["PrereqTech"], r["PrereqCivic"]]),
                      "requires_building": self.name(r["RequiredBuilding"]) or None,
                      "space_race": bool(r["SpaceRace"]), "yield_conversion": conv.get(k),
                      "great_person_points": gpp.get(k), "max_per_player": r["MaxPlayerInstances"] if r["MaxPlayerInstances"] and r["MaxPlayerInstances"] > 0 else None,
                      "effect": d or "; ".join(self.modifiers_text(mods.get(k, [])))}
            summ = (f"{fields['district']} project, " if fields["district"] else "") + f"cost {r['Cost']}. " + first_sentences(d, 180)
            out.append(self.record("project", k, self.name(k), summ.strip(), fields))
        return out

    def emergency(self):
        rewards = defaultdict(list)
        for r in self.rows("EmergencyRewards"):
            t = self.text(r["Description"]) or self.modifier_text(r["ModifierID"], compact_ok=False)
            if t:
                who = "first place" if r["FirstPlace"] else ("top tier" if r["TopTier"] else ("bottom tier" if r["BottomTier"] else "members"))
                rewards[r["EmergencyType"]].append(f"{'success' if r['OnSuccess'] else 'failure'}, {who}: {t}")
        buffs = defaultdict(list)
        for r in self.rows("EmergencyBuffs"):
            t = self.text(r["Description"]) or self.modifier_text(r["ModifierID"], compact_ok=False)
            if t:
                buffs[r["EmergencyType"]].append(t)
        xp2 = {r["EmergencyType"]: r for r in self.rows("Emergencies_XP2")}
        out = []
        for r in self.rows("EmergencyAlliances"):
            k = r["EmergencyType"]
            x = xp2.get(k)
            name = self.text(r["Name"]) or pretty_key(k)
            et = self.rows("EmergencyTexts", "Type=?", r["EmergencyText"])
            gt = self.rows("EmergencyGoalTexts", "GoalType=?", r["GoalText"])
            trig = (r["Trigger"] or "").removeprefix("EMERGENCY_TRIGGER_").lower().replace("_", " ")
            fields = {"trigger": trig if trig and trig != "none" else None,
                      "description": self.text(et[0]["Description"]) if et else None,
                      "goal": self.text(gt[0]["GoalDescription"]) if gt else None,
                      "duration": r["Duration"], "hostile": bool(x["Hostile"]) if x is not None else None,
                      "buffs_while_active": buffs.get(k), "rewards": rewards.get(k)}
            out.append(self.record("emergency", k, name, first_sentences(fields["description"] or fields["goal"] or "", 220), fields))
        return out

    def resolution(self):
        out = []
        for r in self.rows("Resolutions"):
            k = r["ResolutionType"]
            a, b = self.text(r["Effect1Description"]), self.text(r["Effect2Description"])
            fields = {"target": (r["TargetKind"] or "").removeprefix("KIND_").lower(),
                      "earliest_era": self.name(r["EarliestEra"]) or None, "latest_era": self.name(r["LatestEra"]) or None,
                      "option_a": a, "option_b": b}
            out.append(self.record("resolution", k, self.name(k) or self.text(r["Name"]), f"A: {a} B: {b}", fields))
        return out

    def dedication(self):
        out = []
        for r in self.rows("CommemorationTypes"):
            k = r["CommemorationType"]
            name = self.text(r["CategoryDescription"]) or pretty_key(k)
            fields = {"golden_age": self.text(r["GoldenAgeBonusDescription"]),
                      "normal_age": self.text(r["NormalAgeBonusDescription"]),
                      "dark_age": self.text(r["DarkAgeBonusDescription"]),
                      "eras": " to ".join(self.names([r["MinimumGameEra"], r["MaximumGameEra"]]))}
            out.append(self.record("dedication", k, name, first_sentences(fields["golden_age"], 200), fields))
        return out

    def moment(self):
        out = []
        for r in self.rows("Moments"):
            k = r["MomentType"]
            if not r["EraScore"]:
                continue
            d = self.text(r["Description"])
            eras = " to ".join(self.names([r["MinimumGameEra"], r["MaximumGameEra"]]))
            fields = {"era_score": r["EraScore"], "eras": eras, "obsolete_era": self.name(r["ObsoleteEra"]) or None,
                      "description": d}
            out.append(self.record("moment", k, self.text(r["Name"]) or pretty_key(k), f"+{r['EraScore']} era score. {d}", fields))
        return out

    def era(self):
        xp1 = {r["EraType"]: r for r in self.rows("Eras_XP1")}
        out = []
        for r in self.rows("Eras"):
            k = r["EraType"]
            x = xp1.get(k)
            fields = {"order": r["ChronologyIndex"],
                      "min_turns": x["GameEraMinimumTurns"] if x is not None else None,
                      "max_turns": x["GameEraMaximumTurns"] if x is not None else None,
                      "great_person_base_cost": r["GreatPersonBaseCost"],
                      "warmonger_points": r["WarmongerPoints"], "description": self.text(r["Description"])}
            out.append(self.record("era", k, self.name(k), f"Era {r['ChronologyIndex']}.", fields))
        return out

    def victory(self):
        out = []
        for r in self.rows("Victories"):
            k = r["VictoryType"]
            tt = (r["Name"] or "").replace("_NAME", "_TT")
            how = self.text(r["Description"]) or next((t for t in (self.text(tt + "_XP2"), self.text(tt + "_XP1"),
                                                                   self.text(tt)) if t), "")
            fields = {"how_to_win": how, "blurb": self.text(r["Blurb"]),
                      "enabled_by_default": bool(r["EnabledByDefault"])}
            out.append(self.record("victory", k, self.name(k), first_sentences(how or fields["blurb"], 240), fields))
        return out

    def random_event(self):
        yl = defaultdict(list)
        for r in self.rows("RandomEvent_Yields"):
            if r["Amount"]:
                yl[r["RandomEventType"]].append(f"{'+' if r['Amount'] > 0 else ''}{r['Amount']} {self.name(r['YieldType'])}"
                                                + (f" ({r['Percentage']}% of tiles)" if r["Percentage"] else ""))
        out = []
        for r in self.rows("RandomEvents"):
            k = r["RandomEventType"]
            d = self.text(r["Description"])
            fields = {"severity": r["Severity"], "effect": self.text(r["EffectString"]) or None,
                      "yields_after": yl.get(k), "climate_change_points": r["ClimateChangePoints"],
                      "description": d, "long_description": first_sentences(self.text(r["LongDescription"]), 300)}
            out.append(self.record("random_event", k, self.name(k), first_sentences(d, 200), fields))
        return out

    def alliance(self):
        eff = defaultdict(list)
        for r in self.rows("AllianceEffects"):
            t = self.modifier_text(r["ModifierID"])
            if t:
                eff[r["AllianceType"]].append(f"Level {r['LevelRequirement']}: {t}")
        out = []
        for r in self.rows("Alliances"):
            k = r["AllianceType"]
            d = self.text(r["Description"])
            out.append(self.record("alliance", k, self.name(k), first_sentences(d, 200),
                                   {"effects": sorted(eff.get(k, [])), "description": d}))
        return out

    def agenda(self):
        hist = defaultdict(list)
        for r in self.rows("HistoricalAgendas"):
            hist[r["AgendaType"]].append(self.name(r["LeaderType"]))
        rnd = {r["AgendaType"] for r in self.rows("RandomAgendas")}
        out = []
        for r in self.rows("Agendas"):
            k = r["AgendaType"]
            d = self.text(r["Description"])
            fields = {"historical_for": hist.get(k), "random": k in rnd or None, "description": d}
            out.append(self.record("agenda", k, self.name(k), d, fields))
        return out

    def _leader_ai(self, lk: str) -> tuple[list[str], list[str]]:
        traits = [r["TraitType"] for r in self.rows("LeaderTraits", "LeaderType=?", lk)]
        ai_traits = [pretty_key(t) for t in traits if t.startswith("TRAIT_LEADER_") and not self.trait_text(t)
                     and not self.trait_items.get(t)]
        favours = []
        for t in traits:
            for al in self.rows("AiLists", "LeaderType=?", t):
                if al["System"] not in ("Technologies", "Civics", "Buildings", "Districts", "Units", "Yields",
                                        "Wonders"):
                    continue
                for it in self.rows("AiFavoredItems", "ListType=?", al["ListType"]):
                    if it["Favored"] and it["Item"] and self.name(it["Item"]) not in favours:
                        favours.append(self.name(it["Item"]))
        return ai_traits, favours[:12]

    def _uniques_for(self, traits) -> list[str]:
        out = []
        for t in traits:
            for kind, k in self.trait_items.get(t, []):
                rep = self.replaces.get(k)
                out.append(f"{self.name(k)} ({kind}" + (f", replaces {self.name(rep)}" if rep else "") + ")")
        return out

    def civ(self):
        leaders = defaultdict(list)
        for r in self.rows("CivilizationLeaders"):
            leaders[r["CivilizationType"]].append(r["LeaderType"])
        bias = defaultdict(list)
        for t, c in (("StartBiasTerrains", "TerrainType"), ("StartBiasFeatures", "FeatureType"),
                     ("StartBiasResources", "ResourceType")):
            for r in self.rows(t):
                bias[r["CivilizationType"]].append((r["Tier"], self.name(r[c])))
        for r in self.rows("StartBiasRivers"):
            bias[r["CivilizationType"]].append((r["Tier"], "River"))
        out = []
        for r in self.rows("Civilizations", "StartingCivilizationLevelType='CIVILIZATION_LEVEL_FULL_CIV'"):
            k = r["CivilizationType"]
            traits = [x["TraitType"] for x in self.rows("CivilizationTraits", "CivilizationType=?", k)]
            ability = [t for t in (self.trait_text(x) for x in traits if not self.trait_items.get(x)) if t]
            b = sorted(bias.get(k, []))
            fields = {"ability": ability, "uniques": self._uniques_for(traits),
                      "leaders": self.names(leaders.get(k, [])),
                      "start_bias": [f"{n} (tier {t})" for t, n in b][:8],
                      "dlc": PACKS.get(self.rdb.type_source.get(k, ""), self.rdb.type_source.get(k))}
            summ = "; ".join(a.split(":")[0] for a in ability) + (". Uniques: " + ", ".join(fields["uniques"]) if fields["uniques"] else "")
            out.append(self.record("civ", k, self.name(k), summ, fields))
        return out

    def leader(self):
        agendas = {r["LeaderType"]: r["AgendaType"] for r in self.rows("HistoricalAgendas")}
        levels = {r["CivilizationType"]: r["StartingCivilizationLevelType"] for r in self.rows("Civilizations")}
        out = []
        for lk, civs in self.leader_civ.items():
            if not civs or levels.get(civs[0]) != "CIVILIZATION_LEVEL_FULL_CIV":
                continue
            traits = [x["TraitType"] for x in self.rows("LeaderTraits", "LeaderType=?", lk)]
            ability = [t for t in (self.trait_text(x) for x in traits if not self.trait_items.get(x)) if t]
            ag = agendas.get(lk)
            ai_traits, favours = self._leader_ai(lk)
            fields = {"civ": self.names(civs), "ability": ability, "uniques": self._uniques_for(traits),
                      "agenda": f"{self.name(ag)}: {self.text(self.q('SELECT Description FROM Agendas WHERE AgendaType=?', ag)[0][0])}" if ag and self.q('SELECT 1 FROM Agendas WHERE AgendaType=?', ag) else None,
                      "ai_traits": ai_traits, "ai_favours": favours,
                      "dlc": PACKS.get(self.rdb.type_source.get(lk, ""), self.rdb.type_source.get(lk))}
            summ = f"Leads {', '.join(fields['civ'])}. " + "; ".join(a.split(":")[0] for a in ability)
            out.append(self.record("leader", lk, self.name(lk), summ.strip(), fields))
        return out

    def city_state(self):
        leaders = {r["CivilizationType"]: r["LeaderType"] for r in self.rows("CivilizationLeaders")}
        inherit = {r["LeaderType"]: r["InheritFrom"] for r in self.rows("Leaders")}
        out = []
        for r in self.rows("Civilizations", "StartingCivilizationLevelType='CIVILIZATION_LEVEL_CITY_STATE'"):
            k = r["CivilizationType"]
            lk = leaders.get(k)
            typ = (inherit.get(lk) or "").removeprefix("LEADER_MINOR_CIV_").lower() if lk else ""
            bonus = [t for t in (self.trait_text(x["TraitType"]) for x in self.rows("LeaderTraits", "LeaderType=?", lk or "")) if t]
            bonus = [b.split(": ", 1)[-1] for b in bonus]
            fields = {"type": typ, "suzerain_bonus": bonus,
                      "unique_improvement": self._uniques_for([x["TraitType"] for x in self.rows("LeaderTraits", "LeaderType=?", lk or "")] +
                                                              [x["TraitType"] for x in self.rows("CivilizationTraits", "CivilizationType=?", k)]),
                      "dlc": PACKS.get(self.rdb.type_source.get(k, ""), self.rdb.type_source.get(k))}
            out.append(self.record("city_state", k, self.name(k), f"{typ.capitalize()} city-state. Suzerain: " + " ".join(bonus), fields))
        return out


# The table each kind is read from; a kind whose table is absent (e.g. a base-ruleset build without
# emergencies) yields no records instead of failing.
PRIMARY = {"civ": "Civilizations", "leader": "CivilizationLeaders", "agenda": "Agendas", "city_state": "Civilizations",
           "unit": "Units", "building": "Buildings", "wonder": "Buildings", "district": "Districts",
           "improvement": "Improvements", "tech": "Technologies", "civic": "Civics", "policy": "Policies",
           "government": "Governments", "great_person": "GreatPersonIndividuals", "belief": "Beliefs",
           "governor": "Governors", "promotion": "UnitPromotions", "resource": "Resources", "feature": "Features",
           "terrain": "Terrains", "project": "Projects", "emergency": "EmergencyAlliances", "resolution": "Resolutions",
           "dedication": "CommemorationTypes", "moment": "Moments", "era": "Eras", "victory": "Victories",
           "random_event": "RandomEvents", "alliance": "Alliances"}

KINDS = ["civ", "leader", "agenda", "city_state", "unit", "building", "wonder", "district", "improvement", "tech",
         "civic", "policy", "government", "great_person", "belief", "governor", "promotion", "resource", "feature",
         "terrain", "project", "emergency", "resolution", "dedication", "moment", "era", "victory", "random_event",
         "alliance"]


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True,
                              check=False).stdout.strip()
    except OSError:
        return ""


def check_against(rdb: RulesDb, path: Path) -> list[str]:
    """Row-count differences per table against a game-written DebugGameplay.sqlite."""
    other = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    diffs = []
    for (t,) in other.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        n2 = other.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
        try:
            n1 = rdb.db.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
        except sqlite3.Error:
            n1 = None
        if n1 != n2:
            diffs.append(f"{t}: built {n1}, game {n2}")
    return diffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="folder with Base/ and DLC/ (a copy of the install's data and text)")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--game-version", default="unknown", help="e.g. 1.0.12.68 (Logs/Startup.log)")
    ap.add_argument("--ruleset", default=RULESET)
    ap.add_argument("--modes", default="", help="comma-separated game-mode names to include (default: none)")
    ap.add_argument("--db-out", type=Path, help="also write the built rules database to this SQLite file")
    ap.add_argument("--check-against", type=Path, help="a DebugGameplay.sqlite of the same ruleset to compare row counts")
    ap.add_argument("--no-dlc", action="store_true", help="base game only (to compare with a base-ruleset debug database)")
    ap.add_argument("--lenient", action="store_true",
                    help="write records even when operations failed, tables/columns are unknown or a file did not parse")
    a = ap.parse_args(argv)
    t0 = time.time()
    modes = {m.strip() for m in a.modes.split(",") if m.strip()}
    rdb, mods, crit = build_db(a.root, a.ruleset, modes, dlc=not a.no_dlc)
    warnings = list(rdb.warnings)
    loc = build_loc(a.root, mods, crit, warnings)
    bad = problems(rdb, loc)
    if bad and not a.lenient:
        print("extract-civ6: the rules database looks broken; nothing written (--lenient to override):\n  "
              + "\n  ".join(bad[:30]), file=sys.stderr)
        return 1
    warnings = [*bad, *warnings]
    x = Extractor(rdb, loc)
    a.out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for kind in KINDS:
        if not x.table_exists(PRIMARY[kind]):
            warnings.append(f"{kind}: no {PRIMARY[kind]} table in this ruleset")
            recs = []
        else:
            recs = sorted(getattr(x, kind)(), key=lambda r: r["id"])
        ids = [r["id"] for r in recs]
        dup = {i for i in ids if ids.count(i) > 1}
        assert not dup, f"duplicate ids in {kind}: {sorted(dup)[:5]}"
        (a.out / f"{kind}.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        counts[kind] = len(recs)
    if x.table_exists("Adjacency_YieldChanges"):
        (a.out / "_adjacency.json").write_text(json.dumps(x.adjacency_data(), ensure_ascii=False, indent=1) + "\n",
                                               encoding="utf-8")
    if a.db_out:
        if a.db_out.exists():
            a.db_out.unlink()
        rdb.db.execute(f"VACUUM INTO '{a.db_out}'")
    check = check_against(rdb, a.check_against) if a.check_against else None
    dlc = sorted({m.folder for m in mods})
    meta = {"game_version": a.game_version, "ruleset": a.ruleset,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "generator": f"scripts/extract-civ6.py @ {git_commit()}", "source": "xml-layered",
            "counts": counts, "dlc": dlc, "dlc_names": {d: PACKS.get(d, d) for d in dlc},
            "modes": sorted(modes), "localisation_keys": len(loc.raw),
            "operations": dict(rdb.stats), "check_against": check,
            "warnings": (warnings + x.warnings)[:80]}
    (a.out / "_meta.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print(f"{a.out}: " + ", ".join(f"{k} {n}" for k, n in counts.items()) +
          f"; {sum(counts.values())} records; {len(warnings)} warnings; {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

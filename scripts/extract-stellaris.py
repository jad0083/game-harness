#!/usr/bin/env python3
"""Generate corpora/stellaris/data/*.json from the game's own script files.

    python3 scripts/fetch-stellaris-files.py          # copy the files from the PC (incoming/stellaris/)
    python3 scripts/extract-stellaris.py incoming/stellaris

Reads common/{technology,policies,edicts,buildings,districts,traditions,ascension_perks,
governments/civics,scripted_variables}, events/ and localisation/english/. Writes one JSON array
per kind (tech, policy, edict, building, district, tradition, ascension_perk, civic, event) plus
_meta.json, in the record contract of corpora/stellaris/data/README.md. Effects and conditions are
kept as compact script text; names and descriptions come from the English localisation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "corpora/stellaris/data"

# -- Clausewitz script parsing ---------------------------------------------------------------

TOKEN = re.compile(r'\s+|#[^\n]*|"(?:\\.|[^"\\])*"|<=|>=|!=|==|\?=|[{}=<>]|[^\s{}=<>!#"?]+|[!?]')
OPS = {"=", "<", ">", "<=", ">=", "!=", "==", "?="}


@dataclass
class Entry:
    key: str | None          # None for list items ({ a b c })
    op: str | None
    value: str | Block


class Block(list):
    """A `{ … }` body: a list of Entry."""


def tokenize(text: str) -> list[str]:
    out = []
    for m in TOKEN.finditer(text.lstrip("\ufeff")):
        t = m.group()
        if t[0].isspace() or t[0] == "#":
            continue
        out.append(t[1:-1] if t[0] == '"' else t)
    return out


def parse(text: str) -> Block:
    """Tolerant parser: stray closing braces are ignored, unclosed blocks end at end of file."""
    toks = tokenize(text)
    i = 0

    def block(top: bool) -> Block:
        nonlocal i
        b = Block()
        while i < len(toks):
            t = toks[i]
            if t == "}":
                i += 1
                if top:
                    continue
                return b
            if t == "{":
                i += 1
                b.append(Entry(None, None, block(False)))
                continue
            i += 1
            if i < len(toks) and toks[i] in OPS:
                op = toks[i]
                i += 1
                if i < len(toks) and toks[i] == "{":
                    i += 1
                    b.append(Entry(t, op, block(False)))
                elif i < len(toks):
                    b.append(Entry(t, op, toks[i]))
                    i += 1
            else:
                b.append(Entry(None, None, t))
        return b

    return block(True)


def get(b: Block | None, key: str, default=None):
    if not isinstance(b, Block):
        return default
    for e in b:
        if e.key == key:
            return e.value
    return default


def get_all(b: Block | None, key: str) -> list:
    return [e.value for e in b if e.key == key] if isinstance(b, Block) else []


def values(b) -> list[str]:
    """Scalar items of a `{ a b c }` list (or a single scalar)."""
    if isinstance(b, str):
        return [b]
    return [e.value for e in b if e.key is None and isinstance(e.value, str)] if isinstance(b, Block) else []


def render(v, vars_: dict[str, str], limit: int = 400) -> str:
    """Compact one-line script text for effects/conditions."""
    def r(x) -> str:
        if isinstance(x, str):
            return vars_.get(x, x) if x.startswith("@") else (f'"{x}"' if " " in x else x)
        parts = []
        for e in x:
            val = r(e.value)
            if isinstance(e.value, Block):
                val = "{ " + val + " }" if val else "{ }"
            parts.append(val if e.key is None else f"{e.key} {e.op} {val}")
        return " ".join(parts)

    s = r(v)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def scalar(v, vars_: dict[str, str]):
    """Resolve a variable and turn numbers into numbers."""
    if isinstance(v, str) and v.startswith("@"):
        v = vars_.get(v, v)
    if isinstance(v, str):
        try:
            f = float(v)
            return int(f) if f.is_integer() else f
        except ValueError:
            return v
    return v


# -- localisation ---------------------------------------------------------------------------

LOC_LINE = re.compile(r'^\s*([A-Za-z0-9_.\-:@]+?):\d*\s*"(.*)"\s*(?:#.*)?$')


class Loc:
    def __init__(self) -> None:
        self.raw: dict[str, str] = {}

    def load_text(self, text: str) -> None:
        for line in text.lstrip("\ufeff").splitlines():
            m = LOC_LINE.match(line)
            if m and m.group(1) != "l_english":
                self.raw[m.group(1)] = m.group(2)

    def load_dir(self, d: Path) -> None:
        for f in sorted(d.glob("*.yml")):
            self.load_text(f.read_text(encoding="utf-8-sig", errors="replace"))

    def __call__(self, key: str | None, depth: int = 0) -> str | None:
        if not key or key not in self.raw:
            return None
        s = self.raw[key]
        if depth < 3:
            s = re.sub(r"\$([A-Za-z0-9_.|]+)\$",
                       lambda m: self(m.group(1).split("|")[0], depth + 1) or m.group(1), s)
        s = re.sub(r"§.", "", s)                     # colour codes §Y … §!
        s = re.sub(r"£([A-Za-z0-9_]+)(?:\|\d+)?£", lambda m: m.group(1).replace("_", " "), s)
        s = re.sub(r"\[[^\]]*\]", "…", s)            # scripted text [Root.GetName]
        s = s.replace("\\n", " ").replace('\\"', '"')
        return re.sub(r"\s{2,}", " ", s).strip()


def first_sentences(s: str | None, limit: int = 220) -> str:
    if not s:
        return ""
    if len(s) <= limit:
        return s
    cut = s[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > 60 else cut.rstrip() + "…"


# -- extraction -----------------------------------------------------------------------------

SKIP_KEYS = {"ai_weight", "weight_modifier", "ai_will_do", "ai_chance", "ai_resource_production",
             "icon", "picture", "show_sound", "custom_tooltip_fail"}
EVENT_TYPES = re.compile(r"^(\w*_)?event$")


class Extractor:
    def __init__(self, root: Path):
        self.root = root
        self.loc = Loc()
        self.loc.load_dir(root / "localisation/english")
        self.vars: dict[str, str] = {}
        for f in sorted((root / "common/scripted_variables").glob("*.txt")):
            self._collect_vars(parse(self._read(f)))
        self.warnings: list[str] = []

    @staticmethod
    def _read(f: Path) -> str:
        return f.read_text(encoding="utf-8-sig", errors="replace")

    def _collect_vars(self, b: Block) -> None:
        for e in b:
            if e.key and e.key.startswith("@") and isinstance(e.value, str):
                self.vars[e.key] = e.value

    def defs(self, rel: str) -> list[tuple[str, Block, str]]:
        """(key, block, file) for every top-level definition in common/<rel>/*.txt; later files win."""
        out: dict[str, tuple[str, Block, str]] = {}
        d = self.root / rel
        for f in sorted(d.glob("*.txt")) if d.exists() else []:
            b = parse(self._read(f))
            self._collect_vars(b)
            for e in b:
                if e.key and not e.key.startswith("@") and isinstance(e.value, Block):
                    if e.key in out:
                        self.warnings.append(f"{rel}: {e.key} redefined in {f.name}")
                    out[e.key] = (e.key, e.value, f.name)
        return list(out.values())

    def name(self, key: str, *alts: str) -> str:
        for k in (key, *alts):
            n = self.loc(k)
            if n:
                return n
        return key

    def desc(self, key: str) -> str:
        return first_sentences(self.loc(f"{key}_desc") or self.loc(f"{key}_DESC"))

    def r(self, v, limit: int = 400) -> str:
        return render(v, self.vars, limit) if v is not None else ""

    def resources(self, b: Block | None) -> dict:
        res = get(b, "resources")
        out = {}
        for k in ("cost", "upkeep", "produces"):
            v = get(res, k)
            if isinstance(v, Block):
                out[k] = {e.key: scalar(e.value, self.vars) for e in v if e.key and isinstance(e.value, str)}
        return out

    def record(self, kind: str, key: str, name: str, summary: str, fields: dict, aliases=()) -> dict:
        def plain(v):
            # a field that is usually a scalar can be a block in some definitions: render it
            if isinstance(v, (Block, Entry)):
                return self.r(v if isinstance(v, Block) else Block([v]), 200)
            if isinstance(v, list):
                return [plain(x) for x in v]
            if isinstance(v, dict):
                return {k: plain(x) for k, x in v.items()}
            return v
        al = sorted({a for a in (key, *aliases) if isinstance(a, str) and a and a != name})
        return {"id": f"{kind}:{key}", "name": plain(name), "aliases": al, "summary": summary,
                "fields": {k: plain(v) for k, v in fields.items() if v not in (None, "", [], {})}}

    # kinds ---------------------------------------------------------------------------------

    def tech(self) -> list[dict]:
        defs = self.defs("common/technology")
        names = {k: self.name(k) for k, _, _ in defs}
        leads: dict[str, list[str]] = {}
        for k, b, _ in defs:
            for p in values(get(b, "prerequisites")):
                leads.setdefault(p, []).append(names[k])
        out = []
        for k, b, f in defs:
            fields = {
                "area": get(b, "area"), "tier": scalar(get(b, "tier"), self.vars),
                "cost": scalar(get(b, "cost"), self.vars),
                "category": [self.name(c) for c in values(get(b, "category"))],
                "prerequisites": [names.get(p, self.name(p)) for p in values(get(b, "prerequisites"))],
                "leads_to": sorted(leads.get(k, [])),
                "rare": get(b, "is_rare") == "yes" or None, "dangerous": get(b, "is_dangerous") == "yes" or None,
                "repeatable": get(b, "levels") == "-1" or None, "start_tech": get(b, "start_tech") == "yes" or None,
                "potential": self.r(get(b, "potential"), 200), "source": f,
            }
            out.append(self.record("tech", k, names[k], self.desc(k), fields))
        return out

    def policy(self) -> list[dict]:
        out = []
        for k, b, f in self.defs("common/policies"):
            opts, aliases = [], []
            for o in get_all(b, "option"):
                ok = get(o, "name") or "?"
                aliases.append(ok)
                on = self.name(ok)
                if on != ok:
                    aliases.append(on)
                parts = [f"{on} ({ok}): {self.desc(ok)}".rstrip(": ")]
                if get(o, "modifier") is not None:
                    parts.append("modifier: " + self.r(get(o, "modifier"), 250))
                if get(o, "valid") is not None:
                    parts.append("valid: " + self.r(get(o, "valid"), 200))
                if get(o, "potential") is not None:
                    parts.append("potential: " + self.r(get(o, "potential"), 150))
                opts.append("; ".join(parts))
            fields = {"category": get(b, "category"), "allow": self.r(get(b, "allow"), 200), "options": opts,
                      "source": f}
            out.append(self.record("policy", k, self.name(k, f"policy_{k}"), self.desc(k), fields, aliases))
        return out

    def edict(self) -> list[dict]:
        out = []
        for k, b, f in self.defs("common/edicts"):
            fields = {"length": scalar(get(b, "length"), self.vars), **self.resources(b),
                      "cost": self.r(get(b, "cost"), 150) or None,
                      "modifier": self.r(get(b, "modifier"), 300), "effect": self.r(get(b, "effect"), 200),
                      "potential": self.r(get(b, "potential"), 150), "allow": self.r(get(b, "allow"), 150),
                      "source": f}
            if fields.get("cost") is None:
                fields.pop("cost")
            out.append(self.record("edict", k, self.name(k, f"edict_{k}"), self.desc(k), fields))
        return out

    def _placeable(self, kind: str, rel: str) -> list[dict]:
        out = []
        techs = {}
        for k, b, f in self.defs(rel):
            prereq = [self.name(p) for p in values(get(b, "prerequisites"))]
            fields = {"category": get(b, "category"), **self.resources(b),
                      "build_time": scalar(get(b, "base_buildtime"), self.vars),
                      "prerequisites": prereq, "upgrades_to": [self.name(u) for u in values(get(b, "upgrades"))],
                      "capped": get(b, "capital") == "yes" or None,
                      "potential": self.r(get(b, "potential"), 200), "allow": self.r(get(b, "allow"), 200),
                      "planet_modifier": self.r(get(b, "planet_modifier"), 250),
                      "country_modifier": self.r(get(b, "country_modifier"), 200), "source": f}
            techs[k] = prereq
            out.append(self.record(kind, k, self.name(k), self.desc(k), fields))
        return out

    def building(self) -> list[dict]:
        return self._placeable("building", "common/buildings")

    def district(self) -> list[dict]:
        return self._placeable("district", "common/districts")

    def tradition(self) -> list[dict]:
        tree = {}
        for k, b, _ in self.defs("common/tradition_categories"):
            for t in values(get(b, "traditions")):
                tree[t] = self.name(k)
            for t in (get(b, "adoption_bonus"), get(b, "finish_bonus")):
                if isinstance(t, str):
                    tree[t] = self.name(k)
        out = []
        for k, b, f in self.defs("common/traditions"):
            fields = {"tree": tree.get(k), "modifier": self.r(get(b, "modifier"), 300),
                      "on_enabled": self.r(get(b, "on_enabled"), 200), "possible": self.r(get(b, "possible"), 150),
                      "source": f}
            out.append(self.record("tradition", k, self.name(k), self.desc(k), fields))
        return out

    def ascension_perk(self) -> list[dict]:
        out = []
        for k, b, f in self.defs("common/ascension_perks"):
            fields = {"modifier": self.r(get(b, "modifier"), 300), "on_enabled": self.r(get(b, "on_enabled"), 200),
                      "potential": self.r(get(b, "potential"), 200), "possible": self.r(get(b, "possible"), 250),
                      "source": f}
            out.append(self.record("ascension_perk", k, self.name(k), self.desc(k), fields))
        return out

    def civic(self) -> list[dict]:
        out = []
        for k, b, f in self.defs("common/governments/civics"):
            fields = {"modifier": self.r(get(b, "modifier"), 300), "potential": self.r(get(b, "potential"), 200),
                      "possible": self.r(get(b, "possible"), 250), "origin": k.startswith("origin_") or None,
                      "source": f}
            out.append(self.record("civic", k, self.name(k), self.desc(k), fields))
        return out

    def _text(self, v) -> str | None:
        """title/desc: a loc key, or a block with `text = key` (first one)."""
        if isinstance(v, str):
            return self.loc(v)
        if isinstance(v, Block):
            t = get(v, "text")
            return self.loc(t) if isinstance(t, str) else None
        return None

    def event(self) -> list[dict]:
        out = {}
        d = self.root / "events"
        for f in sorted(d.glob("*.txt")) if d.exists() else []:
            b = parse(self._read(f))
            self._collect_vars(b)
            for e in b:
                if not (e.key and EVENT_TYPES.match(e.key) and isinstance(e.value, Block)):
                    continue
                ev = e.value
                eid = get(ev, "id")
                if not isinstance(eid, str) or get(ev, "hide_window") == "yes":
                    continue
                title = self._text(get(ev, "title"))
                options = get_all(ev, "option")
                if not title or not options:
                    continue
                choices = []
                for n, o in enumerate(options, 1):
                    label = self._text(get(o, "name")) or (get(o, "name") if isinstance(get(o, "name"), str) else "OK")
                    tips = [self.loc(t) for t in get_all(o, "custom_tooltip") if isinstance(t, str) and self.loc(t)]
                    rest = Block(x for x in o if x.key not in {"name", "trigger", "allow", "custom_tooltip",
                                                                "default_hide_option", *SKIP_KEYS})
                    effects = "; ".join([*tips, self.r(rest, 300)]).strip("; ")
                    cond = self.r(get(o, "trigger"), 120)
                    choices.append(f"{n}. {label} -> {effects or '(no effect)'}" + (f" [if {cond}]" if cond else ""))
                fields = {"type": e.key.replace("_", " "), "choices": choices,
                          "triggered_only": get(ev, "is_triggered_only") == "yes" or None,
                          "mean_time_to_happen": self.r(get(ev, "mean_time_to_happen"), 80), "source": f.name}
                title_key = get(ev, "title") if isinstance(get(ev, "title"), str) else None
                out[eid] = self.record("event", eid, title, first_sentences(self._text(get(ev, "desc")), 300),
                                       fields, [title_key] if title_key else [])
        return list(out.values())


KINDS = ["tech", "policy", "edict", "building", "district", "tradition", "ascension_perk", "civic", "event"]


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True,
                              check=False).stdout.strip()
    except OSError:
        return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="folder with common/, events/, localisation/english/")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--game-version", help="default: rawVersion from launcher-settings.json")
    a = ap.parse_args(argv)
    x = Extractor(a.root)
    version = a.game_version
    ls = a.root / "launcher-settings.json"
    if not version and ls.exists():
        version = json.loads(ls.read_text(encoding="utf-8-sig")).get("rawVersion")
    a.out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for kind in KINDS:
        recs = sorted(getattr(x, kind)(), key=lambda r: r["id"])
        ids = [r["id"] for r in recs]
        assert len(ids) == len(set(ids)), f"duplicate ids in {kind}"
        (a.out / f"{kind}.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        counts[kind] = len(recs)
    dlc_file = a.root / "dlc.json"
    meta = {"game_version": version or "unknown", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "generator": f"scripts/extract-stellaris.py @ {git_commit()}", "counts": counts,
            "dlc": json.loads(dlc_file.read_text()) if dlc_file.exists() else [],
            "localisation_keys": len(x.loc.raw), "warnings": x.warnings[:50]}
    (a.out / "_meta.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print(f"{a.out}: " + ", ".join(f"{k} {n}" for k, n in counts.items()) + f"; {len(x.warnings)} warnings")
    return 0


if __name__ == "__main__":
    sys.exit(main())

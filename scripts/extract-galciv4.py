#!/usr/bin/env python3
"""Generate corpora/galciv4/data/*.json from Galactic Civilizations IV's own definition files.

Input is a copy of two folders from the game install (`<install>/Data/`):
    Gameplay/   *Defs.xml — techs, improvements, executive orders, ship components, policies, ...
    Text/       *.xml     — <StringTable><Label/><String/> display strings

Usage:
    scripts/extract-galciv4.py <data-dir> [--out corpora/galciv4/data] [--tech-tree HumanTechTree]
                               [--game-version 4.1.1]

<data-dir> must contain `Gameplay/` and `Text/`. Output: tech.json, improvement.json, order.json
and _meta.json in the record shape documented in corpora/galciv4/data/README.md. Standard
library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

DEFAULT_TECH_TREE = "HumanTechTree"  # Terran Alliance

# Definition files whose entries can require a tech: (glob, child tag, human kind label).
# Used to build each tech's "unlocks" list by reverse lookup.
UNLOCK_SOURCES = [
    ("*Improvement*.xml", "Improvement", "Improvement"),
    ("ShipComponent*.xml", "ShipComponent", "Ship component"),
    ("ShipComponents_*.xml", "ShipComponent", "Ship component"),
    ("PolicyDefs*.xml", "Policy", "Policy"),
    ("StarbaseModuleDefs*.xml", "StarbaseModule", "Starbase module"),
    ("starbasemoduledefs*.xml", "StarbaseModule", "Starbase module"),
    ("ExecutiveOrder*.xml", "ExecutiveOrder", "Executive order"),
    ("ShipHullStatDefs.xml", "ShipHullStats", "Ship hull"),
    ("OperationalAbilityDefs.xml", "OperationalAbilityDef", "Ability"),
    ("UnitLeaderDefs*.xml", "UnitLeader", "Leader"),
    ("InvasionTacticDefs.xml", "InvasionTactic", "Invasion tactic"),
]

MARKUP = re.compile(r"\[/?[A-Za-z_]+(?:=[^\]]*)?\]|</?[a-zA-Z][^>]*>")


def clean(s: str | None) -> str:
    """Strip [ICON=...]/[COLOR=...]-style tags and HTML-ish markup; collapse whitespace."""
    if not s:
        return ""
    return " ".join(MARKUP.sub(" ", s).split())


def slug(s: str) -> str:
    return "_".join(re.sub(r"[^0-9a-z]+", " ", s.lower()).split())


def split_camel(s: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)


def fmt_num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class GameData:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.gameplay = root / "Gameplay"
        self.text = root / "Text"
        if not self.gameplay.is_dir() or not self.text.is_dir():
            sys.exit(f"{root} must contain Gameplay/ and Text/ (copied from <install>/Data/)")
        self.strings = self._load_strings()
        self.stat_names, self.stat_percent = self._load_stat_display()
        self.artifact_powers = {
            e.findtext("InternalName", ""): e for _, e in self.defs("ArtifactPowerDefs*.xml", "ArtifactPower")
        }
        self.artifact_powers.update(
            {e.findtext("InternalName", ""): e for _, e in self.defs("artifactpowerdefs*.xml", "ArtifactPower")}
        )

    def _load_strings(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for f in sorted(glob.glob(str(self.text / "*.xml")) + glob.glob(str(self.text / "*.XML"))):
            try:
                root = ET.parse(f).getroot()
            except ET.ParseError as e:
                print(f"warning: skipping unparsable {f}: {e}", file=sys.stderr)
                continue
            for st in root.iter("StringTable"):
                label = st.findtext("Label")
                if label:
                    out[label] = st.findtext("String") or ""
        return out

    def _load_stat_display(self) -> tuple[dict[str, str], set[str]]:
        names: dict[str, str] = {}
        percent: set[str] = set()
        path = self.gameplay / "StatTypeDisplayDefs.xml"
        if path.exists():
            for d in ET.parse(path).getroot():
                uid = d.findtext("UniqueID")
                if not uid:
                    continue
                names[uid] = self.s(d.findtext("DisplayName")) or split_camel(uid)
                if (d.findtext("IsPercentage") or "").lower() == "true":
                    percent.add(uid)
        return names, percent

    def s(self, label: str | None, fallback: bool = False) -> str:
        """Resolve a display-string label. An unknown label yields "" (so a missing description
        is omitted rather than leaking the label), or a readable form of the label when
        `fallback` is set (used for names, which must never be empty)."""
        if not label:
            return ""
        if label in self.strings:
            return clean(self.strings[label])
        return clean(split_camel(label.replace("_", " "))) if fallback else ""

    def defs(self, pattern: str, child_tag: str) -> list[tuple[str, ET.Element]]:
        out = []
        for f in sorted(glob.glob(str(self.gameplay / pattern))):
            try:
                root = ET.parse(f).getroot()
            except ET.ParseError as e:
                print(f"warning: skipping unparsable {f}: {e}", file=sys.stderr)
                continue
            out.extend((os.path.basename(f), e) for e in root if e.tag == child_tag)
        return out

    # -- effect rendering ---------------------------------------------------

    def stat_name(self, effect_type: str) -> str:
        return self.stat_names.get(effect_type, split_camel(effect_type))

    def render_stat(self, st: ET.Element) -> str:
        """'+20% Manufacturing (Colony)' / '+3 Approval' / '5 Durantium (one-time)'."""
        et = st.findtext("EffectType", "")
        bonus = st.findtext("BonusType", "Flat")
        try:
            value = float(st.findtext("Value", "0"))
        except ValueError:
            value = 0.0
        name = self.stat_name(et)
        if bonus == "Multiplier":
            amount = f"{'+' if value >= 0 else ''}{fmt_num(round(value * 100, 3))}%"
        elif bonus == "OneTime":
            amount = f"{fmt_num(value)} × (one-time)"
        elif et in self.stat_percent:
            amount = f"{'+' if value >= 0 else ''}{fmt_num(round(value * 100, 3))}%"
        else:
            amount = f"{'+' if value >= 0 else ''}{fmt_num(value)}"
        target = st.findtext("Target/TargetType")
        suffix = f" ({target})" if target and target not in ("Improvement", "Faction") else ""
        return f"{amount} {name}{suffix}"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def prereq_techs(e: ET.Element) -> list[str]:
    return [o.text.strip() for o in e.findall("Prerequ/Techs/Option") if o.text]


def prereq_traits(e: ET.Element) -> list[str]:
    return [o.text.strip() for o in e.findall("Prerequ/RaceTrait/Option") if o.text]


class Extractor:
    def __init__(self, data: GameData, tech_tree: str) -> None:
        self.d = data
        self.tech_tree = tech_tree
        # Every tech in every tree, so prerequisites from any tree resolve to a name.
        self.all_techs: list[tuple[str, ET.Element]] = []
        for pattern in ("*TechDefs*.xml",):
            self.all_techs.extend(self.d.defs(pattern, "Tech"))
        self.tech_name: dict[str, str] = {}
        for _, t in self.all_techs:
            name = self.d.s(t.findtext("DisplayName"), fallback=True) or t.findtext("InternalName", "")
            for key in (t.findtext("InternalName"), t.findtext("GenericName")):
                if key:
                    self.tech_name.setdefault(key, name)
        self.unlocks = self._build_unlock_index()

    def tech_names(self, keys: list[str]) -> list[str]:
        return [self.tech_name.get(k, split_camel(k.replace("Tech_", "").replace("_", " "))) for k in keys]

    def display_name(self, e: ET.Element) -> str:
        if e.tag == "ExecutiveOrder":
            power = self.d.artifact_powers.get(e.findtext("ArtifactPowerDef", ""))
            if power is not None:
                return self.d.s(power.findtext("DisplayName"), fallback=True)
        return self.d.s(e.findtext("DisplayName"), fallback=True) or split_camel(e.findtext("InternalName", ""))

    def _build_unlock_index(self) -> dict[str, list[str]]:
        index: dict[str, set[str]] = defaultdict(set)
        for pattern, tag, label in UNLOCK_SOURCES:
            for _, e in self.d.defs(pattern, tag):
                name = self.display_name(e)
                if not name:
                    continue
                for key in prereq_techs(e):
                    index[key].add(f"{label}: {name}")
        return {k: sorted(v) for k, v in index.items()}

    # -- techs ----------------------------------------------------------------

    def techs(self) -> list[dict]:
        records = []
        for _, t in self.all_techs:
            if t.findtext("TechTree") != self.tech_tree or t.findtext("RootNode") == "true":
                continue
            internal = t.findtext("InternalName", "")
            generic = t.findtext("GenericName", "")
            name = self.d.s(t.findtext("DisplayName"), fallback=True) or internal
            fields: dict = {"tree": self.tech_tree}
            cost = t.findtext("ResearchCost")
            if cost:
                fields["cost"] = int(float(cost))
            age = [o.text for o in t.findall("Prerequ/TechAge/Option") if o.text]
            if age:
                fields["age"] = ", ".join(split_camel(a) for a in age)
            prereqs = prereq_techs(t)
            if prereqs:
                fields["prerequisites"] = self.tech_names(prereqs)
            effects = [self.d.render_stat(s) for s in t.findall("Stats")]
            if effects:
                fields["effects"] = effects
            unlocks = sorted(set(self.unlocks.get(internal, [])) | set(self.unlocks.get(generic, [])))
            if unlocks:
                fields["unlocks"] = unlocks
            tags = t.findtext("Tags")
            if tags:
                fields["tags"] = tags
            desc = self.d.s(t.findtext("Description"))
            if desc:
                fields["description"] = desc
            records.append(
                {
                    "id": f"tech:{slug(name)}",
                    "name": name,
                    "aliases": [a for a in {internal, generic} if a],
                    "summary": self.d.s(t.findtext("ShortDescription")),
                    "fields": fields,
                }
            )
        return dedupe(records, "tech")

    # -- improvements ---------------------------------------------------------

    def improvements(self) -> list[dict]:
        records = []
        for source, imp in self.d.defs("*Improvement*.xml", "Improvement"):
            internal = imp.findtext("InternalName", "")
            name = self.display_name(imp)
            fields: dict = {}
            for key, tag in (("type", "ImprovementType"), ("placement", "PlacementType")):
                v = imp.findtext(tag)
                if v:
                    fields[key] = split_camel(v)
            effects, level_effects, resources = [], [], []
            for st in imp.findall("Stats"):
                et = st.findtext("EffectType", "")
                target = st.findtext("Target/TargetType", "")
                value = float(st.findtext("Value", "0") or 0)
                if target == "Improvement" and et == "ManufacturingCost":
                    fields["cost"] = fmt_num(value)
                elif target == "Improvement" and et == "Maintenance":
                    fields["maintenance"] = fmt_num(value)
                elif target == "Improvement" and et.endswith("Cost"):
                    resources.append(f"{fmt_num(value)} {et[:-4]}")
                else:
                    effects.append(self.d.render_stat(st))
            for st in imp.findall("LevelEffectStats"):
                level_effects.append(self.d.render_stat(st))
            if resources:
                fields["resources"] = resources
            if effects:
                fields["effects"] = effects
            if level_effects:
                fields["per_level"] = level_effects
            adjacency = []
            for nb in imp.findall("NeighborBonuses"):
                kind = nb.findtext("GiveBonusToNeighborType", "")
                val = nb.findtext("NeighborBonusValue", "")
                if kind:
                    adjacency.append(f"+{val} to adjacent {split_camel(kind)}")
            if adjacency:
                fields["adjacency"] = adjacency
            reqs = self.tech_names(prereq_techs(imp))
            traits = prereq_traits(imp)
            if reqs:
                fields["requires_tech"] = reqs
            if traits:
                fields["requires_trait"] = [split_camel(t) for t in traits]
            if imp.findtext("IsPlayerWonder") == "true":
                fields["unique"] = "one per civilization"
            desc = self.d.s(imp.findtext("Description"))
            if desc:
                fields["description"] = desc
            fields["source"] = source
            records.append(
                {
                    "id": f"improvement:{slug(name)}",
                    "name": name,
                    "aliases": [internal] if internal else [],
                    "summary": self.d.s(imp.findtext("ShortDescription")),
                    "fields": fields,
                }
            )
        return dedupe(records, "improvement")

    # -- executive orders -----------------------------------------------------

    def orders(self) -> list[dict]:
        records = []
        for source, eo in self.d.defs("ExecutiveOrder*.xml", "ExecutiveOrder"):
            internal = eo.findtext("InternalName", "")
            power = self.d.artifact_powers.get(eo.findtext("ArtifactPowerDef", ""))
            name = self.display_name(eo)
            fields: dict = {}
            for key, tag in (
                ("control_cost", "ControlCost"),
                ("credits_cost", "CreditsCost"),
                ("cooldown_turns", "CooldownTurns"),
            ):
                v = eo.findtext(tag)
                if v and float(v) != 0:
                    fields[key] = fmt_num(float(v))
            target = eo.findtext("Target")
            if target:
                fields["target"] = target
            effects = []
            if power is not None:
                for trig in power.findall("Triggers"):
                    lifetime = trig.findtext("Lifetime", "")
                    dur = trig.findtext("RandomDurationMax") or trig.findtext("Duration")
                    for mod in trig.findall("Modifier"):
                        text = self.d.render_stat(mod)
                        if dur and lifetime != "Instant":
                            text += f" for {dur} turns"
                        effects.append(text)
                    for act in trig.findall("PerformAction"):
                        action = split_camel(act.findtext("Action", ""))
                        params = [p for p in (act.findtext("ValueParam"), act.findtext("StringParam")) if p]
                        effects.append(action + (f" ({', '.join(params)})" if params else ""))
            if effects:
                fields["effects"] = effects
            reqs = self.tech_names(prereq_techs(eo))
            if reqs:
                fields["requires_tech"] = reqs
            precl = [o.text for o in eo.findall("Preclusions/RaceTrait/Option") if o.text]
            if precl:
                fields["blocked_by_trait"] = [split_camel(p) for p in precl]
            desc = self.d.s(power.findtext("Description")) if power is not None else ""
            if desc:
                fields["description"] = desc
            fields["source"] = source
            records.append(
                {
                    "id": f"order:{slug(name)}",
                    "name": name,
                    "aliases": [internal] if internal else [],
                    "summary": desc[:140] if desc else "",
                    "fields": fields,
                }
            )
        return dedupe(records, "order")


PREFERRED_FACTION = "Human"  # Terran Alliance variants win over base and other-faction ones
OTHER_FACTION_MARKERS = ("synth", "xendar", "arnor", "fed", "watcher", "drengin", "korath")


def variant_rank(r: dict) -> int:
    """Higher is better when several definitions share a display name."""
    key = " ".join(r["aliases"] + [r["fields"].get("source", "")]).lower()
    traits = " ".join(r["fields"].get("requires_trait", [])).lower()
    if "tutorial" in key:
        return 0
    if any(m in key for m in OTHER_FACTION_MARKERS) or (traits and PREFERRED_FACTION.lower() not in traits):
        return 1
    if PREFERRED_FACTION.lower() in key:
        return 3
    return 2


TRAILING_TIER = re.compile(r"(?:L|_)?(\d+)(?:_[A-Za-z]+)?$")


def dedupe(records: list[dict], kind: str) -> list[dict]:
    """Resolve display-name collisions.

    Tutorial variants lose to anything else; the preferred faction's variant beats the base
    definition, which beats other factions' variants. Definitions that survive with equal rank
    (e.g. tiered projects `Project_UpgradeWealth1/2/3`) are all kept under suffixed ids.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[r["id"]].append(r)
    out: list[dict] = []
    for id_, group in groups.items():
        if len(group) == 1:
            out.append(group[0])
            continue
        best = max(variant_rank(r) for r in group)
        keep = [r for r in group if variant_rank(r) == best]
        dropped = [a for r in group if variant_rank(r) != best for a in r["aliases"]]
        if dropped:
            print(f"note: {kind} {id_}: dropped variant(s) {', '.join(dropped)}", file=sys.stderr)
        if len(keep) == 1:
            keep[0]["aliases"] = sorted({a for r in group for a in r["aliases"]})
            out.append(keep[0])
            continue
        used: set[str] = set()
        for n, r in enumerate(keep):
            internal = r["aliases"][0] if r["aliases"] else ""
            m = TRAILING_TIER.search(internal)
            suffix = m.group(1) if m else "0"  # an un-numbered base tier sorts first
            while suffix in used:
                suffix = f"{suffix}_{n + 1}"
            used.add(suffix)
            r["id"] = f"{id_}_{suffix}"
            r["fields"]["variant"] = internal
            out.append(r)
        print(f"note: {kind} {id_}: kept {len(keep)} tiers ({', '.join(r['id'] for r in keep)})", file=sys.stderr)
    return sorted(out, key=lambda r: r["id"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir", type=Path, help="folder containing Gameplay/ and Text/")
    ap.add_argument("--out", type=Path, default=Path("corpora/galciv4/data"))
    ap.add_argument("--tech-tree", default=DEFAULT_TECH_TREE, help="TechTree to export (default: Terran)")
    ap.add_argument("--game-version", default="", help="recorded in _meta.json")
    args = ap.parse_args(argv)

    data = GameData(args.data_dir)
    ex = Extractor(data, args.tech_tree)
    outputs = {"tech": ex.techs(), "improvement": ex.improvements(), "order": ex.orders()}

    args.out.mkdir(parents=True, exist_ok=True)
    for kind, records in outputs.items():
        (args.out / f"{kind}.json").write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    meta = {
        "game_version": args.game_version,
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "generator": f"scripts/extract-galciv4.py@{git_commit()}",
        "tech_tree": args.tech_tree,
        "counts": {k: len(v) for k, v in outputs.items()},
        "strings": len(data.strings),
    }
    (args.out / "_meta.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    for kind, records in outputs.items():
        print(f"{kind:<12} {len(records):>4} records -> {args.out / (kind + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

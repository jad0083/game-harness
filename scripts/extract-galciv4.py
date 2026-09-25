#!/usr/bin/env python3
"""Generate corpora/galciv4/data/*.json from Galactic Civilizations IV's own definition files.

Input is a copy of two folders from the game install (`<install>/Data/`):
    Gameplay/   *Defs.xml — techs, improvements, executive orders, ship components, policies, ...
                Events/*.xml, HomeworldEvents*.xml, ColonizeEvents*.xml — event dialogs
    Text/       *.xml     — <StringTable><Label/><String/> display strings

Usage:
    scripts/extract-galciv4.py <data-dir> [--out corpora/galciv4/data] [--tech-tree HumanTechTree]
                               [--game-version 4.1.1]

<data-dir> must contain `Gameplay/` and `Text/`. Output: tech.json, improvement.json, order.json,
policy.json, ship_component.json, starbase_module.json, event.json and _meta.json in the record
shape documented in corpora/galciv4/data/README.md. Standard
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

# PerformAction verbs that only maintain script state and mean nothing to a player.
INTERNAL_ACTION = re.compile(
    r"Counter|Flag|StoreEvent|StoredEvent|RemoveEventChoice|UpdateTechTreeUI|UnhideScreen|UnlockAchievement"
)

# Files holding <GameEvent> definitions (event dialogs; Test*.xml developer events are skipped).
EVENT_SOURCES = ["Events/*.xml", "HomeworldEvents*.xml", "ColonizeEvents*.xml"]

# Stats that are AI hints or bookkeeping rather than player-visible effects.
HIDDEN_STATS = {
    "Threat",
    "Value",
    "MiscBattleRatingMod",
    "MiscBattleRatingModDefenseOnly",
    # weapon-count markers; the matching *Attack stat carries the number
    "BeamWeapon",
    "MissileWeapon",
    "KineticWeapon",
}

# One-time build inputs that are not named "<Resource>Cost".
ONE_TIME_RESOURCE = {"EnergyConsumption": "Energy"}

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
        qualifier = st.findtext("Target/TargetQualifier")
        where = [target] if target and target not in ("Improvement", "Faction") else []
        if qualifier:
            where.append(split_camel(qualifier).lower())
        suffix = f" ({', '.join(where)})" if where else ""
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

    def trigger_effects(self, e: ET.Element, *quiet_events: str) -> list[str]:
        """Render an element's <Triggers>: modifiers via render_stat (with duration) plus
        player-visible actions. Triggers firing on an event not in `quiet_events` are labelled
        with it; repeal triggers and script bookkeeping (counters, flags) are skipped."""
        effects = []
        for trig in e.findall("Triggers"):
            event = trig.findtext("OnEvent", "")
            if event.startswith("OnRepeal"):
                continue
            when = f" on {split_camel(event.removeprefix('On')).lower()}" if event and event not in quiet_events else ""
            lifetime = trig.findtext("Lifetime", "")
            dur = trig.findtext("RandomDurationMax") or trig.findtext("Duration")
            for mod in trig.findall("Modifier"):
                text = self.d.render_stat(mod)
                if dur and lifetime != "Instant":
                    text += f" for {dur} turns"
                effects.append(text + when)
            for act in trig.findall("PerformAction"):
                raw = act.findtext("Action", "")
                if INTERNAL_ACTION.search(raw):
                    continue
                params = [p for p in (act.findtext("ValueParam"), act.findtext("StringParam")) if p]
                effects.append(split_camel(raw) + (f" ({', '.join(params)})" if params else "") + when)
        return effects

    def names_of(self, pattern: str, tag: str) -> dict[str, str]:
        """InternalName -> display name for every definition matching (pattern, tag)."""
        return {e.findtext("InternalName", ""): self.display_name(e) for _, e in self.d.defs(pattern, tag)}

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
                    "aliases": list(dict.fromkeys(a for a in (internal, generic) if a)),
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
            effects = self.trigger_effects(power, "OnArtifactPowerUsed") if power is not None else []
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

    # -- policies -------------------------------------------------------------

    def policies(self) -> list[dict]:
        order_names = self.names_of("ExecutiveOrder*.xml", "ExecutiveOrder")
        policy_names = self.names_of("PolicyDefs*.xml", "Policy")
        records = []
        for source, p in self.d.defs("PolicyDefs*.xml", "Policy"):
            internal = p.findtext("InternalName", "")
            name = self.display_name(p)
            fields: dict = {}
            for key, tag in (("type", "PolicyType"), ("alignment", "Alignment")):
                v = p.findtext(tag)
                if v:
                    fields[key] = split_camel(v)
            cost = p.find("Cost")
            if cost is not None:
                currency = split_camel(cost.findtext("EffectType", "").removesuffix("Cost"))
                fields["cost"] = f"{fmt_num(float(cost.findtext('Value', '0') or 0))} {currency}".strip()
            for key, tag in (
                ("authority_cost", "BaseAuthorityCost"),
                ("collateral_cost", "BaseCollateralCost"),
                ("maturity_turns", "MaturityTurns"),
            ):
                v = p.findtext(tag)
                if v:
                    fields[key] = fmt_num(float(v))
            effects = []
            for st in p.findall("Stats"):
                if st.findtext("EffectType") == "Maintenance" and st.findtext("Target/TargetType") == "Policy":
                    fields["upkeep"] = fmt_num(float(st.findtext("Value", "0") or 0))
                else:
                    effects.append(self.d.render_stat(st))
            effects += self.trigger_effects(p, "OnEnactPolicy")
            if effects:
                fields["effects"] = effects
            grants = p.findtext("GrantsExecutiveOrder")
            if grants:
                fields["grants_order"] = order_names.get(grants) or split_camel(grants.removeprefix("EO_"))
            reqs = self.tech_names(prereq_techs(p))
            if reqs:
                fields["requires_tech"] = reqs
            govs = [o.text for o in p.findall("Prerequ/Government/Option") if o.text]
            if govs:
                fields["requires_government"] = [split_camel(g.removesuffix("GovernmentTier")) for g in govs]
            needs = [o.text for o in p.findall("Prerequ/Policy/Option") if o.text]
            if needs:
                fields["requires_policy"] = [policy_names.get(n) or split_camel(n) for n in needs]
            traits = prereq_traits(p)
            if traits:
                fields["requires_trait"] = [split_camel(t) for t in traits]
            precl = [o.text for o in p.findall("Preclusions/RaceTrait/Option") if o.text]
            if precl:
                fields["blocked_by_trait"] = [split_camel(t) for t in precl]
            desc = self.d.s(p.findtext("Description"))
            if desc:
                fields["description"] = desc
            fields["source"] = source
            records.append(
                {
                    "id": f"policy:{slug(name)}",
                    "name": name,
                    "aliases": [internal] if internal else [],
                    "summary": desc[:140] if desc else "",
                    "fields": fields,
                }
            )
        return dedupe(records, "policy")

    # -- ship components ------------------------------------------------------

    def ship_components(self) -> list[dict]:
        records = []
        defs = self.d.defs("ShipComponentDefs*.xml", "ShipComponent") + self.d.defs("ShipComponents_*.xml", "ShipComponent")
        for source, c in defs:
            category = c.findtext("Category", "")
            if category == "Hidden":  # hull-class markers and scripted parts never offered in the designer
                continue
            internal = c.findtext("InternalName", "")
            name = self.display_name(c)
            fields: dict = {}
            for key, tag in (("category", "Category"), ("type", "Type"), ("slot", "PlacementType")):
                v = c.findtext(tag)
                if v:
                    fields[key] = split_camel(v)
            if c.findtext("OnePerPlayer") == "true":
                fields["limit"] = "one per civilization"
            elif c.findtext("OnePerShip") == "true":
                fields["limit"] = "one per ship"
            effects, resources = [], []
            for st in c.findall("Stats"):
                et = st.findtext("EffectType", "")
                if et in HIDDEN_STATS:
                    continue
                if et == "Mass":
                    fields["mass"] = render_mass(st)
                    continue
                value = float(st.findtext("Value", "0") or 0)
                bonus = st.findtext("BonusType", "Flat")
                if et.endswith("ManufacturingCost") and bonus == "Flat":
                    fields["cost"] = fmt_num(value)
                elif et == "Maintenance" and bonus == "Flat":
                    fields["maintenance"] = fmt_num(value)
                elif bonus == "OneTime" and et in ONE_TIME_RESOURCE:
                    resources.append(f"{fmt_num(value)} {ONE_TIME_RESOURCE[et]}")
                elif et.endswith("Cost") and bonus == "OneTime":
                    resources.append(f"{fmt_num(value)} {split_camel(et.removesuffix('Cost'))}")
                else:
                    effects.append(self.d.render_stat(st))
            effects += self.trigger_effects(c, "OnConstructShip", "OnAddLevelUpgradeToShip")
            if resources:
                fields["resources"] = resources
            if effects:
                fields["effects"] = effects
            level_effects = [self.d.render_stat(st) for st in c.findall("LevelEffectStats")]
            if level_effects:
                fields["per_level"] = level_effects
            reqs = self.tech_names(prereq_techs(c))
            if reqs:
                fields["requires_tech"] = reqs
            traits = prereq_traits(c)
            if traits:
                fields["requires_trait"] = [split_camel(t) for t in traits]
            precl = [o.text for o in c.findall("Preclusions/RaceTrait/Option") if o.text]
            if precl:
                fields["blocked_by_trait"] = [split_camel(t) for t in precl]
            desc = self.d.s(c.findtext("Description"))
            if desc:
                fields["description"] = desc
            fields["source"] = source
            records.append(
                {
                    "id": f"ship_component:{slug(name)}",
                    "name": name,
                    "aliases": [internal] if internal else [],
                    "summary": desc[:140] if desc else "",
                    "fields": fields,
                }
            )
        return dedupe(records, "ship_component")

    # -- starbase modules -----------------------------------------------------

    def starbase_modules(self) -> list[dict]:
        defs = self.d.defs("StarbaseModuleDefs*.xml", "StarbaseModule") + self.d.defs(
            "starbasemoduledefs*.xml", "StarbaseModule"
        )
        module_names = {e.findtext("InternalName", ""): self.display_name(e) for _, e in defs}

        def modules(keys: list[str]) -> list[str]:
            return sorted({module_names.get(k) or split_camel(k) for k in keys})

        records = []
        for source, m in defs:
            internal = m.findtext("InternalName", "")
            name = self.display_name(m)
            fields: dict = {}
            for key, tag in (("specialization", "SpecializationType"), ("requires_target", "RequiredTarget")):
                v = m.findtext(tag)
                if v:
                    fields[key] = split_camel(v)
            stars = [s.text for s in m.findall("Prerequ/StarType") if s.text]
            if stars:
                fields["star_type"] = [split_camel(s) for s in stars]
            turns = m.findtext("TurnsToBuild")
            if turns:
                fields["turns_to_build"] = turns
            effects, resources = [], []
            for st in m.findall("Stats"):
                et = st.findtext("EffectType", "")
                if et in HIDDEN_STATS:
                    continue
                value = float(st.findtext("Value", "0") or 0)
                bonus = st.findtext("BonusType", "Flat")
                if et == "ModulesCost":
                    fields["module_cost"] = fmt_num(value)
                elif et == "Credits" and bonus == "OneTime":
                    fields["credits_cost"] = fmt_num(value)
                elif et == "Maintenance" and bonus == "Flat":
                    fields["maintenance"] = fmt_num(value)
                elif bonus == "OneTime" and et in ONE_TIME_RESOURCE:
                    resources.append(f"{fmt_num(value)} {ONE_TIME_RESOURCE[et]}")
                elif et.endswith("Cost") and bonus == "OneTime":
                    resources.append(f"{fmt_num(value)} {split_camel(et.removesuffix('Cost'))}")
                else:
                    effects.append(self.d.render_stat(st))
            effects += self.trigger_effects(m, "OnConstructModule")
            if resources:
                fields["resources"] = resources
            if effects:
                fields["effects"] = effects
            upgrades = [u.text for u in m.findall("Prerequ/UpgradesFrom") if u.text]
            if upgrades:
                fields["upgrades_from"] = modules(upgrades)
            needs = [u.text for u in m.findall("Prerequ/StarbaseModule") if u.text]
            if needs:
                fields["requires_module_any"] = modules(needs)
            excl = [u.text for u in m.findall("Preclusions/StarbaseModule") if u.text]
            if excl:
                fields["excludes_module"] = modules(excl)
            reqs = self.tech_names(prereq_techs(m))
            if reqs:
                fields["requires_tech"] = reqs
            traits = prereq_traits(m)
            if traits:
                fields["requires_trait"] = [split_camel(t) for t in traits]
            if m.findtext("Prerequ/MaxPerNexusType") == "true":
                fields["limit"] = "one per nexus type"
            elif m.findtext("Prerequ/OnePerCluster") == "true":
                fields["limit"] = "one per cluster"
            dlc = m.findtext("Prerequ/DLC")
            if dlc:
                fields["dlc"] = split_camel(dlc)
            desc = self.d.s(m.findtext("Description"))
            if desc:
                fields["description"] = desc
            fields["source"] = source
            records.append(
                {
                    "id": f"starbase_module:{slug(name)}",
                    "name": name,
                    "aliases": [internal] if internal else [],
                    "summary": self.d.s(m.findtext("ShortDescription")),
                    "fields": fields,
                }
            )
        return dedupe(records, "starbase_module")

    # -- events ---------------------------------------------------------------

    def _param_names(self) -> dict[str, str]:
        """InternalName -> display name for anything an event action may hand out by name."""
        names = {k: v for k, v in self.tech_name.items()}
        for pattern, tag, _ in UNLOCK_SOURCES:
            names.update(self.names_of(pattern, tag))
        for key, power in self.d.artifact_powers.items():
            names[key] = self.d.s(power.findtext("DisplayName"), fallback=True)
        return {k: v for k, v in names.items() if k and v}

    def event_trigger(self, trig: ET.Element, param_names: dict[str, str]) -> list[str]:
        """One choice <Trigger>: modifiers marked one-time / permanent / for N turns, plus
        player-visible actions with their parameters resolved to display names."""
        out = []
        lifetime = trig.findtext("Lifetime", "")
        dur = trig.findtext("RandomDurationMax") or trig.findtext("Duration")
        for mod in trig.findall("Modifier"):
            text = self.d.render_stat(mod)
            if dur and lifetime != "Instant":
                text += f" for {dur} turns"
            elif lifetime == "Instant" and mod.findtext("BonusType") != "OneTime":
                text += " (one-time)"
            elif lifetime in ("Target", "Source"):
                text += " (permanent)"
            out.append(text)
        for act in trig.findall("PerformAction"):
            raw = act.findtext("Action", "")
            if INTERNAL_ACTION.search(raw):
                continue
            params = [p for p in (act.findtext("ValueParam"), act.findtext("StringParam")) if p]
            params = [param_names.get(p) or self.d.s(p) or p for p in params]
            out.append(split_camel(raw) + (f" ({', '.join(params)})" if params else ""))
        return out

    def events(self) -> list[dict]:
        param_names = self._param_names()
        defs = []
        for pattern in EVENT_SOURCES:
            defs.extend((s, e) for s, e in self.d.defs(pattern, "GameEvent") if not s.startswith("Test"))
        records = []
        for source, ev in defs:
            internal = ev.findtext("InternalName", "")
            name = (
                self.d.s(ev.findtext("DisplayName"))
                or self.d.s(ev.findtext("WindowTitle"))
                or clean(split_camel(internal.removeprefix("Event_").replace("_", " ")))
            )
            fields: dict = {}
            etype = ev.findtext("Type")
            if etype:
                fields["type"] = split_camel(etype)
            choices = []
            for n, choice in enumerate(ev.findall("Choice"), start=1):
                button = self.d.s(choice.findtext("Description")) or f"Choice {n}"
                bonus = self.d.s(choice.findtext("BonusDescription"))
                effects = [x for t in choice.findall("Trigger") for x in self.event_trigger(t, param_names)]
                text = f"{n}. {button}" + (f" [{bonus}]" if bonus else "")
                choices.append(text + (f" -> {'; '.join(effects)}" if effects else ""))
            if choices:
                fields["choices"] = choices
            if ev.findtext("Prerequ/OccursOncePerPlayer") == "true":
                fields["once_per_player"] = "yes"
            fields["source"] = source
            desc = self.d.s(ev.findtext("Description"))
            records.append(
                {
                    "id": f"event:{slug(name)}",
                    "name": name,
                    "aliases": [internal] if internal else [],
                    "summary": desc[:140] if desc else "",
                    "fields": fields,
                }
            )
        return dedupe(records, "event", drop_variants=False)


def render_mass(st: ET.Element) -> str:
    """Component mass: a flat value, or HullMassScaleMod(base, fraction of hull capacity)."""
    params = [float(p.text or 0) for p in st.findall("SpecialValue/ValueParam")]
    if st.findtext("SpecialValue/Special") == "HullMassScaleMod" and params:
        base = fmt_num(params[0])
        scale = params[1] if len(params) > 1 else 0.0
        return f"{base} + {fmt_num(round(scale * 100, 3))}% of hull" if scale else base
    return fmt_num(float(st.findtext("Value", "0") or 0))


PREFERRED_FACTION = "Human"  # Terran Alliance variants win over base and other-faction ones
PREFERRED_MARKERS = ("human", "terran")  # how the Terran Alliance's own definitions are named
OTHER_FACTION_MARKERS = ("synth", "xendar", "arnor", "fed", "watcher", "drengin", "korath")


def variant_rank(r: dict) -> int:
    """Higher is better when several definitions share a display name."""
    key = " ".join(r["aliases"] + [r["fields"].get("source", "")]).lower()
    traits = " ".join(r["fields"].get("requires_trait", [])).lower()
    if "tutorial" in key:
        return 0
    if any(m in key for m in OTHER_FACTION_MARKERS) or (traits and PREFERRED_FACTION.lower() not in traits):
        return 1
    if any(m in key for m in PREFERRED_MARKERS):
        return 3
    return 2


TRAILING_TIER = re.compile(r"(?:L|_)?(\d+)(?:_[A-Za-z]+)?$")


def common_word_prefix(names: list[str]) -> int:
    """Length of the longest shared prefix of `names` that ends on a word boundary
    (before an uppercase letter, digit or '_', or at the end of a name)."""
    n = len(os.path.commonprefix(names))
    while n > 0 and not all(len(s) == n or s[n].isupper() or s[n].isdigit() or s[n] == "_" for s in names):
        n -= 1
    return n


def merge_identical(group: list[dict]) -> list[dict]:
    """Collapse definitions that render identically (same summary and fields apart from
    `source`) into one record carrying all their aliases."""
    seen: dict[str, dict] = {}
    for r in group:
        key = json.dumps([r["summary"], {k: v for k, v in r["fields"].items() if k != "source"}], sort_keys=True)
        if key in seen:
            seen[key]["aliases"] = sorted(set(seen[key]["aliases"]) | set(r["aliases"]))
        else:
            seen[key] = r
    return list(seen.values())


def dedupe(records: list[dict], kind: str, drop_variants: bool = True) -> list[dict]:
    """Resolve display-name collisions.

    Tutorial variants lose to anything else; the preferred faction's variant beats the base
    definition, which beats other factions' variants. Definitions that survive with equal rank
    (e.g. tiered projects `Project_UpgradeWealth1/2/3`) are all kept under suffixed ids: the
    trailing tier number, else the part of the internal name the variants do not share
    (`DysonSphereBaseModule_Red` -> `_red`); an un-numbered base tier gets `_0`.

    With `drop_variants=False` (events, whose variants differ in their outcomes) nothing is
    ranked away: only exact duplicates are merged, every distinct definition is kept.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[r["id"]].append(r)
    out: list[dict] = []
    taken = set(groups)
    for id_, group in groups.items():
        if not drop_variants:
            group = merge_identical(group)
        if len(group) == 1:
            out.append(group[0])
            continue
        best = max(variant_rank(r) for r in group) if drop_variants else 0
        keep = [r for r in group if not drop_variants or variant_rank(r) == best]
        dropped = [a for r in group if r not in keep for a in r["aliases"]]
        if dropped:
            print(f"note: {kind} {id_}: dropped variant(s) {', '.join(dropped)}", file=sys.stderr)
        if len(keep) == 1:
            keep[0]["aliases"] = sorted({a for r in group for a in r["aliases"]})
            out.append(keep[0])
            continue
        used: set[str] = set()
        internals = [r["aliases"][0] if r["aliases"] else "" for r in keep]
        shared = common_word_prefix(internals)
        for n, (r, internal) in enumerate(zip(keep, internals, strict=True)):
            m = TRAILING_TIER.search(internal)
            suffix = m.group(1) if m else slug(split_camel(internal[shared:])) or "0"
            while suffix in used or f"{id_}_{suffix}" in taken:
                suffix = f"{suffix}_{n + 1}"
            used.add(suffix)
            r["id"] = f"{id_}_{suffix}"
            taken.add(r["id"])
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
    outputs = {
        "tech": ex.techs(),
        "improvement": ex.improvements(),
        "order": ex.orders(),
        "policy": ex.policies(),
        "ship_component": ex.ship_components(),
        "starbase_module": ex.starbase_modules(),
        "event": ex.events(),
    }

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
        print(f"{kind:<16} {len(records):>4} records -> {args.out / (kind + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

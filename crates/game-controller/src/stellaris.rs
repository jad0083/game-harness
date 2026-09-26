//! Stellaris save reader: turns an autosave (`.sav` = ZIP of `meta` + `gamestate`, Clausewitz
//! text) into a compact briefing of the player's empire for the governor model.
//!
//! Layout notes (verified on 4.5.1 saves, see `games/stellaris-spike/journal.md`):
//! - `player={ { name=… country=N } }` names the player country (it stays set in observer mode).
//! - `country={ N={ … } }`: stockpile in `modules.standard_economy_module.resources`, monthly
//!   net = sum of `budget.last_month.balance.<source>.<resource>`, research in `tech_status`,
//!   policies in `active_policies`, flags in `flags`.
//! - `owned_planets` and `capital` hold colony ids. `colony={ id={ stability num_sapient_pops …
//!   carrier={ type=planet reference=P } } }` points at `planets={ planet={ P={ name planet_class … } } }`.
//! - `war={ id={ name attackers defenders … } }`.

use anyhow::{anyhow, bail, Context, Result};
use jomini::text::{ObjectReader, ValueReader};
use jomini::{TextTape, Utf8Encoding};
use serde::Serialize;
use std::collections::BTreeMap;
use std::io::Read;

type Obj<'d, 't> = ObjectReader<'d, 't, Utf8Encoding>;
type Val<'d, 't> = ValueReader<'d, 't, Utf8Encoding>;

#[derive(Debug, Serialize, Default, Clone)]
pub struct Research {
    /// Tech being researched and its progress (research points invested).
    pub current: Option<(String, f64)>,
    /// Techs offered for the next pick in this field.
    pub alternatives: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct Planet {
    pub id: u64,
    pub name: String,
    pub class: String,
    pub size: i64,
    pub pops: Option<i64>,
    pub stability: Option<f64>,
    pub free_housing: Option<f64>,
    pub free_amenities: Option<f64>,
    pub crime: Option<f64>,
}

#[derive(Debug, Serialize, Default)]
pub struct War {
    pub name: String,
    pub attacker: bool,
    pub start: String,
    /// The other side's countries: (name, military power).
    pub enemies: Vec<(String, f64)>,
    pub enemy_ids: Vec<u64>,
    /// War goal types, e.g. "wg_conquest" (empty when a side has none).
    pub our_goal: String,
    pub their_goal: String,
    /// War exhaustion 0..1; at 1 the other side can force a status-quo peace.
    pub our_exhaustion: f64,
    pub their_exhaustion: f64,
    pub battles_won: usize,
    pub battles_lost: usize,
}

/// Our value, the other regular empires' median and best, and our rank (1 = best) for one measure.
#[derive(Debug, Serialize, Default, Clone)]
pub struct PeerStat {
    pub ours: f64,
    pub median: f64,
    pub best: f64,
    pub rank: usize,
}

#[derive(Debug, Serialize, Default)]
pub struct Peers {
    /// Other regular (`type="default"`) empires compared against.
    pub empires: usize,
    /// Measure name → comparison, in PEER_MEASURES order.
    pub stats: BTreeMap<String, PeerStat>,
    /// Measures where we are below half the median ("falling behind").
    pub behind: Vec<String>,
}

/// Another empire we have contact with, compared with us (ratios are theirs / ours).
#[derive(Debug, Serialize, Default, Clone)]
pub struct Neighbour {
    pub id: u64,
    pub name: String,
    /// "default" (regular empire) or "fallen_empire"/"awakened_fallen_empire".
    pub kind: String,
    pub military: f64,
    pub economy: f64,
    pub tech: f64,
    pub systems: usize,
    pub techs: usize,
    /// Our border distance to them from our relation (0 when they touch our borders).
    pub border_range: Option<i64>,
    pub borders: bool,
    /// Opinion: ours of them and theirs of us.
    pub opinion_ours: Option<i64>,
    pub opinion_theirs: Option<i64>,
    pub threat: f64,
    /// Relation flags that are set, e.g. "hostile", "rival", "alliance", "commercial pact", "at war".
    pub status: Vec<String>,
    /// Their ethics, civics, species traits, AI personality, traditions and perks.
    pub identity: Identity,
    pub colonies: usize,
}

/// A species: display name, class, and its traits (script keys, e.g. "trait_adaptive").
#[derive(Debug, Serialize, Default, Clone)]
pub struct Species {
    pub name: String,
    pub class: String,
    pub traits: Vec<String>,
}

/// Who an empire is: ethics, government, civics, origin, AI personality, founder species,
/// tradition trees adopted (with "finished" marks) and ascension perks.
#[derive(Debug, Serialize, Default, Clone)]
pub struct Identity {
    pub ethics: Vec<String>,
    pub authority: String,
    pub civics: Vec<String>,
    pub origin: String,
    pub personality: String,
    pub species: Option<Species>,
    pub traditions: Vec<String>,
    pub ascension_perks: Vec<String>,
}

/// An uncolonised planet in our systems that some species can live on.
#[derive(Debug, Serialize, Default, Clone)]
pub struct ColonyTarget {
    pub name: String,
    pub class: String,
    pub size: i64,
    /// For our main species: "preferred", "same climate", "other climate", or "any species" (gaia,
    /// habitats and other artificial worlds).
    pub fit: String,
}

/// Techs that open growth or fleet capacity, and whether we have them.
pub const KEY_TECHS: [(&str, &str); 8] = [
    ("tech_habitat_1", "Orbital Habitats (build habitats in our systems)"),
    ("tech_habitat_2", "Habitat Expansion"),
    ("tech_terrestrial_sculpting", "Terrestrial Sculpting (terraforming)"),
    ("tech_ecological_adaptation", "Ecological Adaptation (+habitability)"),
    ("tech_climate_restoration", "Climate Restoration (terraform more classes)"),
    ("tech_doctrine_navy_size_1", "Doctrine: Fleet Support (naval capacity)"),
    ("tech_doctrine_navy_size_2", "Doctrine: Support Vessels (naval capacity)"),
    ("tech_doctrine_navy_size_3", "Doctrine: Interstellar Logistics (naval capacity)"),
];

/// Colonizable planet classes by climate (common/planet_classes, 4.5.1 read 2026-09-26).
const WET: [&str; 3] = ["continental", "ocean", "tropical"];
const DRY: [&str; 4] = ["arid", "desert", "savannah", "volcanic"];
const COLD: [&str; 3] = ["tundra", "arctic", "alpine"];
/// Colonizable by any species (habitability does not depend on the climate preference).
const ANY_SPECIES: [&str; 6] = ["gaia", "habitat", "ringworld_habitable", "shattered_ring_habitable", "relic", "city"];

fn climate(class: &str) -> Option<&'static str> {
    if WET.contains(&class) {
        Some("wet")
    } else if DRY.contains(&class) {
        Some("dry")
    } else if COLD.contains(&class) {
        Some("cold")
    } else {
        None
    }
}

/// How well a planet class suits a species with the given preferred class.
fn fit(class: &str, preferred: Option<&str>) -> Option<String> {
    if ANY_SPECIES.contains(&class) {
        return Some("any species".into());
    }
    let cl = climate(class)?;
    Some(match preferred {
        Some(p) if p == class => "preferred".into(),
        Some(p) if climate(p) == Some(cl) => "same climate".into(),
        _ => "other climate".into(),
    })
}

/// "trait_pc_continental_preference" → Some("continental").
fn preferred_class(traits: &[String]) -> Option<String> {
    traits.iter().find_map(|t| t.strip_prefix("trait_pc_").and_then(|x| x.strip_suffix("_preference")).map(str::to_string))
}

/// "trait_rapid_breeders" → "rapid breeders"; "trait_pc_ocean_preference" → "prefers ocean".
pub fn trait_label(t: &str) -> String {
    if let Some(c) = t.strip_prefix("trait_pc_").and_then(|x| x.strip_suffix("_preference")) {
        return format!("prefers {c}");
    }
    t.trim_start_matches("trait_").replace('_', " ")
}

/// Our federation, if any.
#[derive(Debug, Serialize, Default)]
pub struct Federation {
    pub name: String,
    /// e.g. "research_federation"
    pub kind: String,
    pub level: i64,
    pub cohesion: f64,
    pub we_lead: bool,
    pub members: Vec<String>,
    pub associates: Vec<String>,
}

/// The Galactic Community, if it has formed.
#[derive(Debug, Serialize, Default)]
pub struct Community {
    pub members: usize,
    pub we_are_member: bool,
    /// Resolution under vote: (type, proposer, our stance "for" / "against" / "undecided").
    pub voting: Option<(String, String, String)>,
    /// Most recently passed resolution types, newest first (up to 3).
    pub passed: Vec<String>,
}

/// Federation, Galactic Community, crises and our situations.
#[derive(Debug, Serialize, Default)]
pub struct Galaxy {
    pub federation: Option<Federation>,
    pub community: Option<Community>,
    /// Active crisis or awakened empires: (country type, name, military power).
    pub crises: Vec<(String, String, f64)>,
    /// Our situations: (type, progress, approach).
    pub situations: Vec<(String, f64, String)>,
}

/// Country types of the endgame crises and other galaxy-level threats (4.5.1 common/ scripts use
/// these with `is_country_type`; the extradimensional ones have numbered variants).
const CRISIS_TYPES: [&str; 8] = [
    "swarm", "extradimensional", "ai_empire", "awakened_marauders", "awakened_fallen_empire",
    "awakened_synth_queen", "gray_tempest", "voidworm",
];

/// How many neighbours the briefing lists (nearest first; wars and shared borders first).
pub const MAX_NEIGHBOURS: usize = 6;

/// The save's "no object" reference (u32::MAX).
const NULL_ID: &str = "4294967295";

/// Systems around our space by hyperlane distance, and our civilian ships.
#[derive(Debug, Serialize, Default)]
pub struct Expansion {
    /// Systems one jump from ours: total, unclaimed (no starbase or outpost), held by others.
    pub near: usize,
    pub near_unclaimed: usize,
    pub near_foreign: usize,
    /// Systems one or two jumps from ours.
    pub reach: usize,
    pub reach_unclaimed: usize,
    /// Unclaimed systems within two jumps whose planets we surveyed first (a planet records only
    /// its first surveyor, so this undercounts systems another empire surveyed before us).
    pub reach_unclaimed_surveyed: usize,
    pub construction_ships: usize,
    pub science_ships: usize,
    pub colony_ships: usize,
}

/// Measures compared with other empires (name, label).
pub const PEER_MEASURES: [(&str, &str); 7] = [
    ("systems", "systems"),
    ("pops", "pops"),
    ("techs", "techs"),
    ("military_power", "military"),
    ("economy_power", "economy"),
    ("tech_power", "tech power"),
    ("colonies", "colonies"),
];

#[derive(Debug, Serialize, Default)]
pub struct Briefing {
    pub date: String,
    pub version: String,
    pub country: u64,
    pub name: String,
    pub government: String,
    pub authority: String,
    pub civics: Vec<String>,
    pub ethics: Vec<String>,
    pub origin: String,
    pub stockpile: BTreeMap<String, f64>,
    /// Last month's net income per resource.
    pub net: BTreeMap<String, f64>,
    pub military_power: f64,
    pub economy_power: f64,
    pub tech_power: f64,
    pub victory_rank: i64,
    pub fleet_size: i64,
    pub empire_size: i64,
    pub pops: i64,
    pub starbases: (i64, i64),
    /// Star systems the empire owns (distinct systems of its controlled planets): expansion.
    pub systems: usize,
    /// `last_date_was_human` (set when `play` runs; informational, not a control-state signal).
    pub last_human: String,
    pub techs_known: usize,
    pub research: BTreeMap<String, Research>,
    pub policies: BTreeMap<String, String>,
    /// Active edicts (script keys).
    pub edicts: Vec<String>,
    pub flags: Vec<String>,
    pub planets: Vec<Planet>,
    pub wars: Vec<War>,
    /// How we compare with the other regular empires (galaxy-wide aggregates only).
    pub peers: Peers,
    /// Room to expand around our space, and the ships that do it.
    pub expansion: Expansion,
    /// Nearest empires we have contact with (see MAX_NEIGHBOURS).
    pub neighbours: Vec<Neighbour>,
    pub galaxy: Galaxy,
    /// Our ethics, government, species and traditions.
    pub identity: Identity,
    /// Other species living in the empire (not the founder species).
    pub other_species: Vec<Species>,
    /// Uncolonised planets in our systems that can be settled.
    pub colony_targets: Vec<ColonyTarget>,
    /// Growth / naval techs known (script keys from KEY_TECHS).
    pub key_techs_known: Vec<String>,
    pub used_naval_capacity: i64,
    /// Our active monthly market orders (`market.monthly_trades` for our country).
    pub market_orders: Vec<MarketOrderSpec>,
}

fn expansion(
    root: &Obj,
    c: &Obj,
    country: u64,
    origins: &std::collections::HashMap<String, i64>,
    planets: Option<&Obj>,
) -> Expansion {
    use std::collections::{HashMap, HashSet};
    let mut e = Expansion::default();
    // our civilian ships, by fleet class
    if let (Some(fm), Some(fleets)) = (obj(c, "fleets_manager"), obj(root, "fleet")) {
        let ids: Vec<String> = get(&fm, "owned_fleets")
            .and_then(|v| v.read_array().ok())
            .map(|a| a.values().filter_map(|x| x.read_object().ok()).filter_map(|x| i64_(&x, "fleet")).map(|i| i.to_string()).collect())
            .unwrap_or_default();
        let wanted: HashSet<&str> = ids.iter().map(|s| s.as_str()).collect();
        for (k, _, v) in fleets.fields() {
            if !wanted.contains(k.read_str().as_ref()) {
                continue;
            }
            let Ok(f) = v.read_object() else { continue };
            match string(&f, "ship_class").as_deref() {
                Some("shipclass_constructor") => e.construction_ships += 1,
                Some("shipclass_science_ship") => e.science_ships += 1,
                Some("shipclass_colonizer") => e.colony_ships += 1,
                _ => {}
            }
        }
    }
    // systems: hyperlanes, claimed (has a starbase: outpost or better), planets
    let Some(gos) = obj(root, "galactic_object") else { return e };
    let mut lanes: HashMap<i64, Vec<i64>> = HashMap::new();
    let mut claimed: HashSet<i64> = HashSet::new();
    let mut system_planets: HashMap<i64, Vec<String>> = HashMap::new();
    for (k, _, v) in gos.fields() {
        let Ok(id) = k.read_str().parse::<i64>() else { continue };
        let Ok(g) = v.read_object() else { continue };
        let to: Vec<i64> = get(&g, "hyperlane")
            .and_then(|h| h.read_array().ok())
            .map(|a| a.values().filter_map(|x| x.read_object().ok()).filter_map(|x| i64_(&x, "to")).collect())
            .unwrap_or_default();
        lanes.insert(id, to);
        // unclaimed systems list the null id 4294967295 as their starbase
        if strings(get(&g, "starbases")).iter().any(|sb| sb != NULL_ID) {
            claimed.insert(id);
        }
        let ps: Vec<String> = g.fields().filter(|(k, _, _)| k.read_str() == "planet").filter_map(|(_, _, v)| v.read_string().ok()).collect();
        system_planets.insert(id, ps);
    }
    let ours: HashSet<i64> = strings(get(c, "controlled_planets")).iter().filter_map(|p| origins.get(p).copied()).collect();
    let step = |from: &HashSet<i64>| -> HashSet<i64> {
        from.iter().flat_map(|s| lanes.get(s).cloned().unwrap_or_default()).filter(|s| !ours.contains(s)).collect()
    };
    let near = step(&ours);
    let mut reach = near.clone();
    reach.extend(step(&near));
    let surveyed_by_us = |sys: &i64| -> bool {
        let ps = system_planets.get(sys).cloned().unwrap_or_default();
        !ps.is_empty()
            && ps.iter().all(|p| {
                planets.and_then(|all| obj(all, p)).and_then(|pl| i64_(&pl, "surveyed_by")).map(|by| by as u64) == Some(country)
            })
    };
    e.near = near.len();
    e.near_unclaimed = near.iter().filter(|s| !claimed.contains(s)).count();
    e.near_foreign = e.near - e.near_unclaimed;
    e.reach = reach.len();
    e.reach_unclaimed = reach.iter().filter(|s| !claimed.contains(s)).count();
    e.reach_unclaimed_surveyed = reach.iter().filter(|s| !claimed.contains(s) && surveyed_by_us(s)).count();
    e
}

/// Distinct star systems of a country's controlled planets.
fn systems_of(c: &Obj, origins: &std::collections::HashMap<String, i64>) -> usize {
    strings(get(c, "controlled_planets"))
        .iter()
        .filter_map(|pid| origins.get(pid))
        .collect::<std::collections::BTreeSet<_>>()
        .len()
}

fn empire_stats(c: &Obj, origins: &std::collections::HashMap<String, i64>) -> [f64; 7] {
    let techs = obj(c, "tech_status").map(|ts| ts.fields().filter(|(k, _, _)| k.read_str() == "technology").count()).unwrap_or(0);
    [
        systems_of(c, origins) as f64,
        i64_(c, "num_sapient_pops").unwrap_or(0) as f64,
        techs as f64,
        f64_(c, "military_power").unwrap_or(0.0),
        f64_(c, "economy_power").unwrap_or(0.0),
        f64_(c, "tech_power").unwrap_or(0.0),
        strings(get(c, "owned_planets")).len() as f64,
    ]
}

/// Compare the player with the other regular empires. Only aggregates (median, best, rank) are
/// kept: the governor learns where it stands, not what a specific rival has.
fn peers(countries: &Obj, player: &str, c: &Obj, origins: &std::collections::HashMap<String, i64>) -> Peers {
    let ours = empire_stats(c, origins);
    let others: Vec<[f64; 7]> = countries
        .fields()
        .filter(|(k, _, _)| k.read_str() != player)
        .filter_map(|(_, _, v)| v.read_object().ok())
        .filter(|o| string(o, "type").as_deref() == Some("default"))
        .map(|o| empire_stats(&o, origins))
        .collect();
    let mut p = Peers { empires: others.len(), ..Default::default() };
    if others.is_empty() {
        return p;
    }
    for (i, (key, _)) in PEER_MEASURES.iter().enumerate() {
        let mut vals: Vec<f64> = others.iter().map(|s| s[i]).collect();
        vals.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let n = vals.len();
        let median = if n % 2 == 1 { vals[n / 2] } else { (vals[n / 2 - 1] + vals[n / 2]) / 2.0 };
        let best = vals[n - 1];
        let rank = 1 + vals.iter().filter(|v| **v > ours[i]).count();
        if median > 0.0 && ours[i] < median * 0.5 {
            p.behind.push((*key).to_string());
        }
        p.stats.insert((*key).to_string(), PeerStat { ours: ours[i], median, best, rank });
    }
    p
}

/// The `relation={…}` entries of a country's relations_manager.
fn relations<'d, 't>(c: &Obj<'d, 't>) -> Vec<Obj<'d, 't>> {
    obj(c, "relations_manager")
        .map(|rm| rm.fields().filter(|(k, _, _)| k.read_str() == "relation").filter_map(|(_, _, v)| v.read_object().ok()).collect())
        .unwrap_or_default()
}

/// Empires we have contact with (regular and fallen), nearest first: at war with us, then those
/// sharing a border, then by border distance. `at_war` holds the ids we are fighting.
fn neighbours(root: &Obj, countries: &Obj, us: u64, c: &Obj, origins: &std::collections::HashMap<String, i64>, at_war: &[u64]) -> Vec<Neighbour> {
    let yes = |r: &Obj, k: &str| get(r, k).and_then(|v| v.read_string().ok()).as_deref() == Some("yes");
    let mut out = Vec::new();
    for r in relations(c) {
        let Some(id) = i64_(&r, "country").map(|n| n as u64) else { continue };
        if id == us || !yes(&r, "contact") {
            continue;
        }
        let Some(them) = obj(countries, &id.to_string()) else { continue };
        let kind = string(&them, "type").unwrap_or_default();
        if !matches!(kind.as_str(), "default" | "fallen_empire" | "awakened_fallen_empire") {
            continue;
        }
        let theirs = relations(&them).into_iter().find(|x| i64_(x, "country").map(|n| n as u64) == Some(us));
        let mut status = Vec::new();
        if at_war.contains(&id) {
            status.push("AT WAR".to_string());
        }
        for (key, label) in [
            ("is_rival", "rival"), ("hostile", "hostile"), ("friendly", "friendly"), ("alliance", "alliance"),
            ("commercial_pact", "commercial pact"), ("research_agreement", "research agreement"),
            ("migration_access", "migration access"), ("embassy", "embassy"), ("closed_borders", "we closed borders"),
        ] {
            if yes(&r, key) {
                status.push(label.to_string());
            }
        }
        if let Some(t) = theirs.as_ref() {
            if yes(t, "is_rival") && !yes(&r, "is_rival") {
                status.push("they rival us".to_string());
            }
            if yes(t, "closed_borders") {
                status.push("they closed borders".to_string());
            }
        }
        // `truce` is a reference; while fighting it can point at an old truce, so skip it then
        let truce = get(&r, "truce").and_then(|v| v.read_scalar().ok()).and_then(|x| x.to_i64().ok()).is_some_and(|t| t != 0);
        if truce && !at_war.contains(&id) {
            status.push("truce".to_string());
        }
        let stats = empire_stats(&them, origins);
        out.push(Neighbour {
            id,
            name: name_of(&them),
            kind,
            military: f64_(&them, "military_power").unwrap_or(0.0),
            economy: f64_(&them, "economy_power").unwrap_or(0.0),
            tech: f64_(&them, "tech_power").unwrap_or(0.0),
            systems: stats[0] as usize,
            techs: stats[2] as usize,
            colonies: stats[6] as usize,
            identity: identity(root, &them),
            border_range: i64_(&r, "border_range"),
            borders: yes(&r, "borders"),
            opinion_ours: i64_(&r, "relation_current"),
            opinion_theirs: theirs.as_ref().and_then(|t| i64_(t, "relation_current")),
            threat: f64_(&r, "threat").unwrap_or(0.0),
            status,
        });
    }
    out.sort_by_key(|n| (!at_war.contains(&n.id), !n.borders, n.border_range.unwrap_or(i64::MAX)));
    out.truncate(MAX_NEIGHBOURS);
    out
}

/// A species from `species_db` by reference.
fn species(root: &Obj, r: u64) -> Option<Species> {
    let sp = obj(root, "species_db").and_then(|db| obj(&db, &r.to_string()))?;
    let key = obj(&sp, "name").and_then(|n| string(&n, "key")).unwrap_or_default();
    // prescripted species ("PRESCRIPTED_species_name_humans1") have no readable key: use the plural's stem
    let name = match key.strip_prefix("PRESCRIPTED_species_name_") {
        Some(stem) => {
            let stem = stem.trim_end_matches(|c: char| c.is_ascii_digit()).replace('_', " ");
            let mut ch = stem.chars();
            ch.next().map(|f| f.to_uppercase().collect::<String>() + ch.as_str()).unwrap_or_default()
        }
        None => name_of(&sp),
    };
    let traits = obj(&sp, "traits")
        .map(|t| t.fields().filter(|(k, _, _)| k.read_str() == "trait").filter_map(|(_, _, v)| v.read_string().ok()).collect())
        .unwrap_or_default();
    Some(Species { name, class: string(&sp, "class").unwrap_or_default(), traits })
}

/// Ethics, government, species, traditions and perks of a country.
fn identity(root: &Obj, c: &Obj) -> Identity {
    let gov = obj(c, "government");
    let traditions = strings(get(c, "traditions"));
    let trees: Vec<String> = traditions
        .iter()
        .filter_map(|t| t.strip_prefix("tr_").and_then(|x| x.strip_suffix("_adopt")))
        .map(|tree| {
            let done = traditions.iter().any(|t| t == &format!("tr_{tree}_finish"));
            format!("{}{}", tree.replace('_', " "), if done { " (finished)" } else { "" })
        })
        .collect();
    Identity {
        ethics: obj(c, "ethos").map(|e| strings(get(&e, "ethics"))).unwrap_or_default().iter().map(|e| e.trim_start_matches("ethic_").replace('_', " ")).collect(),
        authority: gov.as_ref().and_then(|g| string(g, "authority")).unwrap_or_default().trim_start_matches("auth_").replace('_', " "),
        civics: gov.as_ref().map(|g| strings(get(g, "civics"))).unwrap_or_default().iter().map(|x| x.trim_start_matches("civic_").replace('_', " ")).collect(),
        origin: gov.as_ref().and_then(|g| string(g, "origin")).unwrap_or_default().trim_start_matches("origin_").replace('_', " "),
        personality: string(c, "personality").unwrap_or_default().replace('_', " "),
        species: get(c, "founder_species_ref").and_then(|v| v.read_scalar().ok()).and_then(|x| x.to_u64().ok()).and_then(|r| species(root, r)),
        traditions: trees,
        ascension_perks: strings(get(c, "ascension_perks")).iter().map(|x| x.trim_start_matches("ap_").replace('_', " ")).collect(),
    }
}

fn readable_type(t: &str, prefix: &str) -> String {
    t.strip_prefix(prefix).unwrap_or(t).replace('_', " ")
}

/// Federation, Galactic Community, crises and our situations.
fn galaxy(root: &Obj, countries: &Obj, c: &Obj, us: u64) -> Galaxy {
    let name = |id: u64| -> String {
        if id == us {
            return "us".to_string();
        }
        obj(countries, &id.to_string()).map(|x| name_of(&x)).unwrap_or_else(|| format!("country {id}"))
    };
    let ids = |o: &Obj, key: &str| -> Vec<u64> { strings(get(o, key)).iter().filter_map(|x| x.parse().ok()).collect() };
    let mut g = Galaxy::default();

    if let Some(fid) = i64_(c, "federation") {
        if let Some(f) = obj(root, "federation").and_then(|fs| obj(&fs, &fid.to_string())) {
            let prog = obj(&f, "federation_progression");
            g.federation = Some(Federation {
                name: name_of(&f),
                kind: prog.as_ref().and_then(|p| string(p, "federation_type")).unwrap_or_default(),
                level: prog.as_ref().and_then(|p| i64_(p, "levels")).unwrap_or(0),
                cohesion: prog.as_ref().and_then(|p| f64_(p, "cohesion")).unwrap_or(0.0),
                we_lead: i64_(&f, "leader").map(|l| l as u64) == Some(us),
                members: ids(&f, "members").into_iter().map(name).collect(),
                associates: ids(&f, "associates").into_iter().map(name).collect(),
            });
        }
    }

    if let Some(gc) = obj(root, "galactic_community") {
        let members = ids(&gc, "members");
        let resolutions = obj(root, "resolution");
        let res = |id: i64| resolutions.as_ref().and_then(|r| obj(r, &id.to_string()));
        let voting = i64_(&gc, "voting").and_then(&res).map(|r| {
            let stance = if ids(&r, "supporters").contains(&us) {
                "for"
            } else if ids(&r, "opponents").contains(&us) {
                "against"
            } else {
                "undecided"
            };
            (
                readable_type(&string(&r, "type").unwrap_or_default(), "resolution_"),
                i64_(&r, "country").map(|x| name(x as u64)).unwrap_or_default(),
                stance.to_string(),
            )
        });
        let passed = strings(get(&gc, "passed"))
            .iter()
            .rev()
            .filter_map(|x| x.parse::<i64>().ok())
            .filter_map(|id| res(id).and_then(|r| string(&r, "type")))
            .map(|t| readable_type(&t, "resolution_"))
            .take(3)
            .collect();
        g.community = Some(Community { members: members.len(), we_are_member: members.contains(&us), voting, passed });
    }

    for (_, _, v) in countries.fields() {
        let Ok(x) = v.read_object() else { continue };
        let Some(t) = string(&x, "type") else { continue };
        if CRISIS_TYPES.iter().any(|k| t.starts_with(k)) {
            g.crises.push((t, name_of(&x), f64_(&x, "military_power").unwrap_or(0.0)));
        }
    }

    if let Some(sits) = obj(root, "situations").and_then(|s| obj(&s, "situations")) {
        for (_, _, v) in sits.fields() {
            let Ok(x) = v.read_object() else { continue };
            if i64_(&x, "country").map(|n| n as u64) != Some(us) {
                continue;
            }
            g.situations.push((
                readable_type(&string(&x, "type").unwrap_or_default(), ""),
                f64_(&x, "progress").unwrap_or(0.0),
                readable_type(&string(&x, "approach").unwrap_or_default(), "approach_"),
            ));
        }
    }
    g
}

/// Extract `meta` and `gamestate` from a `.sav` ZIP.
pub fn unzip_save(bytes: &[u8]) -> Result<(Vec<u8>, Vec<u8>)> {
    let mut zip = zip::ZipArchive::new(std::io::Cursor::new(bytes)).context("not a Stellaris .sav (zip)")?;
    let mut read = |name: &str| -> Result<Vec<u8>> {
        let mut f = zip.by_name(name).with_context(|| format!("save has no `{name}`"))?;
        let mut out = Vec::with_capacity(f.size() as usize);
        f.read_to_end(&mut out)?;
        Ok(out)
    };
    let meta = read("meta")?;
    let gamestate = read("gamestate")?;
    Ok((meta, gamestate))
}

/// Build a briefing from a `.sav` file's bytes.
pub fn brief_save(bytes: &[u8]) -> Result<Briefing> {
    let (meta, gamestate) = unzip_save(bytes)?;
    let mut b = brief_gamestate(&gamestate)?;
    // The gamestate names the empire by localisation key; `meta` has the displayed name.
    if let Ok(tape) = TextTape::from_slice(&meta) {
        if let Some(name) = string(&tape.utf8_reader(), "name") {
            // war names were built with the key-derived name ("EMPIRE_DESIGN_humans1" → "humans1")
            let old = std::mem::replace(&mut b.name, name);
            if !old.is_empty() {
                for w in &mut b.wars {
                    w.name = w.name.replace(&old, &b.name);
                }
            }
        }
    }
    Ok(b)
}

/// Agent root holding the Stellaris documents folder (saves, logs, settings).
pub const DOCS_ROOT: &str = "stellaris_docs";

/// Newest autosave across all save folders, fetched through the agent: (path, bytes).
pub async fn fetch_latest_save(client: &crate::client::AgentClient) -> Result<(String, Vec<u8>)> {
    let (path, _) = latest_save_path(client).await?;
    let (bytes, _) = client.files_read(DOCS_ROOT, &path, 0, None).await?;
    Ok((path, bytes))
}

/// Like `fetch_latest_save`, plus the file's modification time (unix seconds, the PC's clock).
pub async fn fetch_latest_save_timed(client: &crate::client::AgentClient) -> Result<(String, Vec<u8>, u64)> {
    let (path, modified) = latest_save_path(client).await?;
    let (bytes, _) = client.files_read(DOCS_ROOT, &path, 0, None).await?;
    Ok((path, bytes, modified))
}

// ---- governor directives (console bridge) ------------------------------------------------

/// Window title substring of the game; input is refused unless it is in the foreground.
pub const WINDOW_TITLE: &str = "Stellaris";
/// Console toggle key (verified on the user's US layout, 2026-09-25).
pub const CONSOLE_KEY: &str = "`";

#[derive(Debug, serde::Deserialize)]
pub struct DirectiveDef {
    pub description: String,
    #[serde(default)]
    pub policies: BTreeMap<String, String>,
    /// Per policy: the trigger under which the game allows the option (copied from its `valid`
    /// block); the console sets a policy only inside `if = { limit = { … } }`, because a console
    /// `set_policy` would otherwise apply an option the empire may not take.
    #[serde(default)]
    pub conditions: BTreeMap<String, String>,
}

#[derive(Debug, serde::Deserialize)]
pub struct Directives {
    pub directive: BTreeMap<String, DirectiveDef>,
}

impl Directives {
    /// Load `directives.toml` from a Stellaris corpus directory.
    pub fn load(corpus_dir: &std::path::Path) -> Result<Directives> {
        let path = corpus_dir.join("directives.toml");
        let text = std::fs::read_to_string(&path).with_context(|| format!("reading {}", path.display()))?;
        let d: Directives = toml::from_str(&text).with_context(|| format!("parsing {}", path.display()))?;
        for (name, def) in &d.directive {
            check_ident(name)?;
            for (k, v) in &def.policies {
                check_ident(k)?;
                check_ident(v)?;
            }
            for (k, c) in &def.conditions {
                if !def.policies.contains_key(k) {
                    bail!("directive {name}: condition for {k}, which it does not set");
                }
                check_condition(c)?;
            }
        }
        Ok(d)
    }

    /// Console lines that apply directive `name` to the player's empire (see directives.toml).
    /// The empire must be player-controlled with `human_ai` on (see `take_control`); the
    /// confirmation line is logged only when the effect has a real country scope, so a directive
    /// sent in observer mode fails loudly instead of silently doing nothing.
    pub fn console_lines(&self, name: &str, nonce: &str) -> Result<Vec<String>> {
        let Some(def) = self.directive.get(name) else {
            bail!("unknown directive {name:?}; known: {}", self.directive.keys().cloned().collect::<Vec<_>>().join(", "))
        };
        let mut lines = vec![];
        let others: Vec<String> = self
            .directive
            .keys()
            .filter(|k| *k != name)
            .map(|k| format!("remove_country_flag = governor_directive_{k}"))
            .collect();
        if !others.is_empty() {
            lines.push(format!("effect {}", others.join(" ")));
        }
        let mut apply = format!("effect set_country_flag = governor_directive_{name}");
        for (policy, option) in &def.policies {
            let set = format!("set_policy = {{ policy = {policy} option = {option} cooldown = no }}");
            match def.conditions.get(policy) {
                Some(c) => apply += &format!(" if = {{ limit = {{ {c} }} {set} }}"),
                None => apply += &format!(" {set}"),
            }
        }
        apply += &format!(" {}", scoped_log(&applied_marker(name, nonce)));
        lines.push(apply);
        Ok(lines)
    }
}

/// Text written to game.log when a directive's effects ran (`nonce` keeps repeats visible).
pub fn applied_marker(name: &str, nonce: &str) -> String {
    format!("GOVERNOR_APPLIED {name} {nonce}")
}

/// Unique suffix for log markers: milliseconds since the Unix epoch, base 36.
pub fn nonce() -> String {
    let mut n = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0);
    let mut s = String::new();
    while n > 0 {
        s.insert(0, std::char::from_digit((n % 36) as u32, 36).unwrap_or('0'));
        n /= 36;
    }
    s
}

/// Poll game.log (written with a few seconds' delay) for `marker` after byte `offset`.
async fn wait_for_log(client: &crate::client::AgentClient, offset: u64, marker: &str) -> Result<bool> {
    for _ in 0..16 {
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        if read_log_since(client, offset).await?.0.contains(marker) {
            return Ok(true);
        }
    }
    Ok(false)
}

/// A `log` effect that runs only with a real country scope (verified 2026-09-25: logged while
/// playing, not while observing). The game writes identical log text only once per in-game day,
/// so callers add a `nonce()` to every marker.
pub fn scoped_log(text: &str) -> String {
    format!("if = {{ limit = {{ exists = capital_scope }} log = \"{text}\" }}")
}

/// A trigger block's contents from directives.toml: identifiers, `=`, `<`, `>`, digits, spaces and
/// balanced braces only (no quotes or line breaks that could end the console line), at most 300 chars.
fn check_condition(c: &str) -> Result<()> {
    let ok_chars = c.chars().all(|ch| ch.is_ascii_alphanumeric() || " _=<>{}.".contains(ch));
    let mut depth = 0i32;
    for ch in c.chars() {
        depth += match ch { '{' => 1, '}' => -1, _ => 0 };
        if depth < 0 {
            break;
        }
    }
    if !ok_chars || depth != 0 || c.len() > 300 || c.trim().is_empty() {
        bail!("refusing policy condition {c:?}: only identifiers, comparisons and balanced braces");
    }
    Ok(())
}

/// Script identifiers only: nothing that could smuggle other console commands.
fn check_ident(s: &str) -> Result<()> {
    if s.is_empty() || !s.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_') {
        bail!("invalid identifier {s:?} (allowed: a-z 0-9 _)");
    }
    Ok(())
}

async fn require_foreground(client: &crate::client::AgentClient) -> Result<()> {
    let h = client.health().await?;
    let fg = h.get("foreground").and_then(|v| v.as_str()).unwrap_or("");
    if fg.trim() != WINDOW_TITLE {   // exact: a browser tab titled "Stellaris Wiki" must not pass
        bail!("refusing console input: foreground window is {fg:?}, not {WINDOW_TITLE:?}");
    }
    Ok(())
}

/// Open the console, run `lines`, close it. Checks the game is in the foreground before every
/// keystroke; if focus is lost midway, stops (the console may be left open).
pub async fn run_console(client: &crate::client::AgentClient, lines: &[String]) -> Result<()> {
    let pause = std::time::Duration::from_millis(300);
    require_foreground(client).await?;
    client.key(CONSOLE_KEY, 1).await?;
    tokio::time::sleep(pause).await;
    for line in lines {
        require_foreground(client).await?;
        client.type_text(line).await?;
        require_foreground(client).await?;
        client.key("enter", 1).await?;
        tokio::time::sleep(pause).await;
    }
    require_foreground(client).await?;
    client.key(CONSOLE_KEY, 1).await?;
    Ok(())
}

/// Game speeds, slowest first (verified 2026-09-25: `-`/`=` step through these; the HUD shows the
/// name while unpaused). 4.5 has no "faster" step; it is accepted as a name for fastest.
pub const SPEEDS: [&str; 5] = ["slowest", "slow", "normal", "fast", "fastest"];

/// Index into [`SPEEDS`] for a speed name.
pub fn speed_index(name: &str) -> Result<usize> {
    let n = name.trim().to_lowercase();
    let n = if n == "faster" { "fastest".to_string() } else { n };
    SPEEDS.iter().position(|s| *s == n).ok_or_else(|| anyhow!("unknown speed {name:?}; use one of {}", SPEEDS.join(", ")))
}

/// Set the game speed: step down to slowest, then up to the wanted speed. Works paused or not.
pub async fn set_speed(client: &crate::client::AgentClient, name: &str) -> Result<&'static str> {
    let idx = speed_index(name)?;
    for _ in 0..SPEEDS.len() - 1 {
        require_foreground(client).await?;
        client.key("-", 1).await?;
    }
    for _ in 0..idx {
        require_foreground(client).await?;
        client.key("=", 1).await?;
    }
    Ok(SPEEDS[idx])
}

/// Detects the pause state from the manifest's `paused` screen (template of the "Paused" label).
pub struct PauseDetector {
    template: image::RgbImage,
    roi: [f64; 4],
    threshold: f64,
    search: u32,
    /// Colour signature (preferred: the "Paused" label pulses, which defeats the template).
    color: Option<([[u8; 3]; 2], f64)>,
    /// The in-game menu (Esc on the bare map): template, ROI, threshold, search radius.
    menu: Option<(image::RgbImage, [f64; 4], f64, u32)>,
    /// The console is open: ROI and colour signature ([screens.console_open]).
    console: Option<([f64; 4], [[u8; 3]; 2], f64)>,
}

impl PauseDetector {
    pub fn from_manifest(m: &crate::corpus::GameManifest) -> Result<PauseDetector> {
        let def = m.screens.get("paused").context("manifest has no [screens.paused]")?;
        let rel = def.template.as_ref().context("[screens.paused] has no template")?;
        let path = m.base_dir.clone().unwrap_or_default().join(rel);
        let template = image::open(&path).with_context(|| format!("loading {}", path.display()))?.to_rgb8();
        let roi = def.template_roi.context("[screens.paused] has no template_roi")?;
        let color = def.color_range.map(|r| (r, def.color_min_fraction.unwrap_or(0.05)));
        let menu = match m.screens.get("game_menu") {
            Some(g) => {
                let rel = g.template.as_ref().context("[screens.game_menu] has no template")?;
                let path = m.base_dir.clone().unwrap_or_default().join(rel);
                let img = image::open(&path).with_context(|| format!("loading {}", path.display()))?.to_rgb8();
                Some((img, g.template_roi.context("[screens.game_menu] has no template_roi")?, g.template_threshold, g.template_search))
            }
            None => None,
        };
        let console = m.screens.get("console_open").and_then(|c| {
            Some((c.template_roi?, c.color_range?, c.color_min_fraction.unwrap_or(0.3)))
        });
        Ok(PauseDetector { template, roi, threshold: def.template_threshold, search: def.template_search, color, menu, console })
    }

    /// Is the console open? (false when the manifest has no console signature)
    pub fn frame_has_console(&self, frame: &image::RgbImage) -> bool {
        let Some((roi, range, min)) = self.console else { return false };
        let r = crate::imaging::roi_from_norm(frame.width(), frame.height(), roi);
        crate::imaging::color_fraction(frame, r, range) >= min
    }

    /// Open the console, run `lines`, close it, checking on screen that it really opened before
    /// typing (text typed onto the map would act as hotkeys) and that it closed afterwards.
    pub async fn run_console(&self, client: &crate::client::AgentClient, lines: &[String]) -> Result<()> {
        if self.console.is_none() {
            return run_console(client, lines).await;
        }
        let pause = std::time::Duration::from_millis(300);
        let open = |_: ()| async { Ok::<bool, anyhow::Error>(self.frame_has_console(&Self::frame(client).await?)) };
        // Console `effect` runs on the selected object: with a planet or station selected, policies
        // still reach the empire but country flags and the scoped confirmation do not (seen
        // 2026-09-26). Esc drops the selection; on the bare map it opens the game menu, closed again.
        if !open(()).await? {
            require_foreground(client).await?;
            client.key("esc", 1).await?;
            tokio::time::sleep(std::time::Duration::from_millis(400)).await;
            self.close_menu(client).await?;
        }
        // a console left open by an earlier failure: close it first so the key opens it again
        if open(()).await? {
            require_foreground(client).await?;
            client.key(CONSOLE_KEY, 1).await?;
            tokio::time::sleep(pause).await;
        }
        let mut opened = false;
        for _ in 0..2 {
            require_foreground(client).await?;
            client.key(CONSOLE_KEY, 1).await?;
            for _ in 0..4 {
                tokio::time::sleep(std::time::Duration::from_millis(250)).await;
                if open(()).await? {
                    opened = true;
                    break;
                }
            }
            if opened {
                break;
            }
        }
        if !opened {
            bail!("the console did not open (no Debug View bar on screen); nothing was typed");
        }
        for line in lines {
            require_foreground(client).await?;
            client.type_text(line).await?;
            require_foreground(client).await?;
            client.key("enter", 1).await?;
            tokio::time::sleep(pause).await;
        }
        require_foreground(client).await?;
        client.key(CONSOLE_KEY, 1).await?;
        tokio::time::sleep(pause).await;
        if open(()).await? {
            require_foreground(client).await?;
            client.key(CONSOLE_KEY, 1).await?;
        }
        Ok(())
    }

    /// Is the in-game menu (Save Game / Load Game / … / Resume) open?
    pub fn frame_has_menu(&self, frame: &image::RgbImage) -> bool {
        let Some((t, roi, threshold, search)) = &self.menu else { return false };
        let r = crate::imaging::roi_from_norm(frame.width(), frame.height(), *roi);
        crate::imaging::template_diff_search(frame, t, r[0], r[1], *search) <= *threshold
    }

    async fn frame(client: &crate::client::AgentClient) -> Result<image::RgbImage> {
        let jpeg = client.screenshot(None, None, None, None, Some(crate::imaging::MAX_SIDE as i32), Some(75)).await?;
        crate::imaging::decode_rgb(&jpeg)
    }

    /// Close the in-game menu if it is open (Esc toggles it; the "Paused" label shows beneath it,
    /// so a pause check alone cannot see it). Returns whether a key was pressed.
    pub async fn close_menu(&self, client: &crate::client::AgentClient) -> Result<bool> {
        let mut pressed = false;
        for _ in 0..2 {
            if !self.frame_has_menu(&Self::frame(client).await?) {
                return Ok(pressed);
            }
            require_foreground(client).await?;
            client.key("esc", 1).await?;
            pressed = true;
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        }
        if self.frame_has_menu(&Self::frame(client).await?) {
            bail!("the game menu is still open after two Esc presses");
        }
        Ok(pressed)
    }

    pub fn frame_is_paused(&self, frame: &image::RgbImage) -> bool {
        let r = crate::imaging::roi_from_norm(frame.width(), frame.height(), self.roi);
        if let Some((range, min)) = self.color {
            return crate::imaging::color_fraction(frame, r, range) >= min;
        }
        crate::imaging::template_diff_search(frame, &self.template, r[0], r[1], self.search) <= self.threshold
    }

    pub async fn is_paused(&self, client: &crate::client::AgentClient) -> Result<bool> {
        Ok(self.frame_is_paused(&Self::frame(client).await?))
    }

    /// Pause or resume, checking the screen before and after (Space toggles, so a blind press
    /// can invert the state). If Space has no effect, a text box or panel probably has keyboard
    /// focus (seen: "Search known star systems"); one Esc closes it before a last try. On the
    /// bare map that Esc opens the in-game menu instead (which also shows "Paused"), so the menu
    /// is closed again before the state is read. Returns whether a key was pressed.
    pub async fn set_paused(&self, client: &crate::client::AgentClient, paused: bool) -> Result<bool> {
        let closed = self.close_menu(client).await?;
        if self.is_paused(client).await? == paused {
            return Ok(closed);
        }
        for attempt in 0..3 {
            if attempt == 2 {
                require_foreground(client).await?;
                client.key("esc", 1).await?;
                tokio::time::sleep(std::time::Duration::from_millis(400)).await;
                self.close_menu(client).await?;
                if self.is_paused(client).await? == paused {
                    return Ok(true);
                }
            }
            require_foreground(client).await?;
            client.key("space", 1).await?;
            for _ in 0..5 {
                tokio::time::sleep(std::time::Duration::from_millis(200)).await;
                if self.is_paused(client).await? == paused {
                    return Ok(true);
                }
            }
        }
        bail!("could not {} the game: the Paused label did not {}", if paused { "pause" } else { "resume" }, if paused { "appear" } else { "disappear" })
    }
}

/// Reads the console's reply to `human_ai` ("… is now ON" / "… is now OFF") by comparing the
/// last output line with both templates from the manifest.
pub struct HumanAiReader {
    on: image::RgbImage,
    off: image::RgbImage,
    roi: [f64; 4],
    search: u32,
}

impl HumanAiReader {
    pub fn from_manifest(m: &crate::corpus::GameManifest) -> Result<HumanAiReader> {
        let load = |name: &str| -> Result<(image::RgbImage, [f64; 4], u32)> {
            let def = m.screens.get(name).with_context(|| format!("manifest has no [screens.{name}]"))?;
            let rel = def.template.as_ref().with_context(|| format!("[screens.{name}] has no template"))?;
            let path = m.base_dir.clone().unwrap_or_default().join(rel);
            let img = image::open(&path).with_context(|| format!("loading {}", path.display()))?.to_rgb8();
            Ok((img, def.template_roi.context("no template_roi")?, def.template_search))
        };
        let (on, roi, search) = load("human_ai_on")?;
        let (off, _, _) = load("human_ai_off")?;
        Ok(HumanAiReader { on, off, roi, search })
    }

    /// Some(true) for ON, Some(false) for OFF, None when neither is clearly closer.
    pub fn read_frame(&self, frame: &image::RgbImage) -> Option<bool> {
        // Compare only the white text: the console is semi-transparent, and a bright nebula behind it
        // pushed plain template distances past any fixed limit (0.103 vs 0.130 on an ON frame).
        // Text masks: the right word 0.000-0.023, the wrong one 0.057-0.064 on real frames.
        let r = crate::imaging::roi_from_norm(frame.width(), frame.height(), self.roi);
        let d_on = crate::imaging::text_mask_diff_search(frame, &self.on, r[0], r[1], self.search, 170);
        let d_off = crate::imaging::text_mask_diff_search(frame, &self.off, r[0], r[1], self.search, 170);
        let (best, other) = if d_on < d_off { (d_on, d_off) } else { (d_off, d_on) };
        (best < 0.04 && other - best > 0.02).then_some(d_on < d_off)
    }

    async fn toggle_and_read(&self, client: &crate::client::AgentClient) -> Result<Option<bool>> {
        // `help` fills the console, so the reply always lands on the bottom line
        for line in ["help", "human_ai"] {
            require_foreground(client).await?;
            client.type_text(line).await?;
            require_foreground(client).await?;
            client.key("enter", 1).await?;
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        }
        let jpeg = client.screenshot(None, None, None, None, Some(crate::imaging::MAX_SIDE as i32), Some(90)).await?;
        Ok(self.read_frame(&crate::imaging::decode_rgb(&jpeg)?))
    }

    /// Switch `human_ai` to `on`, reading the console's reply after each toggle.
    pub async fn set(&self, client: &crate::client::AgentClient, on: bool) -> Result<()> {
        require_foreground(client).await?;
        client.key(CONSOLE_KEY, 1).await?;
        tokio::time::sleep(std::time::Duration::from_millis(300)).await;
        let result = self.toggle_until(client, on).await;
        // close the console even when reading failed, or later keys would type into it
        let closed = match require_foreground(client).await {
            Ok(()) => client.key(CONSOLE_KEY, 1).await,
            Err(e) => Err(e),
        };
        result?;
        closed
    }

    async fn toggle_until(&self, client: &crate::client::AgentClient, on: bool) -> Result<()> {
        for _ in 0..2 {
            match self.toggle_and_read(client).await? {
                Some(state) if state == on => return Ok(()),
                Some(_) => continue, // toggled the wrong way: toggle again
                None => break,
            }
        }
        Err(anyhow!("could not read the console's reply to human_ai"))
    }
}

/// Make sure the game's AI plays the player's empire: leave observer mode if needed (`play`), then
/// switch `human_ai` on (checked on screen). Observer mode leaves the AI half-active (research and
/// warships, but no exploration or expansion), so it is never used. Returns what was done.
pub async fn take_control(
    client: &crate::client::AgentClient,
    pause: &PauseDetector,
    reader: &HumanAiReader,
    country: u64,
) -> Result<Vec<String>> {
    let mut done = vec![];
    pause.set_paused(client, true).await?;
    // a scoped log proves the console reaches a real country (not observer mode)
    let probe = format!("HARNESS_SCOPE_CHECK {}", nonce());
    let (_, before) = client.files_read(DOCS_ROOT, "logs/game.log", 0, Some(0)).await?;
    pause.run_console(client, &[format!("effect {}", scoped_log(&probe))]).await?;
    if !wait_for_log(client, before, &probe).await? {
        pause.run_console(client, &[format!("play {country}")]).await?;
        done.push(format!("left observer mode (play {country})"));
        let again = format!("HARNESS_SCOPE_CHECK {}", nonce());
        let (_, before) = client.files_read(DOCS_ROOT, "logs/game.log", 0, Some(0)).await?;
        pause.run_console(client, &[format!("effect {}", scoped_log(&again))]).await?;
        if !wait_for_log(client, before, &again).await? {
            bail!("still no country scope after `play {country}`: is this the campaign of the newest autosave?");
        }
    }
    reader.set(client, true).await?;
    done.push("human_ai is ON: the game's AI plays the empire".into());
    done.push(match bridge_loaded(client).await {
        Ok(true) => "companion mod Governor Bridge is loaded: directives also steer the AI's budget".into(),
        Ok(false) => "companion mod not loaded: directives set policies only (game-controller stellaris install-mod)".into(),
        Err(e) => format!("could not check the companion mod: {e}"),
    });
    Ok(done)
}

/// Path and modification time of the newest autosave.
async fn latest_save_path(client: &crate::client::AgentClient) -> Result<(String, u64)> {
    let mut best: Option<(u64, String)> = None;
    for dir in client.files_list(DOCS_ROOT, "save games").await?.into_iter().filter(|e| e.is_dir) {
        let rel = format!("save games/{}", dir.name);
        for f in client.files_list(DOCS_ROOT, &rel).await? {
            if !f.is_dir && f.name.ends_with(".sav") && best.as_ref().is_none_or(|(m, _)| f.modified > *m) {
                best = Some((f.modified, format!("{rel}/{}", f.name)));
            }
        }
    }
    best.map(|(m, p)| (p, m)).context("no .sav files under 'save games'")
}

// ---- companion mod ("Governor Bridge") ---------------------------------------------------------

/// Agent write root for the Stellaris documents folder (only the mod and dlc_load.json are writable).
pub const MODS_ROOT: &str = "stellaris_mods";
pub const MOD_NAME: &str = "governor_bridge";

/// dlc_load.json with `mod_ref` added to `enabled_mods` (other entries and keys are kept).
pub fn enable_mod(dlc_load: &str, mod_ref: &str) -> Result<String> {
    let mut v: serde_json::Value = if dlc_load.trim().is_empty() {
        serde_json::json!({})
    } else {
        serde_json::from_str(dlc_load.trim_start_matches('\u{feff}')).context("dlc_load.json is not JSON")?
    };
    let obj = v.as_object_mut().context("dlc_load.json is not an object")?;
    let mods = obj.entry("enabled_mods").or_insert_with(|| serde_json::json!([]));
    let list = mods.as_array_mut().context("enabled_mods is not a list")?;
    if !list.iter().any(|m| m.as_str() == Some(mod_ref)) {
        list.push(serde_json::Value::String(mod_ref.to_string()));
    }
    obj.entry("disabled_dlcs").or_insert_with(|| serde_json::json!([]));
    Ok(serde_json::to_string(&v)?)
}

/// Upload the mod from `<corpus>/mod/governor_bridge/` and enable it in dlc_load.json. The game
/// loads it at the next start. Returns the files written.
pub async fn install_mod(client: &crate::client::AgentClient, corpus_dir: &std::path::Path) -> Result<Vec<String>> {
    let src = corpus_dir.join("mod").join(MOD_NAME);
    let mut files = vec![];
    let mut stack = vec![src.clone()];
    while let Some(dir) = stack.pop() {
        for e in std::fs::read_dir(&dir).with_context(|| format!("reading {}", dir.display()))? {
            let p = e?.path();
            if p.is_dir() {
                stack.push(p);
            } else {
                files.push(p);
            }
        }
    }
    files.sort();
    let mut written = vec![];
    for f in &files {
        let rel = f.strip_prefix(&src)?.to_string_lossy().replace('\\', "/");
        let dest = format!("mod/{MOD_NAME}/{rel}");
        client.files_write(MODS_ROOT, &dest, std::fs::read(f)?).await?;
        written.push(dest);
    }
    // the launcher-level descriptor next to the folder: same fields plus the path
    let descriptor = std::fs::read_to_string(src.join("descriptor.mod")).context("mod has no descriptor.mod")?;
    let outer = format!("{}\npath=\"mod/{MOD_NAME}\"\n", descriptor.trim_end());
    client.files_write(MODS_ROOT, &format!("mod/{MOD_NAME}.mod"), outer.into_bytes()).await?;
    written.push(format!("mod/{MOD_NAME}.mod"));
    let current = match client.files_read(DOCS_ROOT, "dlc_load.json", 0, None).await {
        Ok((bytes, _)) => String::from_utf8_lossy(&bytes).into_owned(),
        Err(_) => String::new(),
    };
    let updated = enable_mod(&current, &format!("mod/{MOD_NAME}.mod"))?;
    client.files_write(MODS_ROOT, "dlc_load.json", updated.into_bytes()).await?;
    written.push("dlc_load.json".into());
    Ok(written)
}

/// Whether the running game has the mod loaded: an effect using its trigger logs only if it exists.
pub async fn bridge_loaded(client: &crate::client::AgentClient) -> Result<bool> {
    let marker = format!("GOVERNOR_BRIDGE_OK {}", nonce());
    let (_, before) = client.files_read(DOCS_ROOT, "logs/game.log", 0, Some(0)).await?;
    run_console(client, &[format!("effect if = {{ limit = {{ governor_bridge_present = yes }} log = \"{marker}\" }}")]).await?;
    wait_for_log(client, before, &marker).await
}

/// Bytes of game.log after `offset` (and the new size), via the agent.
pub async fn read_log_since(client: &crate::client::AgentClient, offset: u64) -> Result<(String, u64)> {
    let (bytes, size) = client.files_read(DOCS_ROOT, "logs/game.log", offset, None).await?;
    Ok((String::from_utf8_lossy(&bytes).into_owned(), size))
}

/// Apply a directive and confirm it from game.log. Returns the console lines sent.
pub async fn apply_directive(
    client: &crate::client::AgentClient,
    directives: &Directives,
    name: &str,
    pause: Option<&PauseDetector>,
) -> Result<Vec<String>> {
    let tag = nonce();
    let lines = directives.console_lines(name, &tag)?;
    let (_, before) = client.files_read(DOCS_ROOT, "logs/game.log", 0, Some(0)).await?;
    // Pause first: at Fastest ~2 s of typing would be months of game time. Restore it afterwards.
    let was_paused = match pause {
        Some(p) => {
            let was = p.is_paused(client).await?;
            p.set_paused(client, true).await?;
            Some(was)
        }
        None => None,
    };
    match pause {
        Some(p) => p.run_console(client, &lines).await?,
        None => run_console(client, &lines).await?,
    }
    if let (Some(p), Some(false)) = (pause, was_paused) {
        p.set_paused(client, false).await?;
    }
    let marker = applied_marker(name, &tag);
    if wait_for_log(client, before, &marker).await? {
        return Ok(lines);
    }
    bail!("directive {name} sent but {marker:?} did not appear in game.log: the empire is probably in observer \
           mode or the console did not take the line; run `stellaris take-control`")
}

// ---- small reader helpers -------------------------------------------------------------------

fn get<'d, 't>(obj: &Obj<'d, 't>, key: &str) -> Option<Val<'d, 't>> {
    obj.fields().find(|(k, _, _)| k.read_str() == key).map(|(_, _, v)| v)
}
fn obj<'d, 't>(o: &Obj<'d, 't>, key: &str) -> Option<Obj<'d, 't>> {
    get(o, key).and_then(|v| v.read_object().ok())
}
fn string(o: &Obj, key: &str) -> Option<String> {
    get(o, key).and_then(|v| v.read_string().ok())
}
fn f64_(o: &Obj, key: &str) -> Option<f64> {
    get(o, key).and_then(|v| v.read_scalar().ok()).and_then(|s| s.to_f64().ok())
}
fn i64_(o: &Obj, key: &str) -> Option<i64> {
    get(o, key).and_then(|v| v.read_scalar().ok()).and_then(|s| s.to_i64().ok())
}
/// Values of a `{ "a" "b" }` list (or of a `key={ … }` object read as an array).
fn strings(v: Option<Val>) -> Vec<String> {
    v.and_then(|v| v.read_array().ok())
        .map(|a| a.values().filter_map(|x| x.read_string().ok()).collect())
        .unwrap_or_default()
}
#[cfg(test)]
fn name_of_key(o: &Obj, key: &str) -> String {
    obj(o, key).map(|n| render_name(&n)).unwrap_or_default()
}
/// A `name={ key="…" variables={…} }` block as readable text ("NAME_Earth" → "Earth").
fn name_of(o: &Obj) -> String {
    obj(o, "name").map(|n| render_name(&n)).unwrap_or_default()
}
/// Render a localisation block. Template keys ("%ADJECTIVE%", "PREFIX_NAME_FORMAT", …) have no
/// text of their own here (the game's localisation files are not read), so they become their
/// variables' values in save order: `%ADJECTIVE%{adjective=SPEC_YaxKalock, 1=Consolidated}` →
/// "Yax Kalock Consolidated".
fn render_name(n: &Obj) -> String {
    let key = string(n, "key").unwrap_or_default();
    let vars: Vec<String> = get(n, "variables")
        .and_then(|v| v.read_array().ok())
        .map(|a| {
            a.values()
                .filter_map(|x| x.read_object().ok())
                .filter_map(|x| obj(&x, "value").map(|v| render_name(&v)))
                .filter(|t| !t.is_empty())
                .collect()
        })
        .unwrap_or_default();
    let template = key.starts_with('%') || key.ends_with("_FORMAT") || key.contains("_vs_");
    if key.starts_with("AofB") && vars.len() == 2 {
        format!("{} of {}", vars[0], vars[1])          // "AofB" {1=Hegemony 2=Kalaxenan} → "Hegemony of Kalaxenan"
    } else if (template || key.starts_with("AofB")) && !vars.is_empty() {
        vars.join(" ")
    } else if !vars.is_empty() {
        // a word that takes words: "Coalition_of" {SovereignStars} → "Coalition of Sovereign Stars"
        format!("{} {}", readable(&key), vars.join(" "))
    } else {
        readable(&key)
    }
}
fn readable(key: &str) -> String {
    // Drop scaffolding prefixes: "NAME_Earth", "SPEC_YaxKalock", "HUMAN1_PLANET_StYegorov".
    let mut k = key.strip_prefix("NAME_").unwrap_or(key);
    if let Some(species) = key.strip_prefix("SPEC_") {
        // "SPEC_Kalaxenan_planet" (a species name's planet/plural form) → "Kalaxenan"
        k = species.split('_').next().unwrap_or(species);
    }
    while let Some((head, rest)) = k.split_once('_') {
        let scaffold = !rest.is_empty() && head.chars().all(|c| c.is_ascii_uppercase() || c.is_ascii_digit());
        if !scaffold {
            break;
        }
        k = rest;
    }
    // "YaxKalock" → "Yax Kalock"; "StYegorov" → "St Yegorov"
    let mut out = String::new();
    let mut prev_lower = false;
    for ch in k.chars() {
        if ch == '_' {
            out.push(' ');
            prev_lower = false;
            continue;
        }
        if ch.is_ascii_uppercase() && prev_lower {
            out.push(' ');
        }
        prev_lower = ch.is_ascii_lowercase();
        out.push(ch);
    }
    out
}
/// `{ energy=1 minerals=2 }` → map.
fn resources(o: &Obj) -> BTreeMap<String, f64> {
    o.fields()
        .filter_map(|(k, _, v)| Some((k.read_string(), v.read_scalar().ok()?.to_f64().ok()?)))
        .collect()
}

// ---- strategy actions (tech picks, market orders) ----------------------------------------------

#[derive(Debug, Clone, PartialEq, Serialize, serde::Deserialize)]
pub struct MarketOrderSpec {
    pub side: String,
    pub resource: String,
    pub amount: i64,
}

// TechPick/choose_tech_pick/market_diff are pure selection logic, called from `pick_tech` and
// `sync_market` below (with a live `prefer`/`desired` list and a corpus tech-cost lookup) as well
// as tested directly.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct TechPick {
    pub field: String,
    pub tech: String,
    /// 0-based position of `tech` in the field's offered alternatives (the screen lists them in this order)
    pub option_index: usize,
}

/// The first preferred tech that is offered in a field whose current research is below 10% of its
/// cost (fields already researching a preferred tech are left alone).
pub fn choose_tech_pick(research: &BTreeMap<String, Research>, prefer: &[String], cost: &dyn Fn(&str) -> Option<f64>) -> Option<TechPick> {
    for want in prefer {
        for (field, r) in research {
            if let Some((cur, _)) = &r.current {
                if prefer.contains(cur) {
                    continue;
                }
            }
            let Some(idx) = r.alternatives.iter().position(|t| t == want) else { continue };
            let started = r.current.as_ref().map(|(t, p)| cost(t).map(|c| *p >= 0.1 * c).unwrap_or(*p > 0.0)).unwrap_or(false);
            if !started {
                return Some(TechPick { field: field.clone(), tech: want.clone(), option_index: idx });
            }
        }
    }
    None
}

/// Orders to add and to remove so the save's monthly trades equal `desired`.
pub fn market_diff(current: &[MarketOrderSpec], desired: &[MarketOrderSpec]) -> (Vec<MarketOrderSpec>, Vec<MarketOrderSpec>) {
    let add = desired.iter().filter(|d| !current.contains(d)).cloned().collect();
    let remove = current.iter().filter(|c| !desired.contains(c)).cloned().collect();
    (add, remove)
}

/// A calibrated `[x, y]` point from `ui.<section>.<key>` (image-space pixels; see AGENTS.md §1).
/// `ui_point` refuses an uncalibrated `[0, 0]` placeholder rather than clicking a guess.
fn ui_point(ui: &toml::Table, section: &str, key: &str) -> Result<(i32, i32)> {
    let v = ui.get(section).and_then(|s| s.get(key)).and_then(|p| p.as_array()).context(format!("manifest has no ui.{section}.{key}"))?;
    let x = v.first().and_then(|n| n.as_integer()).context("bad point")? as i32;
    let y = v.get(1).and_then(|n| n.as_integer()).context("bad point")? as i32;
    if (x, y) == (0, 0) {
        bail!("ui.{section}.{key} is not calibrated");
    }
    Ok((x, y))
}

/// Click a manifest UI point (image-space pixels): checks the game is foreground, re-establishes
/// the current image-to-screen scale from a fresh frame (mirrors the `click` CLI command), then
/// clicks. Manifest points are calibrated in `downscaled_resolution` space, not raw screen pixels.
async fn click_ui_point(client: &crate::client::AgentClient, point: (i32, i32)) -> Result<()> {
    require_foreground(client).await?;
    client.screenshot(None, None, None, None, Some(crate::imaging::MAX_SIDE as i32), Some(75)).await?;
    let orig_w = client.last_width.load(std::sync::atomic::Ordering::Relaxed).max(1) as f64;
    let target_w = client.last_target_width.load(std::sync::atomic::Ordering::Relaxed).max(1) as f64;
    let scale = orig_w / target_w;
    let (x, y) = point;
    require_foreground(client).await?;
    client.click((x as f64 * scale).round() as i32, (y as f64 * scale).round() as i32, "left", 1).await
}

/// Pick the first preferred tech offered in a field under 10% done (screen: F4, swap, option
/// card). Pauses and closes any open in-game menu first, like the other console/UI actions.
pub async fn pick_tech(
    client: &crate::client::AgentClient,
    pause: &PauseDetector,
    ui: &toml::Table,
    research: &BTreeMap<String, Research>,
    prefer: &[String],
    cost: &dyn Fn(&str) -> Option<f64>,
) -> Result<String> {
    let Some(pick) = choose_tech_pick(research, prefer, cost) else {
        return Ok("nothing to pick: no preferred tech offered in a field that is free to change".into());
    };
    pause.set_paused(client, true).await?;
    pause.close_menu(client).await?;
    let tech = ui.get("tech").context("manifest has no [ui.tech]")?;
    let str_key = |k: &str| tech.get(k).and_then(|v| v.as_str()).map(str::to_string);
    let open_key = str_key("open_key").context("ui.tech.open_key missing")?;
    let close_key = str_key("close_key").unwrap_or_else(|| "esc".to_string());

    require_foreground(client).await?;
    client.key(&open_key, 1).await?;
    tokio::time::sleep(std::time::Duration::from_millis(800)).await;

    let swap = tech
        .get("swap")
        .and_then(|s| s.get(&pick.field))
        .and_then(|p| p.as_array())
        .with_context(|| format!("manifest ui.tech.swap has no entry for field {:?}", pick.field))?;
    let sx = swap.first().and_then(|n| n.as_integer()).context("bad ui.tech.swap point")? as i32;
    let sy = swap.get(1).and_then(|n| n.as_integer()).context("bad ui.tech.swap point")? as i32;
    if (sx, sy) == (0, 0) {
        bail!("ui.tech.swap.{} is not calibrated", pick.field);
    }
    click_ui_point(client, (sx, sy)).await?;
    tokio::time::sleep(std::time::Duration::from_millis(600)).await;

    let (fx, fy) = ui_point(ui, "tech", "first_option")?;
    let pitch = tech.get("option_pitch").and_then(|v| v.as_integer()).unwrap_or(66) as i32;
    click_ui_point(client, (fx, fy + pitch * pick.option_index as i32)).await?;
    tokio::time::sleep(std::time::Duration::from_millis(500)).await;

    require_foreground(client).await?;
    client.key(&close_key, 1).await?;
    Ok(format!("picked {} in {} (option {}); the next autosave confirms it", pick.tech, pick.field, pick.option_index + 1))
}

/// One order rendered as `side resource amount` for the tool's result text.
fn describe_orders(orders: &[MarketOrderSpec]) -> String {
    if orders.is_empty() {
        return "none".to_string();
    }
    orders.iter().map(|o| format!("{} {} {}", o.side, o.resource, o.amount)).collect::<Vec<_>>().join(", ")
}

/// Screen steps for `remove` and `add`, run after the Market dialog is open (`ui.market`). Kept
/// separate from `sync_market` so the Market can always be closed afterwards, success or failure.
async fn apply_market_changes(
    client: &crate::client::AgentClient,
    ui: &toml::Table,
    current: &[MarketOrderSpec],
    remove: &[MarketOrderSpec],
    add: &[MarketOrderSpec],
) -> Result<()> {
    // Remove highest row index first so removing one order does not shift the rows below it.
    let mut idxs: Vec<usize> = remove.iter().filter_map(|r| current.iter().position(|c| c == r)).collect();
    idxs.sort_unstable_by(|a, b| b.cmp(a));
    if !idxs.is_empty() {
        let (rx, ry) = ui_point(ui, "market", "order_row_first")?;
        let pitch = ui.get("market").and_then(|m| m.get("order_row_pitch")).and_then(|v| v.as_integer()).unwrap_or(14) as i32;
        let remove_pt = ui_point(ui, "market", "remove")?;
        for i in idxs {
            click_ui_point(client, (rx, ry + pitch * i as i32)).await?;
            tokio::time::sleep(std::time::Duration::from_millis(300)).await;
            click_ui_point(client, remove_pt).await?;
            tokio::time::sleep(std::time::Duration::from_millis(400)).await;
        }
    }

    if !add.is_empty() {
        let add_pt = ui_point(ui, "market", "add")?;
        let buy_pt = ui_point(ui, "market", "buy")?;
        let sell_pt = ui_point(ui, "market", "sell")?;
        let plus_pt = ui_point(ui, "market", "plus")?;
        let confirm_pt = ui_point(ui, "market", "confirm")?;
        let resources = ui.get("market").and_then(|m| m.get("resources")).and_then(|r| r.as_table()).context("manifest ui.market has no resources table")?;
        for order in add {
            click_ui_point(client, add_pt).await?;
            tokio::time::sleep(std::time::Duration::from_millis(400)).await;
            click_ui_point(client, if order.side == "buy" { buy_pt } else { sell_pt }).await?;

            let point = resources.get(&order.resource).and_then(|p| p.as_array()).with_context(|| format!("manifest ui.market.resources has no entry for {:?}", order.resource))?;
            let rx = point.first().and_then(|n| n.as_integer()).context("bad ui.market.resources point")? as i32;
            let ry = point.get(1).and_then(|n| n.as_integer()).context("bad ui.market.resources point")? as i32;
            if (rx, ry) == (0, 0) {
                bail!("ui.market.resources.{} is not calibrated", order.resource);
            }
            click_ui_point(client, (rx, ry)).await?;
            tokio::time::sleep(std::time::Duration::from_millis(300)).await;

            // One `+` click per unit (amount is capped at 25 by MCP-layer validation).
            for _ in 0..order.amount {
                click_ui_point(client, plus_pt).await?;
            }
            click_ui_point(client, confirm_pt).await?;
            tokio::time::sleep(std::time::Duration::from_millis(400)).await;
        }
    }
    Ok(())
}

/// Add and remove monthly Market trades so they match `desired` (screen: energy icon, "Add new
/// monthly trade" dialog, order rows). The Market is never left open: on error the close key is
/// still pressed before the error is returned.
pub async fn sync_market(
    client: &crate::client::AgentClient,
    pause: &PauseDetector,
    ui: &toml::Table,
    current: &[MarketOrderSpec],
    desired: &[MarketOrderSpec],
) -> Result<String> {
    let (add, remove) = market_diff(current, desired);
    if add.is_empty() && remove.is_empty() {
        return Ok("orders already match".into());
    }
    pause.set_paused(client, true).await?;
    pause.close_menu(client).await?;

    let open_click = ui_point(ui, "market", "open_click")?;
    click_ui_point(client, open_click).await?;
    tokio::time::sleep(std::time::Duration::from_millis(600)).await;

    let result = apply_market_changes(client, ui, current, &remove, &add).await;

    // Always try to close the Market, even on error, so a failure never leaves it open over the map.
    let close_key = ui.get("market").and_then(|m| m.get("close_key")).and_then(|v| v.as_str()).unwrap_or("esc").to_string();
    let _ = require_foreground(client).await;
    let _ = client.key(&close_key, 1).await;

    result?;
    Ok(format!("added {}; removed {}", describe_orders(&add), describe_orders(&remove)))
}

/// Build a briefing from the unzipped `gamestate` text.
pub fn brief_gamestate(gamestate: &[u8]) -> Result<Briefing> {
    let tape = TextTape::from_slice(gamestate).map_err(|e| anyhow!("gamestate parse error: {e}"))?;
    let root = tape.utf8_reader();

    let mut b = Briefing {
        date: string(&root, "date").unwrap_or_default(),
        version: string(&root, "version").unwrap_or_default(),
        ..Default::default()
    };
    b.country = get(&root, "player")
        .and_then(|v| v.read_array().ok())
        .and_then(|a| a.values().next())
        .and_then(|p| p.read_object().ok())
        .and_then(|p| i64_(&p, "country"))
        .map(|c| c as u64)
        .unwrap_or(0);
    let id = b.country.to_string();

    let countries = obj(&root, "country").context("save has no country section")?;
    let Some(c) = obj(&countries, &id) else { bail!("player country {id} not found") };

    b.name = name_of(&c);
    b.last_human = string(&c, "last_date_was_human").unwrap_or_default();
    if let Some(g) = obj(&c, "government") {
        b.government = string(&g, "type").unwrap_or_default();
        b.authority = string(&g, "authority").unwrap_or_default();
        b.civics = strings(get(&g, "civics"));
        b.origin = string(&g, "origin").unwrap_or_default();
    }
    b.ethics = obj(&c, "ethos").map(|e| strings(get(&e, "ethics"))).unwrap_or_default();
    b.military_power = f64_(&c, "military_power").unwrap_or(0.0);
    b.economy_power = f64_(&c, "economy_power").unwrap_or(0.0);
    b.tech_power = f64_(&c, "tech_power").unwrap_or(0.0);
    b.victory_rank = i64_(&c, "victory_rank").unwrap_or(0);
    b.fleet_size = i64_(&c, "fleet_size").unwrap_or(0);
    b.empire_size = i64_(&c, "empire_size").unwrap_or(0);
    b.pops = i64_(&c, "num_sapient_pops").unwrap_or(0);
    b.starbases = (i64_(&c, "starbase_capacity_used").unwrap_or(0), i64_(&c, "starbase_capacity").unwrap_or(0));

    if let Some(res) = obj(&c, "modules")
        .and_then(|m| obj(&m, "standard_economy_module"))
        .and_then(|e| obj(&e, "resources"))
    {
        b.stockpile = resources(&res);
    }
    if let Some(bal) = obj(&c, "budget").and_then(|x| obj(&x, "last_month")).and_then(|x| obj(&x, "balance")) {
        for (_, _, src) in bal.fields() {
            if let Ok(src) = src.read_object() {
                for (k, v) in resources(&src) {
                    *b.net.entry(k).or_insert(0.0) += v;
                }
            }
        }
        for v in b.net.values_mut() {
            *v = (*v * 100.0).round() / 100.0;
        }
    }

    if let Some(ts) = obj(&c, "tech_status") {
        b.techs_known = ts.fields().filter(|(k, _, _)| k.read_str() == "technology").count();
        let alts = obj(&ts, "alternatives");
        for field in ["physics", "society", "engineering"] {
            let mut r = Research::default();
            if let Some(q) = get(&ts, &format!("{field}_queue")).and_then(|v| v.read_array().ok()) {
                if let Some(first) = q.values().next().and_then(|x| x.read_object().ok()) {
                    if let Some(t) = string(&first, "technology") {
                        r.current = Some((t, f64_(&first, "progress").unwrap_or(0.0)));
                    }
                }
            }
            r.alternatives = alts.as_ref().map(|a| strings(get(a, field))).unwrap_or_default();
            b.research.insert(field.to_string(), r);
        }
    }

    if let Some(ap) = get(&c, "active_policies").and_then(|v| v.read_array().ok()) {
        for p in ap.values().filter_map(|x| x.read_object().ok()) {
            if let (Some(k), Some(v)) = (string(&p, "policy"), string(&p, "selected")) {
                b.policies.insert(k, v);
            }
        }
    }
    if let Some(ed) = get(&c, "edicts").and_then(|v| v.read_array().ok()) {
        b.edicts = ed.values().filter_map(|x| x.read_object().ok()).filter_map(|e| string(&e, "edict")).collect();
    }
    b.flags = obj(&c, "flags").map(|f| f.fields().map(|(k, _, _)| k.read_string()).collect()).unwrap_or_default();

    // 4.5: `owned_planets` holds colony ids; a colony's `carrier` points at its planet.
    let planets = obj(&root, "planets").and_then(|p| obj(&p, "planet"));
    // planet id -> star system id, for counting owned systems of every empire
    let origins: std::collections::HashMap<String, i64> = planets
        .as_ref()
        .map(|ps| {
            ps.fields()
                .filter_map(|(k, _, v)| {
                    let p = v.read_object().ok()?;
                    Some((k.read_string(), i64_(&obj(&p, "coordinate")?, "origin")?))
                })
                .collect()
        })
        .unwrap_or_default();
    b.systems = systems_of(&c, &origins);
    b.expansion = expansion(&root, &c, b.country, &origins, planets.as_ref());
    b.peers = peers(&countries, &id, &c, &origins);
    let colonies = obj(&root, "colony");
    for cid in strings(get(&c, "owned_planets")) {
        let Some(col) = colonies.as_ref().and_then(|cs| obj(cs, &cid)) else { continue };
        let Some(carrier) = obj(&col, "carrier") else { continue };
        if string(&carrier, "type").as_deref() != Some("planet") {
            continue;
        }
        let Some(pid) = i64_(&carrier, "reference") else { continue };
        let Some(p) = planets.as_ref().and_then(|ps| obj(ps, &pid.to_string())) else { continue };
        b.planets.push(Planet {
            id: pid as u64,
            name: name_of(&p),
            class: string(&p, "planet_class").unwrap_or_default().trim_start_matches("pc_").to_string(),
            size: i64_(&p, "planet_size").unwrap_or(0),
            pops: i64_(&col, "num_sapient_pops"),
            stability: f64_(&col, "stability"),
            free_housing: f64_(&col, "free_housing"),
            free_amenities: f64_(&col, "free_amenities"),
            crime: f64_(&col, "crime"),
        });
    }

    if let Some(wars) = obj(&root, "war") {
        for (_, _, w) in wars.fields() {
            let Ok(w) = w.read_object() else { continue };
            if let Some(war) = war_of(&w, b.country, &countries) {
                b.wars.push(war);
            }
        }
    }
    let at_war: Vec<u64> = b.wars.iter().flat_map(|w| w.enemy_ids.iter().copied()).collect();
    b.neighbours = neighbours(&root, &countries, b.country, &c, &origins, &at_war);
    b.identity = identity(&root, &c);
    let founder = get(&c, "founder_species_ref").and_then(|v| v.read_scalar().ok()).and_then(|x| x.to_u64().ok());
    b.other_species = strings(get(&c, "owned_species_refs"))
        .iter()
        .filter_map(|r| r.parse::<u64>().ok())
        .filter(|r| Some(*r) != founder)
        .filter_map(|r| species(&root, r))
        .filter(|sp| !sp.traits.is_empty())
        .take(6)
        .collect();
    let known: std::collections::HashSet<String> = obj(&c, "tech_status")
        .map(|ts| ts.fields().filter(|(k, _, _)| k.read_str() == "technology").filter_map(|(_, _, v)| v.read_string().ok()).collect())
        .unwrap_or_default();
    b.key_techs_known = KEY_TECHS.iter().filter(|(t, _)| known.contains(*t)).map(|(t, _)| t.to_string()).collect();
    b.used_naval_capacity = i64_(&c, "used_naval_capacity").unwrap_or(0);
    let pref = b.identity.species.as_ref().and_then(|sp| preferred_class(&sp.traits));
    if let Some(ps) = planets.as_ref() {
        for pid in strings(get(&c, "controlled_planets")) {
            let Some(p) = obj(ps, &pid) else { continue };
            if get(&p, "colony").is_some() || get(&p, "owner").is_some() {
                continue;
            }
            let class = string(&p, "planet_class").unwrap_or_default().trim_start_matches("pc_").to_string();
            if let Some(f) = fit(&class, pref.as_deref()) {
                b.colony_targets.push(ColonyTarget { name: name_of(&p), class, size: i64_(&p, "planet_size").unwrap_or(0), fit: f });
            }
        }
    }
    b.galaxy = galaxy(&root, &countries, &c, b.country);
    if let Some(trades) = obj(&root, "market").and_then(|m| get(&m, "monthly_trades")).and_then(|v| v.read_array().ok()) {
        for t in trades.values().filter_map(|x| x.read_object().ok()) {
            let Some(td) = obj(&t, "trade_data") else { continue };
            if i64_(&td, "country").map(|c| c as u64) != Some(b.country) {
                continue;
            }
            let side = match string(&td, "trade_type").as_deref() { Some("market_sell") => "sell", Some("market_buy") => "buy", _ => continue };
            b.market_orders.push(MarketOrderSpec { side: side.into(), resource: string(&td, "resource").unwrap_or_default(),
                                                   amount: i64_(&t, "amount").unwrap_or(0) });
        }
    }
    Ok(b)
}

/// One war we take part in, seen from our side.
fn war_of(w: &Obj, us: u64, countries: &Obj) -> Option<War> {
    let side = |key: &str| -> Vec<u64> {
        get(w, key)
            .and_then(|v| v.read_array().ok())
            .map(|a| a.values().filter_map(|x| x.read_object().ok()).filter_map(|x| i64_(&x, "country")).map(|n| n as u64).collect())
            .unwrap_or_default()
    };
    let (attackers, defenders) = (side("attackers"), side("defenders"));
    let attacker = attackers.contains(&us);
    if !attacker && !defenders.contains(&us) {
        return None;
    }
    let who = |ids: &[u64]| -> Vec<(String, f64)> {
        ids.iter()
            .filter_map(|id| obj(countries, &id.to_string()).map(|c| (name_of(&c), f64_(&c, "military_power").unwrap_or(0.0))))
            .collect()
    };
    let names = |v: &[(String, f64)]| v.iter().map(|(n, _)| n.as_str()).collect::<Vec<_>>().join(", ");
    let (ours, theirs) = if attacker { (&attackers, &defenders) } else { (&defenders, &attackers) };
    let enemies = who(theirs);
    let goal = |key: &str| obj(w, key).and_then(|g| string(&g, "type")).unwrap_or_default();
    let (att_goal, def_goal) = (goal("attacker_war_goal"), goal("defender_war_goal"));
    let (att_ex, def_ex) = (f64_(w, "attacker_war_exhaustion").unwrap_or(0.0), f64_(w, "defender_war_exhaustion").unwrap_or(0.0));
    // each battle lists its attacker side and whether it won
    let (mut won, mut lost) = (0, 0);
    if let Some(battles) = get(w, "battles").and_then(|v| v.read_array().ok()) {
        for bt in battles.values().filter_map(|x| x.read_object().ok()) {
            let ids = |k: &str| strings(get(&bt, k)).iter().filter_map(|x| x.parse::<u64>().ok()).collect::<Vec<_>>();
            let we_attacked = ids("attackers").iter().any(|c| ours.contains(c));
            let we_defended = ids("defenders").iter().any(|c| ours.contains(c));
            if !we_attacked && !we_defended {
                continue;
            }
            let attacker_won = get(&bt, "attacker_victory").and_then(|v| v.read_string().ok()).as_deref() == Some("yes");
            if attacker_won == we_attacked { won += 1 } else { lost += 1 }
        }
    }
    Some(War {
        name: format!("{} vs {}", names(&who(&attackers)), names(&who(&defenders))),
        attacker,
        start: string(w, "start_date").unwrap_or_default(),
        enemies,
        enemy_ids: theirs.clone(),
        our_goal: if attacker { att_goal.clone() } else { def_goal.clone() },
        their_goal: if attacker { def_goal } else { att_goal },
        our_exhaustion: if attacker { att_ex } else { def_ex },
        their_exhaustion: if attacker { def_ex } else { att_ex },
        battles_won: won,
        battles_lost: lost,
    })
}

impl Briefing {
    /// Compact text for a model prompt.
    pub fn to_text(&self) -> String {
        let mut s = String::new();
        let num = |v: f64| if v.abs() >= 100.0 { format!("{v:.0}") } else { format!("{v:.1}") };
        s += &format!("# {} — {} (country {}, {})\n", self.date, self.name, self.country, self.version);
        s += &format!(
            "Government: {} / {}; ethics: {}; civics: {}; origin: {}\n",
            self.government, self.authority, self.ethics.join(", "), self.civics.join(", "), self.origin
        );
        s += &format!(
            "Power: military {:.0}, economy {:.0}, tech {:.0}; victory rank {}. Systems owned {}, colonies {}, empire size {}, pops {}, fleet size {} (naval capacity used {}; the save has no maximum), upgraded starbases {}/{}\n",
            self.military_power, self.economy_power, self.tech_power, self.victory_rank,
            self.systems, self.planets.len(), self.empire_size, self.pops, self.fleet_size, self.used_naval_capacity,
            self.starbases.0, self.starbases.1
        );
        let id = &self.identity;
        if let Some(sp) = &id.species {
            let pref = preferred_class(&sp.traits);
            let clim = pref.as_deref().and_then(climate).map(|c| format!(" ({c} climate)")).unwrap_or_default();
            s += &format!(
                "Species: {} ({}): {}{clim}\n",
                sp.name, sp.class, sp.traits.iter().map(|t| trait_label(t)).collect::<Vec<_>>().join(", ")
            );
        }
        if !self.other_species.is_empty() {
            let list: Vec<String> = self.other_species.iter().map(|sp| {
                let pref = preferred_class(&sp.traits).map(|p| format!("prefers {p}")).unwrap_or_else(|| "no climate preference".into());
                format!("{} ({pref})", sp.name)
            }).collect();
            s += &format!("Other species in the empire: {}\n", list.join(", "));
        }
        s += &format!(
            "Identity: AI personality {}; traditions {}; ascension perks {}\n",
            if id.personality.is_empty() { "none" } else { &id.personality },
            if id.traditions.is_empty() { "none".to_string() } else { id.traditions.join(", ") },
            if id.ascension_perks.is_empty() { "none".to_string() } else { id.ascension_perks.join(", ") }
        );
        s += "Resources (stock, net/month):";
        for (k, v) in &self.stockpile {
            let n = self.net.get(k).copied().unwrap_or(0.0);
            let flag = if n < 0.0 { " DEFICIT" } else { "" };
            s += &format!(" {k} {} ({}{}){flag};", num(*v), if n >= 0.0 { "+" } else { "" }, num(n));
        }
        s += "\n";
        // more than 10 years of income sitting unspent: the AI cannot use it (a market sale would)
        // trade is the market currency (stockpile capped at 50,000, docs:advanced_strategy): idle trade
        // could buy alloys or minerals on the market
        let mut idle: Vec<String> = ["energy", "minerals", "food", "alloys", "consumer_goods"].iter().filter_map(|k| {
            let (v, n) = (*self.stockpile.get(*k)?, *self.net.get(*k)?);
            (v > 5000.0 && n > 0.0 && v > n * 120.0).then(|| format!("{k} {} (over {:.0} years of income)", num(v), v / n / 12.0))
        }).collect();
        // trade is a currency, not a consumable: large and still growing means it is not being spent
        if let (Some(&v), Some(&n)) = (self.stockpile.get("trade"), self.net.get("trade")) {
            if v > 15000.0 && n > 0.0 {
                idle.push(format!("trade {} of the 50,000 cap (+{}/month; spendable only on the market)", num(v), num(n)));
            }
        }
        if !idle.is_empty() {
            s += &format!("IDLE stockpiles (unused by the AI): {}\n", idle.join(", "));
        }
        s += &format!("Research ({} techs known):\n", self.techs_known);
        for (f, r) in &self.research {
            let cur = r.current.as_ref().map(|(t, p)| format!("{t} ({p:.0} pts)")).unwrap_or_else(|| "NONE".into());
            s += &format!("- {f}: {cur}; options: {}\n", r.alternatives.join(", "));
        }
        // only the policies directives change or the governor weighs (all of them are in the JSON)
        s += "Policies: ";
        s += &["diplomatic_stance", "economic_policy", "first_contact_protocol", "war_philosophy", "trade_policy", "fleet_doctrine", "border_policy"]
            .iter()
            .filter_map(|k| self.policies.get(*k).map(|v| format!("{k}={v}")))
            .collect::<Vec<_>>()
            .join(", ");
        s += &format!("\nEdicts: {}", if self.edicts.is_empty() { "none".to_string() } else { self.edicts.join(", ") });
        s += "\nPlanets:\n";
        for p in &self.planets {
            let opt = |v: Option<f64>| v.map(num).unwrap_or_else(|| "-".into());
            s += &format!(
                "- {} ({} size {}): pops {}, stability {}, free housing {}, free amenities {}, crime {}\n",
                p.name, p.class, p.size,
                p.pops.map(|x| x.to_string()).unwrap_or_else(|| "-".into()),
                opt(p.stability), opt(p.free_housing), opt(p.free_amenities), opt(p.crime)
            );
        }
        if self.peers.empires > 0 {
            let n = self.peers.empires + 1;
            s += &format!("Standing among {n} empires (ours / median of the others / best, our rank):");
            for (key, label) in PEER_MEASURES {
                if let Some(st) = self.peers.stats.get(key) {
                    s += &format!(" {label} {} / {} / {} (#{} of {n});", num(st.ours), num(st.median), num(st.best), st.rank);
                }
            }
            s += "\n";
            if !self.peers.behind.is_empty() {
                let parts: Vec<String> = self.peers.behind.iter().filter_map(|k| {
                    let st = self.peers.stats.get(k)?;
                    let label = PEER_MEASURES.iter().find(|(m, _)| m == k).map(|(_, l)| *l).unwrap_or(k.as_str());
                    Some(format!("{label} {} vs median {}", num(st.ours), num(st.median)))
                }).collect();
                s += &format!("FALLING BEHIND (below half the median): {}\n", parts.join("; "));
            }
        }
        if !self.neighbours.is_empty() {
            let ratio = |t: f64, o: f64| if o > 0.0 { format!("{:.1}x", t / o) } else { "?".to_string() };
            s += "Neighbours (nearest first; military/economy/tech as a multiple of ours; opinion ours→them / theirs→us):\n";
            for n in &self.neighbours {
                let place = if n.borders { "shares our border".to_string() } else { format!("border distance {}", n.border_range.map(|r| r.to_string()).unwrap_or_else(|| "?".into())) };
                let op = |o: Option<i64>| o.map(|v| v.to_string()).unwrap_or_else(|| "?".into());
                let fe = if n.kind == "default" { "" } else { " [FALLEN EMPIRE]" };
                s += &format!(
                    "- {}{fe}: {place}; military {} ({}), economy {}, tech {}; systems {}, techs {}; opinion {} / {}; threat {:.0}{}\n",
                    n.name, ratio(n.military, self.military_power), num(n.military), ratio(n.economy, self.economy_power),
                    ratio(n.tech, self.tech_power), n.systems, n.techs, op(n.opinion_ours), op(n.opinion_theirs), n.threat,
                    if n.status.is_empty() { String::new() } else { format!("; {}", n.status.join(", ")) }
                );
                let i = &n.identity;
                let traits = i.species.as_ref().map(|sp| format!("{} ({})", sp.name, sp.traits.iter().map(|t| trait_label(t)).collect::<Vec<_>>().join(", "))).unwrap_or_default();
                s += &format!(
                    "  who: {}; {}; civics {}; AI personality {}; species {traits}; colonies {}; traditions {}{}\n",
                    i.ethics.join(", "), i.authority, i.civics.join(", "), i.personality, n.colonies,
                    if i.traditions.is_empty() { "none".to_string() } else { i.traditions.join(", ") },
                    if i.ascension_perks.is_empty() { String::new() } else { format!("; perks {}", i.ascension_perks.join(", ")) }
                );
            }
        }
        let x = &self.expansion;
        s += &format!(
            "Expansion room: 1 jump from our space {} systems ({} unclaimed, {} held by others); within 2 jumps {} ({} unclaimed, {} of them surveyed by us first). Ships: {} construction, {} science, {} colony\n",
            x.near, x.near_unclaimed, x.near_foreign, x.reach, x.reach_unclaimed, x.reach_unclaimed_surveyed,
            x.construction_ships, x.science_ships, x.colony_ships
        );
        if x.reach > 0 && x.reach_unclaimed == 0 {
            s += "BOXED IN: no unclaimed systems within 2 jumps; growth now means diplomacy, war or colonising planets inside our borders\n";
        } else if x.reach_unclaimed > 0 && x.construction_ships == 0 {
            s += "NO CONSTRUCTION SHIP: unclaimed systems are in reach but nothing can build outposts\n";
        }
        if self.colony_targets.is_empty() {
            s += "Colonisable planets inside our borders: none (growth needs habitats, terraforming, other species, or new territory)\n";
        } else {
            let list: Vec<String> = self.colony_targets.iter().map(|t| format!("{} ({} size {}, {})", t.name, t.class, t.size, t.fit)).collect();
            s += &format!("Colonisable planets inside our borders ({}): {}\n", list.len(), list.join("; "));
        }
        let (have, missing): (Vec<_>, Vec<_>) = KEY_TECHS.iter().partition(|(t, _)| self.key_techs_known.iter().any(|k| k == t));
        s += &format!(
            "Growth and fleet-capacity techs: have {}; missing {}\n",
            if have.is_empty() { "none".to_string() } else { have.iter().map(|(_, n)| *n).collect::<Vec<_>>().join(", ") },
            if missing.is_empty() { "none".to_string() } else { missing.iter().map(|(_, n)| *n).collect::<Vec<_>>().join(", ") }
        );
        if self.wars.is_empty() {
            s += "Wars: none\n";
        } else {
            for w in &self.wars {
                let enemies = w.enemies.iter().map(|(n, m)| format!("{n} (military {m:.0})")).collect::<Vec<_>>().join(", ");
                let goal = |g: &str| if g.is_empty() { "none".to_string() } else { g.trim_start_matches("wg_").replace('_', " ") };
                s += &format!(
                    "War since {}: {} (we are {}) against {}; war goals: theirs {}, ours {}; war exhaustion ours {:.0}%, theirs {:.0}% (100% lets the other side force peace); battles won {}, lost {}\n",
                    w.start, w.name, if w.attacker { "attacker" } else { "defender" }, enemies,
                    goal(&w.their_goal), goal(&w.our_goal), w.our_exhaustion * 100.0, w.their_exhaustion * 100.0,
                    w.battles_won, w.battles_lost
                );
            }
        }
        let gx = &self.galaxy;
        if let Some(f) = &gx.federation {
            let assoc = if f.associates.is_empty() { String::new() } else { format!("; associates: {}", f.associates.join(", ")) };
            s += &format!(
                "Federation: {} ({}, level {}, cohesion {:.0}{}); members: {}{}\n",
                f.name, f.kind.replace('_', " "), f.level, f.cohesion, if f.we_lead { ", we lead it" } else { "" },
                f.members.join(", "), assoc
            );
        }
        if let Some(gc) = gx.community.as_ref().filter(|gc| gc.members > 0) {
            let vote = gc.voting.as_ref().map(|(t, by, st)| format!("; voting now: {t} (proposed by {by}; we are {st})")).unwrap_or_default();
            let passed = if gc.passed.is_empty() { String::new() } else { format!("; recently passed: {}", gc.passed.join(", ")) };
            s += &format!(
                "Galactic Community: {} ({} members){vote}{passed}\n",
                if gc.we_are_member { "we are a member" } else { "we are not a member" }, gc.members
            );
        }
        if gx.crises.is_empty() {
            s += "Crisis: none active\n";
        } else {
            let list: Vec<String> = gx.crises.iter().map(|(t, n, m)| format!("{n} [{t}] military {m:.0}")).collect();
            s += &format!("CRISIS / galaxy-level threat: {}\n", list.join("; "));
        }
        for (t, p, a) in &gx.situations {
            s += &format!("Situation: {t}, progress {p:.0}, approach {a}\n");
        }
        let gov: Vec<&String> = self.flags.iter().filter(|f| f.starts_with("governor_")).collect();
        if !gov.is_empty() {
            s += &format!("Governor flags: {}\n", gov.iter().map(|x| x.as_str()).collect::<Vec<_>>().join(", "));
        }
        s
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAVE: &[u8] = include_bytes!("../tests/fixtures/stellaris_2200_11_01.sav");

    #[test]
    fn briefs_a_real_autosave() {
        let b = brief_save(SAVE).unwrap();
        assert_eq!(b.date, "2200.11.01");
        assert_eq!(b.version, "Cygnus v4.5.1");
        assert_eq!(b.country, 0);
        assert_eq!(b.name, "United Nations of Earth");
        assert_eq!(b.government, "gov_representative_democracy");
        assert_eq!(b.ethics, ["ethic_fanatic_egalitarian", "ethic_xenophile"]);
        assert_eq!(b.policies["diplomatic_stance"], "diplo_stance_isolationist");
        assert!(b.flags.iter().any(|f| f == "harness_probe2"));
        assert!((b.stockpile["energy"] - 429.68223).abs() < 1e-6);
        assert!((b.net["energy"] - 82.12).abs() < 0.01, "net energy {}", b.net["energy"]);
        assert_eq!(b.techs_known, 31); // queued techs are not known yet
        assert_eq!(b.research["physics"].current.as_ref().unwrap().0, "tech_physics_1");
        assert!(!b.research["society"].alternatives.is_empty());
        let earth = b.planets.iter().find(|p| p.name == "Earth").expect("Earth listed");
        assert_eq!(earth.class, "continental");
        assert_eq!(earth.stability, Some(85.24));
        assert_eq!(earth.pops, Some(5327));
        assert_eq!(b.systems, 1, "only Sol in 2200.11");
        assert_eq!(b.last_human, "2200.09.24");
        assert!(b.wars.is_empty());
        assert!(b.edicts.is_empty());
    }

    #[test]
    fn peers_flag_the_stagnant_empire() {
        // 2212.03: our empire (observer mode) still had 1 system while the AI empires had 9-18
        let b = brief_save(include_bytes!("../tests/fixtures/stellaris_2212_03_01.sav")).unwrap();
        assert_eq!(b.peers.empires, 12, "regular AI empires in this medium galaxy");
        let sys = &b.peers.stats["systems"];
        assert_eq!(sys.ours, 1.0);
        assert!(sys.median >= 8.0, "median {}", sys.median);
        assert!(sys.rank > b.peers.empires / 2);
        assert!(b.peers.behind.contains(&"systems".to_string()));
        let t = b.to_text();
        assert!(t.contains("FALLING BEHIND (below half the median): systems 1.0 vs median"), "{t}");
        // why it stagnated: plenty of room, and construction/science ships existed
        let x = &b.expansion;
        assert!(x.near > 0 && x.reach >= x.near, "{x:?}");
        assert!(x.reach_unclaimed > 0, "{x:?}");
        assert!(x.construction_ships >= 1 && x.science_ships >= 1, "{x:?}");
        // 2200.11: everyone still has one system, nothing to flag for systems; Sol's neighbours are free
        let e = brief_save(SAVE).unwrap().expansion;
        assert_eq!(e.near_foreign, 0, "{e:?}");
        assert!(e.near_unclaimed > 0, "{e:?}");
        let early = brief_save(SAVE).unwrap();
        assert!(!early.peers.behind.contains(&"systems".to_string()));
    }

    #[test]
    fn text_briefing_is_compact_and_flags_deficits() {
        let mut b = brief_save(SAVE).unwrap();
        b.net.insert("food".into(), -3.0);
        let t = b.to_text();
        assert!(t.starts_with("# 2200.11.01"));
        assert!(t.contains("food 580 (-3.0) DEFICIT"), "{t}");
        assert!(t.contains("diplomatic_stance=diplo_stance_isolationist"));
        assert!(t.len() < 4000, "briefing is {} bytes", t.len());
    }

    fn directives() -> Directives {
        Directives::load(&std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/stellaris")).unwrap()
    }

    #[test]
    fn directive_console_lines_take_control_apply_and_hand_back() {
        let d = directives();
        let lines = d.console_lines("expand", "k3x9").unwrap();
        assert_eq!(lines.len(), 2, "no play/observe: the empire stays player-controlled under human_ai");
        assert!(lines[0].starts_with("effect remove_country_flag = governor_directive_"));
        assert!(!lines[0].contains("governor_directive_expand "));
        let apply = &lines[1];
        assert!(apply.contains("set_country_flag = governor_directive_expand"));
        // each policy is set only when the game would allow it (the option's `valid` block)
        assert!(apply.contains("if = { limit = { is_homicidal = no } set_policy = { policy = diplomatic_stance option = diplo_stance_expansionist cooldown = no } }"), "{apply}");
        assert!(apply.contains("if = { limit = { is_homicidal = no is_xenophobe = no NOT = { has_origin = origin_payback } } set_policy = { policy = first_contact_protocol option = first_contact_proactive cooldown = no } }"), "{apply}");
        assert!(apply.ends_with("if = { limit = { exists = capital_scope } log = \"GOVERNOR_APPLIED expand k3x9\" }"));
        for name in d.directive.keys() {
            let ls = d.console_lines(name, "k3x9").unwrap();
            assert!(ls.iter().all(|l| l.len() < 1000), "{name}: agent /type limit");
        }
        assert!(d.console_lines("nuke_everyone", "x").is_err());
        assert!(check_condition("is_xenophobe = no NOT = { has_origin = origin_payback }").is_ok());
        assert!(check_condition("is_xenophobe = no } add_resource = { energy = 1").is_err(), "unbalanced braces");
        assert!(check_condition("is_xenophobe = no\"").is_err(), "quotes could end the console line's strings");
        let (a, b) = (nonce(), { std::thread::sleep(std::time::Duration::from_millis(2)); nonce() });
        assert!(a != b && a.chars().all(|c| c.is_ascii_alphanumeric()), "{a} {b}");
    }

    #[test]
    fn directive_identifiers_are_whitelisted() {
        assert!(check_ident("diplo_stance_expansionist").is_ok());
        for bad in ["", "a b", "x\"", "x}", "Play", "x;observe", "a=b"] {
            assert!(check_ident(bad).is_err(), "{bad:?}");
        }
    }

    #[test]
    fn pause_detector_tells_paused_from_running_frames() {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/stellaris");
        let corpus = crate::corpus::GameCorpus::load_from_dir(&dir).unwrap();
        let d = PauseDetector::from_manifest(&corpus.manifest).unwrap();
        // Fixtures are the (600,800)-(1000,882) crop of real 1568x882 frames; paste them back.
        let load = |f: &str| {
            let crop = image::open(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(f)).unwrap().to_rgb8();
            let mut frame = image::RgbImage::new(1568, 882);
            image::imageops::replace(&mut frame, &crop, 600, 800);
            frame
        };
        assert!(d.frame_is_paused(&load("stellaris_paused.jpg")));
        // Same label mid-pulse: the pixel template scored 0.108 here and misread it as running.
        assert!(d.frame_is_paused(&load("stellaris_paused_dim.jpg")));
        assert!(!d.frame_is_paused(&load("stellaris_running.jpg")));
    }

    #[test]
    fn game_menu_is_recognised_under_the_paused_label() {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/stellaris");
        let corpus = crate::corpus::GameCorpus::load_from_dir(&dir).unwrap();
        let d = PauseDetector::from_manifest(&corpus.manifest).unwrap();
        // Fixtures: the (680,270)-(890,600) crop of real paused frames with and without the menu.
        let load = |f: &str| {
            let crop = image::open(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(f)).unwrap().to_rgb8();
            let mut frame = image::RgbImage::new(1568, 882);
            image::imageops::replace(&mut frame, &crop, 680, 270);
            frame
        };
        assert!(d.frame_has_menu(&load("stellaris_game_menu.jpg")));
        assert!(!d.frame_has_menu(&load("stellaris_no_menu.jpg")), "the map behind the menu is not the menu");
        assert!(!d.frame_has_menu(&image::RgbImage::new(1568, 882)));
    }

    #[test]
    fn human_ai_reply_is_read_from_the_console_line() {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/stellaris");
        let corpus = crate::corpus::GameCorpus::load_from_dir(&dir).unwrap();
        let r = HumanAiReader::from_manifest(&corpus.manifest).unwrap();
        // fixtures: the (0,150)-(380,235) crop of real frames after `help` + `human_ai`
        let load = |f: &str| {
            let crop = image::open(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(f)).unwrap().to_rgb8();
            let mut frame = image::RgbImage::new(1568, 882);
            image::imageops::replace(&mut frame, &crop, 0, 150);
            frame
        };
        assert_eq!(r.read_frame(&load("stellaris_human_ai_on.jpg")), Some(true));
        assert_eq!(r.read_frame(&load("stellaris_human_ai_off.jpg")), Some(false));
        // a live frame with a different map behind the console (distances 0.039 / 0.071)
        assert_eq!(r.read_frame(&load("stellaris_human_ai_off_live.jpg")), Some(false));
        // a bright nebula behind the console (plain template distances 0.103 / 0.130)
        assert_eq!(r.read_frame(&load("stellaris_human_ai_on_nebula.jpg")), Some(true));
        assert_eq!(r.read_frame(&image::RgbImage::new(1568, 882)), None, "no console: unknown");
    }

    #[test]
    fn enable_mod_keeps_other_mods_and_is_idempotent() {
        let out = enable_mod(r#"{"enabled_mods":["mod/ugc_1.mod"],"disabled_dlcs":["x"]}"#, "mod/governor_bridge.mod").unwrap();
        let v: serde_json::Value = serde_json::from_str(&out).unwrap();
        assert_eq!(v["enabled_mods"], serde_json::json!(["mod/ugc_1.mod", "mod/governor_bridge.mod"]));
        assert_eq!(v["disabled_dlcs"], serde_json::json!(["x"]));
        assert_eq!(enable_mod(&out, "mod/governor_bridge.mod").unwrap(), out, "second install changes nothing");
        let fresh: serde_json::Value = serde_json::from_str(&enable_mod("", "mod/governor_bridge.mod").unwrap()).unwrap();
        assert_eq!(fresh["enabled_mods"], serde_json::json!(["mod/governor_bridge.mod"]));
        assert!(enable_mod("\u{feff}{\"enabled_mods\":[]}", "m").is_ok(), "BOM accepted");
        assert!(enable_mod("[1,2]", "m").is_err());
    }

    #[test]
    fn mod_files_are_well_formed() {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/stellaris/mod/governor_bridge");
        let descriptor = std::fs::read_to_string(dir.join("descriptor.mod")).unwrap();
        assert!(descriptor.contains("supported_version=\"v4.5.*\"") && !descriptor.contains("path="));
        for f in ["common/ai_budget/zz_governor_bridge_budget.txt", "common/scripted_triggers/zz_governor_bridge_triggers.txt"] {
            let text = std::fs::read_to_string(dir.join(f)).unwrap();
            jomini::TextTape::from_slice(text.as_bytes()).unwrap_or_else(|e| panic!("{f}: {e}"));
            let opens = text.matches('{').count();
            assert_eq!(opens, text.matches('}').count(), "{f}: unbalanced braces");
        }
        let budget = std::fs::read_to_string(dir.join("common/ai_budget/zz_governor_bridge_budget.txt")).unwrap();
        // every entry is gated on a directive flag that exists
        let d = Directives::load(&dir.join("../..")).unwrap();
        for flag in budget.split("has_country_flag = ").skip(1).map(|s| s.split_whitespace().next().unwrap()) {
            let name = flag.strip_prefix("governor_directive_").expect(flag);
            assert!(d.directive.contains_key(name), "{flag} is not a directive");
        }
        assert_eq!(budget.matches("potential = { has_country_flag = governor_directive_").count(), budget.matches(" = {\n\tresource =").count());

        // Each (resource, category) must be one a non-nomadic empire spends from in vanilla 4.5.1
        // (common/ai_budget, read 2026-09-26); e.g. influence in `starbases` is nomad-only, and
        // outposts take influence from `stations`.
        const VANILLA: [(&str, &str); 11] = [
            ("alloys", "ships"), ("alloys", "starbases"), ("alloys", "colonies"), ("alloys", "planets"),
            ("alloys", "megastructures_habitat"), ("influence", "megastructures_habitat"),
            ("influence", "stations"), ("influence", "claims"), ("influence", "edicts"),
            ("minerals", "planets"), ("minerals", "stations"),
        ];
        let tape = jomini::TextTape::from_slice(budget.as_bytes()).unwrap();
        let mut checked = 0;
        for (key, _op, value) in tape.windows1252_reader().fields() {
            checked += 1;
            let entry = value.read_object().unwrap();
            let (mut resource, mut category) = (String::new(), String::new());
            for (k, _o, v) in entry.fields() {
                match k.read_str().as_ref() {
                    "resource" => resource = v.read_string().unwrap(),
                    "category" => category = v.read_string().unwrap(),
                    _ => {}
                }
            }
            let name = key.read_str();
            assert!(VANILLA.contains(&(resource.as_str(), category.as_str())), "{name}: {resource} in {category} is not spent by a non-nomadic empire");
        }
        assert_eq!(checked, budget.matches("\tresource =").count());
    }

    #[test]
    fn war_is_described_from_our_side_with_readable_names() {
        // Shapes copied from a 4.5.1 save (2236): templated names, sides, goals, exhaustion, battles.
        let gs = br#"date="2230.01.01"
player={ { name="x" country=0 } }
country={
    0={ name={ key="NAME_United_Nations_of_Earth" } type="default" military_power=1000
        relations_manager={ relation={ owner=0 country=16777224 contact=yes borders=yes border_range=0 relation_current=-300 threat=40 hostile=yes is_rival=yes } } }
    16777224={ name={ key="%ADJECTIVE%" variables={ { key="adjective" value={ key="SPEC_YaxKalock" } } { key="1" value={ key="%ADJ%" variables={ { key="1" value={ key="Consolidated" } } } } } } }
        type="default" military_power=2500
        relations_manager={ relation={ owner=16777224 country=0 contact=yes relation_current=-450 } } }
}
war={ 0=none 1={
    name={ key="war_vs_adjectives" variables={ { key="1" value={ key="%ADJECTIVE%" variables={ { key="adjective" value={ key="SPEC_YaxKalock" } } } } } } }
    start_date="2229.11.07"
    attackers={ { call_type=primary country=16777224 } }
    defenders={ { call_type=primary country=0 } }
    battles={ { defenders={ 0 } attackers={ 16777224 } attacker_victory=yes }
              { defenders={ 0 } attackers={ 16777224 } attacker_victory=no }
              { defenders={ 16777224 } attackers={ 0 } attacker_victory=no } }
    attacker_war_goal={ type="wg_conquest" }
    defender_war_goal={ type="wg_humiliation" }
    attacker_war_exhaustion=0.48141 defender_war_exhaustion=0.25
} }
"#;
        let b = brief_gamestate(gs).unwrap();
        assert_eq!(b.name, "United Nations of Earth");
        let w = &b.wars[0];
        assert_eq!(w.name, "Yax Kalock Consolidated vs United Nations of Earth");
        assert!(!w.attacker);
        assert_eq!(w.enemies, vec![("Yax Kalock Consolidated".to_string(), 2500.0)]);
        assert_eq!((w.our_goal.as_str(), w.their_goal.as_str()), ("wg_humiliation", "wg_conquest"));
        assert_eq!((w.our_exhaustion, w.their_exhaustion), (0.25, 0.48141));
        assert_eq!((w.battles_won, w.battles_lost), (1, 2), "we won a defence, lost a defence and an attack");
        let t = b.to_text();
        assert!(t.contains("War since 2229.11.07: Yax Kalock Consolidated vs United Nations of Earth (we are defender) against Yax Kalock Consolidated (military 2500); war goals: theirs conquest, ours humiliation; war exhaustion ours 25%, theirs 48%"), "{t}");
        let n = &b.neighbours[0];
        assert_eq!((n.name.as_str(), n.borders, n.opinion_ours, n.opinion_theirs), ("Yax Kalock Consolidated", true, Some(-300), Some(-450)));
        assert_eq!(n.status, vec!["AT WAR", "rival", "hostile"]);
        assert!(t.contains("- Yax Kalock Consolidated: shares our border; military 2.5x (2500)"), "{t}");
    }

    #[test]
    fn federation_community_crises_and_situations() {
        // Shapes copied from the 2278.06 autosave (federation, galactic_community, resolution,
        // situations); the crisis country is synthetic (none was active).
        let gs = br#"date="2278.06.01"
player={ { name="x" country=0 } }
country={
    0={ name={ key="NAME_Us" } type="default" federation=1 }
    1={ name={ key="NAME_Ess_Jaggon_Authority" } type="default" }
    7={ name={ key="NAME_Rihi_Nar" } type="default" }
    9={ name={ key="Prethoryn_Scourge" } type="swarm" military_power=90000 }
}
federation={ 0={ name={ key="NAME_Other" } } 1={
    name={ key="%ADJ%" variables={ { key="1" value={ key="Coalition_of" variables={ { key="1" value={ key="SovereignStars" } } } } } } }
    federation_progression={ federation_type="research_federation" levels=3 cohesion=100 }
    members={ 0 1 } associates={ 7 } leader=0 } }
galactic_community={ members={ 0 1 7 } voting=4 passed={ 1 3 } }
resolution={ 1={ type="resolution_galactic_market_form" country=1 } 3={ type="resolution_industry_regulatory_facilitation" country=7 }
    4={ type="resolution_industry_collective_waste_management" country=7 supporters={ 7 } opponents={ 0 } } }
situations={ situations={ 0=none 1={ country=0 type="rebellion_situation" progress=42.5 approach="approach_crackdown" }
    2={ country=7 type="other_situation" progress=1 approach="x" } } }
"#;
        let b = brief_gamestate(gs).unwrap();
        let f = b.galaxy.federation.as_ref().unwrap();
        assert_eq!(f.name, "Coalition of Sovereign Stars");
        assert!(f.we_lead);
        assert_eq!(f.members, vec!["us", "Ess Jaggon Authority"]);
        assert_eq!(f.associates, vec!["Rihi Nar"]);
        let gc = b.galaxy.community.as_ref().unwrap();
        assert_eq!(gc.voting, Some(("industry collective waste management".into(), "Rihi Nar".into(), "against".into())));
        assert_eq!(gc.passed, vec!["industry regulatory facilitation", "galactic market form"]);
        assert_eq!(b.galaxy.crises, vec![("swarm".to_string(), "Prethoryn Scourge".to_string(), 90000.0)]);
        assert_eq!(b.galaxy.situations, vec![("rebellion situation".to_string(), 42.5, "crackdown".to_string())]);
        let t = b.to_text();
        assert!(t.contains("Federation: Coalition of Sovereign Stars (research federation, level 3, cohesion 100, we lead it); members: us, Ess Jaggon Authority; associates: Rihi Nar"), "{t}");
        assert!(t.contains("voting now: industry collective waste management (proposed by Rihi Nar; we are against)"), "{t}");
        assert!(t.contains("CRISIS / galaxy-level threat: Prethoryn Scourge [swarm] military 90000"), "{t}");
        assert!(t.contains("Situation: rebellion situation, progress 42, approach crackdown"), "{t}");
    }

    #[test]
    fn planet_fit_follows_the_species_climate_preference() {
        let wet = Some("continental");
        assert_eq!(fit("continental", wet).as_deref(), Some("preferred"));
        assert_eq!(fit("ocean", wet).as_deref(), Some("same climate"));
        assert_eq!(fit("tundra", wet).as_deref(), Some("other climate"));
        assert_eq!(fit("gaia", wet).as_deref(), Some("any species"));
        assert_eq!(fit("toxic", wet), None, "toxic worlds are not colonizable in 4.5");
        assert_eq!(fit("barren", wet), None);
        assert_eq!(preferred_class(&["trait_adaptive".into(), "trait_pc_arid_preference".into()]).as_deref(), Some("arid"));
        assert_eq!(trait_label("trait_pc_ocean_preference"), "prefers ocean");
        assert_eq!(trait_label("trait_rapid_breeders"), "rapid breeders");
    }

    #[test]
    fn species_identity_and_key_techs_from_a_real_save() {
        let b = brief_save(include_bytes!("../tests/fixtures/stellaris_2212_03_01.sav")).unwrap();
        let sp = b.identity.species.as_ref().unwrap();
        assert_eq!((sp.name.as_str(), sp.class.as_str()), ("Humans", "HUM"));
        assert!(sp.traits.contains(&"trait_pc_continental_preference".to_string()), "{sp:?}");
        assert_eq!(b.identity.personality, "federation builders");
        assert_eq!(b.identity.ethics, vec!["fanatic egalitarian", "xenophile"]);
        let n = &b.neighbours[0];
        assert_eq!(n.identity.personality, "erudite explorers");
        assert!(n.identity.species.as_ref().unwrap().traits.contains(&"trait_rapid_breeders".to_string()));
        let t = b.to_text();
        assert!(t.contains("Species: Humans (HUM): organic, adaptive, nomadic, wasteful, prefers continental (wet climate)"), "{t}");
        assert!(t.contains("  who: xenophile, fanatic materialist; dictatorial; civics shadow council, philosopher king"), "{t}");
        assert!(t.contains("Growth and fleet-capacity techs: have none; missing Orbital Habitats"), "{t}");
        assert!(t.contains("IDLE stockpiles (unused by the AI): energy"), "{t}");
        assert!(b.peers.stats.contains_key("colonies"));
    }

    #[test]
    fn idle_stockpiles_flag_hoards_and_growing_trade() {
        let mut b = Briefing::default();
        for (k, v, n) in [("energy", 39485.0, 4.1), ("minerals", 900.0, 80.0), ("trade", 18824.0, 255.0), ("alloys", 20000.0, -3.0)] {
            b.stockpile.insert(k.to_string(), v);
            b.net.insert(k.to_string(), n);
        }
        let t = b.to_text();
        let line = t.lines().find(|l| l.starts_with("IDLE stockpiles")).expect("an IDLE line");
        assert!(line.contains("energy 39485 (over 803 years of income)"), "{line}");
        assert!(line.contains("trade 18824 of the 50,000 cap (+255/month"), "{line}");
        assert!(!line.contains("minerals") && !line.contains("alloys"), "small or shrinking stocks are not idle: {line}");
    }

    #[test]
    fn console_is_recognised_by_its_debug_view_bar() {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/stellaris");
        let corpus = crate::corpus::GameCorpus::load_from_dir(&dir).unwrap();
        let d = PauseDetector::from_manifest(&corpus.manifest).unwrap();
        // fixtures: the (0,200)-(400,260) crop of real frames with the console open and closed
        let load = |f: &str| {
            let crop = image::open(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(f)).unwrap().to_rgb8();
            let mut frame = image::RgbImage::new(1568, 882);
            image::imageops::replace(&mut frame, &crop, 0, 200);
            frame
        };
        assert!(d.frame_has_console(&load("stellaris_console_open.jpg")));
        assert!(!d.frame_has_console(&load("stellaris_console_closed.jpg")));
        assert!(!d.frame_has_console(&image::RgbImage::new(1568, 882)));
    }

    #[test]
    fn readable_names_drop_scaffolding() {
        assert_eq!(readable("NAME_Earth"), "Earth");
        assert_eq!(readable("HUMAN1_PLANET_StYegorov"), "St Yegorov");
        assert_eq!(readable("SPEC_YaxKalock"), "Yax Kalock");
        assert_eq!(readable("NAME_United_Nations_of_Earth"), "United Nations of Earth");
        assert_eq!(readable("Consolidated"), "Consolidated");
        assert_eq!(readable("SPEC_Kalaxenan_planet"), "Kalaxenan");
        let gs = br#"n={ key="AofB" variables={ { key="1" value={ key="Hegemony" } } { key="2" value={ key="SPEC_Kalaxenan_planet" } } } }"#;
        let tape = jomini::TextTape::from_slice(gs).unwrap();
        assert_eq!(name_of_key(&tape.utf8_reader(), "n"), "Hegemony of Kalaxenan");
    }

    #[test]
    fn neighbours_come_from_contacts_nearest_first() {
        let b = brief_save(include_bytes!("../tests/fixtures/stellaris_2212_03_01.sav")).unwrap();
        let n = &b.neighbours[0];
        assert_eq!(n.name, "Havarigga High Kingdom");
        assert_eq!(n.border_range, Some(0));
        assert!(n.military > 0.0 && n.systems > 0, "{n:?}");
        assert!(b.to_text().contains("Neighbours (nearest first"));
        assert!(brief_save(SAVE).unwrap().neighbours.is_empty(), "2200.11: no contacts yet");
    }

    #[test]
    fn speed_names() {
        assert_eq!(speed_index("slowest").unwrap(), 0);
        assert_eq!(speed_index("Normal").unwrap(), 2);
        assert_eq!(speed_index("fast").unwrap(), 3);
        assert_eq!(speed_index("faster").unwrap(), 4);
        assert_eq!(speed_index("fastest").unwrap(), 4);
        assert!(speed_index("ludicrous").is_err());
    }

    #[test]
    fn rejects_non_saves() {
        assert!(brief_save(b"not a zip").is_err());
        assert!(brief_gamestate(b"date=\"2200.01.01\"\n").is_err()); // no country section
    }

    #[test]
    fn tech_pick_prefers_offered_techs_and_leaves_started_research_alone() {
        let mut research = BTreeMap::new();
        research.insert("engineering".to_string(), Research { current: Some(("tech_mining_2".into(), 50.0)),
            alternatives: vec!["tech_mining_2".into(), "tech_habitat_1".into(), "tech_lasers_2".into()] });
        research.insert("society".to_string(), Research { current: Some(("tech_gene_crops".into(), 900.0)),
            alternatives: vec!["tech_gene_crops".into(), "tech_doctrine_navy_size_2".into()] });
        let cost = |t: &str| Some(if t == "tech_mining_2" { 1000.0 } else { 2000.0 });
        let prefer = vec!["tech_doctrine_navy_size_2".to_string(), "tech_habitat_1".to_string()];
        let pick = choose_tech_pick(&research, &prefer, &cost).unwrap();
        // society is 45% done (900/2000): not swapped; engineering is 5% done: swapped to habitats (option 2)
        assert_eq!((pick.field.as_str(), pick.tech.as_str(), pick.option_index), ("engineering", "tech_habitat_1", 1));
        // already researching a preferred tech: nothing to do
        let mut r2 = research.clone();
        r2.get_mut("engineering").unwrap().current = Some(("tech_habitat_1".into(), 0.0));
        assert!(choose_tech_pick(&r2, &["tech_habitat_1".to_string()], &cost).is_none());
        // no preferred tech offered: nothing
        assert!(choose_tech_pick(&research, &["tech_zro_1".to_string()], &cost).is_none());
    }

    #[test]
    fn market_diff_adds_missing_and_removes_unwanted_orders() {
        let o = |s: &str, r: &str, a: i64| MarketOrderSpec { side: s.into(), resource: r.into(), amount: a };
        let (add, remove) = market_diff(&[o("sell", "energy", 11), o("buy", "food", 5)], &[o("sell", "energy", 11), o("sell", "trade", 20)]);
        assert_eq!(add, vec![o("sell", "trade", 20)]);
        assert_eq!(remove, vec![o("buy", "food", 5)]);
    }

    #[test]
    fn ui_point_names_missing_keys_and_refuses_uncalibrated_points() {
        let mut market = toml::Table::new();
        market.insert("add".into(), toml::Value::Array(vec![toml::Value::Integer(382), toml::Value::Integer(156)]));
        market.insert("remove".into(), toml::Value::Array(vec![toml::Value::Integer(0), toml::Value::Integer(0)]));
        let mut ui = toml::Table::new();
        ui.insert("market".into(), toml::Value::Table(market));

        let err = ui_point(&ui, "market", "open_click").unwrap_err().to_string();
        assert!(err.contains("ui.market.open_click"), "{err}");

        let err = ui_point(&ui, "market", "remove").unwrap_err().to_string();
        assert!(err.contains("ui.market.remove") && err.contains("not calibrated"), "{err}");

        assert_eq!(ui_point(&ui, "market", "add").unwrap(), (382, 156));
    }

    #[test]
    fn briefing_reads_our_monthly_trades() {
        let gs = br#"date="2201.10.01"
player={ { name="x" country=0 } }
country={ 0={ name={ key="NAME_Us" } type="default" } }
market={ monthly_trades={ { trade_data={ trade_type=market_sell resource="energy" country=0 } amount=11 price=0 id=0 }
                          { trade_data={ trade_type=market_buy resource="minerals" country=7 } amount=5 price=0 id=1 } } }
"#;
        let b = brief_gamestate(gs).unwrap();
        assert_eq!(b.market_orders, vec![MarketOrderSpec { side: "sell".into(), resource: "energy".into(), amount: 11 }]);
    }
}

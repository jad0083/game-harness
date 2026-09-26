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

#[derive(Debug, Serialize, Default)]
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

#[derive(Debug, Serialize)]
pub struct War {
    pub name: String,
    pub attacker: bool,
}

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
    pub techs_known: usize,
    pub research: BTreeMap<String, Research>,
    pub policies: BTreeMap<String, String>,
    pub flags: Vec<String>,
    pub planets: Vec<Planet>,
    pub wars: Vec<War>,
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
            b.name = name;
        }
    }
    Ok(b)
}

/// Agent root holding the Stellaris documents folder (saves, logs, settings).
pub const DOCS_ROOT: &str = "stellaris_docs";

/// Newest autosave across all save folders, fetched through the agent: (path, bytes).
pub async fn fetch_latest_save(client: &crate::client::AgentClient) -> Result<(String, Vec<u8>)> {
    let mut best: Option<(u64, String)> = None;
    for dir in client.files_list(DOCS_ROOT, "save games").await?.into_iter().filter(|e| e.is_dir) {
        let rel = format!("save games/{}", dir.name);
        for f in client.files_list(DOCS_ROOT, &rel).await? {
            if !f.is_dir && f.name.ends_with(".sav") && best.as_ref().is_none_or(|(m, _)| f.modified > *m) {
                best = Some((f.modified, format!("{rel}/{}", f.name)));
            }
        }
    }
    let (_, path) = best.context("no .sav files under 'save games'")?;
    let (bytes, _) = client.files_read(DOCS_ROOT, &path, 0, None).await?;
    Ok((path, bytes))
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
/// Localisation key of a `name={ key="…" }` block, made readable ("NAME_Earth" → "Earth").
fn name_of(o: &Obj) -> String {
    let key = obj(o, "name").and_then(|n| string(&n, "key")).unwrap_or_default();
    readable(&key)
}
fn readable(key: &str) -> String {
    let k = key.strip_prefix("NAME_").unwrap_or(key);
    k.replace('_', " ")
}
/// `{ energy=1 minerals=2 }` → map.
fn resources(o: &Obj) -> BTreeMap<String, f64> {
    o.fields()
        .filter_map(|(k, _, v)| Some((k.read_string(), v.read_scalar().ok()?.to_f64().ok()?)))
        .collect()
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
    b.flags = obj(&c, "flags").map(|f| f.fields().map(|(k, _, _)| k.read_string()).collect()).unwrap_or_default();

    // 4.5: `owned_planets` holds colony ids; a colony's `carrier` points at its planet.
    let planets = obj(&root, "planets").and_then(|p| obj(&p, "planet"));
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
            let side_has = |side: &str| {
                get(&w, side)
                    .and_then(|v| v.read_array().ok())
                    .map(|a| {
                        a.values().filter_map(|x| x.read_object().ok()).any(|x| {
                            i64_(&x, "country").map(|n| n as u64) == Some(b.country)
                        })
                    })
                    .unwrap_or(false)
            };
            let (att, def) = (side_has("attackers"), side_has("defenders"));
            if att || def {
                b.wars.push(War { name: name_of(&w), attacker: att });
            }
        }
    }
    Ok(b)
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
            "Power: military {:.0}, economy {:.0}, tech {:.0}; victory rank {}. Empire size {}, pops {}, fleet size {}, starbases {}/{}\n",
            self.military_power, self.economy_power, self.tech_power, self.victory_rank,
            self.empire_size, self.pops, self.fleet_size, self.starbases.0, self.starbases.1
        );
        s += "Resources (stock, net/month):";
        for (k, v) in &self.stockpile {
            let n = self.net.get(k).copied().unwrap_or(0.0);
            let flag = if n < 0.0 { " DEFICIT" } else { "" };
            s += &format!(" {k} {} ({}{}){flag};", num(*v), if n >= 0.0 { "+" } else { "" }, num(n));
        }
        s += "\n";
        s += &format!("Research ({} techs known):\n", self.techs_known);
        for (f, r) in &self.research {
            let cur = r.current.as_ref().map(|(t, p)| format!("{t} ({p:.0} pts)")).unwrap_or_else(|| "NONE".into());
            s += &format!("- {f}: {cur}; options: {}\n", r.alternatives.join(", "));
        }
        s += "Policies: ";
        s += &self.policies.iter().map(|(k, v)| format!("{k}={v}")).collect::<Vec<_>>().join(", ");
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
        if self.wars.is_empty() {
            s += "Wars: none\n";
        } else {
            for w in &self.wars {
                s += &format!("War: {} (we are {})\n", w.name, if w.attacker { "attacker" } else { "defender" });
            }
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
        assert!(b.wars.is_empty());
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

    #[test]
    fn rejects_non_saves() {
        assert!(brief_save(b"not a zip").is_err());
        assert!(brief_gamestate(b"date=\"2200.01.01\"\n").is_err()); // no country section
    }
}

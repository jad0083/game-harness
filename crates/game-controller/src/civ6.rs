//! Civilization VI governor surface (docs/design/2026-09-26-civ6-governor-design.md).
//!
//! The helper library `corpora/civ6/lua/harness.lua` is installed into the game's Lua states
//! through the agent's tuner relay; every call is `Harness.run(Harness.<fn>, <args>)`, which
//! prints one JSON line. Orders arrive as structured JSON naming corpus ids (`tech:pottery`),
//! are checked against `corpora/civ6/data`, and become one template call whose arguments are
//! encoded here ([`lua_str`]): text from a model never reaches Lua any other way.

use anyhow::{bail, Context, Result};
use serde::Deserialize;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

use crate::client::AgentClient;

/// The Lua state that holds the UI's view of the game: reads (era score, government, policy
/// slots, military strength, purchase prices), production, purchases, policies and autoplay.
pub const STATE_UI: &str = "InGame";
/// The game-state VM (`GameCore_Tuner`): research and civic choices (the UI's request for them is
/// ignored when sent from the tuner; the GameCore setters work and survive autoplay).
pub const STATE_CORE: &str = "GameCore";
/// Printed by a guarded call when the library is not installed (or is another version).
const MISSING: &str = "HARNESS_MISSING";
/// Printed instead of an InGame call while this load's popups are not quieted yet.
const LOUD: &str = "HARNESS_POPUPS_LOUD";
/// Autoplay stretches are short: the governor decides again between them.
pub const MAX_AUTOPLAY_TURNS: u32 = 50;

/// A Lua string literal holding exactly `s`: quotes, backslashes, control characters and every
/// non-ASCII byte are written as escapes, so the result is printable ASCII between two quotes and
/// cannot end the string, start a comment or run code, whatever `s` contains.
pub fn lua_str(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for b in s.bytes() {
        match b {
            b'"' => out.push_str("\\\""),
            b'\\' => out.push_str("\\\\"),
            b'\n' => out.push_str("\\n"),
            b'\t' => out.push_str("\\t"),
            0x20..=0x7e => out.push(b as char),
            // three digits always, so a following digit is never read as part of the escape
            _ => out.push_str(&format!("\\{b:03}")),
        }
    }
    out.push('"');
    out
}

/// A city named by the model: its game ID or its name as shown.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(untagged)]
pub enum CityRef {
    Id(i64),
    Name(String),
}

impl CityRef {
    fn lua(&self) -> Result<String> {
        match self {
            CityRef::Id(i) => Ok(i.to_string()),
            CityRef::Name(n) if n.trim().is_empty() || n.len() > 64 => bail!("city name must be 1-64 characters"),
            CityRef::Name(n) => Ok(lua_str(n.trim())),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Currency {
    Gold,
    Faith,
}

impl Currency {
    fn name(self) -> &'static str {
        match self {
            Currency::Gold => "gold",
            Currency::Faith => "faith",
        }
    }
}

/// One structured order (`civ6 order '<json>'`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(tag = "kind", rename_all = "lowercase", deny_unknown_fields)]
pub enum Order {
    Research { id: String },
    Civic { id: String },
    Policies { ids: Vec<String> },
    Production { city: CityRef, id: String },
    Purchase { city: CityRef, id: String, currency: Currency, #[serde(default)] max_cost: Option<f64> },
    /// Read-only: the live price of an item in a city (ruling 6).
    Price { city: CityRef, id: String, currency: Currency },
}

impl Order {
    pub fn parse(json: &str) -> Result<Order> {
        serde_json::from_str(json).context("order must be one JSON object with a known `kind` (research, civic, policies, production, purchase, price) and its fields")
    }
}

/// Corpus ids -> the game's type keys, from `data/<kind>.json` (`aliases[0]` is the type key).
pub struct CorpusIds {
    types: HashMap<String, (String, String)>,     // id -> (kind, type key)
    purchase: HashMap<String, String>,            // id -> fields.purchase ("gold" | "faith" | "none")
}

#[derive(Deserialize)]
struct RawRecord {
    id: String,
    #[serde(default)]
    aliases: Vec<String>,
    #[serde(default)]
    fields: serde_json::Map<String, serde_json::Value>,
}

const ORDER_KINDS: &[&str] = &["tech", "civic", "policy", "unit", "building", "district", "project", "wonder"];

impl CorpusIds {
    pub fn load(corpus: &Path) -> Result<Self> {
        let mut types = HashMap::new();
        let mut purchase = HashMap::new();
        for kind in ORDER_KINDS {
            let path = corpus.join("data").join(format!("{kind}.json"));
            let raw = std::fs::read_to_string(&path).with_context(|| format!("reading {}", path.display()))?;
            let recs: Vec<RawRecord> = serde_json::from_str(&raw).with_context(|| format!("parsing {}", path.display()))?;
            for r in recs {
                let Some(key) = r.aliases.first() else { continue };
                if let Some(p) = r.fields.get("purchase").and_then(|v| v.as_str()) {
                    purchase.insert(r.id.clone(), p.to_string());
                }
                types.insert(r.id, (kind.to_string(), key.clone()));
            }
        }
        Ok(Self { types, purchase })
    }

    /// The type key of `id` when it is one of `kinds`.
    fn key(&self, id: &str, kinds: &[&str]) -> Result<String> {
        match self.types.get(id.trim()) {
            Some((kind, key)) if kinds.contains(&kind.as_str()) => Ok(key.clone()),
            Some((kind, _)) => bail!("{id:?} is a {kind}; this order takes {}", kinds.join(" / ")),
            None => bail!("unknown id {id:?} (use corpus ids such as {}:<name>; `corpus search` finds them)", kinds[0]),
        }
    }
}

/// The Lua state and the template call for an order, with every argument encoded here.
pub fn order_call(order: &Order, ids: &CorpusIds) -> Result<(&'static str, String)> {
    Ok(match order {
        Order::Research { id } => (STATE_CORE, format!("Harness.run(Harness.set_research, {})", lua_str(&ids.key(id, &["tech"])?))),
        Order::Civic { id } => (STATE_CORE, format!("Harness.run(Harness.set_civic, {})", lua_str(&ids.key(id, &["civic"])?))),
        Order::Policies { ids: list } => {
            if list.is_empty() || list.len() > 12 {
                bail!("policies: 1-12 policy ids");
            }
            let keys = list.iter().map(|p| ids.key(p, &["policy"]).map(|k| lua_str(&k))).collect::<Result<Vec<_>>>()?;
            (STATE_UI, format!("Harness.run(Harness.set_policies, {{{}}})", keys.join(", ")))
        }
        Order::Production { city, id } => {
            if ids.types.get(id.trim()).is_some_and(|(k, _)| k == "wonder") {
                bail!("{id}: wonders need a tile; placement is not supported yet");
            }
            let key = ids.key(id, &["unit", "building", "district", "project"])?;
            (STATE_UI, format!("Harness.run(Harness.set_production, {}, {})", city.lua()?, lua_str(&key)))
        }
        Order::Purchase { city, id, currency, max_cost } => {
            let key = purchase_key(ids, id)?;
            let cap = match max_cost {
                Some(c) if !c.is_finite() || *c < 0.0 => bail!("max_cost must be a number >= 0"),
                Some(c) => format!("{}", c.floor() as i64),
                None => "nil".into(),
            };
            (STATE_UI, format!("Harness.run(Harness.purchase, {}, {}, {}, {cap})", city.lua()?, lua_str(&key), lua_str(currency.name())))
        }
        Order::Price { city, id, currency } => {
            let key = purchase_key(ids, id)?;
            (STATE_UI, format!("Harness.run(Harness.get_purchase_cost, {}, {}, {})", city.lua()?, lua_str(&key), lua_str(currency.name())))
        }
    })
}

fn purchase_key(ids: &CorpusIds, id: &str) -> Result<String> {
    let key = ids.key(id, &["unit", "building"])?;
    if ids.purchase.get(id.trim()).map(String::as_str) == Some("none") {
        bail!("{id} cannot be bought (corpus: purchase = none)");
    }
    Ok(key)
}

/// `Harness.run(Harness.autoplay, n)`.
pub fn autoplay_call(turns: u32) -> Result<String> {
    if !(1..=MAX_AUTOPLAY_TURNS).contains(&turns) {
        bail!("autoplay turns must be 1..{MAX_AUTOPLAY_TURNS}");
    }
    Ok(format!("Harness.run(Harness.autoplay, {turns})"))
}

/// A popup that holds the game's engine event until it is closed (`corpora/civ6/popups.toml`):
/// during autoplay nobody closes it and the AI's turn never ends, so its handler is removed.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct QuietPopup {
    /// The popup's own Lua state (its handlers are globals there).
    pub state: String,
    pub event: String,
    pub handler: String,
}

impl QuietPopup {
    /// Removes the handler; prints QUIET, QUIET_ABSENT (the state has no such handler or event: a
    /// renamed handler) or QUIET_ERR with the reason. Removing it twice is harmless (checked live).
    pub fn code(&self) -> String {
        let (e, h) = (&self.event, &self.handler);
        format!("if Events and Events.{e} and {h} then local ok, err = pcall(function() Events.{e}.Remove({h}) end) \
                 print(ok and \"QUIET\" or (\"QUIET_ERR \" .. tostring(err))) else print(\"QUIET_ABSENT\") end")
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PopupsFile {
    #[serde(default)]
    quiet: Vec<QuietPopup>,
}

fn lua_name(s: &str) -> bool {
    let mut c = s.chars();
    matches!(c.next(), Some(f) if f.is_ascii_alphabetic() || f == '_') && c.all(|ch| ch.is_ascii_alphanumeric() || ch == '_')
}

/// The `[[quiet]]` entries of a popups table; every name must be a plain Lua identifier (they are
/// written into Lua as they are).
pub fn parse_popups(text: &str) -> Result<Vec<QuietPopup>> {
    let f: PopupsFile = toml::from_str(text)?;
    for p in &f.quiet {
        for (field, v) in [("state", &p.state), ("event", &p.event), ("handler", &p.handler)] {
            if !lua_name(v) {
                bail!("popups: {field} {v:?} is not a Lua name");
            }
        }
    }
    Ok(f.quiet)
}

/// The library file and its version (FNV-1a of the text: any edit re-installs it), with the popups
/// to quiet after installing it into `InGame`.
pub struct Library {
    pub path: PathBuf,
    pub source: String,
    pub version: String,
    pub popups: Vec<QuietPopup>,
}

impl Library {
    pub fn load(corpus: &Path) -> Result<Self> {
        let path = corpus.join("lua").join("harness.lua");
        let source = std::fs::read_to_string(&path).with_context(|| format!("reading {}", path.display()))?;
        let mut h: u64 = 0xcbf29ce484222325;
        for b in source.bytes() {
            h ^= b as u64;
            h = h.wrapping_mul(0x100000001b3);
        }
        let table = corpus.join("popups.toml");
        let text = std::fs::read_to_string(&table).with_context(|| format!("reading {}", table.display()))?;
        let popups = parse_popups(&text).with_context(|| format!("in {}", table.display()))?;
        Ok(Self { path, source, version: format!("{h:016x}"), popups })
    }

    /// The chunk that installs the library (a no-op when this version is already there).
    pub fn install_code(&self) -> String {
        format!("local HARNESS_VERSION = {}\n{}", lua_str(&self.version), self.source)
    }

    /// `call` run only when this version is installed; otherwise it prints the missing marker.
    pub fn guarded(&self, call: &str) -> String {
        format!("if Harness and Harness.version == {} then {call} else print({}) end", lua_str(&self.version), lua_str(MISSING))
    }

    /// [`Self::guarded`], and `call` runs only once the popups are quiet (`Harness.popups_quiet`);
    /// otherwise it prints the loud marker and nothing runs.
    pub fn guarded_quiet(&self, call: &str) -> String {
        self.guarded(&format!("if Harness.popups_quiet then {call} else print({}) end", lua_str(LOUD)))
    }
}

/// The last printed line that is a JSON object.
pub fn parse_output(lines: &[String]) -> Result<serde_json::Value> {
    for l in lines.iter().rev() {
        let t = l.trim();
        if t.starts_with('{') {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(t) {
                if v.is_object() {
                    return Ok(v);
                }
            }
        }
    }
    let shown: String = lines.join("\n").chars().take(600).collect();
    bail!("no JSON from the game's Lua: {}", if shown.is_empty() { "(nothing printed)".into() } else { shown })
}

fn printed(r: &crate::client::LuaReply) -> Vec<String> {
    if !r.output.is_empty() {
        return r.output.clone();
    }
    std::iter::once(r.result.clone()).chain(r.extra.iter().cloned()).collect()
}

/// Run a library call in `state`, installing the library there first when it is missing.
pub async fn call(client: &AgentClient, lib: &Library, state: &str, call: &str) -> Result<serde_json::Value> {
    call_with(client, lib, state, call, 15_000).await
}

/// `call` waiting at most `wait_ms` for the game's first reply (a status poll during the AI's turn
/// should give up quickly: the tuner is silent then). In InGame the call waits for the popups: after
/// a load (library missing) or while an earlier attempt left some unsettled, they are quieted first,
/// before the call can start autoplay, and the reply gains `popups_quieted`.
pub async fn call_with(client: &AgentClient, lib: &Library, state: &str, call: &str, wait_ms: u64) -> Result<serde_json::Value> {
    let ui = state == STATE_UI && !lib.popups.is_empty();
    let first = if ui { lib.guarded_quiet(call) } else { lib.guarded(call) };
    let lines = printed(&client.tuner_lua(state, &first, Some(wait_ms)).await?);
    let missing = lines.iter().any(|l| l.trim() == MISSING);
    if !missing && !lines.iter().any(|l| l.trim() == LOUD) {
        return parse_output(&lines);
    }
    if missing {
        let installed = printed(&client.tuner_lua(state, &lib.install_code(), Some(15_000)).await?);
        if installed.iter().any(|l| l.contains("ERR") || l.contains("rror")) {
            bail!("installing {} in {state} failed: {}", lib.path.display(), installed.join(" ").chars().take(600).collect::<String>());
        }
    }
    let mut quieted = None;
    let mut call = call.to_string();
    if ui {
        let q = quiet_popups(client, &lib.popups).await;
        if q.iter().all(|l| quiet_settled(l)) {
            call = format!("Harness.popups_quiet = true {call}");
        } else {
            eprintln!("popups not all quieted (retried on the next InGame call): {}", q.join(", "));
        }
        quieted = Some(q);
    }
    let lines = printed(&client.tuner_lua(state, &lib.guarded(&call), Some(15_000)).await?);
    if lines.iter().any(|l| l.trim() == MISSING) {
        bail!("the library did not stay installed in {state} (is a game loaded?)");
    }
    let mut v = parse_output(&lines)?;
    if let (Some(q), Some(o)) = (quieted, v.as_object_mut()) {
        o.insert("popups_quieted".into(), q.into());
    }
    Ok(v)
}

/// The QUIET line a popup call printed, else what it printed instead.
fn quiet_outcome(lines: &[String]) -> String {
    lines.iter().find(|l| l.starts_with("QUIET")).cloned()
        .or_else(|| lines.first().cloned())
        .unwrap_or_else(|| "no reply".into())
}

/// Whether a `quiet_popups` line needs no retry: removed, absent from a state that exists (a
/// handler renamed by a patch shows up here, in the reply), or no such state in this ruleset (a game
/// without Gathering Storm has no disaster popup).
pub fn quiet_settled(line: &str) -> bool {
    line.ends_with(" QUIET") || line.ends_with(" QUIET_ABSENT") || line.contains("no Lua state named")
}

/// Remove the handlers of the popups that would hold an autoplay turn, one tuner call each; one
/// `<state>.<handler> <outcome>` per popup, where the outcome is QUIET, QUIET_ABSENT, QUIET_ERR …,
/// or `failed: …` (a timeout or a missing state).
pub async fn quiet_popups(client: &AgentClient, popups: &[QuietPopup]) -> Vec<String> {
    let mut out = Vec::with_capacity(popups.len());
    for p in popups {
        let outcome = match client.tuner_lua(&p.state, &p.code(), Some(5_000)).await {
            Ok(r) => quiet_outcome(&printed(&r)),
            Err(e) => format!("failed: {}", e.to_string().chars().take(200).collect::<String>()),
        };
        out.push(format!("{}.{} {outcome}", p.state, p.handler));
    }
    out
}

/// Whether a library reply reports success (`{"ok": false, ...}` makes the command exit 2).
pub fn reply_ok(v: &serde_json::Value) -> bool {
    v.get("ok") != Some(&serde_json::Value::Bool(false))
}

/// Fields every snapshot has; a snapshot without them is an error, not something to decide on.
pub const SNAPSHOT_KEYS: &[&str] = &["turn", "civ", "leader", "yields", "gold", "faith", "cities", "majors", "wars", "units", "policy_slots"];

pub fn check_snapshot(v: &serde_json::Value) -> Result<()> {
    if v.get("ok") == Some(&serde_json::Value::Bool(false)) {
        bail!("snapshot failed in the game: {}", v.get("error").and_then(|e| e.as_str()).unwrap_or("?"));
    }
    let missing: Vec<&str> = SNAPSHOT_KEYS.iter().copied().filter(|k| v.get(*k).is_none()).collect();
    if !missing.is_empty() {
        bail!("snapshot lacks {}", missing.join(", "));
    }
    if !v["cities"].is_array() || !v["turn"].is_u64() {
        bail!("snapshot: cities must be a list and turn a number");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Decode a Lua 5.1 string literal the way the game's parser does (the escapes lua_str emits).
    fn lua_decode(lit: &str) -> Vec<u8> {
        let b = lit.as_bytes();
        assert!(b.len() >= 2 && b[0] == b'"' && b[b.len() - 1] == b'"', "not a quoted literal: {lit}");
        let mut out = Vec::new();
        let mut i = 1;
        while i < b.len() - 1 {
            match b[i] {
                b'"' => panic!("unescaped quote inside {lit}"),
                b'\\' => {
                    let c = b[i + 1];
                    i += 2;
                    match c {
                        b'n' => out.push(b'\n'),
                        b't' => out.push(b'\t'),
                        b'"' | b'\\' => out.push(c),
                        b'0'..=b'9' => {
                            let digits = std::str::from_utf8(&b[i - 1..i + 2]).unwrap();
                            out.push(digits.parse::<u8>().unwrap());
                            i += 2;
                        }
                        _ => panic!("unexpected escape in {lit}"),
                    }
                }
                c => {
                    out.push(c);
                    i += 1;
                }
            }
        }
        out
    }

    #[test]
    fn lua_str_round_trips_hostile_text() {
        for s in ["Beijing", "", "a\"b", "back\\slash", "\"); os.exit() --", "]] print(1) --[[", "line\nbreak\r\0nul",
                  "Xi’an", "Zürich 北京", "\\\"", "9\u{1}2", "end\\"] {
            let lit = lua_str(s);
            assert!(lit.bytes().all(|b| (0x20..=0x7e).contains(&b)), "non-printable in {lit:?}");
            assert_eq!(lua_decode(&lit), s.as_bytes(), "{s:?} -> {lit}");
        }
        assert_eq!(lua_str("\u{1}2"), "\"\\0012\"", "a digit after an escape stays a separate character");
    }

    fn ids() -> CorpusIds {
        CorpusIds::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/civ6")).unwrap()
    }

    #[test]
    fn orders_become_template_calls_with_encoded_arguments() {
        let ids = ids();
        let call = |j: &str| order_call(&Order::parse(j).unwrap(), &ids).unwrap();
        assert_eq!(call(r#"{"kind":"research","id":"tech:pottery"}"#),
                   (STATE_CORE, r#"Harness.run(Harness.set_research, "TECH_POTTERY")"#.to_string()));
        assert_eq!(call(r#"{"kind":"civic","id":"civic:code_of_laws"}"#).1, r#"Harness.run(Harness.set_civic, "CIVIC_CODE_OF_LAWS")"#);
        assert_eq!(call(r#"{"kind":"policies","ids":["policy:god_king","policy:discipline"]}"#),
                   (STATE_UI, r#"Harness.run(Harness.set_policies, {"POLICY_GOD_KING", "POLICY_DISCIPLINE"})"#.to_string()));
        assert_eq!(call(r#"{"kind":"production","city":"Beijing","id":"unit:settler"}"#).1,
                   r#"Harness.run(Harness.set_production, "Beijing", "UNIT_SETTLER")"#);
        assert_eq!(call(r#"{"kind":"production","city":65536,"id":"building:monument"}"#).1,
                   r#"Harness.run(Harness.set_production, 65536, "BUILDING_MONUMENT")"#);
        assert_eq!(call(r#"{"kind":"purchase","city":"Beijing","id":"unit:warrior","currency":"gold","max_cost":120.7}"#).1,
                   r#"Harness.run(Harness.purchase, "Beijing", "UNIT_WARRIOR", "gold", 120)"#);
        assert_eq!(call(r#"{"kind":"price","city":"Beijing","id":"unit:warrior","currency":"faith"}"#).1,
                   r#"Harness.run(Harness.get_purchase_cost, "Beijing", "UNIT_WARRIOR", "faith")"#);
    }

    #[test]
    fn a_city_name_cannot_break_out_of_its_string() {
        let ids = ids();
        let o = Order::parse(r#"{"kind":"production","city":"x\") Players[0]:GetTreasury():SetGoldBalance(99999) --","id":"unit:warrior"}"#).unwrap();
        let (_, lua) = order_call(&o, &ids).unwrap();
        assert_eq!(lua, r#"Harness.run(Harness.set_production, "x\") Players[0]:GetTreasury():SetGoldBalance(99999) --", "UNIT_WARRIOR")"#);
        let lit = &lua["Harness.run(Harness.set_production, ".len()..lua.rfind(", \"UNIT_WARRIOR\"").unwrap()];
        assert_eq!(lua_decode(lit), br#"x") Players[0]:GetTreasury():SetGoldBalance(99999) --"#);
    }

    #[test]
    fn invalid_orders_are_refused_before_reaching_the_game() {
        let ids = ids();
        let err = |j: &str| match Order::parse(j) {
            Err(e) => format!("{e:#}"),
            Ok(o) => order_call(&o, &ids).unwrap_err().to_string(),
        };
        assert!(err(r#"{"kind":"research","id":"tech:warp_drive"}"#).contains("unknown id"));
        assert!(err(r#"{"kind":"research","id":"civic:code_of_laws"}"#).contains("is a civic"));
        assert!(err(r#"{"kind":"research","id":"TECH_POTTERY"}"#).contains("unknown id"), "raw type keys are not ids");
        assert!(err(r#"{"kind":"lua","code":"print(1)"}"#).contains("known `kind`"));
        assert!(err(r#"{"kind":"research","id":"tech:pottery","extra":"x"}"#).contains("known `kind`"));
        assert!(err(r#"{"kind":"production","city":"Beijing","id":"wonder:pyramids"}"#).contains("placement"));
        assert!(err(r#"{"kind":"purchase","city":"Beijing","id":"district:campus","currency":"gold"}"#).contains("is a district"));
        assert!(err(r#"{"kind":"purchase","city":"Beijing","id":"unit:warrior","currency":"iron"}"#).contains("known `kind`"));
        assert!(err(r#"{"kind":"purchase","city":"Beijing","id":"unit:warrior","currency":"gold","max_cost":-1}"#).contains("max_cost"));
        assert!(err(r#"{"kind":"policies","ids":[]}"#).contains("1-12"));
        assert!(err(r#"{"kind":"production","city":"","id":"unit:warrior"}"#).contains("city name"));
    }

    #[test]
    fn purchase_refuses_items_the_corpus_says_cannot_be_bought() {
        let ids = ids();
        let none = ids.purchase.iter().find(|(id, p)| p.as_str() == "none" && ids.types[*id].0 == "unit").map(|(id, _)| id.clone());
        if let Some(id) = none {
            let o = Order::Purchase { city: CityRef::Name("Beijing".into()), id: id.clone(), currency: Currency::Gold, max_cost: None };
            assert!(order_call(&o, &ids).unwrap_err().to_string().contains("cannot be bought"), "{id}");
        }
    }

    #[test]
    fn a_false_ok_is_a_failed_reply() {
        assert!(!reply_ok(&serde_json::json!({"ok": false, "error": "x"})));
        assert!(reply_ok(&serde_json::json!({"ok": true, "active": false})));
    }

    #[test]
    fn autoplay_turns_are_bounded() {
        assert_eq!(autoplay_call(5).unwrap(), "Harness.run(Harness.autoplay, 5)");
        assert!(autoplay_call(0).is_err());
        assert!(autoplay_call(MAX_AUTOPLAY_TURNS + 1).is_err());
    }

    #[test]
    fn library_install_is_versioned_and_guarded() {
        let lib = Library::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/civ6")).unwrap();
        assert_eq!(lib.version.len(), 16);
        assert!(lib.install_code().starts_with(&format!("local HARNESS_VERSION = \"{}\"\n", lib.version)));
        assert!(lib.source.contains("if Harness and Harness.version == HARNESS_VERSION then"), "idempotent install guard");
        let g = lib.guarded("Harness.run(Harness.snapshot)");
        assert!(g.starts_with(&format!("if Harness and Harness.version == \"{}\" then Harness.run(Harness.snapshot) else print(\"HARNESS_MISSING\") end", lib.version)));
        assert!(lib.source.contains("MIT License"), "civ6-mcp attribution");
    }

    #[test]
    fn output_parsing_takes_the_last_json_object() {
        let lines = vec!["noise".to_string(), r#"{"ok":true,"a":1}"#.to_string(), r#"{"ok":true,"a":2}"#.into(), "tail".into()];
        assert_eq!(parse_output(&lines).unwrap()["a"], 2);
        assert!(parse_output(&["ERR:Runtime Error: boom".to_string()]).unwrap_err().to_string().contains("boom"));
        assert!(parse_output(&[]).unwrap_err().to_string().contains("nothing printed"));
    }

    #[test]
    fn live_snapshot_fixture_parses_and_has_the_ruled_fields() {
        let raw = std::fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/civ6_snapshot.json")).unwrap();
        let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
        check_snapshot(&v).unwrap();
        assert!(v["cities"][0]["name"].is_string() && v["cities"][0]["producing"].is_string());
        for k in ["science", "culture", "faith", "gold", "food", "production"] {
            assert!(v["yields"][k].is_number(), "yields.{k}");
        }
        assert!(v["options"]["techs"].is_array() && v["cities"][0]["can_build"].is_array());
        for k in ["era", "era_score", "government", "research", "civic", "military", "score", "map_seed", "autoplay"] {
            assert!(v.get(k).is_some(), "{k}");
        }
        let mut broken = v.clone();
        broken.as_object_mut().unwrap().remove("cities");
        assert!(check_snapshot(&broken).unwrap_err().to_string().contains("cities"));
        assert!(check_snapshot(&serde_json::json!({"ok": false, "error": "boom"})).unwrap_err().to_string().contains("boom"));
    }

    #[test]
    fn engine_locking_popups_are_listed() {
        let lib = Library::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/civ6")).unwrap();
        let names: Vec<String> = lib.popups.iter().map(|p| format!("{}.{}.{}", p.state, p.event, p.handler)).collect();
        for want in ["WonderBuiltPopup.WonderCompleted.OnWonderCompleted", "NaturalWonderPopup.NaturalWonderRevealed.OnNaturalWonderRevealed",
                     "ProjectBuiltPopup.CityProjectCompletedNarrative.OnProjectComplete", "NaturalDisasterPopup.RandomEventStarted.OnRandomEventStarted",
                     "NaturalDisasterPopup.RandomEventOccurred.OnRandomEventOccurred", "RockBandMoviePopup.PostTourismBomb.OnRockBandConcert"] {
            assert!(names.iter().any(|n| n == want), "{want} missing from popups.toml");
        }
    }

    #[test]
    fn quieting_a_popup_removes_its_handler_and_says_what_happened() {
        let p = QuietPopup { state: "WonderBuiltPopup".into(), event: "WonderCompleted".into(), handler: "OnWonderCompleted".into() };
        assert_eq!(p.code(), concat!(
            "if Events and Events.WonderCompleted and OnWonderCompleted then ",
            "local ok, err = pcall(function() Events.WonderCompleted.Remove(OnWonderCompleted) end) ",
            "print(ok and \"QUIET\" or (\"QUIET_ERR \" .. tostring(err))) else print(\"QUIET_ABSENT\") end"));
        assert_eq!(quiet_outcome(&["x".into(), "QUIET".into()]), "QUIET");
        assert_eq!(quiet_outcome(&["ERR:Runtime Error: boom".into()]), "ERR:Runtime Error: boom");
        assert_eq!(quiet_outcome(&[]), "no reply");
        assert!(quiet_settled("WonderBuiltPopup.OnWonderCompleted QUIET"));
        assert!(quiet_settled("WonderBuiltPopup.OnWonderCompleted QUIET_ABSENT"));
        assert!(quiet_settled("RockBandMoviePopup.OnRockBandConcert failed: agent 400: no Lua state named \"RockBandMoviePopup\""));
        assert!(!quiet_settled("WonderBuiltPopup.OnWonderCompleted failed: timed out"));
        assert!(!quiet_settled("WonderBuiltPopup.OnWonderCompleted QUIET_ERR boom"));
        assert!(!quiet_settled("WonderBuiltPopup.OnWonderCompleted no reply"));
    }

    #[test]
    fn ingame_calls_wait_until_the_popups_are_quiet() {
        let lib = Library::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/civ6")).unwrap();
        assert_eq!(lib.guarded_quiet("Harness.run(Harness.autoplay, 3)"),
                   format!("if Harness and Harness.version == \"{}\" then if Harness.popups_quiet then Harness.run(Harness.autoplay, 3) \
                            else print(\"HARNESS_POPUPS_LOUD\") end else print(\"HARNESS_MISSING\") end", lib.version));
    }

    #[test]
    fn the_popups_table_is_required() {
        let dir = std::env::temp_dir().join(format!("civ6-nopopups-{}", std::process::id()));
        std::fs::create_dir_all(dir.join("lua")).unwrap();
        std::fs::write(dir.join("lua/harness.lua"), "-- test").unwrap();
        let err = Library::load(&dir).err().expect("a corpus without popups.toml is refused").to_string();
        assert!(err.contains("popups.toml"), "{err}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn a_popup_table_entry_must_be_plain_lua_names() {
        let ok = "[[quiet]]\nstate = \"WonderBuiltPopup\"\nevent = \"WonderCompleted\"\nhandler = \"OnWonderCompleted\"\n";
        assert_eq!(parse_popups(ok).unwrap().len(), 1);
        assert!(parse_popups("").unwrap().is_empty());
        for bad in ["OnX) os.exit(", "", "1abc", "a.b", "a b"] {
            let t = format!("[[quiet]]\nstate = \"S\"\nevent = \"E\"\nhandler = {}\n", toml::Value::String(bad.into()));
            assert!(parse_popups(&t).is_err(), "{bad:?} accepted");
        }
        assert!(parse_popups("[[quiet]]\nstate = \"S\"\nevent = \"E\"\n").is_err(), "a missing field is an error");
    }
}

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

// ---- last stand (docs/design/2026-09-27-civ6-levers-design.md, rulings 22-27) ------------------
// Controller subcommands only: they stay out of the model-facing `Order`. Cities and units are named
// by their numeric game ID (GameCore has no Locale to look names up).

/// A numeric game ID: digits only, so no other text reaches Lua through it.
pub fn numeric_id(what: &str, s: &str) -> Result<u64> {
    let t = s.trim();
    if t.is_empty() || t.len() > 12 || !t.bytes().all(|b| b.is_ascii_digit()) {
        bail!("{what} must be a numeric game ID (digits only), got {s:?}");
    }
    Ok(t.parse()?)
}

/// Read-only (GameCore): damage, moves and attacks of every unit within 3 tiles of our city.
pub fn ls_state_call(city: &str) -> Result<(&'static str, String)> {
    Ok((STATE_CORE, format!("Harness.run(Harness.ls_state, {})", numeric_id("city", city)?)))
}

/// End the moves of our unit this turn (GameCore), so the hand-back's AI cannot move it.
pub fn finish_moves_call(unit: &str) -> Result<(&'static str, String)> {
    Ok((STATE_CORE, format!("Harness.run(Harness.finish_moves, {})", numeric_id("unit", unit)?)))
}

/// Read-only (InGame): our turn, the engine idle, nothing modal on screen.
pub const TURN_READY_CALL: (&str, &str) = (STATE_UI, "Harness.run(Harness.turn_ready)");

const MAX_STAND_ENTRIES: usize = 256;

/// One last-stand action for our city (InGame). `damage` is ls-state's authoritative damage as
/// JSON `{"<owner>:<unit id>": 0..=1000}`; `skip` lists the actors already used this turn,
/// comma-separated `city:<id>` / `unit:<id>`.
pub fn last_stand_step_call(city: &str, damage: &str, skip: &str) -> Result<(&'static str, String)> {
    let city = numeric_id("city", city)?;
    let raw = if damage.trim().is_empty() { "{}" } else { damage };
    let map: serde_json::Map<String, serde_json::Value> =
        serde_json::from_str(raw).context("--damage must be a JSON object {\"<owner>:<unit id>\": damage}")?;
    if map.len() > MAX_STAND_ENTRIES {
        bail!("--damage: at most {MAX_STAND_ENTRIES} units");
    }
    let mut dmg = Vec::new();
    for (k, v) in &map {
        let Some((owner, id)) = k.split_once(':') else { bail!("--damage key {k:?} must be <owner>:<unit id>") };
        let (owner, id) = (numeric_id("owner", owner)?, numeric_id("unit", id)?);
        let Some(d) = v.as_u64().filter(|d| *d <= 1000) else { bail!("--damage {k:?}: damage must be a whole number 0..1000") };
        dmg.push(format!("[{}] = {d}", lua_str(&format!("{owner}:{id}"))));
    }
    let mut used = Vec::new();
    for e in skip.split(',').map(str::trim).filter(|e| !e.is_empty()) {
        let Some((kind, id)) = e.split_once(':').filter(|(k, _)| *k == "city" || *k == "unit") else {
            bail!("--skip entry {e:?} must be city:<id> or unit:<id>")
        };
        used.push(format!("[{}] = true", lua_str(&format!("{kind}:{}", numeric_id(kind, id)?))));
    }
    if used.len() > MAX_STAND_ENTRIES {
        bail!("--skip: at most {MAX_STAND_ENTRIES} actors");
    }
    Ok((STATE_UI, format!("Harness.run(Harness.last_stand_step, {city}, {{{}}}, {{{}}})", dmg.join(", "), used.join(", "))))
}

// ---- district placement, read-only (docs/design/2026-09-27-civ6-levers-design.md, ruling 30) ----

/// Read-only (InGame): per city (all, or the one given by numeric ID) the districts placed, where
/// each district it could place may go, and the facts of the plots around it.
pub fn district_plots_call(city: Option<&str>) -> Result<(&'static str, String)> {
    let arg = match city {
        Some(c) => numeric_id("city", c)?.to_string(),
        None => "nil".into(),
    };
    Ok((STATE_UI, format!("Harness.run(Harness.district_plots, {arg})")))
}

// ---- the AI's intent (docs/design/2026-09-27-civ6-levers-design.md, ruling 29) -----------------

/// The game's log of AI strategies: "Game Turn, Player, Strategy, Status" rows, appended whenever a
/// player's strategy starts ("Following") or stops ("Stopped"), under the agent's `civ6_appdata`
/// root (`%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VI`).
pub const AI_LOG_ROOT: &str = "civ6_appdata";
pub const AI_LOG_PATH: &str = "Logs/AI_Victories.csv";
/// At most this much of the log per read (the whole log was about 10 KB at T77).
pub const AI_LOG_MAX: u64 = 64 * 1024;

/// The reply of `civ6 ai-strategies`: one player's complete rows in `chunk`, read at `offset` of a
/// file of `size` bytes, and the offset to read from next (a partial last line waits for it). A file
/// smaller than `offset` was started again (a new game session): no rows, read again from 0.
pub fn ai_strategies_reply(chunk: &[u8], offset: u64, size: u64, player: u32) -> serde_json::Value {
    if offset > size {
        return serde_json::json!({"ok": true, "size": size, "offset": offset, "next": 0, "restarted": true, "rows": []});
    }
    let end = chunk.iter().rposition(|&b| b == b'\n').map_or(0, |i| i + 1);
    let mut rows = Vec::new();
    for line in String::from_utf8_lossy(&chunk[..end]).lines() {
        let f: Vec<&str> = line.split(',').map(str::trim).collect();
        if f.len() != 4 {
            continue;
        }
        let (Ok(turn), Ok(who)) = (f[0].parse::<u32>(), f[1].parse::<u32>()) else { continue };     // the header
        if who == player {
            rows.push(serde_json::json!([turn, f[2], f[3]]));
        }
    }
    serde_json::json!({"ok": true, "size": size, "offset": offset, "next": offset + end as u64, "restarted": false, "rows": rows})
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
    /// A field of the library in `InGame` (`Harness.<requires>`) that must be set before the handler
    /// is removed: the library's own handler that takes the popup's place (the leader screen's
    /// statements). Without it the popup's handler is put back, so the popup still shows.
    #[serde(default)]
    pub requires: Option<String>,
}

impl QuietPopup {
    /// Run in `InGame`: prints QUIET_READY when `Harness.<requires>` is set (None: nothing to check).
    pub fn ready_code(&self) -> Option<String> {
        self.requires.as_ref().map(|r| {
            format!("if Harness and Harness.{r} then print(\"QUIET_READY\") else print(\"QUIET_NOT_READY\") end")
        })
    }

    /// Puts the handler back (removed first, so it is never there twice); prints QUIET_HELD,
    /// QUIET_ABSENT or QUIET_ERR with the reason.
    pub fn restore_code(&self) -> String {
        let (e, h) = (&self.event, &self.handler);
        format!("if Events and Events.{e} and {h} then local ok, err = pcall(function() Events.{e}.Remove({h}) \
                 Events.{e}.Add({h}) end) print(ok and \"QUIET_HELD\" or (\"QUIET_ERR \" .. tostring(err))) \
                 else print(\"QUIET_ABSENT\") end")
    }

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
        for (field, v) in [("state", &p.state), ("event", &p.event), ("handler", &p.handler)]
            .into_iter().chain(p.requires.as_ref().map(|r| ("requires", r))) {
            if !lua_name(v) {
                bail!("popups: {field} {v:?} is not a Lua name");
            }
        }
    }
    Ok(f.quiet)
}

/// What the install chunk puts before the library (`{version}` and `{state}` become Lua strings).
/// The version hashes it with the file, so a chunk of another form (a controller built before
/// HARNESS_STATE sent none, and its install registered no diplomacy handler) is installed again.
pub const INSTALL_HEADER: &str = "local HARNESS_VERSION = {version}\nlocal HARNESS_STATE = {state}\n";

/// The library file and its version (FNV-1a of the install header's template and the text: any edit
/// of either re-installs it), with the popups to quiet after installing it into `InGame`. `body` is
/// the text as sent: every full-line comment blanked (the agent takes at most 64 KiB of code, and the
/// file's comments are a fifth of it), so line numbers in the game's errors still match the file.
pub struct Library {
    pub path: PathBuf,
    #[cfg_attr(not(test), allow(dead_code))] // the file as read (hashed into `version`; the tests check its guards)
    pub source: String,
    pub body: String,
    pub version: String,
    pub popups: Vec<QuietPopup>,
}

/// `source` with each line that is only a comment made empty (its newline kept), except the license
/// and copyright notice, which every copy keeps. The library has no block comments or long strings (a
/// test checks), so no line inside one can start with `--`.
pub fn blank_comment_lines(source: &str) -> String {
    let notice = |l: &str| l.contains("License") || l.contains("Copyright");
    source.split_inclusive('\n')
        .map(|l| if l.trim_start().starts_with("--") && !notice(l) { if l.ends_with('\n') { "\n" } else { "" } } else { l })
        .collect()
}

impl Library {
    pub fn load(corpus: &Path) -> Result<Self> {
        let path = corpus.join("lua").join("harness.lua");
        let source = std::fs::read_to_string(&path).with_context(|| format!("reading {}", path.display()))?;
        let mut h: u64 = 0xcbf29ce484222325;
        for b in INSTALL_HEADER.bytes().chain(source.bytes()) {
            h ^= b as u64;
            h = h.wrapping_mul(0x100000001b3);
        }
        let table = corpus.join("popups.toml");
        let text = std::fs::read_to_string(&table).with_context(|| format!("reading {}", table.display()))?;
        let popups = parse_popups(&text).with_context(|| format!("in {}", table.display()))?;
        let body = blank_comment_lines(&source);
        Ok(Self { path, source, body, version: format!("{h:016x}"), popups })
    }

    /// The chunk that installs the library into `state` (a no-op when this version is already
    /// there). The library learns its state from it: the diplomacy handler is registered in InGame only.
    pub fn install_code(&self, state: &str) -> String {
        INSTALL_HEADER.replace("{version}", &lua_str(&self.version)).replace("{state}", &lua_str(state)) + &self.body
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
        let installed = printed(&client.tuner_lua(state, &lib.install_code(state), Some(15_000)).await?);
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
/// handler renamed by a patch shows up here, in the reply), no such state in this ruleset (a game
/// without Gathering Storm has no disaster popup), or kept because what replaces it is missing (the
/// library's field changes only with a reinstall, which clears `Harness.popups_quiet`).
pub fn quiet_settled(line: &str) -> bool {
    line.ends_with(" QUIET") || line.ends_with(" QUIET_ABSENT") || line.ends_with(" QUIET_HELD")
        || line.contains("no Lua state named")
}

/// Remove the handlers of the popups that would hold an autoplay turn, one tuner call each; one
/// `<state>.<handler> <outcome>` per popup, where the outcome is QUIET, QUIET_ABSENT, QUIET_HELD
/// (its `requires` field is not set in InGame, so the handler was put back), QUIET_ERR …, or
/// `failed: …` (a timeout or a missing state; a failed check sends nothing to the popup).
pub async fn quiet_popups(client: &AgentClient, popups: &[QuietPopup]) -> Vec<String> {
    let mut out = Vec::with_capacity(popups.len());
    for p in popups {
        let ready = match p.ready_code() {
            None => Ok(true),
            Some(check) => client.tuner_lua(STATE_UI, &check, Some(5_000)).await
                .map(|r| printed(&r).iter().any(|l| l.trim() == "QUIET_READY"))
                .map_err(|e| format!("checking Harness.{}: {e}", p.requires.as_deref().unwrap_or(""))),
        };
        let outcome = match ready {
            Err(e) => format!("failed: {}", e.chars().take(200).collect::<String>()),
            Ok(ready) => {
                let code = if ready { p.code() } else { p.restore_code() };
                match client.tuner_lua(&p.state, &code, Some(5_000)).await {
                    Ok(r) => quiet_outcome(&printed(&r)),
                    Err(e) => format!("failed: {}", e.to_string().chars().take(200).collect::<String>()),
                }
            }
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
    fn last_stand_calls_take_numeric_ids_and_run_in_the_ruled_states() {
        assert_eq!(ls_state_call("65536").unwrap(), (STATE_CORE, "Harness.run(Harness.ls_state, 65536)".to_string()));
        assert_eq!(finish_moves_call(" 131073 ").unwrap(), (STATE_CORE, "Harness.run(Harness.finish_moves, 131073)".to_string()));
        assert_eq!(TURN_READY_CALL, (STATE_UI, "Harness.run(Harness.turn_ready)"));
        assert_eq!(last_stand_step_call("65536", "", "").unwrap(),
                   (STATE_UI, "Harness.run(Harness.last_stand_step, 65536, {}, {})".to_string()));
        let (state, call) = last_stand_step_call("65536", r#"{"63:5": 69, "4:131072": 0}"#, "city:65536, unit:7").unwrap();
        assert_eq!(state, STATE_UI);
        assert_eq!(call, r#"Harness.run(Harness.last_stand_step, 65536, {["4:131072"] = 0, ["63:5"] = 69}, {["city:65536"] = true, ["unit:7"] = true})"#);
    }

    #[test]
    fn last_stand_calls_refuse_anything_but_numbers_where_an_id_is_required() {
        let hostile = "65536) Players[0]:GetTreasury():SetGoldBalance(99999) --";
        for bad in ["Beijing", "", "-1", "1e5", "0x10", hostile, "12345678901234"] {
            assert!(ls_state_call(bad).unwrap_err().to_string().contains("numeric game ID"), "{bad:?}");
            assert!(finish_moves_call(bad).is_err(), "{bad:?}");
            assert!(last_stand_step_call(bad, "{}", "").is_err(), "{bad:?}");
        }
        let err = |d: &str, s: &str| last_stand_step_call("65536", d, s).unwrap_err().to_string();
        assert!(err(r#"{"63:5": "x\"); os.exit() --"}"#, "").contains("whole number"));
        assert!(err(r#"{"63:5": 1001}"#, "").contains("whole number"));
        assert!(err(r#"{"63:5": -1}"#, "").contains("whole number"));
        assert!(err(r#"{"x\"]=1}--:5": 1}"#, "").contains("numeric game ID"));
        assert!(err(r#"{"635": 1}"#, "").contains("<owner>:<unit id>"));
        assert!(err("[1, 2]", "").contains("JSON object"));
        assert!(err("{}", "tile:5").contains("city:<id> or unit:<id>"));
        assert!(err("{}", r#"unit:5"] = true}) os.exit() --"#).contains("numeric game ID"));
    }

    #[test]
    fn district_plots_is_read_only_in_game_with_an_optional_numeric_city() {
        assert_eq!(district_plots_call(None).unwrap(), (STATE_UI, "Harness.run(Harness.district_plots, nil)".to_string()));
        assert_eq!(district_plots_call(Some("65536")).unwrap().1, "Harness.run(Harness.district_plots, 65536)");
        assert!(district_plots_call(Some("Beijing")).is_err());
        assert!(district_plots_call(Some("1) os.exit() --")).is_err());
    }

    #[test]
    fn ai_strategies_keep_one_players_complete_rows() {
        let log = b"Game Turn, Player, Strategy, Status\n1, 0, STRATEGY_EARLY_EXPLORATION, Following\n\
                    1, 1, STRATEGY_EARLY_EXPLORATION, Following\n56, 0, VICTORY_STRATEGY_SCIENCE_VICTORY, Following\n76, 0, VICT";
        let r = ai_strategies_reply(log, 0, 500, 0);
        assert_eq!(r["rows"], serde_json::json!([[1, "STRATEGY_EARLY_EXPLORATION", "Following"],
                                                 [56, "VICTORY_STRATEGY_SCIENCE_VICTORY", "Following"]]));
        let partial = log.len() - "76, 0, VICT".len();
        assert_eq!(r["next"], partial as u64, "a partial last line waits for the next read");
        let more = b"76, 0, VICTORY_STRATEGY_SCIENCE_VICTORY, Stopped\n";
        let r = ai_strategies_reply(more, partial as u64, 500, 0);
        assert_eq!(r["rows"], serde_json::json!([[76, "VICTORY_STRATEGY_SCIENCE_VICTORY", "Stopped"]]));
        assert_eq!(r["next"], (partial + more.len()) as u64);
        assert_eq!(ai_strategies_reply(log, 0, 500, 1)["rows"].as_array().unwrap().len(), 1, "player 1");
        let restarted = ai_strategies_reply(b"", 900, 120, 0);
        assert_eq!((restarted["restarted"].as_bool(), restarted["next"].as_u64()), (Some(true), Some(0)));
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
        // the chunk names its Lua state: the diplomacy handler is registered in InGame only
        assert!(lib.install_code(STATE_UI).starts_with(&format!("local HARNESS_VERSION = \"{}\"\nlocal HARNESS_STATE = \"InGame\"\n", lib.version)));
        assert!(lib.install_code(STATE_CORE).contains("\nlocal HARNESS_STATE = \"GameCore\"\n"));
        assert!(lib.source.contains("if HARNESS_STATE == 'InGame' then"), "the handler is installed in InGame only");
        assert!(lib.source.contains("if Harness and Harness.version == HARNESS_VERSION then"), "idempotent install guard");
        let g = lib.guarded("Harness.run(Harness.snapshot)");
        assert!(g.starts_with(&format!("if Harness and Harness.version == \"{}\" then Harness.run(Harness.snapshot) else print(\"HARNESS_MISSING\") end", lib.version)));
        assert!(lib.source.contains("MIT License"), "civ6-mcp attribution");
        // the agent refuses tuner code over 64 KiB (crates/game-agent/src/tuner.rs MAX_CODE)
        assert!(lib.install_code(STATE_UI).len() < 64 * 1024, "the install chunk is {} bytes", lib.install_code(STATE_UI).len());
        // comment lines are blanked in what is sent, never code: no block comment or long string
        assert!(!lib.source.contains("[[") && !lib.source.contains("--[") && !lib.source.contains("\\\n"),
                "a block comment or long string would let a blanked line cut it");
        assert_eq!(lib.body.lines().count(), lib.source.lines().count(), "line numbers match the file");
        assert!(lib.body.contains("MIT License") && lib.body.contains("Copyright (c) 2026 Liam Wilkinson"),
                "the civ6-mcp notice is kept in what is sent");
        assert!(lib.body.contains("function H.snapshot()") && !lib.body.contains("-- ---- JSON"));
    }

    #[test]
    fn only_whole_comment_lines_are_blanked() {
        let src = "-- head\nlocal a = 1 -- tail\n  -- indented\n-- MIT License\nprint('--x')\n--";
        assert_eq!(blank_comment_lines(src), "\nlocal a = 1 -- tail\n\n-- MIT License\nprint('--x')\n");
    }

    #[test]
    fn the_version_covers_the_install_header() {
        // A controller built before HARNESS_STATE sent the same file without it (no diplomacy handler)
        // under the version of the text alone; the rebuilt controller must find that install MISSING.
        fn fnv(b: &[u8]) -> String {
            format!("{:016x}", b.iter().fold(0xcbf29ce484222325u64, |h, &c| (h ^ c as u64).wrapping_mul(0x100000001b3)))
        }
        let lib = Library::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/civ6")).unwrap();
        assert_ne!(lib.version, fnv(lib.source.as_bytes()), "an install by the older controller would be kept");
        let chunk = lib.install_code(STATE_UI);
        let header = &chunk[..chunk.len() - lib.body.len()];
        assert_eq!(header.replace(&lib.version, "").replace(STATE_UI, ""), "local HARNESS_VERSION = \"\"\nlocal HARNESS_STATE = \"\"\n");
        // the header's template is hashed with the text, so changing either installs the library again
        assert_eq!(lib.version, fnv(format!("{INSTALL_HEADER}{}", lib.source).as_bytes()));
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
                     "NaturalDisasterPopup.RandomEventOccurred.OnRandomEventOccurred", "RockBandMoviePopup.PostTourismBomb.OnRockBandConcert",
                     // an AI leader's statement: the view locks the engine until a human answers (T240, T342)
                     "DiplomacyActionView.DiplomacyStatement.OnDiplomacyStatement"] {
            assert!(names.iter().any(|n| n == want), "{want} missing from popups.toml");
        }
    }

    #[test]
    fn quieting_a_popup_removes_its_handler_and_says_what_happened() {
        let p = QuietPopup { state: "WonderBuiltPopup".into(), event: "WonderCompleted".into(), handler: "OnWonderCompleted".into(),
                             requires: None };
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
        assert_eq!(parse_popups(ok).unwrap()[0].requires, None);
        let req = format!("{ok}requires = \"dipl_handler\"\n");
        assert_eq!(parse_popups(&req).unwrap()[0].requires.as_deref(), Some("dipl_handler"));
        for bad in ["a.b", "x) os.exit(", ""] {
            let t = format!("{ok}requires = {}\n", toml::Value::String(bad.into()));
            assert!(parse_popups(&t).is_err(), "requires {bad:?} accepted");
        }
    }

    #[test]
    fn the_leader_screen_is_quieted_only_while_the_library_handler_is_in_place() {
        // Without the library's own handler nobody answers an AI statement: the screen keeps its
        // handler then (the statement holds the turn for a human instead of vanishing).
        let lib = Library::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/civ6")).unwrap();
        let view = lib.popups.iter().find(|p| p.state == "DiplomacyActionView").expect("the leader screen entry");
        assert_eq!(view.requires.as_deref(), Some("dipl_handler"));
        assert!(lib.source.contains("H.dipl_handler = on_statement"), "the field the controller checks");
        assert!(lib.popups.iter().filter(|p| p.state != "DiplomacyActionView").all(|p| p.requires.is_none()));
    }

    #[test]
    fn a_held_popup_gets_its_handler_back() {
        let p = QuietPopup { state: "DiplomacyActionView".into(), event: "DiplomacyStatement".into(),
                             handler: "OnDiplomacyStatement".into(), requires: Some("dipl_handler".into()) };
        assert_eq!(p.ready_code().unwrap(),
                   "if Harness and Harness.dipl_handler then print(\"QUIET_READY\") else print(\"QUIET_NOT_READY\") end");
        assert_eq!(p.restore_code(), concat!(
            "if Events and Events.DiplomacyStatement and OnDiplomacyStatement then ",
            "local ok, err = pcall(function() Events.DiplomacyStatement.Remove(OnDiplomacyStatement) ",
            "Events.DiplomacyStatement.Add(OnDiplomacyStatement) end) ",
            "print(ok and \"QUIET_HELD\" or (\"QUIET_ERR \" .. tostring(err))) else print(\"QUIET_ABSENT\") end"));
        assert!(quiet_settled("DiplomacyActionView.OnDiplomacyStatement QUIET_HELD"));
        assert!(QuietPopup { requires: None, ..p }.ready_code().is_none());
    }

    #[tokio::test]
    async fn quieting_checks_the_library_handler_before_the_leader_screen() {
        let lib = Library::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/civ6")).unwrap();
        for ready in [true, false] {
            let (url, sent) = fake_tuner(move |_, code| Ok(vec![
                if code.contains("QUIET_READY") { if ready { "QUIET_READY" } else { "QUIET_NOT_READY" } }
                else if code.contains(".Add(") { "QUIET_HELD" } else { "QUIET" }.to_string()])).await;
            let client = AgentClient::new(Some(&url), Some("t")).unwrap();
            let out = quiet_popups(&client, &lib.popups).await;
            let sent = sent.lock().unwrap().clone();
            let checks: Vec<usize> = (0..sent.len()).filter(|&i| sent[i].1.contains("QUIET_READY")).collect();
            assert_eq!(checks.len(), 1, "one check, for the one entry that requires it");
            assert_eq!(sent[checks[0]].0, STATE_UI, "the library lives in InGame");
            assert_eq!(sent[checks[0] + 1].0, "DiplomacyActionView", "checked right before the screen's call");
            let view = &sent[checks[0] + 1].1;
            assert_eq!(view.contains("Events.DiplomacyStatement.Add(OnDiplomacyStatement)"), !ready, "ready {ready}: {view}");
            assert_eq!(view.contains("QUIET_HELD"), !ready);
            let line = out.iter().find(|l| l.starts_with("DiplomacyActionView.")).unwrap();
            assert_eq!(line, if ready { "DiplomacyActionView.OnDiplomacyStatement QUIET" }
                             else { "DiplomacyActionView.OnDiplomacyStatement QUIET_HELD" });
            assert!(out.iter().all(|l| quiet_settled(l)), "{out:?}");
            assert_eq!(sent.iter().filter(|(_, c)| c.contains(".Add(")).count(), usize::from(!ready), "no other popup is restored");
        }
        // a check that gets no answer quiets nothing and restores nothing: retried on the next call
        let (url, sent) = fake_tuner(|_, code| if code.contains("QUIET_READY") { Err("timed out".into()) }
                                              else { Ok(vec!["QUIET".into()]) }).await;
        let client = AgentClient::new(Some(&url), Some("t")).unwrap();
        let out = quiet_popups(&client, &lib.popups).await;
        assert!(sent.lock().unwrap().iter().all(|(s, _)| s != "DiplomacyActionView"));
        let line = out.iter().find(|l| l.starts_with("DiplomacyActionView.")).unwrap();
        assert!(line.contains("failed: checking Harness.dipl_handler") && !quiet_settled(line), "{line}");
    }

    /// Tuner calls a fake agent received: (state, code).
    type Sent = std::sync::Arc<std::sync::Mutex<Vec<(String, String)>>>;

    /// A fake agent whose `/tuner/lua` answers with `reply(state, code)`: the printed lines, or an
    /// HTTP 400 with the error. Records every call it gets.
    async fn fake_tuner<F>(reply: F) -> (String, Sent)
    where F: Fn(&str, &str) -> Result<Vec<String>, String> + Send + Sync + 'static {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let sent: Sent = Default::default();
        let log = sent.clone();
        tokio::spawn(async move {
            loop {
                let (mut sock, _) = listener.accept().await.unwrap();
                let mut req = Vec::new();
                let mut buf = vec![0u8; 65536];
                let body = loop {
                    let n = sock.read(&mut buf).await.unwrap();
                    req.extend_from_slice(&buf[..n]);
                    let text = String::from_utf8_lossy(&req).to_string();
                    if let Some((head, body)) = text.split_once("\r\n\r\n") {
                        let len = head.lines().find_map(|l| l.to_ascii_lowercase().strip_prefix("content-length:")
                            .map(|v| v.trim().parse::<usize>().unwrap())).unwrap_or(0);
                        if body.len() >= len || n == 0 {
                            break body.to_string();
                        }
                    }
                };
                let v = serde_json::from_str::<serde_json::Value>(&body).unwrap();
                let (state, code) = (v["state"].as_str().unwrap_or("").to_string(), v["code"].as_str().unwrap().to_string());
                log.lock().unwrap().push((state.clone(), code.clone()));
                let (status, reply) = match reply(&state, &code) {
                    Ok(out) => ("200 OK", serde_json::json!({"ok": true, "state": state, "result": "", "extra": [], "output": out})),
                    Err(e) => ("400 Bad Request", serde_json::json!({"error": e})),
                };
                let reply = reply.to_string();
                let head = format!("HTTP/1.1 {status}\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n",
                                   reply.len());
                sock.write_all(head.as_bytes()).await.unwrap();
                sock.write_all(reply.as_bytes()).await.unwrap();
            }
        });
        (url, sent)
    }

    /// A tuner agent with the guards' semantics: the library is installed or not, the popups quiet
    /// or not, and a guarded chunk runs its call only when both hold (or when the chunk sets
    /// `Harness.popups_quiet` itself). Counts the chunks that ran a call containing `marker`.
    async fn guarded_tuner(installed: bool, quiet: bool, marker: &'static str)
        -> (String, std::sync::Arc<std::sync::atomic::AtomicUsize>) {
        use std::sync::atomic::{AtomicUsize, Ordering};
        let runs = std::sync::Arc::new(AtomicUsize::new(0));
        let counter = runs.clone();
        let state = std::sync::Mutex::new((installed, quiet));
        let (url, _) = fake_tuner(move |_, code| {
            let mut st = state.lock().unwrap();
            let (installed, quiet) = &mut *st;
            Ok(if code.starts_with("local HARNESS_VERSION") {
                *installed = true;
                vec!["installed".into()]
            } else if code.contains("QUIET_READY") {
                vec![if *installed { "QUIET_READY" } else { "QUIET_NOT_READY" }.into()]
            } else if code.starts_with("if Events and Events.") {
                vec!["QUIET".into()]
            } else if !*installed {
                vec![MISSING.into()]
            } else if code.contains("if Harness.popups_quiet then") && !*quiet {
                vec![LOUD.into()]
            } else {
                *quiet = *quiet || code.contains("Harness.popups_quiet = true");
                if code.contains(marker) {
                    counter.fetch_add(1, Ordering::SeqCst);
                }
                vec![r#"{"ok":true,"action":"ranged_attack"}"#.into()]
            })
        }).await;
        (url, runs)
    }

    #[tokio::test]
    async fn a_state_changing_ingame_call_runs_once_through_the_popup_guard() {
        // The last stand's step changes the game: after a load (library missing) or while the popups
        // are loud, the first attempt must run nothing, and the call runs exactly once afterwards.
        let lib = Library::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/civ6")).unwrap();
        let (_, call) = last_stand_step_call("65536", "", "").unwrap();
        for (installed, quiet) in [(false, false), (true, false), (true, true)] {
            let (url, runs) = guarded_tuner(installed, quiet, "Harness.last_stand_step").await;
            let client = AgentClient::new(Some(&url), Some("t")).unwrap();
            let v = call_with(&client, &lib, STATE_UI, &call, 1_000).await.unwrap();
            assert_eq!(v["action"], "ranged_attack");
            assert_eq!(runs.load(std::sync::atomic::Ordering::SeqCst), 1, "installed {installed}, quiet {quiet}");
        }
    }
}

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
    let (path, _) = latest_save_path(client).await?;
    let (bytes, _) = client.files_read(DOCS_ROOT, &path, 0, None).await?;
    Ok((path, bytes))
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
            apply += &format!(" set_policy = {{ policy = {policy} option = {option} cooldown = no }}");
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
    if !fg.contains(WINDOW_TITLE) {
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
}

impl PauseDetector {
    pub fn from_manifest(m: &crate::corpus::GameManifest) -> Result<PauseDetector> {
        let def = m.screens.get("paused").context("manifest has no [screens.paused]")?;
        let rel = def.template.as_ref().context("[screens.paused] has no template")?;
        let path = m.base_dir.clone().unwrap_or_default().join(rel);
        let template = image::open(&path).with_context(|| format!("loading {}", path.display()))?.to_rgb8();
        let roi = def.template_roi.context("[screens.paused] has no template_roi")?;
        let color = def.color_range.map(|r| (r, def.color_min_fraction.unwrap_or(0.05)));
        Ok(PauseDetector { template, roi, threshold: def.template_threshold, search: def.template_search, color })
    }

    pub fn frame_is_paused(&self, frame: &image::RgbImage) -> bool {
        let r = crate::imaging::roi_from_norm(frame.width(), frame.height(), self.roi);
        if let Some((range, min)) = self.color {
            return crate::imaging::color_fraction(frame, r, range) >= min;
        }
        crate::imaging::template_diff_search(frame, &self.template, r[0], r[1], self.search) <= self.threshold
    }

    pub async fn is_paused(&self, client: &crate::client::AgentClient) -> Result<bool> {
        let jpeg = client.screenshot(None, None, None, None, Some(crate::imaging::MAX_SIDE as i32), Some(75)).await?;
        Ok(self.frame_is_paused(&crate::imaging::decode_rgb(&jpeg)?))
    }

    /// Pause or resume, checking the screen before and after (Space toggles, so a blind press
    /// can invert the state). If Space has no effect, a text box or panel probably has keyboard
    /// focus (seen: "Search known star systems"); one Esc closes it before a last try.
    /// Returns whether a key was pressed.
    pub async fn set_paused(&self, client: &crate::client::AgentClient, paused: bool) -> Result<bool> {
        if self.is_paused(client).await? == paused {
            return Ok(false);
        }
        for attempt in 0..3 {
            if attempt == 2 {
                require_foreground(client).await?;
                client.key("esc", 1).await?;
                tokio::time::sleep(std::time::Duration::from_millis(400)).await;
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
        let r = crate::imaging::roi_from_norm(frame.width(), frame.height(), self.roi);
        let d_on = crate::imaging::template_diff_search(frame, &self.on, r[0], r[1], self.search);
        let d_off = crate::imaging::template_diff_search(frame, &self.off, r[0], r[1], self.search);
        let (best, other) = if d_on < d_off { (d_on, d_off) } else { (d_off, d_on) };
        // The console is semi-transparent over the map, so absolute distances drift with what is
        // behind it (live OFF frame: 0.039 vs ON 0.071); the gap between the two decides.
        (best < 0.08 && other - best > 0.015).then_some(d_on < d_off)
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
        let mut result = Err(anyhow!("could not read the console's reply to human_ai"));
        for _ in 0..2 {
            match self.toggle_and_read(client).await? {
                Some(state) if state == on => {
                    result = Ok(());
                    break;
                }
                Some(_) => continue, // toggled the wrong way: toggle again
                None => break,
            }
        }
        require_foreground(client).await?;
        client.key(CONSOLE_KEY, 1).await?;
        result
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
    run_console(client, &[format!("effect {}", scoped_log(&probe))]).await?;
    if !wait_for_log(client, before, &probe).await? {
        run_console(client, &[format!("play {country}")]).await?;
        done.push(format!("left observer mode (play {country})"));
    }
    reader.set(client, true).await?;
    done.push("human_ai is ON: the game's AI plays the empire".into());
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
    run_console(client, &lines).await?;
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
    if let Some(ps) = planets.as_ref() {
        let mut systems = std::collections::BTreeSet::new();
        for pid in strings(get(&c, "controlled_planets")) {
            if let Some(origin) = obj(ps, &pid).and_then(|p| obj(&p, "coordinate")).and_then(|co| i64_(&co, "origin")) {
                systems.insert(origin);
            }
        }
        b.systems = systems.len();
    }
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
            "Power: military {:.0}, economy {:.0}, tech {:.0}; victory rank {}. Systems owned {}, empire size {}, pops {}, fleet size {}, upgraded starbases {}/{}\n",
            self.military_power, self.economy_power, self.tech_power, self.victory_rank,
            self.systems, self.empire_size, self.pops, self.fleet_size, self.starbases.0, self.starbases.1
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
        assert_eq!(b.systems, 1, "only Sol in 2200.11");
        assert_eq!(b.last_human, "2200.09.24");
        assert!(b.wars.is_empty());
        assert!(b.edicts.is_empty());
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
        assert!(apply.contains("set_policy = { policy = diplomatic_stance option = diplo_stance_expansionist cooldown = no }"));
        assert!(apply.ends_with("if = { limit = { exists = capital_scope } log = \"GOVERNOR_APPLIED expand k3x9\" }"));
        assert!(lines.iter().all(|l| l.len() < 1000), "agent /type limit");
        assert!(d.console_lines("nuke_everyone", "x").is_err());
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
        assert_eq!(r.read_frame(&image::RgbImage::new(1568, 882)), None, "no console: unknown");
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
}

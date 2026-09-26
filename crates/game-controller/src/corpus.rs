//! Game corpus: hand-verified manifest, generated entity records, and chunked prose.
//!
//! Layout of `corpora/<game>/`:
//!
//! - `manifest.toml` — hotkeys, screen signatures and macros, hand-verified (`game.toml` still accepted)
//! - `strategy.md` — playbook written for the model; also chunked for search
//! - `data/<kind>.json` — generated records (see `data/README.md`), never edited by hand
//! - `docs/*.md` — prose reference with `Source:`/`License:` headers, chunked for search
//!
//! Everything is loaded into memory once. Lookups are by normalized name with alias and
//! trigram-fuzzy fallback; search returns ids plus one-line summaries so the caller fetches
//! only the records it needs with `get`.

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::{Path, PathBuf};

/// Subdirectory holding knowledge learned during play (overlay manifest, templates, notes).
pub const LEARNED_DIR: &str = "learned";

#[derive(Debug, Default, Deserialize)]
struct LearnedOverlay {
    #[serde(default)]
    screens: HashMap<String, ScreenDef>,
    #[serde(default)]
    hotkeys: HashMap<String, String>,
}

/// Manifest file names, in the order they are tried.
pub const MANIFEST_FILES: [&str; 2] = ["manifest.toml", "game.toml"];
/// Upper bound on a prose chunk; a single longer paragraph becomes its own chunk.
pub const MAX_CHUNK_CHARS: usize = 1500;
/// Minimum trigram similarity for a fuzzy name match.
pub const FUZZY_THRESHOLD: f64 = 0.6;
pub const MAX_SEARCH_LIMIT: usize = 50;

// ---------------------------------------------------------------------------
// Manifest (machine-executed: hotkeys, screens, macros)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameManifest {
    /// Directory the manifest was loaded from; screen templates resolve relative to it.
    #[serde(skip)]
    pub base_dir: Option<PathBuf>,
    pub metadata: GameMetadata,
    pub hotkeys: HashMap<String, String>,
    #[serde(default)]
    pub screens: HashMap<String, ScreenDef>,
    #[serde(default)]
    pub macros: HashMap<String, MacroDef>,
    /// Free-form `[ui.*]` tables (e.g. `[ui.tech]`, `[ui.market]`): calibrated screen positions
    /// for game-specific interaction sequences that live in Rust, not the manifest's declarative
    /// screens/macros. Read with `ui_point` (see `stellaris.rs`).
    #[serde(default)]
    pub ui: toml::Table,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameMetadata {
    pub id: String,
    pub name: String,
    pub version: String,
    pub process_title: String,
    pub native_resolution: [u32; 2],
    pub downscaled_resolution: [u32; 2],
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScreenDef {
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub luminance_roi: Option<[u32; 4]>,
    #[serde(default)]
    pub luminance_threshold: Option<f64>,
    #[serde(default)]
    pub is_blocking: bool,
    #[serde(default)]
    pub title_ocr: Option<String>,
    #[serde(default)]
    pub choice_keys: Vec<String>,
    #[serde(default)]
    pub buttons: HashMap<String, ButtonDef>,
    #[serde(default)]
    pub dismiss_key: Option<String>,
    /// Normalized [x, y, w, h] of a HUD element that changes every turn (the date readout);
    /// the autopilot diffs it before/after "end turn" to verify a turn actually advanced.
    #[serde(default)]
    pub turn_indicator_roi: Option<[f64; 4]>,
    /// Reference image (path relative to the corpus dir) that identifies this screen, compared
    /// against `template_roi` (normalized [x, y, w, h]) of the current frame.
    #[serde(default)]
    pub template: Option<String>,
    #[serde(default)]
    pub template_roi: Option<[f64; 4]>,
    /// Max mean difference (0..1) for a template match.
    #[serde(default = "default_template_threshold")]
    pub template_threshold: f64,
    /// Search ±this many pixels around `template_roi` (JPEG jitter; centered titles whose
    /// variable part changes glyph widths move by a pixel or two).
    #[serde(default = "default_template_search")]
    pub template_search: u32,
    /// Colour signature: the screen matches when at least `color_min_fraction` of the pixels in
    /// `template_roi` fall inside `color_range` ([[r,g,b] min, [r,g,b] max]). Robust to labels
    /// that pulse in brightness, where a pixel template fails.
    #[serde(default)]
    pub color_range: Option<[[u8; 3]; 2]>,
    #[serde(default)]
    pub color_min_fraction: Option<f64>,
    /// The autopilot may close this screen on its own (informational popups only).
    #[serde(default)]
    pub auto_dismiss: bool,
    /// Normalized [x, y] to click to dismiss; `dismiss_key` is used when absent.
    #[serde(default)]
    pub dismiss_click: Option<[f64; 2]>,
    /// Several normalized [x, y] clicks, performed in order (e.g. pick, Board, Done).
    /// Takes precedence over `dismiss_click` and `dismiss_key`.
    #[serde(default)]
    pub dismiss_clicks: Vec<[f64; 2]>,
    /// While this screen matches, the game is still processing the turn: keep waiting.
    #[serde(default)]
    pub busy: bool,
    /// Act on this screen only after end-turn was blocked (TAB then selected the idle unit).
    /// A unit that merely stays selected from earlier may already be busy, and re-issuing its
    /// order can cancel work in progress (e.g. "abandon the in-progress survey?").
    #[serde(default)]
    pub only_when_blocked: bool,
}

fn default_template_threshold() -> f64 {
    0.08
}

fn default_template_search() -> u32 {
    2
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ButtonDef {
    pub norm_x: f64,
    pub norm_y: f64,
    #[serde(default = "default_click_action")]
    pub action: String,
}

fn default_click_action() -> String {
    "click".to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MacroDef {
    #[serde(default)]
    pub description: String,
    pub actions: Vec<MacroAction>,
    #[serde(default = "default_settle_timeout")]
    pub settle_timeout: f64,
    #[serde(default = "default_settle_threshold")]
    pub settle_threshold: f64,
}

fn default_settle_timeout() -> f64 {
    10.0
}

fn default_settle_threshold() -> f64 {
    0.02
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum MacroAction {
    #[serde(rename = "key")]
    Key { key: String },
    #[serde(rename = "wait")]
    Wait { ms: u64 },
    #[serde(rename = "click_norm")]
    ClickNorm { x: f64, y: f64 },
}

impl GameManifest {
    pub fn load_from_file<P: AsRef<Path>>(path: P) -> Result<Self> {
        let content = std::fs::read_to_string(path.as_ref())
            .with_context(|| format!("Failed to read game corpus manifest at {:?}", path.as_ref()))?;
        let mut manifest: Self = toml::from_str(&content)
            .with_context(|| format!("Failed to parse game corpus TOML at {:?}", path.as_ref()))?;
        manifest.base_dir = path.as_ref().parent().map(Path::to_path_buf);
        if let Some(dir) = manifest.base_dir.clone() {
            manifest.merge_learned(&dir.join(LEARNED_DIR).join("manifest.toml"))?;
        }
        Ok(manifest)
    }

    /// Merge the learned overlay (written by the pilot app) into this manifest. Hand-verified
    /// entries win: an overlay screen or hotkey with the same name as a main one is ignored.
    /// Overlay template paths are relative to the corpus directory (e.g. `learned/templates/x.png`).
    fn merge_learned(&mut self, path: &Path) -> Result<()> {
        if !path.exists() {
            return Ok(());
        }
        let content = std::fs::read_to_string(path).with_context(|| format!("reading {:?}", path))?;
        let overlay: LearnedOverlay =
            toml::from_str(&content).with_context(|| format!("parsing learned overlay {:?}", path))?;
        for (name, screen) in overlay.screens {
            self.screens.entry(name).or_insert(screen);
        }
        for (name, key) in overlay.hotkeys {
            self.hotkeys.entry(name).or_insert(key);
        }
        Ok(())
    }

    /// The manifest file inside a corpus directory, if any.
    pub fn locate(dir: &Path) -> Option<PathBuf> {
        MANIFEST_FILES.iter().map(|f| dir.join(f)).find(|p| p.exists())
    }

    pub fn find_default() -> Option<Self> {
        default_corpus_dir().and_then(|d| Self::locate(&d)).and_then(|p| Self::load_from_file(p).ok())
    }

    /// Resolve a logical hotkey name (e.g. "next_action") to its actual key (e.g. "tab").
    pub fn resolve_key<'a>(&'a self, name: &'a str) -> &'a str {
        self.hotkeys.get(name).map(|s| s.as_str()).unwrap_or(name)
    }
}

fn default_corpus_dir() -> Option<PathBuf> {
    ["corpora/galciv4", "../corpora/galciv4", "../../corpora/galciv4"]
        .iter()
        .map(PathBuf::from)
        .find(|p| p.is_dir() && GameManifest::locate(p).is_some())
}

// ---------------------------------------------------------------------------
// Records (generated data) and chunks (prose)
// ---------------------------------------------------------------------------

/// One generated entity, e.g. a tech or an improvement. Field names are decided by the extractor.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Record {
    #[serde(default)]
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub aliases: Vec<String>,
    #[serde(default)]
    pub summary: String,
    #[serde(default)]
    pub fields: BTreeMap<String, serde_json::Value>,
    /// `normalize(name)` and normalized summary+fields, computed once at load for search.
    #[serde(skip)]
    norm_name: String,
    #[serde(skip)]
    norm_body: String,
}

impl Record {
    fn index(&mut self) {
        self.norm_name = normalize(&self.name);
        let body = format!("{} {}", self.summary, self.fields.values().map(render_value).collect::<Vec<_>>().join(" "));
        self.norm_body = normalize(&body);
    }

    pub fn kind(&self) -> &str {
        self.id.split(':').next().unwrap_or("")
    }

    /// Compact markdown: one heading line, then one line per field.
    pub fn render(&self) -> String {
        let mut out = format!("**{}** ({}) — `{}`", self.name, self.kind(), self.id);
        if !self.summary.is_empty() {
            out.push('\n');
            out.push_str(&self.summary);
        }
        for (k, v) in &self.fields {
            out.push_str(&format!("\n- {}: {}", k, render_value(v)));
        }
        out
    }
}

fn render_value(v: &serde_json::Value) -> String {
    match v {
        serde_json::Value::String(s) => s.clone(),
        serde_json::Value::Array(items) => items.iter().map(render_value).collect::<Vec<_>>().join(", "),
        other => other.to_string(),
    }
}

/// A slice of prose from `docs/` or `strategy.md`, small enough to return whole.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Chunk {
    pub id: String,
    pub doc: String,
    pub title: String,
    pub text: String,
    /// `normalize(text)`, computed once at load so search does not re-normalize per query.
    #[serde(skip)]
    norm: String,
}

impl Chunk {
    fn new(id: String, doc: String, title: String, text: String) -> Self {
        let norm = normalize(&text);
        Self { id, doc, title, text, norm }
    }

    /// Up to ~120 chars of the chunk centred on the first occurrence of `phrase` (or of its
    /// first word), so a search hit shows the matching context rather than the chunk's first line.
    pub fn snippet(&self, phrase: &str) -> String {
        let lower = self.text.to_lowercase();
        let needles = [phrase.trim().to_lowercase(), phrase.split_whitespace().next().unwrap_or("").to_lowercase()];
        let pos = needles.iter().filter(|n| !n.is_empty()).find_map(|n| lower.find(n.as_str()));
        let text: Vec<char> = self.text.chars().collect();
        let start_char = match pos {
            Some(byte) => self.text[..byte].chars().count().saturating_sub(40),
            None => 0,
        };
        let window: String = text.iter().skip(start_char).take(120).collect();
        let window = window.split_whitespace().collect::<Vec<_>>().join(" ");
        let prefix = if start_char > 0 { "…" } else { "" };
        let suffix = if start_char + 120 < text.len() { "…" } else { "" };
        format!("{}{}{}", prefix, window, suffix)
    }

    pub fn render(&self) -> String {
        format!("**{}** — `{}`\n\n{}", self.title, self.id, self.text)
    }
}

#[derive(Debug, Clone)]
pub struct DocMeta {
    pub stem: String,
    pub title: String,
    pub source: Option<String>,
    pub chunks: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Hit {
    pub id: String,
    pub kind: String,
    pub title: String,
    pub summary: String,
    pub score: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct Stats {
    pub records: BTreeMap<String, usize>,
    pub docs: usize,
    pub chunks: usize,
    pub strategy_chars: usize,
}

pub enum Item<'a> {
    Record(&'a Record),
    Chunk(&'a Chunk),
}

impl Item<'_> {
    pub fn render(&self) -> String {
        match self {
            Item::Record(r) => r.render(),
            Item::Chunk(c) => c.render(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct GameCorpus {
    /// Directory the corpus was loaded from (game-specific files such as directives.toml).
    pub dir: std::path::PathBuf,
    pub manifest: GameManifest,
    pub strategy: String,
    records: Vec<Record>,
    by_id: HashMap<String, usize>,
    /// `"<kind>\0<normalized name or alias>"` → record index
    by_name: HashMap<String, usize>,
    chunks: Vec<Chunk>,
    chunk_by_id: HashMap<String, usize>,
    docs: Vec<DocMeta>,
}

impl GameCorpus {
    pub fn find_default() -> Option<Self> {
        default_corpus_dir().and_then(|d| Self::load_from_dir(d).ok())
    }

    pub fn load_from_dir<P: AsRef<Path>>(dir: P) -> Result<Self> {
        let dir = dir.as_ref();
        let manifest_path = GameManifest::locate(dir)
            .ok_or_else(|| anyhow::anyhow!("No {} in {:?}", MANIFEST_FILES.join(" or "), dir))?;
        let manifest = GameManifest::load_from_file(manifest_path)?;

        let strategy = std::fs::read_to_string(dir.join("strategy.md")).unwrap_or_default();

        let mut corpus = Self {
            dir: dir.to_path_buf(),
            manifest,
            strategy: strategy.clone(),
            records: Vec::new(),
            by_id: HashMap::new(),
            by_name: HashMap::new(),
            chunks: Vec::new(),
            chunk_by_id: HashMap::new(),
            docs: Vec::new(),
        };

        for path in sorted_files(&dir.join("data"), "json") {
            let stem = file_stem(&path);
            if stem.starts_with('_') {
                continue;
            }
            let raw = std::fs::read_to_string(&path).with_context(|| format!("reading {:?}", path))?;
            let records: Vec<Record> =
                serde_json::from_str(&raw).with_context(|| format!("parsing {:?} as a record array", path))?;
            for (i, r) in records.into_iter().enumerate() {
                corpus.add_record(&stem, r).with_context(|| format!("{:?} record #{}", path, i))?;
            }
        }

        if !strategy.is_empty() {
            corpus.add_doc("strategy", "strategy", &strategy);
        }
        for path in sorted_files(&dir.join("docs"), "md") {
            let stem = file_stem(&path);
            let raw = std::fs::read_to_string(&path).with_context(|| format!("reading {:?}", path))?;
            corpus.add_doc(&stem, &format!("doc:{}", stem), &raw.replace('\u{00a0}', " "));
        }
        // Notes learned during play (rules, verified controls) are searchable like docs.
        for path in sorted_files(&dir.join(LEARNED_DIR), "md") {
            let stem = file_stem(&path);
            let raw = std::fs::read_to_string(&path).with_context(|| format!("reading {:?}", path))?;
            corpus.add_doc(&format!("learned_{}", stem), &format!("learned:{}", stem), &raw);
        }

        Ok(corpus)
    }

    fn add_record(&mut self, kind: &str, mut r: Record) -> Result<()> {
        if r.name.trim().is_empty() {
            bail!("record has no name");
        }
        if r.id.is_empty() {
            r.id = format!("{}:{}", kind, slug(&r.name));
        }
        if self.by_id.contains_key(&r.id) {
            bail!("duplicate id {:?}", r.id);
        }
        r.index();
        let idx = self.records.len();
        for key in std::iter::once(&r.name).chain(r.aliases.iter()) {
            self.by_name.entry(name_key(kind, key)).or_insert(idx);
        }
        self.by_id.insert(r.id.clone(), idx);
        self.records.push(r);
        Ok(())
    }

    fn add_doc(&mut self, stem: &str, id_prefix: &str, raw: &str) {
        let (title, source, body) = split_header(raw, stem);
        let mut count = 0;
        for (n, text) in chunk_paragraphs(&body, MAX_CHUNK_CHARS).into_iter().enumerate() {
            let id = format!("{}#{}", id_prefix, n);
            self.chunk_by_id.insert(id.clone(), self.chunks.len());
            self.chunks.push(Chunk::new(id, stem.to_string(), title.clone(), text));
            count += 1;
        }
        self.docs.push(DocMeta { stem: stem.to_string(), title, source, chunks: count });
    }

    pub fn get_strategy(&self) -> &str {
        &self.strategy
    }

    pub fn stats(&self) -> Stats {
        let mut records = BTreeMap::new();
        for r in &self.records {
            *records.entry(r.kind().to_string()).or_insert(0) += 1;
        }
        Stats {
            records,
            docs: self.docs.iter().filter(|d| d.stem != "strategy").count(),
            chunks: self.chunks.len(),
            strategy_chars: self.strategy.chars().count(),
        }
    }

    pub fn docs(&self) -> &[DocMeta] {
        &self.docs
    }

    pub fn count(&self, kind: &str) -> usize {
        self.records.iter().filter(|r| r.kind() == kind).count()
    }

    /// Fetch a record or chunk by id (`tech:colonial_policies`, `doc:anomalies#0`, `strategy#2`).
    pub fn get(&self, id: &str) -> Option<Item<'_>> {
        let id = id.trim();
        if let Some(&i) = self.by_id.get(id) {
            return Some(Item::Record(&self.records[i]));
        }
        self.chunk_by_id.get(id).map(|&i| Item::Chunk(&self.chunks[i]))
    }

    /// Find a record of `kind` by name: exact normalized name or alias, else the closest
    /// trigram match above `FUZZY_THRESHOLD`.
    pub fn lookup(&self, kind: &str, name: &str) -> Option<&Record> {
        let norm = normalize(name);
        if norm.is_empty() {
            return None;
        }
        if let Some(&i) = self.by_name.get(&name_key(kind, &norm)) {
            return Some(&self.records[i]);
        }
        let query = trigrams(&norm);
        self.records
            .iter()
            .filter(|r| r.kind() == kind)
            .map(|r| {
                let best = std::iter::once(&r.name)
                    .chain(r.aliases.iter())
                    .map(|n| similarity(&query, &trigrams(&normalize(n))))
                    .fold(0.0, f64::max);
                (best, r)
            })
            .filter(|(s, _)| *s >= FUZZY_THRESHOLD)
            .max_by(|a, b| a.0.partial_cmp(&b.0).unwrap().then_with(|| b.1.id.cmp(&a.1.id)))
            .map(|(_, r)| r)
    }

    /// Keyword search over records and prose chunks. Returns ids and one-line summaries only;
    /// fetch bodies with `get`. Deterministic: ties break on id.
    pub fn search(&self, query: &str, limit: usize) -> Vec<Hit> {
        let norm = normalize(query);
        let tokens: Vec<&str> = norm.split_whitespace().collect();
        if tokens.is_empty() {
            return Vec::new();
        }
        let limit = limit.clamp(1, MAX_SEARCH_LIMIT);
        let mut hits = Vec::new();

        for r in &self.records {
            let name = &r.norm_name;
            let mut score = 0u32;
            if *name == norm || r.aliases.iter().any(|a| normalize(a) == norm) {
                score += 100;
            } else if name.contains(&norm) {
                score += 70;
            } else if tokens.iter().all(|t| name.contains(t)) {
                score += 50;
            }
            let matched = tokens.iter().filter(|t| r.norm_body.contains(*t)).count();
            if matched == tokens.len() {
                score += 20;
            }
            score += (matched as u32) * 5;
            if score > 0 {
                hits.push(Hit {
                    id: r.id.clone(),
                    kind: r.kind().to_string(),
                    title: r.name.clone(),
                    summary: truncate_chars(&r.summary, 120),
                    score,
                });
            }
        }

        for c in &self.chunks {
            if !tokens.iter().all(|t| c.norm.contains(t)) {
                continue;
            }
            let occurrences: usize = tokens.iter().map(|t| c.norm.matches(t).count()).sum();
            let phrase_bonus = if tokens.len() > 1 && c.norm.contains(&norm) { 20 } else { 0 };
            let title_bonus = if tokens.iter().all(|t| normalize(&c.title).contains(t)) { 15 } else { 0 };
            hits.push(Hit {
                id: c.id.clone(),
                kind: if c.doc == "strategy" { "strategy".into() } else { "doc".into() },
                title: c.title.clone(),
                summary: c.snippet(query),
                score: 30 + phrase_bonus + title_bonus + (occurrences.min(10) as u32) * 2,
            });
        }

        hits.sort_by(|a, b| b.score.cmp(&a.score).then_with(|| a.id.cmp(&b.id)));
        hits.truncate(limit);
        hits
    }
}

// ---------------------------------------------------------------------------
// Text helpers
// ---------------------------------------------------------------------------

/// Lowercase, non-alphanumerics to spaces, whitespace collapsed.
pub fn normalize(s: &str) -> String {
    s.to_lowercase()
        .chars()
        .map(|c| if c.is_alphanumeric() { c } else { ' ' })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

pub fn slug(s: &str) -> String {
    normalize(s).replace(' ', "_")
}

fn name_key(kind: &str, name: &str) -> String {
    format!("{}\0{}", kind, normalize(name))
}

fn trigrams(s: &str) -> HashSet<String> {
    let padded: Vec<char> = format!("  {} ", s).chars().collect();
    padded.windows(3).map(|w| w.iter().collect()).collect()
}

/// Dice coefficient over trigram sets.
fn similarity(a: &HashSet<String>, b: &HashSet<String>) -> f64 {
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    2.0 * a.intersection(b).count() as f64 / (a.len() + b.len()) as f64
}

fn truncate_chars(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        format!("{}…", s.chars().take(max - 1).collect::<String>())
    }
}

/// Split a doc into (title, source, body). The header is everything up to the first blank
/// line: a `# Title` line plus `Source:`/`Sources:`/`License:` lines, which never enter chunks.
fn split_header(raw: &str, fallback_title: &str) -> (String, Option<String>, String) {
    let mut lines = raw.lines();
    let mut title = fallback_title.to_string();
    let mut source = None;
    let mut header_done = false;
    let mut body = Vec::new();
    for line in lines.by_ref() {
        if header_done {
            body.push(line);
            continue;
        }
        let t = line.trim();
        if t.is_empty() {
            header_done = true;
        } else if let Some(h) = t.strip_prefix("# ") {
            title = h.trim().to_string();
        } else if let Some(s) = t.strip_prefix("Source:") {
            source = Some(s.trim().to_string());
        } else if t.starts_with("Sources:") || t.starts_with("License:") || t.starts_with("- ") {
            // part of the source block
        } else {
            // No header block at all: this line is body.
            header_done = true;
            body.push(line);
        }
    }
    (title, source, body.join("\n"))
}

/// Group blank-line-separated paragraphs into chunks of at most `max` chars. A single
/// paragraph longer than `max` becomes its own chunk rather than being split mid-sentence.
fn chunk_paragraphs(body: &str, max: usize) -> Vec<String> {
    let mut chunks = Vec::new();
    let mut current = String::new();
    for para in body.split("\n\n").map(str::trim).filter(|p| !p.is_empty()) {
        let extra = para.chars().count() + if current.is_empty() { 0 } else { 2 };
        if !current.is_empty() && current.chars().count() + extra > max {
            chunks.push(std::mem::take(&mut current));
        }
        if !current.is_empty() {
            current.push_str("\n\n");
        }
        current.push_str(para);
    }
    if !current.is_empty() {
        chunks.push(current);
    }
    chunks
}

fn sorted_files(dir: &Path, ext: &str) -> Vec<PathBuf> {
    let mut files: Vec<PathBuf> = std::fs::read_dir(dir)
        .map(|rd| {
            rd.flatten()
                .map(|e| e.path())
                .filter(|p| p.is_file() && p.extension().and_then(|s| s.to_str()) == Some(ext))
                .collect()
        })
        .unwrap_or_default();
    files.sort();
    files
}

fn file_stem(p: &Path) -> String {
    p.file_stem().and_then(|s| s.to_str()).unwrap_or_default().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    const MANIFEST: &str = r#"
[metadata]
id = "testgame"
name = "Test Game"
version = "1"
process_title = "Test"
native_resolution = [3840, 2160]
downscaled_resolution = [1568, 882]

[hotkeys]
end_turn = "enter"
"#;

    struct Fixture(PathBuf);
    impl Fixture {
        fn new(name: &str) -> Self {
            let dir = std::env::temp_dir().join(format!("corpus-test-{}-{}", name, std::process::id()));
            let _ = std::fs::remove_dir_all(&dir);
            std::fs::create_dir_all(dir.join("data")).unwrap();
            std::fs::create_dir_all(dir.join("docs")).unwrap();
            std::fs::write(dir.join("manifest.toml"), MANIFEST).unwrap();
            Self(dir)
        }
        fn write(&self, rel: &str, content: &str) -> &Self {
            std::fs::write(self.0.join(rel), content).unwrap();
            self
        }
        fn load(&self) -> Result<GameCorpus> {
            GameCorpus::load_from_dir(&self.0)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    const TECHS: &str = r#"[
      {"name": "Colonial Policies", "aliases": ["col policies"], "summary": "Adds a policy slot.",
       "fields": {"tree": "Colonization", "cost": 27, "unlocks": ["Supply Ship", "Minister of Colonization"]}},
      {"name": "Xeno Biology", "summary": "Unlocks xeno farming.", "fields": {"tree": "Colonization", "cost": 40}}
    ]"#;

    #[test]
    fn loads_manifest_named_manifest_toml_or_game_toml() {
        let f = Fixture::new("manifest");
        assert_eq!(f.load().unwrap().manifest.metadata.id, "testgame");
        std::fs::rename(f.0.join("manifest.toml"), f.0.join("game.toml")).unwrap();
        assert_eq!(f.load().unwrap().manifest.metadata.id, "testgame");
        std::fs::remove_file(f.0.join("game.toml")).unwrap();
        assert!(f.load().is_err());
    }

    #[test]
    fn learned_overlay_adds_screens_hotkeys_and_notes_without_overriding() {
        let f = Fixture::new("learned");
        std::fs::create_dir_all(f.0.join("learned")).unwrap();
        f.write(
            "learned/manifest.toml",
            r#"
[hotkeys]
end_turn = "space"      # must not override the main manifest
survey = "v"

[screens.new_popup]
description = "learned"
template = "learned/templates/new_popup.png"
template_roi = [0.1, 0.1, 0.1, 0.1]
auto_dismiss = true
dismiss_key = "esc"
"#,
        )
        .write("learned/strategy.md", "# Learned rules\n\nAlways store artifacts while rich.");
        let c = f.load().unwrap();
        assert_eq!(c.manifest.hotkeys["end_turn"], "enter", "main manifest wins");
        assert_eq!(c.manifest.hotkeys["survey"], "v");
        let s = &c.manifest.screens["new_popup"];
        assert!(s.auto_dismiss && s.template.as_deref() == Some("learned/templates/new_popup.png"));
        assert!(c.search("store artifacts", 5).iter().any(|h| h.id.starts_with("learned:strategy#")));
    }

    #[test]
    fn records_get_ids_and_lookup_by_name_alias_and_fuzzy() {
        let f = Fixture::new("lookup");
        f.write("data/tech.json", TECHS);
        let c = f.load().unwrap();
        assert_eq!(c.count("tech"), 2);
        let exact = c.lookup("tech", "Colonial Policies").unwrap();
        assert_eq!(exact.id, "tech:colonial_policies");
        assert_eq!(c.lookup("tech", "col policies").unwrap().id, exact.id);
        assert_eq!(c.lookup("tech", "colonial policy").unwrap().id, exact.id, "fuzzy singular");
        assert!(c.lookup("tech", "warp drive").is_none());
        assert!(c.lookup("improvement", "Colonial Policies").is_none(), "kind is respected");
        assert!(matches!(c.get("tech:xeno_biology"), Some(Item::Record(r)) if r.name == "Xeno Biology"));
    }

    #[test]
    fn record_renders_compactly_with_fields_in_order() {
        let f = Fixture::new("render");
        f.write("data/tech.json", TECHS);
        let c = f.load().unwrap();
        let text = c.get("tech:colonial_policies").unwrap().render();
        assert!(text.starts_with("**Colonial Policies** (tech) — `tech:colonial_policies`"));
        assert!(text.contains("- cost: 27"));
        assert!(text.contains("- unlocks: Supply Ship, Minister of Colonization"));
        assert!(text.chars().count() < 300, "a record must stay small: {}", text.len());
    }

    #[test]
    fn load_rejects_nameless_and_duplicate_records() {
        let f = Fixture::new("invalid");
        f.write("data/tech.json", r#"[{"summary": "no name"}]"#);
        assert!(f.load().is_err());
        f.write("data/tech.json", r#"[{"name": "A"}, {"name": "a"}]"#);
        let err = format!("{:#}", f.load().unwrap_err()); // alternate form includes the cause chain
        assert!(err.contains("duplicate"), "{err}");
        f.write("data/_meta.json", r#"{"game_version": "4.1.1"}"#).write("data/tech.json", "[]");
        assert!(f.load().is_ok(), "_meta.json is not a record file");
    }

    #[test]
    fn docs_are_chunked_within_limit_and_header_is_excluded() {
        let f = Fixture::new("chunks");
        let para = "Manufacturing districts like minerals. ".repeat(20); // ~800 chars
        let doc = format!(
            "# Planet Guide\nSource: https://example.com/guide\nLicense: test\n\n{p}\n\n{p}\n\n{p}\n\nShort tail.",
            p = para.trim()
        );
        f.write("docs/planet_guide.md", &doc);
        let c = f.load().unwrap();
        let n_chunks = c.docs().iter().find(|d| d.stem == "planet_guide").unwrap().chunks;
        let mut chunks: Vec<&Chunk> = Vec::new();
        for n in 0..n_chunks {
            match c.get(&format!("doc:planet_guide#{}", n)) {
                Some(Item::Chunk(ch)) => chunks.push(ch),
                _ => panic!("missing chunk {n}"),
            }
        }
        assert!(chunks.len() >= 2, "3x800 chars must not fit one 1500-char chunk");
        for ch in &chunks {
            assert!(ch.text.chars().count() <= MAX_CHUNK_CHARS, "chunk too long: {}", ch.text.len());
            assert!(!ch.text.contains("Source:"), "header leaked into chunk");
            assert_eq!(ch.title, "Planet Guide");
        }
        assert_eq!(c.docs().iter().find(|d| d.stem == "planet_guide").unwrap().source.as_deref(), Some("https://example.com/guide"));
    }

    #[test]
    fn search_returns_ids_with_summaries_ranked_and_deterministic() {
        let f = Fixture::new("search");
        f.write("data/tech.json", TECHS)
            .write("docs/guide.md", "# Guide\nSource: x\n\nColonial Policies is worth researching early for the policy slot.")
            .write("docs/war.md", "# War\nSource: x\n\nUnrelated paragraph about warfare and policies.")
            .write("strategy.md", "# Playbook\n\n## Opening\n\nResearch Colonial Policies first.");
        let c = f.load().unwrap();
        let hits = c.search("colonial policies", 10);
        assert_eq!(hits[0].id, "tech:colonial_policies", "name match ranks first: {hits:?}");
        assert!(hits.iter().any(|h| h.id.starts_with("doc:guide#")));
        assert!(hits.iter().any(|h| h.id.starts_with("strategy#") && h.kind == "strategy"));
        assert!(!hits.iter().any(|h| h.id.starts_with("doc:war#")), "chunks require all tokens: {hits:?}");
        let guide = hits.iter().find(|h| h.id.starts_with("doc:guide#")).unwrap();
        assert!(guide.summary.contains("Colonial Policies"), "snippet is centred on the match: {}", guide.summary);
        for h in &hits {
            assert!(h.summary.chars().count() <= 120);
        }
        assert_eq!(hits, c.search("colonial policies", 10), "same query, same order");
        assert!(c.search("", 5).is_empty());
        assert_eq!(c.search("colonial", 1).len(), 1);
    }

    #[test]
    fn real_galciv4_corpus_loads() {
        let c = GameCorpus::find_default().expect("corpora/galciv4 must load");
        assert_eq!(c.manifest.metadata.id, "galciv4");
        let s = c.stats();
        assert_eq!(s.docs, 13, "13 reference docs expected: {:?}", c.docs().iter().map(|d| &d.stem).collect::<Vec<_>>());
        assert!(s.chunks > 50);
        assert!(!c.search("draft colonists", 5).is_empty());
        assert!(c.get("doc:anomalies#0").is_some());
    }
}

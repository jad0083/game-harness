//! Game Corpus Loader, Structured Manifest, and Domain Knowledge Search
//!
//! Provides ultra-low-latency in-memory access to GalCiv IV domain knowledge:
//! - Deterministic keyboard shortcuts and screen definitions (`game.toml`)
//! - Strategic playbook rules (`strategy.md`)
//! - Structured technology tree database (`research_tree.txt`)
//! - Structured planetary improvements / districts (`improvements_gc4.txt`)
//! - Structured executive orders (`executive_orders.txt`)
//! - In-memory multi-document search (<100 microseconds) across all wiki articles

#![allow(dead_code)]
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameManifest {
    pub metadata: GameMetadata,
    pub hotkeys: HashMap<String, String>,
    #[serde(default)]
    pub screens: HashMap<String, ScreenDef>,
    #[serde(default)]
    pub macros: HashMap<String, MacroDef>,
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TechInfo {
    pub name: String,
    pub category: String,
    pub description: String,
    pub cost: String,
    pub requirements: Vec<String>,
    pub effects: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImprovementInfo {
    pub name: String,
    pub description: String,
    pub cost: String,
    pub base_effects: Vec<String>,
    pub adjacencies: Vec<String>,
    pub requirements: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderInfo {
    pub name: String,
    pub description: String,
    pub cost: String,
    pub effects: Vec<String>,
    pub requirements: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub source: String,
    pub title: String,
    pub excerpt: String,
    pub score: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameCorpus {
    pub manifest: GameManifest,
    pub strategy: String,
    pub wiki_articles: HashMap<String, String>,
    pub techs: HashMap<String, TechInfo>,
    pub improvements: HashMap<String, ImprovementInfo>,
    pub orders: HashMap<String, OrderInfo>,
}

impl GameManifest {
    pub fn load_from_file<P: AsRef<Path>>(path: P) -> Result<Self> {
        let content = std::fs::read_to_string(path.as_ref())
            .with_context(|| format!("Failed to read game corpus manifest at {:?}", path.as_ref()))?;
        let manifest: Self = toml::from_str(&content)
            .with_context(|| format!("Failed to parse game corpus TOML at {:?}", path.as_ref()))?;
        Ok(manifest)
    }

    pub fn find_default() -> Option<Self> {
        let candidates = [
            PathBuf::from("corpora/galciv4/game.toml"),
            PathBuf::from("../corpora/galciv4/game.toml"),
            PathBuf::from("../../corpora/galciv4/game.toml"),
        ];

        for path in &candidates {
            if path.exists() {
                if let Ok(manifest) = Self::load_from_file(path) {
                    return Some(manifest);
                }
            }
        }
        None
    }

    /// Resolve a logical hotkey name (e.g. "next_action") to its actual key (e.g. "tab")
    pub fn resolve_key<'a>(&'a self, name: &'a str) -> &'a str {
        self.hotkeys.get(name).map(|s| s.as_str()).unwrap_or(name)
    }
}

impl GameCorpus {
    pub fn find_default() -> Option<Self> {
        let candidates = [
            PathBuf::from("corpora/galciv4"),
            PathBuf::from("../corpora/galciv4"),
            PathBuf::from("../../corpora/galciv4"),
        ];

        for path in &candidates {
            if path.is_dir() && path.join("game.toml").exists() {
                if let Ok(corpus) = Self::load_from_dir(path) {
                    return Some(corpus);
                }
            }
        }
        None
    }

    pub fn load_from_dir<P: AsRef<Path>>(dir: P) -> Result<Self> {
        let dir = dir.as_ref();
        let manifest_path = dir.join("game.toml");
        let manifest = GameManifest::load_from_file(&manifest_path)?;

        let strategy_path = dir.join("strategy.md");
        let strategy = if strategy_path.exists() {
            std::fs::read_to_string(&strategy_path).unwrap_or_default()
        } else {
            String::new()
        };

        let mut wiki_articles = HashMap::new();
        let mut techs = HashMap::new();
        let mut improvements = HashMap::new();
        let mut orders = HashMap::new();

        let wiki_dir = dir.join("wiki");
        if wiki_dir.is_dir() {
            if let Ok(entries) = std::fs::read_dir(&wiki_dir) {
                for entry in entries.flatten() {
                    let p = entry.path();
                    if p.is_file() && p.extension().and_then(|s| s.to_str()) == Some("txt") {
                        if let Some(stem) = p.file_stem().and_then(|s| s.to_str()) {
                            if let Ok(raw) = std::fs::read_to_string(&p) {
                                let cleaned = raw.replace('\u{00a0}', " ");
                                match stem {
                                    "research_tree" => {
                                        techs = parse_techs(&cleaned);
                                    }
                                    "improvements_gc4" => {
                                        improvements = parse_improvements(&cleaned);
                                    }
                                    "executive_orders" => {
                                        orders = parse_orders(&cleaned);
                                    }
                                    _ => {}
                                }
                                wiki_articles.insert(stem.to_string(), cleaned);
                            }
                        }
                    }
                }
            }
        }

        Ok(Self {
            manifest,
            strategy,
            wiki_articles,
            techs,
            improvements,
            orders,
        })
    }

    pub fn resolve_key<'a>(&'a self, name: &'a str) -> &'a str {
        self.manifest.resolve_key(name)
    }

    pub fn get_strategy(&self) -> &str {
        &self.strategy
    }

    pub fn lookup_tech(&self, name: &str) -> Option<&TechInfo> {
        let needle = name.trim().to_lowercase();
        // Exact match first
        if let Some(t) = self.techs.get(&needle) {
            return Some(t);
        }
        // Substring match
        self.techs.values().find(|t| t.name.to_lowercase().contains(&needle))
    }

    pub fn lookup_improvement(&self, name: &str) -> Option<&ImprovementInfo> {
        let needle = name.trim().to_lowercase();
        if let Some(imp) = self.improvements.get(&needle) {
            return Some(imp);
        }
        self.improvements.values().find(|i| i.name.to_lowercase().contains(&needle))
    }

    pub fn lookup_order(&self, name: &str) -> Option<&OrderInfo> {
        let needle = name.trim().to_lowercase();
        if let Some(ord) = self.orders.get(&needle) {
            return Some(ord);
        }
        self.orders.values().find(|o| o.name.to_lowercase().contains(&needle))
    }

    /// Ultra-fast in-memory multi-field search across techs, improvements, orders, strategy, and wiki
    pub fn search(&self, query: &str, limit: usize) -> Vec<SearchResult> {
        let q = query.trim().to_lowercase();
        if q.is_empty() {
            return Vec::new();
        }

        let tokens: Vec<&str> = q.split_whitespace().collect();
        let mut results = Vec::new();

        // 1. Search Techs
        for t in self.techs.values() {
            let name_lower = t.name.to_lowercase();
            let desc_lower = t.description.to_lowercase();
            let mut score = 0;

            if name_lower == q {
                score += 150;
            } else if name_lower.contains(&q) {
                score += 80;
            } else if tokens.iter().all(|tok| name_lower.contains(tok)) {
                score += 50;
            }

            for tok in &tokens {
                if desc_lower.contains(tok) {
                    score += 10;
                }
                for eff in &t.effects {
                    if eff.to_lowercase().contains(tok) {
                        score += 15;
                    }
                }
            }

            if score > 0 {
                let excerpt = format!(
                    "{} (Cost: {}) | Effects: {}",
                    t.description,
                    t.cost,
                    t.effects.join(", ")
                );
                results.push(SearchResult {
                    source: "tech".to_string(),
                    title: t.name.clone(),
                    excerpt,
                    score,
                });
            }
        }

        // 2. Search Improvements
        for imp in self.improvements.values() {
            let name_lower = imp.name.to_lowercase();
            let desc_lower = imp.description.to_lowercase();
            let mut score = 0;

            if name_lower == q {
                score += 150;
            } else if name_lower.contains(&q) {
                score += 80;
            } else if tokens.iter().all(|tok| name_lower.contains(tok)) {
                score += 50;
            }

            for tok in &tokens {
                if desc_lower.contains(tok) {
                    score += 10;
                }
                for adj in &imp.adjacencies {
                    if adj.to_lowercase().contains(tok) {
                        score += 20;
                    }
                }
                for be in &imp.base_effects {
                    if be.to_lowercase().contains(tok) {
                        score += 12;
                    }
                }
            }

            if score > 0 {
                let excerpt = format!(
                    "{} (Cost: {}) | Effects: {} | Adjacencies: {}",
                    imp.description,
                    imp.cost,
                    imp.base_effects.join(", "),
                    imp.adjacencies.join(", ")
                );
                results.push(SearchResult {
                    source: "improvement".to_string(),
                    title: imp.name.clone(),
                    excerpt,
                    score,
                });
            }
        }

        // 3. Search Executive Orders
        for ord in self.orders.values() {
            let name_lower = ord.name.to_lowercase();
            let desc_lower = ord.description.to_lowercase();
            let mut score = 0;

            if name_lower == q {
                score += 150;
            } else if name_lower.contains(&q) {
                score += 80;
            } else if tokens.iter().all(|tok| name_lower.contains(tok)) {
                score += 50;
            }

            for tok in &tokens {
                if desc_lower.contains(tok) {
                    score += 10;
                }
                for eff in &ord.effects {
                    if eff.to_lowercase().contains(tok) {
                        score += 20;
                    }
                }
            }

            if score > 0 {
                let excerpt = format!(
                    "{} (Cost: {}) | Effects: {}",
                    ord.description,
                    ord.cost,
                    ord.effects.join(", ")
                );
                results.push(SearchResult {
                    source: "executive_order".to_string(),
                    title: ord.name.clone(),
                    excerpt,
                    score,
                });
            }
        }

        // 4. Search Strategy Playbook
        for (i, line) in self.strategy.lines().enumerate() {
            let line_lower = line.to_lowercase();
            if tokens.iter().any(|tok| line_lower.contains(tok)) {
                let score = if tokens.iter().all(|tok| line_lower.contains(tok)) { 40 } else { 15 };
                results.push(SearchResult {
                    source: "strategy".to_string(),
                    title: format!("Strategy Playbook (line {})", i + 1),
                    excerpt: line.trim().to_string(),
                    score,
                });
            }
        }

        // 5. Search Wiki Articles
        for (article_name, text) in &self.wiki_articles {
            if article_name == "research_tree" || article_name == "improvements_gc4" || article_name == "executive_orders" {
                continue; // already indexed with high precision above
            }
            for para in text.split("\n\n") {
                let trimmed = para.trim();
                if trimmed.len() < 15 {
                    continue;
                }
                let para_lower = trimmed.to_lowercase();
                if tokens.iter().all(|tok| para_lower.contains(tok)) {
                    results.push(SearchResult {
                        source: format!("wiki:{}", article_name),
                        title: article_name.clone(),
                        excerpt: if trimmed.len() > 180 {
                            format!("{}...", &trimmed[..180])
                        } else {
                            trimmed.to_string()
                        },
                        score: 35,
                    });
                }
            }
        }

        // Sort descending by score
        results.sort_by(|a, b| b.score.cmp(&a.score));
        results.truncate(limit);
        results
    }
}

fn parse_techs(content: &str) -> HashMap<String, TechInfo> {
    let mut map = HashMap::new();
    let lines: Vec<&str> = content.lines().map(|l| l.trim()).collect();

    // Cost line pattern: contains "Research" and ("-" or "+") and a digit
    let cost_indices: Vec<usize> = lines
        .iter()
        .enumerate()
        .filter(|(_, l)| {
            l.contains("Research") && (l.contains('-') || l.contains('+')) && l.chars().any(|c| c.is_ascii_digit())
        })
        .map(|(i, _)| i)
        .collect();

    for (idx, &ci) in cost_indices.iter().enumerate() {
        // Collect header lines before ci
        let mut header = Vec::new();
        let mut k = ci as isize - 1;
        while k >= 0 && header.len() < 4 {
            let l = lines[k as usize];
            if !l.is_empty() {
                header.push(l);
            }
            k -= 1;
        }
        header.reverse();

        let (name, category, description) = match header.len() {
            0 => continue,
            1 => (header[0].to_string(), String::new(), String::new()),
            2 => (header[0].to_string(), String::new(), header[1].to_string()),
            3 => (header[0].to_string(), header[1].to_string(), header[2].to_string()),
            _ => (
                header[0].to_string(),
                header[1].to_string(),
                header[2..].join(" "),
            ),
        };

        // Collect requirements & effects after ci until next item's header
        let next_bound = if idx + 1 < cost_indices.len() {
            cost_indices[idx + 1].saturating_sub(4)
        } else {
            lines.len()
        };

        let mut requirements = Vec::new();
        let mut effects = Vec::new();
        let start = (ci + 1).min(lines.len());
        let end = next_bound.max(start).min(lines.len());
        for l in &lines[start..end] {
            if l.is_empty() {
                continue;
            }
            if l.starts_with("Requires") || l.starts_with("Technology Required") {
                requirements.push(l.to_string());
            } else if l.starts_with('+')
                || l.starts_with('-')
                || l.starts_with("Unlocks")
                || l.starts_with("Allows")
                || l.starts_with("Upgrades")
            {
                effects.push(l.to_string());
            }
        }

        let clean_name = name.trim().trim_start_matches(|c: char| !c.is_alphanumeric()).to_string();
        if clean_name.is_empty() {
            continue;
        }

        let key = clean_name.to_lowercase();
        map.insert(
            key,
            TechInfo {
                name: clean_name,
                category,
                description,
                cost: lines[ci].to_string(),
                requirements,
                effects,
            },
        );
    }

    map
}

fn parse_improvements(content: &str) -> HashMap<String, ImprovementInfo> {
    let mut map = HashMap::new();
    let lines: Vec<&str> = content.lines().map(|l| l.trim()).collect();

    let cost_indices: Vec<usize> = lines
        .iter()
        .enumerate()
        .filter(|(_, l)| l.contains("Manufacturing Cost") && l.chars().any(|c| c.is_ascii_digit()))
        .map(|(i, _)| i)
        .collect();

    for (idx, &ci) in cost_indices.iter().enumerate() {
        let mut header = Vec::new();
        let mut k = ci as isize - 1;
        while k >= 0 && header.len() < 2 {
            let l = lines[k as usize];
            if !l.is_empty() {
                header.push(l);
            }
            k -= 1;
        }
        header.reverse();

        let (name, description) = match header.len() {
            0 => continue,
            1 => (header[0].to_string(), String::new()),
            _ => (header[0].to_string(), header[1].to_string()),
        };

        let next_bound = if idx + 1 < cost_indices.len() {
            cost_indices[idx + 1].saturating_sub(2)
        } else {
            lines.len()
        };

        let mut base_effects = Vec::new();
        let mut adjacencies = Vec::new();
        let mut requirements = Vec::new();
        let start = (ci + 1).min(lines.len());
        let end = next_bound.max(start).min(lines.len());
        for l in &lines[start..end] {
            if l.is_empty() {
                continue;
            }
            if l.starts_with("Technology Required") || l.starts_with("Requires") || l.starts_with("Unavailable") {
                requirements.push(l.to_string());
            } else if l.contains("All Improvements") || l.contains("Adjacent") {
                adjacencies.push(l.to_string());
            } else if l.starts_with('+') || l.starts_with('-') || l.starts_with("+-") {
                base_effects.push(l.to_string());
            }
        }

        let clean_name = name.trim().trim_start_matches(|c: char| !c.is_alphanumeric()).to_string();
        if clean_name.is_empty() {
            continue;
        }

        let key = clean_name.to_lowercase();
        map.insert(
            key,
            ImprovementInfo {
                name: clean_name,
                description,
                cost: lines[ci].to_string(),
                base_effects,
                adjacencies,
                requirements,
            },
        );
    }

    map
}

fn parse_orders(content: &str) -> HashMap<String, OrderInfo> {
    let mut map = HashMap::new();
    let lines: Vec<&str> = content.lines().map(|l| l.trim()).collect();

    let cost_indices: Vec<usize> = lines
        .iter()
        .enumerate()
        .filter(|(_, l)| {
            l.contains("Control") && (l.contains('-') || l.contains('+')) && l.chars().any(|c| c.is_ascii_digit())
        })
        .map(|(i, _)| i)
        .collect();

    for (idx, &ci) in cost_indices.iter().enumerate() {
        let mut k = ci as isize - 1;
        // Skip empty lines immediately before cost
        while k >= 0 && lines[k as usize].is_empty() {
            k -= 1;
        }

        let mut effects = Vec::new();
        while k >= 0 {
            let l = lines[k as usize];
            if l.is_empty() {
                break;
            }
            if l.starts_with('+') || l.starts_with('-') || l.contains("Provides") || l.contains("Spawns") {
                effects.push(l.to_string());
                k -= 1;
            } else {
                break;
            }
        }
        effects.reverse();

        while k >= 0 && lines[k as usize].is_empty() {
            k -= 1;
        }

        let mut desc_lines = Vec::new();
        while k >= 0 && desc_lines.len() < 2 {
            let l = lines[k as usize];
            if !l.is_empty() && !l.ends_with(':') && l != "Requirements" && l != "Cost" {
                desc_lines.push(l.to_string());
            }
            k -= 1;
        }
        desc_lines.reverse();

        let (name, description) = match desc_lines.len() {
            0 => ("Unknown".to_string(), String::new()),
            1 => (desc_lines[0].clone(), String::new()),
            _ => (desc_lines[0].clone(), desc_lines[1..].join(" ")),
        };

        let next_bound = if idx + 1 < cost_indices.len() {
            cost_indices[idx + 1].saturating_sub(4)
        } else {
            lines.len()
        };

        let mut requirements = Vec::new();
        let start = (ci + 1).min(lines.len());
        let end = next_bound.max(start).min(lines.len());
        for l in &lines[start..end] {
            if l.starts_with("Technology Required") || l.starts_with("Race Trait") || l.starts_with("Requires") {
                requirements.push(l.to_string());
            }
        }

        let clean_name = name.trim().trim_start_matches(|c: char| !c.is_alphanumeric()).to_string();
        if clean_name.is_empty() || clean_name.len() > 60 {
            continue;
        }

        let key = clean_name.to_lowercase();
        map.insert(
            key,
            OrderInfo {
                name: clean_name,
                description,
                cost: lines[ci].to_string(),
                effects,
                requirements,
            },
        );
    }

    map
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_find_and_load_corpus() {
        let corpus = GameCorpus::find_default().expect("Default corpus must be found");
        assert_eq!(corpus.manifest.metadata.id, "galciv4");
        assert!(!corpus.manifest.hotkeys.is_empty());
        assert!(!corpus.techs.is_empty());
        assert!(!corpus.improvements.is_empty());
        assert!(!corpus.orders.is_empty());
        assert!(!corpus.strategy.is_empty());
    }

    #[test]
    fn test_lookup_and_search() {
        let corpus = GameCorpus::find_default().expect("Default corpus must be found");
        
        let colonist = corpus.lookup_order("draft colonists");
        assert!(colonist.is_some());
        let ord = colonist.unwrap();
        assert!(ord.effects.iter().any(|e| e.contains("Colony Ship")));

        let capital = corpus.lookup_improvement("capital city");
        assert!(capital.is_some());

        let sublight = corpus.search("sublight drives", 5);
        assert!(!sublight.is_empty());
    }
}

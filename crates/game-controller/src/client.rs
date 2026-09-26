#![allow(dead_code)]
use anyhow::{Context, Result};
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use serde::Serialize;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Duration;

pub const DEFAULT_URL: &str = "http://192.168.1.77:8765";

pub struct AgentClient {
    client: reqwest::Client,
    base_url: String,
    token: String,
    pub last_width: Arc<AtomicU32>,
    pub last_height: Arc<AtomicU32>,
    pub last_target_width: Arc<AtomicU32>,
    pub last_target_height: Arc<AtomicU32>,
}

/// One entry of an agent directory listing.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct FileEntry {
    pub name: String,
    pub is_dir: bool,
    pub size: u64,
    /// Seconds since the Unix epoch.
    pub modified: u64,
}

#[derive(Serialize)]
struct MoveReq {
    x: i32,
    y: i32,
}

#[derive(Serialize)]
struct ClickReq {
    x: i32,
    y: i32,
    button: String,
    count: i32,
}

#[derive(Serialize)]
struct DragReq {
    x1: i32,
    y1: i32,
    x2: i32,
    y2: i32,
    button: String,
    #[serde(flatten)]
    opts: DragOptions,
}

/// Optional `/drag` timing knobs. `None` fields are omitted so the agent applies its
/// own defaults (hold 30 ms, 12 steps, 15 ms/step, dwell 30 ms, no wiggle).
#[derive(Serialize, Debug, Clone, Default, PartialEq)]
pub struct DragOptions {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hold_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub steps: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dwell_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub wiggle: Option<bool>,
}

#[derive(Serialize)]
struct ScrollReq {
    x: i32,
    y: i32,
    clicks: i32,
}

#[derive(Serialize)]
struct KeyReq {
    combo: String,
    repeat: i32,
}

#[derive(Serialize)]
struct TypeReq {
    text: String,
}

#[derive(Serialize)]
struct FocusReq {
    title: String,
}

#[derive(Serialize)]
struct BatchReq {
    actions: Vec<serde_json::Value>,
}

fn load_token(explicit: Option<&str>) -> Result<String> {
    if let Some(t) = explicit {
        if !t.trim().is_empty() {
            return Ok(t.trim().to_string());
        }
    }
    if let Ok(t) = std::env::var("GAME_AGENT_TOKEN") {
        if !t.trim().is_empty() {
            return Ok(t.trim().to_string());
        }
    }
    let candidates = [
        PathBuf::from(".agent_token"),
        PathBuf::from("agent_token.txt"),
    ];
    for p in &candidates {
        if p.exists() {
            if let Ok(c) = std::fs::read_to_string(p) {
                let trimmed = c.trim();
                if !trimmed.is_empty() {
                    return Ok(trimmed.to_string());
                }
            }
        }
    }
    anyhow::bail!("No agent token found: set GAME_AGENT_TOKEN or write to .agent_token")
}

impl AgentClient {
    pub fn new(base_url: Option<&str>, token: Option<&str>) -> Result<Self> {
        let url = base_url
            .map(|s| s.to_string())
            .or_else(|| std::env::var("GAME_AGENT_URL").ok())
            .unwrap_or_else(|| DEFAULT_URL.to_string())
            .trim_end_matches('/')
            .to_string();

        let tok = load_token(token)?;

        let mut headers = HeaderMap::new();
        let auth_val = format!("Bearer {}", tok);
        headers.insert(AUTHORIZATION, HeaderValue::from_str(&auth_val)?);
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));

        let client = reqwest::Client::builder()
            .default_headers(headers)
            .tcp_nodelay(true)
            .pool_idle_timeout(Duration::from_secs(60))
            .pool_max_idle_per_host(10)
            .timeout(Duration::from_secs(30))
            .build()?;

        Ok(Self {
            client,
            base_url: url,
            token: tok,
            last_width: Arc::new(AtomicU32::new(0)),
            last_height: Arc::new(AtomicU32::new(0)),
            last_target_width: Arc::new(AtomicU32::new(0)),
            last_target_height: Arc::new(AtomicU32::new(0)),
        })
    }

    pub fn token(&self) -> &str {
        &self.token
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub async fn health(&self) -> Result<serde_json::Value> {
        let resp = self
            .client
            .get(format!("{}/health", self.base_url))
            .send()
            .await
            .context("Failed to send /health request")?;

        if !resp.status().is_success() {
            anyhow::bail!("Health returned HTTP {}", resp.status());
        }

        let json = resp.json().await?;
        Ok(json)
    }

    pub async fn state(&self) -> Result<serde_json::Value> {
        let health = self.health().await?;
        let windows = self.windows().await.unwrap_or_else(|_| serde_json::json!({}));
        let mut combined = health.as_object().cloned().unwrap_or_default();
        if let Some(wins) = windows.get("windows") {
            combined.insert("windows".to_string(), wins.clone());
        }
        Ok(serde_json::Value::Object(combined))
    }

    pub async fn screenshot(
        &self,
        x: Option<i32>,
        y: Option<i32>,
        w: Option<i32>,
        h: Option<i32>,
        max_side: Option<i32>,
        quality: Option<u8>,
    ) -> Result<Vec<u8>> {
        let mut query = Vec::new();
        if let Some(v) = x { query.push(format!("x={}", v)); }
        if let Some(v) = y { query.push(format!("y={}", v)); }
        if let Some(v) = w { query.push(format!("w={}", v)); }
        if let Some(v) = h { query.push(format!("h={}", v)); }
        if let Some(v) = max_side { query.push(format!("max_side={}", v)); }
        if let Some(v) = quality { query.push(format!("quality={}", v)); }

        let qs = if query.is_empty() { String::new() } else { format!("?{}", query.join("&")) };
        let url = format!("{}/screenshot{}", self.base_url, qs);

        let resp = self.client.get(&url).send().await.context("Failed /screenshot")?;

        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            anyhow::bail!("Screenshot failed (HTTP {}): {}", status, text);
        }

        let headers = resp.headers().clone();
        if let Some(w) = headers.get("x-width").and_then(|v| v.to_str().ok()).and_then(|s| s.parse::<u32>().ok()) {
            self.last_width.store(w, Ordering::Relaxed);
        }
        if let Some(h) = headers.get("x-height").and_then(|v| v.to_str().ok()).and_then(|s| s.parse::<u32>().ok()) {
            self.last_height.store(h, Ordering::Relaxed);
        }
        if let Some(tw) = headers.get("x-target-width").and_then(|v| v.to_str().ok()).and_then(|s| s.parse::<u32>().ok()) {
            self.last_target_width.store(tw, Ordering::Relaxed);
        }
        if let Some(th) = headers.get("x-target-height").and_then(|v| v.to_str().ok()).and_then(|s| s.parse::<u32>().ok()) {
            self.last_target_height.store(th, Ordering::Relaxed);
        }

        let bytes = resp.bytes().await?;
        Ok(bytes.to_vec())
    }

    pub async fn settle(&self, timeout: Option<f64>, threshold: Option<f64>) -> Result<serde_json::Value> {
        let mut query = Vec::new();
        if let Some(t) = timeout { query.push(format!("timeout={}", t)); }
        if let Some(th) = threshold { query.push(format!("threshold={}", th)); }
        let qs = if query.is_empty() { String::new() } else { format!("?{}", query.join("&")) };

        let resp = self
            .client
            .get(format!("{}/settle{}", self.base_url, qs))
            .send()
            .await
            .context("Failed /settle")?;

        let json = resp.json().await?;
        Ok(json)
    }

    pub async fn windows(&self) -> Result<serde_json::Value> {
        let resp = self
            .client
            .get(format!("{}/windows", self.base_url))
            .send()
            .await
            .context("Failed /windows")?;

        let json = resp.json().await?;
        Ok(json)
    }

    pub async fn focus(&self, title: &str) -> Result<String> {
        let resp = self
            .client
            .post(format!("{}/focus", self.base_url))
            .json(&FocusReq { title: title.to_string() })
            .send()
            .await
            .context("Failed /focus")?;

        let json: serde_json::Value = resp.json().await?;
        let focused = json.get("focused").and_then(|v| v.as_str()).unwrap_or(title);
        Ok(focused.to_string())
    }

    /// List a directory inside one of the agent's read-only roots (agent >= 1.2.0).
    pub async fn files_list(&self, root: &str, path: &str) -> Result<Vec<FileEntry>> {
        let resp = self
            .client
            .get(format!("{}/files/list", self.base_url))
            .query(&[("root", root), ("path", path)])
            .send()
            .await
            .context("Failed /files/list")?;
        let status = resp.status();
        let json: serde_json::Value = resp.json().await.context("bad /files/list response")?;
        if !status.is_success() {
            anyhow::bail!("/files/list {root}:{path}: HTTP {status}: {}", json["error"]);
        }
        Ok(serde_json::from_value(json["entries"].clone())?)
    }

    /// Write a file inside one of the agent's write roots (agent >= 1.3.0; allowed paths only).
    pub async fn files_write(&self, root: &str, path: &str, data: Vec<u8>) -> Result<()> {
        let resp = self
            .client
            .put(format!("{}/files/write", self.base_url))
            .query(&[("root", root), ("path", path)])
            .body(data)
            .send()
            .await
            .context("Failed /files/write")?;
        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("/files/write {root}:{path}: HTTP {status}: {body}");
        }
        Ok(())
    }

    /// Read a file (from `offset`, at most `max` bytes) inside one of the agent's roots.
    /// Returns the bytes and the file's total size.
    pub async fn files_read(&self, root: &str, path: &str, offset: u64, max: Option<u64>) -> Result<(Vec<u8>, u64)> {
        let mut q = vec![("root", root.to_string()), ("path", path.to_string()), ("offset", offset.to_string())];
        if let Some(m) = max {
            q.push(("max", m.to_string()));
        }
        let resp = self
            .client
            .get(format!("{}/files/read", self.base_url))
            .query(&q)
            .send()
            .await
            .context("Failed /files/read")?;
        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("/files/read {root}:{path}: HTTP {status}: {body}");
        }
        let size = resp
            .headers()
            .get("x-file-size")
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.parse().ok())
            .unwrap_or(0);
        Ok((resp.bytes().await?.to_vec(), size))
    }

    pub async fn move_mouse(&self, x: i32, y: i32) -> Result<()> {
        self.client
            .post(format!("{}/move", self.base_url))
            .json(&MoveReq { x, y })
            .send()
            .await?
            .error_for_status()?;
        Ok(())
    }

    pub async fn click(&self, x: i32, y: i32, button: &str, count: i32) -> Result<()> {
        self.client
            .post(format!("{}/click", self.base_url))
            .json(&ClickReq {
                x,
                y,
                button: button.to_string(),
                count,
            })
            .send()
            .await?
            .error_for_status()?;
        Ok(())
    }

    pub async fn drag(&self, x1: i32, y1: i32, x2: i32, y2: i32, button: &str, opts: &DragOptions) -> Result<()> {
        self.client
            .post(format!("{}/drag", self.base_url))
            .json(&DragReq {
                x1,
                y1,
                x2,
                y2,
                button: button.to_string(),
                opts: opts.clone(),
            })
            .send()
            .await?
            .error_for_status()?;
        Ok(())
    }

    pub async fn scroll(&self, x: i32, y: i32, clicks: i32) -> Result<()> {
        self.client
            .post(format!("{}/scroll", self.base_url))
            .json(&ScrollReq { x, y, clicks })
            .send()
            .await?
            .error_for_status()?;
        Ok(())
    }

    pub async fn key(&self, combo: &str, repeat: i32) -> Result<()> {
        self.client
            .post(format!("{}/key", self.base_url))
            .json(&KeyReq {
                combo: combo.to_string(),
                repeat,
            })
            .send()
            .await?
            .error_for_status()?;
        Ok(())
    }

    pub async fn type_text(&self, text: &str) -> Result<()> {
        self.client
            .post(format!("{}/type", self.base_url))
            .json(&TypeReq {
                text: text.to_string(),
            })
            .send()
            .await?
            .error_for_status()?;
        Ok(())
    }

    pub async fn batch(&self, actions: Vec<serde_json::Value>) -> Result<Vec<serde_json::Value>> {
        let resp = self
            .client
            .post(format!("{}/batch", self.base_url))
            .json(&BatchReq { actions })
            .send()
            .await?
            .error_for_status()?;

        let json: serde_json::Value = resp.json().await?;
        let results = json
            .get("results")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        Ok(results)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn drag_json(opts: DragOptions) -> serde_json::Value {
        serde_json::to_value(DragReq { x1: 1, y1: 2, x2: 3, y2: 4, button: "left".into(), opts }).unwrap()
    }

    #[test]
    fn drag_request_omits_unset_options_so_agent_defaults_apply() {
        assert_eq!(
            drag_json(DragOptions::default()),
            serde_json::json!({"x1": 1, "y1": 2, "x2": 3, "y2": 4, "button": "left"})
        );
    }

    #[test]
    fn drag_request_flattens_set_options() {
        let v = drag_json(DragOptions { hold_ms: Some(250), steps: Some(40), step_ms: None, dwell_ms: Some(300), wiggle: Some(true) });
        assert_eq!(v["hold_ms"], 250);
        assert_eq!(v["steps"], 40);
        assert_eq!(v["dwell_ms"], 300);
        assert_eq!(v["wiggle"], true);
        assert!(v.get("step_ms").is_none());
    }
}

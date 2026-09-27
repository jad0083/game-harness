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
        json_ok(resp, "/settle").await
    }

    pub async fn windows(&self) -> Result<serde_json::Value> {
        let resp = self
            .client
            .get(format!("{}/windows", self.base_url))
            .send()
            .await
            .context("Failed /windows")?;
        json_ok(resp, "/windows").await
    }

    pub async fn focus(&self, title: &str) -> Result<String> {
        let resp = self
            .client
            .post(format!("{}/focus", self.base_url))
            .json(&FocusReq { title: title.to_string() })
            .send()
            .await
            .context("Failed /focus")?;
        let json = json_ok(resp, "/focus").await?;
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

    /// Read a file (from `offset`, at most `max` bytes; `None` = to the end) inside one of the
    /// agent's roots. Returns the bytes and the file's total size. The agent caps one response
    /// (16 MiB since 1.5.0), so larger reads are fetched in pages; the size of the first response
    /// is the end, and a file that shrinks meanwhile (a save being rewritten) is an error.
    pub async fn files_read(&self, root: &str, path: &str, offset: u64, max: Option<u64>) -> Result<(Vec<u8>, u64)> {
        let (mut out, size) = self.files_read_page(root, path, offset, max).await?;
        let end = max.map_or(size, |m| offset.saturating_add(m).min(size));
        loop {
            let at = offset.saturating_add(out.len() as u64);
            if at >= end {
                break;
            }
            let (chunk, now) = self.files_read_page(root, path, at, Some(end - at)).await?;
            if now < end {
                anyhow::bail!("/files/read {root}:{path}: the file changed while reading ({size} -> {now} bytes)");
            }
            if chunk.is_empty() {
                break;
            }
            out.extend_from_slice(&chunk);
        }
        Ok((out, size))
    }

    /// One /files/read request (the agent may return fewer bytes than asked).
    async fn files_read_page(&self, root: &str, path: &str, offset: u64, max: Option<u64>) -> Result<(Vec<u8>, u64)> {
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

/// The JSON body of a successful response; otherwise an error with the status and the agent's
/// message (a 401 or a 404 "window not found" must not read as success or as a parse error).
async fn json_ok(resp: reqwest::Response, what: &str) -> Result<serde_json::Value> {
    let status = resp.status();
    let body = resp.text().await.with_context(|| format!("reading {what} response"))?;
    if !status.is_success() {
        let msg = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("error").and_then(|e| e.as_str()).map(str::to_string))
            .unwrap_or_else(|| body.chars().take(200).collect());
        anyhow::bail!("{what} returned HTTP {status}{}", if msg.is_empty() { String::new() } else { format!(": {msg}") });
    }
    serde_json::from_str(&body).with_context(|| format!("bad {what} response"))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Serve one canned HTTP response on a local port and return its URL.
    async fn one_shot(status: &str, body: &str) -> String {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let reply = format!("HTTP/1.1 {status}\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}", body.len());
        tokio::spawn(async move {
            let (mut sock, _) = listener.accept().await.unwrap();
            let mut buf = [0u8; 4096];
            let _ = sock.read(&mut buf).await;
            sock.write_all(reply.as_bytes()).await.unwrap();
        });
        url
    }

    #[tokio::test]
    async fn focus_reports_a_missing_window_instead_of_success() {
        let url = one_shot("404 Not Found", r#"{"error":"no window titled Stellaris"}"#).await;
        let c = AgentClient::new(Some(&url), Some("t")).unwrap();
        let e = c.focus("Stellaris").await.unwrap_err().to_string();
        assert!(e.contains("404") && e.contains("no window titled Stellaris"), "{e}");
    }

    #[tokio::test]
    async fn unauthorized_is_an_http_error_not_a_parse_error() {
        let url = one_shot("401 Unauthorized", "").await;
        let c = AgentClient::new(Some(&url), Some("t")).unwrap();
        let e = c.windows().await.unwrap_err().to_string();
        assert!(e.contains("401"), "{e}");
    }

    #[tokio::test]
    async fn focus_returns_the_focused_title() {
        let url = one_shot("200 OK", r#"{"ok":true,"focused":"Stellaris"}"#).await;
        let c = AgentClient::new(Some(&url), Some("t")).unwrap();
        assert_eq!(c.focus("Stell").await.unwrap(), "Stellaris");
    }

    /// A fake /files/read that returns at most `cap` bytes per response, like the agent's
    /// MAX_READ, and reports `sizes[i]` as the file size of the i-th response (last one repeats).
    async fn paging_agent(data: Vec<u8>, cap: usize, sizes: Vec<u64>) -> (String, std::sync::Arc<std::sync::atomic::AtomicUsize>) {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let calls = std::sync::Arc::new(AtomicUsize::new(0));
        let counter = calls.clone();
        tokio::spawn(async move {
            loop {
                let (mut sock, _) = listener.accept().await.unwrap();
                let mut buf = vec![0u8; 8192];
                let n = sock.read(&mut buf).await.unwrap();
                let req = String::from_utf8_lossy(&buf[..n]).to_string();
                let line = req.lines().next().unwrap_or("").to_string();
                let param = |k: &str| -> Option<u64> {
                    let q = line.split_once('?')?.1.split(' ').next()?;
                    q.split('&').find_map(|kv| kv.strip_prefix(&format!("{k}="))?.parse().ok())
                };
                let i = counter.fetch_add(1, Ordering::SeqCst);
                let size = *sizes.get(i).or(sizes.last()).unwrap();
                let off = param("offset").unwrap_or(0).min(data.len() as u64) as usize;
                let max = param("max").unwrap_or(u64::MAX).min(cap as u64) as usize;
                let body = &data[off..(off + max).min(data.len())];
                let head = format!(
                    "HTTP/1.1 200 OK\r\ncontent-type: application/octet-stream\r\nx-file-size: {size}\r\ncontent-length: {}\r\nconnection: close\r\n\r\n",
                    body.len()
                );
                sock.write_all(head.as_bytes()).await.unwrap();
                sock.write_all(body).await.unwrap();
            }
        });
        (url, calls)
    }

    #[tokio::test]
    async fn files_read_pages_past_the_agents_per_response_cap() {
        let data: Vec<u8> = (0..25u8).collect();
        let (url, calls) = paging_agent(data.clone(), 10, vec![25]).await;
        let c = AgentClient::new(Some(&url), Some("t")).unwrap();
        let (bytes, size) = c.files_read("r", "save.sav", 0, None).await.unwrap();
        assert_eq!((bytes, size), (data.clone(), 25));
        assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 3);
        let (tail, _) = c.files_read("r", "save.sav", 18, None).await.unwrap();
        assert_eq!(tail, data[18..]);
        let (some, _) = c.files_read("r", "save.sav", 2, Some(15)).await.unwrap();
        assert_eq!(some, data[2..17], "an explicit max is honoured across pages");
        let (none, size) = c.files_read("r", "save.sav", 0, Some(0)).await.unwrap();
        assert_eq!((none.len(), size), (0, 25), "max=0 asks only for the size");
    }

    #[tokio::test]
    async fn files_read_fails_when_the_file_shrinks_between_pages() {
        let data: Vec<u8> = (0..25u8).collect();
        let (url, _) = paging_agent(data, 10, vec![25, 5]).await;
        let c = AgentClient::new(Some(&url), Some("t")).unwrap();
        let e = c.files_read("r", "save.sav", 0, None).await.unwrap_err().to_string();
        assert!(e.contains("changed"), "{e}");
    }

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

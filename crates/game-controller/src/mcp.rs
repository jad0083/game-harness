#![allow(dead_code)]
use crate::client::AgentClient;
use crate::imaging::{detect_change_bbox, highlight_region, View, MAX_SIDE};
use anyhow::Result;
use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::atomic::Ordering;
use std::sync::{Arc, Mutex};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

#[derive(Deserialize)]
struct RpcRequest {
    jsonrpc: String,
    id: Option<Value>,
    method: String,
    params: Option<Value>,
}

#[derive(Serialize)]
struct RpcResponse {
    jsonrpc: &'static str,
    id: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<Value>,
}

pub struct McpServer {
    client: Arc<AgentClient>,
    last_frame: Mutex<Option<Vec<u8>>>,
    view: Mutex<Option<View>>,
    corpus: Option<Arc<crate::corpus::GameCorpus>>,
    manifest: Option<crate::corpus::GameManifest>,
}

impl McpServer {
    pub fn new(client: Arc<AgentClient>) -> Self {
        let corpus = crate::corpus::GameCorpus::find_default().map(Arc::new);
        let manifest = corpus.as_ref().map(|c| c.manifest.clone()).or_else(crate::corpus::GameManifest::find_default);
        Self {
            client,
            last_frame: Mutex::new(None),
            view: Mutex::new(None),
            corpus,
            manifest,
        }
    }

    pub fn with_corpus(mut self, corpus: Arc<crate::corpus::GameCorpus>) -> Self {
        self.manifest = Some(corpus.manifest.clone());
        self.corpus = Some(corpus);
        self
    }

    pub fn with_manifest(mut self, manifest: crate::corpus::GameManifest) -> Self {
        self.manifest = Some(manifest);
        self
    }

    async fn capture_frame(&self) -> Result<(Vec<u8>, View)> {
        let jpeg = self
            .client
            .screenshot(None, None, None, None, Some(MAX_SIDE as i32), Some(75))
            .await?;

        let orig_w = self.client.last_width.load(Ordering::Relaxed).max(1);
        let target_w = self.client.last_target_width.load(Ordering::Relaxed).max(1);
        let _orig_h = self.client.last_height.load(Ordering::Relaxed).max(1);
        let target_h = self.client.last_target_height.load(Ordering::Relaxed).max(1);

        let scale = orig_w as f64 / target_w as f64;
        let v = View::new(0, 0, scale, target_w, target_h);

        *self.view.lock().unwrap() = Some(v);
        *self.last_frame.lock().unwrap() = Some(jpeg.clone());

        Ok((jpeg, v))
    }

    fn to_screen_coords(&self, x: f64, y: f64) -> (i32, i32) {
        let v = *self.view.lock().unwrap();
        match v {
            Some(view) => view.to_screen(x, y).unwrap_or((x as i32, y as i32)),
            None => (x as i32, y as i32),
        }
    }

    pub async fn run_stdio(&self) -> Result<()> {
        let stdin = tokio::io::stdin();
        let mut stdout = tokio::io::stdout();
        let mut reader = BufReader::new(stdin).lines();

        while let Some(line) = reader.next_line().await? {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }

            let req: RpcRequest = match serde_json::from_str(line) {
                Ok(r) => r,
                Err(e) => {
                    let err_resp = RpcResponse {
                        jsonrpc: "2.0",
                        id: None,
                        result: None,
                        error: Some(serde_json::json!({"code": -32700, "message": e.to_string()})),
                    };
                    let out = serde_json::to_string(&err_resp)? + "\n";
                    stdout.write_all(out.as_bytes()).await?;
                    stdout.flush().await?;
                    continue;
                }
            };

            let res = self.handle_request(req).await;
            if let Some(resp) = res {
                let out = serde_json::to_string(&resp)? + "\n";
                stdout.write_all(out.as_bytes()).await?;
                stdout.flush().await?;
            }
        }
        Ok(())
    }

    async fn handle_request(&self, req: RpcRequest) -> Option<RpcResponse> {
        let id = req.id.clone();
        match req.method.as_str() {
            "initialize" => Some(RpcResponse {
                jsonrpc: "2.0",
                id,
                result: Some(serde_json::json!({
                    "protocolVersion": "2024-11-05",
                    "capabilities": { "tools": {} },
                    "serverInfo": { "name": "game-controller", "version": "1.0.0" }
                })),
                error: None,
            }),
            "notifications/initialized" => None,
            "ping" => Some(RpcResponse {
                jsonrpc: "2.0",
                id,
                result: Some(serde_json::json!({})),
                error: None,
            }),
            "tools/list" => Some(RpcResponse {
                jsonrpc: "2.0",
                id,
                result: Some(serde_json::json!({
                    "tools": self.list_tools()
                })),
                error: None,
            }),
            "tools/call" => {
                let params = req.params.unwrap_or_default();
                let name = params.get("name").and_then(|v| v.as_str()).unwrap_or("");
                let args = params.get("arguments").cloned().unwrap_or(serde_json::json!({}));

                match self.dispatch_tool(name, args).await {
                    Ok(result) => Some(RpcResponse {
                        jsonrpc: "2.0",
                        id,
                        result: Some(result),
                        error: None,
                    }),
                    Err(e) => Some(RpcResponse {
                        jsonrpc: "2.0",
                        id,
                        result: Some(serde_json::json!({
                            "content": [{
                                "type": "text",
                                "text": format!("ERROR: {}", e)
                            }],
                            "isError": true
                        })),
                        error: None,
                    }),
                }
            }
            _ => Some(RpcResponse {
                jsonrpc: "2.0",
                id,
                result: None,
                error: Some(serde_json::json!({
                    "code": -32601,
                    "message": format!("Method not found: {}", req.method)
                })),
            }),
        }
    }

    fn list_tools(&self) -> Vec<Value> {
        vec![
            serde_json::json!({
                "name": "screenshot",
                "description": "Capture the full screen from the Windows agent.",
                "inputSchema": { "type": "object", "properties": {} }
            }),
            serde_json::json!({
                "name": "click",
                "description": "Click at (x, y) in the last image coordinates.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x": { "type": "number" },
                        "y": { "type": "number" },
                        "button": { "type": "string", "default": "left" },
                        "count": { "type": "integer", "default": 1 },
                        "wait": { "type": "number", "default": 0.5 }
                    },
                    "required": ["x", "y"]
                }
            }),
            serde_json::json!({
                "name": "drag",
                "description": "Drag from (x1, y1) to (x2, y2) in the last image coordinates.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x1": { "type": "number" },
                        "y1": { "type": "number" },
                        "x2": { "type": "number" },
                        "y2": { "type": "number" },
                        "button": { "type": "string", "default": "left" },
                        "wait": { "type": "number", "default": 0.5 }
                    },
                    "required": ["x1", "y1", "x2", "y2"]
                }
            }),
            serde_json::json!({
                "name": "key",
                "description": "Press a key or combo (e.g. enter, esc, tab, space, f).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "combo": { "type": "string" },
                        "repeat": { "type": "integer", "default": 1 }
                    },
                    "required": ["combo"]
                }
            }),
            serde_json::json!({
                "name": "type_text",
                "description": "Type literal text into focused field.",
                "inputSchema": {
                    "type": "object",
                    "properties": { "text": { "type": "string" } },
                    "required": ["text"]
                }
            }),
            serde_json::json!({
                "name": "batch",
                "description": "Execute a list of actions atomically in a single round-trip.",
                "inputSchema": {
                    "type": "object",
                    "properties": { "actions": { "type": "array", "items": { "type": "object" } } },
                    "required": ["actions"]
                }
            }),
            serde_json::json!({
                "name": "wait_settle",
                "description": "Wait dynamically for animations / AI turns to stabilize, returning screenshot.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "timeout": { "type": "number", "default": 15.0 },
                        "threshold": { "type": "number", "default": 0.02 }
                    }
                }
            }),
            serde_json::json!({
                "name": "diff",
                "description": "Compare against previous frame and highlight visual changes.",
                "inputSchema": { "type": "object", "properties": {} }
            }),
            serde_json::json!({
                "name": "autopilot_turns",
                "description": "Run high-speed autonomous turn advancement loop until an event modal occurs.",
                "inputSchema": {
                    "type": "object",
                    "properties": { "turns": { "type": "integer", "default": 10 } }
                }
            }),
            serde_json::json!({
                "name": "corpus_info",
                "description": "Query game corpus: list hotkeys, registered screens, and available macros.",
                "inputSchema": { "type": "object", "properties": {} }
            }),
            serde_json::json!({
                "name": "run_macro",
                "description": "Execute a pre-registered reflex macro from game.toml (e.g. 'turn_pump', 'dismiss_tutorial', 'auto_scout_cycle').",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": { "type": "string" }
                    },
                    "required": ["name"]
                }
            }),
            serde_json::json!({
                "name": "corpus_search",
                "description": "Ultra-fast in-memory search (<100us) across all GalCiv IV technologies, planetary improvements, executive orders, strategy rules, and wiki guides.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": { "type": "string" },
                        "limit": { "type": "integer", "default": 5 }
                    },
                    "required": ["query"]
                }
            }),
            serde_json::json!({
                "name": "corpus_tech",
                "description": "Lookup research technology details: research cost, tree category, prerequisites, ship components, policies, and planetary unlocks.",
                "inputSchema": {
                    "type": "object",
                    "properties": { "name": { "type": "string" } },
                    "required": ["name"]
                }
            }),
            serde_json::json!({
                "name": "corpus_improvement",
                "description": "Lookup planetary improvement / district details: production cost, base effects, level bonuses, adjacency bonuses, and tech/civ requirements.",
                "inputSchema": {
                    "type": "object",
                    "properties": { "name": { "type": "string" } },
                    "required": ["name"]
                }
            }),
            serde_json::json!({
                "name": "corpus_order",
                "description": "Lookup executive order details: Control point cost, cooldown, civ/tech requirements, and immediate effects (e.g. 'Draft Colonists').",
                "inputSchema": {
                    "type": "object",
                    "properties": { "name": { "type": "string" } },
                    "required": ["name"]
                }
            }),
            serde_json::json!({
                "name": "corpus_strategy",
                "description": "Retrieve the strategic deliberation playbook for early/mid/late game meta, Core World vs Colony feeding, district placement synergies, and tech pathing.",
                "inputSchema": { "type": "object", "properties": {} }
            }),
            serde_json::json!({
                "name": "game_state",
                "description": "Query live Windows agent status: check if Galactic Civilizations is running, foregrounded, screen resolution, and current windows.",
                "inputSchema": { "type": "object", "properties": {} }
            }),
            serde_json::json!({
                "name": "focus",
                "description": "Bring target window to foreground by title substring (defaults to 'Galactic Civilizations').",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": { "type": "string", "default": "Galactic Civilizations" }
                    }
                }
            }),
        ]
    }

    async fn dispatch_tool(&self, name: &str, args: Value) -> Result<Value> {
        match name {
            "screenshot" => {
                let (jpeg, v) = self.capture_frame().await?;
                let b64 = base64::engine::general_purpose::STANDARD.encode(&jpeg);
                Ok(serde_json::json!({
                    "content": [
                        { "type": "text", "text": format!("Screenshot {}x{} (scale: {:.2})", v.width, v.height, v.scale) },
                        { "type": "image", "data": b64, "mimeType": "image/jpeg" }
                    ]
                }))
            }
            "click" => {
                let x = args.get("x").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let y = args.get("y").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let button = args.get("button").and_then(|v| v.as_str()).unwrap_or("left");
                let count = args.get("count").and_then(|v| v.as_i64()).unwrap_or(1) as i32;
                let wait_sec = args.get("wait").and_then(|v| v.as_f64()).unwrap_or(0.5);

                let (sx, sy) = self.to_screen_coords(x, y);
                self.client.click(sx, sy, button, count).await?;

                if wait_sec > 0.0 {
                    tokio::time::sleep(std::time::Duration::from_secs_f64(wait_sec)).await;
                }

                let (jpeg, _v) = self.capture_frame().await?;
                let b64 = base64::engine::general_purpose::STANDARD.encode(&jpeg);
                Ok(serde_json::json!({
                    "content": [
                        { "type": "text", "text": format!("Clicked {} at screen ({}, {})", button, sx, sy) },
                        { "type": "image", "data": b64, "mimeType": "image/jpeg" }
                    ]
                }))
            }
            "drag" => {
                let x1 = args.get("x1").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let y1 = args.get("y1").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let x2 = args.get("x2").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let y2 = args.get("y2").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let button = args.get("button").and_then(|v| v.as_str()).unwrap_or("left");
                let wait_sec = args.get("wait").and_then(|v| v.as_f64()).unwrap_or(0.5);

                let (sx1, sy1) = self.to_screen_coords(x1, y1);
                let (sx2, sy2) = self.to_screen_coords(x2, y2);
                self.client.drag(sx1, sy1, sx2, sy2, button).await?;

                if wait_sec > 0.0 {
                    tokio::time::sleep(std::time::Duration::from_secs_f64(wait_sec)).await;
                }

                let (jpeg, _v) = self.capture_frame().await?;
                let b64 = base64::engine::general_purpose::STANDARD.encode(&jpeg);
                Ok(serde_json::json!({
                    "content": [
                        { "type": "text", "text": format!("Dragged {} from ({}, {}) to ({}, {})", button, sx1, sy1, sx2, sy2) },
                        { "type": "image", "data": b64, "mimeType": "image/jpeg" }
                    ]
                }))
            }
            "key" => {
                let combo = args.get("combo").and_then(|v| v.as_str()).unwrap_or("");
                let repeat = args.get("repeat").and_then(|v| v.as_i64()).unwrap_or(1) as i32;

                let resolved = self.manifest.as_ref().map(|m| m.resolve_key(combo)).unwrap_or(combo);
                self.client.key(resolved, repeat).await?;
                tokio::time::sleep(std::time::Duration::from_millis(300)).await;

                let (jpeg, _) = self.capture_frame().await?;
                let b64 = base64::engine::general_purpose::STANDARD.encode(&jpeg);
                Ok(serde_json::json!({
                    "content": [
                        { "type": "text", "text": format!("Pressed {} (resolved: '{}') x{}", combo, resolved, repeat) },
                        { "type": "image", "data": b64, "mimeType": "image/jpeg" }
                    ]
                }))
            }
            "type_text" => {
                let text = args.get("text").and_then(|v| v.as_str()).unwrap_or("");
                self.client.type_text(text).await?;

                let (jpeg, _) = self.capture_frame().await?;
                let b64 = base64::engine::general_purpose::STANDARD.encode(&jpeg);
                Ok(serde_json::json!({
                    "content": [
                        { "type": "text", "text": format!("Typed {:?}", text) },
                        { "type": "image", "data": b64, "mimeType": "image/jpeg" }
                    ]
                }))
            }
            "batch" => {
                let actions = args.get("actions").and_then(|v| v.as_array()).cloned().unwrap_or_default();
                // Map coordinates and resolve keys
                let mut converted = Vec::new();
                for act in actions {
                    let mut item = act.clone();
                    let kind = item.get("action").and_then(|v| v.as_str()).unwrap_or("").to_string();
                    if kind == "key" {
                        if let Some(c) = item.get("combo").and_then(|v| v.as_str()).map(|s| s.to_string()) {
                            let resolved = self.manifest.as_ref().map(|m| m.resolve_key(&c).to_string()).unwrap_or(c);
                            item["combo"] = serde_json::json!(resolved);
                        }
                    }
                    if kind == "click" || kind == "move" {
                        if let (Some(x), Some(y)) = (item.get("x").and_then(|v| v.as_f64()), item.get("y").and_then(|v| v.as_f64())) {
                            let (sx, sy) = self.to_screen_coords(x, y);
                            item["x"] = serde_json::json!(sx);
                            item["y"] = serde_json::json!(sy);
                        }
                    }
                    converted.push(item);
                }

                let results = self.client.batch(converted).await?;
                tokio::time::sleep(std::time::Duration::from_millis(400)).await;
                let (jpeg, _) = self.capture_frame().await?;
                let b64 = base64::engine::general_purpose::STANDARD.encode(&jpeg);
                Ok(serde_json::json!({
                    "content": [
                        { "type": "text", "text": format!("Batch executed {} actions", results.len()) },
                        { "type": "image", "data": b64, "mimeType": "image/jpeg" }
                    ]
                }))
            }
            "wait_settle" => {
                let timeout = args.get("timeout").and_then(|v| v.as_f64()).unwrap_or(15.0);
                let threshold = args.get("threshold").and_then(|v| v.as_f64()).unwrap_or(0.02);

                let res = self.client.settle(Some(timeout), Some(threshold)).await?;
                let (jpeg, _) = self.capture_frame().await?;
                let b64 = base64::engine::general_purpose::STANDARD.encode(&jpeg);
                Ok(serde_json::json!({
                    "content": [
                        { "type": "text", "text": format!("Settle result: {}", res) },
                        { "type": "image", "data": b64, "mimeType": "image/jpeg" }
                    ]
                }))
            }
            "diff" => {
                let prev = self.last_frame.lock().unwrap().clone();
                let (curr, _) = self.capture_frame().await?;

                let bbox = prev.as_ref().and_then(|p| detect_change_bbox(p, &curr, 25, 8).ok().flatten());
                let final_jpeg = if let Some(rect) = bbox {
                    highlight_region(&curr, rect, [255, 0, 128], 3, 80).unwrap_or(curr)
                } else {
                    curr
                };

                let b64 = base64::engine::general_purpose::STANDARD.encode(&final_jpeg);
                let note = match bbox {
                    Some(b) => format!("Changed bbox: {:?}", b),
                    None => "No visual changes detected".to_string(),
                };

                Ok(serde_json::json!({
                    "content": [
                        { "type": "text", "text": note },
                        { "type": "image", "data": b64, "mimeType": "image/jpeg" }
                    ]
                }))
            }
            "autopilot_turns" => {
                let turns = args.get("turns").and_then(|v| v.as_i64()).unwrap_or(10) as u32;
                let mut ap = crate::autopilot::Autopilot::new(self.client.clone());
                if let Some(m) = &self.manifest {
                    ap = ap.with_manifest(m.clone());
                }

                let mut completed = 0;
                let mut event_outcome = None;

                for _ in 0..turns {
                    let outcome = ap.advance_single_turn().await?;
                    match outcome {
                        crate::autopilot::TurnOutcome::Advanced { .. } => completed += 1,
                        crate::autopilot::TurnOutcome::ModalEvent { .. } => {
                            event_outcome = Some(outcome);
                            break;
                        }
                    }
                }

                let (note, img_bytes) = if let Some(crate::autopilot::TurnOutcome::ModalEvent { turn, bbox, crop_bytes, full_bytes }) = event_outcome {
                    (
                        format!("Turn {}: Strategic modal event detected! Changed bbox: {:?}", turn, bbox),
                        if !crop_bytes.is_empty() { crop_bytes } else { full_bytes },
                    )
                } else {
                    let (curr, _) = self.capture_frame().await?;
                    (format!("Advanced {} turns autonomously", completed), curr)
                };

                let b64 = base64::engine::general_purpose::STANDARD.encode(&img_bytes);
                Ok(serde_json::json!({
                    "content": [
                        { "type": "text", "text": note },
                        { "type": "image", "data": b64, "mimeType": "image/jpeg" }
                    ]
                }))
            }
            "corpus_info" => {
                if let Some(m) = &self.manifest {
                    Ok(serde_json::json!({
                        "content": [{
                            "type": "text",
                            "text": serde_json::to_string_pretty(m)?
                        }]
                    }))
                } else {
                    Ok(serde_json::json!({
                        "content": [{ "type": "text", "text": "No game corpus manifest loaded." }]
                    }))
                }
            }
            "run_macro" => {
                let name = args.get("name").and_then(|v| v.as_str()).unwrap_or("");
                let macro_def = self.manifest.as_ref().and_then(|m| m.macros.get(name))
                    .ok_or_else(|| anyhow::anyhow!("Unknown macro: {:?}. Call corpus_info to list available macros.", name))?;

                let (tw, th) = {
                    let tw = self.client.last_target_width.load(Ordering::Relaxed);
                    let th = self.client.last_target_height.load(Ordering::Relaxed);
                    if tw > 0 && th > 0 {
                        (tw as f64, th as f64)
                    } else if let Some(m) = &self.manifest {
                        (m.metadata.downscaled_resolution[0] as f64, m.metadata.downscaled_resolution[1] as f64)
                    } else {
                        (1568.0, 882.0)
                    }
                };

                let mut converted = Vec::new();
                for a in &macro_def.actions {
                    match a {
                        crate::corpus::MacroAction::Key { key } => {
                            let resolved = self.manifest.as_ref().map(|m| m.resolve_key(key)).unwrap_or(key);
                            converted.push(serde_json::json!({"action": "key", "combo": resolved}));
                        }
                        crate::corpus::MacroAction::Wait { ms } => {
                            converted.push(serde_json::json!({"action": "wait", "seconds": *ms as f64 / 1000.0}));
                        }
                        crate::corpus::MacroAction::ClickNorm { x, y } => {
                            let (sx, sy) = self.to_screen_coords(*x * tw, *y * th);
                            converted.push(serde_json::json!({"action": "click", "x": sx, "y": sy, "button": "left", "count": 1}));
                        }
                    }
                }

                let results = self.client.batch(converted).await?;
                let _ = self.client.settle(Some(macro_def.settle_timeout), Some(macro_def.settle_threshold)).await;
                let (jpeg, _) = self.capture_frame().await?;
                let b64 = base64::engine::general_purpose::STANDARD.encode(&jpeg);
                Ok(serde_json::json!({
                    "content": [
                        { "type": "text", "text": format!("Executed macro '{}' ({} actions)", name, results.len()) },
                        { "type": "image", "data": b64, "mimeType": "image/jpeg" }
                    ]
                }))
            }
            "corpus_search" => {
                let query = args.get("query").and_then(|v| v.as_str()).unwrap_or("");
                let limit = args.get("limit").and_then(|v| v.as_i64()).unwrap_or(5) as usize;
                if let Some(c) = &self.corpus {
                    let results = c.search(query, limit);
                    Ok(serde_json::json!({
                        "content": [{
                            "type": "text",
                            "text": serde_json::to_string_pretty(&results)?
                        }]
                    }))
                } else {
                    Ok(serde_json::json!({
                        "content": [{ "type": "text", "text": "Game corpus is not loaded." }]
                    }))
                }
            }
            "corpus_tech" => {
                let name = args.get("name").and_then(|v| v.as_str()).unwrap_or("");
                if let Some(c) = &self.corpus {
                    if let Some(tech) = c.lookup_tech(name) {
                        Ok(serde_json::json!({
                            "content": [{
                                "type": "text",
                                "text": serde_json::to_string_pretty(tech)?
                            }]
                        }))
                    } else {
                        Ok(serde_json::json!({
                            "content": [{ "type": "text", "text": format!("Technology '{}' not found in corpus.", name) }]
                        }))
                    }
                } else {
                    Ok(serde_json::json!({
                        "content": [{ "type": "text", "text": "Game corpus is not loaded." }]
                    }))
                }
            }
            "corpus_improvement" => {
                let name = args.get("name").and_then(|v| v.as_str()).unwrap_or("");
                if let Some(c) = &self.corpus {
                    if let Some(imp) = c.lookup_improvement(name) {
                        Ok(serde_json::json!({
                            "content": [{
                                "type": "text",
                                "text": serde_json::to_string_pretty(imp)?
                            }]
                        }))
                    } else {
                        Ok(serde_json::json!({
                            "content": [{ "type": "text", "text": format!("Improvement '{}' not found in corpus.", name) }]
                        }))
                    }
                } else {
                    Ok(serde_json::json!({
                        "content": [{ "type": "text", "text": "Game corpus is not loaded." }]
                    }))
                }
            }
            "corpus_order" => {
                let name = args.get("name").and_then(|v| v.as_str()).unwrap_or("");
                if let Some(c) = &self.corpus {
                    if let Some(ord) = c.lookup_order(name) {
                        Ok(serde_json::json!({
                            "content": [{
                                "type": "text",
                                "text": serde_json::to_string_pretty(ord)?
                            }]
                        }))
                    } else {
                        Ok(serde_json::json!({
                            "content": [{ "type": "text", "text": format!("Executive order '{}' not found in corpus.", name) }]
                        }))
                    }
                } else {
                    Ok(serde_json::json!({
                        "content": [{ "type": "text", "text": "Game corpus is not loaded." }]
                    }))
                }
            }
            "corpus_strategy" => {
                if let Some(c) = &self.corpus {
                    Ok(serde_json::json!({
                        "content": [{
                            "type": "text",
                            "text": c.get_strategy().to_string()
                        }]
                    }))
                } else {
                    Ok(serde_json::json!({
                        "content": [{ "type": "text", "text": "No strategy playbook loaded." }]
                    }))
                }
            }
            "game_state" => {
                let st = self.client.state().await?;
                Ok(serde_json::json!({
                    "content": [{
                        "type": "text",
                        "text": serde_json::to_string_pretty(&st)?
                    }]
                }))
            }
            "focus" => {
                let title = args.get("title").and_then(|v| v.as_str()).unwrap_or("Galactic Civilizations IV:");
                let focused = self.client.focus(title).await?;
                let (jpeg, _) = self.capture_frame().await?;
                let b64 = base64::engine::general_purpose::STANDARD.encode(&jpeg);
                Ok(serde_json::json!({
                    "content": [
                        { "type": "text", "text": format!("Focused window: '{}'", focused) },
                        { "type": "image", "data": b64, "mimeType": "image/jpeg" }
                    ]
                }))
            }
            _ => anyhow::bail!("Unknown tool: {}", name),
        }
    }
}

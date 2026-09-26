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

    /// Map last-image coordinates to screen pixels; never guesses (see `map_point`).
    fn to_screen_coords(&self, x: f64, y: f64) -> Result<(i32, i32)> {
        map_point(*self.view.lock().unwrap(), x, y)
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
                    "tools": Self::list_tools(self.corpus.as_ref().map(|c| c.manifest.metadata.id.as_str()))
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

    /// Tools for the loaded game (`game` = corpus id); game-specific tools only for their game.
    fn list_tools(game: Option<&str>) -> Vec<Value> {
        let mut tools = vec![
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
                "description": "Drag from (x1, y1) to (x2, y2) in the last image coordinates. If a drop does not register, try a longer hold_ms/dwell_ms, more steps, or wiggle.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x1": { "type": "number" },
                        "y1": { "type": "number" },
                        "x2": { "type": "number" },
                        "y2": { "type": "number" },
                        "button": { "type": "string", "default": "left" },
                        "hold_ms": { "type": "integer", "default": 30, "minimum": 0, "maximum": 3000, "description": "Delay after button down before moving" },
                        "steps": { "type": "integer", "default": 12, "minimum": 2, "maximum": 120, "description": "Interpolated moves to the target" },
                        "step_ms": { "type": "integer", "default": 15, "minimum": 5, "maximum": 200, "description": "Delay between moves" },
                        "dwell_ms": { "type": "integer", "default": 30, "minimum": 0, "maximum": 3000, "description": "Delay at the target before release" },
                        "wiggle": { "type": "boolean", "default": false, "description": "Move +/-3 px around the target before release" },
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
                "description": "Keyword search over the game corpus (generated records such as techs/improvements/orders, the strategy playbook, and reference docs). Returns ids with one-line summaries only; call corpus_get with an id for the body.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": { "type": "string" },
                        "limit": { "type": "integer", "default": 5, "maximum": 50 }
                    },
                    "required": ["query"]
                }
            }),
            serde_json::json!({
                "name": "corpus_get",
                "description": "Fetch one corpus item by id from corpus_search: a compact record (e.g. tech:colonial_policies) or one prose chunk (e.g. doc:planetary_management#3, strategy#1).",
                "inputSchema": {
                    "type": "object",
                    "properties": { "id": { "type": "string" } },
                    "required": ["id"]
                }
            }),
            serde_json::json!({
                "name": "corpus_tech",
                "description": "Lookup a technology by name (exact, alias, or closest match) from the generated game data. Returns a compact record with its fields (cost, tree, prerequisites, unlocks).",
                "inputSchema": {
                    "type": "object",
                    "properties": { "name": { "type": "string" } },
                    "required": ["name"]
                }
            }),
            serde_json::json!({
                "name": "corpus_improvement",
                "description": "Lookup a planetary improvement / district by name (exact, alias, or closest match) from the generated game data.",
                "inputSchema": {
                    "type": "object",
                    "properties": { "name": { "type": "string" } },
                    "required": ["name"]
                }
            }),
            serde_json::json!({
                "name": "corpus_order",
                "description": "Lookup an executive order by name (exact, alias, or closest match) from the generated game data.",
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
        ];
        if game == Some("stellaris") {
            tools.push(serde_json::json!({
                "name": "stellaris_briefing",
                "description": "Briefing of the player's Stellaris empire from the newest monthly autosave on the PC: date, government, stockpile and monthly net per resource (deficits flagged), power, research in progress and options, policies, planets (pops, stability, housing, amenities, crime), wars. About 2 KB of text.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "json": { "type": "boolean", "description": "Full structured JSON instead of text" }
                    }
                }
            }));
            tools.push(serde_json::json!({
                "name": "stellaris_directive",
                "description": "Apply one governor directive (see corpus strategy § Governor directives and directives.toml): takes the empire back with `play`, sets the directive flag and its policies, hands it back to the native AI with `observe`, and confirms the change in game.log. Hold a directive about 12 in-game months unless something urgent happens. Refuses if Stellaris is not the foreground window.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": { "type": "string", "enum": ["expand", "consolidate_economy", "tech_rush", "prepare_war", "defend", "diplomacy_first"] }
                    },
                    "required": ["name"]
                }
            }));
            tools.push(serde_json::json!({
                "name": "stellaris_log",
                "description": "Last lines of the game's logs/game.log (script log effects carry the in-game date, e.g. directive confirmations and events).",
                "inputSchema": {
                    "type": "object",
                    "properties": { "lines": { "type": "integer", "default": 30 } }
                }
            }));
        }
        tools
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
                let x = require_f64(&args, "x")?;
                let y = require_f64(&args, "y")?;
                let button = args.get("button").and_then(|v| v.as_str()).unwrap_or("left");
                let count = args.get("count").and_then(|v| v.as_i64()).unwrap_or(1) as i32;
                let wait_sec = args.get("wait").and_then(|v| v.as_f64()).unwrap_or(0.5);

                let (sx, sy) = self.to_screen_coords(x, y)?;
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
                let x1 = require_f64(&args, "x1")?;
                let y1 = require_f64(&args, "y1")?;
                let x2 = require_f64(&args, "x2")?;
                let y2 = require_f64(&args, "y2")?;
                let button = args.get("button").and_then(|v| v.as_str()).unwrap_or("left");
                let wait_sec = args.get("wait").and_then(|v| v.as_f64()).unwrap_or(0.5);

                let (sx1, sy1) = self.to_screen_coords(x1, y1)?;
                let (sx2, sy2) = self.to_screen_coords(x2, y2)?;
                let opts = drag_options(&args);
                self.client.drag(sx1, sy1, sx2, sy2, button, &opts).await?;

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
                for (i, act) in actions.iter().enumerate() {
                    let mut item = act.clone();
                    let kind = item.get("action").and_then(|v| v.as_str()).unwrap_or("").to_string();
                    if kind == "key" {
                        if let Some(c) = item.get("combo").and_then(|v| v.as_str()).map(|s| s.to_string()) {
                            let resolved = self.manifest.as_ref().map(|m| m.resolve_key(&c).to_string()).unwrap_or(c);
                            item["combo"] = serde_json::json!(resolved);
                        }
                    }
                    if kind == "click" || kind == "move" {
                        let at = |e: anyhow::Error| anyhow::anyhow!("batch action #{}: {}", i, e);
                        let x = require_f64(&item, "x").map_err(at)?;
                        let y = require_f64(&item, "y").map_err(at)?;
                        let (sx, sy) = self.to_screen_coords(x, y).map_err(at)?;
                        item["x"] = serde_json::json!(sx);
                        item["y"] = serde_json::json!(sy);
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
                let mut unverified = 0;
                let mut stop_outcome = None;
                // Known screens dismissed on turns that then advanced (lets clients judge them).
                let mut dismissed_ok: Vec<String> = Vec::new();

                for _ in 0..turns.clamp(1, 200) {
                    let outcome = ap.advance_single_turn().await?;
                    match outcome {
                        crate::autopilot::TurnOutcome::Advanced { verified, dismissed, .. } => {
                            completed += 1;
                            dismissed_ok.extend(dismissed);
                            if !verified {
                                unverified += 1;
                            }
                        }
                        other => {
                            stop_outcome = Some(other);
                            break;
                        }
                    }
                }

                let (note, img_bytes) = match stop_outcome {
                    Some(crate::autopilot::TurnOutcome::ModalEvent { turn, bbox, full_bytes }) => (
                        // The full frame, not the crop: click coordinates refer to the full frame.
                        format!(
                            "Advanced {} turn(s), then stopped at turn {}: a dialog is up (HUD dimmed; changed bbox {:?}). Decide and act, then call autopilot_turns again.",
                            completed, turn, bbox
                        ),
                        full_bytes,
                    ),
                    Some(crate::autopilot::TurnOutcome::NotAdvanced { turn, reason, full_bytes }) => (
                        format!(
                            "Advanced {} turn(s), then stopped at turn {}: {}. Look at the screen, clear the blocker (idle unit, empty queue, popup), then retry.",
                            completed, turn, reason
                        ),
                        full_bytes,
                    ),
                    _ => {
                        let (curr, _) = self.capture_frame().await?;
                        let mut note = format!("Advanced {} turn(s); each verified by the date readout changing.", completed);
                        if unverified > 0 {
                            note = format!("Advanced {} turn(s), {} unverified (no turn_indicator_roi in the manifest).", completed, unverified);
                        }
                        (note, curr)
                    }
                };
                let note = if dismissed_ok.is_empty() {
                    note
                } else {
                    format!("{}\nDismissed on advanced turns: {}.", note, dismissed_ok.join(", "))
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
                let m = self.manifest.as_ref().ok_or_else(|| anyhow::anyhow!("No game corpus manifest loaded."))?;
                let mut text = format!("# {} ({}) v{}\n", m.metadata.name, m.metadata.id, m.metadata.version);
                if let Some(c) = &self.corpus {
                    let st = c.stats();
                    let records: Vec<String> = st.records.iter().map(|(k, n)| format!("{} {}", n, k)).collect();
                    text.push_str(&format!(
                        "Records: {}\nDocs: {} in {} chunks (search with corpus_search, fetch with corpus_get)\n",
                        if records.is_empty() { "none generated yet".to_string() } else { records.join(", ") },
                        st.docs, st.chunks
                    ));
                }
                let mut hotkeys: Vec<_> = m.hotkeys.iter().collect();
                hotkeys.sort();
                text.push_str("\nHotkeys:\n");
                for (k, v) in hotkeys {
                    text.push_str(&format!("- {} = {}\n", k, v));
                }
                let mut macros: Vec<_> = m.macros.iter().collect();
                macros.sort_by(|a, b| a.0.cmp(b.0));
                text.push_str("\nMacros (run_macro):\n");
                for (k, d) in macros {
                    text.push_str(&format!("- {}: {} ({} actions)\n", k, d.description, d.actions.len()));
                }
                let mut screens: Vec<_> = m.screens.keys().collect();
                screens.sort();
                text.push_str(&format!("\nScreens: {}\n", screens.iter().map(|s| s.as_str()).collect::<Vec<_>>().join(", ")));
                Ok(serde_json::json!({ "content": [{ "type": "text", "text": text }] }))
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
                            let (sx, sy) = self.to_screen_coords(*x * tw, *y * th)?;
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
                let limit = args.get("limit").and_then(|v| v.as_i64()).unwrap_or(5).max(1) as usize;
                let c = self.corpus.as_ref().ok_or_else(|| anyhow::anyhow!("Game corpus is not loaded."))?;
                let hits = c.search(query, limit);
                let text = if hits.is_empty() {
                    format!("No corpus hits for {:?}.", query)
                } else {
                    let lines: Vec<String> = hits
                        .iter()
                        .map(|h| format!("- `{}` [{}] {} — {}", h.id, h.kind, h.title, h.summary))
                        .collect();
                    format!("{}\n\nFetch a body with corpus_get(id).", lines.join("\n"))
                };
                Ok(serde_json::json!({ "content": [{ "type": "text", "text": text }] }))
            }
            "corpus_get" => {
                let id = args.get("id").and_then(|v| v.as_str()).unwrap_or("");
                let c = self.corpus.as_ref().ok_or_else(|| anyhow::anyhow!("Game corpus is not loaded."))?;
                let text = match c.get(id) {
                    Some(item) => item.render(),
                    None => format!("No corpus item with id {:?}. Ids come from corpus_search.", id),
                };
                Ok(serde_json::json!({ "content": [{ "type": "text", "text": text }] }))
            }
            "corpus_tech" | "corpus_improvement" | "corpus_order" => {
                let kind = &name["corpus_".len()..];
                let query = args.get("name").and_then(|v| v.as_str()).unwrap_or("");
                let c = self.corpus.as_ref().ok_or_else(|| anyhow::anyhow!("Game corpus is not loaded."))?;
                let text = match c.lookup(kind, query) {
                    Some(r) => r.render(),
                    None if c.count(kind) == 0 => format!(
                        "No {} records are loaded (data/{}.json has not been generated yet). Use corpus_search over the reference docs instead.",
                        kind, kind
                    ),
                    None => format!("No {} named {:?}. Try corpus_search({:?}).", kind, query, query),
                };
                Ok(serde_json::json!({ "content": [{ "type": "text", "text": text }] }))
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
            "stellaris_briefing" => {
                let (path, bytes) = crate::stellaris::fetch_latest_save(&self.client).await?;
                let b = crate::stellaris::brief_save(&bytes)?;
                let text = if args.get("json").and_then(|v| v.as_bool()).unwrap_or(false) {
                    serde_json::to_string_pretty(&b)?
                } else {
                    format!("{}(from {path})", b.to_text())
                };
                Ok(serde_json::json!({ "content": [{ "type": "text", "text": text }] }))
            }
            "stellaris_directive" => {
                let name = args.get("name").and_then(|v| v.as_str()).ok_or_else(|| anyhow::anyhow!("missing `name`"))?;
                let dir = self.corpus.as_ref().map(|c| c.dir.clone()).ok_or_else(|| anyhow::anyhow!("no corpus loaded"))?;
                let directives = crate::stellaris::Directives::load(&dir)?;
                let (_, bytes) = crate::stellaris::fetch_latest_save(&self.client).await?;
                let country = crate::stellaris::brief_save(&bytes)?.country;
                let lines = crate::stellaris::apply_directive(&self.client, &directives, name, country).await?;
                let text = format!(
                    "Directive {name} applied to country {country} and confirmed in game.log. Console lines:\n{}\nThe next monthly autosave will list governor_directive_{name} under Governor flags.",
                    lines.join("\n")
                );
                Ok(serde_json::json!({ "content": [{ "type": "text", "text": text }] }))
            }
            "stellaris_log" => {
                let n = args.get("lines").and_then(|v| v.as_u64()).unwrap_or(30).min(500) as usize;
                let (text, _) = crate::stellaris::read_log_since(&self.client, 0).await?;
                let all: Vec<&str> = text.lines().collect();
                let tail = all[all.len().saturating_sub(n)..].join("\n");
                Ok(serde_json::json!({ "content": [{ "type": "text", "text": tail }] }))
            }
            _ => anyhow::bail!("Unknown tool: {}", name),
        }
    }
}

/// Map a point given in last-image pixels to screen pixels.
///
/// Errors rather than guessing: without a prior screenshot there is no scale to apply,
/// and a point outside the image would land somewhere unrelated on screen.
pub(crate) fn map_point(view: Option<View>, x: f64, y: f64) -> Result<(i32, i32)> {
    let view = view.ok_or_else(|| {
        anyhow::anyhow!("No screenshot taken yet; call `screenshot` first so coordinates can be mapped")
    })?;
    view.to_screen(x, y)
}

/// Fetch a required numeric argument; a missing coordinate must not default to 0.
pub(crate) fn require_f64(args: &Value, key: &str) -> Result<f64> {
    args.get(key)
        .and_then(|v| v.as_f64())
        .ok_or_else(|| anyhow::anyhow!("Missing or non-numeric argument `{}`", key))
}

/// Reads the optional `/drag` timing knobs from MCP tool arguments. Negative or
/// non-numeric values are ignored so the agent's defaults apply.
fn drag_options(args: &Value) -> crate::client::DragOptions {
    let uint = |k: &str| args.get(k).and_then(|v| v.as_u64());
    crate::client::DragOptions {
        hold_ms: uint("hold_ms"),
        steps: uint("steps").map(|v| v.min(i32::MAX as u64) as i32),
        step_ms: uint("step_ms"),
        dwell_ms: uint("dwell_ms"),
        wiggle: args.get("wiggle").and_then(|v| v.as_bool()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn four_k_view() -> View {
        // 3840x2160 downscaled to 1568x882
        View::new(0, 0, 3840.0 / 1568.0, 1568, 882)
    }

    #[test]
    fn map_point_without_screenshot_is_an_error() {
        let err = map_point(None, 100.0, 100.0).unwrap_err().to_string();
        assert!(err.contains("No screenshot"), "{err}");
    }

    #[test]
    fn map_point_scales_into_screen_space() {
        assert_eq!(map_point(Some(four_k_view()), 784.0, 441.0).unwrap(), (1920, 1080));
        assert_eq!(map_point(Some(four_k_view()), 0.0, 0.0).unwrap(), (0, 0));
    }

    #[test]
    fn map_point_outside_image_is_an_error_not_a_raw_click() {
        for (x, y) in [(1568.0, 10.0), (10.0, 882.0), (-1.0, 10.0), (1600.0, 900.0)] {
            let err = map_point(Some(four_k_view()), x, y).unwrap_err().to_string();
            assert!(err.contains("outside"), "({x},{y}): {err}");
        }
    }

    #[test]
    fn require_f64_rejects_missing_and_non_numeric() {
        let args = serde_json::json!({"x": 5, "y": "7"});
        assert_eq!(require_f64(&args, "x").unwrap(), 5.0);
        assert!(require_f64(&args, "y").unwrap_err().to_string().contains("`y`"));
        assert!(require_f64(&args, "z").unwrap_err().to_string().contains("`z`"));
    }

    #[test]
    fn drag_tool_schema_exposes_timing_options() {
        let tools = McpServer::list_tools(None);
        let drag = tools.iter().find(|t| t["name"] == "drag").expect("drag tool");
        let props = &drag["inputSchema"]["properties"];
        for key in ["hold_ms", "steps", "step_ms", "dwell_ms"] {
            assert_eq!(props[key]["type"], "integer", "{key}");
        }
        assert_eq!(props["wiggle"]["type"], "boolean");
        let required = drag["inputSchema"]["required"].as_array().unwrap();
        assert_eq!(required.len(), 4, "timing options must stay optional");
    }

    #[test]
    fn stellaris_tools_only_for_the_stellaris_corpus() {
        let has = |g| McpServer::list_tools(g).iter().any(|t| t["name"] == "stellaris_briefing");
        assert!(has(Some("stellaris")));
        let names: Vec<String> = McpServer::list_tools(Some("stellaris")).iter().map(|t| t["name"].as_str().unwrap().to_string()).collect();
        assert!(names.contains(&"stellaris_directive".to_string()) && names.contains(&"stellaris_log".to_string()));
        // The tool's directive enum must match corpora/stellaris/directives.toml.
        let tools = McpServer::list_tools(Some("stellaris"));
        let tool = tools.iter().find(|t| t["name"] == "stellaris_directive").unwrap();
        let mut listed: Vec<String> =
            tool["inputSchema"]["properties"]["name"]["enum"].as_array().unwrap().iter().map(|v| v.as_str().unwrap().to_string()).collect();
        listed.sort();
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../corpora/stellaris");
        let defined: Vec<String> = crate::stellaris::Directives::load(&dir).unwrap().directive.into_keys().collect();
        assert_eq!(listed, defined);
        assert!(!has(Some("galciv4")));
        assert!(!has(None));
    }

    #[test]
    fn drag_options_read_from_args() {
        let none = drag_options(&serde_json::json!({"x1": 1}));
        assert_eq!(none, crate::client::DragOptions::default());
        let some = drag_options(&serde_json::json!({"hold_ms": 250, "steps": 40, "step_ms": 25, "dwell_ms": 300, "wiggle": true}));
        assert_eq!(
            some,
            crate::client::DragOptions { hold_ms: Some(250), steps: Some(40), step_ms: Some(25), dwell_ms: Some(300), wiggle: Some(true) }
        );
        assert_eq!(drag_options(&serde_json::json!({"hold_ms": -5})).hold_ms, None);
    }
}

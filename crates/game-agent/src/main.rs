#![allow(dead_code, unused_variables, unused_imports)]
mod backend;
mod files;
mod keys;

use axum::{
    extract::{Query, Request, State},
    http::{header, HeaderMap, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use clap::Parser;
use jpeg_encoder::{ColorType, Encoder};
use serde::Deserialize;
use std::{
    path::PathBuf,
    sync::Arc,
    time::{Duration, Instant},
};

const VERSION: &str = "1.2.0";
const DEFAULT_PORT: u16 = 8765;

#[derive(Parser, Debug)]
#[command(author, version = VERSION, about = "High-performance game agent")]
struct Args {
    #[arg(long, default_value = "0.0.0.0")]
    host: String,

    #[arg(long, default_value_t = DEFAULT_PORT)]
    port: u16,

    #[arg(long)]
    token: Option<String>,

    /// Read-only file roots (JSON). Default: roots.json next to the executable.
    #[arg(long)]
    roots: Option<PathBuf>,
}

#[derive(Clone)]
struct AppState {
    token: Arc<String>,
    roots: Arc<files::Roots>,
}

#[derive(Deserialize)]
struct ScreenshotParams {
    x: Option<i32>,
    y: Option<i32>,
    w: Option<i32>,
    h: Option<i32>,
    max_side: Option<i32>,
    quality: Option<u8>,
}

#[derive(Deserialize)]
struct MoveReq {
    x: i32,
    y: i32,
}

#[derive(Deserialize)]
struct ClickReq {
    x: i32,
    y: i32,
    button: Option<String>,
    count: Option<i32>,
}

#[derive(Deserialize)]
struct DragReq {
    x1: i32,
    y1: i32,
    x2: i32,
    y2: i32,
    button: Option<String>,
    /// Delay after button down before the first movement (drag-threshold timers).
    hold_ms: Option<u64>,
    /// Number of interpolated moves from start to target.
    steps: Option<i32>,
    /// Delay between interpolated moves.
    step_ms: Option<u64>,
    /// Delay at the target before button up.
    dwell_ms: Option<u64>,
    /// After reaching the target, move +/-3 px and back so drop targets see hover movement.
    wiggle: Option<bool>,
}

#[derive(Deserialize)]
struct ScrollReq {
    x: i32,
    y: i32,
    clicks: i32,
}

#[derive(Deserialize)]
struct KeyReq {
    combo: String,
    repeat: Option<i32>,
}

#[derive(Deserialize)]
struct TypeReq {
    text: String,
}

#[derive(Deserialize)]
struct FocusReq {
    title: String,
}

#[derive(Deserialize)]
struct BatchReq {
    actions: Vec<serde_json::Value>,
}

#[derive(Deserialize)]
struct SettleParams {
    timeout: Option<f64>,
    threshold: Option<f64>,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();

    #[cfg(windows)]
    {
        backend::win::init_dpi();
        backend::win::keep_awake();
    }

    let token = get_or_create_token(args.token)?;
    let roots_path = args.roots.clone().unwrap_or_else(|| {
        std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.join("roots.json")))
            .unwrap_or_else(|| PathBuf::from("roots.json"))
    });
    let roots = files::Roots::load(&roots_path);
    println!("file roots from {:?}: {:?}", roots_path, roots.roots.keys().collect::<Vec<_>>());
    let state = AppState {
        token: Arc::new(token.clone()),
        roots: Arc::new(roots),
    };

    let app = Router::new()
        .route("/health", get(health_handler))
        .route("/screenshot", get(screenshot_handler))
        .route("/windows", get(windows_handler))
        .route("/settle", get(settle_handler))
        .route("/move", post(move_handler))
        .route("/click", post(click_handler))
        .route("/drag", post(drag_handler))
        .route("/scroll", post(scroll_handler))
        .route("/key", post(key_handler))
        .route("/type", post(type_handler))
        .route("/focus", post(focus_handler))
        .route("/batch", post(batch_handler))
        .route("/files/roots", get(files_roots_handler))
        .route("/files/list", get(files_list_handler))
        .route("/files/read", get(files_read_handler))
        .route_layer(middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ))
        .with_state(state);

    let addr = format!("{}:{}", args.host, args.port);
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    println!("game-agent v{} listening on {}", VERSION, addr);

    axum::serve(listener, app).await?;
    Ok(())
}

fn get_or_create_token(cli_token: Option<String>) -> Result<String, Box<dyn std::error::Error>> {
    if let Some(tok) = cli_token {
        return Ok(tok.trim().to_string());
    }
    if let Ok(tok) = std::env::var("GAME_AGENT_TOKEN") {
        if !tok.trim().is_empty() {
            return Ok(tok.trim().to_string());
        }
    }

    let mut paths = Vec::new();
    if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
        paths.push(PathBuf::from(local_app_data).join("GameAgent").join("agent_token.txt"));
    }
    paths.push(PathBuf::from("agent_token.txt"));
    paths.push(PathBuf::from(".agent_token"));

    for p in &paths {
        if p.exists() {
            if let Ok(content) = std::fs::read_to_string(p) {
                let trimmed = content.trim();
                if !trimmed.is_empty() {
                    return Ok(trimmed.to_string());
                }
            }
        }
    }

    // Generate random 24-byte token if none found
    let token = generate_random_token();
    if let Some(target) = paths.first() {
        if let Some(parent) = target.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let _ = std::fs::write(target, &token);
        println!("Generated token in {:?}", target);
    }
    Ok(token)
}

fn generate_random_token() -> String {
    use std::time::SystemTime;
    let seed = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    format!("{:032x}", seed)
}

async fn auth_middleware(
    State(state): State<AppState>,
    req: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    let auth_header = req
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|val| val.to_str().ok());

    match auth_header {
        Some(val) if val.starts_with("Bearer ") => {
            let token = val[7..].trim();
            if token == state.token.as_str() {
                Ok(next.run(req).await)
            } else {
                Err(StatusCode::UNAUTHORIZED)
            }
        }
        _ => Err(StatusCode::UNAUTHORIZED),
    }
}

async fn health_handler() -> impl IntoResponse {
    #[cfg(windows)]
    {
        let (w, h) = backend::win::screen_size();
        let fg = backend::win::foreground_title();
        Json(serde_json::json!({
            "ok": true,
            "version": VERSION,
            "screen": [w, h],
            "foreground": fg,
        }))
    }
    #[cfg(not(windows))]
    {
        Json(serde_json::json!({
            "ok": true,
            "version": VERSION,
            "screen": [1920, 1080],
            "foreground": "Mock Desktop",
        }))
    }
}

async fn screenshot_handler(Query(params): Query<ScreenshotParams>) -> Result<Response, (StatusCode, Json<serde_json::Value>)> {
    #[cfg(windows)]
    {
        let (sw, sh) = backend::win::screen_size();
        let x = params.x.unwrap_or(0);
        let y = params.y.unwrap_or(0);
        let w = params.w.unwrap_or(sw - x);
        let h = params.h.unwrap_or(sh - y);

        if x < 0 || y < 0 || w <= 0 || h <= 0 || x + w > sw || y + h > sh {
            return Err((
                StatusCode::BAD_REQUEST,
                Json(serde_json::json!({"error": format!("Region outside screen: ({},{}) {}x{}", x, y, w, h)})),
            ));
        }

        let mut tw = w;
        let mut th = h;
        if let Some(max_side) = params.max_side {
            let max_dim = w.max(h);
            if max_dim > max_side {
                let factor = max_side as f64 / max_dim as f64;
                tw = (w as f64 * factor).round().max(1.0) as i32;
                th = (h as f64 * factor).round().max(1.0) as i32;
            }
        }

        let rgb = backend::win::capture_rgb(x, y, w, h, tw, th)
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({"error": e}))))?;

        let quality = params.quality.unwrap_or(75).clamp(10, 100);
        let mut jpeg_bytes = Vec::with_capacity((tw * th / 4) as usize);
        let encoder = Encoder::new(&mut jpeg_bytes, quality);
        encoder
            .encode(&rgb, tw as u16, th as u16, ColorType::Rgb)
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({"error": e.to_string()}))))?;

        let mut headers = HeaderMap::new();
        headers.insert(header::CONTENT_TYPE, "image/jpeg".parse().unwrap());
        headers.insert("X-Width", w.to_string().parse().unwrap());
        headers.insert("X-Height", h.to_string().parse().unwrap());
        headers.insert("X-Target-Width", tw.to_string().parse().unwrap());
        headers.insert("X-Target-Height", th.to_string().parse().unwrap());

        Ok((headers, jpeg_bytes).into_response())
    }
    #[cfg(not(windows))]
    {
        Err((
            StatusCode::NOT_IMPLEMENTED,
            Json(serde_json::json!({"error": "Capture requires Windows"})),
        ))
    }
}

async fn windows_handler() -> impl IntoResponse {
    #[cfg(windows)]
    {
        Json(serde_json::json!({
            "windows": backend::win::list_windows()
        }))
    }
    #[cfg(not(windows))]
    {
        Json(serde_json::json!({"windows": []}))
    }
}

async fn move_handler(Json(req): Json<MoveReq>) -> impl IntoResponse {
    #[cfg(windows)]
    backend::win::mouse_move(req.x, req.y);
    Json(serde_json::json!({"ok": true}))
}

async fn click_handler(Json(req): Json<ClickReq>) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    let button = req.button.as_deref().unwrap_or("left");
    let count = req.count.unwrap_or(1).clamp(1, 5);

    #[cfg(windows)]
    {
        backend::win::mouse_move(req.x, req.y);
        tokio::time::sleep(Duration::from_millis(30)).await;
        for _ in 0..count {
            backend::win::mouse_button(button, true)
                .map_err(|e| (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e}))))?;
            tokio::time::sleep(Duration::from_millis(30)).await;
            backend::win::mouse_button(button, false)
                .map_err(|e| (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e}))))?;
            tokio::time::sleep(Duration::from_millis(30)).await;
        }
    }
    Ok(Json(serde_json::json!({"ok": true})))
}

const DRAG_DEFAULT_HOLD_MS: u64 = 30;
const DRAG_DEFAULT_STEPS: i32 = 12;
const DRAG_DEFAULT_STEP_MS: u64 = 15;
const DRAG_DEFAULT_DWELL_MS: u64 = 30;
const DRAG_MAX_DELAY_MS: u64 = 3000;
const DRAG_WIGGLE_PX: i32 = 3;

/// Resolved `/drag` timing and path, with defaults applied and every value clamped.
#[derive(Debug, PartialEq)]
struct DragPlan {
    hold_ms: u64,
    steps: i32,
    step_ms: u64,
    dwell_ms: u64,
    wiggle: bool,
}

impl DragPlan {
    fn from_req(req: &DragReq) -> Self {
        Self {
            hold_ms: req.hold_ms.unwrap_or(DRAG_DEFAULT_HOLD_MS).min(DRAG_MAX_DELAY_MS),
            steps: req.steps.unwrap_or(DRAG_DEFAULT_STEPS).clamp(2, 120),
            step_ms: req.step_ms.unwrap_or(DRAG_DEFAULT_STEP_MS).clamp(5, 200),
            dwell_ms: req.dwell_ms.unwrap_or(DRAG_DEFAULT_DWELL_MS).min(DRAG_MAX_DELAY_MS),
            wiggle: req.wiggle.unwrap_or(false),
        }
    }

    /// Every cursor position after the button goes down, in order. The last point is
    /// always the target so the release happens exactly there.
    fn path(&self, x1: i32, y1: i32, x2: i32, y2: i32) -> Vec<(i32, i32)> {
        let mut pts: Vec<(i32, i32)> = (1..=self.steps)
            .map(|i| (x1 + ((x2 - x1) * i) / self.steps, y1 + ((y2 - y1) * i) / self.steps))
            .collect();
        if self.wiggle {
            let d = DRAG_WIGGLE_PX;
            pts.extend([(x2 + d, y2), (x2, y2 + d), (x2 - d, y2), (x2, y2 - d), (x2, y2)]);
        }
        pts
    }
}

async fn drag_handler(Json(req): Json<DragReq>) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    let button = req.button.as_deref().unwrap_or("left");
    if !matches!(button, "left" | "right" | "middle") {
        return Err((StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": format!("unknown button {:?}", button)}))));
    }
    let plan = DragPlan::from_req(&req);
    #[cfg(windows)]
    {
        backend::win::mouse_move(req.x1, req.y1);
        tokio::time::sleep(Duration::from_millis(30)).await;
        backend::win::mouse_button(button, true)
            .map_err(|e| (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e}))))?;
        tokio::time::sleep(Duration::from_millis(plan.hold_ms)).await;

        for (x, y) in plan.path(req.x1, req.y1, req.x2, req.y2) {
            backend::win::mouse_move(x, y);
            tokio::time::sleep(Duration::from_millis(plan.step_ms)).await;
        }
        tokio::time::sleep(Duration::from_millis(plan.dwell_ms)).await;
        backend::win::mouse_button(button, false)
            .map_err(|e| (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e}))))?;
    }
    Ok(Json(serde_json::json!({
        "ok": true,
        "hold_ms": plan.hold_ms,
        "steps": plan.steps,
        "step_ms": plan.step_ms,
        "dwell_ms": plan.dwell_ms,
        "wiggle": plan.wiggle,
    })))
}

async fn scroll_handler(Json(req): Json<ScrollReq>) -> impl IntoResponse {
    #[cfg(windows)]
    {
        backend::win::mouse_move(req.x, req.y);
        tokio::time::sleep(Duration::from_millis(20)).await;
        backend::win::mouse_scroll(req.clicks);
    }
    Json(serde_json::json!({"ok": true}))
}

async fn key_handler(Json(req): Json<KeyReq>) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    let vks = keys::parse_combo(&req.combo)
        .map_err(|e| (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e}))))?;
    let repeat = req.repeat.unwrap_or(1).clamp(1, 50);

    #[cfg(windows)]
    {
        for _ in 0..repeat {
            for &vk in &vks {
                backend::win::send_key(vk, true);
                tokio::time::sleep(Duration::from_millis(15)).await;
            }
            tokio::time::sleep(Duration::from_millis(30)).await;
            for &vk in vks.iter().rev() {
                backend::win::send_key(vk, false);
                tokio::time::sleep(Duration::from_millis(15)).await;
            }
            tokio::time::sleep(Duration::from_millis(30)).await;
        }
    }
    Ok(Json(serde_json::json!({"ok": true})))
}

async fn type_handler(Json(req): Json<TypeReq>) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    if req.text.chars().count() > MAX_TYPE_CHARS {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({"error": format!("text exceeds {} characters", MAX_TYPE_CHARS)})),
        ));
    }
    #[cfg(windows)]
    backend::win::type_text(&req.text);
    Ok(Json(serde_json::json!({"ok": true})))
}

async fn focus_handler(Json(req): Json<FocusReq>) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    #[cfg(windows)]
    {
        let focused = backend::win::focus_window(&req.title)
            .map_err(|e| (StatusCode::NOT_FOUND, Json(serde_json::json!({"error": e}))))?;
        Ok(Json(serde_json::json!({"ok": true, "focused": focused})))
    }
    #[cfg(not(windows))]
    {
        Ok(Json(serde_json::json!({"ok": true, "focused": req.title})))
    }
}

const MAX_BATCH_ACTIONS: usize = 100;
const MAX_CLICK_COUNT: i32 = 5;
const MAX_KEY_REPEAT: i32 = 50;
const MAX_TYPE_CHARS: usize = 1000;
const MAX_WAIT_SECS: f64 = 30.0;

/// One validated `/batch` step. Built by `parse_batch` before anything is sent to the
/// desktop, so a bad step rejects the whole batch instead of failing part-way through.
#[derive(Debug, PartialEq)]
enum BatchAction {
    Move { x: i32, y: i32 },
    Click { x: i32, y: i32, button: String, count: i32 },
    MouseDown { button: String },
    MouseUp { button: String },
    Key { vks: Vec<u16>, repeat: i32 },
    Type { text: String },
    Wait { seconds: f64 },
}

fn parse_batch(actions: &[serde_json::Value]) -> Result<Vec<BatchAction>, String> {
    if actions.len() > MAX_BATCH_ACTIONS {
        return Err(format!("Batch exceeds {} actions", MAX_BATCH_ACTIONS));
    }
    let coord = |act: &serde_json::Value, i: usize, key: &str| -> Result<i32, String> {
        act.get(key)
            .and_then(|v| v.as_i64())
            .map(|v| v as i32)
            .ok_or_else(|| format!("Action #{}: missing or non-integer `{}`", i, key))
    };
    let button = |act: &serde_json::Value, i: usize| -> Result<String, String> {
        let b = match act.get("button") {
            None | Some(serde_json::Value::Null) => "left",
            Some(v) => v.as_str().ok_or_else(|| format!("Action #{}: `button` must be a string", i))?,
        };
        if !matches!(b, "left" | "right" | "middle") {
            return Err(format!("Action #{}: unknown button {:?}", i, b));
        }
        Ok(b.to_string())
    };
    let mut out = Vec::with_capacity(actions.len());
    for (i, act) in actions.iter().enumerate() {
        let kind = act.get("action").and_then(|v| v.as_str()).unwrap_or("");
        let parsed = match kind {
            "move" => BatchAction::Move { x: coord(act, i, "x")?, y: coord(act, i, "y")? },
            "click" => {
                let button = button(act, i)?;
                BatchAction::Click {
                    x: coord(act, i, "x")?,
                    y: coord(act, i, "y")?,
                    button,
                    count: (act.get("count").and_then(|v| v.as_i64()).unwrap_or(1) as i32).clamp(1, MAX_CLICK_COUNT),
                }
            }
            "mouse_down" => BatchAction::MouseDown { button: button(act, i)? },
            "mouse_up" => BatchAction::MouseUp { button: button(act, i)? },
            "key" => {
                let combo = act.get("combo").and_then(|v| v.as_str()).unwrap_or("");
                let vks = keys::parse_combo(combo).map_err(|e| format!("Action #{}: {}", i, e))?;
                BatchAction::Key {
                    vks,
                    repeat: (act.get("repeat").and_then(|v| v.as_i64()).unwrap_or(1) as i32).clamp(1, MAX_KEY_REPEAT),
                }
            }
            "type" => {
                let text = act.get("text").and_then(|v| v.as_str()).unwrap_or("");
                if text.chars().count() > MAX_TYPE_CHARS {
                    return Err(format!("Action #{}: text exceeds {} characters", i, MAX_TYPE_CHARS));
                }
                BatchAction::Type { text: text.to_string() }
            }
            "wait" => BatchAction::Wait {
                seconds: act.get("seconds").and_then(|v| v.as_f64()).unwrap_or(0.5).clamp(0.0, MAX_WAIT_SECS),
            },
            _ => return Err(format!("Action #{}: unknown action {:?}", i, kind)),
        };
        out.push(parsed);
    }
    Ok(out)
}

async fn batch_handler(Json(req): Json<BatchReq>) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    let actions = parse_batch(&req.actions)
        .map_err(|e| (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e}))))?;

    let mut results = Vec::with_capacity(actions.len());
    for act in &actions {
        match act {
            BatchAction::Move { x, y } => {
                #[cfg(windows)]
                backend::win::mouse_move(*x, *y);
                results.push(serde_json::json!({"action": "move", "ok": true}));
            }
            BatchAction::Click { x, y, button, count } => {
                #[cfg(windows)]
                {
                    backend::win::mouse_move(*x, *y);
                    tokio::time::sleep(Duration::from_millis(20)).await;
                    for _ in 0..*count {
                        backend::win::mouse_button(button, true)
                            .map_err(|e| (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e, "results": results.clone()}))))?;
                        tokio::time::sleep(Duration::from_millis(20)).await;
                        backend::win::mouse_button(button, false)
                            .map_err(|e| (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e, "results": results.clone()}))))?;
                        tokio::time::sleep(Duration::from_millis(20)).await;
                    }
                }
                results.push(serde_json::json!({"action": "click", "ok": true}));
            }
            BatchAction::MouseDown { button } | BatchAction::MouseUp { button } => {
                let down = matches!(act, BatchAction::MouseDown { .. });
                #[cfg(windows)]
                backend::win::mouse_button(button, down)
                    .map_err(|e| (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e, "results": results.clone()}))))?;
                #[cfg(not(windows))]
                let _ = button;
                let name = if down { "mouse_down" } else { "mouse_up" };
                results.push(serde_json::json!({"action": name, "ok": true}));
            }
            BatchAction::Key { vks, repeat } => {
                #[cfg(windows)]
                {
                    for _ in 0..*repeat {
                        for &vk in vks {
                            backend::win::send_key(vk, true);
                        }
                        tokio::time::sleep(Duration::from_millis(20)).await;
                        for &vk in vks.iter().rev() {
                            backend::win::send_key(vk, false);
                        }
                        tokio::time::sleep(Duration::from_millis(20)).await;
                    }
                }
                results.push(serde_json::json!({"action": "key", "ok": true}));
            }
            BatchAction::Type { text } => {
                #[cfg(windows)]
                backend::win::type_text(text);
                results.push(serde_json::json!({"action": "type", "ok": true}));
            }
            BatchAction::Wait { seconds } => {
                tokio::time::sleep(Duration::from_secs_f64(*seconds)).await;
                results.push(serde_json::json!({"action": "wait", "ok": true, "seconds": seconds}));
            }
        }
    }

    Ok(Json(serde_json::json!({"ok": true, "results": results})))
}

#[derive(Deserialize)]
struct FileParams {
    root: String,
    #[serde(default)]
    path: String,
    offset: Option<u64>,
    max: Option<u64>,
}

fn file_error(e: String) -> (StatusCode, Json<serde_json::Value>) {
    let status = if e.contains("No such file") || e.contains("cannot find") || e.contains("unknown root") {
        StatusCode::NOT_FOUND
    } else {
        StatusCode::BAD_REQUEST
    };
    (status, Json(serde_json::json!({"error": e})))
}

async fn files_roots_handler(State(state): State<AppState>) -> impl IntoResponse {
    let roots: serde_json::Map<String, serde_json::Value> = state
        .roots
        .roots
        .iter()
        .map(|(k, v)| (k.clone(), serde_json::json!({"path": v, "exists": v.is_dir()})))
        .collect();
    Json(serde_json::json!({"roots": roots}))
}

async fn files_list_handler(
    State(state): State<AppState>,
    Query(p): Query<FileParams>,
) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    let entries = state.roots.list(&p.root, &p.path).map_err(file_error)?;
    Ok(Json(serde_json::json!({"root": p.root, "path": p.path, "entries": entries})))
}

async fn files_read_handler(
    State(state): State<AppState>,
    Query(p): Query<FileParams>,
) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    let offset = p.offset.unwrap_or(0);
    let (bytes, size) = state
        .roots
        .read(&p.root, &p.path, offset, p.max.unwrap_or(files::MAX_READ))
        .map_err(file_error)?;
    let mut headers = HeaderMap::new();
    headers.insert(header::CONTENT_TYPE, "application/octet-stream".parse().unwrap());
    headers.insert("X-File-Size", size.to_string().parse().unwrap());
    headers.insert("X-Offset", offset.min(size).to_string().parse().unwrap());
    Ok((headers, bytes))
}

/// Game-agnostic visual settle detection.
/// Polls low-res screen thumbnails (64x64) until pixel change between frames is near zero.
async fn settle_handler(Query(params): Query<SettleParams>) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    #[cfg(windows)]
    {
        let timeout_secs = params.timeout.unwrap_or(30.0).clamp(1.0, 120.0);
        let threshold = params.threshold.unwrap_or(0.02).clamp(0.001, 0.5);

        let (sw, sh) = backend::win::screen_size();
        let tw = 64;
        let th = 64;
        let start = Instant::now();

        let mut prev_thumb = backend::win::capture_rgb(0, 0, sw, sh, tw, th)
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({"error": e}))))?;

        let mut consecutive_stable = 0;

        while start.elapsed().as_secs_f64() < timeout_secs {
            tokio::time::sleep(Duration::from_millis(200)).await;
            let cur_thumb = backend::win::capture_rgb(0, 0, sw, sh, tw, th)
                .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({"error": e}))))?;

            // Compute mean normalized pixel difference
            let mut diff_sum = 0u64;
            for (p, c) in prev_thumb.iter().zip(cur_thumb.iter()) {
                diff_sum += (*p as i32 - *c as i32).unsigned_abs() as u64;
            }
            let avg_diff = (diff_sum as f64) / (prev_thumb.len() as f64 * 255.0);

            if avg_diff < threshold {
                consecutive_stable += 1;
                if consecutive_stable >= 2 {
                    return Ok(Json(serde_json::json!({
                        "settled": true,
                        "elapsed": start.elapsed().as_secs_f64(),
                        "diff": avg_diff,
                    })));
                }
            } else {
                consecutive_stable = 0;
            }

            prev_thumb = cur_thumb;
        }

        Ok(Json(serde_json::json!({
            "settled": false,
            "timeout": true,
            "elapsed": start.elapsed().as_secs_f64(),
        })))
    }
    #[cfg(not(windows))]
    {
        Ok(Json(serde_json::json!({"settled": true, "elapsed": 0.0})))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn batch_clamps_click_count_and_key_repeat() {
        let parsed = parse_batch(&[
            json!({"action": "click", "x": 10, "y": 20, "count": 1_000_000}),
            json!({"action": "key", "combo": "tab", "repeat": 1_000_000}),
            json!({"action": "key", "combo": "enter", "repeat": 0}),
        ])
        .unwrap();
        assert_eq!(parsed[0], BatchAction::Click { x: 10, y: 20, button: "left".into(), count: MAX_CLICK_COUNT });
        assert_eq!(parsed[1], BatchAction::Key { vks: vec![0x09], repeat: MAX_KEY_REPEAT });
        assert_eq!(parsed[2], BatchAction::Key { vks: vec![0x0D], repeat: 1 });
    }

    #[test]
    fn batch_rejects_bad_key_combo_with_its_index() {
        let err = parse_batch(&[json!({"action": "key", "combo": "tab"}), json!({"action": "key", "combo": "hyperkey"})])
            .unwrap_err();
        assert!(err.starts_with("Action #1:"), "{err}");
    }

    #[test]
    fn batch_rejects_missing_coordinates_instead_of_clicking_origin() {
        let err = parse_batch(&[json!({"action": "click", "y": 5})]).unwrap_err();
        assert!(err.contains("`x`"), "{err}");
        let err = parse_batch(&[json!({"action": "move", "x": 5})]).unwrap_err();
        assert!(err.contains("`y`"), "{err}");
    }

    #[test]
    fn batch_rejects_unknown_button_action_and_oversize_text() {
        assert!(parse_batch(&[json!({"action": "click", "x": 1, "y": 1, "button": "side"})]).is_err());
        assert!(parse_batch(&[json!({"action": "teleport"})]).is_err());
        let long = "a".repeat(MAX_TYPE_CHARS + 1);
        assert!(parse_batch(&[json!({"action": "type", "text": long})]).is_err());
        let ok = "a".repeat(MAX_TYPE_CHARS);
        assert!(parse_batch(&[json!({"action": "type", "text": ok})]).is_ok());
    }

    #[test]
    fn batch_rejects_more_than_max_actions() {
        let many: Vec<_> = (0..=MAX_BATCH_ACTIONS).map(|_| json!({"action": "wait", "seconds": 0})).collect();
        assert!(parse_batch(&many).unwrap_err().contains("exceeds"));
    }

    #[test]
    fn batch_wait_is_clamped_and_whole_batch_validates_before_execution() {
        let parsed = parse_batch(&[
            json!({"action": "wait", "seconds": 999.0}),
            json!({"action": "wait", "seconds": -1.0}),
        ])
        .unwrap();
        assert_eq!(parsed[0], BatchAction::Wait { seconds: MAX_WAIT_SECS });
        assert_eq!(parsed[1], BatchAction::Wait { seconds: 0.0 });
        // A bad step anywhere rejects the whole batch: nothing before it should run.
        let err = parse_batch(&[json!({"action": "key", "combo": "tab"}), json!({"action": "click"})]).unwrap_err();
        assert!(err.starts_with("Action #1:"), "{err}");
    }

    #[test]
    fn batch_mouse_down_and_up_validate_buttons() {
        let parsed = parse_batch(&[
            json!({"action": "move", "x": 1, "y": 2}),
            json!({"action": "mouse_down"}),
            json!({"action": "move", "x": 50, "y": 60}),
            json!({"action": "mouse_up", "button": "right"}),
        ])
        .unwrap();
        assert_eq!(parsed[1], BatchAction::MouseDown { button: "left".into() });
        assert_eq!(parsed[3], BatchAction::MouseUp { button: "right".into() });
        let err = parse_batch(&[json!({"action": "mouse_down", "button": "side"})]).unwrap_err();
        assert!(err.starts_with("Action #0:") && err.contains("button"), "{err}");
        let err = parse_batch(&[json!({"action": "wait"}), json!({"action": "mouse_up", "button": 3})]).unwrap_err();
        assert!(err.starts_with("Action #1:"), "{err}");
    }

    fn drag_req(extra: serde_json::Value) -> DragReq {
        let mut v = json!({"x1": 0, "y1": 0, "x2": 120, "y2": 60});
        v.as_object_mut().unwrap().extend(extra.as_object().unwrap().clone());
        serde_json::from_value(v).unwrap()
    }

    #[test]
    fn drag_defaults_match_previous_behaviour() {
        let plan = DragPlan::from_req(&drag_req(json!({})));
        assert_eq!(plan, DragPlan { hold_ms: 30, steps: 12, step_ms: 15, dwell_ms: 30, wiggle: false });
        let path = plan.path(0, 0, 120, 60);
        assert_eq!(path.len(), 12);
        assert_eq!(path[0], (10, 5));
        assert_eq!(*path.last().unwrap(), (120, 60));
    }

    #[test]
    fn drag_options_are_clamped() {
        let low = DragPlan::from_req(&drag_req(json!({"hold_ms": 0, "steps": -4, "step_ms": 0, "dwell_ms": 0})));
        assert_eq!(low, DragPlan { hold_ms: 0, steps: 2, step_ms: 5, dwell_ms: 0, wiggle: false });
        let high = DragPlan::from_req(&drag_req(
            json!({"hold_ms": 99_999, "steps": 10_000, "step_ms": 10_000, "dwell_ms": 99_999, "wiggle": true}),
        ));
        assert_eq!(high, DragPlan { hold_ms: 3000, steps: 120, step_ms: 200, dwell_ms: 3000, wiggle: true });
    }

    #[test]
    fn drag_wiggle_circles_target_and_ends_on_it() {
        let plan = DragPlan::from_req(&drag_req(json!({"steps": 2, "wiggle": true})));
        let path = plan.path(0, 0, 100, 100);
        assert_eq!(path, vec![(50, 50), (100, 100), (103, 100), (100, 103), (97, 100), (100, 97), (100, 100)]);
    }
}

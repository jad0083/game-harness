mod backend;
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

const VERSION: &str = "1.0.0";
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
}

#[derive(Clone)]
struct AppState {
    token: Arc<String>,
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
    backend::win::keep_awake();

    let token = get_or_create_token(args.token)?;
    let state = AppState {
        token: Arc::new(token.clone()),
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

async fn drag_handler(Json(req): Json<DragReq>) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    let button = req.button.as_deref().unwrap_or("left");
    #[cfg(windows)]
    {
        backend::win::mouse_move(req.x1, req.y1);
        tokio::time::sleep(Duration::from_millis(30)).await;
        backend::win::mouse_button(button, true)
            .map_err(|e| (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e}))))?;

        let steps = 12;
        for i in 1..=steps {
            let x = req.x1 + ((req.x2 - req.x1) * i) / steps;
            let y = req.y1 + ((req.y2 - req.y1) * i) / steps;
            backend::win::mouse_move(x, y);
            tokio::time::sleep(Duration::from_millis(15)).await;
        }
        tokio::time::sleep(Duration::from_millis(30)).await;
        backend::win::mouse_button(button, false)
            .map_err(|e| (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": e}))))?;
    }
    Ok(Json(serde_json::json!({"ok": true})))
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

async fn type_handler(Json(req): Json<TypeReq>) -> impl IntoResponse {
    #[cfg(windows)]
    backend::win::type_text(&req.text);
    Json(serde_json::json!({"ok": true}))
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

async fn batch_handler(Json(req): Json<BatchReq>) -> Result<impl IntoResponse, (StatusCode, Json<serde_json::Value>)> {
    if req.actions.len() > 100 {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({"error": "Batch exceeds 100 actions"})),
        ));
    }

    let mut results = Vec::new();
    for (i, act) in req.actions.iter().enumerate() {
        let kind = act.get("action").and_then(|v| v.as_str()).unwrap_or("");
        match kind {
            "move" => {
                let x = act.get("x").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
                let y = act.get("y").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
                #[cfg(windows)]
                backend::win::mouse_move(x, y);
                results.push(serde_json::json!({"action": "move", "ok": true}));
            }
            "click" => {
                let x = act.get("x").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
                let y = act.get("y").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
                let button = act.get("button").and_then(|v| v.as_str()).unwrap_or("left");
                let count = act.get("count").and_then(|v| v.as_i64()).unwrap_or(1) as i32;
                #[cfg(windows)]
                {
                    backend::win::mouse_move(x, y);
                    tokio::time::sleep(Duration::from_millis(20)).await;
                    for _ in 0..count {
                        let _ = backend::win::mouse_button(button, true);
                        tokio::time::sleep(Duration::from_millis(20)).await;
                        let _ = backend::win::mouse_button(button, false);
                        tokio::time::sleep(Duration::from_millis(20)).await;
                    }
                }
                results.push(serde_json::json!({"action": "click", "ok": true}));
            }
            "key" => {
                let combo = act.get("combo").and_then(|v| v.as_str()).unwrap_or("");
                let repeat = act.get("repeat").and_then(|v| v.as_i64()).unwrap_or(1) as i32;
                if let Ok(vks) = keys::parse_combo(combo) {
                    #[cfg(windows)]
                    {
                        for _ in 0..repeat {
                            for &vk in &vks {
                                backend::win::send_key(vk, true);
                            }
                            tokio::time::sleep(Duration::from_millis(20)).await;
                            for &vk in vks.iter().rev() {
                                backend::win::send_key(vk, false);
                            }
                            tokio::time::sleep(Duration::from_millis(20)).await;
                        }
                    }
                }
                results.push(serde_json::json!({"action": "key", "ok": true}));
            }
            "type" => {
                let text = act.get("text").and_then(|v| v.as_str()).unwrap_or("");
                #[cfg(windows)]
                backend::win::type_text(text);
                results.push(serde_json::json!({"action": "type", "ok": true}));
            }
            "wait" => {
                let sec = act.get("seconds").and_then(|v| v.as_f64()).unwrap_or(0.5);
                let dur = Duration::from_secs_f64(sec.clamp(0.0, 30.0));
                tokio::time::sleep(dur).await;
                results.push(serde_json::json!({"action": "wait", "ok": true, "seconds": sec}));
            }
            _ => {
                return Err((
                    StatusCode::BAD_REQUEST,
                    Json(serde_json::json!({"error": format!("Action #{}: unknown action {:?}", i, kind)})),
                ));
            }
        }
    }

    Ok(Json(serde_json::json!({"ok": true, "results": results})))
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

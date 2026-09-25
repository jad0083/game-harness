//! Reflex turn loop: send the turn macro, wait for the screen to settle, then decide what
//! happened by looking — a dimmed HUD means a dialog needs the model; an unchanged date
//! readout means the turn did not advance and something is blocking it.

use crate::client::AgentClient;
use crate::imaging::{
    crop_region, decode_rgb, detect_change_bbox, region_diff_max_strip, region_mean_luminance, roi_from_norm,
    template_diff, View, DEFAULT_MODAL_ROI, MAX_SIDE,
};
use anyhow::Result;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

/// Max-strip luminance difference (0..1) above which the turn indicator counts as changed.
/// Real frames: same date <= 0.003, one or two changed glyphs ~0.10.
pub const TURN_CHANGE_THRESHOLD: f64 = 0.03;
/// Strip width in frame pixels, about one glyph of the date readout at 1568x882.
pub const TURN_STRIP_W: u32 = 6;
const DEFAULT_MODAL_THRESHOLD: f64 = 22.0;

#[derive(Debug, Clone)]
pub enum TurnOutcome {
    /// The turn macro ran and the turn indicator changed (`verified`), or no indicator is
    /// configured so the advance could not be checked (`verified == false`).
    Advanced { turn: u32, elapsed_sec: f64, verified: bool, dismissed: Vec<String> },
    /// The HUD is dimmed: an event, report or choice dialog is up and needs the model.
    ModalEvent { turn: u32, bbox: Option<[u32; 4]>, crop_bytes: Vec<u8>, full_bytes: Vec<u8> },
    /// The macro ran but the turn indicator did not change: something on screen is
    /// blocking end-turn (idle unit prompt, empty queue, a non-dimming popup).
    NotAdvanced { turn: u32, reason: String, full_bytes: Vec<u8> },
}

/// How many known informational screens one turn may dismiss before giving up.
const MAX_DISMISSALS_PER_TURN: usize = 4;
/// Upper bound on waiting while a `busy` screen ("Starting New Month") is visible.
pub const BUSY_MAX_WAIT_SECS: f64 = 180.0;

/// Decode every `auto_dismiss` screen's template; screens whose template is missing or
/// unreadable are skipped (reported on stderr) so a bad file cannot stop the autopilot.
pub fn load_known_screens(
    manifest: &crate::corpus::GameManifest,
) -> Vec<(String, crate::corpus::ScreenDef, image::RgbImage)> {
    let mut names: Vec<&String> = manifest.screens.keys().collect();
    names.sort();
    load_screens_where(manifest, &names, |d| d.auto_dismiss && !d.busy)
}

/// Decode the templates of every `busy` screen (turn still processing).
pub fn load_busy_screens(
    manifest: &crate::corpus::GameManifest,
) -> Vec<(String, crate::corpus::ScreenDef, image::RgbImage)> {
    let mut names: Vec<&String> = manifest.screens.keys().collect();
    names.sort();
    load_screens_where(manifest, &names, |d| d.busy)
}

fn load_screens_where(
    manifest: &crate::corpus::GameManifest,
    names: &[&String],
    keep: impl Fn(&crate::corpus::ScreenDef) -> bool,
) -> Vec<(String, crate::corpus::ScreenDef, image::RgbImage)> {
    let base = manifest.base_dir.clone().unwrap_or_default();
    let mut out = Vec::new();
    for name in names {
        let def = &manifest.screens[*name];
        let Some(rel) = def.template.as_ref() else { continue };
        if !keep(def) {
            continue;
        }
        match image::open(base.join(rel)) {
            Ok(img) => out.push(((*name).clone(), def.clone(), img.to_rgb8())),
            Err(e) => eprintln!("warning: screen {name}: cannot load template {rel}: {e}"),
        }
    }
    out
}

/// Name of the first `auto_dismiss` screen in `screens` whose template matches `frame`.
pub fn match_known_screen<'a>(
    frame: &image::RgbImage,
    screens: &'a [(String, crate::corpus::ScreenDef, image::RgbImage)],
) -> Option<&'a (String, crate::corpus::ScreenDef, image::RgbImage)> {
    screens.iter().find(|(_, def, tpl)| {
        let Some(norm) = def.template_roi else { return false };
        let roi = roi_from_norm(frame.width(), frame.height(), norm);
        template_diff(frame, tpl, roi[0], roi[1]) <= def.template_threshold
    })
}

/// What the classifier looks at, resolved from the manifest for a given frame size.
#[derive(Debug, Clone, Copy)]
pub struct TurnCheck {
    pub modal_roi: [u32; 4],
    pub modal_threshold: f64,
    pub turn_roi: Option<[u32; 4]>,
    pub turn_threshold: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub enum TurnVerdict {
    Modal,
    Advanced { verified: bool, indicator_diff: Option<f64> },
    NotAdvanced { indicator_diff: f64 },
}

/// Pure decision: compare the frame before the macro with the settled frame after it.
pub fn classify_turn(before: &[u8], after: &[u8], check: &TurnCheck) -> Result<TurnVerdict> {
    let after_img = decode_rgb(after)?;
    if region_mean_luminance(&after_img, check.modal_roi) < check.modal_threshold {
        return Ok(TurnVerdict::Modal);
    }
    let Some(roi) = check.turn_roi else {
        return Ok(TurnVerdict::Advanced { verified: false, indicator_diff: None });
    };
    let before_img = decode_rgb(before)?;
    let diff = region_diff_max_strip(&before_img, &after_img, roi, TURN_STRIP_W);
    if diff >= check.turn_threshold {
        Ok(TurnVerdict::Advanced { verified: true, indicator_diff: Some(diff) })
    } else {
        Ok(TurnVerdict::NotAdvanced { indicator_diff: diff })
    }
}

pub struct Autopilot {
    client: Arc<AgentClient>,
    /// (name, definition, decoded template) for every `auto_dismiss` screen with a template.
    known_screens: Vec<(String, crate::corpus::ScreenDef, image::RgbImage)>,
    /// `busy` screens: while one matches, the game is still processing the turn.
    busy_screens: Vec<(String, crate::corpus::ScreenDef, image::RgbImage)>,
    view: Mutex<Option<View>>,
    last_frame: Mutex<Option<Vec<u8>>>,
    turn_counter: AtomicU32,
    manifest: Option<crate::corpus::GameManifest>,
}

impl Autopilot {
    pub fn new(client: Arc<AgentClient>) -> Self {
        let manifest = crate::corpus::GameManifest::find_default();
        let known_screens = manifest.as_ref().map(load_known_screens).unwrap_or_default();
        let busy_screens = manifest.as_ref().map(load_busy_screens).unwrap_or_default();
        Self {
            client,
            known_screens,
            busy_screens,
            view: Mutex::new(None),
            last_frame: Mutex::new(None),
            turn_counter: AtomicU32::new(1),
            manifest,
        }
    }

    pub fn with_corpus(self, corpus: Arc<crate::corpus::GameCorpus>) -> Self {
        self.with_manifest(corpus.manifest.clone())
    }

    pub fn with_manifest(mut self, manifest: crate::corpus::GameManifest) -> Self {
        self.known_screens = load_known_screens(&manifest);
        self.busy_screens = load_busy_screens(&manifest);
        self.manifest = Some(manifest);
        self
    }

    pub async fn screenshot_view(&self) -> Result<(Vec<u8>, View)> {
        let jpeg = self
            .client
            .screenshot(None, None, None, None, Some(MAX_SIDE as i32), Some(75))
            .await?;
        let orig_w = self.client.last_width.load(Ordering::Relaxed).max(1);
        let target_w = self.client.last_target_width.load(Ordering::Relaxed).max(1);
        let target_h = self.client.last_target_height.load(Ordering::Relaxed).max(1);
        let v = View::new(0, 0, orig_w as f64 / target_w as f64, target_w, target_h);
        *self.view.lock().unwrap() = Some(v);
        *self.last_frame.lock().unwrap() = Some(jpeg.clone());
        Ok((jpeg, v))
    }

    /// Resolve the manifest's screen signatures for a frame of `width` x `height`.
    pub fn turn_check(&self, width: u32, height: u32) -> TurnCheck {
        let screens = self.manifest.as_ref().map(|m| &m.screens);
        let modal = screens.and_then(|s| s.get("event_modal"));
        let modal_roi = modal
            .and_then(|s| s.luminance_roi)
            .map(|r| crate::imaging::clamp_roi(r, width, height))
            .unwrap_or(DEFAULT_MODAL_ROI);
        let modal_threshold = modal.and_then(|s| s.luminance_threshold).unwrap_or(DEFAULT_MODAL_THRESHOLD);
        let turn_roi = screens
            .and_then(|s| s.get("main_galaxy_map"))
            .and_then(|s| s.turn_indicator_roi)
            .map(|n| roi_from_norm(width, height, n));
        TurnCheck { modal_roi, modal_threshold, turn_roi, turn_threshold: TURN_CHANGE_THRESHOLD }
    }

    fn turn_actions(&self, view: &View) -> Vec<serde_json::Value> {
        let manifest = self.manifest.as_ref();
        if let Some(m) = manifest.and_then(|man| man.macros.get("turn_pump")) {
            let mut acts = Vec::new();
            for a in &m.actions {
                match a {
                    crate::corpus::MacroAction::Key { key } => {
                        let resolved = manifest.map(|man| man.resolve_key(key)).unwrap_or(key);
                        acts.push(serde_json::json!({"action": "key", "combo": resolved}));
                    }
                    crate::corpus::MacroAction::Wait { ms } => {
                        acts.push(serde_json::json!({"action": "wait", "seconds": *ms as f64 / 1000.0}));
                    }
                    crate::corpus::MacroAction::ClickNorm { x, y } => {
                        // Normalized -> image -> screen pixels; the agent expects screen pixels.
                        if let Ok((sx, sy)) = view.to_screen(x * view.width as f64, y * view.height as f64) {
                            acts.push(serde_json::json!({"action": "click", "x": sx, "y": sy, "button": "left", "count": 1}));
                        }
                    }
                }
            }
            acts
        } else {
            ["tab", "space", "tab", "f", "enter"]
                .iter()
                .flat_map(|k| {
                    [
                        serde_json::json!({"action": "key", "combo": k}),
                        serde_json::json!({"action": "wait", "seconds": 0.08}),
                    ]
                })
                .collect()
        }
    }

    pub async fn advance_single_turn(&self) -> Result<TurnOutcome> {
        let start = Instant::now();
        let turn = self.turn_counter.load(Ordering::SeqCst);
        let mut dismissed: Vec<String> = Vec::new();

        self.require_game_foreground().await?;

        // Two attempts: a known informational screen (e.g. a news bulletin) can open at the
        // start of a turn and swallow the end-turn key; it is dismissed and the turn retried.
        for attempt in 0..2 {
            // Look before acting: clear known informational screens, and never send keys into
            // an open dialog.
            let (mut before, mut view) = self.screenshot_view().await?;
            // Each screen at most once per attempt: some stay visible after their action
            // (a colony ship stays selected after Auto Colonize), which must not loop.
            let mut handled: Vec<String> = Vec::new();
            while dismissed.len() < MAX_DISMISSALS_PER_TURN {
                match self.dismiss_known_screen(&before, &view, &handled, attempt > 0).await? {
                    Some(name) => {
                        handled.push(name.clone());
                        dismissed.push(name);
                        (before, view) = self.screenshot_view().await?;
                    }
                    None => break,
                }
            }
            let check = self.turn_check(view.width, view.height);
            if let TurnVerdict::Modal = classify_turn(&before, &before, &check)? {
                return Ok(self.modal_outcome(turn, None, before));
            }

            self.client.batch(self.turn_actions(&view)).await?;

            let (timeout, threshold) = self
                .manifest
                .as_ref()
                .and_then(|m| m.macros.get("turn_pump"))
                .map(|m| (m.settle_timeout, m.settle_threshold))
                .unwrap_or((8.0, 0.02));
            // End-turn processing takes the game a few seconds and the map can look settled
            // before it finishes, so wait for the turn indicator to change (or a dialog), then
            // settle and classify a fresh frame: a dialog that opens once the new turn starts
            // must win over the date change that preceded it.
            self.wait_for_turn_signal(&before, &check, timeout).await?;
            let _ = self.client.settle(Some(timeout), Some(threshold)).await?;
            let (after, _) = self.screenshot_view().await?;
            match classify_turn(&before, &after, &check)? {
                TurnVerdict::Modal => return Ok(self.modal_outcome(turn, Some(&before), after)),
                TurnVerdict::Advanced { verified, .. } => {
                    self.turn_counter.fetch_add(1, Ordering::SeqCst);
                    return Ok(TurnOutcome::Advanced {
                        turn,
                        elapsed_sec: start.elapsed().as_secs_f64(),
                        verified,
                        dismissed,
                    });
                }
                TurnVerdict::NotAdvanced { .. }
                    if attempt == 0 && self.known_screen_name(&after, &dismissed, true)?.is_some() =>
                {
                    continue; // dismissed at the top of the next attempt
                }
                TurnVerdict::NotAdvanced { indicator_diff } => {
                    if match_known_screen(&decode_rgb(&after)?, &self.busy_screens).is_some() {
                        return Ok(TurnOutcome::NotAdvanced {
                            turn,
                            reason: format!(
                                "the game is still processing the turn ('Starting New Month' visible after {:.0} s); wait and retry",
                                start.elapsed().as_secs_f64()
                            ),
                            full_bytes: after,
                        });
                    }
                    let mut reason = format!(
                        "turn indicator unchanged after the turn macro (diff {:.3} < {:.2}); something on screen is blocking end-turn",
                        indicator_diff, check.turn_threshold
                    );
                    if !dismissed.is_empty() {
                        reason.push_str(&format!(" (already dismissed: {})", dismissed.join(", ")));
                    }
                    return Ok(TurnOutcome::NotAdvanced { turn, reason, full_bytes: after });
                }
            }
        }
        unreachable!("the second attempt always returns")
    }

    /// A known screen on `frame` that is not in `exclude`.
    fn known_screen_name(&self, frame: &[u8], exclude: &[String], blocked: bool) -> Result<Option<String>> {
        let img = decode_rgb(frame)?;
        Ok(self.unhandled_matches(&img, exclude, blocked).map(|(n, _, _)| n.clone()))
    }

    /// First known screen on `img`, skipping `exclude` and, unless `blocked`, the screens that
    /// may only be acted on after end-turn was blocked.
    fn unhandled_matches(
        &self,
        img: &image::RgbImage,
        exclude: &[String],
        blocked: bool,
    ) -> Option<&(String, crate::corpus::ScreenDef, image::RgbImage)> {
        let candidates: Vec<_> = self
            .known_screens
            .iter()
            .filter(|(n, d, _)| !exclude.contains(n) && (blocked || !d.only_when_blocked))
            .cloned()
            .collect();
        let name = match_known_screen(img, &candidates)?.0.clone();
        self.known_screens.iter().find(|(n, _, _)| *n == name)
    }

    /// If `frame` shows a known `auto_dismiss` screen not in `exclude`, dismiss it and return its name.
    async fn dismiss_known_screen(
        &self,
        frame: &[u8],
        view: &View,
        exclude: &[String],
        blocked: bool,
    ) -> Result<Option<String>> {
        let img = decode_rgb(frame)?;
        let Some((name, def, _)) = self.unhandled_matches(&img, exclude, blocked) else {
            return Ok(None);
        };
        if let Some([nx, ny]) = def.dismiss_click {
            let (sx, sy) = view.to_screen(nx * view.width as f64, ny * view.height as f64)?;
            self.client.click(sx, sy, "left", 1).await?;
        } else if let Some(key) = &def.dismiss_key {
            self.client.key(key, 1).await?;
        } else {
            return Ok(None); // matched but no way to dismiss: leave it for the model
        }
        tokio::time::sleep(std::time::Duration::from_millis(800)).await;
        Ok(Some(name.clone()))
    }

    /// Poll until the turn indicator differs from `before` or the HUD dims, up to `timeout`
    /// seconds. Returns whether a signal was seen before the deadline.
    async fn wait_for_turn_signal(&self, before: &[u8], check: &TurnCheck, timeout: f64) -> Result<bool> {
        let start = Instant::now();
        let step = std::time::Duration::from_secs_f64(timeout.max(1.0));
        let cap = start + std::time::Duration::from_secs_f64(BUSY_MAX_WAIT_SECS);
        let mut deadline = start + step;
        let before_img = decode_rgb(before)?;
        while Instant::now() < deadline {
            tokio::time::sleep(std::time::Duration::from_millis(300)).await;
            let (frame, _) = self.screenshot_view().await?;
            let img = decode_rgb(&frame)?;
            let dimmed = region_mean_luminance(&img, check.modal_roi) < check.modal_threshold;
            let changed = match check.turn_roi {
                Some(roi) => region_diff_max_strip(&before_img, &img, roi, TURN_STRIP_W) >= check.turn_threshold,
                None => true,
            };
            if dimmed || changed {
                return Ok(true);
            }
            // The game shows "Starting New Month" while AI turns run; those can take far longer
            // than the settle timeout, so keep extending the wait while it is visible.
            if match_known_screen(&img, &self.busy_screens).is_some() {
                deadline = (Instant::now() + step).min(cap);
            }
        }
        Ok(false)
    }

    /// The turn macro is blind keystrokes; refuse to send them anywhere but the game.
    async fn require_game_foreground(&self) -> Result<()> {
        let wanted = self
            .manifest
            .as_ref()
            .map(|m| m.metadata.process_title.clone())
            .unwrap_or_else(|| "Galactic Civilizations".to_string());
        let health = self.client.health().await?;
        let foreground = health.get("foreground").and_then(|v| v.as_str()).unwrap_or("");
        if foreground.to_lowercase().contains(&wanted.to_lowercase()) {
            Ok(())
        } else {
            anyhow::bail!(
                "refusing to send turn keys: foreground window is {:?}, not the game ({:?}). Call focus first.",
                foreground, wanted
            )
        }
    }

    fn modal_outcome(&self, turn: u32, before: Option<&[u8]>, after: Vec<u8>) -> TurnOutcome {
        let bbox = before.and_then(|p| detect_change_bbox(p, &after, 25, 8).ok().flatten());
        let crop = match bbox {
            Some([x, y, w, h]) => crop_region(&after, x, y, w, h, 85).unwrap_or_else(|_| after.clone()),
            None => after.clone(),
        };
        TurnOutcome::ModalEvent { turn, bbox, crop_bytes: crop, full_bytes: after }
    }

}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::imaging::encode_jpeg;
    use image::{Rgb, RgbImage};

    const W: u32 = 1568;
    const H: u32 = 882;

    fn frame(top_bar_gray: u8, date_pattern: u8) -> Vec<u8> {
        let mut img = RgbImage::from_pixel(W, H, Rgb([30, 30, 50]));
        for y in 0..40 {
            for x in 0..W {
                img.put_pixel(x, y, Rgb([top_bar_gray, top_bar_gray, top_bar_gray]));
            }
        }
        // "date text": a pattern of light pixels whose phase depends on the turn
        for y in 8..22 {
            for x in 1490..1560 {
                if (x + y + date_pattern as u32).is_multiple_of(3) {
                    img.put_pixel(x, y, Rgb([220, 220, 240]));
                }
            }
        }
        encode_jpeg(&img, 85).unwrap()
    }

    fn check() -> TurnCheck {
        TurnCheck {
            modal_roi: [0, 0, W, 40],
            modal_threshold: 22.0,
            turn_roi: Some(roi_from_norm(W, H, [0.948, 0.004, 0.05, 0.028])),
            turn_threshold: TURN_CHANGE_THRESHOLD,
        }
    }

    #[test]
    fn advanced_when_the_date_readout_changes() {
        let v = classify_turn(&frame(90, 0), &frame(90, 1), &check()).unwrap();
        assert!(matches!(v, TurnVerdict::Advanced { verified: true, indicator_diff: Some(d) } if d > 0.03), "{v:?}");
    }

    #[test]
    fn not_advanced_when_the_date_readout_is_unchanged() {
        let v = classify_turn(&frame(90, 0), &frame(90, 0), &check()).unwrap();
        assert!(matches!(v, TurnVerdict::NotAdvanced { indicator_diff } if indicator_diff < 0.01), "{v:?}");
    }

    #[test]
    fn modal_when_the_hud_is_dimmed_regardless_of_the_date() {
        let v = classify_turn(&frame(90, 0), &frame(8, 1), &check()).unwrap();
        assert_eq!(v, TurnVerdict::Modal);
    }

    #[test]
    fn manifest_known_screens_load_and_gnn_is_auto_dismissed() {
        let dir = format!("{}/../../corpora/galciv4", env!("CARGO_MANIFEST_DIR"));
        let m = crate::corpus::GameManifest::load_from_file(format!("{dir}/manifest.toml")).unwrap();
        let screens = load_known_screens(&m);
        let declared = m.screens.values().filter(|d| d.auto_dismiss && !d.busy && d.template.is_some()).count();
        assert_eq!(screens.len(), declared, "every auto_dismiss screen's template must load");
        let busy = load_busy_screens(&m);
        assert_eq!(busy.len(), m.screens.values().filter(|d| d.busy).count(), "every busy template must load");
        assert!(busy.iter().any(|(n, _, _)| n == "turn_processing"));
        assert!(!screens.iter().any(|(n, _, _)| n == "turn_processing"), "busy screens are never dismissed");
        for unit_screen in ["idle_colony_ship", "idle_survey_ship"] {
            let def = &m.screens[unit_screen];
            assert!(def.only_when_blocked, "{unit_screen} must only act after end-turn was blocked");
        }
        assert!(declared >= 3);
        let gnn = screens.iter().find(|(n, _, _)| n == "gnn_news").expect("gnn_news template loads");
        assert!(gnn.1.dismiss_click.is_some());
        // a flat frame matches nothing
        let blank = RgbImage::from_pixel(W, H, Rgb([30, 30, 50]));
        assert!(match_known_screen(&blank, &screens).is_none());
        // the template pasted at its roi matches
        let mut frame = blank.clone();
        let roi = roi_from_norm(W, H, gnn.1.template_roi.unwrap());
        image::imageops::replace(&mut frame, &gnn.2, roi[0] as i64, roi[1] as i64);
        assert_eq!(match_known_screen(&frame, &screens).map(|s| s.0.as_str()), Some("gnn_news"));
    }

    #[test]
    fn unverified_advance_without_a_turn_indicator() {
        let c = TurnCheck { turn_roi: None, ..check() };
        let v = classify_turn(&frame(90, 0), &frame(90, 0), &c).unwrap();
        assert_eq!(v, TurnVerdict::Advanced { verified: false, indicator_diff: None });
    }
}

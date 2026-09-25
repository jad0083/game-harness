//! Reflex turn loop: send the turn macro, wait for the screen to settle, then decide what
//! happened by looking — a dimmed HUD means a dialog needs the model; an unchanged date
//! readout means the turn did not advance and something is blocking it.

use crate::client::AgentClient;
use crate::imaging::{
    crop_region, decode_rgb, detect_change_bbox, region_diff_max_strip, region_mean_luminance, roi_from_norm,
    View, DEFAULT_MODAL_ROI, MAX_SIDE,
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
    Advanced { turn: u32, elapsed_sec: f64, verified: bool },
    /// The HUD is dimmed: an event, report or choice dialog is up and needs the model.
    ModalEvent { turn: u32, bbox: Option<[u32; 4]>, crop_bytes: Vec<u8>, full_bytes: Vec<u8> },
    /// The macro ran but the turn indicator did not change: something on screen is
    /// blocking end-turn (idle unit prompt, empty queue, a non-dimming popup).
    NotAdvanced { turn: u32, reason: String, full_bytes: Vec<u8> },
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
    view: Mutex<Option<View>>,
    last_frame: Mutex<Option<Vec<u8>>>,
    turn_counter: AtomicU32,
    manifest: Option<crate::corpus::GameManifest>,
}

impl Autopilot {
    pub fn new(client: Arc<AgentClient>) -> Self {
        let manifest = crate::corpus::GameManifest::find_default();
        Self {
            client,
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

        self.require_game_foreground().await?;

        // Look before acting: keys sent into an open dialog do unpredictable things.
        let (before, view) = self.screenshot_view().await?;
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
        // End-turn processing takes the game a few seconds and the map can look "settled"
        // before it finishes, so wait for the turn indicator itself to change (or a dialog to
        // appear) before letting the settle check and the classifier run.
        // The frame after settle is what gets classified: a dialog that opens once the new turn
        // starts must win over the date change that preceded it.
        self.wait_for_turn_signal(&before, &check, timeout).await?;
        let _ = self.client.settle(Some(timeout), Some(threshold)).await?;
        let (after, _) = self.screenshot_view().await?;
        match classify_turn(&before, &after, &check)? {
            TurnVerdict::Modal => Ok(self.modal_outcome(turn, Some(&before), after)),
            TurnVerdict::Advanced { verified, .. } => {
                self.turn_counter.fetch_add(1, Ordering::SeqCst);
                Ok(TurnOutcome::Advanced { turn, elapsed_sec: start.elapsed().as_secs_f64(), verified })
            }
            TurnVerdict::NotAdvanced { indicator_diff } => Ok(TurnOutcome::NotAdvanced {
                turn,
                reason: format!(
                    "turn indicator unchanged after the turn macro (diff {:.3} < {:.2}); something on screen is blocking end-turn",
                    indicator_diff, check.turn_threshold
                ),
                full_bytes: after,
            }),
        }
    }

    /// Poll until the turn indicator differs from `before` or the HUD dims, up to `timeout`
    /// seconds. Returns whether a signal was seen before the deadline.
    async fn wait_for_turn_signal(&self, before: &[u8], check: &TurnCheck, timeout: f64) -> Result<bool> {
        let deadline = Instant::now() + std::time::Duration::from_secs_f64(timeout.max(1.0));
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
    fn unverified_advance_without_a_turn_indicator() {
        let c = TurnCheck { turn_roi: None, ..check() };
        let v = classify_turn(&frame(90, 0), &frame(90, 0), &c).unwrap();
        assert_eq!(v, TurnVerdict::Advanced { verified: false, indicator_diff: None });
    }
}

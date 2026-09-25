#![allow(dead_code)]
use crate::client::AgentClient;
use crate::imaging::{detect_change_bbox, is_modal_dimmed, crop_region, View, MAX_SIDE};
use anyhow::Result;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

#[derive(Debug, Clone)]
pub enum TurnOutcome {
    Advanced {
        turn: u32,
        elapsed_sec: f64,
    },
    ModalEvent {
        turn: u32,
        bbox: Option<[u32; 4]>,
        crop_bytes: Vec<u8>,
        full_bytes: Vec<u8>,
    },
}

pub struct Autopilot {
    client: Arc<AgentClient>,
    view: Mutex<Option<View>>,
    last_frame: Mutex<Option<Vec<u8>>>,
    turn_counter: AtomicU32,
    corpus: Option<Arc<crate::corpus::GameCorpus>>,
    manifest: Option<crate::corpus::GameManifest>,
}

impl Autopilot {
    pub fn new(client: Arc<AgentClient>) -> Self {
        let corpus = crate::corpus::GameCorpus::find_default().map(Arc::new);
        let manifest = corpus.as_ref().map(|c| c.manifest.clone()).or_else(crate::corpus::GameManifest::find_default);
        Self {
            client,
            view: Mutex::new(None),
            last_frame: Mutex::new(None),
            turn_counter: AtomicU32::new(1),
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

    pub async fn screenshot_view(&self) -> Result<(Vec<u8>, View)> {
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

    pub async fn advance_single_turn(&self) -> Result<TurnOutcome> {
        let start = Instant::now();
        let turn = self.turn_counter.fetch_add(1, Ordering::SeqCst);

        // Build turn housekeeping actions from corpus macro if available
        let actions = if let Some(m) = self.manifest.as_ref().and_then(|man| man.macros.get("turn_pump")) {
            let mut acts = Vec::new();
            for a in &m.actions {
                match a {
                    crate::corpus::MacroAction::Key { key } => {
                        let resolved = self.manifest.as_ref().map(|man| man.resolve_key(key)).unwrap_or(key);
                        acts.push(serde_json::json!({"action": "key", "combo": resolved}));
                    }
                    crate::corpus::MacroAction::Wait { ms } => {
                        acts.push(serde_json::json!({"action": "wait", "seconds": *ms as f64 / 1000.0}));
                    }
                    crate::corpus::MacroAction::ClickNorm { x, y } => {
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
                        let cx = (*x * tw).round() as i32;
                        let cy = (*y * th).round() as i32;
                        acts.push(serde_json::json!({"action": "click", "x": cx, "y": cy, "button": "left", "count": 1}));
                    }
                }
            }
            acts
        } else {
            vec![
                serde_json::json!({"action": "key", "combo": "tab"}),
                serde_json::json!({"action": "wait", "seconds": 0.08}),
                serde_json::json!({"action": "key", "combo": "space"}),
                serde_json::json!({"action": "wait", "seconds": 0.08}),
                serde_json::json!({"action": "key", "combo": "tab"}),
                serde_json::json!({"action": "wait", "seconds": 0.08}),
                serde_json::json!({"action": "key", "combo": "f"}),
                serde_json::json!({"action": "wait", "seconds": 0.08}),
                serde_json::json!({"action": "key", "combo": "enter"}),
            ]
        };

        self.client.batch(actions).await?;

        // Wait dynamically for animations / AI calculations to settle
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        let _ = self.client.settle(Some(8.0), Some(0.02)).await?;

        let prev = self.last_frame.lock().unwrap().clone();
        let (curr, _) = self.screenshot_view().await?;

        // 80-microsecond state classification: check if an event modal or report dimmed the UI
        let threshold = self
            .manifest
            .as_ref()
            .and_then(|m| m.screens.get("event_modal"))
            .and_then(|s| s.luminance_threshold)
            .unwrap_or(22.0);
        let is_modal = is_modal_dimmed(&curr, threshold).unwrap_or(false);

        if is_modal {
            let bbox = prev.as_ref().and_then(|p| detect_change_bbox(p, &curr, 25, 8).ok().flatten());
            let crop = if let Some([x, y, w, h]) = bbox {
                crop_region(&curr, x, y, w, h, 85).unwrap_or_else(|_| curr.clone())
            } else {
                curr.clone()
            };

            return Ok(TurnOutcome::ModalEvent {
                turn,
                bbox,
                crop_bytes: crop,
                full_bytes: curr,
            });
        }

        Ok(TurnOutcome::Advanced {
            turn,
            elapsed_sec: start.elapsed().as_secs_f64(),
        })
    }

    pub async fn run_campaign<F>(&self, max_turns: u32, mut on_turn: F) -> Result<u32>
    where
        F: FnMut(&TurnOutcome),
    {
        let mut completed = 0;
        for _ in 0..max_turns {
            let outcome = self.advance_single_turn().await?;
            on_turn(&outcome);
            match outcome {
                TurnOutcome::Advanced { .. } => completed += 1,
                TurnOutcome::ModalEvent { .. } => {
                    // Halt for strategic deliberation
                    break;
                }
            }
        }
        Ok(completed)
    }
}

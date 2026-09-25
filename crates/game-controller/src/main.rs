mod autopilot;
mod client;
mod corpus;
mod imaging;
mod mcp;

use anyhow::Result;
use clap::{Parser, Subcommand};
use client::AgentClient;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;

#[derive(Parser)]
#[command(name = "game-controller")]
#[command(about = "Ultra-low-latency native Rust game controller, autopilot, and MCP server")]
struct Cli {
    #[arg(long)]
    agent_url: Option<String>,

    #[arg(long)]
    token: Option<String>,

    #[arg(long)]
    corpus: Option<PathBuf>,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Check connectivity and latency of Windows agent
    Health,

    /// Query live game state, foreground window, and screen dimensions
    State,

    /// Capture screenshot and save to disk
    Screenshot {
        #[arg(short, long, default_value = "current_screen.jpg")]
        out: PathBuf,
    },

    /// Click at coordinates in last-image space
    Click {
        x: f64,
        y: f64,
        #[arg(long, default_value = "left")]
        button: String,
        #[arg(long, default_value_t = 1)]
        count: i32,
    },

    /// Drag from (x1, y1) to (x2, y2) in last-image space
    Drag {
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        #[arg(long, default_value = "left")]
        button: String,
    },

    /// Send a key press or combo (e.g. enter, esc, tab, space, f)
    Key {
        combo: String,
        #[arg(long, default_value_t = 1)]
        repeat: i32,
    },

    /// Advance a single turn using fast reflex macro
    Turn,

    /// Run autonomous turn loop until an event/dialog or turn limit
    Autopilot {
        #[arg(long, default_value_t = 10)]
        turns: u32,
    },

    /// Wait dynamically for on-screen motion to settle
    Settle {
        #[arg(long, default_value_t = 15.0)]
        timeout: f64,
        #[arg(long, default_value_t = 0.02)]
        threshold: f64,
    },

    /// Diff current screen against previous capture
    Diff {
        #[arg(short, long, default_value = "current_screen.jpg")]
        out: PathBuf,
    },

    /// Bring the target window to foreground
    Focus {
        #[arg(default_value = "Galactic Civilizations IV:")]
        title: String,
    },

    /// Inspect and search loaded 3-tier game corpus
    Corpus {
        #[command(subcommand)]
        action: Option<CorpusAction>,
    },

    /// Run stdio Model Context Protocol (MCP) server for Claude / Gemini / Antigravity
    Mcp,
}

#[derive(Subcommand)]
enum CorpusAction {
    /// Full-text / keyword search across all techs, improvements, orders, and wiki guides
    Search {
        query: String,
        #[arg(short, long, default_value_t = 5)]
        limit: usize,
    },
    /// Lookup technology details from research tree
    Tech {
        name: String,
    },
    /// Lookup planetary improvement / district details
    Improvement {
        name: String,
    },
    /// Lookup executive order details
    Order {
        name: String,
    },
    /// Display strategic deliberation playbook
    Strategy,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    let client = Arc::new(AgentClient::new(cli.agent_url.as_deref(), cli.token.as_deref())?);

    let corpus = if let Some(p) = &cli.corpus {
        if p.is_dir() {
            Some(Arc::new(corpus::GameCorpus::load_from_dir(p)?))
        } else {
            None
        }
    } else {
        corpus::GameCorpus::find_default().map(Arc::new)
    };

    let manifest = corpus
        .as_ref()
        .map(|c| c.manifest.clone())
        .or_else(corpus::GameManifest::find_default);

    match cli.command {
        Commands::Health => {
            let start = Instant::now();
            let h = client.health().await?;
            let elapsed = start.elapsed().as_secs_f64() * 1000.0;
            println!("Agent Health (took {:.2}ms):", elapsed);
            println!("{}", serde_json::to_string_pretty(&h)?);
        }
        Commands::State => {
            let start = Instant::now();
            let s = client.state().await?;
            let elapsed = start.elapsed().as_secs_f64() * 1000.0;
            println!("Live Game State (took {:.2}ms):", elapsed);
            println!("{}", serde_json::to_string_pretty(&s)?);
        }
        Commands::Corpus { action } => {
            if let Some(c) = corpus {
                match action {
                    Some(CorpusAction::Search { query, limit }) => {
                        let start = Instant::now();
                        let results = c.search(&query, limit);
                        let elapsed_us = start.elapsed().as_micros();
                        println!("=== Corpus Search for {:?} (took {}µs, {} results) ===", query, elapsed_us, results.len());
                        for (i, r) in results.iter().enumerate() {
                            println!("\n[{}] [{}] {} (score: {})", i + 1, r.source, r.title, r.score);
                            println!("    {}", r.excerpt);
                        }
                    }
                    Some(CorpusAction::Tech { name }) => {
                        if let Some(t) = c.lookup_tech(&name) {
                            println!("=== Technology: {} ===", t.name);
                            if !t.category.is_empty() {
                                println!("Category:    {}", t.category);
                            }
                            println!("Cost:        {}", t.cost);
                            println!("Description: {}", t.description);
                            if !t.requirements.is_empty() {
                                println!("Requirements:\n  {}", t.requirements.join("\n  "));
                            }
                            if !t.effects.is_empty() {
                                println!("Effects:\n  {}", t.effects.join("\n  "));
                            }
                        } else {
                            println!("Technology {:?} not found in corpus.", name);
                        }
                    }
                    Some(CorpusAction::Improvement { name }) => {
                        if let Some(imp) = c.lookup_improvement(&name) {
                            println!("=== Improvement: {} ===", imp.name);
                            println!("Cost:        {}", imp.cost);
                            println!("Description: {}", imp.description);
                            if !imp.base_effects.is_empty() {
                                println!("Base Effects:\n  {}", imp.base_effects.join("\n  "));
                            }
                            if !imp.adjacencies.is_empty() {
                                println!("Adjacencies:\n  {}", imp.adjacencies.join("\n  "));
                            }
                            if !imp.requirements.is_empty() {
                                println!("Requirements:\n  {}", imp.requirements.join("\n  "));
                            }
                        } else {
                            println!("Improvement {:?} not found in corpus.", name);
                        }
                    }
                    Some(CorpusAction::Order { name }) => {
                        if let Some(ord) = c.lookup_order(&name) {
                            println!("=== Executive Order: {} ===", ord.name);
                            println!("Cost:        {}", ord.cost);
                            println!("Description: {}", ord.description);
                            if !ord.effects.is_empty() {
                                println!("Effects:\n  {}", ord.effects.join("\n  "));
                            }
                            if !ord.requirements.is_empty() {
                                println!("Requirements:\n  {}", ord.requirements.join("\n  "));
                            }
                        } else {
                            println!("Executive order {:?} not found in corpus.", name);
                        }
                    }
                    Some(CorpusAction::Strategy) => {
                        println!("{}", c.get_strategy());
                    }
                    None => {
                        println!("=== Game Corpus Loaded (GalCiv IV: Supernova) ===");
                        println!("Manifest:");
                        println!("  Hotkeys:      {} registered", c.manifest.hotkeys.len());
                        println!("  Screens:      {} registered", c.manifest.screens.len());
                        println!("  Macros:       {} registered", c.manifest.macros.len());
                        println!("Knowledge Base:");
                        println!("  Wiki Docs:    {} articles", c.wiki_articles.len());
                        println!("  Technologies: {} parsed techs in tree", c.techs.len());
                        println!("  Improvements: {} planetary districts/improvements", c.improvements.len());
                        println!("  Exec Orders:  {} executive orders", c.orders.len());
                        println!("  Strategy:     {} bytes of playbook", c.strategy.len());
                        println!("\nCLI Commands available:");
                        println!("  game-controller corpus search <query>");
                        println!("  game-controller corpus tech <name>");
                        println!("  game-controller corpus improvement <name>");
                        println!("  game-controller corpus order <name>");
                        println!("  game-controller corpus strategy");
                    }
                }
            } else {
                println!("No game corpus found. Ensure 'corpora/galciv4' exists or pass --corpus <path>");
            }
        }
        Commands::Screenshot { out } => {
            let start = Instant::now();
            let bytes = client
                .screenshot(None, None, None, None, Some(imaging::MAX_SIDE as i32), Some(75))
                .await?;
            let elapsed = start.elapsed().as_secs_f64() * 1000.0;
            tokio::fs::write(&out, &bytes).await?;
            println!(
                "Screenshot captured in {:.1}ms ({:.1} KB) -> {}",
                elapsed,
                bytes.len() as f64 / 1024.0,
                out.display()
            );
        }
        Commands::Click { x, y, button, count } => {
            let start = Instant::now();
            let _ = client.screenshot(None, None, None, None, Some(imaging::MAX_SIDE as i32), Some(75)).await?;
            let orig_w = client.last_width.load(std::sync::atomic::Ordering::Relaxed).max(1);
            let target_w = client.last_target_width.load(std::sync::atomic::Ordering::Relaxed).max(1);
            let scale = orig_w as f64 / target_w as f64;

            let sx = (x * scale).round() as i32;
            let sy = (y * scale).round() as i32;

            client.click(sx, sy, &button, count).await?;
            let elapsed = start.elapsed().as_secs_f64() * 1000.0;
            println!("Clicked {} x{} at screen ({}, {}) in {:.1}ms", button, count, sx, sy, elapsed);
        }
        Commands::Drag { x1, y1, x2, y2, button } => {
            let start = Instant::now();
            let _ = client.screenshot(None, None, None, None, Some(imaging::MAX_SIDE as i32), Some(75)).await?;
            let orig_w = client.last_width.load(std::sync::atomic::Ordering::Relaxed).max(1);
            let target_w = client.last_target_width.load(std::sync::atomic::Ordering::Relaxed).max(1);
            let scale = orig_w as f64 / target_w as f64;

            let sx1 = (x1 * scale).round() as i32;
            let sy1 = (y1 * scale).round() as i32;
            let sx2 = (x2 * scale).round() as i32;
            let sy2 = (y2 * scale).round() as i32;

            client.drag(sx1, sy1, sx2, sy2, &button).await?;
            let elapsed = start.elapsed().as_secs_f64() * 1000.0;
            println!("Dragged {} from ({}, {}) to ({}, {}) in {:.1}ms", button, sx1, sy1, sx2, sy2, elapsed);
        }
        Commands::Key { combo, repeat } => {
            let start = Instant::now();
            let resolved = if let Some(m) = &manifest {
                m.resolve_key(&combo)
            } else {
                &combo
            };
            client.key(resolved, repeat).await?;
            let elapsed = start.elapsed().as_secs_f64() * 1000.0;
            if resolved != combo.as_str() {
                println!("Sent key {} (resolved from '{}') x{} in {:.1}ms", resolved, combo, repeat, elapsed);
            } else {
                println!("Sent key {} x{} in {:.1}ms", combo, repeat, elapsed);
            }
        }
        Commands::Turn => {
            let mut ap = autopilot::Autopilot::new(client.clone());
            if let Some(c) = corpus {
                ap = ap.with_corpus(c);
            } else if let Some(m) = manifest {
                ap = ap.with_manifest(m);
            }
            let outcome = ap.advance_single_turn().await?;
            match outcome {
                autopilot::TurnOutcome::Advanced { turn, elapsed_sec } => {
                    println!("Turn {} completed in {:.2}s", turn, elapsed_sec);
                    let (curr, _) = ap.screenshot_view().await?;
                    let _ = tokio::fs::write("current_screen.jpg", &curr).await;
                }
                autopilot::TurnOutcome::ModalEvent { turn, bbox, full_bytes, .. } => {
                    println!("Turn {}: Strategic modal event detected! Changed bbox: {:?}", turn, bbox);
                    let _ = tokio::fs::write("modal_event.jpg", &full_bytes).await;
                    let _ = tokio::fs::write("current_screen.jpg", &full_bytes).await;
                }
            }
        }
        Commands::Autopilot { turns } => {
            println!("=== Starting Rust Autopilot for {} turns ===", turns);
            let start = Instant::now();
            let mut ap = autopilot::Autopilot::new(client.clone());
            if let Some(c) = corpus {
                ap = ap.with_corpus(c);
            } else if let Some(m) = manifest {
                ap = ap.with_manifest(m);
            }

            let mut completed = 0;
            for t in 1..=turns {
                let outcome = ap.advance_single_turn().await?;
                match outcome {
                    autopilot::TurnOutcome::Advanced { elapsed_sec, .. } => {
                        completed += 1;
                        println!("Turn {:02}: {:.2}s | OK", t, elapsed_sec);
                    }
                    autopilot::TurnOutcome::ModalEvent { turn, bbox, full_bytes, .. } => {
                        println!("Turn {:02}: Strategic modal event! BBox: {:?}", turn, bbox);
                        let _ = tokio::fs::write("modal_event.jpg", &full_bytes).await;
                        let _ = tokio::fs::write("current_screen.jpg", &full_bytes).await;
                        break;
                    }
                }
            }
            let (final_screen, _) = ap.screenshot_view().await?;
            let _ = tokio::fs::write("current_screen.jpg", &final_screen).await;
            let total = start.elapsed().as_secs_f64();
            println!(
                "=== Autopilot finished: {} turns in {:.2}s ({:.2}s/turn) ===",
                completed,
                total,
                if completed > 0 { total / completed as f64 } else { 0.0 }
            );
        }
        Commands::Settle { timeout, threshold } => {
            let start = Instant::now();
            let res = client.settle(Some(timeout), Some(threshold)).await?;
            let elapsed = start.elapsed().as_secs_f64() * 1000.0;
            println!("Settle resolved in {:.1}ms: {}", elapsed, res);
        }
        Commands::Diff { out } => {
            let bytes1 = client.screenshot(None, None, None, None, Some(imaging::MAX_SIDE as i32), Some(75)).await?;
            tokio::time::sleep(std::time::Duration::from_millis(150)).await;
            let bytes2 = client.screenshot(None, None, None, None, Some(imaging::MAX_SIDE as i32), Some(75)).await?;

            let bbox = imaging::detect_change_bbox(&bytes1, &bytes2, 25, 8)?;
            let final_jpeg = if let Some(rect) = bbox {
                println!("Detected change bbox: {:?}", rect);
                imaging::highlight_region(&bytes2, rect, [255, 0, 128], 3, 80)?
            } else {
                println!("No changes detected");
                bytes2
            };
            tokio::fs::write(&out, &final_jpeg).await?;
            println!("Saved diff image to {}", out.display());
        }
        Commands::Focus { title } => {
            let start = Instant::now();
            let focused = client.focus(&title).await?;
            let elapsed = start.elapsed().as_secs_f64() * 1000.0;
            println!("Focused {:?} in {:.1}ms", focused, elapsed);
        }
        Commands::Mcp => {
            let mut server = mcp::McpServer::new(client);
            if let Some(c) = corpus {
                server = server.with_corpus(c);
            } else if let Some(m) = manifest {
                server = server.with_manifest(m);
            }
            server.run_stdio().await?;
        }
    }

    Ok(())
}

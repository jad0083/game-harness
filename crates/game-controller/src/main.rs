mod autopilot;
mod client;
mod corpus;
mod imaging;
mod mcp;
mod stellaris;

use anyhow::{Context, Result};
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
        /// Delay after button down before moving (agent default 30, max 3000)
        #[arg(long)]
        hold_ms: Option<u64>,
        /// Interpolated moves to the target (agent default 12, clamped 2..120)
        #[arg(long)]
        steps: Option<i32>,
        /// Delay between moves (agent default 15, clamped 5..200)
        #[arg(long)]
        step_ms: Option<u64>,
        /// Delay at the target before release (agent default 30, max 3000)
        #[arg(long)]
        dwell_ms: Option<u64>,
        /// Move +/-3 px around the target before release
        #[arg(long)]
        wiggle: bool,
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

    /// Stellaris: read autosaves into a governor briefing
    Stellaris {
        #[command(subcommand)]
        action: StellarisAction,
    },

    /// Run stdio Model Context Protocol (MCP) server for Claude / Gemini / Antigravity
    Mcp,
}

#[derive(Subcommand)]
enum StellarisAction {
    /// Briefing of the player's empire from a .sav file, or from the newest autosave on the PC
    Brief {
        /// Local .sav file; omit to fetch the newest autosave through the agent
        file: Option<PathBuf>,
        /// Print JSON instead of text
        #[arg(long)]
        json: bool,
    },
    /// Apply a governor directive from directives.toml (play <country> → effects → observe)
    Directive {
        name: String,
        /// Player country id (default: read from the newest autosave)
        #[arg(long)]
        country: Option<u64>,
        /// Print the console lines without sending anything
        #[arg(long)]
        dry_run: bool,
    },
    /// Set the game speed: slowest, slow, normal, fast, fastest ("faster" = fastest)
    Speed { name: String },
    /// Last lines of the game's logs/game.log
    Log {
        #[arg(short, long, default_value_t = 30)]
        lines: usize,
    },
}

#[derive(Subcommand)]
enum CorpusAction {
    /// Keyword search over records and reference docs; returns ids + one-line summaries
    Search {
        query: String,
        #[arg(short, long, default_value_t = 5)]
        limit: usize,
    },
    /// Fetch one record or prose chunk by id (e.g. tech:colonial_policies, doc:anomalies#0)
    Get {
        id: String,
    },
    /// Lookup a technology by name (exact, alias, or closest match)
    Tech {
        name: String,
    },
    /// Lookup a planetary improvement / district by name
    Improvement {
        name: String,
    },
    /// Lookup an executive order by name
    Order {
        name: String,
    },
    /// Print the strategy playbook
    Strategy,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    // Corpus commands work offline: they never contact the agent, so they must not need its token.
    let offline = matches!(
        cli.command,
        Commands::Corpus { .. }
            | Commands::Stellaris { action: StellarisAction::Brief { file: Some(_), .. } }
            | Commands::Stellaris { action: StellarisAction::Directive { dry_run: true, .. } }
    );
    let token = cli.token.as_deref().or(if offline { Some("offline") } else { None });
    let client = Arc::new(AgentClient::new(cli.agent_url.as_deref(), token)?);

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
        Commands::Stellaris { action: StellarisAction::Brief { file, json } } => {
            let start = Instant::now();
            let (source, bytes) = match file {
                Some(f) => (f.display().to_string(), std::fs::read(&f).with_context(|| format!("reading {}", f.display()))?),
                None => stellaris::fetch_latest_save(&client).await?,
            };
            let fetched = start.elapsed();
            let b = stellaris::brief_save(&bytes)?;
            if json {
                println!("{}", serde_json::to_string_pretty(&b)?);
            } else {
                print!("{}", b.to_text());
                eprintln!("({source}: {} KB, fetch {:?}, parse {:?})", bytes.len() / 1024, fetched, start.elapsed() - fetched);
            }
        }
        Commands::Stellaris { action: StellarisAction::Directive { name, country, dry_run } } => {
            let dir = cli.corpus.clone().unwrap_or_else(|| PathBuf::from("corpora/stellaris"));
            let directives = stellaris::Directives::load(&dir)?;
            let country = match country {
                Some(c) => c,
                None if dry_run => 0,
                None => stellaris::brief_save(&stellaris::fetch_latest_save(&client).await?.1)?.country,
            };
            if dry_run {
                let lines = directives.console_lines(&name, country)?;
                println!("# {name}: {}", directives.directive[&name].description);
                for l in lines {
                    println!("{l}");
                }
            } else {
                let lines = stellaris::apply_directive(&client, &directives, &name, country).await?;
                println!("Applied directive {name} to country {country} (confirmed in game.log):");
                for l in lines {
                    println!("  {l}");
                }
            }
        }
        Commands::Stellaris { action: StellarisAction::Speed { name } } => {
            let set = stellaris::set_speed(&client, &name).await?;
            println!("Speed set to {set}");
        }
        Commands::Stellaris { action: StellarisAction::Log { lines } } => {
            let (text, _) = stellaris::read_log_since(&client, 0).await?;
            let all: Vec<&str> = text.lines().collect();
            for l in &all[all.len().saturating_sub(lines)..] {
                println!("{l}");
            }
        }
        Commands::Corpus { action } => {
            if let Some(c) = corpus {
                let lookup = |kind: &str, name: &str| match c.lookup(kind, name) {
                    Some(r) => println!("{}", r.render()),
                    None if c.count(kind) == 0 => println!(
                        "No {} records loaded: corpora/<game>/data/{}.json is missing. Run the extractor (see corpora/galciv4/data/README.md).",
                        kind, kind
                    ),
                    None => println!("No {} named {:?}. Try `corpus search {:?}`.", kind, name, name),
                };
                match action {
                    Some(CorpusAction::Search { query, limit }) => {
                        let start = Instant::now();
                        let hits = c.search(&query, limit);
                        let elapsed_us = start.elapsed().as_micros();
                        println!("=== Corpus search {:?}: {} hits ({}µs) ===", query, hits.len(), elapsed_us);
                        for h in &hits {
                            println!("{:<40} [{}] {} — {}", h.id, h.kind, h.title, h.summary);
                        }
                        if !hits.is_empty() {
                            println!("\nFetch one with: game-controller corpus get <id>");
                        }
                    }
                    Some(CorpusAction::Get { id }) => match c.get(&id) {
                        Some(item) => println!("{}", item.render()),
                        None => println!("No record or chunk with id {:?}.", id),
                    },
                    Some(CorpusAction::Tech { name }) => lookup("tech", &name),
                    Some(CorpusAction::Improvement { name }) => lookup("improvement", &name),
                    Some(CorpusAction::Order { name }) => lookup("order", &name),
                    Some(CorpusAction::Strategy) => println!("{}", c.get_strategy()),
                    None => {
                        let st = c.stats();
                        println!("=== Game corpus: {} ({}) ===", c.manifest.metadata.name, c.manifest.metadata.id);
                        println!("Manifest:  {} hotkeys, {} screens, {} macros",
                            c.manifest.hotkeys.len(), c.manifest.screens.len(), c.manifest.macros.len());
                        if st.records.is_empty() {
                            println!("Records:   none (data/*.json not generated yet — see corpora/galciv4/data/README.md)");
                        } else {
                            for (kind, n) in &st.records {
                                println!("Records:   {:<12} {}", kind, n);
                            }
                        }
                        println!("Docs:      {} reference docs in {} chunks", st.docs, st.chunks);
                        for d in c.docs().iter().filter(|d| d.stem != "strategy") {
                            println!("           {:<32} {:>3} chunks  {} — {}", d.stem, d.chunks, d.title, d.source.as_deref().unwrap_or("(no source)"));
                        }
                        println!("Strategy:  {} chars", st.strategy_chars);
                        println!("\nCommands: corpus search <query> | get <id> | tech <name> | improvement <name> | order <name> | strategy");
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
        Commands::Drag { x1, y1, x2, y2, button, hold_ms, steps, step_ms, dwell_ms, wiggle } => {
            let start = Instant::now();
            let _ = client.screenshot(None, None, None, None, Some(imaging::MAX_SIDE as i32), Some(75)).await?;
            let orig_w = client.last_width.load(std::sync::atomic::Ordering::Relaxed).max(1);
            let target_w = client.last_target_width.load(std::sync::atomic::Ordering::Relaxed).max(1);
            let scale = orig_w as f64 / target_w as f64;

            let sx1 = (x1 * scale).round() as i32;
            let sy1 = (y1 * scale).round() as i32;
            let sx2 = (x2 * scale).round() as i32;
            let sy2 = (y2 * scale).round() as i32;

            let opts = client::DragOptions { hold_ms, steps, step_ms, dwell_ms, wiggle: wiggle.then_some(true) };
            client.drag(sx1, sy1, sx2, sy2, &button, &opts).await?;
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
                autopilot::TurnOutcome::Advanced { turn, elapsed_sec, verified, dismissed } => {
                    println!(
                        "Turn {} advanced in {:.2}s ({}){}",
                        turn, elapsed_sec,
                        if verified { "date readout changed" } else { "unverified: no turn_indicator_roi in manifest" },
                        if dismissed.is_empty() { String::new() } else { format!("; dismissed {}", dismissed.join(", ")) }
                    );
                    let (curr, _) = ap.screenshot_view().await?;
                    let _ = tokio::fs::write("current_screen.jpg", &curr).await;
                }
                autopilot::TurnOutcome::ModalEvent { turn, bbox, full_bytes, .. } => {
                    println!("Turn {}: dialog detected (HUD dimmed); changed bbox: {:?}", turn, bbox);
                    let _ = tokio::fs::write("modal_event.jpg", &full_bytes).await;
                    let _ = tokio::fs::write("current_screen.jpg", &full_bytes).await;
                }
                autopilot::TurnOutcome::NotAdvanced { turn, reason, full_bytes } => {
                    println!("Turn {} did NOT advance: {}", turn, reason);
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
                    autopilot::TurnOutcome::Advanced { elapsed_sec, verified, dismissed, .. } => {
                        completed += 1;
                        println!(
                            "Turn {:02}: {:.2}s | {}{}",
                            t, elapsed_sec,
                            if verified { "advanced" } else { "unverified" },
                            if dismissed.is_empty() { String::new() } else { format!(" (dismissed {})", dismissed.join(", ")) }
                        );
                    }
                    autopilot::TurnOutcome::ModalEvent { turn, bbox, full_bytes, .. } => {
                        println!("Turn {:02}: dialog detected (HUD dimmed); bbox: {:?}", turn, bbox);
                        let _ = tokio::fs::write("modal_event.jpg", &full_bytes).await;
                        let _ = tokio::fs::write("current_screen.jpg", &full_bytes).await;
                        break;
                    }
                    autopilot::TurnOutcome::NotAdvanced { turn, reason, full_bytes } => {
                        println!("Turn {:02}: did NOT advance: {}", turn, reason);
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

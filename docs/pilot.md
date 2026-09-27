# Pilot app: an LLM that plays on its own

`src/pilot/` (`python -m pilot`) plays through the controller with any model provider: Galactic
Civilizations IV turn by turn from screenshots, Stellaris as a governor over the game's own AI.
Everything it does is recorded and shown on a dashboard where you can watch, ask and steer.

## Running

```bash
echo 'GEMINI_API_KEY=…' >> .env                  # or OPENAI_API_KEY / ANTHROPIC_API_KEY
.venv/bin/python -m pilot check --game stellaris  # agent, game, models, claude CLI
.venv/bin/python -m pilot run --game galciv4      # a vision episode per blocker
.venv/bin/python -m pilot run --game stellaris --months 12   # governor; --speed normal (default) … fastest
.venv/bin/python -m pilot view                    # dashboard over the recorded runs
```

As services: `deploy/game-pilot.service` (the pilot) and `deploy/game-pilot-view.service` (the
dashboard, always on), both systemd user units installed by `scripts/install-services.sh`. A drop-in
(`systemctl --user edit game-pilot.service`) sets `GAME_AGENT_URL` and `GAME_RESOLUTION` for the
PC in use.

| Variable | Meaning |
|---|---|
| `GAME_AGENT_URL`, `GAME_AGENT_TOKEN` | the Windows agent and its token (default token file `.agent_token`) |
| `GAME_RESOLUTION` | the PC's screen size when it is not 3840x2160, e.g. `2560x1440` (see [corpus.md](corpus.md)) |
| `PILOT_MODEL`, `PILOT_MODELS` | default model; extra models offered in the dashboard |
| `PILOT_GAME`, `PILOT_SPEED`, `PILOT_DECIDE_MONTHS`, `PILOT_POLL_S` | game, Stellaris speed, months between decisions, autosave poll |
| `PILOT_THINKING`, `PILOT_GOVERNOR_THINKING` | thinking level for GC4 episodes / Stellaris decisions (default `medium`) |
| `PILOT_RETRO_EVERY` | strategy review every N decisions (default 5) |
| `PILOT_PORT`, `PILOT_RUNS_DIR`, `PILOT_CAMPAIGN`, `PILOT_COMMIT`, `PILOT_JOURNAL` | live dashboard port, run folder, campaign id, commit learned knowledge, journal file |

## Models

Settings → Models sets a list of models per role: **Decisions**, **Strategy**, **Talk** and
**GC4 blockers** (a role without its own list uses the decision models). Each entry is a provider,
a model and a thinking level. The first model answers; on a failure the next one is tried, and a
model that just failed goes to the back for 10 minutes. With "take turns" each decision starts at
the next model. Every decision records the model release that answered (aliases resolve) and the
thinking level; the Decisions list shows it on each row.

| Provider | Needs | Notes |
|---|---|---|
| Google | `GOOGLE_API_KEY` / `GEMINI_API_KEY` | returns thought summaries (shown in the Reasoning tab) |
| Anthropic | `ANTHROPIC_API_KEY` | billed to the API organization's prepaid credit |
| OpenAI | `OPENAI_API_KEY` | |
| Claude Code (subscription) | the `claude` CLI, logged in | see below |

**Claude Code** runs the headless CLI (`claude -p`, found on PATH or in `~/.local/bin`) once per
request, so it is billed to the Claude subscription and its usage limits, never to an API
organization (the `ANTHROPIC_*` variables are removed from its environment). It offers the aliases
`claude-code:opus|sonnet|haiku|fable` (always the latest release) and, when `ANTHROPIC_API_KEY` is
set, every versioned id from the Anthropic model listing (listing needs no credit). Calls are
single-shot and text-only (no tools, no screenshots); the thinking level becomes `--effort`, and
the CLI does not return the thinking text. It suits the Strategy role, with a Google model after it
as the fallback.

## Stellaris governor

`src/pilot/governor.py`. The empire is played by the game's own AI (`human_ai`); the governor only
chooses one standing **directive** (`corpora/stellaris/directives.toml`: expand,
consolidate_economy, tech_rush, prepare_war, defend, diplomacy_first), applied from the console as
flags and policies that the Governor Bridge mod turns into AI budget weights.

The loop: pause → briefing from the newest autosave → the model returns a directive or `keep` →
apply → resume → poll autosaves until the decision interval has passed or something urgent
happens (a war starts or ends, a resource turns negative, we newly fall below half the median in a
measure, a milestone is missed) → pause → decide again. The game is paused whenever a model
thinks, so any speed is safe. `prepare_war` needs a human "yes" on the dashboard.

The briefing (about 2 KB) covers the empire, resources and deficits, power, research options,
planets and colonisable worlds, our species and its traits, identity (civics, traditions,
personality), wars with sides and exhaustion, and the nearest empires with strength ratios and
opinion both ways. The prompt adds a 12-month trend line and what earlier directive changes led to.

If the game stops answering pause and resume (for example a text box holds the keyboard), the
governor stops acting and flags *needs attention* until you press Resume.

## Strategy layer

`src/pilot/strategy.py`, `src/pilot/pillars.py`, `corpora/<game>/pillars.toml`.

A **Strategist** (the Strategy role; give it a strong reasoning model) keeps one strategy per
campaign. Each game's `pillars.toml` defines its pillars (Stellaris: economy, expansion,
technology, diplomacy, defence, government, society), the directive each one ranks, the actions it
may carry, the milestone metrics and the rules below; a missing or invalid file turns the layer
off with the reason on the Strategy tab.

Each pillar has:
- a **weight** (all pillars sum to 100; Stellaris: 5..50, the heaviest at least twice the lightest);
- a stance that cites figures from the briefing, and concrete goals;
- **milestones** `{metric, op, target, by}` (every pillar has one; the heaviest has a checkpoint and
  an end target), whose status (met, on track, at risk, missed) comes from telemetry;
- actions: preferred techs (technology) and one small monthly market order (economy; only an idle
  resource, at most 25 and 20% of its income).

**Pressure drives decisions.** Before each decision the governor computes every pillar's pressure
= weight × milestone need (met 0.3, on track 1, at risk 1.5, missed 2; a pillar without milestones
1) and shows the directives by pressure with a suggestion: the top one, or keep while the current
directive's pressure is within the switch margin (1.25) of the top. The model may choose
otherwise when the briefing gives a reason, says why, and names the milestone its choice
`serves`. A choice outside the top two is tagged off-frame and asks for a review. Games with many
levers at once (GalCiv IV, Civ VI) can use `mode = "share"`, which shows each pillar's share of
effort instead.

**Reviews** run at the start of a campaign without a strategy, every `PILOT_RETRO_EVERY`
decisions, on big events (war, crisis, colony lost, boxed in, military fell by half, a milestone
missed, an off-frame decision; at most one per 12 in-game months) and on *Review strategy now*. An
answer is validated; an invalid one gets one corrective retry with its errors and the rejected
answer, then the strategy stays. Reviews started at the beginning of a run or by you must name the
species traits the strategy builds on. A review may add up to 3 rules to
`corpora/stellaris/learned/strategy.md`, read by later decisions.

**Actions** are carried out through the game's screens after a decision, at most once per
autosave, and checked in a later save: `stellaris_pick_tech` (only in a research field under 10%
done) and `stellaris_market_sync` (monthly trades follow the strategy; hand-placed trades are
removed once a strategy exists).

**Your edits.** *Edit* on a pillar changes it and pins it (a review never changes a pinned pillar);
changing its weight rescales the other unpinned pillars so the total stays 100. *Unpin* hands it
back.

## Dashboard

`python -m pilot view` (port 8780) shows every recorded campaign and forwards the live controls of a
running pilot (whose own dashboard is on `PILOT_PORT`, 8790). It refreshes itself: status every
3 s, the live event stream during a run, campaign data every 10 s otherwise.

- **Readout**: in-game date, directive in force, standing, what the governor is doing, and the pace
  (speed and months between decisions, both changeable).
- **Empire over time**: standing against the other empires, net income, stockpiles and power over
  in-game months, with the directive in force, war periods and a mark per decision.
- **Decisions**: date, directive, trigger, model, the reason, and what changed 12 months later.
- **Reasoning**: a decision's full trace: what the model was shown, its thinking where the provider
  returns it, tool calls, the answer, what it works toward, tokens and time.
- **Talk** (live): ask the model about its reasoning, leave a note for the next decision, decide
  now, standing orders, override a directive, answer confirmations.
- **Strategy**: focus, directives by pressure, one card per pillar (weight × need = pressure, share
  of all pressure, stance, goals, milestones with status, actions), Edit / Unpin, *Review strategy
  now*, and the version history.
- **Settings**: models per role; with no run active, *Start run* starts `game-pilot.service`.

The dashboard has no login: keep it on a trusted network (see the security notes in the README).

## Telemetry

`runs/telemetry.sqlite` (local, gitignored) holds every event, decision with its full trace, and
monthly metric point, grouped by **campaign** (the Stellaris save folder or the GC4 journal
directory; `PILOT_CAMPAIGN` overrides). Each decision is scored against the empire 12 in-game
months later. The JSONL logs in `runs/<id>/` are the raw record; `python -m pilot
rebuild-telemetry` recreates the database. Curated knowledge (`learned/`, strategy, journals) is
committed.

## Galactic Civilizations IV episodes

`python -m pilot run --game galciv4` runs the controller's autopilot and, at each turn it cannot
end by itself, gives the model the screenshot and the controller tools for one episode. Decisions
follow `corpora/galciv4/strategy.md`; see [AGENTS.md](../AGENTS.md) for the decision procedure.

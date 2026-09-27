# Pilot app: an LLM that plays on its own

`src/pilot/` (`python -m pilot`) plays through the controller with any model provider: Galactic
Civilizations IV turn by turn from screenshots, Stellaris and Civilization VI as a governor over the
game's own AI.
Everything it does is recorded and shown on a dashboard where you can watch, ask and steer.

## Running

```bash
echo 'GEMINI_API_KEY=…' >> .env                  # or OPENAI_API_KEY / ANTHROPIC_API_KEY
.venv/bin/python -m pilot check --game stellaris  # agent, game, models, claude CLI
.venv/bin/python -m pilot run --game galciv4      # a vision episode per blocker
.venv/bin/python -m pilot run --game stellaris --months 12   # governor; --speed normal (default) … fastest
.venv/bin/python -m pilot view                    # dashboard over the recorded runs
.venv/bin/python -m pilot dashboard-link          # the dashboard link with its access key
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
| `PILOT_DECIDE_TURNS` | Civilization VI: turns the game's AI plays between decisions (default 5; `--decide-turns`) |
| `PILOT_AUTOPLAY_CHUNK` | Civilization VI: turns per autoplay call in peace (default 3, which keeps the AI's multi-turn plans); at war with a major or with a city in danger it plays one turn at a time |
| `PILOT_LAST_STAND`, `PILOT_LAST_STAND_MAX` | Civilization VI: scripted actions for a city about to fall (default `0`, off until the live checklist L6 passes); at most this many stands in a row per city (default 3) |
| `PILOT_THINKING`, `PILOT_GOVERNOR_THINKING` | thinking level for GC4 episodes / Stellaris decisions (default `medium`) |
| `PILOT_RETRO_EVERY` | strategy review every N decisions (default 5) |
| `PILOT_PORT`, `PILOT_RUNS_DIR`, `PILOT_CAMPAIGN`, `PILOT_COMMIT`, `PILOT_JOURNAL` | live dashboard port, run folder, campaign id, commit learned knowledge, journal file |
| `PILOT_DASHBOARD_KEY` | the dashboard's access key (default: generated once into `runs/dashboard.key`) |

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

## Civilization VI governor

`src/pilot/civ6_governor.py`, `src/pilot/civ6.py`; spec `docs/design/2026-09-26-civ6-governor-design.md`.
The game's own AI plays our civilization through `AutoplayManager` (units, tiles, city management,
district and wonder placement, diplomacy); the model gives macro orders between stretches of
autoplay. No screenshots: everything goes through the controller's `civ6` commands, which run the
helper library `corpora/civ6/lua/harness.lua` inside the game through the agent's tuner relay.

```bash
.venv/bin/python -m pilot run --game civ6 --decide-turns 5     # the game loaded with EnableTuner 1
```

The loop: snapshot → decide → apply orders → read back → then N times: autoplay **one** turn, poll
the cheap `autoplay-status` every second until the game hands the turn back, take a snapshot while
the game is idle → decide again after N turns or as soon as something urgent happens (a new war, a
city lost, threatened or about to fall, a new era, a great person or wonder race lost, gold below the purchase
reserve); stopping early is simply not starting the next turn. The tuner does not answer while the
AI plays its turn, so unanswered status polls are expected; only the turn's deadline counts (10
minutes, for long late-game turns). A turn that does not start (20 s) or end in time, or a game that
gives no snapshot three times between turns, stops the run until the human presses Resume (an
autoplay call whose reply was lost and that did not start is first sent again, twice, but only
while `civ6 turn-ready` reads the game idle at the same turn for 20 s: autoplay reads inactive
before its last turn ends, so a start that runs is waited for, never sent twice). Orders,
snapshots and human requests only ever happen between turns. `PILOT_AUTOPLAY_CHUNK` lets the AI play
several turns per call (urgent checks then run between chunks). Each autoplay call turns the
tutorial advisor off for the session: its popups wait for a click and hold the turn forever.

- **Snapshot** (`game-controller civ6 snapshot`, 2-11 KB; 10.3 KB with six cities at T202): turn, era
  and era score, civ and leader, yields, treasury and faith, research and civic with turns left,
  what can be researched, progressed and slotted now, government and policy slots, every city
  (position, population, production and turns left, districts, buildings, the land unit on its tile,
  garrison and walls HP, threats, what it can build, the AI's own top 3 builds with their scores
  (`recommend`); for a threatened city also its enemies and
  defenders, capture threats, incoming damage, whether it can strike and what a defender costs in
  gold and faith), units by type, the majors met with score and military strength, wars, great
  person points, pantheon and religion, every end-turn blocker. The briefing names every item by
  its corpus id (`tech:pottery`, `unit:settler`).
- **Orders** are structured, never Lua: `research`, `civic`, `policies`, `production`, `purchase`
  (see `corpora/civ6/pilot.md`). The governor checks each against the corpus, the snapshot (options,
  the city's buildable items) and `pillars.toml` (orders per decision; purchases keep the reserves and
  take at most the treasury share, or everything above the reserve for a city in danger); the
  controller checks the ids again and encodes every argument as a Lua string literal. Wonders and new
  districts need a tile and are refused (placement is not supported yet). `price` (a tool) reads a
  live purchase price.
- **Read-back**: a fresh snapshot right after the orders shows which took; one that did not is
  reported to the next decision and refused if it is repeated unchanged.
- **Order record** (spec `docs/design/2026-09-27-civ6-levers-design.md`, rulings 12-16): every order
  that took is followed on each snapshot until it resolves: `completed` (a tech or civic left the
  options, a unit's count rose, a building appeared), `held` (still current when its window of
  turns left + 3, at most 20, ends), `overridden` (the AI switched while it was still available),
  `invalidated`, `superseded` by our own later order, or `unknown`. Each resolved, refused or lost
  order emits an `order_outcome` event and each order still followed an `order_followed` event;
  telemetry keeps both, so the record and the open orders survive restarts. The
  decision prompt and the Strategist get one line per kind (research, civic, policies, production
  fill or replace, purchase gold or faith) with its stick rate over the last 30 turns (`[orders]` in
  `pillars.toml`), flagged "does not stick here" at 50% or less (a production order for what the
  city already builds changes nothing and stays out of the record); the dashboard gets
  `info.order_record`. `scripts/civ6-backfill-orders.py` recovers the apply-time outcomes (refused,
  lost, purchases) of traces written before the record: read-only by default, `--write` once when
  deploying.
- **Buy-outs** (rulings 17-21): a city is *in danger* (not merely threatened) when it is under siege,
  its garrison is damaged, two enemies that can capture it stand next to it, or two enemies are
  near an empty city tile; only then does a purchase there get the threatened share, and one-turn
  autoplay chunks follow it too (with war against a major and a city about to fall). The gold reserve is `gold_reserve` plus
  `gold_reserve_per_deficit` per gold of deficit; faith keeps the pantheon's live price until one is
  founded. Purchases are checked after the other orders, a defender for a city in danger first; while
  such a city has no unit on its tile, other purchases are refused, unless a defender for it was
  tried in the decision (whatever the answer) or it finishes one of its own within 2 turns; a
  defender ordered with gold is bought with faith when the snapshot's `defence_prices` (or a `price`
  answer) allow it and it fits; a production order for a defender there is bought instead; a second
  land unit on a city tile, a defender bought in the same city within 5 turns, what the city
  finishes within 2 turns anyway and a known price over the cap are refused before sending. `gold`
  and `faith` balances cannot be milestone metrics (`[metrics] milestone_exclude`).
- **The AI's own plan** (ruling 29): the briefing shows each city's top 3 builds from the game's AI
  (`GetBuildRecommendations`, the Production panel's call) and our player's strategies from the
  game's log `Logs/AI_Victories.csv` (e.g. "science victory (since T56, stopped T76)"; of the era
  strategies, which keep "Following" once started, only the latest). Each decision
  reads that log once (`game-controller civ6 ai-strategies`: one agent read from where the last one
  ended, at most 64 KB). A production order's row keeps the city's top 3 at order time, and an
  override records `top3_hit`: whether the AI's replacement was in it; the record shows how often
  it was. The scores are on their own scale; if `top3_hit` stays near chance after 10 overrides the
  line leaves the briefing (the design's test).
- **District placement, stage A** (ruling 30; read-only, not part of the loop):
  `scripts/civ6-placement.py` reads `game-controller civ6 district-plots` once (where each district a
  city could place may go, by the game's own check, and the plot facts around it) and rates each plot:
  adjacency from the game's rules (`corpora/civ6/data/_adjacency.json`) x the share of effort of the
  district's pillar (relative to an even split; the campaign's latest strategy weights, or
  `--shares`), minus the tile given up (resource 3, improvement 2, feature 1) and, where the plot is
  the best plot of a district of a heavier pillar, what that district would lose. A wonder counts
  for adjacency once built (the reply lists our built wonders; a plot shows its wonder while it is
  still being built) and is never a district. It rates the districts the AI placed the same way
  against the free plots the game offers that city now, and prints stage B's verdict: go when our
  best plot beats the AI's by at least +1 adjacency on average over at least 4 districts. No
  placement order exists yet.
- **Last stand** (rulings 22-27, off unless `PILOT_LAST_STAND=1`): a city is *about to fall* when a
  unit that can capture it (melee or cavalry) stands next to it, no walls stand, and its garrison is
  at half its hit points or less, or one attack from each enemy in range would take the rest
  (`about_to_fall`). The change to falling is urgent ("city falling: X"), so the model decides first
  and its purchases are read back. Then, at the hand-back, the governor runs scripted actions before
  the AI plays the turn, one per call: a city strike (only with walls), ranged and siege attacks on
  hostile units within 3 tiles (a sure kill first, by the weakest shooter that kills), and the
  retreat of units at 40% HP or less next to a capturer (never the garrison). Each action is read
  back in GameCore (`civ6 ls-state`): it `took`, `did_not_take` or is `unknown`; anything but
  `took`, a lost reply (never resent), a popup or a changed turn stops the stand at once. Units that
  acted and still have moves are pinned (`civ6 finish-moves`), then one-turn autoplay hands the turn
  back: the AI plays the rest of it (no manual end turn). That autoplay never starts while
  `turn-ready` reads a turn playing (autoplay on, the turn over or sent) or does not answer, and a
  game already on the next turn gets no hand-back (the loop reads it afresh). At most 8 actions and 90 s per stand, 3
  stands in a row per city (a stand stopped before its first step, e.g. by a popup, does not
  count); targets are barbarians or players at war with us whose attack would not
  change a war state, never civilians, and never a unit standing in a district that is not ours (a
  City Center or Encampment would take the hit). Each action is an `order_outcome` row (keys `stand
  city_strike`, `stand ranged`, `stand retreat`, `stand pin`) and each stand a `last_stand` event and
  a journal line; the next snapshot checks whether the AI moved a pinned unit (`last_stand_check`).
  When the first action of two stands does not take, the stand turns itself off for the run
  (`last_stand_off`).
- **Blockers**: with no research or no civic in progress and no valid order for it, the governor asks
  the model once more; if the answer still has none, it orders the strategy's first preferred item
  the game offers (else the first offered) and reports it "filled by the governor". A decision whose
  model call fails (an outage, the usage limit, every model of the pool) fills them the same way.
- **Strategy**: `corpora/civ6/pillars.toml` in share mode (science, culture, faith, economy,
  military, expansion, diplomacy) with milestones on turns (`T60`); reviews as for Stellaris.
- **Campaign** `civ6/<leader>_<map seed>`; metrics rows per turn (`date` `T<turn>`), so telemetry,
  milestones and the dashboard work as for Stellaris. The dashboard's pace control sets the turns
  between decisions; directives, overrides and speed do not apply.

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
directive's pressure is within the switch margin (1.25) of the top. A directive held at least 2
years in the campaign whose pillar's milestone metric grew no faster than when it was not held
"does not work here" and has its pressure halved; the frame shows its record, and the Strategist
sees every directive's record when it sets weights. The model may choose
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

### Access key

The dashboard listens on the LAN, so every request needs its access key: the API, the event
stream, the frame, `/control`, `/status` and everything else except the short "how to get in" page.

- **Getting in**: open the link once per browser. It is printed in the viewer's log when it starts
  (`journalctl --user -u game-pilot-view`) and by `python -m pilot dashboard-link [--port 8780]`:
  `http://<controller>:8780/?key=<key>`. The page stores the key in an HttpOnly, SameSite=Lax
  cookie (`pilot_key`) and redirects to `/`, so the key leaves the address bar; bookmark the link
  itself. Scripts send the key as the `X-Pilot-Key` header instead.
- **Where it lives**: `PILOT_DASHBOARD_KEY` if set, else `runs/dashboard.key` (created on first
  start, mode 0600; `runs/` is gitignored). The live pilot (8790) and the viewer (8780) read the
  same key, and the viewer passes it on when it forwards live controls.
- **Rotating**: delete `runs/dashboard.key` (or change `PILOT_DASHBOARD_KEY`) and restart both
  services; old links and cookies stop working, and the page says how to get the new link.
- Changes (`POST /control`, `/api/settings`, `/api/run`) must be `application/json`, and when a
  browser sends an `Origin` it must be the dashboard's own host; anything else gets 403. This
  stops other web pages from driving the pilot through your browser.
- `/api/pc` reports only whether the agent is online, its version, which known games are open and
  whether one is in front, never window titles.

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

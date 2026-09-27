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
.venv/bin/python -m pilot dashboard-link          # sign a browser in: one-time link, three words, QR code
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
| `PILOT_WAR_CRISIS` | Stellaris: the war crisis overlay (default `1`; `0` turns it off for a run) |
| `PILOT_THINKING`, `PILOT_GOVERNOR_THINKING` | thinking level for GC4 episodes / Stellaris decisions (default `medium`) |
| `PILOT_RETRO_EVERY` | strategy review every N decisions (default 5) |
| `PILOT_PORT`, `PILOT_RUNS_DIR`, `PILOT_CAMPAIGN`, `PILOT_COMMIT`, `PILOT_JOURNAL` | live dashboard port, run folder, campaign id, commit learned knowledge, journal file |
| `PILOT_DASHBOARD_KEY` | the dashboard's service key (default: generated once into `runs/dashboard.key`); a header from the controller only |
| `PILOT_LIVE_HOST`, `PILOT_VIEW_HOST` | bind addresses of the live pilot's dashboard (default `127.0.0.1`) and of the viewer (default `0.0.0.0`; `view --host`) |
| `PILOT_PUBLIC_URL`, `PILOT_DASHBOARD_HOSTS` | the viewer's canonical address for links and QR codes (page loads on other names are redirected there), and extra host names it answers to (comma list) |
| `PILOT_NOTIFY_URL` | an ntfy topic's full URL (e.g. a self-hosted server or a long random topic): the live pilot posts a notice when the run has needed you for 5 min, 30 min and 2 h, and once when it no longer does; unset = off (the default) |
| `PILOT_AUTH_DB`, `PILOT_ADD_DEVICE`, `PILOT_KEY_SIGNIN` | the sign-in store (default `runs/auth.sqlite`); `cli` limits adding devices to the controller; `1` turns the recovery-key form on (default off) |

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
flags and policies that the Governor Bridge mod turns into AI budget weights. Policies obey the
player's rules (`can_set_policy`, the 10-year lock started by each change): a directive whose policy
is still locked, or barred (no stance change at war), sets its flag only, and the reply lists the
policies set and those locked; an option already in force in the newest autosave is not set again,
so switching between directives that share it (defend and prepare_war, expand and diplomacy_first)
does not restart its lock. A directive can also switch **postures**, flags the mod v2 reads to
steer the AI's own spending (naval capacity and ship refits under `defend`/`prepare_war`, research
under `tech_rush`, and a war-crisis posture for defence armies and platforms); every posture stays
disabled until its live probe passes, so for now none is set. The mod v2 also writes the naval
capacity into each autosave for the governed empire, so the briefing shows used/max once it is
installed, and only while that export agrees with the save's own use: a campaign later loaded
without the mod keeps the last export, which the briefing calls stale (`governor_vars_stale`).

The loop: pause → briefing from the newest autosave → the model returns a directive or `keep` →
apply → resume → poll autosaves until the decision interval has passed or something urgent
happens (a war starts or ends, a resource turns negative, we newly fall below half the median in a
measure, a milestone is missed) → pause → decide again. The game is paused whenever a model
thinks, so any speed is safe. `prepare_war` needs a human "yes" on the dashboard.

The briefing (about 2 KB) covers the empire, resources and deficits, power, research options,
planets and colonisable worlds, our species and its traits, identity (civics, traditions,
personality), wars with sides and exhaustion (battles of our side, then our own in the last 12
months, invasions of our colonies, a status quo that can be forced), occupied colonies, shipyards at
war, market prices against base with last month's trades, and the nearest empires with strength
ratios and opinion both ways. The JSON form also carries policy dates, each colony's jobs,
unemployment, districts and queue, each war's id and battle count with the invasions' places in
its battle list (a colony we lose and retake counts its old invasion again, so only a place past
the previous save's count is a new invasion), and the mod's `governor_*` variables, for the
governor's rules.
The prompt adds a 12-month trend line and what earlier directive changes led to.

If the game stops answering pause and resume (for example a text box holds the keyboard), the
governor stops acting and flags *needs attention* until you press Resume.

If the autosave date stops moving while the game should be running (a popup that pauses the game,
the launcher in front, a crash), the governor waits max(300 s, 10 x the median real time of a month
in this run's last 24 months), then saves a screenshot, logs `stall` and flags *needs attention*
with the screenshot's path. It sends nothing to the game and focuses no window: it cannot tell the
governed game from another campaign you loaded (which writes no autosave at first), the launcher
or a browser tab titled Stellaris, so you check the PC and press Resume. A pause from the dashboard
never triggers this; a pause made in the game's own menu does look like a stall. Time in which the
save cannot be read (the PC asleep, the network down, the agent reinstalled) does not count: if
reads fail for that long, the governor flags *needs attention* but sends nothing and keeps reading,
and carries on by itself as soon as a save of the campaign reads again.

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
  person points, pantheon and religion, every end-turn blocker, and the diplomacy the library answered
  for us (below). The briefing names every item by
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
  deploying (a run of its own, `runs/<time>-backfill/events.jsonl` named by the earliest backfilled
  decision so it sorts among the runs by time, and the database, so `rebuild-telemetry` keeps the rows).
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
  best plot beats the AI's by at least +1 adjacency on average over at least 4 districts. A district
  whose city offers fewer than 3 other plots to compare with is not rateable and left out (its gain
  of 0 would measure a full city). No placement order exists yet.
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
- **Diplomacy auto-reply** (issues.md T240, T342): an AI leader's statement to us (a warning, a
  proposal, a deal, a declaration) opens the game's leader screen (`DiplomacyActionView`), which holds
  the engine until a human answers, so the autoplay turn never ends and the tuner goes silent.
  `corpora/civ6/popups.toml` removes that screen's statement handler on every load (the deal screen
  it opens goes with it), and the library registers its own `Events.DiplomacyStatement` handler in
  `InGame` (only there: the install chunk names its state, and the library's version covers the
  chunk's header, so an install by a controller built before it is replaced; a reinstall removes the
  old handler first). The screen's handler is removed only while the library's is in place (the entry's
  `requires = "dipl_handler"`, checked in `InGame` before each quieting); otherwise the controller
  puts it back (`QUIET_HELD`), so a statement holds the turn for a human on screen instead of going
  unanswered and unseen, and the briefing says the auto-reply is not installed. While autoplay runs it answers statements to our player from an explicit table: the five
  warnings (troops near the border, settling, spying, digging, converting) get the conciliatory
  promise ("My troops are merely passing by.", never the war or grievance choice), deals and demands
  are refused as the deal screen refuses them, proposals (friendship, delegation, embassy, open
  borders, alliance, renewing one, peace) and first meetings get Goodbye (no safe accept rule is
  proven), and kudos, warnings, denouncements, war declarations and defeats get Goodbye, their only
  choice. Every later statement of a session (the AI's "Thank you.") and any unknown kind get
  Goodbye; a promise is sent only when the game's own data offers it for that statement without a
  diplomatic action. A statement outside autoplay waits (the screen no longer shows it) and is
  answered when autoplay next starts (a follow-up that came after the hand-back gets Goodbye then),
  which also closes sessions answered earlier that no follow-up closed and logs that Goodbye (why
  `sweep`). A reply the game refuses gets Goodbye at once; a session whose Goodbye failed stays listed
  and is closed at the next autoplay start. The snapshot's `diplomacy` lists the last 20 (turn, from, statement, subtype, reply, why);
  the governor emits one `diplomacy_reply` event per new answer (telemetry keeps them, so a restart
  does not report them again), the briefing gets a "Diplomacy answered for us" line (or says the
  handler is missing), the order record the Strategist reviews lists the campaign's last 8 answers
  (published as `diplomacy_record` beside `order_record`, reloaded from telemetry after a restart),
  and the dashboard's activity feed shows each answer. Until the game is loaded
  again, a human at the PC sees no AI statement and cannot use the leader screen's conversations.
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
- actions: preferred techs (technology) and one small monthly market order (economy; a sell only of
  an idle resource, at most 25 and 20% of its income; a buy under the buy rules below).

**Pressure drives decisions.** Before each decision the governor computes every pillar's pressure
= weight × milestone need (met 0.3, on track 1, at risk 1.5, missed 2; a pillar without milestones
1) and shows the directives by pressure with a suggestion: the top one, or keep while the current
directive's pressure is within the switch margin (1.25) of the top. A directive held at least 2
years in the campaign whose pillar's milestone metric grew no faster than when it was not held
"does not work here" and has its pressure halved; the frame shows its record, and the Strategist
sees every directive's record when it sets weights. Where the metrics rows carry the metric's
median over the other empires (military, economy, tech power, systems, pops, colonies, techs), the
growth compared is that of ours ÷ median per year (e.g. `military_power ÷ median -0.009/yr over 56 y
held vs +0.005/yr otherwise`), since an absolute rate rewards whatever was held late, when every
empire grows faster (levers design ruling 7: it turns UNE2's early `expand` from "works" to a
stall); ranks and metrics without a median stay absolute (`[metrics] peer_keys` names a median kept
under another key). When unclaimed systems lie within 2 jumps but none is surveyed and influence
stayed at 950 or more for 12 months, the frame adds "expand cannot claim here: no surveyed room;
influence is not the limit" (Gaea 2221-2252). The model may choose
otherwise when the briefing gives a reason, says why, and names the milestone its choice
`serves`. A choice outside the top two is tagged off-frame and asks for a review. Games with many
levers at once (GalCiv IV, Civ VI) can use `mode = "share"`, which shows each pillar's share of
effort instead.

**Reviews** run at the start of a campaign without a strategy, every `PILOT_RETRO_EVERY`
decisions, on big events (war, crisis, colony lost, boxed in, military fell by half, a milestone
missed, an off-frame decision, a planet crisis or a planet losing pops, a war going badly or a war
crisis over; at most one per 12 in-game months) and on *Review strategy now*. An
answer is validated; an invalid one gets one corrective retry with its errors and the rejected
answer, then the strategy stays. Reviews started at the beginning of a run or by you must name the
species traits the strategy builds on. A review may add up to 3 rules to
`corpora/stellaris/learned/strategy.md`, read by later decisions.

**Actions** are carried out through the game's screens after a decision, at most once per
autosave, and checked in a later save: `stellaris_pick_tech` (only in a research field under 10%
done) and `stellaris_market_sync` (monthly trades follow the strategy; hand-placed trades are
removed once a strategy exists; an alloys or sr_* order to add is refused on its own until their
fractional start amount is measured live: the rest of the sync, removals included, still goes, the
refused order is not waited for in the next save, and later decisions skip it with that reason; an
order of the same side and resource already in the save, e.g. buy alloys 7 when the strategy wants
5, is kept at its amount rather than removed, while it passes the declared order's checks).

**Market buy rules** (Stellaris; levers design rulings 9-10, `[actions.market.buy]` in
`corpora/stellaris/pillars.toml`, `src/pilot/stellaris_market.py`), checked at every sync for the
declared buys and the automatic ones; a buy that breaks one is skipped with the reason (an order of it
in the save is then removed, as a sell that no longer fits):
- price per unit = 100 / market amount x (1 + fluctuation) x 1.3 (the fee), the fluctuation from the
  briefing's market block (0 without one: the buy is not refused, and the sync's log line and the
  next decision's market note say "price unknown");
- the reserve: trade - 12 x (cost over the monthly trade income) must leave 2,500 (where the AI's own
  market spending starts); the spend cap: cost <= 0.25 x trade income + (trade - 2,500) / 24 (0.5 of
  the income for alloys in a war crisis: declared buys, the orders kept in place and the fill alike);
- the price guard: no new order above +50%; an order already placed stays up to +100%, but buying
  more of it than its amount in the save is a new order (above +50% the order in place stays at its
  amount, for a declared buy, the idle-trade fill and the crisis alloys alike);
- the volume: at most one base amount a month on the internal market, six on the galactic one
  (alloys 25 or 150, consumer goods 50 or 300, motes, gases and crystals 10 or 60);
- never what the AI buys anyway: a deficit with under 6 months of stock (the AI buys there itself),
  a resource the AI bought since the last save (our own monthly trade left out), an IDLE one, alloys
  with the fleet at 95% of naval capacity or more (from the Governor Bridge export) outside a crisis.

**Idle-trade fill.** While the briefing flags trade IDLE and no declared order passed, the slot is
filled with deficit cover: the resource in deficit with the fewest months of stock between 6 and 24
(36 for motes, gases and crystals), 1.2 x its monthly deficit (at most the volume and 25), that passes
the rules, has a measured start amount (not alloys or sr_* until live check L2) and is not suspended.
Otherwise nothing is bought and the next decision reads "trade idle: nothing qualifies to buy
(reason)". `amount_max` stays 25 and one order until L2 measures the click step and the second row.

**Read-back.** The next save shows whether an order took (`market_orders`); `market.trades_net` (last
month's monthly trades) shows whether it trades. A buy in the order list with none of its resource
bought in 2 saves after the one that first showed it is recorded **took (not executing)**, and the
action record says so; a held order's line names its last trade (e.g. `+10 minerals for 13 trade`).

**Action record** (Stellaris; spec `docs/design/2026-09-27-stellaris-levers-design.md`, rulings 2-6):
sending is not the outcome, so every directive, tech pick, market order and posture is followed in
the autosaves until it resolves, and each resolution is an `order_outcome` event (the Civ VI row
shape; `turn` is the month), reloaded per campaign at the start of a run together with what is still
followed (`order_followed`).
- A directive **took** (flag in the next save, nothing set to follow), is **held** (every policy the
  game reported set still reads back at the next directive or after 24 months), **failed** (no flag
  in the next save, or the apply raised) or is **overridden** (a reported policy reads back another
  option dated after our apply; the line names it, e.g. `economic_policy → economic_policy_balanced
  on 2272.01.01`). Not judged: **superseded** (our next directive before a save) and **locked** (the
  game set none of its policies: `can_set_policy` said no).
- A tech pick is **researched**, **held** (still researched at the next review or after 24 months)
  or **did not stick** (skipped until the next review); a "nothing to pick" reply is a **no-op**,
  counted apart. After 3 no-op syncs the next review lists what each field offers and asks that
  `prefer_techs` name one of them (a review whose model call fails keeps the count for its retry).
- A market order **did not take** (the next save differs), is **held**, **removed** (gone later
  without our sync) or **failed** (the sync raised, e.g. an agent timeout). Two *did not take* in a
  row for the same side and resource suspend it (the order the save holds, if any, is kept) until
  the `[ui.market]` positions change: each row carries a hash of them, so a recalibration commit
  lifts it. A review no longer resets anything but the tech skip.
- Stick rate per key = (took + held + researched) / judged, over the last 120 months widened back
  to 6 judged, shown from 3 (`[orders]` in `corpora/stellaris/pillars.toml`, in months), flagged
  "does not stick here" at 50% or less. It goes to the decision prompt ("Action record in this
  campaign", after the past outcomes), to the Strategist (before the directive record) and to the
  dashboard (`order_record`). It is advisory: no pressure factor.

**War crisis** (Stellaris; levers design rulings 12-16, `src/pilot/stellaris_crisis.py`; `PILOT_WAR_CRISIS=0`
turns it off). It enters when we are at war and a loss shows: a colony occupied (C1), systems 2 or
more under their most in the last 12 months (C2), military at half or less of its most in 12 months
(C3), a colony lost (C4), a new invasion of our colonies (C5, by battle index, so a retaken colony's
old invasion does not count), or a colony under stability 25 on 2 saves in a row (C6). Never on a
military ratio, battle counts (allies' included) or war exhaustion alone; at most once per war per 12
months; not while you paused the run. The urgent reason `war going badly: <conditions>` runs the
ladder at that decision, in order:
1. a strategy review before the decision (12-month cap);
2. the pillar that ranks `defend` gets need *missed* (2.0) and no stall factor while the crisis lasts
   (the frame and the dashboard's Strategy tab show "war crisis"; dashboard `crisis`; row `crisis need boost`, `no_op` when no pillar
   ranks defend or there is no strategy);
3. `defend` is applied if the decision would leave it or not take it (`crisis defend`; the model's
   other choices stand; your own override on the dashboard stands until the crisis ends);
4. the `war_crisis` posture, only when it is enabled in `directives.toml` and the save shows the
   Governor Bridge v2 running (a current naval-capacity export); until then "skipped: not verified";
5. the market slot buys alloys (`crisis market buy alloys`) only with a shipyard in a system we hold,
   naval use under 95% (or unknown with under 1,000 alloys), alloys not IDLE, a measured start amount
   (not before live check L2) and the buy rules at the crisis cap, sized to what the cap and the
   reserve allow (at most 25 until L2); the decision prompt's `WAR CRISIS` line says what this
   decision's sync buys ("buys 25 alloys a month on the market") or why it buys none;
6. decisions every 3 months (the earlier pace comes back at the end unless you changed it meanwhile);
7. a status-quo question in the feed (never blocking; once per war per 12 months) when a colony is
   occupied, systems fell, our war exhaustion is 60% or more and at least theirs, or their side can
   force a status quo. The harness never proposes peace.

Each step is an `order_outcome` row keyed `crisis <step>` (defend, posture and market judged as their
kind; the others `done`, or `no_op` with why). It ends when every war has ended, or after 6 saves in a
row with none of C1-C6 once held 6 months (`war crisis over: ...`, a review under the cap), each save
counted once (a save not newer than the last one counted, such as the save a restarted run re-reads,
changes nothing); `crisis`
events keep its state across a restart (enter, exit, ladder and closed, and a `state` event whenever
it changes between them: the quiet saves, the conditions, your override, the status-quo asks), and a run stopped between an entry or exit and its ladder
leaves that ladder to the next run's first decision (so the posture is still cleared). Replayed on the campaigns' metrics rows it enters 5 times in
UNE2 (2256.02 and 2260.01 among them) and 25 times in Theia (first collapse 2256.08, 7 months before
the capital fell), never in Gaea.

**Planet check** (Stellaris, read-only; levers design ruling 22, `src/pilot/stellaris_planets.py`).
A colony has a problem when its stability is under 50, its free amenities under -100 on 300+ pops,
its free housing under 0 on 1,000+ pops, 5% or more of its employable pops unemployed (not the
capital), its pops 20% under their peak of the last 12 months, or it is occupied (pops count working
robots). It is flagged once the problem persists across saves at least 2 months apart with none
between them without it and none more than 3 months after the one before (a save from before a
restart gap is not "the save before": nothing was observed between), and the decision prompt gets one line naming the flagged planets only, with
a cause hint: `Planet check: Arnvoss stability 18 (3 saves), amenities -253, housing -283; nothing
queued here` (also "minerals net < 0"; on the dashboard as `planet_check`). Two urgent reasons fire
once, at the transition, and start a review (12-month cap): `planet crisis: <name> stability <n>` (a
colony under 25 on 2 saves in a row, at most 3 months apart; war crisis C6 reads the same) and `planet losing pops: <name> -<p>% in 12 months` (1,000+
pops). Each metrics row keeps every colony's pops, amenities, stability and problems (`colonies`) and
the estimate of job output lost to stability under 75 (`stability_loss`, percent; the go criterion of
a later planet lever), so the check survives a restart. The Strategist gets the planet record: per
directive held, the amenity change per planet-year on colonies with a deficit. No directive repairs
grown colonies (+5 to +14 amenities a planet-year under consolidate_economy); the 17 learned rules
that said otherwise, or that only an edge case (fast growth, massive pops, a short window) stopped it,
were corrected (`test_the_learned_rules_no_longer_credit_consolidate_economy_with_amenity_repairs`
keeps them out).

**Your edits.** *Edit* on a pillar changes it and pins it (a review never changes a pinned pillar);
changing its weight rescales the other unpinned pillars so the total stays 100. *Unpin* hands it
back.

## Dashboard

`python -m pilot view` (port 8780) shows every recorded campaign and forwards the live controls of a
running pilot (whose own dashboard is on `PILOT_PORT`, 8790, on 127.0.0.1). It refreshes itself: status every
3 s, the live event stream during a run, campaign data every 10 s otherwise.

- **Each game speaks its own words** from `corpora/<game>/dashboard.toml` (served by `GET
  /api/view?campaign=|game=`): time unit and date format, the cadence field, the decision noun, the
  levers tab, figures, chart views and series, outcome keys and window, the rivals table and the
  recovery steps per stop. A figure, view, column or cell whose data the game or the running pilot
  does not publish is hidden, never shown as "–". Game ids read as names (`CIVILIZATION_GERMANY` →
  Germany, `unit:trader` → Trader) from the corpus, with prefix-strip and title-case as the fallback.
- **The bar** carries the brand, the campaign, the PC chip, Pause/Resume (live), Settings and ⋯
  (Stop the run…, Start run, Add a device, Devices, Sign out). The campaign is a button ("Kublai
  Khan, China · T57", a dot when it is the live one) that opens the campaign list: each campaign's
  game, state (live, paused, needs you, stopped), last date, decisions and runs, the live one first
  and empty ones (no decision, no figures: a failed start) under *Show empty campaigns*. Stop always confirms in the game's
  words ("The AI finishes this turn and the game stays at T310"). The PC chip names the host, the
  game in front and the agent's version, and says "busy" (no answer in 3 s just after a turn),
  "not answering", "offline" (connection refused) or "refuses our token".
- **The governor line** (the hero, under the bar) says in one sentence whether the run needs you,
  with the date in it, then one line of facts: "The AI is playing T307." / "Next decision at T312
  (every 5 turns). Last turn 42 s. Answered by Gemini 3.1 Pro (fallback)."; "Deciding T310: 1 min
  12 s." with the model, its call number and the model it fell back from, and "Retrying in 0:12";
  "Paused from Pixel phone at T310, 4 min ago." with Resume; "Question for you: …" with Yes, No, an
  answer box and "No answer in 0:31 means: no."; "Viewing a past campaign …" with a link to the live
  one; "No run is playing." with Start run. The pace in the facts opens Settings > Game. A second
  line appears when more than 1 of the last 5 decisions in the hour fell back or failed ("Gemini
  3.8 Flash is overloaded: 3 of the last 5 calls fell back to 3.1 Pro."; `GET /api/health?run=`),
  and Settings > Models marks a model whose calls fail on billing or a refused key, with *Remove
  from list*; the list takes each model once.
- **Needs you** turns the governor line into the page's one filled block: the stop in words ("Needs
  you: autoplay did not start at T57."), how long it has waited, what it costs (Civ VI: "The game
  is stopped at T57"; Stellaris: "The game ran on without the governor: 2274.09 → 2282.08"),
  whether it retries by itself, the recovery steps for its category from the game's view,
  *Resume*, *Capture the game screen* (`POST /api/capture`: the agent's screenshot, read-only for
  the game, stored as the run's frame and named after the device) and *What happened* (the reason,
  the errors behind the stop cut to their cause, the raw text). The tab title ("Needs you – T57 –
  Game Pilot") and the favicon carry the state outside the page.
- **Outside the page** (opt-in, `PILOT_NOTIFY_URL`): the live pilot posts to an ntfy topic when the
  run has needed you for 5 minutes, again at 30 minutes and 2 hours, and once when it no longer
  does: "Game Pilot needs you: Civ VI, autoplay did not start at T57 (5 min)", "Game Pilot no longer
  needs you: Civ VI is playing again at T57 (after 7 min)". Tapping it opens the dashboard's plain
  address (`PILOT_PUBLIC_URL`, else this machine's address on 8780). No key, cookie or token is ever
  in it; whoever knows the topic learns that a run is stuck, so use a self-hosted server or a long
  random topic. Off by default.
- **Figures**: from the view's `[[figures]]`: value, label and a subline with our place among the
  rivals ("#4 of 4, median 42, behind the median", in the warning colour with those words) or what
  purchases keep back. Stellaris leads with the directive in force and the standing.
- **Over time**: the view's chart views (Civ VI: yields, balances, rank with 1 at the top; Stellaris:
  net income, stockpile, power) plus a table of every recorded figure (it scrolls in its own box).
  Every line is named at its end; x ticks count turns or years; war periods are bands. Above the
  plot: the directive lane (Stellaris) and the strategy reviews' own lane. Each decision is a short
  tick under the axis (urgent ones taller, a failed one red), drawn full height only when it is the
  one selected, hovered or current; last stands are red marks on the axis. The chart is one tab
  stop: the arrow keys, Home and End move between decisions (a screen reader hears each), Enter or
  Space opens one in Reasoning. The rivals table (Civilizations met, Neighbours) has the
  view's columns; a column no rival has a value for is left out.
- **Decisions**: each row leads with the model's reason (two lines, in the model's serif), under
  the date, the trigger as a category in words ("City threatened: Chengdu", "Great Scientist race
  lost", "Scheduled", with "urgent"), and the answering model and time at the right ("(fallback)"
  when another model answered). Stellaris puts the directive before the reason ("Kept diplomacy
  first"). Civ VI's orders show as fate chips, the only pills on the page: ✓ held or completed,
  ↺ replaced by the AI → what it chose, ✕ refused (the reason in the chip's title), ? no reply,
  ⋯ in force; one line with "+N" on a desktop, counts per fate on a phone. The outcome line uses
  the game's outcome keys and unit ("12 turns later: score +17, military −226 ▲ watch"; a drop past
  the view's `watch` threshold is flagged). A decision whose model calls all failed reads "No
  decision:" with the cause. *Problems only* keeps errors, refused orders and failed directives.
- **Reasoning** leads with the decision (Stellaris: the directive; Civ VI: the first sentence of the
  reason), then labelled pairs (Trigger; Answered by, with the models that failed before it and
  why, "after Gemini 3.8 Flash was overloaded (503) (×3)"; Took), the orders with their fates and
  badges (filled by the governor, bought with faith, asked again when research was left idle), the
  outcome, the model's reason in full, and the trace (what the model was shown, thinking, tool calls
  with their arguments as pairs, the answer; steps after the first two folded). A failed decision
  shows the cause and the chain of models tried, the raw error one disclosure away. The reader
  column is not a scroll box: the page scrolls. Picking another campaign clears it.
- The chart's x-axis counts turns for turn-based games; a view whose figures the game does not
  record falls back to the table of the figures it does record.
- **The reader tabs**: Reasoning · the game's levers tab · Strategy · Talk · Activity (the selected tab
  is the one tab stop; arrow keys, Home and End move between them). The levers tab is Civ VI's
  **Orders**, Stellaris's **Actions** (the strategy's tech picks and market syncs, and the screen)
  and GalCiv's **Screen** (the latest frame and the blockers cleared lately; selected by default).
  The game screen lives there and on the needs-you card, fetched only when the run recorded one.
- **Orders** (Civ VI; `GET /api/orders?campaign=&kind=&fate=&limit=`): the buy-outs (gold and faith
  against what purchases keep back and why, from the live `info.reserves`, cities in danger), a
  persistent line when the last stand turned itself off, the order record per kind ("Production,
  replace the AI's choice": the stick rate as a bar once enough orders were judged, else "2 held of
  3, too few to judge", "Does not stick here", what was not judged in words, the last override;
  "Last 30 turns; weak at 50% or less"), every order newest first with its fate, filters by kind and
  by fate, "in force, 3 of 8 turns followed" for open ones, a "backfilled" tag on rows from older
  decisions, a click opening the decision it came from, and the last stands with their actions.
- **Actions** (Stellaris; each part only when the pilot publishes its data, which the Stellaris
  levers work adds): the war crisis ("War crisis since 2291.03: a colony occupied (Arnvoss), lost 2
  systems. Step 2 of 4: defensive stance.", from `info.crisis`), the action record in the Orders
  tab's shape with Stellaris keys ("Directive: Defend", "Market: buy alloys", "Tech picks",
  "Posture: naval capacity"; `info.order_record` live, `/api/orders` once the pillars file has
  `[orders]`; a market resource marked "Suspended until recalibrated"), the market per resource from
  the newest metrics row's `market` ("Alloys: 14% above base; net +5 a month; order: buy 5 a month
  (economy)"), then the strategy's actions lately. The crisis also shows in the bar ("War crisis",
  which does not scroll away; on a phone the ▲ alone, so the campaign keeps its name), in the governor line's facts, at the top of Strategy with the
  defence pillar's "need boosted ×2 (crisis)", and as a band on the chart (metrics rows' `crisis`).
  The Directive figure lists the directive's postures ("postures: naval capacity on"; one not
  enabled is greyed and says so on hover or focus; `info.postures` or the metrics row's). A
  directive's policy report (the trace's `applied`) reads "Applied; 1 policy locked (diplomatic
  stance: at war)" in its row and in Reasoning.
- **Game health** (Civ VI, on Now, only when something is off): popups quieted at this load, tuner
  timeouts in the last calls, the last turn's time; in the warning colour when a popup failed to
  quiet or a turn was held. The governor line's facts say whether the last stand is armed or off.
- **On a phone** (700 px and narrower) the page is its own layout: a 52 px bar with the brand dot,
  the campaign and its date, a state dot and ⋯ (which then also holds Pause/Resume, Settings and the
  PC chip); a bottom nav Now · Decisions · the levers tab · Strategy · Talk (the current one is the
  tab stop, arrow keys move); Now leads with the governor line and the last decision, then the
  figures, the chart and the rivals, and ends with the last 5 problems and *All activity*. Off Now
  the governor line shows only when the run needs you (its sentence, not the card). A decision opens
  Reasoning as a full-screen sheet (Back, a swipe down on its head, Escape or the browser's back
  close it, and focus returns to the row); the campaign list, Settings and Add a device are
  full-screen sheets too. Nothing scrolls sideways and no text is under 13 px.
- **Activity**: every event as one sentence in the game's words ("Played T55 → T57 in 2 min 6 s",
  "Gemini 3.8 Flash overloaded (503); used Gemini 3.1 Pro", "Popups quieted 5 of 6 at T50; not: …",
  "Review skipped: within 12 turns of the last; next after T62"), newest first, each with its game
  date over its wall time and the raw event behind *Raw event*; the same thing in a row groups
  ("Autoplay at T57 failed: the game's tuner did not answer (timed out), 3 times, T55–T57",
  "Learned 3 rules"). Filters: Problems, Orders, Model, You, All (Problems while the run needs you).
  A kind the page does not know reads "Unrecognised event: …". The order record's rows are in
  Orders, chat in Talk. A campaign shows its own events (`GET /api/events?campaign=&after=`), a past
  one too, never the newest run's.
- **Talk** (live): ask the model about its reasoning, leave a note for the next decision, decide
  now, standing orders, override a directive, answer confirmations.
- **Strategy**: the focus, then where the effort goes as one stacked bar (share mode, Civ VI) or the
  directives by pressure (exclusive mode, Stellaris); the strategy summary folded to three lines
  with *Read all* (its lists render as lists); one card per pillar (share mode: "34% of effort";
  exclusive mode: weight · need × · pressure, with the share bar; stance, goals, milestones with
  dates in game units, preferred items by name), Edit (a weight change previews how the other
  unpinned weights rescale) / Unpin, *Review strategy now* with the last review's result beside it
  (accepted with the weight changes, rejected and why, or skipped with the next eligible date), and
  the version history.
- **Settings**: models per role (the decisions role's help is the game's; the GC4 blockers role only
  for GalCiv); Game: a speed only where the game has one, the interval bound to the game's cadence
  field (Civ VI's turns only while its run is live). With no run active, *Start run* starts
  `game-pilot.service`, with the game in front on the PC preselected, a warning only when the chosen
  game is not in front, only that game's fields, and a toast naming the game and campaign that
  started.
  Changes save at once, and each field says "Saved" (or why not) next to itself.
- A refused action (the live pilot answers 400, a change the dashboard refuses) is said in a toast
  with the server's reason; the page never blocks on a dialog box. Light mode's text colours pass
  WCAG AA; dark mode is the identity and unchanged.

### Signing in

The dashboard listens on the LAN, so every request needs a principal (design:
`docs/design/2026-09-27-dashboard-v2-design.md`, rulings 34-52; code: `src/pilot/auth.py`):

- **Browsers** each hold their own session: an HttpOnly, SameSite=Lax cookie `pilot_session`
  (400 days, re-sent at most weekly while the browser is used), a random token whose hash is kept
  in `runs/auth.sqlite` (`PILOT_AUTH_DB`; mode 0600). Each is a named device that can be signed out
  on its own; a browser unused for 180 days is signed out. A page whose browser was signed out
  says so ("This browser was signed out from Pixel phone at 14:02"), stops polling and its event
  stream, and links to sign in again; an open event stream closes within 15 s of a sign-out. A
  sign-in code the signed-out browser had made (⋯ > Add a device) is cancelled with it, and a code
  whose maker is signed out never signs anyone in.
- **The service key** (`PILOT_DASHBOARD_KEY`, else `runs/dashboard.key`, 0600) works only as the
  `X-Pilot-Key` or `Authorization: Bearer` header from the controller itself (127.0.0.1 / ::1),
  never through `Forwarded` / `X-Forwarded-For`, never as a cookie or in a URL, and it is no
  longer printed at startup. From another address it gets 401 `service_key_loopback_only` and an
  audit row. Scripts on the controller keep using it; processes re-read the file when it changes.
  The viewer forwards live controls to the pilot with it, plus `X-Pilot-Device` (the device id)
  and `X-Pilot-Device-Name` (its name, percent-encoded) for the browser behind the request.
- **Scripts on other machines** use scoped tokens (`pgt_…`, `read` or `control`), sent as a header
  only (`Authorization: Bearer` or `X-Pilot-Key`, from any address); `read` gets 403 `read_only` on
  anything but GET, and no token can manage devices or sign-ins. They are made only on the
  controller, shown once: `python -m pilot dashboard-token create --name "laptop watch" --scope read
  [--expires 90d]`, `dashboard-token list`, `dashboard-token revoke ID` (or Revoke in Devices).
- **Rotating the service key**: `python -m pilot dashboard-key --rotate --keep <ids>|all|none
  [--force]` writes a new `runs/dashboard.key` (atomic, 0600) that both services read within 2 s,
  so nobody is signed out and nothing restarts. It lists the devices carried over from the old key
  cookie (name, first address, last use), each with the browsers added from it (a device added from a
  carried-over one, or through an old `?key=` link, is carried over too), and keeps only those named
  and what they added (`--keep`, or the answer at a terminal; no default); the rest are signed out,
  including any carried over while the prompt waited, and the carry-over ends: an old `?key=` link's
  code made before it no longer signs anyone in (nor after the 72 hours). It refuses while the key
  comes from `PILOT_DASHBOARD_KEY` (change the variable and restart both services), and while a live
  pilot from before this change runs (it reads the key only at startup) unless `--force`.
  Suspected compromise: `dashboard-devices revoke-all`, `dashboard-key --rotate --keep none`, then
  `dashboard-link` for yourself, and read `dashboard-devices log`.
- **Carry-over**: for 72 hours after the first start of this code (or until the key is rotated), a
  browser holding the old `pilot_key` cookie keeps working, and its first page load turns it into
  a device ("carried over from the old link") and deletes the old cookie; an old `/?key=` link
  becomes a one-time sign-in link. Afterwards the old cookie is deleted wherever it is seen and
  `?key=` values are never read. The window's deadline is also kept next to the key
  (`runs/dashboard.carryover`, 0600), so a new sign-in store (a corrupt one moved aside, a deleted
  file, another `PILOT_AUTH_DB`) neither reopens nor extends it; a store recreated after corruption
  with no such record keeps it shut.
- **Host names**: the `Host` must be an IP literal, `localhost`, this machine's host name (also
  `.local` and its FQDN), a name in `PILOT_DASHBOARD_HOSTS` (comma list) or the host of
  `PILOT_PUBLIC_URL`; anything else gets 421 (no DNS rebinding). With `PILOT_PUBLIC_URL` set, page
  loads on another host are redirected there (308).
- Changes (`POST`) must be `application/json`; a browser's change must carry an `Origin` equal to
  the dashboard's host (`Origin: null`, another site or `Sec-Fetch-Site: cross-site` get 403),
  so other web pages cannot drive the pilot through your browser. Every response is `no-store`,
  cannot be framed and carries `nosniff` and a `Referrer-Policy`; the dashboard page's
  `Content-Security-Policy` lets only its own inline script run (named by its SHA-256), so a name
  that slipped into the page as markup runs no handler and loads no script. API 401s are JSON
  (`error`, `reason`, `fix`, `by`, `at`) with `WWW-Authenticate`; page loads go to `/pair`.
- **Signing a browser in** (`/pair`, the sign-in page; it looks like the dashboard on a phone, in
  light and dark): a signed-in browser opens ⋯ > **Add a device**, which shows a QR code (behind
  "Show QR code" on a phone), three words ("maple · orbit · crane") and the link with **Copy link**
  (it selects the text and copies without the clipboard API, which plain HTTP lacks). The phone
  scans the code, another browser opens the link, or anyone types the words on the sign-in page (the
  first three letters of each are enough). A code works once, within 10 minutes; the sheet shows
  "Signed in: Brave on Windows, 192.168.1.77" when it is used. With no browser signed in anywhere,
  run `python -m pilot dashboard-link` on the controller (it prints the link, the words and a
  terminal QR code, never the key; an agent may run it; `--wait` names the browser that used it).
  The link carries its code in the fragment (`/pair#c=…`), so the code never reaches a request
  line, a log or a link preview, and only the tap on "Sign in" spends it; the address bar loses it
  afterwards. A browser inside another app (a chat app's WebView) is told so and can open the page
  in the real browser without using the code up. `PILOT_ADD_DEVICE=cli` limits adding devices to
  the controller.
- **Guessing and replays**: 5 wrong typed codes from one address in 10 minutes pause typing there
  (429, with a countdown); 20 anywhere pause it for everyone; 5 wrong ones in all switch the words
  of the open codes off (their links and QR codes still work). A valid link is never throttled,
  signed-in browsers and scripts never are. `python -m pilot dashboard-devices unlock` lifts the
  pauses (so does a viewer restart). A code used a second time by another browser signs out the
  browser it had signed in and tells every signed-in page ("A used sign-in code was tried again");
  the same browser submitting it again within 10 s from the same address (a double tap on the form)
  is not a copy and changes nothing.
- **Devices** (Settings > Devices, or ⋯ > Devices): this browser (rename, sign out), the other
  browsers with how and when they signed in and their last use and address (badges: new, carried
  over from the old link, used from two addresses) and **Sign out**, the script tokens with
  **Revoke**, **Sign out all other devices**, and the recent sign-in activity. Other signed-in
  pages show a notice for 24 h after a new device signs in. From the controller:
  `python -m pilot dashboard-devices [list | rename ID NAME | revoke ID | revoke-all [--except ID] |
  log [-n N] | unlock]`.
- **Recovery key form** (off; `PILOT_KEY_SIGNIN=1` turns it on): a password-manager-friendly form on
  the sign-in page that takes the service key; throttled like the words, and it sends the key over
  plain HTTP, so keep it off unless needed.
- `GET /api/auth/me` names the principal and returns notices (carried over, new devices, a used code
  tried again, a device used from two addresses within 10 minutes); `/api/auth/devices`,
  `/api/auth/grants`, `/api/auth/log` serve the panels (browsers only); `POST /api/auth/unlock`
  takes the service key from loopback. Sign-ins, failures, sign-outs, refusals and control actions
  go to an audit table, one row per event, address and minute.
- **The live pilot's own dashboard** (8790, `PILOT_PORT`) listens on 127.0.0.1 (`PILOT_LIVE_HOST`)
  and answers only the service key as a header from loopback: no cookies, no sign-in routes, no
  store. Browsers reach it through the viewer, which names the device behind each forwarded request;
  the pilot records it as `by` on control, chat and instruction events ("Paused, from Pixel phone"
  in Activity; a script on the controller is "the controller"). Its `/status` carries
  `info.auth_version = 1`. Its event stream closes within a keepalive once the key changes.
- **Scripts** on the controller: `python -m pilot control pause|resume|stop|instruct|chat|… [--text T]
  [--index N] [--port 8780]` posts JSON to the viewer over loopback with the key (read on each call),
  prints the reply and exits non-zero with the server's error on any refusal; or send the key
  yourself with `curl -fsS -H "X-Pilot-Key: $(cat runs/dashboard.key)" …` (read it on every call,
  so a rotation does not break a long loop).
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

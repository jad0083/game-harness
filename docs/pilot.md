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
PC in use. One pilot unit runs whichever game `runs/pilot-settings.json` names, so a deploy goes through
`scripts/deploy-pilot.sh <from> <to>` (`--dry-run` to preview; postmortem-fixes design, ruling 28):
`scripts/pilot-affected.py` classifies each changed path (civ6: `src/pilot/civ6*.py` and
`corpora/civ6/**`; stellaris and galciv4 alike, galciv4 with `src/pilot/controller.py`; view:
`src/pilot/static/**`; rust: `crates/**`, `Cargo.*`; none: docs, games, tests, other `.md` files,
`corpora/*/learned/**`, `scripts/ci*`; shared: every other `src/pilot/*.py` and `pyproject.toml`, and any
path not listed). The running pilot (its game read from its own `/status`, else the settings file)
restarts only when its game's class or shared changed; the viewer restarts for view, shared and any
`src/pilot/*.py` of a game's class (it imports game modules too, such as `stellaris_record` and `civ6`); a Rust change pauses the pilot through its dashboard, builds the
controller and resumes a Civ VI pilot, which runs the binary afresh for each call (a pilot paused by the
human or waiting for one is left as it is); a Stellaris or GalCiv IV pilot keeps one `game-controller
mcp` child for its whole run, so a Rust change restarts it after the build. Otherwise
it prints "not restarted: the running civ6 pilot is unaffected; the change applies at its next start".

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
measure, a milestone is missed, or a neighbour builds up: one that is not an alliance or federation
partner, at 2 x our military power or more, grew 50% within `[time] buildup_window` (24 months), once
per neighbour per window, a decision only, never a review or a war-crisis entry; one seen by the
start of a run or a human request goes into that decision's reason; postmortem-fixes design, ruling 11)
→ pause → decide again. Each scheduled interval logs the months that passed
(`interval {months, requested, date}`); more than one month over `decide_every_months` emits
`pace_overrun`, for information only (ruling 27). The game is paused whenever a model
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

**The end of a campaign** (postmortem-fixes design, rulings 22-23): a save in which we own no planet
gets no decision and no review (also the first save of a run); a second one in a row ends the run as lost, with no model call: the
game stays paused, a `campaign_end` event (`result` lost, the last date we held a planet, the date
the loss was seen, the signal, the report: colonies lost, our military against the strongest enemy,
the stocks left, decisions after the loss was seen), a journal line, the run's `lost` status in
telemetry, `info.end` and the status `ended`. A date stall after a save with no planet ends it the
same way, also when that save was the first of the run (the game may stop saving once the empire
falls; unverified). A new run on such a campaign
ends at its start. A lost capital stays the "colony lost" trigger, and a briefing that cannot find our
country still waits for the human (another game's save reads the same way).

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
reserve; postmortem-fixes design, rulings 10-14: falling behind the met majors in a measure (on entry;
`[peers] behind`: military under 0.6 x their median or last with 3+ met, techs and civics under 0.85,
score and cities under 0.8), a neighbour's buildup (a met non-ally at 2 x our military that grew 50% or
more within `[time] buildup_window`, 20 turns; once per neighbour per window), gold per turn turning
negative, a city's loyalty falling below 50 or to 5 times its drop per turn or less (once per city until
it rises; rows count `low_loyalty`), and, at every hand-back while at war with a major, a city in danger
with no unit on its tile whose `defence_prices` list a defender the game allows within the cap and whose
defender cooldown has run out, "city still in danger: ..."; falling behind in military, a buildup and
negative income also start a review); stopping early is simply not starting the next turn. A new war
names who declared it (postmortem-fixes design, ruling 24): one `civ6 log-tail DiplomacySummary.csv`
read (under `civ6_appdata`, Logs/) when a snapshot shows a new war, its "Declaring War" rows between
the two snapshots' turns ("539, 5, Team 0, Individual Declaring War on Team START, Surprise"; a team is
taken as its player's id): "new war: CIVILIZATION_AUSTRALIA declared a surprise war on us
(CIVILIZATION_MALI joined against it through its defensive pact)", "new war: our AI declared war on
CIVILIZATION_AUSTRALIA (a surprise war)", "new war: CIVILIZATION_MALI joined through its defensive
pact", or, when the read fails or finds no row, "new war: at war with CIVILIZATION_X (who declared is
not known)", never a guess. China's own autoplay AI declared the T121 war, which the model recorded as
Australia's. The log's live layout is unverified. Each `turn` event logs the turns that passed
(`turns`) and those requested (`requested`); more turns than requested emits `turn_overrun
{requested, actual, turn}` and the hand-back's snapshot checks for the end of the campaign before
anything else (ruling 27: 18 of 25 autoplay calls after T579 overran, T583 to T612 on a 3-turn call,
while the log showed the numbers requested). Traces keep a decision's whole prompt, up to 100,000
characters (other texts keep the 6,000 cut), so the per-city danger lines can be audited. The tuner does not answer while the
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
  defenders, capture threats, incoming damage and whether it can strike), units by type, the majors met
  with score and military strength (and `allied` while an alliance with us is in force), wars, great
  person points, pantheon and religion, every end-turn blocker, and the diplomacy the library answered
  for us (below). Postmortem-fixes design, rulings 1, 7 and 21: `alive` (our civilization,
  `IsAlive`; null when unreadable), `resources` (our stock of each strategic resource, e.g.
  `RESOURCE_OIL`; left out when the call fails) and, for **every** city, `defence_prices`: per currency
  the two cheapest defenders the game allows now, plus the strongest ranged unit that needs no
  strategic resource and the strongest anti-cavalry unit the city can produce, allowed or not, each
  with its live gold and faith price and, when refused, why (`stacking`, `balance` or `game`; the
  governor names a strategic resource we lack from the corpus `resource_cost`, "needs 1 Oil, have
  0"). A city in danger with nothing to buy says so with each reason ("no defender can be bought now
  (unit:infantry: needs 1 Oil, have 0; unit:modern_at: a unit is on the tile)"). While the weakness
  test holds (a defender may be bought in any city), every other city's line says the unit on its tile
  or, with none, its defenders to buy and why each is refused (T496: Rockhampton could buy a Modern AT
  for 1,160 faith and the briefing did not say so). `allied`, `resources`
  and the refusal table are unverified live (read under `pcall`). The briefing names every item by
  its corpus id (`tech:pottery`, `unit:settler`).
- **Orders** are structured, never Lua: `research`, `civic`, `policies`, `production`, `purchase`
  (see `corpora/civ6/pilot.md`). The governor checks each against the corpus, the snapshot (options,
  the city's buildable items) and `pillars.toml` (orders per decision; purchases keep the reserves and
  take at most the treasury share, or everything above the reserve for a city in danger); the
  controller checks the ids again and encodes every argument as a Lua string literal. Wonders and new
  districts need a tile and are refused (placement is not supported yet). `price` (a tool) reads a
  live purchase price.
- **Read-back**: a fresh snapshot right after the orders shows which took; one that did not is
  reported to the next decision and refused if it is repeated unchanged. An order whose reply was
  lost is never sent again blindly (it may have run), with one exception (postmortem-fixes design,
  ruling 5): a purchase whose read-back of the same turn shows the balance within 1 of its value
  before and the item's count unchanged (`units.by_type`, or the city's buildings) is proved not to
  have run; its row is `lost` ("nothing spent (proved)") and it is sent once more before the next
  autoplay, once `turn-ready` reads the engine idle (else at the next hand-back), through the checks
  again on a fresh snapshot (a new price, a unit now on the tile or the cooldown refuses it). A
  second lost reply is an urgent decision ("order lost twice: purchase unit:modern_at in Longxi");
  an `order_resend` event and a journal line record each re-send. At T570 Longxi's Modern AT (1,160
  gold, allowed) was lost this way and nothing ran until the discount ended at T572. Last-stand
  actions are never sent again.
- **Price changes** (postmortem-fixes design, ruling 6): when a defender's gold or faith price in
  `defence_prices` moved 25% or more since the last decision, within one era, the decision prompt
  says so, with its World Congress cause from one `civ6 log-tail World_Congress.csv` read (only when a
  change is seen; its `RESOLUTION DECIDED` rows of the last 30 turns): "Price change: gold unit prices
  halved since T543 (unit:modern_at 2,320 → 1,160); World Congress: WC_RES_MERCENARY_COMPANIES (T542);
  this may end at the next World Congress session." The session calendar is not read (unverified), nor
  is the log's live layout; a row that does not parse names nothing. Mercenary Companies halved gold
  unit prices T544-T571, and 1,626-1,676 gold was stranded when it ended at T572.
- **Order record** (spec `docs/design/2026-09-27-civ6-levers-design.md`, rulings 12-16): every order
  that took is followed on each snapshot until it resolves: `completed` (a tech or civic left the
  options, a unit's count rose, a building appeared), `held` (still current when its window of
  turns left + 3, at most 20, ends), `overridden` (the AI switched while it was still available),
  `invalidated`, `superseded` by our own later order, or `unknown`. Each resolved, refused or lost
  order emits an `order_outcome` event and each order still followed an `order_followed` event;
  telemetry keeps both, so the record and the open orders survive restarts. The
  decision prompt and the Strategist get one line per kind (research, civic, policies, production
  fill or replace) with its stick rate over the last 30 turns (`[orders]` in
  `pillars.toml`), flagged "does not stick here" at 50% or less (a production order for what the
  city already builds changes nothing and stays out of the record); the dashboard gets
  `info.order_record`. Purchases are keyed by item class and currency (`purchase unit gold`, `purchase
  unit faith`, `purchase building gold`, `purchase building faith`; older `purchase gold|faith` rows
  are keyed by their id's corpus kind when loaded) and shown as counts only, since a purchase read
  back as done is completed by construction (postmortem-fixes design, ruling 9: "faith purchases held
  8 of 8" came from cheap buildings while no faith unit purchase was sent from T385 to T541), e.g.
  "unit purchases: 7 bought (faith 5, gold 2), 2 refused by the harness (cap 2), 2 refused by the game
  (Oil 1, stacking 1), 2 lost", or "unit purchases: 0 sent". Refused purchase rows carry `refusal`
  (`cap`, `reserve`, `stacking`, `cooldown`, `skip`, `defence_first`, `quota`, `other`; the game's own:
  `resource` naming the resource, `stacking`, `game`) and `refused_by` (harness or game). `scripts/civ6-backfill-orders.py` recovers the apply-time outcomes (refused,
  lost, purchases) of traces written before the record: read-only by default, `--write` once when
  deploying (a run of its own, `runs/<time>-backfill/events.jsonl` named by the earliest backfilled
  decision so it sorts among the runs by time, and the database, so `rebuild-telemetry` keeps the rows).
- **Buy-outs** (rulings 17-21): a city is *in danger* (not merely threatened) when it is under siege,
  its garrison is damaged, two enemies that can capture it stand next to it, or two enemies are
  near an empty city tile; one-turn autoplay chunks follow it (with war against a major and a city
  about to fall). A defender purchase gets the threatened share (down to the reserve) in a city in
  danger and, while the weakness test holds (postmortem-fixes design, rulings 1-2), in every city;
  buildings and other units (a Rock Band, a Settler) keep the treasury share everywhere. Under
  weakness defender purchases in different cities do not count toward `max_orders` (one per city per
  decision), and a refusal by the cap names the clause ("a defender may spend down to the reserve: at
  war with CIVILIZATION_AUSTRALIA"). Every decision prompt and the Strategist's review carry "Purchase
  limits now" (e.g. "a defender may cost up to 1,961 faith / 798 gold in any city (military weakness:
  war, last; down to the reserve); anything else up to 980 faith / 414 gold"), the briefing the
  "Military weakness" line and "Strategic stock: Oil 0, ...", and the instructions ask a decision that
  leaves a buyable defender unbought to cite its price. A Strategist answer that prefers or quotes a
  unit whose corpus `resource_cost` our stock cannot pay is sent back once ("unit:mechanized_infantry
  needs 1 Oil; we have 0"; ruling 8; pinned pillars exempt); `info.weakness` lists the clauses. The gold reserve is `gold_reserve` plus
  `gold_reserve_per_deficit` per gold of deficit; faith keeps the pantheon's live price until one is
  founded. Purchases are checked after the other orders, a defender for a city in danger first; while
  such a city has no unit on its tile, other purchases are refused, unless a defender for it was
  tried in the decision (whatever the answer) or it finishes one of its own within 2 turns; a
  defender ordered with gold is bought with faith when the snapshot's `defence_prices` (or a `price`
  answer) allow it and it fits; a production order for a defender there is bought instead; a second
  land unit on a city tile, a defender bought in the same city within 5 turns, what the city
  finishes within 2 turns anyway and a known price over the cap are refused before sending. `gold`
  and `faith` balances cannot be milestone metrics (`[metrics] milestone_exclude`).
- **The governor's own defender** (postmortem-fixes design, ruling 3; `rule_buy = true` in
  `[actions.purchase]`): before an autoplay call of 2 or more turns, while the weakness test holds and no
  defender was bought at this hand-back, the governor orders one purchase itself, with no model call: the
  first ungarrisoned city (in danger, then threatened, then without walls, then the capital, then by
  name) whose `defence_prices` list a defender the game allows, of a defender class, needing no strategic
  resource, within the defender cap, past its 5-turn cooldown, whose upkeep leaves gold per turn at 0 or
  more; the strongest by corpus max(combat, ranged), then the cheaper, faith tried first. It goes through
  the order checks and the read-back like any order (`by: governor`, "bought before autoplay (military
  weakness: ...)", a `rule_buy` event and a journal line), at most one per stretch and tried once per
  hand-back turn whatever came of it (a purchase lost twice makes an urgent decision; the hand-back after
  it starts autoplay rather than sending it a third time). At war with a major
  the chunk is already one turn and the hand-back decides instead ("city still in danger"). Under
  weakness an ungarrisoned city with an empty queue also gets its strongest resource-free defender as a
  production order, at that step and at each decision whose answer leaves the queue empty. A fill stays
  a production order even in a city in danger: only the model's own production order for a defender is
  bought instead (levers ruling 20), so the governor never buys past ruling 3's one purchase, its upkeep
  check or the model's "keep". A rule buy refused for upkeep says so ("upkeep: unit:machine_gun in
  Guangzhou costs 6 gold a turn and gold per turn is +5").
- **What the AI spent** (ruling 4): at each hand-back, per currency, balance before + the start
  snapshot's yield x the turns played - balance now (our own purchases are already in the read-back the
  stretch starts from; when that read-back failed, or after a pause or a Resume, the stretch starts from
  a fresh snapshot instead, so our purchase never reads as the AI's and the rule buy never prices from a
  balance before it; E10: 2,278 + 226 x 3 - 958 = 1,998 faith, the Rock Band the game logged at T526);
  rows carry it as `ai_spent` (telemetry keeps one row per date, so the decision's own row at that
  hand-back and the end check's second read keep it). The next decision's prompt says "Since T525 the AI spent 1,998 faith
  (UNIT_ROCK_BAND, T526) and 1,717 gold (not named)" when a currency's spend since the last decision is at
  least max(50, 10% of its yield over those turns); the items come from the game's
  `Logs/AI_CityBuild.csv` (`FAITH PURCHASE` and `PURCHASE` rows of our player, read by `civ6 log-tail` at most
  once per hand-back, only when there is a spend to name; a row whose layout does not match is "not named").
  The log grows 10-15 KB a turn late in a game, so a read goes on from where the last one ended, page by
  page to the end, while that is at most a page (64 KiB, about 4 turns) behind; otherwise it takes the
  file's tail sized to the turns since the last decision (16 KiB a turn, at most a page, `--tail`), and
  rows of turns an earlier read covered are not counted twice.
  A stretch whose spend in a currency reaches the cheapest defender the game allows in it is an urgent
  decision ("the AI spent 1,998 faith on UNIT_ROCK_BAND in T525-T528"); it never stops the run for a
  human.
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
  unit that can capture it stands next to it, no walls stand, and its garrison is at half its hit
  points or less, or one attack from each enemy in range would take the rest; or when nothing is
  left, garrison 0 and walls 0 with an enemy within 2 tiles (`about_to_fall`; postmortem-fixes
  design, ruling 26). A capturer is a melee or cavalry unit, or any unit the game lets capture
  (`CanCapture`) with a melee strength whose class is not ranged or siege: the Giant Death Robot
  (ranged 120, melee 130) took Guangzhou at T565 unseen, and Beijing fell at T545 with no garrison,
  no walls and no capturer next to it. `CanCapture`'s values by class are unverified live; the
  stand itself stays off. The change to falling is urgent ("city falling: X"), so the model decides first
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
  the game offers (else the first offered) and reports it "filled by the governor".
- **A decision with no answer** (postmortem-fixes design, ruling 20): when every decisions model
  fails (an outage, the usage limit; an `episode_error`), the same hand-back retries once, before any
  autoplay, with the decisions agent on the Strategy role's own models (those not cooling down), the
  same prompt plus "Answer now, with at most 3 tool calls." (a `decision_retry` event; the trace names
  `retried_on` and `first_error`). A Strategy role without models of its own gets no retry: the models
  that just failed are not tried again. When the retry fails too, the governor acts by rule, with no
  model: it fills an idle research or civic, fills empty queues of ungarrisoned cities with a
  defender under military weakness (queued, never bought), and, while the weakness test holds, buys ruling 3's defender for
  the city most in need (in danger first; `rule_buy`), reported "no answer from the model: the
  governor acted by rule". T512, T522 and T525 failed on 503s and the request limit; T525 was the
  only pre-war window, with 2,278 faith and a Machine Gun at 1,080.
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
- **The end of the campaign** (postmortem-fixes design, rulings 21-23): the snapshot's `alive` false
  ends the run at once; 0 cities and 0 settlers is read again at once and ends it when the second read
  agrees (one glitched read never does; a second read that fails runs no decision either: the next
  stretch starts from a fresh snapshot and the next hand-back checks again). The local player id is never used (China was alive again at
  T913 while it read -1 at T916), and the run keeps the player id of its first snapshot: a snapshot for
  another player waits for the human. The end runs no model call and no review: autoplay is stopped,
  two `autoplay-status` reads 60 s apart tell whether the game keeps playing all-AI turns by itself
  (the report then says to exit to the main menu; nothing is sent), then a `campaign_end` event
  (`result` lost, `last_city_turn`, `seen`, the signal and the report: the cities lost with their
  turns, our military against the strongest enemy at war, the gold and faith stranded, the decisions
  made after the loss was seen), a journal line, the run's `lost` status in telemetry, `info.end`
  (`result`, `turn`, `seen`, `signal`, `report`) and the status `ended` while the process lives. A new
  run on the campaign ends at its start while the signal holds. The dashboard shows it through
  feat/dashboard-v2; until then the run reads as not running with the event in Activity.
- **Strategy**: `corpora/civ6/pillars.toml` in share mode (science, culture, faith, economy,
  military, expansion, diplomacy) with milestones on turns (`T60`); reviews as for Stellaris.
  Military targets are relative to the majors we have met (postmortem-fixes design, ruling 18;
  `[strategy] relative_military`): the metrics rows and `[metrics] names` gain `military_vs_median`
  (ours ÷ their median) and `military_vs_strongest` (ours ÷ the strongest that is not our ally), the
  briefing says "peers are the N majors we have met" with both ratios and our rank, and a Strategist
  answer is sent back once when, while our military is weak (ruling 1's `low` or `last`), the military
  pillar holds no milestone on one of them at 0.5 or more, when an absolute `military` target is under
  0.5 x the median, or when a `rank:*` milestone ranks us among fewer than 3 majors (pinned pillars and
  human edits are exempt). A goal that names a word of `[strategy] unpursuable` (peace, ceasefire,
  alliance, friendship, denounce; plurals too) is sent back once, "no order can pursue it: the game's AI
  handles diplomacy during autoplay" (ruling 25: "Get peace with Australia" was the goal at T563, T565
  and T575), and the military stance's exit condition at war is a city retaken, the enemy's strength
  below ours, or the war ending (to watch, not a goal). **Weakness** (ruling 1, `src/pilot/threat.py`): at war with a major, our
  military last of the met majors (2+ met), under `weak_median_share` (0.6) x their median, or a met
  major that is not our ally at `strong_neighbour_ratio` (2.0) x ours (both in `[actions.purchase]`;
  a major without the snapshot's `allied` field counts as not allied). Replayed on the Kublai rows it
  holds in every row from T380 to T540 (the design's E1).
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
  an end target), whose status (met, on track, at risk, missed) comes from telemetry. A milestone is
  judged on one value (postmortem-fixes design, ruling 17): the latest metrics row at or before today
  and not before its `set`, the date the governor stamped when it published the strategy (a milestone
  with the same metric, op, target and `by` as in the previous version keeps its earlier `set`; the
  Strategist neither sees nor writes it); once `by` has passed, the latest such row at or before `by`
  (a target met on its date stays met after a later dip). That value meeting the target is *met*;
  otherwise *missed* once `by` has passed, else *on track* or *at risk* from its projection over the last 12 steps; no
  reading since `set` is *at risk*. A value met in the past no longer counts ("military >= 170 by
  T350" read met at T350 with 124 before). "milestone missed" fires once per milestone per run;
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
crisis over; at most one per `[time] review_cap` steps of the game's clock: 12 months in Stellaris, 5
turns in Civ VI, where a new war or a lost city always reviews and a new war does in Stellaris too,
restarting the count) and on *Review strategy now*. Every time constant the shared code uses is named
in the game's own unit in `[time]` of its `pillars.toml` (`unit`, `review_cap`, `review_exempt`,
`milestone_lookback`, `score_horizon`; postmortem-fixes design, rulings 15 and 19), and log and prompt
text print the unit ("within 5 turns of the last event review"). An
answer is validated; an invalid one gets one corrective retry with its errors and the rejected
answer, then the strategy stays. Reviews started at the beginning of a run or by you must name the
species traits the strategy builds on. A review may add up to 3 rules to
`corpora/stellaris/learned/strategy.md`, read by later decisions. A rule (from a review or the
`remember_rule` tool) whose text or why matches a pattern of `[learned] refuse` in the game's `pillars.toml`
(both are written to the file) is refused and the model gets the reason (postmortem-fixes design, ruling 29). Civ VI refuses the false
rules the Kublai campaign learned: saving until the balance is double the unit cost (a defender may
spend down to the reserve), "cannot buy land units with faith", and "not allowed" in cities in danger
(the refusals were Oil units; a Modern AT or Machine Gun was buyable). The rules already in the live
learned file are corrected on `main` at deploy, each with its post-mortem evidence (the file is the
campaign's history); a test keeps every refused phrase out of the learned files.

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
directory; `PILOT_CAMPAIGN` overrides). Each decision is scored against the empire `[time]
score_horizon` steps later (12 months in Stellaris, 12 turns in Civ VI). A run whose campaign ended
(`campaign_end`) keeps the status `lost` in `runs` after it stops. The JSONL logs in `runs/<id>/` are the raw record; `python -m pilot
rebuild-telemetry` recreates the database. Curated knowledge (`learned/`, strategy, journals) is
committed.

## Galactic Civilizations IV episodes

`python -m pilot run --game galciv4` runs the controller's autopilot and, at each turn it cannot
end by itself, gives the model the screenshot and the controller tools for one episode. Decisions
follow `corpora/galciv4/strategy.md`; see [AGENTS.md](../AGENTS.md) for the decision procedure.

# Game Pilot dashboard v2: design with rulings

Date: 2026-09-27. Status: approved in a hands-off run (2026-09-27), with one ruling changed at approval: the
auth deploy restarts the live pilot instead of adding a firewall rule (ruling 36, runbook step 0). Target: `src/pilot/dashboard.py`, `src/pilot/static/dashboard.html`,
a new `src/pilot/auth.py`, `src/pilot/static/pair.html` and `signin.js`, `src/pilot/pair_words.txt`, per-game
view files under `corpora/<game>/`. Inputs: the UI audit (`ui-audit/`, main at 469cd14 and after the 09:24
restart), the prioritized requirements (M1-M7, S1-S8, L1-L6), the branch deltas, the current-auth analysis, and
the three auth proposals with the passphrase proof of concept, re-judged by three judges who each read all three
(auth rulings 34-52 were rewritten for that verdict). This is a refinement of the existing page, not a rebrand:
the tokens, the two typefaces and the light/dark themes stay.

Marking: **(unverified)** means nobody has checked it on the live system or in code; everything else is taken
from the audit files or was re-checked in the repo on 2026-09-27 (listed under "Checked for this design").

---

## Evidence

### What the audit found (the page, today)
- **The governor stops and nobody notices.** `needs_attention` fired 22 times across 42 runs. The Civ VI stop at
  T57 waited 412 min overnight; Stellaris ran ungoverned 2274.09 → 2282.08 after one agent timeout. 14 of the 15
  Civ VI stops were "autoplay did not start" and one Resume cleared each within 0.4-2.9 min. The banner says
  only "The run needs attention: see Activity, then Resume". The reason exists only as an event
  (`governor.py:808` never puts it in `/status`), and on a phone it is ~4,300 CSS px down.
- **Civ VI is the live game and most of the page is wrong for it.** 3 of 5 readout cells are empty or wrong
  ("Directive none", "Standing –", "a decision every 12 months" while `info.decide_turns = 5`). The chart is
  hard-coded to Stellaris resources: empty series, a NaN y-axis, 3 console errors per render, x-ticks at
  `turn/12`. Neighbours show `CIVILIZATION_GERMANY` with every cell "–". The PC chip says "no game open"
  (`GAME_WINDOWS`, `dashboard.py:208`, knows only Stellaris and GalCiv).
- **Decision rows are inverted.** For Civ VI the machine output (`orders (` + the whole outcome string, including
  Rust error chains such as `Error: Failed /tuner/lua Caused by: 0: …`) is bold and unbounded; the model's
  reason is clamped to 2 lines under it. Rows are 170-450 px tall on desktop, ~600 px on a phone. Outcomes say
  "12 months later: +1 techs" while the stored result hides `military −226`.
- **Failures are unreadable.** `trace.error` (for example a Gemini 503) is never rendered; the fallback chain
  exists only as Activity JSON. 10+ event kinds print raw JSON (`turn`, `strategy_action`, `model_fallback`,
  `briefing_error`, `recover_probe`, `last_stand_check`, …). Across runs: 249 `model_retry` (3,935 s of
  waiting), 75 `model_fallback`, 32 `episode_error`.
- **Campaign bleed.** With a Stellaris or GalCiv campaign picked, the readout still shows the live Civ VI date and
  governor line; Reasoning keeps the previous campaign's decision; history-mode Activity loads the newest run,
  not the chosen campaign's.
- **Hierarchy.** The loudest element (46 px serif date) is the least actionable. System states are written in the
  model's serif. Strategy opens on an 18 px serif wall.
- **Phone (390 px).** Horizontal overflow (405-956 px), Neighbours jumps above the chart (`#p-nb` has no
  `order`), a 125 px sticky bar with Pause and Stop side by side, a 10,000-15,000 px page, 18 px tap targets.
- **Contrast.** Dark passes. Light fails AA for small text: muted 3.33:1, accent 3.33:1, links 3.25:1, warn
  3.57:1 on `#ece9e1`.
- **Keyboard.** 73-105+ chart marks are each a tab stop; tabs lack `aria-controls` and arrow keys.

### What the learnings add
- Civ VI orders (153): 103 held, 14 replaced by the AI, 18 unknown (tuner timeouts), 18 refused. Trader orders:
  0 of 17 held. Civ VI decisions: 71 of 95 urgent; median 63 s, p90 167 s, max 336 s (Stellaris median 14 s).
- 63 of 95 Civ VI decisions were answered by the fallback `gemini-3.1-pro-preview`, not the model the page names.
- The model list was edited 75 times during 503 outages, including duplicate entries; a billing error made the Anthropic
  provider's calls fail repeatedly until removed.
- "Review now" was used 13 times; several reviews were rejected before one was accepted; 32 urgent reviews were
  skipped "within 12 months of the last event review", 30 of them in the turn-based Civ VI run.
- Stellaris campaigns span 7-11 runs; a failed Civ VI start left an empty GalCiv campaign.

### What the branches add (and do not show)
- `feat/civ6-levers` (merged into main at 469cd14) publishes `order_outcome`, `order_followed`, `last_stand`,
  `last_stand_off`, `last_stand_check`, `turn.note`, a new `status = "last stand"`, `info.order_record`,
  `metrics[].idle`, trace `orders[]`/`retried_for`, and `/api/strategy` `spec.orders` + purchase rules. The page
  renders none of it except two feed lines; `order_outcome`/`order_followed` are in `QUIET`.
- Reserves (`gold_reserve_now`, `faith_reserve_now`) exist only in prompt text. `popups_quieted` is dropped by
  the pilot. `PILOT_LAST_STAND` (off by default, max 3) is not in `state.info`, so the UI cannot tell whether a
  stand is armed.
- `feat/stellaris-levers` changes no dashboard file. Its market, crisis inputs, postures and directive policy
  report are controller/briefing fields the pilot does not read yet; crisis itself (levers rulings 12-15) is
  not implemented.

### What auth costs today
- One master key: in the URL (`/?key=`), in every browser's cookie for 400 days (the cookie value **is** the
  key, `dashboard.py:134`), in the service journal on every start (7 copies), in chat apps it was pasted into.
- Each browser, profile, phone and in-app browser needs the link again ("still cannot access": Brave). The
  locked page has no viewport meta, no dark mode, developer words, and a `method="get"` paste box that puts the
  key in the URL ("what is this now?!?"). A wrong key renders the identical page.
- No per-device sign-out or revocation; rotating means deleting the file and restarting both services, which
  stops a live campaign (`game-pilot.service` is `Restart=no`).
- Plain HTTP on a shared, domain-managed /24; the cookie also reaches other services on the host (:3000, :8200,
  :9120) because cookies are not isolated by port. The live pilot binds `0.0.0.0:8790` with no override
  (`config.py:67`). The `Origin == Host` check does not stop DNS rebinding.

### Checked for this design (2026-09-27, read-only)
- `git log main..feat/civ6-levers` is empty: the Civ VI branch is fully merged. `feat/stellaris-levers` has 5
  commits not on main, the newest `09077d9` (date-stall watchdog) touching `governor.py`/`game.py`: it emits
  `stall` and `self_paused` and calls `_needs_attention` with the stall's screenshot path. No dashboard file.
- `Civ6Game.screenshot()` returns `None` by design (`civ6.py:143`), which is why Civ VI has no frames.
- `describe()` (`dashboard.html:1229-1254`) has no case for `turn`, `strategy_*`, `model_fallback`,
  `briefing_error`, `recover_probe`, `recovered`, `last_stand_check`, `stall`, `self_paused`.
- `corpora/galciv4/` has no `pillars.toml`; Stellaris and Civ VI do.
- `telemetry.score()` uses `after_months=12`, and `month_index("T307") == 307`: for Civ VI the window is 12
  **turns**, labelled "months".
- `.venv` has Playwright 1.63 (not in `pyproject` dev deps) and no QR library. `scripts/ci.sh` runs `pytest -q`.
  `tests/test_dashboard_security.py` has 14 tests.
- Light-mode contrast re-measured (WCAG formula) for the replacement values in ruling 33.

---

## Design plan (token plan, reviewed against the brief)

### Subject, audience, job
A remote cockpit for an AI that governs a strategy game on the user's own desktop PC. One operator, hands-off,
checking in from Chrome, Brave and a phone, often by tapping a link in another app. The page's job, in order:
(1) say whether the governor needs the human, and what to do; (2) show what it decided and whether it worked;
(3) let the human steer (talk, strategy, settings).

### Color (kept; names for their jobs)
| Token | Dark (identity) | Light (reading mode) | Job |
|---|---|---|---|
| Deep-space plane | `#0e1220` | `#ece9e1` | page |
| Surface | `#141a2a` | `#f8f7f3` | the one filled block (attention card), dialogs, selected row |
| Ivory ink | `#efeadd` | `#1b1d29` | text |
| Amber | `#f0b34a` | `#a9741b` → **`#8a5a10`** | selection, focus, brand. Never a state. |
| Sensor teal | `#63d1c6` | `#1f8f86` → **`#156f68`** | links, data read from the game, tool calls |
| Thought violet | `#b8a6ff` | `#6b52c9` → **`#5b43b8`** | the model at work (deciding, thinking) |
State colors stay `--good` / `--warn` / `--bad`; light values darken (ruling 33). Two derived tokens, no new hues:
`--attn-bg: color-mix(in srgb, var(--warn) 12%, var(--surface))`, `--alarm-bg: color-mix(in srgb, var(--bad) 12%, var(--surface))`.

### Type
- **Bricolage Grotesque** is the system's voice: states, labels, figures (tabular), buttons, errors, the
  governor line. Optical size axis: 14 for body, 36 for the governor line.
- **Fraunces** is the model's voice, and only that: reasons, thinking, stances, Talk replies, the strategy
  summary. Never for banners, errors or system states.
- **Mono** only for raw machine text (error chains, ids, JSON), always inside a disclosure.
- Scale from 15 px: 12.5 / 13.5 / 15 / 17 / 20 / 24 / 30. Governor line 24 px/600 (20 px on a phone); figures
  22 px/500 tabular; serif reason 16 px/1.55; reasoning headline 30 px serif. Left-aligned everywhere;
  line length ≤ 68ch for serif, ≤ 80ch for sans.

### Layout concept
One sentence at the top tells you whether you are needed; everything under it is evidence.
```
bar      ● Game Pilot  [campaign ▾]                      PC chip   [Pause] [Settings] [⋯]
governor ▌ The AI is playing T307 → T310. Next decision at T312.            (the hero)
         ▌ every 5 turns · answered by Gemini 3.1 Pro (fallback)
body     figures + chart + decisions (evidence)  │  reader tabs (reasoning, orders, strategy, talk, activity)
```

### Principles
1. The governor's state is the hero; the date is context inside it.
2. Serif is the model talking; sans is the system; mono is raw machine output behind a disclosure.
3. Each game speaks its own units and nouns, from data. A cell a game does not have is hidden, never "–" or "none".
4. Every stop shows its reason, its age, what it costs, and the next action, in that order.
5. The phone is its own layout, not the desktop stacked.

### Review against the brief (what was generic, what changed)
- **The 46 px serif date with a small label** is the default "big number, small label" hero, and it answers
  nothing. Changed: the governor line is the hero; the date moves into it.
- **Light theme = the cream + serif + amber cluster.** The brief says keep the identity, so it stays, but dark
  is declared the identity (it is the room the page is watched in, and it passes contrast) and light becomes a
  reading mode whose text tokens are darkened to pass AA. No new palette.
- **Hairline broadsheet sections** are kept (they are the page's structure and cheap on a phone), but the page
  gets exactly one filled block, the attention card, so "needs you" cannot be mistaken for another section.
- **Middle-dot meta strings** (`t-meta`, `facts`) join unlike things. Changed: labelled pairs ("Answered by",
  "Took") where the items are different kinds; the dot stays only between items of one kind.
- **Chips everywhere** would be the SaaS kit. Changed: the pill shape means one thing only, "an order and its
  fate"; figures are unboxed text.
- **Numbered markers** appear only where the content is a sequence: recovery steps.
- **Motion:** one moment only, the governor line changing state (height and edge color, 200 ms, off under
  reduced motion). No pulsing on "needs you": the title and favicon carry it instead.

---

## Rulings

Format: **Decision.** *Why.* *Cost if wrong.*

### A. Information architecture across the three games

**1. One page, the same destinations for every game and width.** Desktop: left column = Now (figures, chart,
game health) and the Decisions list; right column = reader tabs **Reasoning · {Levers} · Strategy · Talk ·
Activity**. Phone: bottom nav **Now · Decisions · {Levers} · Strategy · Talk**; Activity is the last section of
Now ("Recent problems" plus "All activity"), and Reasoning opens as a full-screen sheet from a decision.
*Why:* the operator's questions are the same across games (does it need me, what did it do, did it work); one
map is learned once. Talk must be one tap away because questions time out (S7). *Cost if wrong:* Activity is
one more tap on a phone; if the operator lives in Activity, promote it in place of Strategy in the phone nav
(one line of config).

**2. Each game describes itself in `corpora/<game>/dashboard.toml`, served by `GET /api/view?campaign=`.** The
file holds: game name, time unit (`turn` | `month`), date format, cadence field (`decide_turns` |
`every_months`), decision noun, levers kind and label, whether frames exist, figures (key, label, rank key,
reserve key), chart views and series, outcome keys and window label, rival columns, trigger categories, and
recovery steps per stop category. Sketch:
```toml
# corpora/civ6/dashboard.toml
[game]
name = "Civilization VI"
time_unit = "turn"                 # dates "T307"; cadence "every 5 turns"
cadence = "decide_turns"
decision_noun = "orders"
levers = "orders"                  # orders | actions | screen
levers_label = "Orders"
frames = false                     # true once Civ6Game.screenshot captures (ruling 7)
rivals_label = "Civilizations met"

[[figures]]  key = "rank:score"    label = "Score"    kind = "rank"
[[figures]]  key = "rank:military" label = "Military" kind = "rank"
[[figures]]  key = "techs_known"   label = "Techs"    rank = "rank:techs"
[[figures]]  key = "civics_known"  label = "Civics"   rank = "rank:civics"
[[figures]]  key = "cities"        label = "Cities"   rank = "rank:cities"
[[figures]]  key = "gold"          label = "Gold"     keep = "reserves.gold_keep"
[[figures]]  key = "faith"         label = "Faith"    keep = "reserves.faith_keep"

[chart.yields]   label = "Yields"   series = ["science", "culture", "faith_yield", "gold_yield", "production"]
[chart.balances] label = "Balances" series = ["gold", "faith"]
[chart.rank]     label = "Rank"     series = ["rank:score", "rank:military", "rank:techs", "rank:civics"]  # inverted axis

[outcomes] keys = ["score", "military", "science", "techs_known", "civics_known", "pop"]  window = "{n} turns later"
[rivals]   columns = ["score", "military", "cities", "at_war"]

[recovery.transient]    title = "Autoplay did not start"
steps = ["Press Resume. This cleared 14 of 15 such stops.",
         "Still stuck: look at the game for a popup or a movie, click it away, then Resume."]
[recovery.screen]       title = "Something on the game screen is holding the turn"
steps = ["Look at the PC: a wonder movie or a leader scene can hold the turn.", "Click through it, then Resume."]
[recovery.unreachable]  title = "The game does not answer"
steps = ["Check the game is running with the tuner on (EnableTuner 1) and a game is loaded.", "Then Resume."]
[recovery.game_changed] title = "A different game is loaded"
steps = ["Load the campaign's save, or start a new run for this game.", "Then Resume."]
```
Stellaris gets `time_unit = "month"`, `cadence = "every_months"`, `levers = "actions"`, its current resources
and Neighbours columns and a `stall` recovery entry (from the watchdog). GalCiv gets `time_unit = "turn"`,
`levers = "screen"`, `frames = true`, no figures file keys it lacks. A pytest checks every metric key against
`pillars.toml [metrics].names` where that file exists, and every recovery category against the categories the
governors emit. *Why:* game knowledge stays out of code (AGENTS.md §9), and a separate file, not
`pillars.toml`, because GalCiv has no `pillars.toml` and a broken `pillars.toml` turns the strategy layer off;
the view must survive both. *Cost if wrong:* two files per game to keep in step; the test catches drift.

**3. Absent means hidden.** A figure, chart view, rivals table, levers section or readout cell whose data the
game or the running pilot does not publish is not rendered: no "–", no "none", no empty table. The one
exception is an explicit empty state that invites an action (rulings 16, 18). *Why:* 3 of 5 readout cells were
wrong for Civ VI; "–" reads as broken. *Cost if wrong:* a genuinely missing value is silent; the Activity
"Problems" filter still lists `briefing_error`.

**4. Campaigns first, runs second; the picker is honest about what is live.** The campaign control is a button
("Kublai Khan, China · T310", live dot when live) that opens a list: one row per campaign with game, leader or
empire, state (live, paused, stopped), last date sorted by `month_index` (fixes `MAX(date)` returning "T99"),
run count; empty campaigns (0 decisions, 0 metrics) sit under "Show empty campaigns". On a phone the list is a
full-screen sheet. Switching campaign clears Reasoning, loads that campaign's own events for Activity (not the
newest run's), and hides every live-only element unless the chosen campaign is the live one. In history mode
the governor line reads "Viewing a past campaign: last played 2288.08, stopped 26 Sep. Live now: Civ VI T310"
with a link to the live one. *Why:* audit 3.3; S6. *Cost if wrong:* one more tap to switch; the list is
short (6 campaigns today).

### B. Header and status

**5. The bar carries identity, place and exits, nothing else.** Desktop, 48 px sticky: brand, campaign button,
PC chip, **Pause/Resume** (live only), **Settings**, and a **⋯** menu (Stop…, Start run, Add a device, Devices,
Sign out). Phone, 52 px sticky: brand dot, campaign short name with date, a state dot, and ⋯ (which holds Pause,
Stop…, Settings, Add a device, Sign out). Stop always confirms with game-specific words: Civ VI "Stop the run?
The AI finishes this turn and the game stays at T310." Stellaris "Stop the run? The game is paused and the
governor stops." *Why:* the phone bar was 125 px with Stop next to Pause; nothing in the bar needed to be
there except the exits. *Cost if wrong:* Pause is one extra tap on a phone; Resume is still one tap from the
attention card (ruling 7).

```
desktop
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ● Game Pilot   [● Kublai Khan, China · T310 ▾]      ● mini-rig2 · Civ VI in front   [Pause] [Settings] [⋯] │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
phone (390)
┌──────────────────────────────────────┐
│ ●  Kublai Khan · T310 ▾         ●  ⋯ │
└──────────────────────────────────────┘
```

**6. The governor line is the hero: one sentence per state, then one line of facts.** Full width under the bar,
a 4 px left edge in the state color, 24 px Bricolage 600 (20 px phone), not sticky. `role="status"`, announced
only when the state changes. Sentences (Civ VI / Stellaris):
| State | Sentence | Facts line |
|---|---|---|
| playing | "The AI is playing T307 → T310." / "The AI is playing 2288.08, fast speed." | "Next decision at T312 (every 5 turns). Last turn 42 s." / "Next decision 2289.08 (every 12 months)." |
| deciding | "Deciding T310: 1 min 12 s." | "Gemini 3.1 Pro, call 2 of 4, after 3.8 Flash was overloaded." Retry countdown when waiting. |
| needs you | "Needs you: autoplay did not start at T57." | "Waiting 6 h 52 min. The game is stopped at T57." then the card (ruling 7) |
| paused (by you) | "Paused by you at T310, 4 min ago." | Resume button inline |
| last stand | "Last stand in Chengdu, T88: step 2 of 3." | "City strike took; ranged attack next." |
| starting | "Starting: loading the Civ VI library." | |
| no run | "No run is playing. Last: Civ VI, Kublai Khan, T310, stopped 09:24." | Start run button inline |
The date is part of the sentence; the old readout row is removed (its Directive cell moves to Stellaris figures,
its Pace cell into the facts line, which opens Settings > Game). The facts line always says who answered:
"Answered by Gemini 3.1 Pro (fallback)" when the last decision used a fallback. *Why:* M1, M5; the operator's
first question is "does it need me". *Cost if wrong:* the date is smaller; it is still the first figure in the
sentence and in the tab title.

**7. Needs you is a card with reason, age, cost, recovery and one primary action.** `/status` gains
`info.attention`:
```json
{"reason": "autoplay did not start after 2 tries", "category": "transient",
 "since": 1790283771.2, "date": "T57", "date_now": "T57",
 "auto_recover": true, "next_probe_at": 1790283831.2, "probes": 3,
 "errors": ["tuner did not answer (timed out) at /tuner/lua", "autoplay start not confirmed"],
 "frame": "frame.jpg?t=1790283771"}
```
The governors set `category` at each call site (`transient`, `screen`, `unreachable`, `game_changed`, `stall`,
`control_failed`); nothing parses text. `errors` holds the last ≤3 errors behind the stop, each cut to its cause
(ruling 30). Card layout:
```
┌▌──────────────────────────────────────────────────────────────────────────────────────┐
 ▌ Needs you: autoplay did not start at T57                                 waiting 6 h 52 min
 ▌ The game is stopped at T57. Nothing is lost; the campaign waits for you.
 ▌ Trying again by itself every 60 s: 3 tries so far, next in 0:41.
 ▌
 ▌ 1  Press Resume. This cleared 14 of 15 such stops.
 ▌ 2  Still stuck: look at the game for a popup or a movie, click it away, then Resume.
 ▌
 ▌ [ Resume ]   [ Capture the game screen ]      What happened ▸ (3 errors, raw text)
 ▌ ┌ last frame, if any ─────────────┐
└▌──────────────────────────────────────────────────────────────────────────────────────┘
```
Cost line per game: Civ VI "The game is stopped at T57" (autoplay stops, so wall time is the cost); Stellaris
"The game ran on without the governor: 2274.09 → 2282.08" when the date moved, or "unknown since the stop"
when the agent is unreachable. Resume is the primary button; "Resumed" is the toast. "Capture the game screen"
calls `POST /api/capture` (read-only for the game: an agent screenshot, stored as the run's frame, attributed
to the device); for Civ VI this needs `Civ6Game.screenshot()` to use the controller's screenshot instead of
returning `None` **(unverified that a capture during autoplay is harmless)**. The recovery steps come from
`dashboard.toml [recovery.<category>]`. When the pilot is older than this change and sends no `attention`,
the card falls back to the newest `needs_attention` event's reason and time. *Why:* M1, M2; 14 of 15 stops
needed only Resume, 2 needed eyes on the screen. *Cost if wrong:* the category is wrong for an unforeseen
failure: the card then shows the reason with the generic steps ("Look at the game, then Resume").

**8. Signals outside the page: title and favicon always, a push only when opted in.** The `<title>` mirrors the
state ("Needs you – T57 – Game Pilot", "Deciding – T310 – Game Pilot", "T310 – Game Pilot"); the favicon is an
inline SVG dot in the state color (amber brand dot when playing, `--warn` with a notch when needs you). A
server-side notifier in the pilot posts to an ntfy topic (`PILOT_NOTIFY_URL`, off by default) when needs-you
lasts 5 min, again at 30 min and 2 h, and once on recovery. The message carries no credential and no secret:
"Game Pilot needs you: Civ VI, autoplay did not start at T57 (5 min)", with the plain dashboard URL as its
click action. Web Notifications and Web Push are not used before TLS: both need a secure context and
`http://192.168.1.76` is not one. *Why:* M1; the 412-minute stop happened with no page open. *Cost if
wrong:* the ntfy topic leaks "a Civ VI run is stuck" to whoever guesses it; use a self-hosted server or a long
random topic **(unverified: which ntfy server the user wants)**.

**9. Model health appears only when it is bad, and names the model that answered.** The facts line always
names the answering model. When, in the last 60 min, more than 1 of the last 5 calls fell back or failed, a
second line appears under the governor line: "Gemini 3.8 Flash is overloaded: 3 of the last 5 calls fell back
to 3.1 Pro." Billing and auth errors ("credit balance too low", 401/403) are marked in Settings > Models on
that model's row with "Remove from list". The Models editor refuses duplicates. Source: `GET /api/health?run=`,
computed in the viewer from the run's `model_retry`/`model_fallback`/`episode_error` events, so it also works
for history. *Why:* S1; 75 settings edits during outages, duplicates, a billing loop. *Cost if wrong:* a
flapping provider makes the line come and go; it is debounced to change at most once per minute.

**10. The PC chip tells the truth, including its own uncertainty.** It shows host, agent version and the game in
front: "mini-rig2 · Civ VI in front · agent 1.6.1". `GAME_WINDOWS` gains Civilization VI. States: on (game
named), on (no game), "busy" (the 3 s `/api/pc` call timed out while the live run finished a turn in the last
60 s), "not answering" (timed out otherwise), "offline" (connection refused). A 401 is never shown as offline:
it goes to the signed-out banner (ruling 46). *Why:* M5; the chip was wrong both ways. *Cost if wrong:* "busy"
may mask a real hang for up to 60 s; the governor line and attention card are the authority for that.

**11. Deciding shows progress.** `info.deciding = {since, model, attempt, max_attempts, retry_at, trigger}`,
set by the governor at each attempt. The governor line ticks elapsed time (text only, once a second, not
announced); on a retry wait it shows "Retrying in 0:12". *Why:* S2; Civ VI decisions take a median 63 s and
up to 336 s with "Deciding now" as the only sign of life. *Cost if wrong:* none beyond a few fields.

### C. Per tab

**12. Now: figures, chart, game health, recent problems.** Figures come from `dashboard.toml [[figures]]`: value
large, label under, rank or reserve as a subline ("#4 of 4, median 42"; "keeps 150"). A figure behind the
median gets its subline in `--warn` with the words "behind the median", never color alone. For Stellaris the
first figure is the Directive (with postures, ruling 26) and the second is Standing. Game health is one line,
shown when something is off (Civ VI: "Popups quieted 6 of 6 at T162 · tuner 3 timeouts in the last 40 calls ·
last turn 42 s"; it turns `--warn` when a popup failed to quiet or a turn was held). Recent problems lists the
last 5 problem events as sentences with "All activity". Desktop and phone:
```
desktop, left column
┌ Score        Military     Techs         Civics        Cities       Gold            Faith          ┐
│ #1 of 4      #1 of 4      40            38            9            412             90             │
│                           #4, behind    #2            #2           keeps 150       keeps 60 for   │
│                           the median                                               a pantheon     │
├ Yields over time          [Yields] [Balances] [Rank] [Table]                                       ┤
│  ╭──────╮ science … culture … faith … gold … production                                          │
│ ─┴──────┴──────────────────────────────────────────── T250  T275  T300                            │
│  ▏ ▏▍ ▏  ▏▍▏ ▏  ▏  decision ticks on the axis (urgent = taller), ◆ reviews in their own lane        │
├ Decisions                                    95 decisions, 71 urgent        [Problems only]      ┤
│  …rows, ruling 27…                                                                                │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘

phone, Now
┌──────────────────────────────────────┐
│ ▌ The AI is playing                  │
│ ▌ T307 → T310                        │
│ ▌ Next decision at T312              │
├──────────────────────────────────────┤
│ Last decision, T307, urgent          │
│ “Chengdu is under siege; buy a       │
│  slinger with faith and keep…”       │
│ 3 held · 1 replaced · 1 refused  ›   │
├──────────────────────────────────────┤
│ Score #1   Military #1   Techs 40    │
│ Civics 38  Cities 9      Gold 412    │
├──────────────────────────────────────┤
│ Yields  [chart, full width]          │
├──────────────────────────────────────┤
│ Recent problems                      │
│ Tuner did not answer (T305)          │
│ All activity ›                       │
├──────────────────────────────────────┤
│  Now  Decisions  Orders  Strategy  Talk │  56 px + safe area
└──────────────────────────────────────┘
```
Chart: series from the spec; ticks in game units (turns: T250, T275; months: 2285, 2286); decision marks are
short ticks on the x-axis (urgent taller, error in `--bad`), full-height only for the selected or hovered one;
strategy reviews get their own lane above the plot, never on the directive-lane labels; last stands are
`--bad` marks; war and crisis spans are bands. The chart is one tab stop (a `role="group"` with arrow keys
moving between marks, Enter selects the decision). The Table view scrolls inside its own box. An empty series
never reaches the axis code (fixes the NaN). *Why:* M3, audit 3.4-3.6. *Cost if wrong:* the tick-only marks
hide how dense decisions are; the Decisions count and the "urgent" filter carry that.

**13. Decisions: see ruling 27.** On a phone the list is its own destination; tapping a row opens Reasoning as
a sheet with a back button and swipe-down to close. *Why:* on a phone Reasoning started ~4,300 px down. *Cost if
wrong:* comparing two decisions side by side needs the desktop.

**14. Reasoning leads with the decision, then why, then the evidence.** Headline (serif 30): Stellaris the
directive ("Kept diplomacy first"); Civ VI the first sentence of the model's reason, never the word "orders".
Under it, labelled pairs in sans: "Trigger: city threatened (Chengdu)", "Answered by: Gemini 3.1 Pro after 3.8
Flash was overloaded (503 ×3)", "Took: 63 s, 41k tokens in". Then the orders as a list with fate chips (ruling
28), badges "filled by the governor", "bought with faith", "asked again: research left idle" (`retried_for`).
For an error decision: a `--bad` block in sans "No decision: every model failed. Gemini 3.8 Flash overloaded
(503 ×3) → 3.7 Flash overloaded → 3.1 Pro overloaded", with the raw `trace.error` in a disclosure. Then the
existing prompt / thinking / tool calls / answer steps. On desktop the tab panel no longer scrolls inside
itself: the right column is sticky and the page scrolls. *Why:* audit 3.2; `trace.error` is never shown.
*Cost if wrong:* long traces make the page long; each step is collapsed after the first two.

```
┌ Reasoning  Orders  Strategy  Talk  Activity ──────────────────────────┐
│ T307, urgent                                                          │
│ Chengdu is under siege; buy a slinger with faith.        (serif 30)    │
│ Trigger  city threatened (Chengdu)                                    │
│ Answered by  Gemini 3.1 Pro, after 3.8 Flash was overloaded (503 ×3)   │
│ Took  63 s · 41k tokens in, 1.2k out                                  │
│                                                                       │
│ Orders                                                                │
│ (✓ research Writing)  (↺ production Chengdu: Slinger → AI chose Trader)│
│ (✕ purchase Gurdwara: 380 faith, over the 283 allowed)                 │
│ (? civic Foreign Trade: no reply from the game)                       │
│                                                                       │
│ The model's reason (serif 17.5, full)                                 │
│ ▸ What the model was shown   ▸ Thinking   ▸ Tool calls (4)   ▸ Answer   │
└───────────────────────────────────────────────────────────────────────┘
```

**15. Levers tab: one label per game, contents per game.** Civ VI "Orders" (ruling 19-22), Stellaris "Actions"
(rulings 23-26), GalCiv "Screen" (the latest frame, the last blockers the autopilot cleared, and "Capture the
game screen"). The frame panel is removed from the left column; frames live here and in the attention card.
`/frame.jpg` is polled only when the spec says `frames = true` or `info.frame_at` is newer than the last fetch
(fixes the 404 every 10 s). *Why:* M6; the frame panel said "No screen captured yet" forever for governor games.
*Cost if wrong:* GalCiv players look one tab further for the frame; for GalCiv the Screen tab is selected by
default.

**16. Strategy: pillars first, summary folded.** Top: focus line and "Where the effort goes" as one stacked bar
(share mode: Civ VI, GalCiv) or the "by pressure" ranking (exclusive mode: Stellaris). The strategy summary
("Built on") folds to 3 lines with "Read all", markdown lists render as lists. Pillar rows: name (serif 17),
then in share mode "34% of effort" with a bar, never "rank" or "pressure"; in exclusive mode "weight 30 ·
need ×1.5 · pressure 45" with the share bar. Goals and milestones use readable names ("Trader", "Commercial Hub"),
dates in game units. Weight edits preview how the other unpinned weights rescale before Save. "Review now"
shows its result next to the button: "Accepted: science 30 → 35, culture 20 → 15" or "Rejected: missing pillar
defence (sent back once)". Skipped reviews are listed with the next eligible time in game units ("next after
T318"). A crisis badge shows on the defence pillar and at the top (ruling 25). *Why:* S3, S8, audit 3.4. *Cost
if wrong:* the summary is one tap further; it was a 20-line wall.

**17. Talk: game words, an empty state, questions with deadlines.** Placeholder per game ("Ask why it chose these
orders" / "Ask why it chose this directive"). Empty thread: "Nothing said yet. Ask the governor why it did
something, or leave a note it will read at the next decision." "Decide now" help per game: Civ VI "Decides
before the next autoplay turn"; Stellaris "Pauses the game and decides now". Override stays Stellaris-only. A
pending question moves from the top banner into Talk's head and into the governor line ("Question for you:
prepare for war with the Fallen Empire? No answer in 0:31 means: no."), which needs `question_deadline` and
`default_if_silent` in `/status`. *Why:* S7; `ask_human_timeout_s = 45`. *Cost if wrong:* a question is seen
only in the governor line on other tabs; that line is always visible.

**18. Activity: a sentence for every kind, grouped, filterable, raw on request.** Every kind gets a sentence
(table in ruling 29); the default case renders "Unrecognised event: <kind>" plus a disclosure, never inline
JSON. Repeats group ("Learned 3 rules", "Tuner did not answer, 4 times, T301-T305"). Filters: Problems, Orders,
Model, You, All (default Problems when a stop is open, else All). Each row has its time in game units and wall
time, and a disclosure with the raw event. `order_outcome` and `order_followed` stay out of the feed and go to
the Orders tab. Long strings wrap (`overflow-wrap: anywhere`). History mode loads the chosen campaign's events
once, then only new ones. *Why:* S4, audit 3.5, 3.7. *Cost if wrong:* grouping hides an interleaving that
mattered; the disclosure keeps each raw event.

(The Levers contents are rulings 19-22 for Civ VI and 23-26 for Stellaris.)

**18A. Settings and Start run follow the game.** Three tabs: Models, Game, Devices (ruling 44). Models: role help per game; the "GC4 blockers" role
only when the campaign is GalCiv; model names never truncated (the row wraps on a phone: name on its own
line, thinking and × under it, × is 44 px). Game: fields per game from the spec: Civ VI "Decide every [5]
turns" bound to `decide_turns`, no speed; Stellaris speed plus "Decide every [12] in-game months". Changes still
save at once, with an inline "Saved" per field instead of `alert()`. Start run: game preselected from the PC
chip's game in front, a warning only when the chosen game is not in front, and the toast names the game and
campaign that actually started ("Started Civ VI, Kublai Khan, T310"). *Why:* audit 2 and 3.8 ("in-game months" bound to the wrong field, speed
shown for Civ VI, "GalCiv4" toast, a false "no game window" warning); S1 duplicates. *Cost if wrong:* none.

### D. Civ VI views

**19. Order record: one row per order key, rate only above the sample floor.** Source: `info.order_record` live,
`GET /api/orders?campaign=` when no pilot is live (computes the record from `telemetry.campaign_events(cid,
"order_outcome")` with the campaign's `[orders]` spec). Row: key in words ("Production, replace the AI's
choice"), stick rate as a bar and a number once `judged ≥ min_samples`, counts otherwise ("2 held of 3, too few
to judge"), a "Does not stick here" flag when `weak`, excluded counts in words ("8 refused, 1 lost, 3 no
reply"), the last override inline ("AI replaced Slinger with Trader in Chengdu, T41"). Footer from `spec.orders`:
"Last 30 turns; weak at 50% or less."
```
Orders                                                   last 30 turns · weak at ≤ 50%
Kind                          Stuck     Held / judged   Not judged                   Last override
Research                      ████ 96%  24 / 25         1 no reply
Production, fill empty queue  ███░ 81%  13 / 16         2 refused
Production, replace AI        █░░░ 22%   2 / 9          Does not stick here          Slinger → Trader, Chengdu, T41
Purchase with faith           ████ 100%  6 / 6          8 refused, 1 lost
Trader (any city)             ░░░░  0%   0 / 17         Does not stick here
phone: each kind is a two-line card: name + rate bar, then counts and the flag.
```
*Why:* M6; "see which levers work"; traders 0 of 17. *Cost if wrong:* a rate over few samples misleads; the
floor and the "too few to judge" wording prevent that.

**20. Order log: every order with its fate, linked to its decision.** Under the record, newest first, filter
chips by kind and by fate (Held, Replaced, Refused, No reply, Open). Row: turn, kind icon, item name, city,
fate chip, and for open orders "in force, 3 of 8 turns followed" (from `order_followed`). Tapping a row selects
its decision (`ref`). Backfilled rows carry a small "backfilled" tag; backfill runs are tagged "backfill" and
hidden in run lists. *Why:* M6. *Cost if wrong:* none; it is a read-only list.

**21. Buy-outs: treasury against reserve, what was bought, what was refused.** Needs `info.reserves = {gold,
gold_keep, gold_rule, faith, faith_keep, faith_for}` published by the governor (it computes these for the prompt
today). A two-line block at the top of Orders: "Gold 412, keeps 150 (3 cities in deficit)" and "Faith 90, keeps
60 for a pantheon", with a bar per currency showing reserve and spendable. Below: purchases (the log filtered to
`order_kind = purchase`), each with a gold or faith badge, and refusals with their reason in words ("380 faith,
over the 283 allowed"). Cities `in_danger` are named in red with the defender bought, if any. *Why:* branch
deltas §3; the faith hoarding (38 → 402) was invisible. *Cost if wrong:* the reserve shown can lag one decision
behind the game; it is labelled "at T307".

**22. Last stand: armed state always visible, alarm while running, a report after.** Needs `info.last_stand =
{on, max, in_a_row, off_reason, active}`. Governor facts line: "Last stand: off" or "armed (max 3 in a row)".
While running: status `last stand` becomes the governor line alarm (ruling 6) in `--bad`. After: a card in
Orders: city, turn, `incoming` against garrison and walls HP **(unverified: whether the stand report carries
walls HP)**, each action with predicted damage and read-back ("City strike on Horseman: predicted 28, took"),
and `last_stand_check` results ("2 pins held, 1 moved"). `last_stand_off` is a persistent `--bad` line at the
top of Orders and in the facts line until the run restarts: "Last stand off for this run: <reason>". The
chart gets a `--bad` mark at the turn. **Popups quieted and turn health** live in the Now game-health line
(ruling 12): the governor emits `popups_quieted {entries, turn}` once per library install; the line reads
"Popups quieted 6 of 6 at T162", and turns `--warn` with the failed entries listed; a turn held by a popup sets
attention category `screen` with the popup's name in words. *Why:* branch deltas §1, §4; M2. *Cost if wrong:*
`popups_quieted` arrives only after a load; before that the line says nothing (absent means hidden).

### E. Stellaris levers views

All four render only when the pilot publishes their data; `feat/stellaris-levers` publishes none of it to the
pilot yet, so these are specified now and built when the fields land.

**23. Action record: the Civ VI shape with a months clock.** Same component as ruling 19, keys `directive
<name>`, `market buy/sell <resource>`, `posture <name>`, `crisis <step>`, fates took / held / did not take /
removed / overridden (with the AI's option and date) / locked. The directive policy report
(`Applied {set, locked}`, which `governor.py:1171` discards today) shows in the decision row and Reasoning:
"Applied; 1 policy locked (diplomatic stance: at war)". *Why:* levers design rulings 2-7; M6. *Cost if wrong:*
none until data exists.

**24. Market: price deviation and net trade per resource, and a suspended state.** Needs `metrics[].market =
{kind, fluct, bought, sold, trades_net}`. Actions tab block: one row per traded resource with price vs base
("Alloys 14% above base"), net per month, and the pillar's market order next to it; "Suspended until
recalibrated" badge per levers ruling 6. *Why:* branch deltas §5. *Cost if wrong:* none until data exists.

**25. Crisis: a banner that does not scroll away, and a band on the chart.** Needs `info.crisis = {since, reasons,
step, boost}`. Governor facts line and Strategy top: "War crisis since 2291.03: C1 occupied, C2 lost 2
systems. Step 2 of 4: defensive stance." The defence pillar shows "need boosted ×2 (crisis)". The chart shows
crisis spans as a `--bad` band like war shading. The status-quo question (levers ruling 15) uses the Talk
question path with its deadline (ruling 17). *Why:* levers rulings 12-15. *Cost if wrong:* none until data
exists.

**26. Postures: chips next to the directive.** In the Stellaris Directive figure: "Expand · postures: naval
capacity on", disabled postures greyed with "not enabled" on hover/focus. *Why:* levers ruling 18. *Cost if
wrong:* none until data exists.

### F. The decisions list

**27. A row is the model's reason plus what came of it; machine text never leads.**
```
desktop
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ T307        City threatened: Chengdu                           Gemini 3.1 Pro (fallback) 63 s │
│ urgent      “Chengdu is under siege; buy a slinger with faith and keep science on Writing   │
│             while the walls hold…”                                   (serif 16, 2 lines)     │
│             (✓ Writing) (↺ Chengdu: Slinger → Trader) (✕ Gurdwara: over faith cap) (+2)      │
│             12 turns later: score +17, science +8.1, military −226 ▲ watch                   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
phone
┌──────────────────────────────────────┐
│ T307 · urgent: Chengdu threatened    │
│ “Chengdu is under siege; buy a       │
│  slinger with faith…”                │
│ ✓ 3  ↺ 1  ✕ 1  ? 1        63 s  ›    │
└──────────────────────────────────────┘
error row
│ T307        No decision: every model failed (Gemini overloaded, 503)             95 s         │
```
Anatomy: date (game units) and trigger category (sans 13.5); the model's reason (serif, 2 lines, the primary
text); Stellaris puts the directive label before the reason ("Kept diplomacy first"); Civ VI order chips, at most
one line on desktop with "+N", counts per fate on a phone; the outcome line from `[outcomes]` keys with the
window in game units ("12 turns later"), every key with its sign, and a "watch" flag on a drop larger than a
spec threshold. The answering model and time sit at the right (desktop) or end (phone). Error rows read "No
decision:" plus the cause from ruling 30. A "Problems only" toggle filters to errors, refusals and stops.
Telemetry scoring labels its window by the game's unit and scores the spec's outcome keys **(unverified which
keys `SCORED` holds for Civ VI today; the audit saw military, science, pop, score, civics in stored results)**.
*Why:* audit 3.4; S5; the 226 military drop was hidden. *Cost if wrong:* 2-line clamp hides the rest of the
reason; Reasoning shows it in full.

**28. Order fates are the only pills.** Symbols plus words, never color alone: ✓ held / completed / took
(`--good`), ↺ replaced by the AI → X (`--warn`), ✕ refused: reason (`--bad`), ? no reply (muted), ⋯ open (muted).
The chip text is the item name and city; the reason is in its title and in Reasoning. Trigger categories (S5):
war, city threatened, city lost, race lost (wonder, great person), milestone missed, gold below reserve,
scheduled; the raw trigger (`GREAT_PERSON_CLASS_SCIENTIST`) becomes "Great Scientist race lost". *Why:* one
shape with one meaning keeps the page off the card-kit look and makes fates scannable; 71 of 95 triggers were
"urgent" with raw ids. *Cost if wrong:* a new fate needs a symbol; unknown fates render as muted text chips.

### G. Copy and wording per game

**29. The vocabulary table is data, and the page uses it everywhere.**
| Thing | Civ VI | Stellaris | GalCiv IV |
|---|---|---|---|
| Date | T307 | 2288.08 | turn from the HUD |
| Cadence | every 5 turns | every 12 months | per blocker |
| What the model gives | orders | a directive | clicks on the screen |
| Levers tab | Orders | Actions | Screen |
| Rivals panel | Civilizations met | Neighbours | (hidden) |
| Chart title | Yields over time | Empire over time | (hidden until metrics exist) |
| Outcome window | 12 turns later | 12 months later | (hidden) |
| Decide now help | Decides before the next autoplay turn | Pauses the game and decides now | (hidden) |
| Stop confirmation | The AI finishes this turn; the game stays at T310 | The game is paused and the governor stops | The pilot stops after this action |
| Skipped review | within 12 turns of the last review | within 12 months of the last review | |
Activity sentences (new or fixed): `turn` "Played T307 → T310 in 2 min 6 s" (+ `note` as a warning); `pace`
"Decides every 5 turns" / "Game speed fast"; `strategy_action` "Order: research Writing"; `strategy_review`
"Strategy reviewed: science 30 → 35"; `strategy_review_skipped` "Review skipped: within 12 turns of the last";
`model_fallback` "3.8 Flash overloaded; used 3.1 Pro"; `models`/`roles` "Models changed by Pixel phone";
`briefing_error` "Could not read the game: tuner did not answer"; `episode_error` "No decision: every model
failed"; `recover_probe` "Still not answering (try 3)"; `recovered` "Answering again; carried on by itself";
`last_stand_check` "Last stand check: 2 pins held, 1 moved"; `stall` "Game date stuck at 2288.08 for 6 min;
resumed once"; `self_paused` "The game had paused itself; resumed"; `popups_quieted` "Popups quieted 6 of 6";
`strategy_rejected` / `mismatch` / `disabled` in words. Plurals are real ("1 decision", "2 decisions"). *Why:*
M3; audit 3.8. *Cost if wrong:* a new game needs its column; the dashboard.toml test fails until it exists.

**30. Machine text is cut to its cause; ids become names.** A small, tested `cause()` maps error chains to one
line: `error sending request … /tuner/lua … operation timed out` → "the game's tuner did not answer (timed
out)"; `ModelHTTPError: status_code: 503 … high demand` → "overloaded (503)"; `credit balance too low` →
"billing: credit balance too low"; unknown chains → their last "Caused by" line. Ids resolve to names through
the corpus on the server (`BUILDING_GURDWARA` → "Gurdwara", `unit:trader` → "Trader", `CIVILIZATION_GERMANY` →
"Germany"), with prefix-strip and title-case as the fallback; APIs return `name` next to `id`. Raw text is
always one disclosure away. System messages never apologise and always name the next action. *Why:* audit 2,
M6. *Cost if wrong:* a mapping hides a detail; the disclosure keeps the raw text.

### H. Accessibility and dark mode

**31. Keyboard and screen readers.** Tabs get `aria-controls`, roving tabindex and arrow keys (both the reader
tabs and the phone bottom nav, which is a `nav` of links, not tabs). The chart is one tab stop (ruling 12).
The governor line is `role="status"`, announced on state change only; the attention card is `role="alert"`
once per stop; the countdowns and elapsed timers are `aria-hidden` with a static text alternative. Every state
has a word and a shape, not only a color. Collapsible headers are real buttons with ≥44 px targets on a phone.
Focus is visible (`--accent` outline) and returns to the opener when a dialog or sheet closes. *Why:* audit
3.6. *Cost if wrong:* none.

**32. Phone rules.** No horizontal scroll at 360-430 px (tables become two-line cards; the chart Table view
scrolls inside its box; long strings wrap). Bottom nav 56 px plus `env(safe-area-inset-bottom)`. Sheets for
Reasoning, the campaign list and Settings. Text never below 13 px on a phone. The phone reorder bug disappears
with the new structure. *Why:* M7. *Cost if wrong:* none.

**33. Contrast: light-mode text tokens are darkened; dark stays.** Measured on plane / surface / raised:
| Token | Now | New | New ratios |
|---|---|---|---|
| `--muted` | `#7b7e8c` 3.33 | `#5f6271` | 4.99 / 5.64 / 4.68 |
| `--accent` | `#a9741b` 3.33 | `#8a5a10` | 4.88 / 5.52 / 4.57; `--accent-ink` on it 5.68 (was 3.88) |
| `--sensor` | `#1f8f86` 3.25 | `#156f68` | 4.94 / 5.59 / 4.63 |
| `--warn` | `#b5651d` 3.57 | `#9a4f12` | 4.94 / 5.60 / 4.64 |
| `--good` | `#1f7f46` 4.14 | `#1a6e3c` | 5.18 / 5.87 / 4.86 |
| `--thought` | `#6b52c9` 4.71 | `#5b43b8` | 5.89 / 6.66 / 5.52 |
| `--bad` | `#b8362f` 4.80 | `#a82e28` | 5.61 / 6.35 / 5.26 |
Dark values all pass (muted 5.67 on plane is the lowest). Chart series colors `--s1..--s6` are checked against
the plot background at 3:1 for graphics and each series also gets a direct label at its line end. Both themes
honour `data-theme` and `prefers-color-scheme`; the pair page (ruling 39) uses the same tokens; a `forced-colors`
block keeps state edges and chips visible. *Why:* audit 3.6. *Cost if wrong:* light amber reads browner; it is
the reading mode, not the identity.

---

## Auth rulings

### Panel result
**34. A full re-judge picks the minimal-change proposal 3–0; the pairing ruling is withdrawn.** The first panel
read only the pairing proposal in full, so its choice was not a comparison. Three judges then read all three
proposals (`ui-audit/auth-proposals/auth-{pairing,passphrase,minimal-change}.md`), the current-auth analysis
(`auth-now.md`) and the passphrase proof of concept (`ui-audit/auth-poc`, screenshots `ui-audit/shots/auth-new-*`).
All three chose minimal-change: tally `{"minimal-change": 3}`.

| Proposal | UX | Security | Simplicity | Fit | Sum (3 judges, of 120) |
|---|---|---|---|---|---|
| **Minimal change**: three-word codes, QR and links; per-device sessions; K stays on the controller | 8 · 7 · 7 | 7 · 7 · 7 | 8 · 8 · 7 | 9 · 8 · 8 | **91** |
| Pairing: a code on the new device, approved from a signed-in one or the CLI | 7 · 7 · 6 | 8 · 8 · 8 | 4 · 5 · 3 | 6 · 7 · 4 | 73 |
| Passphrase: scrypt passphrase and remembered devices (tested PoC) | 5 · 8 · 8 | 6 · 5 · 6 | 5 · 6 · 5 | 6 · 6 · 7 | 73 |

The shape: every browser signs in once and then holds its own named, revocable session. The service key
`runs/dashboard.key` (called K below) stops travelling over the LAN and works only as a header from the
controller itself. A signed-in device adds another with a QR code, a copied link or three words. Pairing scores
one point higher on security as written, but each gap the judges found in minimal-change has a known fix in
pairing, and those fixes are grafted here (rulings 38, 40-42, 49-51). Pairing's own machinery (two kinds of
code, claim cookies, long-polls, a 7-state table) is dropped. One judge made the win conditional on those
security grafts landing before deploy: all of them are in commits A1-A2, which deploy together, and nothing
security-related is deferred. The passphrase design stays rejected. A reusable, human-chosen secret would cross
plain HTTP at every sign-in. First run needs an interactive terminal step that an agent cannot do without
learning the secret. Brave keeps its own password store, so the user types the passphrase again, which is the
retyping they objected to. Its tested pieces are ported instead: the sign-in page's shell and in-app warning,
the helpers (`allowed_host`, `safe_next`, `cross_site`, `json_error`, `security_headers`, `device_name` with the
`navigator.brave` hint, IPv6 /64 buckets, the key re-read on mtime and inode), script-token scopes, and its
security tests. Three PoC defects the judges reproduced are designed out:
- The lockout was checked before an `await`, so 41 parallel guesses from one IP were all tried. Ruling 41
  makes check-and-count atomic.
- `stepped_up()` returned true when no passphrase was set. There is no step-up here; tokens come only from the
  CLI (ruling 48).
- Every request carrying the old cookie minted a session. Carry-over now happens only on `GET /` (ruling 45).

*Why:* the best fit for a hands-off user (9 · 8 · 8) and the simplest design (one mechanism). It closes the
real hole (K in cookies, links and the journal) without adding a secret. *Cost if wrong:* a new browser still
needs one signed-in device or one terminal command; the phase-2 reverse flow (ruling 52) removes the second case.

### What "very clunky" becomes: the steps that disappear
| Step today (`auth-now.md`) | After this change |
|---|---|
| **Get the key on the controller first:** `python -m pilot dashboard-link`, the service journal, or `cat runs/dashboard.key` | **Gone** whenever one browser is already signed in. The terminal is left only for a first browser when nothing carried over. Even then it prints single-use words and a link, never the key, and an agent can run it. |
| **Carry a 43-character link to each browser**, often by pasting it into a chat app to reach the phone | **Gone.** The phone scans a QR code on a signed-in screen; Brave gets a link copied from Chrome. No secret passes through a chat app. |
| **Type or paste the key** into the locked page (a GET form that put it in the URL and in history) | **Gone.** At most three words, and three letters of each are enough ("map orb cra"). Nothing to remember. |
| **Open a link from another app, land in its in-app browser, tap "Open in browser", hit the locked page again** (the 303 had stripped `?key=`) | **Gone.** A signed-in browser opens the link straight into the page. A sign-in link keeps its code in the fragment, a GET never spends it, and it survives the hop. |
| **Chrome and the phone on deploy day** | **Nothing to do.** The old cookie becomes a device on the first page load (72-hour window). |
| **Redo every browser after a key rotation** | **Gone.** Rotation signs nobody out. |
| **Lost phone: delete the key, restart both services, stop the campaign** | **Gone.** One Sign out on its row in Devices; the run is untouched. |
| **Decode a page about "controller", "service log" and "the text after ?key="** | **Gone.** The page says "Sign in this browser", looks like Game Pilot on a phone, and names one command, only under "No browser signed in anywhere?". |
| **A script's pause fails without a trace** (`curl -s` hid a 401) | **Gone.** JSON errors, non-2xx replies, and `python -m pilot control` exits non-zero. |

What remains: a brand-new browser still needs one signed-in device or one terminal command. An in-app browser
is its own cookie jar (one "Open in browser", or one more tap). A private window forgets the sign-in when it
closes.

**Disagreements, resolved.** The judges are J1-J3 in the order of the re-run.
| Question | Proposal | Judges | Ruling |
|---|---|---|---|
| Where the one-time code travels | `/pair?c=` query | Fragment `/pair#c=`, posted by a same-origin script (J1; J2 mandatory) | Fragment; `?c=` is ignored (40) |
| Script on the sign-in page | None | Needed for the fragment (J1, J2) and the Brave hint (J1, J3); no script is the most robust in WebViews (J1) | One `script-src 'self'` file; typed words work without it (39, 49) |
| `POST /pair` body | Form or JSON | JSON only (J2 mandatory); keep the no-JS typed path (J1) | JSON; a form only for typed words, and only with a matching `Origin` (49) |
| Recovery-key form | On, collapsed | Remove it or default it off (J2 mandatory); keep it with the password-manager contract (J1, J3) | Off by default (`PILOT_KEY_SIGNIN=0`); when on, the password-manager contract (51) |
| Store | JSON file with `flock`; codes in viewer memory | SQLite, WAL, 0600 (all three) | `runs/auth.sqlite` for devices, grants and the audit; throttles stay in memory (50) |
| Global limit and the CLI | 429 for every sign-in, no unlock | Never block the CLI path; add `unlock` (J2 mandatory) | The 256-bit link half is never throttled; words are; `dashboard-devices unlock` (41) |
| Second use of a spent code | "Already used" | Revoke the device it made and warn (J1; J2 mandatory) | Adopted, except when the device it made presents it again (42) |
| Carry-over of old cookies | Until `rotate-key` | About 72 h; flag the devices; revoke unconfirmed ones at rotation (J2) | 72 h or rotation; `legacy` flag; kept only if named at rotation (45) |
| Script tokens | `dashboard-token`, full access | Read and control scopes (J1, J2); minted only by the CLI or after a step-up (J2) | CLI only, scoped, header only (48) |
| Who may add devices | Any signed-in browser | Offer CLI-only (J2) | Any by default; `PILOT_ADD_DEVICE=cli` (44) |
| Host allowlist | The address the connection arrived on | The PoC's `allowed_host`: any IP literal (J3) | The PoC helper; IP literals cannot be rebound (37) |
| Canonical host | None | `PILOT_PUBLIC_URL` with a 308, and a DHCP reservation (J1) | Opt-in; the runbook sets it to the IP the old cookies live on (37) |
| Attribution in the live pilot | Viewer log only | `X-Pilot-Device`, honoured only with K from loopback (J1, J2) | Adopted (36) |
| New device shows a code for a signed-in one to approve | Not offered | Phase 2 (J2) | Phase 2 (52) |
| `Path=/pilot` | Not offered | Optional (J1); not a boundary (J2) | Optional hygiene, not counted as isolation (52) |
| Earlier pairing grafts (push approval with number matching, approve-QR, "fresh" sessions, claim binding) | n/a | Not asked for by any judge | Dropped: no claim step exists to race, and ruling 42 covers replays |

### Mechanics
**35. The service key K: a header from loopback only, never a cookie, URL or log line.** K is
`PILOT_DASHBOARD_KEY`, else `runs/dashboard.key` (file and format unchanged, mode 0600). It is accepted only as
`X-Pilot-Key` or `Authorization: Bearer`, only when the TCP peer is 127.0.0.1 or ::1 (IPv4-mapped addresses
unwrapped), and never when the request carries `Forwarded` or `X-Forwarded-For`, because no reverse proxy is
trusted until the TLS phase configures one. From a LAN peer the right K gets
`401 {"error": "service_key_loopback_only"}` and an audit row, because the key has left the box. K is used by
the viewer's forwarding to the live pilot, scripts on the controller, the CLI's loopback `unlock` call, and
tests. It never appears in a cookie, URL, page, log line or the startup line again. `KeySource` re-reads the
file when its mtime or inode changes (a stat at most every 2 s). `LiveProxy` takes K from it on every call and,
on a 401 from the live pilot, reloads once and retries. Browser sessions are random tokens with a stored hash,
not `HMAC(K, id)`, so rotating K signs nobody out. *Why:* today K sits in every browser's cookie, in URLs, in 7
journal lines and in chat history, and it is the master credential for both ports and every script. *Cost if
wrong:* a script on another machine cannot use K; it gets a script token (ruling 48).

**36. The live pilot binds 127.0.0.1, accepts only the K header, and holds no auth store.** A new setting
`PILOT_LIVE_HOST` (default `127.0.0.1`) sets the live pilot's bind address. The viewer keeps `0.0.0.0` through
`view --host` and `PILOT_VIEW_HOST`; `dashboard_host` stays as an alias. The live pilot's guard is header-only:
no cookies, no sign-in routes, no `runs/auth.sqlite`. The viewer forwards with K plus `X-Pilot-Device: <device
id>` for the browser behind the request. The live pilot honours that header only alongside K from loopback and
records it as `by` on control and chat events ("Paused, from Pixel phone"). Its `/status` reports
`info.auth_version = 1`, so the CLI can tell new code from old. The deploy restarts the live pilot together with the viewer (a restart is safe: the governor picks the campaign
up from the next snapshot, and a start that times out now recovers by itself), so the old-code pilot that listens
on `0.0.0.0:8790` and accepts K as a cookie from the LAN is gone from the first deploy; no firewall rule is needed. *Why:* 8790 on the LAN and the
Docker bridges accepts the leaked key, and the viewer already forwards `/status`, `/events`, `/events.json`,
`/frame.jpg` and `/control` over loopback (re-checked in `dashboard.py`). *Cost if wrong:* anyone who opened
:8790 directly must use :8780; `PILOT_LIVE_HOST=0.0.0.0` restores the old bind.

**37. Host allowlist first, and an optional canonical host.** Before anything else, `Host` (port stripped) must
be an IP literal, `localhost`, the machine's hostname, `<hostname>.local`, its FQDN, a name in
`PILOT_DASHBOARD_HOSTS`, or the host of `PILOT_PUBLIC_URL`. Anything else gets 421 ("Unknown host name. Open
the dashboard by the controller's address; to allow a name, add it to PILOT_DASHBOARD_HOSTS.") and an
aggregated audit row. IP literals are safe because a rebinding page's `Host` is always its own DNS name, and
they keep working after a DHCP change. `PILOT_PUBLIC_URL` (unset by default) is the base for every link and QR
code. When it is set, HTML navigations (GET with `Accept: text/html`) that arrive on another non-loopback host
get a 308 to it, so cookies do not split between the IP and a name. The runbook sets it to
`http://192.168.1.76:8780`, the host the old cookies live on, so carry-over is unaffected, and it asks for a
DHCP reservation for .76. Without it, links use the `Host` the creating browser used (when that passed the
allowlist and is not loopback), else `link_host()`. *Why:* under DNS rebinding `Origin` and `Host` are both the
attacker's name, so today's check passes and the docstring overstates it; public sign-in routes make this
matter. The controller's names do not resolve on the AD DNS, so the address is the name. *Cost if wrong:* a new
name for the controller needs one env entry. If the IP changes without a reservation, every browser has an empty
cookie jar on the new address and signing in starts again from `dashboard-link`.

**38. Browser sessions: one opaque token per device, checked on every request, kept apart from other
credentials.**
- Cookie `pilot_session=s1.<id>.<secret>`, where `id` is `token_hex(5)` (public) and `secret` is
  `token_urlsafe(32)`. Flags: `HttpOnly`; `SameSite=Lax` (links opened from other apps arrive signed in;
  cross-site subrequests and frames do not carry it); `Path=/`; `Max-Age` 400 days, re-sent at most once a
  week so Chrome's 400-day cap slides with use. No `Secure` on plain HTTP; under HTTPS the code switches to
  `Secure` and `__Host-pilot_session` (ruling 52).
- The store keeps `sha256(secret)`. A check finds the row by id and compares with `compare_digest`. Every
  request reads the row (an indexed SQLite read), so a revocation applies on the next request. `last_seen`
  (time and IP) is written at most every 5 min, through `asyncio.to_thread`. A browser device unseen for 180
  days is signed out (`idle`) and later pruned.
- Credential kinds stay apart. A session is accepted only from the cookie, a script token (`pgt_…`, ruling 48)
  only from a header, and K only from a loopback header. A cookie is never checked as a token or as K, a header
  is never checked as a session, and no credential is read from a query string.
- Live streams: `/events` and the viewer's forwarded stream re-check the principal at each 15 s keepalive and
  close on revocation. The interval is injectable for tests.
- A device used from two addresses within 10 minutes gets a "used from two addresses" badge and a notice on the
  other devices. Sessions are not bound to an IP, because DHCP and phone MAC randomisation would sign people out.

*Why:* a sniffed cookie now yields one visible, revocable device instead of the master key for both ports and
every script. Keeping the kinds apart stops a leaked session being replayed as a script token, or the reverse
(J2 mandatory 5, 6). *Cost if wrong:* the cookie still reaches the other services on this host (:3000, :8200,
:9120), because cookies are not isolated by port; there it is a revocable device token, not K (ruling 52).

**39. The sign-in page (`/pair`) replaces the locked page, ported from the PoC's tested shell.** The visual
system comes from `ui-audit/auth-poc/login.html`, already verified at 390 px in light and dark with no
horizontal scroll (`auth-new-login-phone-{light,dark}.png`, `auth-new-login-desktop-light.png`). It has a viewport
meta, `color-scheme`, the dashboard's tokens (light values from ruling 33), `box-sizing: border-box`, a 16 px
gutter, one card of at most 380 px, 16 px inputs so iOS does not zoom, 46 px buttons, system fonts only (so no
request leaves before sign-in) and the wordmark with the accent dot. Relabelled for three words:
- H1 "Sign in this browser". Lede: "Game Pilot can steer the games on your PC, so each browser signs in once. It
  stays signed in until you sign it out."
- One field, "Sign-in code", placeholder "three words, e.g. maple orbit crane", with
  `autocomplete="one-time-code"`, `autocapitalize="none"`, `autocorrect="off"`, `spellcheck="false"` and
  `enterkeyhint="go"`. Hint: "The first three letters of each word are enough." Button: "Sign in".
- "Get a code on a browser that is already signed in: ⋯ > Add a device. On a phone, scan the QR code there with
  the camera."
- A disclosure, "No browser signed in anywhere?": "On the computer that runs Game Pilot, run python -m pilot
  dashboard-link. An agent working there can run it for you." This is the only command on the page.
- Always shown, small: "Opened from another app? A sign-in belongs to the browser you sign in with. Private
  windows forget it when they close."
- The footer, kept from the PoC: "This connection is not encrypted (plain HTTP on your local network). Sign out
  devices you don't recognise."

The confirm view (`/pair#c=…`, ruling 40): H1 "Sign in this browser?"; "Adds this browser to Game Pilot's
devices. The link works once; signing in here uses it up."; a Name field, prefilled ("Brave on Windows"); one
full-width "Sign in" button; "Type the words instead" as a link. It follows the PoC's link page
(`auth-new-link-phone-dark.png`, `auth-new-link-phone-used-again.png`).

States each get one sentence. They come from a fixed set chosen by `?reason=` or by the reply, never from free
text in the URL:
- signed out; revoked ("This browser was signed out from Pixel phone at 14:02."); idle;
- old link ("Links with ?key= stopped working on 30 Sep. Sign in with a code from a browser that is signed in.");
- wrong words (401): "Those words don't match a current code. Codes last 10 minutes and work once. 3 more tries
  before a short wait.";
- used or expired (410): "This code was already used." / "This code has expired. Make a new one on the other
  device.";
- conflict (ruling 42); typed words switched off (ruling 41: "Use the link or QR code instead.");
- too many tries (429 with `Retry-After` and a live countdown): "Browsers already signed in keep working.";
- cookie blocked: "This browser did not keep the sign-in. Allow cookies for 192.168.1.76, then use a new code.";
- in-app browser (ruling 43).

Headers: CSP `default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src 'self' data:;
connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'` and `Referrer-Policy:
no-referrer`. The page's behaviour lives in `/static/signin.js` (same origin, no inline script). Without it the
typed-words form still works (ruling 49).
```
phone, /pair                                   phone, /pair#c=… (from a link or QR code)
┌──────────────────────────────────────┐       ┌──────────────────────────────────────┐
│ ● Game Pilot                         │       │ ● Game Pilot                         │
│ ┌──────────────────────────────────┐ │       │ ┌──────────────────────────────────┐ │
│ │ Sign in this browser             │ │       │ │ Sign in this browser?            │ │
│ │ Game Pilot can steer the games   │ │       │ │ Adds this browser to Game        │ │
│ │ on your PC, so each browser      │ │       │ │ Pilot's devices. The link works  │ │
│ │ signs in once.                   │ │       │ │ once; signing in uses it up.     │ │
│ │ Sign-in code                     │ │       │ │ Name                             │ │
│ │ [ maple orbit crane            ] │ │       │ │ [ Chrome on Android            ] │ │
│ │ The first three letters of each  │ │       │ │ [           Sign in            ] │ │
│ │ word are enough.                 │ │       │ │ Type the words instead           │ │
│ │ [           Sign in            ] │ │       │ └──────────────────────────────────┘ │
│ │ Get a code on a browser that is  │ │       │ Opened from another app? A sign-in   │
│ │ signed in: ⋯ > Add a device.     │ │       │ belongs to the browser you sign in   │
│ │ ▸ No browser signed in anywhere? │ │       │ with.                                │
│ └──────────────────────────────────┘ │       │ Not encrypted: plain HTTP on your    │
│ Not encrypted: plain HTTP on your    │       │ local network.                       │
│ local network.                       │       └──────────────────────────────────────┘
└──────────────────────────────────────┘
```
*Why:* M4 and both complaints: "what is this now?!?" was a 980 px, light-only page in developer words. The PoC
has already proved this shell on a phone. *Cost if wrong:* only the port; the PoC's screenshot script becomes a
Playwright check.

**40. Sign-in grants: three words to type or a 256-bit link to open; one grant, used once, within 10 minutes.**
A signed-in browser (⋯ > Add a device, ruling 44) or the CLI (`dashboard-link`) creates a grant with two faces:
- **Words.** Three words from the EFF short wordlist 2.0, vendored as `src/pilot/pair_words.txt` with its
  CC BY 3.0 US attribution. It has 1,296 words and every 3-letter prefix is unique (re-checked 2026-09-27:
  1,296 distinct prefixes, 3-10 letters). 1296³ ≈ 2.18e9 codes, 31 bits. Input is lowercased and split on
  anything that is not a letter; there must be exactly three tokens; each maps to a word by its first three
  letters and must be a prefix of that word. So "Maple-ORBIT crane" and "map orb cra" both match. Words are
  throttled and can be switched off (ruling 41).
- **Link.** `http://<host>/pair#c=<grant id>.<secret>`, with a 256-bit secret, shown as a link (Copy) and a QR
  code. The token rides only in the URL fragment, so it never appears on a request line, in a log, in `Referer`
  or in a link-preview fetch, and a sniffer cannot see it before the POST that spends it. `GET /pair` never
  spends anything. `/static/signin.js` reads the fragment and shows the confirm view; only the tap sends
  `POST /pair {link, name, client, next}` as JSON. A `?c=` query parameter is ignored. After success, and on
  any error, `history.replaceState` removes the token from the address bar.

Either face mints one browser device and spends the whole grant. Grants live in `runs/auth.sqlite` (ruling
50), so the CLI can make them while the viewer is down, and the Add panel's status survives a viewer restart.
Each signed-in browser may hold one live grant (a new one replaces it), with at most three live across all
browsers; CLI grants do not count toward either limit. A browser that is already signed in and opens a link is
sent on to `next` without spending it; the dashboard drops the stray `#c=` from its address bar, and the grant
simply expires. The device name comes from the user agent plus a `client` field that signin.js sets from
`navigator.brave`, so Brave becomes "Brave on Windows", not "Chrome on Windows". `next` carries the original
path, query and `#fragment` (signin.js appends `location.hash`, except `#c=`), sanitised by `safe_next`: a
same-origin path only, with no `//`, backslash, scheme, control character, `/pair` or `key=`. After sign-in the
browser goes to `/pair?check=1&next=…`, which sends a browser whose cookie stuck on to `next` and shows the
cookie-blocked state to one whose cookie did not. The no-script form uses the same check. *Why:* J1's graft and
J2's mandatory 1. In `?c=` the code lands in history, sync and any access log, and a sniffer sees it on the GET
before the POST spends it. The 256-bit half keeps the CLI and QR path working under any throttle (J2 mandatory
8). *Cost if wrong:* a phone without a camera, or a browser that cannot run the script, types three words.

**41. Throttles guard the typed words, never a valid link, and count atomically.** The viewer counts failures
in memory, per bucket: an exact IPv4 address, or an IPv6 /64, with IPv4-mapped addresses unwrapped. Failures
are wrong words, a wrong link token, a wrong recovery key (when that form is on), a wrong `?key=` inside the
carry-over window, and a bad header token from the LAN.
- 5 failures in 10 min from one bucket: typed words from that bucket get 429 with `Retry-After`.
- 20 failures in 10 min across all buckets: typed words are refused for everyone for the rest of the window.
- 5 wrong words in total while grants are live: the words of every live grant are switched off, and their
  links and QR codes keep working. The Add panel says "Typed words were switched off after 5 wrong tries on
  your network. The link and QR code still work. [New code]".
- A valid link token always works, from any address, even under a lock. It is 256-bit, so throttling it
  protects nothing. Signed-in traffic and scripts are never throttled.
- Check-and-count is atomic. A sign-in reserves its slot in the bucket synchronously, before any `await`, and a
  success refunds it. So 20 parallel wrong tries from one address yield exactly 5 checks (the PoC checked its
  lock before awaiting the hash and let 41 through).
- `python -m pilot dashboard-devices unlock` clears every bucket through a loopback call with K
  (`POST /api/auth/unlock`); a viewer restart clears them too.

Guessing odds per window: at most 5 tries × 3 live grants / 2.18e9 ≈ 7e-9, and grants exist only while the user
is adding a device. Failure bursts are audited as one row per IP per minute, with a count. *Why:* J2's
mandatory 8 and the gap J2 found: the proposal's global limit answered 429 to every sign-in, including codes
from the CLI, and had no unlock. The atomic count is J2's cross-cutting finding. *Cost if wrong:* a LAN host
can switch off typed words for 10 minutes at a time; links, QR codes and the CLI are unaffected, and `unlock`
ends it.

**42. A spent grant presented again is treated as copied: the device it made is signed out and every device is
told.** When a used grant is presented again (by words or link) from any client other than the device it
minted, the server revokes that device (`revoke_reason = conflict`), writes an audit row and marks the grant
`conflict`. Then:
- the presenting browser sees "This code was already used by another browser (Brave on Windows, 192.168.1.77,
  30 s ago). For safety that sign-in was signed out. If both were you, make a new code; if not, someone on your
  network may be copying traffic.";
- every signed-in page shows for 24 h: "A used sign-in code was tried again from 192.168.1.203. The browser it
  had signed in (Brave on Windows) was signed out. Review devices".

If the device the grant minted presents it again (a double tap, a back-button resubmit), it gets
`200 {"already": true}` and nothing is revoked. Spent grants are kept 24 h for this check. *Why:* J1's graft 6
and J2's mandatory 3. On plain HTTP a sniffer can replay a code, and the proposal only answered "already used".
The server cannot tell which use was genuine, so it revokes the device and tells both sides (pairing's
tamper-evidence rule). *Cost if wrong:* someone who signs in inside an app's browser and then again in the real
browser signs the in-app one out (which they wanted anyway) and needs one new code. The in-app warning above
the button (ruling 43) prevents most of these.

**43. Links from other apps: a signed-in browser goes straight in; an in-app browser is warned and loses
nothing.**
- A signed-in browser opens any dashboard link from another app straight into the page, because the cookie is
  `SameSite=Lax` and is sent on top-level GET navigations.
- In-app browsers (WebViews) keep their own cookie jars. The page detects the common ones by user agent (`; wv)`,
  `FBAN`/`FBAV`, `Instagram`, `Line/`, `GSA/`, `LinkedInApp`, `Snapchat`, `Twitter`, `Slack`, `Teams/`,
  `MicroMessenger`) on the server, so the warning works without script. It leads with: "You opened this inside
  <App>. A sign-in here stays inside that app. Open this page in your browser: menu > Open in browser. The link
  isn't used up until you press Sign in." Under it, a read-only field holds the address (with the copy fallback
  of ruling 44). "Sign in here anyway" stays available and makes an ordinary device, named "In-app browser on
  Android".
- The grant stays unspent in the fragment, so "Open in browser" carries it to the same confirm view in the real
  browser (unverified per app; see the list at the end). This fixes the phone failure the user hit, where
  today's 303 strips `?key=` before the hop.
- iOS `SFSafariViewController` sends Safari's user agent and cannot be detected, so the "Opened from another
  app?" line is always shown.
- Link previews: chat apps fetch GET URLs. `GET /pair` renders a page and sets no cookie, and the fragment never
  reaches the server.

*Why:* M4 and the phone case in the brief. The PoC's in-app warning is already built and screenshotted
(`auth-new-login-phone-inapp.png`). *Cost if wrong:* a detection miss leaves a sign-in inside the app. It works
there and shows in Devices, and the always-shown line explains it.

**44. Devices UI: "Add a device" in the ⋯ menu, the list in Settings > Devices.** The ⋯ menu's "Add a device"
opens a sheet (full-screen on a phone) that holds:
- the QR code: 176 px, dark on white with a white quiet zone even in dark mode, rendered as a `segno` SVG. Below
  600 px it is behind "Show QR code", since a phone rarely scans its own screen;
- the three words in Bricolage 28 px, lowercase, separated by middots, with "The first three letters of each
  word are enough";
- the link with **Copy link**. `navigator.clipboard` and `navigator.share` do not exist on plain HTTP, so Copy
  selects a read-only input and runs `document.execCommand('copy')`; if that fails it leaves the text selected
  with "Press Ctrl+C" (the PoC's fallback). Copy link is the main Brave path, so without this it would fail
  (J1's graft 2);
- "Works once · 9:41", a countdown, with **New code** and **Cancel**;
- an `aria-live` line that polls `GET /api/auth/grants/<id>` every 2 s while the sheet is open: "Waiting for
  the other device…", then "Signed in: Brave on Windows, 192.168.1.77 · Not you? Sign it out".

With `PILOT_ADD_DEVICE=cli` (optional, off by default) the sheet says "Adding devices is limited to the computer
that runs Game Pilot: python -m pilot dashboard-link", and the API refuses with 403. Settings > Devices:
```
┌ Settings   Models   Game   Devices ───────────────────────────────────────────────────┐
│ This browser: Chrome on Windows · carried over from the old link, 30 Sep              │
│ [Rename] [Sign out this browser]                                                      │
│                                                                                       │
│ [Add a device]                                                                        │
│                                                                                       │
│ Brave on Windows    new · last used 2 min ago, 192.168.1.77                [Sign out] │
│   signed in 30 Sep with a link from Chrome on Windows                                 │
│ Chrome on Android   last used 1 h ago, 192.168.1.140                       [Sign out] │
│   carried over from the old link, 30 Sep                                              │
│                                                                                       │
│ Scripts                                                                               │
│ laptop-watch        read only · last used 4 min ago, 192.168.1.90            [Revoke] │
│                                                                                       │
│ [Sign out all other devices]                                                          │
│ ▸ Recent sign-in activity (20)                                                        │
│ Lost every signed-in browser? On the computer that runs Game Pilot:                   │
│ python -m pilot dashboard-link                                                        │
│ Not encrypted: plain HTTP on your network. Sign out devices you don't recognise.      │
└───────────────────────────────────────────────────────────────────────────────────────┘
```
Each row shows the name (renamable, at most 60 characters), a "this browser" tag, how and when it signed in and
from which device, when it was last used and from which IP, badges ("carried over from the old link", "used from
two addresses", "new"), and Sign out with a confirm. Script tokens are listed under "Scripts" with their scope
and last use; they can be revoked here but are created only from the CLI. "Recent sign-in activity" lists the
last 20 aggregated audit events as sentences, failures in `--bad`. For 24 h after a sign-in, every other
signed-in page shows "New device signed in: Brave on Windows, added from Chrome on Windows at 14:02,
192.168.1.77 · Review devices". It is dismissed per device id in `localStorage`, wrapped in try/catch. *Why:*
the list is where revocation lives; J1's grafts (recent activity, the new-device banner, the copy fallback);
J2's mandatory 9 (a CLI-only option). *Cost if wrong:* none.

**45. Carry-over: nobody is locked out on deploy day, and the leaked key stops making devices after 72 hours.**
On its first start the new viewer records `meta.legacy_key_fp = sha256(K)` and `meta.legacy_until = now + 72 h`.
While `now < legacy_until` and K still has that fingerprint:
- A `pilot_key` cookie equal to K (checked with `compare_digest`) is accepted on any request, so open tabs,
  their stream and their frames keep working until they reload. Only a top-level `GET /` turns it into a device
  (`created_via = legacy_cookie`, `legacy = 1`, named from the user agent, badge "carried over from the old
  link"). That response sets `pilot_session` and expires `pilot_key` through `on_response_prepare`, so the
  parallel requests of one page load make one device, not one each (the PoC's defect). The page then shows once:
  "This browser now has its own sign-in. See Devices."
- `GET /?key=K` creates a grant (`created_by = legacy_link`) and answers 303 to `/pair#c=<link>` without a
  cookie. An old bookmark thus becomes the one-tap confirm view, and the device it makes is flagged `legacy`
  too. A wrong value counts as a failure (ruling 41). A browser that already has a session gets a plain 303 to
  `/` (the key leaves the address bar) and no grant.

After the window, or once K is rotated (the fingerprint changes), the old cookie is deleted wherever it is
seen, and `?key=` is never compared again: any value gets the same 303 to `/pair?reason=old_link`, so the route
cannot test guesses. At rotation (ruling 47) every legacy device is listed with its name, first IP and last use.
Only the ones the user names are kept; the rest are revoked (`rotate_unkept`). Mixed versions: the new viewer
still sends the unchanged K to the old live pilot over loopback, so forwarding keeps working. *Why:* J2's
cross-cutting finding. K is known to have leaked (journal, chat, synced history), so "until rotation" (the
proposal) would keep minting durable devices from a leaked key for as long as the Civ VI campaign runs.
Carrying over only on `GET /` is the proposal's own fix for the PoC's duplicate sessions (J3). *Cost if wrong:*
a browser that holds the old cookie but is not opened within 72 h signs in once with a link from a signed-in
device. A legacy device made by someone else inside the window survives only if the user keeps it at rotation,
which is why the prompt shows first IPs.

**46. Signed out, in the page.** Every API 401 carries JSON `{error, reason, fix, by, at}`, where `error` is
one of `sign_in_required`, `revoked`, `idle`, `conflict`, `service_key_loopback_only` or `bad_token`, plus
`WWW-Authenticate: Bearer realm="Game Pilot"`. The page stops polling and the event stream and shows a sans
banner: "This browser was signed out (from Pixel phone at 14:02). [Sign in again]". The button links to
`/pair?reason=<error>&next=<current path and #fragment>`. An EventSource error triggers one `GET /api/auth/me`;
on a 401 the page shows the banner and never reconnects. HTML navigations without a session get a 303 to
`/pair?next=…&reason=…`; browsers keep the fragment across a 303, and signin.js adds it to `next`. The old
banner that told a phone user to run a terminal command is removed. `/api/auth/me` also returns the notices (new
devices, conflicts, two addresses), which the page checks on load and every 60 s. *Why:* audit 3.1 (a lost key
showed as "PC offline" with stale data); J3's graft 4. *Cost if wrong:* none.

**47. CLI: one family of `dashboard-*` commands, safe for an agent to run.** The command names the repo and
AGENTS.md already use are kept (J1 on fit). The CLI opens `runs/auth.sqlite` directly, so it works with both
services down; its authority is file access to `runs/`, the same as for K today.
- `python -m pilot dashboard-link [--port 8780] [--no-qr] [--wait]` makes a grant and prints
  `Sign in a browser (works once, for 10 minutes):`, the link with `#c=`,
  `or open http://192.168.1.76:8780/ and type: maple orbit crane`, and a compact terminal QR code (`segno`). It
  never prints K. With `--wait` it waits for the grant to be used and prints "Signed in: Chrome on Android". The
  output is safe for the Codeman agent to run and show: the link and the words work once, for 10 minutes, and
  whoever uses them appears in Devices.
- `dashboard-devices [list | rename ID NAME | revoke ID | revoke-all [--except ID] | log [-n N] | unlock]`.
- `dashboard-key --rotate [--keep all|none|ID,…] [--force]` writes a new `runs/dashboard.key` atomically (temp
  file, `os.replace`, 0600); both new-code processes pick it up within 2 s. It refuses when `PILOT_DASHBOARD_KEY`
  is set, and explains the manual path (change the variable, restart both services). It also refuses, unless
  given `--force`, while a live pilot's `/status` lacks `info.auth_version ≥ 1`: "a live pilot from before the
  change reads the key only at startup; rotate after it restarts". It lists the legacy devices and asks which to
  keep, with no default; `--keep` answers for non-interactive use. It revokes the rest and ends the carry-over
  window. No other browser session or script token is touched.
- `dashboard-token create --name N --scope read|control [--expires 90d] | list | revoke ID` (ruling 48).
- `control ACTION [--text T] [--index N] [--port 8780]` (ruling 48).
- `view` prints only "dashboard on http://192.168.1.76:8780/ (to sign in a browser: python -m pilot
  dashboard-link)". The key leaves the journal from the first restart on.

AGENTS.md gains one line: "To sign the user in, run python -m pilot dashboard-link; never print
runs/dashboard.key." *Why:* lockout recovery without a browser, and agents can help without reading K. *Cost if
wrong:* none.

**48. Automation: the K header on the controller is unchanged; other machines get scoped tokens from the CLI.**
- On the controller, `X-Pilot-Key: $(cat runs/dashboard.key)` sent to 127.0.0.1:8780 keeps working, so watch.sh
  runs unchanged. Scripts should read the file on every call rather than once at start, so a rotation does not
  break a long loop (watch.sh caches it in `$K`).
- `python -m pilot control pause|resume|stop|instruct|… [--text T] [--index N] [--port 8780]` reads K on each
  call, posts JSON over loopback, prints the reply, and exits non-zero with the server's error on any non-2xx
  reply. It replaces the `curl -s … >/dev/null` pattern that hid techwatch.sh's 401 (techwatch.sh posts to 8790
  with no key; it is not in the repo and moves to `control`).
- Other machines: `dashboard-token create --name "laptop watch" --scope read` prints `pgt_<id>.<secret>` once.
  The script sends it as `Authorization: Bearer` or `X-Pilot-Key`, from any address. It is never accepted as a
  cookie or in a query string. Scope `read` allows GET only (anything else gets 403 `read_only`); `control`
  allows everything except `/api/auth/*`, so no token can list devices, make grants or make tokens. Tokens come
  only from the CLI: the browser has no step-up (there is no passphrase), so a stolen session cannot mint a
  lasting script credential. They are listed and revocable in Devices and in the CLI, with last use and IP.
- Failures are loud: 401, 403 and 429 replies are JSON with `error`, `reason` and `fix`; 401s carry
  `WWW-Authenticate`; the docs tell scripts to use `curl -fsS`.

*Why:* current-auth pain 10; J1's graft 7 and J2 (read and control scopes; only the CLI or a step-up may mint a
token). *Cost if wrong:* a read token that leaks over plain HTTP exposes screenshots and reasoning until it is
revoked; running scripts on the controller avoids that.

**49. Request pipeline and headers.** In order:
1. Host allowlist, else 421 (ruling 37); then the canonical-host 308 when `PILOT_PUBLIC_URL` is set.
2. Any method other than GET, HEAD or OPTIONS: `Origin: null` gets 403; an `Origin` whose netloc differs from
   `Host` gets 403; a `Sec-Fetch-Site` other than `same-origin` or `none` gets 403. Browsers send `Sec-Fetch-*`
   only to HTTPS and localhost origins, so on the LAN today the `Origin` check does this work.
3. Public routes, and only these: `GET /pair`, `POST /pair`, `POST /pair/key` (only when enabled, ruling 51),
   `GET /static/signin.js` and `/favicon.svg`. `POST /pair` takes JSON, which covers everything signin.js sends.
   A form body (`application/x-www-form-urlencoded`) is accepted only for typed words, and only when `Origin`
   is present and matches. So the page still signs in without script (in-app WebViews), while no cross-site
   form can reach it. A link token in a form body is refused.
4. Principal: a header (K from loopback: the service; K from the LAN: 401 `service_key_loopback_only`; a `pgt_`
   token: that token; anything else: 401 `bad_token`), else the `pilot_session` cookie, else the legacy
   `pilot_key` inside the window (ruling 45), else none: an HTML navigation gets a 303 to `/pair`, anything else
   a JSON 401.
5. Mutations with a principal: `application/json` only (403 `json_only`). Cookie-authenticated mutations must
   carry a matching `Origin` (403 when it is missing); header-authenticated scripts may omit it. Read tokens get
   403 `read_only`. `OPTIONS` never answers with CORS headers.
6. `request["principal"]` names the device. `/control`, `/api/settings`, `/api/run` and the auth actions record
   `by` (the device name) in the run's events and the audit table, and the viewer forwards `X-Pilot-Device`.
7. Cookie writes (carry-over, the weekly re-send, deletions) go through `app.on_response_prepare`, so they also
   attach to a `FileResponse`, an SSE `StreamResponse` and a raised HTTP error.

Every response gets (the PoC's `security_headers`, merged into `no_store`): `Cache-Control: no-store`,
`X-Frame-Options: DENY`, `Content-Security-Policy: frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`
and `Referrer-Policy: same-origin` (`no-referrer` on `/pair`). `/pair` also gets the strict CSP of ruling 39.
*Why:* this keeps today's CSRF defences (JSON-only, `Origin == Host`) and adds J2's mandatory 4 (a matching
`Origin` on every cookie-authenticated change, and a JSON `/pair`), with one reasoned exception: the no-script
typed-words form, which J1 asked to keep and which a required, matching `Origin` protects just as well. It also
adds cover against rebinding and clickjacking. *Cost if wrong:* a browser that sends no `Origin` on a same-origin
POST cannot sign in or change anything. Current Chrome, Brave, Firefox and Safari send it on every POST (the
in-app WebViews are on the unverified list).

**50. One store, four tables, kept apart from telemetry.** `runs/auth.sqlite` (`PILOT_AUTH_DB` overrides it;
tests point it at a temp dir). It is created with `os.open(…, 0o600)` before SQLite connects, so `-wal` and
`-shm` get the same mode; it runs in WAL mode with `busy_timeout` 2000 ms, and writes go through
`asyncio.to_thread`. Only the viewer and the CLI open it; the live pilot needs no store (ruling 36). It is not
`telemetry.sqlite`, because `rebuild-telemetry` deletes that file's tables and it is 0644. An unreadable or
corrupt file is moved to `auth.sqlite.corrupt-<time>`, logged loudly, and an empty store starts (fail closed:
browsers sign in again with `dashboard-link`; scripts on the controller keep working with K).
```sql
CREATE TABLE devices (
  id TEXT PRIMARY KEY,               -- token_hex(5); public (lists, logs, revoke); never a credential
  kind TEXT NOT NULL CHECK (kind IN ('browser', 'script')),
  scope TEXT NOT NULL DEFAULT 'control' CHECK (scope IN ('read', 'control')),   -- browsers: control
  name TEXT NOT NULL,                -- ≤ 60 chars; user agent + navigator.brave hint; renamable
  token_hash BLOB NOT NULL,          -- sha256(secret); cookie "s1.<id>.<secret>", script "pgt_<id>.<secret>"
  created_at REAL NOT NULL, created_ip TEXT,
  created_via TEXT NOT NULL,         -- words | link | legacy_cookie | legacy_link | recovery_key | cli
  created_by TEXT,                   -- id of the device that made the grant, or 'cli'
  grant_id TEXT,                     -- the grant it came from (ruling 42)
  legacy INTEGER NOT NULL DEFAULT 0, -- made from the old key (ruling 45)
  user_agent TEXT,                   -- first 200 chars
  last_seen_at REAL, last_ip TEXT, prev_ip TEXT, prev_seen_at REAL,
  cookie_sent_at REAL,               -- Set-Cookie re-sent after 7 days
  expires_at REAL,                   -- scripts: optional; browsers: the idle rule only
  revoked_at REAL, revoked_by TEXT,
  revoke_reason TEXT                 -- signed_out | revoked | revoke_others | idle | conflict | rotate_unkept
);
CREATE TABLE grants (
  id TEXT PRIMARY KEY,               -- token_hex(5); the link is /pair#c=<id>.<secret>
  link_hash BLOB NOT NULL,           -- sha256(256-bit secret)
  words_hash BLOB UNIQUE,            -- sha256(canonical words), redrawn on a clash; NULL once switched off
  created_at REAL NOT NULL, expires_at REAL NOT NULL,   -- +600 s
  created_by TEXT NOT NULL,          -- device id | 'cli' | 'legacy_link'
  state TEXT NOT NULL,               -- waiting | used | expired | cancelled | conflict
  used_at REAL, used_ip TEXT, device_id TEXT
);
CREATE TABLE auth_events (           -- one row per (event, ip, minute), with a count
  id INTEGER PRIMARY KEY, t REAL NOT NULL, event TEXT NOT NULL, ip TEXT, device_id TEXT,
  count INTEGER NOT NULL DEFAULT 1, detail TEXT                     -- JSON; never a secret
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);   -- schema_version, legacy_key_fp, legacy_until
```
Events: `signin` (with how), `signin_failed`, `throttled`, `words_switched_off`, `grant_created`,
`grant_conflict`, `signed_out`, `revoked`, `revoke_others`, `idle`, `service_key_refused_lan`, `host_refused`,
`token_created`, `token_revoked`, `key_rotated`, `legacy_kept`, `legacy_revoked`, `unlock`, and `control` (the
action and the device). Housekeeping at start and hourly removes grants older than 24 h, events older than 90
days or beyond 10,000 rows, and browser devices idle for 180 days (revoked `idle`, deleted 30 days later). Only
hashes of secrets are stored. The words are stored as a `sha256` of the canonical words, which keeps them out of
the file's bytes but is no barrier to someone who can read `runs/` (that person can read K anyway). *Why:* J1's
graft 2, J2's mandatory 7 and J3's graft 6. The viewer and the CLI both write, and the audit writes a row per
minute of failures; the repo already runs SQLite, and the proposal's JSON file with `flock` and debounced merges
between writers was its fragile part. *Cost if wrong:* one more file under `runs/`; a lost store means one
sign-in per browser.

**51. Recovery and lockout; the recovery-key form is off by default.**
- Another signed-in device exists: ⋯ > Add a device.
- No signed-in device: `python -m pilot dashboard-link` on the controller (a terminal, SSH, or the Codeman
  agent).
- Typed words throttled or switched off: use the link or QR code (never throttled), or `dashboard-devices
  unlock`.
- Store corrupt: it is moved aside and an empty one starts (ruling 50).
- Suspected compromise: `dashboard-devices revoke-all`, `dashboard-key --rotate --keep none`, then
  `dashboard-link` for yourself; read `dashboard-devices log`.
- The recovery-key form (the proposal's "Use the recovery key" on the sign-in page) ships **off**:
  `PILOT_KEY_SIGNIN=0` is the default, so K is never accepted from a LAN peer in any form. When the operator
  turns it on, it is a collapsed `POST /pair/key` form with the PoC's password-manager contract: a visually
  hidden `username=pilot` field with `autocomplete="username"`, a `type=password` field with
  `autocomplete="current-password"` and no paste blocking, a real submit button, and a 303 on success. Chrome or
  Brave can then save K once and fill it later without a terminal. The form is throttled like the words, logged,
  needs a matching `Origin`, and each use makes a device flagged "signed in with the recovery key". A rotation
  invalidates the saved entry.

*Why:* J2 made "K is never accepted from a non-loopback peer" a condition of the win, since the form sends a
reusable root secret over plain HTTP, the same flaw as a passphrase. J1 and J3 wanted the form, with the
password-manager contract, as a self-service path. Off by default meets J2, and the contract is how it works
when switched on (J1, J3). The user's own devices never need it: Chrome and the phone carry over, and Brave takes
a copied link. *Cost if wrong:* a lone new browser with no signed-in peer needs the terminal once, which an agent
can do for the user.

**52. Deferred, with the reason.**
- **Phase 2, the reverse flow (J2's graft 10).** A new browser shows a non-secret request code that a signed-in
  device approves after seeing the new device's own screen. It is for a device that cannot receive a link or scan
  a QR code (a TV, a locked-down PC); Chrome, Brave and the phone do not need it.
- **Phase 3, TLS.** A certificate for an internal name (ACME DNS-01 against the public zone, with the AD DNS
  pointing the name at .76), or `tailscale serve`. Then `Secure` and `__Host-pilot_session`, HSTS and Web
  Notifications. A passphrase or passkeys come only after TLS (J2): passkeys need a secure context and a domain
  name, and a passphrase is acceptable only once it no longer crosses plain HTTP.
- **Serving under `/pilot/` with `Path=/pilot`.** Optional hygiene, so browsers stop sending the cookie to
  :3000, :8200 and :9120. It is not isolation: a hostile service on 192.168.1.76 can request `/pilot/` on its own
  port and receive the cookie (J2), so it is not counted as a boundary.

### Every flow
1. **Deploy day, the user's browsers.** Chrome and the phone open the dashboard as usual. The old cookie
   becomes a device on the first page load and one notice appears. Nothing is typed or tapped. Brave (no old
   cookie, or not opened within 72 h) follows flow 3.
2. **First run with nothing carried over.** Open http://192.168.1.76:8780/ → 303 to `/pair` → "No browser
   signed in anywhere?" → run `python -m pilot dashboard-link` on the controller (a terminal, SSH, or ask the
   Codeman agent) → scan the printed QR code with the phone, or open the link on the desktop → "Sign in this
   browser?" → Sign in → the dashboard. Or type the three words on the page.
3. **Add Brave next to Chrome.** Chrome: ⋯ > Add a device > Copy link → paste into Brave's address bar → the
   confirm view, named "Brave on Windows" → Sign in → the dashboard; Chrome's sheet shows "Signed in: Brave on
   Windows". Or open the bare address in Brave and type "map orb cra".
4. **Add a phone.** Desktop: ⋯ > Add a device → point the phone camera at the QR code → the system browser
   opens `/pair#c=…` → Sign in. With no camera: open the address and type the words. Phone to desktop: the
   phone's sheet shows the words (the QR code is hidden below 600 px) and the desktop types them.
5. **A link from another app.** A signed-in browser goes straight into the page (Lax cookie). An in-app
   browser gets the sign-in page led by the warning and the address to copy → menu > Open in browser → the
   unspent link opens the same confirm view in the real browser → Sign in. Signing in inside the app anyway
   makes a device that works only there.
6. **Daily use.** The bookmark is the bare address: no secret, no prompt. The cookie is re-sent weekly and lasts
   while the browser is used.
7. **Sign out and revoke.** Settings > Devices > "Sign out this browser", Sign out on a row, or "Sign out all
   other devices"; from the CLI, `dashboard-devices revoke ID` or `revoke-all`. It applies on the next request,
   open streams close within 15 s, and the live run is never touched.
8. **Rotate.** After `game-pilot.service` restarts on the new code: `dashboard-key --rotate --keep <the user's
   devices>` → K changes in both processes within 2 s → the carry-over window closes, unkept carried-over
   devices are signed out, and nobody else is.
9. **Automation.** The K header from loopback is unchanged; `python -m pilot control …`; scoped `pgt_` tokens
   from the CLI for other machines; loud JSON errors; K from the LAN is refused and logged.
10. **Lockout.** No signed-in browser: `dashboard-link`. Words throttled: the link or QR code, or
    `dashboard-devices unlock`. Store corrupt: sign in again with `dashboard-link`. Compromise: `revoke-all`,
    `--rotate --keep none`, `dashboard-link`, then read the log.

### Endpoints
| Method, path | Who | Body / reply |
|---|---|---|
| `GET /pair` | public | The sign-in page; `?next=`, `?reason=` (a fixed set), `?check=1`. A 303 to `next` when signed in. signin.js switches to the confirm view when `#c=` is present. |
| `POST /pair` | public; JSON, or a form for typed words with a matching `Origin` | `{link}` or `{words}`, plus `{name, client, next}` → `pilot_session` cookie; JSON 200 `{next}` or form 303 to `/pair?check=1&next=`; 200 `{already}` (ruling 42); 401 `wrong_code`; 410 `used` / `expired`; 409 `conflict`; 429 `too_many` with `Retry-After` |
| `POST /pair/key` | public, only with `PILOT_KEY_SIGNIN=1`; form with a matching `Origin` | `username=pilot, key, next` → cookie, 303 (ruling 51) |
| `GET /api/auth/me` | any principal | `{via, device: {id, name, kind, legacy}, notices: […], add_device}` |
| `POST /api/auth/grants` | a browser session (not with `PILOT_ADD_DEVICE=cli`) | `{}` → `{id, words, link, qr_svg, expires_at}`; replaces this device's live grant |
| `GET /api/auth/grants/{id}` | the session that made it | `{state, device: {name, ip}}` |
| `POST /api/auth/grants/{id}/cancel` | the session that made it | `{}` |
| `GET /api/auth/devices` | a browser session | `{devices: […], scripts: […]}`, no hashes |
| `POST /api/auth/devices` | a browser session | `{action, id, name}`, where `action` is `rename`, `revoke`, `revoke_others` or `signout` |
| `GET /api/auth/log` | a browser session | the last 20 aggregated events |
| `POST /api/auth/unlock` | K from loopback | `{}` → clears the throttles (the CLI's `unlock`) |

Script tokens reach nothing under `/api/auth/` except `/me`. The live pilot (8790) gets no auth routes; it
accepts only the K header from loopback. UI data endpoints (not auth): `GET /api/view?campaign=`,
`GET /api/orders?campaign=&kind=&fate=&limit=`, `GET /api/health?run=`, `POST /api/capture`; `/status` additions
`info.attention`, `info.deciding`, `info.reserves`, `info.last_stand`, `info.game_health`, `info.auth_version`,
`question_deadline`, `default_if_silent`; `/api/campaigns` sorted by `month_index`, with `runs`, `empty`,
`state`.

### Security tests (pytest: new `tests/test_dashboard_auth.py`, extended `tests/test_dashboard_security.py`)
Where the PoC covered the same rule, its test in `ui-audit/auth-poc/test_auth_poc.py` is ported. aiohttp's
`TestClient` always connects from loopback, so every "from the LAN" case uses `make_mocked_request` with a
transport whose peername is 192.168.1.50. These tests are required: without them, a regression that accepts K
from the LAN would pass unnoticed.
- **Service key.** From 127.0.0.1 → the service principal. From a mocked LAN peer → 401
  `service_key_loopback_only` and an audit row. With `Forwarded` or `X-Forwarded-For` from loopback → not the
  service. Never in any `Set-Cookie`, `Location`, page or log line across a full flow. A rotation is picked up
  through mtime and inode without a restart (old K 401, new K 200). `LiveProxy` reloads once after a 401 and
  succeeds. `X-Pilot-Device` is ignored unless the principal is the service key.
- **Credential kinds.** A session value in `X-Pilot-Key` → 401. A `pgt_` token as a cookie → 401. A token or K
  in `?key=` → never accepted. A read token → 200 on GET, 403 `read_only` on POST. Any token → 403 on
  `/api/auth/devices` and `/api/auth/grants`.
- **Host.** `evil.example` → 421, including a rebinding `POST /pair` with a matching evil `Origin`. IP literals,
  `localhost`, the hostname, the FQDN and a `PILOT_DASHBOARD_HOSTS` name → allowed. With `PILOT_PUBLIC_URL` set,
  an HTML navigation on another host → 308; loopback requests and API calls → no redirect.
- **Store.** The file, `-wal` and `-shm` are 0600. After a WAL checkpoint the bytes contain no session, link or
  token secret and no plaintext words. A corrupt file is moved aside and an empty store starts. A revoke written
  by the CLI is seen by the viewer on the next request. `Telemetry.rebuild` leaves the file alone.
- **Grants.** A link works once and only through the JSON body: `GET /pair?c=…` is ignored, `GET /pair` twice
  and then a POST still works, and no GET sends `Set-Cookie`. Expiry at 600 s (injected clock). Words normalise
  (case, separators, 3-letter prefixes); 2 or 4 words and unknown prefixes are refused. The vendored list has
  1,296 unique prefixes. One live grant per device and three in total, the CLI exempt. `PILOT_ADD_DEVICE=cli` →
  403.
- **Throttles.** 5 wrong words from one address → 429 with `Retry-After`. 20 across addresses → words get 429
  for everyone while a valid link still signs in. 5 wrong words in total switch off the words of every live
  grant, and the link still works. A valid link from a locked address works. 20 parallel wrong POSTs from one
  address → exactly 5 checks (atomic). IPv6 addresses share a /64 bucket and `::ffff:a.b.c.d` counts as IPv4.
  `unlock` clears every bucket.
- **Conflict.** A spent grant presented by another client → the device it made is revoked (`conflict`), with an
  audit row and the notice in `/api/auth/me`. Presented again by the device it made → 200 `already`, nothing
  revoked.
- **Sessions.** A revoke → the next request gets 401 `revoked` with `by` and `at`. `revoke_others` keeps the
  caller; sign out clears the cookie. 180 days idle → `idle`. `Set-Cookie` is re-sent only after 7 days, and
  `last_seen` writes are throttled to 5 min. The stream on `/events` and the viewer's forwarded stream close
  within one keepalive (0.1 s in tests) after a revoke. Two addresses within 10 min → the badge.
- **CSRF.** A `text/plain` or form POST to `/control` → 403. A foreign `Origin` → 403; `Origin: null` → 403;
  `Sec-Fetch-Site: cross-site` → 403. A cookie-authenticated POST with no `Origin` → 403; a header-authenticated
  POST with no `Origin` from loopback → allowed. A form `POST /pair` with typed words and no `Origin` → 403, and
  with a matching `Origin` → 303. A form `POST /pair` carrying a link → 403. `OPTIONS` has no CORS headers.
- **`next`.** `//evil`, `/\evil`, `https://evil`, `javascript:…`, `/%0d%0a` and `/pair?…` → `/`; `/?key=x#t` →
  `/#t`; `/#tab=strategy` is kept.
- **Carry-over.** Inside the window: `GET /` with the old cookie → one device (`legacy_cookie`, `legacy = 1`),
  `pilot_session` set and `pilot_key` expired. `GET /`, `/events`, `/frame.jpg` and `/status` in parallel with
  the old cookie → exactly one device. The old cookie on `/status` alone → 200 and no device. `/?key=K` → 303 to
  `/pair#c=…` with no `Set-Cookie`. After 72 h or after a rotation: the old cookie is deleted with a 303 to
  `/pair?reason=old_link`, and every `?key=` value gets the same reply without being read. `--rotate --keep ID`
  keeps that legacy device and revokes the others (`rotate_unkept`).
- **Recovery form.** Off by default: `POST /pair/key` → 404, and no form field is ever compared with K. With
  `PILOT_KEY_SIGNIN=1` the page carries the password-manager contract (hidden `username`,
  `autocomplete="current-password"`, POST, 303), and a wrong key counts as a failure.
- **Headers and page.** Every response has `no-store`, `X-Frame-Options: DENY`, `frame-ancestors 'none'`,
  `nosniff` and a `Referrer-Policy`. `/pair` has the strict CSP, `Referrer-Policy: no-referrer`, a viewport
  meta, a `prefers-color-scheme` block, no inline `<script`, a POST form, the in-app warning for `; wv)` and
  Instagram user agents, and it escapes a hostile user agent and `next`.
- **Logs.** Capture all logging through a full flow (carry-over, add by link, add by words, conflict, revoke,
  rotate): no K, word triple, link secret, session or `pgt_` substring appears. The viewer's startup line has no
  `key=`. 100 bad words from one IP within one minute → one audit row with count 100.
- **401 shape.** API 401s are JSON with `error`, `reason` and `fix`, plus `WWW-Authenticate`. HTML navigations
  → 303 to `/pair?next=…&reason=…`.
- **CLI.** `dashboard-link` prints a `#c=` link, three words and a QR code, never K, and works with the viewer
  down; `--wait` sees the use. `dashboard-devices` list, rename, revoke, revoke-all, log and unlock work.
  `dashboard-token create` prints `pgt_…` once, with its scope. `dashboard-key --rotate` refuses with
  `PILOT_DASHBOARD_KEY` set, against a fake pre-change `/status`, and non-interactively without `--keep`.
  `control` exits non-zero with the server's error on a 401.
- **Config.** The live pilot's host defaults to 127.0.0.1, and its guard refuses cookies.
- **Existing tests.** `conftest.py` stays: it sends K from the test server's loopback, which yields the service
  principal. It gains an autouse `PILOT_AUTH_DB` in a temp dir. Of the 14 tests in `test_dashboard_security.py`,
  four assert the old behaviour and change: `test_dashboard_link_cli_prints_the_link` expects a `#c=` link and
  words, not the key; `test_everything_but_the_page_needs_the_key` expects `GET /` to 303 to `/pair`;
  `test_key_link_sets_a_strict_cookie_and_redirects` becomes "a valid `?key=` in the window redirects to
  `/pair#c=` without a cookie"; `test_the_access_page_offers_a_box_for_the_key` expects
  `method="post" action="/pair"` and `name="words"`. The other ten pass unchanged.

---

## Rollout

Work happens in a worktree (`feat/dashboard-v2`, AGENTS.md §9); each commit goes through `scripts/ci-commit.sh`
with its tests and updates `plan.md` / `issues.md` / README / ARCHITECTURE / `docs/pilot.md` as it lands.
**Branch order:** the Civ VI branch that changes `dashboard.html` must merge first; it has (469cd14; `git log
main..feat/civ6-levers` is empty as of 2026-09-27). `feat/stellaris-levers` (5 commits, including the
watchdog `09077d9` in `governor.py`) should merge before commit U3; if it has not passed review by then, U3
lands first and the watchdog's single `_needs_attention` call gets `category="stall"` in the merge.
**Deploy rule:** a viewer restart deploys the page, the view endpoints and auth for 8780; changes inside the
live pilot (attention object, info fields, bind address, `auth_version`) take effect when the pilot restarts,
which a deploy may do (ruling 36). Every page change must still work against a pilot that lacks the new fields.

| # | Commit | Testable on its own by |
|---|---|---|
| U0 | `fix(dashboard): truthful chips and Civ VI basics` — Civ VI in `GAME_WINDOWS`; `/api/campaigns` sorted by `month_index`; `trace.error` in Reasoning; NaN guard; pace uses `decide_turns`; plural "decisions"; clear Reasoning on campaign switch; stop polling `frame.jpg` when frames are off | pytest for campaigns sort and `/api/pc`; Playwright: no console errors on a Civ VI fixture |
| A1 | `feat(auth): device store, loopback-only service key, host allowlist, 72-hour carry-over` — `auth.py` (`KeySource`, SQLite store, guard, `security_headers`, credential kinds kept apart), `/api/auth/me`, sign out, SSE re-check and close, signed-out banner that stops the stream, `X-Pilot-Device` on forwards, startup line without the key | auth pytest: service key (mocked LAN peer), host, credential kinds, sessions, SSE close, carry-over, CSRF (`Origin` required on cookie mutations), headers, logs; the old cookie keeps working |
| A2 | `feat(auth): sign-in page, three-word codes and links, Add a device, Devices` — `/pair` ported from the PoC's `login.html`, `signin.js` (fragment code, Brave hint, `replaceState`, copy fallback), grants, atomic throttles, conflict revocation, `segno` QR, ⋯ > Add a device, Settings > Devices, `dashboard-link`, `dashboard-devices` (incl. `unlock`) | grant, throttle (incl. 20 parallel tries), conflict, form-fallback, `next`, recovery-form-off tests; Playwright `/pair` at 4 contexts, two-context sign-in by link and by words |
| A3 | `feat(pilot): live pilot binds loopback, honours X-Pilot-Device, reports auth_version; pilot control helper` — `PILOT_LIVE_HOST`, header-only guard, `by` in control and chat events, `python -m pilot control` | config test; the live guard refuses cookies; `control` exit codes against a fake server |
| A4 | `feat(auth): key rotation with a carried-over review; scoped script tokens` — `dashboard-key --rotate [--keep]`, `dashboard-token` | rotate refused with the env key and against a fake pre-change `/status`; `--keep` revokes the rest; token scope and kind tests |
| U1 | `style(dashboard): contrast tokens, voice rule, toasts instead of alert()` | Playwright contrast check on computed colors; no `alert` in source |
| U2 | `feat(dashboard): per-game view spec and readable names` — `corpora/*/dashboard.toml`, `/api/view`, id → name | spec test against `pillars.toml`; `/api/view` pytest |
| U3 | `feat(pilot,dashboard): governor line, attention card, title and favicon` — `info.attention` with categories, `info.deciding`, `/api/capture`, Civ VI screenshot | governor tests per category (fakes); Playwright needs-you fixture |
| U4 | `feat(dashboard): decision rows and Reasoning lead with the reason` — fates, cause(), outcomes in game units, triggers | `cause()` table test; Playwright row heights ≤ 140 px desktop |
| U5 | `feat(pilot,dashboard): Civ VI Orders tab` — order record, `/api/orders`, `info.reserves`, `info.last_stand`, `popups_quieted`, game health | `/api/orders` pytest on backfilled fixtures; governor emits tested |
| U6 | `feat(dashboard): Activity sentences, grouping, filters` | static test: every `emit("<kind>")` in `src/pilot` has a `describe` case |
| U7 | `feat(dashboard): phone layout and campaign list` — bottom nav, sheets, ⋯ menu | Playwright 390 px: no horizontal scroll, nav reachability |
| U8 | `feat(dashboard): per-game chart` — series, tick marks, one tab stop | Playwright keyboard: chart is one stop |
| U9 | `feat(pilot): opt-in ntfy notice when a stop lasts` | notifier test with a fake clock and fake HTTP |
| U10 | `feat(dashboard): Stellaris Actions tab` — after the pilot publishes action record, market, crisis, postures | fixtures from the levers branch |

**Auth deploy runbook.** A1 and A2 deploy together with one viewer restart, so every security graft (ruling 34)
is live from the first deploy. A3 reaches the live pilot with the same deploy (both services restart together); A4 is used after that.
0. **Before the first deploy:** ask for a DHCP reservation for 192.168.1.76 (optional) and set
   `PILOT_PUBLIC_URL=http://192.168.1.76:8780` in `game-pilot-view.service` (ruling 37). Install `segno`
   into the `.venv` the units run (`.venv/bin/pip install segno`), or Add a device has no QR code for the
   phone (ruling 44); `view` and `scripts/install-services.sh` say so when it is missing.
1. Merge A1-A2 after `scripts/ci.sh` prints CI OK and a code review. Restart `game-pilot-view.service` and
   `game-pilot.service` together (ruling 36). The new viewer forwards to the old live pilot with the unchanged K over loopback, so
   Pause, Stop and Talk keep working.
2. Within 72 h: open the dashboard in Chrome and on the phone (both carry over with no action), add Brave with a
   link copied from Chrome, and check that Settings > Devices lists the three; rename them if wanted.
3. Move the operator's watch scripts to `python -m pilot control`, or to reading the key on each call with
   `curl -fsS` (techwatch.sh's keyless POST to 8790 has been failing silently).
4. When the campaign ends and `game-pilot.service` next starts on the new code (A3, bound to loopback), run
   `python -m pilot dashboard-key --rotate --keep <the user's devices>`. That makes the key copies in the
   journal, chat apps and synced history worthless and ends the carry-over for good.
5. Verify (the manual checks under Testing), then flip each deployed line in `plan.md` to `[x]` and each fixed
   entry in `issues.md` (the key in cookies, links and the journal; 8790 on `0.0.0.0`; the `Origin` check not
   stopping rebinding; the locked page on phones; silent script 401s).

---

## Testing

- **pytest (CI).** Auth: the list above. APIs: `/api/view` per game, `/api/orders` (live record and campaign
  record agree on the same rows), `/api/health` (fallback counts from fixture events), `/api/campaigns` order
  and `empty`, `/status` new fields present and absent (old pilot), `/api/capture` refused without a session.
  Governors: `_needs_attention` sets each category at each call site; `info.reserves`, `info.last_stand`,
  `popups_quieted` emitted. Static: every emitted event kind has a sentence; every `dashboard.toml` key is a
  known metric; every recovery category is one the governors emit.
- **Playwright (`tests/ui/`, marker `ui`).** Python Playwright's own Chromium (the MCP's Chrome build is
  missing on this host), against a fixture viewer (`make_app` over a temp `runs/` with three campaigns: Civ VI
  live in needs-you, Stellaris history, GalCiv empty) and a fake live pilot; never against 8780/8790. Matrix:
  1440×900 and 390×844 (2×), light and dark (`colorScheme`). Checks per context: `scrollWidth ≤ clientWidth`;
  zero console errors and zero failed requests; governor line text per state fixture; attention card shows
  reason, age, steps and Resume focusable; computed text/background contrast ≥ 4.5:1 for text under 18.66 px
  bold / 24 px; tab-stop count before the Decisions list ≤ 20. Sign-in, ported from the PoC's `shots.py`
  checks: `/pair` renders the ported shell with no overflow and no console errors in every context, including
  the confirm view and the wrong-words, too-many-tries and old-link states; a `; wv)` user agent shows the
  in-app warning; two-context sign-in (one context signed in, one on `/pair`) completes by link, with no `#c=`
  left in the address bar afterwards, and by typed 3-letter prefixes; the Add sheet's Copy link works with
  `navigator.clipboard` absent (plain HTTP); a context whose `Set-Cookie` is stripped by a route handler lands
  on the cookie-blocked state; a revoked session shows the signed-out banner and its stream stops. Screenshots
  are saved to the test's tmp dir for review. `playwright` joins the `dev` extra; `ci.sh` runs `pytest -m ui`
  when Chromium is installed, and `ci-commit.sh` fails a commit that stages `dashboard.html`, `pair.html`,
  `signin.js` or `auth.py` while the UI tests were skipped.
- **Manual, after deploy (read-only).** Chrome and the phone carry over with no action, and Devices lists them;
  Brave signs in with a link copied from Chrome and is named "Brave on Windows"; the phone camera opens a QR
  link in the system browser; a sign-in link sent through a chat app survives "Open in browser"; confirm the
  governor line against `/status`.

## Out of scope
TLS, `Secure`/`__Host-` cookies, HSTS, Web Push/Notifications, passkeys, a passphrase; the reverse sign-in
flow (phase 2, ruling 52); the `/pilot/` path prefix; several hosts in one dashboard (L1); last-stand reports on
the chart beyond a mark (L2); cross-campaign analytics (L3); a GalCiv screen-play view beyond the latest frame
and blockers (L4); read-only share links (L5); token and cost budgets (L6); any change to the controller, the
agent, or the agent's own token on 8765; the Stellaris crisis and market logic themselves (only their views).

## Unverified, in one place
- A screenshot through the controller during Civ VI autoplay does not disturb the game (ruling 7).
- Which ntfy server and topic the user wants, and that the phone has the app (ruling 8).
- Which keys telemetry `SCORED` records for Civ VI, and whether the last-stand report carries walls HP (22, 27).
- That `segno` (pure Python, no dependencies) is acceptable for server-side QR SVGs; no QR library is installed.
- That the in-app browser user-agent markers still match current Slack, Discord and Gmail builds (43).
- That "Open in browser" in Slack, Gmail and WhatsApp carries the URL fragment, so an unspent `#c=` link
  survives the hop (43).
- That the in-app WebViews the user meets send `Origin` on same-origin POSTs; the no-script form depends on it
  (49).
- That `document.execCommand('copy')` still works on plain HTTP in current Chrome and Brave (44).
- That the user's phone camera app opens QR links in the system browser, not an in-app view (40, 44).
- That the controller's DHCP lease can be reserved on this domain-managed network (37).
- The Stellaris data shapes in rulings 23-26 follow the levers design, not built code.

# Stellaris governor, levers: action record, market buy rules, war crisis, mod postures, planet check, stall watchdog

Date: 2026-09-27. Status: approved in a hands-off run (2026-09-27); ruling 20 accepted as written (the AI
reverted console-set policies within a month anyway, so obeying the policy lock costs little). This is an addendum to
`docs/design/2026-09-26-weighted-pillars-design.md` (its rulings 1-13; ruling 13 is the directive record
and stall rule), `2026-09-26-strategy-layer-design.md` and `2026-09-26-game-pillars-design.md`. It carries
over the Civ VI levers design (`2026-09-27-civ6-levers-design.md`, "the Civ VI design" below) where that
design fits Stellaris. The rulings here are numbered from 1. Other documents' rulings are cited with their
document's name.

Base: `main` at bf181e1 (code line numbers). Civ VI branch: `feat/civ6-levers` at 5a54fff. The code map
used dab898d, and the branch has moved since. Its `governor.py` diff is two hunks, at 1367 (`_records_section`)
and 1431 (the review prompt). Game: Stellaris 4.5.1 on mini-rig2. It is not running now, because Civ VI
holds the one Steam account. Anything marked **unverified** has not been observed in this build. The
section "Unverified, in one place" at the end collects every such item.

Sources:
- `runs/telemetry.sqlite`, read only: 735 Stellaris decisions, 4,859 metric rows, 127 `strategy_action`
  events, 747 traces. Four campaigns: UNE1 (spike), UNE2, Theia (Federated Theian Preservers) and Gaea
  (Blooms of Gaea).
- `games/stellaris/journal.md`, `games/stellaris-spike/journal.md`, `issues.md`,
  and a post-mortem of the Theian campaign (working notes, not in the repo).
- Local saves: `a2272.sav` (Theia, 2272.05.01), `t.sav` (2393.11.01), `new*.sav` (UNE2) and the Rust
  fixtures.
- Game files: `incoming/stellaris` plus a local copy of the AI-related `common/` folders (defines, war_goals,
  colony_automation, country_types, on_actions, …), and a few files read from the PC through the agent (at most
  8 GET reads per pass, spaced 3 s or more).
- Five research passes: the code map, campaign data, mod levers, crisis and buy-outs, and planet
  development. Seven adversarial votes on them: 3 on the mod levers, 2 on crisis and buy-outs, 2 on planet
  development.

Writing this design read no files from the PC and sent no input to any game. Five further checks from
telemetry and the local saves are marked "(checked here)".

---

## Evidence

**E1. Directives decide little. The native AI's own trajectory dominates.**
- Measured against the peer median, every directive in every campaign moved its own metric by 0.03 × median
  per year or less (campaign data §1).
- Weighted pillars (2263.02-2274.10 in Gaea, 11.6-11.7 clean years):
  - military growth rose from +7.2 to +27.4 a year, and economy from +22.7 to +36.5 a year, against the
    preceding stretch of the same length (campaign summary);
  - against the whole of 2200-2263 the rises were +14.5 → +27.4 and +15.7 → +36.5;
  - milestone-missed triggers fell from 23 to 3 (40 → 3 counting every mention);
  - the suggestion was followed 13 of 14 times;
  - military ÷ median still went 0.35 → 0.32, and every rank (military 8, economy 7, systems 7) stayed
    where it was.
- **Conclusion:** better choices among six directives do not move the empire's standing. The levers below
  work beside the directive, not through it.

**E2. The stall rule compares absolute rates across eras** (weighted-pillars ruling 13; campaign data §1).

| Campaign, directive | Own metric per year, held vs otherwise | Metric ÷ median per year, held vs otherwise |
|---|---|---|
| Theia defend | military +171.5 vs +121.5 ("works") | +0.008 vs −0.009 |
| UNE2 expand | systems +0.73 vs +0.06 ("works") | −0.032 vs −0.003 |
| UNE2 defend | military −9.2 vs +57.8 (stall) | −0.009 vs +0.005 |
| Gaea tech_rush | techs +0.52 vs +0.80 (stall; fired 8×) | −0.006 vs 0.000 |

- Theia's `defend` looks effective only because most of its 142.6 years were after 2280, when everything
  grew faster.
- UNE2's `expand` was held early, when every empire expands fast.

**E3. What the player actions did** (strategy_action events, all campaigns).

| Action | Outcome |
|---|---|
| tech | 53 skipped ("no preferred tech offered in a field under 10% done"; Gaea 47); 2 clicked (tech_terrestrial_sculpting 2220.02 did not stick; tech_doctrine_fleet_size_2 2254.07 never verified); 1 failed (window gone) |
| market | 24 orders sent (16 adds, 8 removals); 6 did not stick; 2 agent timeouts; 38 skipped (25 over 20% of income, 8 not IDLE, 5 both) |

- Market stick by resource: food 6 of 6, minerals 3 of 3, consumer goods 0 of 3, alloys 0 of 1, rare
  crystals 1 of 3.
- **All 6 failures are click arithmetic, not the AI** (crisis vote 2, with run data):
  - a new monthly trade starts at 0.1 × the resource's `market_amount` (`MARKET_MONTHLY_TRADE_FRACTION`,
    defines :2065): energy, minerals and food 10, consumer goods 5, alloys 2.5, motes, gases and crystals
    1, living metal, Zro and dark matter 0.5 (`00_strategic_resources.txt`, checked here);
  - `amount_clicks` assumes 10 for every resource (`manifest.toml` `new_trade_amount = 10`;
    `stellaris.rs` 1608-1614);
  - run 20260926-152042: "buy rare_crystals 15" was read back from the next save as 6, which is 1 + 5 clicks;
  - every failed add falls to 0 under that rule;
  - orders that land do execute: rare-crystal stock loss went from 17.8 to 11.8 a month once the order of 6
    existed.
- Trade actually made by market orders over all campaigns: 943 food and 237 minerals sold, about 830
  trade. That is negligible.

**E4. Directives read back only in part.**
- The flag appeared in the next save for 101 of 110 switches (92%).
- 7 directives were never confirmed in game.log: expand twice (2218-19, the selection bug, now fixed) and
  tech_rush 5 times (2348, then 2458-2460).
- **Policies:** the AI reverts console policies set with `cooldown = no`. In the 2272.05.01 save (country
  0, checked here):
  - `economic_policy = economic_policy_balanced` is dated 2272.01.01, one month after tech_rush set
    civilian (decision 2271.12.01, "applied");
  - `diplomatic_stance = diplo_stance_cooperative` is dated 2270.11.29, right after peace, replacing
    defend's belligerent.
- Yet civilian held 2252.07 to about 2256 once it was re-applied (postmortem :119, :153).
- So the stick is variable and unmeasured. issues.md:27 (open) records the earlier case.
- Two fairness gaps:
  - `set_policy … cooldown = no` (stellaris.rs:768) skips the player's 10-year lock
    (`POLICY_YEARS = 10`, defines :913);
  - diplomatic_stance and war_philosophy have `allow = { is_at_war = no }` (00_policies.txt:28-30,
    1551-1553), yet `defend` sets belligerent mid-war under only the option's `valid`.

**E5. Idle resources, not deficits, were the economic loss** (campaign data §5).
- Theia discarded **987,121 trade** (457 months at cap) and **592,554 energy** (400 months at cap). UNE2
  discarded 42,856 trade. At base prices plus the 30% fee that is about 270k alloys, 5.1× Theia's whole
  alloy income.
- Deficits almost never threatened solvency. Months with stock under 6 months of the deficit were 0-11 per
  resource, because the AI buys by itself:
  - it buys when cover is under 6 months (`AI_MARKET_BUY_MONTHS_OF_COVER = 6`, defines :2626);
  - it spends trade on the market from 2,500 (`trade_expenditure_trade`, weight 0.5);
  - it starts selling under 1,000 (defines :2617).
- The AI's own buys are one-time bulk buys of about 100 base amounts at about 2× base (crisis vote 2):
  - rare crystals +992 for about 16.9k trade (2458.09→10) and +988 for 17.1k (2463.08→09);
  - consumer goods +4,951 for 18.5k (2458.08→09).
- Alloys piled up where they had no use: Gaea alloys IDLE 179 months (peak 8,727 in 2248), with 80/80 fleet
  use in 2240 and 7,000-8,700 idle.

**E6. A military-ratio trigger would always be on** (checked here, metric rows with neighbours or peer
medians). This is the Stellaris analogue of the Civ VI design's E6.

| Campaign | At war | Military < 0.5 × strongest neighbour | < 0.25 × strongest neighbour | < 0.5 × peer median |
|---|---|---|---|---|
| UNE2 | 47% | 97% | 55% | 53% |
| Theia | 90% | 90% | 45% | 42% |
| Gaea | 0% | 96% | 86% | 55% |

- All 15 wars declared on us came when our military was 0.01-0.25 of the enemy's.
- Gaea sat below 0.25 × its strongest neighbour 86% of the time and had no war in 89 years.
- A ratio says who could attack, not whether we are losing.

**E7. How wars were lost** (campaign data §4).
- Theia 2254-2270:
  - systems 32 → 13, colonies 9 → 3;
  - military 0 in 36 monthly saves (2261.01-2265.06);
  - the capital, which held the only shipyard, was occupied from 2257.03;
  - alloys fell from +23 to +1.8-5 a month;
  - at 2263, 17.9k energy and 9.0k trade sat idle (about 4,150 alloys).
- UNE2 2256-2261: systems 21 → 12, never regained.
- Theia 2299-2309: 22 → 15.
- `defend` was held for 16 years with no exit test (strategy.md §12). In 2289-2294 it kept the empire alive
  and did not make it stronger:
  - military 2,651 against a median of 7,201;
  - alloys +19.9 a month;
  - a "147/147 naval capacity" reading that came from a model's retrospective, not the save. The Theian
    postmortem showed the same kind of reading was false once ("51/115" read as capped).
- "Won all 23 battles" while systems fell 21 → 15: `war_of` counts allies' battles (stellaris.rs:1935-1936).

**E8. Replaying a crisis rule over the campaigns** (checked here). The replay enters a crisis when a war is
on and, within the last 12 months, any of these happened:
- systems fell by 2 or more;
- military fell to half or less;
- a colony was lost.

It leaves after 6 quiet monthly saves.

| Campaign | Months flagged | Episodes | Notes |
|---|---|---|---|
| UNE2 | 33 of 1,124 (3%) | 5 | 2256.02-2257.11 and 2260.01-2261.04 cover the 21 → 12 loss |
| Theia | 280 of 2,642 (11%) | 25 | first collapse flagged from 2256.08, **7 months before** the capital fell (2257.03) |
| Gaea | 0 of 979 | 0 | no wars |

Occupation, invasions and own-battle counts are not in the old rows, so the replay undercounts entries.

**E9. What the mod can reach** (mod-levers finding, 3 votes, none refuted it).
- `economic_plans` merge additively (vanilla README `00_example.txt`:2-7) and are re-picked monthly.
  - Subplan `focus` and `naval_cap` steer construction (Patch 4.5) without holding a plan open.
  - Focus is a 2× build score (defines :2131) against 100× for a deficit (:2129); naval-cap buildings score
    3× (:2143).
  - Every vanilla naval-cap subplan is optional + scaling and gated at `used_naval_capacity_percent > 0.85`.
    A non-scaling one has no vanilla precedent.
- `ai_budget` entries are additive and flag-gated in country scope.
  - Vanilla funds ship upgrades only at peace (01_alloys_budget.txt:82-102).
  - At full naval capacity it cuts ships to 0.75× and doubles starbases.
- Building `ai_weight` is unused in 4.5 (buildings/00_example.txt:189). Districts and triggered
  `ai_resource_production` blocks still count (mod votes 1 and 2).
- Under `human_ai`, `is_ai` is `no` (spike journal :103), so vanilla weights gated on `is_ai = yes` skip us.
- **No live evidence yet** that any flag-gated entry changed what our empire does. The budget category fix
  for `expand` (issues.md:39) has not run live.
- The save stores the mod by name, and install-mod uploads the folder recursively. A changed mod joining an
  existing save is unverified.

**E10. Planets** (planet-development finding, 2 votes).
- Across 617 prompts with planet lines:
  - amenities below −100 in 9-19% of planet observations;
  - housing below 0 in 0-2.3%;
  - stability below 50 in 1.8-3.3%.
- Every observation of stability below 25 was during a war:
  - Arnvoss, 2290-96, stability 0 from 2294.05, lost 2296, deferred for 7.5 years with "wait for peace";
  - Largoll, 6.3 (2338);
  - the capital, 16.9 (2383.05), gone 2383.07 with −6,627 pops (32%).
- Cost of amenity deficits is about 0.5% of job output. That is an order-of-magnitude estimate built on a
  pre-4.0 coefficient (vote 2).
- No directive clears grown-colony deficits: consolidate_economy +5 to +14 a year, clearing 2 of 63-70
  year-intervals. The intervals are dominated by 3 late Theian planets (vote 1).
- `learned/strategy.md`:29 and :191 claim the opposite.
- The rival development gap is confounded: captain AIs get +25% workforce, +5 stability and resettlement of
  unemployed pops (static_modifiers :150-162; vote 2).
- The AI never uses planet automation (0 of 480 colonies) or zone_urban (0 of 1,656 zones).
- No flag-gated zone or designation reaches amenities: every amenity zone needs `resort_colony` (vote 2).

**E11. Popups and stalls.**
- `EVENT_MESSAGE_TYPE` is the only message type with `default_autopause = yes` (00_message_types.txt:197-207).
  That it cannot be disabled is inferred from `can_disable = no`. The PC's message settings are empty
  (defaults).
- Under `human_ai` the AI answers events ("selectedOption 0, human -1", issues.md:31). War declarations stay
  on screen without pausing (issues.md:35).
- 0 of 7 Stellaris `needs_attention` events came from a popup.
- `_run_until_next_decision` (governor.py 1022-1064) has no check for a date that stops advancing.
- Real seconds per in-game month, same-run consecutive rows (checked here; these include decision time, so
  they overstate play time):

  | Campaign | Median | p99 | Max |
  |---|---|---|---|
  | UNE1 | 10.8 s | 17 s | 28 s |
  | UNE2 | 2.1 s | 40 s | 191 s |
  | Theia | 6.4 s | 92 s | 247 s |
  | Gaea | 6.3 s | 91 s | 176 s |

- An agent timeout left Gaea ungoverned for 94 months (2274.10-2282.08, game unpaused). Auto-recover
  (54fa82a) has had 0 live events since.

**E12. Expansion stalls were not budget stalls.**
- Gaea stayed at 9-10 systems for 41 years (2215-2256) with influence at the 1,000 cap for 37 years.
- 8-14 unclaimed systems lay within 2 jumps, with at most 1 surveyed. `expand` gave +1 system over 10 held
  years.
- Surveying capacity is a script value (`desired_science_ships`), overridable only whole-file
  (`00_script_values.txt`:306-367).

**E13. Adversarial votes.**

| Finding | Votes | Refuted overall | Confidence |
|---|---|---|---|
| Mod levers | 3 | 0 of 3 | high, medium, medium |
| Crisis and buy-outs | 2 | 0 of 2 | high, medium |
| Planet development | 2 | 0 of 2 | high, medium |

No finding was refuted as a whole. Individual levers were: ruling 17 tallies each one. Majority means 2 of 3
votes for the mod levers, and 2 of 2 for the other two findings.

---

## What transfers from the Civ VI design

| Civ VI | Stellaris | Ruling |
|---|---|---|
| Order record per kind with stick rates (12-15) | **Transfers.** Keys are directive, tech, market, posture and crisis; the clock is months. | 2-6 |
| No pressure factor for a failing channel (15) | **Transfers** for tech, market and postures. Directives keep weighted-pillars ruling 13, corrected to relative rates. | 6, 7 |
| Research or civic blocker always filled (16) | **Does not transfer.** The AI always picks research. The tech lever's problem is that it never fires (E3). | 6 |
| Danger is `in_danger`, not `threatened` (17) | **Transfers as a warning.** A military ratio is "threatened" (E6). Entry needs losses. | 12 |
| Reserves (18) | **Transfers:** a trade reserve of 2,500. There is no pantheon or prophet analogue. | 9 |
| Defenders first, faith first (19) | **Partly.** Alloys first in a war crisis, but only with naval room and a free shipyard. There is no second currency: everything is paid in trade. | 9, 13 |
| Never buy what the AI finishes anyway (20) | **Transfers** as "never buy what the AI buys anyway" (under 6 months of cover, or its bought counter rose). | 9 |
| Buy must-haves rather than queue (20) | **Does not transfer.** Ships and buildings cannot be bought, and there is no queue to jump. | 11 |
| Walls produced, never bought (21) | **Does not transfer** (no analogue). | — |
| Scripted last stand (22-27) | **Does not transfer.** The AI moves fleets and has its own last stand (`AI_NO_RETREAT_LIMIT = 3`; flees above 2× hostile power, defines :2248, :2271). A war-crisis overlay replaces it. | 12-16 |
| Mod-steered AI priorities, gated probe (28) | **Transfers, stronger.** Plans and budgets are re-read monthly, with no 20-turn lock. Still probe-gated, because no live effect has been seen (E9). | 17-21 |
| AI intent read-only (29) | **Partly.** The save shows construction items per planet, used by the planet check. There is no recommendation API. | 1, 22 |
| Placement planner (30) | **Does not transfer.** Stellaris has zones and districts with no adjacency. The planet check is the read-only analogue. | 22 |
| Popups hold the engine (T134 wonder movie) | **Transfers** as a date-stall watchdog. | 23 |

---

## Rulings

### Shared prerequisite

1. **Briefing additions, read-only (stellaris.rs, one pass).**
   - **Decision.** `brief_gamestate` gains the fields below. Python reads each with `.get`, and every
     to_text line prints only when non-empty or flagged, so `text_briefing_is_compact_and_flags_deficits`
     stays under 4,000 bytes.

     | For ruling | JSON field | Save source |
     |---|---|---|
     | 3 | `policy_dates` (policy → date) | `active_policies[].date` (seen in the 2272 save) |
     | 9-10 | `market = {kind: galactic\|internal, fluct: {res: pct}, bought: {res}, sold: {res}, trades_net: {res}}` | top-level `market` (`fluctuations`, `resources_bought`/`resources_sold` for our country, `internal_market_fluctuations`); `budget.last_month.trade_balance.monthly_trades` |
     | 12-16 | `planets[].occupied`; `wars[].force_peace` (ours, theirs, date); `wars[].own_battles_12m {won, lost, ships_lost, ground_at_our_colonies}`; `shipyards[] {system, occupied}` | planet `owner` ≠ `controller`; war `*_force_peace*`; battles filtered to those listing **our** country (not our side); `starbase_mgr` with a `shipyard` module |
     | 19 | `governor_vars` (e.g. `governor_naval_cap`, `governor_naval_used`) | `country.variables` |
     | 22 | `planets[].{amenities_usage, total_housing, employable, jobs_open, unemployed, designation, district_levels, queued, growth}` | colony block, `pop_jobs`, `districts`, `construction.item_mgr` |

   - The market resource index mapping (0 energy … 10 alloys …) is inferred from `galactic_market_resources`.
     It is **unverified** until one PC read of `common/strategic_resources`; the local scratch copy
     `crisis/00_strategic_resources.txt` may already settle it.
   - **Fix with it:** own battles count only battles that list our country. The old "battles won" line stays
     as "our side".
   - **Why.** Every lever below needs one of these fields (E3-E10). issues.md:26 lists the gaps.
   - **Cost if wrong.** A slower briefing parse (the sections are already walked) and a field that reads
     empty. Each ruling names its fallback when its field is absent.

### A. The action record

2. **Every action is followed until it resolves.**
   - **Decision.** A pure module `src/pilot/stellaris_record.py` classifies each action from the saves that
     follow.

     | Key | Took / held / completed | Overridden / did not take / failed | Neutral (excluded from rates) |
     |---|---|---|---|
     | `directive <name>` | `took` when the flag is in the next save and every policy the console reported as set (ruling 3) reads back; `held` at supersede if nothing reverted | `overridden`: a reported policy reads back different with a `policy_dates` entry after our apply (the detail names the AI's option and date); `failed`: no flag in the next save | `superseded` (our next directive); `locked` (`can_set_policy` false, ruling 20) |
     | `tech` | `researched` (gone from `current` and `alternatives`); `held` (still current at the next review) | `did_not_stick` (offered, not current), as `_carry_out_tech_actions` 1249-1253 today | `nothing to pick` replies, counted apart as no-ops |
     | `market <buy\|sell> <res>` | `took` (the next save's `market_orders` equal what was synced); `held` (still present at supersede or after 24 months) | `did_not_take` (differs at the next save); `removed` (gone later without our sync) | orders skipped by briefing rules (logged as today) |
     | `posture <name>` | `took` (flag present in the next save) | `did_not_take` | `superseded` |
     | `crisis <step>` | as the step's own kind | as the step's own kind | — |

   - **Why.** E3 and E4: sending an order is not the outcome.
     - The market record would have shown "consumer goods 0 of 3, alloys 0 of 1" and pointed at the screen
       arithmetic long before 6 failures.
     - The directive record would have caught the civilian revert (2272.01.01) within one save.
   - **Cost if wrong.** A policy the AI changed for a reason of its own (e.g. a war that bans a stance) reads
     as `overridden`. The detail names the option and date. A reader can tell, and the rate is advisory
     (ruling 6).

3. **The console reports which policies it set.**
   - **Decision.**
     - `Directives::console_lines` (stellaris.rs:752-777) adds `log = "GOVERNOR_POLICY <policy> <option> <nonce>"`
       inside each policy's `if = { limit = { … } set_policy … }`. After ruling 20 the limit includes
       `can_set_policy`.
     - `apply_directive` (1297-1328) returns the markers it saw in game.log, and the `stellaris_directive`
       MCP reply lists them.
     - The governor stores that set as the directive's baseline.
     - A policy without a marker is `locked`, not a failure.
     - `load_directive_policies(corpus)` next to `pillars._directives` gives Python the mapping.
   - **Why.** Only the game can evaluate `valid`, `allow` and `can_set_policy`. Python would guess, and E4
     shows guesses are wrong (belligerent mid-war).
   - **Cost if wrong.** game.log drops a line repeated on the same in-game day. The nonce avoids that, as
     for `GOVERNOR_APPLIED`. A lost marker makes a set policy read as `locked`, which is excluded from rates.

4. **Tracked across decisions and persisted, in the Civ VI shape.**
   - **Decision.**
     - Each resolved action emits `order_outcome` with `{kind, key, id, result, by, detail, turn=months(date), date}`.
       This is the Civ VI row shape, so the dashboard's `order_record` view renders Stellaris unchanged.
     - Tracking is updated on every new save in `_run_until_next_decision`, after the metrics row, through a
       new `self._follow(b)`. Resolutions therefore carry the month of the change.
     - `_set_campaign` (987-992) calls a new `_load_action_record()` after `_load_campaign_state()`, through
       the branch's `telemetry.campaign_events(cid, "order_outcome")`. It is **not** put inside
       `_load_campaign_state`, which Civ6Governor shares.
     - The tech state (`_pending_pick`, `_tech_misses`) and market state (`_pending_market`, `_market_stuck`)
       stop resetting their *history* at each review (1420). The "skip until the next review" behaviour
       stays.
   - **Why.** Campaigns span many runs: 7-11 per Stellaris campaign (Theia 8, Gaea 9, UNE2 11; checked here). The Gaea gap shows play continuing with
     no decision.
   - **Cost if wrong.** A stale entry after a campaign switch. Campaign ids include the game, and the save
     folder guard already stops cross-talk.

5. **Stick rate per key, with a months clock.**
   - **Decision.** Add `[orders]` to `corpora/stellaris/pillars.toml` (the branch's `OrdersSpec`):

     | Key | Value | Meaning |
     |---|---|---|
     | `window_turns` | 120 | months (10 in-game years) |
     | `min_resolved` | 6 | widen back until 6 resolved of the key |
     | `min_samples` | `{ other = 3 }` | every Stellaris key falls in the `other` group |
     | `weak_rate` | 0.5 | at or below: flagged |
     | `open_cap_turns` | 24 | months followed at most |
     | `open_grace_turns` | 1 | |

     - Rate = (took + held + researched) / (those + overridden + did_not_take + failed + did_not_stick).
     - Below the minimum the record shows counts without a percentage.
     - The table's comment says the "turns" keys are months.
   - **Why.**
     - Directive switches came one per 3.4-7.6 years (15 in 114 years, 60 in 266, 26 in 89). The Civ VI
       window of 30 would hold under one switch.
     - Ten years holds 1.3-2.9, and widening to 6 resolved covers roughly 20-45 years of a campaign.
     - Market and tech resolve at every sync, so they fill faster.
   - **Cost if wrong.** A flag on thin data. Only the market enforcement (ruling 6) acts on a flag, and it
     clears itself on recalibration.

6. **Where the record goes. One narrow enforcement.**
   - **Decision.**
     - **Decision prompt:** a section "Action record in this campaign" after the past outcomes (1112-1117)
       and before the standing orders (1118). One line per key, e.g.
       `directive tech_rush: 4 judged; 2 held, 2 overridden (economic_policy → balanced on 2272.01.01)`.
     - **Strategist:** a new prompt element `_action_record_section()`, placed **before** the branch's
       `_records_section()` and included only when non-empty.
       - The directive-record heading and its adjacency to "Latest briefing" stay byte-identical, so the
         branch's `test_the_stellaris_review_keeps_its_directive_record_heading` passes.
       - Civ6Governor never fills the Stellaris record, so its section is empty and omitted.
     - **Dashboard:** `log.state.info["order_record"]`, the same key and shape as the branch.
     - **Market enforcement.** Two `did_not_take` in a row for the same (side, resource) suspend that
       resource until `[ui.market]` changes.
       - Each row stores a hash of the `[ui.market]` table, and a recalibration commit lifts the suspension.
       - This replaces today's `_market_stuck`, which blocks every order until the next review.
     - **Tech.** Two changes, both advisory:
       - no-ops are counted, and the record says "your preferred techs matched the offer 3 times in 56
         chances";
       - after 3 no-op syncs since the last review, the next review prompt lists the currently offered
         alternatives per field and asks that `prefer_techs` name at least one of them.
     - **Pressure:** no new factor. Directives keep weighted-pillars ruling 13, as corrected by ruling 7.
       Tech, market and posture records are advisory, as the Civ VI design's ruling 15 argues: a failing
       channel is not a failing pillar.
   - **Why.**
     - E3: the six market failures were deterministic and repeated. A suspension tied to the calibration
       stops repeats and clears itself when the arithmetic is fixed.
     - The tech lever acted twice in 56 chances because the preferred list rarely met the offer. More
       advice about the offer is the cheapest fix.
   - **Cost if wrong.** A resource suspended by two unlucky failures (e.g. an agent timeout counts as
     `failed`, not `did_not_take`, so it does not suspend). The line names the suspension and how to clear
     it.

7. **Weighted-pillars ruling 13, corrected: efficacy relative to the peer median.**
   - **Decision.**
     - `directive_record` (strategy.py 535-556) measures the per-year change of *ours ÷ peer median* when a
       row carries the metric's median (military, economy, tech, systems, pops, colonies, techs). Ranks stay
       as they are, and metrics without a median stay absolute.
     - Rates are rounded to 3 decimals, and the frame prints "military ÷ median +0.008/yr held vs −0.009/yr
       otherwise".
     - Stall: held ≥ `stall_years` and held rate ≤ other rate, as before.
     - **Blocked hint for expand:** when `room_surveyed` is 0 and the influence stock is at 950 or more for
       12 months, the frame adds "expand cannot claim here: no surveyed room; influence is not the limit".
     - Civ VI is unaffected: its `stall_years = 0`, and the dashboard shows whatever the function returns.
   - **Why.**
     - E2: absolute rates rewarded directives held late in the game, and they flip two verdicts (Theia
       defend, UNE2 expand).
     - E12: expand's 41-year stall was a survey problem, which the stall rule saw only as "slow".
   - **Cost if wrong.** A different set of directives is damped. The rule stays at 0.5 × and advisory in
     the frame, so a wrong damp costs pressure, not a forced switch.

### B. Market buy rules

8. **Fix the monthly-trade start amount first.**
   - **Decision.**
     - `manifest.toml` `new_trade_amount` becomes a per-resource table equal to 0.1 × `market_amount`:
       energy, minerals and food 10; consumer goods 5; motes, gases and crystals 1.
     - Alloys (2.5) and the three sr_* resources (0.5) are **refused before sending** ("start amount not
       measured") until L2 shows how the dialog displays and steps a fractional start.
     - `amount_clicks` takes the start per resource.
   - **Why.** E3. The start amount explains all six failed adds, and run 20260926-152042 confirms it
     directly (15 → 6).
   - **Cost if wrong.** If the dialog does not start at 0.1 × `market_amount` for consumer goods, those orders
     keep failing. The record (ruling 6) suspends the resource after two, and L2 settles it.

9. **Buy rules, with numbers.** The price model and each rule below are checked at every sync, for declared
   buys and for automatic ones.
   - **Price model.** Price per unit = base × (1 + fluct) × (1 + fee), with fee 0.30 (minimum 0.05).
     - Base prices, from `market_price 100 / market_amount`: energy, minerals and food 1; consumer goods 2;
       alloys 4; motes, gases and crystals 10; living metal, Zro and dark matter 20.
     - `fluct` comes from ruling 1. Without it, the rule assumes 0 and the line says "price unknown".
     - `cost` = amount × price per month.
   - **Reserve.** A buy is allowed only if trade − 12 × max(0, cost − trade_net) ≥ **2,500**.
     - 2,500 is where the AI's own market spending starts.
     - The AI starts selling under 1,000.
   - **Spend cap.** cost ≤ **0.25** × max(trade_net, 0) + (trade − 2,500) / **24**.
     - The second term spends a surplus over two years.
     - In a war crisis (ruling 13), for alloys only, the first term's share is **0.5**.
   - **Price guard.**
     - Skip while the resource's `fluct` is above **+50%**; never buy above **+100%**.
     - Monthly volume is at most **1 base amount** on the internal market and **6** on the galactic market
       (alloys 25 or 150; consumer goods 50 or 300; strategic 10 or 60).
     - The volume figures are an inference: prices return to base over 1800 days from +400% (about 6.7% a
       month on the galactic market, 3× slower on the internal one), and each base amount traded adds 1%
       (2% internal). **Unverified** that the decay is linear; L1 compares the save's fluctuation with the
       Market screen.
   - **Never buy what the AI buys anyway.** Skip R when any of these holds:
     - net(R) < 0 and stock(R) < 6 × |net(R)|, because the AI buys there itself;
     - our `bought[R]` rose since the last save;
     - R is flagged IDLE;
     - R is alloys and the fleet is known to be at or above 95% of naval capacity (ruling 19) while no war
       crisis is on, which is Gaea's 80/80 with 8.7k idle.
   - **What may be bought.** Declared orders come first, then automatic ones in this order:
     1. **War crisis alloys** (ruling 13).
     2. **Deficit cover:** R with net < 0 and cover between 6 and 24 months (36 for motes, gases and
        crystals). Amount is min(1.2 × |net|, the volume cap).
     3. **Idle-trade fill:** when the briefing flags trade IDLE and no declared order passed, fill the slot
        with the first candidate from 1-2. If none qualifies, buy nothing, and the frame says "trade idle:
        nothing qualifies to buy (reason)".
   - **Amount limit.**
     - `amount_max` goes from 25 to **100** (pillars.toml and mcp.rs `MARKET_AMOUNT_MAX`) once L2 measures
       the click step, since 100 clicks is the practical ceiling.
     - Until then it stays 25.
   - **Orders.**
     - At most 1 order (`max_items = 1`) until L2 measures `order_row_pitch`; then 2, which is mcp.rs's limit.
     - The crisis order takes the first slot.
   - **Why.**
     - E5: the loss was idle trade and energy, and the AI already covers anything under 6 months, in bulk
       at about 2× base.
     - The rules spend trade that would otherwise be discarded and never duplicate the AI's own buys. The
       reserve and caps are set at the AI's own thresholds.
   - **Cost if wrong.**
     - Trade spent on a resource that turns IDLE later. The IDLE and naval-room skips bound that.
     - Buying into a rising price. The price guard bounds that.
     - At Theia's scale the idle-trade fill uses a small share of discarded trade. That is safe but only a
       modest recovery until `amount_max` and the second slot are measured.

10. **Read-back through the next autosave.**
    - **Decision.**
      - At each sync the governor stores the synced orders.
      - The next save judges stick from `market_orders` (ruling 2), and the realised amount and trade cost
        from `trades_net`, the budget line of last month's monthly trades.
      - A buy that took but shows no trade spent in `trades_net` for 2 saves is recorded
        `took (not executing)`, and the frame shows it.
      - One sync per autosave, as today.
    - **Why.** `net` excludes market trades (stellaris.rs 1770-1781). Without `trades_net` a buy that sits in
      the order list without executing is invisible.
    - **Cost if wrong.** None beyond one parse. A missing `trades_net` degrades to today's stick-only
      check.

11. **No one-time buy-out flow in this version.**
    - **Decision.** No `stellaris_market_buy` screen flow. Monthly trades carry every rule above.
    - **Why.**
      - Buildings and ships cannot be bought in Stellaris, so the Civ VI "buy rather than queue" idea has
        nothing to act on.
      - For resources, the AI already makes one-time bulk buys under 6 months of cover (E5, crisis vote 2).
        A governor flow would duplicate them at a similar price, need a new calibrated screen flow, and could
        misclick.
    - **Cost if wrong.** A war crisis cannot get a burst of alloys in one month. Monthly buys at the crisis
      cap deliver over 3-6 months instead.

### C. War crisis response

12. **Entry condition: losses, never ratios.**
    - **Decision.** A pure `war_crisis(rows, now, prev)` in a new `src/pilot/stellaris_crisis.py`. It fires
      on the transition when we are in at least one war and any of these holds:
      - **C1** an owned colony is occupied (`planets[].occupied`);
      - **C2** systems ≤ (max over the last 12 months) − 2;
      - **C3** military ≤ 0.5 × (max over the last 12 months), which includes 0;
      - **C4** a colony was lost (the existing trigger, at war);
      - **C5** a ground battle at one of our colonies in the last save (an invasion);
      - **C6** a colony below stability 25 on 2 saves in a row (ruling 22).

      Never entry on its own:
      - military ratios (E6);
      - battle counts (they include allies, E7);
      - war exhaustion (in Theia's worst war ours was 60% against theirs 70%).

      It is wired into `urgent_changes` as `"war going badly: <conditions>"`. The reason goes into a new
      **Stellaris-only** trigger tuple assigned to `Governor.event_triggers` (412-413), so a strategy review
      runs under the existing 12-month cap. `EVENT_TRIGGERS` stays unchanged: matching is by substring (880),
      and Civ VI spreads it.
    - **Why.**
      - E8: C2-C4 alone flagged both Theian collapses and UNE2's loss, the first Theian collapse 7 months
        before the capital fell.
      - Theia was flagged 11% of months and UNE2 3%, so it is an overlay, not a mode.
      - E6: a ratio would hold 90-97% of the time, the same trap as the Civ VI design's E6.
    - **Cost if wrong.** A two-system loss in a war we are winning elsewhere enters a crisis. The exit rule
      and the 6-month minimum bound it. The worst case is a forced `defend` for 6 months.

13. **The response ladder: an overlay on `defend`, deterministic, one step each.** While in crisis, in this
    order:
    1. **Review.** The urgent reason starts a strategy review (ruling 12).
    2. **Need boost.** The pillar whose directive is `defend` gets need = `missed` (2.0), and its stall
       factor is 1.0 while the crisis lasts.
       - This is weighted-pillars ruling 12's "event boost to need", until now out of scope.
       - It goes in a hook `_need_boost()` called from `_pressures` (1332-1346), which returns `{}` by default
         so Civ6Governor is unchanged.
       - It is published in `log.state.info["crisis"]` so the dashboard's `api_strategy` can show it.
    3. **Force `defend`** if it is not current. It is applied as at 1169-1177 and recorded as
       `crisis defend`; the model's other choices in that decision stand.
    4. **Posture `war_crisis` on** (ruling 18), but only when `bridge-check` reports the v2 mod and the
       posture is enabled in the registry. Otherwise the step logs "skipped: not verified".
    5. **Market slot → buy alloys.** It needs all of these:
       - a shipyard in a system we control (ruling 1);
       - naval use known below 95% (ruling 19), or unknown with the alloy stock under 1,000;
       - alloys not IDLE;
       - ruling 9's reserve, price guard and crisis cap.

       The key is `crisis market buy alloys`.
    6. **Cadence.** Decisions every 3 months instead of 12, through a private `_set_pace(months, by="crisis")`.
       - It reuses `set_months`'s logic (684-690) without queueing a request, which would look like a human's.
       - The prior value is restored on exit unless the human changed it meanwhile.
       - **No speed change:** the briefing comes from monthly autosaves, so a slower game gives no more
         looks.
    7. **Status-quo question** (ruling 15).

    Each step emits `order_outcome` with key `crisis <step>`.
    - **Why.**
      - Steps 2-3 make the frame agree with the situation (E7: defend held 16 years with no exit test, yet
        was not suggested when losses began).
      - Steps 4-5 are the only levers that add fighting power without cheating: budgets and plans steer the
        AI's own income, and alloys are bought at market price.
      - Step 5's gates come from E7: in Theia's 2257-2265 collapse the only shipyard was occupied, so buying
        alloys would have piled them up. The rule correctly buys nothing there.
      - Step 6 gives 3 more looks per year when things change fastest.
    - **Cost if wrong.**
      - An economy directive is displaced for the crisis length. In the replay that was 3-11% of months plus
        the 6-month minimum.
      - Alloys bought and unused are bounded by the gates and the caps.

14. **Exit, limits and read-back.**
    - **Decision.**
      - **Exit:**
        - on "war ended" for every war, or
        - after 6 consecutive monthly saves with none of C1-C6 and no occupied colony,
        - with a minimum hold of 6 months.
      - **On exit:** posture off, cadence restored, and a review under the cap.
      - **Limits:**
        - at most one entry per war per 12 months;
        - never while `human_paused` or `control.paused`;
        - the posture toggles at most once per 6 months;
        - nothing in this ladder adds resources, armies, ships or modifiers.
      - **Read-back:**
        - the defend flag and the posture flag in the next save;
        - the market order through ruling 10;
        - the cadence through the settings echo in `log.state.info`.
      - A step that does not take is recorded. The ladder continues with the other steps, because each is
        independent.
      - **Setting:** `PILOT_WAR_CRISIS` defaults to 1. It turns the whole overlay off for a run.
    - **Why.** The Civ VI design's ruling 24 pattern: bounded, observable and reversible. The 6-month minimum
      stops flapping on noisy months (E8: several one-month flags in Theia).
    - **Cost if wrong.** A crisis that ends in the game but not in the rule holds `defend` for up to 6 extra
      months.

15. **Status quo is the human's call, asked, never blocking.**
    - **Decision.** A dashboard question, non-blocking like `NEEDS_HUMAN` (1160-1168), at most once per war
      per 12 months, when:
      - C1 or C2 holds, or
      - our war exhaustion is 0.6 or more and at least theirs, or
      - their side can force status quo (`force_peace`).

      The text names the systems lost, both exhaustions and any occupied colony. The harness itself never
      proposes peace.
    - **Why.**
      - The harness cannot sue for peace, and no War-screen flow is calibrated.
      - Whether the AI under `human_ai` accepts a status quo is **unverified**.
      - Peace acceptance is global (`PEACE_STATUS_QUO_FACTOR = -75`, `PEACE_HIGH_WE_STATUS_QUO_FACTOR = 100`),
        so no flag lever exists (crisis finding, not refuted).
    - **Cost if wrong.** An unanswered question. The ladder runs regardless.

16. **What the crisis never does.**
    - **Decision.** None of the following is used:
      - **Console `add_edict`:** it skips the unity cost, and the AI removed console edicts by the next
        monthly save, twice (spike journal :114-117).
      - **Edict `ai_weight` overrides** (ruling 17: refuted 2 of 2).
      - **A diplomatic stance change at war** (refuted 2 of 2): the group's `allow = { is_at_war = no }`
        means a player cannot do it.
      - **Militarized economy** (refuted 2 of 2): AI weight 0 unless authoritarian, reverted within a month
        with `cooldown = no` (E4), a 10-year lock with `cooldown = yes`, consumer goods −25%.
      - **`defense_in_depth_doctrine`:** +10% home fire rate at the cost of a 10-year doctrine lock (not
        refuted, but low value).
      - **Fleet or army micro:** it does not transfer (see the transfer table).
      - **`add_resource` or any cheat effect.**
    - **Why.** Fairness (strategy.md §9) and the votes. The Civ VI last stand needed a tactical API. Stellaris
      has none we can drive under `human_ai`, and the AI already fights to the death under 3 planets.
    - **Cost if wrong.** A lever left unused, recorded here to be reopened with new evidence.

### D. Mod levers (Governor Bridge v2)

17. **Go / no-go per lever.** "Refuted" counts the votes that refuted the lever itself. The majority is 2 of 3
    for the mod-lever finding and 2 of 2 for the other two.

    | Lever | Source | Votes against | Verdict | Why |
    |---|---|---|---|---|
    | Economic-plan subplan `naval_cap` + alloys focus | mod 1 | 0 of 3 | **Go, probe-gated** (ruling 21) | v1: no vanilla precedent for a non-scaling naval_cap; focus 2× is swamped by deficits (100×). v2: a nudge, measure it. v3: fair. |
    | Subplan `research_focus` | mod 1 | 0 of 3 | **Go, probe-gated** | The only lever aimed at tech_rush's measured failure. Building `ai_weight` is unused in 4.5, so the old minerals→planets entry could not choose labs. |
    | Budget alloys → `ship_upgrades` at war at ≥ 95% cap | mod 3 | 0 of 3 | **Go, probe-gated** | v2: funded is not proven to happen; vanilla's peace-only gate may mirror an engine rule. |
    | Crisis budgets: minerals → armies +0.2; alloys → starbases +0.4 at ≥ 95% cap | crisis 2 | 0 of 2 | **Go, probe-gated** | Vanilla armies are 0.1 with no war factor; defence platforms need ≥ 95% use (defines :2149). |
    | Read channel: monthly export of naval capacity to `country.variables` | code map; crisis status flags | not refuted | **Go, G0-gated** (ruling 19) | Closes the "no naval-cap maximum" gap behind false plans (E7). Syntax is in vanilla (`000_how_to_use_variables_in_script.txt`:26; `max_naval_capacity`, `used_naval_capacity_integer` triggers). |
    | Fairness fix: `can_set_policy` + `cooldown = yes` | mod 5; crisis votes | 0 against; supported by 4 votes | **Go** (ruling 20) | E4. |
    | **Watchdog heartbeat** (strip flags when the governor stops renewing) | mod 2 | **2 of 3** (v2, v3) | **Out** | The 94-month gap is closed by auto-recover (issues.md:16 [x]). It would strip `defend` mid-war, cannot undo policies, and needs a console trip at every decision. Its gate flags are set nowhere. |
    | **Edict `ai_weight` overrides** (desperate_measures, grand_fleet, fortify_the_border, fortress_proclamation) | crisis 2 | **2 of 2** | **Out** | Whole-object overrides, not additive, which breaks the mod's no-override rule and carries load-order risk. `NUM_TRADITIONS_FOR_EDICTS = 49` may keep the AI off edicts anyway. |
    | **Crisis stance policies** (belligerent, supremacist at war) | crisis 3 | **2 of 2** | **Out** | `allow = { is_at_war = no }`: not a player action. |
    | **Militarized economy in crisis** | crisis 3 | **2 of 2** | **Out** | Reverted by the AI, or locked for 10 years; consumer goods −25%. |
    | `on_policy_changed` log event | mod 2 | 1 of 3 (v2: "diagnostics at best"; unverified whether it fires for console set_policy) | **No-go on value** | The save's `active_policies` dates (ruling 1) give the same fact monthly with no mod. |
    | `ai_no_wars` flag | mod 4 | 1 of 3 (v3, fairness) | **Held out** | If the engine also blocks wars *against* the flagged country, it grants immunity, which is cheating. The semantics are unknown. Reopen only with evidence it blocks our declarations alone. |
    | Influence → claims (prepare_war) | mod 3 | 0 of 3; v2/v3: the draft drops vanilla's `is_pacifist` and crisis exclusions | **Deferred** | prepare_war was never held in 4 campaigns (tenure table), so there is no demand. |
    | Zone override (`zone_urban` weight by flag and deficit) | planet B1 | 1 of 2 (v2: does not reach amenities) | **No-go on value** | It adds housing. Housing deficits are 0-2.3% of observations; amenity zones need `resort_colony`. |
    | `fix_planets` posture (minerals → planets + automation exceptions) | code map | planet votes: minerals not the constraint | **No-go** | 17k minerals idle (Gaea 2289); the identical consolidate entry did not clear deficits (E10). |
    | Designation (`set_colony_type`) for amenities | planet B3 | both votes: no amenity designation exists | **No-go for planets** | No designation carries an amenity building set. |
    | Script-value override for science ships (surveying) | mod 8 | not voted | **Deferred** | A whole-file (LIOS) override that needs a CI diff against vanilla. E12 shows the need, but only early in a campaign. |
    | Fleet doctrine or weapon preference by policy; `WAS_HUMAN_MONTHS` define | mod 6, 9 | not voted | **Deferred** | Policy lock, unmeasured refit cost; a global define. |

    - **Why.** The rule the task set: a lever refuted by a majority is out, and it is named. Levers under a
      majority but with a fairness or value objection are held out and say why.
    - **Cost if wrong.** A useful lever waits for new evidence. Each "out" names what would reopen it.

18. **Postures: flags beside the directive, bound to it in version 1.**
    - **Decision.**
      - **Flags.** A posture is a country flag `governor_posture_<name>`. The directive removal loop never
        touches it, because that loop lists directive names only.
      - **Registry.** `[posture.<name>]` tables in `corpora/stellaris/directives.toml`, each with
        `description`, `mod_version = 2` and `enabled = false`. The Rust `Directives` struct gains
        `posture: BTreeMap<String, PostureDef>`.
      - **Binding.** Each directive gains `postures = [...]`:
        - `defend` and `prepare_war`: `naval_cap`, `ship_upgrades`;
        - `tech_rush`: `research_focus`;
        - the others: none.

        The crisis sets `war_crisis`.
      - **Enabling.** Only enabled postures are set. Enabling one is a data commit after its probe gate
        (ruling 21) passes.
      - **Apply.** `console_lines` sets the directive's enabled postures and removes the others in the same
        console trip. A new `apply_posture(name, on)` (with an MCP tool `stellaris_posture` and CLI
        `stellaris posture`) serves the crisis.
      - **Read-back.** Flags in the next save, recorded as `posture <name>` (ruling 2).
      - **Efficacy.** An advisory `flag_record(rows, flag, metric)` next to `directive_record`, with no
        pressure factor.
      - **No Strategist action kind** in version 1. `ACTION_KINDS`, `Pillar` and `_action_ids` stay unchanged.
    - **Why.**
      - Separate flags allow the A/B probe (directive with and without the posture) and a per-lever record.
        A lever can then be switched off without a mod change.
      - Binding postures to directives keeps the shared `pillars.py` and `strategy.py` kind tables untouched
        while the Civ VI branch changes them, and it avoids adding `"postures": []` to stored Civ VI
        strategies.
      - The orthogonal-need argument (Arnvoss under `defend`) needed `fix_planets`, which is no-go (ruling 17).
    - **Cost if wrong.** A posture cannot be combined with another directive (e.g. research focus under
      defend). A Strategist-set posture kind can follow once the record shows posture effects over 2+ years.

19. **The read channel: naval capacity in the save.**
    - **Decision.**
      - `common/on_actions/zz_governor_bridge_on_actions.txt` adds `on_monthly_pulse_country = { events = { governor_bridge.1 } }`.
      - `events/governor_bridge_events.txt` defines hidden, triggered-only `governor_bridge.1`:
        - it is limited to `has_country_flag = governor_bridge_player`, which `take_control` sets;
        - it runs `export_trigger_value_to_variable` for `max_naval_capacity` → `governor_naval_cap` and
          `used_naval_capacity_integer` → `governor_naval_used`.
      - stellaris.rs reads `country.variables.governor_*` into `governor_vars`.
      - The briefing prints "naval capacity 131/147 (from the mod)" and replaces the text "the maximum is not
        in the save" (1970).
      - `trends()` may then name the cap as a cause when the data shows it.
      - **Fallback without the mod:** the same effect sent through the console once per decision. It costs
        one console trip and stays off unless G0 fails.
    - **Why.** E7: a naval-cap premise nobody could check steered years of plans. Ruling 9's alloy rules also
      need it.
    - **Cost if wrong.** on_actions may not merge as expected. The evidence is the economic-plans README
      ("a bit like on_actions") and the wiki's "NO/MERGE: new entries merged", which is **unverified live**.
      G0 detects it (no variable in the next save), and the console fallback covers it.

20. **The fairness fix: directives obey the player's policy rules.**
    - **Decision.**
      - Each `set_policy` in `console_lines` sits inside `if = { limit = { can_set_policy = { policy = <p> option = <o> } <existing valid> } … }`
        with `cooldown = yes`. This is vanilla's own guard (`events/on_action_events_2.txt`:3088-3113).
      - The directive's notes in `directives.toml` change: policies are a slow lever, held 10 years once set,
        and flags and postures are the fast lever.
      - A policy that cannot be set is reported as `locked` (ruling 3).
    - **Why.**
      - E4: `cooldown = no` goes beyond what a player can do.
      - `valid` alone missed `allow = { is_at_war = no }` (defend mid-war) and the policy's `potential`
        (economic_policy is not for gestalts; mod vote 3).
      - With no lock, the AI reverted civilian within a month (2272).
    - **Cost if wrong.**
      - Directive switches (every 3.4-7.6 years) will mostly find their policy locked, so a directive becomes
        its flag and postures. E1 says the policies moved little anyway.
      - Whether the lock also stops the AI's reverts is **unverified** (L3). If it does not, the stick is
        unchanged and only the fairness gain remains.

21. **Probe protocol: every mod lever is gated live before it is enabled.**
    - **Decision.** Run on a throwaway, non-Ironman game in a live window (Testing, L4-L5), never on
      "Commonwealth of Man 3". Pause the governor from the dashboard and do not stop the service. Gates:
      - **G0, load.**
        - `stellaris take-control` (human_ai is not saved) and `bridge-check`, which gains a
          `governor_bridge_version_2` trigger check;
        - error.log has no lines naming `zz_governor_bridge_*`, `economic_plans` or `governor_bridge.`;
        - the next autosave carries `governor_naval_cap`.
      - **G1, flags.** Posture flags appear and clear with the directive (next save).
      - **G2/G3, effect, fork-and-reload A/B.** From autosave S0, run A (directive, postures off) and run B
        (postures on), each 24 in-game months at fastest.
        - Pass for `naval_cap`: B's `governor_naval_cap` rises ≥ 10% more than A's, or B builds naval-cap
          buildings or anchorages that A does not.
        - Pass for `research_focus`: B's research income grows faster than A's.
        - Pass for `ship_upgrades`: B shows upgraded ships at war and A does not.
        - Pass for `war_crisis`: B's defence armies or platforms rise and A's do not.
      - **G4, isolation.** No other country carries `governor_*` flags.

      A lever that fails its gate stays `enabled = false`, and no mod change is needed.
    - **Why.** E9: no flag-gated entry has been seen changing our empire. The runtime premise rests on file
      evidence. The Civ VI design's ruling 28 set the fork pattern.
    - **Cost if wrong.** One window (about 1 hour wall-clock, an **estimate**: restart, two 24-month runs,
      reloads). An A/B with n = 1 per arm is a probe. The record (ruling 2) and ruling 13's efficacy give the
      long-run verdict.

### E. The planet check

22. **Stage A, read-only: flag, explain, correct the rules. No lever in this version.**
    - **Decision.**
      - A pure `planet_issues(b, prev, rows)` in `src/pilot/stellaris_planets.py`. A planet is flagged when an
        issue persists across 2 saves at least 2 months apart:
        - stability below 50;
        - amenities below −100 on 300+ pops;
        - housing below 0 on 1,000+ pops;
        - unemployed 5% or more of employable pops (colonies other than the capital);
        - pops down 20% or more in 12 months;
        - occupied.
      - **Briefing and frame:** one "Planet check" line naming flagged planets only, with a cause hint from
        ruling 1's fields: "nothing queued here", "occupied", "minerals net < 0". Example:
        "Arnvoss stability 18 (3 saves), amenities −253, housing −283; nothing queued".
      - **Urgent** (Stellaris-only trigger tuple):
        - `"planet crisis: <name> stability <n>"` on the transition below 25 on 2 saves in a row;
        - `"planet losing pops: <name> −<p>% in 12 months"` for a planet of 1,000+ pops.

        At war the first also enters the crisis (C6).
      - **Planet record:** per directive, the amenity change per planet-year on flagged planets, with the
        number of distinct planets. It is given to the Strategist as advisory, like weighted-pillars ruling 13.
      - **Rule corrections:**
        - fix `corpora/stellaris/learned/strategy.md`:29 (built on LasVeredas, a wartime deficit that
          rebounded after peace);
        - fix `:191` (new colonies clear under any directive);
        - state that consolidate_economy does not repair grown-colony deficits (+5 to +14 a year; 2 of
          63-70 year-intervals, dominated by 3 planets).
      - **Go criterion for a planet lever** (a later design). Both must hold:
        - a lever that reaches amenities exists (none found; ruling 17);
        - peacetime job output lost to planet stability averages 2% or more over 10 years. This is an
          **estimate**: Σ pops × max(0, 75 − stability) × 0.6% / total pops, a pre-4.0 coefficient.

        The rival development ratio is **not** a criterion (E10, the captain-difficulty confound).
    - **Why.**
      - E10: amenity deficits are common and cheap, and every collapse happened in war, where the crisis
        ladder acts.
      - The model deferred Arnvoss for 7.5 years. An urgent line and the planet record stop "wait for peace"
        and the false consolidate rule from recurring.
    - **Cost if wrong.** Briefing bytes (flagged planets only) and one more urgent reason. If thresholds are
      noisy, the 2-save persistence bounds churn.

### F. Popups and stalls

23. **A date-stall watchdog in the Stellaris poll loop.**
    - **Decision.** In `_run_until_next_decision` (1022-1064), which Civ6Governor overrides, so this is
      Stellaris-only:
      - Track the wall-clock time of the last date change.
      - If the date has not changed for `stall_s` while the governor wants the game running
        (`control.paused` and `human_paused` both false; the loop already returns early on
        `control.paused`):
        1. take a screenshot and log `stall` with its path;
        2. call `self.game.set_paused(False)` **once**. The existing `stellaris resume` reads the pause
           state from the screen and closes the game menu first (`[screens.game_menu]`).
        3. log `self_paused` if the game had been paused.
      - If the date is still unchanged after another `stall_s`, call `_needs_attention("the game date has not
        advanced for N s: …")` with the screenshot path.
      - `stall_s = max(300, 10 × median seconds per in-game month over this run's last 24 months)`.
      - A clock is injected (`self._clock = time.monotonic`) so tests can drive it.
    - **Why.**
      - E11: no popup has stalled Stellaris yet, but event windows autopause by default, and a crash or a
        launcher window leaves the last autosave in place forever.
      - Civ VI stalled at T134 on a movie.
      - 300 s is above every observed month (max 247 s, including decision time) and about 30-140× the
        medians.
    - **Cost if wrong.**
      - A false stall at a very slow speed costs one extra resume (harmless) and one `needs_attention`, which
        the 10 × median term makes unlikely.
      - A resume while the human paused in-game is prevented only by `human_paused`. A pause made in the
        game UI, not the dashboard, is indistinguishable (**known limit**; the journal notes it).
    - **Amended after the branch review (2026-09-27): no resume.** Steps 2-3 are dropped.
      - A campaign the human loads writes no autosave at first, so the governed save still looks newest
        and the save-folder guard cannot fire: a resume would unpause the human's own game or close
        their menu.
      - After a crash, `McpGame.ensure_foreground` asks the agent to focus a window whose title contains
        "Stellaris" (a browser tab, an Explorer window), and the Paradox Launcher is titled exactly
        "Stellaris".
      - Nothing read-only proves the governed game is in front. `continue_game.json` or a game.log line
        written on each load might, once L6 shows when they are written.
      - So at the first `stall_s` the watchdog takes the screenshot, logs `stall` and calls
        `_needs_attention`, sending no input and focusing no window. A resume can return only behind
        such positive evidence.

24. **Dismiss the declaration-of-war popup before any screen flow.**
    - **Decision.** A `[screens.war_declaration]` template (captured live, L6), dismissed:
      - before the market and tech screen flows;
      - ~~by the watchdog's resume step~~ (the resume was dropped, ruling 23's amendment).

      It closes issues.md:35.
    - **Why.** The popup stays open under `human_ai` and covers the map, where the market and tech flows
      click.
    - **Cost if wrong.** A template that also matches another dialog. `capture-template.py --against` checks
      other frames (≥ 0.10).

---

## Shared seams with the Civ VI branch

The branch (`feat/civ6-levers` at 5a54fff) changes `governor.py` in two hunks only (1367 `_records_section`,
1431 the review prompt). It also changes `pillars.py` (purchase keys, `OrdersSpec`, `milestone_exclude`),
`strategy.py` (8 lines: milestone_exclude checks and instructions), `config.py` (last_stand settings),
`telemetry.py` (`campaign_events`) and `main.rs` (+99 lines, civ6 subcommands).

| Seam | This design touches it in | Rule |
|---|---|---|
| `_review_strategy` prompt (1431-1440) | ruling 6 | Add one element before `_records_section()`, only when non-empty. Never between it and "Latest briefing". |
| `EVENT_TRIGGERS` (61-62) | rulings 12, 22 | Not edited. A Stellaris-only tuple goes to `Governor.event_triggers`. |
| `_pressures` (1332-1346) | ruling 13 | A hook `_need_boost()` returning `{}` by default. |
| `frame_text` (282-320) | rulings 13, 22 | No signature change: the boost travels in `press` (status "war crisis"); planet and record lines go in `_decide`'s prompt. |
| `pillars.py` kind tables, `ActionLimits`, `OrdersSpec` | rulings 5, 9 | Only after the merge. Reuse `OrdersSpec`, and add market keys beside the branch's purchase keys. |
| `strategy.py` `market_briefing_errors` (151-168), `directive_record` (535-556), instructions (510-517) | rulings 7, 9 | After the merge. New keyword-only parameters with defaults. |
| `telemetry.campaign_events` | ruling 4 | Reuse, no second reader. |
| `order_outcome` rows, `log.state.info["order_record"]` | rulings 2, 4, 6 | Same shape. |
| Branch `civ6.py` record helpers (875-1123) | rulings 5-6 | After the merge, a pure move to `src/pilot/record.py` (civ6.py re-exports), then use it from both games. |
| `main.rs` CLI | ruling 18 | `stellaris posture` sits in the stellaris block, far from the civ6 hunks. |

GalCiv IV is untouched: it runs `controller.Pilot` and never imports the governor, strategy or pillars. mcp.rs
registers Stellaris tools only for the Stellaris corpus (mcp.rs:374).

---

## Rollout

Every commit goes through `scripts/ci-commit.sh` and is testable on its own. Each also updates `plan.md`,
`issues.md` and README, ARCHITECTURE and docs/ where behaviour changes.

**Phase 0: can land now.** It touches no file region the Civ VI branch changes.
1. `fix(stellaris): per-resource start amount for new monthly trades` (ruling 8).
   - Manifest table, `amount_clicks`, alloys and sr_* refused until measured.
   - Tests: Rust `amount_clicks` per resource; the run 20260926-152042 case (15 from a start of 1 → 14
     plus-clicks).
   - issues.md gains `[ ]` "6 of 16 market adds failed on the start amount".
2. `feat(stellaris): briefing fields for the levers` (ruling 1), with the own-battles fix.
   - Rust tests on the 2200/2212 fixtures, plus synthetic gamestates for occupation, force peace, own vs
     allied battles, the market block and `variables`; the compactness test stays < 4000.
3. `feat(stellaris): directives report their policies and obey can_set_policy and the policy lock`
   (rulings 3, 20).
   - Rust `console_lines` tests: a nonce marker in each branch; `can_set_policy`; `cooldown = yes`.
   - Live behaviour changes at the next directive switch, so issues.md:27 gets a note.
4. `feat(stellaris-mod): Governor Bridge v2, postures and the naval-capacity read channel` (rulings 18-19).
   - The files are copied from the research draft of the mod (working copy, not in the repo) and trimmed to the go levers (no watchdog, no
     policy log, no claims).
   - Registry with every posture `enabled = false`, `apply_posture`, MCP and CLI, and the v2 trigger in
     `bridge_loaded`.
   - `mod_files_are_well_formed` accepts registry postures and adds the new vanilla pairs
     (`alloys/ship_upgrades`, `minerals/armies`).
   - The mod is inert until installed and enabled.
5. `feat(pilot): Stellaris date-stall watchdog` (ruling 23).
   - Governor.py `_run_until_next_decision` only; FakeStellaris `self_pause_after` and clock tests.

**Phase 1: after `feat/civ6-levers` merges.**

6. `refactor(pilot): order-record helpers shared by both games`. A pure move; civ6 tests unchanged.
7. `feat(pilot): Stellaris action record` (rulings 2, 4-6). Adds `[orders]` to the Stellaris pillars file.
8. `feat(pilot): directive efficacy relative to the peer median; blocked hint for expand` (ruling 7).
9. `feat(pilot): market buy rules and idle-trade fill` (rulings 9-10). `amount_max` stays 25 until L2.
10. `feat(pilot): planet check stage A and the learned-rule corrections` (ruling 22).
11. `feat(pilot): war crisis overlay` (rulings 12-16).
    - `PILOT_WAR_CRISIS=1`.
    - The posture step and the alloys buy stay skipped until their gates pass.

**Phase 2: a live window when Stellaris is the running game** (L1-L8 below).

12. `chore(stellaris): enable measured levers`. Data only: `enabled = true` for postures that passed G2/G3;
    `amount_max = 100`, the fractional start amounts and `order_row_pitch` from L2; `max_items = 2`.
13. Journal, plan.md `[x]` for each deployed lever, issues.md closures (26, 27, 30, 35, 39 as they verify).

---

## Testing

**Unit tests** (pytest with `FakeStellaris`; `scripts/ci.sh` must stay green). FakeStellaris
(game.py 284-349) changes, all backward compatible; its 149 uses in test_governor and 2 in test_game_pillars
keep today's defaults:
- `directive()` keeps non-directive flags (today it replaces `self.flags`). It sets `b["policies"]` and
  `policy_dates` from directives.toml, and a `reverts={policy: option}` knob changes one on a later briefing.
- `posture(name, on)`.
- `market_sync()` makes the next briefing's `market_orders` equal the synced orders. A `sticky=False` knob
  covers did_not_take, and a `trades` knob fills `market.trades_net`.
- `research` progression scripted per briefing; a `pick_reply` knob ("clicked <id> in <field> …").
- `self_pause_after=n`: after n reads the game pauses itself, so the date holds. `set_paused(False)` clears
  it.
- Briefings carry `market`, `planets[].occupied`, war extras and `governor_vars` straight through.

Tests:
- **Record (2-7).**
  - Pure outcomes:
    - a directive whose policy reverts after our apply → `overridden` with the option and date;
    - no marker → `locked`;
    - no flag → `failed`;
    - superseded;
    - tech researched vs did_not_stick vs no-op;
    - market took vs did_not_take vs removed;
    - posture took.
  - Governor:
    - (a) a revert shows "overridden" in the next decision prompt, and `events.jsonl` has an `order_outcome`;
    - (b) a tech reset at review keeps its rows;
    - (c) a new Governor on the same campaign reloads the record from Telemetry (the test_governor.py:213
      pattern);
    - (d) the Stellaris review prompt carries "Action record" **and** the branch's exact heading test still
      passes;
    - (e) a Civ6Governor review prompt has no Stellaris section;
    - (f) two did_not_take for `buy consumer_goods` suspend it, and a changed `[ui.market]` hash lifts the
      suspension.
  - `directive_record` relative mode reproduces E2's four verdicts on synthetic rows, and stays absolute
    without a median.
  - test_pillars: `spec.orders` for Stellaris.
- **Market (8-10).**
  - Pure rules:
    - the reserve at 2,500, e.g. trade 3,000 with a cost 60 over net → refused;
    - the spend cap with and without crisis;
    - the price guard at +50% and +100%;
    - the volume cap internal vs galactic;
    - the skips: under 6 months of cover, `bought` rose, IDLE, alloys at ≥ 95% with no crisis;
    - the idle-trade fill picks deficit cover, and otherwise nothing with the reason;
    - alloys and sr_* refused until measured.
  - Governor: the crisis replaces the slot; read-back `took (not executing)` after 2 saves with no trade.
  - `test_the_stellaris_pillars_file_limits_equal_the_controllers` stays green, because amounts change only
    in commit 12.
- **Crisis (12-16).**
  - Pure `war_crisis`:
    - each of C1-C6;
    - no entry on ratio, battles or exhaustion alone;
    - transition only;
    - E8 replayed from a fixture of Theia's 2255-2263 metric rows enters at 2256.08.
  - Governor with FakeStellaris (a colony becomes occupied):
    - the ladder order: review, then `directive defend`, then the posture (skipped: not verified), then
      `market_sync buy alloys` only with a shipyard, then cadence 3;
    - one entry per war per 12 months;
    - exit after 6 quiet saves restores the cadence;
    - the human's cadence change during a crisis is kept;
    - `human_paused` blocks every step;
    - `Civ6Governor.event_triggers` lacks the Stellaris tuple;
    - `_pressures` is unchanged for Civ VI.
- **Mod and postures (17-21).**
  - Rust:
    - posture lines never remove directive flags, and directive lines never remove postures;
    - disabled postures are never set;
    - the new mod files parse, and every flag they read is in the registry;
    - subplans appear in all six plan keys with only `focus`, `naval_cap`, `optional`, `set_name` and
      `potential`;
    - `governor_vars` is read from a synthetic `variables` block.
- **Planet check (22).**
  - Pure: thresholds, 2-save persistence, the capital exclusion for unemployment, pops −20%.
  - Local saves as data fixtures, per the planet finding's expected values:
    - Arnvoss in a2272 carries the fields the planet finding lists (col_mining, 272 pops, city 1 + mining 1, 0 unemployed, 248 free jobs, automation off);
    - Nueva Sonora 2256 is flagged for amenities −270.9;
    - Wintered Stane 2393 is flagged −326;
    - the a2272 controller ≠ owner planet is not ours.
  - Governor: the urgent reason fires once at the transition.
- **Watchdog (23).** With an injected clock:
  - a held date while running → `needs_attention` at `stall_s`, with no input (ruling 23's amendment): also
    when another campaign was loaded mid-wait, and no focus after a crash;
  - a held date while `human_paused` → nothing;
  - a date that moves resets the timer.

**Live checks.** Run them only when Stellaris is next the running game. There is one Steam account, so Civ VI
must be stopped first: pause the Civ VI governor from the dashboard, quit Civ VI, and start Stellaris
through Steam. Watch for the launcher, whose window is also titled "Stellaris" (issues.md:38). All checks run
on a throwaway non-Ironman game, never "Commonwealth of Man 3". The Stellaris governor stays paused from the
dashboard during state-changing checks.
- **L1, briefing fields.**
  - One autosave: occupied, `policy_dates`, shipyards, own battles, the market block.
  - The fluctuation matches the Market screen's price.
  - Whether we are on the internal or the galactic market.
- **L2, market calibration.**
  - Monthly buys of 5 for consumer goods, alloys, rare crystals and sr_zro, one at a time, read back from
    the save. This settles every start amount and how a fractional start displays and steps.
  - Try shift- or ctrl-click for a ×10 step.
  - Measure `order_row_pitch` with 2 orders.
  - Confirm the AI keeps an order for 3 months.
- **L3, policies.**
  - Apply tech_rush with `can_set_policy` and `cooldown = yes`; the marker appears; `active_policies` shows
    civilian with the apply date.
  - Watch 3 saves for an AI revert.
  - Apply defend while at war: the stance is reported locked.
- **L4, mod v2 load (G0-G1).**
  - `install-mod`, restart through the launcher with the "Governor Bridge" playset, load the save,
    `take-control`, `bridge-check` v2.
  - error.log is clean.
  - `governor_naval_cap` is in the next autosave and matches the fleet manager's naval capacity.
  - `governor_naval_used` equals that autosave's own `used_naval_capacity`, i.e. the export runs before
    the save is written. The briefing treats the export as current only within max(2, 2%) of the save's
    use (variables outlive the mod); if the export lags a month, a changing fleet reads stale and the
    event needs a month stamp.
- **L5, posture probes (G2-G4).** The fork-and-reload A/B for `naval_cap`, `research_focus`, `ship_upgrades`
  and `war_crisis`, 24 months per arm, then the isolation check.
- **L6, stall and popups.**
  - Fire a player-scoped event from the console under `human_ai`: does the game autopause, and does the AI
    answer?
  - Let the watchdog flag the stall at `stall_s` = 60 s for this check.
  - Whether `continue_game.json` or a game.log line records each load: the evidence a watchdog resume
    would need (ruling 23's amendment).
  - Capture the declaration-of-war popup for ruling 24's template.
- **L7, crisis ladder.**
  - On the throwaway, provoke a war with the console (a war command on an AI empire).
  - Occupation or a lost system enters the crisis; check the order of steps and their read-back in the next
    saves.
  - Peace, or 6 quiet saves, exits and restores the cadence.
- **L8, after deployment on a real campaign** (the user's approval as for any deploy).
  - The record is rebuilt from events at start.
  - The first idle-trade fill reads back with `trades_net`.
  - The first planet check line lists flagged planets only.
  - 10 in-game years of wars compared against the 2289-2294 `defend` baseline: systems lost, the exhaustion
    gap, military ÷ median.

---

## Out of scope

- **A Strategist-set posture action kind** (a new `ACTION_KINDS` entry). Version 1 binds postures to
  directives (ruling 18).
- **One-time market buys, War-screen status quo proposals, and fleet or army micro** (rulings 11, 15, 16).
- **Edicts in any form, stance changes at war, and militarized economy in a crisis** (ruling 17).
- **Planet levers:**
  - zones, buildings' triggered `ai_resource_production` overrides, designations;
  - planet automation toggled through the UI. It is a later probe: the AI never uses it (0 of 480), and
    whether it runs under `human_ai` is **unverified**.

  All wait for ruling 22's go criterion.
- **Surveying capacity** (the `desired_science_ships` script-value override). E12 shows the need; it is a
  whole-file override with vanilla drift.
- **Trade-policy conversion.**
  - The AI would take `trade_policy_consumer_goods` itself (ai_weight 1 against 0 for default) once it has
    `tr_mercantile_adaptive_economic_policies`.
  - Theia never did: the 2393 save shows `trade_policy_default` and no Mercantile tradition (checked here).
  - Steering traditions is not additively moddable.
- **`ai_no_wars`** until its semantics are shown to affect only our own declarations (ruling 17).
- **Influence to claims, the fleet doctrine policy, and `WAS_HUMAN_MONTHS`** (ruling 17, deferred).
- **The launcher-title foreground issue** (issues.md:38). The watchdog and every screen action inherit it.

---

## Unverified, in one place

- **Market:**
  - the start amounts for consumer goods (5), alloys (2.5) and sr_* (0.5), and how fractional starts display
    (E3, ruling 8);
  - linear price decay, and the volume caps derived from it (ruling 9);
  - the market index → resource mapping (ruling 1);
  - internal vs galactic membership (L1).
- **Policies:**
  - whether `cooldown = yes` stops the AI's own reverts;
  - whether console `set_policy` honours `allow` (ruling 20).
- **Mod:**
  - that flag-gated plans and budgets change our empire's behaviour under `human_ai` at all;
  - non-scaling `naval_cap` subplans;
  - wartime ship upgrades happening once funded;
  - on_actions merging;
  - a changed mod joining an existing save (issues.md:39) (rulings 17-21).
- **Crisis:**
  - whether the AI under `human_ai` accepts a status quo (ruling 15);
  - occupation parsing in special situations such as crisis-owned planets; entry is judged only against
    countries we are at war with.
- **Planets:**
  - the 0.6% per stability point coefficient (pre-4.0 prose);
  - the revolt rule below 25 in 4.5 (ruling 22).
- **Popups:** that event autopause cannot be disabled (inferred from `can_disable = no`), and whether it
  fires before the AI answers under `human_ai` (ruling 23).
- **Wall-clock:** the probe window length (about 1 hour, an estimate).

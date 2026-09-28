# Post-mortem fixes: buy-outs, briefing, triggers, milestones and the end of a campaign

Date: 2026-09-27. Status: rulings made in a hands-off run. This design turns sections 5 and 6 of the
post-mortem `games/civ6-kublai/postmortem.md` ("the post-mortem") into changes. It amends
`2026-09-27-civ6-levers-design.md` ("levers ruling N"), `2026-09-27-stellaris-levers-design.md` ("Stellaris
levers ruling N") and `2026-09-26-weighted-pillars-design.md` ("weighted-pillars ruling N"). Its own rulings
are numbered from 1.

Base: `main` at 8d3f10f (all code line numbers). Branch `feat/dashboard-v2` is in flight and owns
`dashboard.py`, `dashboard.html`, auth, and small info fields in `governor.py` and `civ6_governor.py` (see
"Shared seams").

How references read:
- **L1-L20** and **T1-T10** are the post-mortem's lessons (sections 5 and 6).
- **H1-H14** and **S1-S8** are its harness and strategy failures (section 4).
- **war-3**, **treasury-11** and the like are claim IDs from its appendix. The label says how the verifiers
  judged each claim:
  - **[both]**: both verifiers upheld it;
  - **[one]**: the evidence verifier upheld the facts and the causality verifier rejected or downgraded the
    causal weight.
- **E1-E10** below are checks made for this design.

Sources:
- the post-mortem and the evidence it cites;
- `runs/telemetry.sqlite`, read-only: 349 metrics rows of campaign `civ6/kublai_khan_china_702403662`
  (T41-T763), the decisions table, and the metrics rows of three Stellaris campaigns;
- `runs/20260927-135856/events.jsonl`;
- the code at 8d3f10f;
- the live `corpora/civ6/learned/strategy.md` in the main checkout, read only.

Writing this design sent nothing to either game, made no tuner query and read no file through the agent.

A caution carried over from the post-mortem: every city that got a bought Modern AT still fell (RC1, war-3
[both]). These changes use the levers the governor had. They would not have won this war.
treasury-11 [both] estimates their pre-war effect at +400 to +800 military, against a gap of 751 at T538.

---

## Evidence added here

**E1. The weakness test held in every pre-war row from T380.** This is ruling 1's test, replayed on the
metrics rows. Mali is counted as an ally from T511.

| Turns | Rows | At war | Military last | Under 0.6 × median | A major at 2× ours | Any clause |
|---|---|---|---|---|---|---|
| T41-T199 | 134 | 73 | 36 | 14 | 10 | 88 |
| T200-T299 | 41 | 0 | 0 | 0 | 0 | 0 |
| T300-T379 | 37 | 4 | 13 | 23 | 24 | 26 |
| T380-T459 | 42 | 9 | 0 | 13 | 42 | 42 |
| T460-T540 | 31 | 0 | 25 | 31 | 31 | 31 |
| T541-T583 | 40 | 39 | 40 | 40 | 40 | 40 |

- "At war" counts every war in the rows, city-states included, because the rows do not record whether an
  enemy is a major.
- A test that switches on only in a crisis would have stayed off through T462-T540, the window RC2 is
  about. This one is on for the whole late game. That is intended, and it is also why rulings 2-3 carry
  their own limits.

**E2. Yields paid for defenders before the war.**
- T470-T540: gold +146 to +305 a turn, faith +174 to +246 a turn.
- A Modern AT costs 8 gold a turn in upkeep (corpus `maintenance`).
- So faith income alone buys one Modern AT (1,160 faith) about every 5-7 turns, and upkeep is not the
  limit.
- At T460 techs were 57 against a median of 69, and at T541 68 against 77.

**E3. The neighbour-buildup trigger, replayed.** The rule: a met major (not an ally) with at least 2× our
military that grew 50% or more over the window, at most once per neighbour per window.
- **Civ VI, 20-turn window:** 18 fires in T344-T561, 13 of them before the war. That is about one per
  15 turns.
  - Australia fires first at **T478**: 345 → 598, against our 295.
  - It does not fire at T512, the post-mortem's test turn. Australia went 718 → 955 over T496-T512
    (+33%). Maya fired at T510.
- **Stellaris, 24-month window, alliance and federation partners skipped:**
  - UNE2: 3 fires in 63 years;
  - Theia: 25 in 260 years;
  - Gaea: 4 in 85 years.

**E4. The falling-behind threshold must differ by measure in Civ VI.** Transitions into "behind"
(ours < factor × median of met majors) over T41-T583, 325 rows:

| Measure | 0.5 (Stellaris rule) | 0.6 | 0.8 | 0.85 |
|---|---|---|---|---|
| military | 8 | **10** (the last at T457) | 7 | 7 |
| techs | 0 | 0 | 0 | **9** (T150-T240, then T444 and T457) |
| civics | 0 | 0 | 0 | **0** |
| score | 1 | 1 | **2** | 1 |
| cities | 1 | 1 | **2** | 1 |

- Stellaris's 0.5 rule never fires for techs, although the tech gap (57 against 69) is the one RC1 names.

**E5. Gold per turn turned negative 5 times in the campaign:** T77, T84, T123, T291 and T583.

**E6. The learned rules to correct live in the main checkout's working tree, not in git.**
- `corpora/civ6/learned/strategy.md` has 414 lines there, 219 of them uncommitted. The committed file has
  195.
- The rules the post-mortem cites (S6, L1, L7, L12) sit at :362, :374, :377 and :386 of the live file.
- The peacetime rules (T263, T302) and the T121 premise are at :146, :176, :62 and :65. These four lines
  are the same in both copies.

**E7. Code facts at 8d3f10f.**
- **Stored milestone statuses.**
  - `milestone_status` (`strategy.py` 356-372) returns "met" when any past row met the target.
  - Its projection needs a row at least 12 steps old (368).
- **Event reviews.** `_maybe_event_review` (`governor.py` 2202-2218) caps reviews at 12 steps: months in
  Stellaris, turns in Civ VI.
- **Purchase caps.**
  - `purchase_cap` (`civ6.py` 561-568) gives the 1.0 share only to cities that `in_danger` (504-515)
    flags.
  - `tests/test_pillars.py:255` pins `treasury_share <= 0.5`.
- **Defender prices** (`harness.lua` 316-336):
  - `defence_prices` is filled only for threatened cities (449);
  - it keeps the two cheapest by gold;
  - it filters with `CanProduce`, which ignores strategic resources.
- **Capture count.** The capture count (353) counts melee and cavalry only (`unit_kind` 206-211).
- **Majors and our own player.**
  - `majors()` (453-470) has no alliance field.
  - `H.me()` (113-117) falls back to `AutoplayManager.GetReturnAsPlayer()` when the local player is −1.
- **Autoplay turns.** `_wait_turns` logs `turns=n`, the number requested, not the turns that passed
  (`civ6_governor.py` 532).
- **Pause.** `set_paused` only stops autoplay (`civ6.py` 141-144).
- **Traces.** They cut every text at 6,000 characters (`trace.py` 23).
- **No saved snapshots.** No run stores raw snapshots, only metrics rows and traces. Replays in tests are
  therefore synthetic snapshots built from the recorded numbers.
- **One pilot service.** `game-pilot.service` runs whichever game `runs/pilot-settings.json` names.

**E8. L10's loyalty test and its threshold disagree.**
- Haarlem read 95, 77, 59, 41 over T546-T549 and flipped at T552.
- "Below 50 and falling" first holds at T549, but the post-mortem's test row is T547 (77).
- A projection clause fires at T547: 77 left at 18 lost per turn is a flip in about 4 turns.

**E9. The Civ VI pilot runs the Stellaris code paths it inherits.**
- **Event triggers.** `EVENT_TRIGGERS_CIV6` spreads the shared `EVENT_TRIGGERS` (`civ6_governor.py` 110).
- **Milestone statuses.** Civ VI milestones go through the same `milestone_status`, both in `_pressures`
  (`governor.py` 2249) and in `_newly_missed_milestones` (2304-2316).
- **Scoring.** `telemetry.score(after_months=12)` runs at each Civ VI decision.

**E10. Ruling 4's spend formula matches the game's log, and the AI spent gold too.** The formula is
balance before + yield × turns − our spends − balance now.

| Stretch | Our orders | Faith | Gold |
|---|---|---|---|
| T525-T528 | none: the decision failed | 2,278 + 226 × 3 − 958 = **1,998** | 1,630 + 272 × 3 − 730 = **1,717** |
| T496-T499 | research only | 1,833 + 184 × 3 − 698 = **1,687** | 1,065 + 172 × 3 − 518 = **1,063** |

- The T525-T528 faith figure equals the Rock Band logged at T526 (1,998 faith).
- The post-mortem named only the faith. The gold spend is not named anywhere yet.

---

## Rulings

### A. Buy-out rules

1. **Weakness is one shared test.**
   - **Decision.** A pure `weakness(snapshot, limits)` in a new module `src/pilot/threat.py`. It returns the
     clauses that hold, or an empty list:
     - **war**: at war with a major (`wars[].major`);
     - **last**: our military ranks last among the met majors, with at least 2 met;
     - **low**: our military is below `weak_median_share` (0.6) × the median of the met majors;
     - **outgunned**: a met major that is not our ally has at least `strong_neighbour_ratio` (2.0) × our
       military.

     Details:
     - Both numbers are new keys in `[actions.purchase]` of `corpora/civ6/pillars.toml`.
     - `majors()` gains `allied`, true while an alliance with us is in force (`GetAllianceType`,
       **unverified** return shape; read under `pcall`). Without the field, every major counts as not
       allied, which errs toward defending.
     - The governor publishes the clauses in `log.state.info["weakness"]`.
     - The briefing gets one line, e.g. "Military weakness: last of 6; 343 is 0.31 × the median 1,094;
       CIVILIZATION_MALI 2,428 (7.1×, allied), CIVILIZATION_MAYA 1,491 (4.3×)".

     Rulings 2, 3, 14 and 20 use this test.
   - **Why.**
     - RC1 and RC2: the gap built for 150+ turns with nothing that changed the buying rules (war-3 [both],
       treasury-2 [one]).
     - The post-mortem's L1 names these clauses. E1 shows they cover the pre-war window.
   - **Cost if wrong.** A weak late game keeps the test on almost all the time (E1). The limits in rulings 2
     and 3 bound what that costs. A major that later turns on us while flagged allied is missed until the
     alliance ends.

2. **Defenders may spend down to the reserve under weakness, in every city.**
   - **Decision.**
     - **Cap.** `purchase_cap` gives the `threatened_share` (1.0: down to the reserve) to a defender
       purchase (`is_defender`) when `in_danger(city)` holds or `weakness()` is non-empty.
       - Everything else keeps `treasury_share` 0.5: buildings, and units outside `defender_classes` (a Rock
         Band, a Settler).
       - `in_danger` keeps its other users unchanged: defence first, must-haves and chunks (levers rulings
         17, 19, 20 and A1).
     - **Order count.** While the test holds, defender purchases in different cities do not count toward
       `max_orders = 2`, but a city still gets at most one defender per decision.
     - **Other limits.** The per-city cooldown (5 turns), stacking, the skip rule and the reserves stay.
     - **Refusal message.** `cap_binding` names the clause, e.g. "a defender may spend down to the reserve:
       at war with CIVILIZATION_AUSTRALIA".
     - **Levers design.**
       - Levers ruling 17 loses `purchase_cap` from its users.
       - Levers ruling 18's reserves are unchanged.
       - `tests/test_pillars.py:255` stays as it is, because `treasury_share` is still 0.5. A new test pins
         the new keys.
     - **Learned rule.** The rule at learned `strategy.md`:374 ("save gold until the balance is double the
       unit cost") is corrected under ruling 29.
   - **Why.**
     - H1, war-5, treasury-6 and treasury-2 [one].
     - The cap was the only block on a defender the game allowed at T365, T475, T496, T504 and T538
       (strategy-2's correction). During the war it refused T544 and T553 and was cited in five model holds
       (T541, T552, T555, T556, T565).
     - Replays that pass under this rule and fail under 0.5:
       - T496 Rockhampton, Modern AT, 1,160 of 1,833 faith;
       - T538 Machine Gun, 1,080 of 1,222 faith;
       - T541 Jiaodong, Modern AT, 1,160 of 1,961 faith;
       - T553 Taiyuan, Machine Gun, 1,080 of 1,630 gold;
       - T555 Taiyuan, Modern AT, 1,160 of 1,911 gold.
     - treasury-1 is refuted, but only its word "every". The verifiers still put the cap at 4-5 defenders.
   - **Cost if wrong.** Gold and faith become defenders instead of Libraries and Research Labs, and techs lag
     further. RC1 names the tech lag too. The treasury can empty on a city that falls anyway, as every bought
     AT's city did. The reserve and the 5-turn cooldown bound the drain per city.

3. **A rule-based defender buy before each multi-turn stretch.** This is L2's first half, with L15 folded
   in.
   - **Decision.**
     - **When.** Before an autoplay call of 2 or more turns, while `weakness()` holds and no defender was
       bought at this hand-back, the governor orders one purchase itself. No model call is made.
       - At war with a major the chunk is already 1 turn, and ruling 14 decides at each hand-back instead.
     - **Where.** The city is the first ungarrisoned one, ranked in this order:
       1. in danger;
       2. threatened;
       3. no walls;
       4. the capital;
       5. by name.
     - **What.** The unit comes from that city's `defence_prices` (ruling 7). It must:
       - be allowed;
       - need no strategic resource;
       - be of a defender class;
       - fit ruling 2's cap.

       The strongest by corpus `max(combat, ranged)` wins, then the cheaper. Faith is tried first, since
       faith is what the AI's purchases drained.
     - **Limits:**
       - at most one purchase per stretch;
       - the per-city cooldown and the reserves;
       - upkeep: gold per turn minus the unit's `maintenance` stays at 0 or above.
     - **Path.** The order goes through `check_orders` and the read-back like any other. It is recorded
       `by: governor` with the note "bought before autoplay (military weakness: <clauses>)", and gets a
       journal line.
     - **Production (L15).** Levers ruling 16's governor fill, today only for idle research and civics,
       also fills an empty production queue in an ungarrisoned city. It picks the same unit as the purchase
       above, as a production order. Fills into empty queues completed 3 of 3 (levers E1).
     - **Parts of L15 not adopted:**
       - "One Machine Gun per border city": the snapshot has no border data.
       - "Ignore 'leave the AI's queues alone'": replacements of the AI's production held 38% of the time
         (S5).
     - **Switch.** `rule_buy = true` in `[actions.purchase]` turns this ruling and ruling 20's buy on or off.
   - **Why.**
     - strategy-3 [one]: 16 Rock Bands (about 21,600 faith), each bought in the stretch after a decision;
       T496 1,833 → T499 698, T525 2,278 → T528 958.
     - treasury-4 [one]: the T525 window was lost to model errors.
     - treasury-11 [both]: 6-8 pre-war defenders is the size of the missed contribution.
     - E2: the yields paid for it.
     - Once every city is garrisoned, stacking stops further buys. The AI moving units off the tile reopens
       one city at a time, under the cooldown.
   - **Cost if wrong.** A defender the model would not have bought. It costs 800-2,320 in Future-era prices
     and 8 gold a turn. It stops when the test does. The bought unit may not hold the city (RC1).

4. **What the AI spent between decisions.** This is L2's second half and T3.
   - **Decision.**
     - **Computed.** At each hand-back, per currency: `ai_spent = balance before + yield × turns − our own
       spends − balance now`. The yield is the start snapshot's rate. Metrics rows gain `ai_spent`, summed
       between decisions.
     - **Shown.** The briefing line reads, e.g., "Since T525 the AI spent 1,998 faith (UNIT_ROCK_BAND,
       T526) and 1,717 gold (not named)" (E10). It appears only when the spend is at least max(50, 10% of the
       yield over the interval), because yields change mid-stretch.
     - **Named.** The item comes from `AI_CityBuild.csv` under `civ6_appdata` (`FAITH PURCHASE` and
       `PURCHASE` rows of our player). A new controller command `civ6 log-tail <file> --offset N` reads an
       allowlist of three log files. It makes one agent read per decision, and only when there is a spend to
       name. Otherwise the line says "not named".
     - **Urgency.** When one interval's spend in a currency is at least the cheapest allowed defender's price
       in it, the next check raises an urgent decision: "the AI spent 1,998 faith on UNIT_ROCK_BAND".
       - It does not raise `needs_attention`, which stops play until a human answers. The user is hands-off,
         and this would have stopped the run 16 times.
   - **Why.**
     - H2 and strategy-3. At T507 the model wrote "Faith is currently 478 (not 1833)" and moved on.
     - treasury-3 is refuted: the faith was logged row by row, so it can be named.
     - E10: the formula reproduces the logged Rock Band exactly, and it shows an unnamed gold drain of
       similar size.
   - **Cost if wrong.** A yield change inside a stretch (a new building, an era's bonus) reads as spending.
     The threshold hides small errors, and the named item shows a real purchase.

5. **Re-send a lost purchase only when the read-back proves nothing was spent.** This is L3 and T7.
   - **Decision.**
     - **Proof.** A purchase whose reply was lost (a transport error) is proven not to have run when the
       read-back snapshot of the same turn shows both:
       - the balance within 1 of its value before;
       - the item's `units.by_type` count (or `buildings`) unchanged.

       The row is then `lost` with the detail "nothing spent (proved)", and the purchase is queued for one
       re-send.
     - **Re-send.** It runs before the next autoplay call starts, once `turn_ready` reads the engine idle.
       If it is not idle within the start grace, the re-send moves to the next hand-back. It goes through
       `check_orders` again on a fresh snapshot, so a new price, a unit now on the tile or the cooldown
       refuses it.
     - **Limits.**
       - At most one re-send per order.
       - A second lost reply raises an urgent decision: "order lost twice: purchase unit:modern_at in
         Longxi".
       - Nothing is re-sent when the read-back failed or the balance moved (it may have run).
       - Nothing is re-sent for last-stand actions (levers ruling 24).
   - **Why.**
     - war-9, treasury-9 and reliability-6 [one]: at T570 Longxi's Modern AT (1,160 gold, allowed) timed out
       with "gold went from 1407.6484375 to 1407.6484375". Nothing ran T571-T574, and the discount ended at
       T572. The T568 loss was recovered only because the model re-ordered it at T569.
     - A lost purchase does not start the cooldown (H8), so the re-send is allowed.
   - **Cost if wrong.** An engine that applies the first purchase after the read-back: the fresh snapshot
     then shows the balance dropped or the unit on the tile, and the re-send is refused. The worst case is
     one extra defender.

6. **Price changes are shown.** This is L4, narrowed.
   - **Decision.**
     - **Line.** When a defender's gold or faith price in `defence_prices` changes by 25% or more between
       decisions within one era, the briefing says so: "gold unit prices halved since T543 (Modern AT 2,320
       → 1,160)".
     - **Cause.** One `log-tail World_Congress.csv` read, only when a change is seen, names a `RESOLUTION
       DECIDED` row in that window: "World Congress: WC_RES_MERCENARY_COMPANIES (T542)".
     - **Expiry.** It is not read, because the session calendar is **unverified**. The line adds "this may
       end at the next World Congress session".
   - **Why.** treasury-8 [one]: the halved price ran T544-T571, and 1,626-1,676 gold was stranded when it
     ended at T572. Detecting the change from the snapshot needs no new Lua.
   - **Cost if wrong.** A price change from something else, such as a policy card, is reported without a
     cause. That is harmless.

### B. Briefing

7. **List the defenders the game will actually sell, with the reason for each refusal.** This is L5.
   - **Decision.**
     - **Every city.** `defence_prices` runs for every city, not only threatened ones.
     - **Per currency** it lists:
       - the cheapest two defenders the game allows;
       - the best resource-free ranged unit and the best anti-cavalry unit the city can produce, allowed or
         not.
     - **Refusal reasons.** Each refused entry carries a `why`:
       - `resource`: the corpus `resource_cost`, set against the snapshot's stock, e.g. "needs 1 Oil, have
         0";
       - `stacking`: a land unit is already on the tile;
       - `balance`: the price is above the balance;
       - `game`: `CanStartCommand` refused for another reason. With its failure-reason table (**unverified**)
         the text uses the game's own words.
     - **Strategic stock.** The snapshot gains `resources`, our stock of each strategic resource
       (`GetResources():GetResourceAmount`, **unverified**; read under `pcall`, and the field is absent when
       it fails).
     - **Text.** A city with nothing to buy says so: "Guangzhou: no defender can be bought now (Modern AT:
       a unit is on the tile; Infantry: needs 1 Oil, have 0)".
     - **Users.** `_needs_defender_first`, levers ruling 20's conversion and ruling 3 read only the allowed
       entries.
   - **Why.**
     - H5, war-6 and treasury-7 [one]. The list always showed Infantry (860) and Tank (960) "not allowed
       now" for lack of Oil, never the buyable Modern AT (1,160) or Machine Gun (1,080).
     - The harm: the T556 keep with 2,053 gold, the T566 Infantry refusal, "No gold or faith purchases are
       available" at T548, four learned rules, and defence-first switched off.
   - **Cost if wrong.** A slower snapshot: about 300 local purchase checks for 8 cities, and about 120 bytes
     more per city. If the stock read fails, "needs 1 Oil" says "stock unknown" and the entry still carries
     the game's own `allowed`.

8. **Every prompt carries the purchase arithmetic and the strategic stock; plans that need a missing
   resource are sent back.** This is L6's first half.
   - **Decision.**
     - **Limits line.** `_limits_text`, and the Strategist's review prompt, get a "Purchase limits now" line.
       Example: "a defender may cost up to 1,961 faith / 798 gold in any city (at war: down to the reserve);
       anything else up to 980 faith / 414 gold".
     - **Stock line.** "Strategic stock: Oil 0, Aluminum 3, Uranium 0 (units that need them cannot be bought
       or built)".
     - **Deferrals.** The decision instructions require that a defender the answer chooses not to buy cite
       this decision's price result.
     - **Validator.** The Strategist validator sends back once any of these whose corpus `resource_cost`
       names a resource our latest stock cannot pay:
       - a `prefer_purchases` or `prefer_production` id;
       - a `unit:` id quoted in a goal.

       The message reads "unit:mechanized_infantry needs 1 Oil; we have 0". Pinned pillars are exempt, as
       for every validator rule.
   - **Why.**
     - S3 and S4, treasury-2's T486 misbelief ("we cannot buy land units with faith", with an 800-faith AT
       Crew within the 803 cap).
     - T496 "Buy 2 mechanized_infantry" (2,600 faith) with 1,833 on hand.
     - The cap was in the instructions but never computed for the model.
   - **Cost if wrong.** A strategy that plans to gain a resource first (a trade, a mine) is sent back once.
     The retry sees the stock, and a pinned pillar keeps it.

9. **The order record splits purchases by item class.** This is L6's second half and T8.
   - **Decision.**
     - **Keys.** `purchase unit gold`, `purchase unit faith`, `purchase building gold` and `purchase building
       faith` replace `purchase gold` and `purchase faith`. Older rows are keyed by the corpus kind of their
       `id` when loaded.
     - **Counts, not rates.** Purchase keys show counts only, because a purchase read back as done is
       `completed` by construction. For example: "unit purchases: 7 bought, 2 refused by the harness (cap
       2), 2 refused by the game (stacking 1, Oil 1), 2 lost".
     - **Refusal class.** Refused rows gain `refusal`: `cap`, `reserve`, `stacking`, `cooldown`, `skip`,
       `defence_first`, `resource` or `game`.
     - **Scope.** Levers ruling 14 rejected splitting by class to protect sample sizes. That still holds for
       production keys; purchase keys have no rate to protect.
     - **Stellaris** needs no change. Its keys are already one per action class: directive, tech, `market
       <side> <resource>`, posture and `crisis <step>`.
   - **Why.** H11, strategy-6 [one]: "faith purchases held 8 of 8" came from cheap buildings, while no faith
     unit purchase was sent from T385 to T541.
   - **Cost if wrong.** More keys, each under its sample minimum longer. The counts stay true.

### C. Triggers and cadence

10. **Falling behind, ported to Civ VI with per-measure thresholds.**
    - **Decision.**
      - **Rows.** Civ VI metrics rows gain `behind`: the measures where ours < factor × the median of the
        met majors. The factors live in `[peers] behind` of `corpora/civ6/pillars.toml`:
        - `military = 0.6`;
        - `techs = 0.85`;
        - `civics = 0.85`;
        - `score = 0.8`;
        - `cities = 0.8`.

        Military counts as behind also when it ranks last with at least 3 majors met.
      - **Trigger.** Entering "behind" is urgent: "falling behind in military: 318 against a median of
        1,094, last of 6". "falling behind in military" is also a review trigger in Civ VI. The other
        measures are decision-only.
      - **Stellaris** keeps its 0.5 rule in Rust (`stellaris.rs` 551).
    - **Why.** strategy-9 and H4: Civ VI had no rank trigger (Stellaris has one, `governor.py` 379-383). E4
      shows 0.5 never fires for techs in Civ VI.
    - **Cost if wrong.** About 20 more urgent decisions over the 540 turns replayed (E4). The trigger fires on
      entry only. From T457, military stayed behind until the end, so later warnings have to come from
      ruling 11 and the weakness line (ruling 1).

11. **A neighbour-buildup trigger, shared by both games.** This is L10's first bullet and T5.
    - **Decision.**
      - **Function.** A pure `buildup(rows, window, ratio=2.0, growth=0.5)` in `src/pilot/threat.py`. It
        fires for a met neighbour, not our ally, that has at least 2× our military and grew 50% or more
        within the window. It fires at most once per neighbour per window.
      - **Civ VI.** A 20-turn window, over the rows' `neighbours`. It is urgent and a review trigger:
        "neighbour buildup: CIVILIZATION_AUSTRALIA 598 military (+73% in 20 turns), 2.0× ours (295)".
      - **Stellaris.** A 24-month window, over the rows' `neighbours`. Those rows carry absolute
        `military_power`; `alliance` and federation statuses are skipped. It is an urgent decision only:
        no review, and never a war-crisis entry, because Stellaris levers ruling 12 keeps ratios out of
        crisis entry.
    - **Why.**
      - strategy-9 [one]: Australia went from 233 (T454) to 1,106 (T525) with no trigger.
      - T5: neither game warned of a neighbour at 3× our strength.
      - E3's rates: about 1 per 15 turns in Civ VI, about 1 per 10 years in Stellaris.
    - **Cost if wrong.** An urgent decision that changes nothing, which the causality verifier predicted for
      a rank trigger alone. With rulings 2-3 in place, a decision can now act on it.

12. **Gold per turn turning negative is urgent in Civ VI.**
    - **Decision.**
      - "gold per turn negative: −6.8" fires when `gold_yield` goes from 0 or above to below 0.
      - It is a review trigger, so the economy stance gets rewritten.
      - Stellaris already has "net turned negative" (`governor.py` 376-378).
    - **Why.**
      - strategy-8 [one]: -6.8 to -12.6 a turn over T289-T304 while the stance still said +12.4, and the
        only trigger was "gold below the reserve" at T302.
      - E5: 5 fires in 583 turns.
    - **Cost if wrong.** Five reviews in a campaign.

13. **Loyalty falling toward a flip is urgent.**
    - **Decision.** "loyalty falling: Haarlem 77 (−18 a turn)" fires when a city's loyalty fell since the
      previous snapshot and either:
      - it is below 50; or
      - it is at most 5 × its drop per turn (a flip within about 5 turns).

      It fires once per city until that city's loyalty rises again. It is decision-only; the model's levers
      are policy cards and purchases. Metrics rows gain `low_loyalty`, the count of cities under 50, so the
      trigger's frequency can be measured.
    - **Why.**
      - war-4 [both]: Haarlem (T552), Rockhampton (T569) and Shanghai (T475) were lost to loyalty.
      - E8: the projection clause fires at T547 as the post-mortem's test wants; "below 50" alone would wait
        until T549.
    - **Cost if wrong.** Unknown frequency. The field above measures it.

14. **Decide at every hand-back while a city stays in danger in a war.** This is L9.
    - **Decision.** While at war with a major, a hand-back triggers a decision when a city meets all of
      these:
      - it is `in_danger`;
      - no unit is on its tile;
      - ruling 7 lists a defender for it that is allowed and within ruling 2's cap, in either currency.

      The reason reads: "city still in danger: Guangzhou (walls 0/400, garrison 80/200; Modern AT 1,160
      faith allowed)". There is at most one such decision per hand-back, and none when nothing can be
      bought, as in T576-T582.
    - **Why.** war-8, reliability-7 and H6 [one]: triggers fire only on change, so T559-T562, T571-T574 and
      T576-T582 had no decision while Guangzhou, Taiyuan and Longxi stayed in danger.
    - **Cost if wrong.** A model call every war turn: at most 39 in T541-T579, where 20 ran.

15. **Event reviews: a per-game cap in the game's own unit; "new war" and "city lost" always review.** This
    is L8.
    - **Decision.**
      - **Cap.** `[time] review_cap` in each `pillars.toml`:
        - Stellaris: 12 months, as today;
        - Civ VI: **5 turns**.

        The post-mortem suggests about 3. This design picks 5, one default decision interval, because:
        - the exempt triggers already cover the war case;
        - rulings 10-12 add review triggers, and a cap shorter than the decision interval would let
          reviews outnumber decisions.
      - **Exempt.** `[time] review_exempt`:
        - Civ VI: `["new war", "city lost"]`;
        - Stellaris: `["new war"]`. A colony lost at war enters the war crisis, whose review stays under the
          cap (Stellaris levers ruling 12).

        An exempt review still resets the cap's clock. The existing limit of one review per decision point
        holds.
      - **Messages.** The skip message uses the unit: "within 5 turns of the last event review".
    - **Why.** war-7 [one] and H7: 15 of 18 urgent war triggers were skipped in T541-T570. The T541 new
      war came 3 turns after the T538 review, and the first wartime strategy came at T546, after Beijing
      fell.
    - **Cost if wrong.** In a collapse like T541-T579, up to 8 more reviews, one per lost city: a Strategist
      call each.

16. **Autoplay chunks stay as levers amendment A1: L11 is not adopted.**
    - **Decision.**
      - Peace keeps `PILOT_AUTOPLAY_CHUNK` (3).
      - War with a major, or a city in danger or about to fall, keeps 1 turn.
      - The ratio clause L11 proposed is not added.
    - **Why.**
      - E1: a neighbour at 2× ours held in every row from T380 to T540. L11 would have meant one-turn
        autoplay for 160 turns.
      - That has a measured cost: treasury-10 found 0 AI purchases in 186 one-turn turns, and issues.md
        has an open item on one-turn autoplay.
      - Its gain is at most 2 turns' notice. war-1 and reliability-5 [one] found the 3-turn chunk cost one
        decision point, and the governor still bought nothing at T541.
      - Ruling 3 acts before each stretch instead.
    - **Cost if wrong.** A surprise war is seen up to 2 turns late, as at T539-T541.

### D. Milestones

17. **A milestone is judged on the current value, in the shared code.** This is L13 and T1.
    - **Decision.**
      - **Status rule.** `milestone_status` (`strategy.py`) judges one value: the latest row at or before
        `today` and not before the milestone's `set`.
        - **met**: that value meets the target;
        - **missed**: otherwise, when today is past `by`;
        - **on_track** or **at_risk**: otherwise, from today's projection;
        - **at_risk**: when there is no row since `set` ("no reading since it was set").
      - **`set` stamp.** `Milestone` gains `set` (a date or turn). The governor stamps it when it publishes a
        strategy. A milestone with the same metric, op, target and `by` as in the previous version keeps its
        earlier `set`. A stored strategy without `set` gets no row filter; the current value still decides.
      - **Trigger.** "milestone missed" fires once per milestone (pillar, metric, op, target, by) per run,
        so a milestone that recovers and falls again does not re-fire.
      - **Scope.** Stellaris uses the same function (`governor.py` 76, 2249, 2301, 2312).
    - **Why.**
      - strategy-1 [one]: "military >= 170 by T350" read met at T350 with 124. Military's share of effort
        was 2-7% at weight 22, because met cuts need to 0.3 (H3).
      - The same rule hid the missed gold milestone during the T291-T304 deficit (strategy-8) and made rank
        milestones unable to fire (strategy-9's correction).
      - Under the new rule the T350 milestone reads at_risk at T342-T350 and missed from T351.
    - **Cost if wrong.** The day this deploys, Stellaris and Civ VI pressures shift toward pillars whose
      metric fell below an old target. The frames change at once, and the next review rewrites stale
      milestones. The Strategy tab shows the honest statuses.

18. **Military targets relative to the median or the strongest neighbour, in Civ VI.** This is L14.
    - **Decision.**
      - **New metrics.** Civ VI metrics rows and `[metrics] names` gain:
        - `military_vs_median`: ours ÷ the median of the met majors;
        - `military_vs_strongest`: ours ÷ the strongest met major that is not our ally.
      - **Validator rules** (`[strategy]`, Civ VI):
        - while military is below 0.6 × the median, or ranks last (ruling 1's `low` or `last`), the military
          pillar must hold a milestone on one of the two new metrics with a target of at least 0.5;
        - an absolute `military` target under 0.5 × the current median is sent back;
        - `rank:*` milestones are sent back while fewer than 3 majors are met.
      - **Briefing.** It says "peers are the N majors we have met".
      - **Stellaris** is not changed here. Its peers are all regular empires, not only met ones, and its
        records are already relative (Stellaris levers ruling 7).
    - **Why.**
      - strategy-7 [one] and S2: targets were set 10-28% above our own strength, or against the weaker
        Dutch. On their due dates they stood at 0.44-0.56 of the median.
      - strategy-4: rank milestones counted only 2 met civs.
    - **Cost if wrong.** A Strategist retry. With no met major, the rules are off.

### E. Time constants

19. **Every shared time constant is named in the game's unit.** This is T2.
    - **Decision.** Each `pillars.toml` gets a `[time]` table with `unit = "months"` or `"turns"`. The shared
      code reads it. Audit at 8d3f10f:

      | Constant | Where | Stellaris | Civ VI |
      |---|---|---|---|
      | Event-review cap | `governor.py` 2202-2218 | 12 months | 5 turns (ruling 15) |
      | Milestone projection look-back | `strategy.py` 368 | 12 months | 12 turns (unchanged) |
      | Outcome scoring horizon | `telemetry.score`, called at every decision | 12 months | 12 turns (unchanged) |
      | Neighbour-buildup window | new (ruling 11) | 24 months | 20 turns |
      | Order record windows | `[orders]` | already months | already turns |
      | `trends`, `expand_blocked`, status-quo asks, crisis constants, `rows_months`, `stall_months` | `governor.py` | months, unchanged | not reached: Stellaris-only paths |

      - Values with no evidence against them keep today's effective number, now named and tested.
      - Log and prompt text print the unit word.
      - A test loads both `pillars.toml` files and asserts each value.
    - **Why.** war-7 and H7: "12 in-game months" silently became 12 turns. E9 lists the other shared paths.
    - **Cost if wrong.** None in behaviour, beyond ruling 15's change.

### F. Model resilience

20. **A failed decision retries with the strategy model, then acts by rule.** This is L19.
    - **Decision.** On `episode_error`, which means every decisions model failed or the request limit was
      hit, the governor acts before any autoplay:
      1. **Retry.** One retry at the same hand-back. It uses the decisions agent on the `strategy` role's
         models, skipping any that are cooling down. The prompt is the same plus one line: "Answer now, with
         at most 3 tool calls."
         - The request limit stays `governor_max_requests`. The retry is the extra budget, so raising the
           limit for every call is not needed.
         - When the strategy role has no models of its own, the models that just failed are not tried again.
      2. **Rule-based fallback** if the retry fails:
         - today's idle research and civic fill (levers ruling 16);
         - when `weakness()` holds, ruling 3's buy for the city most in need (in danger first).

         It is reported "no answer from the model: the governor acted by rule".
    - **Why.**
      - treasury-4 and war-10 [one], H9: T512, T522 and T525 failed on 503s and the request limit.
      - T525 was the only pre-war window the cap allowed, with 2,278 faith, a cap of 1,139 and a Machine
        Gun at 1,080. Nothing retried, and the next decision came at T530.
      - A retry on another model separates a provider outage from a model that spends its budget on tool
        calls.
    - **Cost if wrong.**
      - One more strategy-model call per failure: 3 of 19 decisions before the war.
      - A rule-based buy the model might not have chosen, within ruling 3's bounds.

### G. Elimination and the end of a run

21. **Civ VI: the run ends when our civilization is gone.** This is L17 and T6.
    - **Decision.**
      - **Snapshot.** It gains `alive` (`Players[me]:IsAlive()`, under `pcall`; `nil` means unknown).
        `units.by_type` already gives the settler count.
      - **Fixed player id.** The run takes its player id from its first snapshot and never re-derives it.
        A later snapshot for another player id stops the run for a human, like the existing leader and
        map check.
      - **End signal**, either:
        - `alive is False` on one read; or
        - 0 cities and 0 settlers on 2 consecutive snapshots.

        `local_player == -1` is never used: China was alive again at T913 while the local player read −1
        at T916 (reliability-2's correction).
      - **Actions, in order, with no model call:**
        1. stop autoplay;
        2. emit `campaign_end {result: "lost", last_city_turn, seen, signal, report}`;
        3. write the journal entry;
        4. set `runs.status = 'lost'` in telemetry;
        5. set `RunState.status = "ended"` and publish `info.end`;
        6. leave the run loop.

        No decision and no review runs after the first 0-city read.
      - **Report.** It is deterministic:
        - the cities lost, with the turn and the taker where known (the "city lost" reasons);
        - the last military ratio against the strongest enemy;
        - the stranded gold and faith;
        - the decisions made after the first 0-city read, which should be 0.
      - **Afterwards.** Two `autoplay_status` reads 60 s apart. If the turn moved, the report adds "the game
        keeps playing all-AI turns by itself; exit to the main menu to stop it". No input is sent. What
        stops the game is **unverified**: stopping the governor did not stop it (T763 → past T1290).
      - **A new run** on the same campaign ends at its start check with the same report while the signal
        holds. A player that comes back to life, as China did at T913, is a new start by a human.
      - **issues.md.** The open "defeat not detected" item (issues.md line 5) closes when this deploys.
    - **Why.**
      - reliability-1 and reliability-3 [one]: 16 decisions and 4 reviews ran over T583-T763 (378,629
        input tokens) until a human stopped the run.
      - reliability-2 is refuted: the defeat was seen ("0 cities, 0 units"); what was missing is an end
        state.
    - **Cost if wrong.**
      - A false `alive = false` ends a live run. A human restarts it, and the start check repeats the
        verdict only while the signal holds.
      - The 2-read rule stops a single glitched 0-city read from ending the run.

22. **Stellaris: the run ends with no owned planets.** This is T6.
    - **Decision.**
      - **End signal.** 0 owned planets (`planets`) in 2 autosaves in a row ends the run the same way as
        ruling 21.
      - **Stall after 0 planets.** When the date stalls after a save with 0 planets, the date-stall watchdog
        (Stellaris levers ruling 23) ends the run as lost instead of raising `needs_attention`. The game may
        stop saving once the empire falls (**unverified**).
      - **Not an end:**
        - a lost capital, which stays the "colony lost" trigger;
        - a briefing that cannot find our country ("player country N not found"). That raises
          `needs_attention`, because a save from another game reads the same way.
    - **Why.** T6. What Stellaris writes once the player's empire is destroyed is **unverified**. The planet
      count is the signal the briefing already reads.
    - **Cost if wrong.** An origin or situation with 0 planets while alive (**unverified** that any exists
      in 4.5.1) would end a live run. A human restarts it.

23. **How the dashboard shows the end.**
    - **Decision.** This branch edits no dashboard file.
      - **Data it publishes:**
        - `info.end = {result, turn, seen, signal, report}` and `status = "ended"` on `/status` while the
          process lives;
        - the `campaign_end` event;
        - `runs.status = 'lost'`.
      - **Dashboard v2 renders it:**
        - one row in its governor-line table (v2 ruling 6): state "lost", sentence "China (Kublai Khan) was
          eliminated in T579, seen at T583. The run ended; the game plays on by itself.", with the report
          as the facts line;
        - a state "lost" in the campaign picker (v2 ruling 4);
        - a mark on the chart at the last-city turn;
        - no Resume for that campaign.
      - **Before v2 merges**, the current page shows the run as not running and the `campaign_end` event in
        Activity.
    - **Why.** v2 owns `dashboard.py` and `dashboard.html`, and its design already covers status when the
      governor stops. Keeping hunks apart avoids a conflict.
    - **Cost if wrong.** Until v2 merges, the end is only a stopped run plus an event line.

### H. Diplomacy

24. **Name who declared each war.** This is L7 and T9.
    - **Decision.**
      - **Source.** When a snapshot shows a new war, one `log-tail DiplomacySummary.csv` read names the
        declarer. The file is under `civ6_appdata` (not `civ6_docs`), and `majors()` supplies the player ids.
      - **Wording:**
        - "539, 5, Team 0, … Declaring War …, Surprise" → "new war: CIVILIZATION_AUSTRALIA declared a surprise
          war on us";
        - our own id declaring → "new war: our AI declared war on CIVILIZATION_AUSTRALIA";
        - "…, Defensive Pact" → "CIVILIZATION_MALI joined through its defensive pact";
        - a failed read → "new war: at war with CIVILIZATION_X (who declared is not known)". It never guesses.
      - **Learned rules.** The T121 premise at learned `strategy.md` :62 and :65 is corrected under ruling
        29.
      - **Stellaris** already says "we are attacker" or "defender" (`governor.py` 359). No change.
    - **Why.**
      - diplomacy-5 [one]: China's own autoplay AI declared war at T121, the model recorded it as
        Australia's, and a rule from the wrong premise followed. The war cost Xi'an.
      - war-2 is refuted: the logs hold the declarer.
    - **Cost if wrong.** One agent read per new war. A changed log format gives "not known", never a wrong
      name.

25. **No diplomacy goals until a diplomacy order exists.** This is L18's short term.
    - **Decision.**
      - **Validator.** `[strategy] unpursuable = ["peace", "ceasefire", "alliance", "friendship",
        "denounce"]` in the Civ VI pillars file. The validator sends back, once, a goal that names one of
        these words: "no order can pursue it: the game's AI handles diplomacy during autoplay".
      - **Instructions.** "the military stance names its exit condition (peace, a city retaken, or the
        enemy's strength below ours)" becomes "(a city retaken, the enemy's strength below ours, or the war
        ending)". The war ending is something to watch, not a goal.
      - **Ruling 1** needs only `allied` from L18's list of relation fields.
    - **Why.** war-11 [one]: "Get peace with Australia" was the goal at T563, T565 and T575, with no order
      kind that could pursue it (`civ6.py` 461).
    - **Cost if wrong.** A goal that uses one of the words for something else is sent back once. The Diplomacy
      pillar keeps its other goals.

### I. Last stand

26. **The capture test counts every class that can take a city.** This is L16.
    - **Decision.**
      - **Capturer.** In `harness.lua`, an adjacent enemy counts as a capturer when either:
        - its kind is melee or cavalry; or
        - its row has `CanCapture` true, melee `Combat` above 0, and a promotion class other than ranged or
          siege. A Giant Death Robot passes: Combat 130, RangedCombat 120.
      - **`about_to_fall`** gains a clause: garrison 0 and walls 0 with an enemy within 2.
      - **Unchanged.** The stand stays off (`PILOT_LAST_STAND=0`).
      - **Effect on the trigger.** "city falling" now fires for Beijing at T545 (garrison 0/200, walls 0/400)
        and Guangzhou at T565 (80/200, 0/400, a GDR next to it).
      - **Unverified.** `CanCapture`'s values by promotion class. One read-only GameCore query at deployment
        lists them.
    - **Why.** war-12 [both]: both cities met the walls and garrison tests and fell in the next AI turn
      without tripping the test. H6.
    - **Cost if wrong.** Overcounting gives more "city falling" urgent decisions (on transitions only). The
      stand itself stays off.

### J. Observability

27. **Turns actually advanced, against those requested; full prompts in traces.** This is L20 and T6.
    - **Decision.**
      - **Civ VI.** `_wait_turns` logs `turns` as the turns that passed (`status.turn − turn`) and
        `requested` as `n`. When more turns passed than requested, it emits `turn_overrun {requested,
        actual, turn}`, and the hand-back's snapshot runs ruling 21's end check before anything else.
      - **Stellaris.** Each scheduled interval logs the months that passed against `decide_every_months`.
        More than one month over emits `pace_overrun`, for information only.
      - **Traces.** A trace's `prompt` steps are stored whole, up to 100,000 characters. Other texts keep
        the 6,000 cut. This closes plan.md's "Full decision prompts in traces".
      - **Game logs** are read only where rulings 4, 6 and 24 need them. A general import into telemetry is
        out of scope.
    - **Why.**
      - reliability-3 [one]: 18 of 25 autoplay calls after T579 passed more turns than requested (T583 →
        T612 on a 3-turn call), while the log showed the numbers requested.
      - H14: most per-city danger lines were cut from stored prompts.
    - **Cost if wrong.** Traces grow by about 10-20 KB per decision.

### K. Operations

28. **A deploy restarts only the affected game's pilot.** This is T10.
    - **Decision.** Two new scripts:
      - `scripts/pilot-affected.py <from> <to>`: a pure path classifier, tested;
      - `scripts/deploy-pilot.sh <from> <to>`, which acts on it.

      Path classes:

      | Class | Paths | Deploy action |
      |---|---|---|
      | civ6 | `src/pilot/civ6*.py`, `corpora/civ6/**` except `learned/` | restart a Civ VI pilot |
      | stellaris | `src/pilot/stellaris*.py`, `corpora/stellaris/**` except `learned/` | restart a Stellaris pilot |
      | galciv4 | `src/pilot/controller.py`, `corpora/galciv4/**` except `learned/` | restart a GalCiv IV pilot |
      | shared | the other `src/pilot/*.py`, including `dashboard.py` (the pilot serves its live controls with it, `cli.py` 81-108), and `pyproject.toml` | restart any pilot, and the viewer for `dashboard.py` |
      | view | `src/pilot/static/**` | restart `game-pilot-view.service` only |
      | rust | `crates/**`, `Cargo.*` | pause from the dashboard, build, resume. No restart: each call runs the binary afresh. |
      | none | `docs/**`, `games/**`, `tests/**`, `*.md`, `corpora/*/learned/**`, `scripts/ci*` | nothing |

      - **Unknown paths** count as shared.
      - **Which game runs.** The script reads the running pilot's game from its `/status` (`info.game`), or
        from `runs/pilot-settings.json` when no pilot runs.
      - **Restart.** It restarts `game-pilot.service` only when that game's class, or shared, is affected.
        Otherwise it prints "not restarted: the running civ6 pilot is unaffected; the change applies at its
        next start".
      - **AGENTS.md** §8 gets the rule.
    - **Why.** H14 and T10: a Stellaris-only merge restarted the live Civ VI run at T462. One unit serves
      whichever game runs (E7).
    - **Cost if wrong.** A path misclassified to another game leaves the running pilot on old code until its
      next start. Unknown paths restart, which is the safe side.

### L. Learned rules

29. **Known-false learned rules are refused, and the existing ones are corrected at deploy.** This is L12.
    - **Decision.**
      - **Refusals.** `add_rule` checks `[learned] refuse = [{pattern, why}]` from the game's `pillars.toml`
        against the rule and its why together, since both are written to the file.
        The Civ VI list:
        - "double the unit cost" and "save … until the balance is double" (ruling 2);
        - "cannot buy land units with faith" (faith bought units at T35, T384 and T544);
        - "'not allowed' … (in|IN) DANGER" and "not allowed in endangered cities" (ruling 7).

        A refused rule returns its `why` to the model.
      - **Corrections at deploy.** They are made against the live file (E6), in a commit on `main` before
        the merge (see Rollout):
        - :362, :374, :377, :386, and the T563, T565 and T575 rules the post-mortem cites (S6);
        - :62 and :65, the T121 premise (ruling 24);
        - :146 and :176, the T263 and T302 peacetime rules (S1).

        Each is corrected with its post-mortem evidence, not deleted. The file is the campaign's history.
      - **Test.** A test keeps the refused phrases out of the committed file.
      - **Out of scope.** The post-mortem's general check of a rule against the episode's price results. It
        needs judgement, not a pattern.
    - **Why.** S6: four learned rules codified the defender-list misreading, and one codified the cap as a
      saving rule, which the model then followed (T556).
    - **Cost if wrong.** A true rule refused by a loose pattern. The patterns are exact phrases from the false
      rules.

---

## Shared seams with feat/dashboard-v2

| Seam | This design | Rule |
|---|---|---|
| `dashboard.py`, `dashboard.html`, auth | ruling 23 | Not edited here. v2 renders `info.end`, `campaign_end` and the "lost" state. |
| `governor.py` info fields | rulings 1, 21-23 | New keys only (`info.weakness`, `info.end`), each set in one call. |
| `civ6_governor.py` | rulings 3-5, 14, 20, 21, 27 | Logic lives in new modules: `src/pilot/threat.py` (weakness, buildup, behind) and `src/pilot/campaign_end.py` (end checks and report). This file gets only the call sites. |
| `telemetry.py` | ruling 21 | One `UPDATE runs SET status` on `campaign_end`. |
| `learned/` files | ruling 29 | Edited only on `main` at deploy, never on a branch. |

---

## Rollout

Every commit goes through `scripts/ci-commit.sh` and is testable on its own. Each one updates `plan.md`,
`issues.md`, README, ARCHITECTURE.md, AGENTS.md §10-11 and `docs/pilot.md` where behaviour changes.

1. `fix(pilot): judge milestones on the current value` (ruling 17). Shared: Stellaris changes the day it
   deploys.
2. `refactor(pilot): time constants per game; new war and city lost always review` (rulings 15, 19).
3. `feat(civ6): snapshot fields for the post-mortem fixes` (read-only; rulings 1, 7, 21): `allied`, `alive`,
   `resources`, and `defence_prices` for every city with a reason for each refusal.
4. `fix(civ6): the capture test counts every capturer class` (ruling 26). The stand stays off.
5. `feat(civ6): defenders may spend to the reserve in war or weakness; purchase arithmetic in the prompts`
   (rulings 1, 2, 8).
6. `feat(civ6): order record by item class` (ruling 9).
7. `feat(civ6): falling-behind, neighbour, income and loyalty triggers; decide while a city stays in danger`
   (rulings 10-14).
8. `feat(stellaris): neighbour-buildup trigger` (ruling 11, Stellaris wiring).
9. `feat(civ6): rule-based defender buy before autoplay; what the AI spent` (rulings 3, 4; `civ6 log-tail`).
10. `feat(civ6): re-send a lost purchase only with proof` (ruling 5).
11. `feat(pilot): a failed decision retries with the strategy model, then acts by rule` (ruling 20).
12. `feat(civ6): relative military milestones` (ruling 18).
13. `feat(civ6): name who declared each war; no diplomacy goals` (rulings 24, 25).
14. `feat(pilot): end the run when the empire is gone` (rulings 21-23).
15. `feat(pilot): turns advanced against those requested; full prompts in traces` (ruling 27).
16. `feat(civ6): price changes in the briefing` (ruling 6).
17. `feat(pilot): refuse known-false learned rules` (ruling 29, code and refusal list).
18. `chore(scripts): a deploy restarts only the affected pilot` (ruling 28).

**Deploy order** (on `main`, in a window with the governor paused from the dashboard):
1. Commit the live learned files as they are (E6).
2. Correct the learned rules (ruling 29) in their own commit, so the phrase test passes on the merged tree.
3. Merge.
4. Build the controller.
5. Deploy with ruling 28's script.
6. Only when deployed:
   - flip each `plan.md` line to `[x]`;
   - close the post-mortem's issues.md lines;
   - close issues.md line 5 ("Civ VI defeat not detected").

---

## Testing

**Unit tests** (pytest; `scripts/ci.sh` must stay green).
- **Fixture.** `tests/fixtures/civ6_kublai_rows.json` holds the Civ VI metrics rows T300-T583, extracted once
  from telemetry. There are no stored snapshots (E7), so snapshot fixtures are synthetic, built from the
  recorded numbers: balances, prices and city flags from the traces' briefing lines.

- **Weakness and caps (1, 2)**, in `test_civ6_governor.py`:
  - These pass: T496 Rockhampton, Modern AT, 1,160 of 1,833 faith; T538 Machine Gun, 1,080 of 1,222; T541
    Jiaodong, 1,160 of 1,961; T553 Taiyuan, Machine Gun, 1,080 of 1,630 gold; T555 Taiyuan, Modern AT, 1,160
    of 1,911 gold.
  - A T465 building purchase is still capped at 50%.
  - A Rock Band under weakness is still capped at 50%.
  - With no clause holding, the old rules apply.
  - An allied major at 7× ours does not count.
  - The E1 counts reproduce from the fixture rows.
  - `test_pillars.py`: the new keys parse, a bad value names its key, and `treasury_share <= 0.5` still
    holds.
- **Pre-stretch buy (3):**
  - The T496 snapshot, before a 3-turn call, gives exactly one faith Modern AT in the top-ranked
    ungarrisoned city, before autoplay starts.
  - No buy when the chunk is 1 turn.
  - No buy when the weakness test is empty.
  - No buy when upkeep would take gold per turn below 0.
  - An empty queue in an ungarrisoned city under weakness gets a defender production order.
- **AI spend (4):**
  - Rows T525 and T528 give 1,998 faith and 1,717 gold (E10), the line, and an urgent decision.
  - Rows T496 and T499 give 1,687 faith.
  - A 30-faith drift gives nothing.
  - The `log-tail` result names UNIT_ROCK_BAND.
- **Lost purchase (5):**
  - A fake tuner times out the first purchase. Gold is unchanged, so there is exactly one re-send, and it
    passes `check_orders`.
  - Gold dropped: no re-send.
  - A read-back failure: no re-send.
  - A second loss: an urgent decision.
  - Last-stand actions are never re-sent.
- **Price change (6):** defender prices 2,320 then 1,160 in one era give the line.
- **Defender list (7):**
  - `test_harness_lua.py`: a Guangzhou-like T563 city lists Modern AT 1,160 allowed, and Infantry either not
    at all or with `why: resource` ("needs 1 Oil").
  - `test_civ6_governor.py`: defence-first engages when a Modern AT is allowed.
  - A city with nothing to buy gets its "no defender can be bought" line.
- **Arithmetic and resources (8):**
  - The limits line at T541 reads 1,961 faith for defenders and 980 for anything else.
  - `test_civ6_strategy.py`: a T496 strategy with `unit:mechanized_infantry` and Oil 0 is sent back with the
    reason. A pinned pillar is exempt.
- **Record (9):**
  - The T512 record text reads "unit purchases: 0 sent" beside "building purchases: …".
  - Old `purchase faith` rows load into the class keys.
  - A cap refusal carries `refusal: cap`.
- **Triggers (10-14):**
  - Falling behind: the counts of E4 reproduce from the fixture.
  - Neighbour buildup:
    - the T478 row fires for Australia (345 → 598 against 295);
    - it does not re-fire within 20 turns;
    - an ally never fires;
    - the E3 count of 18 reproduces;
    - a Stellaris fixture fires once for a non-allied neighbour and never for an `alliance` one.
  - Income: the T291 row fires "gold per turn negative".
  - Loyalty:
    - Haarlem 95 → 77 (T546-T547) fires at T547;
    - it fires once until loyalty rises;
    - Rockhampton's series fires once.
  - Standing danger: the T570-T574 snapshots, with Longxi in danger, no unit and a Modern AT allowed, give a
    decision each hand-back. T576-T582, with nothing buyable, give none.
- **Reviews (15):**
  - A T541 new war after a T538 review runs a review.
  - A T542 "city threatened" is skipped ("within 5 turns").
  - Stellaris keeps 12 months, and its "new war" always reviews.
- **Milestones (17, 18):**
  - `test_strategy.py`: rows T326-T350 with a T342 "military >= 170 by T350" read at_risk at T342-T350 and
    missed at T351. Old rows above the target no longer read met.
  - A milestone with no row since `set` reads at_risk.
  - "milestone missed" fires once.
  - A Stellaris milestone set below a past high reads by today's value.
  - `test_civ6_strategy.py`: the T525 strategy (520 and 580 against a median of 1,106) is sent back. A
    `rank:military` milestone with 2 majors met is sent back.
- **Time constants (19):** both `pillars.toml` files load, and each `[time]` value is asserted.
- **Resilience (20):** a fake model raising 503 three times at a T525 fixture:
  - leads to one retry on the strategy role's models;
  - then a rule-based Machine Gun purchase;
  - with no autoplay started before it.
- **Elimination (21, 22):**
  - A T583 snapshot with 0 cities and 0 settlers read twice ends the run with `campaign_end` "lost", no model
    call, `runs.status = 'lost'` and a journal line.
  - One 0-city read does not end it.
  - `alive = false` ends it at once.
  - A settler alive with 0 cities does not end it.
  - `local_player == -1` alone does not end it.
  - A second run on the campaign ends at start.
  - Stellaris: 2 saves with 0 planets end the run. A missing country raises `needs_attention`.
- **Declarer (24):** a DiplomacySummary fixture where our player declared gives "our AI declared war on
  CIVILIZATION_AUSTRALIA", never "surprise war from Australia". A failed read says "not known".
- **Diplomacy goals (25):** "Get peace with Australia" is sent back.
- **Capture (26):**
  - `test_harness_lua.py`: a GDR-like row counts as a capturer and an Archer-like row does not.
  - `test_civ6_governor.py`: the Beijing T545 city dict gives `about_to_fall` true.
- **Overrun (27):**
  - A fake autoplay returning +29 turns on a 3-turn call emits `turn_overrun`, logs `turns=29 requested=3`,
    and runs the end check.
  - A long prompt is stored whole.
- **Deploy (28):** `pilot-affected.py` classifies:
  - a Stellaris-only diff as not restarting a civ6 pilot;
  - a `governor.py` diff as restarting it;
  - an unknown path as shared;
  - `learned/` as none.
- **Learned (29):**
  - Storing "save gold until the balance is double the unit cost" is refused with its reason.
  - The committed learned files contain no refused phrase.

**Live checks, read-only**, on the loaded Civ VI game, at most 5 tuner queries 3 s or more apart, with the
governor paused:
- one snapshot showing `alive`, `resources`, `allied` and `defence_prices` for every city with its reasons;
- one GameCore query listing `CanCapture` by promotion class (ruling 26);
- one `log-tail` each of `AI_CityBuild.csv` and `DiplomacySummary.csv`.

**After deployment:**
- the first Civ VI decision shows the limits line, the weakness line and the stock;
- the first Stellaris decision's frame shows milestone statuses by today's values;
- the next deploy that touches only one game restarts only that game's pilot.

---

## Out of scope

- **Diplomacy.**
  - Peace and alliance orders through DealManager.
  - The relation fields beyond `allied` (grievances, friendship, agendas).
  - An alliance-expiry trigger.
  - `MAKE_PEACE` answered with accept (L18). No verified evidence says they would have changed this war
    (diplomacy-1 to -6 [one]; peace was illegal before T549).
- **World Congress.** Reading resolutions and their expiry through Lua (L4 beyond ruling 6).
- **Defender placement.** "One Machine Gun per border city" and replacing the AI's production for defenders
  (L15 beyond ruling 3).
- **Chunks.** One-turn chunks on a ratio (L11, ruling 16).
- **Stellaris:**
  - relative milestones;
  - AI-spend lines (T3: the market rules already skip what the AI buys);
  - share-cap scaling at late prices (T4: no binding case seen).
- **GalCiv IV.**
  - Its defeat screen (T6) needs a captured frame first; it will be a `[screens.*]` entry with a stop action,
    never `auto_dismiss`.
  - Its re-send and actor rules (T7, T9).
- **Imports and checks.**
  - A general import of the game's logs into telemetry (L20).
  - Checking learned rules against the episode's price results (L12).
- **Last stand.** Switching it on (L16): it waits for the levers L6 checklist.

## Unverified, in one place

- `GetAllianceType`'s return shape (ruling 1); `GetResources():GetResourceAmount` (ruling 7);
  `CanStartCommand`'s failure-reason table (ruling 7).
- `CanCapture` by promotion class (ruling 26).
- The World Congress session calendar (ruling 6).
- What stops an all-AI game after elimination (ruling 21).
- What Stellaris writes after the player's empire is destroyed, whether it keeps autosaving, and whether any
  living empire can hold 0 planets (ruling 22).

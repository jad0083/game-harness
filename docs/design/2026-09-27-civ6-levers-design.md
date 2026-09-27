# Civilization VI governor, addendum: order record, buy-outs, last stand, and two experiments

Date: 2026-09-27. Status: approved addendum (with the amendments at the end) to `docs/design/2026-09-26-civ6-governor-design.md`. Its rulings
continue that document's numbering (1-10). Base: `main` at 718bed9 (code line numbers from df2a76c).

The three approved changes are (1) an order record per kind, (2) buy-out rules and (3) a scripted last
stand. After them come two experiments: option 4 (mod-steered AI priorities) and option 2 (a placement
planner). Rulings were made in a hands-off run. Anything marked **unverified** has not been observed in
this game build (Civ VI 1.0.12.68, Gathering Storm, mini-rig2).

Sources:
- the live campaign `civ6/kublai_khan_china_702403662`: `runs/20260926-223045` (T41-T85), the scratch
  runs for T12-T41, `games/civ6-kublai/journal.md` and `games/civ6/journal.md`;
- read-only tuner queries at T61-T77 made by the research agents (saved as
  `scratchpad/laststand/q*_out.txt` and `scratchpad/an/q*.lua`);
- PC log copies (kept outside the repo);
- the local copy of the game's XML;
- civ6-mcp at dd20190;
- three adversarial votes on option 4 and two on the tactical API.

Writing this addendum used no tuner queries and no agent file reads.

---

## Evidence

**E1. What happened to the orders, T12-T61 (20 orders).** "Accepted" is today's read-back `stuck`.
The fate comes from the snapshots that followed.

| Kind | n | Completed or held | Overridden by the AI | Other |
|---|---|---|---|---|
| research | 2 | 1 completed | 0 | 1 refused before sending (stale id `tech:writing`, T51) |
| civic | 3 | 3 completed (T27→T38, T38→T45, T52→T55) | 0 | – |
| policies | 1 | held 34 turns (T27-T61); the AI never re-slotted in 5 free windows | 0 | – |
| production, filling an empty queue | 3 | 3 completed (Settler T17, Warrior T51, Archer T52) | 0 | – |
| production, replacing the AI's choice | 6 | 2 completed | **3**: Slinger→Granary (Beijing, T27-31), Slinger→Holy Site (Beijing, T38-41, 1 turn left), Slinger→Trader (Chengdu, T38-41) | 1 invalidated: Slinger obsolete after Archery (T43) |
| production, other | 4 | – | – | 1 lost (tuner timeout, T35); 3 pending at T61 |
| purchase | 1 | executed at once (Warrior, 80 faith, T35: 82→14) | – | – |

- Overrides came 1-3 turns after acceptance. Completions took 1-9 turns.
- There were no overrides after T43 (checked through T61). All three were Slinger orders during
  one-turn autoplay (T27-T41). With n=9 the cause cannot be isolated.
- The orders from T63-T85 have not been analysed.

**E2. The record we have today cannot see outcomes.**
- `_held_report` (`civ6_governor.py` 316-329) says only "no longer current (completed, or changed by
  the AI)".
- It drops purchases and keeps nothing between decisions. `_held` is reset at every `_apply` (439),
  including decisions that give no orders.
- The Civ VI Strategist prompt prints "(no data yet)": `stall_years = 0` (`pillars.toml` 27) and no
  pillar has a directive (`governor.py` 1348-1368, 1434-1435).

**E3. Civic and research blockers were left open.**
- "Civic: none" at T48, T51-T52, T55-T57 and T73.
- At T57 the next autoplay start timed out and a human had to order `civic:state_workforce`
  (issues.md, open).
- At T73 the civics milestone (7 by T72) was missed with "civic in progress: none".
- At T48 and T55 the model wrote that it would choose a civic but returned no order.
- Whether the AI ever picks a civic for us during autoplay is **unverified**. In these windows it did
  not.

**E4. Faith was hoarded, and gold alone was treated as the buying currency.**
- Faith: 38 (T41) → 180 (T61) → 316 (T73) → 402 (T85). It was not spent once after T35.
- Gold: 60 (T41) → 280 (T83), then 120 after the T83 purchase. Net gold per turn was +6 falling to
  +1.4, then −0.6 (T77) and −1.6 (T85).
- Live prices at T61, from the game's own purchase check:

  | Item | Warrior | Archer | Builder | Monument | Settler | Trader |
  |---|---|---|---|---|---|---|
  | gold | 160 | 240 | 215 | 240 | 560 | 195 |
  | faith | 80, allowed | 120, allowed | 105, allowed | 120, allowed | 280, not allowed | 95, not allowed |

- What the model believed:
  - T53: "160 gold is out of reach" (faith 119).
  - T67: "I can't purchase anything with faith unless I have a dedication or a belief" (faith 223).
    It priced only gold (`price` defaults to gold).
  - T83: after Australia declared war and Xi'an was damaged, it bought a Warrior for **160 gold**
    ("Archer is unaffordable while keeping the 60 gold reserve") while holding **388 faith**.
- The corpus lists Warrior, Archer and Monument as `purchase: gold`, yet the game bought a Warrior
  with faith (T35) and allowed faith at T61. The rule that enables this is **unverified**. Valletta's
  suzerain bonus (`Leaders.xml` 2516) would explain the Monument only.
- Conclusion: the currency must come from the game's live check, never from the corpus.

**E5. Stacking.** At T61 the game refused a unit purchase in Chengdu and Xi'an ("Too many units of the
same class in this location"): an Archer already stood on each city tile.

**E6. "Threatened" is nearly always true.**
- 27 of 29 city snapshots from T27 to T61 had ≥1 enemy within 3 tiles; 13 of 29 had ≥2.
- No city was damaged or besieged until T83 (Xi'an, war with Australia).
- So `threatened_share = 1.0` applied almost always, and the one-turn danger chunk
  (`autoplay_turns`) ran almost always.

**E7. Balance milestones rewarded hoarding.** The Strategist set faith ≥80 by T40, ≥200 by T70
(met with 316 at T73). The faith pillar's share of effort sat at 1-2%.

**E8. Pantheon and religion.**
- The pantheon blocker was open from T21 to about T31 with 31-83 faith under one-turn autoplay.
- The AI chose Initiation Rites during a 4-turn call (T31-T35), for 25 faith
  (`RELIGION_PANTHEON_MIN_FAITH` 25, `GlobalParameters.xml` 475).
- The T35 Warrior was bought **after** the pantheon, so a pantheon reserve would not have blocked it.
- At T61: Great Prophet points 0, religions founded 0 of 4.

**E9. Walls.**
- `building:walls`, `castle` and `star_fort` have `purchase: none`.
- A city strikes only with walls (Civilopedia; civ6-mcp `cities.py` 189-199 refuses with NO_WALLS).
- At T61 all 4 cities had walls 0/0. `GetCommandTargets(RANGE_ATTACK)` found 0 targets and
  `GetFirstRangedAttackCity()` was nil, even though 2 barbarians stood next to Beijing (Spearman 31 HP,
  Warrior 100 HP; no unit on Beijing's tile; garrison 200/200).
- `pilot.md` 39-40 and `strategy.md` 110 say "buy … walls at once". That is wrong.

**E10. Tactical API (live presence checks at T61-T63; no request was sent).**
- InGame has `UnitManager.RequestOperation`, `CanStartOperation`, `GetOperationTargets`,
  `GetReachableMovement`; `CityManager.CanStartCommand`, `RequestCommand`, `GetCommandTargets`;
  `CombatManager.SimulateAttackVersus` and `IsAttackChangeWarState`; `UI.RequestAction` and
  `UI.CanEndTurn` (`q2_out.txt`).
- GameCore has `UnitManager.FinishMoves`, `MoveUnit`, `RestoreMovement` and `CombatManager`, but no
  Request or CanStart calls (`q4_out.txt`).
- `UnitOperationTypes` has no HEAL, SKIP_TURN or SLEEP.
- Combat preview: Archer against Spearman, ranged, gave DAMAGE_TO 36. The preview ignores range (it
  computed at distance 4).
- `IsAttackChangeWarState` returned {4} for a peaceful major's Scout, but {} for its Trader and Settler.
- The requests (unit attack, city strike, end turn) are backed only by civ6-mcp, which uses the same
  FireTuner protocol and whose devlogs show ranged kills and city strikes. They are **unverified in
  this build**, where `UI.RequestPlayerOperation(RESEARCH)` was silently ignored.
- civ6-mcp also found three pitfalls:
  - `GetOperationTargets(RANGE_ATTACK)` can return nothing for valid targets (`units.py` 360).
  - A duplicate `ACTION_ENDTURN` skipped turns (`end_turn.py` 1139-1150).
  - InGame queries during AI turns hang the AI (`end_turn.py` 1159-1163).

**E11. Hand-back.**
- Every autoplay call made during our active turn ended that turn with no end-turn request (T9→T12,
  T17→T18, …).
- Open blockers (PANTHEON, COMMEMORATION_AVAILABLE, UNITS) did not stop it.
- QuickCombat and QuickMovement are 0, so animations play.

**E12. Military without micro.** 12 (T41) → 33 (T43) → 99 (T59) → 240 (T82), rank 1 at T85. The AI
itself chose archers in Beijing (T55, T61). No city was damaged before T83 (E6), so ruling 22's HP
clause never held. Its burst clause needs predicted damage of at least the full 200 garrison HP, which
is implausible from two or three Ancient-era attackers (**estimate** from the damage formula). So the
last stand would most likely not have run once before the war.

**E13. Option 4: feasibility and votes.**
- **Finding: partially feasible.** A strategy with a `Call Lua Function` condition, read from a player
  property set through the tuner, switches pre-written AI lists for player 0. There are no continuous
  weights, and purchases are not steerable (SavingTypes lists are bound only to leaders).
- **Vote 1: not refuted (high).** Every citation checked. Live T73 recommendations: HOLY_SITE 729,
  CAMPUS 669, ORACLE 632.
- **Vote 3: not refuted (medium).** Installing needs:
  - an agent reinstall (a new write root), which restarts the tuner relay;
  - a game restart;
  - a reload, which the harness cannot automate for Civ VI.

  It also found that `AffectsSavedGames=0` joining an existing save is **contested**: threads 681526,
  606810 and 669002 against Infixo 631226 and Real Strategy.
- **Vote 2: refuted in part (high), on timing.** In `AI_Victories.csv` (T1-T77), every repeat change of
  the same strategy for the same player (25 cases, all players) is **≥20 turns** apart. Examples:
  player 0 science T11/T36/T56/T76, player 5 T2/T22/T42. The pattern predicted player 0 science
  Stopped at T76 and player 4 exploration at T77, and both happened.
- **Result:** 1 of 3 refuted, so no majority. The design must still treat a strategy as a commitment of
  20 or more turns.

**E14. The AI's intent can be read.**
- `City:GetCityAI():GetBuildRecommendations()` and `GetTechRecommendations()` work read-only in InGame.
- `Logs/AI_Victories.csv` logs player 0's strategies (science victory Following T56, Stopped T76).
- The recommendation scores (~700) are on another scale from `AI_CityBuild.csv` values (~72) (vote 2).
  How well they predict the AI's actual builds is **unverified**.

---

## Rulings

### Shared prerequisite

11. **Snapshot additions, read-only.**
    - **Decision.** `Harness.snapshot` (InGame) gains:
      - **Per city:**
        - `x`, `y`;
        - `buildings`: every building. The loop at `harness.lua` 208-211 already walks them but keeps
          only wonders.
        - `garrison`: the type of our military unit on the city tile, or null;
        - `defense = {garrison_hp, garrison_max, walls_hp, walls_max}`, from the city-centre district's
          `DISTRICT_GARRISON` / `DISTRICT_OUTER`.
      - **Per threatened city only, lists capped at 8:**
        - `enemies`: `[{id, owner, type, kind: melee|ranged|siege|cavalry, x, y, dist, hp}]`. `melee`
          includes anti-cavalry units such as the Spearman, and `melee` and `cavalry` are the kinds
          that can capture a city.
        - `defenders`: `[{id, type, kind, x, y, dist, hp, moves, attacks, range}]`;
        - `can_strike`: whether `GetCommandTargets` has a target;
        - `capture_adjacent`: hostile melee and cavalry units at distance 1;
        - `incoming`: the predicted damage of one attack from each hostile in range. It uses
          `SimulateAttackVersus` under `pcall` (**unverified** with an enemy as the attacker), with the
          fallback `24·e^(0.04·(CS − city defence))` (`GlobalParameters.xml` 132, 202).
        - `defence_prices`: for the cheapest two defenders the city `can_build`, the live gold and faith
          price with the game's `allowed` flag.
      - **Top level:**
        - `religion = {pantheon, can_create_pantheon, pantheon_cost, religion, religions_founded, religions_max, prophet_points, prophet_cost}`,
          under `pcall`, with names from `ReligionScreen.lua` 120-126 and 367;
        - `blockers_all`: every end-turn blocker, not only the first.
      - Python reads every new field with `.get`. `SNAPSHOT_KEYS` (`civ6.rs` 281) is unchanged until a
        live capture refreshes the fixture.
    - **Why.**
      - The record needs `buildings` to tell completed from overridden (E2).
      - The buy-outs need `garrison`, `religion` and both prices (E4, E5, E8).
      - The last stand needs HP, positions and enemies (E9, E10).
      - Limiting the heavy lists to threatened cities keeps the ~2 KB snapshot small.
    - **Cost if wrong.** A slower snapshot reply. A new field that errors is absent, and the rules that
      need it fall back to today's behaviour (each ruling names its fallback).

### Change 1: the order record

12. **Every order is followed until it resolves.**
    - **Decision.** A pure `held_outcome(checked, base, now)` in `civ6.py` classifies an order as one
      of:
      - `completed`:
        - a tech or civic left `options`;
        - a unit's `units.by_type` count rose;
        - a building appeared in `buildings` or left `can_build`;
        - a purchase read back at once.
      - `held`: still current when its window ends.
      - `overridden`: the AI switched while our item was still available. The detail names the
        replacement, e.g. `unit:slinger → building:granary`.
      - `invalidated`: the item became unavailable, e.g. Slinger after Archery. Neutral.
      - `superseded`: our own later order of the same kind, or for the same city. Neutral.
      - `refused`, `lost` or `unknown`: excluded from rates.

      An order's window is `min(20, max(3, turns_left_at_order + 3))` turns, or 20 turns for policies.
      A repeatable project resolves only as held or overridden.
    - **Why.** E1: acceptance is not the outcome. Only 2 of 5 production orders that replaced the AI's
      choice completed, while all 3 that filled an empty queue did. Overrides came within 1-3 turns,
      completions within 1-9, so turns-left + 3 covers both. The cap of 20 bounds the tracking.
    - **Cost if wrong.** A completion misread as an override, for example when a unit is built and lost
      in the same stretch. The by-type count then does not rise, and the order reads as overridden.
      Mitigation: an override also needs `producing` to change *before* the order's `turns_left`
      elapsed. Otherwise the order is `completed?`, which is counted as `unknown`.

13. **Tracked across decisions and persisted.**
    - **Decision.**
      - `self._tracking` replaces the one-shot `_held`. Entries survive decisions that give no orders.
        A new order with the same `(kind, city)` supersedes the older entry.
      - Tracking is updated on every between-turns snapshot (`_run_until_next_decision`, after
        `metrics`), so the record knows the turn of an override.
      - Each resolved order emits `order_outcome` with
        `{kind, key, item_kind, id, city, currency, situation: fill|replace, result, by, turns, date, top3_hit}`.
        `order_outcome` is a new event kind: `orders` is taken by the dashboard's standing orders.
        `top3_hit` belongs to ruling 29.
      - Refused and lost orders emit a row at once.
      - The trace's `orders` items gain `kind`, `id` and `city` (additive).
      - On start, `_set_campaign` reloads the rows through a new read-only
        `telemetry.campaign_events(campaign_id, "order_outcome")`.
      - A one-off backfill from `decisions.trace` recovers only the apply-time outcomes. Held and
        overridden fates before deployment exist only as prose, and are not backfilled.
    - **Why.** The record must survive service restarts: this campaign has already run as five runs
      (four scratch runs for T12-T41, then the live run from T41), and the live run waited about 7
      hours for a human at T57. It must also count what happened while no decision ran.
    - **Cost if wrong.** A stale entry, for example a city renamed or lost. The entry resolves as
      `unknown` when its city is gone.

14. **Stick rate per kind.**
    - **Decision.**
      - **Keys:**
        - `research`, `civic`, `policies`;
        - `production fill`: the queue was empty, or the AI's item had ≤1 turn left;
        - `production replace`;
        - `purchase gold`, `purchase faith`;
        - later `stand city_strike`, `stand ranged`, `stand retreat` (ruling 26);
        - later `posture` (ruling 28).
      - **Rate** = (completed + held) / (completed + held + overridden).
      - **Window:** the last 30 turns, widened back until it holds at least 8 resolved orders of the key
        (or reaches the campaign start).
      - **Minimum samples:** 4 for production and purchase keys, 3 for the others.
        - Below the minimum, the record shows counts without a percentage, e.g. "3 of 3 completed".
        - At or above it, with a rate ≤ 0.5, the key is flagged **"does not stick here"**.
      - Everything is set in `pillars.toml` `[orders]`: `window_turns = 30`, `min_resolved = 8`,
        `min_samples = {production = 4, purchase = 4, other = 3}`, `weak_rate = 0.5`,
        `open_cap_turns = 20`, `open_grace_turns = 3`.
      - Stellaris has no `[orders]` table, and the rule stays off there.
    - **Why.**
      - This campaign gave about 1 production order per 4 turns, so 30 turns hold about 8.
      - The two production situations differ sharply (3/3 against 2/5), so they get separate keys.
        Splitting further by item class would leave every key under its minimum for 50+ turns. The
        class is kept in the rows for later.
    - **Cost if wrong.** A flag raised or cleared on small samples. The flag is advisory (ruling 15),
      and the only rule that acts on production without it is defence (ruling 20). A wrong flag costs
      at most one prompt line.

15. **Where the record goes. No pressure factor, unlike Stellaris ruling 13.**
    - **Decision.**
      - **Decision prompt:** after "What your last orders did", a section "Order record in this
        campaign (held until done / replaced by the AI)" with one line per key. For example:
        `production replace: 5 judged; 2 completed, 3 replaced by the AI (last: unit:slinger → unit:trader in Chengdu, T41) — does not stick here`.
      - **Rebuilt `_held_report`:** it says "completed", "replaced by the AI with X" or "in force".
      - **Strategist:** `governor.py` 1434-1435 calls a hook, `_records_section()`.
        - The base class returns today's heading and `_directive_records_text()`, byte for byte.
        - `Civ6Governor` returns the order record.
        - `pillars.toml` `instructions` gains one sentence: plan levers that stick; where
          `production replace` does not stick, buy what must exist now and queue only into empty
          queues.
      - **Dashboard:** it gets `log.state.info["order_record"]`, and `order_outcome` joins the feed's
        quiet kinds.
    - **Why not pressure.** In Stellaris one directive stands for one pillar, so an ineffective
      directive is an ineffective pillar plan, and damping its pressure is right. In Civ VI the thing
      that fails is a *channel*: queued production gets replaced. The pillar is not wrong. Damping
      military pressure because Slinger orders were replaced would move effort away from defence when
      the right fix is to buy the defender.
    - **Cost if wrong.** The model ignores advisory lines, and orders keep being replaced. Measured by
      the record itself. If `production replace` stays flagged over two Strategist reviews, the next
      step is enforcement: automatic conversion to a purchase, beyond ruling 20's defence case.

16. **A research or civic blocker is always resolved.** This is a companion to change 1 and closes the
    open issues.md item (T55-T57).
    - **Decision.**
      - When the snapshot shows no research or no civic in progress and the answer gives no order for
        it, the governor asks once more (a corrective retry, as for Strategist validation).
      - If it still gets none, it orders the first item in the strategy's preferred list that is in
        `options`, or else the first item in `options`.
      - The trace and the next report say "filled by the governor".
      - Idle turns per kind are counted in the record ("civic idle 9 of the last 30 turns").
    - **Why.**
      - E3: civic was idle at 5 decision points, one of which needed a human, and a milestone was
        missed.
      - E1: research and civic orders held every time (5 of 5 resolved), so filling them is safe.
    - **Cost if wrong.** A choice the model did not make: at worst a suboptimal civic for a few turns.
      That is cheaper than an idle one.

### Change 2: buy-out rules

17. **Danger is `in_danger`, not `threatened`.**
    - **Decision.** A pure `in_danger(city)` in `civ6.py`, true when any of:
      - `under_siege`;
      - `garrison_hp < garrison_max` (damaged);
      - `capture_adjacent ≥ 2`;
      - `enemies_near ≥ 2` and `garrison` is null.

      Without the ruling-11 fields, the fallback is today's rule: `under_siege or damaged or
      enemies_near ≥ 2`, the same test as `urgent_changes` 545-546.

      Users of `in_danger`:
      - `purchase_cap`: `threatened_share` (1.0) applies to in-danger cities only; a merely threatened
        city gets `treasury_share` (0.5);
      - defence first (ruling 19);
      - must-haves (ruling 20).

      `autoplay_turns` is not changed here (see Out of scope).
    - **Why.** E6: "threatened" held in 93% of city snapshots, so today's 1.0 share is effectively
      always on. With the new rule, Beijing at T61 (2 hostile melee units adjacent, no garrison) and
      Haarlem at T51 (3 enemies, empty tile) qualify. A lone scout 3 tiles away does not.
    - **Cost if wrong.** A city in real trouble with a garrison and one attacker gets the 0.5 share.
      Ruling 22's "falling" test and the damaged clause cover the dangerous cases.

18. **Reserves.**
    - **Decision.**

      | Setting | Now | New | Rule |
      |---|---|---|---|
      | `gold_reserve` | 60 | **30**, plus `gold_reserve_per_deficit = 10` per gold per turn of deficit | e.g. 30 at +1.4 gold per turn, 46 at −1.6 |
      | pantheon reserve | none | `pantheon_reserve = true` | While `religion.pantheon` is null and `can_create_pantheon`, the faith reserve is at least the live `pantheon_cost` (25 in this game). Without the `religion` block the rule is off, and the briefing says so. |
      | prophet reserve | none | `prophet_faith_reserve = 0` (off) | While no religion is founded, `religions_founded < religions_max` and prophet points ≥ 50% of the Prophet's cost, keep this much faith. It stays 0 until the patronage-price API is **verified** by one read-only query; no guessed call. |
      | `faith_reserve` (static) | 0 | 0 | Faith has no other use while no Prophet is near (E8: 0 points at T61). |
      | balance milestones | allowed | **not allowed** | `gold` and `faith` balances are no longer valid milestone metrics (`faith_yield` and `gold_yield` stay). A `[metrics] milestone_exclude = ["gold", "faith"]` key; validation names the rule. |

      The urgent trigger "gold below the reserve" uses the new dynamic reserve.
    - **Why.**
      - Net gold was positive every turn until T77, and the one reserve trigger (T37) was not a
        crisis.
      - Even at 30 the reserve would have allowed only the T83 gold purchase; the real money was faith
        (E4).
      - The pantheon blocker sat open about 10 turns (E8). The reserve keeps its price available
        whenever the AI or a later governor action takes it.
      - E7: balance milestones paid the Strategist for hoarding.
    - **Cost if wrong.**
      - A 30-gold reserve lets a deficit eat the treasury faster. The deficit term and the existing
        urgent trigger bound this.
      - A pantheon reserve of 25 faith delays at most one faith purchase by about 4 turns.

19. **Defenders first, faith first.**
    - **Decision.** In `check_orders`, non-purchases keep their order. Purchases are checked in a second
      pass sorted so that *defender for an in-danger city* comes first, where a defender is `unit.json`
      `fields.class` in `defender_classes = ["Melee", "Ranged", "Anti Cavalry", "Light Cavalry", "Heavy Cavalry"]`.
      Outcomes stay in the model's order.

      Then:
      1. **Defence first.** While an in-danger city has no garrison and no defender purchase in this
         decision, any non-defender purchase is refused: "Xi'an is in danger with no defender on its
         tile: buy a defender there first."
      2. **Faith first for defenders.** The governor switches the order to faith, and says so, when all
         of these hold:
         - the order buys a defender with gold;
         - `defence_prices` shows the same unit `allowed` in faith;
         - the faith cap (ruling 18) covers it.

         For other items the choice of currency stays the model's; the briefing shows both prices.
      3. **Stacking.** A land combat unit purchase in a city whose tile already holds our land combat
         unit is refused before sending, as the game would refuse it (E5).
      4. **Cooldown.** At most one defender purchase per city per `defence_cooldown_turns = 5`.
      5. **Known price over the cap.** When `defence_prices` or a `price` result in this decision gives
         the cost, a purchase that costs more than its cap is refused before sending. The message names
         the limit that binds, e.g. "keeps 25 faith for the pantheon". Today such an order goes out and
         `Harness.purchase` refuses it on `max_cost`.

      The briefing lists, for each in-danger city, `defence_prices` and the unit on the tile. The
      `price` tool defaults to showing both currencies.
    - **Why.**
      - E4: faith buys defenders at half the gold price, sat unused from 38 to 402, and the model
        believed faith could not buy units (T67) and bought with gold at T83 while holding 388 faith.
      - E5: stacking refusals are predictable.
      - The cooldown stops one city from draining the treasury over consecutive urgent decisions.
    - **Cost if wrong.** Faith spent on defenders that a later faith use (a Prophet, missionaries,
      faith-bought buildings) would have wanted. The reserves (ruling 18) bound that, and E8 shows no
      competing use at T61.

20. **Never buy what the AI finishes anyway; buy must-haves rather than queue.**
    - **Decision.**
      - **Skip.**
        - A purchase is refused when the city is producing the same item, or a defender of the same
          class, with `turns_left ≤ skip_turns_left = 2`. The message says, e.g., "Beijing finishes
          unit:archer in 1 turn anyway".
        - A building not in `can_build` is refused (when `can_build` is present).
      - **Must-have conversion, narrow.** A `production` order is carried out as a purchase instead,
        within ruling 19's rules, when all of these hold:
        - it is for a defender;
        - it is in an in-danger city with no garrison;
        - the cap covers it;
        - the city's current item is not a defender with ≤ 2 turns left.

        The outcome says "bought instead of queued (in danger)".
      - **Guidance.** When `production replace` is flagged (ruling 14), the frame adds: "The AI
        replaced most production orders that replaced its own choice: buy what must exist now; queue
        only into empty queues."
    - **Why.**
      - Four cases would have finished the next turn anyway (T41, T48, T51, T61).
      - At T51 Haarlem (3 enemies, empty tile, 103 faith) queued a Warrior that arrived 7 turns later;
        a faith Warrior cost 80.
      - Enforcement stays narrow (defence only), because conversion changes what the model asked for.
    - **Cost if wrong.** One purchase the model did not intend: 80-120 faith at today's prices. It is
      reported in the outcome and counted as `purchase faith`.

21. **Walls are produced, never bought.**
    - **Decision.**
      - Fix `pilot.md` 39-40 and `strategy.md` 110: remove "or walls" from the things to buy; walls
        come from production after Masonry.
      - The briefing marks an in-danger city with `walls_max = 0`: "no walls: this city cannot strike".
      - A purchase order for `building:walls`, `castle` or `star_fort` is already refused before
        sending (`purchase = none`).
    - **Why.** E9. The tactical finding's "buy BUILDING_WALLS" is also wrong for the same reason.
    - **Cost if wrong.** None: the text follows the game rule.

### Change 3: the scripted last stand (narrow option 1)

22. **Entry condition.**
    - **Decision.** A pure `about_to_fall(city)` in `civ6.py` over the ruling-11 fields is true when all
      of these hold:
      - `capture_adjacent ≥ 1` (a unit that can take the city is next to it);
      - `walls_hp == 0` (no walls, or walls down);
      - `garrison_hp ≤ 0.5 × garrison_max` **or** `incoming ≥ garrison_hp`.

      The thresholds are module constants with a comment. `urgent_changes` gains "city falling: X" on
      the transition to falling, so the model decides first. Its purchases, under rules 19-20, are
      read back before the stand runs. The stand runs at hand-back turn T when all of these hold:
      - `PILOT_LAST_STAND=1`;
      - a city is falling;
      - that city has had fewer than `last_stand_max = 3` stands in a row.
    - **Why.**
      - Capture needs a melee or cavalry unit adjacent and no walls standing.
      - The HP test and the incoming test catch the two ways a city falls: worn down, or burst.
      - Beijing at T61 (200/200, 2 adjacent) is correctly *not* falling.
      - E12: through T82 no city met this test, so the trigger is rare insurance, not a playstyle.
    - **Cost if wrong.**
      - Too narrow: a city falls without a stand, and the AI's own defence is all it gets (today's
        state).
      - Too wide: turns are spent on scripted actions the AI would also have taken. That is harmless
        but slower (ruling 24 caps it).

23. **Actions, in priority order, one per call.**
    - **Decision.** Each step is two tuner calls:
      1. `Harness.ls_state(city_id)` in **GameCore**: authoritative damage, moves and attacks for our
         units and hostiles within 3.
      2. `Harness.last_stand_step(city_id, damage, skip)` in **InGame**, which requests exactly one
         action or returns `done`.

      The prototype is `scratchpad/laststand/laststand.lua`. It moves into `harness.lua`, installed in
      both states as today. The first legal candidate wins:
      1. **City strike.** Only if `can_strike`, which needs walls. Target: the highest-priority hostile
         among `GetCommandTargets` plots. `CanStartCommand`, then `RequestCommand(RANGE_ATTACK, {PARAM_X, PARAM_Y})`.
      2. **Ranged and siege units** within 3 tiles of the city, with moves > 0 and attacks > 0.
         - **Candidates:** every hostile unit within `u:GetRange()`, plus the `GetOperationTargets`
           plots. The union is used because that list can miss valid targets (E10).
         - **Checks:** each candidate is gated by `CanStartOperation(RANGE_ATTACK, params)` right
           before the request.
         - **Choice:** by target priority plus kill scoring. A sure kill means
           `DAMAGE_TO − 6 ≥ authoritative HP`; the weakest shooter that still kills is preferred.
      3. **Retreat.** A non-garrison unit at ≤ 40% HP, next to a hostile melee or cavalry unit, with
         moves left, goes to the best `GetReachableMovement` plot that is:
         - not adjacent to any hostile;
         - empty of units other than our civilians.

         Plot score: +20 for an empty city centre, −10 per hostile at distance 2, −3 × distance to the
         city, +5 for our territory, +2 for hills. Then `MOVE_TO` with `MoveModifiers.NONE`.
      4. **Pin** (GameCore). `UnitManager.FinishMoves` on each unit the stand moved or that attacked
         with moves still left, so the hand-back's AI cannot walk it back. FinishMoves is present live
         but was never called, so this is **unverified**.

      Target priority (minus hp/10 within a class):
      - 300: melee or cavalry adjacent to the city;
      - 250: siege within 2;
      - 200: other adjacent;
      - 100: distance 2;
      - 50: distance 3.

      Not in this version:
      - melee attacks;
      - fortify and heal (the AI does both during the hand-back turn);
      - attacks on cities or districts;
      - embarking and pillaging.
    - **Why.**
      - This is the approved narrow scope: strike, ranged attacks, retreat of damaged units.
      - One action per call with a GameCore read-back is needed because requests are asynchronous and
        InGame HP lags after combat (E10, civ6-mcp `game_state.py` 334-337).
      - The union of candidates follows vote 2's correction on the tactical finding.
    - **Cost if wrong.** A wasted attack on a unit the AI would have killed anyway (neutral), or a
      retreat to a worse plot than the AI's. Per-incident notes in the journal judge this; the number of
      incidents will be too small for statistics.

24. **Safety limits.**
    - **Decision.**
      - **Budget:** at most 8 actions per stand, 90 s wall-clock, and 1.5 s plus `turn_ready` between
        actions.
      - **Targets:** only hostile units. The owner must be a barbarian (63) or at war with us, **and**
        `IsAttackChangeWarState` must return empty. Civilians are excluded by `FormationClass`, because
        the war check alone misses them (E10).
      - **Reach:** visible plots within 3 of the city only.
      - **Garrison:** never moves.
      - **Stop conditions:**
        - `turn_ready` fails: autoplay active, not our turn, turn already sent, engine busy, or a popup
          or diplomacy screen visible;
        - the turn changed;
        - a read-back shows no effect (ruling 26).
      - **Tuner:** the stand holds it exclusively. It runs outside decisions, so the model's `price`
        tool cannot interleave, and no status polls run until the hand-back.
      - **No resends:** a request whose reply was lost is never sent again.
    - **Why.**
      - E10: the war check misses civilians, popups swallow requests, and moving into ZOC queues a
        request.
      - civ6-mcp saw engine crashes from `CanStartOperation` on remote plots with other operations,
        and hangs from concurrent InGame queries.
      - The 8-action cap covers a city plus 2-4 nearby units with margin.
    - **Cost if wrong.** A stand that stops early leaves the rest to the AI, which is today's behaviour.

25. **Hand-back by one-turn autoplay, not by `ACTION_ENDTURN`.**
    - **Decision.**
      - After the loop, and after `turn_ready` shows the engine idle (≤ 5 s of 1 s polls), the governor
        runs its existing `_play_turns(turn, 1)`.
      - The game's AI plays the rest of turn T: our other units, settlers, builders and every blocker.
        It ends the turn, plays the other civs and hands back at T+1.
      - The approved outline's "autoplay off for that turn" holds for the scripted part: the stand acts
        with autoplay off, and its attacks and pinned moves are final before the AI gets the turn.
      - `UI.RequestAction(ActionTypes.ACTION_ENDTURN)` is **not built** in this version.
    - **Why.**
      - E11: this path ended the turn every time in this campaign, including with open blockers.
      - A manual end turn would need its own blocker clearance (COMMEMORATION, research, pantheon,
        UNITS), idles every other unit for the turn, and has never been sent in this build.
      - civ6-mcp saw duplicate end-turn requests skip turns (E10).
      - Pinning (ruling 23) answers the one drawback: the AI re-ordering units with moves left.
    - **Cost if wrong.** The AI undoes part of a stand (an unpinned unit, or a pin that does not take).
      The stand's read-back at T+1 detects it: a pinned unit moved on T. Then the manual path gets
      built:
      - clear blockers;
      - `GetFirstEndTurnBlocking == NO_ENDTURN_BLOCKING and UI.CanEndTurn()`;
      - `ACTION_ENDTURN` sent once;
      - GameCore-only turn polls.

26. **Calls that are ignored or lost; stand actions in the record.**
    - **Decision.** Each action is classified from the next `ls_state`:
      - `took`: the attacker's attacks or moves dropped, and the target's damage rose or the target is
        gone; or a mover is on its destination; or a pinned unit has 0 moves.
      - `did_not_take`: no change.
      - `unknown`: the reply was lost and the read-back failed.

      On `did_not_take` or `unknown` the stand stops at once, logs why and hands back (ruling 25).
      Nothing is retried.

      Each action emits `order_outcome` with key `stand <action>`, the predicted and the read-back
      result, and a `last_stand` event with the full report (plus a journal line).

      **Circuit breaker:** if the first action of two stands in the same campaign does not take, the
      stand turns itself off for the run. It emits `last_stand_off` with the reason and a journal line,
      and needs no human, because autoplay carries on. A GameCore read-back failure before the first
      action means no action is sent.
    - **Why.** A silently ignored request is the known failure mode in this build (E10: RESEARCH). The
      read-back is the only proof. Two first-action failures are strong evidence that the channel is
      dead and not a one-off popup.
    - **Cost if wrong.** A working stand is switched off after two unlucky popups. It is logged, and a
      human can turn it on again with a restart.

27. **Off by default; first live use only on a throwaway save or in an approved window.**
    - **Decision.**
      - Settings: `PILOT_LAST_STAND=0` by default, and `PILOT_LAST_STAND_MAX=3`.
      - Controller surface:
        - `game-controller civ6 last-stand-step <city-id>`: InGame, one action;
        - `civ6 ls-state <city-id>`: GameCore;
        - `civ6 finish-moves <unit-id>`: GameCore;
        - `civ6 turn-ready`: InGame, read-only.
      - Numeric city ids are used everywhere: the name lookup needs `Locale`, which GameCore lacks.
      - These subcommands stay out of the model-facing `order` JSON (`Civ6Order.kind` and Rust `Order`
        unchanged).
      - The first live run follows a checklist (Testing, L5) on a throwaway save, or in a window the
        user approves, because the current live rules forbid state-changing input.
    - **Why.** Every request type is unverified in this build (E10), and a wrong stand acts on the live
      campaign in wartime (T83-T85, Australia).
    - **Cost if wrong.** A few turns of war without the stand, which is today's behaviour.

### Experiments

28. **Option 4 (mod-steered AI priorities): go for a probe only. Pillar integration is no-go until the
    probe passes.**
    - **Verdict.** Not refuted by a majority: 1 of 3 votes refuted it, and only in part. The probe goes
      ahead with vote 2's timing finding built in. A mod strategy is a commitment of **≥20 turns** at
      Standard speed, in both directions:
      - it starts at the next check only if it has never changed state for this player;
      - once on, it runs at least 20 turns even if the property is cleared;
      - once off, it cannot restart for 20 turns.

      Also unproven (vote 3): whether an `AffectsSavedGames=0` mod joins the existing save.
    - **Probe decisions:**
      - **Window.** Everything that changes state needs one user-approved maintenance window:
        - pause the governor from the dashboard (never stop the service);
        - reinstall the agent with write root `civ6_mods`, allow `Mods/governor_bridge/` only. This
          restarts the tuner relay.
        - `civ6 install-mod` (3 files);
        - restart the game;
        - reload the newest autosave by screen input, or by `Network.LoadGame` through the tuner
          (civ6-mcp `game_lifecycle.py` 413-432, **unverified here**).
      - **Signature aligned with the campaign.** The drafted probe (wonders −100, land combat +300)
        would lock the campaign into a wartime build for 20 turns while gold is already negative with
        11 units. The probe instead favours science: `DISTRICT_CAMPUS` in a Districts list, plus the
        science pseudo-yields. The flip to look for is Beijing's recommendations: at T73 CAMPUS 669
        sat under HOLY_SITE 729. Science is a pillar the current strategy wants, so a 20-turn lock does
        no harm.
      - **Fork and reload.**
        1. Note the newest autosave number.
        2. Run at most 8 one-turn `civ6 autoplay 1` calls from the CLI (the governor is paused, so no
           telemetry rows are written).
        3. Reload that autosave. The game kept 10 autosaves in vote 3's listing (AutoSave_0066..0075),
           so 8 turns stay inside the window.

        The live campaign then continues as if the probe had not run, and the strategy has never
        changed state in that timeline.
      - **Gates, in order:**
        - **G1, load.** Modding.log shows GovBridgeDb and GovBridgeScript applied; Lua.log shows
          "GOVB loaded v1"; a read-only GameCore query finds `GameInfo.Strategies["STRATEGY_GOVB_PROBE"]`.
        - **G2, following.** `AI_Victories.csv` has `STRATEGY_GOVB_PROBE, Following` for player 0
          within 2 turns of setting the property.
        - **G3, effect.** Beijing's CAMPUS recommendation rises above HOLY_SITE, or `AI_CityBuild.csv`
          shows campus choices that were absent at baseline.
        - **G4, isolation.** No other player has a GOVB row.

        Stop latency (expected ≥20 turns) is measured later, in the pillar trial, not in the fork.
    - **Pillar version, only if G1-G4 pass:**
      - **Postures, not directives.** At most two pillars at level 1 at first (science and faith).
      - **When set.** Only at Strategist reviews, never at decisions.
      - **Lock tracking.** The governor tracks each strategy's last state-change turn from
        `AI_Victories.csv` and never changes a property inside a lock. A stale property would flip the
        strategy silently when the lock ends.
      - **Record.** Key `posture`: `stuck` means Following for player 0 within 2 turns of the change,
        or at the lock's end.
      - **Efficacy.** The ruling-13 analogue: the pillar's first-milestone metric growth per turn while
        Following against the rest of the time, with `stall_turns = 20` (the lock) as the minimum
        before judging.
    - **No-go and fallback:**
      - **G1 fails.** The mod does not join saves in this build. Option 4 is parked until a *new*
        campaign starts with the mod enabled, which needs user approval; this campaign is not
        abandoned for it.
      - **G2 or G3 fails.** Option 4 is closed: our slot's strategy lists do not steer.
      - **In every no-go case** the levers are the order record, the buy-outs, ruling 29's read-only
        AI intent, and option 2.
    - **Why.**
      - E13: the channel exists (Firaxis's own `HasFourCities`; Real Strategy), but the 20-turn lock
        and the contested save compatibility make anything beyond a gated probe premature.
      - The fork avoids the lock's harm.
      - Aligning the signature protects the campaign if the reload fails.
    - **Cost if wrong.** One maintenance window (roughly 30-45 min wall-clock, **estimate**) and an
      agent reinstall. If the reload fails, the campaign keeps up to 8 probe turns and a science-leaning
      strategy locked for 20 turns, a direction the Strategist already wants.

29. **The AI's intent, read-only, in the briefing.** This is the part of option 4 that needs no install
    and also serves as its fallback.
    - **Decision.**
      - The snapshot adds, per city, the top 3 of `GetCityAI():GetBuildRecommendations()` (type and
        score; the same call as `ProductionPanel.lua` 638).
      - The governor reads the tail of `Logs/AI_Victories.csv` for player 0 at most once per decision:
        one agent GET with offset, never a bulk read.
      - The briefing shows "The AI's own plan: Beijing → Holy Site, Campus, Oracle; strategies:
        science victory (since T56, stopped T76) …".
      - `order_outcome` rows record `top3_hit`: whether an override's replacement was in the city's top
        3 at order time.
    - **Why.**
      - E14. The one override with a known recommendation fits it: Slinger → Holy Site at T38-41, and
        HOLY_SITE was Beijing's top recommendation at T63 and T73.
      - If the hit rate is high, the model can avoid orders the AI will replace, and the record tests
        exactly that.
      - Vote 2 warns that the scores are on another scale from the AI's build values, so their
        predictive value is **unverified** until the record measures it.
    - **Cost if wrong.** About 100 more bytes per city in the snapshot and one small file read per
      decision. If `top3_hit` stays near chance after 10 overrides, the recommendations leave the
      briefing.

30. **Option 2 (district and wonder placement planner): outline, read-only first.**
    - **Decision.**
      - **Stage A (read-only; allowed under the current live rules, ≤ 5 tuner queries per run).** For
        each city and each district it can produce but has not placed:
        - the valid plots from `CityManager.GetOperationTargets(city, CityOperationTypes.BUILD, {[PARAM_DISTRICT_TYPE] = hash})`
          (civ6-mcp `map.py` 581, **unverified here**);
        - per-plot facts: terrain, feature, resource, improvement, river, hills, coastal, and adjacent
          mountains, districts and wonders.

        A pure Python scorer computes adjacency from structured rules. `scripts/extract-civ6.py` must
        first emit `Adjacency_YieldChanges` and `District_Adjacencies` as data: the corpus has them
        only as prose, e.g. the Campus summary.

        Score = adjacency × the pillar's share of effort
        − lost-tile value (resource 3, improvement 2, feature 1; **initial weights**)
        − a reservation penalty when the plot is the best plot of a higher-share pillar's district.

        The same scorer rates the districts the AI actually placed (the Holy Site in Beijing, about T40,
        and any others). That rating is the baseline.
      - **Go criterion for stage B:** over at least 4 districts the AI placed, our best plot beats the
        AI's plot by ≥ +1 adjacency on average. Otherwise the AI already places well, and option 2
        stops at stage A. Wonders follow only after districts work.
      - **Stage B (orders; needs a throwaway save first).**
        - `production` gains optional `x`, `y` for `district:` and `wonder:` ids.
        - The controller checks that the plot is in the target list and that `CanStartOperation`
          passes, then sends `RequestOperation(BUILD, {PARAM_DISTRICT_TYPE | PARAM_BUILDING_TYPE, PARAM_X, PARAM_Y})`
          (civ6-mcp `cities.py` 428-501).
        - Read-back: the district is listed "(building)" at x,y (the snapshot adds district
          coordinates).
        - One placement per city per decision; never on a luxury or strategic resource.
        - Placed districts join the order record under key `placement`.
    - **Why.**
      - Production orders cannot name an unplaced district or any wonder today (`_check_one`; the
        `pillars.toml` note). So a science pillar that wants a Campus can only wait for the AI.
      - Stage A costs nothing in game state and says whether the lever is worth building.
    - **Cost if wrong.** Stage A: a few read-only queries and the extractor work. Stage B: a district
      placement is permanent, so a bad scorer costs adjacency for the rest of the game. That is why
      stage B goes to a throwaway save first. It is also believed, **unverified**, that a placed district
      keeps its tile when the AI later switches production, which would make placement immune to
      overrides.

---

## Testing

**Unit tests** (pytest, `FakeCiv6`; baseline 40 civ6 tests; `scripts/ci.sh` must stay green):

- **Order record (12-16).**
  - Pure `held_outcome`:
    - research completed (gone from `options.techs`) against overridden (still offered, another
      current);
    - civic, the same;
    - unit completed (by_type +1) against overridden (`producing` changed while still in `can_build`),
      with the detail naming the replacement;
    - building completed (in `buildings`);
    - invalidated (left `can_build` with nothing built);
    - policies changed;
    - purchase completed;
    - `options` None → unknown;
    - superseded by our own order;
    - window expiry → held.
  - Pure `order_record`: counts, rate, the window widening to 8 resolved, minimum samples (counts
    without a percentage below them), the flag at ≤ 0.5.
  - Governor:
    - (a) `ai=` switches Beijing to a Granary. The next prompt contains "production replace … replaced
      by the AI … building:granary", and `events.jsonl` has an `order_outcome`.
    - (b) An `events=` hook completes a tech → "completed".
    - (c) A decision without orders keeps tracking earlier orders.
    - (d) With `Telemetry` (the `test_governor.py` 774-782 pattern), a second run of the campaign
      starts with the cumulative record.
    - (e) The civ6 Strategist prompt contains "Order record".
    - (f) Trace `orders` items carry `kind`.
    - (g) An idle civic with no order → one corrective retry, then the governor fills it from the
      preferred list; the report says "filled by the governor".
  - Stellaris lock: the Stellaris review prompt still contains the exact heading "Directive record in
    this campaign (its pillar's first milestone metric, per in-game year):".
- **Buy-outs (17-21).** Pure `in_danger` and `check_orders`:
  - A lone enemy does not unlock the 1.0 share, but 2 adjacent melee with no garrison do.
  - `turns_left` 1 or 2 on the same item is refused; 3 is allowed.
  - A building not in `can_build` is refused.
  - Pantheon (synthetic; in the real game the pantheon was already chosen at T35): faith 83, no
    pantheon, cost 25, Warrior priced at 80 faith → cap 58 → refused before sending, with the pantheon
    reserve named. With a pantheon, it is allowed. Without a `religion` block, today's behaviour.
  - The dynamic gold reserve at −1.6 gold per turn is 46.
  - Danger city, a Monument listed first and an Archer second: the Archer gets the cap, the Monument
    is refused ("buy a defender there first").
  - A gold defender with faith allowed and affordable → sent as faith, and the outcome says so. Faith
    not allowed → stays gold.
  - Stacking refusal.
  - Cooldown of 5 turns.
  - Must-have conversion: a production Warrior in an in-danger, ungarrisoned city → a purchase.
  - T83 replay from the fixture: gold 280, faith 388, Xi'an damaged, model orders a gold Warrior →
    faith purchase; gold unchanged.
  - Pillars: new keys (`gold_reserve_per_deficit`, `pantheon_reserve`, `prophet_faith_reserve`,
    `skip_turns_left`, `defence_first`, `defender_classes`, `defence_cooldown_turns`, `[orders]`,
    `[metrics] milestone_exclude`) parse. Bad values fail naming the key; unknown keys are still
    rejected; the Stellaris pillars file still loads.
  - A milestone on `faith` fails validation.
- **Last stand (22-27).**
  - Pure `about_to_fall`: each clause; a lone scout and Beijing at T61 (200/200, 2 adjacent) do not
    trigger.
  - `FakeCiv6` gains:
    - `ls_state` (scripted);
    - `last_stand_step` (records `("stand", city, action, self.active)`);
    - `finish_moves`;
    - `turn_ready`;
    - `stand_effect(state)` (damage, kills);
    - `stand_ignored` (no effect);
    - `stand_lost_reply`.
  - Governor:
    - (a) A falling city with `last_stand=True`: the sequence is urgent decision → orders read back →
      steps → pins → `autoplay 1`, with the turn advancing by exactly 1.
    - (b) Default off: the action list is identical to today's.
    - (c) `stand_ignored` → the stand stops after the first action, `order_outcome` says
      `did_not_take`, the hand-back still happens.
    - (d) A second ignored first action → `last_stand_off`, and the next falling turn autoplays only.
    - (e) A lost reply is never resent.
    - (f) After `last_stand_max` stands in a row, autoplay only, with a journal note.
    - (g) The invariant holds for every new call: nothing is sent while autoplay is active (as
      `test_civ6_governor.py` lines 115, 353, 363 and 440 check for orders today).
    - (h) The cap of 8 actions and the 90 s budget stop the loop.
    - (i) A `turn_ready` failure (popup) means no action and a hand-back.
- **Rust.**
  - The new subcommands parse.
  - Numeric city ids are encoded, and a hostile name string is rejected where an id is required (as
    in `civ6.rs` 369-376).
  - `ls-state` and `finish-moves` go to `STATE_CORE`; `last-stand-step` and `turn-ready` go to
    `STATE_UI`.
  - `library_install_is_versioned_and_guarded` still holds.
- **Lua.** The LuaJIT mock (`scratchpad/laststand/mock.lua`, `run_mock*.py`) is kept as a script
  check. It proves syntax and control flow only.

**Live checks:**

- **Read-only, allowed under the current live rules** (≤ 10 tuner queries, ≥ 3 s apart):
  - L1: one snapshot with the ruling-11 fields. Compare with `q1_out.txt` (walls 0/0, garrison
    200/200, Beijing's adjacent units).
  - L2: GetBuildRecommendations top 3 in the snapshot (ruling 29).
  - L3: option 2 stage A on the live cities.
- **Offline:**
  - L4: backfill the record from `runs/telemetry.sqlite` traces and compare it with the E1 table
    (acceptance outcomes only).
- **After a user-approved deployment of the new governor code** (not part of this design; the service
  is not stopped here):
  - L5a: the next decision shows the record rebuilt from events.
  - L5b: the first in-danger decision buys a defender with faith, and it reads back.
  - L5c: no purchase of an item with ≤ 2 turns left.
  - The pantheon reserve cannot be checked in this campaign (pantheon founded), so it is covered by
    unit tests and the next new campaign.
- **State-changing, on a throwaway save or in an approved window only:**
  - **L6, last stand checklist:**
    - the result shapes of `GetCommandTargets` on a walled city and `GetOperationTargets` for an archer
      in range;
    - one ranged attack read back in GameCore (damage visible within the turn);
    - one retreat plus `FinishMoves` (moves 0; the unit stays put through the autoplay hand-back);
    - one city strike after walls;
    - `IsAttackChangeWarState` on a city-state unit;
    - a hand-back after scripted actions ends the turn by itself.
  - **L7:** the option 4 probe gates G1-G4.
  - **L8:** option 2 stage B, one placement.

## Out of scope

- **Melee attacks, fortify and heal micro, and moves onto occupied plots.** The last stand is the
  narrow option 1 only.
- **A manual end turn** (`ACTION_ENDTURN`, blocker clearance). Built only if ruling 25's measurement
  shows the hand-back undoing stands.
- **The governor choosing a pantheon or religion beliefs, and Great Person patronage.** The reserves
  only protect the faith. A pantheon order kind is a candidate after this addendum, because the AI
  left the blocker open about 10 turns (E8).
- **Changing `autoplay_turns` to use `in_danger` instead of `threatened`.** With E6's 93%, one-turn
  chunks ran almost always, which issues.md links to stalled AI plans. This needs its own comparison
  (the open chunk-length issue), because longer chunks delay urgent checks.
- **Tile purchases, unit upgrades, QuickCombat changes, trade, diplomacy, World Congress.**
- **Option 4 pillar integration before the probe passes; option 2 stage B before stage A's go
  criterion; wonder placement before district placement.**
- **MCP tools for the new subcommands** (plan.md keeps the Civ VI MCP item open).

## Rollout

- **Commits, in order:**
  1. ruling 11 (snapshot);
  2. rulings 12-16 (record);
  3. rulings 17-21 (buy-outs, doc fixes);
  4. rulings 22-27 (last stand, off);
  5. ruling 29;
  6. ruling 30 stage A;
  7. ruling 28 (window-gated).

  Each commit goes through `scripts/ci-commit.sh`.
- **`plan.md` gains `[ ]` lines for:** the order record, buy-out rules, last stand, AI-intent briefing,
  option 4 probe and option 2 stage A.
- **`issues.md` gains `[ ]` lines for:**
  - faith unspent T35-T85 and the T83 gold Warrior bought with 388 faith held;
  - the wrong "buy walls" text in `pilot.md` / `strategy.md`;
  - the stick-rate gap: acceptance read back as `stuck` without its fate.

---

## Amendments at review (2026-09-27)

A1. **Autoplay chunks follow `in_danger` (ruling 17), not `threatened`.** Moved into scope from "Out of
    of scope": E6 shows `threatened` held in 93% of city snapshots, so the 3-turn peacetime chunk almost
    never ran, which is the documented cause of stalled AI plans (Settler, pantheon). `autoplay_turns`
    uses `in_danger` (with its fallback), plus war with a major (wars list) as before. Cost if wrong: a
    merely threatened city waits at most 2 more turns for an urgent check; `in_danger` and the
    "city falling" trigger cover the dangerous cases.

A2. **Maintenance windows are approved by the run itself.** The user asked for hands-free operation and
    this campaign is a throwaway test campaign. A state-changing live check (L5-L8, the option 4 probe)
    runs in a window: governor paused from the dashboard (never stopped), autosave noted, fork and
    reload when the game state matters, results in the journal. The last stand still ships off by
    default and is switched on only after the L6 checklist passes.

A3. **Order of work.** Rollout commits 1-6 are implemented and reviewed first; ruling 28 (option 4
    probe) runs afterwards in its own window.

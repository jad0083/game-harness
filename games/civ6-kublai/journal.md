# Journal — Civilization VI governor (throwaway game, Kublai Khan / China)

Goal: the governor of `docs/design/2026-09-26-civ6-governor-design.md`: the game's AI plays our civ
through `AutoplayManager`, the model sets strategy and macro orders between stretches of autoplay.
Game: Civ VI 1.0.12.68, Gathering Storm, Kublai Khan (China), map seed 702403662, on mini-rig2
(agent 1.6.1, tuner relay). A throwaway game: achievements are off once the tuner is used.

## 2026-09-26 — the Lua library, checked live (turns 9-12)

The library is `corpora/civ6/lua/harness.lua`; the controller installs it on first use
(`civ6 snapshot`, `civ6 order`, `civ6 autoplay*`) and again whenever the file changes (its version
is a hash of the text). A second install of the same version returns at once.

**State.** The design put the library in `GameCore_Tuner`; live, GameCore lacks what the snapshot
needs: its `Culture` has no `GetCurrentGovernment`/`GetSlotType`, `Game.GetEras()` only has
`GetCurrentEra` (no era score), `Player:GetStats()` has no `GetMilitaryStrength`, and cities have no
`GetGold()` (purchase prices). The `InGame` state has all of them, plus `AutoplayManager`,
`CityManager` and `UI.RequestPlayerOperation`. So the library lives in **both** states: `InGame`
for the snapshot, production, purchases, prices, policies and autoplay; `GameCore` for research and
civics, because `UI.RequestPlayerOperation(RESEARCH)` sent from the tuner was ignored (research
stayed on Mining) while `GetTechs():SetResearchingTech` in GameCore took at once (and, per the
design's evidence, survives autoplay). The GameCore setters do not check prerequisites, so the
library checks `TechnologyPrereqs`/`CivicPrereqs` itself.

Checklist (each run through `game-controller --corpus corpora/civ6 civ6 …`):

| Function | Call | Result |
|---|---|---|
| install guard | second `snapshot` | no re-install (same version); an edited file re-installs itself |
| `snapshot` | `civ6 snapshot` | one JSON line, 2.2 KB at turn 9 (fixture `crates/game-controller/tests/fixtures/civ6_snapshot.json`) |
| `set_research` | `tech:bronze_working` | refused: "TECH_BRONZE_WORKING needs TECH_MINING first" |
| `set_research` | `tech:mining` (GameCore) | `{"set":"TECH_MINING"}`, read back in the next snapshot |
| `set_research` | `TECH_POTTERY` via InGame UI request | ignored (read-back still Mining) → moved to GameCore |
| `set_civic` | `civic:craftsmanship` | refused: needs Code of Laws first |
| `set_civic` | `civic:code_of_laws` | `{"set":"CIVIC_CODE_OF_LAWS"}` |
| `set_production` | Beijing, `unit:slinger` then `unit:builder` | both requested; read back as the city's `producing` (the builder survived 3 autoplay turns) |
| `set_production` | Beijing, `BUILDING_PYRAMIDS` | refused: wonders need a tile |
| `set_production` | city "Nowhere" | refused: no city of ours named Nowhere |
| `get_purchase_cost` | Beijing, warrior gold / faith; slinger gold | 160 gold / 80 faith / 140 gold, `allowed: false` with 50 gold |
| `purchase` | warrior, `max_cost` 40 | refused before asking the game: costs 160, over the allowed 40 |
| `purchase` | warrior, no cap | the game's `CanStartCommand` refused (not enough gold) |
| `set_policies` | `policy:god_king` at turn 9 | refused: not unlocked (Code of Laws not done) |
| `set_policies` | turn 12, God King + Discipline (already slotted by the AI) | `all already slotted` |
| `set_policies` | turn 12, Survey | refused: "policies are locked until a civic completes (unlocking costs 105 gold)" |
| `autoplay` | 3 turns | turn 9 → 12 in about 12 s; `IsActive()` reads false in the same chunk that set it and true from the next call; control came back at turn 12 |
| `autoplay_status` | polled every 3 s | one poll at the turn change timed out (HTTP) and the next one answered: polls must tolerate a miss |

API names that differed from the expectation: slot types are 0 economic, 1 military, 2 diplomatic,
3 wildcard (as civ6-mcp notes); `GetCurrentGovernment` reads 0 (Chiefdom) with 3 slots at turn 9
(Kublai Khan's extra economic slot); city IDs are large (Beijing 65536), so orders name cities by
name or by that ID; `MapConfiguration.GetValue("RANDOM_SEED")` gives the map seed for the campaign
id; the AI slots policies itself during autoplay (God King, Discipline, Urban Planning at turn 12),
after which changing them costs gold (`GetCostToUnlockPolicies`) until the next civic completes.

Later additions checked live the same day: the snapshot's `options` (at T12: Pottery, Animal
Husbandry, Mining, Sailing, Astrology; Craftsmanship, Foreign Trade; Survey) and each city's
`can_build` (Beijing: Settler, Builder, Scout, Warrior, Slinger, Monument); the library's install
guard (installed twice with one version, a value set between the installs survived); an idle
snapshot takes 0.3 s.

## 2026-09-26 — first governor run (T12 → T17)

`python -m pilot run --game civ6 --episodes 2 --decide-turns 5` with a fast, cheap decision model
(`PILOT_MODEL`), a scratch runs folder and journal, and no commits. Campaign
`civ6/kublai_khan_china_702403662`.

- **Start-of-run review** (36 s): accepted at the first try, milestones on turns. Focus "rapid
  opening expansion to 2 cities while leveraging Chinese 50% boosts and Kublai's economic slots";
  weights expansion 25, science 20, economy 20, military 15, culture 10, faith 5, diplomacy 5;
  expansion cities >= 2 by T40 and >= 3 by T60; preferred techs Mining, Animal Husbandry, Pottery,
  Writing; civics Craftsmanship, Foreign Trade, Early Empire, State Workforce.
- **T12, decision 1** (12 s): no orders — Beijing finishes its Builder next turn and Mining in 3,
  treasury 66 against the 60 reserve. Autoplay 5 turns.
- **Autoplay**: the first poll (T13) answered; the next snapshot, sent while the AI played, timed out
  after 30 s (issues.md) and the stretch ended at T17 (about 40 s for 5 turns). The AI researched
  Mining and chose Animal Husbandry, grew Beijing to 3, and left Beijing with nothing in production.
- **T17, decision 2** (14 s): `production unit:settler in Beijing`, serving "expansion: cities >= 2
  by T40". Read back in a fresh snapshot: stuck (Beijing builds UNIT_SETTLER), confirmed again after
  the run.
- **Exit**: the run stopped after its two decisions; the autoplay-stop sent on exit timed out once
  (autoplay had already ended; the game answered 0.3 s later).

Seen: an autoplay stretch can end with a city building nothing, which the next decision fills; the
tuner does not answer during the AI's turn processing, so mid-stretch urgent stops need polls that
land between turns.

## 2026-09-26 — one-turn autoplay after the code review (T17 → T41)

Same setup (fast, cheap decision model; scratch runs folder and journal; no commits), after the
review fixes: the governor autoplays one turn at a time, polls `autoplay-status` every second, and
reads, checks and orders only between turns.

- **Stuck turn (T17)**: the first one-turn test held T17 for over 10 minutes with autoplay active
  and player 0's turn "complete". A screenshot showed a tutorial advisor popup ("Reconnaissance units
  like Scouts…", OK / Tell me more) waiting for a click. Two clicks on OK (the first as the hover)
  released it. `Harness.autoplay` now sets `UserConfiguration` `TutorialLevel` to -1 for the session
  (the saved options still say 1); no advisor popup since.
- **Per-turn timing** (one turn per call): T18-T21 4.6 s, 6.0 s, 32.8 s (one poll unanswered);
  governor run T21-T25 4.4, 5.8, 4.5, 4.5 s; T25-T27 34 s and 37 s (one poll unanswered each; a
  timed-out poll costs about 20-30 s, so the turn itself is shorter); T27-T31 8.7-10.3 s. A 4-turn
  call (T31-T35) took about 15 s; a 3-turn chunk (T38-T41) 68 s with two unanswered polls.
- **Hand-back side effects**: the library stayed installed in both states across every hand-back
  (no reinstall per turn; versions checked after each turn). The human's popups appear at hand-back
  (Research Completed: Animal Husbandry at T25) and blockers show (ENDTURN_BLOCKING_PANTHEON); they
  did not stop the next autoplay turn. Right after some hand-backs the tuner timed out: the autoplay
  call at T25 (the run waited for Resume; the fix since treats a lost reply as "maybe started" and
  lets the polls decide) and two snapshots at T41 (the third answered).
- **Autoplay's last turn**: with a 3-turn call from T35, autoplay read inactive (turns 0) at T37 while
  the last turn was still to come; the governor decided then. Fixed: an early end now needs the turn
  unchanged for 20 s. The next 3-turn chunk (T38-T41) decided at T41.
- **The AI's behaviour with one-turn toggling looked worse**: T24-T31 the Settler stood unsettled
  for 7 turns, the pantheon blocker stayed open with 59-83 faith, and Beijing's Slinger (our order,
  T27) was replaced by a Granary. One 4-turn call (T31-T35) then settled Chengdu, chose a pantheon and
  used the Builder. Barbarians near Beijing (2 units from T27) may explain the Settler; the pantheon
  and the replaced order point at the hand-back each turn. `PILOT_AUTOPLAY_CHUNK` now sets turns per
  call (default 1); issues.md keeps the comparison open. Military strength fell from 35 (T38) to 12
  (T41) during a chunk.
- **Real policy change (T27)**: Craftsmanship completed at T26 (unlock cost 0); the decision at T27
  ordered Agoge, God King, Urban Planning — Discipline was replaced by Agoge in the military slot and
  read back as stuck. `UNLOCK_POLICIES` then `RequestPolicyChanges`, sent from the tuner, works.
- **Real purchases**: a direct order bought a Scout in Beijing for 120 gold (gold 120 → 0, scouts
  1 → 2); at T35 the governor bought a Warrior with 80 faith (read back as stuck).
- **Orders and read-back**: T27 (urgent "city threatened: Beijing (2 enemy units near)", which also
  started a strategy review that shifted weight to the military): civic Foreign Trade, the policies
  above and a Slinger in Beijing, all stuck. T35: a production order whose reply was lost (tuner
  timeout) was reported "unknown"; the model repeated it at T37 and it was not refused. T37 and T41:
  urgent decisions on gold below the reserve (36 < 60), a missed science milestone and threatened
  cities; Slingers ordered in both cities, stuck.

## 2026-09-27 — a wonder movie stalls autoplay (T134)

- **Stall**: the governor stopped with "T134 did not end within 600 s (14 status polls
  unanswered)". The screen showed "A WORLD WONDER HAS BEEN CREATED!" (our Pyramids): the game's
  `WonderBuiltPopup` locks the engine event (`ExclusivePopupManager:Lock` →
  `UI.ReferenceCurrentEvent()`) until the popup closes, so the AI's turn never finished and the tuner
  stayed silent. Closed by hand (hover + click on the X), then a queue of old Research/Civic
  Completed popups (Animal Husbandry, Pottery, Craftsmanship, Foreign Trade…), which do not lock;
  autoplay had already handed back at T135. Resumed from the dashboard: T137-T138 in ~9 s each.
- **Which popups lock** (read from the game's UI Lua on mini-rig2, GS 1.0.12.68): WonderBuilt
  (`Events.WonderCompleted` → `OnWonderCompleted`), NaturalWonder (`NaturalWonderRevealed`),
  ProjectBuilt (`CityProjectCompletedNarrative` → `OnProjectComplete`), NaturalDisaster
  (`RandomEventStarted`, `RandomEventOccurred`) and RockBandMovie (`PostTourismBomb` →
  `OnRockBandConcert`). GS's EraCompletePopup does not lock by default; tech/civic, boost, era
  review, dedication, World Congress and crisis popups do not use the lock.
- **Each popup is its own tuner state** (`civ6 lua --state WonderBuiltPopup …`); its handlers are
  globals there (`_G` itself is nil). `Events.<Event>.Remove(<handler>)` in each of the five states
  answered `removed true` — the movies are off until the game reloads. The controller must repeat
  this on every library install (a load resets the UI contexts).
- **State at T134**: 6 cities, pop 22, score 186, military 218; gold 0 at +1/turn; faith 358.
  The T134 decision repeated the civic blocker ("civic is None"), asked for Conscription with no
  free military/wildcard slot (refused by the game) and a Trader in Chengdu that did not start.

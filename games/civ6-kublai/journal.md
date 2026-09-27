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

## 2026-09-27 — snapshot defence fields checked live, read-only (T124-T134)

Levers design ruling 11 (`docs/design/2026-09-27-civ6-levers-design.md`), check L1. The live
governor (from `main`) kept playing; every query ran while it was deciding (the game idle between
turns). Five tuner queries in all: the snapshot (guard, install of the branch's library, call) and
two read-only Lua probes. No order, autoplay or state-changing Lua was sent; the live governor
re-installed its own library at its next call.

- **Snapshot at T124** (8.1 KB, answered in about 1 s): every city has `x`/`y` matching the T61
  query (Beijing 22,21, Chengdu 24,16, Haarlem 16,21, Xi'an 26,13), `buildings` (Beijing: Monument,
  Palace, Granary, Shrine; Xi'an: Granary, Walls), `garrison` null in all six cities (no land unit on
  a city tile), `defense` garrison 200/200 everywhere, walls 0/0 except Xi'an 100/100 (walls built
  since T61). No city was threatened, so the per-threat lists did not run. `religion`: pantheon
  Initiation Rites, religion Buddhism, 4 of 4 religions founded, prophet points 34, and a prophet
  cost of 2147483647 (no Prophet left: now read as null). `blockers_all`: RESEARCH and UNITS —
  research was idle at T124 (the gap ruling 16 closes).
- **Probe at T129**: the nearest enemy land unit was an Australian Catapult 4 tiles from Xi'an
  (bombard 35, range 2, promotion class SIEGE); the City Center's `GetDefenseStrength()` is 28;
  `GetComponentID()` works on districts; `GetCommandTargets(RANGE_ATTACK)` on walled Xi'an answers
  (19 plots, 0 targets); Beijing's defenders cost half as much faith as gold (Spearman 260 gold / 130
  faith); `GetRange()` and `GetAttacksRemaining()` answer for our units.
- **Probe at T134** (`SimulateAttackVersus` with an enemy as the attacker, Xi'an as the defender):
  an Archer and a Warrior 4 tiles away previewed 1 damage for every combat type, the Catapult 0
  (`SimulateAttackInto` gave no defender table for it). The preview's `DAMAGE_TO` is the garrison's
  share while walls stand, so a 0 preview now counts only with walls up; without walls it falls back
  to the damage formula.
- **Autoplay start timeouts**: the live run waited for a human four times (T57, T99, T117, T120),
  each time after the autoplay call timed out on the tuner and the polls read inactive; each Resume
  started it at once. The branch sends such a start again, twice, before waiting.
- **Order record backfill (check L4, offline, read-only)**: `scripts/civ6-backfill-orders.py` over
  `runs/telemetry.sqlite` (27 decisions of the live run, T43-T134; the scratch runs for T12-T41 are
  not in it) recovers 15 apply-time outcomes: research refused 2 (tech:writing at T51, as E1 says;
  an empty id at T117), civic refused 2 (an empty id at T90; civic:feudalism read back as "civic is
  None" at T134), lost 1 (T73), unknown 1 (T85), policies refused 1 (T134: no free military or
  wildcard slot), production refused 5 and unknown 1, and two purchases completed (a Warrior for 160
  gold in Xi'an at T83, a Shrine for faith in Beijing at T104). All five production refusals are
  Traders: the read-back found Chengdu still on the Pyramids (T104), Guangzhou on an Entertainment
  Complex (T123), Beijing on a Settler (T129) and Chengdu on nothing (T134); T107 was the repeat
  refused unchanged. For T43-T61 this matches E1 (the T51 refusal); the rest of E1 (the T35 purchase
  and lost order) lies in the scratch runs.

## 2026-09-27 — the AI's own plan and district placement checked live, read-only (T202-T207)

Levers design, checks L2 and L3 (rulings 29 and 30, stage A). The live governor (from `main`) kept
playing; each batch of queries started 2 s after it began deciding (the game idle between turns).
Five tuner queries (the design's budget of 10, with the five above): at T202 an install of the
branch's library in InGame, the snapshot and `district-plots`; at T207 a second install and one
guarded call printing `turn_ready` and the built wonders. One agent file read of
`Logs/AI_Victories.csv`. No order, autoplay or state-changing Lua was sent; the live governor
re-installed its own library at its next call.

- **L2, the AI's top 3 per city (T202)**: every city has `recommend` (the snapshot is 10.3 KB with
  six cities). Beijing: Industrial Zone 2966, Kotoku-in 1898, Theater 1421; Chengdu: Industrial
  Zone 2139, Campus 1868, Holy Site 1814; Haarlem: Aqueduct 1247, Forbidden City 696, Museum
  (artifact) 606; Jiaodong: Campus 4833 (the district it is building), Industrial Zone 1586,
  Aqueduct 1515; Guangzhou: Entertainment Complex 2618 (being built), Industrial Zone 2309, Campus
  1490; Taiyuan: Holy Site 2516 (being built), Theater 1227, Campus 1201. Scores now run 600-4800
  (about 700 at T73). Most top items are districts not yet placed, which production orders cannot
  name.
- **L2, the AI's strategy log**: one read of 13,127 bytes (T1-T202), 21 rows for player 0. The
  briefing line at T202: "The AI's own plan: Beijing → district:industrial_zone, wonder:kotoku_in,
  district:theater; … Taiyuan → district:holy_site, district:theater, district:campus; strategies:
  religious victory (since T6), darkage (since T177), naval (since T115), rapid expansion (since
  T167, stopped T177), renaissance changes (since T192)." Science victory followed T11-T36, T56-T76
  and T136-T156. Rapid expansion started at T167 and stopped at T177: 10 turns, a counter-example to
  vote 2's "every repeat change is 20 or more turns apart" (T1-T77); the option 4 probe should not
  rely on a fixed 20-turn lock for every strategy. The era strategies keep "Following" once started,
  so the briefing now shows only the latest.
- **L3, district plots (T202)**: `district-plots` answered 27 KB in 0.4 s: 216 plots, each city's 37
  plots within 3 tiles, and `GetOperationTargets(BUILD)` lists for 9-10 districts per city (Beijing
  13 plots for most, Taiyuan 4, Haarlem none except one plot for an Aqueduct). A wonder stands on a
  `DISTRICT_WONDER` plot, and the plot names its wonder while it is still being built (Mahabodhi
  Temple in Beijing, Great Bath in Chengdu): the scorer now counts a wonder only once built (the
  reply's `built` list, read live at T207: Pyramids) and never as a district.
- **L3, scored** with the campaign's T171 weights (science 30, military 25, economy 15, culture 10,
  faith 10, expansion 5, diplomacy 5): best plots such as Taiyuan's Harbor at 28,18 (+4 gold),
  Jiaodong's Commercial Hub at 21,26 (+4 gold) and Guangzhou's Theater at 20,19 (+3 culture). The
  AI's seven specialty districts against the free plots each city is offered now: Beijing Holy Site
  0 (+2 at 23,20), Beijing Campus 3 (best), Chengdu Theater 0 (+2 at 24,17, next to the Pyramids),
  Haarlem Campus 2 and Theater 1 (best of what is left), Jiaodong Campus 3 (best), Taiyuan Holy
  Site 0 (+1 at 26,17): a mean gain of **+0.71, so no-go** for stage B under the design's criterion
  (+1 over at least 4 districts). Counting the two unfinished wonders gave +1.14 (go), so the margin
  is thin. Caveats: alternatives are today's free plots, not those free when the AI placed; rules
  that need a tech or civic are left out; resources are read without our visibility check.
- **`turn_ready` at T207** (read-only): every check answered (no "cannot check"), and it reported
  not ready, "on screen: HistoricMoments", while the governor was deciding between turns. Either a
  Historic Moments screen was up at the hand-back or that context reads as shown when it is not; the
  stand fails closed on it (no action, only the hand-back). To settle before the L6 checklist
  (issues.md).

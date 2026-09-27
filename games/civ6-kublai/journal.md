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

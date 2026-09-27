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

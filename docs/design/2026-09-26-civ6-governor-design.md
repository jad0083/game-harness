# Civilization VI governor: the game's AI plays, the model steers

Date: 2026-09-26. Status: approved direction ("A + 3": tuner snapshot + governor over the game's
own AI; test the other options along the way). Rulings below were made in a hands-off run.

## Evidence (live on mini-rig2, Civ VI 1.0.12.68, Gathering Storm, 2026-09-26)

- The tuner relay (agent 1.6.1, `game-controller civ6 lua`) runs Lua in `GameCore_Tuner`; results
  come back only through `print()`.
- `AutoplayManager` (GameCore and InGame states) let the game's AI play our civ for 5 turns in
  ~20 s: it founded the capital, chose research, then handed control back
  (`SetReturnAsPlayer(0)`, `SetObserveAsPlayer(0)`, `SetTurns(n)`, `SetActive(true)`).
- A research choice set through GameCore (`Players[0]:GetTechs():SetResearchingTech`) survived 3
  autoplay turns.
- GameCore reads work for science, culture, faith, gold yields, score, cities, population,
  production and the current civic; military strength, era score, the build queue's current item
  and government need the API names civ6-mcp uses (MIT, port its Lua).

## Rulings

1. **Shape.** The Stellaris governor pattern: the game's AI plays (units, tiles, city micro,
   routine choices) through `AutoplayManager`; the model sets a standing strategy (pillars in
   **share** mode) and macro orders between stretches of autoplay. No screenshots once a game is
   loaded.
2. **Reads: one snapshot per decision.** A Lua helper library (`corpora/civ6/lua/harness.lua`) is
   installed into `GameCore_Tuner` on connect (idempotent; re-installed if missing) and exposes
   `Harness.snapshot()`, which prints one compact JSON document: turn, era, our civ and leader,
   yields per turn, treasury and faith, cities (name, pop, production item and turns left,
   districts, threatened), research and civic in progress with turns left, government and slotted
   policies, units by class, known majors with score and military strength, wars, and the end-turn
   blocker if any. JSON is built in Lua (small encoder in the library).
3. **Orders are structured, never raw Lua from the model.** The model returns orders with corpus
   ids (`tech:…`, `civic:…`, `policy:…`, `unit:…`/`building:…`/`district:…`, purchases); the
   controller validates them against `corpora/civ6/data` and turns each into a template call
   (`Harness.set_research(id)`, `set_civic`, `set_policies`, `set_production(city, item)`,
   `purchase(city, item, "gold"|"faith")`). Each is **read back** in the next snapshot; one that did
   not stick is reported to the model and not retried blindly.
4. **Loop.** snapshot → decide (only at decision points) → apply orders → read back → autoplay
   `PILOT_DECIDE_TURNS` (default 5) turns → snapshot. Autoplay is stopped early
   (`SetActive(false)`) when a poll (every turn) shows an urgent change: war declared on us, a city
   lost or besieged, a new era, a Great Person or wonder race lost, gold below the reserve.
5. **Strategy layer.** `corpora/civ6/pillars.toml` in share mode: science, culture, faith, economy,
   military, expansion, diplomacy; metrics from the snapshot (yields, cities, population, techs and
   civics known, military strength, score, era score, ranks among the majors). Actions: `tech`,
   `civic`, `policy`, `production`, `purchase` (the last with a gold/faith reserve and a treasury
   share cap from `pillars.toml`, and "buy at once for a threatened city").
6. **Buy-outs.** Prices are read live (`city:GetGold():GetPurchaseCost` / faith equivalent through the
   library), never from a formula; a purchase is valid when affordable after the reserve.
7. **Campaign identity.** `civ6/<leader>_<map seed>`; telemetry, dashboard and decisions reuse the
   pilot's (metrics rows from the snapshot).
8. **Controller surface.** `game-controller civ6 snapshot` (JSON), `civ6 order <json>`,
   `civ6 autoplay <turns>`, `civ6 autoplay-stop`; MCP tools later. The pilot talks to the controller
   like it does for Stellaris.
9. **Tests.** A `FakeCiv6` (scripted snapshots, recorded orders, autoplay that advances turns) for the
   governor loop; Lua library functions tested live once (a checklist in the journal), and the JSON
   they print parsed against a committed fixture.
10. **Out of scope now:** unit-level tactics, trade deals and World Congress votes (the AI handles them
    during autoplay), multi-host, and the other options (full control, mod-steered AI), which are tried
    as experiments and recorded in `games/civ6-*/journal.md`.

## Risks

- The AI may override our production or policies during autoplay (research held): measured by the
  read-back, and the governor then re-applies at the next decision point only.
- Autoplay may skip decisions the AI makes poorly (district placement, purchases): the purchase action
  and a later placement planner (option 2) cover them.
- The tuner is a debug feature: achievements are off for these games (throwaway campaigns only).

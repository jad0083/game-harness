# Civilization VI playbook (Gathering Storm rules, game 1.0.12.68)

A first playbook for a model playing Civilization VI through this harness. Numbers come from the
generated records (`corpus get <id>`, built from the game's own files by `scripts/extract-civ6.py`);
advice comes from the sources named in each section. When a doc or guide disagrees with a record,
the record wins. Nothing here has been verified in play yet: treat each rule as a starting point
and record what play teaches (`learned/`, `issues.md`).

Sources used: the records in `data/`; `docs/agent_playbook_civ6mcp.md` (civ6-mcp, MIT);
`docs/civbench_lessons.md` (CivBench, CC BY 4.0); the Civilization Wiki docs (`docs/*.md`,
CC BY-SA 3.0); CivFanatics threads listed in `docs/links.md` (paraphrased, not copied).

## 1. Every turn and every few turns

- You only know what you query. Before ending a turn, clear every blocker the game shows: unit
  orders, empty production, research or civic choice, governor title, promotion, policy slot,
  pantheon or religion, envoys, dedication (civ6-mcp "End Turn Blockers").
- Every ~10 turns: unimproved luxuries and strategics, idle trade routes, unspent gold or faith,
  city count against the benchmarks below, a newly unlocked government tier, era score against the
  thresholds, great people candidates (civ6-mcp "Strategic Checkpoints").
- Every ~20 turns: diplomacy (delegations, friendships, alliances), **all six victory types for
  every rival**, and religion spread. CivBench found agents rarely checked victory progress even
  when told to, and often did not carry out their own plans within ten turns: turn each plan into
  orders the same turn (`docs/civbench_lessons.md`).

## 2. Opening (turns 1–40)

- **Settle at once** unless the start tile is clearly poor; a river, coast or hills and food and
  production tiles in the first ring matter more than a perfect spot. A city cannot be founded
  within 3 tiles of another (`GlobalParameters CITY_MIN_RANGE 3`).
- **Build order** (CivFanatics "Deity build order", paraphrased): scouts first for huts, city-states
  and settle sites, then a Warrior or Slinger for barbarians, then Builder and Settlers. Costs:
  `unit:scout` 30, `unit:warrior` 40, `unit:slinger` 35, `unit:builder` 50 (+4 per earlier
  Builder, 3 charges), `unit:settler` 80 (+30 per earlier Settler, costs 1 population).
- **Expansion benchmarks** (CivBench A.6): 2 cities by turn 40, 3 by 60, 4 by 80, 4–5 by 100. When
  behind, a Settler is usually the best production choice. Exploration: 15% of land by turn 25,
  25% by 50, 35% by 75, 50% by 100.
- **First civics**: Code of Laws opens the first policies: `policy:god_king` (+1 Faith, +1 Gold in
  the capital) or `policy:urban_planning` (+1 Production in all cities), with `policy:discipline`
  (+5 vs barbarians) or `policy:survey`. Craftsmanship gives `policy:ilkum` (+30% toward Builders)
  and `policy:agoge` (+50% toward Ancient and Classical melee, anti-cavalry and ranged units);
  Early Empire gives `policy:colonization` (+50% toward Settlers). Swapping cards is free when a
  civic completes, so re-slot for the current build every time.
- **Eurekas and inspirations** give 40% of a tech or civic (`fields.eureka` on each `tech:`
  record, `fields.inspiration` on `civic:`). Prefer the next tech whose eureka you can trigger soon;
  `tech:writing` (Eureka: meet another civilization) unlocks the Campus.
- **First government**: Political Philosophy offers `government:classical_republic` (2 Economic,
  1 Diplomatic, 1 Wildcard; +1 Housing and +1 Amenity in cities with a district) for a builder
  game, or `government:oligarchy` (2 Military, 1 Economic, 1 Wildcard; +4 strength for melee,
  anti-cavalry and naval melee) for an early war. Each new government tier is free to adopt the
  first time (civ6-mcp).

## 3. Districts and adjacency (Gathering Storm)

- A city can hold one more specialty district per 3 population (`DISTRICT_POPULATION_REQUIRED_PER
  3`; see `doc:districts`). District costs rise as you complete techs and civics, and a district
  you have fewer of than the average civilization is cheaper (`fields.cost_progression`; about 40%
  less per the CivFanatics District Discounts resource). Place early: the cost is fixed when placed.
- Adjacency from the records (`corpus get district:<id>` has the full list; minor bonuses are
  counted per source and rounded down):

| District | Adjacency |
|---|---|
| Campus | +1 per Mountain; +2 per Reef, Geothermal Fissure, Great Barrier Reef or Pamukkale; +1 per 2 Rainforest; +1 per 2 districts; +1 per Government Plaza |
| Holy Site | +2 per natural wonder; +1 per Mountain or Pamukkale; +1 per 2 Woods; +1 per 2 districts; +1 per Government Plaza |
| Commercial Hub | +2 for a River or an adjacent Harbor (or Royal Navy Dockyard, Cothon) or Pamukkale; +1 per 2 districts; +1 per Government Plaza |
| Harbor | +2 per adjacent City Center; +1 per sea resource; +1 per 2 districts; +1 per Government Plaza |
| Industrial Zone | +2 per Aqueduct, Bath, Canal or Dam; +1 per Quarry or strategic resource; +1 per 2 Mines; +1 per 2 Lumber Mills; +1 per 2 districts; +1 per Government Plaza |
| Theater Square | +2 per wonder, Entertainment Complex or Water Park (and their unique replacements) or Pamukkale; +1 per 2 districts; +1 per Government Plaza |

- Placement rules of thumb: cluster districts so each gets the +1 per 2 districts; put the
  Government Plaza (`district:government`, +1 to every adjacent district, +8 Loyalty, a Governor
  title) where three or more specialty districts can touch it; Commercial Hub on a river next to a
  Harbor; Industrial Zone next to an Aqueduct or Dam. `policy:natural_philosophy` doubles Campus
  adjacency, so plan Campuses with +3 or more.
- An Encampment and a Preserve cannot be placed next to the City Center.

## 4. Victory paths

Name one primary victory early and keep a second option; check every rival's progress on all six.

- **Science** (`victory:technology`): Campuses with Library, University and Research Lab, then a
  Spaceport. Projects: `project:launch_earth_satellite` (900), `project:launch_moon_landing`
  (1500), `project:launch_mars_base` (Mars Colony, 1800), `project:launch_exoplanet_expedition`
  (2100); the expedition then travels to its destination, and `project:orbital_laser` /
  `project:terrestrial_laser` (600 each) speed it up. Build Spaceports in two or three high
  production cities (`doc:victory`).
- **Culture** (`victory:culture`): your visiting tourists must exceed every rival's domestic
  tourists. Theater Squares and Great Works, wonders, then National Parks, Seaside Resorts and
  Rock Bands; open borders and trade routes add tourism (civ6-mcp).
- **Religious** (`victory:religious`): found a religion early (the Great Prophet pool fills
  early), build Holy Sites, then Missionaries and Apostles bought with faith from cities where
  your religion is the majority (civ6-mcp).
- **Diplomatic** (`victory:diplomatic`): 20 Diplomatic Victory Points
  (`DIPLOMATIC_VICTORY_POINTS_REQUIRED 20`) from World Congress resolutions, competitions and some
  wonders and techs. Favor comes from government tier, alliances and suzerainties. One vote per
  resolution is free; extra votes cost 6/18/36/60/90/126 favor in total (civ6-mcp).
- **Domination** (`victory:conquest`): hold every rival's original capital.
- **Score** (`victory:score`): the fallback at the turn limit.

## 5. Buying with gold and faith

Buying is how idle gold and faith become tempo. Rules (plan.md buy-out rule; civ6-mcp and
CivBench A.6):

- Spend when the turns saved times the item's value beats the other uses of the gold or faith
  (tile purchases for districts and luxuries, unit upgrades, great person patronage). Gold above
  about 500 with no named purchase is usually better spent (CivBench A.6).
- Keep a small gold reserve (30, more with a deficit) and, until a pantheon is founded, its faith
  price; one purchase at most half the balance unless a city is in danger (enemies next to it that
  can take it, a damaged garrison, or enemies near an empty tile), in which case buy a defender
  there at once, with faith when the game allows it (about half the gold price). Walls cannot be
  bought: they come from production after Masonry, and only a city with walls can strike.
- Faith is a currency, not a score: in the Kublai campaign it sat unspent from 38 to 402 while a
  Warrior was bought with 160 gold. Balances are never milestones; faith and gold per turn are.
- Never buy what finishes in 2 turns or less. Always read the **live** price in the game; never
  compute it from the corpus (the purchase formula uses `GOLD_PURCHASE_MULTIPLIER 2` and
  `PURCHASE_DIVISOR 5`, but the exact formula is unverified).
- What can be bought: units and buildings with `fields.purchase = gold` or `faith` (worship
  buildings and religious units use faith; `fields.must_purchase` units cannot be built).
  Districts and wonders cannot be bought. Tiles cost gold (`PLOT_BUY_BASE_COST 50`;
  `policy:land_surveyors` makes them 20% cheaper). Great people can be patronised with gold or
  faith.
- Faith buys beyond religion: the `dedication:infrastructure` (Monumentality) Golden Age lets you
  buy civilian units, including Settlers and Builders, with faith; `building:gov_faith` (Grand
  Master's Chapel) lets you buy land units with faith; `belief:jesuit_education` buys Campus and
  Theater Square buildings with faith; Theocracy's legacy bonus is 15% off faith purchases.

## 6. Diplomacy, loyalty and war

- Send a delegation (25 gold) on first meeting, declare friendship with Friendly civilizations, and
  form alliances once Diplomatic Service is known (civ6-mcp). Historical agendas are always
  visible (`agenda:` records, `leader:<id>` field `agenda`); avoid what the neighbour dislikes.
- AI war declarations follow proximity first, then military ratio and undefended fronts
  (CivFanatics "any logic behind an AI DoW", paraphrased). A neighbour at twice your strength who
  is not a friend is a real risk: keep one garrison per city and a mobile unit, and upgrade units.
- Loyalty: new cities near a rival's large cities lose loyalty; settle closer to your own
  population or send a Governor at once (`doc:loyalty`, `governor:` records).
- Clear barbarian camps within a few turns of finding them; camps upgrade with the era (civ6-mcp).
- Emergencies (`emergency:` records) and World Congress resolutions (`resolution:` records) list
  both options and rewards; vote with the option that blocks the rival nearest to a victory.

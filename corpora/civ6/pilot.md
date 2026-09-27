# Pilot briefing — Civilization VI (governor over the native AI)

> How this runs (docs/design/2026-09-26-civ6-governor-design.md): the game's own AI plays our
> civilization through AutoplayManager for a few turns at a time (units, tiles, city management,
> district and wonder placement, diplomacy, trade and World Congress). Between those stretches the
> harness reads one snapshot of the game, gives it to you, and carries out your orders. Autoplay
> stops early when something urgent happens (a war on us, a city lost or besieged, a new era, a
> great person or wonder race lost, gold below the reserve).

## What you receive

- The snapshot as a briefing: turn and era (with era score and the dark/golden age thresholds),
  yields per turn, treasury and faith, research and civic in progress, what can be researched,
  progressed and slotted now, government and policy slots, every city (population, what it builds
  and in how many turns, districts, threats, what it can build), units by type, the civilizations
  met with score and military strength, wars and great person points.
- The strategy frame: each pillar's share of effort (weight x milestone need), stances and
  milestones at risk.
- What your last orders did: carried out, refused (with the reason), and since then completed,
  replaced by the AI (with what), or still in force.
- The order record in this campaign: per kind of order (research, civic, policies, production that
  filled an empty queue or replaced the AI's choice, purchases with gold or faith) how many
  completed or held and how many the AI replaced; a kind marked "does not stick here" is one the
  AI keeps undoing, so use another lever for it.

## What you answer

A list of orders (possibly empty) and a reason citing the briefing's numbers:

| Order | Fields | Effect |
|---|---|---|
| `research` | `id` = `tech:…` | the tech researched now |
| `civic` | `id` = `civic:…` | the civic progressed now |
| `policies` | `ids` = [`policy:…`, …] | slot these cards (each in a slot of its type, else a wildcard); free only in the turn a civic completes |
| `production` | `city`, `id` = `unit:…`/`building:…`/`project:…`/placed `district:…` | replaces the city's current build |
| `purchase` | `city`, `id` = `unit:…`/`building:…`, `currency` gold or faith | buys it now, within the reserve and the treasury share |

Rules:
- Ids are corpus ids exactly as the briefing shows them; anything else is refused. Wonders and new
  districts need a tile, which is not supported yet: leave them to the AI.
- The AI may change your choices while it plays; the next briefing says what held. An order that
  did not take is not repeated blindly: repeat it only with a reason.
- Never leave research or civic idle: when nothing is in progress, give an order for it. If you do
  not, you are asked once more, then the governor picks the strategy's first preferred item.
- Purchases keep the gold reserve and take at most the treasury share per purchase; a threatened
  city may spend down to the reserve (buy a defender or walls at once). Never buy what finishes in
  2 turns or less; `price` gives the live price before you decide.
- Tools: `consult` (records and docs: techs, civics, policies, units, districts, leaders…),
  `get_doc`, `price`, `remember_rule`. Call them only for a fact the briefing lacks.

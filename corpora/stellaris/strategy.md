# Stellaris — Strategic Playbook (governor over the native AI)

**Target game version**: 4.5.1 "Cygnus" (verified on the user's PC, 2026-09-25).
**DLC present on the PC**: Plantoids, Leviathans, Horizon Signal, Utopia, Synthetic Dawn,
Apocalypse, Humanoids, MegaCorp, Ancient Relics, Lithoids, Federations, Necroids, Nemesis.
Not present (so ignore advice that needs them): Overlord (subject specialisations, holdings),
The Machine Age (Cosmogenesis, machine ascension paths), Grand Archive, First Contact, Toxoids,
Galactic Paragons, Astral Planes, Biogenesis and later.
**Role**: the playbook the governor model reads before choosing a directive. Every rule cites
the doc it comes from (`doc:<file>` in `docs/`, searchable with `corpus search` / `corpus get`).

Version caution: the wiki pages were last verified for 4.2–4.4 (some sections 3.x; each doc's
first line says which). 4.5 changed pop groups and factions (in-game welcome screen), so treat
pop/faction numbers as approximate until generated data exists.

---

## 1. Opening (first ~10 years)

- **Before unpausing**: review policies and pick research that serves the opening goals; most
  policies need no change yet. [doc:beginners_guide_early_game]
- **Starting assets** (regular empire): homeworld with 100% habitability, a level-2 starbase
  with shipyard, three corvettes, one construction ship, one science ship, four scientists,
  and 100 energy / 100 minerals / 200 food / 100 consumer goods / 100 alloys / 100 influence.
  Origins, ethics and civics change this; gestalts and lithoids differ. [doc:beginners_guide_early_game]
- **Explore first**: only the home system starts surveyed. Building a 2nd–3rd science ship
  speeds exploration, but every scientist costs unity and delays traditions. Don't put the
  first science ship on auto-survey, and skip high-level anomalies / dig sites early — they
  stall critical surveying. [doc:beginners_guide_early_game]
- **Chokepoints vs. adjacency**: surveying outward system by system lets the construction
  ship follow cheaply; racing to chokepoints blocks rivals but outposts beyond the border cost
  more influence. [doc:beginners_guide_early_game]
- **Outpost priority**: colonisable systems (good habitability for the main species) and
  systems with several valuable deposits first; then chokepoints and links to valuable
  systems; interior dead-ends last. [doc:beginners_guide_early_game]
- **Deposit value order**: research > strategic resources (need their techs) > alloys >
  energy / minerals; check the system view — one 6-mineral deposit beats three 2s for
  energy upkeep. [doc:beginners_guide_early_game]
- **Second construction ship** after about 3–5 outposts: one builds outposts, the other
  mining/research stations. [doc:beginners_guide_early_game]
- **Open borders caveat**: an AI with open borders can build outposts behind your systems
  (up to two jumps from its own); close borders or claim those systems. [doc:beginners_guide_early_game]

## 2. Economy priorities

- **Early resource order**: minerals (districts, buildings, stations) > energy (upkeep and
  market) > alloys, research, unity > food and consumer goods (mostly upkeep). [doc:beginners_guide_early_game]
- **Housing and amenities** keep pops happy; unhappy pops raise crime and lower stability.
  City districts give housing, a building slot and clerk jobs. [doc:beginners_guide_early_game]
- **Specialise later**: on the homeworld cover immediate needs first; planet specialisation
  pays off once there are several colonies (stacked job-output bonuses). [doc:beginners_guide_early_game]
- **Economic Policy**: Civilian (+25% consumer goods / −25% alloys from jobs), Mixed (none),
  Militarized (−25% consumer goods / +25% alloys). A changed policy is locked for **10 years**
  — directives must not flip policies casually. [doc:policies]
- **Edicts** cost resources scaled by empire size (+1% per point) and have upkeep; unity
  edicts use the Edict Fund. Useful ones: Map the Stars (Discovery tree; +25% survey speed),
  Fortify the Border (+50% starbase upgrade speed, +2 starbase capacity), Mining/Farming/
  Capacity Subsidies (+50% miner/farmer/technician output for energy upkeep), Fleet
  Supremacy, Diplomatic Grants (Diplomacy tree; +1 envoy, +10% diplomatic weight). [doc:edicts]
- **Fleet economy**: ships cost alloys to build and have ongoing upkeep; advanced parts also
  need strategic resources. Naval capacity is a soft cap — exceeding it raises upkeep. [doc:beginners_guide_late_game]

## 3. Expansion and colonisation

- **Colony ships** take a year to build and cost 200 each of alloys, food and consumer goods
  (regular empires); establishing takes about three years, longer with more total pops. [doc:beginners_guide_early_game]
- **Colonise high habitability first** — low habitability raises pop upkeep. By default the
  galaxy places 2 habitable planets of the homeworld's type (base 80%) near the capital.
  Bigger planets hold more districts; planetary features decide resource districts. [doc:beginners_guide_early_game]
- **Grow new colonies**: a colony starts at 100 pops and needs 1,000 to upgrade its capital
  building (then 2,500 and 5,000). Speed-ups: Nutritional Plenitude edict, resettlement,
  unemployed pops moving to open jobs, and building robots (they grow separately). [doc:beginners_guide_early_game]
- **Blockers**: clearing is usually low priority except for valuable features. [doc:beginners_guide_early_game]
- **First colony** grants an ethic-specific reward (e.g. research, unity or resources) once. [doc:colonization]

## 4. Technology

- Research comes in three areas (physics, society, engineering) with cards drawn from
  weighted options; see [doc:technology] for how alternatives and costs work.
- **Scientists**: council scientists give the research-speed bonus; new scientists level
  faster on science ships (exploration). [doc:technology]
- **Military tech**: always take the next tier of weapons/armour/shields when offered and
  refit; the directly relevant fields are Field Manipulation, Particles, Military Theory,
  Materials, Propulsion and Voidcraft. [doc:beginners_guide_late_game]
- **Chokepoint defence**: FTL Inhibition makes starbases stop enemy fleets from passing
  without a fight. [doc:beginners_guide_early_game]
- Enigmatic Engineering (second perk) offers fallen-empire building techs, but each one gives
  −10 opinion with every fallen empire (−20 with Keepers of Knowledge). [doc:beginners_guide_late_game]

## 5. Traditions and ascension perks

- Traditions cost unity; cost grows with traditions taken and empire size. Each tree has 5
  traditions plus adoption and finisher effects; up to 7 trees; finishing a tree unlocks an
  ascension perk slot. [doc:traditions]
- **Peaceful growth**: Discovery (research, survey speed, +1 research alternative, finisher
  +10% research), Expansion (colonies/starbases), Prosperity (+5% resources from jobs, cheaper
  infrastructure). [doc:traditions]
- **Military**: Supremacy (+20 naval capacity on adoption, +25% ship build speed, +10% fire
  rate), plus Unyielding/Enmity; perks Galactic Force Projection and Eternal Vigilance. [doc:traditions] [doc:beginners_guide_late_game]
- **Diplomatic**: Diplomacy tree (federations; *The Federation* tradition is required to
  found one) and Politics. [doc:beginners_guide_early_game] [doc:beginners_guide_late_game]
- **Ascension paths** (Utopia, present): Genetics, Psionics, Cybernetics, Synthetics — mutually
  exclusive and need a free tradition-tree slot. Choosing one is an **ask_human** decision. [doc:beginners_guide_late_game]
- Detailed lists: [doc:ascension_perks].

## 6. Diplomacy vs. war posture

- **First contact** needs an envoy; completing it establishes communications. [doc:beginners_guide_early_game]
- **Defensive pacts / federations** with neighbours deter opportunistic attacks and add fleets.
  Federation members join each other's defensive wars. [doc:beginners_guide_early_game] [doc:beginners_guide_late_game]
- **Galactic Community** forms once an empire has contact with at least 70% of empires; votes
  are weighted by diplomatic weight. Council and Custodian need Nemesis (present). [doc:beginners_guide_early_game] [doc:galactic_community]
- **Keep a real fleet** even when peaceful: it deters neighbours and clears space monsters.
  Split fleets to cover multiple borders; starbases alone cannot stop fleets. [doc:beginners_guide_late_game]
- **Starbases** are stronger than early fleets until destroyers; gun/missile batteries and
  hangar bays raise their power. [doc:beginners_guide_early_game] [doc:starbase]

## 7. War

- **Claims** decide what territory the winner takes. Base cost 50 influence, +25 per jump from
  your territory, +25 if upgraded starbase, +25 if colonised; doubled during an offensive
  war; −20% against a rival. Claim before declaring. [doc:warfare]
- **Surrender** is pushed by relative fleet strength (up to +50), war exhaustion (up to +100)
  and occupation (up to +100). At 100% war exhaustion a side can be forced into status quo
  after 24 months. [doc:warfare]
- **Occupation** needs assault armies (or bombardment until defenders die); transports are
  defenceless — escort them; lost armies add war exhaustion. [doc:beginners_guide_late_game]
- **Defence**: defense armies come from soldier jobs (Strongholds/Fortresses); a Planetary
  Shield Generator halves bombardment damage. [doc:beginners_guide_late_game]
- **Doom-stack**: keep fleets together into battle; split fleets get picked off. [doc:beginners_guide_late_game]
- Casus belli, war goals and total war rules: [doc:warfare]; combat mechanics: [doc:space_warfare],
  ship roles: [doc:ship_designer].

## 8. Crisis preparation

- **Timing**: an endgame crisis can only start after the End-Game Start Year (galaxy
  setting); checks run every 5 years and it normally appears ~50 years after that year
  (earlier with jump drives or certain resolutions). The chosen crisis then fires after
  200–1000 days. [doc:crisis] [doc:beginners_guide_late_game]
- **Midgame crises** also exist (DLC-tied). [doc:crisis]
- **Damage stacking vs. crises**: Defender of the Galaxy (+50%), a level-5 Galactic Union or
  Martial Alliance (+50% each), Galactic Threats Committee resolution and A United Front
  custodian reform (+20% each) — up to +140%. [doc:beginners_guide_late_game]
- **Checklist when the end-game year is within ~10 years**: naval capacity filled, fleets
  on current tech, starbases at chokepoints fortified, alloys stockpiled, federation /
  community stance set to cooperate against the crisis. [doc:beginners_guide_late_game] [doc:crisis]

---

## 9. Governor directives

The governor model does not micro-manage; it picks **one** standing directive and the
native AI executes it. The empire runs in **observer mode** (`observe`), so the native AI
plays it day to day. A directive is applied from the console (verified 2026-09-25,
`games/stellaris-spike/journal.md`): pause → `play 0` → whitelisted `effect …` commands →
`observe` → unpause. **While observing, `effect` has no country scope and silently does
nothing**, so `play 0` must come first. Verified: `set_policy` (the AI kept it for the 2
months checked) and `set_country_flag`. Untested: edicts, economy plans, and whether the AI
keeps them. Policy changes lock that policy for 10 years in normal play [doc:policies]; the
console's `cooldown = no` skips the lock, so change policies rarely anyway. A later companion
mod could add `ai_weight` modifiers that read a `governor_directive_<name>` flag
[doc:ai_modding]. A directive **never** adds resources, modifiers or anything the empire
could not do itself.

| Directive | AI emphasis (intended) | Pick when | Leave when |
|---|---|---|---|
| `expand` | Outposts, colony ships, science ships, starbase capacity; Map the Stars edict; Discovery/Expansion traditions | Opening; unclaimed habitable systems nearby; no hostile neighbour stronger than us; no deficits | Border closed by other empires, or influence/alloys run dry, or a deficit appears |
| `consolidate_economy` | Districts/buildings for the deficient resources, housing and amenities, subsidies edicts, Prosperity | Any basic resource net < 0 with < ~12 months of stock; stability or housing warnings; after a burst of expansion | All nets positive with some buffer for ~2 years |
| `tech_rush` | Research buildings/jobs and stations, scientists, Discovery; Civilian or Mixed economy | Safe borders (pacts, strong starbases), economy stable, behind in tech vs. neighbours or crisis approaching with outdated ships | A neighbour's fleet overtakes ours, or war is declared |
| `prepare_war` | Alloys (Militarized economy only if the 10-year lock is acceptable), naval capacity, ship refits, claims, armies, Supremacy; Fleet Supremacy edict | A weaker neighbour with claimable systems, our fleet near naval capacity, no deficits, and ask_human confirmed the target | War declared (then `defend` or keep until the war ends), or the target gains allies that outmatch us |
| `defend` | Fleets home and together, starbase upgrades and defense platforms at chokepoints, Fortify the Border, defense armies | War declared on us, a hostile stronger neighbour on the border, a crisis entering our space | Peace signed and no hostile fleet near the border for ~1 year |
| `diplomacy_first` | Envoys to improve relations, pacts, federation membership, galactic community weight; Diplomacy/Politics traditions; Diplomatic Grants | Many contacts, we are weaker than neighbours, or a federation / community seat is within reach | A partner turns hostile, or diplomacy has reached its goals |

Priority when several fit: **defend > consolidate_economy > prepare_war > expand >
tech_rush > diplomacy_first** — survival, then solvency, then growth. Hold a directive at
least ~12 in-game months unless an urgent line forces a change.

**Observer mode is the base of the design** [doc:console_commands]: `observe` hands the
empire to the native AI (in the spike, research queues were filled the same day), and
`play <id>` takes it back just long enough to apply a directive.

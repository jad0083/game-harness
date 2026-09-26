# Advanced strategy for the governor (Stellaris 4.5.1 "Cygnus")

Scope: decision rules for choosing one standing directive (`expand`, `consolidate_economy`,
`tech_rush`, `prepare_war`, `defend`, `diplomacy_first`) about every 12 in-game months, while the
game's own AI runs the empire (`human_ai`). Rules are phrased as "if signal, prefer directive,
because reason". Signals refer to lines in the `stellaris brief` output (Power, Resources,
IDLE stockpiles, Planets, Standing, Neighbours, Expansion room, BOXED IN, Colonisable planets).

Evidence levels:
- **[files 4.5.1]**: read from the game's own script files (`common/traits`, `common/technology`,
  `common/policies`, `common/ascension_perks`, `common/scripted_variables`, `common/buildings`,
  `common/governments/civics`) of the installed 4.5.1 build. The strongest evidence here.
- **[wiki 4.x]**: stellaris.paradoxwikis.com, the version given in Sources.
- **(unverified)**: community knowledge or estimates not confirmed for 4.x.

What changed in 4.0 "Phoenix" and later, and makes older (3.x) advice wrong:
- Pops are **pop groups**, and counts are about 100x the 3.x numbers (a 3.x "30-pop planet" is now
  roughly 3,000 pops). Growth is logistic, monthly and fractional. A new colony needs 100 colonists
  from growth or migration. [wiki 4.x: Patch 4.0]
- Push/pull migration was replaced by **auto-migration** to planets with at least 20% habitability.
  [wiki 4.x: Patch 4.0]
- **Trade** is the market currency. It pays ship logistic upkeep (free docked, cheap in friendly
  space, expensive in hostile space) and planet logistic upkeep for local deficits. [wiki 4.x: Patch 4.0, Trade]
- Deficit situations reduce **job efficiency**, not raw output. [wiki 4.x: Patch 4.0]
- Factions produce **unity**, not influence. [wiki 4.2: Factions]
- 4.5: pop groups are no longer split by ethic or faction (each group holds percentages), so
  ethic attraction now moves faction sizes directly. The AI picks fleet doctrines that suit its
  personality and is much less willing to join wars that are already running. [wiki 4.5: Patch 4.5]

---

## 1. Growth when boxed in

Signals: `BOXED IN`, "Colonisable planets inside our borders: none", Expansion room 0 unclaimed,
Systems owned flat for 2+ briefings.

Decision rules:
- If BOXED IN **and** no colonisable planets, **stop picking `expand`**. The expand budget
  (outposts, colony ships) has nothing to spend on. Choose `tech_rush` (to reach habitat and
  terraforming techs), or `prepare_war` when a weaker neighbour has systems we want (see §6).
- If BOXED IN but colonisable planets remain inside our borders, `expand` is still useful: its
  colony-ship budget fills the internal planets. Switch away once the brief lists none.
- If BOXED IN and every neighbour is at least as strong as us (military ≥ 1.0x in Neighbours),
  prefer `tech_rush` → habitats and gene/terraforming techs, not war.
- If BOXED IN and a neighbour's military is ≤ 0.6x ours, with claims possible and no defensive
  pact behind it, prefer `prepare_war`. Conquest is the fastest 4.x growth route but adds pops
  and upkeep at once; take a few systems per war, not everything. (unverified; community consensus)

Growth routes when boxed in (script name, then display name):

- **Orbital habitats**: `tech_habitat_1` Orbital Habitats (tier 3 engineering, 5,000 points,
  needs `tech_starbase_3` Starhold) → `tech_habitat_2` Habitat Expansion (needs `tech_starbase_4`
  Star Fortress) → `tech_habitat_3` Advanced Space Habitation (needs `tech_starbase_5` Citadel).
  [files 4.5.1]
  - Cost 1,500 alloys (mechanical shipset) or 750 alloys + 2,625 food (biological), plus 200
    influence, 5-year build. One per system. Not in systems with a ring world or an
    uninvestigated anomaly. [wiki 4.5: Megastructures]
  - Habitability 40% / 50% / 60% by admin-building tier I–III. The number of districts grows with
    the planets/stars in the system (+0.25 per body per tier). Resource districts depend on the
    system's deposits (about 1 + half the deposit value). Orbital expansions build themselves as
    districts are added. [wiki 4.5: Megastructures; Steam 4.0 discussion]
  - Worth it when: BOXED IN, alloys net ≥ +30/month (unverified threshold), influence ≥ 200 spare,
    and a system has many bodies or big energy/mineral/research deposits. Not worth it while
    ordinary planets of 60%+ habitability are still free, or while alloys are needed for a threat.
  - `ap_voidborn` Voidborne perk (needs `tech_habitat_1`): habitats get +2 max districts and cost
    20% less. Good for a boxed-in empire. [files 4.5.1]
- **Terraforming**: `tech_terrestrial_sculpting` Terrestrial Sculpting (tier 2, 3,000) →
  `tech_ecological_adaptation` Ecological Adaptation (tier 3, lets you terraform inhabited
  planets) and `tech_climate_restoration` Climate Restoration (tier 4, 8,000, more terraforming
  options). `ap_world_shaper` World Shaper (needs Climate Restoration and one earlier perk):
  −25% terraforming cost and allows **Gaia worlds** (100% habitability for every species).
  [files 4.5.1] Terraforming a 20% (other climate group) planet into the preferred class turns a
  poor planet into an 80% one. Prefer `tech_rush` while these techs are pending.
- **Ecumenopolis**: `ap_arcology_project` Arcology Project needs `tech_housing_2` Anti-Gravity
  Engineering (tier 3) and at least two earlier perks. Ecumenopolis, ring worlds and Gaia worlds
  give 100% habitability. [files 4.5.1; wiki 4.4: Habitability]
- **Hive / machine worlds**: `ap_hive_worlds` / `ap_machine_worlds` need Climate Restoration and
  two earlier perks. [files 4.5.1]
- **Better habitability** (all raise `pop_environment_tolerance`, which the game shows as
  "Planet Habitability"): `tech_colonization_2..5` Atmospheric Filtering, Hostile Environment
  Adaptation, Foreign Soil Enrichment, Eco-Integration Studies (+5% each); Adaptability tradition
  `tr_adaptability_environmental_diversification` (+10%); Genetics `tr_genetics_retrovirus`
  (+10%); `tech_integrated_cybernetics` (+5%). [files 4.5.1]
- **Other species**: a second species with a different climate group doubles the usable planets.
  Sources: the **Migration Treaty** pact (pops of both empires can grow on and be used in colony
  ships; needs positive relations or 20 trust; not with gestalts), refugees (xenophile),
  conquered pops, and uplifting pre-sapients. Gene modding the climate preference needs
  `tech_glandular_acclimation` Glandular Acclimation (tier 3). [wiki 4.4: Diplomacy; files 4.5.1]
  If a friendly neighbour has a different climate preference, `diplomacy_first` can get a
  migration treaty. That is growth without war.
- **Vassals / federations**: `diplomacy_first` builds towards a federation (members +50 opinion,
  −1 influence each). A federation gives shared defence, federation perks and a federation fleet
  (up to 600 naval capacity, no upkeep). Overlord subject specialisation is not installed on this
  PC. [wiki 3.11/4.4: Federations, Diplomacy]
- **Colony development speed**: `tech_cryostasis_1/2` Automated Colony Ships (+50% each),
  `tech_planetary_infrastructure_1/2` (+25% each), Expansion tradition (+25% on adopt, +25% from
  Colonization Fever), expansionist stance (+15%). [files 4.5.1]

## 2. Species traits and habitability

### Habitability rules in 4.5.1 [files 4.5.1 `01_species_traits_habitability.txt`]
- Organic species with a climate preference: **preferred class 80%**, **same climate group 60%**,
  **any other normal class 20%**. Gaia, ring world and ecumenopolis 100%. Homeworld +30%.
- Climate groups:
  - **Dry**: desert, arid, savannah
  - **Wet**: tropical, continental, ocean
  - **Cold**: arctic, tundra, alpine
  - Volcanic-preferring species treat volcanic and the dry classes as 60%.
- Machine and robotic species: `trait_machine_unit` / `trait_mechanical` set a **50%
  habitability floor**. Machine climate traits give 75% in the favoured group and 50% elsewhere.
- Each 1% below 100% habitability: +1% pop upkeep and amenities use, −0.5% job efficiency and
  growth. At 0% that is +100% upkeep and −50% output. [wiki 4.4: Habitability]
- The game asks for confirmation below 70%. Auto-migration fills planets at 20% or more.
  [wiki 4.4; Patch 4.0]

Rules:
- If the main species' preferred climate group has few planets nearby, value `tech_rush`
  (tolerance techs, terraforming, Glandular Acclimation) and a second species (migration treaty,
  `diplomacy_first`) more highly.
- 60% planets (same group) are worth colonising early. 20% planets are not worth it without
  tolerance bonuses, a second species or terraforming.

### Trait effects in 4.5.1 [files 4.5.1 `04_species_traits.txt`, `02_…basic_characteristics.txt`]
Many traits changed meaning in 4.x: they now boost **job categories** (workforce multipliers).
| Script | Display | Effect (4.5.1) | Cost | Strategic shift |
|---|---|---|---|---|
| `trait_intelligent` | Intelligent | +10% researcher jobs | 2 | favour `tech_rush` |
| `trait_natural_engineers` | Natural Engineers | +15% engineer jobs | 1 | tech; engineering (habitats, ships) |
| `trait_natural_physicists` | Natural Physicists | +15% physicist jobs | 1 | tech |
| `trait_natural_sociologists` | Natural Sociologists | +15% biologist jobs | 1 | tech (society: terraforming, genetics) |
| `trait_rapid_breeders` | Rapid Breeders | +10% logistic growth | 2 | favour `expand`: colonies fill faster |
| `trait_slow_breeders` | Slow Breeders | −10% logistic growth | −2 | fewer wide colonies; migration treaties and conquest matter more |
| `trait_strong` / `trait_very_strong` | Strong / Very Strong | +20% / +40% army damage, +2.5% / +5% worker output, +10% / +15% soldier jobs | 1 / 3 | invasions easier: `prepare_war` more viable |
| `trait_weak` | Weak | −20% army damage, −2.5% workers | −1 | avoid invasion-heavy wars |
| `trait_industrious` | Industrious | +15% **miner** jobs (4.x meaning) | 2 | mineral-rich economy, can afford districts and habitats |
| `trait_agrarian` | Agrarian | +15% farmer jobs | 2 | food surplus; sell or grow |
| `trait_ingenious` | Ingenious | +15% technician jobs | 2 | energy surplus; watch for idle energy (§8) |
| `trait_thrifty` | Thrifty | +25% **trader** jobs | 2 | trade surplus: the market is a strong fallback (§8) |
| `trait_adaptive` / `trait_extremely_adaptive` | Adaptive / Extremely Adaptive | +10% / +20% habitability | 2 / 4 | 60% planets become 70–80%: favour `expand` |
| `trait_nonadaptive` | Nonadaptive | −10% habitability | −2 | only preferred-class planets; habitats, terraforming, second species |
| `trait_nomadic` / `trait_sedentary` | Nomadic / Sedentary | −35% / +35% resettlement cost (not migration speed in 4.x) | 1 / −1 | minor |
| `trait_communal` / `trait_solitary` | Communal / Solitary | −10% / +10% housing use | 1 / −1 | Solitary: consolidate housing more often |
| `trait_charismatic` / `trait_repugnant` | Charismatic / Repugnant | ±20% **influential jobs** (4.x meaning; was amenities) | 2 / −2 | Repugnant: watch stability and unity |
| `trait_conformists` / `trait_deviants` | Conformists / Deviants | +30% / −15% attraction to the government ethic | 2 / −1 | Deviants: more faction trouble; keep stability high |
| `trait_traditional` / `trait_quarrelsome` | Traditional / Quarrelsome | ±10% bureaucrat jobs | 1 / −1 | unity pace |
| `trait_docile` / `trait_unruly` | Docile / Unruly | −10% / +10% empire size from this species | 2 / −2 | Unruly: wide empires hurt more; expand in shorter bursts |
| `trait_conservational` / `trait_wasteful` | Conservational / Wasteful | ∓10% consumer goods upkeep | 1 / −1 | Wasteful: more consumer goods; stricter on deficits |
| `trait_decadent` | Decadent | −10% worker and slave happiness | −1 | stability risk |
| `trait_venerable` / `trait_enduring` / `trait_fleeting` | leader lifespan +80 / +20 / −10 | | 4 / 1 / −1 | minor |

Special archetypes [files 4.5.1]:
- **Lithoid** (`trait_lithoid`): eats **minerals** instead of food, **+50% habitability**
  (environment tolerance), −25% growth, +50% army health. Rules: colonise almost anything
  (favour `expand`), but growth is slow and a mineral deficit is also a food deficit, so
  `consolidate_economy` must watch minerals first.
- **Machine / robotic** (`trait_machine_unit`, `trait_mechanical`): 50% habitability floor, so
  every class is at least workable. Pops are assembled, so growth is limited by assembly, not
  planets (unverified for 4.5). Favour wide `expand`. Energy is their food.
- **Hive mind** (`trait_hive_mind`): no factions, so no ethic stability trouble. Amenities come from
  maintenance drones. Gestalts get −20% war exhaustion and +1 influence. [wiki 4.4: Ethics] Cannot
  sign migration treaties.
- **Cybernetic** (4.5): +10% job efficiency baseline, +20% habitability. [files 4.5.1; Patch 4.5]
- Genetic-ascension traits reworked in 4.0: `trait_robust` (+30% habitability, +5% jobs),
  `trait_fertile` (+20% growth), `trait_erudite` (+20% researchers), `trait_nerve_stapled` (+15%
  jobs, −15% empire size). [files 4.5.1]

## 3. Ethics, civics, origins → directive fit

Ethics modifiers [wiki 4.4: Ethics]:
- **Militarist**: +10% (fanatic +20%) ship fire rate, −10% (−20%) claim cost → `prepare_war` is cheap. Its
  faction wants a used navy, and the AI takes the belligerent or supremacist stance itself.
- **Pacifist**: −10% (−20%) empire size, +5 (+10) stability; cannot take the Supremacist stance,
  and fanatic pacifists cannot start offensive wars. Never pick `prepare_war` as an aggressor.
  Use `defend` / `diplomacy_first` / `tech_rush`, and grow tall (habitats, ecumenopolis).
- **Xenophile**: +10% (+20%) trade, +1 (+2) envoys, more refugees → `diplomacy_first`,
  migration treaties, multispecies growth.
- **Xenophobe**: +10% (+20%) pop growth, −20% (−40%) outpost influence cost → `expand` hard early.
  No full citizenship for aliens, and cooperative diplomacy is weak. When boxed in: `prepare_war`.
- **Egalitarian**: +15% (+30%) faction output (unity), +5% (+10%) specialist output → `tech_rush`.
  Keep stability up. Slavery policies are unavailable.
- **Authoritarian**: +0.5 (+1) influence/month, +5% (+10%) worker output → more influence makes
  `expand` stronger.
- **Spiritualist**: +10% (+20%) unity, −10% (−20%) edict cost → traditions and perks come sooner.
  Pairs well with `consolidate_economy` / `expand`.
- **Materialist**: +5% (+10%) research, −10% (−20%) robot upkeep → `tech_rush` is the default
  directive once safe.
- **Gestalt** (hive / machine): −20% war exhaustion, +1 influence, fixed ethics. No factions, no
  consumer goods for drones (unverified for 4.5), no migration treaties. Diplomacy is limited, so
  prefer `expand`, `tech_rush`, `defend`.

Civics and origins (script names verified in the civic data) [files 4.5.1]:
- `civic_technocracy` Technocracy, `civic_meritocracy` Meritocracy → `tech_rush`.
- `civic_distinguished_admiralty` Distinguished Admiralty (+20 command limit),
  `civic_citizen_service` Citizen Service (+15% naval capacity), `civic_warrior_culture` Warrior
  Culture (Duelist jobs: +2 naval capacity each, −10% war exhaustion), `civic_nationalistic_zeal`
  Nationalistic Zeal (−20% war exhaustion) → `prepare_war` is effective.
- `civic_fanatic_purifiers`, `civic_hive_devouring_swarm`, `civic_machine_terminator`
  (+33% naval capacity; they cannot use normal diplomacy) → never `diplomacy_first`. Rotate
  `prepare_war` / `expand` / `defend`.
- `civic_inwards_perfection` Inward Perfection (isolationist, no wars of conquest) →
  `consolidate_economy` / `tech_rush` / `defend` only.
- `civic_diplomatic_corps` Diplomatic Corps, `civic_beacon_of_liberty` Beacon of Liberty,
  `civic_idealistic_foundation` Idealistic Foundation → `diplomacy_first` pays off.
- `civic_mining_guilds` Mining Guilds, `civic_agrarian_idyll` Agrarian Idyll → economy-first;
  Agrarian Idyll has fewer city slots (unverified 4.x), so expansion matters more.
- Origins: `origin_void_dwellers` Void Dwellers (habitat species: prefer habitats, Voidborne);
  `origin_shattered_ring` Shattered Ring (ring-world preference, few normal colonies: `tech_rush`);
  `origin_life_seeded` Life-Seeded (Gaia preference: terraforming and World Shaper matter);
  `origin_post_apocalyptic` Post-Apocalyptic (tomb-world preference); `origin_common_ground`
  Common Ground / `origin_hegemon` Hegemon (start in a federation: `diplomacy_first` early);
  `origin_doomsday` Doomsday (homeworld explodes: `expand` urgently); `origin_remnants` Remnants,
  `origin_syncretic_evolution` Syncretic Evolution (second species from the start: wider
  climates); `origin_galactic_doorstep` Galactic Doorstep (gateway: defend it).

## 4. Naval capacity

Sources in 4.5.1 [files 4.5.1; wiki 4.5: Fleet; wiki 4.4: Starbase]:
- Base 20 (Fleet page, 4.5). Ship sizes use 1/1/2/4/8/16 capacity (corvette … titan).
- Techs: `tech_doctrine_navy_size_1` Doctrine: Fleet Support +25, `_2` Support Vessels +50,
  `_3` Interstellar Logistics +75, `_4` Fleet Liaisons +100 (society, military theory; tiers
  1/2/3/4, costs 1,250/2,500/4,000/12,000). Repeatable `tech_repeatable_naval_cap` Fleet
  Management Procedures +20 each.
- Starbase **Anchorage** module: +5 each (+3 more with a Naval Logistics Office). This is the main
  scalable source, but upgraded starbases use starbase capacity.
- Planet buildings: `building_stronghold` (needs `tech_planetary_defenses`) and its upgrade
  `building_fortress` give **Soldier jobs**, which give naval capacity. The AI limits itself to 2
  of each unless the planet has a fortress zone.
- Traditions: Supremacy adopt `tr_supremacy_adopt` +20 flat. The Fleet Logistics Corps tradition
  +20% (wiki 4.5).
- Diplomatic stance: `diplo_stance_supremacist` +20% naval capacity, −20% war exhaustion.
  `diplo_stance_belligerent` +10%, −10%. Both −10% claim influence cost.
- Civics: Citizen Service +15%, Purifiers / Devouring Swarm / Terminators +33%. Perk
  `ap_galactic_force_projection` Galactic Force Projection +150 flat, +20% command limit, +2 max
  influence from power projection. Edict A Grand Fleet +20%.
- Negatives: no Minister of Defense −25%; the Demobilization / Defense Privatization galactic
  resolutions −10% to −80%.
- Going over capacity raises **all** ship upkeep in proportion to the excess. It is a soft cap.

Why the AI fleet stays small, and what to do:
- In 4.5 the AI weighs naval-capacity buildings against every other building
  (`AI_NAVAL_CAP_SCORE_MULT` 15 → 3) and stopped overbuilding strongholds. [Patch 4.5 notes] The
  AI's own targets are "current naval cap +100" (intermediate plan) up to +350 (beyond endgame),
  and they only apply while used capacity is above 85%. [files 4.5.1 `economic_plans`]
- Ships cost alloys to build **and** trade/energy upkeep. A fleet at 100% capacity with alloys net
  ≤ 0 cannot grow. Rules:
  - If naval capacity used ≥ 90% and alloys net > 0 and a threat exists → `prepare_war` or
    `defend`. Both add alloy budget for ships, and the AI then builds capacity.
  - If naval capacity used < 50% and no neighbour's military exceeds ours → do not pick military
    directives. Alloys are better spent on `expand` / habitats.
  - If alloys net is low (< ~+20 midgame, unverified) the fleet cannot grow whatever the
    directive. Pick `consolidate_economy` first; the militarized economic policy (+25% alloys
    from jobs, −25% consumer goods) is part of `prepare_war`.
- Fleet command limit (base 50; +20 per combat doctrine tech; +10 per hull-size tech) limits one
  fleet's size, not total ships.

## 5. Influence

Sources [wiki 4.4 unless noted]:
- Base income is small (about +3/month, unverified for 4.x). Authoritarian +0.5 / fanatic +1;
  gestalt +1. Rivalries +0.5 each (`diplo_stance_animosity` allows 2 rivals and adds unity).
  Power projection up to +2 when naval capacity used is high relative to empire size.
  `tech_autonomous_agents` Autonomous Agents +1. Domination tradition viceroys +0.5. Edict
  "Will to Power" +5. The Supremacy/Diplomacy traditions and some civics add small amounts.
  [files 4.5.1 for Autonomous Agents, Domination, Force Projection]
- Factions no longer give influence in 4.x (they give unity). Politician-type jobs give unity and
  amenities, not influence. [wiki 4.2 Factions, 4.3 Jobs] So influence is almost flat in 4.x.
  Influence storage caps at 1,000.

Sinks:
- Outposts: 75 × hyperlane jumps from the nearest owned system (bypasses count). Every outpost
  also adds influence upkeep. The expansionist stance gives −10% outpost cost, xenophobe
  −20%/−40%, Interstellar Dominion −20%. [wiki 4.4: Starbase; files 4.5.1]
- Claims (cheaper with militarist, belligerent/supremacist −10%, animosity −20% vs the rival).
- Diplomatic pacts upkeep: federation membership −1. The Diplomacy tradition halves pact upkeep.
  In 4.5 Federation Code cuts diplomacy influence upkeep by 25%.
- Habitats cost 200 influence each. Abandoning a colony costs 50 (4.4). Since 4.0 all buildings
  have an influence cost (doubled on another corporate empire's planets). [Patch 4.0]

Rules:
- The vanilla AI only funds outpost alloys while influence > 75, and the governor's `expand`
  budget sets an influence floor of 75. [mod + vanilla ai_budget] If influence stock < 75 and
  income < +2, `expand` barely works. Pick `consolidate_economy` or `diplomacy_first` for a year,
  then return to `expand`.
- If influence is near the 1,000 cap and there is still room to expand → `expand` (influence is
  being wasted). If BOXED IN with high influence → claims plus `prepare_war`, habitats, or
  federation (`diplomacy_first`).
- A militarist / authoritarian empire fighting over border systems gets cheap claims; keep
  influence ≥ 100–200 before `prepare_war` so claims can be made (unverified amount).

## 6. Military power vs peers: war, defence, diplomacy

Signals: Power military vs Neighbours multiples; "shares our border"; opinion; threat; FALLEN
EMPIRE flags; wars in the brief.

- If a bordering neighbour's military is ≥ 1.5x ours and its opinion of us is negative → `defend`
  (starbase and ship budget; fortify chokepoints). If it is ≥ 1.5x and opinion is positive →
  `diplomacy_first` (non-aggression pact, defensive pact, federation) while it stays friendly.
- If we are at war as defender → `defend` until the war ends; if war exhaustion climbs on both
  sides, a status quo keeps fully occupied claimed systems. Status quo can be forced 24 months
  after one side reaches 100% war exhaustion (automatic after 24 months if both). [wiki 4.4: Warfare]
- `prepare_war` only when: our military ≥ 1.3x the target's (unverified margin), naval capacity
  used ≥ 80%, no deficits, the target has no defensive pact or federation that outweighs us, and
  influence covers claims. Claim-based wars keep only claimed systems that we fully occupy (status
  quo) or all claimed systems (surrender). Each unoccupied claimed colony gives −100 surrender
  acceptance. [wiki 4.4: Warfare] In 4.5 the AI rarely joins wars already running, so a 1v1 war
  against an isolated target is safer than before. [Patch 4.5]
- War exhaustion reducers: supremacist −20%, belligerent −10%, Never Surrender tradition −25%,
  gestalt −20%, Nationalistic Zeal −20%, Colossus perk −15%, Interstellar Campaigns tech −10%.
  [wiki 4.4] In 4.4+, a fully occupied empire gets +5% war exhaustion every month, past 100%.
- Ship upkeep in 4.x depends on location: hostile space costs more, docked ships are free.
  [Patch 4.0] Long wars far from home drain trade; if trade or energy goes negative mid-war,
  seek a status quo.
- Never provoke a **Fallen Empire**. They are far stronger. Keep them friendly or distant.
- Defensive pacts and federations are the cheap substitute for a fleet when we are weaker; pick
  `diplomacy_first` when two or more neighbours have positive opinion and we are not the
  strongest. A federation fleet costs no upkeep (up to 600 capacity).
- Chokepoints: when only 1–2 hyperlanes lead to a hostile neighbour, `defend` (starbases,
  platforms) is more efficient than a mobile fleet. `ap_eternal_vigilance` Eternal Vigilance
  (needs `tech_starbase_4`) gives +25% starbase damage/hull and +5 platforms. [files 4.5.1]

## 7. Timing and benchmarks

Default settings: start 2200, **mid-game 2300**, **end-game 2400**. [wiki: Galaxy settings]

The AI's own economic-plan ladder in 4.5.1 [files 4.5.1 `scripted_variables`, `economic_plans`]
is a good benchmark. Research numbers are **per research type** (physics, society, engineering);
pops are in 4.x units (about 100x 3.x):
| Stage | Energy | Minerals | Alloys | Research (each) | Unity | Trade | Pops | Naval cap goal |
|---|---|---|---|---|---|---|---|---|
| intermediate | +40 | +50 | +50 | 150 | +50 | +25 | 25,000 | +100 over current |
| advanced | +100 | +150 | +150 | 400 | +100 | +50 | 100,000 | +200 |
| mature | +150 | +200 | +200 | 1,000 | +200 | +75 | 175,000 | +250 |
| endgame | +200 | +300 | (1,300 alloy cap in 4.4) | up to 3,500 scaling | | | | +300 |

Rough year targets for a competent empire at normal settings (unverified for 4.x; adjust with
the brief's Standing lines, which compare us with the median):
- **2200–2215**: explore, 10–20 systems, 2–4 colonies. `expand` almost always, unless deficits.
- **2215–2240**: 25–40 systems, 5–10 colonies, "intermediate" plan reached. Alternate `expand` and
  `consolidate_economy`. Get Starhold for habitats if boxed in.
- **2240–2280**: expansion ends (borders meet). Reach "advanced" plan. `tech_rush` whenever safe;
  `prepare_war` only against clearly weaker neighbours.
- **2280–2300**: mid-game events start at 2300 (marauders, AI rebellion, Gray Tempest, and Fallen
  Empire awakening can follow). Fleet at ≥ 80% naval capacity with up-to-date components.
- **2350–2400**: crisis preparation. The endgame crisis can come from 2400 (earlier if the Ancient
  Robot World dig or both Extradimensional Experimentation and Galactic Threats Committee
  resolutions pass). It usually comes 25+ years after 2400 if anyone has jump drives
  (`tech_jump_drive_1` / `tech_psi_jump_drive_1`), and is guaranteed 50 years after. Checks every
  5 years. [wiki 4.4: Crisis]
- If "FALLING BEHIND (below half the median)" appears for tech → `tech_rush` (unless a threat
  needs `defend`). For economy → `consolidate_economy`. For military with a hostile neighbour →
  `defend`.

Crisis preparation rules:
- From ~2370 (unverified lead time): shift to `tech_rush` if safe, then `prepare_war` / `defend`
  from ~2390 to fill naval capacity. Crisis damage bonuses: `ap_defender_of_the_galaxy` Defender
  of the Galaxy (+50% damage vs crises; needs 3 earlier perks), federation perks level 4–5
  (+25%), Galactic Threats Committee resolution (+20%). [wiki 4.4; files 4.5.1]
- Crisis strength setting and difficulty scale crisis hull/armour/shields/damage. With "all
  crises" each one is twice as strong as the one before. [wiki 4.4]
- When a crisis enters or borders our space → `defend` (overrides everything). Refit the fleet to
  counters from the crisis sub-pages (`corpus search crisis`). The AI refits on its own.

## 8. Economy pitfalls

- **Idle stockpiles**: the brief flags "IDLE stockpiles" (stock > 5,000, over 10 years of
  income). Hoarded energy/minerals do nothing. The AI does not use the market well (unverified).
  - Big energy or minerals + positive income + room to grow → `expand` (outposts and colonies use
    alloys and influence, not energy, so idle energy means districts/buildings should be funded)
    or `consolidate_economy` (the governor mod adds mineral budget for planet districts and
    buildings).
  - Big alloys + high naval capacity headroom → `prepare_war` / `defend` (turns alloys into
    ships), or habitats (1,500 alloys each) if BOXED IN.
- **Deficits**: any basic resource net < 0 with < 12 months of stock → `consolidate_economy`
  (highest priority after `defend`). In 4.x a deficit adds planet logistic upkeep paid in trade
  (1/8 of the base market price per missing unit: 0.125 for energy/minerals/food, 0.25 consumer
  goods, 0.5 alloys) and lowers job efficiency through deficit situations. [wiki 4.4: Stability;
  Patch 4.0]
- **Market**: trade is the market currency; fee starts at 30% (minimum 5%). Trade storage 50,000.
  [wiki 4.4: Trade] Buying fixes a short gap; it is not a lasting fix for a structural deficit.
  `trait_thrifty` and `diplo_stance_mercantile` (+10% trade) make trade surpluses; the trade
  policy converts trade into other resources.
- **Amenities and stability**: stability 50 is neutral. Each point above gives +0.6% job output,
  each point below −1%. **Below 25 for a year starts a Planetary Revolt situation.**
  [wiki 4.4: Stability] Amenities deficit reaches −50% happiness when a planet has < 25% of its
  needs; each colony loses a flat amount to inefficiency. Crime above 30 creates persistent
  modifiers. If any planet in the brief has stability < 40, negative free amenities or free
  housing, or crime > 30 → `consolidate_economy`.
- **Hedonist** pops (4.5) give growth only as a share of the colony (max +30%), need free
  housing/amenities, and stop working during consumer goods deficits. [Patch 4.5]
- **Economic policy lock**: a policy change normally locks it for 10 years. The console bypasses
  this, but flipping between Civilian (`tech_rush`) and Militarized (`prepare_war`) every year
  moves ±25% alloys/consumer goods each time. Hold a directive at least 12 months, preferably 24.
  [files 4.5.1 `00_policies.txt`]
- **Empire size**: every system, colony and pop adds empire size, which raises tech and tradition
  costs. `ap_interstellar_dominion` (−25% from systems in 4.5.1 files) and
  `ap_imperial_prerogative` (−25% from colonies) help. Do not `expand` into empty dead-end systems
  late when research is the bottleneck. [files 4.5.1]

## Directive quick map (summary of the rules above)

| Signal pattern | Directive |
|---|---|
| War on us / crisis in our space / hostile neighbour ≥ 1.5x military on border | `defend` |
| Deficit with < 12 months stock, stability < 40, housing/amenities negative | `consolidate_economy` |
| Unclaimed systems within 2 jumps, influence ≥ 75, no deficit | `expand` |
| BOXED IN, internal colonisable planets remain | `expand` (colony ships) |
| BOXED IN, no planets, neighbours strong | `tech_rush` (habitats, terraforming) |
| BOXED IN, weaker neighbour (≤ 0.6x), claims affordable, naval cap ≥ 80% used | `prepare_war` |
| Tech FALLING BEHIND, borders safe | `tech_rush` |
| Weaker than neighbours but they are friendly; different-climate partner available | `diplomacy_first` |
| Idle alloys + naval headroom + threat | `prepare_war` / `defend` |
| 2370+ with no immediate threat | `tech_rush` then `defend` / `prepare_war` by 2390 |

## Market and planet economy notes (Cedar Games, "Stellaris Planet and Economy Guide", 4.3.7)

Recorded on 4.3.7 (June 2026); not re-checked against the 4.5.1 files unless marked.
- **Market trades** cost the fee on each side: selling 100 food at the 30% fee gives 70 trade,
  buying 100 minerals costs 130 trade, so converting one resource into another returns about
  54%. Prices move with supply and demand and drift back over time: many small trades beat one
  large trade. **Monthly trade orders** (a standing buy or sell at the end of every month) do this
  automatically; early on, a small monthly mineral buy with surplus food/energy is recommended.
  For the governor: idle energy or trade (the briefing's `IDLE` line) is only useful through the
  market, which the game's AI does not do on its own (unverified).
- **Colonies** add a flat 20 empire size each however developed they are (unverified for 4.5):
  settle a world only when pops can be moved there to make it productive.
- **Pop growth** is fastest at about half of a planet's capacity; resettling pops from a crowded
  capital to a new colony raises growth on both.
- **Fleets docked** at a starbase with crew quarters pay less upkeep and no trade logistics;
  leaving port for a war raises energy, alloy and trade costs at once, so keep a reserve before
  `prepare_war`.
- **Planetary deficits** are covered by the empire but cost trade (logistics); specialised worlds
  pay more of it, usually still worth it.

## Sources

- Installed game files, Stellaris **v4.5.1** (read 2026-09-26 from the local copy under
  `incoming/stellaris/common/`): `traits/01_species_traits_habitability.txt`,
  `traits/02_species_traits_basic_characteristics.txt`, `traits/04_species_traits.txt`,
  `traits/05_species_traits_robotic.txt`, `traits/09_ascension_traits.txt`,
  `traits/10_species_traits_cyborg.txt`, `technology/00_soc_tech.txt`,
  `technology/00_soc_tech_repeatable.txt`, `traditions/00_supremacy.txt`,
  `policies/00_policies.txt`, `ascension_perks/00_ascension_perks.txt`,
  `buildings/09_army_buildings.txt`, `governments/civics/00_civics.txt`,
  `scripted_variables/00_scripted_variables.txt`, `economic_plans/*.txt`; generated records in
  `corpora/stellaris/data/*.json` (techs, civics, perks).
- Governor mod budget: `corpora/stellaris/mod/governor_bridge/common/ai_budget/zz_governor_bridge_budget.txt`.
- https://stellaris.paradoxwikis.com/Patch_4.0 — 4.0 "Phoenix" notes (pops, migration, trade, deficits, traits).
- https://stellaris.paradoxwikis.com/Patch_4.4 — 4.4 (occupation war exhaustion, abandon cost, AI research/alloy caps).
- https://stellaris.paradoxwikis.com/Patch_4.5 — 4.5 "Cygnus" (pop groups and factions, hedonists, cybernetics, AI war joining, naval cap AI).
- https://steamdb.info/patchnotes/25342231/ — 4.5 release notes (AI_NAVAL_CAP_SCORE_MULT, stronghold overbuild fix).
- https://stellaris.paradoxwikis.com/Fleet — naval capacity and command limit sources, verified 4.5.
- https://stellaris.paradoxwikis.com/Megastructures — orbital habitat cost and tiers, verified 4.5.
- https://stellaris.paradoxwikis.com/Habitability — habitability tiers and penalties, verified 4.4.
- https://stellaris.paradoxwikis.com/Crisis — crisis timing and damage bonuses, verified 4.4.
- https://stellaris.paradoxwikis.com/Ethics — ethic modifiers, verified 4.4.
- https://stellaris.paradoxwikis.com/Trade — trade resource and market fee, verified 4.4.
- https://www.youtube.com/watch?v=8JiqZYKU9PA — Cedar Games, Stellaris Planet and Economy Guide (4.3.7, 2026-06-19): market, pop growth, planet management.
- https://stellaris.paradoxwikis.com/Stability — stability thresholds, revolt, deficit trade cost, verified 4.4.
- https://stellaris.paradoxwikis.com/Influence — influence sinks and sources (thin), verified 4.4.
- https://stellaris.paradoxwikis.com/Warfare — status quo, war exhaustion, verified 4.4 (local copy `docs/warfare.md`).
- https://stellaris.paradoxwikis.com/Starbase — outpost influence cost, starbase capacity, anchorage, 4.4 (local `docs/starbase.md`).
- https://stellaris.paradoxwikis.com/Diplomacy — migration treaty, federation membership, 4.4 (local `docs/diplomacy.md`).
- https://stellaris.paradoxwikis.com/Factions — factions produce unity, 4.2 (local `docs/factions.md`).
- https://stellaris.paradoxwikis.com/Jobs — politician-type jobs (unity/amenities), 4.3 (local `docs/jobs.md`).
- https://stellaris.paradoxwikis.com/Galaxy_settings — default mid-game 2300 / end-game 2400.
- https://steamcommunity.com/app/281990/discussions/0/596278429494589338/ — 4.0 habitat districts (community, 4.0).
- Dropped as pre-4.0 only: push/pull migration, faction influence, Charismatic = amenities,
  Nomadic = migration speed, Intelligent = flat +10% research, Thrifty = trade value per pop.

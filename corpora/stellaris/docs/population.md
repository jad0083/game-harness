# Population
Source: https://stellaris.paradoxwikis.com/Population
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20251218023434 (the live wiki blocks non-browser clients). Page version banner: Version Please help with verifying or updating older sections of this article. At least some were last verified for version 3.14. This article is for the PC version of Stellaris only. | Please help with verifying or updating this section. It was last verified for version 4.0. | Please help with verifying or updating this section. It was last verified for version 4.1._

Population, represented by pops, drives the productivity and political action of an empire. Pops produce resources by working jobs that are created by districts and buildings. Pops belonging to a specific faction will produce unity.

## Population groups

Population is grouped into pop groups. There is one pop group for each combination of species, stratum, ethic, and whether the pop is unemployed or not. Pop groups fill jobs. By default they will fill as many jobs as are available, provided there is sufficient population, but certain bonuses can allow pops to fill jobs above the current limit, producing extra resources.

### Stratum

Strata represent pops' social classes and determines the resettlement cost. Resettlement costs no unity if the empire has the Corvée System, Subsumed Will, or OTA Updates civic, or if the pop is enslaved or a non-sentient robot. If a pop takes a job above its stratum, it will be promoted to the higher stratum.

#### Individualist strata

Individualist empires use the following strata. The higher a pop's stratum, the more political power they have and the more consumer goods they require for upkeep. If there are no available jobs of equal or higher stratum the pop will become unemployed, causing happiness penalties in most living standards for 4 years until the pop becomes a Civilian. The Shared Burdens civic and living standards each reduce demotion time by −45% each, the Kinship tradition reduces it by −75%, and defaulted empires have demotion time reduced by −50%. Slaves and Hive-Minded pops demote instantly regardless of stratum. Hovering over an unemployed pop will show the remaining time until it is demoted.

| Stratum | Demotion time | Requirements | Jobs | Workforce modifiers |
|---|---|---|---|---|
| Elite | 4 years |  | Elite jobs | Modifiers +40% Clone Soldier Ascendant trait +5% Necrophage trait |
| Specialist | 2 years |  | Specialist jobs | Modifiers +25% Clone Soldier Ascendant trait +10% Meritocracy civic +10% Fanatic Egalitarian empire ethic +5% Egalitarian empire ethic +5% Necrophage trait +5% Pursuit of Profit / Creative Collectives tradition |
| Worker | 1 year |  | Worker jobs | Modifiers +10% Fanatic Authoritarian empire ethic +10% Environmental Ordinance Waivers +10% Rural World designation +7.5% Building a Better Tomorrow +5% Authoritarian empire ethic +5% Collective Waste Management +5% Workplace Motivators tradition +5% Very Strong species trait +2.5% Regulatory Facilitation +2.5% Strong species trait −2.5% Weak species trait −10% Necrophage trait |
| Civilian | Cannot demote | Available jobs Enslaved Hive-Minded pop | Civilian if not Pleasure Seekers or Corporate Hedonism Hedonist if Pleasure Seekers or Corporate Hedonism |  |
| Menial Drone | Cannot demote | Available jobs Hive-Minded pop | Disconnected Drone |  |
| Criminal | Cannot demote | High crime | Subversive jobs |  |

#### Gestalt strata

Gestalt Consciousness empires use the following strata. They promote and demote instantly and always take the Corrupt/Deviant Drone jobs if any are present.

| Stratum | Requirements | Jobs | Workforce modifiers |
|---|---|---|---|
| Complex Drone |  | Complex Drone jobs | Modifiers +20% Manufacturing Focus production policy +5% Machine Capital designation +5% Nest Planet designation +5% Machine Nexus designation +5% Peak Performance / Neural Signal Boosters tradition +1% per Bio-trophy "employed" on planet −20% Extraction Focus production policy |
| Menial Drone |  | Menial Drone jobs | Modifiers +20% Extraction Focus production policy +10% Fringe Planet designation +5% Machine Capital designation +5% Hive World designation +5% Machine World designation +5% Drone Network tradition −20% Manufacturing Focus production policy |
| Maintenance Drone | No available jobs Wilderness | Maintenance Drone |  |
| Biomass | No available jobs Wilderness | Pliable Biomass |  |
| Bio-Trophy | Organic species in a Rogue Servitor empire | Bio-Trophy |  |
| Deviant Drone | High deviancy in Hive Mind empires | Deviant Drone |  |
| Corrupt Drone | High deviancy in Machine Intelligence empires | Corrupt Drone |  |

#### Other strata

These strata are present in both Individualist and Gestalt empires, and are always used if their requirements are met.

| Stratum | Requirements | Jobs |  |
|---|---|---|---|
| Assimilation | Assimilation citizenship | Undergoing Assimilation |  |
| Undesirable | Undesirables citizenship | Purging |  |
| Computing Component | Synaptic Lathe | Neural Chip |  |
| Pre-sapient | Pre-sapient species | Pre-sapient jobs |  |

#### Fallen empire strata

These strata can only be used by fallen empires. If their requirements are not met, standard strata will be used.

| Stratum | Requirements | Jobs |
|---|---|---|
| Precursor | Founder species | Fallen empire jobs |
| Primitive | Alien pops on The Preserve | Xeno-Ward |

## Resettlement

Resettlement is the process of pops moving from one planet to another, more desirable one.

### Automatic resettlement

Sapient, unemployed, free Civilian pops have a chance each month to automatically resettle to another planet with available jobs and Housing and at least 20% Habitability. If a Slave Processing Facility is active on the planet, or if a Transit Hub starbase building is present in the system, enslaved pops and robots in servitude are also eligible. Pops cannot automatically resettle from planets that have been colonized for less than 61 months.

Migration controls will prevent this (except for sapient robots).

The number of pops that will resettle from any planet each month is predetermined as of patch 4.0; by default, 10 pops will resettle per month. This value can be increased by:

- a Transit Hub starbase building is present in the system: +20/mo
- Greater than Ourselves edict (from the GalCom resolution of the same name) is active: +20/mo
- Networked Movement edict is active: +5/mo
- researching Hyperlane Breach Points and Hyperspace Slipstreams: +2.5/mo each
- a leader with Frontier Spirit I or II is on the Council: +2.5/mo per rank

Note that the numbers above can be found by multiplying the base 10/mo by the percent increase listed in the tooltips.

Resettling pops will choose their destination based on a hidden weight value, determined using the stability of the planet and its Automatic Resettlement Destination Chance modifiers, ignoring any invalid planets (see above). Be aware that if you have any active migration treaties, other empires' planets become valid destinations for your pops. Of course, this can be used to your benefit if you have strong/several Automatic Resettlement Destination Chance modifiers, such as Open Arms.

### Forced resettlement

Forced resettlement will instantly move a pop from one planet to another. This costs a base amount of energy and unity determined by the pop's stratum, which may be reduced by additional modifiers. Resettling the last pop of a world will add a cost of 200 Influence and abandon the world. Forced resettlement requires either the Allowed Resettlement policy, the Cosmogenesis ascension perk, or the pop to be a non-sapient robot.

| Pop Stratum | Allowed? | Base cost |  |
|---|---|---|---|
| Elite | Policy | 500 | 50 |
| Specialist | Policy | 250 | 25 |
| Worker | Policy | 100 | 10 |
| Complex Drone Menial Drone | Always | 100 | 10 |
| Slave | Policy | 50 | 0 |
| Bio-Trophy | Always | 100 | 25 |
| Purging Assimilation | Always | 100 | 0 |
| Robotic servitude | Always | 100 | 0 |
| Subversive | Never | n/a |  |

| Modifier source | Cost |  |
|---|---|---|
| Evacuation Protocols edict | −50% |  |
| Appropriation tradition | −50% |  |
| Corvee System civic | +0% | No cost |
| Subsumed Will civic | +0% | No cost |
| OTA Updates civic | +0% | No cost |
| Starborn trait | −25% |  |
| Nomadic trait | −25% |  |
| Sedentary trait | +25% |  |

## Happiness

Each pop in an empire has a happiness rating. It ranges from 0% to 100% and has a base level of 50%. Happiness determines approval rating when combined with stratum political power, as well as the following effects:

- Each point of happiness above 50 adds +1% governing ethics attraction to free pops and +2% Authoritarian ethics attraction to slaves.
- Each point of happiness below 50 adds −1% governing ethics attraction to free pops and +10% Egalitarian ethics attraction to slaves.
- Each point of happiness above 50 gives each pop −0.02 crime, up to 0 per pop at 100% happiness.
- Each point of Happiness below 50 gives each pop +0.02 crime, up to +2 per pop at 0% happiness.

Fortunately, there are many ways to improve happiness in an empire. Planetary edicts, civics, living standards, permanent modifiers, planet modifiers, and ruler traits can positively affect happiness.

Faction approval also plays a major role in pop happiness and Events may have an impact on planetary or empire happiness for a limited time as well.

Happiness can be affected by the following:

| Happiness (empire) 0 |  |
|---|---|
| Source | Effect |
| Artisan enclave festival deal | +15% |
| Peace Festivals edict | +10% |
| Lessons of Harmon edict | +10% |
| The Gains of Freedom empire modifier | +10% |
| The Paradise Initiative resolution (5) | +10% |
| Environmental Control Board resolution (4) | +5% |
| Improved Working Environment edict | +5% |
| Sanctum of the Instrument building | +5% |
| Technology of the Divine empire modifier | +5% |
| A Life Worthwhile empire modifier | +5% |
| Cheap Thrills empire modifier | +5% |
| Spurred by the Past empire modifier | +5% |
| Full Circle empire modifier | +5% |
| Goes Around, Comes Around empire modifier | +5% |
| Population United empire modifier | +4% |
| Stuffed Toy empire modifier | +2% |
| Consumer Goods minor deficit | −5% |
| Digital Billboards empire modifier | −5% |
| Enhanced Surveillance edict | −10% |
| Thought Enforcement edict | −10% |
| Tracking Implants edict | −10% |
| Residence species rights | −10% |
| Population Controls Enabled species rights | −10% |
| Consumer Goods major deficit | −10% |
| Consumer Goods severe deficit | −15% |
| Consumer Goods catastrophic deficit | −20% |
| Deeper Secrets of the Vultaum empire modifier | −20% |
| Profit Maximization Engines resolution (5) | −25% |

| Happiness (species) 0 |  |
|---|---|
| Source | Effect |
| Serviles trait | +10% |
| Loyalty Circuits trait | +10% |
| Conservative trait | +5% |
| Psionic trait | +5% |
| Synthetic Salvation trait | +5% |
| Abrasive Implants trait | −10% |

### Political power

Pop political power effects approval rating as well as Faction resource production and support. Pops have a base of 0.01 political power. General political power modifiers stack multiplicatively with stratum specific ones. Stratum specific modifiers, except for living standards, only apply to employed pops.

| Source | Political power |
|---|---|
| Full Citizenship citizenship Speaker for the Kin councilor | +2% per level |
| Civilian category Under One Rule origin Strengthened Government II / III modifier | +25% / 50% |
| Undesirable stratum | −100% |
| Robotic Servitude category |  |
| Assimilation category |  |
| Primitive category |  |
| Pre-sapient category |  |
| Computing Component category |  |
| Slave species rights | −75% |
| Bio-Trophy category | +1000% |
| Unemployed Bio-Trophy category |  |
| Precursor category | +900% |
| Residence citizenship | −50% |
| Protected Drones citizenship | −100% |
| Symbiotic Drones citizenship |  |
| Exploited Drones citizenship |  |
| Indentured Sevitude | +50% |

| Source | Political power |  |  |  |  |  |
|---|---|---|---|---|---|---|
| Elite | Specialist | Worker | Civilian | Slave |  |  |
| Living standards | 0% to +1000% | −25% to +400% | −75% to +400% | −100% to +400% |  |  |
| Slave Processing Facility |  |  |  |  | −25% |  |
| Orbital Slave Processing Hub |  |  |  |  | −25% |  |
| Domination Opener |  |  |  |  | −25% |  |
| Oligarchic Overclocking | +200% | −100% | −100% |  |  |  |
| Chief Posting Officer councilor |  | +5% per level |  |  |  |  |
| Penal Colony |  |  | −100% |  |  |  |
| The Greater Good |  |  | +10 / 25 / 50 / 75 / 100% |  |  |  |
| Elite Benefactor (sector/planet) | +7.5% / 15% |  |  |  |  |  |
| Under One Rule origin Constitutional Freedoms modifier |  |  | +15% / 30% |  |  |  |
| Preserve the Order agenda launched |  |  | −25% |  | −25% |  |
| Power Flip modifier | −10% |  | +10% |  |  |  |
| Stand Your Ground modifier | +90% |  |  |  |  |  |
| Straight Talkers modifier | +50% |  |  |  |  |  |
| Prioritizing The Brightest modifier |  | +10% |  |  |  |  |
| Restricted Synth Body Modification | +20% | +10% |  |  |  |  |

### Approval rating

Pop approval rating is a measure of the population's support towards the empire. It is determined by the average happiness of each stratum, weighted by political power. Pops without happiness are treated as having 50% happiness (for example: pops with Nerve Stapled trait, pops with Machine trait). The displayed approval rating is rounded down, as is the displayed stability bonus.

Approval Rating = ∑ Pop happiness ⋅ political power ∑ Pop political power {\displaystyle {\text{Approval Rating}}={\frac {\sum _{}^{\text{Pop}}{\text{happiness}}\cdot {\text{political power}}}{\sum _{}^{\text{Pop}}{\text{political power}}}}}

Approval rating ranges from 0% to 100% and has a base level of 50%.

- Each point of approval rating above 50% adds +0.6 stability, up to +30 stability at 100% approval rating.
- Each point of approval rating below 50% adds −1 stability, up to −50 stability at 0% approval rating.

## Upkeep

Upkeep of a pop heavily depends on the type of pop and the type of empire. Usually it consists of:

- Base upkeep – some basic resource for the pop to sustain itself
- Living Standards upkeep – an amount of consumer goods
- Job upkeep – additional resources needed for the pop to perform its job
- Housing needs – a planet wide resource for pops to live in
- Amenities needs – a planet wide resource for pops to be happy about

Colony habitability lower than 100% for specific pop leads to penalties in the form of increased pop base upkeep and amenities needed for that pop.

See also: Colonization#Habitability

### Base upkeep

Base upkeep is always 1 of a basic resource per month, which depends on the type of pop and possibly its traits.

Certain species traits can replace part or all of a biological species' base upkeep with energy as well.

- Phototrophic trait, available to Fungoid or Plantoid pops, replace half their base upkeep with energy upkeep. As do pops with the Radiotrophic trait, with the addition that they require no energy upkeep when living on a Tomb World.
- Voidling replaces all of a pop's base upkeep with energy upkeep.
- Exotic Metabolism adds 0.125 exotic gases upkeep and Cyborg traits add additional energy upkeep.

After base upkeep is determined, it can be modified by species, planet, or empire modifiers. For example, Zombie pops have −100% base upkeep. Although there is a hidden cap of −90% for the sum of modified applied, this makes base upkeep always non-zero.

| Pop type | Base | Phototrophic | Radiotrophic | Radiotrophic | Voidling |
|---|---|---|---|---|---|
| Biological | 1.0 food | 0.5 food 0.5 energy | 0.5 food 0.5 energy | 0.5 food | 1.0 energy |
| Lithoid | 1.0 minerals |  | 0.5 minerals 0.5 energy | 0.5 minerals | 1.0 energy |
| Mechanical Machine Extradimensional | 1.0 energy |  |  |  |  |

### Living standards upkeep

See also: Living standards

In addition to base upkeep, non-Gestalt pops, including Bio-Trophies, require a certain amount of consumer goods based on their living standards. Synthetic (Mechanical) pops that are given citizen rights require consumer goods as well. The amount of consumer goods typically depends on the pop's stratum, but other modifiers can increase or decrease this amount.

### Housing

Housing represents the living space available for pops to live comfortably. Housing is primarily provided by districts, with city districts giving more housing than their resource-focused alternatives. Each pop requires 1 unit of housing by default but the housing demands of individual pops can change due to a variety of factors. If the number of pops exceeds the amount of housing it will cause stability to drop by 40 ⋅ missing housing total housing required {\displaystyle 40\cdot {\frac {\text{missing housing}}{\text{total housing required}}}} and a flat +50 planet emigration push.

As a rule of thumb, each resource district exactly pays for itself in terms of housing, while the pops that work building jobs need city districts (or housing buildings) for their housing, though the capital building provides some buffer before cities are needed. This applies equally to Ecumenopolises. The Agrarian Idyll civic gives extra housing to resource districts, allowing the empire to house its pops working building jobs mostly via resource districts. The Trans-Stellar Corporations tradition adds jobs to habitat trade districts, but does not match them with additional housing, making some residential districts necessary.

### Amenities

Amenities represent the infrastructure and jobs dedicated to fulfilling the needs of the population on a given colony. Individualist empires obtain amenities from a variety of jobs while Gestalt Consciousness empires obtain them primarily from Maintenance Drone jobs. High amenities grant increased happiness to citizen pops in regular empires and increased stability in Gestalt Consciousness empires, while insufficient amenities will lower pops' happiness (or stability, for Gestalts) on the colony.

Pops have a base amenity requirement of 1 Amenities, slaves require 0.75, and non-citizen Robots require 0.5. The shown amenities value is the available amenities value, or the surplus. After base amenities upkeep is determined, it can be modified by species, planet, or empire modifiers. 5 Amenities are always lost on every colony due to inefficiencies. The formula for available amenities (or extra amenities) is the following:

Available Amenities = Amenities Provided − (5 + Pop Amenities Usage) = {\displaystyle {\text{Available Amenities}}={\text{Amenities Provided}}-(5+{\text{Pop Amenities Usage}})=}

= (Amenities Provided by Buildings + (Amenities Provided by Jobs ⋅ ∑ modifiers with Job scope)) ⋅ ∑ modifiers with Planet/Empire scope − {\displaystyle =({\text{Amenities Provided by Buildings}}+({\text{Amenities Provided by Jobs}}\cdot \sum {\text{modifiers with Job scope}}))\cdot \sum {\text{modifiers with Planet/Empire scope}}-}

− (5 + Pop base Amenities Upkeep ⋅ ∑ upkeep modifiers) {\displaystyle -(5+{\text{Pop base Amenities Upkeep}}\cdot \sum {\text{upkeep modifiers}})}

One impactful upkeep modifier is the effect of subprime habitability on the specific pop.

Most values representing amenities are rounded to the closest integer value (the tie-breaking rule is unknown), except for amenities from pop jobs - it is rounded down.

The formula for available amenities or amenities deficit effect on a planet's happiness (stability for Gestalt empires) is not strictly linear, with less effect for extra amenities than missing amenities.

The formula for extra amenities (available amenities > 0 case) contributing to happiness is:

happiness bonus = min (20%, 20 ⋅ ⌊ available amenities ⌋ ⌊ pop amenities usage ⌋) {\displaystyle {\text{happiness bonus}}={\text{min}}\left(20\%,{\frac {20\cdot \left\lfloor {\text{available amenities}}\right\rfloor }{\left\lfloor {\text{pop amenities usage}}\right\rfloor }}\right)}

In other words, it scales from +0% with 0 available amenities, to +20% with twice as many available amenities as necessary.

The formula for a amenities deficit (available amenities < 0 case) affecting happiness is:

happiness penalty = max (− 50%, 200 / 3 ⋅ ⌊ available amenities ⌋ ⌊ pop amenities usage ⌋) {\displaystyle {\text{happiness penalty}}={\text{max}}\left(-50\%,{\frac {200/3\cdot \left\lfloor {\text{available amenities}}\right\rfloor }{\left\lfloor {\text{pop amenities usage}}\right\rfloor }}\right)}

In other words, it scales from +0% with 0 available amenities, to −50% when the planet has less than 25% of amenities needed.

Note: for readability reasons in the formulas above for the happiness effect as a function of amenities the rounding operations are noted as rounding down when in reality rounding to the nearest integer is used. The stability bonus or penalty received by Gestalt Consciousness empires from amenities in a colony by value is the same%-value a non-Gestalt empire gets in happiness (the formulas above can be used).

Amenities can be affected on an empire-wide basis by the following:

| Source | Amenities |
|---|---|
| Artificial Moral Codes technology | +5% |
| Executive Retreat branch office building | +10% |
| Resort World | +15% |
| Profane Consecrated World | +1% |
| Respected Consecrated World | +2% |
| Venerated Consecrated World | +3% |
| Holy World Consecrated World | +4% |
| Mega Art Installation (stage I) | +5% |
| Mega Art Installation (stage II) | +10% |
| Mega Art Installation (completed) | +15% |
| Mega Art Installation (perfection) | +20% |
| Vultaum Star Assembly secrets special project | +20% |

| Source | Amenities usage |
|---|---|
| One Vision ascension perk | −10% |
| Vultaum Reality Perforator relic | −10% |
| Ecological Protection resolution 2 | −5% |
| Discourage Planetary Growth decision | +25% |
| Resident citizenship status | −25% |
| Ascetic | −15% |

## Slavery

Entire species can be enslaved by giving them a certain citizenship, which opens a new tab in the Species Rights menu called Slavery Type that determines what are the effects of slavery.

| Citizenship | Slavery requirements | Notes |
|---|---|---|
| Slaves | Species is alien and the empire is Authoritarian, Xenophobe, or Gestalt Consciousness |  |
| Servitude | Species is robot and the empire has the Artificial Intelligence policy set to Servitude | If Synthetic Dawn is active, setting this may cause a robot uprising. |

Grid amalgamation

Enslaved pops also use only 0.75 amenities and 0.75 housing per 100 pops, which can be further reduced by slavery type. They also have a resettlement cost of just 50 energy. Enslaved pops cannot join factions and have only 25% political power, or 18.7% if a Slave Processing Facility is present on the planet. However, they can still increase crime if they're too unhappy. Enslaved pops cannot demote to the Civilian stratum unless the empire has the Slaver Guilds or Indentured Assets civic but they also cannot trigger unemployment events.

Low stability is more dangerous when enslaved pops are present on a planet. Normally dangerous events can only occur if it's lower than 25, but if any pop is enslaved it should be kept above 40.

### Slaves, workers and specialists

In addition to the slave resource output modifiers, worker resource output modifiers can also affect slaves in worker jobs. As of 3.0.1, slaves in specialist jobs are affected by specialist output modifiers, but not by slave resource output modifiers, if in Indentured Servitude.

- Slaves working on Miner jobs can benefit from Worker resource output modifiers, such as Authoritarian and Strong.

If a modifier affects the resource output of both workers and slaves, it actually affects slaves in worker jobs twice.

- The Extended Shifts edict increases slaves resource output by +10% and workers resource output by +10%, resulting in an total +20% bonus to slaves in worker jobs.

Modifiers that affect workers aside from the resource output ones don't affect slaves.

- The Extended Shifts edict decreases slaves' happiness by −10% and worker happiness by −10%. It does not cause the slaves to suffer −20% happiness.

## Robots

Robots are artificial pops and can be constructed once the required technology becomes available. They have the Mechanical trait, alongside a broader set of climate preference traits that determines habitability on different planet categories, rather than specific types. Robots can be given new traits via robo-modding, and the species template with the highest number of used trait points will be built by default. A different template can be specified for each planet.

The jobs a robot can have are limited by the highest robot technology researched. If an empire researches the Artificial Administration technology with AI policy set to Servitude or Citizen Rights, all robots immediately become sapient.

| Mechanics | Mechanical pops (based on Artificial Intelligence policy and technology) | Machine pops |  |  |
|---|---|---|---|---|
| Artificial Workforce | Artificial Specialists | Artificial Administration |  |  |
| Can fill Worker jobs |  |  |  |  |
| Can fill Specialist jobs |  |  |  |  |
| Can fill Elite jobs |  |  | Citizen Rights |  |
| Can colonize |  |  |  |  |
| Can fill Researcher jobs Can fill Administrator jobs |  | Servitude Citizen Rights | Servitude Citizen Rights |  |
| Affected by happiness Contributes to crime |  |  | Servitude Citizen Rights |  |
| Uses −0.5 housing Uses −0.5 amenities |  |  | Servitude Outlawed |  |
| Uses consumer goods |  |  | Citizen Rights |  |

If Synthetic Dawn DLC is enabled and AI policy is set to Servitude, empires with either Artificial Administration or Sapient Combat Simulations technology have a risk of getting the AI-Related Incidents situation.

Synthetic ascension allows a non-gestalt organic empire to turn all organic pops and leaders into synthetics. Completing it will permanently force the Citizen Rights policy.

Hive Mind empires cannot build robots and will always purge all robots on their worlds.

Machine pops are sapient and use consumer goods upkeep as well as full housing and amenities usage regardless of AI policies.

## Purges

Purges represent the systematic elimination of specific species of pops from an empire.

Purging is done by setting a species' citizenship to Undesirables. Gestalt Consciousness pops in empires of a different authority are forced to be set as Undesirables, unless they can be assimilated or the Disconnected Drones policy is set to Sustain. Therefore, gaining planets from a Gestalt Consciousness empire means that the planet will be lost when it is empty of the conquered pops if there is not at least one non-gestalt pop on it. There are also three special cases:

- Pre-sapients can only be purged if the Pre-Sapients policy is not set to Protected and they are automatically purged if it's set to Extermination.
- Robots are automatically purged if the Robotic Workers policy is set to Outlawed.
- Synthetics can only be purged if the Artificial Intelligence policy is not set to Citizen Rights.

Having any species-wide purge is a negative issue for Xenophile factions, aside from the case of Gestalt Consciousness pops and outlawed robots. The empire's founder species cannot be purged regardless of policies or if they are not the default species template.

There are multiple types of purge available, determined by the Purge Type species rights.

Purging pops gives empires for whom that species is their founding species a negative "Purged Our Species" opinion modifier towards the empire doing the purging (−0.25 per pop to a maximum of −1000) and everyone else the negative "Genocidal" opinion modifier (−0.5–0.15, depending on ethics and policies, to a maximum of −1000). An empire that doesn't know the purging is happening (because it isn't in contact with the purger or has no economic intel on them), or that doesn't care (including fallen and awakened empires other than a xenophile Awakened Empire), gets no opinion modifier. Synaptic Service purging only gives penalties when it happens on the Synaptic Lathe; when it happens elsewhere, the pop is moved to the Lathe rather than killed. Necrophage purging provokes smaller "Mysterious Disappearances" or "Necrophaged Our Species" penalties instead.

| Type | Monthly decline | Effects | Happiness | Opinion loss | Refugees chance | Valid species | Requirements | DLC |
|---|---|---|---|---|---|---|---|---|
| Displacement It's not that we drive them from their homes. Their homes are simply no longer theirs. | 25 | −50% Pop housing usage | −30% | no | 100% | Hive-Minded Mechanical, unless the pops are sapient Machine if Machine Intelligence Cybernetic if Driven Assimilator | Genocidal Fanatic Purifiers Devouring Swarm Devouring Swarm Terravore Devouring Wilderness Determined Exterminator Scorched World Heralds Scorched World Heralds Pyromanic Instinct |  |
| Extermination The extermination squads are efficient. The dissolution of entire populations naturally takes time, but they get the job done. | 100 |  | −1000% | yes | 5% | All | Devouring Swarm Terravore |  |
| Neutering Think of it as a phasing-out of a people. Our nation goes to meet the future, only some will not be with us. | 10 |  | −20% | no | 0% | Hive-Minded Mechanical, unless the pops are sapient Machine | Individualist |  |
| Forced Labor With this final sacrifice, they will at least have been of some use. | 50 | +3 Food +3 Minerals | −1000% | yes | 25% | Hive-Minded Machine | Individualist |  |

| Type | Monthly decline | Effects | Happiness | Opinion loss | Refugees chance | Valid species | Requirements | DLC |
|---|---|---|---|---|---|---|---|---|
| Processing It is a sad but inescapable fact that some are destined to simply fuel the ambitions of their betters. | 50 | +6 Food if species is biological +4 Minerals if species is lithoid +3 Alloys if species is robotic | −1000% | yes | 20% | Hive-Minded Robotic, unless Devouring Swarm | Machine Intelligence |  |
| Chemical Processing They will soon attain a more efficient form. | 50 | +6 Energy | −1000% | yes | 20% | Biological | Machine Intelligence |  |
| Necrophage Only the strongest may survive in a hostile galaxy. This way their journey may continue. | 20 | Pops are changed to founder species | −50% | yes | 25% | Biological | Necrophage origin |  |
| Maximize The quota must be reached. | 50 | −0.1 Energy +5 Consumer Goods | −1000% | yes | 20% | All | Obsessional Directive Determined Exterminator or missed a quota |  |
| Synaptic Service Duty calls and the brave and the bright answer its call. We bear our thoughts as torches, to banish the darkness of ignorance and superstition. Step Forth, brave ones, and Burn. | 100 | Resettles pops to Synaptic Lathe | −33% | yes | 5% | All | Owns a Synaptic Lathe |  |

| Type | Monthly decline | Effects | Happiness | Opinion loss | Refugees chance | Valid species | Requirements | DLC |
|---|---|---|---|---|---|---|---|---|
| Sacrifice | 50 | +5 Unity +2 Zro | −1000% | yes | 20% | War enemy founder species | Devouring War casus belli |  |

## Refugees

Humanoid refugees

Pops from other empires may flee to escape purges, slavery, resettlement, crisis bombardment, or as a result of using the Land Appropriation policy or Expel Excess Population decision. Whether another empire is willing to accept those fleeing depends on its Refugees policy. Refugees will not head for empires where they have the Undesirables citizenship. Accepted refugee pops will get +20 Happiness for 10 years and they will give +10 Intel on the empire they escaped from.

Once refugees are generated they will head for any empire that will accept them with their Refugees policy following the following order:

1. Habitability at least 70% and housing at least 100
2. Habitability at least 70%
3. Habitability at least 50% and housing at least 100
4. Habitability at least 50%
5. Habitability at least 20% and housing at least 100
6. Habitability at least 20%
7. Housing at least 100
8. Any other world except a Synaptic Lathe

Pops that have the Hive-Minded, Nerve Stapled, Zombie or Suppressed traits cannot become refugees.

## Demographics

Populations can grow or decline on a planet, based on several variables.

### Pop growth

All pop groups on a planet grow and shrink simultaneously, determined by both the planet-wide logistic growth modifiers (more space and jobs is better) and the species-specific population counts (small populations are penalized).

For the purpose of calculating the "size" of a population, all pop groups under the same top-level species are combined together (merging strata, ethics, and subspecies). Small populations (less than 2000[?] pops) are penalized in growth. The Xeno-Compatibility perk changes this, instead combining all pops together, across species, to determine their growth penalty (entirely negating the penalty for most groups on any reasonably developed planet). Each species's total growth amount each month is then distributed between the pop groups, relative to their size. Any growth amount less than 1 is probabilistic: a 1.2 growth amount will result in 1 guaranteed pop growth, and a 20% chance of a second pop growth.

If all the jobs in a given strata are filled, any new pops from groups in that strata will start out unemployed, and either eventually demote to a strata with jobs (possibly the Civilian/Maintenance Drone strata, which contains unlimited "jobs"), or migrate to another planet with jobs.

#### Migration

Automatic migration occurs randomly for any unemployed pop groups. They will migrate to another random planet with available jobs and at least 40% [?] habitability. There are many hidden factors influencing the weights of the various migration targets, and if you have Migration Pacts with another empire, that empire's planets become valid migration targets as well (and their pops can migrate to your planets).

#### Growth weight

### Pop assembly

Both biological pop assembly (from cloning) and mechanical pop assembly (from assembly) occur in addition to any natural biological pop growth. [Exact details TBD, but presumably all cloneable/assembleable species split the cloning/assembly growth, similar to natural growth.]

### Pop decline

Pop decline represents the decrease of certain species on the planet due to purging or severe overcrowding. [DETAILS TBD]

If the Population Controls policy is set to Allowed, enslaved pops can be manually set to decline on a planet.

If a species is being purged, has the Pathogenic Genes trait, or has the Clone Soldier or Clone Soldier Ascendant trait and insufficient Ancient Clone Vat buildings, it will always be set to decline.

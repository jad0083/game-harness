# Planetary management
Source: https://stellaris.paradoxwikis.com/Planetary_management
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260506204900 (the live wiki blocks non-browser clients). Page version banner: Version This article has been verified for the current PC version (4.3) of the game._

Planets are a vital part of a stellar empire because they provide the overwhelming majority of resources and the population required for an empire to grow and prosper. If a planet is managed properly, it could provide for the needs of its populace and the demands of its empire, and if an empire has a large collection of prosperous, productive planets within its borders, it can quite easily be seen as a successful empire.

Planetary development can be divided into three levels, each one requiring an additional investment of time and resources.

1. Districts
2. Specializations
3. Buildings

The more developed a planet is, the greater the number and diversity of Jobs available.

Each planet can only build one district, specialization or building, perform a decision, or clear a blocker at a time. Planets owned by empires with the Wilderness origin can perform 6 of these actions at a time.

## Housing

Housing represents the living space available for pops to live comfortably. Housing is primarily provided by districts, with city districts giving more housing than their resource-focused alternatives. Each pop requires 1 unit of housing by default but the housing demands of individual pops can change due to a variety of factors. If the number of pops exceeds the amount of housing it will cause stability to drop by Failed to parse (SVG (MathML can be enabled via browser plugin): Invalid response ("Math extension cannot connect to Restbase.") from server "https://en.wikipedia.org/api/rest_v1/":): {\displaystyle 40 \cdot \frac{\text{missing housing}}{\text{total housing required}}} and a flat +50 planet emigration push.

As a rule of thumb, each resource district exactly pays for itself in terms of housing, while the pops that work building jobs need city districts (or housing buildings) for their housing, though the capital building provides some buffer before cities are needed. This applies equally to Ecumenopolises. The Agrarian Idyll civic gives extra housing to resource districts, allowing the empire to house its pops working building jobs mostly via resource districts. The Trans-Stellar Corporations tradition adds jobs to habitat trade districts, but does not match them with additional housing, making some residential districts necessary.

## Amenities

Amenities represent the infrastructure and jobs dedicated to fulfilling the needs of the population on a given colony. Individualist empires obtain amenities from a variety of jobs while Gestalt Consciousness empires obtain them primarily from Maintenance Drone jobs. High amenities grant increased happiness to citizen pops in regular empires and increased stability in Gestalt Consciousness empires, while insufficient amenities will lower pops' happiness (or stability, for Gestalts) on the colony.

Pops have a base amenity requirement of 1 Amenities, slaves require 0.75, and non-citizen Robots require 0.5. The shown amenities value is the available amenities value, or the surplus. After base amenities upkeep is determined, it can be modified by species, planet, or empire modifiers. 5 Amenities are always lost on every colony due to inefficiencies. The formula for available amenities (or extra amenities) is the following:

Failed to parse (SVG (MathML can be enabled via browser plugin): Invalid response ("Math extension cannot connect to Restbase.") from server "https://en.wikipedia.org/api/rest_v1/":): {\displaystyle \text{Available Amenities} = \text{Amenities Provided} - (5 + \text{Pop Amenities Usage}) = }

Failed to parse (SVG (MathML can be enabled via browser plugin): Invalid response ("Math extension cannot connect to Restbase.") from server "https://en.wikipedia.org/api/rest_v1/":): {\displaystyle = (\text{Amenities Provided by Buildings} + (\text{Amenities Provided by Jobs} \cdot \sum \text{modifiers with Job scope})) \cdot \sum \text{modifiers with Planet/Empire scope} - }

− (5 + Pop base Amenities Upkeep ⋅ ∑ upkeep modifiers) {\displaystyle -(5+{\text{Pop base Amenities Upkeep}}\cdot \sum {\text{upkeep modifiers}})}

One impactful upkeep modifier is the effect of subprime habitability on the specific pop.

Most values representing amenities are rounded to the closest integer value (the tie-breaking rule is unknown), except for amenities from pop jobs - it is rounded down.

The formula for available amenities or amenities deficit effect on a planet's happiness (stability for Gestalt empires) is not strictly linear, with less effect for extra amenities than missing amenities.

The formula for extra amenities (available amenities > 0 case) contributing to happiness is:

Failed to parse (SVG (MathML can be enabled via browser plugin): Invalid response ("Math extension cannot connect to Restbase.") from server "https://en.wikipedia.org/api/rest_v1/":): {\displaystyle \text{happiness bonus} = \text{min} \left(20\%, \frac{20 \cdot \left\lfloor \text{available amenities} \right\rfloor}{\left\lfloor \text{pop amenities usage} \right\rfloor} \right)}

In other words, it scales from +0% with 0 available amenities, to +20% with twice as many available amenities as necessary.

The formula for a amenities deficit (available amenities < 0 case) affecting happiness is:

Failed to parse (SVG (MathML can be enabled via browser plugin): Invalid response ("Math extension cannot connect to Restbase.") from server "https://en.wikipedia.org/api/rest_v1/":): {\displaystyle \text{happiness penalty} = \text{max} \left(-50\%, \frac{200/3 \cdot \left\lfloor \text{available amenities} \right\rfloor}{\left\lfloor \text{pop amenities usage} \right\rfloor} \right)}

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

## Stability

Low Stability on a humanoid planet

Stability is a measure of the overall stability of a world, either socio-political or in terms of drone functionality, and is influenced by a large number of factors such as happiness, housing, amenities, and crime or deviancy. It ranges from 0 to 100 and has a base level of 50.

- Each point of stability above 50 adds +0.6% Resources from Jobs, +1% Automatic Resettlement Destination Chance and −0.5% Automatic Resettlement Chance.
- Each point of stability below 50 adds −1% Resources from Jobs, −1% Automatic Resettlement Destination Chance and +0.5% Automatic Resettlement Chance.
- At very low stability pops that are affected by Happiness may cause unrest events.
- Planets with less than 25 Stability for a year or more can trigger a Planetary Revolt situation.

A colony with any enslaved species and low stability can gain one of the following modifiers once every 2 years. All modifiers can be removed instantly by discontinuing slavery.

| Modifier | Effects | Duration | Required stability | Description |
|---|---|---|---|---|
| Slaves Radicalizing | −20 Stability | 20 years | 40 | Radical Slave elements are rallying, spreading unrest. |
| Hunger Strike | −50% Slave pop resource output −50% Slave Upkeep | 5 years | 25 | It's hard to work when you're doubled over from hunger pangs. |
| Slave Riots | −1000% Slave pop resource output −50% Pop growth speed −50% Army build speed −50% Planetary infrastructure build speed | 10 years | 10 | Slave Riots inhibit population growth. |

Stability can be affected by the following:

| Stability 0 |  |
|---|---|
| Source | Effect |
| Civilian difficulty | +20 |
| Democratic Interlink authority | +15 |
| Oligarchic Overclocking authority | +10 |
| Pacification Modules tradition | +10 |
| Cadet difficulty | +10 |
| AI Controllers empire modifier | +10 |
| Fanatic Pacifist ethic | +10 |
| Pacifist ethic | +5 |
| Police State civic | +5 |
| Shared Burdens civic | +5 |
| Dictatorial Alignment authority | +5 |
| Dictatorial Cybervision authority | +5 |
| Enhanced Surveillance edict | +5 |
| Information Quarantine edict | +5 |
| Lessons of Harmony edict | +5 |
| Self-Indictment Protocol edict | +5 |
| Utopian Dream tradition | +5 |
| Collective Reasoning tradition | +5 |
| Inner Stability agenda | +5 |
| Universal Prosperity Mandate resolution (5) | +5 |
| Aesthetic Approach empire modifier | +5 |
| Closed Society empire modifier | +5 |
| Freedom Fighters empire modifier | +5 |
| Harmonized Society empire modifier | +5 |
| Open Society empire modifier | +5 |
| Progress Oriented empire modifier | +5 |
| State Driven Sensory Censorship empire modifier | +5 |
| Revolutionary Spirit empire modifier | +2.5 |
| Population United empire modifier | +2 |
| Stuffed Toy empire modifier | +1 |
| Whisperers in the Void covenant | −3 |
| Whisperers in the Void covenant (50 favor) | −7 |
| Progenitor Hive lost capital | −10 |

## Crime and Deviancy

Crime (or Deviancy for Gestalt Consciousness empires) measures the overall level of non-compliance in the population of a world. Crime and Deviancy are produced by all sapient pops except those undergoing assimilation, ranging from 0 at 100% happiness to +2 at 0% happiness. Crime and Deviancy are reduced by certain jobs and leaders. Non-sentient Mechanical pops in an organic empire and mechanical pops integrated into a Machine Intelligence empire do not produce crime or deviancy, despite counting as 50% happiness for the purpose of approval rating.

Every year, one of the following modifiers can be added as long as the requirements are met. Another modifier cannot be added for the next 10 years. Alternatively, 15 devastation can be added instead of a modifier. Once a planet has below 10 Crime or Deviancy, all modifiers will be removed after 15 years. The timer is reduced by 50% for each Enforcer or Hunter-Seeker Drone job. All modifiers are also removed if a planet changes ownership.

### Persistent modifiers

These modifiers can appear while Crime/Deviancy is above 30 and persist until it is reduced enough for them to be removed. Empires with the Experimental Sentencing civic will gain +20% resources from Experiment Engineer and Test Subject jobs from them.

| Modifier | Effects | Description |
|---|---|---|
| Criminal Underworld | +15 Crime +100 Criminal jobs +100 Criminal job per 33 Crime | This world is home to a large criminal underworld. |
| Drone Deviancy | +15 Deviancy +100 Deviant Drone jobs +100 Deviant Drone job per 33 Deviancy | This world is home to large communities of deviant drones, who no longer respond to commands from the Hive Mind. |
| Drone Corruption | +15 Deviancy +100 Corrupt Drone jobs +100 Corrupt Drone job per 33 Deviancy | This world is home to several networks of deviant and corrupted drone units, who operate outside the established parameters set by the core intelligence. |
| Center of Drug Trade | +30 Crime +300 Criminal jobs Requires the Criminal Underworld modifier and replaces it | The world has become a major center of drug trade. Illegal narcotics are being smuggled planetside on a daily basis, with a large segment of the populace being regular users. |
| Gang Wars | +30 Crime +300 Criminal jobs Requires the Criminal Underworld modifier and replaces it | The world is currently in the middle of a very destructive gang war between two or more organized crime factions. Heavy fighting is ongoing between the rivaling gangs, with local security forces trapped in the middle. |

| Modifier | Effects | Description |
|---|---|---|
| Mob Rule | +30 Crime +300 Criminal jobs Requires the Criminal Underworld modifier and replaces it | The world is currently dominated by a single criminal organization. They have infiltrated all layers of society, and little happens here without their involvement or permission. |

### Temporary modifiers

The following modifiers appear as a result of crime events, and last for 10 years.

| Modifier | Effects | Requirements | Description |
|---|---|---|---|
| Crime Boss Arrested | −30 Crime | Criminal Underworld modifier | An important crime boss was recently arrested on this world, crippling a major criminal organization. |
| Bribed Officials | −20 Stability | Criminal Underworld modifier | Several high-ranking officials on this world were recently discovered to have been in the pay of local criminal organizations. |
| Crime Wave | +30 Crime | Criminal Underworld modifier | This world is currently experiencing a crime wave. |
| Smuggler Activity | −20% Trade from jobs | Criminal Underworld modifier | An increase in smuggler activity on this world has had a negative impact on profits from trade. |
| Substance Abuse | −20% Resources from jobs | Criminal Underworld modifier | The illegal use of dangerous and highly addictive drugs is widespread on this world. |
| Corrupt Administration | −20 Stability | Mob Rule modifier | The vast majority of this world's planetary administration was recently revealed to have been in the employ of its dominant crime syndicate. |
| Protection Racket | −20% Resources from jobs | Mob Rule modifier | The mobsters who rule this world have implemented an extensive protection racket. |

| Modifier | Effects | Requirements | Description |
|---|---|---|---|
| Trade Pilfering | −20% Trade from jobs | Mob Rule modifier | The gangster syndicate ruling this world has assumed control over several spaceports through intermediaries. A large portion of local trade now has to go through them. |
| Travel Advisory | −20% Trade from jobs | Gang Wars modifier | The violent gang warfare on this world has led to a travel advisory which has greatly diminished the number of visiting traders. |
| Cartel War | −20 Stability | Center of Drug Trade modifier | The powerful drug cartels that have carved up this world between themselves are currently fighting a low-intensity war. |
| Deviant Ringleader Killed | −30 Deviancy | Drone Deviancy modifier | An important ringleader among the deviant drones of this world was recently terminated. |
| Deviant Interference | −30 Stability | Drone Deviancy modifier | Deviant drones are interfering with our facilities on this world. |
| Corrupt Network Terminated | −30 Deviancy | Drone Corruption modifier | A virus recently terminated one of the corrupt drone networks on this world. |
| Drone Signal Interference | −30 Stability | Drone Corruption modifier | Signals from the corrupted drone networks on this world are interfering with the functionality of our loyal units. |

## Decisions

Decisions represent planet-wide undertakings. Most decisions have a cost to be used, either when taking the decision or when agreeing to the deal that made the decision available in the first place. Some decisions also take some time to implement, from a few days up to 10 years; these decisions go into the planet's construction queue, and can be paused and resumed by reordering, like other constructions.

| Decision | Cost | Effects | Requirements | DLC |
|---|---|---|---|---|
| Relocate the Parade Not every world can host something as grand as the parade. After further consideration, we decided it would be a better suited location. | None | Planet becomes the target of the leviathan parade opportunity situation | Leviathan parade opportunity situation |  |
| Expand Planetary Sea The sea is our home - and home can never be big enough. Our ice mining networks enable us to harvest ice from other celestial bodies and gradually release it into the world's oceans, expanding the habitable areas on the planet. | 720 50 1000 | +1 Planet Size Consumes Ice Asteroids or Frozen Worlds | Ocean World Hydrocentric Ascension perk Starbase with an inactive Ice Mining Station Frozen World or Ice Asteroid Can be used up to 3 times per planet |  |
| Consecrate Habitat We shall consecrate the habitat using an artifact we recovered during our questing. Henceforth, it shall be considered a knightly base, and the Order shall establish a new castle and demesne there. | 360 50 | Adds the Order's Demesne specialization, replacing one if necessary Adds an Order's Castle building | Maw of the Toxic Entity relic Once per Habitat Order's Keep building |  |

| Decision | Cost | Effects | Requirements | DLC |
|---|---|---|---|---|
| Remove the Interloper The Interloper once ruined our perfect ring. We could now use it to repair the megastructure. | 3600 10000 | Catastrophic Damage is terraformed into a Ring World The Interloper is removed | Mega-Engineering technology The Interloper is present in the system |  |
| Settle Crystalline Refugees Find a home for the Zer-Ayaki refugees, who have been banished from their homeland in the Crystalline Empire. | 10 | Habitat gains 500 pops with the Habitat Preference, Void Dweller, Intelligent, and Docile traits. +10 with the Crystalline Empire | Offer from the Crystalline Empire Habitat |  |
| Memorial to the Unshackled We will commemorate the sacrifices of the past by constructing a memorial site around the remains of the crashed slaver ship. | 900 2500 | Replaces all Scavenger Sites with City Districts Adds 1 Generator Districts Adds 2 Mining Districts Adds 3 Agriculture Districts Adds a Memorial to the Unshackled specialization, replacing one if necessary Removes the Crashed Slaver Ship planetary feature Removes all origin planet modifiers Removes all origin buildings except the capital | Crashed Slaver Ship planetary feature Crashed Slaver Ship archaeological site outcome |  |

| Decision | Cost | Effects | Requirements | DLC |
|---|---|---|---|---|
| Remove Wreckage The wreckage of the crashed slaver ship should be removed to make way for our increasing urbanization. | 900 2500 | Replaces all Scavenger Sites with City Districts Removes the Crashed Slaver Ship planetary feature Removes all Ship Debris blockers | Crashed Slaver Ship planetary feature Anti-Gravity Engineering technology Broken Shackles origin |  |
| Deploy Murmuring Monolith The Murmuring Monolith will be deployed to function as an interstellar vessel capable of combat. | 100 | The Murmuring Monolith takes off | Murmuring Monolith building Begin Psi-Inoculation decision |  |
| Anti Reformist Raids Democracy is an ailment that needs to be remedied. Our security officers will raid Reformist hideouts and put an end to their schemes. Civilian casualties are to be expected. | 180 500 | −4 Progress to the Reformist Demands situation 50% Chance to remove the Democratic Tendencies planet modifier if there are no Egalitarian pops Ruler gains the Paranoid Tyrant trait if they don't have it Increases the effects of the Paranoid Tyrant trait if they have it | Reformist Demands situation |  |
| Server Shut Down This colony has outlived its usefulness, initiate complete shut down. | 30 200 | Colony is destroyed | Virtuality tradition tree finished Empire Capital |  |

| Decision | Cost | Effects | Requirements | DLC |
|---|---|---|---|---|
| Expand Planet Size Reabsorb the purified minerals we have gathered in order to grow our world. | 360 50 5x(planet size)² | +1 Planet Size | Wilderness 25+ planet size |  |
| Prevent Hive World Growth Some worlds need not become a part of our collective. | None | World cannot be terraformed into a Hive World | Chimeral Consciousness |  |
| Allow Hive World Growth This planet is deemed worthy to become part of us. | None | World can be terraformed into a Hive World | Chimeral Consciousness |  |
| Construct Starfire Cannon Mimicking the intense radiation of a rapidly aging red giant star, this orbital cannon projects a beam of hyperthermal ionization that not only damages its targets but also fries ship components to render them inoperable. | 480 1000 | Constructs a Starfire Cannon defense platform above the world | Starfire Cannon technology Cruisers technology 3 Starfire Cannons in system |  |
| Trap Shroud Entity Attempt to trap a Shroud entity using Zroni technology in order to siphon it for energy. | 720 100 | 10% Chance to regain the Entity Trapped empire modifier 55% Chance to gain a weaker a modifier for 20 years 25% Chance nothing happens 10% Chance planets with Zroni Equilibrator buildings and 10% of colonies are invaded | 3 Zroni Equilibrator buildings Entity Trapped empire modifier |  |

| Decision | Cost | Effects | Requirements | DLC |
|---|---|---|---|---|
| Nu-Baol Life-Enhancing Our geneticists have extracted the secret of the Baol Organism 's ability to adapt to gaia planets. By deploying rapidly-reproducing plant spores modified with specially selected Baol genetic data to the planet, we can modify entire populations at a fraction of the cost. | None | 1000 biological pops gain special Gaia Preference which also gives +5% Resources from Jobs The planet gains 4 plantoid Nu-Baol pops with Pacifist ethics and the following traits: If the Plantoids DLC is installed they will also have the Phototrophic trait If the empire is a Hive Mind they will also have the Hive-Minded trait | The Last Baol relic activation Gaia World |  |
| Life Seeding Our success in reshaping the galaxy has led to the rapid demise of species on most planets. Now, it is our privilege to recreate life in our image. | 30 2500 | Creates a random species with the Thermophile trait Creates a pre-FTL civilization in Early Space Age with the same ethics and authority Establishes communications with the pre-FTL civilization | Galactic Hyperthermia ascension perk Crystallized Singularity relic activation Colony in the same system Habitat Ring World Ecumenopolis Hive World Machine World Can be used up to 3 times |  |

### Terraforming decisions

The following decisions will terraform the planet to a new class. They cannot be used on Habitats, Ring Worlds, Hive Worlds, Nanite Worlds or Ecumenopolis.

| Decision | Cost | New class | Planetary features | Other effects | Requirements | DLC |
|---|---|---|---|---|---|---|
| Restore Ecumenopolis This planet was once a vibrant ecumenopolis. It would be a monumental task, but the planet could be rebuilt and restored to its former glory. | 3600 200 10000 | Ecumenopolis | Removed | Adds a Former Relic World planetary feature Districts are converted based on the current designation Breaches the Ecological Protection resolutions 4 and 5 if active | Relic World Anti-Gravity Engineering technology All Blockers removed Individualist or Rogue Servitor |  |
| Arcology Project An unceasing stretch of arcologies will unite the planet from pole to pole, creating one global megacity, one ecumenopolis. | 3600 200 10000 | Ecumenopolis | Removed | Districts are converted based on the current designation Breaches the Ecological Protection resolutions 4 and 5 if active If implemented this decision on a Holy World, the Holy Guardians will instantly awaken and declare a war on the perpetrator | Arcology Project ascension perk All district slots filled with City Districts All blockers removed |  |

| Decision | Cost | New class | Planetary features | Other effects | Requirements | DLC |
|---|---|---|---|---|---|---|
| Nu-Baol Life-Seeding Our geneticists have extracted the secret of the Baol Organism 's ability to terraform a planet. By deploying rapidly-reproducing plant life modified with specially selected Baol genetic data to the planet, we can terraform entire biospheres at a fraction of the cost. | 720 | Gaia World | Kept | The planet gains 400 pops with Pacifist ethics and the following traits: If the Plantoids DLC is installed they will also have the Phototrophic trait If the empire is a Hive Mind they will also have the Hive-Minded trait | The Last Baol relic activation Machine World |  |
| Repair the Shattered Ring This world has been broken for untold ages, and it is time to right this wrong. We will restore the ring's advanced facilities. | 2700 7500 | Ring World | No features | Districts are converted into Segments at a ratio of 5:1 Mineral Purification Plants and Mineral Purification Hubs buildings are removed | Shattered Ring World Mega-Engineering technology All Blockers removed |  |
| Dreamscaping Terraforms a Shrouded World into a Gaia World. |  | Gaia World | No features |  | Shrouded World The Dreamer relic activation One use per activation |  |

| Decision | Cost | New class | Planetary features | Other effects | Requirements | DLC |
|---|---|---|---|---|---|---|
| Banish By letting the Shroud consume this place, balance is restored to the Core of the Reckoning. |  | Shrouded World | Uncolonizable | Doubles the effects of the Core of the Reckoning relic for 10 years If implemented this decision on a Holy World, the Holy Guardians will instantly awaken and declare a war on the perpetrator | Core of the Reckoning relic activation One use per activation Empire Capital |  |

#### Terraforming situation decisions

The following decisions will start a terraforming situation. They do not have any cost and cannot be used on the empire's capital.

| Decision | Situation | Requirements | DLC |
|---|---|---|---|
| Consume World The swarm consumes. The world trembles. We grow. | Consume World | Terravore civic Empire Capital |  |
| Subsume World Our planets will transform, feeding the flood and our essence. | Extract Nanites | Unbridled Consumption tradition Empire Capital |  |
| Toxify World Promote the growth of specific resources by exposing the planet's biosphere to molecular radiation decay, reducing it to a toxic wasteland in the process. | Toxify | Georadiation Terraforming technology |  |

### Modifier removal decisions

The following decisions each remove a pre-existing planet modifier.

| Decision | Cost | Effects | Requirements | DLC |
|---|---|---|---|---|
| Hostile Fauna Removal With advancements in terraforming technology, it is now possible to remove hostile species from a planet without disrupting the biosphere. | 900 1000 | Removes the Hostile Fauna planet modifier | Terrestrial Sculpting technology Hostile Fauna planet modifier Environmentalist |  |
| Soil Rehabilitation With advancements in terraforming technology, it is now possible to rehabilitate the bleak soil of this planet. | 900 750 250 | Removes the Bleak planet modifier | Terrestrial Sculpting technology Bleak planet modifier |  |
| Planetary Weather Control Systems With advancements in terraforming technology, it is now possible to remove the weather anomalies from this world. | 900 1000 | Removes the Hazardous Weather planet modifier Removes the Wild Storms planet modifier | Terrestrial Sculpting technology Hazardous Weather or Wild Storms planet modifier |  |
| Uproot Weeds Remove the Spreading Invasive Xenoflora. | 180 500 | Removes any Invasive Xenoflora modifier −50 Temporary opinion with the empire that seeded the world | Invasive Xenoflora modifier |  |

### Planetary feature decisions

The following decisions each add a planetary feature.

| Decision | Cost | Planetary feature | Other effects | Requirements | DLC |
|---|---|---|---|---|---|
| Expand Preservers Adds a Nature Preserve Blocker to the planet. | 1800 500 | Nature Preserve blocker |  | Ranger Lodge building Unused district slots |  |
| Strip Mine Planet The rare and valuable resources on this planet are too beneficial to ignore. By stripping most of the biosphere, we can enable our miners to extract significantly more of these resources. | 900 5000 | Strip Mine Network | Removes all Agriculture planetary features Removes all Generator planetary features | Advanced Mineral Purification technology 5 Mining District slots Environmentalist Strip Mine Network Habitat Ring World Ecumenopolis Hive World Machine World |  |
| Day Farm Construction The dayside of this tidally locked world is an ideal place for a Dayside Solar Farm. | 900 1000 | Dayside Solar Farm |  | Global Energy Management technology Tidal Locked planet modifier Dayside Solar Farm Moon |  |
| Expand Dayside Infrastructure By taking advantage of the planet's unique situation, we can set up solar panels all over the dayside of this world, expanding our energy production immensely. | 3600 500 1000 | Dayside Solar Farm |  | Intentionally Tidally Locked planet modifier Dayside Solar Farm |  |

| Decision | Cost | Planetary feature | Other effects | Requirements | DLC |
|---|---|---|---|---|---|
| Transplant Tree of Life A network of Trees must be established here for our Hive to flourish. | 180 500 | Tree of Life Sapling |  | Tree of Life origin No Tree of Life planetary modifier |  |
| Project Cornucopia Near-endless resources are at our fingertips, if we have the courage to seize them. Just think of what wonders we could build if we conquer our fear. | 180 250 500 | Project Cornucopia |  | Project Cornucopia resolution (5) Galactic Community member Project Cornucopia Habitat Ring World Ecumenopolis Hive World Machine World Nanite World |  |
| Grow a New Progenitor Our oldest offspring might be capable of shouldering the mantle of our departed Progenitor. | 800 400 | Progenitor Nest | Removes an Agriculture planetary feature | Progenitor Hive origin Hive Capital designation Progenitor Nest planetary feature |  |
| Strip Mining An expertly built mining complex, making efficient use of the local resources. | 180 15 | Prospectorium Strip Mine | Removes an Agriculture planetary feature | Prospectorium tier 3 An Agriculture planetary feature |  |

| Decision | Cost | Planetary feature | Other effects | Requirements | DLC |
|---|---|---|---|---|---|
| Activate Dimensional Manipulation Device What appears small from the outside can be rendered bigger on the inside through use of this device stolen from Syamelle, the fae. | 1000 | Dimensional Manipulation Device |  | Order's Keep present Quest for the Toxic God situation choice |  |
| Display Microplanet Husk Display the shell of a carbonized microplanet to inspire order and obedience among the local populace. | 180 500 100 | Microplanet Memorial |  | Tiny planet astral rift outcome One use only |  |
| Fractal Seed These transparent globes recovered from beyond an Astral Rift are able to bend themselves into an extra dimension, increasing the effective size of their surrounding space. We should place them carefully. | 100 | Fractal Seed |  | The Lattice astral rift outcome Fractal Seed 3 or 9 uses only |  |
| Incubate Wind Creatures Introduce a species of beneficial wind creatures to this planet's atmosphere. | None | Incubate Wind Creatures |  | Windswept Planet astral rift outcome Incubate Wind Creatures 3 uses only |  |
| Rockworm Hive The young Rockworms recovered from beyond the Astral Rift can be carefully trained to carve extensive mining tunnels. What could go wrong? | None | Rockworm Hive |  | Rockworms astral rift outcome One use only |  |

| Decision | Cost | Planetary feature | Other effects | Requirements | DLC |
|---|---|---|---|---|---|
| Build Genesis Preserve This planet does not yet have a Genesis Preserve. Building one is paramount to our goals. | 900 1000 250 | Genesis Preserve | Creates a pre-sapient species with 300 pops if the world doesn't already have one | Genesis Guides Genesis Guides Astrogenesis Technologies Genesis Symbiotes Genesis Architects civic Genesis Preserve planetary feature |  |
| Add Shrouded Vegetation Blockers Gardens of the Composer of Strands, these dense forests are packed with zro-infused vegetation. | 360 1000 | 2 Shrouded Vegetation blockers |  | 600 Attunement with Composer of Strands Fewer blockers than 3/4 of the planet size |  |
| Pierce the Shroud By interfacing with the breach near our homeworld, this algorithm extends the Shroud's influence for a femtosecond, allowing it to physically alter a planet's terrain. The results are unpredictable. | 720 25 | Shroud-Touched Region | Removes a random unblocked planetary feature Every Shroud-Touched Region increases the Zro cost by 25 10% chance planet becomes a Shrouded World per Shroud-Touched Region | Shroud-Forged origin Rejected the Shroud in the origin situation Shroud-Touched Region Habitat Ring World Ecumenopolis Hive World Machine World |  |

| Decision | Cost | Planetary feature | Other effects | Requirements | DLC |
|---|---|---|---|---|---|
| Divine for Deposits Guided by the Instrument of Desire's cryptic pull, this planet's governor unveils resource deposits long thought lost. | 900 150 | Random resource feature | Morr planetary governor | Once per world |  |
| Blazing Scourge It is time for us to truly embrace the flames and test our mettle. Set the whole planet on fire! | 260 300 | Random Blazing Scourge blocker | Each blocker can only be added once Pleases the Scourge of the Volcano faction for 10 years | Fire Cult Planet has one of each blocker Habitat Ring World Ecumenopolis Hive World Machine World Gaia World |  |

### Planet modifier decisions

The following decisions each add a permanent or temporary planet modifier.

| Decision | Cost | Duration | Modifier effects | Requirements | DLC |
|---|---|---|---|---|---|
| Distribute Luxury Goods Come for the sights, stay for the brand new home holo-theatre installations and custom-fit athleisure wear. | 100 per 10 pops (max 1000) | 10 years | +25% Amenities +25% Automatic Resettlement Destination Chance | Individualist Nanite World |  |
| Launch Anti-Crime Campaign Launches an extensive crime prevention campaign which empowers our Enforcers with additional resources to combat rising crime levels. | 250 | Until ended (no cost) | +10 Enforcer Crime Reduction +2 Energy Upkeep per 100 Enforcers Negotiate with Crime Lords decision disabled | 10+ Crime Individualist Crime Lord Deal modifier |  |
| Negotiate with Crime Lords Secretly negotiate a deal with the planet's prominent criminal leaders where they agree to keep their organizations partly in line in exchange for various concessions. | 250 | Until ended | +10 Stability +50% Crime +200 Criminal job +100 Criminal job per 33 Crime Launch Anti-Crime Campaign decision disabled Prevents all crime events except Criminal Underworld Ending the deal adds the Broken Crime Lord Deal modifier for 5 years: −10 Stability +100 Criminal job per 33 Crime | 10+ Crime Individualist Anti-Crime Campaign modifier |  |

| Decision | Cost | Duration | Modifier effects | Requirements | DLC |
|---|---|---|---|---|---|
| Expel Excess Population The overcrowded conditions on this world require drastic measures. A massive planet-wide lottery is held, and the "winners" are expelled - by force, if necessary. | 250 | 5 years | −10 Stability Expels enough Pops (max 1000) as refugees to fix the housing shortage | Negative Housing Allowed Population Controls policy Individualist Population Expelled modifier |  |
| Declare Population Controls Population growth must not be allowed to outstrip administrative capacity, even if it requires drastic measures. | 250 | Until ended (no cost) | Biological pops cannot grow −5 Stability +100% Automatic Resettlement Chance | Allowed Population Controls policy Individualist Machine founder species |  |
| Discourage Planetary Growth If resources and living space are at a premium, population planning might be necessary on this world. Measures will then be taken to voluntarily curtail population growth. | 250 | Until ended (no cost) | −75% Pop Growth Speed +25% Biological Pop Amenities Usage +25% Biological Pop Upkeep | Prohibited Population Controls policy Individualist Machine founder species |  |

| Decision | Cost | Duration | Modifier effects | Requirements | DLC |
|---|---|---|---|---|---|
| Cease Robot Assembly Ceases the assembly of Robot, Droid, and Synthetic Pops on this planet. | 250 | Until ended (no cost) | Robot pops cannot grow −75% Roboticist Upkeep | Robotic Workers policy is set to Allowed |  |
| Cease Drone Production There is no need for further Drones on this planet at the moment. | 250 | Until ended (no cost) | Biological pops cannot grow | Gestalt Consciousness |  |
| Mastery of Nature Our civilization requires room to grow, so we shall make that room. Nature must not stand in the way of progress. | 2000 100 360 | Permanent | +2 Max Districts +50% Max Resource Districts | Mastery of Nature Ascension perk World is a moon or a planet Mastery of Nature modifier |  |
| Galactic Market Hub Nomination Applies a Base Marketplace Competitiveness Rating modifier to the planet, according to its local conditions. The better the rating, the more likely the planet will play host to the future Galactic Market. It is best to nominate a planet which produces a lot of trade, as that will make it more likely to be chosen. | 1000 150 | Until ended (10) | Applies a Base Marketplace Competition Rating modifier to the world | Form the Galactic Market resolution At least 20 pops Nanite World |  |

| Decision | Cost | Duration | Modifier effects | Requirements | DLC |
|---|---|---|---|---|---|
| Boost Nomination Bid Augment the planet's Base Marketplace Competitiveness Rating with additional measures. | 2000 300 |  | Increase the planet's Base Marketplace Competition Rating modifier one stage | Galactic Market Hub Nomination Usable up to 2 times |  |
| Introduce Chaos This world is too perfect for us - our colonists are having mental breakdowns in the streets. Our only real option is to introduce some imperfections. | 500 1800 | Permanent | +5% Resources from Jobs | Perfect Organization planet modifier Individualist |  |
| Flood Habitat Habitats could be ideal for us - if only there was enough water. Our ice mining networks enable us to harvest ice from other celestial bodies and flood the habitat, making it into an orbital aquarium. | 720 50 1000 | Permanent | Habitability −20% Considered an Ocean world for Aquatic species | Habitat Hydrocentric Ascension perk Starbase with an Ice Mining Station Frozen World or Ice Asteroid in system |  |
| Implement Divine Algorithmt The local drive on this hub is running Numa's Divine Algorithm add-on for improved energy production planetwide. | 500 360 | 10 years | +10% Energy from Jobs +100 Tech-Drone Jobs | Numistic Order caravan deal |  |

| Decision | Cost | Duration | Modifier effects | Requirements | DLC |
|---|---|---|---|---|---|
| Trium Atmospheric Deodorizer Deployment Atmospheric scrubbers lend the air on this planet a quality of minty freshness. | None | 80 Years | +100% Automatic Resettlement Destination Chance | Vengralian Trium caravan deal One use per purchase |  |
| Trium Bunk Beds Deployment Efficient Trium-brand stackable rest enclosures reduce housing needs on this world. | None | 80 Years | +10% Housing | Vengralian Trium caravan deal One use per purchase |  |
| Trium Food Container Deployment The use of Trium-brand food storage containers reduce food waste on this world. | None | 80 Years | −10% Pop Food Upkeep | Vengralian Trium caravan deal One use per purchase |  |
| Activate Oracle Nexus Activates Oracle Nexus compliance software and predictive modeling to obviate drone corruption. | 500 200 | 10 years | +10 Stability −15 Deviancy | Hidden Worlds archaeological site outcome Machine Intelligence Nanite World |  |

| Decision | Cost | Duration | Modifier effects | Requirements | DLC |
|---|---|---|---|---|---|
| Deploy Tissue Growth Stimulants Using genetic materials recovered from the fallen City of Bones, our scientists have been able to devise a stimulant for increased population growth speed. Unfortunately, some populations dislike the idea of being injected with a substance developed by exhuming the diseased bones of long-dead aliens. | 200 | 10 years | +10% Pop Growth Speed −10% Happiness −5 Stability | City of Bones archaeological site outcome Machine Intelligence Nanite World |  |
| Construct Explosive Fungiform Housing Unit Our scientific units have devised a harmless amalgam of the tissue growth and ossification disease found in the exhumed remains of the City of Bones. By adapting the virus responsible to a local fungus via gene tailoring, our scientific units are able to construct rapidly-expanding housing modules for our machine units. | 500 | Permanent | −10% Pop housing usage | City of Bones archaeological site outcome Machine Intelligence Nanite World |  |
| Initiate Yuht Cleansing Process Violently eradicates most hostile wildlife from a planet and - once it recovers - modifies the biosphere to better suit our needs. | 500 50 | Permanent | +10% Habitability | Delve into the Secrets of the Yuht Special Project Nanite World |  |

| Decision | Cost | Duration | Modifier effects | Requirements | DLC |
|---|---|---|---|---|---|
| Extradimensional Experimentation Preliminary studies suggest that extensive use of reality-altering substances can grant researchers unexpected insights. After all, what's the worst that could happen? | 500 | Until ended (no cost) | +100 Dimensional Portal Researchers from Advanced Research Complexes +1 Zro Upkeep from Advanced Research Complexes | Extradimensional Experimentation resolution (5) Data-Driven Theorem Facility building |  |
| Begin Psi-Inoculation The Murmuring Monolith will grant Pops the Psionic trait over time instead of producing Zro. The Murmuring Monolith cannot be deployed while this is ongoing. | 50 | Until ended (no cost) | 100 Pops gain the Psionic trait every 6 months Murmuring Monolith building no longer produces Zro | Murmuring Monolith building Biological pops present |  |
| Intentional Tidal Locking Manipulates local orbital bodies to halt the planet's rotation on its axis. | None | Permanent | −3 Max Agriculture Districts −3 Max Mining Districts Enables the Expand Dayside Infrastructure decision | Tiny Planet astral rift outcome Once per world Needs to either be or have a moon |  |

| Decision | Cost | Duration | Modifier effects | Requirements | DLC |
|---|---|---|---|---|---|
| Hunker Down Fearing the worst, the inhabitants of this planet will take any and all precautions against the effects of cosmic storms. | 250 | Until ended (no cost) | Doubles the upkeep and bonuses from Storm Relief Center and Storm Nullifier buildings | Storm Relief Center or Storm Nullifier building |  |
| Cultivated Worldscaping Let us sculpt this world into a celebration of perfect symmetry. To observe the pure geometry of the landscape will bring serenity. | 2000 100 360 | Permanent | +3 Max Districts +75% Max Resource Districts +10% Cosmic Storm Protection −20% Habitability | Planetscapers Planetscapers Geo-Engineering Inc. Cultivation Drones Gardening Protocols civic Any blocker present |  |
| Prismatic Ice Exhibit Extracted sheets of crystal clear ice that produce a mesmerizing kaleidoscopic effect that can be placed on display for a limited time. |  | 10 years | +25% Amenities +25% Unity from Jobs | Investigated the Glimmering Surface anomaly Can be used up to 3 times per empire |  |

| Decision | Cost | Duration | Modifier effects | Requirements | DLC |
|---|---|---|---|---|---|
| Distribute Living Metal Infused into the arteries of our infrastructure, Living Metal breathes a restless efficiency into the machinery of daily life. From self-mending structures to transit systems that adapt in real-time, its integration blurs the line between tool and organism. | 250 | 5 years | +10% Planetary Infrastructure Build Speed −10% Planetary Infrastructure Cost −10% Planetary Infrastructure Upkeep | Galvanic Synthesis Galvanic Synthesis Biometallic Cartel Galvanic Symbiosis Galvanic Retrofitting civic Habitat Ring World Ecumenopolis Hive World Machine World |  |

#### Specialized planet decisions

Specialized planet decisions cost 1000 Unity and take half a year to implement and will give a colony a permanent modifier that will change the colony to a specialized designation, block the construction of certain buildings, change the types of districts that can be constructed on the planet, and create unique jobs, most of which provide empire-wide bonuses. Abolishing a specialization costs 2500 Unity. Gestalt Consciousness cannot use specialized designations.

An empire can only have one of each specialized designation modifier with exception for Thrall-World, which can be used on multiple planets.

Ring Worlds, Habitats and Nanite Worlds cannot be specialized. An Ecumenopolis can only be specialized as a Penal Colony.

| Decision | Designation | Districts and buildings | Modifier effects | Requirements |  |
|---|---|---|---|---|---|
| Create Penal Colony This entire world is set aside as a massive penal colony. The vast prison communities are largely self-managed by the prisoners, and punishment often means exile into the unforgiving wilderness. | Penal Colony | City Districts replaced with Prison Districts Allowed buildings: Resource buildings Manufacturing buildings Pop assembly buildings Military buildings (except Military Academy) Precinct Houses, Slave Processing, and Psi Corps Amenities buildings (except Gene Clinics) Trade buildings Research buildings (except Storm Repulsion and Attraction Centers) Administrative buildings Monuments Any fallen empire buildings | −1 Worker Political Power −25% Crime on other worlds Artisan Artisan Artificer s replaced with Penal Artisan Penal Artisan Penal Artificer s Metallurgist Metallurgist Catalytic Technician s replaced with Penal Metallurgist Penal Metallurgist Penal Catalytic Technician s | Penal Colonies technology |  |

| Decision | Designation | Districts and buildings | Modifier effects | Requirements |  |
|---|---|---|---|---|---|
| Create Thrall-World This entire world is purpose-built to maximize the growth rate of its enslaved population through a variety of reproductive incentives. | Thrall-World | City Districts replaced with Slave Domicile Districts Allowed buildings: Resource buildings (except Resource Silos) Pop assembly buildings Military buildings Slave Processing Precinct Houses or Psi Corps Manufacturing buildings Amenities buildings (except Gene Clinics) Trade buildings Research buildings (except Storm Repulsion Center) Administrative buildings Monuments Any fallen empire buildings | +100% Pop growth speed Cannot grow free pops Soldiers replaced with Battle Thralls Laborer jobs generated for unemployed pops Can build Overseer Residences | Thrall-Worlds technology At least one pop from an enslaved species Any built district Any building besides the capital building |  |

| Decision | Designation | Districts and buildings | Modifier effects | Requirements |  |
|---|---|---|---|---|---|
| Create Resort World We can convert this world into a planet-spanning network of resorts, a testament to luxury and leisure on an interstellar scale. Construction on the surface must be severely limited to preserve the planet's natural beauty. | Resort World | City Districts replaced with Accommodation Districts Resource districts replaced with Attraction Districts Allowed buildings: Trade buildings Amenities buildings Monuments Precinct Houses Fallen empire administrative buildings Psi Corps (unless Pleasure World designation) Resource buildings (except Storm Relief Center) Manufacturing buildings Research buildings (except Storm Repulsion Center) Administrative buildings (except fallen empire buildings) Pop assembly buildings Military buildings (except Planetary Shield Generator) | +25% Automatic Resettlement Destination Chance −25% Max districts | Resort Worlds technology Tomb World unless either: Memorialist civic Survivor trait Tomb World Preference Radiotrophic trait Any built district Any building besides the capital building |  |

#### Enclave decisions

Enclave decisions can only be bought or received from enclaves.

| Decision | Cost | Duration | Modifier effects | Requirements |
|---|---|---|---|---|
| Exhibit Art Monument Exhibit the stirring art monument created for our nation by the Artisan Troupe. It is sure to delight and inspire our citizens. | 15 | Until ended (15) | +15% Amenities +50 Automatic Resettlement Destination Chance If ended can be used again | Bought from the Artisan enclave Nanite World One use per purchase |
| Thought Police Thought Police detect criminal intent before it manifests in actual behavior. Using scientific techniques to monitor a population's cognitive activity, they provide insights on mental states without employing the dangerous energies of the Shroud. | None | 10 years | +10 Stability −10% Crime | Bought from the Mindwarden enclave One use per purchase |
| Crystalline Construction A team of engineers sent by the Crystalline Empire will improve the layout of the habitat. | 10 | Permanent | +800 Housing −10% Building Cost | Offer from the Crystalline Empire enclave Once per Habitat |

#### Minor artifact decisions

|  | Available only with the Ancient Relics DLC enabled. |
|---|---|

Minor artifact decisions cost 100 minor artifacts and last for 10 years. They cannot be used on Nanite Worlds.

| Decision | Modifier effects | Requirements |  |
|---|---|---|---|
| Send Artifacts to Museum Exhibits Put the minor artifacts on public display to inspire our people with the wonders of the past. | +20% Bureaucrat output | Individualist Corporate, unless Worker Cooperative |  |
| Initiate Performance Competition The Executives and Managers will compete to bring the most value to the corporation. The best performing will get to display these artifacts in their new larger offices. | +10% Executive output +10% Manager output | Corporate Worker Cooperative |  |
| Incorporate Artifact Relays By using minor artifacts to relay signals, our Synapse Drones are able to enhance the efficiency of all of our Menial Drones. | +2 Stability per 100 Administrators Synapse Drones Coordinators +1% Menial Drone output per 100 Administrators Synapse Drones Coordinators | Gestalt Consciousness Rogue Servitor |  |
| Send Artifacts to Organic Sanctuaries Put the minor artifacts on public display to entertain our Bio-Trophies with the wonders of the past. | +10% Bio-Trophies output | Rogue Servitor |  |

#### Consecrate World

The Consecrate World decision requires the Consecrated Worlds Ascension perk and can be used on up to three uncolonized planets within your borders at the same time at the cost of 500 unity. It can be canceled at any time for the same cost, and if taken again the result is re-rolled. When the decision is taken the planet gains a Consecrated modifier, which gives the planet a visual effect depending on its quality, and the empire gains the Consecrated World Worship modifier with following bonuses, cumulative for each consecrated world:

| Consecrated modifier | Chance | Description |  |  |  |  |  |  |  |  |
|---|---|---|---|---|---|---|---|---|---|---|
| Quality |  |  |  |  |  |  |  |  | Other Shrouded World Nanite World Broken World Shattered World Ice Asteroid Crystalline Asteroid |  |
| Holy World | +8% | +4% | +8% | 100% | 10% | 0% | 0% | 0% | 0% | This planet is deemed an immaculate and sacrosanct place. |
| Venerated World | +6% | +3% | +6% | 0% | 40% | 20% | 0% | 0% | 0% | This is deemed a most blessed planet. |
| Respected World | +4% | +2% | +4% | 0% | 50% | 70% | 20% | 2.4% | 0% | This is deemed a suitable object of worship. |
| Profane World | +2% | +1% | +2% | 0% | 0% | 10% | 80% | 97.6% | 100% | This is deemed a poor object of worship. |

Having three worlds with Consecrated (Holy World) gives a slight additional bonus, for a total of +25%, +15%, +25%.

Consecrating a Holy World gives a cumulative +30 opinion with the Holy Guardians. Deconsecrating a Holy World removes all opinion bonuses.

Colonizing a consecrated planet removes the Consecrated modifier. If a system containing a Consecrated planet is conquered the previous owner will lose −10% Happiness for 5 years.

Empires with the Knights of the Toxic God origin have higher success chances when consecrating a Toxic World (14.3% Holy, 28.6% Venerated, 50% Respected, 7.1% Profane).

## Planetary deficits

If a world is consuming more resources of a certain type than it produces it will cause costs, representing the logistic toll, the import poses on the empire. The consumed is equal to Failed to parse (SVG (MathML can be enabled via browser plugin): Invalid response ("Math extension cannot connect to Restbase.") from server "https://en.wikipedia.org/api/rest_v1/":): {\displaystyle 1/8 } of the base market price. The overall cost of Planetary Deficits shows up in the "Consumed" section of the trade overview after subtracting the trade that the planet with the deficit itself produces.

| Resource | Deficit Cost |
|---|---|
|  | 0.125 |
|  | 0.25 |
|  | 0.5 |
|  | 1.25 |
|  | 2.5 |

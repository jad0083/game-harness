# Console commands
Source: https://stellaris.paradoxwikis.com/Console_commands
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260829221101 (the live wiki blocks non-browser clients). Page version banner: Version This article has been verified for the current PC version (4.4) of the game._

If you want to contribute to this page, which is a work in progress, in the console type "help" to see the list of commands, then to see a description and parameter of a command, type "help [command-name]", and put the corresponding details into the list.

This page deals with commands used in the console. For the modding term, see effects.

This page lists the codes which may be input into the console window, a special debugging window which may be accessed on non-ironman games by pressing Shift+2, ALT+2+1, Shift+3, §, ~, ^, °, ², or ` (key varies based on keyboard layout). For a QWERTY keyboard, the key is `. Else, try pressing Shift + Alt + C if none of the above worked. Press the up or down arrow keys to traverse through previously executed commands. Many codes can be turned off by repeating the command, but sometimes reloading the save or exiting the game is necessary. The console also comes with menus and buttons for the most common commands. Using any console command will disable achievements.

## IDs

Most IDs are predefined and can be found on the ID page. Species, leader, empire and pop IDs however are defined when the game is created and have to be found with the debugtooltip command.

- Species IDs can be read by hovering over a species in the species menu. Unless the starting system or galaxy were modded, the player's species will always be 1 for the founder species and 2 for the syncretic/cyborg/bio-trophy/prepatent species.
- Leader IDs can be read by hovering over a leader in the leaders or empire menus. Unless the starting system or galaxy were modded, the player's starting ruler will always be 0.
- Empire IDs can be read by hovering over an empire's flag in the contacts menu or its borders on the galaxy map. Unless the starting system or galaxy were modded, the player's empire will always be 0.
- Ship IDs can be read by hovering over a ship in the fleet window. Unless the starting system or galaxy were modded, the player's starting science ship will always be 0.
- Pop IDs can be read by hovering over a pop in the population tab. Alternatively using the add_pops command empty will list all pop IDs. Unless the starting system or galaxy were modded, the player's pops will always be 0 to 32.

Trait IDs can also be found by hovering over the trait in the debug window.

## Cheats

Cheats are console commands that can be used to give unfair advantages as opposed to sole testing purposes.

| Command | Effect | Parameters | Example |
|---|---|---|---|
| activate_all_traditions | Activates all traditions NOTE: DLC traditions will be added but most will have no effects without the required DLC | None | activate_all_traditions |
| activate_ascension_perk | Activates the specified ascension perk, pressing tab reveals all IDs | [AP id] | activate_ascension_perk ap_mind_over_matter |
| activate_gateways | Activates all gateways in the galaxy | None | activate_gateways |
| activate_relic | Activates the triumph effect of [relic id] | [relic id] | activate_relic r_unbidden_warlock |
| activate_tradition | Activates the specified Tradition, pressing tab reveals all IDs including tree adoption | [tradition id] | activate_tradition tr_prosperity_sct |
| add_anomaly | Adds the specified anomaly to the selected celestial object, pressing tab reveals all IDs | [anomaly id] | add_anomaly life_asteroid_category |
| add_first_contact_clues | Adds [amount] of insights for the currently opened first contact, default 10 | [amount] | add_first_contact_clues 5 |
| add_intel | Adds [amount] of intel towards [target], default 10 | [target] [amount] | add_intel 1 100 |
| add_loyalty | Adds [amount] of loyalty from [target], default 10 | [target] [amount] | add_loyalty 1 50 |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| add_opinion | Increases the [source] empire's Opinion of the [target] empire by [amount], default 40 | [source] [target] [amount] | add_opinion 1 0 100 |
| add_pops | Creates [amount] of pops from [species id] on the selected celestial object, entering without ID reveals all species IDs | [species id] [amount] | add_pops 0 5 |
| add_relic | Grants [relic id], pressing tab reveals all IDs and writing all instead of the ID grants all relics. Same relic can be added multiple times. NOTE: Cybrex War Forge will not work correctly the first time it's activated if added this way | [relic id] | add_relic r_unbidden_warlock |
| add_ship | Creates a fleet with one ship of [design name], pressing tab reveals the NPC ship names NOTE: Spawned juggernauts will not be able to build, upgrade or repair ships | [design name] | add_ship Avatar |
| add_spynetwork_value | Adds [amount] of infiltration progress on [target] | [target] [amount] | add_spynetwork_value 1 1000 |
| add_time | Adds [amount] of [unit] time, valid units are days, months and years WARNING: Leader age will be affected too, potentially killing them | [unit] [amount] | add_time years 10 |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| add_trait_leader | Adds [trait id] to [leader id], entering only the leader ID reveals all trait IDs for that class, opposite traits cannot be added | [leader id] [trait id] | add_trait_leader 1 leader_trait_gale_speed |
| add_trait_species | Adds [trait id] to [species id] | [species id] [trait id] | add_trait_species 5 intelligent |
| add_trust | Increases the [source] empire's Trust of the [target] empire by [amount], default 10 | [source] [target] [amount] | add_trust 1 0 100 |
| advance_council_agenda | Adds [amount] of progress to the council agenda, entering without an amount readies the agenda for launch | [amount] | advance_council_agenda 1000 |
| ai | Toggles the AI on or off | None | ai |
| alloys | Adds [amount] of Alloys, default 5000 | [amount] | alloys 500 |
| annex | Takes control of all worlds and starbases of target | [target] | [annex] 3 |
| break_fleet_contract | Returns the selected leased fleet to its original owner | None | break_fleet_contract |
| cash | Adds [amount] of Energy Credits, defaults 5000 | [amount] | cash 500 |
| colonize | Starts the colonization process of the selected celestial object using a copy of the pop with the ID given, uncolonizable celestial objects will not make colonization progress | [colonizer pop id] | colonize 1 |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| communications | Establishes communications with all empires and enclaves and the Shroud | None | communications |
| complete_first_contact | Completes the selected first contact WARNING: Will not receive any rewards if used on space fauna | None | complete_first_contact |
| complete_focus_task | Completes the empire focus task number [task number] | [task number] | complete_focus_task 1 |
| complete_focus_tasks | Completes all current empire focus tasks | None | complete_focus_tasks |
| contact | Starts first contact with all empires | None | contact |
| create_megastructure | Creates a Megastructure in the current system, pressing tab reveals the IDs NOTE: Settled and nomadic empires can't create megastructures exclusive to the other NOTE: Orbital Rings cannot be correctly spawned | [megastructure id] | create_megastructure gateway_final |
| create_navy | Creates a fleet using your most recent designs that uses [amount] percentage of Naval Capacity, 1 means 100% | [amount] | create_navy 0.5 |
| damage | All ships in the selected fleet take [amount] hull damage | [amount] | damage 100 |
| debug_nomen | Toggles AI empires always refusing player proposals | None | debug_nomen |
| debug_yesmen | Toggles AI empires always agreeing to player proposals | None | debug_yesmen |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| effect add_awareness = | Adds [amount] of awareness, must select a pre-FTL civilization in the diplomacy menu to work | [amount] | effect add_awareness = 10 |
| effect add_building = | Adds [building id] to the primary zone of the selected celestial object | [building id] | effect add_building = building_fe_dome |
| effect add_deposit = | Adds [deposit id] resource deposit or planetary feature to the selected celestial object | [deposit id] | effect add_deposit = d_arid_highlands |
| effect add_planet_devastation = | Adds [amount] of Devastation to the selected celestial object, negative values lower it | [amount] | effect add_planet_devastation = 10 |
| effect add_situation_progress = | Adds [amount] of progress to the selected situation | [amount] | effect add_situation_progress = 20 |
| effect country_add_ethic = | Adds [ethic id] to the player empire, using more than 3 ethic points will remove lowest attraction ethics | [ethic id] | effect country_add_ethic = ethic_spiritualist |
| effect country_remove_ethic = | Removes [ethic id] from the player empire | [ethic id] | effect country_remove_ethic = ethic_spiritualist |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| effect create_archaeological_site = | Adds [archaeological site id] to the selected celestial object, writing random creates a random archeological site | [archaeological site id] | effect create_archaeological_site = lithoids_digsite |
| effect destroy_fleet = this | Destroys the selected fleet | None | effect delete_fleet = this |
| effect destroy_situation = this | Ends the selected situation | None | effect destroy_situation = this |
| effect enrage_behemoth | Selected fleet, starbase or world becomes hostile to everyone for 6 months | None | effect enrage_behemoth |
| effect force_add_civic = | Adds [civic id] to the player empire, origins can be added too but incompatible civics and origins will remain inactive NOTE: Will not work if something is selected | [civic id] | effect force_add_civic = civic_corporate_dominion |
| effect force_remove_civic = | Removes [civic id] to the player empire NOTE: Will not work if something is selected | [civic id] | effect force_remove_civic = civic_meritocracy |
| effect remove_ascension_perk = | Removes [AP id] | [AP id] | effect remove_ascension_perk = ap_detox |
| effect remove_deposit = | Removes [deposit id] resource deposit or planetary feature to the selected celestial object | [deposit id] | effect remove_deposit = d_arid_highlands |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| effect remove_megastructure = this | Removes the selected megastructure | None | effect remove_megastructure = this |
| effect remove_modifier = | Removes [modifier id] from the selected celestial object, or empire if none is selected | [modifier id] | effect remove_modifier = holy_planet |
| effect set_origin = | Replaces the origin of the player empire with | [origin id] | effect set_origin = origin_fallen_empire |
| effect shift_ethic = | Shifts the player empire's ethics to [ethic id] NOTE: Will not work if something is selected | [ethic id] | effect shift_ethic = ethic_fanatic_spiritualist |
| effect destroy_colony | Decolonizes the selected world | None | effect destroy_colony |
| election | Starts a ruler election | None | election |
| end_senate_session | Passes/fails the currently voted resolution | None | end_senate_session |
| engineering | Adds [amount] of Engineering tech points, default 5000 | [amount] | engineering 500 |
| event | Triggers [event id], worlds can be selected manually but ships require [target id] | [event id] [target id] | event anomaly.1 0 |
| federation_add_experience | Adds [amount] of Experience to the Federation, default 1000 | [amount] | federation_add_experience 1200 |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| federation_add_cohesion | Adds [amount] of Cohesion to the Federation, default 200 | [amount] | federation_add_cohesion 10 |
| federation_add_cohesion_speed | Adds [amount] of Monthly Cohesion to the Federation, default 10 | [amount] | federation_add_cohesion_speed 10 |
| federation_examine_leader | Triggers a Federation succession | None | federation_examine_leader |
| finish_arc_stage | Finishes the current chapter of an archaeological site, requires selecting its celestial object and a science ship excavating it | None | finish_arc_stage |
| finish_research | Finishes all active research and special projects | None | finish_research |
| finish_special_projects | Finishes all special projects | None | finish_special_projects |
| finish_terraform | Finishes all terraforming processes | None | finish_special_projects |
| food | Adds [amount] of Food, default 5000 | [amount] | food 500 |
| force_integrate | Integrates [target] empire into the player's empire, will not work if on integration cooldown | [target] | force_integrate 2 |
| force_senate_vote | Ends the current senate recess | None | end_senate_session |
| free_government | Toggles allowing player to change governments without the time limit and ignores civics restrictions | None | free_government |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| free_policies | Toggles allowing player to change policies and species rights without restriction, including policies previously disabled | None | free_policies |
| grow_pops | Runs pop growth/assembly/decline monthly update on selected planet | None | grow_pops |
| hire_all_leaders | Hires all leaders in the leader pool | None | hire_all_leaders |
| influence | Adds [amount] of Influence, default 5000 | [amount] | influence 500 |
| instant_build | Toggles instantly finishing constructions and upgrades and resource storage becomes unlimited WARNING: This also applies to AI empires | none | instant_build |
| instant_specialization_conversion | Toggles instantly converting specialized subjects | none | instant_specialization_conversion |
| intel | Gives sight of the entire galaxy | None | intel |
| invincible | Player ships will not take damage | None | invincible |
| kill_country | Kills [empire id], if no ID is entered than the player's empire | [empire id] | kill_country 2 |
| max_resources | Fills all resource storages | None | max_resources |
| minerals | Adds [amount] of Minerals, default 5000 | [amount] | minerals 500 |
| observe | Switches to observer mode, use the play command to revert control WARNING: If the game is unpaused in observer mode the AI will take control of the player empire | None | observe |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| own | Take ownership and control of the selected fleet, starbase or planet, or if none is selected takes ownership of the planet ID given as an argument. Uncolonizable celestial objects will be created as colonies but have no construction menu. | [planet id] | own |
| physics | Adds [amount] of Physics tech points, default 5000 | [amount] | physics 500 |
| planet_ascension_tier | Changes the ascension tier of the selected celestial object to [amount], can go above regular values | [amount] | planet_ascension_tier 3 |
| planet_class | Changes the selected celestial object to [celestial object id] WARNING: If no celestial object is selected everyting in the galaxy will be terraformed | [planet class id] | planet_class pc_arid |
| planet_happiness | Adds a modifier with [amount] Happiness to the selected planet, default 100 | [amount] | planet_happiness 25 |
| planet_size | Changes the Size of the selected celestial object, can go above regular sizes but above 78 will move the celestial object backwards | [size] | planet_size 30 |
| play | Switches player control to empire [empire ID] | [empire ID] | play 2 |
| random_ruler | Replaces the empire ruler with a new random one | None | random_ruler |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| remove_trait_leader | Removes [trait id] from [leader id], entering only the leader ID reveals the name for all current traits. | [leader id] [trait id or index] | remove_trait_leader 1 leader_trait_gale_speed |
| remove_trait_species | Removes [trait id] from [species id] | [species id] [trait id] | remove_trait_species 5 intelligent |
| research_all_technologies | Instantly researches all non-repeatable technologies. Add 1 for space creatures and crisis techs too. Add a second number for [amount] of repeatable technologies. NOTE: Galactic Archivism technology can only be added after acquiring a specimen NOTE: Space fauna technologies can only be added after encountering space fauna | [boolean] [amount] | research_all_technologies 1 5 |
| research_technology | Instantly research [technology id] NOTE: Space fauna technologies can only be added after encountering space fauna | [technology id] | research_technology tech_automated_exploration |
| resource | Adds [amount] of [resource], default 5000 | [amount] [resource] | resource consumer_goods 1000 |
| skills | Adds [amount] of skill levels to every leader hired by the player, default 1 | [amount] | skills 9 |
| skip_agreement_cooldowns | Toggles allowing the change of subject terms of agreement without cooldown | none | skip_agreement_cooldowns |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| skip_federation_cooldowns | Toggles allowing the change of federation laws without cooldown | none | skip_federation_cooldowns |
| skip_galactic_community_cooldowns | Toggles allowing the proposition of resolutions from the same group without cooldown | none | skip_galactic_community_cooldowns |
| society | Adds [amount] of Society tech points, default 5000 | [amount] | society 500 |
| survey | Surveys all celestial objects, requires at least one science ship | None | survey |
| techupdate | Re-rolls the current available tech choices | None | techupdate |
| unity | Adds [amount] of Unity, default 500 | [amount] | unity 5000 |
| unlock_edicts | Unlocks all edicts | None | unlock_edicts |
| update_leader_pool | Refreshes the leader pool | None | update_leader_pool |
| branchoffice | Create or take control of the branch office on the selected world | None | branchoffice |
| minor_artifacts | Adds [amount] of Minor Artifacts, default 5000 | [amount] | minor_artifacts 100 |
| menace | Adds [amount] of Menace, default 5000 | [amount] | menace 1000 |
| imperial_authority | Adds [amount] of Imperial Authority, default 10 | [amount] | imperial_authority 20 |
| add_subject_xp | Adds [amount] of specialized subject experience to [target], default 10 | [target] [amount] | add_subject_xp 1 1000 |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| effect unlock_council_slots = 1 | Unlocks a council slot | None | effect unlock_council_slots = 1 |
| astral_threads | Adds [amount] of Astral Threads, default 5000 | [amount] | astral_threads 100 |
| finish_rift_stage | Finishes the current chapter of the selected astral rift | None | finish_rift_stage |
| set_completed_rifts | Sets the number of completed Astral Rifts to [amount] | [amount] | set_completed_rifts 2 |
| spawn_astral_rift | Spawns [astral rift id] in the current system or a random one if none is entered, pressing tab reveals all IDs None: The Crystal Rift will require using event astral_planes.45 after exploring to continue | [astral rift id] | spawn_astral_rift station |
| advanced_logic | Adds [amount] of Advanced Logic, default 5000 | [amount] | advanced_logic 1000 |
| add_specimen | Adds a specimen, pressing tab reveals all IDs while writing random adds a random specimen | [specimen id] | add_specimen advisor_core |
| add_to_vivarium | Adds a copy of the selected space fauna fleet to the Vivarium | None | add_to_vivarium |
| add_psionic_aura_intensity | Changes the system's psionic aura intensity by [amount] | [amount] | add_psionic_aura_intensity 100 |
| create_patron_relation | Makes contact with [patron id] | [patron id] | create_patron_relation the_eater_of_worlds |

| Command | Effect | Parameters | Example |
|---|---|---|---|
| skip_accord_cooldowns | Resets the covenant power cooldown | None | skip_accord_cooldowns |
| skip_calling_cooldowns | Resets the calling replace cooldown | None | skip_calling_cooldowns |
| skip_delve_cooldown | Resets the Shroud delve cooldown NOTE: Only works in Shadows of the Shroud, for the base base game use event utopia.3000 | None | skip_delve_cooldown |
| max_patron_relation | Forms a covenant with [patron id], if one already exists it gets replaced NOTE: Only works in Shadows of the Shroud, not with the base game alone | [patron id] | max_patron_relation the_eater_of_worlds |

### List of major events

| ID | Major event | Notes | Required selection |
|---|---|---|---|
| akx.8888 | The Horizon Signal | Can start the Horizon Signal event, selected ship must have a leader and be in a black hole system | Ship |
| anomaly.95 | Voyager 1 | Can start the Solar Coordinates event if the Sol system exists somewhere in the galaxy | Ship |
| anomaly.186 | Limbo | With the right technology and AI policies you can resurrect them as a new colony or as a new empire | Ship |
| anomaly.2523 | Gigantic Skeleton | Gain a Skeletal Giant army | Ship |
| anomaly.3085 | The Prince | Event with small but permanent opinion effects | Ship |
| colony_mod.101 | Titanic Life Study: Success | Allows the recruitment of Titanic Beast armies | Planet |
| crisis.50 | Rise of the Sentinels | Doesn't require the crisis but will add its sound effects | None |
| crisis.71 | Sentinel Fleet Donation | Doesn't require the crisis or the Sentinels | None |
| crisis.105 | Long live the Queen! | Spawns the Domesticated Prethoryn Queen | Ship |
| crisis.2400 | Cybrex Return | Doesn't require the crisis | None |
| crisis.4550 | Star-Eater Firing | The current system is destroyed | Planet |
| fallen_empires_tasks.1 | A patronizing or machine Fallen Empire sends a random gift |  | None |
| namarian.1 | Galactic Nomads | Will not spawn if a Sentry Array is completed | None |

| ID | Major event | Notes | Required selection |
|---|---|---|---|
| precursor.98 | Vultraum Home System Located | Spawns the Vultraum Home System | None |
| precursor.598 | Yuht Home System Located | Spawns the Yuht Home System | None |
| precursor.1098 | First League Home System Located | Spawns the First League Home System | None |
| precursor.1598 | Irassian Home System Located | Spawns the Irassian Home System | None |
| precursor.2098 | Cybrex Home System Located | Spawns the Cybrex Home System | None |
| story.107 | Amoebas Pacified |  | None |
| story.207 | Crystals Pacified |  | None |
| origin.5605 | Teachers of the Shroud | Unlocks the Shroud Beacon starbase building and gives bonus opinion with the shroudwalkers | None |
| utopia.3021 | Avatar (army) |  | None |
| utopia.3190 | The Chosen One |  | None |
| utopia.3304 | Whisperers in the Void | Option to form a covenant (base game mechanics) | None |
| utopia.3305 | Composer of Strands | Option to form a covenant (base game mechanics) | None |
| utopia.3306 | Eater of Worlds | Option to form a covenant (base game mechanics) | None |
| utopia.3307 | Instrument of Desire | Option to form a covenant (base game mechanics) | None |
| syndaw.545 | A Question | Starts the AI-Related Incidents situation | Planet |

| ID | Major event | Notes | Required selection |
|---|---|---|---|
| syndaw.1000 | Machine Uprising | Requires the AI-Related Incidents situation and at least 1 robot pop | Situation |
| enclave.220 | Mercenary Garrison | Option to buy the mercenary Garrison starbase building | None |
| leviathans.322 | Patrons with Benefits | Option to buy the Ministry of Culture building | None |
| leviathans.1040 | The Infinity Equation | Rewards for defeating the Infinity Sphere, with The Machine Age it unlocks the Infinity Sphere trait | None |
| leviathans.2101 | Enigmatic Fortress Disabled | With The Machine Age it unlocks the Enigmatic Fortress trait | None |
| leviathans.3102 | Dreadnought Disabled | Rewards for defeating the Automated Dreadnought, with The Machine Age it unlocks the Ancient Dreadnought trait | None |
| leviathans.3103 | Dreadnought Repaired |  | Ship |
| marauder.85 | Mercenaries Become Available | Must be triggered multiple times for each Marauder empire | None |
| distar.137 | The Scavenger's End | Rewards for defeating the Scavenger Bot, with The Machine Age it unlocks the Scavenger Bot trait | None |
| distar.172 | Neural Symbiosis | Option to get the Brain Slug Host trait for some pops and leaders | Ship |
| distar.212 | Death of the Matriarch | Rewards for defeating the Tiyanki Matriarch, with Leviathan Transgenesis it unlocks the Polymelic trait | Ship |

| ID | Major event | Notes | Required selection |
|---|---|---|---|
| distar.260 | Wild Eukaryotes | Creates a pre-sapient species with the Docile Livestock trait on the world | Planet |
| distar.1001 | Paradise Lost | Creates a nearby system with a Gaia World and a Stone Age primitive civilization | None |
| distar.1081 | Azizians | Option to enable the recruitment of Azizian armies on a random owned world | None |
| distar.2050 | Alien Entity | Spawns the Enigmatic Cache in the galaxy | None |
| distar.3014 | The Nivlac (unfriendly) | Creates an empire with a permanent -100 opinion modifier | None |
| distar.3016 | The Nivlac (friendly) | Creates an empire with a permanent +100 opinion modifier | None |
| distar.3055 | Alien Box Opened | Gain one of three free traits | None |
| distar.5006 | The Voidspawn | The selected celestial object is turned into a cracked world from where a Voidspawn hatches | Planet |
| distar.5012 | Gargantuan Evolution | Rewards for defeating the Voidspawn, with Leviathan Transgenesis it unlocks the Voidling trait | Ship |
| graygoo.400 | A Quiet Stroll | Encounter Gray | Ship |
| ancrel.4000 | Whispers in the Stone | Creates the Whispers in the Stone archaeology site | Planet |
| ancrel.4058 | The Sentinels | Option to gain Sentinels armies | Planet |

| ID | Major event | Notes | Required selection |
|---|---|---|---|
| ancrel.6130 | Zarqulan's Chosen | Allows colonizing Holy Worlds and gives +150 permanent opinion from Holy Guardians | None |
| ancrel.10050 | Secrets of the Yuht | Unlocks the Initiate Yuht Cleansing Process decision | None |
| aquatics.105 | Sky Dragon Vanquished | Rewards for defeating the Sky Dragon, with Leviathan Transgenesis it unlocks the Drake-Scaled trait | None |
| aquatics.120 | The Time Has Come | Option to unlock the Dragon Hatchery starbase building | None |
| paragon.241 | The Last Bud | Unlocks the Contained Ecosphere building | None |
| paragon.3001 | Arrival | Required for the following event to work | None |
| paragon.3005 | Skrand Sharpbeak Recruitment | Requires the previous event to work | None |
| astral_planes.45 | Strange Wormhole | Required after spawning The Crystal Rift with the console to continue | Fleet |
| cstorms.195 | Delve into the Secrets of the Inetian Traders | Unlocks the Hyperlane Detailer starbase building | Ship |
| grand_archive.1002 | Primal Calling Stance | Can unlock multiple stance buildings | Ship |
| bio.2030 | BioMechanical Plague | Unlocks the Warden of the Citadel council position | None |
| shroud.4045 | Whisperers in the Void | Replace a major Shroud patron with Whisperers in the Void | None |

| ID | Major event | Notes | Required selection |
|---|---|---|---|
| shroud.4205 | Mindwarden Enclave | Can interact with the Mindwardens even if psionic | None |
| shroud.4935 | Creation | Spawns a new colonized gaia world in the capital system | None |
| shroud.5012 | Secret Societies Emerge | Can get secret societies factions if the game wasn't started with enough AI empires | None |
| shroud.5310 | Shroudwalker Attunement | Can choose a major Shroud patron to gain Attunement with | None |
| shroud.6865 | Enclave Capacity | Can buy increased Enclave capacity | None |

#### For changing the galaxy

| ID | Major event | Notes | Required selection |
|---|---|---|---|
| galcom.16 | The Birth of the Galactic Community | Option to instantly create or join the Galactic Community | None |
| action.99 | Galactic Market: Established | Forms the Galactic Market in the capital system | None |
| crisis.199 | Prethoryn Scourge | Begins Prethoryn crisis | None |
| crisis.1000 | The Unbidden | Begins Unbidden crisis | None |
| crisis.1100 | The Aberrant | Doesn't require the Unbidden | None |
| crisis.1200 | The Vehement | Requires the Unbidden | None |
| crisis.2000 | The Contingency | Begins Contingency crisis | None |
| crisis.7516 | Cosmogenesis Ending | Empire becomes a fallen empire and player is forced to switch empires | None |
| crisis.8005 | The Synthetic Queen | Begins Synthetic Queen crisis | None |
| fallen_empires_awakening.1 | Sleepers Awake | Must select a Fallen Empire with the play command beforehand or YOU will awaken | None |
| war_in_heaven.1000 | War in Heaven | Will awaken two Fallen Empires if none were already awakened | None |
| utopia.3308 | End of the Cycle (base game version) | Option to form a covenant (base game mechanics) | None |
| utopia.3320 | The Reckoning | Requires accepting the covenant in the previous event to work properly | None |

| ID | Major event | Notes | Required selection |
|---|---|---|---|
| fallen_machine_empire.1 | Ancient Caretakers Awaken | Must select the Ancient Caretakers with the play command beforehand or YOU will awaken | None |
| marauder.500 | The Drums of War | Must select a Marauder Empire with the play command beforehand or YOU will become the Horde | None |
| distar.232 | Junk Ratlings | Creates the Ketling species if the Junk Ratling systems exist | None |
| distar.236 | Junk Ratlings | Creates the Ketling Star Pack empire if the Ketling species exists | None |
| distar.11000 | Spawn L-Cluster | Spawns a sealed L-Cluser | None |
| distar.13000 | The L-Cluster (L-Drake) | Doesn't require the L-Cluster but will open every L-Gate as well | None |
| graygoo.1 | The L-Cluster (Gray Tempest) | Requires the L-Cluster to work | None |
| graygoo.100 | The L-Cluster (Dessanu Consonance) | Requires the L-Cluster to work | None |
| grand_archive.2300 | Voidworm Plague | Must select the Voidworms with the play command beforehand or the empire will break | None |
| fallen_empires_awakening.10 | Shattered Fragments Awaken | Must select one of the Shattered Fragments with the play command beforehand or YOU will awaken | None |
| shroud.4135 | End of the Cycle (Shadows of the Shroud) | Option to form a covenant (Shadows of the Shroud mechanics) | None |

| ID | Major event | Notes | Required selection |
|---|---|---|---|
| infernals.1055 | Galactic Hyperthermia ending | All stars become Class-M Red Giants, all habitable planets become Volcanic Worlds, and all non-Thermophile empires are killed | None |
| nomads.610 | Vindication | Option to become The Horde | None |

#### For unlocking ascension authorities

| ID | Authority set | Required selection |
|---|---|---|
| cyber.1505 | Cybernetic | None |
| synth.1505 | Synthetic | None |
| bio.170 | Purity | None |
| bio.175 | Cloning | None |
| bio.180 | Mutation | None |
| shroud.20 | Psionic | None |

#### For unlocking edicts

| ID | Edict | Required selection |
|---|---|---|
| anomaly.4051 | Improved Working Environment | Ship |
| anomaly.4081 | Extensive Sensor Searches | Ship |
| anomaly.4105 | Improved Energy Initiative | Ship |
| anomaly.4136 | Grants Master's Teachings: The Greater Good | None |
| anomaly.4141 | Grants Master's Teachings: Philosophical Mindset | None |
| anomaly.4151 | Grants Master's Teachings: Diplomatic Trust | None |
| anomaly.4166 | Grants Master's Teachings: Warring States | None |
| shroud.3200 | Animatus | None |
| shroud.3210 | Will of Temperance | None |
| shroud.3220 | Will of Distraction | None |
| shroud.3230 | Will of Endless | None |
| shroud.3240 | Will of Rebirth | None |
| shroud.3260 | Will of Order | None |
| shroud.3270 | Will of Motion | None |

#### For unlocking paragons

Other paragons can be obtained with the paragons debug window.

| ID | Paragon | Required selection |
|---|---|---|
| galactic_features.303 | Tuborek | Ship |
| distar.156 | S875.1 Warform | Ship |
| distar.245 | Caretaker AX7-b | Ship |
| ancrel.4036 | Oracle | None |
| paragon.1 | The Beholder | None |
| paragon.228 | Astrocreator Azaryn | None |
| paragon.3115 | Keides, Scion of Vagros | None |
| leviathans.123 | XuraCorp paragon | None |
| leviathans.124 | Riggan paragon | None |
| leviathans.125 | Muutagan paragon | None |
| leviathans.590 | Curator paragon | None |
| enclave.7100 | Shroud-Touched paragon | None |
| astral_planes.3100 | zadigal | None |
| crisis.21125 | Nameless Apostate | None |

### Modifier cheats

The following cheats will only work if nothing is selected. The numbers can be replaced to provide smaller bonuses instead of unlimited ones.

| Command | Effect |
|---|---|
| effect add_modifier = { modifier = fotd_triumviri multiplier = 999 } | Unlimited civic points |
| effect add_modifier = { modifier = cyber_creed_no_creed_robot_points_modifier multiplier = 999 } | Unlimited genetic modification points |
| effect add_modifier = { modifier = synthetic_dawn multiplier = 999 } | Unlimited machine modification points |
| effect add_modifier = { modifier = subterranean_expansion multiplier = 999 } | Unlimited district slots |
| effect add_modifier = { modifier = the_eater_of_worlds_blessing multiplier = 999 } | Unlimited command limit |
| effect add_modifier = { modifier = procedural_space_modifier multiplier = 4 } | All branch office slots unlocked |

## Testing commands

Testing commands are used for developer, beta tester or modder testing.

Command

Description

Parameters

Example

3dstats

Toggles 3D Stats (FPS and render time)

None

3dstats

achievement_status

Print achievement status

None

achievement_status

activate_relic

Activates the triumph effect of [Relic ID]

[Pop ID] [Ethic Key]

activate_relic r_unbidden_warlock

add_ethic_pop

Add ethic to a pop

[Pop ID] [Ethic Key]

add_ethic_pop purged ethic_fanatic_authoritarian

advanced_galaxy

Simulates a game in year 2400 (every default empire gains colonies, technologies and fleets)

none

advanced_galaxy

ai_anomalies

Toggles whether human empires get ai-only anomalies

None

ai_anomalies

alienfx

Attempt to change computer lights with Alien FX

None

alienfx

ambient_object

Spawns an ambient object of the specified type.

[type]

ambient_object turbulent_nebula_2

attackallfleets

Makes all player fleets target all other fleets

None

attackallfleets

audio.playeffect

Play the sound effect with the given name

None

TODO

audio.setactivegroup

Sets the active audio group

None

TODO

audio.testeffectweights

Test the random distribution of the weighs for a sound effect

None

TODO

berserk_ai

AI aggression set to 10

None

berserk_ai

blend_post_effect

Blends to a new post effect setting

[nSetting] [vTime] [nMode]

TODO

borders

Calculates map borders

None

borders

casusbelli

Add a Casus Belli against the given target empire

[casus belli key] [country id]

casusbelli cb_subjugation 2

check_save

Check save and load persistence

None

check_save

clear_debug_lines

Clears any persistent debug lines

None

clear_debug_lines

clear_debug_strings

Clears any persistent debug strings

None

clear_debug_strings

clearflag

Clears an event flag on a specific target

[type] [flag] [target id]

clearflag global prethoryn_invasion_happened

collision

Displays collision boxes and circles

None

collision

communications

Enable/disable communication with the target empire, leave with no arguments for all

[target country id]

communications 1

contacts_summary

Hides who holds casus belli on the contacts screen

None

contacts_summary

control

Used to occupy planets. If there is no war with the owner of [planet id] control will be reverted instantly.

[planet id]

control 50

copy_pop

Copies a pop to the selected planet using the id of a single pop.

[pop id]

copy_pop 1247

crash

Crash the game

None

crash

debug_achievements

Enables popups for achievements to debug them

None

debug_achievements

debug_achievements_clear

Clear all achievements and user stats

None

debug_achievements_clear

debug_dumpevents

Prints fired events

None

debug_dumpevents

debug_stats

Shows game performance stats

None

debug_stats

debug_traits_view

Opens the traits list

None

debug_traits_view

debuglines

Toggles debug lines on/off

None

debuglines

debugtexture

Debug drawer for textures

[texture name] [transparency] [alpha channel]

debugtexture name 0,5 alpha

debugtooltip

Reveals debug info in tooltips such as pop ID for pops, and planet ID for planets.

None

tweakergui debugtooltip(pre 1.1) or debugtooltip(1.1)

deltat

Scales Delta Time with given value

[delta_t] [scale value]

TODO

democratic_election

Start a democratic ruler election

None

democratic_election

deposits

Shows stats for deposits

None

deposits

diplo_3rd_party

Does

diplomacy

between two players from 3rd party perspective.

[diplo] [actor id] [recipient id]

diplo_3rd_party action_offer_peace 1 4

dump_ai_build_plan

Prints what the AI intends to construct next

None

dump_ai_build_plan

dump_origins

Prints all origins in the galaxy

None

dump_origins

effect

Executes an

effect script

.

None

effect crystal_hit_effect

effect set_planet_flag =

Sets [flag id] on the selected planet

[flag id]

effect set_planet_flag = titanic_life_can_build

error

Show errors in log

None

error

eventscopes

Prints the scope trees of current events

None

<Event open> eventscopes

eventstats

Show event statistics.

None

eventstats

factions.showallfactions

Prints all factions and information on them.

None

factions.showallfactions

factions.showattraction

Prints attraction levels for every faction.

None

factions.showattraction

factions.spawnall

Spawns all possible factions. They will disappear immediately if 10 years haven't passed.

None

factions.spawnall

fast_forward

Fast forward a set amount of days

[amount of days] [observer]

fast_forward 100

filewatcher

Toggles filewatcher

None

filewatcher

ftl

Enable/Disable unlimited FTL, obsolete

None

ftl

fullscreen

Toggles fullscreen

None

fullscreen

give_fleet

Gives the selected fleet to [player id]

[player id]

give_fleet 0

game_over

Executes the specified type of Game Over

[victory type index]

game_over 0

game_paused

Pauses or resumes the game

None

game_paused

game_speed

Sets the specified game speed

[speed]

game_speed 2

gfxculture

Sets graphical culture for player empire, pressing tab reveals the culture keys

[culture key]

gfxculture mammalian_01

goto

Moves camera to position

[x] [y]

goto 10 10

guibounds

Displays the file location of UI elements hovered over

None

guibounds

hdr

Toggles HDR

None

hdr

help

Prints the help documentation for a command.

[command name]

help human_ai

helphelp

No help for you!

None

helphelp

hsv

Converts RGB to HSV

None

hsv 25 25 25

human_ai

Toggles AI for Human countries

None

human_ai

human_anomalies_for_ai

Allows the AI to get regular anomalies

None

human_anomalies_for_ai

info

Displays rendering info

None

info

kill_leader

Kills specified leader.

[leader id]

kill_leader ?

kill_ruler

Kills current ruler.

None

Kills current ruler.

kill_pop

Kills [Pop ID] pop

[Pop ID]

kill_pop 745

lockcamera

Locks the camera to the current position.

[debug_lockcamera, lockcamera]

lockcamera

map_names

Regenerates map names.

None

map_names

mature_galaxy

Simulates a 100 years old galaxy.

None

mature_galaxy

memtest

Used to test for memory leakage with certain functions.

[iterations]

memtest 1

message

Shows every message type on the top bar.

None

message

nogui

Toggles GUI on/off

None

nogui

nomouse

Toggles mouse scrollwheel on\off

None

nomouse

one_year

Run the game for one year then logs how long it took

None

one_year

overnight

Sets the game up for an overnight session.

[ticks per turn]

overnight 2

particle

Toggles particle debug info.

None

particle crystal_hit_effect

particle.miplevels

TODO

None

TODO

particle.useringbuffer

TODO

None

TODO

particle.wireframe

TODO

None

TODO

particle_editor

Spawns a particle editor.

None

particle_editor

path

Finds path between stars.

[from index] [to index]

path 0 1

peace_on_player

Targeted country offers peace on player.

[country id]

peace_on_player 05

planets

Lists every type of planet and the amount of each.

None

planets

players

Lists every human player in the current game.

None

players

populate

Fills all housing on selected planet with pops

WARNING:

Will hang the game as of version 3.2

None

populate

pp

Gives the player minerals

[amount]

pp 1000

production

Dumps some debug info about production

None

production

rebuild_sectors

Rebuilds sector boundaries

None

rebuild_sectors

recalc_fleet_presence

Recalculates fleet presence cache, useful if loading old saves.

None

recalc_fleet_presence

regenerate_border_colors

Regenerates border colors for empires with the same primary color

None

regenerate_border_colors

reload

Reloads assets

[file name]

reload main.gui

reload_galaxy

Starts a new game

None

reload_galaxy

reload_graphical_map

Reloads the graphical map

None

reload_graphical_map

reloadfx

Reloads the shader

[arguments: map/mapname/postfx or *.fx filename]

reloadfx arrow

remove_ethic_pop

Removes an ethic from a target pop.

[pop id] [ethic key]

remove_ethic_pop ? ethic_xenophobe

remove_notification

Removes all notifications belonging to the player

[amount]

remove_notification 1

rendertype

Prints the current rendering type.

None

rendertype

resources

Show stats for resources

None

resources

reverse_diplo

Sends a

diplomatic command

from the target to the player.

[diplo] [id]

reverse_diplo action_invite_to_federation 01

run

Runs the specified file with list of commands. File should be placed in the root Stellaris folder in your My Documents. File must be called '[insert file name here]' without the brackets. The file should be in the INI extension.

None

run group_commands.ini

scaling

Enables/disable scaling of models.

None

scaling

script_profiler

Use once to start profiling, and again to finish and print the results. So you can find out why your mod is causing performance issues.

None

script_profiler

smooth

Toggle framesmoothing

None

smooth

spawnentity

Spawns specified entity at cursor position. The entity names are found in the gfx folder in the .asset files.

[entity name]

spawnentity test_object_entity

srgb

Toggles RBG color mode

None

srgb

surrender

Surrender and gives in to all demands. Using only [country id] parameter lists wars with their appropriate war_ids for given country.

[country id] [war id]

List all wars for country with country_id = 5 along with their war_ids: surrender 5.

Force country with country_id = 5 to surrender in war with war_id = 19975: surrender 5 19975.

switchlanguage

Reload localization files and switches language

None

switchlanguage l_english

techweights

Prints weights for the tech tree of the player

[tech area]

techweights phy

test_achievement

Used to test an achievement trigger

[achievement]

test_achievement achievement_colonize

thirty_years

Run the game for 30 years then logs how long it took

Note: Currently does not work

None

thirty_years

threading.taskthreadcount

Returns the number of CPU threads used

None

threading.taskthreadcount

ticks_per_turn

Controls the number of ticks per turn

[amount of ticks]

ticks_per_turn 10

time

Returns the local system time

None

time

trigger

Tests a trigger script (*.txt) when placed in the \\Paradox Interactive\Stellaris\ folder

[trigger script]

trigger test_trigger

trigger_docs

Prints docs for triggers and effects

None

trigger_docs

trigger_file

Tests the trigger script, and crashes the game

None

trigger_file

version

Copies game version to clipboard

None

version

volume

Modifies music volume

[volume delta]

volume 20

war

The first country declares war on the second with the given wargoal

| ID list |  |
|---|---|
| Conquer | wg_conquest |
| Liberate | wg_liberation |
| Vassalize | wg_subjugation |
| Make Tributary | wg_tribute |
| Humiliate | wg_humiliation |
| Impose Ideology | wg_force_ideology |
| Humiliate (Fallen Empires) | wg_fe_humiliation |
| Stop Atrocities (Fallen Empires) | wg_fe_stop_atrocities |
| Cleanse Holy Worlds (Fallen Empires) | wg_fe_cleanse_holy_worlds |
| Decontaminate Border Territories (Fallen Empires) | wg_fe_cleanse_border_worlds |
| Outlaw AI (Fallen Empires) | wg_fe_stop_ai |
| Domination | wg_ae_domination |
| End Threat | wg_end_threat |
| Cleansing | wg_cleansing |
| Assimilation | wg_assimilation |
| Absorption | wg_absorption |
| War in Heaven | wg_war_in_heaven |
| Machine Uprising | wg_machine_uprising |
| Independence | wg_independence |
| Assert Overlordship | wg_assert_overlordship |
| Plunder | wg_plunder |
| Total War | wg_colossus |
| Stop Colossus | wg_end_threat_colossus |

[attacker country id] [defender country id] [war goal]

war 2 4 wg_independence

warexhaustion

Adds the given war exhaustion for all of an empire's active wars

[amount]

warexhaustion 75

window

Opens an GUI window element

[arguments open/close] [window gui name]

window open advisor_window

wireframe

Toggles forced wireframe on/off

None

wireframe

## TweakerGUI commands

- TweakerGUI commands are a specific sub-set of commands that spawn UI elements for toggling of commands preventing the need for re-opening the console and typing out the command again.
- All commands in this sub-set ' must' start with tweakergui.

| Command | Description | Parameters | Example |
|---|---|---|---|
| alerts.showall | Toggles displaying all UI alerts | None | tweakergui alerts.showall |
| draw.asteroids | Toggles rendering of asteroid belts. | None | tweakergui draw.asteroids |
| draw.background | Toggles rendering of the background space texture. | None | tweakergui draw.background |
| draw.borders | Toggles rendering of border colors and empire icons. | None | tweakergui draw.borders |
| draw.center | Toggles rendering of the galaxy center glow. | None | tweakergui draw.center |
| draw.clusters | Toggles rendering of white circles in the galaxy map. Empires seems to be distributed evenly across clusters. | None | tweakergui draw.clusters |
| draw.combatdebuglines | Toggles rendering of lines during combat showing which target a ship is focusing on. A line also shows where the ship was located before combat. | None | tweakergui draw.combatdebuglines |
| draw.dust | Toggles rendering of the galaxy dust. | None | tweakergui draw.dust |
| draw.greenscreen | Toggles rendering a green screen behind the background. Turning of the background (draw.background) will give you a totally greenscreened game that you can use for video purposes. You should also use line draw.navigationarrows and draw.systemlines. | None | tweakergui draw.greenscreen |

| Command | Description | Parameters | Example |
|---|---|---|---|
| draw.hyperlanes | Toggles rendering of hyperlanes. | None | tweakergui draw.hyperlanes |
| draw.names | Toggles rendering of empire and nebula names on the galaxy map. | None | tweakergui draw.names |
| draw.navigationarrows | Toggles rendering of the arrows and names towards neighbors of a system. (Crashed the game during first test, but might have been coincidence) | None | tweakergui draw.navigationarrows |
| draw.nebula | Toggles rendering of nebulas on the galaxy map. | None | tweakergui draw.nebula |
| draw.neighbors | Toggles rendering of cyan and yellow lines in the starmap. Cyan lines are drawn from a system to its neighbouring systems. Yellow lines divides the map into cells with each cell beloning to a single system. | None | tweakergui draw.neighbors |
| draw.objects | Toggles rendering of stars, ships, stations, planets and arrows towards neighboring systems. | None | tweakergui draw.objects |
| draw.pathtosystem | Displays a slider with default value -1. When a ship is selected a path will be rendered from the ship's system towards the system corresponding to the ID in the slider. An ETA is displayed for every jump made. ETA says "X Days", but seems to be 10x the amount of ingame days needed. (Possibly game ticks) | None | tweakergui draw.pathtosystem |

| Command | Description | Parameters | Example |
|---|---|---|---|
| draw.sensor | Toggles the green dashed circle (i.e. sensor range) around ships and owned systems. | None | tweakergui draw.sensor |
| draw.shipintersection | ? | None | tweakergui draw.shipintersection |
| draw.stars | Toggles rendering of stars and black holes on the galaxy map. | None | tweakergui draw.stars |
| draw.systeminit | Toggles rendering of the systems initialization template. I.e. a system starts with hostiles, made to suit as colony for nearby empire etc. | None | tweakergui draw.systeminit |
| draw.systemlines | Toggles rendering of systems planetary orbits, warp bounds and outer bounds. | None | tweakergui draw.systemlines |
| draw.tigrid | Toggles rendering of yellow grid in galaxy map. Use unknown. | None | tweakergui draw.tigrid |
| draw.trails | Toggles rendering of ships engine trails. | None | tweakergui draw.trails |
| draw.weaponlocators | Draws weapon locators. | None | tweakergui draw.weaponlocators |
| enable.ai | Enables AI. | None | tweakergui enable.ai |
| enable.asserts | Enables asserts. | None | tweakergui enable.asserts |
| enable.framesmoothing | Enables frame smoothing. | None | tweakergui enable.framesmoothing |
| endscreen | Displays the endscreen. | None | tweakergui endscreen |
| entity.names | Displays entity names. | None | tweakergui entity.names |

| Command | Description | Parameters | Example |
|---|---|---|---|
| entity.recursiveboundingvolumes | Displays recursive bounding volumes. | None | tweakergui entity.recursiveboundingvolumes |
| gui.wireframe | Displays the wireframe of the GUI. | None | tweakergui gui.wireframe |
| ignore_truce | Wars can be declared during truces | Toggle on and off. | tweakergui ignore_truce |
| instant_anomaly_research | Anomalies are researched instantly | Toggle on and off. | tweakergui instant_anomaly_research |
| instant_colony | Colony ships will no longer take time to settle. | Toggle on and off. | tweakergui instant_colony |
| instant_move | Ships will teleport instantly to right click cursor. | Toggle on and off. | tweakergui instant_move |
| instant_survey | Planets are surveyed instantly | Toggle on and off. | tweakergui instant_survey |
| maxfps | Limits the maximum FPS. Defaults to no limit (0). | None | tweakergui maxfps |
| mesh.miplevels | ? | None | tweakergui mesh.miplevels |
| mesh.names |  | Displays the names of the.mesh file used for each model. | tweakergui mesh.names |
| mesh.texturenames | Displays the folder/filename of textures used for each model. | None | tweakergui mesh.texturenames |
| mesh.wireframe | Toggles the wireframe for models. | None | tweakergui mesh.wireframe |
| missilegfx.extratimepertick | ? | None | tweakergui missilegfx.extratimepertick |

| Command | Description | Parameters | Example |
|---|---|---|---|
| missilegfx.slowdownradius | ? | None | tweakergui missilegfx.slowdownradius |
| music.fade | ? | None | tweakergui music.fade |
| music.next | ? | None | tweakergui music.next |
| no_resources | ? | None | tweakergui no_resources |
| normals | Displays normalisation points on each mode. | None | tweakergui normals |
| pathfindcache | ? | None | tweakergui pathfindcache |
| pop_happiness | Forces pop happiness to specific level. | None | tweakergui pop_happiness |
| popfactionlogs | ? | None | tweakergui popfactionlogs |
| portraits | ? | None | tweakergui portraits |
| portraits.poplevel | ? | None | tweakergui portraits.poplevel |
| terraincognita | Used to reveal all uncharted space. | None | tweakergui terraincognita |

## Changing galactic imperium color

The color of the galactic imperium can be changed mid-game while playing as the galactic emperor by copying the following command combination into the console and replacing the color name: effect = { change_country_flag = { icon = { category = "special" file = "the_empire.dds" } background= { category = "backgrounds" file = "00_solid.dds" } colors={ "red" "red" "null" "null" } } }

The word red can be replaced by any color name to give a different color, such as dark_blue

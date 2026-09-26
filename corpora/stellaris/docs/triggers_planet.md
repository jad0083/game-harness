# Conditions — planet, pop, species and army scopes
Source: https://stellaris.paradoxwikis.com/Conditions
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260716201409 (the live wiki blocks non-browser clients). Page version banner: Version Please help with verifying or updating older sections of this article. At least some were last verified for version 4.3. This article is for the PC version of Stellaris only._

Rows whose first listed scope is: planet, pop, pop_group, species, deposit, sector, army.

| Name | Desc | Example | Scopes |
|---|---|---|---|
| has_orbital_station | Checks if the planet has any kind of orbital station | has_orbital_station = yes | planet |
| happiness | Checks the pop group's happiness percentage | happiness < 0.5 | pop pop_group |
| has_designation | Checks if the colony has a certain designation | has_designation = col_rural/<planet scope> | planet |
| colony_type | Checks if the colony is of a certain type | colony_type = col_rural/<planet scope> | planet |
| last_building_changed | Checks if the last building queued/unqueued/built/demolished/upgraded was the specified building | last_building_changed = building_capitol | planet |
| last_district_changed | Checks if the last district queued/unqueued/built/demolished/upgraded was the specified district | last_district_changed = district_capitol | planet |
| capital_tier | Checks the tier of the planet's capital building | capital_tier > 1 | planet |
| has_ring | Checks if the planet has a planetary ring | has_ring = yes | planet |
| is_moon | Checks if the planet is the moon of another planet | is_moon = yes | planet |
| ethos | Checks the average ethics divergence on the planet, i.e. num of pops not of the country's ethics / total num of pops | ethos < 0.4 | planet |
| planet_size | Checks the planet's size | planet_size < 20 | planet |

| pop_has_ethic | Checks if the pop has a specific ethos | pop_has_ethic = ethic_fanatic_xenophile | pop pop_group |
| pop_group_has_ethic | Checks if the pop group has a specific ethos | pop_group_has_ethic = ethic_fanatic_xenophile | pop_group |
| pop_group_has_trait | Checks if the pop group has a specific trait | pop_group_has_trait = trait_decadent | pop_group |
| has_observation_outpost | Checks if the planet has an observation post | has_observation_outpost = yes | planet |
| is_in_cluster | Checks if the planet/system belongs to a specific spawning cluster | is_in_cluster = resource_cluster_3 | planet galactic_object |
| has_deposit | Checks if the planet has any, or a specific, deposit | has_deposit = yes has_deposit = d_immense_engineering_deposit | planet deposit |
| has_pop_faction_flag | Checks if the pop faction has a specific flag | has_pop_faction_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | pop pop_group pop_faction |
| original_owner | Checks if the planet is still owned by its first colonizer | original_owner = yes | planet |
| can_colonize | Checks if the planet can be colonized by target country | can_colonize = { who = <target> status = yes } | planet |
| is_valid | Checks to see if target scope is valid for the country/planet/army | is_valid = yes/no | planet country army |

| is_robot_pop | Checks if the pop is a robot | is_robot_pop = yes | pop pop_group |
| is_robot_pop_group | Checks if the pop group is a robot | is_robot_pop_group = yes | pop_group |
| is_point_of_interest | Checks if the planet/country/ship/system/ambient object has a specific point of interest for a specific event chain for a specific country | is_point_of_interest = { id = <id> event_chain = <event_chain> owner = <target> } | planet country ship galactic_object ambient_object |
| terraformed_by | Checks if planet is terraformed by country. | terraformed_by = <scope> | planet |
| has_any_megastructure | Checks if the scope has a megastructure | has_any_megastructure = yes | planet galactic_object |
| former_living_standard_type | Compares the former living standard type with the given one. | former_living_standard_type = living_standard_normal | pop pop_group |
| former_citizenship_type | Compares the former citizenship type with the given one. | former_citizenship_type = citizenship_full | pop pop_group |
| former_military_service_type | Compares the former military service type with the given one. | former_military_service_type = military_service_full | pop pop_group |
| former_slavery_type | Compares the former slavery type with the given one. | former_slavery_type = slavery_normal | pop pop_group |

| former_purge_type | Compares the former purge type with the given one. | former_purge_type = purge_normal | pop pop_group |
| former_population_control_type | Compares the former population control type with the given one. | former_population_control_type = population_control_yes | pop pop_group |
| former_migration_control_type | Compares the former migration control type with the given one. | former_migration_control_type = migration_control_yes | pop pop_group |
| has_forbidden_jobs | Check that you have forbidden job of a specific type | has_forbidden_jobs = "miner" | planet |
| is_robotic | Check if the species in the scope is a robot species or not | is_robotic=<yes/no> | species |
| has_available_jobs | Check that you have available job of a specific type | has_available_jobs = "miner" | planet |
| free_jobs_of_type | Check how many free jobs there are of a specific jobtype or pop category on a planet | free_jobs_of_type = { job = <jobtype> category = <pop_category> include_deprioritized_jobs = <yes/no>: default = no value <comparator> <value> } | planet |
| is_star | Checks if the planet is a star | is_star = yes | planet |
| is_asteroid | Checks if the planet is an asteroid | is_asteroid = yes | planet |
| is_astral_scar | Checks if the planet is an astral scar | is_astral_scar = yes | planet |

| is_infertile | Checks if the pop group/species has any trait with infertile | is_infertile = yes/no | pop pop_group species |
| has_picked_auto_mod_habitability | Checks if a pop has already picked an auto modded habitability trait. | has_picked_auto_mod_habitability = <yes/no> | pop_group |
| has_district | Checks if the planet has any, or a specific, district | has_district = yes has_district = district_mining | planet |
| free_district_slots | Checks the planet's number of slots available for new constructions | free_district_slots > 2 | planet |
| has_owner | Checks if the planet is colonized (in planet scope) or the system has an owner (in system scope) | has_owner = yes | planet galactic_object |
| free_housing | Checks the planet's available housing | free_housing > 5 | planet |
| can_live_on_planet | Checks if the pop group or species is allowed to live on a specified planet | can_live_on_planet = from.capital_scope | pop pop_group species |
| free_amenities | Checks the planet's available amenities | free_amenities > 5 | planet |
| has_deficit | Checks if the country or planet has a deficit of the defined resource. Only populated planets can have deficits. | has_deficit = minerals | planet country |
| is_being_assimilated | Checks if the pop group is being assimilated | is_being_assimilated = yes | pop pop_group |

| has_branch_office | Check if the planet has a branch office owned by target country/any country/no country | has_branch_office = <target/yes/no> | planet |
| is_blocker | Checks if scoped deposit is a blocker-type | is_blocker = yes | deposit |
| free_branch_office_building_slots | Checks the planet's number of branch office slots available for new constructions | free_branch_office_building_slots > 2 | planet |
| branch_office_value | Checks the planet's branch officevalue | branch_office_value = { who = <target> value > 10/variable } | planet |
| free_jobs | Checks the number of unassigned jobs on the planet | free_jobs > 12 | planet |
| is_planet_class | Checks if the planet is of a certain class | is_planet_class = pc_tundra/<planet scope> | planet dlc_recommendation |
| has_strategic_resource | Checks if the planet or astral rift has any strategic resource | has_strategic_resource = yes | planet astral_rift |
| is_star_class | Checks if the system/planet(star) is of a certain class | is_star_class = sc_black_hole/<system scope> | planet galactic_object |
| planet_devastation | Checks the planet's devastation | planet_devastation > 10 | planet |
| is_pop_category | Checks if the pop group has the chosen pop category | is_pop_category = <key> | pop_group |

| planet_stability | Compares the stability present on the planet with the given value | planet_stability > 50 | planet |
| planet_crime | Compares the crime present on the planet with the given value | planet_crime > 50 | planet |
| has_planetary_ascension_tier | Checks if the planet's ascension tier is as specified: | has_planetary_ascension_tier >= 1 | planet |
| has_job_type | Checks if the job has a specific type set. | has_job_type = <key> | pop job |
| has_planet_modifier | Checks if the planet has a specific planet modifier | has_planet_modifier = pm_titanic_life | planet |
| is_deposit_type | Checks if deposit is specified type | is_deposit_type = d_immense_engineering_deposit | deposit |
| num_buildings | Checks the number the planet has of any, or a specific, building | num_buildings = { type = <key/any> value > 2/variable disabled = <any(default)/yes(only)/no(only)> in_construction = <any/no(default)/yes(only)> category = <any(default)/for example unity or resource> owner_type = <normal/corporate/subject_holding> limit = {} (scope = planet) } | planet country galactic_object |
| num_districts | Checks the number the planet has of any, or a specific, district | num_districts = { type = <key/any> value > 2/variable } | planet country |

| num_free_districts | Checks the number of available slots the planet has of any, or a specific, district | num_free_districts = { type = <key/any> value > 2/variable } | planet |
| has_planet_flag | Checks if the planet has a specific flag | has_planet_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | planet |
| has_army_flag | Checks if the army has a specific flag | has_army_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | army |
| has_deposit_flag | Checks if the deposit has a specific flag | has_deposit_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | deposit |
| has_sector_flag | Checks if the sector has a specific flag | has_sector_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | sector |
| is_capital | Checks if the planet is its owner's capital | is_capital = yes | planet |
| has_ground_combat | Checks if ground combat is taking place on the planet | has_ground_combat = yes | planet |
| num_unemployed | Checks the number of unemployed pops on the planet or in the entire country | num_unemployed > 301 | planet country |
| can_work_specific_job | Checks if the pop group can work a specific job if a vacancy becomes available | can_work_specific_job = <key> | pop pop_group |

| is_archetype | Checks if species has specified archetype: | is_archetype = PRESAPIENT | species |
| uplift_is_archetype | Checks if the uplifted version of the species has the specified archetype: | uplift_is_archetype = LITHOID | species |
| is_inside_nebula | checks if the planet/ship/fleet/system is inside a nebula | is_inside_nebula = yes | planet ship fleet galactic_object |
| is_in_frontier_space | checks if the planet/ship/fleet/system is in frontier space | is_in_frontier_space = yes | planet ship fleet galactic_object |
| is_inside_border | Checks if the planet/ship/fleet/system is inside the borders of the target country | is_inside_border = <target> | planet ship fleet galactic_object |
| is_colonizable | Checks if the planet can theoretically be colonized | is_colonizable = yes | planet |
| num_minerals | Checks the planet's total amount of minerals | num_minerals < 20 | planet |
| num_physics | Checks the planet's total amount of physics research | num_physics = 8 | planet |
| num_society | Checks the planet's total amount of society research | num_society > 8 | planet |
| num_engineering | Checks the planet's total amount of engineering research | num_engineering < 8 | planet |
| num_modifiers | Checks the planet's number of modifiers | num_modifiers < 3 | planet |

| has_any_strategic_resource | Checks if the planet has any strategic resource | has_any_strategic_resource = yes | planet |
| has_pop_flag | Checks if the pop has a specific flag | has_pop_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | pop |
| has_pop_group_flag | Checks if the pop group has a specific flag | has_pop_group_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | pop_group |
| is_occupied_flag | Checks if the planet is under military occupation | is_occupied_flag = yes | planet |
| is_surveyed | Checks if the planet/astral_rift/system has been survey by target country | is_surveyed = { who = <target> status = yes } | planet galactic_object astral_rift |
| check_economic_production_modifier_for_job | Checks the value of economic production modifiers a pop has for producing a certain resource via a certain job. Can specify checking all modifiers or just those from traits. WARNING: expensive trigger | check_economic_production_modifier_for_job = { job = miner resource = minerals resource = { minerals = 0.5 energy = 0.5 } (for evaluating the bonuses to multiple resources, with weights) species_modifiers_only = no (default: yes - only checks trait modifiers, trait triggered pop modifiers, and species habitability) value > 1.25 } | planet pop_group |

| is_colony | Checks if the planet is colonized | is_colony = yes | planet |
| habitability | Checks the planet's habitability (0 to 1) for target pop group/species | habitability = { who = <target> value = 0.6 } | planet |
| has_building | Checks if the planet has any, or a specific, building | has_building = yes has_building = building_capital_3 | planet |
| has_holding | Checks if the planet has any, or a specific, holding | has_holding = { holding = any/none/<holding> owner = <owner> } | planet |
| has_active_building | Checks if the planet has a specific building, and that that building is not disabled or ruined. | has_active_building = building_capital_3 | planet |
| is_controlled_by | Checks if the planet/ship/fleet/astral rift/starbase is controlled by the target country | is_controlled_by = <target> | planet ship fleet starbase astral_rift |
| is_terraformed | Checks if the planet has ever been terraformed | is_terraformed = yes | planet |
| is_terraforming | Checks if the planet is currently being terraformed | is_terraforming = yes | planet |
| is_scripted_terraforming | Checks if the planet is currently being terraformed manually by script | is_scripted_terraforming = yes | planet |

| is_in_sensor_range_of_country | Checks if the scoped ship, fleet, planet or system can be seen by the specified country. | is_in_sensor_range_of_country = root.owner | planet ship fleet galactic_object |
| has_mining_station | Checks if the planet has an orbital mining station | has_mining_station = yes | planet |
| has_research_station | Checks if the planet has an orbital research station | has_research_station = yes | planet |
| army_type | Checks the army's type | army_type = assault_army | army |
| is_defensive_army | Checks if the army is defensive | is_defensive_army = yes | army |
| has_army | Checks if the planet has an army | has_army = yes | planet |
| num_uncleared_blockers | Checks the planet's total amount of uncleared blockers | num_uncleared_blockers > 3 | planet |
| has_anomaly | Checks if the planet has an anomaly | has_anomaly = yes | planet |
| is_planet | Checks if the planet is the same as target planet | is_planet = <target> | planet |
| is_army | Checks if the army is the same as target army | is_army = <target> | army |
| has_resource | Checks if the planet has a specific amount of a specific resource | has_resource = { type = minerals amount < 5 } has_resource = no | planet country deposit astral_rift |

| has_building_construction | Checks if the planet has any, or a specific, ongoing building construction | has_building_construction = yes has_building_construction = building_capital_3 | planet |
| free_building_slots | Checks the planet's number of slots available for new constructions | free_building_slots > 2 | planet |
| has_moon | Checks if the planet has a moon | has_moon = yes | planet |
| num_moons | Checks the planet's number of moons | num_moons < 4 | planet |
| is_sapient | Checks if the pop group or species is sapient | is_sapient = no | pop_group species |
| inherits_parent_rights | Checks if the pop group or species inherits the base species' rights. Returns false if there is no parent species. | inherits_parent_rights = no | pop_group species |
| is_preventing_anomaly | Checks if the planet is prevented from generating anomalies | is_preventing_anomaly = yes | planet |
| has_deposit_for | Checks if the planet has a deposit for a specific ship class | has_deposit_for = shipclass_mining_station | planet |
| colony_age | Checks the planet's (colony's) age in months | colony_age > 12 | planet |
| colony_age_years | Checks the planet's (colony's) age in years | colony_age_years > 12 | planet |
| is_ringworld | Checks if the planet is a ringworld | is_ringworld = yes | planet |

| member_of_faction | Checks if the pop group belongs to any, or a specific, faction | member_of_faction = no/<pop faction scope>/isolationist | pop pop_group |
| is_ideal_planet_class | Checks if the planet is of the ideal class for target country, species or pop | is_ideal_planet_class = { who = <target> status = yes/no } | planet |
| species_gender | Checks what gender settings the species allows. | species_gender = female/male/indeterminable/not_set | species |
| count_deposits | Checks the number of deposits on the planet that meet the specified criteria | count_deposits = { type = <deposit> category = <category> count < 2 } | planet |
| count_species_traits | Checks the number of unique traits within the set parameters on a species or pop group | count_species_traits = { limit = {} category = <category> cost < = > <trait cost> / count < 2 } | pop pop_group species |
| has_point_of_interest | Checks if the scoped country has a specific point of interest in its situation log | has_point_of_interest = { poi = <id> } | planet country ship fleet galactic_object ambient_object |
| is_in_frontline | Checks if the army is currently in the frontline of a combat | is_in_frontline = yes | army |
| is_homeworld | Checks if the planet is its owner's homeworld | is_homeworld = yes | planet |

| is_neighbor_of | Checks if the country/planet is neighbors with target country | is_neighbor_of = <target> | planet country ship fleet galactic_object |
| is_under_colonization | Checks if the planet is being colonized | is_under_colonization = yes | planet |
| distance_to_empire | Checks the ship/fleet/planet/system's galaxy map distance to target empire | distance_to_empire = { who = <target> distance = x use_bypasses = no (default: yes) type = hyperlane/euclidean (default: hyperlane) } | planet ship fleet galactic_object |
| is_within_borders_of | Checks if the planet/system/fleet/ship is within the borders of the target country | is_within_borders_of = <target> | planet ship fleet galactic_object |
| has_species_flag | Checks if the species has a specific flag | has_species_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | species |
| is_original_owner | Checks if the target country is the planet's original owner | is_original_owner = <target> | planet |
| num_energy | Checks the planet's total amount of energy | num_energy > 19 | planet |
| num_armies | Checks the country's or planet's number of armies | num_armies < 20 | planet country |
| is_majority_species | Checks if the specified species is the majority species on the current planet. | is_majority_species = <species> | planet |

| distance_to_capital | Checks the distance of a controlled system to its owner's capital | distance_to_capital > 5 | planet galactic_object |
| happiness_planet | Checks the average happiness on the planet | happiness_planet < 0.6 | planet |
| can_join_factions | Checks if scoped pop group can join a faction |  | pop pop_group |
| num_pops_assigned_to_job | Checks the number of pops assigned to the job (in total or from a specific pop group) | num_pops_assigned_to_job = { pop_group = <target> (if not specified, check total number) value < 300 } | pop job |
| is_custom_capital_location | Checks if the spatial object is its owner's custom capital location | is_custom_capital_location = yes | planet ship fleet galactic_object |
| planet_resource_compare | Checks specific resource value for scoped planet. Warning: performance-intensive trigger! | planet_resource_compare = { resource = <resource_name> value ><= <value>/variable> type = upkeep/produces/balance(default) } | planet |
| pop_amount_percentage | Checks the percentage of pops in the scope that fulfill the specified criteria | pop_amount_percentage = { percentage > 0.74/variable limit = { <triggers> } exclude = { <triggers> } (optional: specifies pop groups to exclude from the calculation) } | planet country pop_faction sector |

| num_species | Checks if the number of species on a planet, in an empire or in a pop faction is according to the argument. Does not count genetically modified species as unique. | num_species > 8 | planet country pop_faction |
| num_unique_species | Checks if the number of species on a planet, in an empire or in a pop faction is according to the argument. Counts genetically modified species as unique. | num_unique_species < 12 | planet country pop_faction |
| has_citizenship_type | Checks if a species/pop group/leader has a particular citizenship type in their country | has_citizenship_type = { country = <who> type = <type> } | pop pop_group leader species |
| former_colonization_control_type | Compares the former migration control type with the given one. | former_colonization_control_type = colonization_control_yes | pop pop_group |
| has_population_control | Checks if the pop group is prevented from reproducing | has_population_control = { type = bool/<type> country = scope } | pop pop_group leader species |
| has_migration_control | Checks if the pop group is prevented from migrating | has_migration_control = { type = bool/<type> country = scope } | pop pop_group leader species |

| has_military_service_type | Checks if a species/pop group/leader has a particular military service type in their country | has_military_service_type = { country = <who> type = <type> } | pop pop_group leader species |
| has_purge_type | Checks if a species/pop group/leader has a particular purge type in their country | has_purge_type = { country = <who> type = <type> } | pop pop_group leader species |
| has_slavery_type | Checks if a species/pop group/leader has a particular slavery type in their country | has_slavery_type = { country = <who> type = <type> } | pop pop_group leader species |
| has_living_standard | Checks if a species/pop group/leader has a particular living standard in their country | has_living_standard = { country = <who> type = <type> } | pop pop_group leader species |
| has_citizenship_rights | Checks if the pop group/species/leader has rights | has_citizenship_rights = yes/no | pop pop_group leader species |
| has_colonization_control | Checks if the pop group is prevented from colonizing | has_colonization_control = { type = bool/<type> country = scope } | pop pop_group leader species |
| planet_garrison_strength | Checks the planet's army strength (as calculated by all armies including offensive or defensive owned by its current controller). Warning: moderately intensive trigger: | planet_garrison_strength >= 510 | planet |

| count_species | Counts the number of species in the scope that fulfill the specified criteria, not counting sub-species as unique. | count_species = { count > 4 limit = { <triggers> } } | planet country |
| count_exact_species | Counts the number of species in the scope that fulfill the specified criteria, counting sub-species as unique. | count_exact_species = { count > 4 limit = { <triggers> } } | planet country |
| pop_maintenance_cost | Checks the maintenance costs of a pop group | pop_maintenance_cost = { value > 0.5/variable resource = energy } | pop_group |
| has_orbital_bombardment | Checks whether a planet is under bombardment | has_orbital_bombardment = yes | planet |
| has_orbital_bombardment_stance | Checks to what degree the planet is being bombarded | has_orbital_bombardment_stance = selective | planet |
| is_scope_set | Checks if the scope is set for appropriate target | is_scope_set = <target> | planet country ship pop pop_group fleet |
| is_primary_star | Checks if the planet is the system's primary star | is_primary_star = yes | planet |
| uses_district_set | Checks if the planet has the specified tag for district usage: | uses_district_set = standard | planet |
| has_climate | Checks if the planet's climate is set to a specified string in planet_classes: | has_climate = dry | planet |

| last_changed_species_rights_type | Check if the last species rights type changed for the pop group or leader is of type type | last_changed_species_rights_type = <living_standard/citizenship/military_service/slavery/purge/colonization_control/population_control/migration_control/none> | pop pop_group leader |
| has_sector_type | Checks if the sector has a specific type | has_sector_type = <sector type> | sector |
| has_deposit_category | Checks if a deposit has specified category | has_deposit_category = <category key> | deposit |
| num_housing | Checks the planet's total housing | num_housing > 5 | planet |
| num_deposits | Checks the planet's total number of deposits | num_deposits > 5 | planet |
| is_sector_capital | Checks if the planet is its sector's capital | is_sector_capital = yes | planet |
| is_artificial | Checks if the planet is artificial (as set in planet_classes) | is_artificial = yes | planet |
| is_ideal | Checks if the planet is ideal (as set in planet_classes) | is_ideal = yes | planet |
| pop_has_happiness | Checks if the current pop has happiness or not. | pop_has_happiness = yes/no | pop pop_group |
| pop_group_has_happiness | Checks if the current pop group has happiness or not. | pop_group_has_happiness = yes/no | pop_group |
| pop_group_size | Checks if the size of the pop group is according to the argument. | pop_group_size > 8 | pop_group |

| has_current_purge | Checks if any pops are being purged on the current planet. | has_current_purge = yes/no | planet |
| species_has_happiness_with_owner | Checks if the current species has happiness or not when owned by a specified country. | species_has_happiness_with_owner = country | species |
| num_assigned_jobs | Checks the number of pops the planet or country has that work a specific job. | num_assigned_jobs = { job = <key> value > 201 } | planet country galactic_object |
| organic_pops_last_month_growth | Checks how many organic pops the planet gained last month (through growth and assembly). | organic_pops_last_month_growth > 4 | planet |
| artificial_pops_last_month_growth | Checks how many artificial pops the planet assembled last month. | artificial_pops_last_month_growth > 4 | planet |
| has_job_category | Checks if the job has a specific category set. | has_job_category = <key> | pop job |
| is_on_galaxy_map | Checks if the current player is currently viewing the galaxy map. |  | planet country ship pop pop_group fleet |
| is_paused | Checks if the current player is currently paused. |  | planet country ship pop pop_group fleet |
| is_on_slave_market | Checks if any pops from the scoped pop group are being sold on the slave market: | is_on_slave_market = yes/no | pop pop_group |

| num_storm_exploitation_buildings | Checks the number of cosmic storm exploitation buildings with positive effects on a country |  | planet country |
| planet_happiness_above_threshold | Checks if a planet's happiness is past a given threshold. Can be used in a scoped system, then it returns the sum of every planets' happiness past the given threshold. | planet_happiness_above_threshold = { threshold = 0.5 value > 0 | planet galactic_object |
| is_being_integrated_by | Checks if a species has a particular species right that enabled sub-species integration | is_being_integrated_by = <country> | species |
| num_zones | Checks the number the planet has of any, or a specific, zone | num_zones = { type = <key/any> value > 2/variable } | planet country |
| total_workforce_with_job_tag | Checks how much workforce that has jobs with all given tags in a planet | total_workforce_with_job_tag = { tags = { farmer trader } value = 1000 } | planet |
| is_last_building_changed_capital | Checks if the last building queued/dequeued/built/demolished/upgraded is a capital building. If there is no last building set, returns false. | is_last_building_changed_capital = yes | planet |
| nb_pop_exact_species | Checks the amount of pops in the planet that have the exact species. | nb_pop_exact_species = { species = <target> value = 1/variable } | planet |

| pop_group_crime | Checks the raw crime value of a pop group. When scope is a colony, checks the sum of every pop group's raw crime in the planet. | pop_group_crime >= 50 | planet pop_group |
| any_planet_army | Iterate through each army on the planet (not in ground combat), regardless of owner. - checks whether the enclosed triggers return true for any of them | any_planet_army = { <triggers> } | planet |
| count_planet_army | Iterate through each army on the planet (not in ground combat), regardless of owner. - checks whether the enclosed triggers return true for X/all of them | count_planet_army = { count = <num/all/variable> limit = { <triggers> } } | planet |
| any_ground_combat_defender | Iterate through each army currently defending the planet in ground combat - checks whether the enclosed triggers return true for any of them | any_ground_combat_defender = { <triggers> } | planet |
| count_ground_combat_defender | Iterate through each army currently defending the planet in ground combat - checks whether the enclosed triggers return true for X/all of them | count_ground_combat_defender = { count = <num/all/variable> limit = { <triggers> } } | planet |

| any_ground_combat_attacker | Iterate through each army currently attacking the planet in ground combat - checks whether the enclosed triggers return true for any of them | any_ground_combat_attacker = { <triggers> } | planet |
| count_ground_combat_attacker | Iterate through each army currently attacking the planet in ground combat - checks whether the enclosed triggers return true for X/all of them | count_ground_combat_attacker = { count = <num/all/variable> limit = { <triggers> } } | planet |
| any_deposit | Iterate through each deposit on the planet - checks whether the enclosed triggers return true for any of them | any_deposit = { <triggers> } | planet |
| count_deposit | Iterate through each deposit on the planet - checks whether the enclosed triggers return true for X/all of them | count_deposit = { count = <num/all/variable> limit = { <triggers> } } | planet |
| any_moon | Iterate through each moon of the planet - checks whether the enclosed triggers return true for any of them | any_moon = { <triggers> } | planet |
| count_moon | Iterate through each moon of the planet - checks whether the enclosed triggers return true for X/all of them | count_moon = { count = <num/all/variable> limit = { <triggers> } } | planet |

| any_owned_pop_group | Iterate through all owned pop groups - checks whether the enclosed triggers return true for any of them | any_owned_pop_group = { <triggers> } | planet country galactic_object pop_faction sector |
| count_owned_pop_group | Iterate through all owned pop groups - checks whether the enclosed triggers return true for X/all of them | count_owned_pop_group = { count = <num/all/variable> limit = { <triggers> } } | planet country galactic_object pop_faction sector |
| count_owned_pop_amount | Sums all pop amounts - checks whether the enclosed triggers return true for X/all of them | count_owned_pop_amount = { count = <num/all/variable> limit = { <triggers> } } | planet country galactic_object pop_faction sector |
| any_species_pop_group | Iterate through each pop group that belongs to this species; warning: resource-intensive! - checks whether the enclosed triggers return true for any of them | any_species_pop_group = { <triggers> } | species |
| count_species_pop_group | Iterate through each pop group that belongs to this species; warning: resource-intensive! - checks whether the enclosed triggers return true for X/all of them | count_species_pop_group = { count = <num/all/variable> limit = { <triggers> } } | species |

| any_job_pop_group | Iterate through each pop group that contains this job - checks whether the enclosed triggers return true for any of them | any_job_pop_group = { <triggers> } | pop job |
| count_job_pop_group | Iterate through each pop group that contains this job - checks whether the enclosed triggers return true for X/all of them | count_job_pop_group = { count = <num/all/variable> limit = { <triggers> } } | pop job |
| any_owned_pop_job | Iterate through all owned pop jobs - checks whether the enclosed triggers return true for any of them | any_owned_pop_job = { <triggers> } | planet country galactic_object sector |
| count_owned_pop_job | Iterate through all owned pop jobs - checks whether the enclosed triggers return true for X/all of them | count_owned_pop_job = { count = <num/all/variable> limit = { <triggers> } } | planet country galactic_object sector |
| count_owned_workforce | Sums all workforce - checks whether the enclosed triggers return true for X/all of them | count_owned_workforce = { count = <num/all/variable> limit = { <triggers> } } | planet country galactic_object sector |
| any_targeting_situation | Iterate through each situation that is targeting the current planet - checks whether the enclosed triggers return true for any of them | any_targeting_situation = { <triggers> } | planet |

| count_targeting_situation | Iterate through each situation that is targeting the current planet - checks whether the enclosed triggers return true for X/all of them | count_targeting_situation = { count = <num/all/variable> limit = { <triggers> } } | planet |
| any_owned_species | Check if any of the species <on the planet/in the country> meet the specified criteria - checks whether the enclosed triggers return true for any of them | any_owned_species = { <triggers> } | planet country |
| count_owned_species | Check if any of the species <on the planet/in the country> meet the specified criteria - checks whether the enclosed triggers return true for X/all of them | count_owned_species = { count = <num/all/variable> limit = { <triggers> } } | planet country |
| any_enslaved_species | Check if any of the species with enslaved pops <on the planet/in the country> meet the specified criteria - checks whether the enclosed triggers return true for any of them | any_enslaved_species = { <triggers> } | planet country |
| count_enslaved_species | Check if any of the species with enslaved pops <on the planet/in the country> meet the specified criteria - checks whether the enclosed triggers return true for X/all of them | count_enslaved_species = { count = <num/all/variable> limit = { <triggers> } } | planet country |

| any_trait_of_species | Iterate through each trait that the scoped species has | trait_of_species = { trait_has_all_tags = { positive } } - checks whether the enclosed triggers return true for any of them any_trait_of_species = { <triggers> } | pop pop_group leader species |
| count_trait_of_species | Iterate through each trait that the scoped species has | trait_of_species = { trait_has_all_tags = { positive } } - checks whether the enclosed triggers return true for X/all of them count_trait_of_species = { count = <num/all/variable> limit = { <triggers> } } | pop pop_group leader species |
| any_trait_available_for_species | Iterate through all species traits and check if scope species doesn't have this trait | traits_available_for_species = { trait_has_all_tags = { organic positive } } - checks whether the enclosed triggers return true for any of them any_trait_available_for_species = { <triggers> } | pop pop_group leader species |
| count_trait_available_for_species | Iterate through all species traits and check if scope species doesn't have this trait | traits_available_for_species = { trait_has_all_tags = { organic positive } } - checks whether the enclosed triggers return true for X/all of them count_trait_available_for_species = { count = <num/all/variable> limit = { <triggers> } } | pop pop_group leader species |

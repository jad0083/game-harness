# Conditions — system, starbase, megastructure, fleet and ship scopes
Source: https://stellaris.paradoxwikis.com/Conditions
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260716201409 (the live wiki blocks non-browser clients). Page version banner: Version Please help with verifying or updating older sections of this article. At least some were last verified for version 4.3. This article is for the PC version of Stellaris only._

Rows whose first listed scope is: galactic_object, megastructure, starbase, fleet, ship, design, cosmic_storm, cosmic_storm_influence_field, astral_rift, bypass, ambient_object, nebula.

| Name | Desc | Example | Scopes |
|---|---|---|---|
| has_mission | Checks if the observation post has a specific mission | has_mission = technological_enlightenment_4 | fleet |
| has_fleet_order | Checks if the ship/fleet has a specific fleet order. Fleet orders include: move_to_system_point_order orbit_planet_order build_orbital_station_order build_space_station_order colonize_planet_order survey_planet_order research_discovery_orde research_anomaly_order collect_data_fleet_order upgrade_design_at_starbase_fleet_order upgrade_design_at_orbitable_fleet_order return_fleet_order repair_fleet_order evade_hostiles_order follow_order land_armies_order merge_fleet_order aggressive_stance_fleet_order auto_explore_order build_megastructure_fleet_order destroy_planet_order planet_killer_weapon_windup_order planet_killer_weapon_fire_order explore_bypass_order use_bypass_order jumpdrive_order jumpdrive_windup experimental_subspace_navigation_fleet_order excavate_archaeological_site_fleet_order | has_fleet_order = survey_planet_order | ship fleet |
| is_orbiting_star | Checks if a ship is orbiting a star |  | ship fleet |
| cosmic_storm_influence_value | Returns the amount of influence on a system |  | galactic_object |

| distance | Checks the ship/fleet/planet/leader/pop group/system's galaxy map distance to target in absolute units | distance = { source = <target> min_distance >= 50 max_distance <= 120 type=<hyperlane/euclidean> bypass_empire=<empire> min_jumps = 2 max_jumps = 10 same_solar_system = yes/no (default: no; this toggles whether the trigger checks galaxy map or solar system distances) } | megastructure planet ship pop pop_group fleet galactic_object leader ambient_object starbase deposit archaeological_site first_contact |
| starting_system | Checks if the system is the starting system for any country | starting_system = yes | galactic_object |
| graphical_culture | Checks if the country/ship/megastructure/species has specific graphical culture or the same graphical culture as the target. | When used on a species this compares the culture of the species class to the target. graphical_culture = <fungoid_01/FROM> | megastructure country ship species |
| is_civilian | Checks if the scoped fleet or ship is civilian (as set in ship sizes). | is_civilian = <yes/no> | ship fleet |
| is_designable | Checks if the scoped ship design, ship or fleet (all ships) has a designable ship size. | is_designable = yes | ship fleet design ship_growth_stage |
| has_access_fleet | Checks if the target country is allowed to enter the system | has_access_fleet = <target> | galactic_object |

| upgrade_days_left | Checks how many days an upgrading megastructure will take to complete its upgrade. | upgrade_days_left > 360 | megastructure |
| inner_radius | Checks the inner radius of a solar system | inner_radius > 300 | galactic_object |
| is_alliance_fleet | Checks if the scoped fleet is an alliance fleet. | is_alliance_fleet = <yes/no> | fleet |
| is_reanimated | Checks if the scoped fleet or ship is reanimated (as set in ship sizes). | is_reanimated = <yes/no> | ship fleet ship_growth_stage |
| is_leased | Checks if the scoped fleet is leased. | is_leased = <yes/no> | fleet |
| lease_days | Checks the number of days left before fleet lease contract is finished | lease_days < 77 | fleet |
| can_lock_be_renewed | Returns true if the Bypass Lock can be renewed | can_lock_be_renewed = yes | bypass |
| is_inside_storm | Checks if the system is inside any storm or a specific storm type. | is_inside_storm = yes/no/<storm_type> | galactic_object |
| is_on_border | Checks if the system is on a countries border |  | galactic_object |
| is_growth_complete | Checks if the ship growth progress has maxed out. | is_growth_complete = yes / no | ship |
| can_be_crisis_terraformed | Checks if a system has the can_be_crisis_terraformed flag or not. | can_be_crisis_terraformed = <yes/no> | galactic_object |

| is_owned_by | Checks if the planet/system/army/ship is owned by the target country | is_owned_by = <target> | megastructure planet ship pop pop_group fleet galactic_object leader army pop_faction starbase deposit sector archaeological_site first_contact spy_network espionage_operation agreement situation |
| has_role | Checks ship design has a certain role. | has_role = gunship | design ship_growth_stage |
| has_fleet_flag | Checks if the fleet has a specific flag | has_fleet_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | fleet |
| has_ship_flag | Checks if the ship has a specific flag | has_ship_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | ship |
| has_starbase_flag | Checks if the starbase has a specific flag | has_starbase_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | starbase |
| has_astral_rift_flag | Checks if the astral rift has a specific flag | has_astral_rift_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | astral_rift |
| is_ship_class | Checks if the ship/fleet/design is a specific class | is_ship_class = shipclass_colonizer | ship fleet ship_growth_stage |

| is_ship_size | Checks if the ship/fleet/design is a specific ship size | is_ship_size = mining_station | ship fleet design starbase ship_growth_stage |
| is_capital_system | Checks if the solar system has its owner's capital | is_capital_system = yes | galactic_object |
| is_damaged | Checks if the ship is damaged | is_damaged = yes | ship |
| has_hp | Checks the ship's hull points | has_hp > 200 | ship |
| has_shield_hp | Checks the ship's shield hit points | has_shield_hp > 200 | ship |
| has_max_hp | Checks the ship's max hull points | has_max_hp > 200 | ship |
| has_max_armor_hp | Checks the ship's max armor hit points | has_max_armor_hp > 200 | ship |
| is_variable_set | Checks if the specified variable is set on the current scope. Use to avoid unset variables errors | is_variable_set = my_var | megastructure planet country ship pop pop_group fleet galactic_object leader army ambient_object species bypass pop_faction war federation starbase deposit sector archaeological_site first_contact spy_network espionage_operation espionage_asset agreement situation astral_rift ship_growth_stage |

| check_variable | Checks a variable for the country/leader/planet/system/fleet | check_variable = { which = <variable> value >=< <float>/<variable>/<scope.variable>/trigger:<trigger> } | megastructure planet country ship pop pop_group fleet galactic_object leader army ambient_object species bypass pop_faction war federation starbase deposit sector archaeological_site first_contact spy_network espionage_operation espionage_asset agreement situation astral_rift ship_growth_stage |
| check_variable_arithmetic | Checks a variable for the scope if a certain amount of arithmetic is done to it (note: the variable's value is not changed by this trigger) | check_variable_arithmetic = { which = <variable> add/subtract/multiply/divide/modulo = <float>/<variable>/<scope.variable>/trigger:<trigger> (note: this line can be repeated as many times as desired) value <=> <float>/<variable>/<scope.variable>/trigger:<trigger> (the value to compare against) } | megastructure planet country ship pop pop_group fleet galactic_object leader army ambient_object species bypass pop_faction war federation starbase deposit sector archaeological_site first_contact spy_network espionage_operation espionage_asset agreement situation astral_rift ship_growth_stage |

| check_modifier_value | Checks the value of a specified modifier in the current scope against a value. | check_modifier_value = { modifier = logistic_growth_mult value > 1.05/variable | megastructure planet country ship pop pop_group fleet galactic_object leader army species design pop_faction spy_network espionage_operation |
| is_mobile | Checks if the scoped fleet can move. | is_mobile = <yes/no> | fleet |
| has_star_flag | Checks if the solar system has a specific flag | has_star_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | galactic_object dlc_recommendation |
| is_ship | Checks if the ship is the same as target ship | is_ship = <target> | ship |
| has_planet_class | Checks if the system has planet of specific class | has_planet_class = pc_tundra/<scope> | galactic_object |
| is_disabled | Checks if the ship/fleet is disabled | is_disabled = yes | ship fleet |
| is_bottleneck_system | Checks if the system is bottleneck within the range NDefines::NGameplay::SYSTEM_BOTTLENECK_RADIUS | is_bottleneck_system = yes | galactic_object |
| is_rim_system | Checks if the system is on the galactic rim | is_rim_system = yes | galactic_object |

| has_modifier | Checks if the scope object has a certain modifier | has_modifier = <modifier> | megastructure planet country ship pop pop_group fleet galactic_object pop_faction federation starbase spy_network espionage_operation astral_rift |
| mission_progress | Checks if the observation post has achieved specific progress in a mission | mission_progress > 0.7 | fleet |
| can_access_system | Checks if the scoped fleet is able to enter the system. Note: Avoid overusing this, it is a performance-intensive trigger! | can_access_system = <solar system> | fleet |
| is_being_repaired | Checks if the ship/fleet is being repaired | is_being_repaired = yes | ship fleet |
| compare_distance | Checks whether the current scope is closer to a specified object than it is to a second specified object within the same solar system. | compare_distance = { closer_object = root further_object = from } | megastructure planet ship pop pop_group fleet galactic_object leader ambient_object starbase deposit archaeological_site first_contact |
| has_ambient_object_flag | Checks if the ambient object has a specific flag | has_ambient_object_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | ambient_object |
| is_ambient_object_type | Checks if the ambient object is a specific type. | is_ambient_object_type = caravaneer_billboard_1 | ambient_object |

| is_in_combat | Checks if the ship/fleet is engaged in combat | is_in_combat = yes | ship fleet |
| has_auto_move_target | Checks if the fleet/ship has an active auto-move target set | has_auto_move_target = yes | ship fleet |
| fleet_size | Checks the fleet's fleet size | fleet_size < 125 | fleet |
| used_defense_platform_capacity_percent | Checks the starbases's used defense platform capacity in relative terms (0.00-1.00) | used_defense_platform_capacity_percent < 0.75 | starbase |
| has_hp_percentage | Checks a fleet or ship's hit points percentage | has_hp_percentage > 0.5 | ship fleet |
| has_armor_percentage | Checks a fleet or ship's armor hit points percentage | has_armor_percentage > 0.5 | ship fleet |
| has_shield_percentage | Checks a fleet or ship's shield hit points percentage | has_shield_percentage > 0.5 | ship fleet |
| has_presence | Checks if a system contains any fleets, stations, mega structures or colonized planets. | has_presence = yes | galactic_object |
| is_megastructure_type | Compares the type of scope's mega structure to a type from the database. | is_megastructure_type = <name of type> | megastructure |
| is_upgrading | Checks if the scope's fleet or mega structure is currently upgrading. | is_upgrading = <yes/no> | megastructure fleet |

| can_be_upgraded | Checks if the scope's fleet, ship, starbase or megastructure can be upgraded. | can_be_upgraded = <yes/no>. | megastructure ship fleet starbase |
| has_megastructure_flag | Checks if the mega structure has a specific flag | has_megastructure_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | megastructure |
| is_fleet_idle | Checks if the ship/fleet is idle | is_fleet_idle = yes | ship fleet |
| is_constructing | Checks if the scoped construction ship is building the specified thing | is_constructing = megastructure / <megastructure type> / starbase / mining_station / research_station / observation_post / <ship class> | ship fleet |
| has_component | Checks if a ship has a certain component | has_component = <component template key> | ship ship_growth_stage |
| has_natural_wormhole | Returns true if the scopes system contains at least one natural wormhole | has_natural_wormhole = yes | galactic_object |
| has_astral_rift | Returns true if the scopes system contains at least one astral rift | has_astral_rift = yes | galactic_object |
| has_starbase_module | Checks if the starbase has a specific module | has_starbase_module = <starbase module> | starbase |
| has_starbase_building | Checks if the starbase has a specific building | has_starbase_building = <starbase building> | starbase |

| has_starbase_size | Compares the starbase ship size | has_starbase_size >= <starbase ship size> | starbase |
| has_status | Checks the current status of the scoped ship or fleet. | has_status = <colossus status> #charging/firing | ship fleet |
| valid_planet_killer_target | Checks if the scoped fleet can target the given planet with its planet killer weapon | valid_planet_killer_target = <planet> | fleet |
| is_starbase_type | Checks if scoped starbase would evaluate to be a certain starbase_type for its current owner. | is_starbase_type = sfortress | starbase |
| has_hyperlane_to | Checks if the system has a hyperlane connection to target system | has_hyperlane_to = <target> | galactic_object |
| is_bridge | Checks if a system has the bridge flag or not. | is_bridge = <yes/no> | galactic_object |
| is_system_connected_to_relay_network | Checks if target system is connected to own capitals through hyper relay network | is_system_connected_to_relay_network = <target> | galactic_object |
| built_on_planet | Checks if the scoped megastructure is built on a planet | built_on_planet = yes | megastructure |
| num_planets_in_system | Checks the solar system's total number of planets | num_planets_in_system > 5 | galactic_object |

| has_ship_owner_type | Checks if the ship/fleet/design/growth stage has a specific owner type (country/federation/galactic_community/global_ship_design) | has_ship_owner_type = galactic_community | ship fleet design ship_growth_stage |
| is_starbase_building_module | Checks if the starbase is currently building a specific module | is_starbase_building_module = <starbase module> | starbase |
| is_starbase_building_building | Checks if the starbase is currently building a specific building | is_starbase_building_building = <starbase building> | starbase |
| starbase_buildable_is_in_queue_before | Check if the first buildable is in the starbase building queue before the second buildable (for prerequisites, mostly) | Returns false if the first one, or both aren't in the queue. Returns true if the first one is in, but the second isn't. starbase_buildable_is_in_queue_before = { first = <buildable> second = <buildable> | starbase |
| has_design_flag | Checks if the design has a specific flag | has_design_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | design |
| is_cloaked | Checks if a fleet or ship is cloaked. | is_cloaked = <yes/no> | ship fleet |
| has_cloaking_strength | Compares cloaking strength value of the scoped fleet or ship. | has_cloaking_strength >= <value> | ship fleet |

| has_cloaking_detection | Compares cloaking detection value of the scoped fleet or ship. | has_cloaking_detection >= <value> | ship fleet |
| astral_rift_relative_difficulty | Checks the difference between an explorer's level and an Astral Rift current difficulty | astral_rift_relative_difficulty ><= <int> | astral_rift |
| is_garrison | Checks if the scoped fleet is a garrison. | is_garrison = yes / no | fleet |
| is_bypass_type | Returns true if the scope bypass is of type <type> | is_bypass_type = <type> | bypass |
| has_lock | Returns true if the bypass is locked by a dimensional lock | has_lock = yes | bypass |
| can_go_mia | Checks if the scoped fleet can go MIA. | can_go_mia = yes / no | fleet |
| timed_flag_days_left | Checks the scoped object for the remaining days left of the specified timed flag | timed_flag_days_left = { flag = <flag> value > 30 } (note: one can use e.g. my_flag@from to track relationships between objects) | megastructure planet country ship pop pop_group fleet galactic_object leader army ambient_object species pop_faction war federation starbase deposit sector no_scope archaeological_site first_contact spy_network espionage_operation espionage_asset agreement situation astral_rift |
| has_asteroid_belt | Returns true if the scoped galactic object has an asteroid belt. | has_asteroid_belt = yes/no | galactic_object |

| cosmic_storm_system_influence | Checks the systems total cosmic storm influence |  | galactic_object |
| is_influence_center | Checks if the planet is colonized (in planet scope) or the system has an owner (in system scope) | has_owner = yes | galactic_object |
| has_storm_flag | Checks if the cosmic storm has a specific flag | has_storm_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | cosmic_storm |
| num_asteroid_belts | Checks the system's number of asteroid belts | num_asteroid_belts > 1 | galactic_object |
| has_environmental_effects | Checks if a star system has any environmental effects |  | galactic_object |
| is_storm_active_in_storm_sector | Checks if there is currently a storm active within the storm sector that this system belongs to. The galaxy is split up in multiple storm sectors, which we use to avoid spawning storms too close to each other. |  | galactic_object |
| is_storm_type | Checks if the scoped Cosmic Storm's type is equal to <type> | is_storm_type = <type> | cosmic_storm |
| ship_size_multiplier | Compares ship size multiplier of the scoped design or ship. | ship_size_multiplier >= <value> | ship ship_growth_stage |
| is_space_fauna | Checks if the scoped fleet or ship is space fauna (as set in ship sizes). | is_space_fauna = <yes/no> | ship fleet design ship_growth_stage |

| can_be_reanimated | Checks if the ship/design can be reanimated. | can_be_reanimated = yes / no | ship ship_growth_stage |
| is_ship_category | Checks if the ship/fleet/design is a specific ship category | is_ship_category = <key> | ship fleet ship_growth_stage |
| fleet_integrity | Checks the fleet integrity (shield + hull points) of a fleet. | fleet_integrity > 100 | fleet |
| ship_size_cost_resource_percent | Retrieves the percentage of usage of a given resource in the ship size. If the ship size cost is 100 food and 300 minerals, the value when checking for food is 0.25 | ship_size_cost_resource_percent = <resource_key> | ship ship_growth_stage |
| has_psionic_aura | Check if the scoped system is affected by any, or a specific type, Psionic Aura. | has_psionic_aura = <yes/no> | galactic_object |
| is_aura_intensity_level | Checks the Psionic Aura's intensity level inside the scoped system. | is_aura_intensity_level = 2 | galactic_object |
| governors_skill_in_system | Checks if valid colony governors in the scoped has a specific base experience level | has_base_skill > 2 | galactic_object |
| bioship_can_grow | Checks if the bioship can get growth progress. | bioship_can_grow = yes / no | ship |

| total_system_workforce_with_job_tag | Checks how much workforce that has jobs with all given tags in a system | total_system_workforce_with_job_tag = { tags = { farmer trader } value = 1000 } | galactic_object |
| monthly_intensity_increase | Checks the Psionic Aura's monthly intensity increase inside the scoped system. | monthly_intensity_increase >= 20.5 | galactic_object |
| count_ship_size_in_system | Checks the sum of the ship_size's size_multiplier of every ship present in the scoped system. | Checks whether the enclosed triggers return true for X/all of them count_ship_size_in_system = { count = <num/all/variable> limit = { <triggers> } } | galactic_object |
| any_system_ambient_object | Iterate through every ambient object in the solar system - checks whether the enclosed triggers return true for any of them | any_system_ambient_object = { <triggers> } | galactic_object |
| count_system_ambient_object | Iterate through every ambient object in the solar system - checks whether the enclosed triggers return true for X/all of them | count_system_ambient_object = { count = <num/all/variable> limit = { <triggers> } } | galactic_object |
| any_bypass_in_system | Iterate through every bypass in the scoped galactic object. - checks whether the enclosed triggers return true for any of them | any_bypass_in_system = { <triggers> } | galactic_object |

| count_bypass_in_system | Iterate through every bypass in the scoped galactic object. - checks whether the enclosed triggers return true for X/all of them | count_bypass_in_system = { count = <num/all/variable> limit = { <triggers> } } | galactic_object |
| any_system_within_storm | Iterate through all systems within the storm - checks whether the enclosed triggers return true for any of them | any_system_within_storm = { <triggers> } | cosmic_storm |
| count_system_within_storm | Iterate through all systems within the storm - checks whether the enclosed triggers return true for X/all of them | count_system_within_storm = { count = <num/all/variable> limit = { <triggers> } } | cosmic_storm |
| any_system_added_to_storm | Iterate through all systems added to the storm - checks whether the enclosed triggers return true for any of them | any_system_added_to_storm = { <triggers> } | cosmic_storm |
| count_system_added_to_storm | Iterate through all systems added to the storm - checks whether the enclosed triggers return true for X/all of them | count_system_added_to_storm = { count = <num/all/variable> limit = { <triggers> } } | cosmic_storm |
| any_system_removed_from_storm | Iterate through all systems removed from storm - checks whether the enclosed triggers return true for any of them | any_system_removed_from_storm = { <triggers> } | cosmic_storm |

| count_system_removed_from_storm | Iterate through all systems removed from storm - checks whether the enclosed triggers return true for X/all of them | count_system_removed_from_storm = { count = <num/all/variable> limit = { <triggers> } } | cosmic_storm |
| any_system_in_cosmic_storm_influence_field | Iterate through all influence fields owned by a country - checks whether the enclosed triggers return true for any of them | any_system_in_cosmic_storm_influence_field = { <triggers> } | cosmic_storm_influence_field |
| count_system_in_cosmic_storm_influence_field | Iterate through all influence fields owned by a country - checks whether the enclosed triggers return true for X/all of them | count_system_in_cosmic_storm_influence_field = { count = <num/all/variable> limit = { <triggers> } } | cosmic_storm_influence_field |
| any_country_neighbor_to_system | Iterate through all countries that own system 1 jump away from current system (bypasses included) - checks whether the enclosed triggers return true for any of them | any_country_neighbor_to_system = { <triggers> } | galactic_object |

| count_country_neighbor_to_system | Iterate through all countries that own system 1 jump away from current system (bypasses included) - checks whether the enclosed triggers return true for X/all of them | count_country_neighbor_to_system = { count = <num/all/variable> limit = { <triggers> } } | galactic_object |
| any_combatant_fleet | Iterate through each fleet this fleet is in combat with - checks whether the enclosed triggers return true for any of them | any_combatant_fleet = { <triggers> } | fleet |
| count_combatant_fleet | Iterate through each fleet this fleet is in combat with - checks whether the enclosed triggers return true for X/all of them | count_combatant_fleet = { count = <num/all/variable> limit = { <triggers> } } | fleet |
| any_fleet_in_system | Iterate through each fleet in the current system - checks whether the enclosed triggers return true for any of them | any_fleet_in_system = { <triggers> } | galactic_object |
| count_fleet_in_system | Iterate through each fleet in the current system - checks whether the enclosed triggers return true for X/all of them | count_fleet_in_system = { count = <num/all/variable> limit = { <triggers> } } | galactic_object |

| any_fleet_in_orbit | Iterate through each fleet orbiting the current planet/starbase/megastructure - checks whether the enclosed triggers return true for any of them | any_fleet_in_orbit = { <triggers> } | megastructure planet starbase |
| count_fleet_in_orbit | Iterate through each fleet orbiting the current planet/starbase/megastructure - checks whether the enclosed triggers return true for X/all of them | count_fleet_in_orbit = { count = <num/all/variable> limit = { <triggers> } } | megastructure planet starbase |
| any_system_planet | Iterate through each planet (colony or not) in the current system - checks whether the enclosed triggers return true for any of them | any_system_planet = { <triggers> } | galactic_object |
| count_system_planet | Iterate through each planet (colony or not) in the current system - checks whether the enclosed triggers return true for X/all of them | count_system_planet = { count = <num/all/variable> limit = { <triggers> } } | galactic_object |
| any_system_colony | Iterate through each colony in the current system - checks whether the enclosed triggers return true for any of them | any_system_colony = { <triggers> } | galactic_object |

| count_system_colony | Iterate through each colony in the current system - checks whether the enclosed triggers return true for X/all of them | count_system_colony = { count = <num/all/variable> limit = { <triggers> } } | galactic_object |
| any_ship_in_system | Iterate through each ship in the current system - checks whether the enclosed triggers return true for any of them | any_ship_in_system = { <triggers> } | galactic_object |
| count_ship_in_system | Iterate through each ship in the current system - checks whether the enclosed triggers return true for X/all of them | count_ship_in_system = { count = <num/all/variable> limit = { <triggers> } } | galactic_object |
| any_starbase_in_system | Iterate through every starbase in the scoped galactic object. - checks whether the enclosed triggers return true for any of them | any_starbase_in_system = { <triggers> } | galactic_object |
| count_starbase_in_system | Iterate through every starbase in the scoped galactic object. - checks whether the enclosed triggers return true for X/all of them | count_starbase_in_system = { count = <num/all/variable> limit = { <triggers> } } | galactic_object |
| any_neighbor_system | Iterate through all a system's neighboring systems by hyperlane - checks whether the enclosed triggers return true for any of them | any_neighbor_system = { <triggers> } | galactic_object |

| count_neighbor_system | Iterate through all a system's neighboring systems by hyperlane - checks whether the enclosed triggers return true for X/all of them | count_neighbor_system = { count = <num/all/variable> limit = { <triggers> } } | galactic_object |
| any_neighbor_system_euclidean | Iterate through all a system's neighboring systems (by closeness, not by hyperlanes) - checks whether the enclosed triggers return true for any of them | any_neighbor_system_euclidean = { <triggers> } | galactic_object |
| count_neighbor_system_euclidean | Iterate through all a system's neighboring systems (by closeness, not by hyperlanes) - checks whether the enclosed triggers return true for X/all of them | count_neighbor_system_euclidean = { count = <num/all/variable> limit = { <triggers> } } | galactic_object |

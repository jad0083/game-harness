# Conditions — country scope
Source: https://stellaris.paradoxwikis.com/Conditions
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260716201409 (the live wiki blocks non-browser clients). Page version banner: Version Please help with verifying or updating older sections of this article. At least some were last verified for version 4.3. This article is for the PC version of Stellaris only._

Rows whose first listed scope is: country.

| Name | Desc | Example | Scopes |
|---|---|---|---|
| num_fleets | Checks the country's number of fleets | num_fleets < 8 | country |
| num_ships | Checks the country/fleet's number of ships | num_ships > 39 | country ship fleet |
| get_councilor_level | Get the level of a specific councilor | get_councilor_level = { type = <key> } | country |
| num_favors | Check amount of favors that scoped country can collect from target country: | num_favors = { target = <country> value ><= <value>/<variable> } | country |
| empire_size | Checks the empire's size. Identical to empire_sprawl trigger. | empire_size < 20 | country |
| empire_sprawl | Checks the empire's sprawl. Identical to empire_size trigger. | empire_sprawl < 20 | country |
| empire_sprawl_over_cap | Checks how much the empire's sprawl is over its admin capacity | empire_sprawl_over_cap < 5 | country |
| empire_sprawl_cap_fraction | Checks the empire's sprawl compared to its admin level | empire_sprawl_cap_fraction < 0.5 | country |
| opinion | Checks the country's opinion of the target country | opinion = { who = <target> value = -70/variable } | country |
| opinion_level | Checks the country's opinion level of the target country (with support for comparison operators) | opinion_level = { who = <target> level >= neutral } | country |

| envoy_opinion_change | Checks the country's opinion of the target country has been changed by envoys | envoy_opinion_change = { who = <target> value >= 25/variable } | country |
| ideal_planet_class | Checks if the pop group, species or country's ideal planet class is a specific class | ideal_planet_class = pc_tundra/<planet scope> | country pop pop_group species |
| is_pirate | Checks if the country is a pirate country | is_pirate = yes | country |
| vassals | Checks the country's number of subjects with agreement preset 'preset_vassal' | vassals > 0 | country |
| has_edict | Checks if the country has a specific edict enabled | has_edict = crystal_sonar | country |
| num_empires | Checks the number of regular empires in the galaxy | num_empires > 3 | country |
| intel | Checks the country's Intel on the target country | intel = { who = <target> value = 70/variable } | country |
| num_communications | Checks the country's number of established communications | num_communications > 3 | country |
| last_changed_policy | Checks if the last policy changed by the country was a specific policy | last_changed_policy = slavery | country |
| is_species | Checks if the pop group/country's founder species is of a specific pre-defined species | is_species = ROBOT_POP_SPECIES_2 | country pop pop_group leader species |

| last_increased_tech | Checks if the country's last researched technology was a specific tech | last_increased_tech = tech_gene_expressions | country |
| subjects | Checks the country's number of subjects | subjects > 0 | country |
| tech_unlocked_ratio | Checks the relative amount of already-researched tech between the country and target country | tech_unlocked_ratio = { who = <target> ratio = 0.4/variable } | country |
| has_special_project | Checks if the country has a specific special project available | has_special_project = EMERGENCY_BUOY_PROJECT | country |
| has_completed_special_project_in_log | Checks if the country has completed a specific special project as part of an in-progress event chain | has_completed_special_project_in_log = EMERGENCY_BUOY_PROJECT | country |
| has_failed_special_project_in_log | Checks if the country has failed, timed out or aborted a specific special project as part of an in-progress event chain | has_failed_special_project_in_log = EMERGENCY_BUOY_PROJECT | country |
| is_subspecies | Checks if the pop group/country/species is a subspecies of the target species | is_subspecies = <target> | country pop pop_group leader species |

| city_graphical_culture | Checks if the country has a specific graphical culture for its city image or the same graphical culture as the target. | If the target is a country, this trigger will compare its city graphical culture to the scoped country city graphical culture city_graphical_culture = <fungoid_01/FROM> | country |
| num_fallen_empires | Checks the number of fallen empires in the galaxy | num_fallen_empires > 3 | country |
| is_preferred_weapons | Checks if the country's AI prefers weapons using this component tag | is_preferred_weapons = weapon_type_energy | country |
| has_megastructure | Checks if a country or star has a mega structure. | has_megastructure = spy_orb_4 | country galactic_object |
| recently_lost_war | Checks if the country recently lost a war ('recently' meaning recent enough to have a truce) | recently_lost_war = yes | country |
| has_research_agreement | Checks if two countries have a research agreement. | has_research_agreement = <target> | country |
| council_agenda_progress | Checks the progress of the current Agenda. | council_agenda_progress >= <value> | country |
| is_researching_special_project | Checks if the country is currently researching a specific special project | is_researching_special_project = special_project_name | country leader |

| last_activated_relic | Checks if the specified relic was the last activated one | last_activated_relic = <relic_key> | country |
| has_unlocked_all_traditions | Checks if the country has unlocked all traditions | has_unlocked_all_traditions = yes/no | country |
| has_potential_claims | Checks if the country has any potential claims they can make. | has_potential_claims = yes/no | country |
| is_ethic_represented_on_council | Checks if any Councilor has a given ethic. | is_ethic_represented_on_council = ethic_materialist | country |
| last_lost_relic | Checks if the specified relic was the last lost one | last_lost_relic = <relic_key> | country |
| last_received_relic | Checks if the specified relic was the last received one | last_received_relic = <relic_key> | country |
| civics_count | Checks the country's number of civics | civics_count < 3 | country |
| is_galactic_custodian | Checks if an empire is Custodian of the Galactic Council | is_galactic_custodian = yes/no | country |
| is_galactic_emperor | Checks if an empire is the Galactic Emperor | is_galactic_emperor = yes/no | country |
| has_intel_level | Checks the country's intel level on a category for the target country | has_intel_level = { who = <target> category = economy level = 2/variable } | country |

| has_intel_report | Checks if the country has intel report of at least the specified level on a category for the target country | has_intel_report = { who = <target> category = economy level = 2/variable } | country |
| has_intel | Checks if the specified intel is available for the target country (stale intel will not return true) | has_intel = { who = <target> intel = system_low_intel } | country |
| has_stale_intel | Checks if the specified intel is stale for the target country (available intel will not return true) | has_stale_intel = { who = <target> intel = system_low_intel } | country |
| species_portrait | Checks if the species (or pop group/empire's dominant species) uses a certain portrait | species_portrait = rep13 | country pop pop_group species |
| is_neutral_to | Checks if the country has a neutral attitude towards target country | is_neutral_to = <target> | country |
| trust | Checks the country's trust of the target country | trust = { who = <target> value = 50/variable } | country |
| is_under_societal_enlightenment | Checks if country is under societal enlightenment | is_under_societal_enlightenment = <target> | country |
| is_under_open_technological_enlightenment | Checks if country is under open technological enlightenment | is_under_open_technological_enlightenment = <target> | country |

| is_under_stratified_technological_enlightenment | Checks if country is under stratified technological enlightenment | is_under_stratified_technological_enlightenment = <target> | country |
| has_pre_ftl_trade | Checks if country has pre-ftl trade | has_pre_ftl_trade = <target> | country |
| has_loyalty | Checks the subject's current loyalty to its overlord. | has_loyalty >=< -50 | country |
| has_monthly_loyalty | Checks the subject's current monthly loyalty gain/loss. | has_monthly_loyalty >=< -5 | country |
| acquired_specimen_count | Returns the country's acquired specimens count | acquired_specimen_count > <num> | country |
| balance | Checks the country's energy credit balance | balance < 39 | country |
| attunement | Checks the attunement level with the Shroud | attunement > 0.5 | country |
| has_highest_technology_score | Checks if the country has the highest technology score | has_highest_technology_score = yes/no | country |
| is_in_domain | Checks if the current country in the the domain of the given patron. | is_in_domain = the_eater_of_worlds | country |
| diplomacy_weight | Checks the country's diplomatic weight | diplomacy_weight > 200 | country |
| is_ai | Checks if the country is played by the AI | is_ai = no | country |

| has_trait | Checks if a pop group/leader/species/country's dominant species has a certain trait | has_trait = leader_trait_carefree | country pop pop_group leader species dlc_recommendation |
| has_ethic | Checks if a country/pop group/leader/faction has a certain ethos | has_ethic = ethic_fanatic_pacifist | country pop pop_group leader pop_faction dlc_recommendation |
| has_commercial_pact | Check if the country has a commercial pact with target country | has_commercial_pact = <target> | country |
| num_owned_relics | Checks the number of relics owned by the scoped country | num_owned_relics > 1 | country |
| has_civic_in_slot | Checks if the country has a civic in a slot | has_civic_in_slot = { civic = civic_galactic_sovereign index = 2 } | country |
| has_total_civic_points | Compares the amount of total civic points. | has_total_civic_points >= <value> | country |
| has_unused_civic_points | Compares the amount of unused civic points. | has_unused_civic_points >= <value> | country |
| council_agenda_progress_percent | Compares the progress (0-1) of the current Agenda. | council_agenda_progress_percent >= <value> | country |
| council_legitimacy | Checks current value for council legitimacy for the scoped country. | council_legitimacy >= <value> | country |

| has_agenda_selected | Checks if the country has a specific Council Agenda selected, or any at all | has_agenda_selected = <yes/any/no/none/type> | country |
| has_unlocked_council_positions | Compares the amount of unlocked council positions, typically from 'unlock_council_slots' | has_unlocked_council_positions >= <value> | country |
| is_same_species | checks if the scoped object is of the same species as another object | is_same_species = <target> | country ship pop pop_group leader army species |
| is_criminal_syndicate | Checks if the country is a criminal syndicate | is_criminal_syndicate = yes | country |
| is_same_empire | Checks if the country is the same as another, target country | is_same_empire = <target> | country |
| has_technology | Checks if the country has a technology (of at least a specific level) | has_technology = tech_spaceport_4 | country |
| can_research_technology | Checks whether the current country is allowed to have the specified technology, i.e. does it fulfil the potential = { } field for that tech, and for any prereq techs that tech has. | can_research_technology = <tech key> | country |

| can_copy_random_tech_from | Checks whether the target country has a technology the current country can steal via copy_random_tech_from effect | can_copy_random_tech_from = { who = <country> category = computing (optional) area = physics (optional) } | country |
| can_set_policy | Checks if the country is allowed to set its policy to a specific one using set_policy effect | can_set_policy = { policy = <key> option = <key> } | country |
| won_the_game | Checks if scoped country won the game | won_the_game = yes | country |
| perc_communications_with_playable | Checks the country's percentage of communications with playable empires | perc_communications_with_playable > 0.3 | country |
| num_planetary_ascension_tiers | Checks if the empire has activated as many ascension tiers as specified: | num_planetary_ascension_tiers >= 15 | country |
| has_built_species | Checks if country has a built species defined | has_built_species = yes/no | country |
| has_extorted_faction | Checks if the the country has an extorted faction | has_extorted_faction = yes/no | country |
| has_country_flag | Checks if the empire has a specific flag | has_country_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | country |

| has_attitude_behavior | Checks if the country has the specified AI behavior towards another country | has_attitude_behavior = { target = <country> behavior = attack/weaken/vassalize/alliance/coexist/trade } | country |
| is_at_war | Checks if the country is at war | is_at_war = yes | country |
| num_owned_leaders | Checks the country's number of owned (recruited) non-envoy leaders (includes the ruler) | num_owned_leaders < 8 | country |
| num_owned_planets | Checks the country's or sector's number of owned planets | num_owned_planets < 8 | country sector |
| has_government | Checks if the country has a specific government type, or any government at all | has_government = <yes/any/no/none/type> | country |
| is_primitive | Checks if the country is a primitive, pre-FTL civilization | is_primitive = yes | country |
| is_overlord | Checks if the country is the overlord of any subject countries | is_overlord = yes | country |
| is_at_war_with | Checks if the country is at war with the target country | is_at_war_with = <target> | country |
| their_opinion | Checks target country's opinion value of the current country | their_opinion = { who = <target> value > 25/variable } | country |

| is_same_species_class | Checks if the pop group/country is of the same species class as another pop group/country | is_same_species_class = <target> | country ship pop pop_group leader army species |
| has_federation | Checks if the country is in a federation | has_federation = yes | country |
| is_federation_leader | Checks if the country is the leader of their federation | is_federation_leader = yes | country |
| is_in_sensor_range | Checks if the specified ship, fleet, planet or system can be seen by the scoped country. | is_in_sensor_range = <ship/fleet/system> | country |
| has_sensor_link_from | Checks if country has an active sensor link from another empire | has_sensor_link_from = <target> | country |
| is_advisor_active | Checks if a country has an advisor | is_advisor_active = yes | country |
| income | Checks the country's monthly energy credit income | income < 90 | country |
| expenses | Checks the country's monthly energy credit expenses | expenses > 28 | country |
| num_envoys_to_federation | Checks the country's number of envoys sent to its federation | num_envoys_to_federation < 2 | country |
| num_envoys_to_galcom | Checks the country's number of envoys sent to the galactic community | num_envoys_to_galcom < 2 | country |
| stored_physics_points | Checks the country's amount of stored physics research | stored_physics_points | country |

| stored_society_points | Checks the country's amount of stored society research | stored_society_points | country |
| stored_engineering_points | Checks the country's amount of stored engineering research | stored_engineering_points | country |
| running_balance | Checks the country's running energy credit balance | running_balance > 61 | country |
| is_country | Checks if the country is the same as target country | is_country = <target> | country |
| is_tutorial_level | Checks the country's tutorial level (0 off, 1 limited, 2 full) | is_tutorial_level = 0 | country |
| has_event_chain | Checks if the country has a specific event chain | has_event_chain = old_gods_chain | country |
| has_completed_event_chain | Checks if the country has completed a specific event chain | has_completed_event_chain = <event_chain_key> | country |
| is_species_class | Checks if the pop group/country's founder species is a specific species class | is_species_class = MAM | country pop pop_group species dlc_recommendation |
| has_opinion_modifier | Checks if the country has a specific opinion modifier towards target country or anyone | has_opinion_modifier = { who = <target (optional)> modifier = encroaching_colony is_reverse = no } | country |
| has_established_contact | Checks if the country has established contact with target country | has_established_contact = <target> | country |

| has_completed_event_chain_counter | Checks if the country has completed a specific counter in an event chain | has_completed_event_chain_counter = { event_chain = amoebas_2_chain counter = amoebas_slaughtered } | country |
| has_existing_ship_design | Checks if the country has a specific ship design available |  | country |
| has_relation_flag | Checks if the country has a relation flag towards target country | has_relation_flag = { who = <target> flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) } | country |
| reverse_has_relation_flag | Checks if the target country has a relation flag towards the country | reverse_has_relation_flag = { who = <target> flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) } | country |
| is_country_type | Checks if the country is a specific type | is_country_type = fallen_empire | country |
| num_ethics | Checks the country/pop group's number of ethics | num_ethics = 3 | country pop pop_group |
| num_traits | Checks the country/pop group/leader/species' number of traits | num_traits < 3 | country pop pop_group leader species |
| has_truce | Checks if the country has a truce with target country | has_truce = <target> | country |
| intel_level | Checks the country's intel level of target system | intel_level = { level > low system = <target> } | country |

| has_faction | Checks if the country has any instance of target faction type | has_faction = isolationist | country |
| can_declare_war | Checks if the country can declare war against target country | can_declare_war = { target = <target country> attacker_war_goal = <war goal> } | country |
| is_hostile | Checks if the country is hostile towards target country | is_hostile = <target> | country |
| is_forced_neutral | Checks if the country has been set to be neutral towards target country via set_faction_hostility | is_forced_neutral = <target> | country |
| is_forced_friendly | Checks if the country has been set to be friendly towards target country via set_faction_hostility | is_forced_friendly = <target> | country |
| has_communications | Checks if the country has established communications with target country | has_communications = <target> | country |
| has_country_resource | Checks the country's amount of a specific stored resource | has_country_resource = { type = minerals amount > 99/variable } | country |
| num_killed_ships | Checks how many of target country's ships that the country has destroyed | num_killed_ships = { target = <target> value > 5/variable } | country |
| num_taken_planets | Checks how many planets the country has taken from target country | num_taken_planets = { target = <target> value > 1 } | country |

| opposing_ethics_divergence | Checks how far removed the country/pop group's ethos is from target's | opposing_ethics_divergence = { steps > 1/variable who = <target> } | country pop pop_group |
| is_war_leader | Checks if the country leads in a war | is_war_leader = yes | country pop_faction |
| is_in_federation_with | Checks if the country is in a federation with target country | is_in_federation_with = <target> | country |
| can_change_policy | Checks if the country can change a specific policy | can_change_policy = slavery | country |
| has_monthly_income | Checks the country's monthly income of a specific resource | has_monthly_income = { resource = engineering_research value < 20 } | country |
| has_policy_flag | Checks if the country has a specific policy | has_policy_flag = slavery_not_allowed | country |
| has_tech_option | Checks if the country has a tech research option currently available | has_tech_option = tech_mining_network_2 | country |
| count_tech_options | Checks the country's number available tech research options in a specific field | count_tech_options = { area = physics count > 0/variable } | country |
| galaxy_percentage | Checks if the country has a specific percentage (0.00-1.00) of the galaxy within its borders | galaxy_percentage > 0.40 | country |

| is_guaranteeing | Checks if the country is guaranteeing the independence of target country | is_guaranteeing = <target> | country |
| is_war_participant | Checks if target country is participating in the war on the specified side | is_war_participant = { who = <target>/war = <target> side = attackers/defenders/<target> } | country war |
| is_friendly_to | Checks if the country has a friendly attitude towards target country | is_friendly_to = <target> | country |
| is_hostile_to | Checks if the country has a hostile attitude towards target country | is_hostile_to = <target> | country |
| is_protective_to | Checks if the country has a protective attitude towards target country | is_protective_to = <target> | country |
| is_threatened_to | Checks if the country has a threatened attitude towards target country | is_threatened_to = <target> | country |
| is_dismissive_to | Checks if the country has a dismissive attitude towards target country | is_dismissive_to = <target> | country |
| is_patronizing_to | Checks if the country has a patronizing attitude towards target country | is_patronizing_to = <target> | country |
| is_angry_to | Checks if the country has an angry attitude towards target country | is_angry_to = <target> | country |
| is_rival | Checks if the country has a rival attitude towards target country | is_rival = <target> | country |

| is_unfriendly_to | Checks if the country has an unfriendly attitude towards target country | is_unfriendly_to = <target> | country |
| is_loyal_to | Checks if the country has a loyal attitude towards target country | is_loyal_to = <target> | country |
| is_disloyal_to | Checks if the country has a disloyal attitude towards target country | is_disloyal_to = <target> | country |
| is_cordial_to | Checks if the country has a cordial attitude towards target country | is_cordial_to = <target> | country |
| is_domineering_to | Checks if the country has a domineering attitude towards target country | is_domineering_to = <target> | country |
| fleet_power | Checks the scope's total fleet power | fleet_power > 2500 | country fleet federation |
| has_election_type | Checks if the country has a specific election type | has_election_type = oligarchic | country |
| has_ai_personality | Checks if an AI empire has a certain personality type | has_ai_personality = fanatic_befrienders | country |
| has_ai_personality_behaviour | Checks if a country has a certain AI personality behavior | has_ai_personality_behaviour = slaver | country |
| has_valid_ai_personality | Checks if the country has a valid AI personality | has_valid_ai_personality = yes | country |
| has_migration_access | Checks if the country has migration access to target country | has_migration_access = <target> | country |

| would_join_war | Checks if the country would join the side of target country in a hypothetical war | would_join_war = { attacker = <target> defender = <target> side = <target> } | country |
| years_of_peace | Checks the number of in-game years country has been at peace, with optional parameter to delay from start of game | years_of_peace = { value > 10/variable delay = 0 } | country |
| count_starbase_modules | Checks the number of starbase modules that are of the specified type or not | count_starbase_modules = { type = anchorage (optional) include_being_constructed = yes/no count < 12/variable } | country galactic_object starbase |
| count_starbase_buildings | Checks the number of starbase buildings that are of the specified type or not | count_starbase_buildings = { type = command_center (optional) include_being_constructed = yes/no count < 12/variable } | country galactic_object starbase |
| is_belligerent_to | Checks if the country has a belligerent attitude towards target country | is_belligerent_to = <target> | country |
| is_imperious_to | Checks if the country has a imperious attitude towards target country | is_imperious_to = <target> | country |
| is_arrogant_to | Checks if the country has a arrogant attitude towards target country | is_arrogant_to = <target> | country |

| has_association_status | Check if the country has federation association status with target country | has_association_status = <target> | country |
| subject_can_diplomacy | Checks if the current country is allowed by its overlord to take diplomatic action | subject_can_diplomacy = <target> | country |
| has_surveyed_class | Checks if the country has surveyed any planet of a specific class | has_surveyed_class = pc_tundra | country |
| num_rare_techs | Checks the country's number of researched rare technologies | num_rare_techs < 4 | country |
| num_dangerous_techs | Checks the country's number of researched dangerous technologies | num_dangerous_techs < 4 | country |
| num_insight_techs | Checks the country's number of researched insight technologies | num_insight_techs < 4 | country |
| num_custom_1_techs | Checks the country's number of researched custom_1 technologies | num_custom_1_techs < 4 | country |
| num_custom_2_techs | Checks the country's number of researched custom_2 technologies | num_custom_2_techs < 4 | country |
| num_custom_3_techs | Checks the country's number of researched custom_3 technologies | num_custom_3_techs < 4 | country |
| num_repeatable_techs | Checks the country's number of researched repeatable technologies | num_repeatable_techs < 4 | country |

| num_researched_techs | Checks the country's number of researched technologies | num_researched_techs > 21 | country |
| num_researched_techs_of_tier | Checks the country's number of researched technologies of a certain tier | num_researched_techs_of_tier = { tier = 2 value > 21 | country |
| can_research_tier | Checks whether the country can research a certain tech tier | can_research_tier = { tier = 1 area = society } | country |
| max_naval_capacity | Checks the country's max naval capacity in absolute numbers | max_naval_capacity > 120 | country |
| used_naval_capacity_integer | Checks the country's used naval capacity in absolute numbers | used_naval_capacity_integer < 89 | country |
| used_naval_capacity_percent | Checks the country's used naval capacity in relative terms (0.00-1.00) | used_naval_capacity_percent < 0.75 | country |
| max_starbase_capacity | Checks the country's max starbase capacity | max_starbase_capacity = 15 | country |
| used_starbase_capacity_integer | Checks the country's used starbase capacity in absolute numbers | used_starbase_capacity_integer = 15 | country |
| used_starbase_capacity_percent | Checks the country's used starbase capacity in relative terms (0.00-1.00) | used_starbase_capacity_percent < 0.75 | country |
| has_active_event | Checks if country has active events: | has_active_event = { event.1 event.2 event.n } | country |

| has_defensive_pact | Checks if the country has a defensive pact with target country | has_defensive_pact = <target> | country |
| is_researching_technology | Checks if the country is currently researching a specific technology | is_researching_technology = tech_gene_seed_purification | country |
| is_subject | Checks if the country is a subject of any other country | is_subject = no | country |
| is_enigmatic_to | Checks if the country has a enigmatic attitude towards target country | is_enigmatic_to = <target> | country |
| is_berserker_to | Checks if the country has a berserker attitude towards target country | is_berserker_to = <target> | country |
| has_same_ethos | Checks if a country has the same ethos (complete set of ethics) as a country or pop group | has_same_ethos = <target> | country pop pop_group |
| has_closed_borders | Check if the country has closed its borders to target country | has_closed_borders = <target> | country |
| is_exact_same_species | Checks if the scoped object is originally of the same species, or currently of the exact same species instance, as another object | is_exact_same_species = <target> | country ship pop pop_group leader army species |
| can_control_access_for | Checks if the country is allowed to control target country's border access to the country | can_control_access_for = <target> | country |

| is_overlord_to | Checks if the country has an overlord attitude towards target country | is_overlord_to = <target> | country |
| is_improving_relations_with | Checks if the country has an envoy sent to the target country to improve relations | is_improving_relations_with = <target> | country |
| is_harming_relations_with | Checks if the country has an envoy sent to the target country to harm relations | is_harming_relations_with = <target> | country |
| has_non_aggression_pact | Check if the country has a non-aggression pact with target country | has_non_aggression_pact = <target> | country |
| is_custodial_to | Checks if the country has a custodial attitude towards target country | is_custodial_to = <target> | country |
| has_valid_civic | Checks if the current country has a certain civic and if its validated | has_valid_civic = my_test_civic_1 | country |
| has_active_tradition | Checks if a country has the given tradition or tradition swap. Tradition specified must be the one giving effects, i.e. tradition swaps with 'inherit_effects = yes' are ignored and the base tradition should be specified in those cases. | has_active_tradition = tr_my_santa_claus_tradition | country |
| num_tradition_categories | Checks number of tradition categories the country has picked | num_tradition_categories > 2 | country |

| resource_income_to_expenditure_balance_ratio | Checks ratio between the country's income and expenditures for a specific resource. E.g. if it makes 80 energy and spends 100, its ratio is 0.8. | resource_income_to_expenditure_balance_ratio = { resource = <resource_name> category = <category_name> # Optional; if not provided, will use sum for all Categories value ><= <value> } | country |
| resource_stockpile_compare | Checks specific resource stockpile for the country scope: | resource_stockpile_compare = { resource = <resource_name> value ><= <value> mult = <variable> (optional: multiply the value by a variable, e.g. for when you are doing the same with add_resource) } | country |
| resource_income_compare | Checks specific resource income value for the country scope (note: checks profit minus loss, not revenue): | resource_income_compare = { resource = <resource_name> value ><= <value> } | country |
| resource_expenses_compare | Checks specific resource expenses value for the country scope: | resource_expenses_compare = { resource = <resource_name> category = <category_name> # Optional; if not provided, will use sum for all Categories value ><= <value> } | country |

| resource_revenue_compare | Checks specific resource revenue value for the country scope: | resource_revenue_compare = { resource = <resource_name> category = <category_name> # Optional; if not provided, will use sum for all Categories value ><= <value> } | country |
| market_resource_price | Checks market price of a specific resource for the current country: | market_resource_price = { resource = <resource_name> amount = <value> (how much are you buying/selling) trade_type = market_buy/market_sell/not_set (i.e. price without market fees) value ><= <value>/<variable> } | country |
| has_diplo_migration_treaty | Checks if two countries have a migration treaty. |  | country |
| relative_power | Compares relative power between two countries. relative_power = { who = <target country> category = <fleet/economy/technology/all> value ><= <pathetic/inferior/equivalent/superior/overwhelming> |  | country federation |
| has_tradition | Checks if a country has the given tradition. | has_tradition = tr_my_santa_claus_tradition | country |
| has_ascension_perk | Checks if a country has the given ascension perk. | has_ascension_perk = ap_my_ascension_perk | country |
| num_ascension_perks | Compares the number of AP points the country has spent with the given value | num_ascension_perks > 7 | country |

| num_ascension_perk_slots | Compares the number of unlocked ascension perk slots of the scope with the given value | num_ascension_perks > 7 | country |
| has_civic | Checks if the current country has the specified civic | has_civic = my_test_civic_1 | country dlc_recommendation |
| has_authority | Checks if the current country has the specified government authority | has_authority = auth_democratic | country dlc_recommendation |
| has_invalid_civic | Checks if the current country has a certain civic and if its invalidated | has_invalid_civic = my_test_civic_1 | country |
| has_secret_fealty_from_subject_of | Checks if the country has a secret fealty from any of the target country's subjects | has_secret_fealty_from_subject_of = <country> | country |
| num_trait_points | Checks the country/pop group/leader/species' number of traits points spent | num_trait_points < 3 | country pop pop_group leader species |
| has_notification_modifier | Checks if a country has a certain notification modifier | has_notification_modifier = <key> | country |
| is_astral_rift_pool_empty | Returns true if the astral rift starting event pool is empty | is_astral_rift_pool_empty = yes | country |
| has_claim | Checks if the country has claims on the given country or system. | has_claim = <country/system> | country |

| off_war_exhaustion_sum | Checks the country's total war exhaustion for all offensive wars | off_war_exhaustion_sum < 0.1 | country |
| def_war_exhaustion_sum | Checks the country's total war exhaustion for all defensive wars | def_war_exhaustion_sum > 0.75 | country |
| has_seen_any_bypass | Checks the scoped country has ever encountered a bypass of a given type before | has_seen_any_bypass = bypass_type | country |
| has_seen_specific_bypass | Checks the scoped country has encountered a specific bypass before | has_seen_specific_bypass = ROOT | country |
| owns_any_bypass | Checks if the scoped country controls any system containing a bypass of a specific type | owns_any_bypass = bypass_type | country |
| has_casus_belli | Checks if the country has a valid casus belli (any casus belli or a specific one) on the given country. | has_casus_belli = { target = <country> type = <cb_type> #optional } | country |
| num_starbases | Counts the number of starbases owned by the scoped country | num_starbases >= 1 | country |
| num_owned_active_gateways | Checks the number of active gateways owned by the scoped country | num_owned_active_gateways < 3 | country |
| has_secret_fealty_with | Checks if the country has a secret fealty with the other country (in either direction) | has_secret_fealty_with = <country> | country |

| count_starbase_sizes | Checks if the scoped country has a specified quantity of a starbase size | count_starbase_sizes = { starbase_size = <starbase_ship_size> count >= 2/variable } | country |
| command_limit | Checks the country's command limit | command_limit > 120 | country |
| is_capitals_connected_through_relay_network | Checks if current country's capital is connected to target's capital through hyper relay network | is_capitals_connected_through_relay_network = <target> | country |
| controlled_systems | Checks the country's or sector's number of owned systems | controlled_systems < 3 | country sector |
| exploitable_planets | Checks the country has planets that are unexploited (i.e. orbital stations can be built on them) | exploitable_planets < 3 | country |
| controlled_colonizable | Returns the number of planets within the current country's borders that are habitable but have not been colonized | controlled_colonizable > 0 | country |
| ai_colonize_plans | Checks how many plans the AI have for colonization (lighter than controlled_colonizable for AI) | ai_colonize_plans > 0 | country |
| ai_terraform_plans | Checks how many plans the AI have for terraforming | ai_terraform_plans > 0 | country |
| scientist_count | Checks the country's number of scientists | scientist_count < 4 | country |

| has_ai_expansion_plan | Checks if the country AI has any plans to expand | has_ai_expansion_plan = no | country |
| ai_wants_to_negotiate_agreement | Checks if the country AI wants to renegotiate any existing agreements |  | country |
| can_buy_on_market | Checks if the current country can buy the specified resource on the market or galactic market | can_buy_on_market = <resource_name> | country |
| highest_threat | Checks the country's highest threat against it | highest_threat > 100 | country |
| has_rival | Checks if the target country is the country's rival | has_rival = <target> | country |
| has_subject | Checks if the target country is a subject of the current country. | has_subject = <target> | country |
| has_overlord | Checks if the target country is the country's overlord | has_overlord = <target> | country |
| has_any_overlord | Checks if the country has an overlord | has_any_overlord = yes | country |
| num_sectors | Counts the number of sectors owned by the scoped country | num_sectors >= 1 | country |
| has_relic | Checks if the scoped country has the specified relic | has_relic = <relic_key> | country |
| is_proposing_resolution | Checks if the scoped country is currently proposing any, or a specific, resolution | is_proposing_resolution = <resolution/any> | country |

| position_on_current_resolution | Checks if the current country is supporting, opposing or abstaining from the currently proposed galcom resolution. | position_on_current_resolution = support/oppose/abstain | country |
| position_on_last_resolution | Checks if the current country was supporting, opposing or abstaining from the last proposed galcom resolution. | position_on_last_resolution = support/oppose/abstain | country |
| is_galactic_community_member | Checks if scoped country is part of the Galactic Community | is_galactic_community_member = yes/no | country |
| has_galactic_community_emissary | Checks if scoped country has an Emissary assigned to the Galactic Community | has_galactic_community_emissary = yes/no | country |
| has_passed_resolution | Checks if country has passed a Galactic Community resolution in last x days/months/years | has_passed_resolution = { days/months/years = <int32> } | country |
| is_part_of_galactic_council | Checks if scoped country is part of the Galactic Council | is_part_of_galactic_council = yes/no | country |
| has_origin | Checks if scoped country has specified origin | has_origin = <origin key> | country dlc_recommendation |
| is_last_lost_relic | Checks whether the relic passed in parameter is the last relic lost by the country int the current scope. | is_last_lost_relic = <relic_key> | country |

| is_last_received_relic | Checks whether the relic passed in parameter is the last relic received by the country int the current scope. | is_last_received_relic = <relic_key> | country |
| is_in_breach_of_any | Checks if an empire is in breach of any galactic resolution. | is_in_breach_of_any = yes/no | country |
| in_breach_of | Checks if the scoped country is in breach of the specified resolution (or would be, were it to be enacted) | in_breach_of = <resolution> | country |
| galactic_community_rank | Compares empire rank (sorted by diplomatic weight) in the Galactic Community. NOTE: If the scoped country isn't part of the community this returns -1. | galactic_community_rank >= <int32> | country |
| is_permanent_councillor | Checks if an empire has a permanent seat on the Galactic Council | is_permanent_councillor = yes/no | country |
| num_defensive_pacts | Checks the number of defensive pacts the current country has. | num_defensive_pacts > 2 | country |
| num_support_independence | Checks the number of empires the current country is supporting the independence of. | num_support_independence > 2 | country |
| num_guarantees | Checks the number of empires the current country is guaranteeing. | num_guarantees > 2 | country |
| num_non_aggression_pacts | Checks the number of non-aggression pacts the current country has. | num_non_aggression_pacts > 2 | country |

| num_commercial_pacts | Checks the number of commercial pacts the current country has. | num_commercial_pacts > 2 | country |
| num_research_agreements | Checks the number of research agreements a country has | num_research_agreements > 2 | country |
| num_migration_pacts | Checks the number of migration pacts a country has | num_migration_pacts > 2 | country |
| num_rivals | Checks the number of rivalries a country has | num_rivals > 2 | country |
| num_closed_borders | Checks the number of countries the country has closed borders to | num_closed_borders > 2 | country |
| num_truces | Checks the number of truces country has | num_truces > 2 | country |
| has_active_first_contact_with | Checks if the scoped country has an active First Contact site with the target country | has_active_first_contact_with = <country> | country |
| can_have_first_contact_site_with | Checks if the scoped country is allowed to have a First Contact site with the target country | can_have_first_contact_site_with = <country> | country |
| has_spynetwork | Checks if scoped country has any spynetworks with a value > 0 | has_spynetwork = yes | country |
| has_crisis_perk | Checks if a country has a specific Crisis Perk unlocked. | has_crisis_perk = <crisis_perk_name> | country |
| has_menace_perk | Checks if a country has a specific Menace Perk unlocked. | has_menace_perk = <crisis_perk_name> | country |

| is_running_espionage_operation | Checks if the scope is currently running an espionage operation | is_running_espionage_operation = <bool> | country spy_network |
| relative_encryption_decryption | Divides the encryption value of the scope object with the decryption value of the target and compares with value. Target is only used for country scope. | relative_encryption_decryption = { target = <country> value > 1.0/variable } | country spy_network espionage_operation |
| has_crisis_level | Checks if a country has a specific Crisis Level unlocked. | has_crisis_level = <crisis_level_name> | country |
| is_counter_espionage | Compares counter espionage of the scoped object | is_counter_espionage >= <value> | country |
| has_embassy | Check if the country has an embassy with the target country | has_embassy = <target> | country |
| is_action_active | Check if a trade action is already active in a trade deal with the specified empire (or with any empire if so specified) | is_action_active = { action = <action_key> with_country = <other_country_scope/any> } | country |
| is_offer_terms_actual | Checks if terms of the special offer between scoped and target countries is not obsolete | Only works in certain parts of the script marked with ai_trade_facility. is_offer_terms_actual = { target = <country> } | country |

| can_afford_special_offer | Checks if the scoped country can afford the offer given by the target country. Only works in certain parts of the script marked with ai_trade_facility. | can_afford_special_offer = { target = <country> } | country |
| enclave_capacity_left | Checks the country's free enclave number capacity in absolute numbers | enclave_capacity_left > 1 | country |
| has_awareness | Checks the country's awareness if it's pre-FTL | has_awareness < 90 | country |
| current_awareness_level | Checks the country's awareness level if it's pre-FTL | current_awareness_level > none/low/medium/high/full | country |
| has_next_pre_ftl_age | Checks if the country is a pre-FTL civilization and has another pre-FTL tech age after its current one | has_next_pre_ftl_age = yes | country |
| has_pre_ftl_age | Checks if the country is a pre-FTL civilization and is in the specified age | has_pre_ftl_age = <age_key> | country |
| triumph_days_left | Checks the number of days left for the Relics Triumph | triumph_days_left > 900 | country |
| num_positive_traits | Checks the country/pop/leader/species' number of positive traits (traits with a cost strictly greater than 0 count as positive) | num_positive_traits < 3 | country pop pop_group leader species |

| num_negative_traits | Checks the country/pop/leader/species' number of negative traits (traits with a cost strictly lower than 0 count as negative) | num_negative_traits < 3 | country pop pop_group leader species |
| astral_rifts_completed | Return how many Astral Rifts were completed by the country | astral_rifts_completed ><= <int> | country |
| is_astral_rift_explored | Returns true if the astral rift with the given id is or was explored by the scoped country | is_astral_rift_explored = <rift_id> | country |
| is_last_acquired_specimen | Checks if the specified specimen was the last acquired one | last_acquired_specimen = <specimen> | country |
| can_give_specimen | Checks if can give a specific specimen. Checks if specimen is already given and if there is an available exhibit slot | can_give_specimen = <specimen> | country |
| num_cosmic_storms_encountered | Returns the amount of all storms the country was affected by. Storms that leave stop affecting the country to return to it later are counted as multiple |  | country |
| num_unique_cosmic_storms_encountered | Returns the amount of all unique storms the country was affected by. Storms that leave stop affecting the country to return to it later are counted as one |  | country |
| num_vivarium_slots | Returns the country's used Vivarium slots | num_vivarium_slots > 0 | country |

| has_specimen | Checks if the scoped country has the specified specimen | has_specimen = <specimen_key/exhibit> | country |
| count_used_naval_cap | Checks used naval cap by the scoped country or fleet's controlled ships which fulfill the specified criteria. | count_used_naval_cap = { limit = { <triggers> } count < 6 } | country ship fleet |
| has_dna | Check if dna has been acquired for the given category | has_dna = { ship_category = <key> rarity=<key> (optional) } | country |
| is_last_acquired_specimen_rarity | Checks if the last acquired specimen is of the given rarity | is_last_acquired_specimen_rarity = <rarity> | country |
| uses_ship_category | Checks if the graphical culture used by the scoped country allows for usage of a given ship category | uses_ship_category = <category> | country |
| is_market_leader | Checks if country owns the galactic market: | is_market_leader = yes/no | country |
| used_favors_on_last_resolution | Checks scoped country's called in favors used to pass the last resolution | used_favors_on_last_resolution >=< <int32> | country |
| num_proxy_war | Checks the number of started proxy wars by the scoped country | num_proxy_war >=< <value> | country |
| has_patron_aura | Check if the scoped country has a psionic aura from given patron. | has_patron_aura = the_eater_of_worlds | country |

| has_patron_relation | Check if the scoped country has established a relation with given patron. The contact state can be specified (completed by default). | has_patron_relation = { patron = <patron_key / any> contact (optional) = <completed (default)/in_progress/none/any> } | country |
| is_last_acquired_specimen_from_trade | Checks if the last acquired specimen was acquired through a trade deal | is_last_acquired_specimen_from_trade = <yes/no> | country |
| is_default_species | checks if the scoped country has the target species set a default for its species group. | is_default_species = <target> | country |
| has_active_focus | Checks if a country has a particular focus card active active | has_active_focus = <focus_card_key> | country |
| has_completed_focus | Checks if a country has a particular focus card completed | has_completed_focus = <focus_card_key> | country |
| total_country_workforce_with_job_tag | Checks how much workforce that has jobs with all given tags in a country | total_country_workforce_with_job_tag = { tags = { farmer trader } value = 1000 } | country |
| category_last_picked_tradition | Checks if the last picked tradition has the given tradition category. If there is no last picked tradition set, returns false. | category_last_picked_tradition = tradition_example | country |

| has_covenant | Checks if the current country has a covenant with the given patron. | has_covenant = the_eater_of_worlds | country |
| last_completed_special_project_has_research_cost | Checks if the last completed special project by the scoped country has a research cost. | last_completed_special_project_has_research_cost = yes | country |
| is_researching_any_technology | Checks if the country is currently researching any technology. | is_researching_any_technology = <yes/no> | country |
| is_last_increased_tech_repeatable | Checks if the last increased tech is repeatable | is_last_increased_tech_repeatable = yes | country |
| is_last_increased_tech_rare | Checks if the last increased tech is rare | is_last_increased_tech_rare = yes | country |
| is_last_increased_tech_category | Checks if the last increased tech is of the specified category: | is_last_increased_tech_category = psionics | country |
| get_attunement_points_for | Checks the amount of attunement points earned for a specified patron. | get_attunement_points_for = { patron = <key> value = <int/variable> negative = <yes/no> (default = no, authorize negative attunement) } | country |
| is_cardinal_patron | Checks if the given patron is cardinal (if it has its own quadrant in the shroud wheel). | is_cardinal_patron = whisperers_in_the_void | country |

| count_systems_with_aura | Checks the amount of systems covered by the country's aura | count_systems_with_aura > 50 | country |
| count_unlocked_active_accords | Checks the number of active accords unlocked by the country | count_unlocked_active_accords > 2 | country |
| is_preferred_patron | Check scoped country AI's preferred patron. | is_preferred_patron = the_eater_of_worlds | country |
| has_most_attunement | Check if specified patron is scoped country's most attuned patron. | has_most_attunement = the_eater_of_worlds | country |
| patron_has_all_accords_unlocked | Check if specified patron has unlocked every accord and every covenant power. | patron_has_all_accords_unlocked = the_eater_of_worlds | country |
| has_patron_counter | Checks if the scoped country can increment towards given counter | has_patron_counter = po_grow_pop | country |
| any_agreement | Iterate through each agreement - checks whether the enclosed triggers return true for any of them | any_agreement = { <triggers> } | country no_scope |
| count_agreement | Iterate through each agreement - checks whether the enclosed triggers return true for X/all of them | count_agreement = { count = <num/all/variable> limit = { <triggers> } } | country no_scope |

| any_owned_army | Iterate through each army that is owned by the country - checks whether the enclosed triggers return true for any of them | any_owned_army = { <triggers> } | country |
| count_owned_army | Iterate through each army that is owned by the country - checks whether the enclosed triggers return true for X/all of them | count_owned_army = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_owned_storm_influence_field | Iterate through all influence fields owned by a country - checks whether the enclosed triggers return true for any of them | any_owned_storm_influence_field = { <triggers> } | country |
| count_owned_storm_influence_field | Iterate through all influence fields owned by a country - checks whether the enclosed triggers return true for X/all of them | count_owned_storm_influence_field = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_relation | Iterate through all relations - checks whether the enclosed triggers return true for any of them | any_relation = { <triggers> } | country |
| count_relation | Iterate through all relations - checks whether the enclosed triggers return true for X/all of them | count_relation = { count = <num/all/variable> limit = { <triggers> } } | country |

| any_neighbor_country | Iterate through all neighbor countries - checks whether the enclosed triggers return true for any of them | any_neighbor_country = { <triggers> } | country |
| count_neighbor_country | Iterate through all neighbor countries - checks whether the enclosed triggers return true for X/all of them | count_neighbor_country = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_rival_country | Iterate through all countries rivalled by the scoped country - checks whether the enclosed triggers return true for any of them | any_rival_country = { <triggers> } | country |
| count_rival_country | Iterate through all countries rivalled by the scoped country - checks whether the enclosed triggers return true for X/all of them | count_rival_country = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_federation_ally | Iterate through all countries in a federation with the scoped country - checks whether the enclosed triggers return true for any of them | any_federation_ally = { <triggers> } | country |
| count_federation_ally | Iterate through all countries in a federation with the scoped country - checks whether the enclosed triggers return true for X/all of them | count_federation_ally = { count = <num/all/variable> limit = { <triggers> } } | country |

| any_subject | Iterate through all subjects of the scoped country - checks whether the enclosed triggers return true for any of them | any_subject = { <triggers> } | country |
| count_subject | Iterate through all subjects of the scoped country - checks whether the enclosed triggers return true for X/all of them | count_subject = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_available_debris | Iterate through all debris belong to available special projects of the scoped country - checks whether the enclosed triggers return true for any of them | any_available_debris = { <triggers> } | country |
| count_available_debris | Iterate through all debris belong to available special projects of the scoped country - checks whether the enclosed triggers return true for X/all of them | count_available_debris = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_pre_ftl_within_border | Iterate through all pre-ftl countries within the country's or sector's borders - checks whether the enclosed triggers return true for any of them | any_pre_ftl_within_border = { <triggers> } | country sector |

| count_pre_ftl_within_border | Iterate through all pre-ftl countries within the country's or sector's borders - checks whether the enclosed triggers return true for X/all of them | count_pre_ftl_within_border = { count = <num/all/variable> limit = { <triggers> } } | country sector |
| any_observed_pre_ftl_within_border | Iterate through all pre-ftl countries with an observation post around their capital within the country's or sector's borders - checks whether the enclosed triggers return true for any of them | any_observed_pre_ftl_within_border = { <triggers> } | country sector |
| count_observed_pre_ftl_within_border | Iterate through all pre-ftl countries with an observation post around their capital within the country's or sector's borders - checks whether the enclosed triggers return true for X/all of them | count_observed_pre_ftl_within_border = { count = <num/all/variable> limit = { <triggers> } } | country sector |
| any_owned_design | Iterate through all designs owned by the current country - checks whether the enclosed triggers return true for any of them | any_owned_design = { <triggers> } | country |
| count_owned_design | Iterate through all designs owned by the current country - checks whether the enclosed triggers return true for X/all of them | count_owned_design = { count = <num/all/variable> limit = { <triggers> } } | country |

| any_spynetwork | Iterate through each spynetwork - checks whether the enclosed triggers return true for any of them | any_spynetwork = { <triggers> } | country no_scope |
| count_spynetwork | Iterate through each spynetwork - checks whether the enclosed triggers return true for X/all of them | count_spynetwork = { count = <num/all/variable> limit = { <triggers> } } | country no_scope |
| any_espionage_operation | Iterate through each espionage operation - checks whether the enclosed triggers return true for any of them | any_espionage_operation = { <triggers> } | country no_scope spy_network |
| count_espionage_operation | Iterate through each espionage operation - checks whether the enclosed triggers return true for X/all of them | count_espionage_operation = { count = <num/all/variable> limit = { <triggers> } } | country no_scope spy_network |
| any_exhibit | Iterate through every exhibit - checks whether the enclosed triggers return true for any of them | any_exhibit = { <triggers> } | country |
| count_exhibit | Iterate through every exhibit - checks whether the enclosed triggers return true for X/all of them | count_exhibit = { count = <num/all/variable> limit = { <triggers> } } | country |

| any_first_contact | Iterate through each first contact (both active and complete) that this country is engaging in - checks whether the enclosed triggers return true for any of them | any_first_contact = { <triggers> } | country |
| count_first_contact | Iterate through each first contact (both active and complete) that this country is engaging in - checks whether the enclosed triggers return true for X/all of them | count_first_contact = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_active_first_contact | Iterate through each active (non-completed) first contact that this country is engaging in - checks whether the enclosed triggers return true for any of them | any_active_first_contact = { <triggers> } | country |
| count_active_first_contact | Iterate through each active (non-completed) first contact that this country is engaging in - checks whether the enclosed triggers return true for X/all of them | count_active_first_contact = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_owned_fleet | Iterate through each fleet owned by the country - checks whether the enclosed triggers return true for any of them | any_owned_fleet = { <triggers> } | country |

| count_owned_fleet | Iterate through each fleet owned by the country - checks whether the enclosed triggers return true for X/all of them | count_owned_fleet = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_controlled_fleet | Iterate through each fleet controlled by the country - checks whether the enclosed triggers return true for any of them | any_controlled_fleet = { <triggers> } | country |
| count_controlled_fleet | Iterate through each fleet controlled by the country - checks whether the enclosed triggers return true for X/all of them | count_controlled_fleet = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_orbital_station | Iterate through each orbital station owned by the current country or in the current system - checks whether the enclosed triggers return true for any of them | any_orbital_station = { <triggers> } | country galactic_object |
| count_orbital_station | Iterate through each orbital station owned by the current country or in the current system - checks whether the enclosed triggers return true for X/all of them | count_orbital_station = { count = <num/all/variable> limit = { <triggers> } } | country galactic_object |

| any_owned_leader | Iterate through each leader that is owned by the country - checks whether the enclosed triggers return true for any of them | any_owned_leader = { <triggers> } | country |
| count_owned_leader | Iterate through each leader that is owned by the country - checks whether the enclosed triggers return true for X/all of them | count_owned_leader = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_pool_leader | Iterate through each leader that is recruitable for the country - checks whether the enclosed triggers return true for any of them | any_pool_leader = { <triggers> } | country |
| count_pool_leader | Iterate through each leader that is recruitable for the country - checks whether the enclosed triggers return true for X/all of them | count_pool_leader = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_envoy | Iterate through each envoy available to the country - checks whether the enclosed triggers return true for any of them | any_envoy = { <triggers> } | country |
| count_envoy | Iterate through each envoy available to the country - checks whether the enclosed triggers return true for X/all of them | count_envoy = { count = <num/all/variable> limit = { <triggers> } } | country |

| any_owned_megastructure | Iterate through each owned megastructure - checks whether the enclosed triggers return true for any of them | any_owned_megastructure = { <triggers> } | country |
| count_owned_megastructure | Iterate through each owned megastructure - checks whether the enclosed triggers return true for X/all of them | count_owned_megastructure = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_planet_within_border | Iterate through each planet within the current empire's borders - checks whether the enclosed triggers return true for any of them | any_planet_within_border = { <triggers> } | country |
| count_planet_within_border | Iterate through each planet within the current empire's borders - checks whether the enclosed triggers return true for X/all of them | count_planet_within_border = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_owned_planet | Iterate through each inhabited planet owned by the current empire - checks whether the enclosed triggers return true for any of them | any_owned_planet = { <triggers> } | country sector |
| count_owned_planet | Iterate through each inhabited planet owned by the current empire - checks whether the enclosed triggers return true for X/all of them | count_owned_planet = { count = <num/all/variable> limit = { <triggers> } } | country sector |

| any_controlled_planet | Iterate through each inhabited planet controlled by the current empire - checks whether the enclosed triggers return true for any of them | any_controlled_planet = { <triggers> } | country |
| count_controlled_planet | Iterate through each inhabited planet controlled by the current empire - checks whether the enclosed triggers return true for X/all of them | count_controlled_planet = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_pop_faction | Iterate through all the country's pop factions - checks whether the enclosed triggers return true for any of them | any_pop_faction = { <triggers> } | country |
| count_pop_faction | Iterate through all the country's pop factions - checks whether the enclosed triggers return true for X/all of them | count_pop_faction = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_owned_sector | Iterate through every owned sector - checks whether the enclosed triggers return true for any of them | any_owned_sector = { <triggers> } | country |
| count_owned_sector | Iterate through every owned sector - checks whether the enclosed triggers return true for X/all of them | count_owned_sector = { count = <num/all/variable> limit = { <triggers> } } | country |

| any_owned_ship | Iterate through each ship in the fleet or controlled by the country - checks whether the enclosed triggers return true for any of them | any_owned_ship = { <triggers> } | country fleet |
| count_owned_ship | Iterate through each ship in the fleet or controlled by the country - checks whether the enclosed triggers return true for X/all of them | count_owned_ship = { count = <num/all/variable> limit = { <triggers> } } | country fleet |
| any_controlled_ship | Iterate through each ship in the fleet or controlled by the country - checks whether the enclosed triggers return true for any of them | any_controlled_ship = { <triggers> } | country fleet |
| count_controlled_ship | Iterate through each ship in the fleet or controlled by the country - checks whether the enclosed triggers return true for X/all of them | count_controlled_ship = { count = <num/all/variable> limit = { <triggers> } } | country fleet |
| any_system_with_aura | Iterate through every system with an Aura - checks whether the enclosed triggers return true for any of them | any_system_with_aura = { <triggers> } | country |
| count_system_with_aura | Iterate through every system with an Aura - checks whether the enclosed triggers return true for X/all of them | count_system_with_aura = { count = <num/all/variable> limit = { <triggers> } } | country |

| any_situation | Iterate through each situation a country is experiencing - checks whether the enclosed triggers return true for any of them | any_situation = { <triggers> } | country |
| count_situation | Iterate through each situation a country is experiencing - checks whether the enclosed triggers return true for X/all of them | count_situation = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_owned_pop_species | Iterate through each species of a country's owned pops - checks whether the enclosed triggers return true for any of them | any_owned_pop_species = { <triggers> } | country |
| count_owned_pop_species | Iterate through each species of a country's owned pops - checks whether the enclosed triggers return true for X/all of them | count_owned_pop_species = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_owned_starbase | Iterate through every owned primary starbase - checks whether the enclosed triggers return true for any of them | any_owned_starbase = { <triggers> } | country |
| count_owned_starbase | Iterate through every owned primary starbase - checks whether the enclosed triggers return true for X/all of them | count_owned_starbase = { count = <num/all/variable> limit = { <triggers> } } | country |

| any_owned_nonprimary_starbase | Iterate through every owned non-primary starbase (e.g. orbital rings), not including juggernauts - checks whether the enclosed triggers return true for any of them | any_owned_nonprimary_starbase = { <triggers> } | country |
| count_owned_nonprimary_starbase | Iterate through every owned non-primary starbase (e.g. orbital rings), not including juggernauts - checks whether the enclosed triggers return true for X/all of them | count_owned_nonprimary_starbase = { count = <num/all/variable> limit = { <triggers> } } | country |
| any_system_within_border | Iterate through all systems within the country's or sector's borders - checks whether the enclosed triggers return true for any of them | any_system_within_border = { <triggers> } | country sector |
| count_system_within_border | Iterate through all systems within the country's or sector's borders - checks whether the enclosed triggers return true for X/all of them | count_system_within_border = { count = <num/all/variable> limit = { <triggers> } } | country sector |
| any_war | Iterate through all wars the country is engaged in - checks whether the enclosed triggers return true for any of them | any_war = { <triggers> } | country |

| count_war | Iterate through all wars the country is engaged in - checks whether the enclosed triggers return true for X/all of them | count_war = { count = <num/all/variable> limit = { <triggers> } } | country |

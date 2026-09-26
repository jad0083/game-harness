# Conditions — leader, federation, war, espionage and other scopes
Source: https://stellaris.paradoxwikis.com/Conditions
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260716201409 (the live wiki blocks non-browser clients). Page version banner: Version Please help with verifying or updating older sections of this article. At least some were last verified for version 4.3. This article is for the PC version of Stellaris only._

Rows whose first listed scope is: any other scope.

| Name | Desc | Example | Scopes |
|---|---|---|---|
| leader_years_of_service | Checks the scope leader's years of service | years_of_service > 25 | leader |
| num_leader_traits | Checks the number of leader traits or total tiers of traits for a specific leader | num_leader_traits = { value > 2/variable is_councilor = <any(default)/yes(only)/no(only)> negative <any(default)/no(only)/yes(only)> count_tiers = <yes/no(default)> contains_modifier = { string = "federation" type=<any(default)/yes(only)/no(only) # filters on whether the trait has a modifier that contains the string "string"is_subclass = <any(default)/yes(only)/no(only) } | leader |
| is_ruler | Checks if scoped leader is the Ruler of the Empire | is_ruler = yes/no | leader |
| is_heir | Checks if scoped leader is the Heir of the Empire | is_heir = yes/no | leader |
| agreement_preset | Checks if the agreement has the specified preset | agreement_preset = <preset key> | agreement |
| faction_approval | Checks the scoped faction's approval percentage | faction_approval < 0.9 | pop_faction |
| num_ships_in_debris | Checks the number of ships of a ship size in debris | num_ships_in_debris = { ship_size = corvette value > 15 } | debris |
| gender | Checks the leader's gender | gender = female/male/indeterminable | leader |
| leader_class | Checks if the leader is of a specific class | leader_class = scientist | leader |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| leader_age | Checks the scope leader's age | leader_age > 85 | leader |
| leader_lifespan | Checks the scope leader's lifespan | leader_lifespan > 85 | leader |
| check_pop_faction_parameter | Checks if one of the faction's parameters is the same as target scope | check_pop_faction_parameter = { which = <parameter> value = <target> } | pop_faction |
| is_councilor_type | Checks if the leader holds a specific Councilor type | is_councilor_type = councilor_research | leader |
| has_stage_modifier | Checks if the espionage operation has a certain modifier specific for the current stage | has_stage_modifier = <modifier> | espionage_operation astral_rift |
| name_list_category | Checks if a specific name list is used for the a species during empire creation |  | dlc_recommendation |
| current_stage | Checks if the specified stage is currently active in the scoped situation. | current_stage = <stage> (name defined in situation's stages) | situation |
| is_leader_tier | Checks if the tier of the leader is what is provided. | is_leader_tier = leader_tier_default | leader |
| must_scavenge | Checks if the debris is set as "must scavenge" | must_scavenge = yes/no | debris |
| must_research | Checks if the debris is set as "must research" | must_research = yes/no | debris |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| is_immortal | Checks if the leader is immortal (either by script effect or species characteristics) | is_immortal = yes/no | leader |
| is_hidden | Checks if the leader is hidden from the player | is_hidden = yes/no | leader |
| num_candidate_supported | Compares the number of times an election candidate was supported. | num_candidate_supported >= <value> | leader |
| has_background_job | Checks if the leader's background contains a specific previous job, or any job if set to yes | has_background_job = <key/yes> | leader |
| is_faction_extorted | Checks if the scoped pop faction is extorted | is_faction_extorted = yes/no | pop_faction |
| has_first_contact_flag | Checks if the first contact site has a specific flag | has_first_contact_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | first_contact |
| has_situation_flag | Checks if the situation has a specific flag | has_situation_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | situation |
| has_agreement_flag | Checks if the agreement has a specific flag | has_agreement_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | agreement |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| has_federation_flag | Checks if the federation has a specific flag | has_federation_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | federation |
| has_war_flag | Checks if the war has a specific flag | has_war_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | war |
| has_archaeology_flag | Checks if the archaeological site has a specific flag | has_archaeology_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | archaeological_site |
| has_spynetwork_flag | Checks if the spy network has a specific flag | has_spynetwork_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | spy_network |
| has_espionage_asset_flag | Checks if the espionage asset has a specific flag | has_espionage_asset_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | espionage_asset |
| is_idle | Checks if scoped leader is idle | is_idle = yes | leader |
| has_envoy_task | Checks the scoped leader's diplomatic/envoy task. | has_envoy_task = { task = improve_relations/harm_relations/federation/galactic_community/spy_network/first_contact/strengthen_imperial_authority/undermine_imperial_authority/none target = <country> (optional) } | leader |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| has_envoy_cooldown | Checks the scoped envoy currently has a cooldown on its status. | has_envoy_cooldown = yes/no | leader |
| support | Checks the support level of a faction, or that of a leader's faction(s) | support > 0.5 | leader pop_faction |
| is_pop_faction_type | Checks the faction's type | is_pop_faction_type = isolationist | pop_faction |
| situation_progress | Checks if the scoped situation's progress is a certain value. | situation_progress > 15 | situation |
| situation_monthly_progress | Checks if the scoped situation's monthly progress is a certain value. Returns the cached value from the last monthly tick. | situation_monthly_progress > 1 | situation |
| is_situation_type | Checks if the scoped situation is a certain type. | is_situation_type = my_situation_type | situation |
| current_situation_approach | Checks if the specified approach has been picked on the scoped situation. | current_situation_approach = <approach> (name field of the approach) | situation |
| can_set_situation_approach | Checks if the specified approach is allowed to be picked (according to potential and allow triggers) on the scoped situation. | can_set_situation_approach = <approach> (name field of the approach) | situation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| has_leader_flag | Checks if the leader has a specific flag | has_leader_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | leader |
| is_background_planet | Check if a planet is the background planet of a leader | is_background_planet = <target> | leader |
| count_war_participants | Checks the number of participants in the war on a specific side that meet the specified criteria | count_war_participants = { limit = { <triggers> } side = target count < 4/variable | war |
| has_base_skill | Checks if the leader has a specific base experience level | has_base_skill > 2 | leader |
| has_total_skill | Checks if the leader has a specific total (base + effective) experience level | has_total_skill > 2 | leader |
| has_experience | Checks if the leader has a specific amount of experience | has_experience < 900 | leader |
| war_begun_num_fleets_gone_mia | Checks amount of target country's fleets that went MIA when the war began | war_begun_num_fleets_gone_mia = { who = <target> value < 10 } | war |
| is_event_leader | Checks if a leader is a special event leader (defined in create_leader) | is_event_leader = no | leader |
| has_ruler_trait | Checks if a leader has a certain ruler trait, even if they are not currently ruler | has_ruler_trait = leader_trait_carefree | leader |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| attacker_war_exhaustion | Checks the war exhaustion of the war's attackers | attacker_war_exhaustion > 0.6 | war |
| defender_war_exhaustion | Checks the war exhaustion of the war's defenders | defender_war_exhaustion < 0.2 | war |
| using_war_goal | Checks if a war has a specific war goal | using_war_goal = { type = <war goal> owner = <eventtarget, country> } | war |
| has_specialist_perk | Checks if the agreement has a specific specialist perk active | has_specialist_perk = <perk_key> | agreement |
| has_active_specialization | Checks if the agreement has an active specialization of the specified type, or of any type if 'any' is specified | has_active_specialization = <specialist_type_key/any> | agreement |
| specialist_tier | Checks the specialization tier of the subject of the agreement. | specialist_tier >=< 2 | agreement |
| is_total_war | Checks if a war is a total war | is_total_war = yes/no | war |
| is_site_last_die_result | Compares the last dice roll. | is_site_last_die_result >= <int> | archaeological_site first_contact astral_rift |
| is_current_stage_difficulty | Compares the current stage difficulty. | is_current_stage_difficulty >= <int> | archaeological_site first_contact astral_rift |
| is_site_at_stage | Compares the current stage index. | is_site_at_stage >= <int> | archaeological_site |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| is_current_stage_clues | Compares the current stage clues. | is_current_stage_clues >= <int> | archaeological_site first_contact |
| is_site_days_to_next_die_roll | Compares days to next die roll. | is_site_days_to_next_die_roll >= <int> | archaeological_site first_contact |
| is_site_last_excavator | Checks last excavating country. | is_site_last_excavator = <country> | archaeological_site |
| is_site_type | Checks the type of the site. | is_site_type = <archaeological site type key> | archaeological_site |
| is_site_completed | Checks if the site has been completed. | is_site_completed = yes/no | archaeological_site first_contact |
| is_site_under_excavation | Checks if the site is currently being excavated. | is_site_under_excavation = yes/no | archaeological_site |
| is_site_locked | Checks if an archaeological site has progression locked or not. | is_site_locked = yes/no | archaeological_site |
| is_site_current_stage_score | Compares the current stage discovery score. | is_site_current_stage_score >= <int> | archaeological_site first_contact astral_rift |
| is_site_current_stage_score_no_die | Compares the current stage discovery score excluding the current die roll. | is_site_current_stage_score_no_die >= <int> | archaeological_site first_contact astral_rift |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| is_current_excavator_fleet | Checks current excavator fleet. | is_current_excavator_fleet = <fleet> | archaeological_site |
| federation_experience | Checks experience of the federation. | federation_experience >=< 40); | federation |
| federation_cohesion | Checks cohesion of the federation. | federation_cohesion >=< 40); | federation |
| federation_cohesion_growth | Checks cohesion growth of the federation. | federation_cohesion_growth >=< 40); | federation |
| has_any_federation_law_in_category | Checks if given law category has any active law | has_any_federation_law_in_category = <federation law category> | federation |
| has_federation_law | Checks if given law has been enacted in scoped federation | has_federation_law = <federation law> | federation |
| has_federation_perk | Checks if given perk has been unlocked in scoped federation | has_federation_perk = <federation perk> | federation |
| has_federation_type | Checks if federation has specific federation type | has_federation_type = <federation type> | federation |
| federation_level | Checks federation level in comparison to given value in scoped federation | federation_level >=< <federation level> | federation |
| num_members | Checks number of members in scoped federation | num_members >=< <integer value> | federation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| num_associates | Checks number of associates in scoped federation | num_associates >=< <integer value> | federation |
| is_councilor | Checks if scoped leader is a member of the Empire Council or the Ruler | is_councilor = yes/no | leader |
| has_federation_setting | Checks if given setting is on for scoped federation | has_federation_setting = <setting> | federation |
| is_current_first_contact_stage | Checks if the scoped first contact is at the specified stage. | is_current_first_contact_stage = default_stage_2 | first_contact |
| has_espionage_asset | Checks if the scope hold an asset of specified type | has_espionage_asset = <asset type> | spy_network espionage_operation |
| has_espionage_operation_flag | Checks if the espionage operation has a specific flag | has_espionage_operation_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | espionage_operation |
| has_spy_power | Compares the infiltration level of the network | has_spy_power = <num> | spy_network |
| has_available_spy_power | Compares the available infiltration level of the network | has_available_spy_power = <num> | spy_network |
| has_espionage_category | Checks if the scope is of a specific category | has_espionage_category = <espionage category key> | espionage_operation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| has_espionage_type | Checks if the scope is of a specific type | has_espionage_type = <espionage type key> | espionage_operation |
| is_espionage_operation_days_to_next_die_roll | Compares days to next die roll. | is_espionage_operation_days_to_next_die_roll >= <value> | espionage_operation |
| is_espionage_operation_chapter | Compares the current espionage operation chapter index. | is_espionage_operation_chapter >= <int> | espionage_operation |
| is_espionage_operation_difficulty | Compares the espionage operation difficulty. | is_espionage_operation_difficulty >= <value> | espionage_operation |
| is_espionage_operation_score_no_die | Compares the current espionage score excluding the current die roll. | is_espionage_operation_score_no_die >= <value> | espionage_operation |
| is_espionage_operation_score | Compares the current espionage score. | is_espionage_operation_score >= <value> | espionage_operation |
| is_espionage_operation_last_die_result | Compares the last dice roll. | is_espionage_operation_last_die_result >= <int> | espionage_operation |
| is_espionage_operation_auto_accept_events | Checks if scoped espionage operation accepts events automatically when they are ready | is_espionage_operation_auto_accept_events = <bool> | espionage_operation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| num_espionage_assets | Compares the number of assets associated with the scope object. | num_espionage_assets = <int> | spy_network espionage_operation |
| has_spynetwork_value | Compares spy network value of the scoped object | has_spynetwork_value >= <value> | spy_network |
| is_spynetwork_level | Compares spy network level of the scoped object | is_spynetwork_level >= <int> | spy_network |
| is_spynetwork_max_level | Compares spy network max level of the scoped object | is_spynetwork_max_level >= <int> | spy_network |
| has_term_value | Checks if the agreement has a specific term | has_term_value = { term = <term> value = <term_value> } | agreement |
| is_exhibit_active | Check if the scoped exhibit is active | is_exhibit_active = <yes/no> | exhibit |
| is_specimen_rarity | Checks if the specified specimen contained by the scoped exhibit is of indicated rarity | is_specimen_rarity = <rarity> | exhibit |
| is_specimen_category | Checks if the specified specimen contained by the scoped exhibit is of indicated collection category | is_specimen_category = <specimen_type> | exhibit |
| trait_has_all_tags | Checks if a trait has all tags in the list | trait_has_all_tags = { biological lithoids } | trait |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| trait_has_any_tag | Checks if a trait has at least one tag from the list | trait_has_any_tag = { biological lithoids } | trait |
| is_from_proxy_war | Checks if a war was started by a proxy war | is_from_proxy_war = yes/no | war |
| any_member | Iterate through each member of the federation - checks whether the enclosed triggers return true for any of them | any_member = { <triggers> } | federation |
| count_member | Iterate through each member of the federation - checks whether the enclosed triggers return true for X/all of them | count_member = { count = <num/all/variable> limit = { <triggers> } } | federation |
| any_associate | Iterate through each associate member of the federation - checks whether the enclosed triggers return true for any of them | any_associate = { <triggers> } | federation |
| count_associate | Iterate through each associate member of the federation - checks whether the enclosed triggers return true for X/all of them | count_associate = { count = <num/all/variable> limit = { <triggers> } } | federation |
| any_war_participant | Iterate through all war participants - checks whether the enclosed triggers return true for any of them | any_war_participant = { <triggers> } | war |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| count_war_participant | Iterate through all war participants - checks whether the enclosed triggers return true for X/all of them | count_war_participant = { count = <num/all/variable> limit = { <triggers> } } | war |
| any_attacker | Iterate through all attackers in the current war - checks whether the enclosed triggers return true for any of them | any_attacker = { <triggers> } | war |
| count_attacker | Iterate through all attackers in the current war - checks whether the enclosed triggers return true for X/all of them | count_attacker = { count = <num/all/variable> limit = { <triggers> } } | war |
| any_defender | Iterate through all defenders in the current war - checks whether the enclosed triggers return true for any of them | any_defender = { <triggers> } | war |
| count_defender | Iterate through all defenders in the current war - checks whether the enclosed triggers return true for X/all of them | count_defender = { count = <num/all/variable> limit = { <triggers> } } | war |

Note: For comparing different game versions of Stellaris triggers (modifiers and effects) since launch, you can use the GitHub file history feature here (created by OldEnt).

## Scripted Triggers

There are more than singular Conditions can be used for a Condition. See dynamic modding for details.

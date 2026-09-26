# Effects — leader, federation, war, espionage and other scopes
Source: https://stellaris.paradoxwikis.com/Effects
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260720111012 (the live wiki blocks non-browser clients). Page version banner: Version Please help with verifying or updating older sections of this article. At least some were last verified for version 4.3. This article is for the PC version of Stellaris only._

Rows whose first listed scope is: any other scope.

| Name | Desc | Example | Scopes |
|---|---|---|---|
| change_background_ethic | Changes the background ethic of a leader | change_background_ethic = <key> | leader |
| set_immortal | Sets the scoped leader immortal. The 'no' case will not override immortality granted by species characteristics (but will disable immortality granted by this effect). | set_immortal = yes | leader |
| freeze_leader_age | Freezes the scoped leader's age. The 'no' case will disable the freeze granted by this effect. | freeze_leader_age = yes | leader |
| set_first_contact_flag | Sets an arbitrarily-named flag on the scoped first contact site | set_first_contact_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | first_contact |
| set_situation_flag | Sets an arbitrarily-named flag on the scoped situation | set_situation_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | situation |
| set_agreement_flag | Sets an arbitrarily-named flag on the scoped agreement | set_agreement_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | agreement |
| set_federation_flag | Sets an arbitrarily-named flag on the scoped federation | set_federation_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | federation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| remove_first_contact_flag | Removes a flag from the scoped first contact site | remove_first_contact_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | first_contact |
| remove_situation_flag | Removes a flag from the scoped situation | remove_situation_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | situation |
| remove_agreement_flag | Removes a flag from the scoped agreement | remove_agreement_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | agreement |
| remove_federation_flag | Removes a flag from the scoped federation | remove_federation_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | federation |
| add_experience | Adds a sum of experience points to the scoped leader | add_experience = 200 | leader |
| set_war_flag | Sets an arbitrarily-named flag on the scoped war | set_war_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | war |
| set_archaeology_flag | Sets an arbitrarily-named flag on the scoped arc site | set_archaeology_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | archaeological_site |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| set_spynetwork_flag | Sets an arbitrarily-named flag on the scoped spy network | set_spynetwork_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | spy_network |
| set_espionage_asset_flag | Sets an arbitrarily-named flag on the scoped espionage asset | set_espionage_asset_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | espionage_asset |
| remove_war_flag | Removes a flag from the scoped war | remove_war_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | war |
| remove_archaeology_flag | Removes a flag from the scoped arc site | remove_archaeology_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | archaeological_site |
| remove_spynetwork_flag | Removes a flag from the scoped spy network | remove_spynetwork_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | spy_network |
| remove_espionage_asset_flag | Removes a flag from the scoped espionage asset | remove_espionage_asset_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | espionage_asset |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| add_trait | Adds a specific trait to the scoped leader or a random common/negative trait | add_trait = <trait>/random_common/random_negative or add_trait = { trait = <trait>/random_common/random_negative consume_selection = yes/no (if yes and leader has unspent trait selections, consume one of them; default: no) show_message = yes/no (default: yes) } | leader |
| remove_trait | Removes a specific trait from the scoped leader, or removes all negative traits | remove_trait = <key/all_negative> | leader |
| remove_all_negative_traits | Removes all negative traits from the scoped leader | remove_all_negative_traits = yes | leader |
| remove_all_positive_traits | Removes all non-negative traits from the scoped leader | remove_all_positive_traits = yes | leader |
| remove_all_traits | Removes all traits from the scoped leader | remove_all_traits = yes | leader |
| set_years_served | Copies years served duration from the target | set_years_served = <target> | leader |
| set_timed_first_contact_flag | Sets an arbitrarily-named flag on the scoped first contact site for a set duration | set_timed_first_contact_flag = { flag = <key> (note: one can use <key>@scope e.g. my_flag@from to track relationships between objects) days/months/years = <int>/<variable> } | first_contact |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| set_timed_situation_flag | Sets an arbitrarily-named flag on the scoped situation for a set duration | set_timed_situation_flag = { flag = <key> (note: one can use <key>@scope e.g. my_flag@from to track relationships between objects) days/months/years = <int>/<variable> } | situation |
| set_timed_agreement_flag | Sets an arbitrarily-named flag on the scoped agreement for a set duration | set_timed_agreement_flag = { flag = <key> (note: one can use <key>@scope e.g. my_flag@from to track relationships between objects) days/months/years = <int>/<variable> } | agreement |
| set_timed_federation_flag | Sets an arbitrarily-named flag on the scoped federation for a set duration | set_timed_federation_flag = { flag = <key> (note: one can use <key>@scope e.g. my_flag@from to track relationships between objects) days/months/years = <int>/<variable> } | federation |
| set_timed_war_flag | Sets an arbitrarily-named flag on the scoped war for a set duration | set_timed_war_flag = { flag = <key> (note: one can use <key>@scope e.g. my_flag@from to track relationships between objects) days/months/years = <int>/<variable> } | war |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| set_timed_archaeology_flag | Sets an arbitrarily-named flag on the scoped arc site for a set duration | set_timed_archaeology_flag = { flag = <key> (note: one can use <key>@scope e.g. my_flag@from to track relationships between objects) days/months/years = <int>/<variable> } | archaeological_site |
| set_timed_spynetwork_flag | Sets an arbitrarily-named flag on the scoped spy network for a set duration | set_timed_spynetwork_flag = { flag = <key> (note: one can use <key>@scope e.g. my_flag@from to track relationships between objects) days/months/years = <int>/<variable> } | spy_network |
| set_timed_espionage_asset_flag | Sets an arbitrarily-named flag on the scoped espionage asset for a set duration | set_timed_espionage_asset_flag = { flag = <key> (note: one can use <key>@scope e.g. my_flag@from to track relationships between objects) days/months/years = <int>/<variable> } | espionage_asset |
| set_leader_flag | Sets an arbitrarily-named flag on the scoped leader | set_leader_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | leader |
| remove_leader_flag | Removes a flag from the scoped leader | remove_leader_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | leader |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| recruitable | Sets scoped leader as non/recruitable | recruitable = yes | leader |
| remove_war_participant | Removes a specified country from the war | remove_war_participant = <target> | war |
| add_skill | Adds to the scoped leader's skill level | add_skill = 2 | leader |
| set_skill | Sets the scoped leader's level | set_skill = 3 | leader |
| set_gender | Sets the gender of the scoped leader | set_gender = female | leader |
| set_timed_leader_flag | Sets an arbitrarily-named flag on the scoped leader for a set duration | set_timed_leader_flag = { flag = <key> (note: one can use <key>@scope e.g. my_flag@from to track relationships between objects) days/months/years = <int>/<variable> } | leader |
| change_leader_portrait | Changes the portrait of the leader in scope. | change_leader_portrait = <key or species event target> | leader |
| change_leader_class | Changes the class of the leader in scope. | change_leader_class = <leader class event target> | leader |
| set_agreement_terms | Sets agreement terms of the agreement. Can be used to set multiple terms at once, including resource subsidies. | set_agreement_terms = { subject_diplomacy = subject_can_not_do_diplomacy subject_integration = subject_can_be_integrated resource_subsidies_alloys = 0.5 } | agreement |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| set_agreement_preset | Sets the preset of an agreement and applies its terms on the agreement if 'apply_terms' is 'yes'. | set_agreement_preset = { preset = <preset key> apply_terms = no #Defaults to 'yes' } | agreement |
| add_timed_trait | Adds a specific trait to the scoped leader for a specific duration | add_timed_trait = { trait = <trait> days/months/years = <value>/<variable> } | leader |
| add_stage_clues | Adds clues to the current stage of an archaeological or first contact site | add_stage_clues = <int> | archaeological_site first_contact astral_rift |
| add_expedition_log_entry | Adds a specific expedition log entry to an archaeological site chapter | add_expedition_log_entry = { title = <loc key> tooltip = <loc key> } | archaeological_site |
| reset_current_stage | Resets the current stage | reset_current_stage = yes/no yes = also randomize new difficulty if stage allows that. no = does not change difficulty | archaeological_site |
| set_current_stage | Sets the current stage for this arc site (first chapter is index 0). | set_current_stage = <stage number> | archaeological_site |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| finish_current_stage | Finish the current stage | finish_current_stage = yes/no/<country> yes = trigger stage completed for each stage and current excavator. no = do not trigger any stage completed country = use this country instead of excavator, no stage complete will be triggered. | archaeological_site |
| finish_site | Finish the whole archaeological site | finish_site = yes/no/<country> yes = trigger stage completed for each stage and current excavator. no = do not trigger any stage completed country = use this country instead of excavator, no stage complete will be triggered. | archaeological_site |
| set_site_progress_locked | Locks or unlocks the progress of a site | set_site_progress_locked = yes/no | archaeological_site first_contact |
| set_federation_law | Sets the given law for the scoped federation | set_federation_law = <federation law> | federation |
| remove_from_empire_council | Removes scoped leader from empire council | remove_from_empire_council = yes | leader |
| set_cooldown | Locks the leader in its current role for the next X days. | set_cooldown = int | leader |
| add_federation_experience | Adds experience to the scoped federation | add_federation_experience = <federation experience> | federation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| set_federation_type | Sets federation type to the scoped federation | set_federation_type = <federation type> | federation |
| set_federation_succession_type | Sets scoped federation's succession type to the specified value. Please don't use outside law on_enact, functional effect! Use set_federation_law and has_federation_law instead. | set_federation_succession_type = <federation succession type> Federation succession types: strongest/diplomatic_weight/rotation/challenge/random | federation |
| set_federation_succession_term | Sets scoped federation's succession term to the specified value. Please don't use outside law on_enact, functional effect! Use set_federation_law and has_federation_law instead. | set_federation_succession_type = <federation succession term> Federation succession terms: status_change/years_10/years_20/years_30/years_40 | federation |
| set_only_leader_builds_fleets | Sets exclusive right to build fleets by federation leader. Please don't use outside law on_enact, functional effect! Use set_federation_law and has_federation_law instead. | set_only_leader_builds_fleets = <yes/no> | federation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| set_allow_subjects_to_join | Sets right for subjects to join federation. Please don't use outside law on_enact, functional effect! Use set_federation_law and has_federation_law instead. | set_allow_subjects_to_join = <yes/no> | federation |
| set_equal_voting_power | Sets different voting weight. Please don't use outside law on_enact, functional effect! Use set_federation_law and has_federation_law instead. | set_equal_voting_power = <yes/no> | federation |
| set_diplomacy_action_setting | Sets diplomatic action custom setting. Please don't use outside law on_enact, functional effect! Use set_federation_law and has_federation_law instead. | set_diplomacy_action_setting = { action = <action_key> settings = { vote_type = default } } | federation |
| set_free_migration | Sets unified migration flag for federation. Please don't use outside law on_enact, functional effect! Use set_federation_law and has_federation_law instead. | set_free_migration = <yes/no> | federation |
| set_federation_settings | Sets diplomatic action custom setting. Please don't use outside law on_enact, functional effect! Use set_federation_law and has_federation_law instead. | set_federation_settings = { <setting> = <value>... } | federation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| add_associate_member | Add specified country as an associate member | add_associate_member = { who = <target> override_requirements = yes/no } | federation |
| remove_associate_member | Removes a specific associate member from the federation | remove_associate_member = { who = <country> override_requirements = yes/no } | federation |
| add_cohesion | Add cohesion to the federation | add_cohesion = <value> | federation |
| add_loyalty | Add loyalty to subject of an agreement | add_loyalty = 5 | agreement |
| set_first_contact_stage | Sets the given stage for the scoped first contact | set_first_contact_stage = <stage name> | first_contact |
| finish_current_operation_stage | Finish the current operation phase | finish_current_operation_stage = yes/no yes = trigger stage completed for each stage and current excavator. no = do not trigger any stage completed | espionage_operation |
| create_espionage_asset | Creates espionage asset within a given spy network | create_espionage_asset = { type = <espionage asset type> effect = { <effects executed on asset> } } | spy_network |
| destroy_espionage_asset | Destroys espionage asset within a given spy network/operation | destroy_espionage_asset = <espionage asset type> | spy_network espionage_operation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| set_espionage_operation_progress_locked | Locks or unlocks the progress of an espionage operation | set_espionage_operation_progress_locked = yes/no | espionage_operation |
| unassign_espionage_asset | Unassigns espionage asset from the scope operation to owning spy network | unassign_espionage_asset = <espionage asset type> | espionage_operation |
| assign_espionage_asset | Assigns espionage asset to the scope operation from owning spy network | assign_espionage_asset = <espionage asset type> | espionage_operation |
| set_espionage_operation_flag | Sets an arbitrarily-named flag on the scoped espionage operation | set_espionage_operation_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | espionage_operation |
| remove_espionage_operation_flag | Removes a flag from the scoped espionage operation | remove_espionage_operation_flag = <key> (note: one can use e.g. my_flag@from to track relationships between objects) | espionage_operation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| espionage_operation_event | Fires a espionage event event for the scoped object, with optional DAYS and RANDOM delay | espionage_operation_event = { id = <id> days = x (optional: specify delay) random = y (optional: specify random delay from 0 to value, which is added on to the 'days' delay) scopes = { from = fromfrom } (optional: specify scope overrides) } | espionage_operation |
| dissolve_federation | Dissolved the current federation | dissolve_federation = yes | federation |
| set_timed_espionage_operation_flag | Sets an arbitrarily-named flag on the scoped espionage operation for a set duration | set_timed_espionage_operation_flag = { flag = <key> (note: one can use <key>@scope e.g. my_flag@from to track relationships between objects) days/months/years = <int>/<variable> } | espionage_operation |
| add_espionage_information | Adds information to the current stage of an espionage operation | add_espionage_information = <value> | espionage_operation |
| add_situation_progress | Adds progress to scoped situation | add_situation_progress = 5.5 | situation |
| set_situation_progress | Sets the progress of scoped situation | set_situation_progress = 5.5 | situation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| set_situation_approach | Sets the approach to the Situation. Respects allow and potential triggers. | set_situation_approach = <approach> (name field of the approach) | situation |
| set_situation_locked | Locks the Situation so it will not progress until unlocked. | set_situation_locked = yes/no (no unlocks it) | situation |
| change_situation_target | Changes the target of a Situation. | change_situation_target = none/scope | situation |
| set_rule_can_subject_be_integrated | Changes the agreement term for whether the Subject can be integrated | set_rule_can_subject_be_integrated = <yes/no> | agreement |
| set_rule_can_subject_do_diplomacy | Changes the agreement term for whether the Subject can do diplomacy | set_rule_can_subject_do_diplomacy = <yes/no> | agreement |
| set_rule_can_subject_expand | Changes the agreement term for whether the Subject can expand | set_rule_can_subject_expand = <can_expand/can_expand_with_tithe/cannot_expand> | agreement |
| set_rule_can_subject_vote | Changes the agreement term for whether the Subject can vote independently of its overlord in GalCom/federations | set_rule_can_subject_vote = <yes/no> | agreement |
| set_rule_join_overlord_wars | Changes the agreement term for Subject to join Overlord wars | set_rule_join_overlord_wars = <none/defensive/offensive/all> | agreement |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| set_rule_join_subject_wars | Changes the agreement term for Overlord to wars of its Subject | set_rule_join_subject_wars = <none/defensive/offensive/all> | agreement |
| set_rule_subject_has_access | Changes the agreement term for whether the Subject can access the overlord's territory (and territories the overlord has access to) despite closed borders | set_rule_subject_has_access = <yes/no> | agreement |
| set_rule_subject_has_sensors | Changes the agreement term for whether the Subject gets sensors data from Overlord | set_rule_subject_has_sensors = <yes/no> | agreement |
| convert_to_specialist | Starts the process of converting the subject of the scoped agreement to the given specialist type. | Can also be used to remove the specialization from a subject, by using 'none' as value. convert_to_specialist = <specialist_subject_type> | agreement |
| pass_debris_ownership | Passes the scoped debris ownership to the specified country | pass_debris_ownership = { owner = <target country> } | debris |
| set_council_position | Sets the scoped leader to a council position if it is present in the government of the leader's owner country. | set_council_position = COUNCIL_POS_KEY | leader |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| set_faction_extorted | Sets the scope faction as extorted and removes extortion from any other ones | set_faction_extorted = <yes/no> | pop_faction |
| set_age | Sets the age of the scoped leader | set_age = <int> | leader |
| add_age | Adds the age of the scoped leader | add_age = <int> | leader |
| pop_faction_event | Fires a pop faction event for the scoped pop faction, with optional DAYS and RANDOM delay | pop_faction_event = { id = <id> days = x (optional: specify delay) random = y (optional: specify random delay from 0 to value, which is added on to the 'days' delay) scopes = { from = fromfrom } (optional: specify scope overrides) } | pop_faction |
| add_skill_without_trait_selection | Adds to the scoped leader's skill level but does not select any traits | add_skill_without_trait_selection = 2 | leader |
| expire_site_event | Manually flags an archaeological event as expired | expire_site_event = ancrel.7003 | archaeological_site |
| first_contact_event | Fires a first contact event for the scoped first contact site, with optional DAYS and RANDOM delay | first_contact_event = { id = <id> days = x (optional: specify delay) random = y (optional: specify random delay from 0 to value, which is added on to the 'days' delay) scopes = { from = fromfrom } (optional: specify scope overrides) } | first_contact |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| finish_first_contact | Ends the First Contact | finish_first_contact = yes | first_contact |
| add_stage_modifier | Adds a specific modifier to the target's current stage for a set duration or until stage is changed | add_stage_modifier = { modifier = <key> days = <int>, -1 means it never expires> } | espionage_operation astral_rift |
| remove_stage_modifier | Removes a specific modifier from the target current stage | remove_stage_modifier = <key> | espionage_operation astral_rift |
| leader_event | Fires a leader event for the scoped leader | leader_event = { id = <id> days = x (optional: specify delay) random = y (optional: specify random delay from 0 to value, which is added on to the 'days' delay) scopes = { from = fromfrom } (optional: specify scope overrides) } | leader |
| situation_event | Fires a situation event for the scoped situation | situation_event = { id = <id> days = x (optional: specify delay) random = y (optional: specify random delay from 0 to value, which is added on to the 'days' delay) scopes = { from = fromfrom } (optional: specify scope overrides) } | situation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| agreement_event | Fires an agreement event for the scoped agreement | agreement_event = { id = <id> days = x (optional: specify delay) random = y (optional: specify random delay from 0 to value, which is added on to the 'days' delay) scopes = { from = fromfrom } (optional: specify scope overrides) } | agreement |
| add_spy_network_level | Adds levels to the current Spy Network | add_spy_network_level = <int> | spy_network |
| set_leader_tier | Sets the leader's tier. | set_leader_tier = leader_tier_default | leader |
| random_member | Iterate through each member of the federation - executes the enclosed effects on one of them for which the limit triggers return true. Picks the specific object randomly. | random_member = { limit = { <triggers> } weights = { (optional - adds weights to affect the chance a specific object is selected) base = float modifier = { <add/factor = float> <triggers> } } <effects> } | federation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| ordered_member | Iterate through each member of the federation - executes the enclosed effects on one of them for which the limit triggers return true. Picks the specific object according to the order specified (position 0, order_by = trigger:num_pops would run the effects on the X with the most pops) | ordered_member = { limit = { <triggers> } position = <integer, starting with 0> order_by = <variable>/trigger:<trigger> inverse = yes/no (default: no - if yes, then 0 is lowest rather than highest) <effects> } | federation |
| every_member | Iterate through each member of the federation - executes the enclosed effects on all of them for which the limit triggers return true | every_member = { limit = { <triggers> } <effects> } | federation |
| random_associate | Iterate through each associate member of the federation - executes the enclosed effects on one of them for which the limit triggers return true. Picks the specific object randomly. | random_associate = { limit = { <triggers> } weights = { (optional - adds weights to affect the chance a specific object is selected) base = float modifier = { <add/factor = float> <triggers> } } <effects> } | federation |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| ordered_associate | Iterate through each associate member of the federation - executes the enclosed effects on one of them for which the limit triggers return true. Picks the specific object according to the order specified (position 0, order_by = trigger:num_pops would run the effects on the X with the most pops) | ordered_associate = { limit = { <triggers> } position = <integer, starting with 0> order_by = <variable>/trigger:<trigger> inverse = yes/no (default: no - if yes, then 0 is lowest rather than highest) <effects> } | federation |
| every_associate | Iterate through each associate member of the federation - executes the enclosed effects on all of them for which the limit triggers return true | every_associate = { limit = { <triggers> } <effects> } | federation |
| random_war_participant | Iterate through all war participants - executes the enclosed effects on one of them for which the limit triggers return true. Picks the specific object randomly. | random_war_participant = { limit = { <triggers> } weights = { (optional - adds weights to affect the chance a specific object is selected) base = float modifier = { <add/factor = float> <triggers> } } <effects> } | war |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| ordered_war_participant | Iterate through all war participants - executes the enclosed effects on one of them for which the limit triggers return true. Picks the specific object according to the order specified (position 0, order_by = trigger:num_pops would run the effects on the X with the most pops) | ordered_war_participant = { limit = { <triggers> } position = <integer, starting with 0> order_by = <variable>/trigger:<trigger> inverse = yes/no (default: no - if yes, then 0 is lowest rather than highest) <effects> } | war |
| every_war_participant | Iterate through all war participants - executes the enclosed effects on all of them for which the limit triggers return true | every_war_participant = { limit = { <triggers> } <effects> } | war |
| random_attacker | Iterate through all attackers in the current war - executes the enclosed effects on one of them for which the limit triggers return true. Picks the specific object randomly. | random_attacker = { limit = { <triggers> } weights = { (optional - adds weights to affect the chance a specific object is selected) base = float modifier = { <add/factor = float> <triggers> } } <effects> } | war |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| ordered_attacker | Iterate through all attackers in the current war - executes the enclosed effects on one of them for which the limit triggers return true. Picks the specific object according to the order specified (position 0, order_by = trigger:num_pops would run the effects on the X with the most pops) | ordered_attacker = { limit = { <triggers> } position = <integer, starting with 0> order_by = <variable>/trigger:<trigger> inverse = yes/no (default: no - if yes, then 0 is lowest rather than highest) <effects> } | war |
| every_attacker | Iterate through all attackers in the current war - executes the enclosed effects on all of them for which the limit triggers return true | every_attacker = { limit = { <triggers> } <effects> } | war |
| random_defender | Iterate through all defenders in the current war - executes the enclosed effects on one of them for which the limit triggers return true. Picks the specific object randomly. | random_defender = { limit = { <triggers> } weights = { (optional - adds weights to affect the chance a specific object is selected) base = float modifier = { <add/factor = float> <triggers> } } <effects> } | war |

| Name | Desc | Example | Scopes |
|---|---|---|---|
| ordered_defender | Iterate through all defenders in the current war - executes the enclosed effects on one of them for which the limit triggers return true. Picks the specific object according to the order specified (position 0, order_by = trigger:num_pops would run the effects on the X with the most pops) | ordered_defender = { limit = { <triggers> } position = <integer, starting with 0> order_by = <variable>/trigger:<trigger> inverse = yes/no (default: no - if yes, then 0 is lowest rather than highest) <effects> } | war |
| every_defender | Iterate through all defenders in the current war - executes the enclosed effects on all of them for which the limit triggers return true | every_defender = { limit = { <triggers> } <effects> } | war |

For comparing old lists of Stellaris effects (modifiers and triggers) for most game versions since launch, you can use the GitHub file history feature here (created by OldEnt).

#### Deprecated

| set_primitive | [ DEPRECATED REMOVED in 3.1, USE set_country_type ] Sets the scoped country as primitive. | country |
|---|---|---|
| random_pop | [ DEPRECATED REMOVED in 3.1, USE random_owned_pop ] Executes enclosed effects on a random pop that meets the limit criteria. | planet |
| random/every_(research/mining) _station | [REMOVED in 3.1] Executes enclosed effects on a (random/every) orbital (research/mining) station that meets the limit criteria. | planet country |

## Scripted Effects

There are more than singular Effects can be used for an Effect. See Scripted Effects for details. Here are only a small number of examples:

Modding

| Empire | Empire • Ethics • Governments • Civics • Origins • Mandates • Agendas • Traditions • Ascension perks • Edicts • Policies • Relics • Technologies • Custom empires |
|---|---|

| Pops | Jobs • Factions |
|---|---|

| Leaders | Leaders • Leader traits |
|---|---|

| Species | Species • Species traits |
|---|---|

| Planets | Planets • Planetary feature • Orbital deposit • Buildings • Districts • Planetary decisions |
|---|---|

| Systems | Systems • Starbases • Megastructures • Bypasses • Map |
|---|---|

| Fleets | Fleets • Ships • Components |
|---|---|

| Land warfare | Armies • Bombardment stance |
|---|---|

| Diplomacy | Diplomacy • Federations • Galactic community • Opinion modifiers • Casus Belli • War goals |
|---|---|

| Events | Events • Anomalies • Special projects • Archaeological sites |
|---|---|

| Gameplay | Gameplay • Defines • Resources • Economy • Game start |
|---|---|

| Dynamic modding | Dynamic modding • Effects • Conditions • Scopes • Modifiers • Variables • AI • On actions |
|---|---|

| Media/localisation | Maya exporter • Fonts • Portraits • Flags • Event pictures • Interface • Icons • Music • Localisation |
|---|---|

| Other | Console commands • Save-game editing • Steam Workshop • Modding tutorial |
|---|---|

NewPP limit report Cached time: 20260720110855 Cache expiry: 86400 Reduced expiry: false Complications: [show‐toc] CPU time usage: 0.310 seconds Real time usage: 0.337 seconds Preprocessor visited node count: 181/1000000 Post‐expand include size: 18735/2097152 bytes Template argument size: 8180/2097152 bytes Highest expansion depth: 7/100 Expensive parser function count: 0/100 Unstrip recursion depth: 0/20 Unstrip post‐expand size: 83/5000000 bytes

Transclusion expansion time report (%,ms,calls,template) 100.00% 18.168 1 -total 50.43% 9.163 1 Template:Version 35.53% 6.455 1 Template:ModdingNavbox 26.50% 4.815 1 Template:Infobox 15.19% 2.759 1 Template:Navbox 10.86% 1.974 1 Template:Nowrap 5.33% 0.969 14 Template:Navboxgroup 2.14% 0.388 1 Template:Clear

Saved in parser cache with key wiki_stellaris-mwstella_:pcache:idhash:1766-0!canonical and timestamp 20260720110854 and revision id 115924.

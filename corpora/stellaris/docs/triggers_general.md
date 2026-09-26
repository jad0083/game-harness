# Conditions — general and control flow (all scopes)
Source: https://stellaris.paradoxwikis.com/Conditions
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260716201409 (the live wiki blocks non-browser clients). Page version banner: Version Please help with verifying or updating older sections of this article. At least some were last verified for version 4.3. This article is for the PC version of Stellaris only._

## Logical boolean operators

Operators allow conditions and triggers to be manipulated in order to return a simple true or false statement to be processed.

They appear:

- In condition blocks (trigger section of events, or equivalent: mult_modifier, can_use_…, potential, allow, …).
- In the limit clause of command blocks.
- In scripted blocks: as scripted triggers (or scripted effects), which can be used to group conditions into re-usable macro.
- At the root of events for pre-triggers used to improve performances (actually only on planets).

| Name | Description | Example |
|---|---|---|
| if… else_if… else… | Returns true if the conditional statement inside the block evaluates to true. | if = { limit = { owner = { has_ethic = ethic_fanatic_xenophile } } … } else_if = { limit = { … } … } else = { … } |
| AND | Returns true if all conditional statements inside the block evaluate to true. This is usually the default in a trigger or new scope, so is not needed to be explicitly specified. i.e. trigger = { AND = { A B } } is the same as trigger = { A B } Putting the conditions most likely to be false first can slightly help performance of the scripting engine. | AND = { has_ethic = ethic_fanatic_xenophile has_ethic = ethic_egalitarian } |
| OR | Returns true if at least one conditional statement inside the block evaluates to true. Putting the conditions most likely to be true first can slightly help performance of the scripting engine. | OR = { has_ethic = ethic_fanatic_xenophile has_ethic = ethic_egalitarian } |

| Name | Description | Example |
|---|---|---|
| NOT | Returns true if the conditional statement inside the block evaluates to false, and false if it evaluates to true. Note that NOT only accepts one statement. If you use more than one, it will usually work, but can cause unforeseen bugs, as well as put an error in the error.log file. It's better to use NOR or NAND for blocks containing more than one statement. | NOT = { has_ethic = ethic_fanatic_xenophile } |
| NOR | Returns true if none of the conditional statements inside the block evaluate to true. Same as NOT = { OR = { <conditions> } } (all are false). | NOR = { has_ethic = ethic_fanatic_xenophile has_ethic = ethic_fanatic_militarist } |
| NAND | Returns true unless all of the conditional statements inside the block evaluate to true. Same as NOT = { AND = { <conditions> } } (at minimum one is false). | NAND = { has_ethic = ethic_fanatic_xenophile has_technology = "tech_zero_point_power" } |
| calc_true_if | Returns true if at least amount conditions return true. amount supports numerical operators. | calc_true_if = { amount >= 3 leader_class = scientist is_researching_area = society gender = female has_level > 2 leader_age < 85 } |

It is important to remember De Morgan's laws to use NOR and NAND correctly:

```
 NAND =	{ A B } <=> NOT = { AND = { A B } } <=> OR  = { NOT = { A } NOT = { B } }
 NOR  =	{ A B } <=> NOT = { OR  = { A B } } <=> AND = { NOT = { A } NOT = { B } }
```

So this means a list of NOTs in an AND can be simplified:

```
 trigger = {
 	NOT = { A }
 	NOT = { B }
 	NOT = { C }
 }
```

Is the same as:

```
 trigger = {
 	NOR = { A B C }
 }
```

Conversely, a list of NOTs in an OR can be simplified:

```
 trigger = {
 	OR = {
 		NOT = { A }
 		NOT = { B }
 		NOT = { C }
 	}
 }
```

Is the same as:

```
 trigger = {
 	NAND = { A B C }
 }
```

If you need XOR logic, you can use calc_true_if or something like this:

```
 trigger = {
 	OR = { A B }
 	NAND = { A B }
 }
```

Is the same as:

```
 trigger = {
 	calc_true_if = { amount = 1 A B	}
 }
```

Or this for 3 input XOR logic:

```
 trigger = {
 	OR = {
 		AND = {
 			OR = { A B C }
 			NOR = {
 				AND = { A B }
 				AND = { A C }
 				AND = { B C }
 			}
 		}
 		AND = { A B C }
 	}
 }
```

Is the same as:

```
 trigger = {
 	OR = {
 		AND = { A B C }
 		calc_true_if = { amount = 1 A B C }
 	}
 }
```

## Scopes

Main article: Scopes

Scopes specify the target of the trigger or condition in question. They allow for variables to be checked on other objects that the trigger script is not attached to. Currently, Stellaris recognises a set of keywords as valid scopes. The most commonly used are outlined in the table below. An empire or nation scope is referred to as country scope.

| Name | Description |
|---|---|
| capital_scope | If the script this belongs to is attached to a country, capital_scope will return the capital planet of the country. |
| controller | Returns the country which may be not owner, but currently controls this object (i.e. in case of occupation) |
| owner | Returns the country that owns the object that the script belongs to. |
| space_owner | Returns the country that owns the system the script object is currently in. Should be used in place of owner for non-inhabited planets. |
| leader | Returns the leader assigned to the current country, planet, science ship, military fleet or army (can be used in several other places, see scope documentation) |
| species | Returns the species associated with the current country, leader, pop group, army or colony ship. |
| planet | Returns the planet of the current object. |
| this | Returns the current scope object in the cycle (i.e., for example, each instance in any_owned_sector) |
| root | Returns the object that the script belongs to. If called on a planet-level script, then this returns the planet. |
| from | Returns the location of the object that the script belongs to. If this is attached to a ship-level script, then this returns the ship's current planet. |
| fromfrom | Returns the location of the object that the script belongs to, twice removed. |

| Name | Description |
|---|---|
| prev | Returns the object from previous scope |
| prevprev | Returns the object from the scope before the previous scope |
| prevprevprev | Returns the object from the third previous scope (i.e. the previous scope before the prevprev scope) |
| prevprevprevprev | Returns the object from the fourth previous scope in the pattern of prev, prevprev and prevprevprev |

## Trigger list

The vanilla game has many scripted triggers defined you can use, though they don't show here, as this list is only the triggers built-in to the engine. In addition, you can write your own scripted triggers. Scripted Triggers are stored in the./common/scripted_triggers/ directory. Current built-in triggers can be also found in the triggers.log file in your local data folder's script_documentation.

Rows whose first listed scope is: all, no_scope.

| Name | Desc | Example | Scopes |
|---|---|---|---|
| text | For 'desc={trigger={' use. Shows custom text | text = <text> | all |
| not | An inverted trigger |  | all |
| custom_tooltip | Replaces the tooltips for the enclosed triggers with a custom text | custom_tooltip = { text = <text used as fallback for both fails and successes> fail_text = <text used for fails["string"/default/none]> success_text = <text used for successes["string"/default/none]> <triggers> } | all |
| if | Evaluates the triggers if the display_triggers of the limit are met | if = { limit = { <display_triggers> } <triggers> } | all |
| switch | Switch case for a trigger | switch = { trigger = pop_has_ethic ethic_xenophile = { <trigger> } ethic_xenophobe = { <trigger> } default = { <trigger> } } | all |
| closest_system | Finds the closest system within the given hyperlane steps and limit = { <triggers> }. If this system does not exist, it returns false. If it does exist, it is checked against the triggers outside of the limit = {}. | closest_system = { limit = { <triggers> } min_steps = 2 max_steps = 20 use_bypasses = yes/no (default: no) <triggers> } | all |

| else_if | Evaluates the enclosed triggers if the display_triggers of the preceding `if` or `else_if` is not met and its own display_trigger of the limit is met | if = { limit = { <display_triggers> } <triggers> } else_if = { limit = { <display_triggers> } <triggers> } | all |
| exists | Checks if a target scope exists | exists = <target> | all |
| is_same_value | Checks if the current scope and the target scope are the same thing | is_same_value = <target> | all |
| additional_crisis_strength | Checks the degree to which multiply_crisis_strength effect is increasing the strength of endgame crises | additional_crisis_strength > 1.4 | all |
| is_scope_type | Checks currently in the specified scope: | is_scope_type = fleet valid tokens are: none, megastructure, planet, country, ship, pop, fleet, galactic_object, leader, army, ambient_object, species, design,pop_faction, war, alliance, starbase,deposit,observer, sector, astral_rift. | all |
| has_galactic_custodian | Checks if the Galactic Community has named a Custodian | has_galactic_custodian = yes/no | all |
| has_galactic_emperor | Checks if the Galactic Emperor has taken over | has_galactic_emperor = yes/no | all |
| imperial_authority | Checks imperial authority. | imperial_authority >=< 40 | all |

| galactic_defense_force_exists | Checks if the Galactic Defense Force or Imperial Armada exists | galactic_defense_force_exists = yes/no | all |
| and | all inside trigger must be true |  | all |
| or | At least one entry inside the trigger must be true |  | all |
| voidworms_scaling | Checks Voidworms presence scaling in game setup |  | all |
| cutholoids_scaling | Checks Cutholoids presence scaling in game setup |  | all |
| hidden_trigger | Hides the tooltip for the triggers within | hidden_trigger = { <triggers> } | all |
| always | Sets trigger to be either always true or false | always = yes | all |
| days_passed | Checks the number of in-game days passed since the 2200.1.1 start | days_passed < 15 | all |
| num_guaranteed_colonies | Checks the number of guaranteed colonies defined in setup | num_guaranteed_colonies > 1 | all |
| has_any_flag | Checks if any Flag has been set to the given scope | has_any_flag = yes/no | all |
| has_global_flag | Checks if a Global Flag has been set | has_global_flag = <flag> (note: one can use e.g. my_flag@from to track relationships between objects) | all |

| check_galaxy_setup_value | Checks the value for a specific option from the galaxy setup | check_galaxy_setup_value = { setting = <string> value >=< <float>/<variable> } possible values: num_empires, num_advanced_empires, num_fallen_empires, num_marauder_empires, mid_game_year, end_game_year, victory_year, num_guaranteed_colonies, num_gateways, num_wormhole_pairs, num_hyperlanes, habitable_worlds_scale, primitive_worlds_scale, crisis_strength_scale, tech_costs_scale | all |
| is_multiplayer | Checks if the game is running in multiplayer | is_multiplayer = yes | all |
| num_fallen_empires_setting | Checks the number of fallen empires defined in setup | num_fallen_empires_setting > 1 | all |
| is_scope_valid | Checks if the current scope is valid | is_scope_valid = yes | all |
| is_ironman | Check if current game is running in ironman mode | is_ironman = yes | all |
| else | Evaluates the triggers if the display_triggers of preceding 'if' or 'else_if' is not met | if = { limit = { <display_triggers> } <triggers> } else = { <triggers> } | all |
| custom_tooltip_fail | Shows custom text only when the associated trigger fails | custom_tooltip_fail = { text = <text> <triggers> } | all |
| custom_progress | Adjusts progress of triggers inside it | custom_progress = {... current_val_coeff = 0.5 final_val_coeff = 0.5 mode = <normal/simplified/clamped> } | all |

| hidden_progress | Nullifies progress of triggers inside it and returns progress '0 of 0' | hidden_progress = { <triggers> } | all |
| simple_progress | Hides the progress of the triggers inside and returns progresses '0 of 1' or '1 of 1' | simple_progress = { <triggers> } | all |
| years_passed | Checks the number of in-game years passed since the 2200 start | years_passed < 150 | all |
| mid_game_years_passed | Checks the number of in-game years passed since the mid-game start date | mid_game_years_passed >= 50 | all |
| end_game_years_passed | Checks the number of in-game years passed since the end-game start date | end_game_years_passed >= 50 | all |
| logged_in_to_pdx_account | Checks if the local human is logged in to a Pdx account. This WILL cause an out of sync if used for anything that can change the game state |  | all |
| count_potential_war_participants | Checks the amount of potential war participants in a specific war that meet the specified criteria | count_potential_war_participants = { attacker = <target> defender = <target> side = <target> limit = { <triggers> } count > 2/variable | all |
| num_marauder_empires_to_spawn | Checks the number of marauder empires specified by the galaxy setup | num_marauder_empires_to_spawn > 1 | all |
| host_has_dlc | Checks if the host has a specific DLC enabled |  | all |

| local_has_dlc | Checks if the local player has a specific DLC enabled |  | all |
| nor | An inverted OR trigger |  | all |
| nand | An inverted AND trigger |  | all |
| has_war_goal | Checks if a war goal is set. Only works in diplomatic phrases. | has_war_goal = yes | all |
| custom_tooltip_success | Shows custom text only when the associated trigger passes | custom_tooltip_success = { text = <text> <triggers> } | all |
| success_text | For 'desc={trigger={' use. Shows custom text when the associated trigger passes. | success_text = { text = <text> <triggers> } | all |
| fail_text | For 'desc={trigger={' use. Shows custom text when the associated trigger fails. | fail_text = { text = <text> <triggers> } | all |
| calc_true_if | Returns true if the specified number of sub-triggers return true | calc_true_if = { amount = 2/variable <trigger> <trigger> <trigger> } | all |
| log | Prints a message to game.log for debugging purposes | log = <string> | all |
| is_difficulty | Checks the game's difficulty level (0 to 6, with 0 as Civilian and 6 as Grand Admiral) | is_difficulty = 2 | all |
| distance_to_core_percent | Checks the ship/fleet/planet/leader/pop/system's distance to the galactic core in percent, where center = 0 and galactic rim = 100 | distance_to_core_percent < 60 | all |
| is_crises_allowed | Check if current game allows crises | is_crises_allowed = yes | all |

| allowed_crisis_type | Checks which crisis is allowed to spawn in the current game | allowed_crisis_type = prethoryn/unbidden/contingency/synth_queen/all | all |
| is_job_of_pop_category | Checks if a job is of a certain pop category. Note that the result for this trigger is not dependent on where it is used - so it's for use in e.g. templated script values. | is_job_of_pop_category = { job = <job> category = <category> } | all |
| debug_break | Trigger an assertion to stop the debugger when encountering this trigger; returns the value it is assigned | debug_break = yes | all |
| conditional_tooltip | The enclosed trigger will be completely ignored if the condition in "trigger" isn't true. Useful to hide part of tooltips that are not relevant. |  | all |
| num_active_gateways | Checks the number of active gateways in the galaxy | num_active_gateways < 3 | all |
| inverted_switch | Switch case for a trigger treated as NOT. | inverted_switch = { trigger = pop_has_ethic ethic_xenophile = { <trigger> } ethic_xenophobe = { <trigger> } default = { <trigger> } } | all |
| is_on_market | Checks if resource is enabled on the Galactic Market | is_on_market = <resource_name> | all |
| caravaneers_enabled | Checks if Caravaneers are enabled in game setup |  | all |
| lgate_enabled | Checks if L-Gates are enabled in game setup |  | all |

| is_voting_on_resolution | Checks if the Galactic Community is currently voting on any, or a specific, resolution | is_voting_on_resolution = <resolution/any> | all |
| last_resolution_changed | Checks if the last resolution the Galactic Community voted on or otherwise passed or failed is as specified. | last_resolution_changed = <resolution> | all |
| last_resolution_category_changed | Checks if the last resolution the Galactic Community voted on or otherwise passed or failed is part of the specified category. | last_resolution_category_changed = <resolution_category> | all |
| is_years_since_community_formation | Compare with number of years since the formation of the Galactic Community. NOTE: A negative value means it hasn't been formed yet! | is_years_since_community_formationn >= <int32> | all |
| is_years_since_council_establishment | Compares with number of years since the establishment of the Galactic Council. NOTE: A negative value means it hasn't been established yet! | is_years_since_council_establishment >= <int32> | all |
| is_galactic_community_formed | Checks if the Galactic Community has been formed | is_galactic_community_formed = yes/no | all |
| is_galactic_council_established | Checks if the Galactic Council has been established | is_galactic_council_established = yes/no | all |

| is_active_resolution | Checks if the provided Resolution is active in the Community | is_active_resolution = <resolution_type_key> | all |
| num_council_positions | Compares the number of council positions in the Galactic Community. | num_council_positions >= <int32> | all |
| num_ai_empires_setting | Checks the number of AI empires defined in setup | num_ai_empires_setting >= 1 | all |
| galaxy_size | Checks whether the galaxy size if of a certain type | galaxy_size=medium | all |
| galaxy_shape | Checks whether the galaxy shape if of a certain shape | galaxy_shape = spiral_2 | all |
| num_galaxy_systems | Checks number of star systems in the galaxy | num_galaxy_systems > 400 | all |
| num_cosmic_storms | Checks the amount of currently active cosmic storms. |  | all |
| num_cosmic_storm_early_game_spawn_chance_scale_setting | Checks the spawn storm chance scale in early game for cosmic storms |  | all |
| num_cosmic_storm_mid_game_spawn_chance_scale_setting | Checks the spawn storm chance scale in mid game for cosmic storms |  | all |
| num_cosmic_storm_late_game_spawn_chance_scale_setting | Checks the spawn storm chance scale in late game for cosmic storms |  | all |
| num_cosmic_storm_early_game_spawn_max_cap_setting | Checks the spawn storm max cap in early game for cosmic storms |  | all |

| num_cosmic_storm_mid_game_spawn_max_cap_setting | Checks the spawn storm max cap in mid game for cosmic storms |  | all |
| num_cosmic_storm_late_game_spawn_max_cap_setting | Checks the spawn storm max cap in late game for cosmic storms |  | all |
| num_cosmic_storm_spawn_cooldown_scale_setting | Checks the spawn storm cooldown scale for cosmic storms |  | all |
| num_neighbor_systems | Checks the number of neighbor systems within a specific distance | num_neighbor_systems = { max_distance = 1 limit = <triggers> } | all |
| count_end_cycle_systems | Checks the amount of needed systems with the End Cycle psionic aura | count_end_cycle_systems > 50 Only works if one country is currently the crisis. | all |
| any_ambient_object | Iterate through every ambient object in the game - checks whether the enclosed triggers return true for any of them | any_ambient_object = { <triggers> } | all |
| count_ambient_object | Iterate through every ambient object in the game - checks whether the enclosed triggers return true for X/all of them | count_ambient_object = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_archaeological_site | Iterate through every archaeological sites - checks whether the enclosed triggers return true for any of them | any_archaeological_site = { <triggers> } | all |

| count_archaeological_site | Iterate through every archaeological sites - checks whether the enclosed triggers return true for X/all of them | count_archaeological_site = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_astral_rift | Iterate through every astral rift - checks whether the enclosed triggers return true for any of them | any_astral_rift = { <triggers> } | all |
| count_astral_rift | Iterate through every astral rift - checks whether the enclosed triggers return true for X/all of them | count_astral_rift = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_bypass | Iterate through every bypass - checks whether the enclosed triggers return true for any of them | any_bypass = { <triggers> } | all |
| count_bypass | Iterate through every bypass - checks whether the enclosed triggers return true for X/all of them | count_bypass = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_cosmic_storm | Iterate through all cosmic storms in the galaxy - checks whether the enclosed triggers return true for any of them | any_cosmic_storm = { <triggers> } | all |
| count_cosmic_storm | Iterate through all cosmic storms in the galaxy - checks whether the enclosed triggers return true for X/all of them | count_cosmic_storm = { count = <num/all/variable> limit = { <triggers> } } | all |

| any_cosmic_storm_start_position | Iterate through all systems valid to be a storms start position - checks whether the enclosed triggers return true for any of them | any_cosmic_storm_start_position = { <triggers> } | all |
| count_cosmic_storm_start_position | Iterate through all systems valid to be a storms start position - checks whether the enclosed triggers return true for X/all of them | count_cosmic_storm_start_position = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_cosmic_storm_end_position | Iterate through all systems valid to be a storms end position - checks whether the enclosed triggers return true for any of them | any_cosmic_storm_end_position = { <triggers> } | all |
| count_cosmic_storm_end_position | Iterate through all systems valid to be a storms end position - checks whether the enclosed triggers return true for X/all of them | count_cosmic_storm_end_position = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_country | Iterate through all countries - checks whether the enclosed triggers return true for any of them | any_country = { <triggers> } | all |
| count_country | Iterate through all countries - checks whether the enclosed triggers return true for X/all of them | count_country = { count = <num/all/variable> limit = { <triggers> } } | all |

| any_playable_country | Iterate through all playable countries - checks whether the enclosed triggers return true for any of them | any_playable_country = { <triggers> } | all |
| count_playable_country | Iterate through all playable countries - checks whether the enclosed triggers return true for X/all of them | count_playable_country = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_espionage_asset | Iterate through each espionage asset - checks whether the enclosed triggers return true for any of them | any_espionage_asset = { <triggers> } | no_scope spy_network espionage_operation |
| count_espionage_asset | Iterate through each espionage asset - checks whether the enclosed triggers return true for X/all of them | count_espionage_asset = { count = <num/all/variable> limit = { <triggers> } } | no_scope spy_network espionage_operation |
| any_federation | Iterate through each federation - checks whether the enclosed triggers return true for any of them | any_federation = { <triggers> } | all |
| count_federation | Iterate through each federation - checks whether the enclosed triggers return true for X/all of them | count_federation = { count = <num/all/variable> limit = { <triggers> } } | all |

| any_galaxy_fleet | Iterate through each fleet in the entire game - checks whether the enclosed triggers return true for any of them | any_galaxy_fleet = { <triggers> } | all |
| count_galaxy_fleet | Iterate through each fleet in the entire game - checks whether the enclosed triggers return true for X/all of them | count_galaxy_fleet = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_galcom_member | Iterate through each member of the galactic community - checks whether the enclosed triggers return true for any of them | any_galcom_member = { <triggers> } | all |
| count_galcom_member | Iterate through each member of the galactic community - checks whether the enclosed triggers return true for X/all of them | count_galcom_member = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_council_member | Iterate through each member of the galactic council - checks whether the enclosed triggers return true for any of them | any_council_member = { <triggers> } | all |
| count_council_member | Iterate through each member of the galactic council - checks whether the enclosed triggers return true for X/all of them | count_council_member = { count = <num/all/variable> limit = { <triggers> } } | all |

| any_megastructure | Iterate through each megastructure - checks whether the enclosed triggers return true for any of them | any_megastructure = { <triggers> } | all |
| count_megastructure | Iterate through each megastructure - checks whether the enclosed triggers return true for X/all of them | count_megastructure = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_system_megastructure | Iterate through each megastructure in system - checks whether the enclosed triggers return true for any of them | any_system_megastructure = { <triggers> } | all |
| count_system_megastructure | Iterate through each megastructure in system - checks whether the enclosed triggers return true for X/all of them | count_system_megastructure = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_galaxy_planet | Iterate through each planet ANYWHERE in the game; warning: resource intensive! - checks whether the enclosed triggers return true for any of them | any_galaxy_planet = { <triggers> } | all |
| count_galaxy_planet | Iterate through each planet ANYWHERE in the game; warning: resource intensive! - checks whether the enclosed triggers return true for X/all of them | count_galaxy_planet = { count = <num/all/variable> limit = { <triggers> } } | all |

| any_galaxy_sector | Iterate through all sectors in the game - checks whether the enclosed triggers return true for any of them | any_galaxy_sector = { <triggers> } | all |
| count_galaxy_sector | Iterate through all sectors in the game - checks whether the enclosed triggers return true for X/all of them | count_galaxy_sector = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_galaxy_species | Check if any species in the galaxy meet the specified criteria - checks whether the enclosed triggers return true for any of them | any_galaxy_species = { <triggers> } | all |
| count_galaxy_species | Check if any species in the galaxy meet the specified criteria - checks whether the enclosed triggers return true for X/all of them | count_galaxy_species = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_existing_species_traits | Iterate through all existing species traits in the game - checks whether the enclosed triggers return true for any of them | any_existing_species_traits = { <triggers> } | no_scope |
| count_existing_species_traits | Iterate through all existing species traits in the game - checks whether the enclosed triggers return true for X/all of them | count_existing_species_traits = { count = <num/all/variable> limit = { <triggers> } } | no_scope |

| any_system | Iterate through all systems - checks whether the enclosed triggers return true for any of them | any_system = { <triggers> } | all |
| count_system | Iterate through all systems - checks whether the enclosed triggers return true for X/all of them | count_system = { count = <num/all/variable> limit = { <triggers> } } | all |
| any_rim_system | Iterate through all rim systems - checks whether the enclosed triggers return true for any of them | any_rim_system = { <triggers> } | all |
| count_rim_system | Iterate through all rim systems - checks whether the enclosed triggers return true for X/all of them | count_rim_system = { count = <num/all/variable> limit = { <triggers> } } | all |

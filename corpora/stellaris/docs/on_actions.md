# On actions
Source: https://stellaris.paradoxwikis.com/On_actions
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260714121040 (the live wiki blocks non-browser clients). Page version banner: Version Please help with verifying or updating older sections of this article. At least some were last verified for version 3.7. This article is for the PC version of Stellaris only._

## Introduction

Aside from the default polling another very common way to get an event triggered is on_action. The vanilla game itself has a number of events registered this way in Stellaris\common\on_actions\00_on_actions.txt

The situations of triggering range from polling less aggressive (monthly or yearly) to numerous developments of the galaxy like ending of a planetary invasion, survey, entering of a system and so forth. This is later part is comparable to registering an Event in a GUI Environment of many higher programming languages.

Registered events should be marked with "triggered only" modifier. As easily dozens of events can be registered to any one development (often belonging to the same chain) the triggers decide which events are actually called.

## Custom On Actions

Since 3.0 you can define your own "on_actions" in script by effect fire_on_action = { on_action = <string> scopes = { from = X fromfrom = Y } }. Do note that when defining scopes, fire_on_action appears to be considered a scope and all non-event_target scopes require a prev added before them (from = prev will scope to the scope firing the on_action, and to scope to the previous scope from = prevprev must be used instead). In addition, non-global event_targets will not be available in the fired events if the from scope is overwritten.

### Performance

For planet, system, starbase, leader and pop events, it's recommended to use pre_triggers (fast triggers that are checked before normal ones) to improve performance.

## Order of Events

When multiple events are registered to the same action, they will be fired in the order listed. If they are registered in multiple files, they are fired in ASCII-betical order. So, if you have a file aaa_on_actions.txt with on_game_start = { events = { event.1 event.2 } } and a file bbb_on_actions.txt with on_game_start = { event = { event.3 event.4 } }, then those events will be fired in the order event.1, event.2, event.3, event.4. The ID of the event has no effect.

## Firing Behavior

Every time an On Action gets fired, it will:

- Go through every single event in its events = {} block, exclude the ones that trigger false, and fire all the other events.
- Go through every single event in its random_events = {} block, exclude the ones that trigger false, roll weights, and fire one random valid event.
  - Unlike random_list = {}, random_events = {} don't support weight modifiers, but you can add a weight_multiplier = {} block to the event itself.

## List of Vanilla On Actions

| Name | Desc | Community Notes |
|---|---|---|
| on_game_start | Triggers when the game starts |  |
| on_game_start_country |  |  |
| on_single_player_save_game_load | No scope, like on_game_start Does not run when loading MP saves due to OOS concerns | Border related triggers/effects do not work. |
| on_monthly_pulse | No scope, like on_game_start |  |
| on_monthly_pulse_pre_ftl_observation | Via pre_ftl_tech_progress_situation / preftl.50 See also: on_monthly_pulse_pre_ftl_observation_broken_shackles (below) |  |
| on_monthly_pulse_pre_ftl_observation_broken_shackles | The following are considered valid for "Broken Shackles" empires observing their original civilizations; see also on_monthly_pulse_pre_ftl_observation (above) Via pre_ftl_tech_progress_situation / preftl.50 |  |
| on_yearly_pulse | No scope, like on_game_start |  |
| on_bi_yearly_pulse | No scope, like on_game_start |  |
| on_five_year_pulse | No scope, like on_game_start |  |
| on_decade_pulse | No scope, like on_game_start |  |
| on_mid_game_pulse | No scope, like on_game_start |  |
| on_late_game_pulse | No scope, like on_game_start |  |
| on_monthly_pulse_country | this = country | Only country_types with has_pulse_events = yes will get these events. Notably, Fallen/Awakened Empires will not get these events. |

| Name | Desc | Community Notes |
|---|---|---|
| on_yearly_pulse_country | this = country | Only country_types with has_pulse_events = yes will get these events. Notably, Fallen/Awakened Empires will not get these events. |
| on_bi_yearly_pulse_country | this = country | Only country_types with has_pulse_events = yes will get these events. Notably, Fallen/Awakened Empires will not get these events. |
| on_five_year_pulse_country | this = country | Only country_types with has_pulse_events = yes will get these events. Notably, Fallen/Awakened Empires will not get these events. |
| on_five_year_random_pulse_country | this = country, fired via action.220 from on_five_year_pulse_country |  |
| on_five_year_random_pulse_overlord | this = country, fired via action.420 |  |
| on_five_year_random_pulse_pre_ftl | this = country, fired via action.620 |  |
| on_five_year_random_pulse_pre_ftl_tech_events | this = country, fired via action.630 |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_five_year_random_pulse_country_negative_list | Why do this, you might ask, and not just use a random_list? Because on_actions check the triggers of the event before they try to fire them and exclude them from the list if they are false, so a list with no 0 weight will always fire an event so long as any of them are able to be fired Used in operation_diplomatic_incident. Beware when changing. this = country, fired via action.2211 from on_five_year_random_pulse_country |  |
| on_decade_pulse_country | this = country | Only country_types with has_pulse_events = yes will get these events. Notably, Fallen/Awakened Empires will not get these events. |
| on_mid_game_pulse_country | this = country | Only country_types with has_pulse_events = yes will get these events. Notably, Fallen/Awakened Empires will not get these events. |
| on_decade_random_pulse_country_payback_broken_shackles |  |  |
| on_late_game_pulse_country | this = country | Only country_types with has_pulse_events = yes will get these events. Notably, Fallen/Awakened Empires will not get these events. |
| on_initialize_advanced_colony | setup advanced colony. So far it has a pop on the capital and a colony shelter building matching the is_colony trigger scope: planet from: country |  |
| on_become_advanced_empire |  |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_press_begin | Triggers when pressing begin in the intro window This = country to press begin |  |
| on_custom_diplomacy | Triggers when trying to open the diplomacy view for countries with custom diplomacy. Country scope This = target country (player) From = source country |  |
| on_first_contact | Triggered when two empires discover each other This = Empire 1 From = Empire 2 Fromfromfrom = System where contact occurred |  |
| on_first_contact_finished | Triggered when a first contact process is finished This = first contact scope From = other country |  |
| on_enforce_borders | Triggered when an Empire has fleets within another Empire’s borders. This = receiver From = sender FromFrom = fleet FromFromFrom = system |  |
| on_ground_combat_started | Triggers when ground combat starts This = planet From = country attacking |  |
| on_planet_attackers_win | Triggers country_event for the attacker upon victory (Before controller is switched) This = country, leader attacker From = country, planet owner FromFrom = planet IDENTITIES: attacker is the side that "IsHostile" to the planet controller; e.g. spawned monster armies are attackers, but if they win and the player attempts to retake the planet, the player is the attacker |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_planet_attackers_lose | Triggers country_event for the attacker upon defeat This = country, attack leader From = country, planet owner FromFrom = planet |  |
| on_planet_defenders_win | Triggers country_event for the defender upon victory Root = country, planet owner From = country, attack leader FromFrom = planet |  |
| on_planet_defenders_lose | Triggers country_event for the defender upon defeat This = country, planet owner From = country, attack leader FromFrom = planet |  |
| on_system_first_visited | Fires when you first get intel (_low and up) on a new system Scope = Country From = System |  |
| on_entering_system_first_time | Triggers event when each country first sends a ship into the system (once per country) Scope = Ship From = System FromFrom = Country |  |
| on_entering_system | Triggers event when ship enters a system. It’s usually better to use on_entering_system_first_time or on_entering_system_fleet Scope = Ship From = System FromFrom = Country |  |
| on_entering_system_fleet | See also: on_fleet_auto_move_arrival Scope = Fleet From = System |  |
| on_crossing_border | A fleet executes a move order to exit borders Scope = Fleet From = Origin System FromFrom = Destination System |  |
| on_survey | A ship has surveyed a planet. Scope = Ship From = Planet |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_planet_surveyed | A country has gained a surveyed status on a planet. Happens after "on_survey" if a science ship surveyed a planet. (Can also happen without a ship through changes in intel levels) Root = Planet From = Country FromFrom = Fleet of the science ship that surveyed it, if any |  |
| on_system_survey | A country has gained a surveyed status on a planet. Happens after "on_survey" if a science ship surveyed a planet. Root = Country From = system FromFrom = Fleet of the science ship that surveyed it, if any |  |
| on_system_survey_ship | A ship is done surveying the last unsurveyed planet in a system Scope = ship From = system |  |
| on_colonization_started | A planet has begun the colonization process. Scope = Planet |  |
| on_colonized | A planet has been colonized. Scope = Planet |  |
| on_colony_destroyed | A colony has been destroyed. Called just before owner and controller is cleared Scope = Planet |  |
| on_entering_battle | This = owner of fleet 1 From = owner of fleet 2 FromFrom = fleet 1 FromFromFrom = fleet 2 |  |
| on_ship_destroyed_victim | This = owner of ship 1 (destroyed) From = owner of ship 2 (combatant) FromFrom = ship 1 FromFromFrom = ship 2 |  |
| on_ship_destroyed_perp | This = owner of ship 1 (combatant) From = owner of ship 2 (destroyed) FromFrom = ship 1 FromFromFrom = ship 2 |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_starbase_destroyed | This = starbase being destroyed (not ship!) From = fleet that destroyed the starbase |  |
| on_starbase_disabled | This = starbase being disabled (not ship!) From = fleet that disabled the starbase |  |
| on_ship_disengaged_victim | This = owner of ship 1 (destroyed) From = owner of ship 2 (combatant) FromFrom = ship 1 FromFromFrom = ship 2 |  |
| on_ship_disengaged_perp | This = owner of ship 1 (combatant) From = owner of ship 2 (destroyed) FromFrom = ship 1 FromFromFrom = ship 2 |  |
| on_fleet_destroyed_victim | This = owner of fleet 1 (destroyed) From = owner of fleet 2 (combatant) FromFrom = fleet 1 FromFromFrom = fleet 2 |  |
| on_fleet_destroyed_perp | This = owner of fleet 1 (combatant) From = owner of fleet 2 (destroyed) FromFrom = fleet 1 FromFromFrom = fleet 2 |  |
| on_space_battle_won | This = owner of fleet 1 (winner) From = owner of fleet 2 (loser) FromFrom = fleet 1 FromFromFrom = fleet 2 |  |
| on_space_battle_lost | This = owner of fleet 1 (loser) From = owner of fleet 2 (winner) FromFrom = fleet 1 FromFromFrom = fleet 2 |  |
| on_fleet_disbanded | This = owner of fleet From = disbanded fleet |  |
| on_fleet_auto_move_arrival | This = owner of fleet From = fleet FromFrom = planet (if any) |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_fleet_contract_started | This = fleet From = country that borrowed the fleet FromFrom = country that owns the fleet Is fired immediately after fleet is leased out |  |
| on_fleet_contract_expired | This = fleet From = country that borrowed the fleet FromFrom = country that owns the fleet FromFromFrom = country that initiated the ending (the same as owner in a case of expiration) Is fired immediately after fleet contract is expired |  |
| on_fleet_contract_cancelled | This = fleet From = country that borrowed the fleet FromFrom = country that owns the fleet FromFromFrom = country that initiated the ending (trade deal actor when the contract cancellation is a part of trade deal) Is fired immediately after fleet contract is cancelled (when controller prematurely finishes the contract or when the contract cancellation is a part of trade deal) |  |
| on_fleet_contract_broken | This = fleet From = country that borrowed the fleet FromFrom = country that owns the fleet FromFromFrom = country that initiated the ending (main attacker in a case of war) Is fired immediately after fleet contract is broken (when country is attacked by someone of when a war is started) |  |
| on_building_mining_station | This = construction ship From = planet it is built on Fires when construction is complete, immediately before station is created |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_building_research_station | This = construction ship From = planet it is built on Fires when construction is complete, immediately before station is created |  |
| on_building_outpost_station | This = construction ship From = planet it is built on Fires when construction is complete, immediately before station is created |  |
| on_building_wormhole_station | This = construction ship Fires when construction is complete, immediately before station is created |  |
| on_building_starbase_outpost | This = ship (starbase) From = owner country |  |
| on_building_starbase_fe_outpost |  |  |
| on_building_observation_station | This = construction ship From = planet it is built on |  |
| on_building_starbase_ai |  |  |
| on_building_starbase_exd_0 |  |  |
| on_building_starbase_exd |  |  |
| on_building_starbase_swarm |  |  |
| on_building_starbase_marauder |  |  |
| on_destroying_station | This = station From = planet it was built on |  |
| on_losing_station_control | This = station From = planet it was built on |  |
| on_gaining_station_control | This = station From = planet it was built on |  |
| on_entering_war | This = country From = opponent war leader |  |
| on_fleet_detected | This = Country From = Fleet |  |
| on_ship_disabled | This = Ship From = Disabler Ship |  |
| on_ship_enabled | This = Ship |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_uplift_completion | Triggers when a Special Project to uplift a pre-sapient species is completed. Note that this will trigger once for each combination of planet & original species (but for uplifting this should be only once). Scope = planet_event This = planet scope From = uplifted species (pre-modification) |  |
| on_terraforming_begun | Planets starts being terraformed This = Planet From = Terraforming country |  |
| on_terraforming_complete | Planet has been terraformed This = Planet From = Terraforming country |  |
| on_planet_class_changed | Planet has changed planet class in whatever way. Note that this is also called during galaxy creation in some places. This = Planet |  |
| on_planet_bombarded | Planet has taken damage from orbital bombardment – Damage is applied daily This = Planet From = Bombarder |  |
| on_planet_zero_pops | Planet has reached 0 pops from orbital bombardment This = Planet From = Bombarder |  |
| on_planet_zero_pops_ground_combat | Planet has reached 0 pops from collateral damage This = Planet From = Army owner |  |
| on_pop_abducted | Pop is abducted by raiding stance This = Pop scope From = planet abducted from |  |
| on_pop_enslaved | Pop is enslaved This = Pop scope owner_species = { (species) owner = { owner_species = { (empire main species) owner = { (empire) |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_pop_emancipated | Pop is released from slavery This = Pop scope owner_species = { (species) owner = { owner_species = { (empire main species) owner = { (empire) |  |
| on_pop_resettled | Pop is resettled From is previous planet planet = { } is new planet |  |
| on_pre_communications_established | Executed right before a country has established communications with another country This = Country which established the communications From = Country which communications were established with |  |
| on_post_communications_established | Executed right after country has established communications with another country. Does not fire if comms are established with establish_communications_no_message This = Country which established the communications From = Country which communications were established with |  |
| on_post_communications_established_always_fire | Executed right after country has established communications with another country. Always fires, even if comms are established with establish_communications_no_message This = Country which established the communications From = Country which communications were established with |  |
| on_presence_revealed | Serves to reveal presence to pre-ftl country This = Country which is revealing its presence From = Pre-ftl country |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_pop_bombed_to_death | Executed just after country has established communications with another country This = Planet where the pop was bombed to death From = Country which is raining down fire and brimstone |  |
| on_leader_death | Executed as a leader has died This = Country From = Leader |  |
| on_leader_fired | Executed as a leader has been fired This = Country From = Leader |  |
| on_leader_level_up | A leader leveled up. Scope = Country From = Leader |  |
| on_leader_assigned | Scope: Leader (after assignment) |  |
| on_leader_unassigned | Scope: Leader (just before unassignment) Fires if a leader is unassigned from their position for any reason (including being assigned elsewhere) |  |
| on_ruler_set | Executed as new ruler has been set This = Country |  |
| on_ruler_removed | Executed when a ruler has been removed From = Previous Ruler This = Country |  |
| on_ruler_back_to_pre_ruler_class | Executed when the ruler is ousted and goes back to their pre-ruler class From = Previous Ruler, already has the new class This = Country |  |
| on_blocker_cleared | This = Planet |  |
| on_ship_order | A ship has started a new order Root = Ship From = Country |  |
| on_policy_changed | Executes after a policy has been changed use last_changed_policy to identify which policy it was This = Country |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_ship_built | Scope: Ship Event A ship has been built Root = Ship From = Planet |  |
| on_ship_designed | A ship design has been finished Root = Country |  |
| on_ship_upgraded | A ship has been upgraded Root = Ship |  |
| on_war_beginning | A war is beginning, executed for every country in the war. Root = Country From = War |  |
| on_war_ended | A war has ended Root = Loser From = Main Winner |  |
| on_country_released_in_war | A country has been released through a peace deal in a war Root = new country From = country forcing the release FromFrom = country they are released from FromFromFrom = war |  |
| on_tech_increased | A country has increased the level of a tech, use last_increased_tech trigger to check tech and level. This = Country |  |
| on_modification_complete | Triggers when a Special Project to apply a species modification template has completed. Note that this will trigger once for each combination of planet & original species. This = Country From = Species (Post Modification) |  |
| on_planet_occupied | A planets controller becomes a country not the same as the owner. Root = Planet From = Planet Owner FromFrom = Planet Controller (the one occupying) |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_emergency_ftl | A fleet has successfully escaped from combat, executed right before the fleet enters FTL This = escaping fleet From = system escaped from FromFrom = system escaping to |  |
| on_army_recruited | An army construction has been completed. This = Planet From = Army |  |
| on_army_killed_in_combat | An army has been killed in ground combat This = owner From = army FromFrom = opponent FromFromFrom = planet |  |
| on_army_killed_no_combat | An army has ceased to exist for any other reason This = country From = army |  |
| on_building_complete | A building construction has been completed. This = Planet |  |
| on_building_queued | A building construction has been queued. This = Planet |  |
| on_building_unqueued | A building construction has been unqueued. This = Planet |  |
| on_building_upgraded | A building construction has been completed, which is an upgrade of previous building. This = Planet |  |
| on_building_demolished | A building construction has demolished. This = Planet |  |
| on_district_complete | A district construction has been completed. This = Planet |  |
| on_building_replaced | A building construction has finished, replacing another building. This = Planet |  |
| on_building_downgraded | A building construction has been downgraded and replaced. This = Planet |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_district_queued | A district construction has been queued. This = Planet |  |
| on_district_unqueued | A district construction has been unqueued. This = Planet |  |
| on_district_demolished | A district construction has demolished. This = Planet |  |
| on_tutorial_level_changed | Tutorial level for a country has changed This = Country |  |
| on_war_won | A war has been won Root = Winner Warleader From = Loser Warleader FromFrom = War |  |
| on_war_lost | A war has been lost Root = Loser Warleader From = Winner Warleader FromFrom = War |  |
| on_status_quo | A status quo has been signed Root = Actor From = Recipient FromFrom = Main Attacker FromFromFrom = Main Defender FromFromFromFrom = War |  |
| on_status_quo_forced | A status quo has been signed, by force Root = Recipient From = Actor FromFrom = Main Attacker FromFromFrom = Main Defender FromFromFromFrom = War |  |
| on_pop_added | A pop has been added to the planet Root = pop From = planet |  |
| on_pop_rights_change | We changed a species right This = pop |  |
| on_pop_grown | A pop has finished growing This = Planet scope From = Country FromFrom = Pop |  |
| on_pop_assembled | A pop has finished assembling This = Planet scope From = Country FromFrom = Pop |  |
| on_pop_purged | A pop has finished purging This = Planet scope From = Country FromFrom = Pop |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_pop_declined | A pop has finished declining (while not being purged) This = Planet scope From = Country FromFrom = Pop |  |
| on_pop_displaced | A pop has been displaced This = Planet scope From = Country FromFrom = Pop |  |
| on_rebels_take_planet | Initial rebels manage to take control of the planet, happens before the new owner is set, after the war is created. This = Rebel Country From = Planet FromFrom = War |  |
| on_rebels_take_planet_owner_switched | Initial rebels manage to take control of the planet, happens after the new owner is set, after the war is created. This = Rebel Country From = Planet FromFrom = War |  |
| on_planet_ownerless | FromFrom = Former Owner From = Country scope (new owner, so invalid) This = Planet scope |  |
| on_planet_transfer | Fired whenever a new owner is set for a planet, be it after a war or through a trade FromFrom = Former Owner (if any) From = Country scope (new owner) This = Planet scope |  |
| on_planet_conquer | Fired whenever a new owner is set for a planet, and the planet was aggressively conquered Fired in ADDITION to on_planet_transfer FromFrom = Former Owner From = Country scope (new owner) This = Planet scope |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_capital_changed | You have changed the location of your capital. Also called when a country’s capital is first set e.g. during galaxy creation (but then FROM is not set) this/root = new capital from = old capital |  |
| on_fleet_enter_orbit | From = Planet/Starbase/Megastructure scope This = Fleet scope |  |
| on_join_federation | This = Federation leader From = Joining member |  |
| on_leave_federation | This = Federation leader From = Leaving member |  |
| on_federation_law_vote_succeed | This = Country scope, federation leader From = Country to initiate the vote |  |
| on_federation_law_vote_failed | This = Country scope, federation leader From = Country to initiate the vote |  |
| on_federation_leader_elections | This = Country scope, federation leader From = Country to exclude from the federation elections |  |
| on_federation_new_leader | This = Country scope, new federation leader From = Previous leader (if still existing) |  |
| on_federation_leader_challenge |  |  |
| on_country_created | A country is created via create_country or create_rebels This = created country From = root of context where create_country/create_rebels happens |  |
| on_country_destroyed | This = destroyed country From = optional, destroyer (country) |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_megastructure_built | A Megastructure has been built Root = Country From = Megastructure FromFrom = System FromFromFrom = Fleet |  |
| on_megastructure_upgrade_begin | A Megastructure has begun to be upgraded Root = Country From = Megastructure FromFrom = System |  |
| on_megastructure_upgraded | A Megastructure has been upgraded Root = Country From = Megastructure FromFrom = System |  |
| on_colony_1_year_old | X years has passed since a planet was colonized (won't trigger on empire homeworld) |  |
| on_colony_2_years_old |  |  |
| on_colony_3_years_old |  |  |
| on_colony_4_years_old |  |  |
| on_colony_5_years_old |  |  |
| on_colony_6_years_old |  |  |
| on_colony_7_years_old |  |  |
| on_colony_8_years_old |  |  |
| on_colony_9_years_old |  |  |
| on_colony_10_years_old |  |  |
| on_colony_25_years_old |  |  |
| on_colony_yearly_pulse | Fires for each planet every year (counting up from colonisation date, includes home planet) |  |
| on_colony_5_year_pulse | Fires for each planet every 5 years (counting up from colonisation date, includes home planet) |  |
| on_colony_10_year_pulse |  |  |
| on_leader_spawned | a new leader is generated for an empire, to be available for recruitment scope: country, from: leader |  |
| on_election_started | Called when an election starts scope: country |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_election_ended | Called when an election ends scope: country |  |
| on_entering_gateway | Called upon entering FTL (on-action name scripted on the Bypass type) THIS = Fleet FROM = System jumping to FROMFROM = System jumped from |  |
| on_entering_wormhole | Called upon entering FTL (on-action name scripted on the Bypass type) THIS = Fleet FROM = System jumping to FROMFROM = System jumped from |  |
| on_entering_shroud_tunnel | Called upon entering FTL (on-action name scripted on the Bypass type) THIS = Fleet FROM = System jumping to FROMFROM = System jumped from |  |
| on_jump_drive | THIS = Ship |  |
| on_ship_quantum_catapult | Called upon a catapult jump being finished, per ship in catapulted fleet THIS = Ship FROM = System jumping to FROMFROM = System jumped from |  |
| on_fleet_quantum_catapult | Called upon a catapult jump being finished, per fleet THIS = Fleet FROM = System jumping to FROMFROM = System jumped from |  |
| on_pirate_spawn | this = country |  |
| on_starbase_transfer | Called when a Starbase changes owner THIS = Ship (Starbase) FROM = Former Owner (Country) |  |
| on_fleet_combat_joined_attacker | This = Aggressor Fleet From = Attacked Fleet FromFrom = Additional Attacked Fleet (if part of ongoing combat) FromFromFrom = Additional Attacked Fleet (if part of ongoing combat) |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_fleet_combat_joined_defender | This = Attacked Fleet From = Aggressor Fleet FromFrom = Additional Attacked Fleet (if joining ongoing combat) FromFromFrom = Additional Attacked Fleet (if joining ongoing combat) |  |
| on_system_lost | From = system FromFrom = country (new owner) This = country (previous owner) |  |
| on_system_gained | From = system FromFrom = country (previous owner) This = country (new owner) |  |
| on_slave_sold_on_market | This = Pop From = Country (buyer) Fromfrom = Country (seller) |  |
| on_relic_activated | This = Country |  |
| on_arch_stage_finished | This = Fleet (science vessel) From = Archaeological Site |  |
| on_arch_site_finished |  |  |
| on_resolution_passed | A galcom resolution passed this/root = proposer from = target if valid To find out which resolution it was, use last_resolution_changed trigger |  |
| on_resolution_failed | A galcom resolution failed to pass this/root = proposer from = target if valid To find out which resolution it was, use last_resolution_changed trigger |  |
| on_galactic_community_formed | This = Country, first member added |  |
| on_galactic_council_established |  |  |
| on_add_community_member | This = Country |  |
| on_remove_community_member |  |  |
| on_add_to_council |  |  |
| on_remove_from_council |  |  |
| on_join_alliance |  |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_leave_alliance |  |  |
| on_sign_commercial_pact | This = Country who accepted the proposal From = Country who proposed the commercial pact |  |
| on_sign_defensive_pact | This = Country who accepted the proposal From = Country who proposed the defensive pact |  |
| on_sign_migration_pact | This = Country who accepted the proposal From = Country who proposed the migration treaty |  |
| on_sign_non_aggression_pact | This = Country who accepted the proposal From = Country who proposed the non-aggression pact |  |
| on_sign_research_act | This = Country who accepted the proposal From = Country who proposed the research agreement |  |
| on_becoming_subject | This = subject From = subject’s overlord |  |
| on_subject_integrated | fires when a country finishes being integrated This = overlord From = subject |  |
| on_released_as_vassal | fires when a country releases a sector as a vassal This = released vassal From = overlord |  |
| on_ask_to_leave_federation_declined | This = empire trying to leave federation From = empire who declined (federation leader) |  |
| on_spynetwork_formed | this = owner country, from = spynetwork scope |  |
| on_add_to_imperial_council | THIS = Country: Emperor FROM = Country added to council |  |
| on_remove_from_imperial_council | THIS = Country: Emperor FROM = Country removed from council |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_first_contact_started | these three are fired from script, basically for modders who want to change how first contact works or add some extra flavour stories in without overwriting things THIS = first_contact |  |
| on_first_contact_stage_1_no_path | use for custom country types that need first contact paths THIS = first_contact |  |
| on_first_contact_generic_stage_2 | THIS = first_contact |  |
| on_branch_office_established | THIS = Planet: Branch office planet FROM = Country: Branch office owner |  |
| on_branch_office_closed | THIS = Planet: Branch office planet FROM = Country: Branch office owner |  |
| on_system_occupied | THIS = System: system being occupied FROM = Country: Conqueror of the system FROMFROM = Country: Original owner of the system |  |
| on_system_controller_changed | THIS = System: system whos controller has changed FROM = Country: New controller of the system FROMFROM = Country: Old controller of the system |  |
| on_system_returned | THIS = System: system being returned from occupation FROM = Country: Previous owner of the system FROMFROM = Country: Occupier of the system |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_orbital_defense_planet_ownerless | A planet has been rendered ownerless, it has an orbital ring or similar, though. The orbital ring is still there, but is about to be deleted this = starbase from = planet fromfrom = old owner |  |
| on_operation_chapter_finished | THIS = Espionage operation FROM = Operation target |  |
| on_operation_finished | THIS = Espionage operation FROM = Operation target |  |
| on_operation_cancelled | THIS = Espionage operation |  |
| on_pre_government_changed | Executed just as country is changing its government, before the new one is applied THIS = country |  |
| on_post_government_changed | Executed just as country is changing its government, after the new one is applied THIS = country |  |
| on_custodian_term_ends | Executed when the Custodian’s term ends THIS = country |  |
| on_tradition_picked | Executed when a country picks any tradition (including starters and finishers) THIS = country |  |
| on_ascension_perk_picked | Executed when a country picks an ascension perk THIS = country |  |
| on_megastructure_change_owner | Executed when a megastructure has a new owner this = new owner from = megastructure fromfrom = old owner (if existing) |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_megastructure_ownerless | Executed when a megastructure is rendered ownerless this = solar system containing megastructure from = megastructure fromfrom = old owner (if existing) |  |
| on_crystalline_empire_task |  |  |
| on_destroy_star_system | Fired from destroy_star_system scripted effect This = system From = destroyer (if using a star cracker) |  |
| on_admirals_bickering_event_chain |  |  |
| on_establish_mercenary_enclave | Executed when an empire wishes to turn a mercenary fleet into a Mercenary enclave This = fleet |  |
| on_debris_researched | Fired when a science ship succesfully analyzed or scavenged debris this = country from = debris fromfrom = controller of destroyed ship |  |
| on_debris_scavenged | Fired when a science ship succesfully analyzed or scavenged debris this = country from = debris fromfrom = controller of destroyed ship |  |
| on_debris_scavenged_and_researched | Fired when a science ship succesfully analyzed or scavenged debris this = country from = debris fromfrom = controller of destroyed ship |  |
| on_specialist_subject_conversion_started | Fired when a subject has started converting to a specialist type This = agreement owner = overlord target = subject |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_specialist_subject_conversion_finished | Fired when a subject has finished converting to a specialist type This = agreement owner = overlord target = subject |  |
| on_specialist_subject_conversion_aborted | Fired when a subject specialist conversion has been aborted This = agreement owner = overlord target = subject |  |
| on_capitals_connected | Executed when a two capitals get connected through relay network THIS = Country: Owner FROM = Country: Other |  |
| on_agreement_change_accepted | Fired when a change to an existing subject agreement has been accepted This = agreement owner = overlord target = subject |  |
| on_shroudwalker_divination_visitors_situation |  |  |
| on_shroudwalker_divination_locus_situation |  |  |
| on_shroudwalker_insight_situation_finish |  |  |
| on_cloaking_activated | Fired when a fleet activates cloaking This = Fleet |  |
| on_cloaking_deactivated | Fired when cloaking is deactivated for a fleet (voluntarily or involuntarily) This = Fleet |  |
| on_awareness_level_increase | Fired when a pre-FTL's awareness level increases (by uncloaking ships or using add/set_awareness in events) This = PreFTL Country From = Observing Country |  |

| Name | Desc | Community Notes |
|---|---|---|
| on_awareness_level_decrease | Fired when a pre-FTL's awareness level decreases (by uncloaking ships or using add/set_awareness in events) This = PreFTL Country From = Observing Country |  |
| on_pre_ftl_pop_ethic_shift | Chance of pre-FTL civilizations to shift their ethics |  |
| on_country_attacked | Fired when a country attacks another country This = attacked country From = attacker country |  |

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

NewPP limit report Cached time: 20260714121040 Cache expiry: 86400 Reduced expiry: false Complications: [show‐toc] CPU time usage: 0.052 seconds Real time usage: 0.062 seconds Preprocessor visited node count: 172/1000000 Post‐expand include size: 18735/2097152 bytes Template argument size: 8180/2097152 bytes Highest expansion depth: 7/100 Expensive parser function count: 0/100 Unstrip recursion depth: 0/20 Unstrip post‐expand size: 0/5000000 bytes

Transclusion expansion time report (%,ms,calls,template) 100.00% 17.835 1 -total 57.04% 10.174 1 Template:ModdingNavbox 42.51% 7.582 1 Template:Version 42.17% 7.522 1 Template:Navbox 25.10% 4.476 1 Template:Infobox 13.35% 2.382 14 Template:Navboxgroup 12.74% 2.272 1 Template:Clear 11.72% 2.090 1 Template:Nowrap

Saved in parser cache with key wiki_stellaris-mwstella_:pcache:idhash:11044-0!canonical and timestamp 20260714121040 and revision id 115992.

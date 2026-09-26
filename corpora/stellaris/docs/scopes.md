# Scopes
Source: https://stellaris.paradoxwikis.com/Scopes
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260720111045 (the live wiki blocks non-browser clients). Page version banner: Version Please help with verifying or updating older sections of this article. At least some were last verified for version 3.2. This article is for the PC version of Stellaris only. | Please help with verifying or updating this section. It was last verified for version 3.2._

Most objects in the game provide a scope to access them through script. A planet will provide a planet scope and a pop will provide a pop scope. The relationship between objects also relates to their scopes. To access the planet which a pop is on is called a scope switch, as your code is switching from referring to the pop to referring to the planet. Most objects and their scopes form a tree-like relationship, with the global scope representing the entire game.

In code, scopes are written as <scope_type> = { }, with all the script in the brackets referring to the specific object of the scope. For example: pop = { unemploy_pop = yes } would cause the current pop to become unemployed. Scopes can be used in both trigger and effect blocks. Some triggers and effects will take a scope as an argument, and some apply to a specific scope despite what scope they are run. For example, years_passed < 50 always refers to global scope, no matter what the current scope is.

A list of all known scopes is available below.

## System scopes

There are special system scopes that refer to relationships between scopes. These are THIS, PREV, ROOT, and FROM.

- THIS – Refers to the current scope. It is useless as context switch, but sometimes is used as input for certain effects. If you are in a pop scope, this would refer to that pop.
- PREV – Refers to the previous scope. If you are in a pop scope, and change to the planet scope, prev would refer back to the pop. pop = { planet = { habitability = { who = prev value > 0.6 } } } would check that the habitability of the current pop has over 60% habitability on its current planet. Sometimes you will want to refer back more than one scope step, in which case you can repeat prev up to four times, i.e. prevprev up to prevprevprevprev
- FROM – Refers to the scope from which the current script was called. For example, if an event executed a planet event, the planet event could refer back to the objects in the first event using the from scope. Just like PREV, up to four FROMs can be repeated to refer back multiple times.

- ROOT – Refers to the main scope of the script. For events, this will be the object the event is called in. For example, in a planet_event, root will be the specific planet the event was called on. ROOT is usually the default scope for script blocks in the event, but is shorter and more clear than PREV to refer to when you have switched to other scopes. For example, in a pop event’s immediate block, the pop is the default scope. But if you switch to the planet scope of the pop, and possibly to even more chained scopes, root will always refer back to the pop the event was called on. Note that in some scripts, such as scripted_effects and scripted_triggers, the default scope, this, is not necessarily the same as root.

In some contexts, these relationships aren't intuitive. For instance, on_action s will often override some of these system scopes to hold the objects the action refers to. For example, in events called from on_ship_disabled, this will refer to the disabled ship, and from will refer to the ship that disabled it. The vanilla on_actions.txt file has comments describing most of these, while others you will have to look at code to determine to which objects they refer.

Note that these scopes can be also treated as new script context in some initial effect blocks (when they actually aren't), e.g. for create_leader / clone_leader (however, it is not clear if this is a bug or a feature, as this is an inconsistent behavior).

## Chaining scopes

To simplify code and increase readability, a. can be used to chain scopes together. For example, owner = { capital_scope = { solar_system = { … } } } is equivalent to owner.capital_scope.solar_system = { … }, and will take you to the solar system of the capital of the country that owns the current scope. For the PREV and FROM system scopes, if you need more than four, you can chain them together as well: prevprevprevprev.prevprev. Note that this dot-scoping does not work with the scope-changing triggers and effects referred to below, also this does not imply a new PREV.

## Scope existence

Oftentimes scripts expect certain scopes to exist, or to run in certain scopes. Sometimes, some scopes and relationships don't always exist. For example, if you scope to the owner of a planet (planet = { … owner = { … } }), and the planet isn't owned, the script will fail and produce an error in the error.log. As such, it is good practice to always check that a scope exists if there is any chance it might not. This is done using exists. Before changing the scope, use exists = [scope]. If it doesn't exist, the following code won't run. planet = { exists = owner owner = { … } }

## Triggers and scopes

Main article: Triggers

Most triggers can only be called within certain scopes. For instance, is_moon will only work in a planet scope. If you attempt to call a trigger in the wrong scope, it will produce an error in the error.log and often cause the rest of the code to fail or produce unintended results. The code will also error if you attempt to execute a trigger on a scope that doesn't exist.

Some triggers will also perform a scope change. These triggers usually begin with any_, and script in them will run in the implied scope. They will return yes if any object of that scope matches the criteria. For example, any_planet_within_border = { is_planet_class = pc_gaia } will return yes if the country it is called on has a Gaia planet in its borders. It will iterate through all planet scopes of the country and execute the trigger criteria in the scope. So all script within the trigger’s braces will execute in planet scope, even though it was called from country scope.

## Effects and scopes

Main article: Effects

Much like triggers, most effects only work in specific scopes. If you attempt to call a trigger in the wrong scope, it will produce an error in the error.log. However, executing an effect on a scope that doesn't exist will just cause nothing to happen with no error.

Some effects will also perform a scope change. These effects usually being with every_ or random_. every_ will apply the effect(s) within to every object of that scope, while random_ will apply the effect(s) within to a single random object of that scope. A limit = { … } statement can be used within these effects to narrow down the results. For example, every_owned_planet = { limit = { is_planet_class = pc_continental } … } is called from country scope, but would apply the enclosed effect(s) to every Continental planet the country owned. The effects within would all run in the planet scope of the continental planet, even though they were called from country scope.

## Event target

Sometimes it’s a good idea to save certain scopes as event targets to use in later events or projects in the same namespace, or to use globally.

- Use the save_event_target_as = <name> to save the scope for later use in the namespace, or save_global_event_target_as = <name> to save the scope for later use anywhere.
- They can be scoped to using event_target:<name> = { … }, or used as a target for trigger or effect parameter.

For example, if an event at the start of a war saved the war leader as save_event_target_as:war_leader, after the war you could refer to them again:

planet.owner = { set_subject_of = { who = event_target:war_leader subject_type = vassal } }

Event targets are used in localization by referencing directly the variable name:

"I have decided to release my vassal [target_leader.GetFullName]"

Or can be used in tooltips of the event in which they are saved (which is normally not possible, as tooltips are built before effects are executed).

- Dynamic event targets: you have the ability add @scope in event targets and global event targets names. For example:

save_event_target_as = something@root. Although be warned, it doesn’t handle dot scoping very well and probably won’t do what you want it to do if you try something like something@root.owner or exists check also do not work properly.

When you know you will no longer need a saved global event target, it is good practice to clear it: clear_global_event_target = <name>

See also: Event modding

## Scope Types

Every scope is of a particular type of object. The type determines when it can be used. They can be checked with is_scope_type = (see Conditions). The following are types that apply in game:

| Scope Type | Scopes of this type | Can scope to owner = { xyz = {…} } | Description |
|---|---|---|---|
| country | owner, controller, space_owner, overlord, subject, last_created_country, branch_office_owner | capital_scope capital_star home_planet unhappiest_pop leader ruler alliance overlord federation associated_federation species owner_species built_species | An empire. Some of these are unique. For instance, the Shroud is a country, all Tiyanki’s are a members of the Tiyanki country, etc. |
| sector | sector | owner leader ruler heir owner_species sector_capital | A sector in an empire. |
| galactic_object | solar_system, last_created_system | star starbase owner space_owner leader ruler heir owner_species sector | An object (solar system) on the galactic map. |
| megastructure | megastructure | solar_system system_star star planet planet_owner owner leader ruler heir owner_species sector | A system object built by constructor ships. Note that habitats and ringworlds are converted to type planet after they are completed. |
| ambient_object | ambient_object, last_created_ambient_object | solar_system system_star space_owner star sector | A point-of-interest in a galactic_object. |

| Scope Type | Scopes of this type | Can scope to owner = { xyz = {…} } | Description |
|---|---|---|---|
| planet | planet, capital_scope, orbit, star | solar_system system_star space_owner star sector orbit planet_owner controller owner_species sector starbase orbital_defence orbital_station ruler heir unhappiest_pop (assembling_species branch_office_owner declining_species growing_species) | An entity within a galactic_object. Stars, asteroids, habitats, ringworlds and planets are all considered planet-type scopes. If a pop can live on it, it is a planet-type. |
| deposit | deposit | planet | A planetary feature, including blockers. Some are exploitable by orbiting stations, others are exploitable by colonizing the planet. |
| tile | tile ? | ? | Mostly deprecated, but still officially supported. Never used in Vanilla. |
| archaeological_site | archaeological_site | owner owner_species planet planet_owner ruler leader heir sector star solar_system space_owner system_star (excavator_fleet) | A site of an archaeological dig, persists after it’s completed. |
| army | last_created_army | ship, fleet leader ruler heir owner planet_owner planet orbit home_planet sector solar_system system_star space_owner pop species owner_species | An army. |
| pop | pop, last_created_pop | owner planet home_planet species | A pop. |

| Scope Type | Scopes of this type | Can scope to owner = { xyz = {…} } | Description |
|---|---|---|---|
| pop_faction | pop_faction | country leader ruler heir owner_species | A political faction within a country. |
| species | species, owner_species, last_created_species | home_planet owner_species – (pop) | The specific pop (sub)species. |
| leader | leader, ruler, last_created_leader | fleet species owner ruler heir sector solar_system home_planet | A leader in a country. This includes the current ruler, as well as leaders in the hiring pool. |
| ship | starbase, last_created_ship | fleet orbit leader heir owner owner_species space_owner sector | An empire controlled entity in space. This includes starbases and defense platforms. |
| fleet | fleet, last_created_fleet | orbit star starbase system_star leader ruler heir owner controller space_owner owner_species sector solar_system archaeological_site | Every ship belongs to a fleet, even a lone ship. A starbase fleet includes its defense platforms. |
| debris | debris | – | A shipwreck debris. |
| design | design, last_created_design | – | A ship design. |
| federation / alliance | federation / alliance | leader federation_leader | A federation. Other than localisation of triggers, federation and alliance alliance are interchangeable. Vanilla uses federation. |

| Scope Type | Scopes of this type | Can scope to owner = { xyz = {…} } | Description |
|---|---|---|---|
| war | war | attacker defender | A two-sided diplomatic war between two or more empires. |
| first_contact | first_contact, reverse_first_contact | contact_country owner owner_species leader ruler heir star system_star solar_system sector | A two-sided first contact site between two empires. |
| espionage_operation | ? | spynetwork target owner owner_species leader ruler heir | An espionage operation (site). |
| spy_network | spynetwork | target owner owner_species leader ruler heir space_owner | A spy network of an espionage operation or spymaster envoy. |

## List of scopes

You can get the latest version in-game by using the trigger_docs console command or can be found in the scopes.log file in your local user data folder script_documentation (e.g.%USERPROFILE%\Documents\Paradox Interactive\Stellaris\logs\script_documentation\).

| Scope name | Scope type | Can be scoped from xyz = { owner = {…} } | Description |
|---|---|---|---|
| owner | country | fleet ship planet pop leader army megastructure sector starbase | Scopes to the country that owns the object. NOTE: uncolonized planets do NOT have an owner. Use space_owner to get the owner of the space that contains an uninhabited planet. |
| controller | country | fleet ship planet pop leader army megastructure sector starbase | Scopes to the country that currently occupies the object. |
| contact_country | country | first_contact | Scopes from a first contact site to the country that the owner of the site is seeking to establish communications with. |
| federation_leader | country | federation | Scopes from a federation to the empire leading it. |
| last_refugee_country | country | any | Scopes to the last country from which a pop fled to escape purge (via on_pop_displaced). |
| galactic_emperor | country | any | Scopes to the ruling empire of the Galactic Imperium. |
| galactic_custodian | country | any | Scopes to the Custodian empire of the Galactic Community. |
| attacker / defender | country | war | Scopes from a war to its main attacker / defender. |
| branch_office_owner | country | planet | Scopes from a planet to the owner of a branch office. |
| overlord | country | country | Scopes from a country to its overlord. |

| Scope name | Scope type | Can be scoped from xyz = { owner = {…} } | Description |
|---|---|---|---|
| planet_owner | country | megastructure planet pop army starbase deposit archaeological_site | Scopes from an object to the owner of the planet it is on. |
| space_owner | country | megastructure planet country ship fleet galactic_object army ambient_object starbase archaeological_site spy_network debris | Scopes to the country that currently owns the galactic_object |
| last_created_country | country | any | Scopes to the last created country. Usually used after a create_country effect. |
| sector | sector | megastructure planet ship pop fleet galactic_object leader army ambient_object starbase deposit sector archaeological_site first_contact debris | A sector in a country. |
| solar_system | galactic_object | megastructure planet country ship pop fleet galactic_object leader army ambient_object starbase deposit archaeological_site first_contact debris | A solar system. |
| last_created_system | galactic_object | any | The last created solar system. Usually used after a spawn_system effect. |
| ambient_object | ambient_object | – | A non-planet entity in a solar_system. Often a point-of-interest for a special project. |
| last_created_ambient_object | ambient_object | any | The last created ambient object. Usually used after a create_ambient_object effect. |

| Scope name | Scope type | Can be scoped from xyz = { owner = {…} } | Description |
|---|---|---|---|
| megastructure | megastructure | – | A megastructure. |
| star | planet | megastructure planet ship fleet galactic_object ambient_object starbase archaeological_site first_contact debris | The star of the solar system. May consist of multiple planet-scope stars though one is always considered the main star. See "orbit" for how to determine secondary stars and planets. |
| system_star | planet | megastructure planet country ship pop fleet galactic_object leader army ambient_object starbase deposit archaeological_site first_contact debris | The primary star of the solar system. Works on all objects visible in star system view. |
| planet | planet | megastructure planet (moon) pop army starbase deposit archaeological_site | A planet, star or habitable structure. |
| capital_scope | planet | country | The capital planet of the country. |
| capital_star | planet | country | The primary star of the empire capital’s system. |
| home_planet | planet | leader pop species country | The home planet of a species/country. |

| Scope name | Scope type | Can be scoped from xyz = { owner = {…} } | Description |
|---|---|---|---|
| orbit | planet | planet ship fleet army starbase | The planet-type object a fleet, ship, or moon is orbiting. In a system with multiple stars with their own orbiting planets, scopes to the star the planet is orbiting, UNLESS it is orbiting the primary star, in which case this scope does not exist. |
| sector_capital | planet | sector | The capital planet of the sector. |
| deposit | deposit | – | A planetary feature, including blockers and space deposits. |
| archaeological_site | archaeological_site | megastructure planet ship fleet galactic_object ambient_object starbase archaeological_site debris | An arc site on the location. |
| army | army | – ship (country planet) | A defensive or offensive army. |
| last_created_army | army | any | The last created army, usually used with the create_army effect. |
| pop | pop | leader army (planet country pop_faction sector species) | A pop. |
| last_created_pop | pop | any | The last created pop, usually used with the create_pop effect. |
| unhappiest_pop | pop | planet country | The unhappiest pop from country or planet. |
| pop_faction | pop_faction | – | A political faction in an empire. |
| last_created_pop_faction | pop_faction | any | The last created pop faction that was created anywhere in the game. |

| Scope name | Scope type | Can be scoped from xyz = { owner = {…} } | Description |
|---|---|---|---|
| species | species | country ship pop leader army species (planet) | A specific pop species or subspecies. |
| owner_species / owner_main_species | species | megastructure planet country ship pop fleet galactic_object leader army species pop_faction starbase deposit sector archaeological_site first_contact spy_network espionage_operation agreement situation debris | The main species of a country. Usually the founder species, unless changed with change_dominant_species effect. Works in every scope that 'owner' would work in. |
| last_created_species | species | any | The last created species, usually used with the create_species effect, or the secondary species created by a player during empire creation. |
| leader | leader | country ship fleet leader army pop_faction federation sector archaeological_site first_contact spy_network espionage_operation | A leader in a country including potential leaders in the pool. |
| ruler | leader | megastructure planet country ship pop fleet galactic_object leader army pop_faction starbase deposit sector archaeological_site first_contact spy_network espionage_operation agreement situation debris | The leader that is the current ruler of a country. |

| Scope name | Scope type | Can be scoped from xyz = { owner = {…} } | Description |
|---|---|---|---|
| last_created_leader | leader | any | The last created leader, usually used with the create_leader effect. |
| ship | ship | – (fleet) | A ship. |
| last_created_ship | ship | any | The last created ship, usually used with the create_ship effect. |
| starbase | ship | planet (star) galactic_object | An outpost or larger starbase that claims a system. |
| fleet | fleet | ship fleet leader army starbase (country galactic_object) | A fleet containing at least one ship-type object. |
| last_created_fleet | fleet | any | The last created fleet, usually used with the create_fleet effect. |
| excavator_fleet | fleet | archaeological_site | A fleet whose leader is currently investigating an arc (not vanilla used). |
| orbital_defence | fleet | planet | A orbital defense station (orbital ring, starbase) orbiting the planet. |
| orbital_station (research_station / mining_station / observation_outpost) | fleet | planet | A station station in orbiting a planet. |
| design | design | ship (fleet) | A ship design. |
| last_created_design | design | any | The last created design, usually used with the create_design effect. |

| Scope name | Scope type | Can be scoped from xyz = { owner = {…} } | Description |
|---|---|---|---|
| federation / alliance / associated_federation | federation / alliance | country | A federation. Note that federation and alliance are seemingly interchangeable but vanilla uses federation. |
| war | war | – (country) | A declared war. |
| spynetwork | spy_network | leader espionage_operation | Scopes from an espionage operation or spymaster envoy to its spy network. |
| target | various (country) | spy_network espionage_operation agreement situation | A target country to a spy network, or an espionage operation. – (can be various objects, as set in common/espionage_operation_types). |

### Flat list of scopes

The source page ends with a flat list of about 1,600 scope-changing triggers and effects. It is omitted here because the same entries, with descriptions and examples, are in `triggers_*.md` and `effects_*.md`.

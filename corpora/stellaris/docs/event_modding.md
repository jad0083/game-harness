# Event modding
Source: https://stellaris.paradoxwikis.com/Event_modding
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260420221551 (the live wiki blocks non-browser clients). Page version banner: Version Please help with verifying or updating older sections of this article. At least some were last verified for version 3.6. This article is for the PC version of Stellaris only._

## Event types

There are several types of events:

1. event – for an entire game (global event)
2. country_event – for an entire empire
3. planet_event – for a planet
4. fleet_event – for a fleet
5. ship_event – for a ship
6. pop_faction_event – for a faction
7. pop_group_event – for a population unit (since v4.0, former pop_event)
8. observer_event – for the observer (development usage only; use console command "observe" to enter observer mode)
9. system_event – for a system, galactic_object (since v3.0)
10. starbase_event – for a starbase (since v3.0)
11. leader_event – for a leader (since v3.0)
12. espionage_operation_event – for use inside espionage operations (since v3.0)
13. first_contact_event – for first contacts (since v3.0)
14. situation_event – for a situation (since v3.3)
15. agreement_event – for subject agreements (since v3.4)

## Basic Behavior

### Namespace and Event ID

The top of every event file must contain a namespace line. The namespace is used as the basis for identifying all events in the file. If you open the on_action_events.txt file near the top of the file you will find namespace = action. Then every event in this file has an ID that starts with action followed by a period then a unique number as shown here for the actions.8 event:

```
country_event = {
	id = action.8
	hide_window = yes
	is_triggered_only = yes
	trigger = {
		is_country_type = default
		from = { is_country_type = default }
		NOT = { has_communications = from }
		is_hostile = from
	}
	immediate = {
		establish_communications = from
		fromfrom = {
			conquer = root
			set_controller = root
		}
	}
}
```

Anywhere in the game that needs to call this event will use the ID property.

An event file can have any number of namespace.

Namespace names can be very long. Max character length that's currently verified for is 100 characters.

Also, namespaces can include numbers as part of their name (see the vanilla paragon_2 namespace).

Event ID can't have letters, or it will be recognized as "namespace.0". Leading zeros in IDs are truncated (namespace.003 is the same as namespace.3).

### Execution

By default every event has all its triggers checked against every game object at least once per game day, possibly once per game tick. For the objects where the triggers are all met, the code of the event is executed with the scope of said object.

However, events should usually not be run in this fashion, as it is very expensive on performance. Instead, an event should either use is_triggered_only = yes, which will exempt the event from this persistent polling, and trigger the event from elsewhere; or it should use mean_time_to_happen, which increases the intervals at which the event is checked.

Similarly works fire_only_once = yes. However unlike is_triggered_only the code will still be polled, only to be removed after it was executed at least once. Also, as of 2.1.2, the conditions for a fire_only_once event should exclude the event firing a second time or error log entries are created.

### Condition

Events can have conditions represented with trigger section of Condition statements. If the condition is evaluated false, this event doesn't trigger. Here is an example from the event "apoc.1".

```
 trigger = {
 	owner = {
 		NOT = { has_country_flag = encountered_first_gateway }
 	}
 	from = {
 		has_star_flag = abandoned_gateway
 		any_system_megastructure = { is_megastructure_type = gateway_ruined }
 	}
 }
```

#### Pre triggers

Pre-triggers are fast triggers that are tested before full triggers, they are meant to be fast and quickly exclude target scopes from events, they take the form of "yes/no" question. Use this to improve performance related to events. If an entry is not included, it will be ignored. They work for planet, pop, system, starbase and leader scopes.

Note: Pre-triggers are functionally independent of normal triggers. Any naming similarities are just for convenience (they don't share the same code base and work independently).

Possible planet values:

```
pre_triggers = {
	has_owner = yes				# whether the planet has an owner
	is_homeworld = no			# whether the planet is its owner's homeworld
	original_owner = yes		# whether the planet still belong to its original owner
	has_ground_combat = no		# whether ground combat is going on the planet
	is_capital = no				# whether the planet is the capital world of the empire it belongs too
	is_occupied_flag = no		# whether the planet is occupied
    is_ai = no					# whether the planet owner is controlled by the computer or by a human
}
```

Note: In this case, all triggers have counterparts with normal triggers, except for is_ai, which is seemingly the only one which has not a direct planet scope (in older versions, pre v3.3 it was not functional).

Possible pop from jobs values:

```
possible_pre_triggers = {
	has_owner = yes				# whether the pop planet has an owner
	is_enslaved = no			# whether the pop is enslaved
	is_being_purged = no		# whether the pop is being purged
	is_being_assimilated = no	# whether the pop is being assimilated
	has_planet = yes			# whether the pop is on a planet or not
	is_sapient = yes			# whether the pop is sapient
	is_robotic = yes			# whether the pop is robotic - since v4.0
}
```

can_join_pre_triggers in pop_factions accepts the same parameters.

**system**

has_owner # whether the system has an owned starbase is_capital # whether the system has its owner's capital in it is_occupied_flag # whether the system is fully occupied by someone other than its owner, including all of its planets

**starbase**

has_owner # whether it has an owner is_occupied_flag # whether the controller is not the owner

**leader**

has_owner is_idle # whether the leader is assigned to a task

Note: Any other syntax in this pre-triggers blocks will raise an error (except for code comment syntax, of course).

### Visibility

By default every Event will display a window and thus needs at least one option and a number of textfields to display. In order to suppress that window (and the need to set all the necessary text fields) hide_window = yes can be used. This is mainly used to trigger events that are used for achievements or events that the player should not know are happening.

### Code execution

The primary place for code is the immediate section of Effect statements. Most events have all their code contained inside this block. You can use if statement in immediate section, like the following, as seen in colony.events.txt.

```
 immediate = {
 	if = {
 		limit = {
 			event_target:subterranean_nation = {
 				NOT = { has_country_flag = tech_request_approved }
 			}
 		}
 		create_army = {
 			name = "NAME_Invading_Horde"
 			owner = event_target:subterranean_nation
 			species = event_target:subterranean_species
 			type = "industrial_army"
 			leader = last_created_leader
 		}
 	}
 }
```

However visible events need at least one option (the OK Button of a message box). Every option can carry its own code.

Scope is a very important consideration for any code executed in any event and it is heavily based on how the event was called.

### Mean Time To Happen

A additional condition very often used on event that triggered by regular polling, is the mean_time_to_happen (MTTH). This will delay the execution of the event by a random amount of ingame days. On average the activation will be delayed as given, but the exact number can vary considerably. Counting starts the moment all other trigger conditions are met and it is not clear how exact the internal implementation of this delay works, however it seems likely the MTTH is regularly polled just like all other triggers.

- mean_time_to_happen = { months = 5 } or mean_time_to_happen = { days = 15 }

Available time units: days, months, years.

The MTTH can be modified with any number of conditional modifiers and it seems such things can take effect after the MTTH counting has begun.

Testing has shown that a simple MTTH will be called with a 50% chance during the period of time specified for each item in that scope e.g. each country for a country event. It will then check the triggers, and if they are true, the event will be triggered. However, if modifiers to the MTTH are introduced, the game will check the conditions every day for each scope – meaning that these are considerably more expensive in terms of performance.

Warning: Due to poor performance, using MTTH has fallen out of favor, and vanilla has started to remove uses of MTTH, and is instead using events with random delays (see below).

## Calling events from other events

It is possible to manually call an event onto any gameobject from a running event. Doing so will put the event into the game objects scope. There might be a slight delay of at least one or more game ticks until the event is actually called. For example:

```
 random_galaxy_planet = {
 	planet_event = { id = my_planet_event.1 }
 }
```

While doing this the triggering can be delayed by any fixed or semi-fixed timeframe (with optional DAYS and RANDOM delay). For example: country_event = { id = crisis.2000 days = 200 random = 100 } delays it by 200–300 days.

As the event attempts to execute, if its conditions are not met, it doesn't execute. If the event is delayed, the conditions are checked only before execute, but not before queuing up.

Since 3.0 there is also an optional scope parameter, where you can override the calling scope: scopes = { from = fromfrom }. Do note that when defining scopes, local event_targets will not be properly scoped to in events firing from the event. For more see section On Actions below.

## On Actions

Aside from the default polling another very common way to get an event triggered is on_action. The vanilla game itself has a number of events registered this way in Stellaris\common\on_actions\00_on_actions.txt

Mods can provide their own, uniquely named, on_action file whose events are called in addition the vanilla events. The file should be put into Stellaris\common\on_actions\, but the Modding Guidelines should be observed

The situations of triggering range from polling less aggressive (monthly or yearly) to numerous developments of the galaxy like ending of a planetary invasion, survey, entering of a system and so forth. This is later part is comparable to registering an Event in a GUI Environment of many higher programming languages.

Registered events should be marked with "triggered only" modifier. As easily dozens of events can be registered to any one development (often belonging to the same chain) the triggers decide which events are actually called.

A special case is random events which have a specific chance to trigger anytime that development happens. However, the triggers can make this a lot rarer than even chance might indicates.

Aside from "on_actions", events can be triggered from any file with an effects field. Most notable are anomalies, but one can similarly trigger an event from e.g. within an edict (it will then trigger every time the edict is activated), policy, diplomatic action, etc.

Since 3.0 you can define your own "on_actions" in script by effect fire_on_action = { on_action = <string> scopes = { from = X fromfrom = Y } }. Do note that when defining scopes, fire_on_action appears to be considered a scope and all non-event_target scopes require a prev added before them (from = prev will scope to the scope firing the on_action, and to scope to the previous scope from = prevprev must be used instead). In addition, event_targets will not be properly scoped to in events firing from the on_action if used for any scope above from (fromfrom, fromfromfrom, etc.).

## Conditional Description

The description of an event may change based on conditions. It uses the following syntax as seen in colony_events.txt.

```
 planet_event = {
 	id = colony.182
 	title = "colony.182.name"
 	desc = {
 		trigger = {
 			owner = { NOT = { has_authority = auth_machine_intelligence } }
 		}
 		text = colony.182.desc
 	}
 	desc = {
 		trigger = {
 			owner = { has_authority = auth_machine_intelligence }
 		}
 		text = colony.182.desc.mach
 	}
 	…
 }
```

If multiple triggers match, only one of them will be shown at random. If none of the triggers match, the system will show the first description anyway.

If more than one desc entry is provided, only one of them will be shown at random (since 3.0).

So conditional description and static description can be used together. For instance:

```
 planet_event = {
 	id = colony.182
 	title = "colony.182.name"
 	desc = {
 		trigger = {
 			owner = { NOT = { has_authority = auth_machine_intelligence } }
 		}
 		text = colony.182.desc
 	}
 	desc = colony.182.desc.mach
 	…
 }
```

Additionally, you can use this setup below create Dynamic Localisation that allows usage of multiple Loc Keys (as long as triggers match) in a single desc entry:

```
 planet_event = {
 	id = colony.182
 	title = "colony.182.name"
 	desc = {
 		trigger = {
 			# Always Available TEXT (1)
 			text = colony.182.desc.top
 			# Text to Show if the Game is Multiplayer
 			success_text = {
				text = colony.182.desc.multiplayer
				is_multiplayer = yes
			}
 			# Text to Show if the Game is Singleplayer
 			fail_text = {
				text = colony.182.desc.singleplayer
				is_multiplayer = yes
			}
 			…
 			<triggers>
 			…
 			# Always Available TEXT (2)
 			text = colony.182.desc.bottom
 			…
			<triggers>
 		}
 	}
 	…
 }
```

You can use this setup in combination with multiple desc entries as shown above for incredibly dynamic localisations.

## Options

All visible events need at least one Option (comparable to the “OK” button of a message box). Options themselves have numerous variables that can be set.

The after block has to be written as a peer of the options, it is executed after an option is chosen, regardless which option was chosen. That makes it comparable to a finally block in many error handling systems of a language like Java.

name Defines the display name of the option. It is the only value somewhat mandatory. Often a localizable string is used here. There are numerous default strings that can be used here which are already localised.

name can also take a triggered block with multiple name blocks per option'

```
 option = {
 	name = {
 		trigger = { <display_triggers> }
		text = <localization_string>
	}
 	name = {
 		trigger = { <display_triggers> }
		text = <localization_string>
	}
	...
 }
```

trigger Defines if the option is shown at all. If it’s not shown, so is it unchoosable.

exclusive_trigger If valid, disables all other event options (added with 2.0).

default_hide_option If set to yes, this option is selected by default when a “Cancel” key is pressed (does NOT hide the option as the name suggests).

icon Defines an optional icon sprite.

sound Defines an optional sound-effect file played when the option is chosen.

allow Defines if the option is choosable. A option can be both shown and not choosable, often to show which options will become available with specific play. This subblock is comparable to the "Enabled" value or property in many GUI environments. The check is done only when the Event window is first shown and not updated with game progress.

tag Special tag to indicate that this is the option to dismiss/hire a leader, only works if the country event has event_window_type = leader_recruit (added with 3.8).

hide_option_if_not_allowed Special option that hides this Option if it's not allowed, only works if the country event has event_window_type = leader_recruit (added with 3.10).

Effect statements can be put into the body of the option. No special block must be put around it.

The game tries to generate a tooltip for this option based on all the effects. custom_tooltip = xxx can be used to show the player a tooltip in addition to the generated tooltips. Also, hidden_effect = { … } can be used to contain other effects to prevent the game from generating tooltips based on them.

```
 option = {
 	name = "xxx"
 	custom_tooltip = "yyy"
 	hidden_effect = {
 		 (Effect statements to be executed when this event is chosen)
 	}
 }
```

ai_chance use this subblock to allow an AI to do a semi-random decision between all available options, to make some choices more likely to be picked by the AI. Here is an example from a War in Heaven event.

```
 ai_chance = {
 	factor = 100
 	modifier = {
 		factor = 0
 		OR = {
 			has_valid_civic = civic_hive_devouring_swarm
 			has_valid_civic = civic_fanatic_purifiers
 			has_valid_civic = civic_machine_terminator
 		}
 		# Instead you can also use the corresponding scripted trigger: is_homicidal = yes
 	}
 }
```

The following options are available for diplomatic events (if diplomatic = yes):

response_text: optional setting for an localisation key. NOTE: Without 'is_dialog_only' setting, Event window shows localisation key with just an 'OK' button to exit the Event. In this case,the after = {} code block gets Executed immediately. It doesn't wait for the Player to press the 'OK' Button.

is_dialog_only: optional boolean setting that opens a text response only. NOTE: Dialog only Event Buttons still fire their effects, just without closing the event. Thus, the after = {} code block doesn't get executed. Requires response_text (without it, game gives error and exits event)

custom_gui: optional setting that changes the Event look with designated GUI. Can also be used inside event options to change the focused event option's gui with a custom gui.

custom_gui_option: optional setting that changes Every existing Event Button with a custom gui. Can NOT be used inside event option fields. Can be overwritten by custom_gui used in option's themselves.

## Best Practices

Unlike literally any other game file, which does LIOS, Stellaris loads /events with First In Only Serve basis, meaning in order to override a vanilla event without overriding the entire file, the filename for the event text file needs to be higher than vanilla files in UTF-8 order. This is usually achieved by attaching exclamation point(s) to the front of filename, like !!vanilla_override_event.txt

### Triggering

Hide Window and Triggered Only are the two most common settings for events, with the bulk of vanilla events having either or even both of them. The MTTH is also a very common setting on any event that is using polling to add some randomness to the game where it seems useful.

Due to a possible massive CPU load load regular polling should be avoided unless absolutely necessary. The preferred way to get a series of events started initially is either via a gatekeeper event that does use regular polling with early failing triggers, or by having it triggered by a on_action development. A combination of on_action developments that lead to gatekeeper events may also be useful.

### Chaining Events, Scope, Execution Order

The vanilla code often has long chains of events calling one another indicating that this chaining might be necessary for proper execution and scope setting.

In particular a pattern where there is a hidden Event is calling a visible event is extremely common. The hidden event often doing actually (setup) work. This indicates that even "Immediate" code needs a least until the next event is called to take effect past any internal caching.

### Example Events

Visible Events (Robot Rebellion, 1.6.2 version; actually removed):

```
 # Servant AI Perfected
 country_event = {
 	id = crisis.2192
 	title = crisis.2192.name
 	desc = crisis.2192.desc
 	picture = GFX_evt_robot_assembly_plant
 	show_sound = event_laboratory_sound
 	location = root
 	is_triggered_only = yes
 	immediate = {
 		set_country_flag = robots_pacified
 	}
 	option = {
 		name = crisis.2192.a
 		custom_tooltip = crisis.2192.a.tooltip
 		hidden_effect = {
 			set_country_flag = ai_perfect_servants
 		}
 	}
 	option = {
 		name = crisis.2192.b
 		hidden_effect = {
 			country_event = {
 				id = crisis.2000
 				days = 400
 				random = 400
 			}
 		}
 	}
 }
```

Invisible Events (test Prethoryn crisis – from version 1.8.3):

```
# WARNING: May cause galactic mass extinction and/or loss of appetite
country_event = {
	id = crisis.199				# Event ID
hide_window = yes			# Makes the event run without the player knowing, essential because this is a trigger event
 trigger = { always = no }		# Makes event only trigger when called on (I think)
 immediate = {
		set_global_flag = prethoryn_invasion_happened # Global Flags are created to tell the game that the crisis is happening
		set_global_flag = prethoryn_transmission
		begin_event_chain = {
			event_chain = "coming_storm_chain"
			target = ROOT
		}
		random_rim_system = {
			set_star_flag = swarm_invasion_target_1
			save_event_target_as = prethoryn_invasion_system
		}
		create_point_of_interest = {
			id = coming_storm_poi.1
			name = "coming_storm_poi_1_poi"
			desc = "coming_storm_poi_1_poi_desc"
			event_chain = "coming_storm_chain"
			location = event_target:prethoryn_invasion_system
		}
		country_event = { id = crisis.17 days = 10 }
	}
}
```

## Example event with all parameters

```
# Specifies the type of the event.
country_event = {
	# Unique ID for your event. Must match namespace parameter
id = example.1
 # Specifies localization string for the title (Header) of the event
title = example.1.name
 # Specifies localization string for event text that describes what’s happening.
# Multiple is allowed; random one will be shown.
desc = example.1.desc
	# Descriptions can be conditional
desc = {
		text = example.1.desc.conditional	# Localization string
trigger = {
			# Conditions for this to be available.
# For example: has_authory = auth_machine_intelligence
# Similar to custom_tooltip few sub commands can be used (also switch trigger)
text = example.1.desc.conditional	# Shows custom text
success_text = # Shows custom text when the associated trigger passes (multiple are possible and merged)
fail_text = # Shows custom text when the associated trigger not passes
		}
		# If valid, disables all other desc (added with 2.1).
exclusive_trigger = {
			# Condition statement(s)
		}
	}
 # A name of a picture to display. Pictures are defined at "interface/xxx.gfx".
picture = GFX_evt_exploding_ship
	# Pictures can also be conditional
picture = {
		picture = # The name of a picture
trigger = { # Condition statement(s) }
		exclusive_trigger = {
			# Condition statement(s) – if you have more than one
		}
	}
 # A scope to the object that is relevant to the event that player can move to. For example, the planet where event is happening.
location = from
 # Name of the sound clip to be played when event is shown. Sounds are defined in "sound/xxx.asset".
show_sound = event_ship_explosion
 # If event is not meant to be seen or there’s no person to see. Makes title and desc unnecessary.
# Service event that runs some sort of routine or prepares grounds for other events should have this.
hide_window = yes
 # Makes event look like diplomatic communications. First contact events use this.
diplomatic = yes
 # An optional setting that changes the looking of this event window, if "diplomatic = yes".
custom_gui = "enclave_caravaneer_window"
 # An optional setting that changes the looking of all used event option's buttons view, if "diplomatic = yes".
custom_gui_option = "enclave_caravaneer_option"
 # Specifies picture for diplomatic event. Most options are optional here
picture_event_data = {
		# Animated portrait. Accepts country, leader or species scope as an input
portrait = event_target:contact_empire
		# Planet background, if your picture has a window
planet_background = event_target:contact_empire
		# City graphic type on the planet in the window
graphical_culture = event_target:contact_empire
		# The size of the city. Usable to make planet behind look like capital
city_level = event_target:contact_empire
		# Static background. Can use static pictures or scopes as the input
room = event_target:contact_empire.ruler
	}
 # Probably removed in v.3.8: Event will show for other countries if this is set to yes. Those countries can be narrowed down with major_trigger.
major = yes
 auto_select = yes
 # Force a diplomatic event to be viewed.
force_open = yes
 # Forces the event to pop-up even if player has supressed pop-ups.
auto_opens = yes
 # Makes the event happen only once per game
fire_only_once = yes
 # enables the Auto-Track feature button at the top of the event (requires location)
trackable = yes
 # This event will not fire itself. It must be called by another event or an on_action.
# Most events will use this.
is_triggered_only = yes
 # The event be considered for starting with daily probability calculated so on average it would happen in time specified.
mean_time_to_happen = {
		# To specify average time for the event to fire. "months" or "days" are also acceptable input.
		years = 100
 # Mean time to happen can be conditionally modified
modifier = {
			# Multiply MTTH by number specify. Here it will make this event trigger in a mean time of 10 years.
			factor = 0.1
			# Condition statement(s)
		}
	}
 # If neither is_triggered_only or MTTH is set, the event will trigger every day the conditions are met.
# So don't forget them, lest you might affect the entire galaxy or see event trigger again and again forever.
 # Trigger block contains conditions. The event will not start if conditions inside aren't met.
# Used for events on mean_time_to_happen or for events that called from situation where
# you can't or want specify conditions for it to happen, before calling
# (For example an event in on_action block or a delayed event that might be blocked by other events)
trigger = {
		# Condition statement(s)
	}
 # Effects that are applied the moment event fires. Can be effects that can't wait like
# setting a flag to prevent other events, or the undesirable effects you don't want player to be able to delay
# (For example, killing science ship’s captain.) This is also the only block you'll need on hidden events
immediate = {
		# Effect statement(s)
	}
 # The button under the event, allowing player to pick a reaction.
# Any event that is not hidden, needs at least one. Multiple can be specified.
option = {
		# Reference to localization string with option text
name = example.1.a
# An optional setting that changes the looking of this event option window, if "diplomatic = yes" Overwrites the 'custom_gui_option' gui only on this option.
custom_gui = "enclave_curator_option"
# If not met, this option will be disabled and hidden.
trigger = {
			# Condition statement(s)
		}
 # If valid, disables all other event options (added with 2.0).
exclusive_trigger = {
			# Condition statement(s)
		}
 # If not met, this option will be disabled, but still shown.
allow = {
			# Condition statement(s)
		}
 # Effects of the event can be described here. They will generate tooltips shown when hovering over option.
 # This is a special Effect that it does nothing more than a customizable tooltip.
# Static strings can be used here, but using localisation keys is recommended.
custom_tooltip = example.1.a.tooltip
 # This is a special Effect that it makes the game to generate tooltips based on the Effects inside.
# These statements have NO actual effects, just tooltips.
tooltip = {
			# effect statement(s)
		}
 # This is a special Effect that it prevents the game from generating tooltips based on the Effects inside.
hidden_effect = {
			# effect statement(s)
		}
	}
 # Probably removed in v.3.8: Triggers for other countries on whether a major event should show for them. I.e. if it reads has_ethic = ethic_materialist, then all materialist countries will see the event.
major_trigger = {
		# Condition statement(s)
	}
# Event will cancel (disappear without executing any of the effects in the options) if these triggers return true. Not evaluated while the game is paused.
abort_trigger = {
		# Condition statement(s)
	}
	# Effects executed when abort_trigger returns true.
abort_effect = {
		# effect statement(s)
	}
 after = {
		# Effects that are applied after option is chosen.
# Will generate a tooltip in addition the tooltip of every option, unless hidden_effect is used.
	}
}
```

With v.3.4 there is a new “ event inheritance ” system added (e.g. it saved thousands of lines in the scripts for enclaves). With this, an event can be specified to inherit properties from another via “ base = <some_event_id> ”. Then, various properties can be overwritten via “ desc_clear ”, “ option_clear ”, “ picture_clear ” and “ show_sound_clear ”. Basically, this lets us inherit the behaviour of a given event while changing its flavour. Note: the base event must be defined before.

## Empty Event Box Bug

Sometimes the game fills the screen with empty event boxes. They have no title, no text, no picture and a single button that says "OK". New events like that pop up every day rendering game unplayable. Normally this happens in a modded game.

### What is happening?

This bug is caused by a corrupted event file being loaded into the game. When game encounters a pair of curly braces in the wrong places, or doesn't find curly braces where they should be, the file becomes corrupted. The events after the syntax error still exist, however their code gets essentially hollowed out – parameters such as title, description and whatever is supposed to keep the event from firing daily on every single object in the game are not read.

Usually this is a result of a mod that hasn't been updated to accommodate syntax changes between versions – either by modders themselves or new file simply haven't made it to your machine.

### How to deal with it

First you need to find out what events are causing it. By using debugtooltip console command and hovering over "OK" button, you can find out the event’s id. With luck, the modder who made this event would add some kind of identification to help you, such as adding an acronym of their mod’s name, or their own.

You would need then to investigate if the mod is up to date. If it is not, you'd have to disable it and wait. If the problem is on your local machine, you'd need to force a re-download of the mod files – starting with unsubscribing and subscribing again.

Note: There is also a (Python) tool on GitHub, which can easily fix outdated syntax of an entire mod folder for you (created by FirePrince).

# AI modding
Source: https://stellaris.paradoxwikis.com/AI_modding
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20240920225232 (the live wiki blocks non-browser clients). Page version banner: Version Please help with verifying or updating older sections of this article. At least some were last verified for version 3.0. This article is for the PC version of Stellaris only._

## Summary

Stellaris AI behaviour is determined by attitudes, behaviours and weights. Attitudes describe which actions an AI empire can pursue according to its current opinion level towards another empire, while behaviours describe the AI empire's behaviour in general. Weights are defined for most objects to help the AI determine what to do or build.

## AI attitudes

AI attitudes describe how an AI empire would react at certain opinion levels towards another empire, and what actions it may take. Attitude entries consist of a type and a list of allowed behaviours. The type of attitude is normally set to be the same as the name of the entry itself.

### Structure

Example:

```
   neutral = {
       type = neutral
       behaviour = {
           trade = yes
       }
   }
```

Any number of behaviours may be attached to the behaviour list on each attitude entry. If a behaviour is not listed inside the attitude's behaviour list, it will assume the value of 'no'. Available behaviours are listed in the table below.

| Behaviour name | Data type | Default value | ! Example | Description |
|---|---|---|---|---|
| trade | Boolean (yes/no) | no | trade = yes | An attitude with trade set to yes will permit an empire to be traded with. |
| weaken | Boolean (yes/no) | no | weaken = yes | An attitude with weaken set to yes will cause an empire to try and weaken another. This does not mean that they will fight. |
| attack | Boolean (yes/no) | no | attack = yes | An attitude with attack set to yes will cause an empire to actively attack another, provided that war goals can be achieved. |
| vassalize | Boolean (yes/no) | no | vassalize = yes | An attitude with vassalize set to yes will cause an empire to attempt vassalization on another. This does not necessarily involve war. |
| coexist | Boolean (yes/no) | no | coexist = yes | An attitude with coexist set to yes will cause the empire to be more accepting of non-aggression pacts. |
| alliance | Boolean (yes/no) | no | alliance = yes | An attitude with alliance set to yes will cause the empire to try and seek an alliance, or accept an alliance offer if it comes their way. |

### Warnings

Removing attitude entries from attitudes.txt can cause the game to crash to desktop. It is likely that these are accessed in a hard-coded manner by the game.

## AI personalities

Personalities describe how an AI empire will react to other empires around them. Each personality consists of a behaviour archetype which describes the empire's goal, a list of behaviours which describe the likely actions taken against other empires and pops, and several modifiers which alter other features which require numeric values as inputs.

### Personality archetypes

Personality archetypes describe the overall goal of the AI nation. If a personality archetype is not set, then the AI will pursue a balanced goal with no distinct focus.

| Personality name | Description |
|---|---|
| honorbound | Cares about honor and martial prowess above all else. |
| capitalist | Cares about trade and material profit above all else. |
| hegemon | Cares about the superiority of their own empire above all else. |
| ideologue | Cares about combating opposing ethics above all else. |
| isolationist | Cares about maintaining their isolation from other empires above all else. |
| federation builder | Cares about bringing different species together in a federation above all else. |
| propagator | Cares about the propagation of its species above all else. |
| purifier | Cares about purifying the galaxy of other species above all else. |
| explorer | Cares about exploring the galaxy and making scientific or spiritual discoveries above all else. |

### Behaviours

Behaviours determine the type of actions that an AI empire may take against other empires. These are set either to yes or no only; there is no current way to weight the AI's emphasis on certain aspects of their interactions. Currently, it is unknown what behaviour the AI will assume for each type of action if it remains unset. These behaviours are listed in the table below:

| Behaviour name | Description |
|---|---|
| conqueror | Will they conquer planets from other empires? |
| subjugator | Will they vassalise other empires? |
| liberator | Will they liberate conquered empires? |
| opportunist | Are they more likely to attack someone already embroiled in war? |
| uplifter | Will they uplift and enlighten other species? |
| infiltrator | Will they infiltrate primitives? |
| dominator | Will they invade primitives? |
| slaver | Will they enslave pops? |
| purger | Will they purge alien pops? |
| robot_exploiter | Will they use robots for menial labor? |
| robot_liberator | Will they give rights to robots? |
| propagator | Will they only get aggressive once boxed in? |
| multispecies | Will they give rights to aliens? |
| crisis_leader | Will they fight the crisis and invite others to do so (Fallen Empires special behviour. Emperor/Custodian will behave the same way regardless of this flag.) |
| crisis_fighter | Will they consider fighting the crisis? (If 'no' they will only care about themselves.) |
| holy_planets | special for spiritualist FE |
| isolationist | always keep borders closed |
| demands_clear_borders | used by xenophobe FE, AI will hate anyone who link up with their territory. |
| enigmatic | used by machine fallen empires.you never know what is this AI thinking,for example: our relationship. |

| Behaviour name | Description |
|---|---|
| custodian | special for awakened machine fallen empires, prevents colonization & locks attitude |
| berserker | used by awakened berserk machine fallen empires, prevents colonization & locks attitude |
| limited | prevents certain AI behaviours. I don't know what behaviours limited, anyone can decode the AI files ? |
| migrator | (NOT FOUND in 3.x, maybe not working)Will they want to migrate to other empires? |

Example:

```
   behaviour = {
       conqueror = no
       subjugator = no
       liberator = no
       opportunist = yes
       slaver = no
       uplifter = no
       purger = no
       dominator = no
       infiltrator = no
       robot_exploiter = yes
       robot_liberator = no
       migrator = no
   }
```

### Modifiers:

Modifiers affect specific aspects of interactions that an AI empire may take against other empires. Unlike behaviours, these are numeric and allow for fine-tuning of the AI personality. All modifier values are assumed to be floating-point numbers. These modifiers are listed in the table below:

| Modifier name | Description |
|---|---|
| aggressiveness | Chance of declaring wars. Multiplier; set this to 1.0 for default AI behaviour. Values between 0 and 1 will result in a less aggressive AI. Values greater than 1 will result in a more aggressive AI. Must be greater than or equal to zero. |
| trade_willingness | Willingness to pursue trade. At 0.0, trade will not be considered; at 1.0, trades will attempt to achieve a total value which is approximately equal for both sides. Greater values will weight the trade towards the other party. Must be greater than or equal to zero. |
| bravery | Affects the chance that they will pick rivals and war targets of similar strength, instead of picking on the weak. Values between 0 and 1 will result in an AI which prefers to target weakened enemies. Values greater than 1 will result in an AI that may declare war against an equal or stronger enemy. Must be greater than or equal to zero. |
| military_spending | Affects mineral and energy budget that goes to navies and armies. Values between 0 and 1 will result in an AI which spends less than normal on its military. Values greater than 1 will result in an AI that spends more than normal on its military. Must be greater than or equal to zero. |

| Modifier name | Description |
|---|---|
| colony_spending | Affects mineral and energy budget that goes to new colonies. Values between 0 and 1 will result in an AI which spends less than normal on colonising new worlds. Values greater than 1 will result in an AI that spends more than normal on colonising new worlds. Must be greater than or equal to zero. |
| threat_modifier | Affects the severity of opinion modifiers generated by wars near an AI nation, or against the AI nation. Values between 0 and 1 will result in an AI that doesn't care too much about threat. Values higher than 1 will cause threat to be generated faster than normal. |
| threat_others_modifier | Afffects how much threat is generated for other empires when this empire is conquered. |
| friction_modifier | Affects the severity of opinion modifiers generated by colonies or frontier outposts near an AI nation's borders. Values between 0 and 1 will result in an AI that cares less about contested borders and territorial pressure. Values higher than 1 will result in an AI that cares more about contested borders and territorial pressure. |
| claims_modifier | Affects opinion penalty from claims |
| federation_acceptance | Affects the likelihood of an AI accepting federation offers from other nations. Value is additive to the base reluctance values. |

| Modifier name | Description |
|---|---|
| nap_acceptance | Added directly to chance of accepting to form a non-aggression pact |
| commercial_pact_acceptance | Added directly to chance of accepting to form a commercial pact |
| research_agreement_acceptance | Added directly to chance of accepting to form a research agreement |
| migration_pact_acceptance | Added directly to chance of accepting to form a migration pact |
| defensive_pact_acceptance | Added directly to chance of accepting to form a defensive pact |
| alliance_acceptance | (NOT FOUND in 3.X,maybe been replace by other things)Affects the likelihood of an AI accepting alliance offers from other nations. Value is additive to the base reluctance values. |

Example:

```
   aggressiveness = 0.5
   trade_willingness = 0.5
   bravery = 0.75
   military_spending = 1.2
   colony_spending = 1.0
   alliance_acceptance = -50
   federation_acceptance = -50
   threat_modifier = 0.75
   friction_modifier = 2.0
```

### Requirements and weighting

Personality types for randomly-generated AI nations can be restricted by adding additional conditions. Standard conditions may be inserted to restrict personalities from being attached to certain empire types, or to weight personalities more heavily on others.

To allow a personality to be attached, every condition in the field 'allow' must evaluate to true.

Example:

```
   allow = {
        NOT { is_country_type = fallen_empire }         ## Does not permit this personality to be attached to a fallen empire.
        NOT { has_ethic = ethic_pacifist }              ## Does not permit this personality to be attached to a pacifist empire.
   }
```

Weighting is described in a similar manner. The field 'weight_modifier' must contain a numeric weight value greater than zero, and a list of weight modifiers containing a modifying factor and a list of conditions which must all evaluate to true for the modifying factor to apply.

Example:

```
   weight_modifier = {
       weight = 10	
       modifier = {
           factor = -2
           NOT = {
               has_ethic = "ethic_pacifist"
               has_ethic = "ethic_fanatic_pacifist"		
           }
       }
   }
```

### Examples

Below are examples of complete AI personalities taken from the base game files, with comments to illustrate the effects that each line has.

#### Honorbound warriors

```
    honorbound_warriors = {
	aggressiveness = 1.75
	trade_willingness = 0.7
	bravery = 1.5
	combat_bravery = 2.0	# rarely ever retreat in battle
	military_spending = 1.2
	colony_spending = 0.9
	federation_acceptance = -10
	nap_acceptance = -50
	defensive_pact_acceptance = 20
	migration_pact_acceptance = 0
	advanced_start_chance = 75
	weapon_preferences = weapon_type_strike_craft
	armor_ratio = 0.4
	shields_ratio = 0.4
	hull_ratio = 0.2
	threat_modifier = 0.75
	threat_others_modifier = 0.5
	friction_modifier = 1.0
	claims_modifier = 2.0
	behaviour = {
		conqueror = yes
		subjugator = yes
		liberator = no
		opportunist = no
		slaver = no
		caste_system = no
		uplifter = no
		purger = no
		displacer = no
		infiltrator = no
		dominator = yes
		robot_exploiter = no
		robot_liberator = no
		propagator = no
		multispecies = yes
		crisis_fighter = yes
	}
	allow = {
		is_country_type = default
		OR = {
			AND = {
				has_ethic = "ethic_fanatic_militarist"
				OR = {
					has_ethic = "ethic_spiritualist"
					has_ethic = "ethic_egalitarian"
					has_ethic = "ethic_xenophile"
				}			
			}
			AND = {
				has_ethic = "ethic_fanatic_xenophile"
				has_ethic = "ethic_militarist"
			}
		}
	}
	weight_modifier = {
		weight = 50
	}
 }
```

## AI Weights

As seen above, most objects or actions scripted into the game support an ai_weight = { } section to help the AI determine the best course of action. Most AI improvement mods change these AI weights so the AI will make different choices than they do in vanilla. Many modders will neglect to write these sections into their mods, leaving the AI unable to use the new content effectively. In general, the AI will choose what to do based on attitudes and behaviors, but will decide the specific one from AI weights.

For example, the AI will choose to develop a planet. They must decide which district or building it is going to build. It will evaluate all the ai_weight sections in each available building and district, modify these weights based on their attitudes and behaviors, then build whichever has the highest weight, with some variability and randomization built-in to reduce determinism. The more thorough and effective the ai_weight sections are written, the better the AI performs and makes intelligent decisions in game.

For example, if you mod in new traits that will affect the performance of a particular job, it won't be used effectively unless the job's weight section is updated to include a modifier = { factor = x has_trait = my_new_trait } for the new trait. Without this, a pop with a new trait that increases mineral output, for example, may end up as a farmer, while a pop with no bonus to mineral production works as a miner. Your new building may never be built by the AI!

The AI will only make good decisions if we give it the information to make good decisions.

### Modifying ai_weight

The main way to modify the ai_weight section is through use of a base weight flag and subsequent modifier blocks containing factor and add flags. The simplest way to start is with simply a single base weight, such as in the following example:

```
   ai_weight = {
       weight = 1.5
   }
```

In this example the entry that this is attached to would have a weight of 1.5. Depending on where exactly this is this weight can then be processed in a number of different ways, from highest value is chosen to a weighted randomized selection.

Now to make this example more complex we can add some modifier blocks to it, for example:

```
   ai_weight = {
       weight = 1.5
       modifier = {
           add = 1.5
           has_ethic = ethic_authoritarian
       }
       modifier = {
           factor = 2
           OR = {
               has_policy_flag = slavery_allowed
               has_ethic = ethic_fanatic_authoritarian
           }
       }
   }
```

In order to determine what a final weight is the game engine starts at the top of the ai_weight entry, retrieves the starting weight, and then checks each of the modifier blocks in order. So for example if an empire is an authoritarian with slavery enabled, then in the above example they begin with the starting weight of 1.5, add 1.5 to that for a weight of 3, and then multiply that value by a factor of 2 for a final value of 6. Be aware that stacking factors can lead to numbers quickly growing in size; a starting value of 5 that has a factor = 2 applied a half dozen times can reach all of the way up to a value of 5 x 2 ^ 6 = 320, with each successive doubling increasing by drastically more than the previous! Also be aware that there is no requirement for numbers to remain positive; both factor and add will accept negative numbers and multiply or add them as expected.

Like most other cases, multiple factors present in a single modifier block will default to an AND requirement, where all must be true in order to apply the factor. If an OR is desired then it will need to be added as in the example above.

This can, however, allow for us to command AI's to not perform a certain decision in certain cases. For example, consider the example below:

```
   ai_weight = {
       weight = 1.5
       modifier = {
           add = 1.5
           has_ethic = ethic_authoritarian
       }
       modifier = {
           factor = 2
           OR = {
               has_policy_flag = slavery_allowed
               has_ethic = ethic_fanatic_authoritarian
           }
       }
       modifier = {
           factor = 0
           has_ethic = ethic_fanatic_egalitarian
       }
   }
```

In this example we add a factor of 0 in the event that the AI is a fanatic egalitarian. Because 0 multiplied by any value is still 0, this means that an AI that meets that requirement will never perform the given action, no matter what other factors might apply. NOTE: Because modifier blocks are checked in order, if you multiply the weight by 0 and then later add to it is will result in a non-zero weight! Make sure that if you have any add modifiers in place that any 0 factors come after them in the code entries!

### Forbidding an AI from an action

A common use case that shows up in many mods is to prevent AI players from performing an action at all, limiting it only to human players. In that case one simply needs to add the following block to the action to prevent the AI from ever performing it:

```
   ai_weight = {
       weight = 0
   }
```

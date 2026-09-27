# Combat (Civilization VI)
Source: https://civilization.fandom.com/wiki/Combat_(Civ6)
License: CC BY-SA 3.0 (Civilization Wiki, Fandom: "Community content is available under CC-BY-SA unless otherwise noted.")

_Retrieved 2026-09-26 through the wiki's MediaWiki API (Combat (Civ6) rev 478617). Wiki prose may predate Gathering Storm balance changes; the generated records in ../data (the game's own files, 1.0.12.68) win where numbers differ._

This article will describe the intricacies of **combat** and combat-related activities in Civilization VI and its expansions. War and fighting has always been part of human civilization, and is integral to the game. Combat in Civilization VI follows most of the guidelines from Civilization V: Gods & Kings and Sid Meier's Civilization: Beyond Earth, but there are some important differences, which will be described at length below.

## Creating military units
Units are, of course, created in cities, either by producing them in the main Production queue, or by purchasing them with Gold or Faith (which is only possible under the Theocracy government, or in Rise and Fall with a Grand Master's Chapel built in your Government Plaza). The main difference from previous games is that not all cities may automatically produce all units anymore.

There are now Districts specialized in training/building specific classes of military units:

- Encampment - specialized in land units
- Harbor - specialized in naval units
- Aerodrome - specialized in air units

Air units may only be produced in cities with an Aerodrome. Naval units may be produced both in cities founded on coastal tiles, and in inland cities which have constructed a Harbor. Land units may be produced in all cities, unless they have a strategic resource requirement. In this case, and if you have only 1 count of the relevant resource, only cities with the relevant specialty district may produce them (so, cities with an Encampment for land units, and cities with a Harbor for naval units, regardless of whether or not they're founded on the Coast). If, however, you have access to 2 or more counts of the resource you may produce units in any city (for example, any city with or without an Encampment for land units, and cities on Coast with or without a Harbor for naval units). Again, air units may only be produced in a city with an Aerodrome, regardless of how many counts of strategic resources you have.

In Gathering Storm this distinction is not valid anymore - all land units may be produced in every city, and naval units may be produced in coastal cities or in those with a Harbor, if you have enough of the necessary strategic resource accumulated. Air units may still be produced only in cities with an Aerodrome.

Furthermore, buildings of the Encampment, Harbor and Aerodrome confer XP bonuses to units produced in their cities. This bonus allows them to accumulate XP faster and earn more Promotions.

## Combat statistics
The combat statistics system is largely unchanged from Civilization V: Gods & Kings. Each military unit possesses statistics which describe its strength in combat. This strength may be modified further by factors such as promotions, terrain bonuses or other special bonuses. There are several statistics important to combat:

- Damage Icon **Hit Points** - Each military unit has 100 hit points, or HP (sometimes called "Health" or "Health Points" instead). Each attack it suffers brings its HP down, with more powerful attacks causing a greater loss of HP. If a unit is reduced to 0 HP, it dies.
- Strength **Combat Strength (CS)** - This defines the general strength of the unit. For melee units this comprises both its offensive and defensive power; for ranged units it only comprises its defensive power (used only when it is attacked).
- Ranged Strength **Ranged Strength (RS)** - Only ranged types of units have this stat. It defines the unit's power when attacking from afar. Note that this power is significantly reduced when attacking City Defenses and naval units.
- Bombard Strength **Bombard Strength** - Only siege units have this stat. It defines the damage they do to Fortifications/City and District defenses. Units with Bombard Strength Bombard Strength do significantly reduced damage versus land units, but full damage to City Defenses and naval units. Note that a ranged unit has either Ranged Strength Ranged or Bombard Strength Bombard Strength; it cannot have both.
- Antiair Strength **Anti-Air Strength** - Only anti-air support units, GDRs, and certain naval units have this stat. It defines the damage they do to aircraft they intercept.
- **Range** - Again, only ranged and siege units, some recon units, and Immortals have this stat. It defines which tiles around the unit's position they may attack. For example, a Range of 1 means the unit may only attack the surrounding tiles; a Range of 3 means that the unit may attack all tiles up to three away from its position.
- **Movement** - This stat (sometimes called "Movement Points," or "MP" for short) is consumed when units are directed to move across terrains and perform actions. The default consumption is 1 point per tile on plains and water which may be modified by roads, hills, river crossing, enemy zones of control, etc. Units may only attack if they have enough Movement left to do so. Strategically, high Movement means greater defense coverage of territory holdings by fewer units.
- **Sight** - This denotes how many tiles around its position the unit is able to "see" (that is, remove the fog of war from). Units generally have a Sight of 2. Again, although not strictly a combat stat, this is very important, especially for ranged units.

### Combat modifiers
Units may use many modifiers in combat, according to the combat situation on the ground and the special abilities they have acquired. One big difference from older games is that all these bonuses confer direct increase or decrease to the unit's combat statistics, instead of a percentage increase. Thus, for example, a Flanking Bonus will increase the unit's CS by 4, and not by 10% anymore. This may not seem like a big change, but the odds of a battle hold in the strength difference and not in the strength ratio between the opponents like Civilization V.

The term "modifiers" is technically more accurate than "bonuses," because they may be both positive and negative. Modifiers of different types may stack, vastly increasing (or diminishing) a unit's final combat statistics, making it possible for two otherwise equal units (of the same type, era, and level) to have very different combat statistics.

Modifiers that defend against ranged attacks, such as those from the Tortoise Promotion, don't apply to Bombard Strength Bombard-type ranged attacks.

The combat modifiers are listed below.

#### Terrain
Various terrain types apply bonuses or penalties to defense. The unit which benefits or suffers is the unit currently occupying the tile. Mouse over any tile and you will see its modifiers listed in the popup info tab.

- "**Ideal terrain**" is a positive modifier that provides a +3 CS bonus. Terrains that are considered ideal are Hills (any type), Woods, and Rainforests. Note that the latter two may combine with Hills, and their bonuses stack for a total of +6. In Rise and Fall, Reefs provide a +3 Defensive CS bonus for units in the water.
- "**Unfavorable terrain**" is a negative modifier that provides a -2 CS penalty. Terrains considered unfavorable are Marshes and Floodplains (but not Oases).
- "**River defense**" is a positive modifier that applies when the attacker and defender are on opposite banks of a River. When targeted by a melee attack, the defender receives a +5 CS bonus.
- "**Amphibious attack**" is a negative modifier that applies to any attack made by an embarked unit against a unit or district on land that is unobstructed by Cliffs. This is the most complicated type of attack and carries a -10 CS penalty.

A unit with the Amphibious Promotion negates the defender's river defense bonus and doesn't suffer the amphibious attack penalty when it attacks.

#### Flanking and Support

These bonuses depend on the grouping and position of units on the field.

#### Fortification
When a land unit assumes and maintains a defensible position, it receives a fortification bonus. A defending unit receives a +3 Strength Combat Strength bonus if it hasn't used any Movement or performed other actions in the last turn, or a +6 Strength Combat Strength bonus if it hasn't used any Movement or performed other actions for two or more turns. Forts and Fort-like improvements instantly grant units on them 2 turns of fortification, even if they just entered the tile.

A land unit can also be commanded to **Fortify until Healed**, which will have it Fortify until its HP have fully recovered. The unit will automatically wake when it reaches full HP, but it can also be manually woken at any time and given new commands.

The "Alert" command also allows a unit to receive a fortification bonus and can be given even if the unit has moved this turn, as long as no enemy units have line of sight to it. Due to a bug, a unit that is given the "Fortify" or "Alert" command twice will immediately receive 2 turns of fortification (i.e., a +6 Strength Combat Strength bonus).

#### Unit class modifiers
Some unit classes receive modifiers when in combat with specific targets:

- **Melee units** receive a +5 CS bonus against anti-cavalry units.
- **Anti-cavalry units** receive a +10 CS bonus against light cavalry, heavy cavalry, or ranged cavalry units.

#### Ranged attack type
- Ranged Strength **Ranged attacks** receive a -17 penalty when attacking city and district defenses or naval units.
- Bombard Strength **Bombard attacks** receive a -17 penalty when attacking land units.

#### Intel on enemy movements
If your intelligence apparatus is superior to your enemy's (that is, your level of Diplomatic Visibility on them is greater than theirs on you), then you gain a +3 bonus for each level of difference, because you have advance warning on their armies' whereabouts and intentions. Mongolia gains +6 for each level of difference. Of course, the reverse situation is also possible.

#### Promotions

All military units may gain promotions by acquiring experience. The promotion system is different from Civilization V: Brave New World, and more akin to Civilization: Beyond Earth. Each unit class has separate promotion choices - there are no cross-class promotions anymore. Furthermore, each unit class has two separate paths towards a single, top-tier promotion, such as the ability to attack twice in a round.

Note that, unlike in Civilization V, units battling Barbarians will still earn XP after reaching Level 1. However, since the battle tactics of the uncouth louts/rebel scum are always the same (unlike those of civilized combatants), all combat encounters after Level 1 will grant only 1 XP regardless of circumstances.

There are many Promotions granting units extra Strength Combat Strength against Districts, when occupying a District, against certain lines of units, etc.

#### Lost HP
Units that have lost HP suffer a penalty to their Strength Combat Strength. The lower the unit's HP, the greater the penalty becomes. The penalty is round(10-\frac{HP}{10}) either attacking or defending. The maximum lost HP penalty is 10-\frac{1}{10} = 9.9, rounding to 10, which means a unit with 1 HP will have 10 less Strength Combat Strength than normal.

The only units that never suffer from this are the Samurai, and Nihang with the Sanjo Promotion. Certain policy cards can reduce or eliminate this penalty for your entire civilization.

#### Strategic resource shortage
In Gathering Storm, certain late-game units require per turn resource maintenance. When your reserve is not enough to pay the maintenance of all units, they will all suffer a combat penalty - we can infer that they won't have enough fuel and power to maneuver normally and use all their weapon systems! The penalty is calculated as follows: -1 * (the number of units that spend the turn without maintenance), up to a maximum of -20. However, the defensive Anti-Air strength ​​is not reduced.

For example, suppose you have 5 Oil left in your reserve and have 5 Infantry and 5 Artillery. Since 5 units will then spend their turn without maintenance, all 10 units will suffer a -5 Strength Combat Strength penalty. Next turn when your reserve hits 0, all 10 units will receive a -10 Strength Combat Strength penalty.

#### Miscellaneous
These are bonuses only applicable in special circumstances, such as from policy cards, religious beliefs, World Congress resolutions, or civilization-specific bonuses. Note, for example, that the difficulty level of the game applies a permanent bonus or penalty to enemy military units.

## Engaging in combat
In order for your units to engage in combat with another entity in the game, they must be at war with it. You may force an attack on another civilization's or city-state's units, and this will be considered an act of war, automatically declaring war on this entity. However, this is highly inadvisable, because the type of war declared in such circumstances is the worst possible (Surprise War), and grants the most severe warmonger penalty. So, you should first consider the formal diplomatic options for declaring war before actually engaging in combat.

Note that you are considered at War with Barbarians at all times. The same is true for Rebels within your borders, and for units belonging to Free Cities in Rise and Fall.

### Declaration and types of war

At first glance, declaring war is simple: you just need to enter the Diplomatic screen of the target leader, and press a button. A confirmation screen will appear, and then guns will start firing. Note that unlike previous games, Trade Routes with this civilization won't get automatically plundered; instead, they will get cancelled and your Traders will be ready for reassignment in the beginning of the next turn.

However, you can't declare war if you're Declared Friends or Allies with this civilization. Furthermore, you will have to carefully consider what type of war you want to declare. Civilization VI introduces a sophisticated system of diplomatic options for declaring a war. As the designers say, "with the passing of time, war becomes less and less the normal state of the world." Leaders become more conscious of aggressors, and are more willing to condemn unjust wars. In terms of the game, this means two things:

1. With the passing of eras, declaring a Formal or Surprise War brings higher and higher diplomatic repercussions (i.e., warmonger penalties, or Grievances in Gathering Storm). For example, declaring such a war in the Ancient Era brings no penalties at all, while in the Modern Era it brings egregious penalties. Note that in Rise and Fall, the penalties increase with passing of individual eras and not the World Era. Warmonger penalties will apply a direct negative result to your relations with a leader.
1. With civic development, more and more types of war declarations (Casus Belli) are unlocked. These can now be used in some situations to declare types of war which will be more or less justified in the eyes of other civilizations and bring lessened penalties - or in some cases, none at all. For example, declaring a war to liberate a city you've lost to the rival civilization will bring no penalties. What's more, some leaders gain special bonuses upon declaring certain types of wars.

Unlike in Civilization V, entering a city-state's territory is now forbidden unless you are their Suzerain, haven't discovered Early Empire yet, have slotted Gunboat Diplomacy, or are playing as João III.

### Attacking a unit
After hostilities have been opened, your units may engage the enemy. In order to attack an enemy unit, your unit(s) must be in range of the target. For melee units, that means they must be in a nearby tile and have the means to move to the target's tile; furthermore, the attacker unit must have enough Movement left to be able to enter the target's tile. This is also the major difference from the previous battle system, where a melee unit was able to attack the target regardless of where its so long as it had even a fraction of a Movement point left. According to the new rules, an attacker needs to have at least so many points left as it normally takes to move onto the target's tile. This is not the case with ranged attackers, who can attack even having a fraction of a MP left - under the new rules this is a significant strategic advantage.

A ranged attack must both be within the number of hexes the attacker's Range dictates and obey line-of-sight rules - in other words, there can't be any obstacles in a straight line between the attacker's position and the target. Obstacles comprise terrain features, such as Woods, Rainforests, Hills, and Mountains. If the attacker is on higher ground (i.e., a Hill), it is able to ignore all obstacles on lower ground, including other Hills. Mountains and Hills with Woods or Rainforests on them are insurmountable obstacles, even for units on higher ground, since they add an additional "level" of obstacle which effectively eliminates the advantage of higher ground. However, units can always make ranged attacks against adjacent tiles, and units with a Range of 3 or more can lob their shots over obstacles to attack any target that they or another friendly unit can see.

Selecting a military unit and right-clicking on an enemy unit will command the selected unit to attack the target. If the selected unit is capable of making both melee and ranged attacks (like an Immortal or a Giant Death Robot), this will command the unit to use its stronger form of attack.

Siege units (Catapults, Bombards, etc.) cannot attack in the same turn they move, even if they're in range of the target, unless they have acquired the Expert Crew promotion or a Movement bonus (Great General, Supply Convoy, etc.).

A unit may take shelter (that is, avoid being attacked) if it enters a City Center or Encampment tile. There it is invulnerable as long as the city/Encampment stands; however, when an enemy destroys/takes the city/Encampment, the unit inside will be destroyed instantly, regardless of its remaining HP. Civilian and support units which are in the same tile with a military unit are also safe from attacks, as long as the military unit lives.

### Damage
When a currently selected unit is able to attack an enemy, a red target cross will appear over the enemy's tile. When an attack occurs, the Strength Combat Strength of the attacker is compared to the CS of the defender, or if the attacker is a ranged unit, its Ranged Strength Ranged or Bombard Strength Bombard Strength (as applicable) is compared to the target's CS. All bonuses or penalties are taken into account, and the final difference between the two strengths determines what damage the target will suffer to its HP. Starting from a "default" damage, if the difference is zero (that is, the attacker's strength equals the defender's), the attacker will deal progressively more damage for each point of positive difference, and the opposite for negative difference, down to a minimum of 1 (verification needed).

Note that if the attacker is a melee unit, it will also suffer damage in retaliation to its attack. Ranged attacks don't incur retaliation.

An Attack dialogue will appear always when you mouse over an enemy unit while commanding a military unit. This dialogue shows your unit to the right, and the enemy unit to the left; both have a list of items which modify their Strength Combat Strength and project the HP loss from the attack. Use this to determine the possible outcome of the attack, and judge whether you should attack indeed, or not! In the absence of a comprehensive list of combat bonuses, the Attack dialogue is also your all-important source of information about those.

#### Damage formula
Currently, the damage formula, according to players' research, is the following exponential equation:

Damage (HP) = 30 * e^{0.04*StrengthDifference} * randomBetween(80\%, 120\%)

Where:

- **e** is Euler's number, a mathematical constant approximately equal to **2.71828**.
- **StrengthDifference** is a result of subtraction of defending unit's strength (always Strength Combat Strength) from attacking unit's strength (either Strength Combat Strength, Ranged Strength Ranged, Bombard Strength Bombard Strength, or Antiair Strength Anti-Air Strength).
- **randomBetween** is a random multiplier between given arguments, including both ends.
An interactable damage calculator is located here.

There are a few things to note about damage calculation:

- Every strength point multiplies your damage dealt (and divides damage received) by roughly 1.041.
- For units of equal total strength the expected damage dealt to each is 30 HP, reliably falling between 24 and 36.
- Only strength difference matters, which means that combat buffs don't diminish in effectiveness and are equally useful in later eras (e.g., a battle between units with 30 Strength Combat Strength and 20 Strength Combat Strength will play out exactly the same as one between units with 110 Strength Combat Strength and 100 Strength Combat Strength, which makes the +4 Strength Combat Strength bonus from Wars of Religion equally effective in both situations even despite the proportional difference).
- For smaller strength differences (up to about +20), the expected difference in damage between two units is approximately linear at 2.5x the strength difference (e.g., a battle between units with 30 Strength Combat Strength and 20 Strength Combat Strength will be expected to have a difference of 2.5 * 10 = 25 HP; the damage midpoint is always skewed higher than 30, so in this case the units deal 45 and 20 damage respectively). This is a usual rule of thumb for in-game calculations.
- A strength difference of 26-35 may result in a one-hit-kill, and a difference of 36+ guarantees a one-hit-kill.
- Theological combat and city combat damage calculation work the same way as normal combat.
- Damage of wounded units is diminished up to a half of the original strength. The formula is round(10-\frac{HP}{10}), where HP is the current HP of the unit, which means that units with 30 HP will lose 7 Strength Combat Strength and units with 1 HP will lose 10 Strength Combat Strength.
- When a unit's Strength Combat Strength is reduced to 0 (through the Varu's and Toa's debuffs, amphibious penalty, terrain penalty, etc.), it is a guaranteed one-hit-kill if it attacks or is attacked, regardless of the opponent's Strength Combat Strength.

### Melee and ranged attack locations
As before, all battles happen in the tile of the defending unit, not the attacking unit. This is very important when calculating terrain bonuses/penalties, and in certain other situations. Melee units have to physically be able to move into the attacked tile, so if the defending unit is beyond a border the attacker cannot pass, there can be no attack at all! If the attack destroys the defending unit, the attacker will advance into the tile of the battle; in the opposite case (the attacker is destroyed), the defender will stay where it is, and the attacker will simply disappear.

Ranged attacks may happen regardless of borders. In the event that the attack destroys the defender, it will simply disappear, and the attacker won't move.

### Zone of control

### Attacking embarked units
Embarked units may not attack any other unit in the water, including other embarked units. Embarked units with melee attacks may attack targets on land when adjacent to it, but they will suffer the amphibious attack CS penalty (unless they're of the melee class and have earned the Amphibious Promotion, as mentioned above). On the other hand, land melee units in tiles adjacent to embarked units may also attack, and will do so at full strength.

All embarked units have Strength Combat Strength which is normalized for all unit classes (since it is accepted that all units use the same type of transport ship). This Strength Combat Strength is used when embarked units are defending, depends on the owner's current technological era (not the World Era), and is updated upon discovery of the first technology or civic of that era. Corps and Armies also have +10/+17 Strength Combat Strength when embarked. When embarked units attack, they use their original Strength Combat Strength.

- Classical and Medieval: 15 Strength Combat Strength
- Renaissance: 30 Strength Combat Strength
- Industrial: 35 Strength Combat Strength
- Modern: 50 Strength Combat Strength
- Atomic onward: 55 Strength Combat Strength

Note that there are two exceptions: Nihang keep their unique Strength Combat Strength bonus from Barracks, Armories, and Military Academies being constructed when embarked, and embarked Heroes have the same Strength Combat Strength they do on land, which makes them tougher than other embarked units.

While it may be said that "transport ships" have decent defense, the inability to attack or retaliate against attacks makes them easy pickings for enemy ships. If you want to avoid unpleasant surprises, you should always provide an embarked army with a good maritime escort. More than one overseas invasion has failed due to the lack of adequate maritime support!

When a naval unit and an embarked unit occupy the same hex, the unit with the higher Strength Combat Strength will defend against ranged attacks. An unfortunate quirk of this design is that strong but gravely injured embarked units can be prioritized over weak but healthy naval units (e.g., embarked units in the Modern Era cannot be protected by Frigates, Privateers, or other ships with less than 50 Strength Combat Strength).

### Attacking stacked units and Priority Targeting
As mentioned elsewhere, in Civilization VI units of different types may form Escort formations by stacking in the same tile. This ensures defenseless units (such as civilian or support units) will be defended by military units while moving in hostile areas of the map. All attacks against this tile will be absorbed by the military unit of the formation, and only after its death will the enemy be able to destroy the other defenseless units.

Some units of the Modern Era and beyond, however, have the special ability to attack support units directly - this is called **Priority Targeting**. It becomes active only when the unit is in range of a valid enemy formation, and permits a direct attack against the support unit, which will harm it while leaving the military unit unharmed. Note that you cannot instantly destroy a support unit this way, as you can by entering its tile while it is undefended. Use this option to destroy strategically important units, such as Drones or Supply Convoys.

### Healing
A unit which hasn't performed any action for at least one turn starts to recover lost HP. Note that Healing won't happen if a unit has used its MPs for this turn, even partially. Also, unlike Civilization V, the unit regains HP only when all other players finish their turns, and not at the end of your own turn. This difference is very important, because it means that in the first round after starting to Heal, the unit will still have only its old HP, and will be more vulnerable.

The base Healing rate is as follows:

- Normal rate** - 10 HP/turn. This applies to all neutral territory.
- Friendly territory rate** - 15 HP/turn. "Friendly territory" comprises your own territory, and the territory of Allied civilizations and city-states of which you're the Suzerain. It does not include civilizations with which you have Open Borders.
- District/Improvement healing rate** - 20 HP/turn. The district or improvement must be within the "friendly territory" outlined above.
- Enemy/rival territory rate** - 5 HP/turn. This includes the territory of civilizations with which you have Open Borders.

Note that naval and embarked units may Heal only in Friendly territory unless they acquire certain promotions, are a Norwegian naval melee unit, or are adjacent to Abu Al-Qasim Al-Zahwari, a Medic, a Chaplain-promoted Apostle, or a Supply Convoy.

The Medic support unit increases Healing rate by 20 HP for all units on and around its tile. It becomes incredibly useful for assaulting armies, since their Healing rate in enemy territory is greatly diminished. An Apostle with the Chaplain promotion and the Medieval Era Great Scientist Abu Al-Qasim Al-Zahrawi also provides the same Healing bonus, granting a pre-Industrial Era, maintenance-free Medic. Expending the Great Scientist lets all units receive a permanent Healing bonus of +5 HP/turn. Mamluks and Māori units in a Pā will heal +10 HP/turn.

### Capturing units
In Civilization VI some civilian units may be captured by other civilizations and then forced to serve their interests. In order to capture a unit, you need to move your own military unit into the tile currently occupied by the target civilian - it will then switch colors and become yours. You cannot capture civilians with civilian, support, or religious units - only military units command enough respect (and fear) to force the enemy into submission! Note also that embarked military units cannot capture - only naval units may capture on water tiles. If you haven't unlocked embarkation technology, such as Cartography, embarked civilians will be destroyed instead of being captured.

Both Settlers and Builders can get captured, and are among the best targets for raids. Use cavalry-type units to sweep into enemy territory, grab their civilians, then defend until the captives move away! Note that captured Builders will have the same abilities as your own - that is, you won't get access to exotic foreign tile improvements, or to those unlocked by technologies you haven't researched yet.

Note that religious units, Archaeologists, Naturalists, and Great People cannot get captured - the first can move freely through tiles occupied by non-religious units (more on that below), while the latter three retreat to the nearest friendly city. Trader units are also immune to being captured; however, their Trade Routes may get plundered, which destroys the unit itself.

### Condemning heretics
The Fall 2017 Update introduces a new way for military units to attack religious units: the Condemn Heretic action. It is no longer possible for military units to attack religious units directly - the latter are now on their own independent layer, which for purposes of normal combat amounts to them being in a different universe altogether. In practical terms this means that both types of units may share the same tile, enter and exit it without anything happening. However, military units now may use the special "Condemn Heretic" action whenever they're in the same tile as an enemy religious unit to destroy it instantly. The action can be performed only if the military unit has Movement remaining, and ends that unit's turn. In any nearby cities, Religious Pressure for the religion of the condemned unit will drop by 1/2 of the usual amount. Note, however, that there won't be a corresponding rise in Religious Pressure for the military unit's Religion (assuming their civ follows one). Also note that this action may only be undertaken against units from a civilization with which you're at war.

## Strategic breakdown of units
All military units from the different eras in Civilization VI belong to a certain class, which is most easily visible from the promotions they have access to. Each one of them has a different use and purpose.

### Land units

#### Infantry land units
As their name suggests, these are the infantry units in the front of your lines. They are good at soaking up damage, and protecting more vulnerable units in the army. Note that sometimes both units below are described in-game as "melee", for example for the purposes of the training bonus from Agoge and its later replacements.

- **Land Melee** - Strong frontline melee units that fight in close combat. They can soak up lots of damage, and are extremely effective against anti-cavalry units. They acquire Promotions that allow them to ignore some terrain penalties when attacking, and even move faster. They are also one of the classes that can attack twice per turn after acquiring their ultimate Promotion.
- **Land Anti-Cavalry** - Defensive melee units designed to counter cavalry units (or tanks in later Eras). They are extremely good at defending against almost anything (even Melee units, after they acquire Promotions), and like fighting in close formation with other units.

#### Cavalry land units
These are highly mobile mounted units, designed to outrun enemies, flank the enemy formations and exploit vulnerabilities in their lines. All of them have lots of MPs and are able to ignore zone of control, which allows them to move freely around enemy armies.

- **Land Light Cavalry** - Swift mounted skirmishers that use hit-and-run attacks. After acquiring Promotions, light cavalry may attack enemy ranged units with exceptional efficiency. They can also become very good at Pillaging and Escorting units (allowing these to move as fast as the cavalry unit itself), which may be incredibly useful when settling or moving Builders to faraway cities.
- **Land Heavy Cavalry** - Powerful mounted frontline melee units that hit hard and can soak up lots of damage. They are the second class which can learn to attack twice in a round, and are able to move after attacking. Chariot-type heavy cavalry (i.e., the War-Cart, Heavy Chariot, Tank, and Modern Armor) receive a +1 Movement bonus when starting their turn on flat terrain with no Woods or Rainforests. Heavy cavalry units with the right promotions become city-killers, able to swoop in the right moment and deliver enough melee damage to conquer the city.

#### Artillery land units
These units deal damage from a distance without suffering any in retaliation. They are, however, more vulnerable in close combat, so make sure to protect them with melee units. Note that any shooting unit is unable to capture cities! They can still capture or destroy enemy civilians, though, as well as activate Tribal Villages and disperse Barbarian Outposts.

- **Land Recon** - Swift skirmishers that use hit-and-run attacks. They explore quickly and efficiently, but are not particularly strong in combat. They receive XP not only from combat, as is usual, but also from activating Tribal Villages and discovering natural wonders. Recon Promotions allow them to traverse difficult terrain more easily, and even become invisible and launch ambushes. A high-level recon unit with the right promotions may actually stand up to any military unit of the same era.
- **Land Ranged** - Units that specialize at dealing damage, mostly to other units (they suffer a -17 RS penalty when attacking cities and naval units). With promotions, they may become especially deadly against land units, or when occupying a District. Even with promotions, however, they aren't especially effective against cities. They are the last class that can learn to attack twice.
- **Land Siege** - Units meant for taking down cities, districts, and naval units, not land units (they suffer a RS penalty when attacking land units). With promotions, these units may overcome their ineffectiveness against land units, and become as deadly as ranged units. Their main strength, however, is destroying cities' defenses. They are the only land unit which may develop long range, and shoot cities from outside their defensive perimeter.

### Naval units
Naval units move on water tiles only, or they may get stationed in coastal cities. Note that until you research Cartography naval units may only move onto Coast tiles.

- **Naval Melee** - Swift ships specialists at naval combat and patrolling. They are also good when moving in formation, and against Raider type units. Naval melee units are capable of capturing coastal cities. From the Caravel on, naval melee units develop a Sight of 3.
- **Naval Ranged** - Ships designed to bombard from sea. With Promotions, they may specialize against land units, other naval units, or cities (or against all of them, of course!). Ranged units can develop exceptionally long range, so as to be able to shoot cities from outside their defensive perimeter. Naval ranged units do not suffer the -17 RS penalty against cities (but still suffer against Walls, just like other ranged units), making them the unit of choice for naval sieges.
- **Naval Raider** - Ships designed to be invisible, to ambush the enemy, and to pillage coastlines. They may attack both naval and land units, but are much more effective against the first. Raider ships stay naturally invisible, even without Promotions, which makes them very good at sneaking into enemy territory, then wreaking havoc on their coastline by Pillaging. What's more, they are the only ship class which is able to ignore ZOC, which makes them able to easily achieve the best position for launching devastating attacks against any unit in any formation. They are also the only naval class that can learn to attack twice. The most advanced naval raider unit, the Nuclear Submarine, is capable of launching nukes! Naval raider units do not suffer the -17 RS penalty against cities (but still suffer against Walls, just like other ranged units).
- **Naval Carrier** - Comprised of only one ship, the Aircraft Carrier. Each Carrier is able to serve as a base to aircraft, which makes it invaluable for invasions to other continents.

### Air units
Airplanes move through the air, flying above all obstacles on land or sea, and attacking targets on the ground at will. Unfortunately, they are locked to their bases, which severely limits their freedom of movement. On the other hand, air units are able to attack all land units without retaliation (except for the Giant Death Robot in Gathering Storm). However, later naval units (i.e., the Minas Geraes, Battleship, Destroyer, and Missile Cruiser) possess anti-air weapons and can damage attacking aircraft, while land units may enjoy the defense of the Anti-Air Gun and the Mobile SAM, which are quite lethal against attacking aircraft.

- **Air Fighter** - Aerial units to attack other aerial units, or land units. They are also capable of defending against air units by staying on Patrol and executing Interceptions. Their range is generally smaller than Bombers, but they end up being more versatile thanks to deployment capabilities.
- **Air Bomber** - Aerial units specialized at attacking land-based targets. They are naturally good at attacking city defenses thanks to their Bombard Strength Bombard-type damage, but can earn promotions that make them stronger against both land and naval units. Bombers may also Pillage and deliver nukes.

### Nuclear weapons

As in any Civilization game, we have nukes! Their rules are much different than Civilization V, though. Nukes are now called "nuclear devices" and are stored in a secured, undisclosed location after their production. They are launched automatically by all nuclear-capable units and buildings, whenever you decide. So, no more moving bombs and missiles around the map! In fact, the actual delivery form which the device will take is created on-the-fly, according to where you will launch the nuclear strike from.

There are only two types of nukes: the Nuclear Device, with a Range of 12 and area-of-effect of 1 hex; and the more powerful Thermonuclear Device, with a Range of 15 and AOE of 2 hexes.

## Pillaging
Pillaging is back with a new twist in Civilization VI, thanks to the new district system. Military units may now pillage not only tile improvements, but also districts, with different results. Pillaging now takes 3 Movement, or a full action for units with 3 or less Movement (under normal circumstances); note, however, that this action doesn't terminate a unit's turn - if it has more Movement left after the pillaging, the unit may take other actions. That means that from the land units, only cavalry may pillage and continue moving afterwards - indeed, light cavalry units are specialist pillagers and may acquire the Depredation Promotion, which allows them to pillage with 1 Movement. Ships are also good pillagers because of their high Movement, especially after technological developments.

### Pillaging improvements and districts
This action can be done when a military unit moves onto a tile with an improvement or district. The spoils of pillaging vary, depending on the type of thing pillaged - for example, pillaging a Campus will yield Science. Note that pillaging doesn't heal the unit automatically anymore, and is instead a function of a specific loot type - that is, the unit will get Healed for 50 HP only if it pillages a specific improvement or district, such as a Farm or an Entertainment Complex.

Note that pillaging a district will damage one building within this district per Pillage action, starting with the most advanced one. When all available buildings have been damaged, the district itself will be pillaged, disabling it. This means that by default, one unit can pillage a single tile multiple times.

The Encampment and Oppidum cannot be pillaged normally - they have to be "conquered" by a melee unit, as you would a City Center. At this point the entire district and all buildings in it are automatically pillaged, but you don't gain any spoils from it. The Oppidum can still be pillaged by the Sabotage Production espionage mission.

The values of spoils of pillaging are fixed in vanilla Civilization VI and Rise and Fall. In Gathering Storm, however, all spoils except Healing scale up with the passing of time. Thus, pillaging will preserve its strategic uses even into modern times, allowing the attacking civilization to boost its development significantly by preying on others. Note also that since the Antarctic Late Summer Update pillaging improvements will not provide Science and Culture yields anymore, just Gold, Faith, and Healing. Science and Culture are still available from pillaging Districts, though. Refer to the individual lists for info on what district/improvement provides what type of loot. With a Grand Master's Chapel, pillaging improvements and districts provides extra Faith as spoils.

### Plundering Trade Routes
Trade Routes of enemies may also be pillaged. This action is commonly known as "plundering" and requires less MP than pillaging tile improvements or districts, but yields a large sum of Gold. However, simply placing a military unit in any tile of the route's trajectory is not enough anymore - you must move a military unit into the tile the Trader unit is currently in to plunder its route. Plundering a Trade Route also ends the unit's turn.

### Pillaging Barbarian Outposts
Unoccupied Barbarian Outposts can be pillaged by moving a land unit over their tile (except when the Barbarian Clans game mode is enabled, in which case the unit must then be ordered to Disperse the outpost). Pillaging a Barbarian Outpost removes the outpost and yields 50 Gold (depending on the difficulty level). This yield does not scale through research and era progression (except when playing as Julius Caesar) and is unaffected by policy cards.

### Pillaging Roads
All land military units can pillage roads on their tile (be it in friendly territory, neutral, or enemy territory), which removes the road and gives no spoils.

### Coastal Raid
This is a unique action performed by naval raider class units, such as the Privateer. It is basically a Pillage action performed by a naval unit on an adjacent land tile. The result of a Coastal Raid is the same as a Pillage action, with the nifty difference that the pillaging ship is invulnerable to anything but ranged retaliatory strikes. In this way, strong maritime civilizations can wage wars of attrition against their enemies by wrecking their economy rather than engaging them directly. Coastal Raids can also be used to activate Tribal Villages or disperse Barbarian Outposts.

Norway under Harald Hardrada is a civ specifically adept at Coastal Raids: all their naval melee units may perform this action in addition to their naval raider units. What's more, they can earn Science and Culture by raiding certain improvements, and even capture civilian units which happen to be in a vulnerable tile.

## Strategy
Pillaging is notable for being a relatively safe way to badly damage opponents' (and especially AI opponents') economies. It ostensibly earns zero Grievances, so it avoids giving your opponents political ammunition to use against you and denies diplomacy-focused civilizations the opportunity to earn extra points.

Build up a force of light cavalry and naval raider units, and always prioritize the Depredation Promotion for your cavalry. Next, target the civs that are in the lead in technologies and civics and find ways to declare war without earning too many Grievances. This is very easy from the Industrial Era onward if you can manage to snag the To Arms! dedication, allowing you to declare war often and quickly without causing too much fuss. It's also great against civilizations who have previously conquered cities from other civs; simply ally yourself with the victim in that exchange and then denounce their rival, eventually leading to a Liberation War.

Move your raiding units into enemy territory and pillage any high-value targets: Theater Squares, Campuses, Industrial Zones, and improved luxury resources. Don't forget to chase down and capture any vulnerable Builders. Be careful to always strike and then move your units out of danger as they can be quickly destroyed by interlocking fields of fire from cities and Encampments, even if the enemy's units cannot pin them down. Your naval raiders are fairly safe, as long as they avoid ending their turn while revealed to the enemy. Take advantage of enemy Farms and Entertainment Complexes, as your raiders can quickly recover 50% of their HP by pillaging them and go back to taking out higher priority targets.

Unless your opponent is very well-fortified indeed, this can easily lead to a massive problem, with falling Amenities, falling Science and Culture output, Housing crises and an enormous amount of work for their Builders for dozens of turns to come, as well as many turns spent repairing their districts and buildings. If their position was precarious enough (i.e., very large cities and not many surplus Amenities), it could actually lead to revolts and cities being lost to Loyalty pressure. Pillaging has the potential to cause far worse problems than spending many turns to conquer one or two cities and earns far fewer Grievances, meaning other civilizations will care little - in relative terms - for your warmongering.

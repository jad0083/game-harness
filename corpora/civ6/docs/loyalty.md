# Loyalty (Civilization VI)
Source: https://civilization.fandom.com/wiki/Loyalty_(Civ6)
License: CC BY-SA 3.0 (Civilization Wiki, Fandom: "Community content is available under CC-BY-SA unless otherwise noted.")

_Retrieved 2026-09-26 through the wiki's MediaWiki API (Loyalty (Civ6) rev 482684). Wiki prose may predate Gathering Storm balance changes; the generated records in ../data (the game's own files, 1.0.12.68) win where numbers differ._

- Loyalty** is a game mechanic added to Civilization VI in the Rise and Fall expansion pack. It represents the political alignment of a city and how much political control its current owner has over it. Loyalty introduces a new way in the game to change city ownership (along with associated territory) without military conquest.

## Mechanics
Loyalty applies to each city of each civilization individually and represents how much political control that civ has over the city's ruling class. Loyalty has far-reaching consequences with serious gameplay effects; below a certain point, Loyalty problems will start affecting the city's economy as the ruling class starts disagreeing with local government officials. The situation may become so serious as to completely cripple city life: Population Population growth will stall, scientific and cultural contribution will stop, basic production will become a burden, and if the situation persists, the city will rebel.

Each city has a Loyalty score which is a value between 0 and 100, and a Loyalty change per turn. The latter is decided by the sum of four factors:

- Pressure from nearby Population Citizens.
- The effect of domestic and foreign Governors.
- Happiness of the Citizen Citizens in the city.
- Other factors.

Below you will find a more detailed breakdown of these factors.

### Loyalty states
The current Loyalty of a city is described by four stages with relevant gameplay effects:

- **Loyal** (76-100): No penalties.
- **Wavering Loyalty** (51-75): 75% Population Population growth, -25% to all yields.
- **Disloyal** (26-50): 25% Population Population growth, -50% to all yields.
- **Unrest** (1-25): no Population Population growth, -100% to all yields, meaning that the city effectively becomes non-functional.

Thus low Loyalty, even without falling further, will still cripple a city's development! You should try your utmost not to let Loyalty fall below 26.

If a city reaches 0 Loyalty or less while continuously receiving negative Loyalty per turn, it will revolt and break away from the empire which owns it, turning into a "Free City" (see below).

Note that it is possible to flip another player's Capital! Of course, since it exerts extra Loyalty on its own, you will need to achieve really big pressure - that is, you need to remove their own pressure by eliminating their other cities, and possibly surrounding it with your own cities from every direction.

### City-states and Loyalty
City-states are a special case within the Loyalty pressure system. They have a special extra Loyalty feat which gives a bonus to resisting pressure from nearby civilizations.

### Loyalty lens

## Factors affecting Loyalty
The following factors are all cumulative; that means that a combination of all could potentially achieve a Loyalty pressure of 40+ for a given city.

### Pressure from nearby citizens
The **pressure from nearby citizens** is a metric calculated for each individual city dependent upon the Population Populations of neighboring cities from the same civilization compared against the Population Populations of neighboring cities from foreign civilizations. Only cities within 9 tiles can impact the pressure from nearby Citizen Citizens, and Free Cities and city-states have no impact.

The calculation is done in two stages: first, pressure from your own neighboring Citizen Citizens and pressure from foreign neighboring Citizen Citizens are calculated; second, a comparison is performed to determine the final pressure value. Each unit of Population Population exerts pressure proportional to its distance away - the amount of pressure diminishes by 10% per tile away from the home city. The Age each civilization is currently experiencing also has an impact:

 Domestic Pressure = Age Factor * Sum of [ each Domestic Population * (10 - Distance Away) ]

 Foreign Pressure = Age Factor of Foreign Civ * Sum of [ each Foreign Population * (10 - Distance Away) ]

where Age Factor is 1.0 for Normal Ages, 0.5 for Dark Ages, and 1.5 for Golden or Heroic Ages. Each Citizen Citizen in the Capital exerts an additional 1.0 per turn regardless of Age. A city always exerts its own domestic pressure with the Distance Away set to zero. The Bread and Circuses project from a nearby Entertainment Complex or Water Park also has the effect of doubling the Population Population count, so a Bread and Circuses project in a highly populated city can be very powerful. In the Dramatic Ages game mode, cities owned by a player who achieves a Golden Age exert even more Loyalty pressure based on excess Era Score.

 Pressure from Nearby Citizens = 10 * (Domestic - Foreign) / (minimum of [Domestic, Foreign] + 0.5)

This final pressure value is capped at ±20. In other words, even if nearby cities have enough Citizen Citizens to exert more than 20 points of pressure, the final effect won't exceed +20 or -20. Other factors (happiness, religion, etc.), however, will still build upon this pressure, potentially resulting in a total Loyalty per turn well over +20.

There is a special case which occurs when a city someone just conquered becomes the reason for an Emergency (a "Free this city" type of mission). To ensure that this city remains owned by the actual target of the Emergency and doesn't flip before it ends, it will receive an extra 20 points of Loyalty for the duration of the Emergency. Of course, military conquest will result in ending the Emergency itself, and cancel these points.

#### Example of pressure from nearby citizens

The image to the right contains a small island with 5 cities, 1 city-state (which we ignore), 2 cities owned by England (which is experiencing a Normal Age), and 2 cities owned by Kongo (which is experiencing a Dark Age). If we calculate the pressure for the city of Kinchassa:

 Domestic = 0.5 * [ 5 * (10-0) + 2 * (10-4) ] = 31

 Foreign = [ 1 * 11 * (10-7) + 1 * 2 * (10-4) ] = 45

 Pressure = 10 * (31 - 45) / (min[31,45] + 0.5) = -4.4

The pressure for Mbanza Mbata and Manchester can be similarly calculated but Liverpool has external influence from other cities from the south and west.

England could mount a "Loyalty attack" (see below) by running Bread and Circuses in Liverpool. This would reduce Kinchassa's pressure to -15.2 (and Mbanza Mbata's to -10.8). Neutralising its Governor, whilst also using Amani's Emissary title and quickly growing the Population Population of Manchester, would see Kinchassa revolt in around 5 turns, and Mbanza Mbata would also fall shortly after. Kongo's Dark Age makes this a fairly straightforward attack to mount. If England were also in a Golden Age, this attack might succeed even without the player necessarily doing anything or being aware of it.

### Happiness of the citizens
Happiness of the citizens (which depends on Amenities in the city) also plays a role:

- -6 if the citizens are **Unhappy** or worse (Amenities deficit is at least 3).
- -3 if the citizens are **Displeased** (Amenities deficit is 1-2).
- +3 if the citizens are **Happy** (Amenities surplus is 1-2, or 3-4 in Gathering Storm).
- +6 if the citizens are **Ecstatic** (Amenities surplus is at least 3, or at least 5 in Gathering Storm).

### Domestic and foreign Governors
Impacts from Governors can be direct or indirect depending upon their abilities.

- +8 Loyalty per turn for having any Governor assigned to that city (activated from the moment you assign the Governor, not the moment they actually become established).
- -2 Loyalty per turn for another civilization having Governor Amani, with the Emissary title, established in a city or city-state within 9 tiles.
- +2 Loyalty per turn for having Governor Amani, with the Prestige title, established in another city or city-state within 9 tiles.
- +4 Loyalty per turn for having Governor Victor, with the Garrison Commander title, established in the city or in another city within 9 tiles.

### Other factors
A number of policy cards have a major impact on Loyalty. Usually, however, they only provide their benefit under certain circumstances:

- +2 with the Limitanei policy card and if the city is garrisoned.
- +2 (+4 in Gathering Storm) with the Martial Law policy card and if the city is garrisoned.
- +2 with the Praetorium policy card and if the city has a Governor.
- +1-6 with the Communications Office policy card and if the city has a Governor.
- +3 with the Colonial Offices policy card and if the city is not on your Capital's continent.
- -2 with the Police State policy card.
- -5 with the Automated Workforce policy card.
- If the Dramatic Ages game mode is enabled:
- -2 to each foreign city within 9 tiles for each wonder in your cities with the Mandala State policy card.
- +0.5 for each Citizen Citizen in a city with the Sakdina policy card and if a project is underway.
- +2 to each foreign city with the Solidarity policy card and if your city has a Governor.
- +4 with the Decentralization policy card and if the city has a Population Population of 6 or less.
- +4 with the Despotic Paternalism policy card and if the city has a Governor.

Buildings also can have an impact on Loyalty:

- +1 if the city has constructed a Monument.
- +8 if the city has constructed the Government Plaza.
- -2 if the Audience Chamber has been constructed in the civilization's Government Plaza district and the city is without a Governor.

And there are also a number of other factors:

- +2 for each Encampment building in the city if you are the Suzerain of Preslav.
- +2 from having the Colosseum within 6 tiles.
- +3 if a city is following the religion you have founded.
- -3 if you have founded a religion and the city doesn't follow it.
- -5 if the city is Occupied (which may be negated by keeping a unit garrisoned in it).
- -4 if the city is facing starvation (for example, if its Farms have been pillaged).
- +10 as a base level for Free Cities.
- +20 as a base level for city-states.
- If you own the Statue of Liberty, all your cities within 6 tiles have their Loyalty locked at 100.
- Variable penalty to Loyalty if the city has been conquered and you have lots of Grievances with its founder.
- If you are culturally dominant over another civilization, your Citizen Citizens exert 25% more Loyalty pressure on their cities.

A number of Great People can permanently increase Loyalty in the city where they are Retired. Note that many of them are Great Admirals and can only be activated in coastal cities, meaning that only such cities will be able to benefit from their ability.

Finally, there are a number of civilization-, leader-, and game mode-specific abilities which increase or decrease Loyalty:

- +4 for an English city on a separate continent from the Capital with a Royal Navy Dockyard.
- +2 for a Spanish city on a separate continent from the Capital with a Mission adjacent to its City Center.
- +3 for a Zulu city with a garrisoned unit, increased to +5 if the unit is a Corps or Army.
- +5 for a Persian city with a garrisoned unit.
- +2 for a Dutch city for each domestic Trade Route starting there.
- +2 for a Swedish city with an Open-Air Museum.
- +4 for an Ottoman city not founded by the Ottomans.
- A coastal Phoenician city on the same continent as the Capital has its Loyalty locked at 100.
- +4 for a city within 9 tiles of a city in which a Mapuche Governor is established.
- +3 for a city with an Industrial Zone when playing as Abraham Lincoln.
- -2 for each Plantation a city owns when playing as Abraham Lincoln.
- If the Secret Societies game mode is enabled:
- +4 for a city where a Spy owned by a member of the Owls of Minerva who has taken Indoctrination is performing a Counterspy mission.
- If the Heroes & Legends game mode is enabled:
- +1 to the owner's civilization for each Hero within 2 tiles (at the end of each turn).

## Free Cities

If the Loyalty score of a city that is exerting negative Loyalty pressure per turn drops to 0, it will declare independence, ripping itself away from its mother civilization and becoming a Free City. Unlike a city-state, a Free City doesn't have a strong national identity, and is basically the local governors of the city becoming fed up with central government and deciding to have a crack at independence. Consequently, their functionality is quite limited.

Free Cities' colors are dark gray and dark red, and just like Barbarians they are always hostile toward (i.e., at war with) other civilizations. This means that they will attack any units that near their territory, and often will invade neighboring cities. For this purpose, Free Cities spawn military units as soon as they declare independence, and continue training them non-stop. But apart from this, they don't do anything else. The tech level of units matches the tech era of the last civilization which was in control of this city, not that of its original owner.

Free Cities are like city-states in that they don't compete to win the game, but they are different in everything else. They cannot be negotiated with (e.g., attracted as allies for wars), they are not valid destinations for Trade Routes, and they do not provide any other benefits which real city-states grant to empires with enough Envoys present. And it is because they don't have real governmental structures and national identity that they are still subject to Loyalty pressures, and will eventually petition to join another empire which manages to exert sufficient pressure on them. You can always see the flag of the civilization exerting the greatest pressure flashing under the city.

Note that Free Cities receive a +10 Loyalty bonus to help them resist foreign pressure. This bonus makes it possible for Free Cities to entice other cities - including their previous owner's Capital - to join them, especially when the Dramatic Ages game mode is enabled. The Population Population of a Capital that becomes a Free City, however, will continue to exert Loyalty pressure for its original owner (which might be a bug).

The process of causing a city of a foreign empire to become a Free City and then causing it to join your own empire is known as "flipping" a city. First you need to exert enough Loyalty pressure on a nearby foreign city to force it to become a Free City, then make sure no one else exerts more pressure on it until you flip it to your empire. This is, in practice, a way to conquer enemy cities without firing a single shot.

If a Free City petitions to join your civilization, you will have the choice of accepting or rejecting their petition, with the following consequences:

- If you accept the petition, the city joins your civilization without any penalties, with the Population Population, buildings, and Districts it currently has. Any units it had spawned or trained are immediately disbanded.
- If you reject the petition, the city will remain a Free City, but your civilization will no longer be able to exert Loyalty pressure on it. It will remain free for the rest of the game unless another civ manages to attract or conquer it.

Of course, Free Cities may eventually rejoin their previous owner if they take measures to increase Loyalty pressure in the region.

Free Cities can also be liberated to their original owner when captured. This will greatly improve diplomatic relations, and also lower the liberator's global Grievances and provide a one-time bonus of Diplomatic Favor in Gathering Storm. Liberated cities are immune to Loyalty pressure from the liberator to prevent players from exploiting this mechanic, but a city that succumbs to Loyalty pressure from a third party can be liberated repeatedly.

## Strategy
Loyalty is a mechanic to which you might not need to pay much attention, unless you:

- Decide to found cities far from the core of your empire and close to the territory of other empires.
- Are in a Dark Age and the closest neighboring empire is not.
- Plan to conquer cities which have strong domestic pressure - for example, those on another continent, densely positioned, or of civilizations in a more favorable Age than you.
- Plan to use Loyalty to flip foreign cities which are poorly settled.

The Loyalty system was designed alongside that of Ages and Governors, and the effect of Ages on Loyalty is often underestimated. A Dark Age is very damaging to Loyalty defense. Either in wartime or with contentious borders, the Ages of civilizations should be considered. Maintaining control of conquered cities might be impossible if you're in a Dark Age and the opponent a Golden Age, yet straightforward if the Ages are reversed.

### Loyalty defense
If you are an expansionist or struggling to maintain Loyalty of your cities, try to:

- Install Governors where needed and utilize Governor Amani's Prestige or Promoter titles.
- Keep citizens happy by improving luxury resource tiles, trading for luxury resources or constructing buildings that provide Amenities. Sue for peace if war weariness is too great.
- Build Monuments.
- Maintain your religion through the help of Inquisitors.
- Increase your Population Population quickly by focusing on Food, removing features with Builders, and re-routing domestic Trade Routes.
- Found additional nearby cities.
- Run Bread and Circuses projects in nearby cities to amplify their domestic pressure.
- Avoid Dark Ages.
- Slot the Praetorium, Limitanei, Martial Law, and/or Colonial Offices policy cards in more desperate times.
- Found and/or conquer cities in globular shapes where each can assert maximal domestic pressure on the others, rather than having linear empires.
- Form a Cultural Alliance. This will stop any Loyalty pressure from your ally, and vice versa.

### Loyalty while conquering
If you plan to conquer cities with military force, try to:

- Consider the effect of Ages on Loyalty pressure - ideally, target a Dark Age civilization when you are in a Golden Age.
- Conquer the city with the highest Population Population first to dramatically reduce the foreign pressure on nearby cities, while also ensuring maximum domestic pressure.
- Conquer multiple cities in quick succession to amplify the domestic pressure each conquered city exerts on the others.
- Use Settlers to found new opportunistic cities supporting domestic pressure.
- Use the above defensive strategies to maintain control of conquered cities.
- Maintain a garrison in each conquered city.

Dealing with the war weariness resulting from a campaign affecting the general happiness in all your cities including the newly-conquered ones can be difficult, especially when combined with the other factors or assaulting a new continent with no domestic pressure foothold, or attacking civilizations in superior Ages.

### Loyalty attack
A Loyalty attack can be executed peacefully or supported by pillaging. To try to "flip" cities, you can do the following to lower their Loyalty pressure:

- Use Spies to neutralize the target city's Governor.
- Grow your neighboring cities' Population Populations as quickly as possible, as described above.
- Run Bread and Circuses projects to amplify your pressure; ideally they should be run in big cities surrounding the target.
- "Flank" the target city by having numerous cities of your own surrounding it.
- Use Governor Amani's Emissary title.
- Convert the city to your religion.
- Pillage districts and improvements that provide Amenities to cause unhappiness.
- Pillage Farms to cause starvation.
- Establish Governors in nearby cities when playing as the Mapuche.
- Use Great Works when playing as Eleanor of Aquitaine.
- If the Heroes & Legends game mode is enabled, don't position Heroes around the city.

Once the city's Loyalty pressure is negative, you can do the following to drive the city's Loyalty down to 0 and make it rebel faster:

- Use Spies to perform Foment Unrest missions.
- Kill enemy units within the city's borders when playing as Lautaro.
- Slot the Hallyu policy card, purchase Rock Bands with the Indie promotion, and send them to perform concerts in the city.
- If the Secret Societies game mode is enabled and you're a member of the Voidsingers, purchase Cultists and use their charges to reduce the city's Loyalty.

Being in a better Age than your opponent makes Loyalty attacks easier to execute. An example of when to use a Loyalty attack is detailed above.

All in all, the Loyalty mechanics offer great possibilities on one hand, and great problems on the other. They make it all but impossible to expand your empire by founding or conquering cities far from your own empire, and at the same time very close to other empires. If this is part of your strategy, you should plan to dedicate half your policy slots to cards that increase Loyalty, and at the same time move Governors to the new cities immediately after founding/conquering them. Keep your happiness levels as high as possible, and try to spread your religion (if you have one) to the new cities immediately (or even beforehand, if you intend to conquer them).

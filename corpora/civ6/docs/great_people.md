# Great People (Civilization VI)
Source: https://civilization.fandom.com/wiki/Great_People_(Civ6)
License: CC BY-SA 3.0 (Civilization Wiki, Fandom: "Community content is available under CC-BY-SA unless otherwise noted.")

_Retrieved 2026-09-26 through the wiki's MediaWiki API (Great People (Civ6) rev 473796). Wiki prose may predate Gathering Storm balance changes; the generated records in ../data (the game's own files, 1.0.12.68) win where numbers differ._

- Great People** (GPs) return in Civilization VI. They are exceptional historical figures with special abilities, which appear in your civilization when you develop a particular aspect of the gameplay sufficiently. Unlike in prior games, individual Great People now have distinct bonuses similar to Founding Fathers in Civilization IV: Colonization. What's more, each individual Great Person can only be earned once.

## List of Great People
-
-
-
-
-
-
-
-
-
- *

- Simón Bolívar only.

## Mechanics
There are many changes to Great People mechanics compared to Civilization V.

First, each class of Great Person (including Great Prophets) is earned via accumulating a distinct Great Person Point resource. Each civilization accumulates the relevant resource separately, but unlike in Civilization V, the accumulation happens empire-wide rather than citywide. Every distinct source of the same type of Great Person points will contribute to the common pool. Whenever a civilization attracts the Person (whether by acquiring enough points, or in other ways - see below), the pool is depleted and starts accumulating again.

Second, as mentioned above, Great People are distinct, even when they are of the same type - one Great Scientist, for example, is completely distinct from another, even to his/her special abilities. This is important because civilizations will now compete to attract each specific Great Person. They also have a historically correct biography in the Civilopedia.

Third, each distinct Great Person belongs to a certain era. With each new era, Persons belonging to it require more Great Person Points to attract.

Finally, all Great People of a certain class now come in a "queue," arranged by era. The queue starts with People from the Classical Era, and finishes with those from the Information Era. People from the same era always appear in random order, but when all that belong to a certain era are attracted, the next era's queue will start, and the amount of GPPs required to earn them will rise. After all Great People of a certain class are attracted, it becomes impossible to earn any more of them.

The developers seem to have a policy of not using a person that is still alive as a Great Person. In addition, there seems to be a policy of using a writer, artist, or musician only if the person's work is in public domain (i.e., copyright has expired, generally 50-70 years after death). As a result of this, some Great People - especially Great Artists, Writers, and Musicians - appear in a different period than in real life. For example, Gauhar Jaan (who died in 1930) is an Information Era Great Musician.

### The Great People screen
To check Great People progress in detail, there is now the brand new Great People screen, which can be opened from a button in the upper left part of the UI. This screen will display all Great People which are currently up for grabs. This usually means one of each class; however, Great Prophets are usually all attracted by Turn Icon Turn 100 or so, while at the very end of the game (Turn Icon Turn 350+) other classes of Great People start also vanishing one by one because all of their representatives have been earned.

Under each Great Person you will see a list of all players in the game (including unmet ones), and how many of the respective GPPs they've earned for now. The list is arranged from the one with the most GPPs accumulated, to the one with the least (GPPs per turn doesn't affect this). Mouse over to see the exact rate at which each player earns GPPs for this Person. Thus you can estimate which player has the greatest chance of earning this particular Great Person. But know that the situation may change all of a sudden at any time, due to players using projects (which net a sum of GPPs at one time), gaining new sources of GPPs, or Patronizing Great People to earn them instantly. Finally, underneath the list you'll find the two buttons allowing you to Patronize the Person, and how much Gold or Faith this will currently cost you.

The Great People screen has also another tab, which switches to present a list of all Great People which were already earned, their class, who earned them and when. This can be useful if you want to establish patterns in a player's tendency to strive for particular Great People.

## How to Earn Great People
There are two primary ways to earn Great People.

### Attracting via Great People Points
Great People are normally earned (or "attracted") through accumulating a special resource, the Great Person Point (GPP). Whenever you accumulate enough GPPs of a certain type, you will have the possibility to attract the next Great Person of this class in the queue. You can also choose to pass the opportunity and preserve your accumulated GPPs for the next Person. It is fully possible that, when the next person in the queue arrives, the person is from the next era, and thus costs much more than the Points you've accumulated currently.

With each successive era, Great People require more GPPs to earn; that is, a Great General from the Classical Era costs much less than one from the Industrial Era. Moreover, most Great People classes' GPP cost (all but art-related People and the Great Prophet) will scale up from the general era base cost, according to the following formula:

GPP cost = base cost * (1 + 0.3 * difference in era) ^ difference in era

where **base cost** is determined by the era that a Great Person is in, and **difference in era** denotes the number of eras between the era of the Great Person and the World Era when the Great Person appears in the queue. This number is either 0 or a positive integer.

Example 1: In the Medieval Era, when the last Medieval Great Scientist is recruited, a Renaissance Great Scientist will appear in the queue, and the difference in era is 1, so the GPPs needed will be 312 (240*1.3^1).

Example 2: Following Example 1, if the Renaissance Great Scientist is not recruited by any civilization until the world enters the Renaissance Era, then the following Renaissance Great Scientist will only cost 240 GPPs.

Example 3: Following Example 1, if ALL Renaissance Great Scientists are recruited in the Medieval Era, then an Industrial Great Scientist will pop up with a GPP cost of 1075 (420*1.6^2). If this Great Scientist is recruited during the Medieval Era, then the next Industrial Great Scientist will still cost 1075 GPPs, but if it is recruited during the Renaissance Era, then the next Industrial Great Scientist will only cost 545 (420*1.3) GPPs.

- Era | GPP cost (on Standard speed) | Notes
- Classical | 60
- Medieval | 120
- Renaissance | 240 | First Great Artists available
- Industrial | 420 | No more Great Prophets First Great Musicians available
- Modern | 660
- Atomic | 960
- Information | 1320

GPPs accumulated by a player are never lost, though - if you didn't manage to earn the current Person, you will continue accumulating points for the next one. Two competing civilizations will frequently earn Great People one after the other, if the successive Great People of this class are from the same era - this happens because both are very close to the GPP total needed for this era, and soon after one wins, the other wins the next Great Person in the queue.

GPPs are earned in a variety of ways, but the most common sources are appropriate Districts (e.g., Campuses provide Scientist points, Encampments provide General points), policy cards, and wonders. Having Classical Republic as your government boosts all Great People point generation (if you generate more than 0, of course); moreover, this is a Legacy bonus that will accumulate and remain useful for the rest of the game.

Some wonders make Great People appear when they are completed; for example, Stonehenge provides a free Great Prophet. When this happens, the Person attracted is the next in the queue.

In Gathering Storm, unused Great People points of any kind (points for a class of Great Person that your civilization cannot attract for some reason) are converted to Faith, in a 1:1 ratio. For example, after you earn a Great Prophet, or when you fail to get one before the maximum number allowed for this game are attracted, the Great Prophet points from Holy Sites and others will be converted to Faith.

### Attracting via Patronage
The second way to attract Great People is via "Patronage" (and no, this is not a social policy like in Civilization V). As the name suggests, this involves a player announcing a large grant, or something of the sort, which attracts the attention of a Great Person to his/her civilization. The effect is, of course, instantly acquiring this Great Person.

You can pay for this grant in either Gold or Faith, with the Gold cost always being roughly 1.5 times larger. The exact sum depends on two things: the era the specific Great Person belongs to, and how many GPPs you have already accumulated towards this class of Great Person. The Gold/Faith you pay makes up for the difference, so the more GPPs you have accumulated, the less you will have to pay to "patronize" this Great Person.

On Standard speed, the Faith cost of Patronage is:

150 + (10 * (total - available))

The Gold cost is:

200 + (15 * (total - available))

In both formulae, **total** means total GPP points needed for this Great Person, and **available** means how many GPP points you currently have. Fractional points are always rounded down.

The Oracle diminishes all Patronage Faith costs by 25%.

Finally, you may choose to pass the opportunity to earn a particular Great Person. In this case, you preserve most of the GPPs collected, which will continue accumulating for the next Great Person of the same class. A small portion of these points, however, are granted to your competitors, thus helping them to attract this particular Great Person. Use this option when the specific abilities of a Great Person don't suit your current needs and goals.

### District Projects
There are now special projects which may be developed in cities with the relevant districts, which will provide a lump sum of the relevant Great Person points when finished. Use these projects to "jump" ahead in the points race. Note that each such project produces a fixed amount of points.

### Number of Available Great People
Map size affects the number of Great Prophets available, but has no bearing on other classes of Great People. This means, for example, that the same 21 Great Engineers are available for recruitment whether you're playing in a Tiny 4-player game or a Huge 12-player game.

That said, it is still possible for a Great Person not to appear in a particular game. When a Great Person is claimed, the replacement is chosen randomly from those available in the current era, or the next if all those from the current era have been claimed. As an example, assume Andrei Rublev has been claimed and Hieronymus Bosch is the currently available Great Artist. If Bosch is claimed before the end of the Renaissance Era, then he might be replaced with Donatello, Michelangelo, or Kamāl ud-Dīn Behzād. If he isn't claimed until the Industrial Era, however, his replacement would be an Industrial Era Great Artist (e.g., Titian or El Greco). This would prevent Donatello, Michelangelo, and Kamāl ud-Dīn Behzād from ever appearing in that playthrough.

## Great People Abilities
As mentioned before, Great People abilities aren't streamlined anymore - each Great Person of a particular class has different abilities. Most of the time they are associated with the era in which that Person usually appears - for example, the Great Admiral Themistocles has an "aura" increasing CS for Classical and Medieval Era naval units, but not for later era units. However, all Great Persons of a particular class share a general direction for their abilities (e.g., all Great Admirals will have abilities improving naval combat, or other aspects of seafaring). There are though some notable exceptions, in which Great Persons of one field contribute to another.

Some abilities of the Great Person are related to the person's real-life counterpart. For example, Great Admiral Grace Hopper's ability is unlocking a random technology of the Information Era. While it might be strange for a Great Admiral's ability to be scientific in nature, it makes sense because the real-life Hopper was known not only for attaining the rank of Rear Admiral in the U.S. Navy, but for building the first compiler in computing and being on the team that created the COBOL programming language.

All in all, Great People are generally useful only from and up to a certain point in the game, related to their native era. This is now valid even in the case of the Great General and Great Admiral - their passive bonuses now only apply to units of particular eras and become useless after that period passes. Thus, players no longer have a reason to hoard Generals and Admirals throughout the game, and should instead activate their special abilities before their usefulness passes. There are, of course, exceptions to the rule: all Great Artists, for example, create Great Works which are useful throughout the game, regardless of the native era of the Person who created it.

### Activating Great People
Most Great People abilities are one-time, instant actions, such as creating a type of Great Work, or getting the boost for a particular technology. For most Great People, these actions may only be taken in specific places (i.e., a city district relevant to their abilities). That would generally be the Campus for the Great Scientist, the Commercial Hub for the Great Merchant, the Industrial Zone for the Great Engineer, the Theater Square for the art-related Great Persons - and, of course, the Holy Site for the Great Prophet. The Great General's and Great Admiral's one-time abilities may usually be activated anywhere.

Note that sometimes the bonuses activated are related to this specific city, so think about where exactly you want this bonus to apply before activating them.

All art-related Great Persons produce Great Works. However, note that in order to activate their abilities, they need to be in a Theater Square or otherwise in a tile with a building which provides free slots for the relevant type of Great Work. If you have such slots in wonders, you must bring your Great Person to the tile of the wonder with the slot. And if all relevant buildings in your empire have their available slots taken by other Great Works, you will be unable to Activate your Great Person.

Of course, if you don't have the relevant district for a specific Great Person, you will again be unable to activate their ability.

## Moving Great People
Great People aren't such a bother to move around anymore, because now all of them have the "Move to city" ability which instantaneously transports them from one City Center to another. Note that this ability may only be activated from a City Center, save for the Great Admiral, who can also move from a City Center to a Harbor (but not vice versa).

Great People cannot be captured by enemy military units, and automatically retreat to their owner's nearest City Center rather than being killed. The only exception to this is a nuclear strike.

## Strategy
All changes made to the Great People system contribute to a much more interesting and dynamic game. Different Great People may now benefit different civilizations more, or be more useful at specific moments of the game. You should take some time to study the available Great People, then plan ahead to decide which ones you want to attract. However, since all civilizations are now competing to attract the same Great People, you will have to race them, similar to building a wonder.

A common tactic used to beat others to a specific Great Person is to combine both ways of attracting Great People. You should, of course, try to produce as many GPPs of the relevant type as you can; however, when you get close to the goal for the Person you want, you may spend Gold or Faith to Patronize them. This is a great strategy to use when you see that you're slightly behind another competitor, and you see no way to outpace them in time, even with special projects. But it can be useful even when you're ahead and will clearly finish before the others, because you will get the Great Person earlier, and will be able to use their benefits earlier.

This is a fine line to walk, since with each passing turn the Patronage cost will fall, but you risk another player doing the same and beating you to the Person! Sometimes greed may cost you the victory.

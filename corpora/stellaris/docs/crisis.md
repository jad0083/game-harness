# Crisis
Source: https://stellaris.paradoxwikis.com/Crisis
License: CC BY-SA 3.0 (page footer: "Content is available under Attribution-ShareAlike 3.0 unless otherwise noted.")

_Retrieved from the Wayback Machine capture 20260804085630 (the live wiki blocks non-browser clients). Page version banner: Version This article has been verified for the current PC version (4.4) of the game._

This article is about scripted midgame and endgame crisis events and factions. For regular empires pursuing a crisis path (becoming the crisis), see Crisis empire.

A crisis is an event that threatens all civilizations in the galaxy.

Crises occur in the galaxy at certain points of the game and tend to attack all empires indiscriminately in a manner similar to a Total War; systems conquered by a crisis faction will either be immediately absorbed into their territory or will have their starbases completely destroyed, depending on the crisis. Arkships defeated by crisis factions will likewise be destroyed rather than disabled. Each time a crisis conquers a planet, it causes a Threat opinion bonus between with all empires, making them more likely to cooperate against the crisis. Fallen Empires will send their fleets against a Crisis if it approaches their borders and may even awaken to help fight it.

Crisis factions are typically removed from diplomacy and cannot be negotiated with like common empires. Empires with certain authorities, ethics, or ascensions may gain additional dialogue options with some crisis factions and learn additional information, but peace is impossible. The arrival of a crisis faction will cause a Galactic Focus resolution to fight them to become available in the Galactic Community.

The Crisis Strength galaxy setting and the various difficulty bonuses increase the hull, shield, armor, and damage of crisis factions, but not the ship fire rate. These bonuses affect both midgame and endgame crises, with the former getting a square root value of the bonus. Having a crisis active in the galaxy will stop the game from ending, even if the Victory Year has been reached.

There are two types of crises: midgame crises and endgame crises.

## Midgame crises

Midgame crises occur during the midgame phase of the game and, while having a smaller impact than endgame events, are capable of notably reshaping the current state of the galaxy. Rather than following the same mechanics of the endgame crises noted below, midgame crises tend to be locked to specific DLC mechanics. The list of possible midgame crises are:

- The Horde
- The Gray Tempest
- The Formless
- The Voidworm Plague

## Endgame crises

Endgame crises can only happen if they haven't been disabled in the galaxy settings. Normally only one crisis can happen per game, but if the Crisis Type setting was set to All, then all of them will eventually happen and each one will be twice more powerful than the previous one. Endgame crises cannot take place within 25 years of each other. The list of possible endgame crises are:

- Prethoryn Scourge
- Extradimensional Invaders
- Contingency
- The Synthetic Queen

### Requirements

As the name implies, endgame crises normally can only happen after the end-game year set at game settings has passed, although in special cases, the Extradimensional Invaders can spawn early.

Every 5 years, a check is made to determine whether a crisis can spawn, with the trigger being that both of the following conditions must be true:

- One of the following must be true:
  - The endgame year has been reached, and one of the following is true:
    - The Ancient Robot World archaeological site in Ultima Vigilis enabled endgame_crisis_early_start flag (50% chance upon finishing the site).
    - Both the Extradimensional Experimentation resolution and the Galactic Threats Committee resolution have been passed.
  - At least 25 years have passed since the endgame year, and one of the following is true:
    - Any empire has Jump Drives or Psi Jump Drives technology.
    - Either the Extradimensional Experimentation resolution or the Galactic Threats Committee resolution has been passed.
    - One of the following must be true (default_endgame_early_start_triggers scripted trigger):
      - No Fallen or Awakened empires exist
      - There cannot be a War in Heaven, regardless of the galactic situation
      - A War in Heaven has already occurred, and finished
  - At least 50 years have passed since the endgame year.
- The following must be true:
  - If galaxy setting allows only 1 crisis, check that the crisis has not already occurred.
  - Otherwise, check that at least 25 years have passed since the last crisis spawn (it could still be active)

### Spawn conditions

Once the above requirements are met, the crisis is determined by a weighted chance.

- Empty weight of 120, where nothing happens until the next check is made in 5 years:
  - Reduced to 1 if the Ancient Robot World archaeological site in Ultima Vigilis enabled endgame_crisis_early_start flag (50% chance upon finishing the site).
- Extradimensional Invaders has a base weight of 8:
  - x0 if crisis type is set to anything else, or if it has already happened in all-crisis setting.
  - x3.75 if crisis type is set to Extradimensional Invaders.
  - x2 if no Fallen or Awakened empires exist, or there cannot be a War in Heaven.
  - x0.5 if less than 20 years have passed since endgame year.
  - x2/2/3/3/4 if 35/50/70/85/100 years have passed since endgame year.
- Prethoryn Scourge, Contingency, and The Synthetic Queen each has a base weight of 10:
  - x0 if crisis type is set to anything else, or if it has already happened in all-crisis setting.
  - x3 if crisis type is set to Prethoryn Scourge/Contingency/The Synthetic Queen, respectively.
  - x2 if no Fallen or Awakened empires exist, or there cannot be a War in Heaven.
  - x2/2/3/3/4 if 35/50/70/85/100 years have passed since endgame year.

Once a crisis is determined, the corresponding event chain is triggered after 200-1000 days, beginning the crisis proper.

### Situation log

Endgame crises have a Situation Log entry that keeps count of the casualties on both sides and shows how close the crisis is to being defeated. During an endgame crisis, an audio cue will play in the background and grow more pronounced the more systems are controlled by the crisis.

Once an endgame crisis arrives, the following things will happen:

- If the Galactic Community or Galactic Imperium exists, a Galactic Focus resolution to fight the crisis will become available.
- If the Enigmatic Observers, Keepers of Knowledge or War Splinter Fallen Empires are present, they can awaken as Guardians of the Galaxy, and may also do so if they had already awakened beforehand. The Ancient Caretakers can also awaken, but only if the crisis is the Contingency.
- The Shroudwalkers will disappear if present.
- Empires with the Fear of the Dark origin will receive a bonus to ship build speed and cost.

If an endgame crisis is defeated, every empire will receive +10% Happiness for 10 years and a large reward of Unity.

### Damage modifiers

Endgame crises each possess their own mechanics and ship components, meaning the best means to combat one may not be as effective on another; strategies for combating each individual crisis faction can be found on their respective sub-sections. However, there are a number of damage modifiers which apply to all crisis factions, making them useful in all cases:

| Damage to endgame crisis factions 0 |  |
|---|---|
| Source | Effect |
| Defender of the Galaxy ascension perk | +50% |
| Galactic Peacekeepers (Level 5) | +25% |
| Stronger Together (Level 4) | +25% |
| Stronger Together (Level 5) | +25% |
| Galactic Threats Committee resolution | +20% |
| A United Front resolution | +20% |
| Underdog empire modifier | +20% |
| Skrand Crisis Insight empire modifier | +20% |

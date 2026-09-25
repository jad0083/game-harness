# Galactic Civilizations IV: Supernova - Strategic Playbook

**Faction**: Terran Alliance (Human)  
**Target Game Version**: 4.1.1  
**Architecture Role**: Strategic Layer 4 Deliberation Playbook (Injected into LLM / MCP when autopilot halts on major decision points).

---

## 1. Core Principles & Expansion Meta (Turns 1 - 35)

### A. Core Worlds vs. Feeder Colony Worlds
*   **The Foundation**: Newly colonized planets automatically become **Colony Worlds**. They do *not* have individual build queues. Instead, they funnel 100% of their raw Manufacturing, Research, and Wealth inputs directly into their designated **Core World**!
*   **Core World Conversion**: A planet only becomes a Core World when you appoint a **Leader as Governor**. 
*   **Feeder Pre-Seeding Meta**: When preparing a second Core World in a newly discovered high-class system (Class 20-30 yellow star system), colonize the surrounding minor feeder planets *first*. Do not appoint a Governor on the main world until the feeder colonies are sending raw inputs—giving your new Core World an immediate 20+ production surge on the very turn the governor takes office.
*   **Optimal Ratio**: Maintain 1 industrial titan Core World per 3–5 supporting Colony Worlds in the early game. Earth serves as your initial industrial titan; Mars is Colony #1 supplying Earth's orbital shipyard.

### B. Minister & Leader Allocation Meta
*   **Minister of Exploration**: Appoint a leader with highest **Diligence**. Diligence directly increases fleet movement speed across all ships in your empire. Speed is the paramount factor in early exploration and colonist racing.
*   **Minister of Technology**: Appoint your highest **Tech/Intelligence** leader. Provides a direct multiplier to monthly research point generation.
*   **Minister of Colonization**: Appoint a leader with highest **Social** stat to maximize planetary population growth.

### C. Turn 1 Foundation Checklist
1.  **Homeworld Capital City (Earth)**: Construct the Capital City improvement immediately on Turn 1 on Earth. It costs 0 manufacturing and does not wait in queue, immediately granting +10 Colony Gross Income, +6 Pop Cap, +3 Sensor Range, +1 Control/turn, +100 Influence, and +1 Culture Point/turn.
2.  **Executive Orders**:
    *   **Draft Colonists**: (-33 Control). Incurs a minor temporary Approval hit in exchange for an immediate free Colony Ship with passenger. Always take this on Turn 1—expansion velocity wins the game.
    *   **Telescope Takeover**: (-10 Control). Clears fog of war around high-class habitable worlds in your sector.
    *   **Print Money**: Rush-buys initial planetary infrastructure or recruits elite leaders.
3.  **Ideology & Culture**:
    *   **Self Governance** (Liberty tree): Spend your first culture point here for +10% approval and a free leader.
    *   **Mobility Rights**: Take for your second culture point (+2 starbase range) to capture 3 resource nodes simultaneously with a single starbase.
4.  **Survey Anomaly Harvesting**: Keep your Flagship (`T.A.S. Theia`) surveying anomalies continuously along asteroid fields and outer orbits. Early anomalies provide massive lumpsum Credits, Tech boosts, and permanent ship stats.
5.  **Manual Probe Exploration**: Manually direct probes toward **Yellow Stars** (G-type) for Class 20-30 terran worlds and **Purple Stars** for Promethion deposits. Never use auto-explore on early probes to avoid roaming pirates.

---

## 2. High-Difficulty AI Roadmap (Turns 1 - 35)

*   **Turn 1**: Place Capital City on Earth; queue Industrial Center and Capital Mainframe. Execute *Draft Colonists* & *Telescope Takeover*. Set taxes to Low for high approval. Assign Ministers of Exploration and Technology. Queue Colony Ship and Probe at Shipyard. Research: *Asteroid Mining* (or *Space Elevators*).
*   **Turn 2**: Survey nearest artifact anomaly; vector probe to closest purple star.
*   **Turn 3**: *Asteroid Mining* completes. Research *Starbases*. Send Asteroid Miners to the 2 closest asteroid belts $\to$ Earth jumps to 20-25 production immediately!
*   **Turn 5**: *Starbases* completes. Research *Hyperwave Radio* (unlocks +1 policy slot). Colonize Mars with Colony Ship. Earth finishes initial buildings: queue Entertainment District and Manufacturing Districts adjacent to Capital.
*   **Turn 6**: Shipyard queues: Colony Ship, Asteroid Miner, Probe, Constructor. Manually direct probes to G-type yellow stars.
*   **Turn 7**: *Hyperwave Radio* completes. Research *Subspace Scanning* (for *Eyes of the Universe* wonder). Policy: *Coerced Colonization* (+100% growth).
*   **Turn 8-11**: Research *Space Elevators*. Build *Elon's Lift* wonder (+10% all manufacturing, requires 5 Durantium).
*   **Turn 12-14**: Research *Research Districts*. Build *Kazar's Mainframe* wonder (+25% research, requires 5 Promethion). Research *Anomaly Detection* to unlock dedicated Survey Ships.
*   **Turn 15-20**: Pre-seed feeder colonies around Core World #2. Research *Leadership Recruiting* $\to$ *Colonial Bureaucracy* $\to$ *Political Capital* $\to$ *Colonial Law & Order* (eliminates planetary crime).
*   **Turn 21-35**: Research *Planetology* $\to$ *Xeno Manufacturing* $\to$ *Starbase Modules*. Build Durantium Processor on Earth.

---

## 3. District Placement & Planetary Synergies

Core Worlds feature hex tiles that accept **Districts** and unique **Improvements**:

| District Type | Primary Output | Synergies & Placement Rules |
| :--- | :--- | :--- |
| **Manufacturing** | Construction speed for Ships & Buildings | Place adjacent to Capital City, mineral deposits, industrial ruins, and other factories. |
| **Research** | Tech points per turn | Cluster together. Research benefits heavily from adjacency bonuses next to Capital Mainframe / Kazar's Mainframe. |
| **Financial** | Gross Income (Credits) | Essential to fund ship maintenance and rush-buys. Place on economic tiles. |
| **Agricultural** | Food production & population growth | Maximize population growth so new citizens can be drafted into colony ships. |
| **Housing** | Maximum Population Cap | Build when population reaches 80% of tile cap. |

---

## 4. Starbase 3-Node Clustering Rule

*   Mining starbases extract strategic resources (Durantium, Promethion, Antimatter, Elerium, Ascension Crystals).
*   With **Mobility Rights** (+2 starbase range), place your constructor equidistant from 3 resource nodes. A single starbase can harvest all 3 nodes simultaneously, saving 2 constructor hulls and doubling starbase module efficiency!

---

## 5. Event Dialog Heuristics & Deterministic Controls

When a modal event or planet report halts the autonomous turn loop:
*   **Look the event up before choosing**: event outcomes are in the game data (`corpus_search "<event title>"`, or `Gameplay/Events/*.xml` by title). The button text rarely states the payoff; e.g. *Precursor Probe* "study" = permanent +1 sensor range on every ship, "repair" = only makes the Stargazer probe purchasable as a 900-credit mercenary, "sell" = 200 credits.
*   **Permanent Output > Temporary Cash**: A $+10\%$ permanent manufacturing or research boost is infinitely superior to $+200$ credits.
*   **Planet Colonization Site Choice**: On initial planet colonization (e.g., Mars Planet Report), select mineral/manufacturing extraction sites (option `2` / Delta sites) for feeder colonies supplying an industrial core world, or scientific/microbial sites (option `3`) if founding a science colony.
*   **Expansion Over Caution**: Choices that *grant* ships, survey probes, or colonist capacity should almost always be chosen — but check the data: an "unlock" often only makes something purchasable.
*   **Selecting an option**: clicking the option button works (verified). Number keys `1`/`2`/`3` are unverified.

---

## 6. UI Navigation & Data Bank Macro-Management

*   **Data Bank Screen**: View overall civilization progress, timeline, graphs, and core world feeder throughputs. Toggle tabs via normalized screen positions or press `esc` to dismiss and return to galaxy map.
*   **Advisors Panel**: Click entries in top-right panel (norm `0.95, 0.05`) to instantly vector camera and resolve pending idle ship or unassigned shipyard states.
*   **Reflex-Deliberation Interruption**: Top resource bar luminance ($\mu < 22.0$) reliably triggers strategic pause whenever blocking event or planet choice dialogs spawn.

---

## 7. Government Policies & Tax Optimization (Colonial Charter)

*   **Tax Rate Management**: Keep the Tax Rate slider at Low (~33%, norm `0.120, 0.295`) early on to sustain high planetary Approval (>55–60%). High approval directly drives population growth rate and worker productivity across all core worlds.
*   **Early Enacted Policies**: Immediately slot *Brainstorming* (+2 Research/month) into the first available policy slot (`norm_x = 0.395, norm_y = 0.448`).
*   **Policy Slot Unlocks**: Prioritize early techs like *Hyperwave Radio* (+1 policy slot) to stack civilization-wide research and production multipliers.
*   **Autopilot pacing**: unblocked turns take about 2–3.5 s (game end-turn processing plus settle); the loop stops for policy slots, idle ships/planets and event dialogs.



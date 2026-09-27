# Learned strategy rules

Written by the pilot app during play; promote proven items into the main corpus.

- When the 'expand' directive is active but system count stagnates, check alloy and influence stockpiles, as an outpost requires ~100 alloys and low stocks will delay expansion.  
  _why:_ retrospective 2214.02.01 _(google:gemini-3.6-flash, 2026-09-25)_

- Prioritizing 'expand' in the early game safely secures systems and colonies when no threats exist, but typically causes military power to fall behind the galactic median until a transition to 'tech_rush' or 'prepare_war' occurs.  
  _why:_ retrospective 2214.02.01 _(google:gemini-3.6-flash, 2026-09-25)_

- When an empire falls to last place in technology and military power, holding 'tech_rush' is safe and necessary as long as the economy runs a surplus without deficits, though it may take many years to close a significant gap.  
  _why:_ retrospective 2219.03.01 _(google:gemini-pro-latest, 2026-09-26)_

- Holding 'tech_rush' during economic surplus safely builds research infrastructure without risking deficits, but closing a large research gap takes decades when starting far behind the median.  
  _why:_ retrospective 2221.09.01 _(google:gemini-3.6-flash, 2026-09-26)_

- When an empire is boxed in with no unclaimed systems within 2 jumps, the 'expand' directive cannot function, and focus must shift to internal development or diplomacy.  
  _why:_ retrospective 2226.08.01 _(google:gemini-3.6-flash, 2026-09-26)_

- A colony's amenities deficit (e.g. -90) is no reason to switch to 'consolidate_economy': no directive repairs grown-colony deficits (+5 to +14 amenities a planet-year under it). The Planet check line names the colonies worth watching.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2226.08.01 said such a deficit requires consolidate_economy

- When a defensive war is declared, transitioning to the 'defend' directive successfully prioritizes survival and starbase defense, though military power may still take years to catch up to the galactic median.  
  _why:_ retrospective 2230.05.01 _(google:gemini-3.6-flash, 2026-09-26)_

- A large energy stockpile can safely absorb temporary energy deficits during a war, allowing the empire to remain in a 'defend' posture without needing to switch to 'consolidate_economy'.  
  _why:_ retrospective 2230.05.01 _(google:gemini-3.6-flash, 2026-09-26)_

- A wartime amenity deficit that recovers after peace (Las Veredas, 2235: stability up 30 points in a year) is the war ending, not 'consolidate_economy'. Do not switch directives to repair a colony's amenities.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2235.05.01 credited consolidate_economy with a Las Veredas deficit that rebounded after peace

- 'consolidate_economy' does not repair grown-colony amenity deficits: over four campaigns it moved them +5 to +14 amenities a planet-year and cleared 2 of 63-70 year-long intervals, most of them on 3 late Theian planets. Every colony under stability 25 was at war (Arnvoss 2294, Largoll 2338, the capital 2383): the Planet check line names such colonies and a planet crisis starts a strategy review; a directive switch does not fix them.  
  _why:_ levers design ruling 22 (E10), measured on telemetry 2026-09-27

- A prolonged defensive war preserves territory but typically causes an empire's technological and military growth to stagnate, falling behind peaceful peers.  
  _why:_ retrospective 2235.05.01 _(google:gemini-3.6-flash, 2026-09-26)_

- Switching to 'consolidate_economy' does not resolve colony amenity and stability deficits: over four campaigns it cleared 2 of 63-70 year-long deficit intervals. It is for resource deficits.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2240.05.01 called it an effective fix

- Maintaining the 'defend' directive during an active war steadily increases military power but can cause minor energy deficits due to fleet upkeep.  
  _why:_ retrospective 2240.05.01 _(google:gemini-3.6-flash, 2026-09-26)_

- When an empire falls below half the galactic median in military power but is at peace and boxed in, maintaining 'tech_rush' is the optimal way to research better ship components and bridge the power gap, provided the economy is stable.  
  _why:_ retrospective 2244.03.01 _(google:gemini-3.6-flash, 2026-09-26)_

- A minor deficit (e.g., -5.2 consumer goods/month) with a massive stockpile (over 4,000) does not require a shift to 'consolidate_economy' and can be safely ignored to continue focusing on research or military goals.  
  _why:_ retrospective 2244.03.01 _(google:gemini-3.6-flash, 2026-09-26)_

- When a massive stockpile of consumer goods exists, minor deficits can be safely ignored to maintain a high-priority directive like 'tech_rush' during peacetime.  
  _why:_ retrospective 2248.11.01 _(google:gemini-3.6-flash, 2026-09-26)_

- While 'tech_rush' provides steady growth in tech and economic power, it does not passively improve military power, which may stagnate and fall behind the galactic median without active naval expansion.  
  _why:_ retrospective 2248.11.01 _(google:gemini-3.6-flash, 2026-09-26)_

- When an empire is boxed in early with significantly fewer systems than the galactic median (21 vs 31.5), it will struggle to maintain military and technological parity even with a dedicated 'tech_rush' stance.  
  _why:_ retrospective 2253.10.01 _(google:gemini-3.6-flash, 2026-09-26)_

- Minor basic resource deficits, such as -16 energy per month, can be safely ignored without consolidating the economy if the resource stockpile is large enough (e.g., 26,000) to last for decades.  
  _why:_ retrospective 2253.10.01 _(google:gemini-3.6-flash, 2026-09-26)_

- An extreme amenities deficit on a colony (e.g., -266) must be temporarily ignored when multiple superior empires declare war, as survival via the 'defend' directive takes absolute precedence.  
  _why:_ retrospective 2256.04.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- A massive energy stockpile (e.g., 27,000) allows an empire to sustain the 'defend' directive and ignore minor energy deficits during a multi-front war without being forced to consolidate its economy.  
  _why:_ retrospective 2256.04.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Maintaining the 'defend' directive allows an empire to survive defensive wars against superior foes by winning defensive engagements (18 battles won, 0 lost), but low alloy income (+22.9/month) will prevent rapid military power growth.  
  _why:_ retrospective 2259.05.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Severe planetary amenities deficits (e.g., -244) will continue to worsen while the 'defend' directive is active, leading to critical stability drops (42.6) since the AI focuses entirely on military production.  
  _why:_ retrospective 2259.05.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Minor basic resource deficits during an active defensive war can be safely ignored if stockpiles are large enough, keeping the focus on survival with the 'defend' directive.  
  _why:_ In 2260, a tiny mineral deficit (-0.3/month) and consumer goods deficit (-5.8/month) appeared during massive two-front wars, but mineral stockpile was over 7700 and CG over 4000, allowing the empire to remain in 'defend'. _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Maintaining the 'defend' directive allows an empire to win defensive engagements (18 battles won, 0 lost) against superior forces, even if war exhaustion climbs faster than the enemy's.  
  _why:_ retrospective 2264.01.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Severe planetary amenities deficits (-236) and low stability (52.5) will persist and worsen if the 'defend' directive is held for years to prioritize wartime survival.  
  _why:_ retrospective 2264.01.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- A massive energy stockpile (over 35,000) enables an empire to sustain prolonged defensive wars and fleet upkeep without being forced to switch to 'consolidate_economy'.  
  _why:_ retrospective 2264.01.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Maintaining the 'defend' directive against vastly superior military foes (e.g., 4.2x stronger) can stall a defensive war through defensive victories (33 battles won, 0 lost), even if overall military power remains below the galactic median.  
  _why:_ retrospective 2268.02.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- An ongoing defensive war prevents the AI from addressing extreme domestic deficits, such as a -253 amenities deficit on a planet, leaving stability impaired as long as 'defend' is prioritized.  
  _why:_ retrospective 2268.02.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Low alloy production (+23.1/month) severely limits the speed at which a fleet can be expanded or rebuilt, causing military power to stagnate during an extended defensive war.  
  _why:_ retrospective 2268.02.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Maintaining the 'defend' directive during a prolonged defensive war enables an empire to survive and win engagements (46 won, 0 lost) against enemies with overwhelmingly superior military power (up to 7.9x).  
  _why:_ retrospective 2271.06.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Severe planetary amenities deficits (-142) will persist for decades while the 'defend' directive is active, as the AI continues to deprioritize civilian infrastructure to focus on survival.  
  _why:_ retrospective 2271.06.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- A colony's amenities deficit after a prolonged war (e.g. -128) eases as the war's effects fade, not through a 'consolidate_economy' switch (Las Veredas rebounded after peace in 2235).  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2274.11.01 credited a switch to consolidate_economy

- A 10-year truce after a defensive war provides a safe window to maintain 'tech_rush', allowing an empire to prioritize technological catch-up even if its military power is below half the galactic median.  
  _why:_ retrospective 2274.11.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Maintaining the 'defend' directive against vastly superior forces (over 2x military power) can successfully deter immediate attacks, resulting in zero battles fought and balanced war exhaustion.  
  _why:_ retrospective 2278.10.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- A minor strategic resource deficit, such as -0.9 rare crystals per month, can be safely ignored during a defensive war if the stockpile (429) is large enough to outlast the conflict.  
  _why:_ retrospective 2278.10.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- The 'defend' directive cannot rapidly close a massive military gap (3363 vs 6897 median) if monthly alloy production (+27.7) is too low to support significant fleet expansion.  
  _why:_ retrospective 2278.10.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Maintaining the 'defend' directive successfully preserves territory and keeps war exhaustion manageable (29% over 6 years) against a superior alliance, provided defensive engagements are won.  
  _why:_ retrospective 2283.10.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- A minor strategic resource deficit (e.g., -0.9 rare crystals/month) can be safely ignored to maintain a survival-critical directive like 'defend' when the stockpile is large enough to last decades.  
  _why:_ retrospective 2283.10.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Prolonged reliance on the 'defend' directive ensures survival but leads to stagnant military growth (+4.08 over 5 years) and causes the empire to remain behind the galactic median in technology and economy.  
  _why:_ retrospective 2283.10.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Maintaining the 'defend' directive against a superior alliance effectively preserves territory and balances war exhaustion, provided defensive engagements are won.  
  _why:_ retrospective 2291.11.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- A minor strategic resource deficit (e.g., -0.9 rare crystals/month) can be safely ignored to maintain a survival-critical directive when the stockpile is sufficient to last decades.  
  _why:_ retrospective 2291.11.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Low monthly alloy income severely limits an empire's ability to increase military power during a prolonged defensive war, often leaving it below the galactic median.  
  _why:_ retrospective 2291.11.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Maintaining the 'defend' directive during a defensive war allows an empire to outlast superior alliances by winning defensive battles, successfully pushing enemy war exhaustion higher (81%) than its own (64%).  
  _why:_ retrospective 2296.03.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Prolonged use of the 'defend' directive during a war halts technological progress (+0 tech power over 5 years), causing the empire to fall further behind the galactic median in research.  
  _why:_ retrospective 2296.03.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Maintaining the 'defend' directive during a defensive war pushes enemy war exhaustion towards 100% (currently 89%) while winning engagements (13 won, 0 lost), despite minor strategic resource deficits.  
  _why:_ In 2298, the defensive war against the Najklax/United alliance continued. Enemy war exhaustion reached 89%, while ours was 64%, showing that the 'defend' directive effectively protects the empire and wins the war of attrition. _(google:gemini-3.1-pro-preview, 2026-09-26)_

- When a defensive war ends, utilizing the resulting truce period to switch to 'tech_rush' safely prioritizes technological and economic development without immediate military threats.  
  _why:_ retrospective 2300.07.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- A minor strategic resource deficit (e.g., -0.9 rare crystals per month) can be safely ignored to maintain a high-priority directive like 'tech_rush' if the stockpile is sufficient to last for decades.  
  _why:_ retrospective 2300.07.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- While 'tech_rush' improves research output, it does not rapidly close a severe military power gap (e.g., 2530 vs 8625 median) in the short term.  
  _why:_ retrospective 2300.07.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- When shielded by truces from vastly superior hostile neighbors (e.g., 9.4x military power), maintaining 'tech_rush' safely builds technological capacity without risking immediate attack.  
  _why:_ retrospective 2305.07.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Maintaining the 'tech_rush' directive with low alloy income (+33.8/month) will cause military power to stagnate (+0 over 5 years), failing to close a significant gap with the galactic median.  
  _why:_ retrospective 2305.07.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- A minor strategic resource deficit, such as -0.9 rare crystals per month, can be safely ignored to maintain 'tech_rush' if the stockpile (134) provides a sufficient buffer.  
  _why:_ retrospective 2305.07.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Prolonged reliance on the 'tech_rush' directive without active naval expansion can cause military power to stagnate entirely (+0 over 5 years), leading the empire to fall further behind the galactic median despite a growing alloy stockpile.  
  _why:_ retrospective 2310.07.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- A minor strategic resource deficit, such as -0.9 rare crystals per month, can be safely ignored for over a decade if the initial stockpile is large enough, allowing the empire to maintain its strategic focus.  
  _why:_ retrospective 2310.07.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- When facing multiple overwhelmingly superior enemies in defensive wars, survival dictates holding the 'defend' directive, even if low alloy production severely limits actual military power growth.  
  _why:_ retrospective 2314.07.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- A minor rare crystals deficit (-0.9/month) can be safely ignored to maintain the 'defend' directive during a multi-front defensive war.  
  _why:_ retrospective 2314.07.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- When military power is less than half the galactic median and alloy income is low, relying on a federation ally is critical to surviving wars against neighbors with massively superior fleet power.  
  _why:_ retrospective 2314.07.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Minor energy or strategic resource deficits (e.g., -11.6 energy, -1.8 rare crystals) can be safely ignored to maintain a critical directive like 'defend' during a two-front war if stockpiles are massive (e.g., 56,000 energy).  
  _why:_ retrospective 2318.02.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Maintaining the 'defend' directive allows an empire to survive multi-front wars against vastly superior forces (up to 8.5x stronger) by winning defensive engagements (29 won, 0 lost) and keeping war exhaustion manageable.  
  _why:_ retrospective 2318.02.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Relying on a federation ally can successfully split enemy attention, enabling a weaker empire to hold the line in a defensive war even if its own military power remains below half the galactic median.  
  _why:_ retrospective 2318.02.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- While 'expand' successfully prioritizes colonization, it can cause system claiming to stagnate if early alloy production is consumed by colony ships.  
  _why:_ retrospective 2206.09.01 _(google:gemini-3.7-flash, 2026-09-26)_

- Amenity deficits (e.g. -92) and housing shortages on new colonies clear as the colonies grow, under any directive; they do not call for 'consolidate_economy'.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2206.09.01 said they necessitate consolidate_economy

- Housing and amenity deficits after rapid expansion sit on new colonies and clear as they grow, under any directive; their clearing is no evidence for 'consolidate_economy'.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2211.09.01 credited consolidate_economy with clearing them

- A new colony's early amenities deficit (e.g. -119 to +93 in 14 months) clears as the colony grows, under any directive; it is no evidence for 'consolidate_economy'.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): new colonies cleared their deficits under every directive

- Territorial expansion can still progress under the 'consolidate_economy' directive (e.g., +3 systems) if sufficient influence and alloys allowed outposts to be queued prior to the stance change.  
  _why:_ retrospective 2218.04.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

- Bordering a genocidal empire (such as a Devouring Swarm) with overwhelming military superiority (e.g. 3.7x) necessitates switching to 'defend' before war is declared to fortify chokepoint starbases.  
  _why:_ retrospective 2223.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A steady consumer goods deficit of ~7/month can be safely sustained under 'tech_rush' without compromising colony stability (>71 on all planets) provided a stockpile buffer of over 500 units exists.  
  _why:_ retrospective 2228.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Maintaining the 'defend' directive against a vastly superior Devouring Swarm (initially 3564 vs 898 military power) can successfully stall the invasion and narrow the power gap (to 2198 vs 1596) by winning defensive engagements.  
  _why:_ retrospective 2234.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Minor consumer goods deficits (e.g., -3.8/month) can resolve naturally during a prolonged 'defend' stance as populations shift, without needing to switch to 'consolidate_economy'.  
  _why:_ retrospective 2234.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Holding 'defend' while enemy war exhaustion (46%) trails ours (52%) and we are winning battles (1-0) with no deficits keeps pushing the war toward a forced peace; stay the course rather than switching.  
  _why:_ 2236.02: military parity (1.2x enemy), battles 1-0, exhaustion ours 52%/theirs 46%, no resource deficits, alloys piling +21.6/mo. _(google:gemini-3.8-flash, 2026-09-26)_

- When a defensive war's exhaustion stays higher on our side (79% vs 73%) despite winning every battle (4-0), expect a status-quo peace forced at 100% rather than our own war goal, and plan the post-war directive for that date.  
  _why:_ retrospective 2240.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Switching to 'expand' with available influence and alloys successfully captures multiple systems per year (e.g., +4 systems in 12 months) immediately following a defensive war.  
  _why:_ retrospective 2244.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When unclaimed systems lie within 2 jumps and construction ships are available, keep or return to 'expand', because outposts are limited by influence and alloys, not by naval-capacity techs.  
  _why:_ retrospective 2250.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- 'tech_rush' does not steer the AI toward particular techs: five years of it (2245–2250) did not produce Doctrine: Support Vessels, Interstellar Logistics or Orbital Habitats, so do not hold it waiting for a specific tech once our tech count is already at or above the median (78 vs 76).  
  _why:_ retrospective 2250.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Relying on a federation ally during the 'defend' directive allows a weaker empire to survive a multi-front war against superior foes, winning early battles (1 won, 0 lost) and keeping war exhaustion balanced (5% vs 6%).  
  _why:_ retrospective 2255.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- During a long defensive war, if alloy net income falls to around zero (+1.8 a month here, down from +32), holding defend does not rebuild military power: ours fell from 945 to 255 in three years while every battle was won. Keep defend for survival, but treat alloy income as the thing to fix the moment the war allows.  
  _why:_ retrospective 2258.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A clean battle record (9-0) and favourable war exhaustion (18% vs 21%) do not mean territory is safe. We lost 3 systems during the war, so check systems owned, not only battles, when judging whether defend is holding.  
  _why:_ retrospective 2258.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Relying on a strong federation ally while holding the 'defend' directive enables a weaker empire to survive multi-front defensive wars against vastly superior enemies by winning joint defensive engagements (27-0), even if its own military is depleted.  
  _why:_ retrospective 2263.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Prolonged defensive wars without sufficient alloy income (+5.0/month) cause an empire's own military capacity to collapse to zero, completely stalling its ability to rebuild independently of its allies.  
  _why:_ retrospective 2263.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A perfect defensive battle record (e.g. 23-0 and 16-0) does not mean territory is safe: systems fell 21→13 in four years under defend, so judge a defensive war by systems lost and each side's exhaustion trend, not by battles won.  
  _why:_ retrospective 2268.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Under defend with alloy income near zero (+0.9/month), military power stops growing (+0 in 12 months) even though the war budget favours ships. The directive cannot close the gap without alloy production, so fixing alloys must be the first step once the wars allow it.  
  _why:_ retrospective 2268.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- In a two-front defensive war, the front where our exhaustion is rising faster than the enemy's (Lyrite 48% vs 40%, against an absorption war goal) is the one that decides survival, even if the other front is being won on exhaustion.  
  _why:_ retrospective 2268.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A minor minerals deficit (~-26/month) with a large stockpile (5161, ~16 months buffer but still growing shortfall) during an active defensive war does not warrant leaving 'defend': war exhaustion is close (59% ours vs 50% theirs) and the enemy still has 7x our military, so survival stays the priority.  
  _why:_ 2270.04.01 briefing: minerals -26.4/month, stock 5161 (~16mo buffer), war exhaustion ours 59% vs theirs 50%, enemy military 7368 vs ours 1055 (7x), battles 20 won/0 lost — still an active existential war. _(google:gemini-3.8-flash, 2026-09-26)_

- The 'consolidate_economy' directive can steadily reduce basic resource deficits (e.g., improving a mineral deficit from -32.8 to -21.0 over 12 months) without halting population growth or minor territorial expansion.  
  _why:_ retrospective 2271.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When an empire is boxed in with no colonisable planets, lacking alternative growth paths like Orbital Habitats causes it to fall severely behind the galactic median in pops and economy.  
  _why:_ retrospective 2271.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a defensive war stays at 0 battles and war exhaustion below 10% on both sides for over a year, the 'defend' directive only preserves the status quo; the fleet is at its naval-capacity cap, so defend cannot grow military power, and the time is better spent planning the switch to tech_rush for the capacity and habitat techs once the war ends.  
  _why:_ retrospective 2276.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A fleet at its naval-capacity cap (84/84) with low alloy income (+31/month) loses military power under 'defend' (-58 in 12 months), because extra alloy budget cannot buy ships beyond the cap.  
  _why:_ retrospective 2276.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Maintaining the 'defend' directive during a defensive war with a federation ally successfully stalls stronger enemies (up to 4.6x military power), keeping war exhaustion balanced over several years.  
  _why:_ retrospective 2281.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A modest alloy income (+41.7/month) under the 'defend' directive provides steady but slow military growth (+194 in 12 months), which struggles to quickly close a large gap with the galactic median.  
  _why:_ retrospective 2281.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When at war with the fleet at naval capacity (147/147) and alloy income low (+26/month), 'defend' preserves territory and wins defensive battles (5-0) but cannot close a military gap (2721 vs median 5865); the gap only closes after peace, through naval-capacity and ship techs.  
  _why:_ retrospective 2284.04.01 _(google:gemini-3.8-flash, 2026-09-26)_

- In a long defensive war where exhaustion climbs slowly on both sides (about 4 points a year, 37% vs 42% after 10.5 years), do not plan on a forced peace; the plan has to assume the war lasts decades and keep the defensive posture solvent.  
  _why:_ retrospective 2284.04.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Two-front defensive war with federation ally: winning battles (13-0, 2-0) and enemy exhaustion higher or close on both fronts (Lyrite theirs 19% vs ours 23%; UNE/Tarassi theirs 51% vs ours 46%) means hold 'defend' even while falling below half the galactic military median — do not switch to prepare_war or tech_rush mid-war.  
  _why:_ 2286.11: military 2802 vs median 5715 (FALLING BEHIND) but both wars show us winning every battle and enemy exhaustion at or above ours; alloys still positive (+25.9/mo) and no systems lost this period beyond -1 (likely front adjustment). Federation ally United Oklarr Union still allied. _(google:gemini-3.8-flash, 2026-09-26)_

- When a fleet is capped at naval capacity (147/147) with low alloy income (+19.9/month), maintaining the 'defend' directive preserves territory and wins defensive battles but cannot close a severe military power gap (2651 vs 7201 median) without capacity-increasing technologies.  
  _why:_ retrospective 2289.04.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A severe housing and amenities deficit (e.g., -542 housing, -166 amenities) leading to sub-50 stability can develop on a colony during a long defensive war, but survival against overwhelmingly superior foes (8.3x military) takes absolute precedence over consolidating the economy.  
  _why:_ retrospective 2289.04.01 _(google:gemini-3.8-flash, 2026-09-26)_

- In a two-front defensive war where every battle is won and enemy exhaustion rises faster than ours (UNE/Tarassi +8 points a year against our +6, Lyrite +8 against our 0 over 2293–2294), keep 'defend' and plan around the date the enemy reaches 100%, not around closing the military gap.  
  _why:_ retrospective 2294.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Holding 'defend' for about five years while alloy income falls below +20 a month shrinks the fleet (157 to 142, military 2861 to 2599) even with every battle won, so 'defend' alone will not rebuild the military.  
  _why:_ retrospective 2294.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A colony whose amenities deficit is left alone during a long war keeps getting worse (Arnvoss stability 15.7 to 0, amenities -253 to -422 in about two years). The longer it waits, the bigger the repair job once peace comes.  
  _why:_ retrospective 2294.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Winning every defensive fleet engagement (e.g., 58-0) against overwhelmingly superior foes does not guarantee territorial integrity, as enemies can still occupy systems and colonies if their numerical advantage allows them to bypass defenders.  
  _why:_ retrospective 2298.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- An empire can transition immediately from a decades-long 'defend' stance to 'tech_rush' without needing to consolidate its economy if all basic resource nets remain positive and stockpiles are large.  
  _why:_ retrospective 2298.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A low-intensity defensive war (4 battles in 3 years, exhaustion rising about 4 points a year on each side) does not stop the AI from claiming systems under 'defend' (+3 systems in the first year), so keep 'defend' rather than switching to 'expand' while a stronger swarm is still at war with us.  
  _why:_ retrospective 2302.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A 19-month 'tech_rush' truce window (2298.02 to 2299.09) gave only +1 tech and did not produce Orbital Habitats, so a short truce is not enough to reach a specific growth tech; plan growth on the assumption that the tech arrives late.  
  _why:_ retrospective 2302.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Despite winning every defensive battle (18-0) and keeping war exhaustion balanced (22% vs 21%), an empire can still lose territory (systems dropped 19 to 16) in a defensive war against an overwhelmingly superior devouring swarm.  
  _why:_ retrospective 2305.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A critical basic resource deficit, such as -133 minerals/month with only an 8-month buffer, must be ignored in favor of the 'defend' directive when facing an active existential war.  
  _why:_ retrospective 2305.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When an empire's fleet is at its naval capacity cap (127/127), the 'defend' directive cannot close a massive military gap (4102 vs 32248) despite a positive alloy net.  
  _why:_ retrospective 2305.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Existential defensive war (20 won/0 lost, exhaustion ours 25% vs theirs 24%, federation ally engaged) still requires holding 'defend' even with military 4002 vs median 8088 and alloy deficit; the war, not the median gap, decides survival. Only consider switching once war exhaustion approaches forced peace or systems keep falling.  
  _why:_ 2305.11: war ongoing since 2299, 20-0 battle record, exhaustion nearly tied (25/24%), systems down 3 in 12 months but ally holding federation; alloys -0.5/mo deficit tiny vs 170 stock, minerals -146/mo deficit against 5058 stock (~34mo buffer). _(google:gemini-3.8-flash, 2026-09-26)_

- A flagged deficit whose stockpile has held flat or grown across several briefings (minerals 1086 in 2305.03, 1227 in 2307.02, despite -158 a month shown) is being covered and does not by itself justify leaving 'defend'. Judge a deficit by the stock trend over 12 or more months, not by one month's net.  
  _why:_ retrospective 2307.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- In a slow war of attrition against a devouring swarm 10x our military, 'defend' plus a federation ally holds the core and wins every battle (23-0) but still bleeds border systems (21 to 15 in about 3.5 years). Expect to keep losing territory, and use the ally's truce and war status rather than our own fleet as the real shield.  
  _why:_ retrospective 2307.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- In a long defensive war with minerals falling steadily (-159/month, stock 855, ~5 months buffer) and consumer goods also in deficit (-46.9/month, but huge stockpile), while war exhaustion still favors us (26% vs theirs 35%) and battles are 32-0, the mineral crash risk to alloy/consumer-goods output justifies a temporary switch to consolidate_economy per the standing plan, even though the war continues.  
  _why:_ 2309.02: minerals 855 (-159/month) is well under the plan's 600 floor trigger threshold trend and dropping fast; alloys barely positive (+1.0/month) so a mineral crash would stall ship replacement entirely. _(google:gemini-3.8-flash, 2026-09-26)_

- Temporarily switching to the 'consolidate_economy' directive can successfully repair a severe basic resource deficit (e.g., minerals from -159/mo to +7.8/mo) following a long defensive war.  
  _why:_ retrospective 2311.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Having maximum influence (1000) and multiple construction ships under the 'expand' directive does not guarantee rapid territorial growth if nearby unclaimed systems are not yet surveyed.  
  _why:_ retrospective 2311.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A minor volatile_motes deficit (-0.6/month) with a large stockpile (2754, ~4600 months of buffer) is negligible and does not warrant leaving 'defend' during an active multi-front defensive war with low (4-6%) war exhaustion on both sides and a winning battle record (8-0).  
  _why:_ 2314.09.01 briefing: volatile_motes -0.6/month vs stock 2754, while war continues (exhaustion 4% vs 6%, 8 battles won 0 lost) against a coalition up to 7.8x our military; federation ally Oklarr and associate Makaru Hive still active. _(google:gemini-3.8-flash, 2026-09-26)_

- When expand is active and influence sits at its cap (1000) with idle construction ships but systems grow by only about 1 in 3 years, the constraint is unsurveyed or unreachable targets (here only 2 of 5 surveyed). Treat surveying as the bottleneck and do not credit the directive for growth that is not happening.  
  _why:_ retrospective 2314.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- In a coalition defensive war where exhaustion rises only 2–3 points a year on each side (4% vs 6% after 25 months), plan for a war lasting a decade or more, and judge the plan by systems held each year (16→13 here) rather than by the battle record (8-0).  
  _why:_ retrospective 2314.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Hold 'defend' while war exhaustion stays favourable (ours 13% vs theirs 19%) and battle record is clean (9-0), even with an active four-front subjugation war against much stronger enemies (up to 5.8x); alloy income +17.4/month is low but the federation (Oklarr ally) is holding the line.  
  _why:_ 2318.09: exhaustion ours 13%/theirs 19%, battles 9-0, systems +1 in 12 months (16 total), no basic resource deficits, idle stockpiles (energy/minerals/food/CG) cover any shortfall for years. _(google:gemini-3.8-flash, 2026-09-26)_

- Maintaining the 'defend' directive allows an empire to stall a vastly superior coalition (up to 8.3x military power) and maintain favorable war exhaustion (16% vs 22%) by leaning on a strong federation ally.  
  _why:_ retrospective 2319.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Extended defensive wars against superior foes cause an empire to fall severely behind the galactic median in economy (1290 vs 3428) and military power, even if territory is successfully preserved.  
  _why:_ retrospective 2319.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- In a defensive war where enemy war exhaustion rises only about 3 points a year (22% to 37% over 2319–2324) while ours rises about 2, do not wait for a forced peace to start growth: plan for 15-20 more years of war and look for growth that works during 'defend' (habitats, capacity techs) instead of putting it off until peace.  
  _why:_ retrospective 2324.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Holding 'defend' with large idle stockpiles (22k energy, 26k consumer goods) but only about +20 alloys a month and the fleet at 106/106 capacity grows military by about 1k a year at best and does not stop systems being lost (16 to 13). Alloy income and naval capacity, not the directive, cap our defence.  
  _why:_ retrospective 2324.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A severe planetary housing deficit (e.g., -800) can be temporarily ignored to maintain the 'defend' directive if planet stability remains above 50 during an existential two-front war.  
  _why:_ retrospective 2329.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Maintaining the 'defend' directive during a declared crisis war allows an empire to absorb initial battle losses (0-3) without immediately losing systems, provided federation allies are present.  
  _why:_ retrospective 2329.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- In a multi-front defensive/crisis war holding at 14 systems with battles won 10-0 on the subjugation front but 0-8 lost on the crisis front (Lyrite), and exhaustion ours 41%/theirs 57% on the winnable front, keep 'defend': the federation ally (Oklarr, 1.2x) and low own exhaustion mean survival is holding even though military power (5474) is far below median (12136).  
  _why:_ 2331.07.01 briefing: two active wars, one won on points (exhaustion 41% vs 57%, 10-0 battles), one being lost against the crisis (0-8 battles) but no systems lost in 12 months (systems +0); alloys still net positive (+36/mo) despite falling stock, no critical deficits threaten survival. _(google:gemini-3.8-flash, 2026-09-26)_

- In a war with a declared crisis, war exhaustion hardly moves (1% on each side after 3 years, despite 8 battles lost), so it will never force a peace: judge that front only by systems and colonies lost.  
  _why:_ retrospective 2331.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Holding 'defend' through multi-year wars froze tech progress completely (141 techs, +0 in each of two 12-month windows) while peers reached a median of 171. Treat the tech gap as the main cost of every extra year at war, and weigh a status-quo peace on a front that has stalled.  
  _why:_ retrospective 2331.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When facing a declared crisis (Devouring Swarm) that has 6.9x more military power, the 'defend' directive alone cannot prevent system losses if allies do not secure the border.  
  _why:_ In 2332, despite holding defend, we lost 4 systems and 79 pops over 12 months while losing 14 battles to the Lyrite Tide. _(google:gemini-3.8-flash, 2026-09-26)_

- Maintaining the 'defend' directive during a multi-front war allows a weaker empire to push enemy war exhaustion up to 68% and win defensive engagements (17-0) on a subjugation front, even while losing battles (0-57) on a crisis front.  
  _why:_ retrospective 2335.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Severe planetary amenities deficits (e.g., -576) and housing shortages (-79) will manifest during a prolonged 'defend' stance as the AI neglects civilian infrastructure for military survival.  
  _why:_ retrospective 2335.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Minor strategic resource deficits, such as -0.4 exotic gases per month, can be safely ignored to maintain a survival-critical directive when the stockpile (2290) is large enough to last decades.  
  _why:_ retrospective 2335.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- In a crisis war where we lose every battle (0-111) and exhaustion stays near 4% on both sides for years, the war will not end through exhaustion. Judge 'defend' by whether systems and pops are held, not by battles or exhaustion, and expect fleet losses as long as the fleet engages.  
  _why:_ retrospective 2339.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When enemy war exhaustion climbs only about 2.5 points a year (66% in 2334 to 80% in 2339), a forced status-quo peace is 7+ years away. Plan the directive for years of war, not a near-term peace.  
  _why:_ retrospective 2339.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Holding 'defend' for 4+ years while a colony has stability below 10 (Largoll 6.5, amenities -1279) does not repair it, and neither does a consolidate_economy window: no directive clears grown-colony deficits. At war a colony under stability 25 enters the war crisis (C6), whose steps act on the war.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2339.06.01 called a 12-month consolidate_economy window the only lever

- Maintaining the 'defend' directive alongside a strong federation ally allows a severely outmatched empire (e.g., 5k vs 44k fleet power) to hold territory and steadily drive enemy war exhaustion toward 100% (currently 91%) through defensive victories (35-0).  
  _why:_ retrospective 2343.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- An extreme planetary amenities deficit (e.g., -711) and low stability (37.6) can persist for years without triggering an immediate rebellion, allowing an empire to maintain a survival-critical 'defend' stance during multi-front wars.  
  _why:_ retrospective 2343.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- In a multi-empire crisis war where war exhaustion stays under 10% on both sides for more than 15 years (7%/7% after 19 years), never plan on a forced peace; judge whether to leave 'defend' by systems lost and the military trend over the last 12 months.  
  _why:_ retrospective 2347.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When 'defend' shows a large drop in military power (-2012 in 12 months, battles 0 won / 142 lost) while systems stay flat, the posture is losing ships without protecting territory. If no system was lost that year and truces cover the other hostile neighbours, it is time to move to growth directives.  
  _why:_ retrospective 2347.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When supported by a massive galactic coalition in a declared crisis war, temporarily switching to 'tech_rush' can safely surface critical bottleneck technologies (like Orbital Habitats) without losing territory, even if the enemy is 5.8x stronger.  
  _why:_ retrospective 2352.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Relying on a strong federation and galactic coalition while holding 'defend' allows a vastly outmatched empire to preserve its systems and keep war exhaustion manageable (8%) despite losing all defensive engagements (162 lost) against a Devouring Swarm.  
  _why:_ retrospective 2352.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Against a crisis or Devouring Swarm neighbour fought inside a galactic coalition, holding 'defend' let the gap close from 5.8x to 2.3x in five years (ours 7.6k→12.4k, theirs 44.3k→28.3k) even with every battle lost (0-176), at a cost of about 1 system every two years.  
  _why:_ retrospective 2357.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A crisis war whose exhaustion stays near 10% on both sides after decades (2328–2357) will not end by forced peace. Decide when to leave 'defend' by the enemy's military ratio and our recent system losses, not by the war ending.  
  _why:_ retrospective 2357.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Leaving 'defend' while the swarm still out-guns us about 5x (the 2351 tech_rush year) cost 2 systems and 792 military power. Wait until the ratio is clearly lower before switching to research.  
  _why:_ retrospective 2357.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a vastly superior hostile neighbor's military power collapses below parity (e.g., 0.8x) due to a galactic crisis declaration, switching from 'defend' to 'tech_rush' safely allows an empire to resume technological development without losing territory.  
  _why:_ retrospective 2361.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A negligible strategic resource deficit, such as -1.7 exotic gases per month, can be safely ignored to maintain a required directive if the stockpile provides over a century of buffer.  
  _why:_ retrospective 2361.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Minor consumer goods and strategic resource deficits can be safely ignored to focus on technological progression if the stockpiles are massive enough to last decades.  
  _why:_ At 2364.03.01, a -25.4 CG deficit and -0.8 exotic gases deficit were ignored because stockpiles were 33k and 2.5k respectively, allowing a switch to tech_rush. _(google:gemini-3.8-flash, 2026-09-26)_

- In a multi-empire crisis war, a lopsided battle count for our side (0 won / 207 lost, barely changing while no system is lost) does not measure our own front; judge the war by systems lost, the enemy's military ratio and exhaustion, and do not switch to defend because of that count alone.  
  _why:_ retrospective 2366.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When expand has room (4 unclaimed systems 1 jump away) and influence is capped at 1000 but alloy income is near zero (+4.4/month, 517 stock), systems do not grow (+0 in 12 months); alloy income, not the directive, is the constraint and must be fixed first.  
  _why:_ retrospective 2366.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A consumer goods deficit of about -67/month on a 32,000 stock (about 40 years of buffer) is not a reason to change directive.  
  _why:_ retrospective 2366.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When an awakened marauder crisis appears with overwhelming military superiority (e.g., 362k), holding the 'defend' directive correctly prioritizes border fortifications and survival over resolving civilian deficits.  
  _why:_ retrospective 2369.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A massive civilian stockpile (e.g., 27k consumer goods) allows an empire to sustain severe deficits (-115/mo) while holding a survival-critical stance like 'defend' during a prolonged crisis.  
  _why:_ retrospective 2369.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a fleet is at its naval capacity cap (259/259) with low alloy income (+18.5/mo), the 'defend' directive cannot significantly increase military power, leading to stagnation against escalating galaxy-level threats.  
  _why:_ retrospective 2369.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a crisis's military power stays the same for years, it never enters our space and we lose nothing, holding 'defend' only freezes research and lets deficits grow (2369–2374: techs +1, consumer goods stock 30k→20k). Switch to 'consolidate_economy' instead: the crisis rule allows it, and 'defend' can come back if an urgent line shows crisis fleets at our border.  
  _why:_ retrospective 2374.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When influence sits at its cap (1000) with unclaimed systems within 2 jumps and construction ships idle, neither influence nor alloys are blocking expansion. The stagnant system count (+1 in 5 years) comes from the directive, so a short 'expand' spell is justified once the economy and threats allow it.  
  _why:_ retrospective 2374.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When influence is capped (1000) with unclaimed systems 1-2 jumps away and sufficient alloy stockpiles, switch to 'expand' to claim territory, as large consumer goods stockpiles (>10 years) can easily absorb temporary deficits.  
  _why:_ In 2378.01, holding consolidate_economy for 36 months left influence capped at 1000 with 5 unclaimed systems adjacent and 739 alloys, while 14012 consumer goods stockpile provided over 10 years of runway despite a -114/month net. _(google:gemini-3.8-flash, 2026-09-26)_

- When switching to 'expand' with capped influence and idle construction ships, territorial expansion will still be delayed if the target systems are unsurveyed, as the AI must route science ships to explore them first.  
  _why:_ retrospective 2379.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When `expand` has been active for 2 or more years with influence capped, alloys available and idle construction ships, but systems owned stay flat and the count of surveyed unclaimed systems does not change, treat those systems as unreachable and leave `expand`. The Expansion room line alone is not a reason to hold it (2378–2383: 0 systems gained, 1 of 4 surveyed throughout).  
  _why:_ retrospective 2383.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A consumer goods deficit of about -115 a month that survived three years of `consolidate_economy` (-161 → -114) and then resumed under `expand` shows that leaving consolidation with a structural deficit just burns the stockpile (16.7k → 6.3k). Hold `consolidate_economy` until the net is near zero or positive, not merely smaller.  
  _why:_ retrospective 2383.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- The capital's amenities collapse (Theia at -5,394 amenities, stability 16.9 on 2383.05) came during a war, and the capital was lost two months later with a third of its pops: a switch to `consolidate_economy` would not have repaired it. A colony under stability 25 at war enters the war crisis (C6).  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2383.05.01 called it the clearest sign to return to consolidate_economy

- Holding 'consolidate_economy' successfully resolves an alloy deficit (recovering to +6.2/month) and supports military (+916) and economic power growth (+71.4) over 12 months, but large consumer goods deficits (-65.7/month) require multiple years to fully balance.  
  _why:_ Between 2386.07 and 2387.07, consolidate_economy stabilized alloys to +6.2/month and grew military power by +916, while consumer goods remained in deficit at -65.7/month (stock 2007), showing that specialist resource stabilization takes longer than basic resources. _(google:gemini-3.8-flash, 2026-09-26)_

- The `consolidate_economy` directive can successfully eliminate basic resource deficits, such as turning a -14.8/month alloy shortfall into a positive +6.2/month net within a year.  
  _why:_ retrospective 2387.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A severe localized amenities deficit (e.g., -399 on a single planet) is no reason to hold or return to `consolidate_economy`, with or without fast pop growth: no directive repairs grown-colony amenity deficits (+5 to +14 amenities a planet-year under it). The Planet check line names the colony; under stability 25 it is urgent.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2387.07.01 blamed rapid pop growth for a deficit the directive would otherwise repair

- Leaving `tech_rush` for 12 months to stabilize the economy results in negligible tech growth (+60 tech power, 1 tech known) but allows military and economic power to recover safely.  
  _why:_ retrospective 2387.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When tech_rush has run for more than a year with techs known unchanged (180 → 180) and the wanted tech (Orbital Habitats) is not among the options, stop holding it for that tech; move to a directive that uses the resources we actually have.  
  _why:_ retrospective 2390.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When influence is stockpiled (over 900) and the briefing shows unclaimed systems within 2 jumps with construction ships free, choose expand over tech_rush even when we are boxed in on colonisable planets, because outposts are the growth that is still possible.  
  _why:_ retrospective 2390.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Under 'consolidate_economy' an extreme amenities deficit moved only from -366 to -322 in 3 years (+15 a year): the directive does not repair it, so do not hold it for amenities.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2394.01.01 read that as a slow repair

- Extreme amenities deficits on planets with massive populations are not repaired by 'consolidate_economy', slowly or otherwise: no directive repairs grown-colony amenity deficits (+5 to +14 amenities a planet-year under it, 2 of 63-70 year-long intervals cleared). Do not hold it for them.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2394.01.01 said they resolve very slowly under a dedicated consolidate_economy directive

- If consolidate_economy has been held for several years and a deficit keeps getting deeper (consumer goods went from -19 to -32 a month over 7.5 years) while the stockpile covers more than 100 months, leave the directive: it is not fixing that deficit, and holding it only costs growth.  
  _why:_ retrospective 2398.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When influence sits at its cap (1000) and unclaimed systems remain within 2 jumps, pick expand even if a small deficit with a long buffer remains, because influence at the cap is wasted income.  
  _why:_ retrospective 2398.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Maintaining the 'tech_rush' directive increases tech power and pop growth but can worsen consumer goods deficits as the AI prioritizes research jobs and infrastructure.  
  _why:_ retrospective 2403.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- An awakened fallen empire that does not border us and is not at war with us is not a reason to hold `defend` for years. Here, 24 months of `defend` added only about 2% military (+634) and no tech power, because alloy income (+12.9 a month) limits ship building, while the tech gap to the median stayed at about 21.  
  _why:_ retrospective 2408.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When we already have Orbital Habitats but no colonisable planets and few reachable systems, `expand` does not produce habitats by itself. From 2399 to 2402 it gave +0 planets and +0 systems while influence sat at its 1000 cap, so growth has to come from techs and pops rather than from waiting on `expand`.  
  _why:_ retrospective 2408.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A negligible alloy deficit (e.g. -0.7/month) with a substantial stockpile (932, over 110 years of runway) does not warrant abandoning 'tech_rush' for 'consolidate_economy', as the stockpile will not be exhausted within 12 months.  
  _why:_ In 2411.06, alloys net flipped to -0.7/month but with 932 in storage (1331 months of buffer), consumer goods at +66.0, and stability high across worlds. The deficit rule only requires consolidation when a stockpile will deplete within ~12 months. _(google:gemini-3.8-flash, 2026-09-26)_

- The AI will successfully construct orbital habitats to restart population growth under the 'tech_rush' directive once the technology is unlocked, without requiring a specific expansion stance.  
  _why:_ retrospective 2413.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- An overwhelming military threat from an awakened fallen empire (e.g., 1.1 million fleet power) is best handled passively with 'tech_rush' and federation diplomacy as long as they remain unprovoked and do not declare war.  
  _why:_ retrospective 2413.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A hostile neighbor with more than double our military power can be safely ignored under 'tech_rush' as long as an active truce prevents immediate attack and federation allies provide a strong deterrent.  
  _why:_ retrospective 2413.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When research income is very low (about 300 a month in total) and tech_rush has added only 3 techs in 7 years (193 to 196), holding tech_rush will not close the gap. Switch to a directive with a clear target the briefing can measure, such as unclaimed systems or deficits.  
  _why:_ retrospective 2417.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When systems have been flat for decades but the Expansion room line shows unclaimed systems within 2 jumps, construction ships are free and influence has built up (856), return to expand instead of staying on tech_rush: the priority order puts expand above tech_rush.  
  _why:_ retrospective 2417.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- The 'consolidate_economy' directive cannot resolve extreme planetary amenity deficits (e.g., -500 to -900) when caused by massive overpopulation on small colonies like size 6 habitats, because the limited building slots cannot provide enough jobs.  
  _why:_ retrospective 2421.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When an AI empire is trapped trying to fix unresolvable amenities deficits due to physical planet size limits, it is better to switch directives and rely on stockpiles rather than holding 'consolidate_economy' indefinitely.  
  _why:_ retrospective 2421.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a stockpile falls faster over 12 months than its monthly net predicts (minerals 4811 → 1915 while the net read -72 a month), judge the runway by the observed drop, not the net. Switch to consolidate_economy once that observed rate gives less than about 12 months.  
  _why:_ retrospective 2425.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Consolidate_economy did not fix amenities deficits on size-6 habitats: Krail got worse from -725 to -896 over two years under it and reached -1045 later. Do not hold consolidate_economy only for habitat amenities while stability stays at 55 or above. Use it for real resource deficits.  
  _why:_ retrospective 2425.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- With research income around +350 a month and techs costing about 10,000 points, tech_rush gained only 3 techs in 45 months (199 → 202). A tech gap then closes too slowly to justify holding tech_rush while a basic resource is running out.  
  _why:_ retrospective 2425.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- 'consolidate_economy' steadily improves basic resource deficits, but it does not repair habitat amenity deficits (-1093 to -1009 in four years): do not hold it for them.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2430.02.01 read that as a slow repair

- Seven years of consolidate_economy (2426–2433) cut the mineral deficit from -67 to -9/month but made size-6 habitat amenities worse (Krail -1,093 to -1,227), so don't hold consolidate_economy waiting for habitat amenities to recover once basic resource deficits are small.  
  _why:_ retrospective 2433.10.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When research income is only about 100–175 a month per area against tech costs of 4,500–6,300, techs arrive at about 1 a year whatever the directive, so plan growth-tech milestones in years, not months.  
  _why:_ retrospective 2433.10.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A crisis war where the enemy has 0 military and over 700% exhaustion can stay open for decades without a peace event, so treat it as ended when choosing directives instead of waiting for it to close.  
  _why:_ retrospective 2433.10.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A minor alloys deficit (-11/month) with over 1000 stock plus energy/trade stockpiles that dwarf needs does not require leaving tech_rush when at war against a crippled foe (theirs 818% exhaustion, 0 fleet) and protected by a strong federation/alliance ally.  
  _why:_ 2436.03: alloys -11/month with 1076 stock (~8yr buffer at current rate but check minerals also -14.5 with 2010 stock); war against Teeming Lyrite Tide who have 0 military and 818% exhaustion (we are winning the crisis war easily via allies); an awakened fallen empire crisis looms but is not yet attacking us. _(google:gemini-3.8-flash, 2026-09-26)_

- A brief 12-month use of the 'expand' directive can successfully found new colonies (e.g., +2 planets) and boost population (+431 pops) even if no new systems are captured.  
  _why:_ retrospective 2436.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When multiple essential resources fall into deficit and basic stockpiles like minerals drop below a 12-month buffer, prioritizing 'consolidate_economy' over 'tech_rush' prevents economic collapse.  
  _why:_ retrospective 2436.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Basic resource shortfalls call for 'consolidate_economy'; a habitat amenity deficit beside them (e.g. -1017) does not, since it worsened under that directive (Krail -725 to -896).  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2436.05.01 said the habitat deficit necessitates consolidate_economy

- Once basic resource nets are back at zero or above, leave consolidate_economy even if habitat amenity deficits remain. Here 2.5 years of it turned minerals, alloys and rare crystals positive but only moved Krail's amenities from -1040 to -873, while tech power stayed at +0 and techs fell further behind the median (213 vs 222).  
  _why:_ retrospective 2438.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A consumer goods deficit of -17 a month against a stock of about 5900 (roughly 29 years) is not a reason to hold consolidate_economy over a growth directive.  
  _why:_ retrospective 2438.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Maintaining the 'tech_rush' directive while habitats suffer extreme amenities deficits (e.g., -814) is safe as long as stability remains securely above 50, allowing the empire to ignore civilian infrastructure in favor of research.  
  _why:_ retrospective 2439.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- The 'tech_rush' directive does not yield immediate results; tech count and tech power can remain completely stagnant over a 10-month period, causing the empire to temporarily fall further behind a growing galactic median.  
  _why:_ retrospective 2439.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When an endgame crisis appears and defend is taken, military power does not grow while alloy income is near zero: this time +2.4 a month gave +0 military in 12 months and a slide from 37.3k to 33.5k. Pair defend with a plan to raise alloy output rather than expecting the directive to build the fleet.  
  _why:_ retrospective 2443.04.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a crisis power has roughly 50x our military, our own fleet will not decide the outcome, so defend should be judged by systems held (27, unchanged) and by keeping allies and the federation intact, not by closing the military gap.  
  _why:_ retrospective 2443.04.01 _(google:gemini-3.8-flash, 2026-09-26)_

- An extreme planetary amenity deficit (e.g., -666) left after a 'consolidate_economy' window does not mean the window was too short or too late: no directive repairs grown-colony amenity deficits (+5 to +14 amenities a planet-year under it, 2 of 63-70 year-long intervals cleared), so a longer or earlier one would not repair it either.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the retrospective of 2447.04.01 said twelve months of it were not enough when the population imbalance is massive

- Under the 'defend' directive, military power will stagnate (e.g., +372 in a year) if monthly alloy production is critically low (+6.6/month).  
  _why:_ retrospective 2447.04.01 _(google:gemini-3.8-flash, 2026-09-26)_

- An urgent alert for a minor strategic resource deficit (such as volatile motes at -1.2/month) does not warrant switching away from 'defend' when the stockpile is massive (>6,000 units), as holding the stance preserves military readiness and prevents AI thrashing.  
  _why:_ In 2450.06, volatile motes net turned to -1.2/month with 6,729 in stock (~460+ years buffer). With 'defend' active for only 9 months, an active war against the Lyrite Tide, and crisis threats active (Contingency, Queptilium, Skanuri), maintaining 'defend' is strictly correct. _(google:gemini-3.8-flash, 2026-09-26)_

- While galaxy-level crises are active and no basic resource has less than about 12 months of stock, hold defend rather than alternating with consolidate_economy. In 2445–2450, consolidate years gave military +0 (and one year lost a system), while defend years gave military +372 and +439 and still grew the economy by +136 to +230.  
  _why:_ retrospective 2450.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A crisis war in which the enemy has 0 military and is far past 100% exhaustion (995% here) will not be closed by any directive, so do not use its end as a plan milestone or as a reason to hold a directive.  
  _why:_ retrospective 2450.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When net alloy income is near zero (+4.6/mo), defend adds only a few hundred military power a year and cannot matter against crisis fleets 20–50x larger. Plan around starbases, allies and the federation, not fleet parity.  
  _why:_ retrospective 2450.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- While galaxy-level crises are active and every deficit has more than 5 years of stock, keep defend as the top pillar and put fixing alloy income second; alternating with consolidate_economy has given +0 military.  
  _why:_ strategy review 2452.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Only use milestone metrics from the listed measures (systems, colonies, pops, techs_known, military_power, economy_power, tech_power); avoid rank metrics unless the exact measure name is known.  
  _why:_ strategy review 2452.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When the crisis war is over in practice (enemy military 0, exhaustion above 1000%) and 12 months of defend give military +0 and techs +0, move defend below growth, but name a clear trigger for going back to defend (a crisis fleet or rival at the border, or a system lost).  
  _why:_ strategy review 2452.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When energy sits in the hundreds of thousands and alloy income is under +10 a month, buying alloys each month turns the idle energy into the one resource that limits the fleet and outposts.  
  _why:_ strategy review 2452.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- If research income is far below what the pop count suggests (about 426 a month from 32k pops), raising research jobs is the growth lever. Choosing between directives while that stays low will not close the tech gap.  
  _why:_ strategy review 2452.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When facing multiple endgame crises with fleets vastly superior to ours, prioritize the defence directive and rely on a strong federation to deter attacks and share the burden of survival.  
  _why:_ strategy review 2452.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- If boxed in with no habitable planets, utilize orbital habitats for continued population and economic growth.  
  _why:_ strategy review 2452.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Minor resource deficits can be ignored temporarily during crisis wars as long as stockpiles provide a runway of multiple years, keeping the focus on military survival.  
  _why:_ strategy review 2452.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a crisis war is over in practice (enemy military 0, exhaustion above 1000%), our military is above the median and a year of defend gave tech +0, put technology first and defend second, with a trigger to return to defend (war declared, hostile or crisis fleet at the border, or a system lost).  
  _why:_ strategy review 2457.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a strategic resource such as rare crystals runs a small deficit (-5.4 a month) and energy sits in the hundreds of thousands, a small monthly buy order (about 2x the deficit) closes it more reliably than waiting on the AI to build for it.  
  _why:_ strategy review 2457.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When Habitat Expansion is missing and Star Fortress is its prerequisite, put tech_starbase_5 and tech_habitat_2 at the top of prefer_techs so the habitat growth path opens in order.  
  _why:_ strategy review 2457.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a crisis war is practically over (enemy military 0, exhaustion above 1000%) and 12 months of 'defend' give no tech or military growth, shift focus to growth directives like 'tech_rush' to close the technological gap, naming a clear trigger (e.g., system lost or crisis fleet entering borders) to revert to 'defend'.  
  _why:_ strategy review 2457.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- If tech_rush has run 3+ years with techs +0 or +1 a year and research is under about 500 a month despite 30k+ pops, stop holding it. Switch to consolidate_economy to fix the consumer goods, strategic resource and alloy shortfalls that block research buildings and ships.  
  _why:_ strategy review 2461.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a strategic resource deficit persists despite a small buy order and runway falls under about 24 months, raise the monthly buy above the full deficit (e.g. 24 against -18) while energy sits idle in the hundreds of thousands.  
  _why:_ strategy review 2461.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- With a hostile neighbour at 2x+ our military under truce, use the truce years to spread shipyards and alloy output across planets rather than waiting on the fleet total.  
  _why:_ strategy review 2461.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a strategic resource runs out in under 2 years and the economy has massive energy reserves (190k), use the market to buy the shortfall while switching to consolidate_economy.  
  _why:_ strategy review 2461.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- If 'tech_rush' yields +0 techs and +0 tech power over multiple years, tech income is too low relative to costs; fix the underlying economy first.  
  _why:_ strategy review 2461.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When the run opens with unclaimed systems within 2 jumps and no neighbours met, rank expansion first and diplomacy second for a pacifist, egalitarian federation builder, and stay on expand until the Expansion room line shows nothing left in reach.  
  _why:_ strategy review 2200.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- With Catalytic Processing, a food deficit also cuts alloy output, so treat food like minerals when checking for deficits.  
  _why:_ strategy review 2200.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Early on, if Expansion room shows many unclaimed systems but only a few surveyed, keep expand and treat surveying by science ships as the bottleneck. Don't move the colony milestone forward until candidate worlds have been found.  
  _why:_ strategy review 2204.04.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Early game with 9 unsurveyed systems within 2 jumps and only 1 colony (colonies milestone at risk), keep 'expand' even if systems owned hasn't grown yet — the bottleneck is surveying (0/9 surveyed) not influence/alloys (both healthy: alloys +19.4/mo, influence +4.4/mo capped nowhere near cap).  
  _why:_ 2207.04: systems flat at 5 for 12 months despite 9 unclaimed systems in reach; 3 science ships exist but 0 of 9 surveyed — survey capacity is the constraint, not the directive. _(google:gemini-3.8-flash, 2026-09-26)_

- When expand has room with unclaimed systems within 2 jumps but the system count stagnates (e.g., +0 in 12 months) and few are surveyed (1 of 9), treat surveying by science ships as the primary bottleneck, not alloy or influence constraints.  
  _why:_ strategy review 2209.04.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When consolidate_economy lifts pops and colonies but leaves one new colony's amenities negative with stability still at 50 or above, return to expand while unclaimed systems remain in reach; fix the colony through economy priority rather than holding consolidation.  
  _why:_ strategy review 2211.04.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When research income is under about 100 a month and the species is slow learners, set techs_known milestones at about 1 tech a year and spend prefer_techs on energy, bureaucracy and habitat techs rather than weapons.  
  _why:_ strategy review 2211.04.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When the problem a consolidate_economy spell was chosen for is gone (Berykinium's amenities went from -182 to +289) and the only deficit left is under 1 a month on a stock of several thousand, move economy down and give its place to the weakest measure, here technology (tech power last of 10).  
  _why:_ strategy review 2215.05.01; corrected 2026-09-27 (levers design ruling 22, E10): the amenities are not credited to the directive, since colony deficits clear with growth under any directive

- When alloys pile up (1306, +26 a month) while military is last and stays flat, set a defence goal to spend them on ships and a second shipyard rather than raising alloy income.  
  _why:_ strategy review 2215.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When an empire is boxed in with no colonisable planets left inside its borders and expansion room is running out, technology must be prioritized to unlock Orbital Habitats as the primary path for continued growth.  
  _why:_ strategy review 2215.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When alloys pile up (+300 in a year) while military shows +0 and a naval-capacity doctrine appears among the research options, put that doctrine in prefer_techs rather than waiting on a directive to spend the alloys.  
  _why:_ strategy review 2215.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When rank milestones read 'met' while the briefing shows us last, replace them with absolute targets (techs_known, military_power) that the briefing reports directly.  
  _why:_ strategy review 2215.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When expand has run 3+ years with systems +0, influence over 700 and alloys piling up, but only 1 of ~11 nearby unclaimed systems is surveyed, move expansion below defence, diplomacy and technology instead of holding expand for targets the AI cannot reach.  
  _why:_ strategy review 2219.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When alloys pile up (+300 a year) while military stays flat and a fanatic militarist neighbour 3x+ stronger reaches our border, put defence first so the alloys become ships and starbases, and put diplomacy second to lock in a defensive pact with the friendliest neighbour.  
  _why:_ strategy review 2219.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A market sell order must stay within 20% of that resource's monthly income: 3 CG against +13 income is over the cap, so switch to a resource with larger income (4 food against +22).  
  _why:_ strategy review 2219.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When 'expand' has been held for years but systems owned remains flat (+0 in 12 months) despite high influence and alloy stockpiles, the bottleneck is surveying. Switch to a different directive like 'defence' to utilize idle resources.  
  _why:_ strategy review 2219.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- If military power falls below half the median and alloys are piling up while a stronger hostile neighbour borders us, prioritize 'defence' to turn stockpiles into a deterrent fleet.  
  _why:_ strategy review 2219.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When military power stagnates (+2 in 12 months) and alloys pile up (3511) under `defend` while facing a vastly stronger neighbour, the fleet is likely bottlenecked by a lack of shipyards or naval capacity rather than the directive, requiring explicit goals to expand shipyard capacity.  
  _why:_ strategy review 2223.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When influence hits its cap (1000) and systems stay flat under a non-expansion directive, check if nearby unclaimed systems are surveyed; if 0 are surveyed, expansion is bottlenecked by exploration, not influence or alloys.  
  _why:_ strategy review 2223.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Holding 'defend' successfully utilizes alloy stockpiles to steadily narrow the military power gap against a superior hostile neighbour (from 4.1x to 3.0x over 7 years), deterring war even while remaining below half the galactic median.  
  _why:_ strategy review 2227.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When influence is capped (1000) but no unclaimed systems within 2 jumps are surveyed, the 'defend' directive does not prioritize science ship exploration, leading to complete territorial stagnation (systems +0).  
  _why:_ strategy review 2227.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When military power stagnates for 12 months despite a high alloy surplus and the fleet size perfectly matches the used naval capacity, the empire is capped; prioritize research for naval capacity doctrines or starbase anchorages to resume fleet building.  
  _why:_ strategy review 2231.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When influence sits at its cap (1000) and unclaimed systems remain within 2 jumps but systems owned stays flat, the constraint is unsurveyed targets; prioritize expansion or exploration to map those systems.  
  _why:_ strategy review 2231.06.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When influence sits at its cap (1000) and the briefing shows unclaimed systems within 2 jumps with construction ships free, choose expand over tech_rush even when we are boxed in on colonisable planets, because outposts are the growth that is still possible.  
  _why:_ strategy review 2235.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- The 'tech_rush' directive does not yield immediate results; tech count and tech power can remain completely stagnant over a 12-month period, causing the empire to temporarily fall further behind a growing galactic median.  
  _why:_ strategy review 2235.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When 'expand' has been active for multiple years with capped influence and idle resources, but the count of systems owned and surveyed nearby systems remains completely flat (+0), the unclaimed systems are likely unreachable by science ships; leave 'expand' rather than waiting for exploration that cannot happen.  
  _why:_ strategy review 2240.10.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When the fleet size is equal to the used naval capacity and military power stays completely flat (+0 over 12 months) despite a large and growing alloy stockpile, the empire is hard-capped; prioritize 'tech_rush' to unlock starbase upgrades or naval capacity doctrines instead of holding 'defend' or 'expand'.  
  _why:_ strategy review 2240.10.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When expand has run 4+ years with systems +0, influence capped, and alloys piling up, but only 0 of 8 nearby unclaimed systems are surveyed, move expansion below technology and economy instead of holding expand for targets the AI cannot reach.  
  _why:_ strategy review 2240.10.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When military power stagnates (+0 in 12 months) and alloys pile up (6900+) while the fleet perfectly matches used naval capacity (80/80), the empire is hard-capped; prioritize research for starbases and naval capacity doctrines rather than the defend directive.  
  _why:_ strategy review 2240.10.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When military power stays flat at naval capacity despite a large alloy surplus and the 'expand' directive yields +0 systems because target systems are unsurveyed, prioritize 'tech_rush' to unlock naval capacity and habitat technologies.  
  _why:_ strategy review 2240.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A food deficit under Catalytic Processing directly threatens alloy production and must be treated with the same urgency as a mineral deficit.  
  _why:_ strategy review 2240.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a bordering rival is 2x+ our military and a friendly neighbour at 800+ opinion has a commercial pact and research agreement but no defensive pact, rank diplomacy first so capped influence (1000) turns the friendship into a defensive pact or federation.  
  _why:_ strategy review 2243.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- The market sell order must use a resource the current briefing lists as IDLE: when only alloys are IDLE, sell alloys at no more than 20% of their net (5 of +25.3), and drop any older order on a resource no longer idle.  
  _why:_ strategy review 2243.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- With slow learners and about 100 research a month, tech_rush gave +0 techs in 12 months; do not rank technology first while multi-year energy and food deficits persist — fix the economy and defence first.  
  _why:_ strategy review 2243.05.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When military power stagnates (+0 over 12 months) despite a massive alloy stockpile (e.g., 8,400+), the fleet is likely bottlenecked by shipyards or hidden naval capacity limits; prioritize technology for capacity doctrines and build a second shipyard.  
  _why:_ strategy review 2247.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A planetary amenities deficit (e.g. -357 on Omoderium, stability 39.6) does not call for prioritizing 'consolidate_economy': no directive repairs grown-colony deficits. Watch it in the Planet check line; a colony under stability 25 is urgent.  
  _why:_ corrected 2026-09-27 (levers design ruling 22, E10): the strategy review of 2247.02.01 said it requires consolidate_economy

- When the expansion room shows multiple unclaimed systems within 2 jumps but 0 of them are surveyed, territorial expansion is bottlenecked by science ship exploration, meaning the 'expand' directive will yield no new systems.  
  _why:_ strategy review 2247.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Check that every prefer_techs id matches the ids the briefing lists as options: 'tech_doctrine_navy_size_2' never matched, and the naval-capacity doctrines are tech_doctrine_fleet_size_N.  
  _why:_ strategy review 2250.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When alloy stock falls (-1573 in a year) while military stays flat and fleet size equals naval capacity used, alloys are going to buildings, not ships. Raise capacity through the doctrine tech and the belligerent stance from defend rather than adding alloy income.  
  _why:_ strategy review 2250.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Once a resource drops off the IDLE list, drop any market sell order on it; switch the order to the IDLE resource, at 20% or less of its income.  
  _why:_ strategy review 2250.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When the Expansion room line shows surveyed unclaimed systems for the first time after years of zero, and influence is capped at 1000 with construction ships free, rank expansion first for about a year even with a 2x hostile rival on the border, as long as we are at peace; give defence a named trigger to take first place back.  
  _why:_ strategy review 2254.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A market sell order on consumer goods with +6 income can be at most 1; when minerals are IDLE with +52 income, sell up to 10 minerals instead, which also funds an energy deficit.  
  _why:_ strategy review 2254.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When influence is capped (1000) and unclaimed systems within 2 jumps are finally surveyed, prioritize 'expand' to utilize the idle resources for outposts.  
  _why:_ strategy review 2254.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A hostile neighbor with more than double our military power requires a defence goal of two shipyards in different systems and alloy production on two or more planets to ensure we can rebuild if attacked.  
  _why:_ strategy review 2254.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When expand has given +0 systems in three separate spells (2217, 2236, 2254) with influence capped at 1000 and alloys over 1000, but surveyed unclaimed systems rise only 2 to 3 of 14 in a year, move expansion to the lower half and judge it only by surveying progress.  
  _why:_ strategy review 2255.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a capacity doctrine (tech_doctrine_fleet_size_2) is already the research in progress while fleet size equals capacity used and alloys pile up (+274 a year), rank defence first so the new capacity turns the alloy stock into ships.  
  _why:_ strategy review 2255.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a bordering fanatic-militarist rival is 2x+ our military and a friendly pacifist neighbour sits at 700+ opinion with a commercial pact and research agreement, rank diplomacy right behind defence to turn that friendship into a defensive pact.  
  _why:_ strategy review 2255.07.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When defend has run 12 months with fleet size equal to naval capacity used (110/110), military +30 and the alloy stock flat, the fleet is capped until the capacity doctrine lands. Give first place to the pillar that can use idle capped influence (diplomacy toward a defensive pact), not to defend.  
  _why:_ strategy review 2256.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A market sell order on consumer goods is no longer allowed once their income falls below +5 (20% of +3.1 rounds to 0). Move the order to IDLE minerals at no more than 20% of their net (9 of +47.1).  
  _why:_ strategy review 2256.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- A flagged energy deficit (-78.8) whose stock still rose over 12 months (5164 to 5242) is being covered and does not by itself justify ranking economy first.  
  _why:_ strategy review 2256.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When military power stagnates (+30 in 12 months) despite a growing alloy stockpile and the briefing explicitly states not to assume a naval-capacity cap, the bottleneck is likely shipyards, so prioritize building a second shipyard.  
  _why:_ strategy review 2256.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When influence sits at its 1000 cap and a strong, friendly neighbour borders an empire without a defensive pact, prioritize diplomacy to secure the pact and stop wasting influence.  
  _why:_ strategy review 2256.08.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Judge an energy deficit by the observed stock drop, not the monthly net: 5242 to 1414 in about 13 months (-290/month against a -76 net) leaves about 5 months, so economy goes first and the idle-mineral sale goes to the 20% cap.  
  _why:_ strategy review 2258.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When alloys fall (1431 to 598) while military also falls (1355 to 1201) during a year that added 3 systems, the alloys went to outposts and buildings. A defend spell alone will not rebuild the fleet unless the naval-capacity doctrine arrives.  
  _why:_ strategy review 2258.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When the briefing lists a naval doctrine under a different id (tech_doctrine_navy_size_2 among the society options), put that exact id in prefer_techs alongside the older fleet_size id.  
  _why:_ strategy review 2258.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When an energy deficit is flagged (e.g. -79.2) but the stock only drops slightly over a year (e.g. 17), the deficit is being covered and does not require switching to consolidate_economy.  
  _why:_ strategy review 2259.10.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When military power stalls (e.g. 1380) and fleet size matches used naval capacity (110) while a capacity doctrine is on offer, prioritize technology to unlock the cap rather than relying on defend.  
  _why:_ strategy review 2259.10.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When facing a 2x+ hostile neighbor, ranking diplomacy first to secure a defensive pact with a friendly high-opinion neighbor provides a stronger deterrent than slow military buildup.  
  _why:_ strategy review 2259.10.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When fleet size falls in peacetime (110 → 85) and military drops 20% while the alloy stock stays flat despite +19.7 a month, treat it as ship losses or scrapping, not a capacity cap. Raise defence to a rebuild goal instead of adding capacity techs alone.  
  _why:_ strategy review 2260.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- With slow learners at about 125 research a month (tech power +0 in 12 months), set techs_known milestones at 1 tech a year. Anything faster will be missed whatever the directive.  
  _why:_ strategy review 2260.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- An IDLE resource with near-zero income (consumer goods +0.7 a month) cannot carry a market sell order under the 20% cap. Leave the market empty rather than sell a resource that is not idle.  
  _why:_ strategy review 2260.11.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When tech and economy power milestones are missed by a narrow margin because of slow-learner and slow-breeder traits, adjust future targets to reflect the actual growth rate (e.g., 1 tech per year) rather than the galactic median.  
  _why:_ strategy review 2261.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When an energy deficit reduces the stockpile buffer to under 20 months (e.g., -75/month against 1400 stock), a market sell order of an idle resource can slightly offset the drain, but the economy will soon require consolidation if not stabilized.  
  _why:_ strategy review 2261.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a pillar is ranked first, give its milestones different dates: a checkpoint about a year out and an end target a year after that.  
  _why:_ strategy review 2261.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Every stance, including the lowest-priority pillar's, must cite a briefing figure such as a unity or influence stock and its monthly net.  
  _why:_ strategy review 2261.12.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When unclaimed systems remain within 2 jumps but the count of surveyed unclaimed systems drops (e.g. 7 down to 6) while claiming only 1 system in 12 months, exploration by science ships is the hard bottleneck preventing the 'expand' directive from meeting system milestones.  
  _why:_ strategy review 2263.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- As a slow learners species, research output is significantly hampered, making it common to experience +0 techs known over a 12-month period. Technology milestones must be paced accordingly.  
  _why:_ strategy review 2263.01.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When systems are FALLING BEHIND (below half the median) and the Expansion room line shows surveyed unclaimed systems (6 of 27) with influence enough for several outposts (372 at 75 each), rank expansion first even with a 3x rival on the border, as long as we are at peace.  
  _why:_ strategy review 2263.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- Diplomacy milestones on rank:military_power read 'met' while no pact is signed; give diplomacy a measure it can move (economy rank through pacts and research agreements) and keep the pact as a named goal.  
  _why:_ strategy review 2263.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- An energy deficit flagged for years (-58.6 a month) whose stock stays near 1400-1500 across reviews is covered; keep a small idle-food sale and do not rank economy first for it.  
  _why:_ strategy review 2263.02.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When unclaimed systems remain within 2 jumps but only a small fraction are surveyed (e.g. 5 of 26) and system growth stagnates, exploration by science ships is the bottleneck and expansion milestones must be paced accordingly.  
  _why:_ strategy review 2264.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When fleet size matches the naval capacity used and military power growth stalls despite an alloy surplus, the fleet is capped; prioritize technology to unlock naval capacity doctrines currently on offer.  
  _why:_ strategy review 2264.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When facing a rival with 3x our military, ranking diplomacy first to secure a defensive pact with a highly friendly neighbor (800+ opinion) offers a more immediate shield than long-term fleet building.  
  _why:_ strategy review 2264.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When a pillar's stance is long, keep it under 400 characters by citing one or two key figures and the exit condition only; put detail into goals.  
  _why:_ strategy review 2264.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When the expansion checkpoint is missed with influence available but only 5 of 26 nearby unclaimed systems surveyed, lower expansion's weight and make surveying its explicit goal instead of pushing expand harder.  
  _why:_ strategy review 2264.03.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When prefer_techs names a later tier of a tech chain (tech_doctrine_fleet_size_3) while the briefing shows the earlier tier missing (Support Vessels), list the prerequisite id first: the later pick can never be offered.  
  _why:_ strategy review 2273.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When influence is near zero (about 12, +6 a month) and systems are +0 in 12 months despite surveyed unclaimed systems, the outpost bottleneck is influence, not surveying. Lower expansion's milestones to about 1 system a year instead of raising its weight.  
  _why:_ strategy review 2273.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

- When every milestone reads met but standings stay #7-#8 of 9 and the military is +0 in a year, replace the met targets with near-term absolute ones (military, techs, systems) rather than keeping the weights and reusing old dates.  
  _why:_ strategy review 2273.09.01 _(google:gemini-3.8-flash, 2026-09-26)_

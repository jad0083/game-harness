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

- A severe amenities deficit on a colony (e.g., -90 amenities) requires shifting the directive to 'consolidate_economy' to force the AI to build holistic infrastructure like holotheaters or housing.  
  _why:_ retrospective 2226.08.01 _(google:gemini-3.6-flash, 2026-09-26)_

- When a defensive war is declared, transitioning to the 'defend' directive successfully prioritizes survival and starbase defense, though military power may still take years to catch up to the galactic median.  
  _why:_ retrospective 2230.05.01 _(google:gemini-3.6-flash, 2026-09-26)_

- A large energy stockpile can safely absorb temporary energy deficits during a war, allowing the empire to remain in a 'defend' posture without needing to switch to 'consolidate_economy'.  
  _why:_ retrospective 2230.05.01 _(google:gemini-3.6-flash, 2026-09-26)_

- The 'consolidate_economy' directive effectively repairs severe amenity deficits and low stability, capable of raising a planet's stability by over 30 points in a single year.  
  _why:_ retrospective 2235.05.01 _(google:gemini-3.6-flash, 2026-09-26)_

- A prolonged defensive war preserves territory but typically causes an empire's technological and military growth to stagnate, falling behind peaceful peers.  
  _why:_ retrospective 2235.05.01 _(google:gemini-3.6-flash, 2026-09-26)_

- Temporarily adopting the 'consolidate_economy' directive is an effective way to resolve severe amenities and stability deficits on colonies.  
  _why:_ retrospective 2240.05.01 _(google:gemini-3.6-flash, 2026-09-26)_

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

- When a massive amenities deficit (e.g., -128) exists on a colony after a prolonged war, temporarily switching to the 'consolidate_economy' directive can rapidly improve stability and reduce the deficit.  
  _why:_ retrospective 2274.11.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

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

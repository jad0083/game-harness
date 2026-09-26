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

- While 'expand' successfully prioritizes colonization, it can cause system claiming to stagnate if early alloy production is consumed by colony ships.  
  _why:_ retrospective 2206.09.01 _(google:gemini-3.7-flash, 2026-09-26)_

- Severe amenities deficits (e.g., -92) and housing shortages on new colonies necessitate a temporary shift to 'consolidate_economy' to force the AI to construct civilian infrastructure.  
  _why:_ retrospective 2206.09.01 _(google:gemini-3.7-flash, 2026-09-26)_

- The 'consolidate_economy' directive efficiently resolves extreme planetary housing and amenities deficits in under two years, stabilizing colonies after rapid expansion.  
  _why:_ retrospective 2211.09.01 _(google:gemini-3.7-flash, 2026-09-26)_

- The 'consolidate_economy' directive successfully and rapidly resolves extreme planetary amenities deficits (e.g., reversing -119 to +93 in 14 months) by forcing the AI to prioritize holistic infrastructure.  
  _why:_ retrospective 2218.04.01 _(google:gemini-3.1-pro-preview, 2026-09-26)_

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

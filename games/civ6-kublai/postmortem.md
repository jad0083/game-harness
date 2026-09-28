# Post-mortem: Civ VI campaign civ6/kublai_khan_china_702403662 (China, Kublai Khan)

The pilot governed this campaign from T41. The game's AI played China through AutoplayManager, and the model gave macro orders between autoplay stretches.

**Method.** Five analyses (war, treasury, long-run strategy, harness reliability, diplomacy) produced 45 causal claims. Two verifiers checked each one:
- verifier 1 checked the evidence (were the rows, events, traces and logs as cited?);
- verifier 2 checked the causality (did this cause the defeat, or is it a correlate or symptom?).

Labels:
- **[both verifiers]**: both upheld the claim. Five claims earned this.
- **[one verifier]**: only one upheld it. In every such case the evidence verifier upheld the facts and the causality verifier rejected or downgraded the causal weight. Its reason is given with each claim.

Claim IDs (war-3, treasury-11, and so on) refer to the register in the appendix. All turn numbers are game turns.

**Where the evidence lives:**
- runs/telemetry.sqlite;
- runs/20260926-223045, 20260927-092427, 20260927-122128 and 20260927-135856 (events.jsonl, traces);
- the game's own logs. These are under the **civ6_appdata** root, Logs/, not civ6_docs. The files used are DiplomacySummary.csv, DiplomacyModifiers.csv, DiplomacyManager.csv, DiplomacyDeals.log, World_Congress.csv, AI_CityBuild.csv and AI_Victories.csv;
- read-only tuner queries;
- the verifier notes (working notes, not in the repo).

## Short answer

**Why we lost:**
- China entered Australia's surprise war (T539) with about a third of Australia's military: 343 against 1,094 at T538, and 318 against 1,061 at T541.
- Once the war started, buying defenders could not close that gap. Every city that received a bought Modern AT still fell.
- The gap had built up over 150+ turns. The AI playing China completed no combat unit through its own contracts from T380 to T583, and China lagged in tech.
- The governor never turned its gold and faith into defenders before the war, for three reasons:
  - its own 50% per-purchase cap made a modern defender need twice its price in the bank;
  - the game's AI spent that faith on Rock Bands during autoplay;
  - at the only two moments the cap allowed a purchase, one decision failed on model errors and the other on a model misbelief.
- The milestone and warning logic also muted the decline.

**What did not decide it:**
- **Wartime harness bugs cost one to three defenders and a few turns, not the outcome.** These were the cap still at 50% outside "in danger" cities, a misleading defender list, change-only triggers, a lost purchase reply and a review cap sized for Stellaris.
- **Diplomacy is not a demonstrated cause.** Australia's opinion of China was positive, with 0 grievances. It attacked the weakest military among the majors.
- **The last stand was a non-factor.**

After the last city fell, the governor ran 180 more turns because it has no end state.

## 1. The outcome in numbers

### Trajectory (metrics table, campaign civ6/kublai_khan_china_702403662)

| Turn | Cities | Our military | Rival median (rank) | Australia | Gold / faith | Note |
|---|---|---|---|---|---|---|
| T302 | 8 | 352 | rank 1 of 3 met | 58-71 (T288-T302) | 26.8 gold, -12.6/turn | end of an undetected deficit |
| T305 | 8 | 136 | | | +3.4/turn | 4 units gone in one step (strategy-8) |
| T380 | 8 | 256 | 565 (5 of 6) | | | score rank 6 of 6 |
| T460 | 9 | 210 | 517 (6 of 6) | 345 | 744 / 1,454 | techs 57 against median 69 |
| T525 | 8 | 454 | 1,106 (6 of 6) | 1,106 | 1,630 / 2,278 | pre-war treasury peak |
| T538 | 8 | 343 | 1,094 | 1,094 | 711 / 1,222 | weakest of the six majors: Mali 2,428, Maya 1,491, Netherlands 993, Germany 636 |
| T541 | 8 | 318 | | 1,061 | 828 / 1,961 | wars 2; first decision after the declaration |
| T546 | 6 | 299 | 1,253 | 1,253 | 1,739 / 790 | |
| T565 | 4 | 340 | | 1,528 | 2,224 gold | |
| T568 | 3 | 358 | 1,750 | | 2,446 / 648 | |
| T575 | 1 | 135 | 1,561 | 1,561 | 1,626 / 943 | |
| T579 | 1 | 139 | 1,561 | | 1,676 / 995 | Longxi captured in this AI turn |
| T583 | 0 | 139 | | 1,717 | 1,676 / 995 (frozen to T763) | elimination seen |

### City losses

Sources are war-4 [both verifiers], the game's AI_CityBuild.csv owner rows and DiplomacySummary.csv City Capture rows.

| City | Lost (AI turn in the game log) | Seen by the governor | Taker, mechanism | Defender bought |
|---|---|---|---|---|
| Shanghai | T475 (at peace) | T475 | loyalty flip to the Free Cities (then the Netherlands at T486) | none |
| Chengdu | T543 | T544 | Australia, razed | none bought. A Modern AT was already on its tile (T542 trace) |
| Beijing (capital) | T545 | T546 | Australia. Revolted to the Free Cities at T550 | Modern AT bought T545 |
| Haarlem | T552 | T552 | loyalty flip to the Free Cities (95, 77, 59, 41 over T546-T549) | refused T544 by the cap |
| Jiaodong | T554 | T555 | Australia. Revolted to the Free Cities at T558 | Modern AT bought T549 |
| Guangzhou | T565 | T566 | Australia, razed | Modern AT bought T563 |
| Rockhampton | T569 | T569 | loyalty flip to the Free Cities (93 at T552 to 3 at T568) | none |
| Taiyuan (capital) | T574 | T575 | Australia | Modern AT bought T544, T558 and T569 |
| Longxi (capital) | T579 | T583 | Australia. Elimination: every player logs "Peace" with China at T579 | Modern AT bought T546; T570 purchase lost to a tuner timeout |

Hunza, a city-state following Australia, declared war at T540, T552 and T564 and took no city. Of the eight cities lost in the war, six were conquered. The two loyalty flips followed nearby conquests.

### Spending and decisions

**Before the war (T462-T540):**
- The governor bought 3 buildings and 0 defenders: a Library for 180 faith (T465), a Library for 360 gold (T483) and a Granary for 130 faith (T517).
- Its last combat-unit purchase was a Field Cannon at T384 (treasury-2).

**The game's AI, buying for China with faith** (AI_CityBuild.csv FAITH PURCHASE rows, player 0):
- 14 Apostles (T188-T356), 1 Cuirassier (T367) and 16 Rock Bands (T374-T534).
- The Rock Bands cost about 21,600 faith in total. The 9 bought in T461-T534 cost 15,247, which is the entire pre-war faith drain (strategy-3, treasury-3).

**During the war (T541-T583):**
- 21 decisions produced 13 defender purchase orders.
- 7 completed, all Modern ATs: 4 with faith and 3 with gold, about 8,120 in total.
- 4 were refused:
  - T542, stacking;
  - T544, Haarlem, the cap;
  - T553, Taiyuan, the cap;
  - T566, Infantry, no Oil.
- 2 were lost to tuner timeouts:
  - T568, Taiyuan: re-ordered by the model at T569;
  - T570, Longxi: never re-sent.
- Gold for military units was at half price from T544 to T571 (World Congress Mercenary Companies, option B on gold, decided T542 and not renewed at the T572 session; treasury-8).
- At the end 1,676 gold and 995 faith were stranded below every buyable unit's price.

**Model outages:**
- Before the war, 3 of 19 decisions (T462-T538) got no answer: T512, T522 and T525.
- In the war, 0 of 21 got no answer; 2 were answered only after a fallback (reliability, minor finding).

**After elimination:**
- 16 decisions and 4 strategy reviews ran from T583 to T763.
- They used 378,629 input and 41,693 output tokens and 352.7 s of model time.
- A human stopped the run at T763 (reliability-1).

**After the stop:** the game kept running on its own and passed T1290 during this post-mortem. China reappeared at T913 holding Shanghai, after Australia took the city from the Netherlands ("913, 5, 4, City Capture, LOC_CITY_NAME_SHANGHAI"; tuner at T916: alive=true, 1 city, 1 Builder).

### Corrections to the brief

- **Elimination turn.** Cities hit 0 at T583: Longxi was captured in AI turn T579. The brief's "by T683" is wrong.
- **Military against the median.** Military was 30-78% of the met-rival median from T341 to T525, typically about 45%. It was not "a third or less" throughout (strategy, minor finding).
- **Score rank.** The "fall from 3 to 6" is an artifact of meeting more civs. We were last among known majors by T192 and continuously from T291, and each new contact was already ahead.
- **Unspent faith.** "Faith 790-2,278 unspent during the collapse" overstates it. Faith went on 4 Modern ATs: 2,688 at T544, 790 at T546, 277 at T550. Unspent gold (1,490-2,503 over T552-T569) is accurate.
- **Game logs.** The diplomacy logs are not empty. An early listing was stale. Only AI_Diplomacy.csv, CombatLog.csv and Player_Stats.csv are 0 bytes.

## 2. Root causes, ranked

**About the shares.** They are judgement estimates drawn from the verified counterfactuals, not measurements. They apportion the defeat among causes. RC1's share is the part of the gap that no verified governor failure accounts for.

| Rank | Root cause | Label | Share of the loss (estimate) |
|---|---|---|---|
| RC1 | A force gap at the declaration, built by a long military and tech deficit | [both verifiers] | Mechanism of every wartime loss. The part outside the governor's levers is about 50-60% |
| RC2 | The treasury never became defenders before the war | [one verifier]; size of the counterfactual [both verifiers] | About 25-35%, the largest controllable part |
| RC3 | Planning and warning defects muted the military decline | [one verifier] | About 5-10%, mostly acting through RC2 |
| RC4 | Wartime execution defects | [one verifier] | Under 10%: 1-3 defenders and a few turns; changed timing, not outcome |
| RC5 | Diplomacy: relations, isolation, no peace lever | [one verifier] | None demonstrated |
| none | Harness outages | [both verifiers] not the main cause (reliability-4) | Small, inside RC4 |
| none | Last stand switched off | [both verifiers] non-factor (war-12) | 0 |
| none | Governor ran on after elimination | [one verifier] (reliability-1, -3) | 0; cost only |

### RC1. The force gap at the declaration decided the war [both verifiers]

**Claims:** war-3 (force ratio decided the war), war-4 (city-by-city losses) and treasury-11 (no spending rule could have saved the empire once the war began).

**Evidence:**
- **The ratio** (metrics, ours against Australia): 318/1,061 at T541, 274/1,309 at T544, 147/1,074 at T548, 340/1,528 at T565, 135/1,561 at T575.
- **Our army at T538** (trace ep19): "Our land combat forces consist of 1 Cuirassier, 1 Mechanized Infantry, and 1 Modern AT!" The T563 strategy review says: "Our army is now a single Battleship, with no land combat unit at all."
- **Australia's army.**
  - It completed Giant Death Robots (strength 130) at T469, T480 and T505 (AI_CityBuild.csv, player 5), about 70 turns before the war.
  - Its siege contracts from T530 to T580 were 30 Jet Bombers, 24 Giant Death Robots and 16 Modern Armor.
  - Our best buyable defender, the Modern AT, has strength 85 and cannot engage aircraft.
- **Bought defenders did not hold:**
  - Beijing: bought T545, captured T545.
  - Jiaodong: bought T549, captured T554.
  - Guangzhou: bought T563, captured T565.
  - Taiyuan: bought T544, T558 and T569, captured T574.
  - Longxi: bought T546, captured T579.
  - Each purchase added about 100 military (274 to 374 at T544-T545; 233 to 330 at T563-T564), and the gain was destroyed within turns.
- **The ceiling on wartime spending** (treasury-11, both verifiers):
  - A rule-free greedy replay of T541-T579 buys 8 Modern ATs (or 9 Machine Guns), against the 7 actually bought.
  - Its main gain is timing: 3 units by T544 instead of 1.
  - Tile stacking and "not allowed" answers in besieged cities make 8 an upper bound.
- **How the deficit was built** (war-3 verifier 2; treasury-11 verifier 2):
  - The AI playing China completed no military unit through its own contracts from T380 to T583.
  - We held 57-68 techs against a median of 69-77.
  - We ranked 5th or 6th of 6 in military from about T360.
  - We had no Oil. The only Oil within 3 tiles of our cities was one offshore deposit near Rockhampton.

**Corrections the verifiers made:**
- **Oil was not the binding limit.** The Modern AT has the same 85 strength as Mechanized Infantry and Tanks, needs no resource, and stayed buyable.
- **Australia's strength did not rise steadily.** It sat at 965-1,263 over T543-T562. The ratio moved mainly because ours fell.

### RC2. The treasury never became defenders before the war [one verifier]

The size of the missed opportunity is [both verifiers] (treasury-11). The mechanisms below are [one verifier].

**treasury-2: no defender bought from T462 to T540, only 3 buildings.**
- The evidence verifier upheld the facts but placed the cause mostly in the harness and in failed decisions, not in model discipline.
- The model priced defenders and cited the 50% cap at T462, T470, T475, T483, T491, T504, T507, T535 and T538.
  - T496 thinking: "That 50% cap means I can only spend 916 faith (1833 / 2) ... the governor's going to shut that down."
  - T504: "The cap is the problem!"
- The three buildings fit under the cap and displaced no defender.
- The cap was the only thing blocking a defender the game would sell at T475 (AT Crew), T496 and T504 (Modern AT) and T538 (Machine Gun); also T365 and, uncited, T454.
- **Causality verifier:** at most a minor contributor. One to three more units would still leave us under half of Australia's strength.

**strategy-3: the game's AI spent the faith the governor was saving.**
- The AI bought 16 Rock Bands (about 21,600 faith), each during the autoplay stretch that followed a governor decision. Examples: T496 1,833 to T499 698; T525 2,278 to T528 958.
- No journal entry, issue or learned rule ever diagnosed it. T507: "Faith is currently 478 (not 1833)", then the model moved on.
- Corrections:
  - Only about 24,000 faith came out of a defender reserve. The saving intent starts at T326; earlier Apostles matched the governor's own plans.
  - The balance did reach twice a defender's price twice:
    - T486: 1,607 faith against an 800-faith AT Crew;
    - T525: 2,278 against a 1,080-faith Machine Gun.
- **Causality verifier:** a "moderate contributing condition". The cap turned normal AI cultural-victory buying into a race the governor could not win.

**treasury-4 and war-10: the only clear window was lost to model outages.**
- At T525 the cap was 1,139, enough for a 1,080 Machine Gun.
- The decision failed: two 503 fallbacks, then "RuntimeError: no answer within 6 model calls; no orders given".
- The T512 and T522 decisions also failed (503s and "request_limit of 6").
- Nothing retried. The next decision came at T530, with faith at 1,420.
- **Causality verifier:** marginal. It cost one Machine Gun, about +100 military.

**The T486 misbelief** (treasury-2 verifier 1 correction).
- Faith was 1,607, so the cap was 803, and an AT Crew cost 800.
- The model priced only Mechanized Infantry and wrote "we cannot buy land units with faith".
- The same belief appears at T457, T496 and T517. A resolved issues.md entry (T35-T85) records the same misbelief earlier in the campaign.

**Size of RC2:**
- Removing the cap alone gives 4-5 more Modern ATs, about +400-500 (treasury-1 and strategy-2 verifiers).
- A reserve-only rule at every affordable pre-war decision gives about 6-8 defenders, about +600-800. treasury-11 (both verifiers) calls this an estimate, not a replay.
- The gap to Australia at T538 was 751. On paper this closes half to all of it, and it lifts China above Germany (636) as the weakest major.
- Discounted, because:
  - bought ATs did not hold cities;
  - the enemy's unit types outclassed them;
  - nothing shows deterrence. Australia also attacked China at T82, when China was stronger (diplomacy-1 verifier 2).
- Hence the 25-35% estimate.

### RC3. Planning and warning defects muted the decline [one verifier]

**strategy-1: milestone status is "met" if the metric ever reached the target** (src/pilot/strategy.py:356-362).
- The target "military >= 170 by T350" read met at T350 with military at 124.
- From T305 to T385 the military share of effort in the frame was 2-7%, while military was the heaviest pillar (weight 22, T342-T384).
- The same rule hid the missed "gold per turn >= 15 by T298" milestone during the T291-T304 deficit (strategy-8). It also made rank:military milestones unable to fire (strategy-9 correction).
- **Causality verifier:**
  - The frame text still named the weakness ("123, the lowest of all known civs").
  - Military recovered to 287 by T385.
  - From T446 the statuses were honest (share 18-77%) and still no defender was bought.

**strategy-7: military targets were anchored on our own strength (+10-28%) or on the weaker Dutch.**
- They were never set against the median or against Mali, Maya or Australia, though the model named their 3-4x strength.
- On their due dates they sat at 0.44-0.56 of the median. The T512 Strategist: "military reached 425 at T502 but is back down to 385" against a median of about 750.
- **Causality verifier:** even these modest targets were missed repeatedly; execution (the cap), not the target level, held strength down.

**strategy-9: Civ VI has no rank or "falling behind" trigger.** Stellaris has one (governor.py:379-383).
- "Milestone missed: military" fired at T396, T446, T465, T496, T504, T512 and T538. Before the war it produced no defender purchase.
- Australia went from 233 (T454) to 1,106 (T525) with no trigger.
- **Causality verifier:** the rival militaries were in every briefing. A rank trigger would only have added more decisions blocked by the same cap.

**strategy-4: peacetime doctrine, T197-T302.**
- Military weight was 8-12. The rank milestones counted only the 2 met civs.
- Learned rules at T263 and T302 moved production from military to science.
- Decisions overrode AI defence builds at T215, T279, T282 and T296.
- **Causality verifier:** military did not decay in that window (268 to 352, rank 1-2). The doctrine ended by T310. The attacker, Australia, was a met peer and weak then.

**strategy-8: military fell from 352 to 136 over T302-T305, during a 14-turn gold deficit no trigger caught.**
- The briefings showed -6.8 to -12.6 gold per turn while the economy stance still said +12.4.
- Correction: this was not the game's bankruptcy disband. The treasury never reached -10, and 4 units vanished with about 15 gold in the bank; the cause is unlogged.
- **Causality verifier:** recovered by T386; obsolete units; not linked to the T539 war.

**strategy-6: the Strategist leaned on "faith purchases held 8 of 8".**
- That rate is 100% by construction: a purchase resolves as "completed" at once and never counts as failed.
- It said nothing about whether defenders were affordable. From T385 to T541 no faith unit purchase was ever sent.
- **Causality verifier:** the plan would have been made anyway. The real error was not doing the cap arithmetic.

**war-10: the strategists named Mali (our ally from T511) and Maya as the threats, never Australia.**
- **Causality verifier:** the defender plan did not depend on who the threat was, and there is no diplomacy lever, so this changed no order.

### RC4. Wartime execution defects [one verifier]

The causality verifier rejected the "contributing" weight of each claim below for the same reason: every city with a bought defender still fell, and the war was decided by T546. Their combined effect is about 1-3 more Modern ATs, or the same units 2-5 turns earlier.

**war-5 and treasury-6: the 50% cap stayed in force in wartime for every city not flagged in_danger** (pillars.toml:124-125; civ6.py purchase_cap:561-568; levers ruling 17).
- Refused by the harness:
  - T544 Haarlem: "1160 faith ... over the 764 allowed";
  - T553 Taiyuan: Machine Gun, "1080 gold ... over the 814 allowed".
- Held back by the model, citing the cap:
  - T541: "1160 vs 980 50% cap of 1961 faith";
  - T552;
  - T555: "limits us to 955 gold";
  - T556: "1026 of 2053 gold";
  - T565: "50% cap of 1112 on our 2224 gold".
- The model wrote the rule into learned/strategy.md:374 at T555: "save gold until the balance is double the unit cost".
- Corrections:
  - Haarlem fell to loyalty, not capture.
  - The faith refused at T544 was spent in Beijing the next turn.
  - Net effect: about 1-2 extra Modern ATs, a few turns earlier.

**war-6 and treasury-7: the briefing's "defenders to buy" list was misleading** (harness.lua:316-336).
- It keeps the two cheapest defenders by gold. `CanProduce` ignores strategic resources, so it always showed Infantry (860) and Tank (960), both "not allowed now" for lack of Oil.
- It never showed the buyable Modern AT (1,160) or Machine Gun (1,080).
- Harm:
  - T556: kept 2,053 gold because "defender purchases there are not allowed now".
  - T566: ordered Infantry, which the game refused for Oil.
  - T558: second purchase slot left unused.
  - Four learned rules (T546, T563, T565, T575) codified the misreading.
  - It also switched off defence-first (civ6.py `_needs_defender_first`).
- The model usually worked around it with the price tool. It ordered a Modern AT in a city flagged in danger 6 times: T545, T546, T549, T563 and T569 completed, and T570 was lost to a timeout.

**war-9, treasury-9 and reliability-6: a lost purchase reply was never re-sent.**
- At T570 the Longxi Modern AT (1,160 gold, allowed, 1,407.65 in the bank) timed out: "gold went from 1407.6484375 to 1407.6484375".
- The governor never re-sends (civ6_governor.py `_apply`/`_record_order`), and no decision ran from T571 to T574.
- At T575 the price was 2,320 gold, because the World Congress discount ended at the T572 session.
- The T568 Taiyuan timeout was recovered: the model re-ordered it at T569.
- **Causality verifier:** one defender for a city that fell later anyway; only T571 was a viable retry turn.

**treasury-8: gold prices halved from T544 to T571.**
- Cause: the Mercenary Companies resolution (World_Congress.csv "542, RESOLUTION DECIDED, WC_RES_MERCENARY_COMPANIES, , 2, 2").
- The price doubled back at T572 and stranded the last 1,626-1,676 gold. The harness never showed the discount or its expiry.

**war-8 and reliability-7: urgent triggers fire only when something changes** (civ6.py:1274-1297).
- A city that stays in danger never re-triggers a decision. The gaps were T559-T562, T571-T574 and T576-T582.
- "City falling" fired 0 times in 8 losses.
- **Causality verifier:**
  - Decisions ran on 20 of the 39 turns from T541 to T579 (8 in the 9 turns T541-T549), and Chengdu and Beijing still fell.
  - In T576-T582 nothing was buyable (Modern AT 2,320 gold against 1,626; faith 943-995 against 1,160).

**war-7: strategy reviews were throttled by the Stellaris event-review cap** (governor.py:2202-2218).
- The cap is "12 in-game months"; `months("T541")` returns 541, so in Civ VI it means 12 turns.
- It skipped 15 of 18 urgent war triggers from T541 to T570, including the new war at T541, 3 turns after the T538 review.
- The first wartime strategy came from the scheduled review at T546, after Beijing fell.
- **Causality verifier:** the cap delayed the strategy frame, not the decisions, which were already about defence. Five wartime reviews (T546-T575) raised military's weight to 34-40, and gold still rose to 2,503.

**war-1 and reliability-5: the surprise war fell inside a 3-turn peace chunk (T538-T541).**
- Correction: it cost one decision point, not two. The game logs an event at N and the governor first sees it at N+1, so with 1-turn chunks the war would have been visible at T540.
- **Causality verifier:** Chengdu's tile already held a Modern AT (the game refused a purchase there), and with the war known the governor still bought nothing at T541.

**treasury-10: one-turn autoplay switches off the AI's start-of-turn city management.**
- In 186 one-turn turns the AI made 0 purchases. After T539 the governor was the only buyer.
- **Causality verifier:** the AI never bought a defender for us in 500 turns, so there was no second buyer to lose.

### RC5. Diplomacy: no demonstrated share [one verifier]

**diplomacy-1: Australia's T539 war was not driven by relations.**
- Its opinion of China was net positive: about +12, bounded +4 to +27, with Same Government +20 from T505.
- Grievances had been 0 since T469.
- It was a surprise war with no casus belli ("539, 5, Team 0, Individual Declaring War on Team START, Surprise").
- China had the weakest military of the six majors.
- **Causality verifier:** "because China was weak" is an inference; the AI's reasoning logs are 0 bytes.
  - Australia also declared at T82 when China was about 1.8x stronger.
  - The ratio sat near 0.4 for about 45 turns without war.
  - Australia declared while China's defensive pact with Mali (military 2,428) was still in force.

**diplomacy-2, diplomacy-3, diplomacy-4, diplomacy-6 and war-11: context, not cause.**
- China's diplomacy was made by the game's AI during autoplay (47 statements answered "between two AIs").
- The model could not see relations or who declared a war, and it had no diplomacy order (civ6.py:461).
- Nobody proposed peace from T539 to T579.
- Why the causality verifiers found no effect:
  - Peace was illegal before T549 (DIPLOMACY_WAR_MIN_TURNS=10), after Chengdu and Beijing had fallen.
  - Australia's only peace with a major it was beating cost the Netherlands a city (Rotterdam, T247).
  - The one alliance (Mali, via its defensive pact) brought the strongest military into the war and changed nothing: Mali captured nothing and paid Australia for peace at T568.

**diplomacy-5: at T121 the autoplay AI declared a surprise war on Australia in China's name.**
- The model recorded it as Australia's war and learned a rule from the wrong premise (corpora/civ6/learned/strategy.md:62).
- It cost Xi'an (T149).
- **Causality verifier:** its effects had decayed by about T191, and the rule's "weaker neighbour" premise never matched T539.

### Non-causes confirmed by both verifiers

**war-12: the last stand would not have run with PILOT_LAST_STAND=1, and would not have helped.**
- Its gate `about_to_fall` (civ6.py:1134-1146) needs walls at 0 and a capturer adjacent. `capture_adjacent` counts only melee and cavalry (harness.lua:353, unit_kind 206-210).
- A Giant Death Robot has RangedCombat 120 and CanCapture true, so it was never counted.
- Beijing (T545: garrison 0/200, walls 0/400) and Guangzhou (T565: 80/200, walls 0/400) met the walls and garrison tests and fell the next AI turn without triggering.
- We had no land ranged or siege units. The lesson is the too-narrow capture test, not the switch.

**reliability-4: harness outages were not the main cause.**
- The final run had no needs_attention stops and no turn played twice. Every war decision got an answer.
- The only war-time harness losses were the 2 purchase replies (T568, T570).

## 3. What the governor saw and did at each critical moment

| Turn | What the governor saw | What it did | What followed |
|---|---|---|---|
| T289-T304 | Briefings showed gold per turn at -6.8, then -11.2, then -11.7. The economy stance still said "Gold per turn is 12.4" (stale T288 text). The milestone "gold per turn >= 15 by T298" read met (sticky). The first gold trigger was T302 "gold below the reserve" | Universities and Monuments (T291, T296, T299); Conscription slotted at T302 | Military 352 to 136 (T302-T305), cause unlogged; recovered by T386 (strategy-8) |
| T305-T385 | Frame: military share 2-7%, weight 22 (heaviest); military milestones "met" from old rows | Wanted Line Infantry at T347-T373; blocked by the 720 price and the cap | Strategist at T310: "even though the recorded status says 'met'" (strategy-1) |
| T446-T538 | "Milestone missed: military" at T446, T465, T496, T504, T512 and T538; rival militaries in "Civilizations met" (Australia 955 at T512, 1,106 at T525) | T446 builder and Synagogue; T465 Library and University; T496 research only; T504 Research Labs; T512 error (503); T538 keep | No defender bought T462-T540 (strategy-9, treasury-2) |
| T486 | 1,607 faith; unit:at_crew (800 faith) in Beijing's can-build list; cap 803 | Priced only Mechanized Infantry; "we cannot buy land units with faith"; keep | The only pre-war window that needed no model outage to fail (treasury-2 correction) |
| T496, T504 | 1,833 and 1,659 faith; Modern AT 1,160 allowed | "the governor's going to shut that down"; "The cap is the problem!"; research and Research Labs | Rock Bands T497 and T505 took the faith |
| T507 | Faith 478 | "Faith is currently 478 (not 1833)"; keep | Drain never diagnosed (strategy-3) |
| T512, T522, T525 | 503s and "request_limit of 6"; T525: 2,278 faith, cap 1,139, Machine Gun 1,080 | episode_error; T525: "no answer within 6 model calls; no orders given" | Rock Band T526 (1,998 faith); next decision T530 at 1,420 faith (treasury-4) |
| T538 | "Milestone missed: military"; "1 Cuirassier, 1 Mechanized Infantry, and 1 Modern AT"; 343 against Australia's 1,094 | Keep: "cap non-emergency purchases at 611 faith and 355 gold"; strategy review (uses the event-review slot) | Autoplay reply lost, re-sent; a 3-turn chunk to T541 |
| T539-T540 | Nothing: urgent checks run only between autoplay calls | none | Australia's surprise war (T539); Mali joins by defensive pact; Hunza (T540) (war-1) |
| T541 | "new war: CIVILIZATION_AUSTRALIA ...; new war: CIVILIZATION_HUNZA ...; city threatened: Chengdu (5 enemy units near)"; reason "Australia declared war with 1061 military against our 318" | Held a Jiaodong Modern AT ("1160 vs 980 50% cap of 1961 faith"); the game refused a Chengdu faith buy; ordered Robotics, a civic and Modern AT production in Rockhampton. Strategy review skipped (12-"month" cap) | Faith rose 1,961 to 2,688 by T544, unspent |
| T542 | Chengdu "defenders to buy ... (not allowed now)"; "There's a unit, a modern AT, on Chengdu's tile" | Machine Gun in Rockhampton, refused (tile occupied) | Chengdu captured and razed in AI turn T543; no decision at T543 |
| T544 | "city lost: Chengdu" | Modern AT in Taiyuan (faith), completed; Haarlem Modern AT refused ("over the 764 allowed") | |
| T545 | Beijing (capital) "IN DANGER ... under siege; garrison 0/200, walls 0/400"; no "city falling" (capturer test) | Modern AT in Beijing (faith), completed | Beijing captured the same AI turn (war-12) |
| T546 | "city lost: Beijing"; first wartime strategy (scheduled): "We lost Chengdu on T544 and Beijing on T546" | Modern AT in Longxi (gold, discounted 1,160); learned rule "A city IN DANGER shows its defender purchase as 'not allowed' -> buy defenders in the nearest cities" | |
| T548 | Faith 1,121 | "No gold or faith purchases are available" | Misread defender list (war-6) |
| T549 | | Modern AT in Jiaodong (faith) | Jiaodong captured T554 |
| T552-T556 | Haarlem lost to loyalty; gold 1,490 to 2,053; Guangzhou "in danger (garrison 44/200, walls 257/400)" | T552 event review; T553 Machine Gun refused by the cap; T555 "The 50% purchase cap limits us to 955 gold" and learned "save gold until the balance is double the unit cost"; T556 keep, "defender purchases there are not allowed now" | Guangzhou never priced (war-6, treasury-6) |
| T558 | | Modern AT in Taiyuan (gold) | No decision T559-T562 while Guangzhou stayed in danger |
| T563-T566 | T563 strategy: "Our army is now a single Battleship"; goal "Get peace with Australia..."; T565 Guangzhou walls 0/400, garrison 80/200, no unit | T563 Modern AT in Guangzhou (paid with faith); T565 Taiyuan held ("exceeds the 50% cap of 1112"); T566 Infantry refused by the game: "requires 1 Oil" | Guangzhou captured and razed in AI turn T565 |
| T568-T570 | T569 Rockhampton lost to loyalty; T570 Taiyuan "IN DANGER: 5 enemy units ..., 1 next to it that can take it; garrison 82/200, walls 186/400" | T568 Taiyuan purchase lost (timeout); T569 re-ordered by the model, completed; T570 Longxi Modern AT (1,160 gold, allowed) lost (timeout) | No decision T571-T574; gold discount ended at the T572 World Congress |
| T575 | "city lost: Taiyuan"; Longxi IN DANGER, walls 400/400, garrison 200/200, no unit on tile; Modern AT 2,320 gold / 1,160 faith, not allowed (balance 1,626 / 943) | "it looks like a timeout prevented the purchase last turn. I will hold off on purchases"; research tech:cybernetics | |
| T579-T583 | A one-turn call advanced 4 turns | none | Longxi captured in AI turn T579 (elimination); T583 trigger "city lost: Longxi"; "0 cities, 0 units"; review "The game is effectively lost." |
| T583-T763 | 0 cities; gold and faith frozen at 1,676 / 995; 18 of 25 autoplay calls advanced more turns than requested (e.g. T583 to T612 on a 3-turn call) | 16 decisions and 4 reviews, mostly re-queuing research | Stopped by hand at T763; the game ran on (reliability-1, reliability-3) |

## 4. Harness failures, separate from strategy failures

**Harness failures** are defects in code, configuration or infrastructure that the model cannot change. **Strategy failures** are choices by the Strategist or the decision model inside those rules.

### Harness failures (ordered by estimated impact)

**H1. The buy-out cap had no war or weakness exception** (treasury-2, war-5, treasury-6 [one verifier]).
- `treasury_share = 0.5` applies to any city that `in_danger()` does not flag (pillars.toml:124-125; civ6.py:504, 561-568).
- Levers design ruling 17 narrowed that flag from "threatened", and its "Cost if wrong" names exactly this case: "A city in real trouble with a garrison and one attacker gets the 0.5 share."
- tests/test_pillars.py:255 pins `treasury_share <= 0.5`.
- At Future-era prices (Modern AT 1,160 faith, 2,320 gold at full price), a defender needed 2,160-2,320 in the bank.

**H2. Nothing protected the stock from the game's AI during multi-turn autoplay, or reported what it spent** (strategy-3 [one verifier]).
- 16 Rock Bands cost about 21,600 faith.
- No briefing line showed where the faith went.

**H3. `milestone_status` counts any past row** (src/pilot/strategy.py:356-362; strategy-1 [one verifier]).
- Its result feeds pressure (need met=0.3 against missed=2.0), so "met" cuts a pillar's weight about 6x.
- The same code is shared by the Stellaris governor (governor.py:76, 2249, 2301, 2312).

**H4. Missing Civ VI triggers** (strategy-9, strategy-8 [one verifier]).
- `civ6.urgent_changes` has no rank or "falling behind" trigger.
- It has no neighbour-buildup trigger.
- It has no negative-income trigger, only "gold below the reserve".

**H5. `defence_prices` shows Oil-locked units as the only defenders** (harness.lua:316-336; war-6, treasury-7 [one verifier]).
- It also disabled defence-first (`_needs_defender_first`).
- Ruling 20's must-have conversion never got a known price for Modern AT or Machine Gun.

**H6. Urgent checks fire only on a change, and the "falling" test is too narrow** (civ6.py:1274-1297 and 1134-1146; war-8, reliability-7 [one verifier]; war-12 [both verifiers]).
- A city that stays in danger never re-triggers a decision.
- `about_to_fall` needs walls at 0, and `capture_adjacent` never counts ranged capturers such as the GDR.

**H7. A Stellaris time constant applied to Civ VI turns** (governor.py:2202-2218; war-7 [one verifier]).
- The "12 in-game months" event-review cap became 12 Civ VI turns. Civ6Governor inherits it unchanged.

**H8. Lost order replies are never re-sent** (civ6_governor.py `_apply`, `_record_order`; war-9, treasury-9, reliability-6 [one verifier]).
- This holds even when the read-back proves nothing happened, e.g. gold unchanged.
- A lost purchase does not start the cooldown, so a retry would have been allowed.

**H9. A failed decision has no fallback action and no retry before the next autoplay** (treasury-4, war-10 [one verifier]).
- 503s plus `request_limit` 6 caused 3 pre-war failures (T512, T522, T525).

**H10. Chunking** (war-1, reliability-5, treasury-10 [one verifier]).
- 3-turn peace chunks see a surprise war one decision point late.
- One-turn chunks switch off the AI's start-of-turn city management; issues.md already has an open entry on one-turn autoplay.

**H11. The order record cannot show purchase failure** (record.py; strategy-6 [one verifier]).
- The purchase stick rate is 100% by construction.
- Purchases withheld by the decider over the cap never reach the record.

**H12. No diplomatic visibility and no diplomacy order** (civ6.py:461, 1280, 1506-1514; harness.lua majors() 453-470; war-11, diplomacy-2, diplomacy-4, diplomacy-6 [one verifier]).
- The trigger text "new war: X is at war with us" never says who declared.
- `harness.lua:1295-1296` maps MAKE_PEACE to Goodbye. This is latent only: peace offers settle AI-to-AI during autoplay and never reach the handler (diplomacy-4 correction).

**H13. No end state** (reliability-1, reliability-3 [one verifier]).
- There is no alive or elimination check.
- `_wait_turns` accepts any turn at or past its target and logs the requested count, not the actual advance.
- `Civ6Game.set_paused` only calls `autoplay_stop`, and the game ran on after the stop.
- Correction (reliability-2 verifiers): `Game.GetLocalPlayer() == -1` is not a death signal, since China was alive again from T913 while the tuner read local -1 at T916.

**H14. Observability** (analysts' minor findings, not verified).
- Stored decision prompts are cut at about 6,000 characters, so most per-city danger lines are missing from traces.
- The game's logs are under civ6_appdata, not civ6_docs.
- AI_Diplomacy.csv, CombatLog.csv and Player_Stats.csv are 0 bytes.
- A Stellaris-only merge restarted the live Civ VI run at T462 (reliability minor finding, not verified).

**Not a harness failure** (reliability-4 [both verifiers]): outages did not cause the collapse.

### Strategy failures (Strategist and decision model)

**S1. Peacetime doctrine, T197-T302** (strategy-4 [one verifier]).
- Military weight was 8-12, with rank milestones counted against the 2 met civs.
- Learned rules moved production from units to science: T263 "switch it to the science building", and T302 "defence is bought when a threat appears".
- The model deliberately overrode AI defence builds at T215, T279, T282 and T296.

**S2. Military targets tied to our own strength or the Dutch** (strategy-7 [one verifier]).
- Targets were 0.44-0.56 of the median, while the model itself wrote that Mali and Maya had 3-4 times our strength.

**S3. Purchase plans that the rules and resources made impossible** (strategy-3, strategy-6 [one verifier]; war analyst fix 7).
- The Strategist planned faith-bought Mechanized Infantry at T496 and T512. It was never allowed: it needs Oil.
- At T496 it asked for "Buy 2 mechanized_infantry" (2,600) with 1,833 on hand.
- It read snapshot peaks as idle faith and never did the cap arithmetic, although the cap was in its instructions (strategy.md section 5).

**S4. Decision-model misbeliefs** (treasury-2 verifier 1).
- T486: "we cannot buy land units with faith" (also T457, T496, T517), although faith unit purchases worked at T384 and T544.
- It did not price a Machine Gun until T538.

**S5. Hands-off production** (strategy-7 and strategy-9 verifier 2).
- The Strategist said to "leave the AI's production queues alone" (T496, T512, T525), because production replacement held only 38% of the time.
- Queue fills went to Research Labs, a Granary, a Food Market and a Sewer.

**S6. Learned rules built on misreadings** (diplomacy-5, war-6, treasury-7, war-5 [one verifier]).
- T123: the T121 war was recorded as Australia's (strategy.md:62).
- T546, T563, T565 and T575: "not allowed in endangered cities".
- T555: "save gold until the balance is double the unit cost" (strategy.md:374).

**S7. Wartime misses the rules allowed** (war-6, treasury-7 corrections).
- T556: kept 2,053 gold with Guangzhou in danger.
- T558: second purchase slot unused.
- T566: ordered Infantry although the price tool said allowed=false.

**S8. Threat misidentification** (war-10 [one verifier]).
- Mali (our ally) and Maya were named as threats; Australia never was. This changed no order.

## 5. Lessons for the Civ VI governor, as concrete changes

Priority follows the root-cause ranking. Each lesson lists its evidence, the change and a test. Tests name existing suites: tests/test_civ6_governor.py, tests/test_civ6_strategy.py, tests/test_strategy.py, tests/test_governor.py, tests/test_harness_lua.py and tests/test_pillars.py.

### Buy-out rules

**L1. Lift the 50% cap for defenders in war or weakness.**
- **Evidence:**
  - Pre-war: the cap was the only block on a game-allowed defender at T365, T475, T496, T504 and T538.
  - War: refusals at T544 and T553, and holds at T541, T552, T555, T556 and T565 (H1).
- **Change:** a defender-class purchase may spend down to the reserve (`threatened_share`) in every city, not only the in_danger one, whenever any of these holds:
  - we are at war with a major;
  - our military ranks last or is below 0.6x the met-major median;
  - a met non-allied major has at least 2x our military.

  Also:
  - keep 0.5 for buildings;
  - allow one defender per city per decision, keeping only the per-city cooldown;
  - update rulings 17-19 of the levers design and relax tests/test_pillars.py:255 for defender classes;
  - remove learned rule strategy.md:374 (save to 2x).
- **Test:** in tests/test_civ6_governor.py, replay the recorded snapshots and assert the check passes:
  - T496: Rockhampton Modern AT, 1,160 faith of 1,833, allowed;
  - T538: Machine Gun, 1,080 of 1,222;
  - T541: Jiaodong Modern AT, 1,160 of 1,961;
  - T553: Taiyuan Machine Gun, 1,080 gold of 1,630;
  - T555: Taiyuan Modern AT, 1,160 gold of 1,911.

  Assert that a T465 building purchase is still capped at 50%.

**L2. Buy before the AI spends, and show what the AI spent.**
- **Evidence:** 16 Rock Bands (about 21,600 faith), each within a few turns after a governor decision. Examples: 1,833 to 698 over T496-T499, and 2,278 to 958 over T525-T528. The T507 model did not know where the faith went (H2).
- **Change:**
  - Before each multi-turn autoplay stretch, when the military milestone is at risk or missed, or military ranks last, the governor itself buys the cheapest allowed resource-free defender for the weakest ungarrisoned city. No model call is needed.
  - Add a briefing line "the AI spent N faith / N gold since the last decision". Compute it as balance delta minus yield minus our own orders, and name the item from AI_CityBuild.csv when it can be read.
  - Raise needs_attention when a drop exceeds one defender's price.
- **Test:**
  - With the T496 snapshot and the Rock Band drop, the pre-stretch hook orders a defender.
  - The briefing built from the T496 and T499 metrics rows contains the drain line.

**L3. Retry a lost purchase when the read-back proves it did not happen.**
- **Evidence:** T570 Longxi, "gold went from 1407.6484375 to 1407.6484375". Nothing was re-sent, no decision came T571-T574, and the discount ended at T572 (H8).
- **Change:**
  - When the reply is lost, the balance is unchanged and no new unit is on the tile, record did_not_take.
  - Re-send once at the next hand-back after a fresh snapshot, or force an urgent decision "order lost: purchase X in Y".
  - Keep "never re-send" for last-stand actions.
- **Test:** a fake tuner times out on the first purchase call. Assert exactly one re-send when gold is unchanged, and none when gold dropped.

**L4. Show time-limited price changes.**
- **Evidence:** Mercenary Companies halved gold prices T544-T571 and expired at the T572 session (treasury-8).
- **Change:** read World Congress resolutions and their expiry into the snapshot. Tell the model "gold unit prices halved until T572".
- **Test:** a snapshot fixture with a Mercenary Companies (B, gold) resolution yields the briefing line and its expiry turn.

### Prompts and briefing

**L5. List the defenders the game will actually sell.**
- **Evidence:** H5; the T556 keep with 2,053 gold; the T566 Infantry refusal; the T548 "No gold or faith purchases are available".
- **Change:**
  - `defence_prices` lists, per currency, the cheapest defenders with purchase allowed true.
  - For each refusal it gives the reason from CanStartCommand: resource, stacking, siege or balance.
  - It always includes a resource-free ranged defender (Machine Gun) and an anti-cavalry one (Modern AT), and says "no buyable defender" explicitly.
  - `_needs_defender_first` and ruling 20 read the new list.
- **Test:**
  - tests/test_harness_lua.py: for a Guangzhou-like city at T563, the list contains Modern AT 1,160 allowed, and Infantry either does not appear or appears as "needs Oil".
  - tests/test_civ6_governor.py: defence-first engages when a Modern AT is allowed.

**L6. Give the Strategist the purchase arithmetic, strategic resources and an honest order record.**
- **Evidence:**
  - Plans for faith-bought Mechanized Infantry (never allowed, Oil) at T496 and T512.
  - "Buy 2 mechanized_infantry" (2,600 faith) with 1,833 on hand.
  - "faith purchases held 8 of 8" when no unit purchase had been sent since T384 (S3, H11).
  - The recurring belief that faith cannot buy land units (S4, and a resolved issues.md entry from T35-T85).
- **Change:**
  - The frame carries the live prices of buyable defenders, the effective cap per city, and the stock of Oil, Aluminum and Uranium.
  - The order record splits purchases into units and buildings, and counts "withheld by cap" and "refused by the game".
  - Decision prompts require that any deferred defender cite a price-tool result.
  - The Strategist validator rejects a goal that names a unit whose last price probe was not allowed for resource reasons.
- **Test:**
  - tests/test_civ6_strategy.py: a T496 strategy naming unit:mechanized_infantry is sent back with the reason.
  - The record text for a T512 fixture reads "defender purchases: 0 sent, N withheld by cap".

**L7. Say who declared each war.**
- **Evidence:** the T121 war was declared by China's own autoplay AI ("121, 0, Team 5, ... Surprise") and recorded as Australia's. A learned rule came from it (strategy.md:62). The trigger text never names the declarer (civ6.py:1280).
- **Change:**
  - Word the trigger "X declared war on us" or "our AI declared war on X", taking the initiator from the diplomacy state or DiplomacySummary.csv.
  - Correct strategy.md:62 and :65.
- **Test:** a fixture where our player declared produces "our AI declared war on CIVILIZATION_AUSTRALIA", never "surprise war from Australia".

### Rules: triggers, cadence, learned rules

**L8. Exempt new war and city loss from the event-review cap in Civ VI.**
- **Evidence:** 15 of 18 war triggers skipped at T541-T570. The first wartime strategy came at T546 (H7).
- **Change:** give each game its own review cap in its pillars.toml (Civ VI: about 3 turns). Always review on "new war" and "city lost".
- **Test:** tests/test_civ6_governor.py: T541 after a T538 review runs a strategy review.

**L9. Decide every hand-back while a city stays in danger in war.**
- **Evidence:** no decisions in T559-T562, T571-T574 or T576-T582 while Guangzhou, Taiyuan and Longxi were IN DANGER (H6).
- **Change:** while at war with a major, trigger a decision at every hand-back where a city is IN DANGER, has no unit on its tile, and a defender is affordable under L1.
- **Test:** replay the T570-T574 snapshots and expect a decision each turn.

**L10. Add the missing warning triggers.**
- **Evidence:**
  - Australia went from 233 (T454) to 1,106 (T525) with no trigger (strategy-9).
  - The T291-T304 deficit had no trigger (strategy-8).
  - Haarlem's loyalty fell 95 to 41 over T546-T549, and Rockhampton's 93 to 3 over T552-T568.
- **Change:** port the Stellaris "falling behind" trigger (governor.py:379-383) to `civ6.urgent_changes`, emit a `behind` field in the Civ VI metrics rows, and add triggers for:
  - a met non-ally with at least 2x our military that grew 50% in 20 turns;
  - gold per turn turning negative;
  - loyalty below 50 and falling.
- **Test:**
  - The T512 fixture fires the neighbour trigger.
  - The T291 row fires "gold per turn negative".
  - The T547 Haarlem row fires the loyalty trigger.

**L11. Use one-turn chunks when military is last or a neighbour has at least 2x our military.**
- **Evidence:** the T539 war was seen one decision point late (war-1, reliability-5).
- **Caveat:** one-turn autoplay stops the AI's own city management and purchases (treasury-10).
- **Change:** make the rule conditional on the military ratio. Track production-queue neglect as a cost.
- **Test:** `autoplay_turns` returns 1 for the T538 snapshot (343 against 1,094).

**L12. Keep learned rules honest.**
- **Evidence:** the misread rules at T123, T546, T555, T563, T565 and T575 (S6).
- **Change:**
  - Before a rule is stored, check it against the hard purchase rules and against the price-tool results in the same episode.
  - Flag or remove the T263 and T302 peacetime rules and the rules above.
- **Test:** storing "save gold until the balance is double the unit cost" is refused once L1 is in.

### Pillar weights and milestones

**L13. Judge milestones on current values since they were set.**
- **Evidence:** "military >= 170 by T350" read met at T350 with 124. Military's share of effort was 2-7% at weight 22 (strategy-1).
- **Change:** store each milestone's creation turn. For level metrics, "met" means at or above target on the check date. This fix is shared with Stellaris.
- **Test:** tests/test_strategy.py: rows T326-T350 with the T342 milestone give at_risk, then missed.

**L14. Make military targets relative.**
- **Evidence:** targets were 0.44-0.56 of the median, never tied to the strongest non-allied neighbour (strategy-7). Rank milestones counted only 2 met civs (strategy-4).
- **Change:** while military is below 0.6x the median or ranked last, require one relative milestone: military / median, or military / strongest non-allied neighbour, of at least 0.5. Also:
  - reject absolute military targets under 0.5x the median;
  - reject rank milestones while fewer than 3 majors are met;
  - have the briefing say that peers are met civs only.
- **Test:** tests/test_civ6_strategy.py: the T525 strategy (520/580 against a median of 1,106) is sent back.

**L15. Keep a standing defender floor.**
- **Evidence:** the AI completed no combat-unit contract for China from T380 to T583 (war-3 verifier 2). At T538 there were 3 land units for 8 cities.
- **Change:** while the military pillar leads or ranks last:
  - fill idle queues in border cities with the best allowed defender;
  - keep one resource-free ranged defender (Machine Gun) per border city;
  - do not follow "leave the AI's production queues alone" for defender fills.
- **Test:** a T530 fixture with an idle border queue and military rank 6 of 6 gets a Machine Gun production order.

### Last stand

**L16. Fix the capture test before relying on the last stand.**
- **Evidence:**
  - `capture_adjacent` ignores ranged units that can capture, such as the GDR (RangedCombat 120, CanCapture true).
  - Beijing (T545) and Guangzhou (T565) met the walls and garrison tests, fell the next AI turn, and never tripped `about_to_fall` (war-12, both verifiers).
  - We had no land ranged units.
- **Change:**
  - Count any adjacent enemy with CanCapture as a capturer.
  - Add "garrison at 0 and walls at 0 with an enemy within 2" as falling.
  - Leave the stand off until it is calibrated on this campaign's T541-T579 snapshots. It could not have saved these cities.
- **Test:**
  - tests/test_harness_lua.py: unit_kind or the capture count treats a GDR-like row as a capturer.
  - tests/test_civ6_governor.py: the Beijing T545 city dict gives about_to_fall true.

### Detecting defeat and elimination

**L17. End the run when the player is gone.**
- **Evidence:**
  - 0 cities from T583.
  - 16 decisions and 4 reviews ran with 378,629 input tokens until a manual stop at T763.
  - 18 of 25 autoplay calls after T579 advanced more turns than requested.
  - The game ran on after the stop, and China was alive again from T913 while local player read -1 at T916 (reliability-1, reliability-3; reliability-2 corrections).
- **Change:**
  - Add `alive` (Players[me]:IsAlive()), cities, units and settlers to `H.snapshot()`.
  - If cities == 0 and no settlers, or the player is not alive: emit campaign_lost, write the final journal entry and strategy report, stop autoplay, end the run with status "lost" and make no more model calls.
  - Log the actual turns advanced. Treat an advance beyond the request as an anomaly that re-checks alive.
  - Do not use local_player == -1 as a death signal.
  - Tell the human that the game keeps playing all-AI turns after the stop. Find out what stops it; the game passed T1290 during this post-mortem.
  - Close issues.md line 5 once this is deployed.
- **Test:**
  - tests/test_civ6_governor.py: a T583 snapshot with 0 cities ends the run with status lost and no model call.
  - A fake autoplay that returns +29 turns on a 3-turn call emits the anomaly event.

### Diplomacy policy

**L18. Until levers exist, keep diplomacy out of the Strategist's goals. Then add read-back diplomacy orders.**
- **Evidence:**
  - "Get peace with Australia" was the goal at T563, T565 and T575, with no order kind able to pursue it (civ6.py:461; war-11).
  - The only alliance lapsed at T542 and was never renewed (diplomacy-3).
  - The auto-reply maps MAKE_PEACE to Goodbye (diplomacy-4).
  - Relations fields are not in the snapshot (diplomacy-6).
- **Change, short term:**
  - The Strategist validator rejects diplomacy goals that need an order kind we lack.
  - Put diplomatic state, grievances, friendship and alliance expiry, the last denouncement and visible agendas in `majors()` (API names confirmed live: GetDiplomaticStateIndex, GetGrievancesAgainst, GetDeclaredFriendshipTurn, GetAllianceType/Level, GetAgendaTypes, GetAtWarChangeTurn).
  - Add an "alliance expires within 5 turns" trigger.
  - Change MAKE_PEACE from EXIT to accept while at war and losing.
- **Change, medium term:** add "peace" and "renew alliance" orders through DealManager with gold/faith caps and read-back, first tested on a throwaway save. Remember that peace is illegal for 10 turns after a declaration (DIPLOMACY_WAR_MIN_TURNS=10).
- **Evidence limit:** no verified evidence shows these would have changed this war. They are capability gaps.
- **Test:**
  - tests/test_civ6_strategy.py: a "Get peace with Australia" goal is refused while no peace kind exists.
  - A majors() fixture shows alliance turns left.

### Model resilience

**L19. Never leave an urgent or treasury-peak decision without an action.**
- **Evidence:** T512, T522 and T525 failed on 503s and `request_limit` 6. T525 was the only pre-war window that a model outage wasted (treasury-4).
- **Change:**
  - On episode_error, retry at the same hand-back with the strategy role's model before autoplaying.
  - If that fails, run a deterministic fallback: fill idle research and queues (ruling 16) and buy the defender L1 allows for the city most in need.
  - Raise `governor_max_requests` for the pro-preview model, or cap its tool rounds.
- **Test:** tests/test_civ6_governor.py: a fake model raising 503 three times at a T525 fixture leads to a rule-based Machine Gun purchase, and no autoplay starts before it.

### Observability

**L20. Keep enough evidence to audit the governor.**
- **Evidence:**
  - Traces are cut at about 6,000 characters, so most per-city danger lines are missing (war minor finding).
  - The casus belli could have been read from DiplomacySummary.csv; the early analysis missed it by listing the wrong root.
- **Change:**
  - Store the full briefing per decision.
  - Read the game's diplomacy, World Congress and AI_CityBuild logs from civ6_appdata into telemetry (deals, declarations with the initiator, AI purchases in our name).
  - Record decisions per war turn and the actual turns advanced.
- **Test:** the telemetry row for a decision contains the full "Cities" block, and a declaration event names the initiator.

## 6. Lessons that transfer to Stellaris and GalCiv IV

These follow from this campaign's evidence. They have not been verified in those games.

**T1. Fix `milestone_status` once for both governors.**
- The "ever met" rule lives in shared code (src/pilot/strategy.py:356-362). The Stellaris governor uses it through governor.py (lines 76, 2249, 2301 and 2312).
- The Civ VI fix (L13) and its test in tests/test_strategy.py also cover Stellaris. A Stellaris milestone set below a past high will read met today.

**T2. Express every shared time constant in the game's own unit.**
- The 12-"month" event-review cap (governor.py:2202-2218) silently became 12 turns in Civ VI.
- Audit governor.py for month-based constants. Move each into the game's pillars.toml with a per-game value, and test each game's value.

**T3. Measure what the native AI does with our stock between decisions.**
- Both governors hand the empire to the game's AI: `human_ai` in Stellaris, AutoplayManager in Civ VI.
- Before calling a stock "idle", compute balance delta minus yield minus our own orders, and name the spender where a log exists.
- Reserve what a directive needs before handing control back.

**T4. Scale share-of-balance caps with late-game prices.**
- Civ VI's 0.5 cap was calibrated on Ancient-era prices of 80-240 (levers rulings 17-19) and bound every Future-era defender.
- Any cap written as a share of a balance should be checked against the prices seen at the end of a game: Stellaris market sync, and alloy or ship purchases.

**T5. Warn on relative strength against the strongest non-allied neighbour, not only the median.**
- Stellaris has "falling behind other empires" against the median.
- Neither game warned about a neighbour at 3x our strength, which is what preceded this war.
- In GalCiv IV, add this to corpora/galciv4/strategy.md as a decision rule for the model.

**T6. Every loop needs a terminal state.**
- The Stellaris governor and the GalCiv IV autopilot should detect defeat or elimination, then stop and report instead of continuing:
  - Stellaris: no owned planets or capital lost, read from the autosave briefing.
  - GalCiv IV: the defeat screen as a `[screens.*]` entry with a stop action, never `auto_dismiss`.
- Log the actual turns or months advanced against the request, and treat overruns as anomalies.

**T7. Re-send only with proof.**
- A lost reply should be retried only when a read-back proves it did not take: Stellaris directives confirmed in game.log, GalCiv clicks confirmed by a fresh frame.
- Never re-send blindly, and never drop it silently.

**T8. Report order success by item class.** A 100% purchase stick rate made of cheap buildings misled the Civ VI Strategist about unit purchases. Stellaris's order record should split by class too.

**T9. Name the actor in every war or diplomatic event.** The Civ VI governor learned a false rule from a war its own AI declared. Stellaris game.log lines and GalCiv trade screens should record who initiated.

**T10. Deploys should restart only the affected game's pilot.** A Stellaris-only merge restarted the live Civ VI run at T462 (reliability minor finding, not verified).

## 7. Claims that were refuted, and why

Seven claims were refuted by both verifiers.

**war-2: "The casus belli and Australia's reasons cannot be recovered."**
- The "0 bytes" listing was stale. DiplomacySummary.csv (277 KB), DiplomacyModifiers.csv and DiplomacyManager.csv under civ6_appdata hold the whole game.
- They record a Surprise war: "539, 5, Team 0, Individual Declaring War on Team START, Surprise".
- Mali joined through its Defensive Pact with China ("539, 3, Team 5, ... Defensive Pact").
- Australia's opinion of China was net positive, with Same Government +20 and grievances 0 since T469.
- The listed denunciations had decayed to between 0 and -3. They are not credible causes.
- Only the AI's internal motive is unlogged: AI_Diplomacy.csv is 0 bytes.

**treasury-1: "The 50% cap made every pre-war defender purchase impossible (2x = 2,160-2,320 faith)."**
- Not every one. At T486 faith was 1,607, so the cap was 803, and an 800-faith AT Crew was buildable. The model never priced it.
- The threshold before Composites was 1,600, not 2,160.
- Mechanized Infantry was refused by the game at every check, whatever the cap.
- Both verifiers put the cap's effect at 4-5 units (+400-500) and called it a missed lever, not decisive.

**treasury-3: "The game's AI drained about 15k gold and 15k faith on unlogged items, which kept the balance from ever reaching 2x."**
- The faith was logged. Each of the 9 bursts is an AI_CityBuild.csv "FAITH PURCHASE, UNIT_ROCK_BAND" row (T461-T534, 15,247 faith). The analyst had filtered only "PURCHASE" rows.
- The 2x bar was reached twice, at T486 and T525, and the governor failed both times.
- The binding mechanism was the governor's own cap.

**treasury-5: "During the collapse the treasury was spent at about one unit per decision, roughly what the balances allowed."**
- The rate was 7 units in 21 decisions (0.33 per decision), against a limit of 2 purchases per decision.
- Balances covered a Modern AT at T541, T545, T552, T555, T556, T565 and T575, and nothing was bought.
- The model cited the 50% cap and the cooldown.
- The empire ended with 1,676 gold and 995 faith unspent.

**strategy-2: "The decider deferred defender purchases on the cap about 13 times."**
- The cap was the only binding limit in 5 of the 14 cited decisions: T365, T475, T496, T504 and T538, plus T454, uncited.
- In the other 9, the balance was below the price or the game refused the unit (allowed=false).
- The effect was minor: at most 4-5 defenders against a gap of 751.

**strategy-5: "Our production orders set production mainly by cancelling the AI's defensive builds."**
- About 1 order in 10 did so: 9 of 82-91 orders, all between T282 and T332. The AI rebuilt most of them.
- Steel's Urban Defenses made walls obsolete before the war.
- Wall status did not predict the order in which cities fell. Longxi never had walls and fell last.
- Australia also logged few unit starts, yet its military grew from 0 to 1,094.

**reliability-2: "The root cause of the missed defeat is the snapshot's fallback to the dead player, the missing alive field and the missing elimination check."**
- The defeat was detected.
  - T583 triggered "urgent: city lost: Longxi".
  - The model wrote "0 cities, 0 units".
  - The review wrote "The game is effectively lost."
- The fallback returned the correct player and surfaced the true state.
- The root cause is that the loop has no end state and the model has no end-run action.
- local_player == -1 is not a death signal: China was alive again from T913 while local read -1 at T916.

Beyond these seven, the causality verifier rejected the causal weight of every [one verifier] claim. The reasons are given with each claim in Section 2. The most common reason: every city that received a bought Modern AT still fell, against an enemy three to twelve times stronger.

## Appendix: claim register

Key: E = evidence verifier, C = causality verifier; U = upheld, R = refuted.

| ID | Claim (short) | Analyst weight | E | C | Label |
|---|---|---|---|---|---|
| war-1 | T539 war hidden in a 3-turn chunk, seen at T541 | major | U | R | one verifier |
| war-2 | Casus belli unrecoverable | contributing | R | R | refuted |
| war-3 | Force ratio decided the war | major | U | U | both verifiers |
| war-4 | City-by-city losses, 6 conquered and 3 to loyalty | major | U | U | both verifiers |
| war-5 | 50% cap in war blocked defenders the game allowed | major | U | R | one verifier |
| war-6 | Defender list showed only Oil units, which misled the model | contributing | U | R | one verifier |
| war-7 | 12-"month" review cap skipped war reviews | contributing | U | R | one verifier |
| war-8 | Change-only triggers; no decisions T571-T574 or T576-T579 | contributing | U | R | one verifier |
| war-9 | Tuner timeouts lost purchases, never re-sent | contributing | U | R | one verifier |
| war-10 | No pre-war defender; model errors; Mali and Maya named as threats | contributing | U | R | one verifier |
| war-11 | No diplomatic signal or lever; peace goal unpursuable | contributing | U | R | one verifier |
| war-12 | Last stand would not have run or mattered | major | U | U | both verifiers |
| treasury-1 | Cap made every pre-war defender purchase impossible | major | R | R | refuted |
| treasury-2 | No defender bought in the 80 pre-war turns | major | U | R | one verifier |
| treasury-3 | AI drain on unlogged items; balance never at 2x | major | R | R | refuted |
| treasury-4 | T525 faith window lost to model errors | contributing | U | R | one verifier |
| treasury-5 | Wartime spending matched the balances | major | R | R | refuted |
| treasury-6 | Cap blocked or deterred 7 wartime purchases | major | U | R | one verifier |
| treasury-7 | Briefing list hid the buyable Modern AT | contributing | U | R | one verifier |
| treasury-8 | Gold price halving ended; treasury stranded | contributing | U | R | one verifier |
| treasury-9 | Timeouts lost 2 purchases; Longxi never retried | contributing | U | R | one verifier |
| treasury-10 | No AI purchases after T539; one-turn autoplay | contributing | U | R | one verifier |
| treasury-11 | No rule could save the empire in war; the missed contribution was pre-war | contributing | U | U | both verifiers |
| strategy-1 | Sticky "met" milestones hid the military decline | major | U | R | one verifier |
| strategy-2 | Cap deferred defenders about 13 times | major | R | R | refuted |
| strategy-3 | AI spent the faith on Apostles and Rock Bands | major | U | R | one verifier |
| strategy-4 | Peacetime doctrine T197-T302 | major | U | R | one verifier |
| strategy-5 | Orders mainly cancelled the AI's defences | contributing | R | R | refuted |
| strategy-6 | Faith stick rate came from cheap buildings | contributing | U | R | one verifier |
| strategy-7 | Military targets 10-25% above our own strength | contributing | U | R | one verifier |
| strategy-8 | T302-T305 military drop during an undetected deficit | contributing | U | R | one verifier |
| strategy-9 | No rank trigger; military-missed triggers bought nothing | contributing | U | R | one verifier |
| reliability-1 | Elimination not acted on; ran to T763 | major | U | R | one verifier |
| reliability-2 | Root cause is the fallback and no alive field | major | R | R | refuted |
| reliability-3 | Turn overruns after elimination ignored | major | U | R | one verifier |
| reliability-4 | Harness outages were not the main cause | major | U | U | both verifiers |
| reliability-5 | 3-turn stretch hid the war | contributing | U | R | one verifier |
| reliability-6 | Lost purchases not re-sent | contributing | U | R | one verifier |
| reliability-7 | Change-only triggers; "city falling" never fired | contributing | U | R | one verifier |
| diplomacy-1 | War not driven by relations; China weakest | major | U | R | one verifier |
| diplomacy-2 | The game's AI ran all diplomacy; no lever | contributing | U | R | one verifier |
| diplomacy-3 | Isolated; the alliance did not stop the collapse | contributing | U | R | one verifier |
| diplomacy-4 | No peace proposed; no lever | contributing | U | R | one verifier |
| diplomacy-5 | T121 war misattributed; false learned rule | contributing | U | R | one verifier |
| diplomacy-6 | Model could not see relations | contributing | U | R | one verifier |

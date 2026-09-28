# Civ VI campaign: Japan, Hojo Tokimune (civ6/hojo_887816960)

Started 2026-09-28 on mini-rig2 with the post-mortem fixes deployed: Prince, Standard speed, Continents,
Small map, disaster intensity 2 (the game's remembered settings; only the leader changed).

## 2026-09-28 — T1 → T338, stopped by the user

- T1: the opening strategy was accepted (Strategist `claude-code:opus`); the first autoplay start's
  reply was lost, the bounded wait and second look found the game idle, and the start was re-sent.
- T258: the tuner went quiet around a World Congress session and the run stopped with "no snapshot
  after 3 tries"; resumed by hand. Fixed the same day (47841cc): a silent tuner now probes and carries on.
- T338 (1917 AD): stopped at the user's request; the governor stopped autoplay and the game was exited to
  the desktop through the pause menu's own handler (`OnExitGame` in `InGameTopOptionsMenu`). The autosave
  holds the campaign.
- State at T338: 4 cities, population 34, science 29, culture 37, gold 0, faith 348, military 152, score
  510, 3 wars; 3rd of the majors in score, military and techs.

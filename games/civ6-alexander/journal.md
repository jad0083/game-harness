# Civ VI campaign: Macedon — Alexander (`civ6/alexander_1792126623`)

Started 2026-10-05 on mini-rig2 with Single Player > Play Now (the remembered setup: Prince, Standard
speed, Continents, Small map; the leader was random). First campaign with the model guard deployed
(docs/design/2026-10-02-model-guard-design.md).

## 2026-10-05 — T1 → T60, stopped by the user

- Bringing the PC back: the console was locked; unlocked with the SYSTEM `tsdiscon`/`tscon` task and
  started through Steam from a task as the signed-in user (AGENTS.md §11).
- The opening strategy took about 6 minutes on Gemini 3.1 Pro (thinking high), with a 504 and a 503
  each recovered by the guard's one retry inside the run.
- Model guard over 20 model calls (strategy and decisions): 13 single retries, 8 failovers inside a
  run, 20 breaker changes, no failed decision and no `pool_exhausted`. Gemini 3.8 Flash answered 503
  almost every time this morning, so 3.1 Pro made nearly every decision. Decision time: median 42 s;
  the slow ones (143 s, 300 s) came from a 3.1 Pro request that hung about 2 minutes before a 504 and
  from waiting for a trial, since the decision pool had only two Gemini models and no third family.
- T45: "autoplay did not start" (game side); it recovered by itself.
- Stopped at T60 at the user's request: the pilot stopped through its control and the game exited to
  the desktop through the pause menu's handler (`OnExitGame` in `InGameTopOptionsMenu`). The autosave
  holds the campaign.
- State at T60: 1 city (Pella), population 3, science 3.5, culture 3.9, gold 168, military 64, score
  35, at peace; 2nd of the met majors in score, military, techs and civics.

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

## 2026-10-05 (afternoon) — T60 → T174, stopped by the user

- Resumed from the T60 autosave (Resume Game; Continue Game answered about 4 minutes after loading)
  after two Gemini probes (docs/pilot.md): the decision pool became gemini-pro-latest first and
  gemini-3.8-flash second, no rotation; at the user's request the Strategy role's Claude Opus fallback
  was replaced by gemini-3.8-flash during the run ("no claude"), so the pools are Gemini only.
- 47 decisions in 86 minutes: median 36 s, p90 285 s, max 440 s; 41 answered by gemini-pro-latest.
  The guard logged 23 retries, 14 failovers and 32 breaker changes. The long tail is gemini-pro-latest
  requests that hang about 2 minutes before a 504 or a read timeout, then the wait for a trial.
- One strategy review failed after the Claude removal with every Gemini model overloaded
  (`pool_exhausted`, role strategy); the run carried on with the strategy it had.
- Stopped at T174 at the user's request (pilot stopped through its control; the game exited through
  `OnExitGame`). State at T174: 4 cities, population 19, science 15.2, culture 14.3, military 93,
  score 168, 3 wars; 3rd of the met majors in score (median 402).

## T174-T221 (2026-10-06): the first run on the data platform

- Resumed hands-off on mini-rig2 (one-off task launched the game; esc, Single Player, Resume Game,
  Continue Game about 2.5 minutes after the load started). Run `20261006-063027`, the first on
  `runs/pilot.db`: events, 18 decision traces, journal lines, two learned rules (T181 review) and model
  usage all landed in the store; the learned overlay was rebuilt at start and after the new rules;
  nothing under `corpora/` or `games/` changed at run time.
- Gemini was overloaded for most of the hour: 9 strategy reviews and 7 decisions were lost when
  gemini-pro-latest and gemini-3.8-flash answered 503/504 in the same minute (`pool_exhausted`); the
  game's AI played on between them. A dashboard question asked while the decision held the only open
  model's trial was refused at once; asked again it was answered (issues.md).
- Stopped at T221 when the user moved on to the next sub-project (pilot stopped, game exited through
  `OnExitGame`). State at T221: Industrial era, 4 cities, population 26, science 30.1, culture 19.4,
  gold per turn -0.8, military 92, score 213, 3 wars (Germany at 278 military, 10 cities); 3rd of the met
  majors in score (median 536.5), 2nd in military.

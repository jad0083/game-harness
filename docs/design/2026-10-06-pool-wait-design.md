# Pool wait: a role's models all down waits for one to come back

Date: 2026-10-06. Status: approved in conversation ("go until deploy"); rulings below are numbered from 1.
Base: `main` at 5ec67ee. Amends the model guard design (docs/design/2026-10-02-model-guard-design.md),
ruling 11.

## Evidence

- **E1. Today's live hour** (Alexander, run 20261006-063027, pools gemini-pro-latest then gemini-3.8-flash):
  - Every model of a role's pool was unavailable at once 17 times (`pool_exhausted`).
  - The losses were 9 strategy reviews, 7 decisions and 1 chat answer.
  - The time from each exhaustion to the next answered model call (seconds): 273, 153, 2, 106, 0, 31, 1, 31, 1, 47,
    36, 36, 0, 200, 43, 0, 185. The median is 36 s; 13 of the 17 came within 120 s, 16 within 210 s, and all within
    273 s. The next answered call may belong to another role, so these gaps approximate when the pool came back.
- **E2. Ruling 11 today** (`PoolModel.request`, modelguard.py ~713):
  - When no model can take a request, the pool waits ONCE for the earliest open breaker's window, and only if that
    window ends within `pool_max_wait_s` (60 s). Otherwise it raises `PoolExhausted` at once.
  - It also raises at once when the only models left are `half_open` (another request holds the trial; `earliest_reopen`
    counts only `open`). That is how the dashboard chat failed while the decision held the trial.
  - A failed trial doubles the window, so the second outage minute is never waited for.
- **E3. A failed strategy review is already retried at the next decision** (`_review_strategy` sets `review_requested`
  and `_review_retry`). The 9 lost reviews were mostly such retries meeting the same outage. No change is needed there.
- **E4. The 503s do not depend on our request rate** (the 2026-10-04 probes). Waiting is the lever; pacing is not.

## Goal

An outage of a role's whole pool costs wall-clock time, up to a cap, not a lost decision, review or chat answer. During
a decision the game is paused (Stellaris) or between autoplay turns (Civ VI), so the time is cheap.

## Non-goals

- More models, other providers, or changes to the pools (the user keeps them Gemini only; gemini-3.1-pro-preview shares
  the gemini-pro family with gemini-pro-latest, so it would add little).
- Changes to per-model retries, breaker windows, family caution or pacing.

## Rulings

1. **The pool waits, repeatedly, up to a total budget.**
   - When `ordered()` is empty, the pool sleeps until the earliest moment a model of the pool can be tried, and tries
     again. It repeats until the request's total waiting reaches `pool_max_wait_s`, then raises `PoolExhausted` as
     today.
   - The earliest moment is the smaller of two things:
     - the earliest `until` of the pool's `open` breakers;
     - one poll step (`POOL_POLL_S = 2` s) when any of the pool's models is `half_open`, because another request holds
       its trial and its outcome decides.
   - A pool whose remaining models are all `broken` raises at once (nothing will come back).
   - Failover between models stays immediate. Only the all-down case waits.
2. **The budget.**
   - `pool_max_wait_s` becomes the total wait per request: default 120 s (the user's choice; it covers 13 of today's 17
     outages, and `PILOT_POOL_WAIT_S` raises it without a release).
   - It is set by `PILOT_POOL_WAIT_S` (seconds, a number ≥ 0). `0` restores fail-at-once.
   - A model call that is answered resets nothing; the budget is per request.
3. **Stop requests end the wait.**
   - `Hooks` gains `stopping: Callable[[], bool]` (default: never). The pool sleeps in steps of at most 1 s and checks it
     between steps.
   - When it says stop, the pool raises `PoolExhausted` with the cause "stopped while waiting". A page Stop or a
     container stop is never held up by a wait.
   - The governors and the GalCiv pilot pass their `control.stopping`.
4. **The wait is reported.**
   - `Hooks` gains `on_wait(models, seconds, waited, reason)`. `event_hooks` emits `model_wait` with the role, the
     models waited for, `seconds` (this sleep), `waited_s` (so far in this request), `budget_s` and `reason`:
     - "every model is overloaded"/"unavailable" (open breakers);
     - "a trial is running on <model>" (half_open).
   - The dashboard's Activity line reads "Waiting up to 1 m 30 s for Gemini to recover (every model is overloaded),
     45 s so far". The Deciding card shows the same while a decision waits.
5. **Every role's pool waits the same way:** decisions, strategy, chat, the retrospective and the GalCiv episodes. A chat
   answer waits for the trial the decision holds instead of failing.

## Tests

- **Fake clock and fake sleep (modelguard):**
  - all models open, one window ending within the budget → the request succeeds after waiting;
  - windows keep moving (a failed trial doubles them) until the budget runs out → `PoolExhausted` after ≤ budget;
  - a `half_open` model whose trial succeeds while the second request waits → the second request is answered;
  - all `broken` → raises at once;
  - `stopping()` turning true mid-wait → raises within one step;
  - `pool_max_wait_s=0` → raises at once (old behaviour);
  - `on_wait` is called with the right reason and totals.
- **Config:** `PILOT_POOL_WAIT_S` is parsed and validated (a negative or non-number is an error naming it).
- **Governor wiring:** `stopping` reaches the pool hooks (Stellaris, Civ VI, GalCiv).
- **Dashboard:** the `model_wait` line in Activity and on the Deciding card (UI test).

## Docs

- docs/pilot.md, model guard section: ruling 11 replaced by the budgeted wait; the settings table row `pool_max_wait_s`
  becomes 120 s with `PILOT_POOL_WAIT_S`.
- `.env.example`: `PILOT_POOL_WAIT_S` under Optional.
- issues.md: the "a one-model pool whose request loses the race for the model's trial gives up at once" and "Gemini-only
  pools lose a strategy review" entries are ticked when deployed.

## Rollout

Merge, then CI publishes a new image (`project.version` 0.1.1, so the version tag is new). Bump the pin in
jad0083/stacks `apps/personal/game-pilot/compose.yaml`, and Komodo redeploys. Then check: a `model_wait` appears in a
forced test (a unit test covers it), and the container is healthy with the new digest.

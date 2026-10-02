# Model guard: pacing, retries, circuit breakers and failover for model calls

Date: 2026-10-02. Status: design approved in conversation (approach A, "fail over fast"); rulings below are
numbered from 1. Base: `main` at 8c80134 (all code line numbers).

This design changes how the pilot calls models (Gemini through the public Gemini Developer API, Claude through
the Anthropic API and the claude-code CLI). It replaces whole-run retries in the governor with a guard on
every model request: pacing, error classification, at most one short retry, a circuit breaker per model, and
failover to another model family that continues the same run.

Sources: `runs/telemetry.sqlite` (read-only; 51 runs, 1,123 decisions, 2026-09-25 to 2026-09-28), the code at
8c80134, pydantic-ai-slim 2.51.0, google-genai 2.25.0 and anthropic as installed in `.venv`, and the Gemini
Developer API's documented behaviour (503 means the service is overloaded or down; every quota, rate and
spend limit returns 429, per project; daily quotas reset at midnight Pacific). Notes about Google's internal
Jetski tool (per-user buckets, User-Agent allowlists, backend pools) do not apply to the pilot's API key and
are not used.

---

## Evidence

- **E1. No quota errors, only capacity errors.** 389 `model_retry` and 164 `model_fallback` events; every
  Gemini error is 503 "This model is currently experiencing high demand" (UNAVAILABLE) or a timeout. No 429
  in any run.
- **E2. Retries work a third of the time each.** The governor retries the first model of a call after 5, 15
  and 45 s (`config.py:57`, `governor.py:722`); other models get one try. Of 188 first-model 503 sequences:
  66 answered after 1 retry, 39 after 2, 23 after 3 (65 s of waits), 60 fell back. Per-retry success:
  35%, 32%, 29%.
- **E3. Sibling Flash models fail together; other families do not.** 3.8 Flash -> 3.7 Flash: 31 of 45
  fallbacks were also 503. 3.7 Flash -> 3.1 Pro answered 58 of 60. Claude answered 3 of 3.
- **E4. Overload comes in episodes.** 3.8 Flash: 271 503s in 66 episodes (gaps under 10 min), median 1.6
  min, longest 30 min. 3.7 Flash: 203 in 70, median 1.4 min, longest 38 min. 3.1 Pro: 21 in 14, longest
  8 min. Most between 08:00 and 13:00 Pacific.
- **E5. Waits drive the decision tail.** Decision seconds: p50 23, p90 100, p99 208, max 399.
- **E6. Retries replay whole runs.** `run_with_retry` (`agent.py:28`) wraps `agent.run_sync`, so a 503 on
  a later request of a run starts the run again from its first request. A run's tools send real game
  actions (directives, market orders, Civ VI orders and purchases), which a replay can issue again.
- **E7. No hidden SDK retries for Gemini, two for Anthropic.** pydantic-ai passes `retry_options=None` to
  google-genai, whose `retry_args(None)` is `stop_after_attempt(1)`. pydantic-ai's Anthropic provider
  builds `AsyncAnthropic(...)` without `max_retries`, so the SDK default of 2 retries applies.
- **E8. The live pools.** Decisions: 3.8 Flash, 3.7 Flash, 3.1 Pro (thinking high, rotating). Strategy:
  claude-code opus, 3.1 Pro (rotating). Up to 6 model requests per decision (`governor_max_requests`),
  about 40k input tokens per request. One pilot process at a time; the dashboard viewer makes no model calls.

## Goals and success criteria

1. A failed request never makes a tool run twice (E6).
2. Retries happen in exactly one place: the guard (E7).
3. During a Flash overload episode a decision moves to another family within seconds, not after 65 s of
   waits (E2-E5).
4. Quota and rate errors (429), when they appear, are honoured instead of retried blindly.
5. An optional minimum gap between requests and optional per-model limits keep calls inside known quotas.

Measured on the first 100 decisions after deployment, against the baseline above: no repeated tool call,
zero 429s, decision p90 under 60 s.

## Non-goals

The Gemini Priority tier (needs the Interactions API), the Batch API, Vertex AI Provisioned Throughput,
anything specific to Jetski, and model choice itself (which models are in which pool stays a dashboard
setting). These remain future options.

---

## Rulings

### Structure

1. **One module, three parts.** `src/pilot/modelguard.py` holds `ModelHealth`, `GuardedModel` and
   `PoolModel`. Nothing game-specific goes in it.
2. **`ModelHealth` is per process.** One instance per pilot process, shared by every role and thread
   (decisions, strategy, chat, episodes). Per model it keeps: breaker state (`closed`, `open` until a time,
   `half_open` while one trial runs, `broken`), consecutive openings, the last request time (pacing), the
   last input token count, today's request count, and the reason of the last opening. All access goes
   through one `threading.Lock`; the lock is never held across a wait or a request.
3. **Families.** Each model belongs to one family, derived from its name unless `model_families` says
   otherwise: Gemini names containing `flash-lite` -> `gemini-flash-lite`; `flash` -> `gemini-flash`; `pro`
   -> `gemini-pro`; other Gemini -> `gemini`; `anthropic:*` and `claude-code:*` -> `claude`; anything else
   -> its provider prefix. E3 is why: siblings fail together.
4. **`GuardedModel` wraps every model object** (a pydantic-ai `WrapperModel`). It carries that pool
   entry's own model settings (its thinking level, built by the existing `model_settings` rules for its
   provider) and merges them into each request, so models of different providers can share one agent whose
   own settings hold only what is common (the timeout). Per request it: waits for its pacing slot (rulings
   12-13), sends the request, classifies a failure (ruling 6), retries once where ruling 7 allows, updates
   `ModelHealth`, and raises `ModelUnavailable(model, kind, until, cause)` when the model cannot answer.
5. **`PoolModel` holds a role's models** (a pydantic-ai `Model`, built after `FallbackModel`). On every
   request it orders its entries (ruling 10), calls each in turn, and on `ModelUnavailable` sends the same
   messages (the run's history so far, prepared for that model) to the next one. The run continues; tools
   that already ran are not run again. When none can answer it raises `PoolExhausted` with each model's
   cause. A successful response carries the model name that produced it.

### Failure rules

6. **Classification.** From the exception (`ModelHTTPError` status and body, httpx errors, timeouts,
   `ClaudeCodeError`):
   - `overloaded`: HTTP 500, 502, 503, 504, 529; connection errors (`ConnectError`, `RemoteProtocolError`).
   - `timeout`: the request passed `model_timeout_s` (`httpx.TimeoutException`, `TimeoutError`).
   - `rate_limited`: HTTP 429 whose body has no daily quota id; `retry_after` from the body's
     `google.rpc.RetryInfo` `retryDelay` when present.
   - `daily_quota`: HTTP 429 whose `google.rpc.QuotaFailure` quota id contains `PerDay`.
   - `broken`: HTTP 401, 403, 404 (key, permission, or model name).
   - `rejected`: HTTP 400 and 422 (this request).
   - `other`: anything else from the model.
   pydantic-ai's own `UsageLimitExceeded` (the per-decision request cap) is not a model failure and passes
   through untouched, as today.
7. **What each kind does** (starting values; all are settings, ruling 15):

   | Kind | Retry on the same model | Breaker |
   |---|---|---|
   | overloaded | once, after a uniform random 1-2 s, unless this request is the model's half-open trial | opens (ruling 8) |
   | timeout | no | opens |
   | rate_limited, `retry_after` <= 10 s | once, after `retry_after` plus up to 1 s of jitter | stays closed if the retry answers, else opens |
   | rate_limited, longer or none | no | opens for max(`retry_after`, 60 s) |
   | daily_quota | no | opens until the next midnight in America/Los_Angeles |
   | broken | never | `broken` until the pool is rebuilt (a model or role change) or the pilot restarts |
   | rejected | never | unchanged |
   | other | no | opens |

   After the retry (or without one) the request fails over (ruling 5).
8. **Breaker windows.** An opening lasts `breaker_open_s` (60 s) times 2^(consecutive openings - 1),
   capped at `breaker_max_s` (600 s). When the window ends, the next request that would use the model is its
   single trial (`half_open`; concurrent requests skip it meanwhile). A trial that answers closes the
   breaker and resets the count; any failure reopens it with the next window. A model that answers outside a
   trial also resets the count.
9. **Family caution.** While a model's breaker is open after `overloaded` or `timeout`, the other models of
   its family are ordered after every other family (not skipped). This is what E3 measured.
10. **Order per request.** The role's configured list, rotated as today when `rotate` is on (the rotation
    is chosen once per run by `_call` and kept for every request of that run). Open and broken models are
    skipped. Closed models of a family under caution move after the models of every other family. A model
    due for its half-open trial keeps its configured place: the trial is how a preferred model comes back,
    and a failed trial costs one fast request (no retry).
11. **Everything open.** If no model can be tried, the pool waits for the earliest window to end when that
    is at most `pool_max_wait_s` (60 s) away, then tries that model; otherwise it raises `PoolExhausted`
    at once. The governor then follows today's path: ruling 20 of the post-mortem fixes (retry the decision
    once on the Strategy role's models, which go through the same `ModelHealth`), then decisions by rule,
    then the needs-attention notice. The game is paused meanwhile, as today.

### Pacing and limits

12. **A minimum gap per provider.** `min_call_interval_s` maps a provider prefix to seconds between
    request starts: `google` 0.5, everything else 0. One slot reservation per request under the
    `ModelHealth` lock; the wait itself happens outside it.
13. **Optional per-model limits.** `model_limits` maps a model to any of `rpm`, `tpm`, `daily_requests`.
    The gap for that model becomes max(provider floor, 60 / rpm, 60 x last input tokens / tpm): the
    formula interval >= W x max(60 / RPM, 60 x tokens per request / TPM) with W = 1, since one pilot
    process makes the calls. When `daily_requests` is reached, the breaker opens until the next midnight
    Pacific (reason `daily budget`). None are set by default: E1 shows no limit was reached.
14. **Daily counts survive restarts.** Requests per model per Pacific date are written to
    `runs/model-usage.json` (after each request, atomically; entries older than 7 days dropped). A file
    that is missing or unreadable starts the day's counts at 0 and logs one line.

### Settings, compatibility and the old path

15. **Settings** (`config.py`, environment in brackets; JSON for maps):
    - `model_guard` [`PILOT_MODEL_GUARD`, default 1]: 0 runs today's code path (rulings 19-20).
    - `overload_retry_s` (1.0, 2.0); `rate_retry_max_s` 10; `breaker_open_s` 60; `breaker_max_s` 600;
      `pool_max_wait_s` 60.
    - `min_call_interval_s` [`PILOT_MIN_CALL_INTERVAL`] `{"google": 0.5}`.
    - `model_limits` [`PILOT_MODEL_LIMITS`] `{}`; `model_families` [`PILOT_MODEL_FAMILIES`] `{}`.
    - `model_timeout_s` stays (120 s per request).
16. **One place for retries.** Gemini models keep google-genai's `retry_options` unset (a test asserts it).
    Anthropic models are built with a provider whose client has `max_retries=0`. claude-code keeps no retry
    of its own.
17. **The governor's `_call`** (`governor.py:700`) runs the role's single pool agent once (no
    `run_with_retry`), with the run's rotation set on the role's pool under a per-role lock held for the
    run (two runs of one role never overlap today; the lock makes it explicit). The entry that answered is
    found from the response's model name, so decisions keep `model`, `model_version` and `thinking`, and
    the dashboard's "deciding" information (model, attempt, already tried, skipped) is updated from the
    pool's callback on each try. `_retry_decision` (post-mortem ruling 20) runs the decisions agent with the Strategy
    pool passed as the run's `model`. `set_models`, `set_roles` and `set_fallback` rebuild the pools; a
    rebuild clears `broken` marks of the models it changes.
18. **The GC4 episode path** (`agent.py:320`) runs its agent with a pool of `model` and `fallback_model`
    instead of `run_with_retry`.
19. **Kill switch.** With `model_guard` 0 the code runs exactly as at 8c80134 (whole-run retries,
    `retry_delays`, `model_cooldown_s`). It exists for one campaign.
20. **Removal.** After one full campaign on the guard meets the success criteria, `run_with_retry`,
    `retry_delays`, `model_cooldown_s` and the kill switch are removed in their own commit.

### Telemetry and the dashboard

21. **Existing events keep their names and fields.** `model_retry` keeps `error` ("model X answered 503"),
    `delay` and `attempt`; `model_fallback` keeps `role`, `model`, `error` and `fallback`. Both gain
    `kind` (ruling 6), `family` and `request` (the request's number in the run). The dashboard's decision
    attempts (`dashboard.py:385`, `wording.py:213`) keep working unchanged.
22. **New events.** `model_breaker` {model, family, state: open | half_open | closed | broken, until,
    reason, openings} on every state change; `model_pace` {model, waited_s} only for waits of 1 s or more;
    `pool_exhausted` {role, causes}. Each gets an Activity sentence (the existing test requires one per
    emitted kind) and belongs to the model kinds.
23. **A model-health line on Now.** While any breaker is open or broken, or a family is under caution, Now
    shows one line, e.g. "Skipped: Gemini 3.8 Flash until 10:42 (overloaded, 3rd time); 3.7 Flash after
    other families". The models panel shows today's request count per model. Both read `info.model_health`,
    which `ModelHealth` publishes on each change.
24. **Docs.** `docs/pilot.md` gets a "Model calls" section (the rules, the pacing formula, the settings);
    `README.md` settings rows; `ARCHITECTURE.md` the module; `plan.md` and `issues.md` entries (the replay
    risk of E6 is an issue until deployed).

### Tests

25. **Required tests** (fake clock and sleep; models are pydantic-ai `FunctionModel`s that raise
    `ModelHTTPError` with real-shaped bodies):
    - a 503 on the second request of a run fails over to the next model and the run's tool ran exactly once;
    - every row of ruling 7, including the 1-2 s jitter range, the RetryInfo wait, `PerDay` reopening at
      midnight Pacific (across a DST change), and no retry for 400/403/404;
    - breaker doubling and cap, the single half-open trial, reset on success;
    - order: rotation kept for the whole run, family caution, open and broken skipped;
    - all open: the wait up to `pool_max_wait_s`, then `PoolExhausted`; the governor's post-mortem ruling 20 retry
      and rule fallback still run after it;
    - pacing: the provider floor, the rpm and tpm formula, the daily budget and its file across a restart;
    - a run that starts on Gemini (with thought parts in its history) continues on an Anthropic model: the
      messages are prepared without error;
    - google-genai `retry_options` is None and the Anthropic client's `max_retries` is 0;
    - `model_guard` 0 behaves as at 8c80134 (the existing retry tests run against it);
    - the decision record names the model that answered after a failover;
    - Activity sentences for the new kinds; a Playwright test for the model-health line.

### Rollout

26. **Deploy** with `scripts/deploy-pilot.sh <from> <to>` after merging; no pilot runs now, so the viewer
    restarts for the dashboard and the next campaign starts on the guard.
27. **Verify live** on the first overload: `model_retry` with `kind` overloaded, `model_breaker` open,
    the same run answered by another family, and the order record free of repeated actions. Then the
    success criteria over 100 decisions; the numbers go into the campaign journal and this design's status.

---

## Risks

- **Cross-provider history.** A run that fails over from Gemini to Claude sends Claude a history with
  Gemini thought parts. pydantic-ai prepares messages per model (as `FallbackModel` does); ruling 25 tests
  it. If a provider still rejects such a history, that request is `rejected` and the pool moves on.
- **Fail-fast spends more on Pro and Claude** during Flash episodes (E4: up to 38 min). That is the chosen
  trade; `model_limits` can cap a model per day.
- **A shorter first retry (1-2 s) may succeed less often than today's 5 s** (35%). Failover answers
  58 of 60 times on another family (E3), so the expected stall is still shorter.
- **The kill switch doubles the code paths for one campaign.** Ruling 20 here removes it.

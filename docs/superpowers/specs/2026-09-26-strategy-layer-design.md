# Strategy layer: top-down pillar strategies for the Stellaris governor

Date: 2026-09-26 · Status: approved design, awaiting spec review

## Why

The governor picks one standing directive every few in-game months from a free-text campaign plan.
In the Theian test campaign (2200–2253) that plan was rewritten 16 times in 37 in-game years (10 by
ordinary decisions, 6 by forced retrospective rewrites), its long-term goals (federation, habitats,
2250/2300 milestones) disappeared, nothing checked whether milestones were met, and directives
flip-flopped (`tech_rush` ↔ `expand` in 2245, 2251, 2252). `tech_rush` ran five years without
delivering its target techs, because a directive only raises research in general.

## Intent (agreed)

A strategy layer is the main orchestrator. It holds a top-down strategy per pillar, changed only at
reviews and special events, and it frames every directive choice. A strong reasoning model can be
assigned to it through its own model role. Decisions (option B) pick a directive within the frame
and may break from it only for an urgent trigger, which also schedules a review. Pillars can carry a
few concrete player actions (option B: preferred tech picks, small market orders). The human can
edit and pin pillars (option B); the model never changes pinned pillars.

Success: strategy versions stay stable for years unless something big happens; directives visibly
follow the frame; milestones are tracked automatically; target techs actually get researched.

## 1. Data model

A **strategy version** per campaign, stored in telemetry (`strategies` table: campaign_id, run_id,
t, date, trigger, model, json), newest = current. JSON:

- `pillars`: exactly these seven, each once: `economy`, `expansion`, `technology`, `diplomacy`,
  `defence`, `government`, `society`. Each pillar:
  - `priority` (1 = first; unique 1..7)
  - `stance` (1–2 sentences)
  - `goals` (1–3 strings)
  - `milestones`: list of `{metric, op, target, by}`; `metric` ∈ the metrics the harness records
    (systems, colonies, pops, techs_known, military_power, economy_power, tech_power, and
    peer ranks `rank:<measure>`); `op` ∈ `>=`, `<=`; `by` an in-game date
  - `actions` (only technology and economy):
    - technology: `prefer_techs` (tech ids that exist in the corpus, at most 6)
    - economy: `market` (at most 2 orders `{side: sell|buy, resource, amount}`; sell only for a
      resource the briefing flags idle; amount ≤ 20% of that resource's monthly income, or ≤ 25 for
      trade)
  - `pinned` (bool), `edited_by` (`model` | `human`)
- `focus`: one line, the current focus
- `ranking`: directives in order, derived by code from pillar priorities (mapping below)
- `reason`: why this version exists (per changed pillar)
- Milestone **status** is computed by the harness from the metrics table, never stored from the
  model: `met` once the metric satisfies `op target` (it stays met); `missed` when `by` has passed
  unmet; otherwise the last 12 months' change is projected linearly to `by` — `on_track` if the
  projection satisfies the target, `at_risk` if not (and `at_risk` with under 12 months of data).

Directive mapping for the ranking: economy → `consolidate_economy`, expansion → `expand`,
technology → `tech_rush`, diplomacy → `diplomacy_first`, defence → `defend` (and `prepare_war` only
if the defence stance says offensive and the human approved), government/society → no directive of
their own (they shape stances and rules only).

## 2. Flow

**Strategy review** (the Strategist; replaces today's retrospective) runs:
- at run start if the campaign has no strategy (seeded from species, ethics, civics, origin,
  neighbours' identity);
- every N decisions (default 5) — may answer "no change", which records the review but no version;
- on events, at once: war started or ended, crisis appeared, colony lost, became boxed in, a
  milestone turned `missed`, a decision broke the frame (urgent trigger) — at most one event review
  per 12 in-game months;
- on the dashboard's "Review strategy now".

Input: current strategy with pins, milestone status, briefing, 12-month trends, past directive
outcomes, learned rules, the review trigger. Output: a new version (unpinned pillars only, each
change with a reason) or "no change". Model: the `strategy` role.

**Decisions** get a strategy frame at the top of the prompt: pillar priorities, directive ranking,
milestones at risk, focus. They pick the directive consistent with the ranking; a pick against it
must cite an urgent trigger, is tagged `off_frame`, and schedules an event review.

**Actions** (executed by the harness at each decision, game paused):
- tech pick: if a `prefer_techs` tech is offered in a field whose current research has < 10% of its
  cost done, pick it (F4 → swap → click, as verified 2026-09-26); verify in the next save; one miss
  per tech per review, then skip until the next review.
- market: keep the monthly orders in the save equal to the economy pillar's `market` (add, change,
  remove through Market → monthly trade); verify in the next save; if an order disappears, log it
  and do not re-add before the next review.

Retired: `Retrospective` output and the free-text plan (old plans stay in history). Learned rules
(`remember_rule`, `learned/strategy.md`) stay.

## 3. Dashboard

- **Strategy tab** (replaces Plan): focus + ranking + last review (date, trigger, model); one card per
  pillar in priority order with stance, goals, milestones with status marks, actions, and a pinned
  tag; per card Edit (saves and pins) and Unpin; collapsible version history (date, trigger, changed
  pillars, reasons); "Review strategy now" (disabled while a review runs).
- **Settings → Models**: new `strategy` role (label Strategy, help recommends a reasoning model),
  default "same as Decisions"; the `retrospective` role is removed and its saved list moves to
  `strategy`.
- Chart: review marks on the directive lane. Decisions list: `off-frame` tag with its trigger.

## 4. Failures

- Strategist failure: normal model fallback through the role's list; if all fail, the current
  strategy stays, the error is logged, the review retries at the next decision; play never stops.
- Invalid output (unknown pillar, duplicate priority, pinned pillar changed, unknown metric or tech,
  market order over limits): rejected with the reasons and retried once; still invalid → no change.
- Human edits win: an edit during a running review is kept and that review's change to the same
  pillar is dropped.
- No strategy yet: decisions work as today until the first review succeeds.
- Tech pick / market order failures: logged, never retried in a loop (see §2).
- Decision request limit raised from 4 to 6 (Claude used more tool rounds and hit the limit on
  2246.05); the output tool is required on the final request.

## 5. Testing

- Unit: pillar/milestone/action validation; milestone status from metrics rows; ranking from
  priorities; pinned pillars kept; review triggers incl. the 12-month event cap; `off_frame` tagging;
  rejected output and retry; strategy versions saved/loaded; dashboard strategy, pin, edit, history
  and review-now APIs; the `retrospective` → `strategy` role migration.
- Governor with scripted models: review at start, on schedule, on a war event; "no change" writes
  no version; decisions receive the frame.
- Actions: tech-pick and market-order selection on real save fixtures; screen steps verified live
  once in the Theian test game.
- UI: Strategy tab and editing in a headless browser, no console errors.
- Live: ~30 in-game years in the test game; expect far fewer versions than 16/37 years, tracked
  milestones, directives following the frame, preferred techs researched.

## Out of scope

Enclave deals and other diplomacy actions; offensive war planning beyond today's `prepare_war`
gate; GC4 (the GC4 pilot keeps its episode loop).

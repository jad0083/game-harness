# Weighted pillars: weights instead of priorities, decisions driven by pressure

Date: 2026-09-26. Status: approved by the user ("go", "continue till deployment"); design decisions
below are rulings made during a hands-off run.

## Problem

The Strategist ranks pillars 1..N. A rank hides how far apart two pillars are, and the directive
ranking stays fixed until the next review: once economy's milestone is met the governor keeps
preferring `consolidate_economy` while defence falls behind. Decisions are black and white.

## Idea

Each pillar gets a **weight** (integers summing to 100). At every decision the code computes each
pillar's **pressure = weight × need**, where need comes from the status of the pillar's milestones.
Directives are scored by the pressure of the pillar that ranks them. A met pillar lets go; an at-risk
or missed one pushes in proportion to its weight. Balance comes without a new review.

## Rulings

1. **Data.** `Pillar.weight: int` is stored and written by the Strategist. `Pillar.priority` stays,
   but is derived: `Strategy` sets it to the pillar's rank by weight (1 = heaviest; ties by pillar
   name). Everything rank-based keeps working unchanged: `sorted_pillars`, the detail rules
   ("priority 1 needs 2 milestones", "top 3 need 2 goals"), the dashboard's ordering.
2. **Old strategies convert on load.** A strategy with priorities and no weights (all stored ones
   today) gets weights from its ranks: `w(r) = min + (100 - N·min) · (N + 1 - r) / ΣN`, rounded by
   largest remainder so they sum to 100. For 7 pillars and min 5: 21/19/17/14/12/10/7.
3. **The Strategist writes weights.** Its output shape has `weight` instead of `priority`; a
   `priority` key in an answer (an echo of an old shape) is dropped, and a missing weight fails
   validation with a clear message, so the corrective retry fixes it.
4. **Weight rules** (pillars.toml `[weights]`, per game): sum exactly 100; each in `min..max`
   (Stellaris 5..50, so every pillar counts and none dominates); the heaviest at least `spread` × the
   lightest (Stellaris 2, which rejects an even spread). Pinned pillars keep their weight (the
   pinned-content check already covers it). Human edits are validated by the same rules.
5. **Need** (pillars.toml `[weights.need]`): the largest multiplier among the pillar's milestones:
   met 0.3, on_track 1.0, at_risk 1.5, missed 2.0; a pillar without milestones has need 1.0. "Largest"
   means a pillar lets go only when all its milestones are met.
6. **Pressure** = weight × need, one decimal. Computed from the same metrics rows as the
   milestone badges.
7. **Exclusive mode** (`mode = "exclusive"`, Stellaris: one standing directive). The decision frame
   replaces "Directive ranking" with the pressure table, e.g.
   `consolidate_economy 45.0 (economy 30 × at_risk 1.5) > defend 30.0 (defence 30 × on_track 1.0) > …`,
   and a suggestion: the top directive, unless the current directive's pressure is at least the top's
   divided by `switch_margin` (Stellaris 1.25), in which case "keep" (switching costs the AI time to
   re-plan). The model may choose otherwise and says why. `off_frame` means: not keep/current and not
   in the top 2 by pressure. No minimum hold: decisions are 12 months apart, and urgent triggers must
   stay free to act.
8. **Share mode** (`mode = "share"`, for GalCiv IV and Civ VI, where many levers act at once). The
   frame shows each pillar's share of effort (pressure normalised to 100%) instead of a directive
   suggestion. Defined and tested now; no game uses it yet.
9. **Decisions name what they serve.** `GovernorDecision.serves` (optional text): the pillar and
   milestone the choice works toward. The prompt asks for it; it is recorded on the episode and trace
   and shown in the Reasoning tab. Not enforced in this version.
10. **Human weight edits.** `weight` becomes editable. The other unpinned pillars are rescaled in
    proportion so the sum stays 100 (pinned ones keep theirs); if that breaks a bound the edit is
    rejected with the reason.
11. **Dashboard.** Each pillar shows `weight 30 · pressure 45` and a thin bar of its share of the
    total pressure; the edit form has a weight field. `/api/strategy` adds `pressure` per pillar.
12. **Out of scope** (plan.md): a directive-efficacy table fed back to the Strategist, event boosts to
    need (war → defence), share-mode consumers in GalCiv IV / Civ VI.

## Errors

- A broken `[weights]` table is a pillars-file error: the strategy layer turns off with the reason
  (existing behaviour for a broken pillars file).
- Pressure uses `milestone_status`; if the metrics rows are missing, need is 1.0 for every pillar
  (pressure = weight) and the frame says so.

## Testing

Unit tests for conversion (ranks → weights), weight validation, need and pressure, the exclusive
suggestion (switch margin both ways), share percentages, the output schema (weight required,
priority dropped), human weight edit rescaling, the frame text, `serves` recording, and the
dashboard's strategy API. Live: restart on the running Blooms of Gaea campaign, request a review,
check the weights and the pressure table in the next decision's trace.

# CivBench: lessons for LLM agents playing Civilization VI
Source: https://arxiv.org/abs/2609.02459
License: CC BY 4.0 (arXiv licence of the paper: Andrews, Wilkinson, Coppock, Foerster, Heagerty, Costa, "CivBench: A Long-Horizon Benchmark for Tool-Mediated Agents in Civilization VI", 2026)

_Retrieved 2026-09-26 from the arXiv HTML version (v1). Excerpts: the abstract's findings and Appendices A.5 "Playbook Design Principles" and A.6 "Agent Playbook Excerpt", quoted with light formatting changes (lists, headings). Tool names such as `get_victory_progress` belong to the benchmark's MCP server, not to this harness._

## Findings (from the abstract)

CivBench evaluates language model agents over 300+ turn games driven through the Model Context Protocol, with 76 tools and a narration layer that turns the game state into text. Across 23 runs the authors report two consistent patterns under a shared playbook: agents under-monitor latent strategic state, rarely querying victory progress despite playbook guidance to check it every 20 turns (measured as the Proactive Monitoring Rate), and commitments stated in planning reflections are often not executed within the next ten turns (measured as RAG@10, the reflection-action gap).

What this means for a player-model here: check every rival's victory progress on a schedule rather than only when something looks wrong, and turn each stated plan into concrete orders in the same or the next turn.

## A.5 Playbook design principles

1. Flag urgency. Threats are bold-marked (**[Barbarian WARRIOR]**), unimproved resources receive !! warnings, and critical states such as loyalty crises or starvation are explicitly highlighted. The narration is intentionally selective about what is emphasised.
2. Provide context for action. Unit readouts include valid attack targets and buildable improvements. City readouts include available production and defensive status. The agent is presented with actionable options rather than raw state alone.
3. Compress intelligently. Fog-of-war tiles are marked [fog] rather than omitted, so the agent can distinguish between absence of information and absence of content. Resources are classified by type (bonus/luxury + /strategic *) to support prioritisation, and rankings are sorted by score.

Strategic guidance with benchmarks. The playbook uses advisory rather than imperative language. Earlier versions included hard IF/WHEN triggers (e.g. "IF gold > 500: spend before ending turn"), but these were softened to allow more organic behaviour. The agent frequently violates even this guidance, making the reflection-action gap observable against instructions it demonstrably interprets but does not consistently follow.

The playbook therefore serves both as a stabilisation mechanism and as an experimental control. It standardises interaction structure and highlights relevant signals while leaving attention allocation and execution decisions to the agent.

This loop—orient, detect, reason, act, reflect—repeats 5–15 times per turn across 300+ turns, producing a structured trajectory of situated, tool-mediated decision-making.

## A.6 Agent playbook excerpt

### Sensorium awareness

You only know what you explicitly query. A human player passively absorbs the minimap, score ticker, religion lens, unit health bars—you have none of that. Information you don't ask for simply doesn't enter your world model. The checkpoints and patterns below exist to compensate for this.

Gold. Gold sitting above 500 with no specific plan is usually better deployed. A builder, a luxury tile, a building that skips 5+ turns of production—these compound. Saving for a specific purchase is fine, but it helps to name the item and the turn.

Expansion. Each city multiplies your districts, yields, and Great Person generation. The gap between a 3-city and 5-city empire at T100 is hard to recover from. Benchmarks: T40: 2 cities, T60: 3 cities, T80: 4 cities, T100: 4–5 cities. If city count is lagging, a settler is typically the highest-impact production choice.

Exploration. You can't settle what you can't see, and you can't counter threats you don't know exist. A scout set to automate is one of the best investments in the early game. Benchmarks: T25 ≥ 15%, T50 ≥ 25%, T75 ≥ 35%, T100 ≥ 50%.

### Strategic checkpoints (every 20 turns)

- get_diplomacy — delegations to new civs, friendships with Friendly civs, alliances if eligible.
- get_victory_progress — check all 6 victory types, not just your own path.
- get_religion_spread — religious victory is invisible without active checking; a rival with majority in most civs is a serious threat.

### Turn diary fields

Five fields each turn:

- tactical: What happened—specific units, tiles, outcomes.
- strategic: Standings vs rivals—yields, city count, victory path viability with numbers.
- tooling: Tool issues observed, or "No issues".
- planning: Concrete actions for the next 5–10 turns—specific builds, moves, research targets with turn estimates.
- hypothesis: Specific predictions—attack timing, milestone turns, biggest risks.

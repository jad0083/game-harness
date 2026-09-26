# GEMINI.md

The operating guide for this repository is **[AGENTS.md](AGENTS.md)** — it applies to every model,
including Gemini. Read it fully before acting; `.gemini/settings.json` also loads it as context.

Gemini-specific notes:
- **MCP**: `.gemini/settings.json` registers the `game` MCP server (`./target/release/game-controller mcp`).
  Build it first (`cargo build --release -p game-controller`). It runs from the repo root and
  reads the agent token from `.agent_token` (or `GAME_AGENT_TOKEN` if exported). Check with `/mcp`.
- **Shell fallback**: everything is also available through `scripts/play/*.sh` and
  `./target/release/game-controller` (see AGENTS.md §3). Screenshots are written to `play/`;
  read the image files to see them.
- **Long tool calls**: `autopilot` can run for minutes (the game processes AI turns); the MCP
  timeout in `.gemini/settings.json` is 10 minutes. Prefer 10–20 turns per call.
- Record what you learn and commit through `scripts/ci-commit.sh` exactly as AGENTS.md §8 says,
  with no AI attribution in commits or files.

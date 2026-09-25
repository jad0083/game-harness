# game-harness

Lets an AI agent play a turn-based Windows game (Galactic Civilizations IV) running on
another PC on the LAN, by looking at screenshots and sending mouse/keyboard input.

```
 Linux controller (192.168.1.76)                 Windows 11 gaming PC (192.168.1.77)
 ┌──────────────────────────────┐   HTTP+token   ┌──────────────────────────────────┐
 │ Claude Code                  │   TCP 8765     │ windows_agent/agent.py           │
 │   └─ MCP server "game"       │ ─────────────► │  (stdlib Python, runs in your    │
 │      src/harness/*           │ ◄───────────── │   desktop session at logon)      │
 │      screenshot/click/key... │   PNG / JSON   │  GDI capture + SendInput         │
 └──────────────────────────────┘                └──────────────────────────────────┘
```

## Pieces

| Path | Runs on | Purpose |
|---|---|---|
| `windows_agent/agent.py` | Windows | HTTP API: `/health`, `/screenshot`, `/click`, `/move`, `/drag`, `/scroll`, `/key`, `/type`, `/windows`, `/focus`. Standard library only. |
| `windows_agent/install.ps1` | Windows | Installs Python if needed, copies the agent, opens the firewall to the local subnet, registers a logon task. |
| `scripts/serve-agent.sh` | Linux | Serves the agent + installer + token so Windows installs with one line. |
| `src/harness/mcp_server.py` | Linux | MCP tools used by Claude: `screenshot`, `zoom`, `click`, `hover`, `drag`, `scroll`, `key`, `type_text`, `focus_game`, `wait`, `status`, `list_windows`. |
| `src/harness/cli.py` | Linux | `game-harness health|screenshot|click|move|key|type|focus|windows` for manual testing. |
| `PLAYING.md` | — | Playbook the agent follows while playing GC4. |

Every action tool returns a fresh screenshot. Coordinates passed to tools are pixels in the
**most recent image** (screenshots are downscaled to 1568px wide; `zoom` crops are upscaled),
and the server maps them back to real screen pixels.

## Setup

1. **Controller (Linux)**
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
   scripts/serve-agent.sh          # creates .agent_token and prints a PowerShell one-liner
   ```
2. **Windows PC**: open PowerShell (normal, not admin) and paste the printed line, e.g.
   ```powershell
   $env:GA_SRC='http://192.168.1.76:8000'; irm "$env:GA_SRC/install.ps1" | iex
   ```
   Accept the single UAC prompt (firewall rule). Then stop `serve-agent.sh` with Ctrl-C.
3. **Verify** from Linux:
   ```bash
   .venv/bin/game-harness health
   .venv/bin/game-harness screenshot shot.png
   ```
4. Restart Claude Code in this directory so it picks up `.mcp.json` (server name `game`).

### Game settings
- Display mode **Borderless** or **Windowed**. Exclusive fullscreen may capture as black.
- Stay logged in with the screen unlocked; a locked desktop captures black and rejects input.
  The agent keeps the PC from sleeping while it runs, but does not stop a lock-screen timeout.

### Updating the agent
Re-run `scripts/serve-agent.sh` and the same one-liner; it overwrites the files and restarts the task.

### Uninstall (Windows)
```powershell
Unregister-ScheduledTask GameAgent; Remove-NetFirewallRule -DisplayName 'Game Agent (TCP 8765)'; Remove-Item -Recurse "$env:LOCALAPPDATA\GameAgent"
```

## Security
The agent can inject arbitrary input into your desktop. It requires a bearer token
(`.agent_token` here, `agent_token.txt` on Windows), the firewall rule only admits the local
subnet, and it runs unelevated. The token travels in plain HTTP on the LAN; don't expose port
8765 beyond your network.

## Development
```bash
.venv/bin/pytest -q      # agent logic runs against a fake backend, so tests pass on Linux
.venv/bin/ruff check .
```

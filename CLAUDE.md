# Stuart's Accountability Bot

Discord bot that helps Stuart (solo founder of Method Line Group) stay accountable to daily tasks and goals. Uses Claude as the reasoning engine and Letta as persistent identity storage.

## Architecture

```
Discord ← cogs/ → agent_interface.py → claude_client.py → Anthropic API
                                             ↕                  ↕
                                        state.py          tool_use loop
                                      (bot/state/)        (memory, state,
                                                           self-modify)
```

### Key modules
- `bot/main.py` — Discord bot entry point, loads cogs and scheduler
- `bot/claude_client.py` — Anthropic API client with tool_use loop. Builds system prompt, dispatches tools, manages conversation history
- `bot/agent_interface.py` — Unified interface for all agent interactions. Calls claude_client, logs to journal, syncs Letta→disk
- `bot/letta_agent.py` — Letta client setup + static identity constants (PERSONA, HUMAN, LIMITATIONS)
- `bot/memory_tools.py` — CRUD for Letta memory blocks (identity storage)
- `bot/state.py` — Read/write `.md` files in `bot/state/` (working memory)
- `bot/self_modify.py` — PR-based self-modification workflow (dev branch + GitHub PR)
- `bot/logs.py` — Journal (JSONL) and event logging
- `bot/db.py` — SQLite for task tracking
- `bot/scheduler.py` — APScheduler for perch reviews and EOD summaries

### Memory model (hybrid)
- **Identity (Letta)**: persona, human — core identity blocks, rarely changed. Accessed via `read_memory`/`update_memory` tools
- **Working memory (state files)**: commitments, projects, patterns, current_focus — frequently updated. Accessed via `read_state`/`write_state`/`list_state` tools. Stored in `bot/state/*.md`
- **Journal**: temporal log in `bot/logs/journal.jsonl`. Recent entries injected into system prompt for time awareness
- State files are gitignored (runtime data). Letta blocks sync to state files after each interaction via `state.sync_from_letta()`

### Tool dispatch
All tools defined in `claude_client.TOOLS` and dispatched in `_execute_tool()`:
- `read_state`, `write_state`, `list_state` — state file tools
- `read_memory`, `update_memory`, `list_memories`, `create_memory` — Letta memory tools
- `read_file`, `edit_code` — self-modification (creates PR for human review)
- `web_search` — Anthropic built-in web search

## Running

Runs in Docker. See `bot/Dockerfile`. Requires `.env` with:
- `DISCORD_TOKEN`
- `ANTHROPIC_API_KEY`
- `LETTA_BASE_URL` (defaults to `http://localhost:8283`)
- `LETTA_AGENT_ID` (set after first run to reuse agent)
- `GITHUB_TOKEN` (for self-modify PRs)

## Conventions
- Python 3.11+, no type stubs needed
- Timezone: `Europe/London` (hardcoded in system prompt)
- Imports are local modules (no package prefix) — bot runs from `bot/` as working dir
- Keep system prompt lean — no bulk memory injection, agent reads state on demand
- All code changes by the agent go through PR review (never auto-merge)
- GH_TOKEN env var is available for git push operations — use it in remote URL

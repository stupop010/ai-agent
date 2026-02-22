# Stuart's Accountability Bot

Discord bot that helps Stuart (solo founder of Method Line Group) stay accountable to daily tasks and goals. Uses Claude as the reasoning engine, Letta for highly observed modifiable memory, and a three-tier file memory system.

## Architecture

```
Discord ← cogs/ → agent.py → Claude Agent SDK → Anthropic API
                      ↕              ↕
                  memory.py     tools/ (MCP)
                (three-tier)    (state, tasks,
                                 journal, schedule)
```

### Key modules
- `bot/main.py` — Discord bot entry point, loads cogs and scheduler
- `bot/agent.py` — Singleton Claude SDK client with conversation history, system prompt from three-tier memory, journal logging, Letta sync, and all convenience functions
- `bot/memory.py` — Three-tier memory system (core/index/files) + Letta sync
- `bot/letta_agent.py` — Letta client setup + identity constants
- `bot/memory_tools.py` — CRUD for Letta memory blocks
- `bot/tools/` — MCP tool modules:
  - `state_tools.py` — read_state, write_state, list_state
  - `task_tools.py` — add_task, complete_task, list_tasks
  - `journal_tools.py` — search_journal, read_journal
  - `schedule_tools.py` — schedule_job, cancel_job, list_jobs
  - `__init__.py` — Tool registry + MCP server creation
- `bot/logs.py` — Journal (JSONL) and event logging
- `bot/db.py` — SQLite for task tracking
- `bot/scheduler.py` — APScheduler for perch reviews and EOD summaries
- `bot/agent_jobs.py` — Agent-created scheduled job lifecycle
- `bot/bot_context.py` — Global bot instance singleton

### Memory model
- **Letta memory blocks**: Highly observed, modifiable memory — the agent actively monitors and refines these (persona, human, patterns). Accessed via `read_memory`/`update_memory` tools. Synced to `state/core/` after each interaction.
- **Tier 1 — Core** (`state/core/*.md`): Always loaded into system prompt. Mirrors Letta blocks.
- **Tier 2 — Index** (`state/index/*.md`): Pointers loaded into prompt, content on-demand. Lists available state files with summaries.
- **Tier 3 — Files** (`state/files/*.md`): On-demand via `read_state`/`write_state` tools. commitments, projects, patterns, current_focus, etc.
- **Journal**: temporal log in `bot/logs/journal.jsonl`. Recent entries injected into system prompt for time awareness.

### Cogs
- `cogs/conversation.py` — Message flow: check-ins, chat, scheduled messages
- `cogs/commands.py` — Slash commands: /add, /done, /tasks, /focus, /state, /journal, /events, /search_journal, /clear

### Tool dispatch
Tools exposed via MCP server in `bot/tools/`:
- `read_memory`, `update_memory`, `list_memories`, `create_memory` — Letta memory blocks
- `read_state`, `write_state`, `list_state` — state file tools
- `add_task`, `complete_task`, `list_tasks` — task CRUD
- `search_journal`, `read_journal` — journal search
- `schedule_job`, `cancel_job`, `list_jobs` — scheduling
- Plus SDK built-in: WebSearch, Read, Write, Edit, Grep, Glob, Bash, Skill

## Running

Runs in Docker. See `bot/Dockerfile`. Requires `.env` with:
- `DISCORD_TOKEN`
- `ANTHROPIC_API_KEY`
- `LETTA_BASE_URL` (defaults to `http://localhost:8283`)
- `LETTA_AGENT_ID` (set after first run to reuse agent)
- `CHANNEL_ID`
- `GITHUB_TOKEN` (for self-modify PRs)

## Conventions
- Python 3.11+, no type stubs needed
- Timezone: `Europe/London` (hardcoded in system prompt)
- Imports are local modules (no package prefix) — bot runs from `bot/` as working dir
- Keep system prompt lean — core memory + index pointers + journal only
- All code changes by the agent go through PR review (never auto-merge)

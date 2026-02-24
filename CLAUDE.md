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
- `run_claude_code` — Claude Code CLI for code changes, git ops, Obsidian vault
- Plus SDK built-in: WebSearch, Read, Write, Edit, Grep, Glob, Bash, Skill

## Running

Runs in Docker on `root@46.225.190.185` at `/opt/ai-agent`. Requires `.env` (`/opt/ai-agent/bot/.env`) with:
- `DISCORD_TOKEN`
- `ANTHROPIC_API_KEY`
- `CHANNEL_ID`
- `GITHUB_TOKEN` (for self-modify PRs and Obsidian vault access)
- `OBSIDIAN_REPO` (GitHub repo path, e.g. `stupop010/obsidian-vault`)

### Rebuild & deploy

```bash
ssh root@46.225.190.185
cd /opt/ai-agent
git pull origin main
docker stop letta-bot-1 && docker rm letta-bot-1
docker build -t letta-bot -f bot/Dockerfile bot/
docker run -d --name letta-bot-1 --restart unless-stopped \
  --env-file /opt/ai-agent/bot/.env \
  -v /opt/ai-agent:/repo \
  -v /opt/ai-agent/claude-config/claude-home:/home/botuser/.claude \
  -v /opt/ai-agent/claude-config/managed/managed-settings.json:/etc/claude-code/managed-settings.json:ro \
  letta-bot
```

### Claude Code CLI (in-container)

The bot has a `run_claude_code` tool that shells out to `claude -p`. It uses Stuart's OAuth subscription (not the API key) to avoid API charges.

- **OAuth token expires ~weekly.** Stuart must SSH in and re-auth:
  ```bash
  ssh -t root@46.225.190.185
  docker exec -it letta-bot-1 bash
  claude auth login
  ```
- Credentials persist at `/opt/ai-agent/claude-config/claude-home/.credentials.json` (volume-mounted into the container at `/home/botuser/.claude/`)
- `/opt/ai-agent/claude-config/managed/managed-settings.json` must exist (empty `{}` is fine) — mounted read-only to `/etc/claude-code/managed-settings.json`
- The `.claude` home dir needs subdirs owned by UID 1000 (botuser): `backups cache debug plugins projects session-env shell-snapshots todos`
- `ANTHROPIC_API_KEY` is stripped from the Claude Code subprocess env in `claude_code_tools.py` so it uses OAuth instead

## Conventions
- Python 3.11+, no type stubs needed
- Timezone: `Europe/London` (hardcoded in system prompt)
- Imports are local modules (no package prefix) — bot runs from `bot/` as working dir
- Keep system prompt lean — core memory + index pointers + journal only
- All code changes by the agent go through PR review (never auto-merge)

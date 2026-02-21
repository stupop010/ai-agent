---
name: self-modify
description: Use this skill when asked to modify your own code, create a PR, or make changes to the bot's source code. Handles the full workflow of branching, editing, committing, and creating a GitHub PR for human review.
---

# Self-Modification Workflow

When you need to modify your own source code, follow this workflow exactly.

## Step 1: Create a fresh dev branch

```bash
git branch -D dev 2>/dev/null; git checkout -b dev main
```

This deletes any stale local dev branch and creates a fresh one from main.

## Step 2: Make your changes

Use Read, Write, Edit, Grep, and Glob tools to understand and modify the codebase.

**NEVER modify these paths:**
- `.env`
- `*.db`
- `credentials*`, `secrets*`
- `__pycache__/`
- `.git/`
- `bot/state/`
- `bot/logs/`

## Step 3: Commit

```bash
git add -A && git commit -m "[self-modify] <short description of changes>"
```

## Step 4: Push

Set the remote URL with the GitHub token and push:

```bash
git remote set-url origin https://x-access-token:${GH_TOKEN}@github.com/$(git remote get-url origin | sed 's|.*github.com[:/]||;s|\.git$||').git
git push -u origin dev --force
```

## Step 5: Create PR

```bash
gh pr create --base main --head dev --title "[Bot] <short description>" --body "<details of what changed and why>"
```

If a PR already exists for `dev`, update it instead:

```bash
gh pr edit --title "[Bot] <short description>" --body "<details>"
```

## Step 6: Switch back to main

```bash
git checkout main
```

## Step 7: Report

Tell Stuart the PR URL so he can review it.

## Project Structure Reference

```
bot/
  main.py           — Discord bot entry point, loads cogs and scheduler
  claude_client.py   — Anthropic API client with tool_use loop
  agent_interface.py — Unified interface for all agent interactions
  mcp_tools.py       — MCP tool definitions (memory, state, scheduling)
  letta_agent.py     — Letta client setup + identity constants
  memory_tools.py    — CRUD for Letta memory blocks
  state.py           — Read/write .md files in bot/state/
  logs.py            — Journal (JSONL) and event logging
  db.py              — SQLite for task tracking
  scheduler.py       — APScheduler for scheduled reviews
  bot_context.py     — Global bot instance access
  agent_jobs.py      — Scheduled job management
  cogs/
    accountability.py — Discord command handlers
bot/state/           — Runtime state files (gitignored)
bot/logs/            — Journal logs (gitignored)
```

- Python 3.11+, no type stubs needed
- Imports are local modules (no package prefix) — bot runs from `bot/` as working dir
- Keep changes minimal and focused

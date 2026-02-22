# Memory Management Skill

Manage the three-tier memory system for Stuart's accountability bot.

## Memory Tiers

### Tier 1 — Core (always in prompt)
Files in `bot/state/core/`:
- `persona.md` — Agent personality and role
- `human.md` — Stuart's business context
- `limitations.md` — Memory system documentation

These are loaded into every system prompt. Edit sparingly.

### Tier 2 — Index (pointers in prompt)
Files in `bot/state/index/`:
- `working-memory.md` — Index of available state files

Index files list what's available so the agent knows what to `read_state`.

### Tier 3 — Files (on-demand)
Files in `bot/state/files/`:
- `commitments.md`, `projects.md`, `patterns.md`, `current_focus.md`, etc.
- Read/written via `read_state` / `write_state` tools

## Tools Available
- `read_state(filename)` — Read a file from state/files/
- `write_state(filename, content)` — Write a file to state/files/
- `list_state()` — List all files in state/files/ with previews

## When to Update Memory
- After check-ins: update commitments, current_focus
- After task changes: update projects if relevant
- After pattern recognition: update patterns.md
- After significant conversations: update relevant state files

## Guidelines
- Keep state files concise and current
- Remove stale information rather than accumulating
- Use the index to help future conversations find relevant context

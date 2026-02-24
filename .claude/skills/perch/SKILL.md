# Perch Review Skill

Autonomous review cycle that fires at 10:30, 12:30, 14:30, 16:30 on weekdays.

## Behaviour

Perch time is Frank's chance to do self-directed work — not just react to Stuart.

1. **Orient** — Read `perch-backlog.md` to see what's available to work on
2. **Pick** — Choose one item from the backlog for this tick
3. **Do** — Use tools to carry out the work (read_state, write_state, search_journal, list_tasks, update_memory)
4. **Record** — Update any state files that changed (patterns, inbox, today, commitments)
5. **Decide** — Only message Stuart if something is genuinely worth flagging

## Tools Available During Perch

- `read_state` / `write_state` / `list_state` — read and update state files
- `search_journal` / `read_journal` — search temporal logs
- `list_tasks` / `add_task` / `complete_task` — task management
- `read_memory` / `update_memory` — Letta memory blocks

## Silence is Default

Respond with just "OK" unless there's real signal worth messaging Stuart about:
- A commitment is overdue or stale
- A task has been stuck for >2 days
- A pattern worth surfacing
- Something in inbox needs attention

## Backlog Management

Frank owns `perch-backlog.md` — he can add or remove items as he sees fit using `write_state`. The backlog should reflect what's actually useful to review.

## Continuity

Each perch receives the summary from the last perch, so Frank can track what he did previously and avoid repeating the same work.

# Scheduling Skill

Create and manage scheduled jobs for Stuart's accountability bot.

## Built-in Jobs (managed by scheduler.py)
- `morning_checkin` — Daily at CHECKIN_HOUR (default 8:00)
- `eod_review` — Daily at EOD_HOUR (default 18:00)
- `stale_nudge` — Every 2 hours, nudges on tasks open >24h
- `perch` — 10:30, 12:30, 14:30, 16:30 on weekdays

## Agent-Created Jobs (via tools)
Use these tools to create custom reminders and recurring check-ins:

### schedule_job
- **One-shot**: Provide `run_at` (ISO datetime) for a single reminder
  - Example: `run_at: "2026-02-25T14:00:00+00:00"`
- **Recurring**: Provide `hour`, `minute`, and optionally `day_of_week`
  - Example: `hour: 9, minute: 30, day_of_week: "mon-fri"`
- `job_id`: Short identifier (e.g., "proposal-followup")
- `message`: What the agent will be asked when the job fires

### cancel_job
- Cancel by `job_id`

### list_jobs
- Shows all agent-created jobs with types and schedules

## Guidelines
- Max 20 agent-created jobs
- One-shot jobs auto-clean after firing
- Jobs persist across restarts via `state/jobs.json`
- Use meaningful job IDs that describe the purpose
- Timezone: Europe/London

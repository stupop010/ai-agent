"""Scheduling tools — create, cancel, list agent-created jobs."""
import json
from typing import Any

from claude_agent_sdk import tool

import agent_jobs
import bot_context


@tool(
    "schedule_job",
    "Schedule a one-shot or recurring job. For one-shot reminders, "
    "provide run_at (ISO datetime). For recurring jobs, provide hour "
    "and minute (and optionally day_of_week like 'mon', 'mon-fri', 'mon,wed,fri'). "
    "The message is what you'll be asked to respond to when the job fires.",
    {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Short identifier for the job (e.g. 'proposal-followup')"},
            "message": {"type": "string", "description": "The message/prompt you'll receive when the job fires"},
            "run_at": {"type": "string", "description": "ISO datetime for one-shot jobs (e.g. '2026-02-20T15:00:00+00:00')"},
            "hour": {"type": "integer", "description": "Hour (0-23) for recurring jobs"},
            "minute": {"type": "integer", "description": "Minute (0-59) for recurring jobs"},
            "day_of_week": {"type": "string", "description": "Day(s) of week for recurring jobs (e.g. 'mon', 'mon-fri')"},
        },
        "required": ["job_id", "message"],
    },
)
async def schedule_job(args: dict[str, Any]) -> dict[str, Any]:
    bot = bot_context.get_bot()
    if not bot or not bot.scheduler:
        text = json.dumps({"error": "Scheduler not available"})
    else:
        cron_args = {}
        if "hour" in args:
            cron_args["hour"] = args["hour"]
        if "minute" in args:
            cron_args["minute"] = args["minute"]
        if "day_of_week" in args:
            cron_args["day_of_week"] = args["day_of_week"]
        result = agent_jobs.add_job(
            bot.scheduler,
            args["job_id"],
            args["message"],
            cron_args=cron_args if cron_args else None,
            run_at=args.get("run_at"),
        )
        text = json.dumps(result)
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "cancel_job",
    "Cancel an agent-created scheduled job by its ID.",
    {"job_id": str},
)
async def cancel_job(args: dict[str, Any]) -> dict[str, Any]:
    bot = bot_context.get_bot()
    if not bot or not bot.scheduler:
        text = json.dumps({"error": "Scheduler not available"})
    else:
        result = agent_jobs.cancel_job(bot.scheduler, args["job_id"])
        text = json.dumps(result)
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "list_jobs",
    "List all agent-created scheduled jobs. Shows job IDs, messages, "
    "types (once/recurring), and schedules.",
    {},
)
async def list_jobs(args: dict[str, Any]) -> dict[str, Any]:
    result = agent_jobs.list_jobs()
    text = json.dumps(result)
    return {"content": [{"type": "text", "text": text}]}


ALL_TOOLS = [schedule_job, cancel_job, list_jobs]

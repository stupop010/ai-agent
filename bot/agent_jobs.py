"""
Agent-created scheduled jobs.

Handles job lifecycle: add, cancel, list, persist to JSON, reload on startup.
Jobs fire by calling agent_interface.ask() and sending the reply to Discord.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

import agent_interface
import bot_context
import logs

logger = logging.getLogger(__name__)

JOBS_FILE = Path(__file__).parent / "state" / "jobs.json"
MAX_JOBS = 20
UK_TZ = ZoneInfo("Europe/London")


def _load_jobs() -> list[dict]:
    if not JOBS_FILE.exists():
        return []
    try:
        return json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read jobs.json, returning empty list")
        return []


def _save_jobs(jobs: list[dict]) -> None:
    JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOBS_FILE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def add_job(scheduler, job_id: str, message: str,
            cron_args: dict | None = None, run_at: str | None = None) -> dict:
    """Add a one-shot or recurring job. Returns status dict."""
    prefixed_id = f"agent-{job_id}"

    jobs = _load_jobs()
    if len(jobs) >= MAX_JOBS:
        return {"error": f"Maximum of {MAX_JOBS} agent jobs reached. Cancel some first."}

    # Check for duplicate ID
    if any(j["id"] == prefixed_id for j in jobs):
        return {"error": f"Job '{job_id}' already exists. Use a different ID or cancel it first."}

    now = datetime.now(UK_TZ).isoformat()
    job_record = {
        "id": prefixed_id,
        "message": message,
        "created_at": now,
    }

    if run_at:
        # One-shot job
        trigger = DateTrigger(run_date=run_at, timezone=UK_TZ)
        job_record["type"] = "once"
        job_record["run_at"] = run_at
    elif cron_args:
        # Recurring job
        trigger = CronTrigger(timezone=UK_TZ, **cron_args)
        job_record["type"] = "recurring"
        job_record["cron"] = cron_args
    else:
        return {"error": "Must provide either run_at (one-shot) or cron args (recurring)."}

    scheduler.add_job(
        _run_job,
        trigger,
        id=prefixed_id,
        args=[prefixed_id, message],
        replace_existing=True,
    )

    jobs.append(job_record)
    _save_jobs(jobs)

    logger.info("Added agent job: %s (%s)", prefixed_id, job_record["type"])
    return {"success": True, "job_id": job_id, "type": job_record["type"]}


def cancel_job(scheduler, job_id: str) -> dict:
    """Cancel and remove an agent job."""
    prefixed_id = f"agent-{job_id}"

    jobs = _load_jobs()
    original_count = len(jobs)
    jobs = [j for j in jobs if j["id"] != prefixed_id]

    if len(jobs) == original_count:
        return {"error": f"No agent job found with ID '{job_id}'."}

    try:
        scheduler.remove_job(prefixed_id)
    except Exception:
        pass  # Job may have already fired/expired

    _save_jobs(jobs)
    logger.info("Cancelled agent job: %s", prefixed_id)
    return {"success": True, "job_id": job_id}


def list_jobs() -> dict:
    """List all agent-created jobs."""
    jobs = _load_jobs()
    return {"jobs": jobs, "count": len(jobs), "max": MAX_JOBS}


def reload_jobs(scheduler) -> None:
    """Reload persisted jobs into the scheduler on startup."""
    jobs = _load_jobs()
    now = datetime.now(UK_TZ)
    kept = []

    for job in jobs:
        prefixed_id = job["id"]
        message = job["message"]

        try:
            if job["type"] == "once":
                run_at = datetime.fromisoformat(job["run_at"])
                if run_at.tzinfo is None:
                    run_at = run_at.replace(tzinfo=UK_TZ)
                if run_at <= now:
                    logger.info("Skipping expired one-shot job: %s", prefixed_id)
                    continue
                trigger = DateTrigger(run_date=job["run_at"], timezone=UK_TZ)
            elif job["type"] == "recurring":
                trigger = CronTrigger(timezone=UK_TZ, **job["cron"])
            else:
                logger.warning("Unknown job type '%s' for job %s", job["type"], prefixed_id)
                continue

            scheduler.add_job(
                _run_job,
                trigger,
                id=prefixed_id,
                args=[prefixed_id, message],
                replace_existing=True,
            )
            kept.append(job)
            logger.info("Reloaded agent job: %s", prefixed_id)
        except Exception as e:
            logger.warning("Failed to reload job %s: %s", prefixed_id, e)

    # Save back only the jobs we kept (removes expired one-shots)
    if len(kept) != len(jobs):
        _save_jobs(kept)


async def _run_job(job_id: str, message: str) -> None:
    """Callback when a job fires: ask the agent and send reply to Discord."""
    logger.info("Agent job firing: %s", job_id)
    logs.write_event("decision", f"Agent job firing: {job_id}", {"message": message[:200]})

    try:
        reply = agent_interface.ask(
            f"[Scheduled reminder] {message}",
            topics=["scheduled", "agent-job"],
        )

        bot = bot_context.get_bot()
        if bot and reply.strip():
            channel_id = int(os.environ["CHANNEL_ID"])
            channel = bot.get_channel(channel_id)
            if channel is None:
                channel = await bot.fetch_channel(channel_id)
            await channel.send(reply)
    except Exception as e:
        logger.exception("Agent job %s failed: %s", job_id, e)
        logs.write_event("error", f"Agent job failed: {e}", {"job_id": job_id})

    # Auto-clean one-shot jobs after firing
    jobs = _load_jobs()
    original_count = len(jobs)
    jobs = [j for j in jobs if not (j["id"] == job_id and j["type"] == "once")]
    if len(jobs) != original_count:
        _save_jobs(jobs)
        logger.info("Cleaned up one-shot job: %s", job_id)

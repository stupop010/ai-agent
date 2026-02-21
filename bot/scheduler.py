import os
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

import db
import agent_interface
import logs

logger = logging.getLogger(__name__)
UK_TZ = pytz.timezone("Europe/London")


def build_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=UK_TZ)

    checkin_hour = int(os.environ.get("CHECKIN_HOUR", 8))
    eod_hour = int(os.environ.get("EOD_HOUR", 18))
    channel_id = int(os.environ["CHANNEL_ID"])

    async def _get_channel():
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)
        return channel

    async def morning_checkin():
        logger.info("Running morning check-in job")
        logs.write_event("decision", "Starting morning check-in job", {"job": "morning_checkin"})
        try:
            channel = await _get_channel()
            checkin_cog = bot.cogs.get("Checkin")
            if checkin_cog:
                await checkin_cog.send_morning_checkin(channel)
        except Exception as e:
            logger.exception("Morning check-in job failed")
            logs.write_event("error", f"Morning check-in failed: {e}", {"job": "morning_checkin"})

    async def eod_review():
        logger.info("Running EOD review job")
        logs.write_event("decision", "Starting EOD review job", {"job": "eod_review"})
        try:
            channel = await _get_channel()
            checkin_cog = bot.cogs.get("Checkin")
            if checkin_cog:
                await checkin_cog.send_eod_review(channel)
        except Exception as e:
            logger.exception("EOD review job failed")
            logs.write_event("error", f"EOD review failed: {e}", {"job": "eod_review"})

    async def stale_nudge():
        logger.info("Running stale task nudge job")
        try:
            stale = db.get_stale_tasks(hours=24)
            if not stale:
                return
            channel = await _get_channel()
            for task in stale:
                reply = await agent_interface.ask(
                    f'Task #{task["id"]} has been open for over 24 hours: "{task["description"]}". '
                    "Send a short, direct nudge to Stuart — not more than one sentence. "
                    "Don't be preachy.",
                    topics=["nudge", "stale", "scheduled"],
                )
                await channel.send(f"**Nudge — task #{task['id']}:** {reply}")
                db.update_nudge_time(task["id"])
                logs.write_event(
                    "observation",
                    f"Sent stale nudge for task #{task['id']}",
                    {"task_id": task["id"], "description": task["description"][:100]},
                )
        except Exception as e:
            logger.exception("Stale nudge job failed")
            logs.write_event("error", f"Stale nudge failed: {e}", {"job": "stale_nudge"})

    async def perch():
        """Autonomous review cycle — fires mid-morning and afternoon on weekdays.
        Reads current state + tasks and speaks up only if something is worth flagging."""
        logger.info("Running perch review")
        logs.write_event("decision", "Starting perch review", {"job": "perch"})
        try:
            open_tasks = db.list_open_tasks()
            completed_today = db.list_todays_completed()

            open_list = [
                f"#{t['id']} [{_age(t['created_at'])}] {t['description']}"
                for t in open_tasks
            ]
            completed_list = [t["description"] for t in completed_today]

            reply = await agent_interface.perch_review(open_list, completed_list)

            # Only send if the agent has something to say
            if reply.strip().upper() != "OK" and reply.strip():
                channel = await _get_channel()
                await channel.send(f"**Perch** — {reply}")
                logs.write_event(
                    "observation",
                    "Perch review sent message to user",
                    {"reply_preview": reply[:100]},
                )
            else:
                logs.write_event("observation", "Perch review: nothing to flag")
        except Exception as e:
            logger.exception("Perch job failed")
            logs.write_event("error", f"Perch review failed: {e}", {"job": "perch"})

    def _age(created_at: str) -> str:
        created = datetime.fromisoformat(created_at)
        delta = datetime.now(timezone.utc) - created
        hours = int(delta.total_seconds() // 3600)
        if hours < 1:
            return "< 1h"
        if hours < 24:
            return f"{hours}h"
        return f"{hours // 24}d"

    scheduler.add_job(
        morning_checkin,
        CronTrigger(hour=checkin_hour, minute=0, timezone=UK_TZ),
        id="morning_checkin",
        replace_existing=True,
    )
    scheduler.add_job(
        eod_review,
        CronTrigger(hour=eod_hour, minute=0, timezone=UK_TZ),
        id="eod_review",
        replace_existing=True,
    )
    scheduler.add_job(
        stale_nudge,
        IntervalTrigger(hours=2),
        id="stale_nudge",
        replace_existing=True,
    )
    scheduler.add_job(
        perch,
        CronTrigger(hour="10,12,14,16", minute=30, day_of_week="mon-fri", timezone=UK_TZ),
        id="perch",
        replace_existing=True,
    )

    return scheduler

"""
Commands cog — slash commands for tasks, state, journal, events.
Merges tasks.py + memory.py, replaces Letta commands with state file equivalents.
"""
import sqlite3
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord import app_commands

import db
import agent
import memory
import logs


def _age(created_at: str) -> str:
    created = datetime.fromisoformat(created_at)
    delta = datetime.now(timezone.utc) - created
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "< 1h"
    if hours < 24:
        return f"{hours}h"
    return f"{hours // 24}d"


class Commands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Task commands ───────────────────────────────────────────────

    @app_commands.command(name="add", description="Add a new task")
    @app_commands.describe(task="What do you need to do?")
    async def add(self, interaction: discord.Interaction, task: str):
        await interaction.response.defer()
        task_id = db.add_task(task)
        reply = await agent.task_added(f"#{task_id}: {task}")
        await interaction.followup.send(f"**#{task_id}** — {task}\n{reply}")

    @app_commands.command(name="done", description="Mark a task as complete")
    @app_commands.describe(task_id="ID of the task to mark done")
    async def done(self, interaction: discord.Interaction, task_id: int):
        await interaction.response.defer()
        open_tasks = db.list_open_tasks()
        task_desc = next(
            (t["description"] for t in open_tasks if t["id"] == task_id),
            f"Task #{task_id}"
        )
        success = db.complete_task(task_id)
        if not success:
            await interaction.followup.send(f"No open task with ID #{task_id}.")
            return
        reply = await agent.task_completed(task_desc)
        await interaction.followup.send(f"Task #{task_id} marked done. {reply}")

    @app_commands.command(name="tasks", description="List all open tasks")
    async def tasks(self, interaction: discord.Interaction):
        open_tasks = db.list_open_tasks()
        if not open_tasks:
            await interaction.response.send_message("No open tasks. Clean slate.")
            return
        lines = [f"**Open tasks ({len(open_tasks)}):**"]
        for t in open_tasks:
            lines.append(f"  `#{t['id']}` [{_age(t['created_at'])}] {t['description']}")
        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="focus", description="Ask the agent which task to focus on now")
    async def focus(self, interaction: discord.Interaction):
        await interaction.response.defer()
        open_tasks = db.list_open_tasks()
        if not open_tasks:
            await interaction.followup.send("No open tasks to focus on.")
            return
        task_list = [
            f"#{t['id']} [{_age(t['created_at'])}] {t['description']}"
            for t in open_tasks
        ]
        reply = await agent.focus_request(task_list)
        await interaction.followup.send(reply)

    @app_commands.command(name="clear", description="Delete all completed tasks (cleanup)")
    async def clear(self, interaction: discord.Interaction):
        with sqlite3.connect(db.DB_PATH) as conn:
            cur = conn.execute("DELETE FROM tasks WHERE completed_at IS NOT NULL")
            conn.commit()
            count = cur.rowcount
        await interaction.response.send_message(f"Cleared {count} completed task(s).")

    # ── State / memory commands ─────────────────────────────────────

    @app_commands.command(name="state", description="Show the agent's current working memory")
    async def show_state(self, interaction: discord.Interaction):
        content = memory.format_for_prompt()
        if not content:
            await interaction.response.send_message("No state files found.")
            return
        if len(content) > 1900:
            content = content[:1900] + "\n...(truncated)"
        await interaction.response.send_message(f"```markdown\n{content}\n```")

    # ── Journal / events commands ───────────────────────────────────

    @app_commands.command(name="journal", description="Show recent journal entries")
    @app_commands.describe(count="Number of entries to show (default 10, max 50)")
    async def journal(self, interaction: discord.Interaction, count: int = 10):
        count = min(count, 50)
        entries = logs.read_recent_journal(n=count)

        if not entries:
            await interaction.response.send_message("No journal entries found.")
            return

        lines = [f"**Recent Journal ({len(entries)} entries):**"]
        for entry in entries:
            timestamp = entry["t"][:16].replace("T", " ")
            topics = f" [{', '.join(entry['topics'])}]" if entry.get("topics") else ""
            user_stated = f" | User stated: {entry['user_stated']}" if entry.get("user_stated") else ""
            lines.append(f"`{timestamp}`{topics} {entry['summary']}{user_stated}")

        content = "\n".join(lines)
        if len(content) > 1900:
            content = content[:1900] + "\n...(truncated)"
        await interaction.response.send_message(content)

    @app_commands.command(name="events", description="Show recent event logs")
    @app_commands.describe(count="Number of events to show (default 10, max 30)")
    async def events(self, interaction: discord.Interaction, count: int = 10):
        count = min(count, 30)
        entries = logs.read_recent_events(n=count)

        if not entries:
            await interaction.response.send_message("No event logs found.")
            return

        lines = [f"**Recent Events ({len(entries)} entries):**"]
        for entry in entries:
            timestamp = entry["t"][:16].replace("T", " ")
            event_type = entry["event_type"].upper()
            message = entry["message"][:80]
            lines.append(f"`{timestamp}` **{event_type}**: {message}")

        content = "\n".join(lines)
        if len(content) > 1900:
            content = content[:1900] + "\n...(truncated)"
        await interaction.response.send_message(content)

    @app_commands.command(name="search_journal", description="Search journal entries by topic")
    @app_commands.describe(topic="Topic tag to search for (e.g., checkin, task, focus)")
    async def search_journal(self, interaction: discord.Interaction, topic: str):
        entries = logs.query_journal_by_topic(topic)

        if not entries:
            await interaction.response.send_message(f"No journal entries found with topic: `{topic}`")
            return

        entries = entries[-20:]
        lines = [f"**Journal entries with topic `{topic}` ({len(entries)} shown):**"]
        for entry in entries:
            timestamp = entry["t"][:16].replace("T", " ")
            topics = f" [{', '.join(entry['topics'])}]" if entry.get("topics") else ""
            lines.append(f"`{timestamp}`{topics} {entry['summary']}")

        content = "\n".join(lines)
        if len(content) > 1900:
            content = content[:1900] + "\n...(truncated)"
        await interaction.response.send_message(content)


async def setup(bot: commands.Bot):
    await bot.add_cog(Commands(bot))

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone

import db
import agent_interface
import state


def _age(created_at: str) -> str:
    created = datetime.fromisoformat(created_at)
    delta = datetime.now(timezone.utc) - created
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "< 1h"
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


class Tasks(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="add", description="Add a new task")
    @app_commands.describe(task="What do you need to do?")
    async def add(self, interaction: discord.Interaction, task: str):
        await interaction.response.defer()
        task_id = db.add_task(task)
        reply = await agent_interface.task_added(f"#{task_id}: {task}")
        await interaction.followup.send(f"**#{task_id}** — {task}\n{reply}")

    @app_commands.command(name="done", description="Mark a task as complete")
    @app_commands.describe(task_id="ID of the task to mark done")
    async def done(self, interaction: discord.Interaction, task_id: int):
        await interaction.response.defer()
        # Get task description before completing
        open_tasks = db.list_open_tasks()
        task_desc = next(
            (t["description"] for t in open_tasks if t["id"] == task_id),
            f"Task #{task_id}"
        )
        success = db.complete_task(task_id)
        if not success:
            await interaction.followup.send(f"No open task with ID #{task_id}.")
            return
        reply = await agent_interface.task_completed(task_desc)
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
        reply = await agent_interface.focus_request(task_list)
        await interaction.followup.send(reply)

    @app_commands.command(name="state", description="Show the agent's current working memory")
    async def show_state(self, interaction: discord.Interaction):
        content = state.format_for_prompt()
        if not content:
            await interaction.response.send_message("No state files found.")
            return
        if len(content) > 1900:
            content = content[:1900] + "\n...(truncated)"
        await interaction.response.send_message(f"```markdown\n{content}\n```")

    @app_commands.command(name="clear", description="Delete all completed tasks (cleanup)")
    async def clear(self, interaction: discord.Interaction):
        import sqlite3
        with sqlite3.connect(db.DB_PATH) as conn:
            cur = conn.execute("DELETE FROM tasks WHERE completed_at IS NOT NULL")
            conn.commit()
            count = cur.rowcount
        await interaction.response.send_message(f"Cleared {count} completed task(s).")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tasks(bot))

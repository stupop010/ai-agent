import os

import discord
from discord.ext import commands
from discord import app_commands

import db
import agent_interface


class Checkin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._active_checkins: set[int] = set()

    @app_commands.command(name="checkin", description="Start a manual check-in with the bot")
    async def checkin(self, interaction: discord.Interaction):
        await interaction.response.defer()
        open_tasks = db.list_open_tasks()
        task_summary = ""
        if open_tasks:
            task_lines = "\n".join(f"- #{t['id']}: {t['description']}" for t in open_tasks)
            task_summary = f"\n\nCurrent open tasks:\n{task_lines}"
        prompt = (
            f"Stuart is starting a check-in.{task_summary}\n\n"
            "Ask him what he's planning to work on today and whether there's anything blocking him. "
            "Keep it to 2-3 sentences max."
        )
        reply = await agent_interface.ask(prompt, topics=["checkin", "manual"])
        self._active_checkins.add(interaction.user.id)
        await interaction.followup.send(reply)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        user_id = message.author.id

        # Check-in continuation takes priority
        if user_id in self._active_checkins:
            self._active_checkins.discard(user_id)
            reply = await agent_interface.checkin(message.content)
            await message.reply(reply)
            return

        # General chat: respond to any message in the bot's channel
        bot_channel_id = int(os.environ.get("CHANNEL_ID", 0))
        if message.channel.id == bot_channel_id:
            async with message.channel.typing():
                reply = await agent_interface.ask(
                    message.content,
                    topics=["chat", "conversation"],
                )
            await message.reply(reply)

    async def send_morning_checkin(self, channel: discord.TextChannel):
        open_tasks = db.list_open_tasks()
        task_summary = ""
        if open_tasks:
            task_lines = "\n".join(f"- #{t['id']}: {t['description']}" for t in open_tasks)
            task_summary = f"\n\nYou have {len(open_tasks)} open task(s):\n{task_lines}"
        prompt = (
            f"It's morning check-in time for Stuart.{task_summary}\n\n"
            "Start the day with a brief, energising message asking what he's focused on today. "
            "Reference any active commitments or projects if relevant. 2-3 sentences max. No fluff."
        )
        reply = await agent_interface.ask(prompt, topics=["checkin", "morning", "scheduled"])
        await channel.send(f"**Morning check-in**\n{reply}")

    async def send_eod_review(self, channel: discord.TextChannel):
        completed = db.list_todays_completed()
        open_tasks = db.list_open_tasks()

        completed_list = [t["description"] for t in completed]
        open_list = [f"#{t['id']}: {t['description']}" for t in open_tasks]

        reply = await agent_interface.eod_review(open_list, completed_list)
        await channel.send(f"**End-of-day review**\n{reply}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Checkin(bot))

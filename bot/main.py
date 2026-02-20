# v1.0.1 - PR workflow test
import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

import db
import logs
from scheduler import build_scheduler

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

COGS = [
    "cogs.tasks",
    "cogs.checkin",
    "cogs.memory",
]


class AccountabilityBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.scheduler = None

    async def setup_hook(self):
        for cog in COGS:
            await self.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
        await self.tree.sync()
        logger.info("Slash commands synced")
        self.scheduler = build_scheduler(self)
        self.scheduler.start()
        logger.info("Scheduler started")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")

    async def close(self):
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
        await super().close()


def main():
    db.init_db()
    logs.ensure_logs_dir()
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set in environment")
    bot = AccountabilityBot()
    asyncio.run(bot.start(token))


if __name__ == "__main__":
    main()

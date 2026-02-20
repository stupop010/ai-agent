"""
Discord commands for memory inspection and journal viewing.
"""
import discord
from discord.ext import commands
from discord import app_commands

import letta_agent
import memory_tools
import logs


class Memory(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="memories", description="List all agent memory blocks")
    async def memories(self, interaction: discord.Interaction):
        """Show all Letta memory blocks attached to the agent."""
        await interaction.response.defer()

        client = letta_agent.get_client()
        agent_id = letta_agent.get_agent_id()
        blocks = memory_tools.list_memories(client, agent_id)

        if not blocks:
            await interaction.followup.send("No memory blocks found.")
            return

        lines = ["**Agent Memory Blocks:**"]
        for block in blocks:
            label = block["label"]
            value_preview = block["value"]
            lines.append(f"\n**{label}:**")
            lines.append(f"```\n{value_preview}\n```")

        content = "\n".join(lines)
        if len(content) > 1900:
            content = content[:1900] + "\n...(truncated)"

        await interaction.followup.send(content)

    @app_commands.command(name="memory", description="Show a specific memory block")
    @app_commands.describe(label="The memory block label (e.g., persona, human, patterns)")
    async def memory(self, interaction: discord.Interaction, label: str):
        """Show the full content of a specific memory block."""
        await interaction.response.defer()

        client = letta_agent.get_client()
        agent_id = letta_agent.get_agent_id()
        value = memory_tools.get_memory(client, agent_id, label)

        if value is None:
            await interaction.followup.send(f"No memory block found with label: `{label}`")
            return

        content = f"**Memory block: {label}**\n```markdown\n{value}\n```"
        if len(content) > 1900:
            content = content[:1900] + "\n...(truncated)"

        await interaction.followup.send(content)

    @app_commands.command(name="journal", description="Show recent journal entries")
    @app_commands.describe(count="Number of entries to show (default 10, max 50)")
    async def journal(self, interaction: discord.Interaction, count: int = 10):
        """Show recent journal entries for pattern recognition."""
        count = min(count, 50)  # Cap at 50
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
        """Show recent event logs for debugging and introspection."""
        count = min(count, 30)  # Cap at 30
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

    @app_commands.command(name="patterns", description="Show observed behavioral patterns")
    async def patterns(self, interaction: discord.Interaction):
        """Show the agent's observed patterns memory block."""
        await interaction.response.defer()

        client = letta_agent.get_client()
        agent_id = letta_agent.get_agent_id()
        patterns = memory_tools.get_memory(client, agent_id, "patterns")

        if not patterns:
            await interaction.followup.send("No patterns recorded yet.")
            return

        content = f"**Observed Patterns:**\n```markdown\n{patterns}\n```"
        if len(content) > 1900:
            content = content[:1900] + "\n...(truncated)"

        await interaction.followup.send(content)

    @app_commands.command(name="search_journal", description="Search journal entries by topic")
    @app_commands.describe(topic="Topic tag to search for (e.g., checkin, task, focus)")
    async def search_journal(self, interaction: discord.Interaction, topic: str):
        """Search journal entries by topic tag."""
        entries = logs.query_journal_by_topic(topic)

        if not entries:
            await interaction.response.send_message(f"No journal entries found with topic: `{topic}`")
            return

        # Show last 20 matching entries
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
    await bot.add_cog(Memory(bot))

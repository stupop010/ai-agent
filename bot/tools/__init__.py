"""
Tool registry — collects all tool modules and creates the MCP server.
"""
from claude_agent_sdk import create_sdk_mcp_server

from tools.memory_tools import ALL_TOOLS as MEMORY_TOOLS
from tools.state_tools import ALL_TOOLS as STATE_TOOLS
from tools.schedule_tools import ALL_TOOLS as SCHEDULE_TOOLS
from tools.task_tools import ALL_TOOLS as TASK_TOOLS
from tools.journal_tools import ALL_TOOLS as JOURNAL_TOOLS

ALL_TOOLS = MEMORY_TOOLS + STATE_TOOLS + SCHEDULE_TOOLS + TASK_TOOLS + JOURNAL_TOOLS

mcp_server = create_sdk_mcp_server("bot", tools=ALL_TOOLS)

# Tool names for allowed_tools config (mcp__bot__<name>)
ALLOWED_TOOL_NAMES = [f"mcp__bot__{t.name}" for t in ALL_TOOLS]

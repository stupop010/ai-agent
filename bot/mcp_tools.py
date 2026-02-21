"""
MCP tool definitions for the Claude Agent SDK.

Each tool wraps existing logic from claude_client._execute_tool(),
exposing it via the @tool decorator for use with create_sdk_mcp_server.
"""
import json
import logging
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

import agent_jobs
import bot_context
import letta_agent
import memory_tools
import state

logger = logging.getLogger(__name__)


# ── Memory tools ─────────────────────────────────────────────────────


@tool(
    "read_memory",
    "Read a specific memory block from persistent storage. "
    "Use this to recall information you've previously stored. "
    "Common labels: persona, human, patterns, limitations, current_focus",
    {"label": str},
)
async def read_memory(args: dict[str, Any]) -> dict[str, Any]:
    client = letta_agent.get_client()
    agent_id = letta_agent.get_agent_id()
    result = memory_tools.get_memory(client, agent_id, args["label"])
    if result is None:
        text = json.dumps({"error": f"No memory block found with label '{args['label']}'"})
    else:
        text = json.dumps({"label": args["label"], "value": result})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "update_memory",
    "Update an existing memory block in persistent storage. "
    "Use this to save observations, update patterns, or record changes "
    "in Stuart's focus/commitments.",
    {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "The label of the memory block to update"},
            "value": {"type": "string", "description": "The new content for the memory block"},
        },
        "required": ["label", "value"],
    },
)
async def update_memory(args: dict[str, Any]) -> dict[str, Any]:
    client = letta_agent.get_client()
    agent_id = letta_agent.get_agent_id()
    ok = memory_tools.set_memory(client, agent_id, args["label"], args["value"])
    if ok:
        text = json.dumps({"success": True, "label": args["label"]})
    else:
        text = json.dumps({"error": f"Failed to update block '{args['label']}'"})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "list_memories",
    "List all memory blocks in persistent storage. "
    "Returns labels and truncated previews of each block.",
    {},
)
async def list_memories(args: dict[str, Any]) -> dict[str, Any]:
    client = letta_agent.get_client()
    agent_id = letta_agent.get_agent_id()
    blocks = memory_tools.list_memories(client, agent_id)
    text = json.dumps({"blocks": blocks})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "create_memory",
    "Create a new memory block in persistent storage. "
    "Use this to store new categories of information about Stuart.",
    {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "The label for the new memory block"},
            "value": {"type": "string", "description": "The initial content for the memory block"},
        },
        "required": ["label", "value"],
    },
)
async def create_memory(args: dict[str, Any]) -> dict[str, Any]:
    client = letta_agent.get_client()
    agent_id = letta_agent.get_agent_id()
    ok = memory_tools.create_memory(client, agent_id, args["label"], args["value"])
    if ok:
        text = json.dumps({"success": True, "label": args["label"]})
    else:
        text = json.dumps({"error": f"Failed to create block '{args['label']}'"})
    return {"content": [{"type": "text", "text": text}]}


# ── State tools ──────────────────────────────────────────────────────


@tool(
    "read_state",
    "Read a working-memory state file from bot/state/. "
    "Use this to check commitments, projects, patterns, current_focus, "
    "or any other .md file you've previously written.",
    {"filename": str},
)
async def read_state_tool(args: dict[str, Any]) -> dict[str, Any]:
    filename = args["filename"]
    if not filename.endswith(".md") or "/" in filename or "\\" in filename:
        text = json.dumps({"error": "Filename must be a .md file with no path separators"})
    else:
        content = state.read(filename)
        if not content:
            text = json.dumps({"error": f"State file '{filename}' not found or empty"})
        else:
            text = json.dumps({"filename": filename, "content": content})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "write_state",
    "Write to a working-memory state file in bot/state/. "
    "Use this to persist commitments, projects, patterns, current_focus, "
    "or any working memory you want to recall later.",
    {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "Name of the .md file to write (e.g. 'commitments.md')"},
            "content": {"type": "string", "description": "The full content to write to the file"},
        },
        "required": ["filename", "content"],
    },
)
async def write_state_tool(args: dict[str, Any]) -> dict[str, Any]:
    filename = args["filename"]
    if not filename.endswith(".md") or "/" in filename or "\\" in filename:
        text = json.dumps({"error": "Filename must be a .md file with no path separators"})
    else:
        state.write(filename, args["content"])
        text = json.dumps({"success": True, "filename": filename})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "list_state",
    "List all working-memory state files in bot/state/ with previews. "
    "Use this to see what state files exist before reading one.",
    {},
)
async def list_state_tool(args: dict[str, Any]) -> dict[str, Any]:
    state._ensure_dir()
    files = []
    for path in sorted(state.STATE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        preview = content[:120] + "..." if len(content) > 120 else content
        files.append({"filename": path.name, "preview": preview})
    text = json.dumps({"files": files})
    return {"content": [{"type": "text", "text": text}]}


# ── Scheduling tools ─────────────────────────────────────────────────


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
async def schedule_job_tool(args: dict[str, Any]) -> dict[str, Any]:
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
async def cancel_job_tool(args: dict[str, Any]) -> dict[str, Any]:
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
async def list_jobs_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = agent_jobs.list_jobs()
    text = json.dumps(result)
    return {"content": [{"type": "text", "text": text}]}


# ── MCP server bundle ────────────────────────────────────────────────


ALL_TOOLS = [
    read_memory,
    update_memory,
    list_memories,
    create_memory,
    read_state_tool,
    write_state_tool,
    list_state_tool,
    schedule_job_tool,
    cancel_job_tool,
    list_jobs_tool,
]

mcp_server = create_sdk_mcp_server("bot", tools=ALL_TOOLS)

# Tool names for allowed_tools config (mcp__bot__<name>)
ALLOWED_TOOL_NAMES = [f"mcp__bot__{t.name}" for t in ALL_TOOLS]

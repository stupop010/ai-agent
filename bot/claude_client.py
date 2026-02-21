"""
Claude Agent SDK client with Letta memory integration.

Uses the Claude Agent SDK (ClaudeSDKClient) for reasoning, with custom MCP
tools for memory, state, scheduling, and self-modification. Falls back to
the raw Anthropic API if the SDK is unavailable.
"""
import hashlib
import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import agent_jobs
import bot_context
import letta_agent
import logs
import memory_tools
import self_modify
import state

logger = logging.getLogger(__name__)

_conversation_history: list[dict] = []

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
MAX_TOOL_ITERATIONS = 10
MAX_HISTORY = 20  # Keep last N messages (user + assistant pairs)


# ── System prompt ────────────────────────────────────────────────────


def _build_system_prompt() -> str:
    """
    Assemble the system prompt from persona, human context,
    recent journal entries, and limitations.

    Working memory is NOT injected here — the agent reads state files
    on demand via read_state / list_state tools.
    """
    # Recent journal entries for temporal context
    journal_section = logs.format_journal_for_prompt()

    now = datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d %H:%M %Z")

    persona = state.read("persona.md") or letta_agent.PERSONA
    human = state.read("human.md") or letta_agent.HUMAN
    limitations = state.read("limitations.md") or letta_agent.LIMITATIONS

    return (
        f"Current time: {now}\n\n"
        f"{persona}\n\n"
        f"# About Stuart\n{human}\n\n"
        f"{journal_section}"
        f"{limitations}\n"
    )


# ── SDK-based ask() ──────────────────────────────────────────────────


async def ask(message: str) -> str:
    """
    Send a message to Claude via the Agent SDK.

    Uses ClaudeSDKClient with custom MCP tools for memory/state/scheduling.
    Falls back to the raw Anthropic API if the SDK is unavailable or fails.
    """
    global _conversation_history

    # Try SDK first, fall back to raw API
    try:
        reply = await _ask_sdk(message)
    except Exception as e:
        logger.warning("SDK ask failed (%s), falling back to API", e)
        reply = _ask_fallback(message)

    return reply


async def _ask_sdk(message: str) -> str:
    """Send a message using the Claude Agent SDK with custom MCP tools."""
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        AssistantMessage,
        TextBlock,
        ResultMessage,
    )
    from mcp_tools import mcp_server, ALLOWED_TOOL_NAMES

    global _conversation_history

    _conversation_history.append({"role": "user", "content": message})

    # Trim to prevent unbounded growth
    if len(_conversation_history) > MAX_HISTORY:
        _conversation_history = _conversation_history[-MAX_HISTORY:]

    system_prompt = _build_system_prompt()

    # Inject recent conversation history into the prompt for context
    history_context = _format_history_for_prompt()
    if history_context:
        full_prompt = f"{history_context}\n\nUser: {message}"
    else:
        full_prompt = message

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=MODEL,
        mcp_servers={"bot": mcp_server},
        allowed_tools=ALLOWED_TOOL_NAMES + ["WebSearch"],
        permission_mode="bypassPermissions",
        max_turns=MAX_TOOL_ITERATIONS,
    )

    result_parts = []

    async with ClaudeSDKClient(options=options) as client:
        await client.query(full_prompt)

        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        result_parts.append(block.text)
            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    logger.error("SDK returned error: %s", msg.result)
                    if msg.result:
                        result_parts.append(msg.result)

    reply = "\n".join(result_parts) if result_parts else ""

    _conversation_history.append({"role": "assistant", "content": reply})
    return reply


def _format_history_for_prompt() -> str:
    """Format recent conversation history for injection into the prompt."""
    if not _conversation_history:
        return ""

    # Keep last 10 messages for context
    recent = _conversation_history[-10:]
    parts = []
    for msg in recent:
        role = "User" if msg["role"] == "user" else "Assistant"
        content = msg["content"]
        if isinstance(content, str) and content.strip():
            # Truncate long messages
            if len(content) > 500:
                content = content[:500] + "..."
            parts.append(f"{role}: {content}")

    if not parts:
        return ""

    return "Recent conversation:\n" + "\n".join(parts)


# ── Fallback: raw Anthropic API ──────────────────────────────────────

_api_client = None


def _get_api_client():
    """Return (and lazily create) the Anthropic API client singleton."""
    global _api_client
    if _api_client is None:
        import anthropic
        _api_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _api_client


# Tool definitions for fallback mode
FALLBACK_TOOLS = [
    {
        "name": "read_memory",
        "description": "Read a specific memory block from persistent storage.",
        "input_schema": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        },
    },
    {
        "name": "update_memory",
        "description": "Update an existing memory block in persistent storage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["label", "value"],
        },
    },
    {
        "name": "list_memories",
        "description": "List all memory blocks in persistent storage.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_memory",
        "description": "Create a new memory block in persistent storage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["label", "value"],
        },
    },
    {
        "name": "read_state",
        "description": "Read a working-memory state file from bot/state/.",
        "input_schema": {
            "type": "object",
            "properties": {"filename": {"type": "string"}},
            "required": ["filename"],
        },
    },
    {
        "name": "write_state",
        "description": "Write to a working-memory state file in bot/state/.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "list_state",
        "description": "List all working-memory state files in bot/state/.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
    },
    {
        "name": "read_file",
        "description": "Read a file from the project repository.",
        "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
    },
    {
        "name": "edit_code",
        "description": "Propose a code change via PR.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "content_hash": {"type": "string"},
                "new_content": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["file_path", "content_hash", "new_content", "description"],
        },
    },
    {
        "name": "schedule_job",
        "description": "Schedule a one-shot or recurring job.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "message": {"type": "string"},
                "run_at": {"type": "string"},
                "hour": {"type": "integer"},
                "minute": {"type": "integer"},
                "day_of_week": {"type": "string"},
            },
            "required": ["job_id", "message"],
        },
    },
    {
        "name": "cancel_job",
        "description": "Cancel an agent-created scheduled job.",
        "input_schema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "list_jobs",
        "description": "List all agent-created scheduled jobs.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _execute_tool(name: str, args: dict) -> str:
    """Dispatch a tool call (fallback mode)."""
    client = letta_agent.get_client()
    agent_id = letta_agent.get_agent_id()

    if name == "read_memory":
        result = memory_tools.get_memory(client, agent_id, args["label"])
        if result is None:
            return json.dumps({"error": f"No memory block found with label '{args['label']}'"})
        return json.dumps({"label": args["label"], "value": result})

    elif name == "update_memory":
        ok = memory_tools.set_memory(client, agent_id, args["label"], args["value"])
        if ok:
            return json.dumps({"success": True, "label": args["label"]})
        return json.dumps({"error": f"Failed to update block '{args['label']}'"})

    elif name == "list_memories":
        blocks = memory_tools.list_memories(client, agent_id)
        return json.dumps({"blocks": blocks})

    elif name == "create_memory":
        ok = memory_tools.create_memory(client, agent_id, args["label"], args["value"])
        if ok:
            return json.dumps({"success": True, "label": args["label"]})
        return json.dumps({"error": f"Failed to create block '{args['label']}'"})

    elif name == "read_state":
        filename = args["filename"]
        if not filename.endswith(".md") or "/" in filename or "\\" in filename:
            return json.dumps({"error": "Filename must be a .md file with no path separators"})
        content = state.read(filename)
        if not content:
            return json.dumps({"error": f"State file '{filename}' not found or empty"})
        return json.dumps({"filename": filename, "content": content})

    elif name == "write_state":
        filename = args["filename"]
        if not filename.endswith(".md") or "/" in filename or "\\" in filename:
            return json.dumps({"error": "Filename must be a .md file with no path separators"})
        state.write(filename, args["content"])
        return json.dumps({"success": True, "filename": filename})

    elif name == "list_state":
        state._ensure_dir()
        files = []
        for path in sorted(state.STATE_DIR.glob("*.md")):
            content = path.read_text(encoding="utf-8").strip()
            preview = content[:120] + "..." if len(content) > 120 else content
            files.append({"filename": path.name, "preview": preview})
        return json.dumps({"files": files})

    elif name == "read_file":
        file_path = args["file_path"]
        if self_modify._is_path_blocked(file_path):
            return json.dumps({"error": f"Cannot read blocked path: {file_path}"})
        full_path = self_modify.PROJECT_ROOT / file_path
        if not full_path.is_file():
            return json.dumps({"error": f"File not found: {file_path}"})
        try:
            raw = full_path.read_text(encoding="utf-8")
            content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
            content = raw[:10_000]
            return json.dumps({"file_path": file_path, "content": content, "content_hash": content_hash})
        except Exception as e:
            return json.dumps({"error": f"Failed to read file: {e}"})

    elif name == "edit_code":
        result = self_modify.propose_code_change(
            args["file_path"], args["content_hash"], args["new_content"], args["description"],
        )
        return json.dumps(result)

    elif name == "schedule_job":
        bot = bot_context.get_bot()
        if not bot or not bot.scheduler:
            return json.dumps({"error": "Scheduler not available"})
        cron_args = {}
        if "hour" in args:
            cron_args["hour"] = args["hour"]
        if "minute" in args:
            cron_args["minute"] = args["minute"]
        if "day_of_week" in args:
            cron_args["day_of_week"] = args["day_of_week"]
        result = agent_jobs.add_job(
            bot.scheduler, args["job_id"], args["message"],
            cron_args=cron_args if cron_args else None, run_at=args.get("run_at"),
        )
        return json.dumps(result)

    elif name == "cancel_job":
        bot = bot_context.get_bot()
        if not bot or not bot.scheduler:
            return json.dumps({"error": "Scheduler not available"})
        result = agent_jobs.cancel_job(bot.scheduler, args["job_id"])
        return json.dumps(result)

    elif name == "list_jobs":
        result = agent_jobs.list_jobs()
        return json.dumps(result)

    return json.dumps({"error": f"Unknown tool: {name}"})


def _ask_fallback(message: str) -> str:
    """
    Fallback: send a message via the raw Anthropic API with tool_use loop.
    Used when the SDK is unavailable or fails.
    """
    global _conversation_history

    _conversation_history.append({"role": "user", "content": message})

    # Trim to last N messages
    if len(_conversation_history) > MAX_HISTORY:
        _conversation_history = _conversation_history[-MAX_HISTORY:]

    system_prompt = _build_system_prompt()
    client = _get_api_client()

    working_messages = list(_conversation_history)

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            tools=FALLBACK_TOOLS,
            messages=working_messages,
        )

        if response.stop_reason == "end_turn":
            text_parts = [block.text for block in response.content if block.type == "text"]
            reply = "\n".join(text_parts) if text_parts else ""
            _conversation_history.append({"role": "assistant", "content": reply})
            return reply

        if response.stop_reason == "tool_use":
            working_messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("Tool call (fallback): %s(%s)", block.name, json.dumps(block.input)[:100])
                    result = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            working_messages.append({"role": "user", "content": tool_results})
            continue

        text_parts = [block.text for block in response.content if block.type == "text"]
        reply = "\n".join(text_parts) if text_parts else ""
        _conversation_history.append({"role": "assistant", "content": reply})
        return reply

    logger.warning("Hit max tool iterations (%d) in fallback", MAX_TOOL_ITERATIONS)
    _conversation_history.append({
        "role": "assistant",
        "content": "I got caught in a loop processing that. Could you try again?",
    })
    return _conversation_history[-1]["content"]


def clear_history() -> None:
    """Reset conversation history (e.g. for session resets)."""
    global _conversation_history
    _conversation_history = []

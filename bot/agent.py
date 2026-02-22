"""
Unified agent — singleton Claude SDK client with three-tier memory.

Replaces claude_client.py + agent_interface.py. The SDK client is kept
alive as a module-level singleton so conversation history persists
across calls within the same process lifetime.
"""
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ResultMessage,
)
from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

import logs
import memory

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOOL_ITERATIONS = 15
MAX_HISTORY = 20

# Resolve repo root once at import time
_REPO_ROOT = Path("/repo").resolve()

# Directories — any file at or under these paths is blocked
_BLOCKED_DIRS = [
    _REPO_ROOT / "__pycache__",
    _REPO_ROOT / ".git",
    _REPO_ROOT / "bot" / "state",
    _REPO_ROOT / "bot" / "logs",
]

# Name substrings — any file whose resolved name contains one of these is blocked
_BLOCKED_NAME_PATTERNS = [".env", ".db", "credentials", "secrets"]

# Conversation history (SDK doesn't persist across async with blocks)
_conversation_history: list[dict] = []


# ── Permission guard ────────────────────────────────────────────────


def _is_path_blocked(raw_path: str) -> bool:
    """Return True if raw_path resolves to a protected location.

    Uses pathlib.resolve() so path-traversal tricks (e.g. /repo/safe/../.env)
    are neutralised before any comparison is made.
    """
    if not raw_path:
        return True
    try:
        resolved = Path(raw_path).resolve()
    except Exception:
        return True

    for blocked_dir in _BLOCKED_DIRS:
        try:
            resolved.relative_to(blocked_dir)
            return True
        except ValueError:
            pass
        if resolved == blocked_dir:
            return True

    name_lower = resolved.name.lower()
    if any(pattern in name_lower for pattern in _BLOCKED_NAME_PATTERNS):
        return True

    return False


async def _can_use_tool(tool_name, input_data, context):
    """Hard safety guardrail blocking writes/edits to sensitive paths."""
    if tool_name in ("Write", "Edit"):
        raw_path = input_data.get("file_path") or ""
        if _is_path_blocked(raw_path):
            return PermissionResultDeny(message=f"Blocked: {raw_path}")
    return PermissionResultAllow(updated_input=input_data)


# ── System prompt ───────────────────────────────────────────────────


def _build_system_prompt() -> str:
    """
    Assemble system prompt from three-tier memory + journal.

    Tier 1 (core) — always loaded: persona, human, limitations
    Tier 2 (index) — pointers loaded, content on-demand
    Journal — recent entries for temporal awareness
    """
    now = datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d %H:%M %Z")

    core = memory.load_core()
    indices = memory.load_indices()
    journal_section = logs.format_journal_for_prompt()

    parts = [f"Current time: {now}"]

    if core:
        parts.append(core)

    if indices:
        parts.append(f"## Available State Files\n{indices}")

    if journal_section:
        parts.append(journal_section)

    parts.append(
        "To modify your own code, use the self-modify Skill. "
        "Never edit files on the main branch directly."
    )

    return "\n\n".join(parts)


# ── Main ask() ──────────────────────────────────────────────────────


async def ask(
    message: str,
    *,
    topics: list[str] | None = None,
    user_stated: str | None = None,
) -> str:
    """
    Send a message to Claude via the Agent SDK and return the reply.

    Handles:
    - Building system prompt from three-tier memory
    - Conversation history injection
    - Tool loop via SDK
    - Journal logging after each interaction
    """
    from tools import mcp_server, ALLOWED_TOOL_NAMES

    global _conversation_history

    _conversation_history.append({"role": "user", "content": message})
    if len(_conversation_history) > MAX_HISTORY:
        _conversation_history = _conversation_history[-MAX_HISTORY:]

    system_prompt = _build_system_prompt()

    # Inject recent conversation history for context
    history_context = _format_history_for_prompt()
    if history_context:
        full_prompt = f"{history_context}\n\nUser: {message}"
    else:
        full_prompt = message

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=MODEL,
        cwd="/repo",
        setting_sources=["project"],
        mcp_servers={"bot": mcp_server},
        allowed_tools=ALLOWED_TOOL_NAMES + [
            "WebSearch",
            "Skill",
            "Read", "Write", "Edit",
            "Grep", "Glob",
            "Bash",
        ],
        permission_mode="bypassPermissions",
        can_use_tool=_can_use_tool,
        max_turns=MAX_TOOL_ITERATIONS,
    )

    result_parts = []

    try:
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
    except Exception as e:
        logger.error("Agent request failed: %s", e)
        logs.write_event("error", f"Agent request failed: {e}", {"message": message[:200]})
        return "Sorry, I encountered an error processing that request."

    reply = "\n".join(result_parts) if result_parts else ""

    _conversation_history.append({"role": "assistant", "content": reply})

    # Log to journal
    logs.journal(
        summary=_summarize(message),
        topics=topics,
        user_stated=user_stated,
    )

    # Sync Letta memory blocks to disk
    try:
        memory.sync_from_letta()
    except Exception as e:
        logger.warning("Failed to sync state from Letta: %s", e)

    return reply


# ── History formatting ──────────────────────────────────────────────


def _format_history_for_prompt() -> str:
    """Format recent conversation history for injection into the prompt."""
    if not _conversation_history:
        return ""

    recent = _conversation_history[-10:]
    parts = []
    for msg in recent:
        role = "User" if msg["role"] == "user" else "Assistant"
        content = msg["content"]
        if isinstance(content, str) and content.strip():
            if len(content) > 500:
                content = content[:500] + "..."
            parts.append(f"{role}: {content}")

    if not parts:
        return ""

    return "Recent conversation:\n" + "\n".join(parts)


def _summarize(message: str) -> str:
    """Create a brief summary for the journal."""
    msg_preview = message[:80].replace("\n", " ")
    if len(message) > 80:
        msg_preview += "..."
    return f"User: {msg_preview}"


def clear_history() -> None:
    """Reset conversation history."""
    global _conversation_history
    _conversation_history = []


# ── Convenience functions (previously in agent_interface.py) ────────


def log_event(
    event_type: str,
    message: str,
    context: dict | None = None,
) -> None:
    """Log an event for debugging and introspection."""
    logs.write_event(event_type, message, context)


async def checkin(user_message: str) -> str:
    """Handle a check-in interaction."""
    return await ask(user_message, topics=["checkin", "daily"])


async def task_added(task_description: str) -> str:
    """Acknowledge a newly added task."""
    return await ask(
        f"Stuart just added a new task: {task_description}\n\nAcknowledge briefly.",
        topics=["task", "added"],
    )


async def task_completed(task_description: str) -> str:
    """Celebrate a completed task."""
    return await ask(
        f"Stuart just completed: {task_description}\n\nGive brief encouragement.",
        topics=["task", "completed"],
    )


async def focus_request(open_tasks: list[str]) -> str:
    """Ask the agent for focus recommendation."""
    tasks_formatted = "\n".join(f"- {t}" for t in open_tasks)
    return await ask(
        f"Stuart's open tasks:\n{tasks_formatted}\n\nWhich should he focus on first and why?",
        topics=["focus", "prioritization"],
    )


async def perch_review(open_tasks: list[str], completed_today: list[str]) -> str:
    """Autonomous review during perch time."""
    open_formatted = "\n".join(f"- {t}" for t in open_tasks) if open_tasks else "(none)"
    done_formatted = "\n".join(f"- {t}" for t in completed_today) if completed_today else "(none)"

    return await ask(
        f"""Perch review time. Check in on Stuart's progress.

Open tasks:
{open_formatted}

Completed today:
{done_formatted}

If you notice anything concerning (procrastination, stalled tasks, focus issues), say something. Otherwise, you can stay quiet.""",
        topics=["perch", "review", "autonomous"],
    )


async def eod_review(open_tasks: list[str], completed_today: list[str]) -> str:
    """End of day review."""
    open_formatted = "\n".join(f"- {t}" for t in open_tasks) if open_tasks else "(none)"
    done_formatted = "\n".join(f"- {t}" for t in completed_today) if completed_today else "(none)"

    return await ask(
        f"""End of day review.

Completed today:
{done_formatted}

Still open:
{open_formatted}

Give a brief recap and any thoughts for tomorrow.""",
        topics=["eod", "review", "daily"],
    )

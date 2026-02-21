"""
Claude Agent SDK client with Letta memory integration.

Uses the Claude Agent SDK (ClaudeSDKClient) for reasoning, with custom MCP
tools for memory, state, scheduling, and self-modification.
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

import letta_agent
import logs
import state

logger = logging.getLogger(__name__)

_conversation_history: list[dict] = []

MODEL = "claude-sonnet-4-6"
MAX_TOOL_ITERATIONS = 15
MAX_HISTORY = 20  # Keep last N messages (user + assistant pairs)

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
        return True  # treat unparseable paths as blocked

    # Check if path is inside (or exactly equal to) any blocked directory
    for blocked_dir in _BLOCKED_DIRS:
        try:
            resolved.relative_to(blocked_dir)
            return True
        except ValueError:
            pass
        if resolved == blocked_dir:
            return True

    # Check filename against blocked name patterns
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


# ── System prompt ────────────────────────────────────────────────────


def _build_system_prompt() -> str:
    """
    Assemble the system prompt from persona, human context,
    recent journal entries, and limitations.

    Working memory is NOT injected here — the agent reads state files
    on demand via read_state / list_state tools.
    """
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
        f"{limitations}\n\n"
        "To modify your own code, use the self-modify Skill. "
        "Never edit files on the main branch directly.\n"
    )


# ── Main ask() ───────────────────────────────────────────────────────


async def ask(message: str) -> str:
    """
    Send a message to Claude via the Agent SDK.

    Uses ClaudeSDKClient with custom MCP tools for memory/state/scheduling.
    The SDK handles the tool loop automatically.
    """
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
            if len(content) > 500:
                content = content[:500] + "..."
            parts.append(f"{role}: {content}")

    if not parts:
        return ""

    return "Recent conversation:\n" + "\n".join(parts)


def clear_history() -> None:
    """Reset conversation history (e.g. for session resets)."""
    global _conversation_history
    _conversation_history = []

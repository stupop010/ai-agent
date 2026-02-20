"""
Claude Agent SDK wrapper for file/system operations.

This module provides optional integration with the Claude Agent SDK
for sophisticated file manipulation, bash commands, and other tools.
The SDK is optional - if not installed, these features are disabled.
"""
import logging
from pathlib import Path
from typing import AsyncIterator

import logs

logger = logging.getLogger(__name__)

# Check if claude-agent-sdk is available
try:
    from claude_agent_sdk import (
        query,
        ClaudeAgentOptions,
        AssistantMessage,
        TextBlock,
        CLINotFoundError,
        CLIConnectionError,
    )
    CLAUDE_SDK_AVAILABLE = True
    logger.info("Claude Agent SDK is available")
except ImportError:
    CLAUDE_SDK_AVAILABLE = False
    logger.warning("claude-agent-sdk not installed; SDK features disabled")


def is_available() -> bool:
    """Check if Claude Agent SDK is available."""
    return CLAUDE_SDK_AVAILABLE


async def execute_with_tools(
    prompt: str,
    allowed_tools: list[str] | None = None,
    cwd: str | Path | None = None,
    max_turns: int = 10,
) -> str:
    """
    Execute a prompt with Claude Agent SDK tools.

    Args:
        prompt: The task to perform
        allowed_tools: List of tools to allow (Read, Write, Bash, Grep, Glob, etc.)
        cwd: Working directory for tool execution
        max_turns: Maximum conversation turns (default 10)

    Returns:
        The agent's response text

    Raises:
        RuntimeError: If claude-agent-sdk is not installed
    """
    if not CLAUDE_SDK_AVAILABLE:
        raise RuntimeError("claude-agent-sdk is not installed")

    # Default to read-only tools for safety
    if allowed_tools is None:
        allowed_tools = ["Read", "Grep", "Glob"]

    options = ClaudeAgentOptions(
        allowed_tools=allowed_tools,
        cwd=str(cwd) if cwd else None,
        max_turns=max_turns,
    )

    result_parts = []
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_parts.append(block.text)
    except CLINotFoundError:
        logs.write_event("error", "Claude CLI not found", {"prompt": prompt[:100]})
        raise RuntimeError("Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code")
    except CLIConnectionError as e:
        logs.write_event("error", f"Claude CLI connection error: {e}", {"prompt": prompt[:100]})
        raise RuntimeError(f"Failed to connect to Claude CLI: {e}")
    except Exception as e:
        logs.write_event("error", f"Claude SDK error: {e}", {"prompt": prompt[:100]})
        raise

    return "".join(result_parts)


async def read_file(path: str | Path) -> str:
    """Read a file using Claude Agent SDK."""
    return await execute_with_tools(
        f"Read and return the contents of the file: {path}",
        allowed_tools=["Read"],
    )


async def search_codebase(query_str: str, cwd: str | Path | None = None) -> str:
    """Search the codebase for a pattern using Claude Agent SDK."""
    return await execute_with_tools(
        f"Search the codebase for: {query_str}. Return relevant file paths and code snippets.",
        allowed_tools=["Read", "Grep", "Glob"],
        cwd=cwd,
    )


async def execute_code_task(
    task: str,
    cwd: str | Path | None = None,
    allow_write: bool = False,
    allow_bash: bool = False,
) -> str:
    """
    Execute a coding task using Claude Agent SDK.

    Args:
        task: Description of the coding task
        cwd: Working directory
        allow_write: Whether to allow file writing (default False for safety)
        allow_bash: Whether to allow bash commands (default False for safety)

    Returns:
        The agent's response
    """
    tools = ["Read", "Grep", "Glob"]
    if allow_write:
        tools.append("Write")
    if allow_bash:
        tools.append("Bash")

    logs.write_event(
        "decision",
        f"Executing code task with tools: {tools}",
        {"task": task[:100], "allow_write": allow_write, "allow_bash": allow_bash},
    )

    return await execute_with_tools(task, allowed_tools=tools, cwd=cwd)

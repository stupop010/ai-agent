"""
Unified agent interface with logging and state sync.

This module provides the primary interface for all agent interactions.
Claude handles reasoning via the Agent SDK (or fallback API). Letta is
used as a persistent memory store. After each interaction we:
- Log to the journal (temporal awareness layer)
- Sync Letta memory blocks to state files (readable on disk)
"""
import logging

import claude_client
import logs
import state

logger = logging.getLogger(__name__)


async def ask(
    message: str,
    *,
    topics: list[str] | None = None,
    user_stated: str | None = None,
) -> str:
    """
    Send a message to Claude via the Agent SDK and return the reply.
    Claude manages its own memory via MCP tool calls to Letta.
    After each interaction, we log to journal and sync state files.
    """
    try:
        reply = await claude_client.ask(message)
    except Exception as e:
        logger.error("Agent request failed: %s", e)
        logs.write_event("error", f"Agent request failed: {e}", {"message": message[:200]})
        return "Sorry, I encountered an error processing that request."

    # Log to journal
    logs.journal(
        summary=_summarize_interaction(message, reply),
        topics=topics,
        user_stated=user_stated,
    )

    # Sync Letta memory blocks to state files on disk
    try:
        state.sync_from_letta()
    except Exception as e:
        logger.warning("Failed to sync state from Letta: %s", e)

    return reply


def log_event(
    event_type: str,
    message: str,
    context: dict | None = None,
) -> None:
    """Log an event for debugging and introspection."""
    logs.write_event(event_type, message, context)


def _summarize_interaction(message: str, reply: str) -> str:
    """Create a brief summary for the journal."""
    msg_preview = message[:80].replace("\n", " ")
    if len(message) > 80:
        msg_preview += "..."
    return f"User: {msg_preview}"


# Convenience functions for common interaction patterns


async def checkin(user_message: str) -> str:
    """Handle a check-in interaction."""
    return await ask(
        user_message,
        topics=["checkin", "daily"],
    )


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

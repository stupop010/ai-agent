"""
Unified agent interface with context injection and logging.

This module provides the primary interface for all agent interactions,
automatically injecting state context, journal history, and logging
every interaction for pattern recognition.
"""
import logging
from datetime import datetime, timezone

import letta_agent
import logs
import state

logger = logging.getLogger(__name__)


def ask(
    message: str,
    *,
    topics: list[str] | None = None,
    user_stated: str | None = None,
    include_journal: bool = True,
    include_state: bool = True,
) -> str:
    """
    Send a message to the agent with full context injection and logging.

    Args:
        message: The prompt/message to send to the agent
        topics: Optional topic tags for this interaction (e.g., ["task", "focus"])
        user_stated: Optional explicit user commitment to track
        include_journal: Whether to include recent journal in context (default True)
        include_state: Whether to include state files in context (default True)

    Returns:
        The agent's reply as a string
    """
    # Build context
    context_parts = []

    if include_state:
        state_context = state.format_for_prompt()
        if state_context:
            context_parts.append(state_context)

    if include_journal:
        journal_entries = logs.read_recent_journal(n=30)
        journal_context = logs.format_journal_for_prompt(journal_entries)
        if journal_context:
            context_parts.append(journal_context)

    # Compose full prompt
    context = "".join(context_parts)
    full_prompt = f"{context}{message}" if context else message

    # Get agent response
    try:
        reply = letta_agent.ask(full_prompt)
    except Exception as e:
        logger.error("Agent request failed: %s", e)
        logs.write_event("error", f"Agent request failed: {e}", {"message": message[:200]})
        return "Sorry, I encountered an error processing that request."

    # Log this interaction
    logs.journal(
        summary=_summarize_interaction(message, reply),
        topics=topics,
        user_stated=user_stated,
        my_intent=_extract_intent(reply),
    )

    return reply


def ask_with_state_update(
    message: str,
    *,
    topics: list[str] | None = None,
    user_stated: str | None = None,
) -> str:
    """
    Send a message and process any state file updates from the response.

    Use this for interactions where the agent might want to update
    commitments.md, projects.md, etc.

    Args:
        message: The prompt/message to send
        topics: Optional topic tags
        user_stated: Optional user commitment to track

    Returns:
        The agent's reply (with any JSON state updates stripped)
    """
    reply = ask(message, topics=topics, user_stated=user_stated)

    # Check for and apply state updates
    if "{" in reply and "}" in reply:
        try:
            state.apply_updates(reply)
            # Strip the JSON from the reply for display
            reply = _strip_json_block(reply)
        except Exception as e:
            logger.warning("Failed to apply state updates: %s", e)

    return reply


def log_event(
    event_type: str,
    message: str,
    context: dict | None = None,
) -> None:
    """
    Log an event for debugging and introspection.

    Args:
        event_type: Type of event (error, decision, observation, warning)
        message: Description of the event
        context: Optional additional context
    """
    logs.write_event(event_type, message, context)


def _summarize_interaction(message: str, reply: str) -> str:
    """Create a brief summary for the journal."""
    # Truncate message for summary
    msg_preview = message[:80].replace("\n", " ")
    if len(message) > 80:
        msg_preview += "..."
    return f"User: {msg_preview}"


def _extract_intent(reply: str) -> str | None:
    """
    Try to extract the agent's intent from the reply.

    Currently returns None; could be enhanced to parse agent's
    stated intentions from the response.
    """
    # Future: Could use simple heuristics or another LLM call
    # to extract what the agent intended to do
    return None


def _strip_json_block(text: str) -> str:
    """Remove JSON code blocks from text for display."""
    lines = text.split("\n")
    result = []
    in_json = False

    for line in lines:
        if line.strip().startswith("```json"):
            in_json = True
            continue
        elif line.strip() == "```" and in_json:
            in_json = False
            continue
        elif not in_json:
            result.append(line)

    return "\n".join(result).strip()


# Convenience functions for common interaction patterns


def checkin(user_message: str) -> str:
    """Handle a check-in interaction."""
    return ask_with_state_update(
        user_message,
        topics=["checkin", "daily"],
    )


def task_added(task_description: str) -> str:
    """Acknowledge a newly added task."""
    return ask(
        f"Stuart just added a new task: {task_description}\n\nAcknowledge briefly.",
        topics=["task", "added"],
    )


def task_completed(task_description: str) -> str:
    """Celebrate a completed task."""
    return ask(
        f"Stuart just completed: {task_description}\n\nGive brief encouragement.",
        topics=["task", "completed"],
    )


def focus_request(open_tasks: list[str]) -> str:
    """Ask the agent for focus recommendation."""
    tasks_formatted = "\n".join(f"- {t}" for t in open_tasks)
    return ask(
        f"Stuart's open tasks:\n{tasks_formatted}\n\nWhich should he focus on first and why?",
        topics=["focus", "prioritization"],
    )


def perch_review(open_tasks: list[str], completed_today: list[str]) -> str:
    """Autonomous review during perch time."""
    open_formatted = "\n".join(f"- {t}" for t in open_tasks) if open_tasks else "(none)"
    done_formatted = "\n".join(f"- {t}" for t in completed_today) if completed_today else "(none)"

    return ask_with_state_update(
        f"""Perch review time. Check in on Stuart's progress.

Open tasks:
{open_formatted}

Completed today:
{done_formatted}

If you notice anything concerning (procrastination, stalled tasks, focus issues), say something. Otherwise, you can stay quiet.""",
        topics=["perch", "review", "autonomous"],
    )


def eod_review(open_tasks: list[str], completed_today: list[str]) -> str:
    """End of day review."""
    open_formatted = "\n".join(f"- {t}" for t in open_tasks) if open_tasks else "(none)"
    done_formatted = "\n".join(f"- {t}" for t in completed_today) if completed_today else "(none)"

    return ask_with_state_update(
        f"""End of day review.

Completed today:
{done_formatted}

Still open:
{open_formatted}

Give a brief recap and any thoughts for tomorrow.""",
        topics=["eod", "review", "daily"],
    )

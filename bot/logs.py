"""
JSONL temporal log management for agent memory.

Provides journal and event logging for pattern recognition and introspection.
Inspired by Strix: https://timkellogg.me/blog/2025/12/15/strix
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict, Literal

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).parent / "logs"


class JournalEntry(TypedDict):
    """Per-interaction journal entry for temporal tracking."""
    t: str  # ISO timestamp
    topics: list[str]  # Tags for queryability
    user_stated: str | None  # User's verbalized plans/commitments
    my_intent: str | None  # Agent's current task/goal
    summary: str  # Brief summary of interaction


class EventEntry(TypedDict):
    """Event entry for errors, decisions, and observations."""
    t: str  # ISO timestamp
    event_type: Literal["error", "decision", "observation", "warning"]
    message: str
    context: dict | None  # Additional context


def ensure_logs_dir() -> None:
    """Ensure the logs directory exists."""
    LOGS_DIR.mkdir(exist_ok=True)


def write_journal(entry: JournalEntry) -> None:
    """Append a journal entry to journal.jsonl."""
    ensure_logs_dir()
    with open(LOGS_DIR / "journal.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    logger.debug("Journal entry written: %s", entry.get("summary", "")[:50])


def write_event(
    event_type: Literal["error", "decision", "observation", "warning"],
    message: str,
    context: dict | None = None,
) -> None:
    """Write an event entry to events.jsonl."""
    ensure_logs_dir()
    entry: EventEntry = {
        "t": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "message": message,
        "context": context,
    }
    with open(LOGS_DIR / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    logger.debug("Event logged: [%s] %s", event_type, message[:50])


def read_recent_journal(n: int = 40) -> list[JournalEntry]:
    """Read the last n journal entries for prompt injection."""
    path = LOGS_DIR / "journal.jsonl"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return [json.loads(line) for line in lines[-n:]]


def read_recent_events(n: int = 20) -> list[EventEntry]:
    """Read the last n event entries."""
    path = LOGS_DIR / "events.jsonl"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return [json.loads(line) for line in lines[-n:]]


def query_journal_by_topic(topic: str) -> list[JournalEntry]:
    """Query journal entries by topic tag."""
    path = LOGS_DIR / "journal.jsonl"
    if not path.exists():
        return []
    results = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if topic.lower() in [t.lower() for t in entry.get("topics", [])]:
                results.append(entry)
    return results


def format_journal_for_prompt(entries: list[JournalEntry] | None = None) -> str:
    """Format journal entries for injection into agent prompt."""
    if entries is None:
        entries = read_recent_journal(n=40)
    if not entries:
        return ""
    lines = ["## Recent Activity Log:"]
    for entry in entries:
        timestamp = entry["t"][:16].replace("T", " ")
        topics_str = f" [{', '.join(entry['topics'])}]" if entry.get("topics") else ""
        lines.append(f"- [{timestamp}]{topics_str} {entry['summary']}")
    return "\n".join(lines) + "\n\n"


def journal(
    summary: str,
    topics: list[str] | None = None,
    user_stated: str | None = None,
    my_intent: str | None = None,
) -> None:
    """Convenience function to write a journal entry with current timestamp."""
    write_journal({
        "t": datetime.now(timezone.utc).isoformat(),
        "topics": topics or [],
        "user_stated": user_stated,
        "my_intent": my_intent,
        "summary": summary,
    })

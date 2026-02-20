"""
State file management — write-only mirror of Letta memory blocks.

Letta memory blocks are the source of truth. After each interaction,
we sync them to markdown files on disk so they're readable via
VS Code, SSH, or the /state Discord command.
"""
import logging
from pathlib import Path

import letta_agent

logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).parent / "state"


def _ensure_dir():
    STATE_DIR.mkdir(exist_ok=True)


def read(filename: str) -> str:
    path = STATE_DIR / filename
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write(filename: str, content: str) -> None:
    _ensure_dir()
    (STATE_DIR / filename).write_text(content, encoding="utf-8")


def format_for_prompt() -> str:
    """Return all non-empty state files formatted for display."""
    _ensure_dir()
    parts = []
    for path in sorted(STATE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if content:
            parts.append(f"### {path.name}\n{content}")
    if not parts:
        return ""
    return "## Agent's working memory:\n\n" + "\n\n".join(parts) + "\n\n"


def sync_from_letta() -> None:
    """Sync Letta memory blocks to state files on disk."""
    _ensure_dir()
    try:
        client = letta_agent.get_client()
        agent_id = letta_agent.get_agent_id()
        blocks = client.agents.blocks.list(agent_id=agent_id)

        for block in blocks:
            label = block.label
            value = block.value or ""
            if value.strip():
                write(f"{label}.md", value)
                logger.debug("Synced memory block to state: %s.md", label)
    except Exception as e:
        logger.warning("Failed to sync Letta blocks to state: %s", e)

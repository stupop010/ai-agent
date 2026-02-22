"""
Three-tier memory system for the accountability bot.

Tier 1 — Core: Always loaded into system prompt (state/core/*.md)
Tier 2 — Index: Pointers loaded into prompt, content on-demand (state/index/*.md)
Tier 3 — Files: On-demand via tools (state/files/*.md)

Letta memory blocks are a separate layer — highly observed, modifiable
memory that the agent actively monitors and refines (persona, patterns, etc.).
After each interaction, Letta blocks sync to state/core/ files on disk.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).parent / "state"
CORE_DIR = STATE_DIR / "core"
INDEX_DIR = STATE_DIR / "index"
FILES_DIR = STATE_DIR / "files"


def _ensure_dirs():
    """Ensure all state directories exist."""
    for d in (STATE_DIR, CORE_DIR, INDEX_DIR, FILES_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ── Tier 1: Core (always in prompt) ─────────────────────────────────


def load_core() -> str:
    """Load all core memory files for injection into system prompt."""
    _ensure_dirs()
    parts = []
    for path in sorted(CORE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if content:
            parts.append(content)
    return "\n\n".join(parts)


# ── Tier 2: Index (pointers in prompt) ──────────────────────────────


def load_indices() -> str:
    """Load index files — one-line summaries of available state files."""
    _ensure_dirs()
    parts = []
    for path in sorted(INDEX_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if content:
            parts.append(content)
    if not parts:
        return ""
    return "\n\n".join(parts)


# ── Tier 3: Files (on-demand via tools) ─────────────────────────────


def read_file(filename: str) -> str:
    """Read a state file from files/ (with backward compat for root state/)."""
    path = FILES_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    # Backward compat: check root state/ during migration
    fallback = STATE_DIR / filename
    if fallback.exists():
        return fallback.read_text(encoding="utf-8")
    return ""


def write_file(filename: str, content: str) -> None:
    """Write a state file to files/."""
    _ensure_dirs()
    (FILES_DIR / filename).write_text(content, encoding="utf-8")


def list_files() -> list[dict]:
    """List all state files in files/ with previews."""
    _ensure_dirs()
    files = []
    for path in sorted(FILES_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        preview = content[:120] + "..." if len(content) > 120 else content
        files.append({"filename": path.name, "preview": preview})
    return files


def sync_from_letta() -> None:
    """Sync Letta memory blocks to core state files on disk."""
    _ensure_dirs()
    try:
        import letta_agent
        client = letta_agent.get_client()
        agent_id = letta_agent.get_agent_id()
        blocks = client.agents.blocks.list(agent_id=agent_id)

        for block in blocks:
            label = block.label
            value = block.value or ""
            if value.strip():
                (CORE_DIR / f"{label}.md").write_text(value, encoding="utf-8")
                logger.debug("Synced Letta block to core: %s.md", label)
    except Exception as e:
        logger.warning("Failed to sync Letta blocks: %s", e)


def format_for_prompt() -> str:
    """Format all non-empty state files for display (used by /state command)."""
    _ensure_dirs()
    parts = []
    # Show files from files/ dir
    for path in sorted(FILES_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if content:
            parts.append(f"### {path.name}\n{content}")
    if not parts:
        return ""
    return "## Agent's working memory:\n\n" + "\n\n".join(parts) + "\n\n"

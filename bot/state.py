import json
import logging
from pathlib import Path

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
    """Return all non-empty state files formatted for injection into a prompt."""
    _ensure_dir()
    parts = []
    for path in sorted(STATE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if content:
            parts.append(f"### {path.name}\n{content}")
    if not parts:
        return ""
    return "## Stuart's working memory:\n\n" + "\n\n".join(parts) + "\n\n"


def apply_updates(raw: str) -> None:
    """Parse JSON from an agent response and write any updated state files."""
    text = raw.strip()
    # Strip markdown code fence if present
    if "```" in text:
        start = text.find("```") + 3
        end = text.rfind("```")
        text = text[start:end].strip()
        if text.startswith("json"):
            text = text[4:].strip()
    # Find the outermost JSON object
    brace_start = text.find("{")
    brace_end = text.rfind("}") + 1
    if brace_start == -1 or brace_end == 0:
        logger.warning("No JSON found in state update response")
        return
    try:
        updates: dict[str, str] = json.loads(text[brace_start:brace_end])
        for filename, content in updates.items():
            if filename.endswith(".md"):
                write(filename, content)
                logger.info("State updated: %s", filename)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse state update: %s", exc)

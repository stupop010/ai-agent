"""
Self-modification workflow with PR-based human review.

Allows the agent to propose changes to its own code through a safe
workflow: spawns a Claude Code session to make changes on a dev branch,
then creates a PR for human review.

SAFETY: The bot cannot restart itself or merge its own changes.
Human review and deployment is always required.
"""
import os
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import TypedDict

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ResultMessage,
)

import logs

logger = logging.getLogger(__name__)

# Project paths — env var override for Docker (mounted repo at /repo)
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
BOT_DIR = PROJECT_ROOT / "bot"

# Git configuration
DEV_BRANCH = "dev"
MAIN_BRANCH = "main"

# Blocked paths - files the bot should never modify
BLOCKED_PATHS = [
    ".env",
    "*.db",
    "credentials*",
    "secrets*",
    "__pycache__",
    ".git",
]

# System prompt for the inner Claude Code session
_INNER_SYSTEM_PROMPT = """\
You are modifying the Stuart's Accountability Bot codebase.

Project structure:
- bot/ — Python source (main.py, claude_client.py, agent_interface.py, mcp_tools.py, etc.)
- bot/state/ — runtime state files (gitignored, do not modify)
- bot/logs/ — journal logs (gitignored, do not modify)
- bot/Dockerfile — container build

Constraints:
- NEVER modify: .env, *.db, credentials*, secrets*, __pycache__/, .git/
- NEVER modify bot/state/ or bot/logs/ contents
- Python 3.11+, no type stubs needed
- Imports are local modules (no package prefix) — bot runs from bot/ as working dir
- Keep changes minimal and focused on the requested task
- Do NOT add unnecessary comments, docstrings, or type annotations beyond what's needed
"""


class SelfModifyResult(TypedDict):
    success: bool
    pr_url: str | None
    message: str


def _run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the project root."""
    return subprocess.run(
        ["git"] + args,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=check,
        timeout=60,
    )


def _is_path_blocked(path: str) -> bool:
    """Check if a path matches any blocked patterns."""
    from fnmatch import fnmatch
    path_lower = path.lower()
    for pattern in BLOCKED_PATHS:
        if fnmatch(path_lower, pattern.lower()):
            return True
        if pattern.lower() in path_lower:
            return True
    return False


def get_current_branch() -> str:
    """Get the current git branch name."""
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout.strip()


def ensure_dev_branch() -> bool:
    """
    Ensure we're on a fresh dev branch based on current main HEAD.

    Always deletes any existing dev branch first so we start clean —
    stale dev branches from previous PRs would otherwise cause conflicts.

    Returns:
        True if successful, False otherwise
    """
    try:
        current = get_current_branch()

        # If we're on dev already, switch to main first so we can delete it
        if current == DEV_BRANCH:
            _run_git(["checkout", MAIN_BRANCH])

        # Delete stale local dev branch if it exists
        result = _run_git(
            ["rev-parse", "--verify", DEV_BRANCH],
            check=False
        )
        if result.returncode == 0:
            _run_git(["branch", "-D", DEV_BRANCH])

        # Create fresh dev branch from main HEAD
        _run_git(["checkout", "-b", DEV_BRANCH])

        logger.info("Switched to dev branch")
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Failed to ensure dev branch: %s", e)
        return False


def commit_and_push(message: str) -> bool:
    """
    Stage all changes, commit, and push to dev branch.

    Returns:
        True if successful, False otherwise
    """
    try:
        # Stage all changes
        _run_git(["add", "-A"])

        # Check if there are changes to commit
        result = _run_git(["status", "--porcelain"], check=False)
        if not result.stdout.strip():
            logger.info("No changes to commit")
            return False

        # Commit
        _run_git(["commit", "-m", message])

        # Push to origin
        _run_git(["push", "-u", "origin", DEV_BRANCH])

        logger.info("Changes committed and pushed to %s", DEV_BRANCH)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Failed to commit/push: %s", e)
        return False


def create_pr(title: str, body: str) -> str | None:
    """
    Create a GitHub PR from dev to main.

    Returns:
        PR URL if successful, None otherwise
    """
    try:
        result = subprocess.run(
            [
                "gh", "pr", "create",
                "--base", MAIN_BRANCH,
                "--head", DEV_BRANCH,
                "--title", title,
                "--body", body,
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        pr_url = result.stdout.strip()
        logger.info("PR created: %s", pr_url)
        return pr_url
    except FileNotFoundError:
        logger.error("GitHub CLI (gh) not found")
        return None
    except subprocess.CalledProcessError as e:
        logger.error("Failed to create PR: %s\n%s", e, e.stderr)
        return None


def revert_changes() -> bool:
    """Revert all uncommitted changes."""
    try:
        _run_git(["checkout", "."])
        _run_git(["clean", "-fd"])
        logger.info("Reverted uncommitted changes")
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Failed to revert changes: %s", e)
        return False


def _can_use_tool(tool_name: str, tool_input: dict) -> bool:
    """Block writes to sensitive paths in the inner Claude Code session."""
    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        if _is_path_blocked(file_path):
            return False
    return True


async def propose_change(description: str) -> SelfModifyResult:
    """
    Propose a code change using an inner Claude Code session.

    Spawns a Claude Code agent with Read/Write/Edit/Grep/Glob tools
    that makes changes like a developer, then commits to a dev branch
    and creates a PR for human review.

    Args:
        description: What to change and why

    Returns:
        SelfModifyResult with success status and PR URL
    """
    result: SelfModifyResult = {
        "success": False,
        "pr_url": None,
        "message": "",
    }

    logs.write_event(
        "decision",
        f"Starting self-modification: {description}",
        {"description": description},
    )

    # Step 1: Switch to dev branch
    if not ensure_dev_branch():
        result["message"] = "Failed to switch to dev branch"
        logs.write_event("error", result["message"])
        return result

    # Step 2: Spawn inner Claude Code session to make changes
    try:
        response_text = await _run_inner_session(description)
    except Exception as e:
        result["message"] = f"Inner Claude Code session failed: {e}"
        logs.write_event("error", result["message"])
        revert_changes()
        _run_git(["checkout", MAIN_BRANCH], check=False)
        return result

    # Step 3: Commit and push
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    commit_msg = f"[self-modify] {description}\n\nAutomated change at {timestamp}"

    if not commit_and_push(commit_msg):
        result["message"] = "No changes were made by the inner session"
        _run_git(["checkout", MAIN_BRANCH], check=False)
        return result

    # Step 4: Create PR
    pr_body = f"""## Self-Modification Request

**Description:** {description}

**Claude Code Session Output:**
{response_text[:3000]}

---
*This PR was created automatically by the bot's self-modification system.*
*Please review carefully before merging.*
*The bot cannot restart itself — deployment must be done manually.*
"""

    pr_url = create_pr(f"[Bot] {description}", pr_body)

    if pr_url:
        result["success"] = True
        result["pr_url"] = pr_url
        result["message"] = f"PR created successfully: {pr_url}"
        logs.write_event(
            "observation",
            "Self-modification PR created",
            {"pr_url": pr_url, "description": description},
        )
    else:
        result["message"] = "Changes committed but PR creation failed. Check GitHub manually."
        logs.write_event("warning", "PR creation failed after successful commit")

    # Step 5: Switch back to main
    _run_git(["checkout", MAIN_BRANCH], check=False)

    return result


async def _run_inner_session(description: str) -> str:
    """Run the inner Claude Code session and return its response text."""
    options = ClaudeAgentOptions(
        system_prompt=_INNER_SYSTEM_PROMPT,
        model="claude-sonnet-4-6",
        allowed_tools=["Read", "Write", "Edit", "Grep", "Glob"],
        permission_mode="bypassPermissions",
        max_turns=25,
        cwd=str(PROJECT_ROOT),
    )

    result_parts = []

    async with ClaudeSDKClient(options=options) as client:
        await client.query(description)

        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        result_parts.append(block.text)
            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    logger.error("Inner session error: %s", msg.result)
                    if msg.result:
                        result_parts.append(f"Error: {msg.result}")

    return "\n".join(result_parts) if result_parts else "(no output)"

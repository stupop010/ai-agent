"""
Self-modification workflow with PR-based human review.

Allows the agent to propose changes to its own code through a safe
workflow: changes go to a dev branch, validation runs, and a PR is
created for human review.

SAFETY: The bot cannot restart itself or merge its own changes.
Human review and deployment is always required.
"""
import os
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable, TypedDict

import logs

logger = logging.getLogger(__name__)

# Project paths — env var override for Docker (mounted repo at /repo)
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
BOT_DIR = PROJECT_ROOT / "bot"

# Git configuration
DEV_BRANCH = "dev"
MAIN_BRANCH = "main"

# Safety limits
MAX_PRS_PER_DAY = 5

# Blocked paths - files the bot should never modify
BLOCKED_PATHS = [
    ".env",
    "*.db",
    "credentials*",
    "secrets*",
    "__pycache__",
    ".git",
]


class SelfModifyResult(TypedDict):
    success: bool
    validation_passed: bool
    pr_url: str | None
    message: str


class SelfModifyError(Exception):
    """Error during self-modification workflow."""
    pass


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
    Ensure we're on the dev branch, creating it if needed.

    Returns:
        True if successful, False otherwise
    """
    try:
        current = get_current_branch()
        if current == DEV_BRANCH:
            return True

        # Check if dev branch exists
        result = _run_git(
            ["rev-parse", "--verify", DEV_BRANCH],
            check=False
        )

        if result.returncode == 0:
            # Branch exists, check it out
            _run_git(["checkout", DEV_BRANCH])
        else:
            # Create new branch from current HEAD
            _run_git(["checkout", "-b", DEV_BRANCH])

        logger.info("Switched to dev branch")
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Failed to ensure dev branch: %s", e)
        return False


def run_validation() -> tuple[bool, str]:
    """
    Run pyright and pytest validation.

    Returns:
        Tuple of (success, output_message)
    """
    results = []
    success = True

    # Run pyright type checking
    try:
        result = subprocess.run(
            ["pyright", "bot/"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            success = False
            results.append(f"Pyright FAILED:\n{result.stdout}\n{result.stderr}")
        else:
            results.append("Pyright: OK")
    except FileNotFoundError:
        results.append("Pyright: Not installed (skipped)")
    except subprocess.TimeoutExpired:
        success = False
        results.append("Pyright: Timeout")
    except Exception as e:
        success = False
        results.append(f"Pyright error: {e}")

    # Run pytest
    try:
        result = subprocess.run(
            ["pytest", "tests/", "-v", "--tb=short"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            success = False
            results.append(f"Pytest FAILED:\n{result.stdout}\n{result.stderr}")
        else:
            results.append("Pytest: OK")
    except FileNotFoundError:
        results.append("Pytest: No tests directory found (skipped)")
    except subprocess.TimeoutExpired:
        success = False
        results.append("Pytest: Timeout")
    except Exception as e:
        success = False
        results.append(f"Pytest error: {e}")

    return success, "\n".join(results)


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


def self_modify_workflow(
    description: str,
    changes_callback: Callable[[], None],
) -> SelfModifyResult:
    """
    Full self-modification workflow with safety guardrails.

    1. Switch to dev branch
    2. Make changes via callback
    3. Run validation (pyright + pytest)
    4. If valid, commit and create PR
    5. Return result (human must review and merge)

    Args:
        description: Brief description of the changes
        changes_callback: Function that makes the actual file changes

    Returns:
        SelfModifyResult with success status and PR URL
    """
    result: SelfModifyResult = {
        "success": False,
        "validation_passed": False,
        "pr_url": None,
        "message": "",
    }

    logs.write_event(
        "decision",
        f"Starting self-modification: {description}",
        {"description": description},
    )

    # Step 1: Ensure dev branch
    if not ensure_dev_branch():
        result["message"] = "Failed to switch to dev branch"
        logs.write_event("error", result["message"])
        return result

    # Step 2: Make changes
    try:
        changes_callback()
    except Exception as e:
        result["message"] = f"Failed to apply changes: {e}"
        logs.write_event("error", result["message"])
        revert_changes()
        return result

    # Step 3: Run validation
    valid, validation_output = run_validation()
    result["validation_passed"] = valid

    if not valid:
        result["message"] = f"Validation failed:\n{validation_output}"
        logs.write_event("warning", "Self-modify validation failed", {"output": validation_output[:500]})
        revert_changes()
        return result

    # Step 4: Commit and push
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    commit_msg = f"[self-modify] {description}\n\nAutomated change at {timestamp}"

    if not commit_and_push(commit_msg):
        result["message"] = "No changes to commit or push failed"
        return result

    # Step 5: Create PR
    pr_body = f"""## Self-Modification Request

**Description:** {description}

**Validation Results:**
```
{validation_output}
```

---
*This PR was created automatically by the bot's self-modification system.*
*Please review carefully before merging.*
*The bot cannot restart itself - deployment must be done manually.*
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

    return result


def propose_code_change(
    file_path: str,
    old_content: str,
    new_content: str,
    description: str,
) -> SelfModifyResult:
    """
    Propose a specific code change via the self-modify workflow.

    Args:
        file_path: Relative path to the file (from project root)
        old_content: Expected current content (for verification)
        new_content: New content to write
        description: Description of the change

    Returns:
        SelfModifyResult
    """
    # Security check
    if _is_path_blocked(file_path):
        return {
            "success": False,
            "validation_passed": False,
            "pr_url": None,
            "message": f"Cannot modify blocked path: {file_path}",
        }

    full_path = PROJECT_ROOT / file_path

    def make_change():
        # Verify current content matches expected
        if full_path.exists():
            current = full_path.read_text(encoding="utf-8")
            if current != old_content:
                raise SelfModifyError(
                    f"File content doesn't match expected. "
                    f"File may have been modified."
                )
        elif old_content:
            raise SelfModifyError(f"File doesn't exist: {file_path}")

        # Write new content
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(new_content, encoding="utf-8")

    return self_modify_workflow(description, make_change)

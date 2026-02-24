"""Claude Code CLI tool — shells out to `claude -p` for code changes and repo operations."""
import asyncio
import json
import os
from typing import Any

from claude_agent_sdk import tool

MAX_TIMEOUT = 300  # 5 minutes hard cap


@tool(
    "run_claude_code",
    "Run a prompt through the Claude Code CLI (claude -p). "
    "Use this for code changes, git operations, reading/editing files across repos, "
    "and interacting with the Obsidian vault via GitHub. "
    "Returns Claude Code's JSON output including any files changed.",
    {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "What to ask Claude Code to do",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (default: /repo)",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 120, max: 300)",
            },
        },
        "required": ["prompt"],
    },
)
async def run_claude_code(args: dict[str, Any]) -> dict[str, Any]:
    prompt = args["prompt"]
    cwd = args.get("cwd", "/repo")
    timeout = min(args.get("timeout", 120), MAX_TIMEOUT)

    cmd = [
        "claude",
        "-p", prompt,
        "--output-format", "json",
        "--dangerously-skip-permissions",
    ]

    env = os.environ.copy()
    # Ensure git is configured for commits
    env.setdefault("GIT_AUTHOR_NAME", "Stuart Bot")
    env.setdefault("GIT_COMMITTER_NAME", "Stuart Bot")
    env.setdefault("GIT_AUTHOR_EMAIL", "bot@methodline.co.uk")
    env.setdefault("GIT_COMMITTER_EMAIL", "bot@methodline.co.uk")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        text = json.dumps({"error": f"Claude Code timed out after {timeout}s"})
        return {"content": [{"type": "text", "text": text}]}
    except FileNotFoundError:
        text = json.dumps({"error": "claude CLI not found — is @anthropic-ai/claude-code installed?"})
        return {"content": [{"type": "text", "text": text}]}
    except Exception as e:
        text = json.dumps({"error": f"Failed to run Claude Code: {e}"})
        return {"content": [{"type": "text", "text": text}]}

    stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
    stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

    if proc.returncode != 0:
        text = json.dumps({
            "error": f"Claude Code exited with code {proc.returncode}",
            "stderr": stderr_str[:2000],
            "stdout": stdout_str[:2000],
        })
    else:
        # Try to parse JSON output, fall back to raw text
        try:
            result = json.loads(stdout_str)
            text = json.dumps(result)
        except json.JSONDecodeError:
            text = json.dumps({"output": stdout_str[:5000]})

    return {"content": [{"type": "text", "text": text}]}


ALL_TOOLS = [run_claude_code]

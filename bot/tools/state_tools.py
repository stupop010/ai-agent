"""State file tools — read, write, list working memory files."""
import json
from typing import Any

from claude_agent_sdk import tool

import memory


@tool(
    "read_state",
    "Read a working-memory state file. "
    "Use this to check commitments, projects, patterns, current_focus, "
    "or any other .md file you've previously written.",
    {"filename": str},
)
async def read_state(args: dict[str, Any]) -> dict[str, Any]:
    filename = args["filename"]
    if not filename.endswith(".md") or "/" in filename or "\\" in filename:
        text = json.dumps({"error": "Filename must be a .md file with no path separators"})
    else:
        content = memory.read_file(filename)
        if not content:
            text = json.dumps({"error": f"State file '{filename}' not found or empty"})
        else:
            text = json.dumps({"filename": filename, "content": content})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "write_state",
    "Write to a working-memory state file. "
    "Use this to persist commitments, projects, patterns, current_focus, "
    "or any working memory you want to recall later.",
    {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "Name of the .md file to write (e.g. 'commitments.md')"},
            "content": {"type": "string", "description": "The full content to write to the file"},
        },
        "required": ["filename", "content"],
    },
)
async def write_state(args: dict[str, Any]) -> dict[str, Any]:
    filename = args["filename"]
    if not filename.endswith(".md") or "/" in filename or "\\" in filename:
        text = json.dumps({"error": "Filename must be a .md file with no path separators"})
    else:
        memory.write_file(filename, args["content"])
        text = json.dumps({"success": True, "filename": filename})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "list_state",
    "List all working-memory state files with previews. "
    "Use this to see what state files exist before reading one.",
    {},
)
async def list_state(args: dict[str, Any]) -> dict[str, Any]:
    files = memory.list_files()
    text = json.dumps({"files": files})
    return {"content": [{"type": "text", "text": text}]}


ALL_TOOLS = [read_state, write_state, list_state]

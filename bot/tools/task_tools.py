"""Task tools — agent can directly manage Stuart's task list."""
import json
from datetime import datetime, timezone
from typing import Any

from claude_agent_sdk import tool

import db


def _age(created_at: str) -> str:
    created = datetime.fromisoformat(created_at)
    delta = datetime.now(timezone.utc) - created
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "< 1h"
    if hours < 24:
        return f"{hours}h"
    return f"{hours // 24}d"


@tool(
    "add_task",
    "Add a new task to Stuart's task list. Returns the task ID.",
    {"description": str},
)
async def add_task(args: dict[str, Any]) -> dict[str, Any]:
    task_id = db.add_task(args["description"])
    text = json.dumps({"success": True, "task_id": task_id, "description": args["description"]})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "complete_task",
    "Mark a task as complete by its ID.",
    {"task_id": int},
)
async def complete_task(args: dict[str, Any]) -> dict[str, Any]:
    success = db.complete_task(args["task_id"])
    if success:
        text = json.dumps({"success": True, "task_id": args["task_id"]})
    else:
        text = json.dumps({"error": f"No open task with ID #{args['task_id']}"})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "list_tasks",
    "List all open tasks with their IDs, descriptions, and age.",
    {},
)
async def list_tasks(args: dict[str, Any]) -> dict[str, Any]:
    tasks = db.list_open_tasks()
    task_list = [
        {
            "id": t["id"],
            "description": t["description"],
            "age": _age(t["created_at"]),
        }
        for t in tasks
    ]
    text = json.dumps({"tasks": task_list, "count": len(task_list)})
    return {"content": [{"type": "text", "text": text}]}


ALL_TOOLS = [add_task, complete_task, list_tasks]

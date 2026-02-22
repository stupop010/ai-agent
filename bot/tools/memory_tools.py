"""Letta memory tools — highly observed, modifiable memory blocks."""
import json
from typing import Any

from claude_agent_sdk import tool

import letta_agent
import memory_tools


@tool(
    "read_memory",
    "Read a specific memory block from Letta persistent storage. "
    "These are highly observed, modifiable memory blocks — core identity "
    "that you actively monitor and refine. "
    "Common labels: persona, human, patterns, limitations, current_focus",
    {"label": str},
)
async def read_memory(args: dict[str, Any]) -> dict[str, Any]:
    client = letta_agent.get_client()
    agent_id = letta_agent.get_agent_id()
    result = memory_tools.get_memory(client, agent_id, args["label"])
    if result is None:
        text = json.dumps({"error": f"No memory block found with label '{args['label']}'"})
    else:
        text = json.dumps({"label": args["label"], "value": result})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "update_memory",
    "Update an existing Letta memory block. "
    "Use this to refine your observations, update patterns, or evolve "
    "your understanding of Stuart over time.",
    {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "The label of the memory block to update"},
            "value": {"type": "string", "description": "The new content for the memory block"},
        },
        "required": ["label", "value"],
    },
)
async def update_memory(args: dict[str, Any]) -> dict[str, Any]:
    client = letta_agent.get_client()
    agent_id = letta_agent.get_agent_id()
    ok = memory_tools.set_memory(client, agent_id, args["label"], args["value"])
    if ok:
        text = json.dumps({"success": True, "label": args["label"]})
    else:
        text = json.dumps({"error": f"Failed to update block '{args['label']}'"})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "list_memories",
    "List all Letta memory blocks with previews. "
    "Shows your highly observed memory — identity, patterns, focus.",
    {},
)
async def list_memories(args: dict[str, Any]) -> dict[str, Any]:
    client = letta_agent.get_client()
    agent_id = letta_agent.get_agent_id()
    blocks = memory_tools.list_memories(client, agent_id)
    text = json.dumps({"blocks": blocks})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "create_memory",
    "Create a new Letta memory block. "
    "Use this to store new categories of observed information about Stuart.",
    {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "The label for the new memory block"},
            "value": {"type": "string", "description": "The initial content for the memory block"},
        },
        "required": ["label", "value"],
    },
)
async def create_memory(args: dict[str, Any]) -> dict[str, Any]:
    client = letta_agent.get_client()
    agent_id = letta_agent.get_agent_id()
    ok = memory_tools.create_memory(client, agent_id, args["label"], args["value"])
    if ok:
        text = json.dumps({"success": True, "label": args["label"]})
    else:
        text = json.dumps({"error": f"Failed to create block '{args['label']}'"})
    return {"content": [{"type": "text", "text": text}]}


ALL_TOOLS = [read_memory, update_memory, list_memories, create_memory]

"""
Direct Anthropic API client with tool_use for Letta memory management.

Claude handles all reasoning directly. Letta is used solely as a persistent
memory store, accessed via tool_use functions that map to memory_tools.py.
"""
import json
import logging
import os

import anthropic

import letta_agent
import logs
import memory_tools
import self_modify

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None
_conversation_history: list[dict] = []

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
MAX_TOOL_ITERATIONS = 10

# ── Tool definitions for Claude tool_use ──────────────────────────────

TOOLS = [
    {
        "name": "read_memory",
        "description": (
            "Read a specific memory block from persistent storage. "
            "Use this to recall information you've previously stored. "
            "Common labels: persona, human, patterns, limitations, current_focus"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "The label of the memory block to read",
                },
            },
            "required": ["label"],
        },
    },
    {
        "name": "update_memory",
        "description": (
            "Update an existing memory block in persistent storage. "
            "Use this to save observations, update patterns, or record changes "
            "in Stuart's focus/commitments."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "The label of the memory block to update",
                },
                "value": {
                    "type": "string",
                    "description": "The new content for the memory block",
                },
            },
            "required": ["label", "value"],
        },
    },
    {
        "name": "list_memories",
        "description": (
            "List all memory blocks in persistent storage. "
            "Returns labels and truncated previews of each block."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "create_memory",
        "description": (
            "Create a new memory block in persistent storage. "
            "Use this to store new categories of information about Stuart."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "The label for the new memory block",
                },
                "value": {
                    "type": "string",
                    "description": "The initial content for the memory block",
                },
            },
            "required": ["label", "value"],
        },
    },
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
    },
    {
        "name": "read_file",
        "description": (
            "Read a file from the project repository. Use this to inspect "
            "code before proposing changes. Path is relative to project root. "
            "Returns up to 10,000 characters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the file (e.g. 'bot/main.py')",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "edit_code",
        "description": (
            "Propose a code change to the bot's own source code. "
            "This commits the change to a dev branch and creates a GitHub PR "
            "for human review. Stuart must approve and merge before it takes effect. "
            "You MUST read the file first to get the exact old_content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the file (e.g. 'bot/main.py')",
                },
                "old_content": {
                    "type": "string",
                    "description": "The full current content of the file (must match exactly)",
                },
                "new_content": {
                    "type": "string",
                    "description": "The new content to write to the file",
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what the change does and why",
                },
            },
            "required": ["file_path", "old_content", "new_content", "description"],
        },
    },
]


# ── Client & helpers ──────────────────────────────────────────────────


def get_client() -> anthropic.Anthropic:
    """Return (and lazily create) the Anthropic client singleton."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _build_system_prompt() -> str:
    """
    Assemble the system prompt from persona, human context, live Letta
    memory blocks, recent journal entries, and limitations.

    Rebuilt every call so Claude always sees fresh memory state.
    """
    client = letta_agent.get_client()
    agent_id = letta_agent.get_agent_id()

    # Fetch all current memory blocks from Letta
    blocks = memory_tools.list_memories(client, agent_id)
    if blocks:
        memory_section = "# Current Memory Blocks\n\n"
        for b in blocks:
            memory_section += f"## [{b['label']}]\n{b['value']}\n\n"
    else:
        memory_section = "# Current Memory Blocks\n\n(no blocks loaded)\n\n"

    # Recent journal entries for temporal context
    journal_section = logs.format_journal_for_prompt()

    return (
        f"{letta_agent.PERSONA}\n\n"
        f"# About Stuart\n{letta_agent.HUMAN}\n\n"
        f"{memory_section}"
        f"{journal_section}"
        f"{letta_agent.LIMITATIONS}\n"
    )


def _execute_tool(name: str, args: dict) -> str:
    """Dispatch a tool call to the corresponding memory_tools function."""
    client = letta_agent.get_client()
    agent_id = letta_agent.get_agent_id()

    if name == "read_memory":
        result = memory_tools.get_memory(client, agent_id, args["label"])
        if result is None:
            return json.dumps({"error": f"No memory block found with label '{args['label']}'"})
        return json.dumps({"label": args["label"], "value": result})

    elif name == "update_memory":
        ok = memory_tools.set_memory(client, agent_id, args["label"], args["value"])
        if ok:
            return json.dumps({"success": True, "label": args["label"]})
        return json.dumps({"error": f"Failed to update block '{args['label']}'"})

    elif name == "list_memories":
        blocks = memory_tools.list_memories(client, agent_id)
        return json.dumps({"blocks": blocks})

    elif name == "create_memory":
        ok = memory_tools.create_memory(client, agent_id, args["label"], args["value"])
        if ok:
            return json.dumps({"success": True, "label": args["label"]})
        return json.dumps({"error": f"Failed to create block '{args['label']}'"})

    elif name == "read_file":
        file_path = args["file_path"]
        if self_modify._is_path_blocked(file_path):
            return json.dumps({"error": f"Cannot read blocked path: {file_path}"})
        full_path = self_modify.PROJECT_ROOT / file_path
        if not full_path.is_file():
            return json.dumps({"error": f"File not found: {file_path}"})
        try:
            content = full_path.read_text(encoding="utf-8")[:10_000]
            return json.dumps({"file_path": file_path, "content": content})
        except Exception as e:
            return json.dumps({"error": f"Failed to read file: {e}"})

    elif name == "edit_code":
        result = self_modify.propose_code_change(
            args["file_path"],
            args["old_content"],
            args["new_content"],
            args["description"],
        )
        return json.dumps(result)

    return json.dumps({"error": f"Unknown tool: {name}"})


# ── Main ask() with tool_use loop ─────────────────────────────────────


def ask(message: str) -> str:
    """
    Send a message to Claude via the Anthropic API.

    If Claude responds with tool_use, execute the tools and feed results
    back until Claude produces a text response (up to MAX_TOOL_ITERATIONS).

    Only text messages are kept in conversation history; tool exchanges
    are ephemeral (memory blocks are the persistent state).
    """
    global _conversation_history

    _conversation_history.append({"role": "user", "content": message})

    system_prompt = _build_system_prompt()
    client = get_client()

    # Working messages include history + any tool exchanges for this turn
    working_messages = list(_conversation_history)

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            tools=TOOLS,
            messages=working_messages,
        )

        # If Claude gives a text response (possibly with tool_use), check stop reason
        if response.stop_reason == "end_turn":
            # Extract text from the response
            text_parts = [
                block.text for block in response.content if block.type == "text"
            ]
            reply = "\n".join(text_parts) if text_parts else ""

            # Store only the text reply in persistent history
            _conversation_history.append({"role": "assistant", "content": reply})
            return reply

        if response.stop_reason == "tool_use":
            # Add Claude's response (with tool_use blocks) to working messages
            working_messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("Tool call: %s(%s)", block.name, json.dumps(block.input)[:100])
                    result = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            working_messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason — extract whatever text we got
        text_parts = [
            block.text for block in response.content if block.type == "text"
        ]
        reply = "\n".join(text_parts) if text_parts else ""
        _conversation_history.append({"role": "assistant", "content": reply})
        return reply

    # Safety valve: hit max iterations
    logger.warning("Hit max tool iterations (%d)", MAX_TOOL_ITERATIONS)
    _conversation_history.append({
        "role": "assistant",
        "content": "I got caught in a loop processing that. Could you try again?",
    })
    return _conversation_history[-1]["content"]


def clear_history() -> None:
    """Reset conversation history (e.g. for session resets)."""
    global _conversation_history
    _conversation_history = []

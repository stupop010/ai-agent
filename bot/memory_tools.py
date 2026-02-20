"""
Enhanced Letta memory tools for agent self-management.

Provides CRUD operations for memory blocks so the agent can manage
its own memory dynamically.
"""
import logging
from typing import Any

from letta_client import Letta

logger = logging.getLogger(__name__)


def get_memory(client: Letta, agent_id: str, label: str) -> str | None:
    """
    Retrieve a specific memory block by label.

    Args:
        client: Letta client instance
        agent_id: The agent's ID
        label: The memory block label (e.g., "persona", "human", "patterns")

    Returns:
        The block's value as a string, or None if not found
    """
    try:
        block = client.agents.blocks.retrieve(
            agent_id=agent_id,
            block_label=label
        )
        return block.value
    except Exception as e:
        logger.warning("Failed to get memory block '%s': %s", label, e)
        return None


def set_memory(client: Letta, agent_id: str, label: str, value: str) -> bool:
    """
    Update an existing memory block's value.

    Args:
        client: Letta client instance
        agent_id: The agent's ID
        label: The memory block label
        value: The new value for the block

    Returns:
        True if successful, False otherwise
    """
    try:
        client.agents.blocks.update(
            agent_id=agent_id,
            block_label=label,
            value=value
        )
        logger.info("Updated memory block: %s", label)
        return True
    except Exception as e:
        logger.error("Failed to set memory block '%s': %s", label, e)
        return False


def create_memory(
    client: Letta,
    agent_id: str,
    label: str,
    value: str,
    limit: int = 5000,
    description: str | None = None,
) -> bool:
    """
    Create a new memory block and attach it to the agent.

    Args:
        client: Letta client instance
        agent_id: The agent's ID
        label: The label for the new block
        value: The initial value
        limit: Character limit for the block (default 5000)
        description: Optional description of the block's purpose

    Returns:
        True if successful, False otherwise
    """
    try:
        # Create the standalone block
        block = client.blocks.create(
            label=label,
            value=value,
            limit=limit,
            description=description,
        )
        # Attach it to the agent
        client.agents.blocks.attach(agent_id=agent_id, block_id=block.id)
        logger.info("Created and attached memory block: %s", label)
        return True
    except Exception as e:
        logger.error("Failed to create memory block '%s': %s", label, e)
        return False


def list_memories(client: Letta, agent_id: str) -> list[dict[str, Any]]:
    """
    List all memory blocks attached to an agent.

    Args:
        client: Letta client instance
        agent_id: The agent's ID

    Returns:
        List of dicts with block info: label, value (truncated), limit
    """
    try:
        blocks = client.agents.blocks.list(agent_id=agent_id)
        return [
            {
                "label": b.label,
                "value": b.value[:200] + "..." if len(b.value) > 200 else b.value,
                "limit": getattr(b, "limit", None),
                "id": b.id,
            }
            for b in blocks
        ]
    except Exception as e:
        logger.error("Failed to list memory blocks: %s", e)
        return []


def delete_memory(client: Letta, agent_id: str, label: str) -> bool:
    """
    Detach and delete a memory block by label.

    Args:
        client: Letta client instance
        agent_id: The agent's ID
        label: The memory block label to delete

    Returns:
        True if successful, False otherwise
    """
    try:
        # First get the block to find its ID
        block = client.agents.blocks.retrieve(
            agent_id=agent_id,
            block_label=label
        )
        # Detach from agent
        client.agents.blocks.detach(agent_id=agent_id, block_id=block.id)
        # Delete the block
        client.blocks.delete(block_id=block.id)
        logger.info("Deleted memory block: %s", label)
        return True
    except Exception as e:
        logger.error("Failed to delete memory block '%s': %s", label, e)
        return False


def append_to_memory(
    client: Letta,
    agent_id: str,
    label: str,
    content: str,
    separator: str = "\n",
) -> bool:
    """
    Append content to an existing memory block.

    Args:
        client: Letta client instance
        agent_id: The agent's ID
        label: The memory block label
        content: Content to append
        separator: Separator between existing and new content

    Returns:
        True if successful, False otherwise
    """
    current = get_memory(client, agent_id, label)
    if current is None:
        logger.warning("Cannot append to non-existent block: %s", label)
        return False

    new_value = current + separator + content
    return set_memory(client, agent_id, label, new_value)


def memory_exists(client: Letta, agent_id: str, label: str) -> bool:
    """Check if a memory block with the given label exists."""
    return get_memory(client, agent_id, label) is not None

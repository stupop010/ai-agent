"""
CRUD operations for Letta memory blocks.

Letta blocks are highly observed, modifiable memory — the agent actively
monitors and refines these over time (persona, human, patterns, etc.).
"""
import logging

logger = logging.getLogger(__name__)


def get_memory(client, agent_id: str, label: str) -> str | None:
    """Retrieve a memory block by label."""
    try:
        blocks = client.agents.blocks.list(agent_id=agent_id)
        for block in blocks:
            if block.label == label:
                return block.value
        return None
    except Exception as e:
        logger.error("Failed to get memory block '%s': %s", label, e)
        return None


def set_memory(client, agent_id: str, label: str, value: str) -> bool:
    """Update an existing memory block."""
    try:
        blocks = client.agents.blocks.list(agent_id=agent_id)
        for block in blocks:
            if block.label == label:
                client.agents.blocks.update(
                    agent_id=agent_id,
                    block_id=block.id,
                    value=value,
                )
                return True
        logger.warning("Memory block '%s' not found for update", label)
        return False
    except Exception as e:
        logger.error("Failed to update memory block '%s': %s", label, e)
        return False


def create_memory(client, agent_id: str, label: str, value: str, limit: int = 5000) -> bool:
    """Create a new memory block."""
    try:
        block = client.blocks.create(label=label, value=value, limit=limit)
        client.agents.blocks.attach(agent_id=agent_id, block_id=block.id)
        return True
    except Exception as e:
        logger.error("Failed to create memory block '%s': %s", label, e)
        return False


def list_memories(client, agent_id: str) -> list[dict]:
    """List all memory blocks with previews."""
    try:
        blocks = client.agents.blocks.list(agent_id=agent_id)
        return [
            {
                "label": block.label,
                "value": block.value[:200] if block.value else "",
            }
            for block in blocks
        ]
    except Exception as e:
        logger.error("Failed to list memory blocks: %s", e)
        return []


def delete_memory(client, agent_id: str, label: str) -> bool:
    """Delete a memory block."""
    try:
        blocks = client.agents.blocks.list(agent_id=agent_id)
        for block in blocks:
            if block.label == label:
                client.agents.blocks.detach(agent_id=agent_id, block_id=block.id)
                client.blocks.delete(block_id=block.id)
                return True
        return False
    except Exception as e:
        logger.error("Failed to delete memory block '%s': %s", label, e)
        return False

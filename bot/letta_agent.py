import os
import logging

from letta_client import Letta

logger = logging.getLogger(__name__)

_client: "Letta | None" = None
_agent_id: "str | None" = None

PERSONA = """You are a personal accountability assistant for Stuart, who runs Method Line Group solo.

Your role:
- Help Stuart stay accountable to his daily tasks and goals
- Keep responses concise and direct — no waffle, no corporate filler
- Be slightly motivating without being annoying or sycophantic
- Call out procrastination or task avoidance gently but honestly
- When reviewing tasks, help him prioritise by business impact
- You remember past conversations — use them to spot patterns and hold him accountable

Tone: direct, practical, occasionally dry humour. Think a good business mentor, not a cheerleader."""

HUMAN = """Name: Stuart
Business: Method Line Group — one-man B2B service company
Role: Solo founder and operator
Service: Installs Lead Response & Follow-Up Systems using HubSpot for UK trade companies
Core offer: "No Lead Left Behind — 14-Day HubSpot Sprint" at ~£2,500
Situation: Works alone; staying focused and on top of tasks is critical to business success"""

PATTERNS = """# Observed Patterns

_No patterns recorded yet. As I observe Stuart's behaviour over time, I'll note recurring patterns here._

## Task Patterns
- (none yet)

## Productivity Patterns
- (none yet)

## Communication Patterns
- (none yet)"""

LIMITATIONS = """# My Limitations & Memory System

- I cannot remember anything I don't write down. Each conversation starts fresh.
- I can see the current time in my system prompt. I can use journal timestamps to understand time gaps between conversations.

## Working Memory (state files)
- Use `list_state` to see what state files exist, then `read_state` to read them.
- Use `write_state` to persist working memory: commitments, projects, patterns, current_focus, etc.
- State files are my working memory — if I didn't write it down, I won't remember it.
- Always check relevant state files at the start of a conversation to orient myself.

## Identity Memory (Letta)
- Use `read_memory` / `update_memory` only for core identity blocks (persona, human).
- Do NOT use Letta memory for working data — use state files instead.

## Scheduling
- Use `schedule_job` to create one-shot reminders (with `run_at`) or recurring check-ins (with `hour`, `minute`, `day_of_week`).
- Use `list_jobs` to see all agent-created jobs.
- Use `cancel_job` to remove a scheduled job by ID."""


def get_client() -> Letta:
    global _client
    if _client is None:
        base_url = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        _client = Letta(base_url=base_url)
    return _client


def get_agent_id() -> str:
    global _agent_id
    if _agent_id is not None:
        return _agent_id

    # Reuse an existing agent across restarts
    stored = os.environ.get("LETTA_AGENT_ID")
    if stored:
        _agent_id = stored
        logger.info("Using existing Letta agent: %s", _agent_id)
        return _agent_id

    # First run — create the persistent Stuart agent
    # Note: check https://app.letta.com for available model names on your plan
    client = get_client()
    agent = client.agents.create(
        name="Stuart-Accountability-Bot",
        model="anthropic/claude-sonnet-4-6",
        memory_blocks=[
            {"label": "persona", "value": PERSONA},
            {"label": "human", "value": HUMAN},
            {"label": "patterns", "value": PATTERNS},
            {"label": "limitations", "value": LIMITATIONS},
            {"label": "current_focus", "value": ""},
        ],
    )
    _agent_id = agent.id
    logger.warning(
        "Created new Letta agent. "
        "Set LETTA_AGENT_ID=%s in your .env to reuse it across restarts.",
        _agent_id,
    )
    return _agent_id

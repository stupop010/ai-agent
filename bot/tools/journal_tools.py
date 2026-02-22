"""Journal tools — agent can search and read past interactions."""
import json
from typing import Any

from claude_agent_sdk import tool

import logs


@tool(
    "search_journal",
    "Search journal entries by topic tag or keyword in summary. "
    "Returns matching entries with timestamps and summaries.",
    {"query": str},
)
async def search_journal(args: dict[str, Any]) -> dict[str, Any]:
    query = args["query"].lower()

    # Search by topic tag first
    by_topic = logs.query_journal_by_topic(query)

    # Also search in summaries
    all_entries = logs.read_recent_journal(n=200)
    by_summary = [
        e for e in all_entries
        if query in e.get("summary", "").lower()
        and e not in by_topic
    ]

    results = (by_topic + by_summary)[-30:]  # Last 30 matches

    entries = [
        {
            "timestamp": e["t"][:16].replace("T", " "),
            "topics": e.get("topics", []),
            "summary": e.get("summary", ""),
        }
        for e in results
    ]
    text = json.dumps({"query": query, "results": entries, "count": len(entries)})
    return {"content": [{"type": "text", "text": text}]}


@tool(
    "read_journal",
    "Read the most recent journal entries. "
    "Returns timestamps, topics, and summaries.",
    {"count": int},
)
async def read_journal(args: dict[str, Any]) -> dict[str, Any]:
    count = min(args.get("count", 15), 50)
    entries = logs.read_recent_journal(n=count)
    results = [
        {
            "timestamp": e["t"][:16].replace("T", " "),
            "topics": e.get("topics", []),
            "summary": e.get("summary", ""),
            "user_stated": e.get("user_stated"),
        }
        for e in entries
    ]
    text = json.dumps({"entries": results, "count": len(results)})
    return {"content": [{"type": "text", "text": text}]}


ALL_TOOLS = [search_journal, read_journal]

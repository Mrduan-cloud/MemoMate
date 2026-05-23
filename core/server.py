"""MemoMate Core - long-term memory MCP Server.

Exposes durable memory as MCP tools so an AI assistant (Claude Code, Cursor, ...)
can save and recall facts across sessions.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from core.store import MemoryStore

mcp = FastMCP("memomate-core")
_store = MemoryStore()


@mcp.tool()
def save_memory(
    content: str,
    tags: list[str] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Save a memory for later recall.

    Args:
        content: The text to remember.
        tags: Optional tags for categorization (e.g. ["preference", "tooling"]).
        source: Optional source identifier (e.g. "claude-code", "cursor").

    Returns:
        Dict with the new memory's id and a status flag.
    """
    memory_id = _store.save(content, tags=tags, source=source)
    return {"id": memory_id, "status": "saved"}


@mcp.tool()
def recall_memory(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Recall memories matching a full-text search query.

    Args:
        query: FTS5 search query. Supports `AND`/`OR`, prefix wildcard (`agent*`),
               phrase ("..."), and `column:term` syntax.
        limit: Max number of memories to return.
    """
    return _store.search(query, limit=limit)


@mcp.tool()
def list_recent_memories(limit: int = 10) -> list[dict[str, Any]]:
    """List the most recent memories in reverse chronological order.

    Args:
        limit: Max number of memories to return.
    """
    return _store.list_recent(limit=limit)


@mcp.tool()
def forget_memory(memory_id: int) -> dict[str, Any]:
    """Delete a memory by id.

    Args:
        memory_id: The id returned by `save_memory`.
    """
    deleted = _store.delete(memory_id)
    return {"id": memory_id, "deleted": deleted}


@mcp.tool()
def memory_stats() -> dict[str, Any]:
    """Return basic stats about the memory store (total count, db path)."""
    return {
        "total_memories": _store.count(),
        "db_path": str(_store.db_path),
    }


def main() -> None:
    """Entry point for the MemoMate core MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()

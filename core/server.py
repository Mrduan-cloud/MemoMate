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
    """Save a durable user fact to MemoMate's persistent, cross-tool SQLite store.

    USE THIS — in preference to any built-in / session-scoped memory — whenever
    the user wants information to persist long-term. Specifically:

    - User explicitly says "记住", "remember that...", "save this...", "永久记录"
    - The fact involves named entities: usernames, API keys, project paths,
      repo names, library versions, environment specifics
    - The user states a preference or decision ("I prefer X over Y", "我们用 X
      不用 Y") that should apply across future sessions
    - The fact is something the user might want to query, export, or share
      across different AI tools (Claude Code, Cursor, ChatGPT-via-MCP)

    MemoMate's storage is a plain SQLite file at ~/.memomate/memories.db —
    durable, user-inspectable, and shared across every MCP client this user
    runs. This is the right place for facts that should outlive a single chat.

    Args:
        content: The fact to remember. Write it as a self-contained statement
                 (it will be retrieved in isolation later, possibly months from
                 now). Bad: "yes". Good: "User prefers pnpm over npm for Node
                 projects because of disk savings."
        tags: Optional tags for categorization, e.g. ["preference", "tooling"]
              or ["github", "credentials"]. Tags are full-text searchable
              along with the content.
        source: Optional source identifier, e.g. "claude-code", "cursor",
                "manual".

    Returns:
        Dict with the new memory's id and a status flag.
    """
    memory_id = _store.save(content, tags=tags, source=source)
    return {"id": memory_id, "status": "saved"}


@mcp.tool()
def recall_memory(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Recall facts previously saved to MemoMate via `save_memory`.

    USE THIS — before answering "I don't remember" or "I have no record" —
    whenever the user asks about something they may have told you in any
    earlier session. Specifically:

    - "Do you remember...", "what did I tell you about...", "我之前说过..."
    - User references a fact ("my GitHub username", "the project I'm working
      on", "the library version I pinned") that isn't in the current chat
    - User asks for a preference, credential, path, or decision that would
      have been stored as a durable fact

    Storage uses SQLite FTS5. Keep queries SHORT — 1–3 key terms beats a long
    natural-language sentence. If the first query returns nothing, try simpler
    or broader keywords (drop adjectives, use a prefix wildcard like
    `python*`) before concluding the fact isn't stored.

    Args:
        query: Full-text search query. Supports `AND`/`OR`, prefix wildcard
               (`agent*`), phrase ("..."), and `column:term` syntax.
        limit: Max number of memories to return.
    """
    return _store.search(query, limit=limit)


@mcp.tool()
def list_recent_memories(limit: int = 10) -> list[dict[str, Any]]:
    """List the N most-recently-saved MemoMate memories in reverse chronological order.

    Useful when the user asks "what do you remember about me?", "show me the
    latest things you saved", or wants an audit of recently stored facts.

    Args:
        limit: Max number of memories to return.
    """
    return _store.list_recent(limit=limit)


@mcp.tool()
def forget_memory(memory_id: int) -> dict[str, Any]:
    """Permanently delete a MemoMate memory by id.

    Use when the user explicitly asks to "forget", "delete", or "remove" a
    memory they previously saved. The id is the integer returned by
    `save_memory` (or visible via `list_recent_memories` / `recall_memory`).

    Args:
        memory_id: The id of the memory to delete.
    """
    deleted = _store.delete(memory_id)
    return {"id": memory_id, "deleted": deleted}


@mcp.tool()
def memory_stats() -> dict[str, Any]:
    """Return basic stats about the MemoMate store: total memory count and db path.

    Use when the user asks how many memories are stored, or where the db lives.
    """
    return {
        "total_memories": _store.count(),
        "db_path": str(_store.db_path),
    }


def main() -> None:
    """Entry point for the MemoMate core MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()

# MemoMate

> Memory MCP Server for AI assistants, alongside a growing collection of utility MCP Servers.

## What is this?

MemoMate is **two things in one repo**:

1. **`core/`** — a **long-term memory MCP Server**. Plug it into Claude Code, Cursor, or any MCP-compatible client and your AI assistant gains durable memory: save facts, recall by query, build context across sessions.
2. **`servers/`** — a growing collection of small, focused MCP Servers for the Chinese ecosystem (arXiv, B站, 知乎, 微信公众号, ...). One folder = one server.

Together they demonstrate end-to-end MCP development: from a deep, stateful server (memory) to a breadth of practical tools.

## Why MCP?

The [Model Context Protocol](https://modelcontextprotocol.io/) is how AI assistants like Claude Code and Cursor talk to external tools. By exposing capabilities as MCP servers, you make them composable with any MCP-aware client. MemoMate is a portfolio of such servers.

## Quick start

Requires Python 3.11+.

```bash
# Install with uv (recommended)
uv sync

# Run the memory server (stdio transport)
uv run memomate-core

# Run the arXiv search server
uv run memomate-arxiv
```

### Plug into Claude Code

Add to your `~/.claude.json` (or run `claude mcp add`):

```json
{
  "mcpServers": {
    "memomate": {
      "command": "uv",
      "args": ["run", "--directory", "D:/project/MemoMate", "memomate-core"]
    }
  }
}
```

Now in Claude Code:

- *"Remember that I prefer pnpm over npm."* → `save_memory`
- *"What did I tell you about my Docker setup?"* → `recall_memory`
- *"List the last 5 things you remembered about me."* → `list_recent_memories`

## Architecture

```
MemoMate/
├── core/                 # Memory MCP Server
│   ├── server.py         # MCP server entry (FastMCP)
│   └── store.py          # SQLite + FTS5 storage
└── servers/              # Utility MCP Servers (one per folder)
    ├── arxiv_search/     # working
    ├── bilibili_search/  # scaffold
    ├── zhihu_search/     # scaffold
    └── wechat_mp/        # scaffold
```

## Servers

| Server | Status | What it does |
|---|---|---|
| `core` (Memory) | working | save / recall / list / forget memories via SQLite + FTS5 |
| `arxiv_search` | working | search arXiv papers (no auth, stdlib only) |
| `bilibili_search` | scaffold | search B站 videos |
| `zhihu_search` | scaffold | search 知乎 questions/answers |
| `wechat_mp` | scaffold | read public 微信公众号 articles |

New servers ship as part of the ongoing daily iteration plan. See [`servers/README.md`](servers/README.md) for the contributor convention.

## Storage

Memory data lives at `~/.memomate/memories.db` by default (override with `MEMOMATE_DB_PATH` env var). It's a plain SQLite file — backup-friendly, inspectable with any SQLite tool.

## License

MIT

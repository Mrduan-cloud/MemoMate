# MemoMate

> A growing collection of MCP Servers + a portable, exportable memory store — all in one Python repo.

MemoMate is **two things in one project**:

1. **`servers/`** — a growing collection of small, focused **MCP Servers** for the Chinese ecosystem (arXiv, B站, 知乎, 微信公众号, ...). One folder per server. *This is the main draw.*
2. **`core/`** — an **opinionated, portable memory MCP Server** backed by SQLite + FTS5. Single-file storage, cross-tool, queryable. Use when Claude Code's built-in memory isn't enough.

Together they demonstrate end-to-end MCP development: breadth (many tools) and depth (one stateful, exportable store).

---

## The servers (`servers/`) — main attraction

| Server | Status | What it does |
|---|---|---|
| [`arxiv_search`](servers/arxiv_search/) | working | Search arXiv papers via the public Atom API (zero dependencies) |
| [`bilibili_search`](servers/bilibili_search/) | working | Search B站 videos + fetch video info (zero dependencies) |
| [`zhihu_search`](servers/zhihu_search/) | scaffold | Search 知乎 questions & answers |
| [`wechat_mp`](servers/wechat_mp/) | scaffold | Read public 微信公众号 articles |

Each server is a self-contained folder. New servers ship as part of the daily iteration plan.

### Plug into Claude Code

```bash
claude mcp add memomate-arxiv --scope user -- uv run --directory D:/project/MemoMate memomate-arxiv
```

Then ask: *"Find the 3 most recent papers on RAG evaluation."*

---

## The memory store (`core/`) — opinionated alternative

A long-term memory MCP Server backed by SQLite + FTS5. Storage lives in a single file at `~/.memomate/memories.db` that you can:

- **Inspect** with any SQLite tool (DB Browser, DataGrip)
- **Back up** by copying one file
- **Sync** across devices via Syncthing / Dropbox / Git
- **Share** across AI clients — same memory in Claude Code, Cursor, Continue, anything MCP-compatible
- **Query** with tags or full-text search

### Why a memory server when Claude Code already has one?

[Claude Code v2.1+](https://docs.claude.com/en/docs/claude-code) ships with an excellent built-in memory feature that writes to `~/.claude/projects/<project>/memory/*.md` automatically when you say "remember that..." or "记住...". For most workflows, **that's all you need** — and the built-in is what you should use.

MemoMate's memory server fills the gaps where built-in falls short:

| Need | Built-in memory | MemoMate `core/` |
|---|---|---|
| Daily "remember this preference" | ✅ Best | Overkill |
| Project-scoped notes | ✅ Best | Less natural |
| **Cross-tool** memory (Claude Code + Cursor + Continue + custom agents) | ❌ Claude Code only | ✅ Any MCP client |
| **Structured query** by tags + FTS5 | ❌ Plain markdown | ✅ SQLite FTS5 + tag column |
| **Programmatic export** / backup / inspection | ⚠️ Scattered markdown files | ✅ Single portable `.db` file |
| **User-global** (cross-project) facts | ⚠️ Scoped to one project | ✅ Lives in `~/.memomate/` |
| **Programmatic access** from your own scripts | ❌ Parse markdown | ✅ Standard SQL |

If you need any of the bottom four rows, install `core/`. If not, skip it and just use the servers above.

### How to deliberately invoke MemoMate's memory

Because Claude Code's built-in memory has **system-level priority** on generic "记住 / remember" prompts, address MemoMate explicitly when you want it:

- *"save to MemoMate: ..."*
- *"用 MemoMate 记一下：..."*
- *"recall from memomate: ..."*
- *"list memomate memories"*

This explicit-routing pattern is a deliberate design choice — see *Notes on competing with built-in memory* below.

---

## Quick start

Requires Python 3.11+. The project uses [`uv`](https://docs.astral.sh/uv/) for dependency management.

```bash
# clone and install
git clone https://github.com/Mrduan-cloud/MemoMate.git
cd MemoMate
uv sync

# run the memory server (optional)
uv run memomate-core

# run a utility server
uv run memomate-arxiv
```

### Register with Claude Code (user-global)

```bash
# Memory server (only if you decided you want it — see comparison above)
claude mcp add memomate --scope user -- uv run --directory $(pwd) memomate-core

# Utility servers (recommended for all)
claude mcp add memomate-arxiv --scope user -- uv run --directory $(pwd) memomate-arxiv
```

---

## Architecture

```
MemoMate/
├── core/                       # Memory MCP Server (opinionated, optional)
│   ├── server.py               # FastMCP server, 5 tools
│   └── store.py                # SQLite + FTS5 storage
└── servers/                    # Utility MCP Servers (the main draw)
    ├── arxiv_search/           # working
    ├── bilibili_search/        # scaffold
    ├── zhihu_search/           # scaffold
    └── wechat_mp/              # scaffold
```

### Memory tools (`core/`)

| Tool | Purpose |
|---|---|
| `save_memory(content, tags?, source?)` | Persist a fact to SQLite |
| `recall_memory(query, limit=5)` | FTS5 full-text search across saved memories |
| `list_recent_memories(limit=10)` | Reverse-chronological list |
| `forget_memory(memory_id)` | Hard delete by id |
| `memory_stats()` | Total count + db path |

### Adding a new utility server

1. Create `servers/<name>/` with `__init__.py`, `__main__.py`, `server.py`, `README.md`.
2. In `server.py`, expose `mcp = FastMCP("memomate-<name>")` and a `main()` entry point.
3. Register in `pyproject.toml` under `[project.scripts]` as `memomate-<name>`.

See [`servers/arxiv_search/`](servers/arxiv_search/) as the reference implementation.

---

## Notes on competing with built-in memory

During development, I tried hard to make MemoMate's `save_memory` the default destination for "记住 X" prompts. I tightened tool docstrings, added explicit routing hints — none of it overrode Claude Code's built-in memory. The built-in lives at a higher priority than user-installed MCP tools.

**The lesson** isn't "Claude Code built-in beats my project" — it's:

> When your MCP server overlaps with a host's first-party feature, **don't compete on the same trigger phrase**. Differentiate on capability (portability, query model, export format) and require explicit routing.

This is also why MemoMate's main pitch shifted from "your memory layer" to "your **portable** memory layer, plus a collection of practical MCP servers." The portability and the servers are where I add value the built-in can't.

---

## License

MIT

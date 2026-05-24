<div align="center">

<img src="docs/banner.svg" alt="MemoMate · MCP Servers for the Chinese ecosystem + portable cross-tool memory" width="100%"/>

# MemoMate

**A growing collection of MCP Servers + a portable, exportable memory store — all in one Python repo.**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-1.2%2B-purple.svg)](https://modelcontextprotocol.io/)
[![Stars](https://img.shields.io/github/stars/Mrduan-cloud/MemoMate?style=social)](https://github.com/Mrduan-cloud/MemoMate)

[简体中文](README.md) | **English**

</div>

---

MemoMate is **two things in one project**:

1. **`servers/`** — a growing collection of small, focused **MCP Servers** for the Chinese tooling ecosystem (arXiv, Bilibili, Zhihu, WeChat MP, ...). One folder per server. *This is the main draw.*
2. **`core/`** — an **opinionated, portable memory MCP Server** backed by SQLite + FTS5. Single-file storage, cross-tool, queryable. Use when Claude Code's built-in memory isn't enough.

Together they demonstrate end-to-end MCP development: breadth (many tools) and depth (one stateful, exportable store).

---

## The servers (`servers/`) — main attraction

| Server | Status | What it does |
|---|---|---|
| [`arxiv_search`](servers/arxiv_search/) | working | Search arXiv papers via the public Atom API (zero dependencies) |
| [`bilibili_search`](servers/bilibili_search/) | working | Search Bilibili (B站) videos + fetch video info (zero dependencies) |
| [`zhihu_search`](servers/zhihu_search/) | scaffold | Search Zhihu (知乎) questions & answers |
| [`wechat_mp`](servers/wechat_mp/) | scaffold | Read public WeChat MP (微信公众号) articles |

Each server is a self-contained folder. New servers ship as part of the daily iteration plan.

For setup instructions across all IDEs (Cursor, Claude Code, Trae, CodeBuddy, Lingma IDE, ...), see **[Plug into your AI IDE](#plug-into-your-ai-ide)** below.

---

## Why MemoMate for Chinese AI IDE users?

International AI coding tools (Cursor, Claude Code, Cline) excel at code generation, but their MCP ecosystems are heavily Western-centric — arXiv, GitHub, npm, Stack Overflow. Chinese developers regularly need things those don't cover:

- Search **Bilibili / Zhihu / WeChat MP** for technical articles and tutorials
- Look up **12306 train schedules**, **AMap (高德) routes**, **Douban (豆瓣) ratings**
- Query **Chinese SaaS** like Notion-CN, Feishu (飞书), DingTalk (钉钉)
- Read **arXiv-CN mirror** or **CNKI (中国知网)** instead of the slow international arXiv

**MemoMate's `servers/` collection is built to fill exactly this gap.** Each server is a small, focused MCP server for one Chinese-ecosystem tool. Any MCP-compatible IDE plugs them in the same way.

| Common need | MemoMate server | Status |
|---|---|---|
| Find Bilibili video tutorials | `bilibili_search` | working |
| Query arXiv papers | `arxiv_search` | working |
| Search Zhihu technical answers | `zhihu_search` | planned (W03) |
| Read long-form WeChat MP articles | `wechat_mp` | planned (W04) |
| Train schedules / availability | `12306` | planned (W07) |
| GitHub trending | `github_trending` | planned (W06) |
| Douban movie / book ratings | `douban` | planned (W08) |
| Chinese-city weather | `weather_cn` | planned (W06) |
| HackerNews top stories | `hackernews` | planned (W06) |
| Summarize an arXiv paper (local LLM) | `arxiv_summary` | planned (W09) |
| Query a Notion workspace | `notion_query` | planned (W11) |

If you use **Trae / CodeBuddy / Lingma IDE / Cursor / Claude Code** and want your AI to *"find LangGraph tutorial videos on Bilibili"* or *"search Zhihu for RAG evaluation answers"* — MemoMate is built exactly for you.

### Plug into your AI IDE

The MCP JSON structure is **identical across all clients** (it's protocol-standard) — only the file location and the editing UI differ.

**Canonical config (drop this anywhere `mcpServers` is accepted):**

```json
{
  "mcpServers": {
    "memomate-bilibili": {
      "command": "uv",
      "args": ["run", "--directory", "D:/project/MemoMate", "memomate-bilibili"]
    },
    "memomate-arxiv": {
      "command": "uv",
      "args": ["run", "--directory", "D:/project/MemoMate", "memomate-arxiv"]
    },
    "memomate": {
      "command": "uv",
      "args": ["run", "--directory", "D:/project/MemoMate", "memomate-core"]
    }
  }
}
```

#### Where to put it, per IDE

| IDE | Config location | Notes |
|---|---|---|
| **Cursor** | `~/.cursor/mcp.json` (or `.cursor/mcp.json` per-project) | Edit the file directly, then restart Cursor |
| **Claude Code** | `~/.claude.json` (or use the `claude mcp add` CLI) | Recommended: use the CLI (see below) |
| **Trae** (ByteDance) | Settings → AI Models / MCP Servers (menu varies by version) | Paste the entries from the JSON above; or see [Trae docs](https://docs.trae.ai/) |
| **CodeBuddy** (Tencent) | Settings → Extensions → MCP Servers | Add a stdio-type server; transcribe command & args from the JSON |
| **Lingma IDE / 通义灵码** (Alibaba) | Settings → AI Enhanced → MCP Servers | Same UI flow as CodeBuddy |
| **Cline / Continue / Zed** (VSCode/JetBrains extensions) | Each tool's `settings.json` `mcpServers` field | Format is the same |

**Claude Code CLI** (recommended):

```bash
claude mcp add memomate-bilibili --scope user \
  -- uv run --directory D:/project/MemoMate memomate-bilibili
```

> This is the core value of MemoMate — **one server, every IDE.** A Bilibili video you searched in Cursor and saved with `save_memory` can be recalled by `recall_memory` in Lingma IDE next time.

---

## The memory store (`core/`) — opinionated alternative

A long-term memory MCP Server backed by SQLite + FTS5. Storage lives in a single file at `~/.memomate/memories.db` that you can:

- **Inspect** with any SQLite tool (DB Browser, DataGrip)
- **Back up** by copying one file
- **Sync** across devices via Syncthing / Dropbox / Git
- **Share** across AI clients — same memory in Claude Code, Cursor, Continue, anything MCP-compatible
- **Query** with tags or full-text search

### Why a memory server when Claude Code already has one?

[Claude Code v2.1+](https://docs.claude.com/en/docs/claude-code) ships with an excellent built-in memory feature that writes to `~/.claude/projects/<project>/memory/*.md` automatically when you say "remember that..." For most workflows, **that's all you need** — and the built-in is what you should use.

MemoMate's memory server fills the gaps where the built-in falls short:

| Need | Built-in memory | MemoMate `core/` |
|---|---|---|
| Daily "remember this preference" | Best | Overkill |
| Project-scoped notes | Best | Less natural |
| **Cross-tool** memory (Claude Code + Cursor + Continue + custom agents) | Claude Code only | Any MCP client |
| **Structured query** by tags + FTS5 | Plain markdown | SQLite FTS5 + tag column |
| **Programmatic export / backup / inspection** | Scattered markdown files | Single portable `.db` file |
| **User-global** (cross-project) facts | Scoped to one project | Lives in `~/.memomate/` |
| **Programmatic access** from your own scripts | Parse markdown | Standard SQL |

If you need any of the bottom four rows, install `core/`. If not, skip it and just use the servers above.

### How to deliberately invoke MemoMate's memory

Because Claude Code's built-in memory has **system-level priority** on generic "remember" prompts, address MemoMate explicitly when you want it:

- *"save to MemoMate: ..."*
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

### Register with your AI IDE

See **[Plug into your AI IDE](#plug-into-your-ai-ide)** above for full instructions covering Cursor, Claude Code, Trae, CodeBuddy, Lingma IDE, Cline, Continue, and Zed.

---

## Architecture

```
MemoMate/
├── core/                       # Memory MCP Server (opinionated, optional)
│   ├── server.py               # FastMCP server, 5 tools
│   └── store.py                # SQLite + FTS5 storage (WAL mode for concurrent clients)
└── servers/                    # Utility MCP Servers (the main draw)
    ├── arxiv_search/           # working
    ├── bilibili_search/        # working
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

During development, I tried hard to make MemoMate's `save_memory` the default destination for "remember X" prompts. I tightened tool docstrings, added explicit routing hints — none of it overrode Claude Code's built-in memory. The built-in lives at a higher priority than user-installed MCP tools.

**The lesson** isn't "Claude Code built-in beats my project" — it's:

> When your MCP server overlaps with a host's first-party feature, **don't compete on the same trigger phrase.** Differentiate on capability (portability, query model, export format) and require explicit routing.

This is also why MemoMate's main pitch shifted from "your memory layer" to "your **portable** memory layer, plus a collection of practical MCP servers." The portability and the servers are where I add value the built-in can't.

---

## License

MIT

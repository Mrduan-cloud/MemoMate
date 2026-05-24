# MemoMate Servers

A growing collection of small, focused MCP Servers. Each subfolder is one independent server.

## Adding a new server

Each server should:

1. Live in its own folder under `servers/<server_name>/`.
2. Have a `server.py` exposing `mcp = FastMCP(...)` and a `main()` entry point.
3. Have a `__main__.py` so `python -m servers.<name>` works.
4. Have its own `README.md` describing tools, examples, env vars.
5. Be registered in `pyproject.toml` under `[project.scripts]` as `memomate-<name>`.

## Available servers

| Folder | Status | Description |
|---|---|---|
| [`arxiv_search`](arxiv_search/) | working | Search arXiv papers (stdlib only, no auth) |
| [`bilibili_search`](bilibili_search/) | working | Search B站 videos + fetch video info (stdlib only, no auth) |
| [`zhihu_search`](zhihu_search/) | scaffold | Search 知乎 questions / answers |
| [`wechat_mp`](wechat_mp/) | scaffold | Fetch public 微信公众号 article content |

## Why one-folder-per-server?

Each MCP server is independently composable. A user can plug just `arxiv_search` into Claude Code without dragging the rest along. This also makes daily incremental work cheap: adding a new server is adding a folder, not refactoring shared code.

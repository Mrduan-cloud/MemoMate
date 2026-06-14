# github_trending

MCP server for **GitHub Trending** repositories — scrape, **no API key**.

**Zero external dependencies** — stdlib only (`urllib`, `html`, `re`). GitHub has no official
trending API, so this server parses the `github.com/trending` HTML.

## Tools

| Tool | Description |
|---|---|
| `get_github_trending(language="", since="daily", limit=15)` | 热门仓库:`full_name` / `url` / `description` / `language` / `stars`(总星) / `forks` / `stars_in_period`(该时段新增星)。 |

- `since`：`daily` / `weekly` / `monthly`（也认 `今日` / `本周` / `本月`），默认 `daily`。
- `language`：编程语言过滤，如 `python` / `rust` / `c++`（留空 = 全部语言；内部 URL 编码，`c++` → `c%2B%2B`）。
- `limit`：clamp 到 1..50。

## How it works

- 解析 `https://github.com/trending[/<language>]?since=<daily|weekly|monthly>` 的 HTML。
- 自我限流 ≥1s/次（与本仓其它 server 同款 `_RateLimiter`）。
- 解析全部纯函数化（`_build_url` / `_normalize_since` / `_parse_row` / `_parse_trending`），离线可单测。
- 优雅降级：网络/解析错误返回 `[]`；HTML 抓取脆弱，每字段 guarded，缺失即 `None`，不让整页因一个字段崩。

## Example prompts

- *"看看今天 GitHub 上 Python 的热门项目。"*
- *"用 memomate-github-trending 查本周 Rust trending 前 10。"*
- *"What's trending on GitHub this month?"*

## Plug into Claude Code

```bash
claude mcp add memomate-github-trending --scope user \
  -- uv run --directory D:/project/MemoMate memomate-github-trending
```

## Limitations

- 依赖 GitHub trending 页面 HTML 结构；GitHub 改版可能需要更新正则（已尽量用稳定锚点：`/owner/repo/stargazers` 链接、`itemprop="programmingLanguage"`、`N stars today/this week/this month`）。
- 无官方 API，故无分页；trending 每页约 25 条，`limit` 上限 50 已覆盖。

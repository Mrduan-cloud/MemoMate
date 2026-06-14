# hackernews

MCP server for **Hacker News** — official read-only API, **no API key**.

**Zero external dependencies** — stdlib only (`urllib`, `json`). 榜单走 HN 官方 Firebase API
(`/v0/{category}stories.json` + `/v0/item/{id}.json`),全文检索走 Algolia(`hn.algolia.com/api/v1/search`),两者均免 key。

## Tools

| Tool | Description |
|---|---|
| `get_hackernews_stories(category="top", limit=15)` | 榜单条目:`id` / `title` / `url`(无外链时为 HN 讨论页)/ `score` / `by` / `comments` / `age`(m/h/d)/ `hn_url`。 |
| `search_hackernews(query, limit=15)` | 全文检索帖子,返回与榜单同形状的条目(按相关度排序,`age` 留空)。 |

- `category`：`top` / `new` / `best` / `ask` / `show` / `job`（也认 `热门` / `最新` / `最佳` / `提问` / `展示` / `招聘`），默认 `top`。
- `get_hackernews_stories` 的 `limit` clamp 到 1..30（逐条取详情，过大请求数会变多）；`search_hackernews` 的 `limit` clamp 到 1..50。

## How it works

- 榜单：先取 `{category}stories.json` 的 ID 列表，再逐条取 `/v0/item/{id}.json` 详情归一。
- 自我限流：每次工具调用入口 acquire 一次（≥0.5s/次，与本仓其它 server 同款 `_RateLimiter`）；逐条详情之间**不**再限流——HN API 本为高并发只读设计。
- 解析/归一全部纯函数化（`_normalize_category` / `_stories_endpoint` / `_normalize_item` / `_parse_search` / `_humanize_age`），离线可单测。
- 优雅降级：网络/解析错误返回 `[]`；个别条目坏掉（被删 / dead / 无标题）只跳过该条，不让整个榜单崩。

## Example prompts

- *"看看 Hacker News 今天的热门帖子前 10。"*
- *"用 memomate-hackernews 查 Ask HN 最新都在聊什么。"*
- *"Search Hacker News for posts about Rust async runtimes."*

## Plug into Claude Code

```bash
claude mcp add memomate-hackernews --scope user \
  -- uv run --directory D:/project/MemoMate memomate-hackernews
```

## Limitations

- 榜单按「ID 列表 → 逐条详情」拉取，`limit` 越大 HTTP 请求越多，故上限 30；搜索是单次请求，上限 50。
- 搜索结果走 Algolia 索引（社区维护、与官方数据偶有延迟），`age` 不返回。

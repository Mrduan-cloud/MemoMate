# zhihu_search

> **Status:** scaffold — implementation pending.

## Planned tools

| Tool | Description |
|---|---|
| `search_zhihu(query, kind="question"\|"answer", limit=5)` | Search 知乎 questions or answers. |
| `fetch_answer(answer_id)` | Fetch a single answer's body (markdown). |

## Implementation notes

- 知乎 has anti-scraping; we'll use the public `www.zhihu.com/api/v4/search_v3` endpoint with a polite UA.
- Rate-limit aggressively: 2–3s between calls.
- Cache results (24h) in `~/.memomate/zhihu_cache.db` to avoid hammering.

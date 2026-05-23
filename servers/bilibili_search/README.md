# bilibili_search

> **Status:** scaffold — implementation pending.

## Planned tools

| Tool | Description |
|---|---|
| `search_bilibili_videos(query, page=1)` | Search B站 videos by keyword. |
| `get_video_info(bvid)` | Fetch title, uploader, duration, view/like stats. |

## Implementation notes

- B站 has public web search endpoints that do **not** require login (e.g. `api.bilibili.com/x/web-interface/search/all/v2`).
- Subtitle fetching (a possible future tool) requires `SESSDATA` cookie — keep it env-based.
- Rate-limit: add a 1s sleep between calls to be polite.

# wechat_mp

> **Status:** scaffold — implementation pending.

## Planned tools

| Tool | Description |
|---|---|
| `fetch_wechat_article(url)` | Given `mp.weixin.qq.com/s/...`, return `{title, author, publish_time, markdown}`. |

## Implementation notes

- HTML extraction via `httpx` + `selectolax` (fast) or `beautifulsoup4` (forgiving).
- Some `mp.weixin.qq.com/s/...` links are short-lived; persist raw HTML to `~/.memomate/wechat_raw/<sha1>.html` to allow re-parsing later.
- Convert HTML body → markdown via `markdownify`.

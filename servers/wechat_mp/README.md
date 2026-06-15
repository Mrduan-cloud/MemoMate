# wechat_mp

MCP server for **微信公众号 public articles** — parse a given article URL, **no API key**.

**Zero external dependencies** — stdlib only (`urllib` / `re` / `html` / `time`). 给定一篇公开的公众号文章链接,抓取并抽取标题/公众号/作者/发布时间/正文纯文本。

## Tools

| Tool | Description |
|---|---|
| `fetch_wechat_article(url)` | 抓取并解析一篇公开文章,返回统一形状 dict:`url / title / account / account_id / author / digest / publish_time / text / error`。 |

- `url`：`https://mp.weixin.qq.com/s/...` 或 `https://mp.weixin.qq.com/s?__biz=...`。
- 非文章链接 / 网络失败 / 解析失败 → `error` 非空、其余字段为空(优雅降级,不抛异常)。

## How it works

- 标题/摘要/作者走 `og:` meta(最稳),公众号名走 `var nickname = htmlDecode("...")`,正文在 `id="js_content"` 区(以 `content_bottom_area` / `js_temp_bottom_area` 为收尾哨兵)。
- 自我限流 ≥1s/次(与本仓其它 server 同款 `_RateLimiter`);解析全部纯函数化(`parse_article` / `_extract_body` / `_html_to_text` / `_format_publish_time`),离线可单测。
- **抗截断**(实测要点):微信文章页 3MB+ 且常触发 `http.client.IncompleteRead`(声明的 Content-Length 收不齐)→ 用 `e.partial` 兜住;而 `var nickname` / `var ct` / `var user_name` 在文末易被截断,故 `account` 在 nickname 缺失时回退 `author`(og 头部),`publish_time` 优先取正文前的 `create_timestamp`。`account_id` 仅文末有,属 best-effort,截断时可能为空。
- 优雅降级:数据中心 IP 偶尔被返「环境异常」验证页 → 解析不到标题且正文为空时按失败返回 `error`。

## Example prompts

- *"帮我把这篇公众号文章读出来:https://mp.weixin.qq.com/s/xxxx"*
- *"用 memomate-wechat-mp 取一下这篇推文的标题、公众号和正文。"*
- *"Summarize this WeChat article: <mp.weixin.qq.com link>."*

## Plug into Claude Code

```bash
claude mcp add memomate-wechat-mp --scope user \
  -- uv run --directory D:/project/MemoMate memomate-wechat-mp
```

## Limitations

- 仅支持**公开**文章;需要登录/付费/仅粉丝可见的内容拿不到。
- 部分 `mp.weixin.qq.com/s/...` 短链会过期失效;返回纯文本(图片/排版丢弃),不做 markdown 还原。
- 数据中心 IP 可能被返验证页 → 此时 `error` 非空,换 CN 家用网络重试。
- live 测试(`@network`)默认跳过,需设 `WECHAT_TEST_URL` 环境变量再 `pytest -m network`。

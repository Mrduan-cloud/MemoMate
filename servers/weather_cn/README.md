# weather_cn

MCP server for Chinese-city weather via [wttr.in](https://wttr.in) — **no API key required**.

**Zero external dependencies** — uses only the Python standard library (`urllib`, `json`).

## Tools

| Tool | Description |
|---|---|
| `get_weather(city)` | 当前天气:中文天气描述、气温/体感(°C)、湿度、风速风向、降水、能见度、UV、今日最高/最低温。 |
| `get_forecast(city, days=3)` | 未来 1–3 天预报(wttr.in 上限 3 天):逐日最高/最低温、正午天气描述、最大降雨概率、日出日落。 |

中文城市名可直接用(`北京` / `杭州` / `乌鲁木齐`),英文也行(`Shanghai`);内部 URL 编码后交给 wttr.in 解析。

## How it works

- 走 wttr.in 的 `format=j1` JSON 端点,`lang=zh` 请求中文天气描述(`lang_zh`,缺翻译时回退英文 `weatherDesc`)。
- 自我限流 ≥1s/次(wttr.in 对高频客户端会限流),与本仓其他 server 同款 `_RateLimiter`。
- 解析全部纯函数化(`_build_url` / `_zh_desc` / `_parse_current` / `_parse_forecast`),离线可单测。
- 优雅降级:任何网络/解析错误返回 `{"error": ...}`,不抛栈给 MCP client。

## Example prompts

- *"北京今天天气怎么样?"*
- *"用 memomate-weather 查一下杭州未来三天的天气,周末适合骑行吗?"*
- *"What's the weather in Chengdu?"*

## Plug into Claude Code

```bash
claude mcp add memomate-weather --scope user \
  -- uv run --directory D:/project/MemoMate memomate-weather
```

## Limitations

- wttr.in 免费公共服务,偶有限流/超时;失败时返回 error dict,稍后重试即可。
- 预报上限 3 天(j1 契约);小城市/区县名可能被解析到邻近城市,返回的 `location` 字段会回显实际命中的地点。

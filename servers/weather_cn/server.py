"""MCP server for Chinese-city weather via wttr.in (no API key required).

Zero external dependencies: stdlib HTTP + JSON only. wttr.in's ``format=j1``
endpoint returns structured JSON for any city worldwide — Chinese city names
(北京 / 上海 / 杭州…) work directly once URL-encoded, and ``lang=zh`` asks for
Chinese condition descriptions (``lang_zh``; we fall back to the English
``weatherDesc`` when a translation is missing).

Conventions shared with the sibling servers (zhihu / bilibili):
- self-rate-limit between calls (wttr.in throttles aggressive clients);
- pure parse functions (offline unit-testable);
- graceful degradation — network / parse errors return an ``{"error": ...}``
  dict instead of raising to the MCP client.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP

from runtime import run_server

mcp = FastMCP("memomate-weather-cn")

_BASE = "https://wttr.in"
_UA = "memomate-weather-cn/0.1 (+https://github.com/Mrduan-cloud/MemoMate)"
# j1 hourly is 8 slots at 3h steps (00:00..21:00) → index 4 == 12:00 noon,
# the most representative slot for a day's headline description.
_NOON_SLOT = 4

# WWO 标准天气码 → 中文。实测 wttr.in 的 lang_zh 字段经常装的是英文
# (lang=zh 参数 / Accept-Language 头 / zh 子域三种姿势都一样),
# 所以中文描述以本地码表为准,lang_zh 只作未知码的回退。
_WEATHER_CODE_ZH: dict[str, str] = {
    "113": "晴", "116": "局部多云", "119": "多云", "122": "阴",
    "143": "薄雾", "248": "雾", "260": "冻雾",
    "176": "局部阵雨", "263": "局部毛毛雨", "266": "毛毛雨",
    "281": "冻毛毛雨", "284": "强冻毛毛雨",
    "293": "局部小雨", "296": "小雨", "299": "局部中雨", "302": "中雨",
    "305": "局部大雨", "308": "大雨", "311": "冻雨", "314": "强冻雨",
    "353": "小阵雨", "356": "中到大阵雨", "359": "强阵雨",
    "179": "局部阵雪", "227": "风吹雪", "230": "暴风雪",
    "323": "局部小雪", "326": "小雪", "329": "局部中雪", "332": "中雪",
    "335": "局部大雪", "338": "大雪", "368": "小阵雪", "371": "中到大阵雪",
    "182": "局部雨夹雪", "185": "局部冻毛毛雨", "317": "小雨夹雪",
    "320": "中雨夹雪", "362": "小阵雨夹雪", "365": "中阵雨夹雪",
    "350": "冰粒", "374": "小冰粒阵", "377": "中冰粒阵",
    "200": "局部雷阵雨", "386": "雷阵雨", "389": "强雷阵雨",
    "392": "雷阵雪", "395": "大暴雪",
}


class _RateLimiter:
    """Minimal min-interval limiter (same shape as the 知乎 / B站 servers').

    ``wait_seconds(now)`` is a **pure** function of the last-call timestamp so
    the throttle math is unit-testable without sleeping; ``acquire()`` applies
    it against the real monotonic clock.
    """

    def __init__(self, min_interval: float = 1.0) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def wait_seconds(self, now: float) -> float:
        return max(0.0, self.min_interval - (now - self._last))

    def acquire(self) -> None:
        wait = self.wait_seconds(time.monotonic())
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()


_limiter = _RateLimiter(1.0)


# ============ pure helpers (offline unit-testable) ============
def _build_url(city: str) -> str:
    """wttr.in JSON URL for a city. Chinese names are percent-encoded.

    ``safe=""`` also encodes ``/`` so a city string can't address other
    wttr.in paths (e.g. ``:help``) — harmless but sloppier.
    """
    q = urllib.parse.quote((city or "").strip(), safe="")
    return f"{_BASE}/{q}?format=j1&lang=zh"


def _zh_desc(obj: dict[str, Any]) -> str:
    """Condition text: local WWO code map first, then lang_zh, then English.

    上游 lang_zh 不可靠(常为英文),本地码表才是中文描述的权威来源;
    未知码再走 ``lang_zh → weatherDesc`` 回退链。所有字段访问都有防护
    (列表元素可能不是 dict)。
    """
    code = str(obj.get("weatherCode") or "").strip()
    if code in _WEATHER_CODE_ZH:
        return _WEATHER_CODE_ZH[code]
    for key in ("lang_zh", "weatherDesc"):
        arr = obj.get(key) or []
        # wttr.in 偶有形状漂移:列表元素可能不是 dict —— 跳过而不是抛 AttributeError
        if arr and isinstance(arr, list) and isinstance(arr[0], dict):
            val = arr[0].get("value", "")
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def _parse_current(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize ``current_condition[0]`` into a flat dict. Raises KeyError-free."""
    cur = (payload.get("current_condition") or [{}])[0]
    area = (payload.get("nearest_area") or [{}])[0]
    area_name = ((area.get("areaName") or [{}])[0] or {}).get("value", "")
    return {
        "location": area_name,
        "desc": _zh_desc(cur),
        "temp_c": cur.get("temp_C"),
        "feels_like_c": cur.get("FeelsLikeC"),
        "humidity_pct": cur.get("humidity"),
        "wind_kmph": cur.get("windspeedKmph"),
        "wind_dir": cur.get("winddir16Point"),
        "precip_mm": cur.get("precipMM"),
        "visibility_km": cur.get("visibility"),
        "uv_index": cur.get("uvIndex"),
        "observed_at": cur.get("observation_time"),
    }


def _parse_forecast(payload: dict[str, Any], days: int) -> list[dict[str, Any]]:
    """Normalize ``weather[]`` (up to ``days`` entries) into per-day dicts."""
    out: list[dict[str, Any]] = []
    for day in (payload.get("weather") or [])[: max(1, days)]:
        hourly = day.get("hourly") or []
        noon = hourly[_NOON_SLOT] if len(hourly) > _NOON_SLOT else (hourly[0] if hourly else {})
        rain_chances = []
        for h in hourly:
            try:
                rain_chances.append(int(h.get("chanceofrain", 0)))
            except (TypeError, ValueError):
                continue
        astro = (day.get("astronomy") or [{}])[0]
        out.append(
            {
                "date": day.get("date"),
                "min_c": day.get("mintempC"),
                "max_c": day.get("maxtempC"),
                "desc": _zh_desc(noon),
                "chance_of_rain_pct": max(rain_chances) if rain_chances else None,
                "sunrise": astro.get("sunrise"),
                "sunset": astro.get("sunset"),
            }
        )
    return out


# ============ HTTP ============
def _fetch_j1(city: str) -> dict[str, Any]:
    """One rate-limited GET of the j1 payload. Raises on network/parse errors."""
    req = urllib.request.Request(_build_url(city), headers={"User-Agent": _UA})
    _limiter.acquire()
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


# 网络错误 + payload 形状漂移(非 dict 元素 / 缺键 / 类型不符)都走优雅降级 ——
# docstring 承诺 "returns error dict instead of raising",这里是兜底防线
_NET_ERRORS = (
    urllib.error.URLError, json.JSONDecodeError, OSError,
    ValueError, TypeError, AttributeError, KeyError, IndexError,
)


# ============ tools ============
@mcp.tool()
def get_weather(city: str) -> dict[str, Any]:
    """查询一个城市的当前天气(中文城市名可直接用,如 "北京" / "杭州")。

    Args:
        city: City name — Chinese or English both work (wttr.in resolves it).

    Returns:
        Dict with location, Chinese condition text, temperature / feels-like
        (°C), humidity, wind, precipitation, visibility, UV index and the
        observation time. On failure returns ``{"city": ..., "error": ...}``
        instead of raising.
    """
    city = (city or "").strip()
    if not city:
        return {"error": "请提供城市名,例如 北京 / Shanghai"}
    try:
        payload = _fetch_j1(city)
        current = _parse_current(payload)
    except _NET_ERRORS:
        return {"city": city, "error": "天气服务暂时不可用(wttr.in 拉取失败),稍后再试"}
    today = _parse_forecast(payload, 1)
    if today:
        current["today_min_c"] = today[0]["min_c"]
        current["today_max_c"] = today[0]["max_c"]
    current["city"] = city
    return current


@mcp.tool()
def get_forecast(city: str, days: int = 3) -> dict[str, Any]:
    """查询一个城市未来 1–3 天的天气预报(wttr.in 最多提供 3 天)。

    Args:
        city: City name — Chinese or English both work.
        days: Number of days, clamped to 1..3.

    Returns:
        Dict with ``city`` and ``forecast`` — a list of per-day entries
        (date, min/max °C, Chinese condition at noon, max chance of rain,
        sunrise/sunset). On failure returns an ``error`` dict instead of
        raising.
    """
    city = (city or "").strip()
    if not city:
        return {"error": "请提供城市名,例如 北京 / Shanghai"}
    try:
        days = max(1, min(int(days), 3))
    except (TypeError, ValueError):
        days = 3  # 非数字输入回退到 wttr.in 上限
    try:
        payload = _fetch_j1(city)
        forecast = _parse_forecast(payload, days)
    except _NET_ERRORS:
        return {"city": city, "error": "天气服务暂时不可用(wttr.in 拉取失败),稍后再试"}
    return {"city": city, "days": len(forecast), "forecast": forecast}


def main() -> None:
    """Entry point for the weather MCP server (stdio by default; --transport streamable-http for remote access)."""
    run_server(mcp)


if __name__ == "__main__":
    main()

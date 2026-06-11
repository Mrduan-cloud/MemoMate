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

mcp = FastMCP("memomate-weather-cn")

_BASE = "https://wttr.in"
_UA = "memomate-weather-cn/0.1 (+https://github.com/Mrduan-cloud/MemoMate)"
# j1 hourly is 8 slots at 3h steps (00:00..21:00) → index 4 == 12:00 noon,
# the most representative slot for a day's headline description.
_NOON_SLOT = 4


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
    """Condition text: prefer the ``lang_zh`` translation, fall back to English.

    Both fields are wttr.in's ``[{"value": "..."}]`` shape; either may be
    missing or empty, so every access is guarded.
    """
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
    """Entry point for the weather MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()

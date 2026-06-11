"""Tests for weather_cn MCP server.

Pure logic (URL building, Chinese-desc fallback, current/forecast parsing,
rate-limit math) runs by default with a canned wttr.in ``j1`` payload; the
end-to-end paths are exercised by monkeypatching the fetch layer. The live
network test is marked and skipped by default (`pytest -m network`).
"""

from __future__ import annotations

import urllib.error

import pytest

from servers.weather_cn import server as wserver
from servers.weather_cn.server import (
    _build_url,
    _parse_current,
    _parse_forecast,
    _RateLimiter,
    _zh_desc,
    get_forecast,
    get_weather,
)


# Trimmed-but-realistic j1 payload: current condition + nearest area + 3 days,
# each day with the 8-slot (3-hourly) hourly array wttr.in actually returns.
def _hourly(noon_desc_zh: str, rains: list[int]) -> list[dict]:
    slots = []
    for i, rain in enumerate(rains):
        slot = {"chanceofrain": str(rain), "weatherDesc": [{"value": "Cloudy"}]}
        if i == 4:  # 12:00 noon slot
            slot["lang_zh"] = [{"value": noon_desc_zh}]
        slots.append(slot)
    return slots


SAMPLE = {
    "current_condition": [
        {
            "temp_C": "29", "FeelsLikeC": "31", "humidity": "40",
            "windspeedKmph": "11", "winddir16Point": "SSW",
            "precipMM": "0.0", "visibility": "10", "uvIndex": "6",
            "observation_time": "06:24 AM",
            "lang_zh": [{"value": "晴"}], "weatherDesc": [{"value": "Sunny"}],
        }
    ],
    "nearest_area": [{"areaName": [{"value": "Beijing"}]}],
    "weather": [
        {
            "date": "2026-06-11", "mintempC": "19", "maxtempC": "33",
            "astronomy": [{"sunrise": "04:45 AM", "sunset": "07:43 PM"}],
            "hourly": _hourly("晴", [0, 0, 0, 10, 0, 0, 20, 0]),
        },
        {
            "date": "2026-06-12", "mintempC": "20", "maxtempC": "30",
            "astronomy": [{"sunrise": "04:45 AM", "sunset": "07:44 PM"}],
            "hourly": _hourly("小雨", [0, 30, 60, 80, 70, 40, 20, 10]),
        },
        {
            "date": "2026-06-13", "mintempC": "18", "maxtempC": "28",
            "astronomy": [{"sunrise": "04:46 AM", "sunset": "07:44 PM"}],
            "hourly": _hourly("多云", [0, 0, 0, 0, 0, 0, 0, 0]),
        },
    ],
}


# ---------- _build_url ----------
def test_build_url_encodes_chinese_and_params() -> None:
    url = _build_url("北京")
    assert url.startswith("https://wttr.in/")
    assert "format=j1" in url and "lang=zh" in url
    assert "北京" not in url  # percent-encoded
    assert "%E5%8C%97%E4%BA%AC" in url


def test_build_url_strips_whitespace() -> None:
    assert _build_url(" Shanghai ") == _build_url("Shanghai")


# ---------- _zh_desc ----------
def test_zh_desc_prefers_lang_zh() -> None:
    obj = {"lang_zh": [{"value": "晴"}], "weatherDesc": [{"value": "Sunny"}]}
    assert _zh_desc(obj) == "晴"


def test_zh_desc_falls_back_to_english() -> None:
    assert _zh_desc({"weatherDesc": [{"value": "Sunny"}]}) == "Sunny"
    # empty lang_zh value also falls through
    assert _zh_desc({"lang_zh": [{"value": "  "}], "weatherDesc": [{"value": "Rain"}]}) == "Rain"


def test_zh_desc_handles_missing() -> None:
    assert _zh_desc({}) == ""
    assert _zh_desc({"lang_zh": [], "weatherDesc": None}) == ""


# ---------- _parse_current ----------
def test_parse_current_fields() -> None:
    cur = _parse_current(SAMPLE)
    assert cur["location"] == "Beijing"
    assert cur["desc"] == "晴"
    assert cur["temp_c"] == "29" and cur["feels_like_c"] == "31"
    assert cur["humidity_pct"] == "40" and cur["wind_dir"] == "SSW"


def test_parse_current_empty_payload() -> None:
    cur = _parse_current({})
    assert cur["desc"] == "" and cur["temp_c"] is None and cur["location"] == ""


# ---------- _parse_forecast ----------
def test_parse_forecast_noon_desc_and_rain_max() -> None:
    days = _parse_forecast(SAMPLE, 3)
    assert [d["date"] for d in days] == ["2026-06-11", "2026-06-12", "2026-06-13"]
    assert days[0]["desc"] == "晴" and days[0]["chance_of_rain_pct"] == 20
    assert days[1]["desc"] == "小雨" and days[1]["chance_of_rain_pct"] == 80
    assert days[0]["sunrise"] == "04:45 AM" and days[0]["sunset"] == "07:43 PM"


def test_parse_forecast_respects_days() -> None:
    assert len(_parse_forecast(SAMPLE, 1)) == 1
    assert len(_parse_forecast(SAMPLE, 2)) == 2
    # asking beyond available days returns what exists
    assert len(_parse_forecast(SAMPLE, 3)) == 3


def test_parse_forecast_short_hourly_guard() -> None:
    payload = {"weather": [{"date": "2026-06-11", "mintempC": "1", "maxtempC": "2",
                            "hourly": [{"lang_zh": [{"value": "雪"}], "chanceofrain": "5"}]}]}
    days = _parse_forecast(payload, 3)
    assert days[0]["desc"] == "雪"  # falls back to hourly[0] when <5 slots
    assert days[0]["chance_of_rain_pct"] == 5


def test_parse_forecast_empty() -> None:
    assert _parse_forecast({}, 3) == []


# ---------- _RateLimiter (pure math) ----------
def test_rate_limiter_math() -> None:
    rl = _RateLimiter(1.0)
    assert rl.wait_seconds(100.0) == 0.0
    rl._last = 100.0
    assert rl.wait_seconds(100.4) == pytest.approx(0.6)
    assert rl.wait_seconds(101.5) == 0.0


# ---------- tools end-to-end with mocked fetch (offline) ----------
def test_get_weather_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wserver, "_fetch_j1", lambda city: SAMPLE)
    out = get_weather("北京")
    assert out["city"] == "北京" and out["desc"] == "晴"
    assert out["today_min_c"] == "19" and out["today_max_c"] == "33"
    assert "error" not in out


def test_get_forecast_happy_path_and_clamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wserver, "_fetch_j1", lambda city: SAMPLE)
    out = get_forecast("北京", days=99)  # clamps to 3
    assert out["days"] == 3 and len(out["forecast"]) == 3
    out1 = get_forecast("北京", days=0)  # clamps to 1
    assert out1["days"] == 1


def test_tools_degrade_gracefully_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(city: str) -> dict:
        raise urllib.error.URLError("down")

    monkeypatch.setattr(wserver, "_fetch_j1", boom)
    assert "error" in get_weather("北京")
    assert "error" in get_forecast("北京")


def test_tools_reject_blank_city() -> None:
    assert "error" in get_weather("  ")
    assert "error" in get_forecast("")


# ---------- live (network) ----------
@pytest.mark.network
def test_get_weather_live() -> None:
    """Live integration — requires network to wttr.in (may be throttled)."""
    out = get_weather("北京")
    # graceful contract: either parsed weather or an error dict; never raises
    assert isinstance(out, dict)
    assert ("temp_c" in out) or ("error" in out)

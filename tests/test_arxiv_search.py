"""Tests for the arxiv_search MCP server.

Covers two offline-testable surfaces:
1. Query parsing  — `_build_url` turns (query, max_results, sort_by) into a URL
2. Atom parsing   — `_parse` turns arXiv's Atom XML into structured dicts

Plus `search_arxiv` orchestration (param clamping / sort whitelist) with the
network call monkey-patched out, and one live `@pytest.mark.network` test
(deselected by default; run with `pytest -m network`).
"""

from __future__ import annotations

import urllib.parse

import pytest

from servers.arxiv_search.server import (
    _build_url,
    _parse,
    search_arxiv,
)


# =========================================================================
# Helpers
# =========================================================================
def _query_params(url: str) -> dict[str, list[str]]:
    """Pull the query-string params out of a built URL for assertions."""
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)


# Minimal but realistic Atom feed with two entries; second entry deliberately
# omits optional fields (summary, authors) and uses an id without `/abs/`.
SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2310.06825v1</id>
    <title>  ReAct: Synergizing  Reasoning
       and Acting in Language Models </title>
    <summary>  We explore the use of LLMs to generate
       reasoning traces and task-specific actions.  </summary>
    <published>2023-10-10T17:59:00Z</published>
    <author><name>Shunyu Yao</name></author>
    <author><name>Jeffrey Zhao</name></author>
    <author><name>Dian Yu</name></author>
  </entry>
  <entry>
    <id>2401.00001v2</id>
    <title>Minimal Entry</title>
    <published>2024-01-01T00:00:00Z</published>
  </entry>
</feed>
"""

EMPTY_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>ArXiv Query: no results</title>
</feed>
"""


# =========================================================================
# Query parsing — _build_url
# =========================================================================
def test_build_url_includes_all_params():
    url = _build_url("agent", 5, "relevance")
    params = _query_params(url)
    assert params["search_query"] == ["agent"]
    assert params["max_results"] == ["5"]
    assert params["sortBy"] == ["relevance"]
    assert params["sortOrder"] == ["descending"]


def test_build_url_points_at_arxiv_api():
    url = _build_url("agent", 5, "relevance")
    assert url.startswith("https://export.arxiv.org/api/query?")


def test_build_url_uses_https():
    """Query + results must travel encrypted (privacy + MITM resistance)."""
    assert _build_url("agent", 5, "relevance").startswith("https://")


def test_build_url_passes_field_prefixes_through_verbatim():
    """arXiv field-prefix syntax must survive URL-encoding intact."""
    url = _build_url("ti:agent AND cat:cs.AI", 10, "submittedDate")
    params = _query_params(url)
    # parse_qs decodes percent-encoding, so we get the original string back
    assert params["search_query"] == ["ti:agent AND cat:cs.AI"]


def test_build_url_encodes_special_characters():
    """Spaces, colons and ampersands must be percent-encoded in the raw URL."""
    url = _build_url("au:Yann LeCun & friends", 3, "relevance")
    # The raw URL must not contain a literal space or a bare '&' inside the value
    raw_value = url.split("search_query=")[1].split("&")[0]
    assert " " not in raw_value
    assert "%20" in raw_value or "+" in raw_value
    # round-trips back to the original
    assert _query_params(url)["search_query"] == ["au:Yann LeCun & friends"]


def test_build_url_sort_order_is_always_descending():
    for sort_by in ("relevance", "lastUpdatedDate", "submittedDate"):
        params = _query_params(_build_url("x", 1, sort_by))
        assert params["sortOrder"] == ["descending"]


def test_build_url_max_results_is_stringified():
    params = _query_params(_build_url("x", 30, "relevance"))
    assert params["max_results"] == ["30"]


# =========================================================================
# Atom parsing — _parse
# =========================================================================
def test_parse_extracts_full_entry():
    results = _parse(SAMPLE_ATOM)
    first = results[0]
    assert first["id"] == "2310.06825v1"
    assert first["url"] == "https://arxiv.org/abs/2310.06825v1"
    assert first["pdf_url"] == "https://arxiv.org/pdf/2310.06825v1"
    assert first["published"] == "2023-10-10T17:59:00Z"


def test_parse_normalizes_whitespace_in_title_and_summary():
    """Multi-line / multi-space title+summary should collapse to single spaces."""
    first = _parse(SAMPLE_ATOM)[0]
    assert first["title"] == "ReAct: Synergizing Reasoning and Acting in Language Models"
    assert "  " not in first["title"]
    assert first["summary"].startswith("We explore the use of LLMs")
    assert "  " not in first["summary"]


def test_parse_collects_multiple_authors_in_order():
    first = _parse(SAMPLE_ATOM)[0]
    assert first["authors"] == ["Shunyu Yao", "Jeffrey Zhao", "Dian Yu"]


def test_parse_handles_missing_optional_fields():
    """Second entry has no summary and no authors — must not crash."""
    second = _parse(SAMPLE_ATOM)[1]
    assert second["id"] == "2401.00001v2"
    assert second["summary"] == ""
    assert second["authors"] == []
    assert second["title"] == "Minimal Entry"


def test_parse_id_without_abs_prefix_is_used_as_is():
    """An id that isn't a full /abs/ URL should still produce a usable id+url."""
    second = _parse(SAMPLE_ATOM)[1]
    assert second["id"] == "2401.00001v2"
    assert second["url"] == "https://arxiv.org/abs/2401.00001v2"


def test_parse_empty_feed_returns_empty_list():
    assert _parse(EMPTY_ATOM) == []


def test_parse_raises_on_malformed_xml():
    """Garbage / non-XML input should raise ParseError (caught upstream)."""
    import xml.etree.ElementTree as ET

    with pytest.raises(ET.ParseError):
        _parse("<html><body>429 Too Many Requests</body>")  # truncated / not a feed


def test_parse_returns_one_dict_per_entry():
    results = _parse(SAMPLE_ATOM)
    assert len(results) == 2
    expected_keys = {"id", "title", "authors", "summary", "published", "url", "pdf_url"}
    for r in results:
        assert set(r.keys()) == expected_keys


# =========================================================================
# search_arxiv orchestration — network monkey-patched out
# =========================================================================
@pytest.fixture
def patch_fetch(monkeypatch):
    """Replace _fetch with a stub that records its args and returns SAMPLE_ATOM."""
    calls: dict[str, object] = {}

    def _stub(query: str, max_results: int, sort_by: str) -> str:
        calls["query"] = query
        calls["max_results"] = max_results
        calls["sort_by"] = sort_by
        return SAMPLE_ATOM

    monkeypatch.setattr("servers.arxiv_search.server._fetch", _stub, raising=True)
    return calls


def test_search_arxiv_returns_parsed_results(patch_fetch):
    results = search_arxiv("agent")
    assert len(results) == 2
    assert results[0]["id"] == "2310.06825v1"


def test_search_arxiv_clamps_max_results_upper_bound(patch_fetch):
    search_arxiv("agent", max_results=999)
    assert patch_fetch["max_results"] == 30


def test_search_arxiv_clamps_max_results_lower_bound(patch_fetch):
    search_arxiv("agent", max_results=0)
    assert patch_fetch["max_results"] == 1


def test_search_arxiv_negative_max_results_clamped_to_one(patch_fetch):
    search_arxiv("agent", max_results=-5)
    assert patch_fetch["max_results"] == 1


def test_search_arxiv_invalid_sort_falls_back_to_relevance(patch_fetch):
    search_arxiv("agent", sort_by="bogus")
    assert patch_fetch["sort_by"] == "relevance"


def test_search_arxiv_valid_sort_is_preserved(patch_fetch):
    search_arxiv("agent", sort_by="submittedDate")
    assert patch_fetch["sort_by"] == "submittedDate"


def test_search_arxiv_returns_empty_on_malformed_response(monkeypatch):
    """If arXiv returns a non-XML / truncated body, don't crash — return []."""
    def _garbage(query: str, max_results: int, sort_by: str) -> str:
        # Unbalanced tags → ET.fromstring raises ParseError (the catch path).
        return "<html><body>429 Too Many Requests"

    monkeypatch.setattr("servers.arxiv_search.server._fetch", _garbage, raising=True)
    # Must not raise — caller gets an empty list instead of a ParseError.
    assert search_arxiv("agent") == []


def test_search_arxiv_returns_empty_on_non_atom_xml(monkeypatch):
    """Well-formed but non-Atom XML (no <entry>) yields an empty result set."""
    def _non_atom(query: str, max_results: int, sort_by: str) -> str:
        return "<html><body>maintenance</body></html>"

    monkeypatch.setattr("servers.arxiv_search.server._fetch", _non_atom, raising=True)
    assert search_arxiv("agent") == []


# =========================================================================
# Live integration (deselected by default)
# =========================================================================
@pytest.mark.network
def test_search_arxiv_live():
    """Live integration test — requires network access to export.arxiv.org.

    arXiv aggressively rate-limits (HTTP 429). A throttle means "couldn't
    verify", not "code is broken", so we skip rather than fail on 429.
    """
    import urllib.error

    try:
        results = search_arxiv("ti:transformer", max_results=3)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            pytest.skip("arXiv rate-limited this run (HTTP 429) — retry later")
        raise

    assert isinstance(results, list)
    assert len(results) >= 1
    first = results[0]
    assert first["id"]
    assert first["title"]
    assert first["url"].startswith("https://arxiv.org/abs/")
    assert first["pdf_url"].startswith("https://arxiv.org/pdf/")

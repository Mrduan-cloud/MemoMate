"""MCP server for searching arXiv papers via the public Atom API.

Zero external dependencies: uses only the Python standard library for HTTP and XML.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("memomate-arxiv-search")

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
_ALLOWED_SORT = {"relevance", "lastUpdatedDate", "submittedDate"}


def _build_url(query: str, max_results: int, sort_by: str) -> str:
    """Build the arXiv API query URL.

    Pure function (no I/O) so the query-construction logic can be unit-tested
    offline. The user query string is passed through verbatim — arXiv's own
    syntax (field prefixes ``ti:`` / ``au:`` / ``abs:`` / ``cat:`` and boolean
    ``AND`` / ``OR`` / ``ANDNOT``) is handled server-side by arXiv, we only
    URL-encode it safely.
    """
    params = {
        "search_query": query,
        "max_results": str(max_results),
        "sortBy": sort_by,
        "sortOrder": "descending",
    }
    return f"{ARXIV_API}?{urllib.parse.urlencode(params)}"


def _fetch(query: str, max_results: int, sort_by: str) -> str:
    url = _build_url(query, max_results, sort_by)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MemoMate/0.1 (https://github.com/Mrduan-cloud/MemoMate)"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8")


def _parse(atom_xml: str) -> list[dict[str, Any]]:
    root = ET.fromstring(atom_xml)
    out: list[dict[str, Any]] = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        raw_id = (entry.findtext(f"{ATOM_NS}id") or "").strip()
        arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id
        title = " ".join((entry.findtext(f"{ATOM_NS}title") or "").split())
        summary = " ".join((entry.findtext(f"{ATOM_NS}summary") or "").split())
        published = entry.findtext(f"{ATOM_NS}published") or ""
        authors = [
            (a.findtext(f"{ATOM_NS}name") or "").strip()
            for a in entry.findall(f"{ATOM_NS}author")
        ]
        out.append(
            {
                "id": arxiv_id,
                "title": title,
                "authors": authors,
                "summary": summary,
                "published": published,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            }
        )
    return out


@mcp.tool()
def search_arxiv(
    query: str,
    max_results: int = 5,
    sort_by: str = "relevance",
) -> list[dict[str, Any]]:
    """Search arXiv papers via the public API.

    Args:
        query: Search query. Supports field prefixes:
               `ti:` (title), `au:` (author), `abs:` (abstract), `cat:` (category).
               Example: `ti:agent AND cat:cs.AI`.
        max_results: Number of results to return (clamped to 1..30).
        sort_by: One of 'relevance', 'lastUpdatedDate', 'submittedDate'.
    """
    max_results = max(1, min(int(max_results), 30))
    if sort_by not in _ALLOWED_SORT:
        sort_by = "relevance"
    atom_xml = _fetch(query, max_results, sort_by)
    return _parse(atom_xml)


def main() -> None:
    """Entry point for the arXiv search MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()

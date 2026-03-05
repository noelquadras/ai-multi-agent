"""
Web search tool for agents.

Provides web search capability using DuckDuckGo (no API key required).
Falls back to a stub if the duckduckgo-search package is not installed.

Inspired by MetaGPT's SearchEngine tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    """Single web search result."""
    title: str = ""
    url: str = ""
    snippet: str = ""


@dataclass
class SearchResponse:
    """Response from a web search query."""
    success: bool = True
    results: list[SearchResult] = field(default_factory=list)
    error: str = ""


def search_web(
    query: str,
    num_results: int = 5,
) -> SearchResponse:
    """
    Search the web using DuckDuckGo.
    
    Args:
        query: Search query string
        num_results: Maximum number of results to return
    
    Returns:
        SearchResponse with list of results or error.
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return SearchResponse(
            success=False,
            error="duckduckgo-search package not installed. "
                  "Install with: pip install duckduckgo-search"
        )

    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=num_results))

        results = []
        for r in raw_results:
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("href", r.get("link", "")),
                snippet=r.get("body", r.get("snippet", "")),
            ))

        return SearchResponse(success=True, results=results)

    except Exception as e:
        return SearchResponse(success=False, error=f"Search error: {e}")


def search_and_summarize(
    query: str,
    num_results: int = 3,
) -> str:
    """
    Search the web and return a formatted text summary.
    
    Convenience function that returns a plain text string
    suitable for including in an LLM prompt.
    
    Args:
        query: Search query string
        num_results: Maximum number of results
    
    Returns:
        Formatted text string with search results.
    """
    response = search_web(query, num_results)

    if not response.success:
        return f"Search failed: {response.error}"

    if not response.results:
        return f"No results found for: {query}"

    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(response.results, 1):
        lines.append(f"{i}. {r.title}")
        lines.append(f"   URL: {r.url}")
        lines.append(f"   {r.snippet}")
        lines.append("")

    return "\n".join(lines)

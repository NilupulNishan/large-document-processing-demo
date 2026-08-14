"""Tavily boundary. SDK types stop here; callers receive plain dicts."""

import logging
from functools import cache

from app.config import TAVILY_API_KEY, WEB_DOMAINS, WEB_RESULTS

logger = logging.getLogger(__name__)


@cache
def _client():
    if not TAVILY_API_KEY:
        raise RuntimeError("Missing in backend/.env: TAVILY_API_KEY")

    from tavily import TavilyClient

    return TavilyClient(api_key=TAVILY_API_KEY)


def search(query: str, max_results: int = WEB_RESULTS) -> list[dict]:
    """Search the web. Returns title, url and content per result, ranked by Tavily."""
    # basic, not advanced: measured on this corpus advanced doubled the content but also the
    # latency (2.1 s -> 4.8 s) for two credits instead of one. See build-log Slice 8.
    response = _client().search(
        query=query,
        max_results=max_results,
        search_depth="basic",
        # A parameter, never a site: operator pasted into the query — Tavily treats those as
        # ordinary words, which is what made the previous build's web search useless.
        include_domains=list(WEB_DOMAINS) or None,
    )

    results = [
        {"title": r["title"], "url": r["url"], "content": r["content"]}
        for r in response["results"]
    ]

    # A restriction that matches nothing returns an empty list rather than an error, so a
    # typo in WEB_DOMAINS would silently disable web search forever. Say so.
    if WEB_DOMAINS and not results:
        logger.warning("no results within WEB_DOMAINS=%s for %r", list(WEB_DOMAINS), query)

    return results

from __future__ import annotations

"""Search client wrapper for DuckDuckGo web and news retrieval."""

import logging
import time
from typing import Iterable

from ddgs import DDGS

from config import settings
from agent.types import SearchResult

logger = logging.getLogger(__name__)


class SearchClient:
    """DuckDuckGo search wrapper with retry handling and URL deduplication."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    @staticmethod
    def _extract_url(item: dict[str, str]) -> str:
        return item.get("href", item.get("url", item.get("link", "")))

    def search_web(self, queries: Iterable[str], max_results: int | None = None) -> list[SearchResult]:
        limit = settings.SEARCH_RESULTS if max_results is None else max_results
        return self._search(queries, limit, "web")

    def search_news(self, queries: Iterable[str], max_results: int | None = None) -> list[SearchResult]:
        limit = settings.NEWS_RESULTS if max_results is None else max_results
        return self._search(queries, limit, "news")

    def _search(self, queries: Iterable[str], max_results: int, mode: str) -> list[SearchResult]:
        """Execute DuckDuckGo queries with retry and deduplication safeguards."""

        results: list[SearchResult] = []
        for query in queries:
            for attempt in range(3):
                try:
                    ddgs = DDGS()
                    if mode == "news":
                        items = ddgs.news(query, max_results=max_results, safesearch="off")
                    else:
                        items = ddgs.text(query, max_results=max_results, safesearch="off")
                    for item in items:
                        url = self._extract_url(item)
                        if not url or url in self._seen:
                            continue
                        self._seen.add(url)
                        results.append(
                            SearchResult(
                                title=item.get("title", ""),
                                url=url,
                                snippet=item.get("body", ""),
                                source=query,
                            )
                        )
                    break
                except Exception as exc:
                    if attempt == 2:
                        logger.warning("Search failed for query '%s': %s", query, exc)
                    else:
                        # Linear backoff helps absorb transient upstream errors.
                        time.sleep(1 + attempt)
        return results

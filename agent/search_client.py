from __future__ import annotations

import logging
import time
from typing import Iterable

from ddgs import DDGS

from config import settings
from agent.types import SearchResult

logger = logging.getLogger(__name__)


class SearchClient:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def search_web(self, queries: Iterable[str]) -> list[SearchResult]:
        return self._search(queries, settings.SEARCH_RESULTS, "web")

    def search_news(self, queries: Iterable[str]) -> list[SearchResult]:
        return self._search(queries, settings.NEWS_RESULTS, "news")

    def _search(self, queries: Iterable[str], max_results: int, mode: str) -> list[SearchResult]:
        results: list[SearchResult] = []
        for query in queries:
            for attempt in range(3):
                try:
                    ddgs = DDGS()
                    items = ddgs.news(query, max_results=max_results, safesearch="off") if mode == "news" else ddgs.text(query, max_results=max_results, safesearch="off")
                    for item in items:
                        url = item.get("href", item.get("url", item.get("link", "")))
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
                        time.sleep(1 + attempt)
        return results

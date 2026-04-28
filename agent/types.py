from dataclasses import dataclass


@dataclass
class SearchResult:
    """Single search result item gathered from web/news search."""

    title: str
    url: str
    snippet: str
    source: str = ""


@dataclass
class ScrapedPage:
    """Normalized page content extracted from a crawled URL."""

    url: str
    title: str
    text: str
    success: bool = True
    error: str = ""

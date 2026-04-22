from dataclasses import dataclass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""


@dataclass
class ScrapedPage:
    url: str
    title: str
    text: str
    success: bool = True
    error: str = ""

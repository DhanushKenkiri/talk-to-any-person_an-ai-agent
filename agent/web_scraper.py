from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from config import settings
from agent.types import ScrapedPage

SKIP_DOMAINS = {"facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com"}
SKIP_EXTENSIONS = {".pdf", ".jpg", ".png", ".gif", ".mp4", ".zip", ".doc", ".docx"}


class WebScraper:
    def __init__(self) -> None:
        self.headers = {
            "User-Agent": settings.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    def scrape(self, urls: list[str]) -> list[ScrapedPage]:
        if not urls:
            return []
        return asyncio.run(self._scrape_many(urls))

    async def _scrape_many(self, urls: list[str]) -> list[ScrapedPage]:
        timeout = httpx.Timeout(settings.REQUEST_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=self.headers) as client:
            tasks = [self._scrape_one(client, url) for url in urls]
            raw = await asyncio.gather(*tasks, return_exceptions=True)
        return [item for item in raw if isinstance(item, ScrapedPage)]

    async def _scrape_one(self, client: httpx.AsyncClient, url: str) -> ScrapedPage:
        low = url.lower()
        if any(d in low for d in SKIP_DOMAINS):
            return ScrapedPage(url=url, title="", text="", success=False, error="Skipped domain")
        if any(low.endswith(ext) for ext in SKIP_EXTENSIONS):
            return ScrapedPage(url=url, title="", text="", success=False, error="Skipped extension")

        try:
            resp = await client.get(url)
        except Exception as exc:
            return ScrapedPage(url=url, title="", text="", success=False, error=str(exc))

        if resp.status_code != 200:
            return ScrapedPage(url=url, title="", text="", success=False, error=f"HTTP {resp.status_code}")

        if "html" not in resp.headers.get("content-type", ""):
            return ScrapedPage(url=url, title="", text="", success=False, error="Non-HTML")

        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "form", "iframe"]):
            tag.decompose()

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True)[:200] if title_tag else ""
        body = soup.find("main") or soup.find("article") or soup.find("body") or soup
        text = body.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        if len(text) > 4200:
            text = text[:4200] + "\n...[truncated]"

        if not text:
            return ScrapedPage(url=url, title=title, text="", success=False, error="Empty content")
        return ScrapedPage(url=url, title=title, text=text, success=True)

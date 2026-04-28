from __future__ import annotations

"""Research orchestration for evidence collection and ranking."""

import re
from urllib.parse import urlparse

from config import settings
from agent.llm_client import build_responder, build_summarizer
from agent.search_client import SearchClient
from agent.types import ScrapedPage, SearchResult
from agent.web_scraper import WebScraper

LOW_TRUST_DOMAINS = {
    "facebook.com",
    "pinterest.com",
    "instagram.com",
    "sociumin.com",
    "stackexchange.com",
    "stackoverflow.com",
    "ok.ru",
}

BLOCKLIST_DOMAINS = {
    "facebook.com",
    "pinterest.com",
    "instagram.com",
    "sociumin.com",
    "stackexchange.com",
    "stackoverflow.com",
    "imdb.com",
    "oneeyeland.com",
    "namebday.com",
    "exaly.com",
}

HIGH_TRUST_HINTS = {
    "linkedin.com",
    "github.com",
    "masumi",
    "youtube.com",
    "medium.com",
    "substack.com",
}


class ResearchAPersonService:
    """Coordinates search, scraping, ranking, and response generation components."""

    def __init__(self) -> None:
        self.search = SearchClient()
        self.scraper = WebScraper()
        self.summarizer = build_summarizer()
        self.responder = build_responder()

    @staticmethod
    def _domain_from_url(url: str) -> str:
        try:
            return urlparse(url).netloc.lower().replace("www.", "")
        except Exception:
            return ""

    def gather_evidence(
        self,
        name: str,
        company: str = "",
        socials: str = "",
        extra_queries: list[str] | None = None,
        deep_research: bool = False,
    ) -> tuple[list[SearchResult], list[ScrapedPage]]:
        queries, news_queries = self._build_queries(name, company, socials, extra_queries or [], deep_research)
        web_limit = min(settings.SEARCH_RESULTS + (6 if deep_research else 0), 30)
        news_limit = min(settings.NEWS_RESULTS + (4 if deep_research else 0), 18)
        results = self.search.search_web(queries, max_results=web_limit) + self.search.search_news(news_queries, max_results=news_limit)
        results = self._dedupe(results)
        results = self._drop_blocklisted_domains(results)
        ranked = self._rank_results(name, company, socials, results)
        ranked = self._enforce_single_identity(name, company, socials, ranked)
        scrape_limit = min(settings.SCRAPE_LIMIT + (8 if deep_research else 0), 32)
        urls = self._pick_urls(ranked)[: scrape_limit]
        scraped = self.scraper.scrape(urls)
        return ranked, scraped

    def run_report(self, name: str, company: str = "", socials: str = "") -> str:
        ranked, scraped = self.gather_evidence(name, company, socials)
        return self.summarizer.summarize(name, company, socials, ranked, scraped)

    def answer_query(
        self,
        name: str,
        company: str,
        socials: str,
        query: str,
        extra_queries: list[str] | None = None,
        deep_research: bool = False,
        hitl_notes: str = "",
    ) -> str:
        ranked, scraped = self.gather_evidence(name, company, socials, extra_queries, deep_research)
        return self.responder.answer(name, company, socials, query, ranked, scraped, hitl_notes=hitl_notes)

    def _drop_blocklisted_domains(self, items: list[SearchResult]) -> list[SearchResult]:
        out: list[SearchResult] = []
        for item in items:
            domain = self._domain_from_url(item.url)
            if any(domain.endswith(bad) for bad in BLOCKLIST_DOMAINS):
                continue
            out.append(item)
        return out

    def _build_queries(
        self,
        name: str,
        company: str,
        socials: str,
        extra_queries: list[str],
        deep_research: bool,
    ) -> tuple[list[str], list[str]]:
        base = f'"{name}"'
        queries = [
            base,
            f"{base} profile",
            f"{base} biography",
            f"{base} work experience",
        ]
        if company:
            queries.extend(
                [
                    f'{base} "{company}"',
                    f"{base} {company} linkedin",
                ]
            )

        first_social = self._first_social(socials)
        if first_social:
            queries.append(f"{base} {first_social}")

        if deep_research:
            queries.extend(
                [
                    f"{base} publications",
                    f"{base} research profile",
                    f"{base} Google Scholar",
                    f"site:scholar.google.com {base}",
                    f"{base} arXiv",
                    f"site:arxiv.org {base}",
                ]
            )

        for q in extra_queries:
            if q and q not in queries:
                queries.append(q)

        news = [
            f"{name} news",
            f"{name} interview",
            f"{name} podcast",
            f"{name} conference",
        ]
        if deep_research:
            news.append(f"{name} keynote")
            news.append(f"{name} publication")

        max_queries = 12 if deep_research else 8
        max_news = 6 if deep_research else 4
        return queries[:max_queries], news[:max_news]

    def _first_social(self, socials: str) -> str:
        if not socials:
            return ""
        return socials.split(",")[0].strip()

    def _tokenize(self, value: str) -> list[str]:
        return [part for part in re.split(r"[^a-z0-9]+", value.lower()) if part]

    def _identity_terms(self, name: str, company: str, socials: str) -> set[str]:
        terms = set(self._tokenize(name))
        if company:
            terms.update(self._tokenize(company))
        for item in socials.split(","):
            item = item.strip().lower()
            if not item:
                continue
            terms.update(self._tokenize(item))
        return {t for t in terms if len(t) > 2}

    def _context_terms(self, company: str, socials: str) -> set[str]:
        terms: set[str] = set()
        if company:
            terms.update(self._tokenize(company))

        for raw in socials.split(","):
            value = raw.strip().lower()
            if not value:
                continue
            terms.update(self._tokenize(value))
            if "/in/" in value:
                handle = value.split("/in/")[-1].strip("/")
                if handle:
                    terms.update(self._tokenize(handle))

        return {t for t in terms if len(t) > 2}

    def _is_strict_identity_match(self, result: SearchResult, name_tokens: list[str], context_terms: set[str]) -> bool:
        hay = f"{result.title} {result.snippet} {result.url}".lower()
        domain = self._domain_from_url(result.url)

        has_name = all(token in hay for token in name_tokens[:2]) if len(name_tokens) >= 2 else bool(name_tokens and name_tokens[0] in hay)
        if not has_name:
            return False

        has_context = any(term in hay for term in context_terms)
        trusted_profile_domain = any(x in domain for x in HIGH_TRUST_HINTS)
        return has_context or trusted_profile_domain

    def _is_loose_identity_match(self, result: SearchResult, name_tokens: list[str]) -> bool:
        hay = f"{result.title} {result.snippet} {result.url}".lower()
        if len(name_tokens) >= 2:
            return name_tokens[0] in hay and name_tokens[-1] in hay
        return bool(name_tokens and name_tokens[0] in hay)

    def _enforce_single_identity(self, name: str, company: str, socials: str, items: list[SearchResult]) -> list[SearchResult]:
        if not items:
            return items

        name_tokens = [t for t in self._tokenize(name) if len(t) > 2]
        # Some valid names can be very short (for example "Li"); in that case,
        # keep ranked items instead of filtering everything out.
        if not name_tokens:
            return items[: max(10, settings.SCRAPE_LIMIT * 2)]
        context_terms = self._context_terms(company, socials)

        strict = [item for item in items if self._is_strict_identity_match(item, name_tokens, context_terms)]
        if len(strict) >= 8:
            return strict

        loose = [item for item in items if item not in strict and self._is_loose_identity_match(item, name_tokens)]
        merged = strict + loose
        return merged[: max(10, settings.SCRAPE_LIMIT * 2)]

    def _score_result(self, result: SearchResult, full_name: str, terms: set[str]) -> int:
        hay = f"{result.title} {result.snippet} {result.url}".lower()
        domain = self._domain_from_url(result.url)
        score = 0

        if full_name.lower() in hay:
            score += 8

        name_parts = [p for p in self._tokenize(full_name) if len(p) > 2]
        for part in name_parts:
            if part in hay:
                score += 2

        for term in terms:
            if term in hay:
                score += 1

        # Mild quality preference for profile and editorial pages.
        if any(x in hay for x in ["linkedin", "about", "bio", "profile", "interview", "speaker"]):
            score += 1

        if any(hint in domain for hint in HIGH_TRUST_HINTS):
            score += 2

        if any(domain.endswith(bad) for bad in LOW_TRUST_DOMAINS):
            score -= 3

        if "researchgate.net" in domain and "masumi" not in hay:
            score -= 2

        return score

    def _rank_results(self, name: str, company: str, socials: str, items: list[SearchResult]) -> list[SearchResult]:
        if not items:
            return items

        terms = self._identity_terms(name, company, socials)
        scored = [(self._score_result(item, name, terms), idx, item) for idx, item in enumerate(items)]

        # Keep likely matching evidence first, but still retain some long-tail results.
        strong = [row for row in scored if row[0] >= 8]
        medium = [row for row in scored if 4 <= row[0] < 8]
        weak = [row for row in scored if row[0] < 4]

        strong.sort(key=lambda x: (-x[0], x[1]))
        medium.sort(key=lambda x: (-x[0], x[1]))

        ranked = [row[2] for row in strong]
        ranked.extend([row[2] for row in medium])

        # Guardrail: if we already have enough likely matches, drop weak matches
        # to reduce same-name contamination from other people.
        if len(ranked) >= 8:
            return ranked

        fallback_weak = [row for row in weak if row[0] >= 0]
        ranked.extend([row[2] for row in fallback_weak[: max(4, settings.SEARCH_RESULTS // 3)]])
        return ranked

    def _dedupe(self, items: list[SearchResult]) -> list[SearchResult]:
        seen = set()
        out: list[SearchResult] = []
        for item in items:
            if item.url in seen:
                continue
            seen.add(item.url)
            out.append(item)
        return out

    def _pick_urls(self, results: list[SearchResult]) -> list[str]:
        urls: list[str] = []
        seen_domains: set[str] = set()
        for item in results:
            domain = self._domain_from_url(item.url)
            if domain and domain in seen_domains:
                continue
            if domain:
                seen_domains.add(domain)
            urls.append(item.url)
        return urls

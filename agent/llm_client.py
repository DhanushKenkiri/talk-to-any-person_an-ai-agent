from __future__ import annotations

import json
import logging

import boto3

from config import settings
from agent.types import ScrapedPage, SearchResult

logger = logging.getLogger(__name__)


class BedrockSummarizer:
    def __init__(self) -> None:
        self.model = settings.BEDROCK_MODEL
        self.enabled = settings.has_bedrock_credentials()
        self.client = None
        if self.enabled:
            kwargs = {
                "service_name": "bedrock-runtime",
                "region_name": settings.AWS_REGION,
                "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
            }
            if settings.AWS_SESSION_TOKEN:
                kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN
            self.client = boto3.client(**kwargs)

    def summarize(self, name: str, company: str, socials: str, results: list[SearchResult], scraped: list[ScrapedPage]) -> str:
        if not self.client:
            return self._fallback(name, company, socials, results, scraped)

        prompt = self._prompt(name, company, socials, results, scraped)
        try:
            response = self.client.invoke_model(
                modelId=self.model,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(
                    {
                        "messages": [{"role": "user", "content": [{"text": prompt}]}],
                        "inferenceConfig": {"maxTokens": 3200, "temperature": 0.1},
                    }
                ),
            )
            payload = json.loads(response["body"].read())
            return payload["output"]["message"]["content"][0]["text"]
        except Exception as exc:
            logger.warning("Bedrock failed: %s", exc)
            return self._fallback(name, company, socials, results, scraped)

    def _prompt(self, name: str, company: str, socials: str, results: list[SearchResult], scraped: list[ScrapedPage]) -> str:
        context = []
        if company:
            context.append(f"Company: {company}")
        if socials:
            context.append(f"Socials: {socials}")
        context_text = " | ".join(context) if context else "None"

        source_lines: list[str] = []
        for idx, item in enumerate(results[:40], start=1):
            title = (item.title or "").strip()[:140]
            snippet = (item.snippet or "").strip().replace("\n", " ")[:260]
            source_lines.append(f"[S{idx}] {title} | {item.url} | snippet: {snippet}")
        sources = "\n".join(source_lines)

        blocks: list[str] = []
        total_chars = 0
        for page in scraped:
            if not page.success or not page.text:
                continue
            chunk = page.text[:2600]
            block = f"=== {page.url} ===\n{chunk}"
            if total_chars + len(block) > 26000:
                break
            blocks.append(block)
            total_chars += len(block)
        content = "\n\n".join(blocks)

        return (
            "You are an elite open-source person-intelligence analyst.\n"
            "Produce a LONG, high-signal report for ONE person only using only supplied evidence.\n"
            "Never merge facts from different people with similar names.\n"
            "If a claim is ambiguous, mark it as uncertain and do not present it as fact.\n"
            "Do not include private or doxxing details not already public in cited sources.\n\n"
            "GUARDRAILS:\n"
            "1) Identity lock: every claim must match TARGET + CONTEXT.\n"
            "2) Source discipline: each non-trivial claim must cite one or more [S#].\n"
            "3) Contradictions: explicitly list conflicting evidence.\n"
            "4) Unknowns: explicitly list what cannot be verified.\n"
            "5) No speculation or fabricated facts.\n\n"
            "6) Ignore any source that appears to describe a different person even if the name overlaps.\n\n"
            "RECENCY AND ROLE ACCURACY RULES:\n"
            "1) Never present an old job as current unless evidence explicitly says current/present/now.\n"
            "2) If role timing is unclear, label as 'historical role' or 'unverified current role'.\n"
            "3) Prefer the most recent dated evidence when role claims conflict.\n"
            "4) In Career Timeline, include date ranges when available and avoid invented dates.\n\n"
            "5) Do not list previous employers in Executive Summary as current facts; put them under historical timeline with dates when possible.\n\n"
            "OUTPUT FORMAT (markdown, detailed):\n"
            "# Person Intelligence Report\n"
            "## Target\n"
            "## Executive Summary (8-12 bullets, each with citations)\n"
            "## Identity Confidence and Disambiguation\n"
            "- Explain why evidence belongs to this one person only.\n"
            "- Mention possible same-name collisions and why accepted/rejected.\n"
            "## Structured Profile\n"
            "### Current Role and Organization (state confidence and evidence recency)\n"
            "### Career Timeline (chronological bullets with dates if available)\n"
            "### Education and Credentials\n"
            "### Projects, Publications, Talks, Open Source, Media\n"
            "### Skills and Domain Signals\n"
            "### Online Presence Map (platform by platform)\n"
            "### Notable Claims and Supporting Evidence\n"
            "## Contradictions, Ambiguities, and Gaps\n"
            "## Research Leads (what to check next)\n"
            "## Source Index (S1..Sn with URL and short relevance note)\n"
            "Aim for a thorough report; prefer depth over brevity.\n\n"
            f"TARGET: {name}\n"
            f"CONTEXT: {context_text}\n\n"
            f"SOURCES:\n{sources}\n\n"
            f"CONTENT:\n{content}"
        )

    def _fallback(self, name: str, company: str, socials: str, results: list[SearchResult], scraped: list[ScrapedPage]) -> str:
        lines = ["# Person Intelligence Report", "", f"## Target", f"- Name: {name}"]
        if company:
            lines.append(f"- Company context: {company}")
        if socials:
            lines.append(f"- Social context: {socials}")
        lines.extend(
            [
                "",
                "## Executive Summary",
                "- Bedrock summarizer is currently unavailable; this is an evidence inventory mode.",
                "- Use the sources below to build a full profile.",
                "",
                "## Source Index",
            ]
        )
        for idx, r in enumerate(results[:40], start=1):
            title = (r.title or "").strip()[:120]
            snippet = (r.snippet or "").strip().replace("\n", " ")[:200]
            lines.append(f"- [S{idx}] {title} | {r.url}")
            if snippet:
                lines.append(f"  snippet: {snippet}")
        lines.extend(["", "## Raw Page Extracts"])
        for page in scraped[:12]:
            if not page.success or not page.text:
                continue
            lines.append(f"### {page.url}")
            lines.append(page.text[:1200])
            lines.append("")
        return "\n".join(lines)

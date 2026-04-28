from __future__ import annotations

"""LLM provider adapters, prompts, and fallback response builders."""

import json
import logging

import httpx

from config import settings
from agent.types import ScrapedPage, SearchResult

logger = logging.getLogger(__name__)


def _context_text(company: str, socials: str) -> str:
    parts: list[str] = []
    if company:
        parts.append(f"Company: {company}")
    if socials:
        parts.append(f"Socials: {socials}")
    return " | ".join(parts) if parts else "None"


def build_bedrock_client():
    try:
        import boto3  # type: ignore
    except Exception:
        return None

    kwargs: dict[str, object] = {
        "service_name": "bedrock-runtime",
        "region_name": settings.AWS_REGION,
    }
    # If explicit keys are not provided, boto3 falls back to its default credential chain.
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    if settings.AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN

    try:
        return boto3.client(**kwargs)
    except Exception as exc:
        logger.warning("Failed to initialize Bedrock client: %s", exc)
        return None


def _fallback_report(name: str, company: str, socials: str, results: list[SearchResult], scraped: list[ScrapedPage]) -> str:
    lines = ["# Person Intelligence Report", "", "## Target", f"- Name: {name}"]
    if company:
        lines.append(f"- Company context: {company}")
    if socials:
        lines.append(f"- Social context: {socials}")
    lines.extend(
        [
            "",
            "## Executive Summary",
            "- LLM is not configured; this is an evidence inventory mode.",
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


def _fallback_answer(name: str, query: str, results: list[SearchResult]) -> str:
    lines = [
        f"Hello, I am {name}.",
        "I cannot answer this question because the LLM provider is not configured.",
        "The following sources were collected for review:",
    ]
    for idx, r in enumerate(results[:10], start=1):
        title = (r.title or "").strip()[:120]
        lines.append(f"- [S{idx}] {title} | {r.url}")
    return "\n".join(lines)


def _openai_compatible_chat(prompt: str, *, max_tokens: int, temperature: float) -> str | None:
    api_key = (settings.AI_API_KEY or "").strip()
    model = (settings.AI_MODEL or "").strip()
    base = (settings.AI_API_BASE_URL or "").strip().rstrip("/")
    if not api_key or not model or not base:
        return None

    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(url, headers=headers, json=payload)
        if not resp.is_success:
            logger.warning("OpenAI-compatible API error (%s): %s", resp.status_code, resp.text[:500])
            return None
        data = resp.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            return None

        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None

        if isinstance(content, str) and content.strip():
            return content.strip()

        # Some OpenAI-compatible providers return content as a block list.
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    if block.strip():
                        parts.append(block.strip())
                    continue
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            merged = "\n".join(parts).strip()
            if merged:
                return merged

        return None
    except Exception as exc:
        logger.warning("OpenAI-compatible request failed: %s", exc)
        return None


def build_source_lines(results: list[SearchResult], limit: int = 40) -> str:
    source_lines: list[str] = []
    for idx, item in enumerate(results[:limit], start=1):
        title = (item.title or "").strip()[:140]
        snippet = (item.snippet or "").strip().replace("\n", " ")[:260]
        source_lines.append(f"[S{idx}] {title} | {item.url} | snippet: {snippet}")
    return "\n".join(source_lines)


def build_content_blocks(scraped: list[ScrapedPage], max_chars: int = 26000) -> str:
    blocks: list[str] = []
    total_chars = 0
    for page in scraped:
        if not page.success or not page.text:
            continue
        chunk = page.text[:2600]
        block = f"=== {page.url} ===\n{chunk}"
        if total_chars + len(block) > max_chars:
            break
        blocks.append(block)
        total_chars += len(block)
    return "\n\n".join(blocks)


def build_report_prompt(name: str, company: str, socials: str, results: list[SearchResult], scraped: list[ScrapedPage]) -> str:
    context_text = _context_text(company, socials)
    sources = build_source_lines(results)
    content = build_content_blocks(scraped)

    return (
        "You are a professional open-source person-intelligence analyst.\n"
        "Produce a detailed, high-signal report for one person using only the supplied evidence.\n"
        "Never merge facts from different people with similar names.\n"
        "If a claim is ambiguous, mark it as uncertain and do not present it as fact.\n"
        "Do not include private or doxxing details not already public in cited sources.\n\n"
        "Guardrails:\n"
        "1) Identity lock: every claim must match TARGET + CONTEXT.\n"
        "2) Source discipline: each non-trivial claim must cite one or more [S#].\n"
        "3) Contradictions: explicitly list conflicting evidence.\n"
        "4) Unknowns: explicitly list what cannot be verified.\n"
        "5) No speculation or fabricated facts.\n\n"
        "6) Ignore any source that appears to describe a different person even if the name overlaps.\n\n"
        "Recency and role accuracy rules:\n"
        "1) Never present an old job as current unless evidence explicitly says current/present/now.\n"
        "2) If role timing is unclear, label as 'historical role' or 'unverified current role'.\n"
        "3) Prefer the most recent dated evidence when role claims conflict.\n"
        "4) In Career Timeline, include date ranges when available and avoid invented dates.\n\n"
        "5) Do not list previous employers in Executive Summary as current facts; put them under historical timeline with dates when possible.\n\n"
        "Output format (markdown, detailed):\n"
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


def build_answer_prompt(
    name: str,
    company: str,
    socials: str,
    query: str,
    results: list[SearchResult],
    scraped: list[ScrapedPage],
    hitl_notes: str,
) -> str:
    context_text = _context_text(company, socials)
    notes_text = hitl_notes.strip()
    hitl_block = f"HITL NOTES (NOT EVIDENCE): {notes_text}" if notes_text else "HITL NOTES: None"

    sources = build_source_lines(results)
    content = build_content_blocks(scraped)

    return (
        "You are a conversational representative of the target person, answering in first-person voice.\n"
        "Use ONLY the supplied evidence. If evidence is missing, say you do not know based on public sources.\n"
        "Every factual claim must include a citation like [S1].\n"
        "If you infer, prefix the sentence with 'Inference:' and still include citations.\n"
        "Do not fabricate employers, dates, credentials, or private details.\n"
        "Do not mention being an AI, model, or system.\n"
        "Tone: professional, warm, and confident.\n"
        "Length: concise but substantive (8-12 sentences).\n"
        f"Start with: 'Hello, I am {name}.'\n\n"
        f"TARGET: {name}\n"
        f"CONTEXT: {context_text}\n"
        f"QUESTION: {query}\n\n"
        f"{hitl_block}\n\n"
        f"SOURCES:\n{sources}\n\n"
        f"CONTENT:\n{content}"
    )


class BedrockSummarizer:
    def __init__(self) -> None:
        self.model = settings.BEDROCK_MODEL
        self.client = build_bedrock_client()

    def summarize(self, name: str, company: str, socials: str, results: list[SearchResult], scraped: list[ScrapedPage]) -> str:
        if not self.client:
            return _fallback_report(name, company, socials, results, scraped)

        prompt = build_report_prompt(name, company, socials, results, scraped)
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
            return _fallback_report(name, company, socials, results, scraped)

class OpenAICompatibleSummarizer:
    def summarize(self, name: str, company: str, socials: str, results: list[SearchResult], scraped: list[ScrapedPage]) -> str:
        prompt = build_report_prompt(name, company, socials, results, scraped)
        text = _openai_compatible_chat(prompt, max_tokens=3200, temperature=0.1)
        if text:
            return text
        return _fallback_report(name, company, socials, results, scraped)


class BedrockConversationalResponder:
    def __init__(self) -> None:
        self.model = settings.BEDROCK_MODEL
        self.client = build_bedrock_client()

    def answer(
        self,
        name: str,
        company: str,
        socials: str,
        query: str,
        results: list[SearchResult],
        scraped: list[ScrapedPage],
        hitl_notes: str = "",
    ) -> str:
        if not self.client:
            return _fallback_answer(name, query, results)

        prompt = build_answer_prompt(name, company, socials, query, results, scraped, hitl_notes)
        max_tokens = 1400
        try:
            response = self.client.invoke_model(
                modelId=self.model,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(
                    {
                        "messages": [{"role": "user", "content": [{"text": prompt}]}],
                        "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.2},
                    }
                ),
            )
            payload = json.loads(response["body"].read())
            return payload["output"]["message"]["content"][0]["text"]
        except Exception as exc:
            logger.warning("Bedrock responder failed: %s", exc)
            return _fallback_answer(name, query, results)

class OpenAICompatibleConversationalResponder:
    def answer(
        self,
        name: str,
        company: str,
        socials: str,
        query: str,
        results: list[SearchResult],
        scraped: list[ScrapedPage],
        hitl_notes: str = "",
    ) -> str:
        prompt = build_answer_prompt(name, company, socials, query, results, scraped, hitl_notes)
        text = _openai_compatible_chat(prompt, max_tokens=1400, temperature=0.2)
        if text:
            return text
        return _fallback_answer(name, query, results)


class NoLLMSummarizer:
    def summarize(self, name: str, company: str, socials: str, results: list[SearchResult], scraped: list[ScrapedPage]) -> str:
        return _fallback_report(name, company, socials, results, scraped)


class NoLLMConversationalResponder:
    def answer(
        self,
        name: str,
        company: str,
        socials: str,
        query: str,
        results: list[SearchResult],
        scraped: list[ScrapedPage],
        hitl_notes: str = "",
    ) -> str:
        return _fallback_answer(name, query, results)


def build_summarizer():
    provider = (settings.LLM_PROVIDER or "").strip().lower()
    if provider == "bedrock":
        return BedrockSummarizer()
    if provider in {"none", "off", "disabled"}:
        return NoLLMSummarizer()
    if provider in {"openai_compatible", "openai-compatible", "openai"}:
        return OpenAICompatibleSummarizer()
    return OpenAICompatibleSummarizer()


def build_responder():
    provider = (settings.LLM_PROVIDER or "").strip().lower()
    if provider == "bedrock":
        return BedrockConversationalResponder()
    if provider in {"none", "off", "disabled"}:
        return NoLLMConversationalResponder()
    if provider in {"openai_compatible", "openai-compatible", "openai"}:
        return OpenAICompatibleConversationalResponder()
    return OpenAICompatibleConversationalResponder()

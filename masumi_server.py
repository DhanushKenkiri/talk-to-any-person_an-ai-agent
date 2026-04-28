#!/usr/bin/env python3
"""TalkToAnyPerson Masumi-compatible server."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from masumi import Config as MasumiConfig, create_masumi_input_hash
from masumi.hitl import clear_job_context, provide_input_to_job, request_input, set_job_context
from masumi.job_manager import JobManager, InMemoryJobStorage
from masumi.models import JobStatus
from masumi.payment import Payment as MasumiPayment
from masumi.validation import ValidationError, validate_input_data

from agent.research import ResearchAPersonService
from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

INPUT_SCHEMA = json.loads(Path(__file__).with_name("input_schema.json").read_text(encoding="utf-8"))
_IDENTIFIER_RE = re.compile(r"^[0-9a-f]{14,26}$")
_AGENT_ID_CACHE = ""
_AGENT_ID_LAST_CHECK = 0.0
_AGENT_ID_TTL_SECONDS = 60.0

_SOURCE_CITATION_RE = re.compile(r"\[S(\d{1,3})\]")
_SOURCE_LIST_LINE_RE = re.compile(r"^\s*(?:-|\*|\d+\.)\s*(?:\[S\d{1,3}\]|S\d{1,3})\b.*https?://", re.MULTILINE)
_DONE_TOKENS = {"done", "finish", "stop", "exit", "quit"}


def normalize_identifier(value: Any) -> str:
    if value is None:
        return ""
    raw = str(value).strip().lower()
    if _IDENTIFIER_RE.fullmatch(raw):
        return raw
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:26]


def normalize_input_data(input_data: Any) -> dict[str, str]:
    if isinstance(input_data, dict):
        return {str(k): "" if v is None else str(v) for k, v in input_data.items()}
    if isinstance(input_data, list):
        out: dict[str, str] = {}
        for item in input_data:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or item.get("id") or item.get("name")
            if not key:
                continue
            value = item.get("value")
            if value is None and isinstance(item.get("data"), dict):
                value = item["data"].get("value") or item["data"].get("default")
            out[str(key)] = "" if value is None else str(value)
        return out
    return {}


def coerce_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "identifier_from_purchaser" not in payload and "identifierFromPurchaser" in payload:
        payload["identifier_from_purchaser"] = payload["identifierFromPurchaser"]
    if "input_data" not in payload and "inputData" in payload:
        payload["input_data"] = payload["inputData"]
    return payload


def normalize_endpoint(value: str) -> str:
    return value.rstrip("/") if value else ""


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_list(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[,;\n]+", str(value))
    return [part.strip() for part in parts if part.strip()]


def parse_socials(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def normalize_socials(value: str) -> str:
    items = [part.strip() for part in value.split(",") if part.strip()]
    normalized = []
    for item in items:
        if item.startswith("http://") or item.startswith("https://"):
            normalized.append(item)
        else:
            normalized.append(f"https://{item}")
    return ", ".join(normalized)


def find_invalid_socials(value: str) -> list[str]:
    invalid: list[str] = []
    for item in parse_socials(value):
        parsed = urlparse(item)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            invalid.append(item)
    return invalid


def build_hitl_schema(missing: list[str], invalid_socials: list[str]) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    if "name" in missing:
        fields.append(
            {
                "id": "name",
                "type": "string",
                "name": "Full Name",
                "data": {"description": "Enter the full name exactly as it should be searched."},
            }
        )
    if "company" in missing:
        fields.append(
            {
                "id": "company",
                "type": "string",
                "name": "Company",
                "data": {"description": "Enter the company or organization (required)."},
            }
        )
    if "socials" in missing or invalid_socials:
        fields.append(
            {
                "id": "socials",
                "type": "string",
                "name": "Social URLs",
                "data": {
                    "description": "Comma-separated URLs starting with http:// or https:// (required).",
                },
            }
        )
    if "query" in missing:
        fields.append(
            {
                "id": "query",
                "type": "string",
                "name": "Your Question",
                "data": {"description": "Enter the specific question to answer."},
            }
        )
    return {"input_data": fields}


def build_followup_hitl_schema() -> dict[str, Any]:
    return {
        "input_data": [
            {
                "id": "query",
                "type": "string",
                "name": "Follow-up Question",
                "data": {
                    "description": "Ask another question, or type DONE to finish.",
                },
            }
        ]
    }


def is_done_query(value: str) -> bool:
    return str(value or "").strip().lower() in _DONE_TOKENS


def extract_cited_source_numbers(text: str) -> list[int]:
    cited: set[int] = set()
    for match in _SOURCE_CITATION_RE.findall(text or ""):
        try:
            cited.add(int(match))
        except Exception:
            continue
    return sorted(cited)


def attach_sources_section(answer_text: str, results: list[Any], fallback_limit: int = 10) -> str:
    cited = extract_cited_source_numbers(answer_text)
    if not cited:
        cited = list(range(1, min(len(results), fallback_limit) + 1))

    lines: list[str] = [answer_text.rstrip(), "", "## Sources"]
    for idx in cited:
        if idx < 1 or idx > len(results):
            continue
        item = results[idx - 1]
        title = (getattr(item, "title", "") or "").strip()
        url = (getattr(item, "url", "") or "").strip()
        if not url:
            continue
        label = title if title else url
        lines.append(f"- [S{idx}] {label} | {url}")

    return "\n".join(lines).rstrip()


def ensure_sources_list(text: str, results: list[Any]) -> str:
    """Ensure the output contains an explicit list of cited sources.

    Bedrock prompts *ask* for sources, but the model can omit them; this makes
    the output reliably auditable for Sokosumi users.
    """

    if _SOURCE_LIST_LINE_RE.search(text or ""):
        return (text or "").rstrip()
    return attach_sources_section(text or "", results)


def apply_hitl_corrections(input_data: dict[str, str]) -> dict[str, str]:
    raw = input_data.get("hitl_corrections", "").strip()
    if not raw:
        return input_data
    for chunk in re.split(r"[;\n]+", raw):
        item = chunk.strip()
        if not item:
            continue
        if "=" in item:
            key, value = item.split("=", 1)
        elif ":" in item:
            key, value = item.split(":", 1)
        else:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key in {"name", "company", "socials", "query"} and value:
            input_data[key] = value
    return input_data


def prepare_inputs(input_data: dict[str, str]) -> dict[str, Any]:
    data = dict(input_data)
    data = apply_hitl_corrections(data)
    data["name"] = data.get("name", "").strip()
    data["company"] = data.get("company", "").strip()
    data["socials"] = normalize_socials(data.get("socials", "").strip())
    data["initial_question"] = (data.get("initial_question") or data.get("initialQuestion") or "").strip()
    data["query"] = data.get("query", "").strip()
    if not data["query"] and data["initial_question"]:
        data["query"] = data["initial_question"]
    data["deep_research"] = parse_bool(data.get("deep_research", ""))
    data["extra_queries"] = parse_list(data.get("extra_queries", ""))[:8]
    data["hitl_notes"] = data.get("hitl_notes", "").strip()
    return data


def missing_required_profile_fields(prepared: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not prepared.get("name"):
        missing.append("name")
    if not prepared.get("company"):
        missing.append("company")
    if not prepared.get("socials"):
        missing.append("socials")
    return missing


_TXN_ALIAS_KEYS = (
    "transactionId",
    "transaction_id",
    "txId",
    "tx_id",
    "txnId",
    "txn_id",
    "txnHash",
    "txn_hash",
    "blockchainIdentifier",
    "blockchain_identifier",
    "blockchainId",
    "blockchain_id",
    "paymentId",
    "payment_id",
    "purchaseId",
    "purchase_id",
    "transactionHash",
    "transaction_hash",
    "txHash",
    "tx_hash",
    "currentTransactionHash",
    "current_transaction_hash",
    "currentTransactionId",
    "current_transaction_id",
)


def add_tx_aliases(payload: dict[str, Any], payment_id: Any) -> None:
    if payment_id is None:
        return
    payment_id_str = str(payment_id).strip()
    if not payment_id_str:
        return

    for key in _TXN_ALIAS_KEYS:
        payload.setdefault(key, payment_id_str)

    current_txn = {
        "transactionId": payment_id_str,
        "transactionHash": payment_id_str,
        "txHash": payment_id_str,
        "txnHash": payment_id_str,
        "id": payment_id_str,
        "hash": payment_id_str,
    }
    payload.setdefault("currentTransaction", current_txn)
    payload.setdefault("CurrentTransaction", current_txn)


async def resolve_agent_identifier(endpoint: str) -> str:
    global _AGENT_ID_CACHE, _AGENT_ID_LAST_CHECK

    if settings.AGENT_IDENTIFIER:
        return settings.AGENT_IDENTIFIER

    now = time.monotonic()
    if _AGENT_ID_CACHE and (now - _AGENT_ID_LAST_CHECK) < _AGENT_ID_TTL_SECONDS:
        return _AGENT_ID_CACHE
    _AGENT_ID_LAST_CHECK = now

    if not settings.REGISTRY_API_URL or not settings.REGISTRY_API_KEY:
        return settings.AGENT_IDENTIFIER or ""

    params = {
        "network": settings.NETWORK,
        "limit": 20,
        "searchQuery": settings.AGENT_NAME,
    }
    headers = {"token": settings.REGISTRY_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.REGISTRY_API_URL.rstrip('/')}/registry", params=params, headers=headers)
        if not resp.is_success:
            logger.warning("Registry lookup failed: %s", resp.text)
            return settings.AGENT_IDENTIFIER or ""
        payload = resp.json()
    except Exception as exc:
        logger.warning("Registry lookup error: %s", exc)
        return settings.AGENT_IDENTIFIER or ""

    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    entries = data.get("Assets", []) if isinstance(data, dict) else []
    target = normalize_endpoint(endpoint)

    candidates: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if normalize_endpoint(entry.get("apiBaseUrl", "")) != target:
            continue

        agent_id = str(entry.get("agentIdentifier") or "").strip()
        if not agent_id:
            continue
        candidates.append(entry)

    if not candidates:
        return settings.AGENT_IDENTIFIER or ""

    # Prefer exact name matches when available.
    name_matched = [c for c in candidates if not c.get("name") or c.get("name") == settings.AGENT_NAME]
    if name_matched:
        candidates = name_matched

    def state_rank(state: str) -> int:
        s = (state or "").strip()
        if s == "RegistrationConfirmed":
            return 3
        if s.startswith("Registration"):
            return 2
        if s.startswith("Deregistration"):
            return 0
        return 1

    def timestamp_key(entry: dict[str, Any]) -> str:
        # Registry timestamps are ISO strings; lexicographic order matches chronological order.
        return str(entry.get("updatedAt") or entry.get("createdAt") or "")

    # If there are confirmed registrations, choose the newest confirmed one.
    confirmed = [c for c in candidates if str(c.get("state") or "") == "RegistrationConfirmed"]
    if confirmed:
        confirmed.sort(key=lambda x: timestamp_key(x), reverse=True)
        agent_id = str(confirmed[0].get("agentIdentifier") or "").strip()
        if agent_id:
            _AGENT_ID_CACHE = agent_id
            return agent_id

    # Otherwise, choose the newest non-deregistering registration by state rank then timestamp.
    candidates.sort(
        key=lambda x: (
            state_rank(str(x.get("state") or "")),
            timestamp_key(x),
        ),
        reverse=True,
    )
    agent_id = str(candidates[0].get("agentIdentifier") or "").strip()
    if agent_id:
        _AGENT_ID_CACHE = agent_id
        return agent_id

    return settings.AGENT_IDENTIFIER or ""


async def process_job(input_data: dict[str, str]) -> str:
    prepared = prepare_inputs(input_data)

    service = ResearchAPersonService()
    ranked, scraped = await asyncio.to_thread(
        service.gather_evidence,
        prepared["name"],
        prepared["company"],
        prepared["socials"],
        prepared["extra_queries"],
        prepared["deep_research"],
    )

    report = await asyncio.to_thread(
        service.summarizer.summarize,
        prepared["name"],
        prepared["company"],
        prepared["socials"],
        ranked,
        scraped,
    )
    report = ensure_sources_list(report, ranked)

    initial_question = prepared.get("query", "").strip()
    if initial_question and not is_done_query(initial_question):
        answer = await asyncio.to_thread(
            service.responder.answer,
            prepared["name"],
            prepared["company"],
            prepared["socials"],
            initial_question,
            ranked,
            scraped,
            prepared["hitl_notes"],
        )
        answer = attach_sources_section(answer, ranked)
        return "\n\n---\n\n".join([report, f"## Initial Question\n{initial_question}\n\n{answer}"]).rstrip()

    return report.rstrip()


async def process_job_conversation(job_id: str, input_data: dict[str, str]) -> str:
    prepared = prepare_inputs(input_data)

    # Only validate the 3 form fields up-front; queries come via HITL.
    missing = missing_required_profile_fields(prepared)

    invalid_socials = find_invalid_socials(prepared["socials"]) if prepared["socials"] else []
    if missing or invalid_socials:
        message = "Some required fields are missing or invalid."
        if invalid_socials:
            message += f" Invalid socials: {', '.join(invalid_socials)}."
        message += " Social URLs should be full http(s) links, comma-separated."

        corrections = await request_input(build_hitl_schema(missing, invalid_socials), message=message)
        if isinstance(corrections, dict):
            for key in ("name", "company", "socials"):
                value = corrections.get(key)
                if value is not None:
                    prepared[key] = str(value).strip()

        prepared["socials"] = normalize_socials(prepared.get("socials", ""))
        missing = missing_required_profile_fields(prepared)
        invalid_socials = find_invalid_socials(prepared["socials"]) if prepared["socials"] else []
        if missing or invalid_socials:
            return "Error: required fields are missing or invalid after HITL correction"

    service = ResearchAPersonService()
    ranked, scraped = await asyncio.to_thread(
        service.gather_evidence,
        prepared["name"],
        prepared["company"],
        prepared["socials"],
        prepared["extra_queries"],
        prepared["deep_research"],
    )

    parts: list[str] = []

    report = await asyncio.to_thread(
        service.summarizer.summarize,
        prepared["name"],
        prepared["company"],
        prepared["socials"],
        ranked,
        scraped,
    )
    report = ensure_sources_list(report, ranked)
    parts.append(report)
    transcript = "\n\n---\n\n".join(parts)
    await job_manager.update_job_status(job_id, JobStatus.RUNNING.value, result=transcript)

    initial_question = prepared.get("query", "").strip()
    if initial_question and not is_done_query(initial_question):
        initial_answer = await asyncio.to_thread(
            service.responder.answer,
            prepared["name"],
            prepared["company"],
            prepared["socials"],
            initial_question,
            ranked,
            scraped,
            prepared["hitl_notes"],
        )
        initial_answer = attach_sources_section(initial_answer, ranked)
        parts.append(f"## Initial Question\n{initial_question}\n\n{initial_answer}")
        transcript = "\n\n---\n\n".join(parts)
        await job_manager.update_job_status(job_id, JobStatus.RUNNING.value, result=transcript)

    turn = 1
    while True:
        followup = await request_input(
            build_followup_hitl_schema(),
            message="Ask a follow-up question, or type DONE to finish.",
        )
        followup_data = normalize_input_data(followup)
        next_query = str(followup_data.get("query") or "").strip()
        if not next_query:
            continue
        if is_done_query(next_query):
            return transcript

        answer = await asyncio.to_thread(
            service.responder.answer,
            prepared["name"],
            prepared["company"],
            prepared["socials"],
            next_query,
            ranked,
            scraped,
            prepared["hitl_notes"],
        )
        answer = attach_sources_section(answer, ranked)

        parts.append(f"## Q{turn}\n{next_query}\n\n{answer}")
        transcript = "\n\n---\n\n".join(parts)
        await job_manager.update_job_status(job_id, JobStatus.RUNNING.value, result=transcript)
        turn += 1


app = FastAPI(title="Talk To Any Person - Persona Report & Q&A (HITL)", version="1.0.0")
job_manager = JobManager(storage=InMemoryJobStorage())
masumi_config = MasumiConfig(
    payment_service_url=settings.PAYMENT_SERVICE_URL,
    payment_api_key=settings.PAYMENT_API_KEY,
    registry_service_url=settings.REGISTRY_API_URL or None,
    registry_api_key=settings.REGISTRY_API_KEY or None,
)


@app.get("/availability")
async def availability():
    return {"status": "available", "type": "masumi-agent", "message": "Server operational"}


@app.get("/input_schema")
async def input_schema_get():
    return JSONResponse(content=INPUT_SCHEMA)


@app.options("/input_schema")
async def input_schema_options():
    response = JSONResponse(content=INPUT_SCHEMA)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


@app.post("/start_job")
async def start_job(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid request body")

    payload = coerce_payload(payload)
    if isinstance(payload.get("input_data"), list):
        payload["input_data"] = normalize_input_data(payload["input_data"])

    identifier = normalize_identifier(payload.get("identifier_from_purchaser"))
    if not identifier:
        raise HTTPException(status_code=400, detail="identifier_from_purchaser is required")

    input_data = payload.get("input_data") or {}
    if not isinstance(input_data, dict):
        raise HTTPException(status_code=400, detail="input_data must be an object")

    if settings.DEV_MODE:
        job_id = f"local-{int(time.time())}"
        result = await process_job(normalize_input_data(input_data))
        response_payload = {
            "id": job_id,
            "jobId": job_id,
            "job_id": job_id,
            "status": "completed",
            "result": result,
            "identifierFromPurchaser": identifier,
        }
        return JSONResponse(content=response_payload)

    endpoint = normalize_endpoint(str(request.base_url))
    agent_identifier = await resolve_agent_identifier(endpoint)
    if not agent_identifier:
        raise HTTPException(status_code=400, detail="Agent registration pending; identifier not assigned yet")

    payment = MasumiPayment(
        agent_identifier=agent_identifier,
        config=masumi_config,
        identifier_from_purchaser=identifier,
        input_data=input_data,
        network=settings.NETWORK,
    )

    try:
        payment_request = await payment.create_payment_request()
    except Exception as exc:
        logger.exception("Payment request creation failed")
        raise HTTPException(status_code=502, detail="Payment service error") from exc

    data = payment_request.get("data") if isinstance(payment_request, dict) else None
    if not isinstance(data, dict):
        logger.error("Unexpected payment request payload: %s", payment_request)
        raise HTTPException(status_code=502, detail="Payment service returned invalid response")

    blockchain_identifier = str(data.get("blockchainIdentifier") or "").strip()
    if not blockchain_identifier:
        logger.error("Payment request missing blockchainIdentifier: %s", payment_request)
        raise HTTPException(status_code=502, detail="Payment service did not return a transaction identifier")

    payment.payment_ids.add(blockchain_identifier)
    seller_vkey = settings.SELLER_VKEY or str(data.get("sellerVKey") or "")
    pay_by_time = int(data["payByTime"])
    submit_result_time = int(data["submitResultTime"])
    unlock_time = int(data["unlockTime"])
    external_dispute_unlock_time = int(data["externalDisputeUnlockTime"])

    job_id = await job_manager.create_job(
        identifier_from_purchaser=identifier,
        input_data=input_data,
        payment=payment,
        blockchain_identifier=blockchain_identifier,
        pay_by_time=pay_by_time,
        submit_result_time=submit_result_time,
        unlock_time=unlock_time,
        external_dispute_unlock_time=external_dispute_unlock_time,
        agent_identifier=agent_identifier,
        seller_vkey=seller_vkey,
        input_hash=payment.input_hash,
    )

    async def run_job_after_payment(payment_info: dict[str, Any]):
        payment_id = payment_info.get("blockchainIdentifier", "")
        await job_manager.update_job_status(job_id, JobStatus.RUNNING.value, payment_id=payment_id)
        try:
            set_job_context(job_id, job_manager)
            try:
                result = await process_job_conversation(job_id, normalize_input_data(input_data))
            finally:
                clear_job_context()
            await job_manager.set_job_completed(job_id, result)
        except Exception as exc:
            await job_manager.set_job_failed(job_id, str(exc))

    async def payment_callback(payment_info: dict[str, Any]):
        asyncio.create_task(run_job_after_payment(payment_info))

    await payment.start_status_monitoring(callback=payment_callback)

    response_payload = {
        "id": job_id,
        "jobId": job_id,
        "job_id": job_id,
        "blockchainIdentifier": blockchain_identifier,
        "blockchain_identifier": blockchain_identifier,
        "payByTime": pay_by_time,
        "submitResultTime": submit_result_time,
        "unlockTime": unlock_time,
        "externalDisputeUnlockTime": external_dispute_unlock_time,
        "agentIdentifier": agent_identifier,
        "sellerVKey": seller_vkey,
        "identifierFromPurchaser": identifier,
        "input_hash": payment.input_hash or "",
    }
    add_tx_aliases(response_payload, blockchain_identifier)
    return JSONResponse(content=response_payload)


@app.get("/status")
async def status(request: Request):
    params = dict(request.query_params)
    job_id = params.get("job_id") or params.get("jobId") or params.get("id")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    payload = {
        "id": job_id,
        "jobId": job_id,
        "job_id": job_id,
        "status": job.get("status", JobStatus.AWAITING_PAYMENT.value),
        "result": job.get("result"),
        "error": job.get("error"),
        "input_schema": None,
        "message": None,
    }

    if payload["status"] == JobStatus.AWAITING_INPUT.value:
        payload["input_schema"] = job.get("awaiting_input_schema") or INPUT_SCHEMA
        payload["message"] = job.get("awaiting_input_message")

    payment_id = (
        job.get("payment_id")
        or job.get("blockchain_identifier")
        or job.get("blockchainIdentifier")
        or job.get("blockchain_id")
        or ""
    )
    add_tx_aliases(payload, payment_id)
    return JSONResponse(content=payload)


@app.post("/provide_input")
async def provide_input(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid request body")

    job_id = payload.get("job_id") or payload.get("jobId") or payload.get("id")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    if "input_data" in payload:
        input_data = payload.get("input_data")
    else:
        input_data = payload.get("inputData")
    if not isinstance(input_data, dict):
        raise HTTPException(status_code=400, detail="input_data must be an object")

    job = await job_manager.get_job(str(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    if job.get("status") != JobStatus.AWAITING_INPUT.value:
        raise HTTPException(
            status_code=400,
            detail=f"job is not awaiting input (status={job.get('status')})",
        )

    schema = job.get("awaiting_input_schema")
    if schema:
        try:
            validate_input_data(input_data, schema)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    await job_manager.resume_job_with_input(str(job_id), input_data)
    provide_input_to_job(str(job_id), input_data)

    identifier_from_purchaser = job.get("identifier_from_purchaser", "")
    input_hash = create_masumi_input_hash(input_data, identifier_from_purchaser)
    return JSONResponse(content={"input_hash": input_hash, "signature": ""})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Talk To Any Person - Persona Report & Q&A (HITL)")
    logger.info("Host: %s:%s", settings.HOST, settings.PORT)
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)




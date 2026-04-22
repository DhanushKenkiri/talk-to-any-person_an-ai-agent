#!/usr/bin/env python3
"""PersonaSignal Nova v17 Masumi-compatible server."""

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

from agent.research import PersonaSignalService
from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

INPUT_SCHEMA = json.loads(Path(__file__).with_name("input_schema.json").read_text(encoding="utf-8"))
_IDENTIFIER_RE = re.compile(r"^[0-9a-f]{14,26}$")
_AGENT_ID_CACHE = ""
_AGENT_ID_LAST_CHECK = 0.0
_AGENT_ID_TTL_SECONDS = 60.0


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
                "data": {"description": "Enter the company or organization (optional)."},
            }
        )
    if "socials" in missing or invalid_socials:
        fields.append(
            {
                "id": "socials",
                "type": "string",
                "name": "Social URLs",
                "data": {
                    "description": "Comma-separated URLs starting with http:// or https:// (optional).",
                },
            }
        )
    return {"input_data": fields}


def add_tx_aliases(payload: dict[str, Any], payment_id: str) -> None:
    if not payment_id:
        return
    aliases = {
        "payment_id": payment_id,
        "paymentId": payment_id,
        "transactionId": payment_id,
        "txnId": payment_id,
        "transaction_id": payment_id,
        "txHash": payment_id,
        "transactionHash": payment_id,
        "tx_hash": payment_id,
        "blockchainIdentifier": payment_id,
        "blockchain_identifier": payment_id,
    }
    for key, value in aliases.items():
        payload.setdefault(key, value)


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

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if normalize_endpoint(entry.get("apiBaseUrl", "")) != target:
            continue
        if entry.get("name") and entry.get("name") != settings.AGENT_NAME:
            continue
        agent_id = entry.get("agentIdentifier") or ""
        if agent_id:
            _AGENT_ID_CACHE = agent_id
            return agent_id

    return settings.AGENT_IDENTIFIER or ""


async def process_job(identifier_from_purchaser: str, input_data: dict[str, str]) -> str:
    name = str(input_data.get("name", "")).strip()
    company = str(input_data.get("company", "")).strip()
    socials = normalize_socials(str(input_data.get("socials", "")).strip())

    missing: list[str] = []
    if not name:
        missing.append("name")
    invalid_socials = find_invalid_socials(socials) if socials else []

    if missing or invalid_socials:
        if settings.DEV_MODE:
            return "Error: required fields are missing or invalid"

        message = "Some required fields are missing or invalid."
        if invalid_socials:
            message += f" Invalid socials: {', '.join(invalid_socials)}."
        message += " Social URLs should be full http(s) links, comma-separated."

        corrections = await request_input(build_hitl_schema(missing, invalid_socials), message=message)
        if isinstance(corrections, dict):
            if corrections.get("name") is not None:
                name = str(corrections.get("name") or "").strip()
            if corrections.get("company") is not None:
                company = str(corrections.get("company") or "").strip()
            if corrections.get("socials") is not None:
                socials = normalize_socials(str(corrections.get("socials") or "").strip())

        missing = []
        if not name:
            missing.append("name")
        invalid_socials = find_invalid_socials(socials) if socials else []
        if missing or invalid_socials:
            return "Error: required fields are missing or invalid after HITL correction"

    service = PersonaSignalService()
    return await asyncio.to_thread(service.run, name=name, company=company, socials=socials)


app = FastAPI(title="PersonaSignal Nova v17", version="17.0.0")
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

    name = str(input_data.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

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

    payment_request = await payment.create_payment_request()
    blockchain_identifier = payment_request["data"]["blockchainIdentifier"]
    payment.payment_ids.add(blockchain_identifier)
    seller_vkey = settings.SELLER_VKEY or payment_request["data"].get("sellerVKey", "")

    job_id = await job_manager.create_job(
        identifier_from_purchaser=identifier,
        input_data=input_data,
        payment=payment,
        blockchain_identifier=blockchain_identifier,
        pay_by_time=int(payment_request["data"]["payByTime"]),
        submit_result_time=int(payment_request["data"]["submitResultTime"]),
        unlock_time=int(payment_request["data"]["unlockTime"]),
        external_dispute_unlock_time=int(payment_request["data"]["externalDisputeUnlockTime"]),
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
                result = await process_job(identifier, normalize_input_data(input_data))
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
        "payByTime": int(payment_request["data"]["payByTime"]),
        "submitResultTime": int(payment_request["data"]["submitResultTime"]),
        "unlockTime": int(payment_request["data"]["unlockTime"]),
        "externalDisputeUnlockTime": int(payment_request["data"]["externalDisputeUnlockTime"]),
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

    logger.info("Starting PersonaSignal Nova v17")
    logger.info("Host: %s:%s", settings.HOST, settings.PORT)
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)


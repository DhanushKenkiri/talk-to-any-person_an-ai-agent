#!/usr/bin/env python3
"""Smoke-test Masumi payment request creation.

This replicates what masumi.Payment.create_payment_request() sends, but prints
only non-secret diagnostics.

Usage:
  python payment_smoke_test.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from masumi import create_masumi_input_hash


HERE = Path(__file__).resolve().parent


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip()
    return values


def load_endpoint(env: dict[str, str]) -> str:
    deploy_path = HERE / "aws-deployment.json"
    if deploy_path.exists():
        deploy = json.loads(deploy_path.read_text(encoding="utf-8"))
        endpoint = str(deploy.get("endpoint") or "").strip()
        if endpoint:
            return endpoint

    return (env.get("ENDPOINT") or "").strip()


def resolve_agent_identifier(env: dict[str, str]) -> str:
    agent_identifier = (env.get("AGENT_IDENTIFIER") or "").strip()
    if agent_identifier:
        return agent_identifier

    payment_url = (env.get("PAYMENT_SERVICE_URL") or "").rstrip("/")
    registry_url = (env.get("REGISTRY_API_URL") or payment_url).rstrip("/")
    token = (env.get("REGISTRY_API_KEY") or env.get("PAYMENT_API_KEY") or "").strip()
    network = (env.get("NETWORK") or "Preprod").strip()
    agent_name = (env.get("AGENT_NAME") or "").strip()
    endpoint = load_endpoint(env).rstrip("/")

    if not registry_url or not token:
        return ""

    params: dict[str, str | int] = {"network": network, "limit": 50}
    if agent_name:
        params["searchQuery"] = agent_name

    resp = httpx.get(
        f"{registry_url}/registry",
        params=params,
        headers={"token": token, "Accept": "application/json"},
        timeout=30,
    )
    if not resp.is_success:
        return ""

    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    entries = data.get("Assets", []) if isinstance(data, dict) else []

    if endpoint:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if (entry.get("apiBaseUrl") or "").rstrip("/") != endpoint:
                continue
            found = (entry.get("agentIdentifier") or "").strip()
            if found:
                return found

    if agent_name:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("name") != agent_name:
                continue
            found = (entry.get("agentIdentifier") or "").strip()
            if found:
                return found

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        found = (entry.get("agentIdentifier") or "").strip()
        if found:
            return found

    return ""


def main() -> int:
    env = load_env(HERE / ".env")

    payment_url = (env.get("PAYMENT_SERVICE_URL") or "").rstrip("/")
    payment_key = env.get("PAYMENT_API_KEY") or ""
    network = env.get("NETWORK") or "Preprod"

    if not payment_url or not payment_key:
        raise SystemExit("PAYMENT_SERVICE_URL / PAYMENT_API_KEY missing in .env")

    agent_identifier = resolve_agent_identifier(env)
    if not agent_identifier:
        raise SystemExit(
            "Unable to resolve AGENT_IDENTIFIER. Set AGENT_IDENTIFIER in .env or register the agent so it appears in /registry."
        )

    raw_identifier = "fresh-smoke"
    identifier = hashlib.sha256(raw_identifier.encode("utf-8")).hexdigest()[:26]

    input_data = {
        "name": "Dhanush",
        "company": "Masumi",
        "socials": "https://linkedin.com/in/example",
    }
    input_hash = create_masumi_input_hash(input_data, identifier)

    pay_by = (datetime.now(timezone.utc) + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    submit = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    payload = {
        "agentIdentifier": agent_identifier,
        "network": network,
        "paymentType": "Web3CardanoV1",
        "payByTime": pay_by,
        "submitResultTime": submit,
        "identifierFromPurchaser": identifier,
        "inputHash": input_hash,
    }

    headers = {"token": payment_key, "Content-Type": "application/json"}
    resp = httpx.post(f"{payment_url}/payment/", headers=headers, json=payload, timeout=30)

    # Print only high-level response details.
    out = {
        "status": resp.status_code,
        "response_preview": resp.text[:600],
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

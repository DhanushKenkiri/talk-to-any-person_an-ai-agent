#!/usr/bin/env python3
"""Register TalkToAnyPerson HITL v1 with the Masumi registry.

- Loads config from .env in this folder.
- Uses registry_payload.json as the base payload.
- Overrides apiBaseUrl from the ENDPOINT env var.

Usage:
  python register_agent.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

REGISTRY_API_URL = os.getenv("REGISTRY_API_URL") or os.getenv("REGISTRY_API") or ""
REGISTRY_API_KEY = os.getenv("REGISTRY_API_KEY") or os.getenv("PAYMENT_API_KEY") or ""
NETWORK = os.getenv("NETWORK", "Preprod")


def load_endpoint() -> str:
    endpoint = (os.getenv("ENDPOINT") or "").strip()
    if endpoint:
        return endpoint

    raise SystemExit("No endpoint found. Set ENDPOINT in .env")


def main() -> int:
    if not REGISTRY_API_URL:
        raise SystemExit("REGISTRY_API_URL is missing in .env")
    if not REGISTRY_API_KEY:
        raise SystemExit("REGISTRY_API_KEY (or PAYMENT_API_KEY) is missing in .env")

    payload_path = HERE / "registry_payload.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8-sig"))

    endpoint = load_endpoint().rstrip("/")
    payload["apiBaseUrl"] = endpoint
    payload["network"] = NETWORK

    seller_vkey = (os.getenv("SELLER_VKEY") or "").strip()
    if seller_vkey:
        payload["sellingWalletVkey"] = seller_vkey

    if not str(payload.get("sellingWalletVkey") or "").strip():
        raise SystemExit("SELLER_VKEY is missing in .env")

    headers = {"token": REGISTRY_API_KEY}

    url = f"{REGISTRY_API_URL.rstrip('/')}/registry"
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=headers, json=payload)

    try:
        result = resp.json()
    except Exception:
        print(f"Status: {resp.status_code}")
        print(resp.text)
        return 1

    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(data, dict):
        data = {}

    registry_id = data.get("id") or result.get("id")
    agent_identifier = data.get("agentIdentifier") or result.get("agentIdentifier")
    state = data.get("state") or result.get("state")

    print(
        json.dumps(
            {
                "status_code": resp.status_code,
                "registryId": registry_id,
                "agentIdentifier": agent_identifier,
                "state": state,
                "apiBaseUrl": endpoint,
            },
            indent=2,
        )
    )

    sokosumi_base = "https://preprod.sokosumi.com" if NETWORK.lower() == "preprod" else "https://app.sokosumi.com"
    if agent_identifier:
        print(f"Sokosumi URL: {sokosumi_base}/agents/{agent_identifier}")

    if not resp.is_success:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


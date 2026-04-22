#!/usr/bin/env python3
"""Poll the Masumi registry until the deployed agent is confirmed.

Prints only non-secret fields: registry id, state, agentIdentifier, apiBaseUrl.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

REGISTRY_API_URL = os.getenv("REGISTRY_API_URL") or os.getenv("REGISTRY_API") or ""
REGISTRY_API_KEY = os.getenv("REGISTRY_API_KEY") or os.getenv("PAYMENT_API_KEY") or ""
NETWORK = os.getenv("NETWORK", "Preprod")
AGENT_NAME = os.getenv("AGENT_NAME", "Talk To Any Person - Persona Report & Q&A (HITL)")


def load_endpoint() -> str:
    deploy_path = HERE / "aws-deployment.json"
    if deploy_path.exists():
        deploy = json.loads(deploy_path.read_text(encoding="utf-8"))
        endpoint = (deploy.get("endpoint") or "").strip()
        if endpoint:
            return endpoint.rstrip("/")
    endpoint = (os.getenv("ENDPOINT") or "").strip()
    if endpoint:
        return endpoint.rstrip("/")
    raise SystemExit("No endpoint found")


def fetch_listing(client: httpx.Client, endpoint: str) -> dict:
    url = f"{REGISTRY_API_URL.rstrip('/')}/registry"
    headers = {"token": REGISTRY_API_KEY}
    params = {"network": NETWORK, "limit": 40, "searchQuery": AGENT_NAME}
    resp = client.get(url, headers=headers, params=params)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    assets = data.get("Assets", []) if isinstance(data, dict) else []
    for a in assets:
        if not isinstance(a, dict):
            continue
        if (a.get("apiBaseUrl") or "").rstrip("/") == endpoint:
            return a
    return {}


def main() -> int:
    if not REGISTRY_API_URL:
        raise SystemExit("REGISTRY_API_URL missing")
    if not REGISTRY_API_KEY:
        raise SystemExit("REGISTRY_API_KEY missing")

    endpoint = load_endpoint()

    deadline = time.monotonic() + 180  # 3 minutes
    interval = 10

    with httpx.Client(timeout=20) as client:
        while True:
            listing = fetch_listing(client, endpoint)
            out = {
                "apiBaseUrl": endpoint,
                "found": bool(listing),
                "id": listing.get("id") if listing else None,
                "state": listing.get("state") if listing else None,
                "agentIdentifier": listing.get("agentIdentifier") if listing else None,
                "updatedAt": listing.get("updatedAt") if listing else None,
            }
            print(json.dumps(out, indent=2))

            if listing and listing.get("agentIdentifier"):
                return 0
            if time.monotonic() >= deadline:
                return 2
            time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())


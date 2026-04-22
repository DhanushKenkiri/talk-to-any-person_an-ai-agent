#!/usr/bin/env python3
"""Minimal Bedrock smoke test for Research A Person."""

from __future__ import annotations

import json

from agent.llm_client import build_bedrock_client
from config import settings


def main() -> int:
    client = build_bedrock_client()
    if not client:
        print("Bedrock client not configured. Check AWS credentials.")
        return 1

    prompt = "Reply with OK and one short sentence confirming you received this message."
    try:
        response = client.invoke_model(
            modelId=settings.BEDROCK_MODEL,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {"maxTokens": 64, "temperature": 0.0},
                }
            ),
        )
        payload = json.loads(response["body"].read())
        text = payload["output"]["message"]["content"][0]["text"]
        print(text)
        return 0
    except Exception as exc:
        print(f"Bedrock smoke test failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


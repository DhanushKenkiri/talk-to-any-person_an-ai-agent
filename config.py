import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(ENV_PATH)


@dataclass(frozen=True)
class Settings:
    # --- LLM provider selection ---
    # Supported values:
    # - openai_compatible: OpenAI-compatible HTTP API (recommended for portability)
    # - bedrock: AWS Bedrock via boto3 (optional dependency)
    # - none: disable LLM calls (fallback evidence inventory output)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai_compatible")

    # OpenAI-compatible API settings (LLM_PROVIDER=openai_compatible)
    AI_API_BASE_URL: str = os.getenv("AI_API_BASE_URL", "")
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_MODEL: str = os.getenv("AI_MODEL", "")

    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_SESSION_TOKEN: str = os.getenv("AWS_SESSION_TOKEN", "")
    BEDROCK_MODEL: str = os.getenv("BEDROCK_MODEL", "amazon.nova-pro-v1:0")

    SEARCH_RESULTS: int = int(os.getenv("SEARCH_RESULTS", "18"))
    NEWS_RESULTS: int = int(os.getenv("NEWS_RESULTS", "10"))
    SCRAPE_LIMIT: int = int(os.getenv("SCRAPE_LIMIT", "14"))
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "12"))

    USER_AGENT: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )

    PAYMENT_SERVICE_URL: str = os.getenv("PAYMENT_SERVICE_URL", "")
    PAYMENT_API_KEY: str = os.getenv("PAYMENT_API_KEY", "")
    REGISTRY_API_URL: str = os.getenv("REGISTRY_API_URL", "")
    REGISTRY_API_KEY: str = os.getenv("REGISTRY_API_KEY", "")

    SELLER_VKEY: str = os.getenv("SELLER_VKEY", "")
    AGENT_IDENTIFIER: str = os.getenv("AGENT_IDENTIFIER", "")
    NETWORK: str = os.getenv("NETWORK", "Preprod")

    AGENT_NAME: str = os.getenv("AGENT_NAME", "Talk To Any Person - Persona Report & Q&A (HITL)")
    CAPABILITY_NAME: str = os.getenv("CAPABILITY_NAME", "talktoanyperson")
    PRICE_PER_REQUEST: int = int(os.getenv("PRICE_PER_REQUEST", "5"))
    TOKEN_UNIT: str = os.getenv(
        "TOKEN_UNIT",
        "16a55b2a349361ff88c03788f93e1e966e5d689605d044fef722ddde0014df10745553444d",
    )

    ENDPOINT: str = os.getenv("ENDPOINT", "")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8080"))
    DEV_MODE: bool = os.getenv("DEV_MODE", "false").lower() in {"1", "true", "yes"}

    def has_bedrock_credentials(self) -> bool:
        return bool(self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY)


settings = Settings()




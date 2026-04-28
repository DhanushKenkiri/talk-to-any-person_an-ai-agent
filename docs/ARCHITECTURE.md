# Architecture

This agent combines web search, scraping, and LLM synthesis behind a Masumi-compatible FastAPI interface.

## High-level flow
1. `/start_job` receives purchaser identifier and `inputData`.
2. Inputs are normalized and validated (including socials URL checks).
3. `ResearchAPersonService` gathers evidence:
   - `SearchClient` runs web + news searches.
   - Results are deduplicated, blocklisted, ranked, and identity-filtered.
   - `WebScraper` fetches and cleans selected pages.
4. `llm_client` generates:
   - Persona report (summarizer)
   - Optional first-person Q&A answer (responder)
5. Output is forced to include a `Sources` section for auditability.
6. In production mode, job lifecycle runs through Masumi payment + async status monitoring.

## Runtime modes
- **DEV_MODE=true**: bypasses payment/registry and returns the result directly from `/start_job`.
- **DEV_MODE=false**: requires payment + registry settings; `/start_job` creates payment request and background execution starts after payment confirmation.

## Module responsibilities
| Module | Responsibility |
| --- | --- |
| `masumi_server.py` | API endpoints, payload normalization, HITL flow, Masumi job/payment integration |
| `agent/research.py` | Search query generation, evidence retrieval, ranking, identity guardrails |
| `agent/search_client.py` | DuckDuckGo text/news retrieval with retries and dedupe |
| `agent/web_scraper.py` | Async scraping, HTML cleanup, text extraction |
| `agent/llm_client.py` | OpenAI-compatible/Bedrock adapters, prompts, fallback behavior |
| `config.py` | Environment variable loading and typed settings |
| `register_agent.py` | Registry registration helper using `registry_payload.json` |

## Identity and evidence guardrails
- Same-name collision reduction via strict + loose identity checks.
- Domain quality weighting and blocklists to reduce low-signal sources.
- Citation tracking (`[S#]`) and post-processing to guarantee explicit source listing.
- HITL corrections (`hitl_corrections`) to update key fields without restarting jobs.

# Talk To Any Person - Persona Report & Q&A (HITL)

Masumi-compatible FastAPI agent that builds an evidence-backed persona report and supports continuous Human-in-the-Loop (HITL) follow-up Q&A.

## What this agent does
- Generates a long, citation-grounded persona report with `[S#]` references and an explicit `Sources` section.
- Answers an optional `initial_question` after report generation.
- Supports follow-up questions in the same job until the user sends a done token.
- Applies identity guardrails (same-name disambiguation, source ranking, domain filtering).
- Falls back to evidence-inventory mode when no LLM is configured.

## How the workflow behaves
1. Client submits `/start_job` with person context (`name`, `company`, `socials`).
2. Agent gathers evidence via web/news search + scraping.
3. Agent generates a report (and optional initial answer).
4. In HITL mode, the job can continue with iterative Q&A via `/provide_input`.
5. User ends conversation with one of: `DONE`, `finish`, `stop`, `exit`, `quit`.

## Repository map
| Path | Purpose |
| --- | --- |
| `masumi_server.py` | FastAPI app, job lifecycle, Masumi payment/HITL integration |
| `register_agent.py` | One-time Masumi registry registration helper |
| `config.py` | Centralized environment configuration |
| `input_schema.json` | Input schema returned by `/input_schema` |
| `registry_payload.json` | Base payload used by registration script |
| `agent/research.py` | Evidence gathering, ranking, identity filtering |
| `agent/search_client.py` | DuckDuckGo web/news search wrapper |
| `agent/web_scraper.py` | Async scraping and HTML text extraction |
| `agent/llm_client.py` | Bedrock/OpenAI-compatible prompting and fallbacks |
| `agent/types.py` | Shared dataclasses |
| `docs/` | Architecture, API, deployment, and listing documentation |

## Prerequisites
- Python 3.11+ recommended
- Network access for search/scraping and your LLM provider endpoint
- Masumi credentials only if running production flow (`DEV_MODE=false`)

## Quick start (local dev mode)
1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env`.
4. Set at minimum:
   - `DEV_MODE=true`
   - `LLM_PROVIDER=openai_compatible` (or `none`)
   - If using OpenAI-compatible mode: `AI_API_BASE_URL`, `AI_API_KEY`, `AI_MODEL`
5. Start the server:
   ```bash
   python masumi_server.py
   ```

## Required input fields
| Field | Required | Description |
| --- | --- | --- |
| `name` | Yes | Full name of the person |
| `company` | Yes | Organization context for disambiguation |
| `socials` | Yes | Comma-separated profile URLs |
| `initial_question` | No | Optional first question answered after report |

### Optional tuning fields accepted by the server
| Field | Type | Purpose |
| --- | --- | --- |
| `deep_research` | bool-like string (`true`, `1`, etc.) | Increases query breadth and scrape depth |
| `extra_queries` | Comma/semicolon/newline separated string | Adds custom search queries |
| `hitl_notes` | string | Guidance for tone/focus (not treated as evidence) |
| `hitl_corrections` | `key=value` pairs | Correct `name`, `company`, `socials`, `query` |

## API behavior notes
- `/start_job` accepts both snake_case and camelCase keys:
  - `identifier_from_purchaser` or `identifierFromPurchaser`
  - `input_data` or `inputData`
- `socials` values without scheme are normalized to `https://...`.
- `/status` accepts `job_id`, `jobId`, or `id`.
- `/provide_input` accepts `input_data` or `inputData`.

## Smoke test (DEV_MODE=true)
Start a job:

```bash
curl -s -X POST "http://localhost:8080/start_job" \
  -H "Content-Type: application/json" \
  -d '{
    "identifierFromPurchaser": "demo-user-1",
    "inputData": {
      "name": "Ada Lovelace",
      "company": "Example Corp",
      "socials": "https://en.wikipedia.org/wiki/Ada_Lovelace",
      "initial_question": "What are the strongest signals about her contributions?"
    }
  }'
```

Check status:

```bash
curl -s "http://localhost:8080/status?jobId=<JOB_ID>"
```

Send follow-up input:

```bash
curl -s -X POST "http://localhost:8080/provide_input" \
  -H "Content-Type: application/json" \
  -d '{
    "jobId": "<JOB_ID>",
    "inputData": {
      "query": "DONE"
    }
  }'
```

## LLM provider configuration
`LLM_PROVIDER` supports:
- `openai_compatible` (default, recommended)
- `bedrock`
- `none` (disables LLM calls and returns evidence inventory output)

If provider calls fail or are not configured, the agent returns fallback output based on collected evidence.

## Environment variables (summary)
Use `.env.example` as the source of truth. Most important groups:

### AI provider
- `LLM_PROVIDER`
- OpenAI-compatible: `AI_API_BASE_URL`, `AI_API_KEY`, `AI_MODEL`
- Bedrock: `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `BEDROCK_MODEL`

### Search and scrape tuning
- `SEARCH_RESULTS`
- `NEWS_RESULTS`
- `SCRAPE_LIMIT`
- `REQUEST_TIMEOUT`
- `USER_AGENT`

### Masumi integration (required for production)
- `PAYMENT_SERVICE_URL`, `PAYMENT_API_KEY`
- `REGISTRY_API_URL`, `REGISTRY_API_KEY`
- `SELLER_VKEY`
- `NETWORK`
- `AGENT_IDENTIFIER` (optional; server can resolve from registry)

### Server
- `HOST`
- `PORT`
- `DEV_MODE`
- `ENDPOINT` (used by registry registration script)

## Endpoint summary
| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/availability` | GET | Service liveness |
| `/input_schema` | GET/OPTIONS | Returns input schema JSON |
| `/start_job` | POST | Starts a job (dev immediate result / prod payment flow) |
| `/status` | GET | Retrieves job status, result, and HITL prompt |
| `/provide_input` | POST | Resumes a job when status is `AWAITING_INPUT` |

## Dev mode vs production mode
| Mode | `DEV_MODE` | Behavior |
| --- | --- | --- |
| Local/dev | `true` | Skips payment/registry and returns completed result immediately |
| Production | `false` | Uses payment + registry workflow and async job progression |

## Registry registration
If you want to register/update listing metadata in Masumi:
1. Set `ENDPOINT` to your public base URL.
2. Set registry credentials and seller vkey in `.env`.
3. Run:
   ```bash
   python register_agent.py
   ```

## Troubleshooting
- **Empty or weak output quality**: increase `SEARCH_RESULTS`, `NEWS_RESULTS`, or use `deep_research=true`.
- **No LLM-style narrative output**: verify provider config (`LLM_PROVIDER`, API keys, model).
- **Agent not found in production start**: ensure registration is complete or set `AGENT_IDENTIFIER`.
- **HITL not resuming**: call `/provide_input` only when `/status` is `AWAITING_INPUT`.
- **Bad socials input**: provide full URLs separated by commas.

## Documentation index
- Architecture and flow: `docs/ARCHITECTURE.md`
- API details and payload examples: `docs/API_REFERENCE.md`
- Production deployment and registration: `docs/DEPLOYMENT_AND_REGISTRY.md`
- Sokosumi long-form listing copy: `docs/SOKOSUMI_LISTING_COPY.md`

# Talk To Any Person - Persona Report & Q&A (HITL)

Masumi-compatible FastAPI agent that builds an evidence-backed persona report and supports continuous Human-in-the-Loop (HITL) follow-up Q&A.

## What this project does
- Generates a long, citation-grounded report (`[S#]` references + explicit `Sources` section).
- Answers an optional `initial_question` immediately after report generation.
- Keeps the job open for iterative follow-up questions until the user sends `DONE`.
- Handles missing/invalid required fields through HITL correction prompts.

## Repository map
| Path | Purpose |
| --- | --- |
| `masumi_server.py` | FastAPI app and Masumi workflow endpoints |
| `register_agent.py` | One-time Masumi registry registration helper |
| `config.py` | Centralized environment configuration |
| `input_schema.json` | Input schema returned by `/input_schema` |
| `registry_payload.json` | Base payload used by registration script |
| `agent/research.py` | Evidence gathering, ranking, and identity matching |
| `agent/search_client.py` | DuckDuckGo web/news search wrapper |
| `agent/web_scraper.py` | Async scraper and HTML text extraction |
| `agent/llm_client.py` | Bedrock/OpenAI-compatible prompting and fallbacks |
| `agent/types.py` | Shared dataclasses |
| `docs/` | Architecture, API, deployment, and listing documentation |

## Quick start (local)
1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set values.
4. For local testing, set `DEV_MODE=true`.
5. Start server:
   ```bash
   python masumi_server.py
   ```

## Smoke test
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

Check job status:

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

## Configuration summary
- `LLM_PROVIDER=openai_compatible` (recommended), `bedrock`, or `none`.
- `DEV_MODE=true` bypasses payment/registry and returns completed results immediately.
- In production (`DEV_MODE=false`), set payment + registry env vars (see deployment doc).

Use `.env.example` as the authoritative variable list.

## Endpoint summary
| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/availability` | GET | Service liveness |
| `/input_schema` | GET/OPTIONS | Returns input schema JSON |
| `/start_job` | POST | Starts a job (dev immediate result / prod payment workflow) |
| `/status` | GET | Retrieves job status/result/HITL prompt |
| `/provide_input` | POST | Resumes job when in `AWAITING_INPUT` |

## Documentation index
- Architecture and flow: `docs/ARCHITECTURE.md`
- API details and payload examples: `docs/API_REFERENCE.md`
- Production deployment and registration: `docs/DEPLOYMENT_AND_REGISTRY.md`
- Sokosumi long-form listing copy: `docs/SOKOSUMI_LISTING_COPY.md`

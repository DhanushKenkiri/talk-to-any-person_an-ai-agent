# PersonaSignal Nova v17

Fresh deployment codebase for a clean v17 agent instance (uses v15 env config values).

## Run locally
1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and fill credentials.
4. Start server: `python masumi_server.py`.

## Required checks
- `GET /availability` returns status available.
- `GET /input_schema` returns JSON schema.
- `POST /start_job` accepts Sokosumi payload format:
  - `identifierFromPurchaser`
  - `inputData`
- `GET /status` returns transaction aliases even before payment confirmation.

## AWS deploy flow
Use AWS CLI from this directory and launch a new EC2 instance tagged `sokosumi-agent-v17`.
After deploy:
- Set `.env` `ENDPOINT` to the new public endpoint.
- Set `registry_payload.json` `apiBaseUrl` to the same endpoint.
- Register via `POST {REGISTRY_API_URL}/registry` with `token` header.
- Put returned `agentIdentifier` into `.env` and restart service.


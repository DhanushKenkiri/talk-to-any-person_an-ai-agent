# Deployment and Registry

## 1) Environment setup
Copy `.env.example` to `.env`, then set:

### Required for production (`DEV_MODE=false`)
- `PAYMENT_SERVICE_URL`
- `PAYMENT_API_KEY`
- `REGISTRY_API_URL`
- `REGISTRY_API_KEY`
- `SELLER_VKEY`
- `NETWORK` (for example: `Preprod`)
- LLM settings (`LLM_PROVIDER` + provider-specific credentials)

### Important optional values
- `AGENT_IDENTIFIER`: if empty, server attempts registry lookup by `AGENT_NAME + apiBaseUrl`.
- `ENDPOINT`: required by `register_agent.py` when registering.

## 2) Run the service
```bash
python masumi_server.py
```

## 3) Register agent in Masumi registry (optional helper script)
`register_agent.py` uses `registry_payload.json` and overrides:
- `apiBaseUrl` from `ENDPOINT`
- `network` from `NETWORK`
- `sellingWalletVkey` from `SELLER_VKEY` (if present)

Run:
```bash
python register_agent.py
```

## 4) Verify post-deployment endpoints
- `GET /availability`
- `GET /input_schema`
- `POST /start_job`
- `GET /status?jobId=<JOB_ID>`
- `POST /provide_input`

## Registry notes
- Registry `description` field has a strict short length limit; keep listing payload concise.
- Use `docs/SOKOSUMI_LISTING_COPY.md` for long-form storefront copy.

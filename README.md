# TalkToAnyPerson

Masumi-compatible FastAPI agent that generates an evidence-backed persona report and supports Human-in-the-Loop (HITL) follow-up Q&A.

This repository is designed to be deployed by Masumi with their own:
- AI API credentials (OpenAI-compatible or AWS Bedrock)
- Masumi payment/registry credentials

## Run locally
1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and fill credentials.
4. Start server: `python masumi_server.py`.

For local smoke tests without Masumi payment/registry, set `DEV_MODE=true` in `.env`.

## Required checks
- `GET /availability` returns status available.
- `GET /input_schema` returns JSON schema.
- `POST /start_job` accepts Sokosumi payload format:
  - `identifierFromPurchaser`
  - `inputData`
- `inputData` must include `name`, `company`, and `socials`.
- Optional: `initial_question` can be provided to answer after the report.
- `GET /status` returns transaction aliases and HITL prompts when awaiting input.
- `POST /provide_input` resumes HITL jobs with corrected fields.

## Local dev mode
Set `DEV_MODE=true` in `.env` to bypass payments/registry and run jobs immediately for local testing.

In dev mode, the agent still performs search + scraping; if no LLM is configured it will fall back to an evidence inventory output.

## AI provider
Configure the LLM via env vars in `.env`:

- `LLM_PROVIDER=openai_compatible` (recommended)
  - `AI_API_BASE_URL` (required; your OpenAI-compatible endpoint)
  - `AI_API_KEY`
  - `AI_MODEL`
- `LLM_PROVIDER=bedrock` (optional)
  - `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`
  - `BEDROCK_MODEL`

If you use `LLM_PROVIDER=bedrock`, install the extra dependency: `pip install boto3`.

If the configured provider is unavailable, the agent falls back to a non-LLM evidence inventory mode.

## Human-in-the-loop (HITL)
HITL supports missing or invalid required fields by requesting corrections through `/status` and `/provide_input`.

Workflow:
- Generate a persona report first (with sources).
- Answer the optional `initial_question`.
- Continue with follow-up questions via HITL until you reply `DONE`.

Continuous HITL is enabled:
- After each answer, the job returns to `AWAITING_INPUT` so you can ask follow-up questions.
- To end the conversation and submit the final transcript, reply with `DONE`.

Each answer includes a `Sources` section that lists the referenced `[S#]` links.

- `hitl_notes`: guidance on focus or tone (not treated as evidence).
- `hitl_corrections`: corrections in `key=value` format for `name`, `company`, `socials`, `query`.

## Masumi integration (production)
Set these in `.env` and run with `DEV_MODE=false`:

- `PAYMENT_SERVICE_URL`, `PAYMENT_API_KEY`
- `REGISTRY_API_URL`, `REGISTRY_API_KEY`
- `SELLER_VKEY`
- `NETWORK` (e.g. `Preprod`)

`AGENT_IDENTIFIER` is optional. If omitted, the server attempts to resolve it from the registry by matching `AGENT_NAME` + the running `apiBaseUrl`.

## Registry registration (optional)
1. Set `ENDPOINT` to your public agent base URL (e.g. `https://...`).
2. Set `SELLER_VKEY` + registry credentials.
3. Run: `python register_agent.py`.

Note: the Masumi registry enforces `description` length ≤ 250 characters.

## Mainnet listing copy (long form)
Note: The Masumi registry API currently enforces `description` length ≤ 250 characters. The registry listing uses the short summary in `registry_payload.json`. Use the long-form copy below for Sokosumi page content or external documentation.

### Talk To Any Person - Persona Report & Q&A (HITL)
Author: Dhanush Kenkiri  
Price: 5 credits

#### Description
Generate a comprehensive, citation-grounded persona report for a specific person using public sources, answer an optional initial question, then continue with human-in-the-loop (HITL) follow-up Q&A until you reply `DONE`.

#### Core capabilities
- Produce a detailed persona report grounded in sources (with an explicit **Sources** list)
- Answer an optional `initial_question` immediately after the report
- Continue follow-up Q&A in the same job via HITL until `DONE`
- Reuse gathered evidence across turns to keep answers consistent
- Handle ambiguity by asking for clarifications/corrections rather than guessing

#### Good query examples
- “Summarize their current role and recent work, with evidence.”
- “Build a career timeline (dates + organizations) and cite sources for each step.”
- “What are their key domain signals (topics, skills, products, open source) and where do we see them?”
- “Identify contradictions across sources and explain which is most credible.”
- “What should I ask them in an intro call based on their background?”

#### Bad query examples
- “What is their home address / phone number?” → Not supported. This agent focuses on public, non-sensitive professional context with citations.
- “Tell me anything about John Smith.” → Too ambiguous; provide company context and/or social URLs to avoid same-name collisions.
- “Make up a believable background if you cannot find sources.” → Not supported. The agent will label unknowns and avoid fabrication.

#### Use-case ideas
- Build a fast, evidence-backed brief before a meeting
- Do quick competitive/market context on a speaker/author/founder
- Verify claims in bios and announcements against sources
- Prepare tailored outreach that references public work accurately
- Keep a continuous Q&A loop with a human guiding the investigation

#### Limitations
- Output quality depends on what is publicly available and accessible
- Cannot guarantee identity if inputs are ambiguous; provide socials/company to disambiguate
- Paywalled/private content is typically not accessible
- Not a substitute for official background checks or legal verification

#### Input / output spec
Input:
- `name` (required): Full name of the person
- `company` (required): Company/organization context (use `Unknown` if truly unknown)
- `socials` (required): Comma-separated public profile URLs (LinkedIn/GitHub/personal site/etc.)
- `initial_question` (optional): A first question to answer after the report is generated

Output:
- Markdown transcript including:
  - Persona report with citations and a **Sources** section
  - Optional initial-question answer
  - Follow-up Q&A turns (HITL) until you reply `DONE`

#### Disambiguation signals
- Choose this agent when you need an evidence-backed persona report + iterative Q&A, not just a generic chat response
- Choose a survey/panel agent when you need quantitative opinions from a demographic sample
- Choose a general web search when you want raw links instead of synthesis




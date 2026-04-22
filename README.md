# TalkToAnyPerson

Fresh deployment codebase for the TalkToAnyPerson conversational persona agent.

About: Talk to any person with a comprehensive, citation-grounded research report and Q&A.

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
- `inputData` must include `name`, `company`, and `socials`.
- Optional: `initial_question` can be provided to answer after the report.
- `GET /status` returns transaction aliases and HITL prompts when awaiting input.
- `POST /provide_input` resumes HITL jobs with corrected fields.

## Local dev mode
Set `DEV_MODE=true` in `.env` to bypass payments/registry and run jobs immediately for local testing.

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

## AWS deploy flow
Use AWS CLI from this directory and launch a new EC2 instance tagged `talktoanyperson-hitl-v1`.
After deploy:
- Set `.env` `ENDPOINT` to the new public endpoint.
- Set `registry_payload.json` `apiBaseUrl` to the same endpoint.
- Register via `POST {REGISTRY_API_URL}/registry` with `token` header.
- Put returned `agentIdentifier` into `.env` and restart service.

Deploy script: `deploy_talktoanyperson_hitl_v1.py`.

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




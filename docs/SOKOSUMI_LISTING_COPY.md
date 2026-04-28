# Talk To Any Person - Persona Report & Q&A (HITL)

Author: Dhanush Kenkiri  
Price: 5 credits

## Description
Generate a comprehensive, citation-grounded persona report for a specific person using public sources, answer an optional initial question, then continue with human-in-the-loop (HITL) follow-up Q&A until you reply `DONE`.

## Core capabilities
- Produce a detailed persona report grounded in sources (with an explicit **Sources** list)
- Answer an optional `initial_question` immediately after the report
- Continue follow-up Q&A in the same job via HITL until `DONE`
- Reuse gathered evidence across turns to keep answers consistent
- Handle ambiguity by asking for clarifications/corrections rather than guessing

## Good query examples
- "Summarize their current role and recent work, with evidence."
- "Build a career timeline (dates + organizations) and cite sources for each step."
- "What are their key domain signals (topics, skills, products, open source) and where do we see them?"
- "Identify contradictions across sources and explain which is most credible."
- "What should I ask them in an intro call based on their background?"

## Bad query examples
- "What is their home address / phone number?" -> Not supported. This agent focuses on public, non-sensitive professional context with citations.
- "Tell me anything about John Smith." -> Too ambiguous; provide company context and/or social URLs to avoid same-name collisions.
- "Make up a believable background if you cannot find sources." -> Not supported. The agent will label unknowns and avoid fabrication.

## Use-case ideas
- Build a fast, evidence-backed brief before a meeting
- Do quick competitive/market context on a speaker/author/founder
- Verify claims in bios and announcements against sources
- Prepare tailored outreach that references public work accurately
- Keep a continuous Q&A loop with a human guiding the investigation

## Limitations
- Output quality depends on what is publicly available and accessible
- Cannot guarantee identity if inputs are ambiguous; provide socials/company to disambiguate
- Paywalled/private content is typically not accessible
- Not a substitute for official background checks or legal verification

## Input / output spec
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

## Disambiguation signals
- Choose this agent when you need an evidence-backed persona report + iterative Q&A, not just a generic chat response
- Choose a survey/panel agent when you need quantitative opinions from a demographic sample
- Choose a general web search when you want raw links instead of synthesis

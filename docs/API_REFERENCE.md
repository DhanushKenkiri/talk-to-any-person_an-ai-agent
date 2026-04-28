# API Reference

Base URL is your running server (default local: `http://localhost:8080`).

## GET `/availability`
Returns service health metadata.

**Example response**
```json
{
  "status": "available",
  "type": "masumi-agent",
  "message": "Server operational"
}
```

## GET `/input_schema`
Returns the schema from `input_schema.json`.

## OPTIONS `/input_schema`
CORS-friendly schema access for UI clients.

## POST `/start_job`
Starts a new job.

### Accepted payload keys
- `identifier_from_purchaser` or `identifierFromPurchaser`
- `input_data` or `inputData`

`inputData` required fields:
- `name` (string, required)
- `company` (string, required)
- `socials` (comma-separated URL string, required)

Optional:
- `initial_question`
- `deep_research` (`true/false` style string)
- `extra_queries` (comma/semicolon/newline separated string)
- `hitl_notes`
- `hitl_corrections` (`key=value` pairs for `name/company/socials/query`)

### DEV mode behavior
When `DEV_MODE=true`, `/start_job` returns a completed result directly.

### Production behavior
When `DEV_MODE=false`, `/start_job` creates payment workflow state and returns job/payment metadata.

## GET `/status`
Query parameters:
- `job_id`, `jobId`, or `id`

Returns:
- job status
- result/error if available
- HITL input schema + message when status is `AWAITING_INPUT`
- transaction aliases (multiple key names for compatibility)

## POST `/provide_input`
Resumes a job in `AWAITING_INPUT`.

Required:
- `job_id` or `jobId` or `id`
- `input_data` or `inputData` object matching the awaiting schema

Returns:
```json
{
  "input_hash": "<hash>",
  "signature": ""
}
```

## HITL loop semantics
- Agent asks follow-up question input via schema field `query`.
- User can continue asking questions indefinitely.
- Sending `DONE` (or `finish/stop/exit/quit`) ends the loop and finalizes transcript.

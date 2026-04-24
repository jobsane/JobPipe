# JobPipe MCP Server — Architecture Proposal

**Status:** Proposal v1 (2026-04-24). Not yet implemented.
**Owner:** Lars / JobPipe orchestrator
**Scope:** Expose JobPipe pipeline controls and data reads as an MCP server so external
agents (CrewAI Job Hunter crew, Claude Desktop, future apps) can call JobPipe as a tool.

---

## 1. Why this makes sense

JobPipe currently runs as a local CLI. The Job Hunter crew (CrewAI) consumes its output
via static files (`calibration/*.json`, `profile_pack.md`). That's a one-way, polling
relationship — the crew can't trigger a run, check live status, or fetch the current
KEEP pile without Lars in the middle.

An MCP server changes this: JobPipe becomes a **callable service**. Any MCP-compatible
client can:
- Ask "what's in the queue right now?"
- Trigger a cheap FINN keyword pull for a specific role
- Get the current APPLY/REVIEW pile to act on
- Check whether a calibration pass is needed
- Run the full pipeline on a small batch

This is the right abstraction. MCP is already the integration layer Claude Desktop,
Cursor, and CrewAI use for tool calls. No new protocol needed.

---

## 2. Proposed MCP tools

### Status and reads (cheap — no network, no LLM)

**`jobpipe_status`**
Returns current pipeline state: queue depth, last run timestamp, decision breakdown
(SKIP/REVIEW_LOW/REVIEW_HIGH/APPLY counts), calibration artifact path.
```json
{
  "queue_depth": 10840,
  "last_run_at": "2026-04-24T09:20:00Z",
  "last_run_jobs": 440,
  "decisions": { "APPLY": 1, "REVIEW_LOW": 5, "SKIP": 1299 },
  "calibration_artifact": "calibration/2026-04-24_n440.json"
}
```

**`jobpipe_get_keeps`**
Returns all jobs with `final_decision` = APPLY or REVIEW_* from the DB.
Optionally filter by decision type, date range, or employer.
This is the primary tool for the CrewAI crew — it replaces polling the DB directly.

**`jobpipe_get_calibration`**
Returns the latest calibration artifact JSON (or a specific one by batch_id).
Replaces the crew reading `calibration/*.json` off disk.

**`jobpipe_get_job`**
Returns full pipeline artifacts for a specific `job_id` — triage, parsed, profile_match,
pivot, application_pack JSON blobs. Allows the crew to inspect a job deeply before
drafting a cover letter.

---

### Pull triggers (network, no LLM cost)

**`jobpipe_pull_nav`**
Triggers a NAV sheet pull. Parameters: `status_filter` (default ACTIVE),
`skip_expired_deadline` (default true), `reset_state` (default false).
Returns row count written to delta.

**`jobpipe_pull_finn`**
Triggers a FINN keyword search pull. Parameters: `queries` (list of search strings,
overrides YAML defaults), `max_fetch` (default 40), `dry_run` (default false).
Returns list of new finnkodes found.

**`jobpipe_pull_suggested`**
Triggers the FINN suggested / Gmail leads pull. Parameters: `max` (default 20).
Returns count fetched.

---

### Pipeline run (LLM cost — nano/mini models)

**`jobpipe_run_pipeline`**
Runs `drain_queue` with specified parameters. This is the expensive call.
Parameters: `batch_size` (default 100), `max_loops` (default 1), `no_skip_processed`
(default false), `overwrite` (default false).
Returns: jobs processed, decision breakdown, artifact paths.

Important constraints:
- Should be async / long-running aware — pipeline takes 15–90 min depending on batch
- Should require explicit confirmation before running (destructive to queue state)
- Rate-limit: only one pipeline run at a time

---

### Write operations (escalate before calling)

**`jobpipe_add_override`**
Appends a Lars override to `calibration/overrides.jsonl`. Parameters: `job_id`,
`title`, `employer`, `override` (SKIP/APPLY/REVIEW_LOW/REVIEW_HIGH), `note`.
This is how the crew can record Lars's decisions without file access.

**`jobpipe_update_profile_pack`** *(Phase 5 — not now)*
Proposes a diff to `profile_pack.md`. Lars approves before it's written.

---

## 3. Implementation approach

**Language:** Python. The MCP server wraps the existing CLI modules as library calls
(not subprocess) — import and call `main()` directly, or refactor the CLI modules to
expose a clean `run(**kwargs) -> dict` API.

**Transport:** stdio MCP (same as most Claude Desktop MCPs). No HTTP server needed
for local use. If CrewAI needs remote access, wrap in SSE transport later.

**Auth:** None for local stdio. If exposed over network, simple API key in env.

**State:** The MCP server is stateless — each tool call invokes the underlying Python
function and returns the result. No persistent MCP server process needed (Claude
Desktop respawns it per session anyway).

**Suggested file layout:**
```
jobpipe/
  mcp/
    __init__.py
    server.py          # MCP server entry point (stdio)
    tools/
      status.py        # jobpipe_status, jobpipe_get_keeps, jobpipe_get_calibration
      pulls.py         # jobpipe_pull_nav, jobpipe_pull_finn, jobpipe_pull_suggested
      pipeline.py      # jobpipe_run_pipeline
      overrides.py     # jobpipe_add_override
```

**Entry point in pyproject.toml / setup:**
```toml
[project.scripts]
jobpipe-mcp = "jobpipe.mcp.server:main"
```

**Claude Desktop config (`claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "jobpipe": {
      "command": "python",
      "args": ["-m", "jobpipe.mcp.server"],
      "cwd": "C:\\Users\\larsv\\Jobpipe-orchestrator-v2",
      "env": { "JOBPIPE_ENV_FILE": "C:\\Users\\larsv\\Jobpipe\\.env" }
    }
  }
}
```

---

## 4. CrewAI integration

CrewAI can consume MCP tools natively via its MCP tool adapter (CrewAI 0.80+).
The crew would connect to the JobPipe MCP server and get access to the tool set above.

Typical crew usage pattern:
1. `jobpipe_status` → check if new KEEP pile exists since last run
2. `jobpipe_get_keeps` → fetch APPLY/REVIEW jobs
3. `jobpipe_get_job(job_id)` → fetch full artifacts for a specific job before drafting
4. `jobpipe_add_override(...)` → record Lars's decision after review
5. `jobpipe_get_calibration` → read latest calibration artifact for profile_pack diff review
6. `jobpipe_pull_finn(queries=["produkteier Oslo"])` → cheap on-demand lead search

The crew does NOT need `jobpipe_run_pipeline` in normal operation — Lars controls
when the pipeline runs. The crew is a consumer, not a driver, until Phase 5.

---

## 5. Risks and constraints

| Risk | Mitigation |
|---|---|
| `jobpipe_run_pipeline` costs real money (LLM calls) | Require explicit `confirm=true` parameter; log cost estimate before running |
| FINN anti-bot time guard | Enforce in tool layer, return error if outside 09:00–19:00 Oslo |
| MCP server path/env mismatch on different machines | Bake env file path into server config; document clearly |
| CrewAI calling destructive ops | `update_profile_pack` gated behind Lars approval flow; overrides are append-only |
| Long-running pipeline run blocking MCP session | Return a run_id immediately, expose `jobpipe_run_status(run_id)` for polling |

---

## 6. Sequencing

This is Phase 4–5 work. Current priority is completing the staged ingest calibration.

Suggested order:
1. ✅ Now: complete staged ingest, calibration artifacts, crew-calibration-contract
2. **Next:** implement read-only tools first (`status`, `get_keeps`, `get_calibration`,
   `get_job`) — zero risk, immediate value for CrewAI
3. Then: pull triggers (`pull_nav`, `pull_finn`)
4. Last: `run_pipeline` with confirmation gate and async status polling

The read-only tools can be a one-day implementation — the data is already in the DB
and calibration JSON files. Wrapping them in MCP is straightforward.

---

## 7. Open questions

1. Should `jobpipe_run_pipeline` be async (return run_id, poll for result) or
   synchronous with a long timeout? CrewAI's MCP adapter may not handle 90-min calls well.
2. CrewAI version — does your crew's CrewAI version support MCP tool adapters natively,
   or does it need a custom `BaseTool` wrapper around the MCP client?
3. Should the MCP server live in the `Jobpipe-orchestrator-v2` worktree (orchestrator
   concern) or the main `Jobpipe` repo (core infra)? Probably core infra — it's a
   runtime capability, not an orchestration script.

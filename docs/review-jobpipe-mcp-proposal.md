# Review — JobPipe MCP Proposal + Connectors Reference

**Reviewer:** Job hunter crew side (Lars via crew assistant)
**Date:** 2026-04-24
**Reviewed documents:**
- `docs/jobpipe-mcp-proposal.md` (v1, 212 lines)
- `docs/jobpipe-connectors.md` (v1, 179 lines)
**Verdict:** Approve direction. Three blocking concerns, several design refinements.

---

## 1. Summary

The MCP abstraction is correct. Read-only-first sequencing is correct. The four-connector
model in `jobpipe-connectors.md` is a clean reference document and can ship as-is.

The MCP proposal has the right shape but under-specifies three things that will cause
pain if built as drafted: cost-gating, filesystem-vs-MCP truth ownership, and async
run semantics. Fix these before implementation starts.

---

## 2. Approved as drafted

- **Section 2 read-only tools** (`jobpipe_status`, `jobpipe_get_keeps`,
  `jobpipe_get_calibration`, `jobpipe_get_job`). Clean. Zero risk. One-day build.
  Ship first, independently of the rest.
- **Section 2 pull triggers** (`jobpipe_pull_nav`, `jobpipe_pull_finn`,
  `jobpipe_pull_suggested`). Correct scope, correct parameter surface.
- **Section 3 implementation approach.** Python stdio, stateless, import-not-subprocess.
  All correct choices.
- **Section 5 risk table.** FINN anti-bot time guard at tool layer is right.
- **Section 6 sequencing.** Order is sensible.
- **`jobpipe-connectors.md` in full.** Accurate current-state documentation,
  well structured, no edits needed. Only small request: add a "MCP tool mapping"
  column to the §"Which connector to use when" table so readers can see
  `pull-sheets` → `jobpipe_pull_nav`, etc. in one glance.

---

## 3. Blocking concerns (fix before build)

### 3.1 Filesystem artifacts stay canonical — MCP is a view

The proposal reads as if MCP tools *replace* file reads. Section 1 even says
the crew will "fetch the current KEEP pile without Lars in the middle" via
MCP instead of static files.

This is the wrong mental model for calibration artifacts specifically.
`calibration/*.json` and the crew-calibration-contract assume files are the
authoritative record — git-trackable, diffable, debuggable without a server
running. If MCP becomes the source of truth, we lose all of that.

**Fix:** Add explicit architectural principle to §1:

> Filesystem artifacts in `calibration/` and `profile_pack.md` remain
> canonical. MCP tools (`jobpipe_get_calibration`, `jobpipe_get_keeps`)
> are a live-access layer over the same data — they do not replace the
> filesystem record. Any tool that *writes* state (overrides, profile_pack
> diffs) writes to both the DB/JSONL and the corresponding file, so the
> filesystem remains the single source of truth for review and git history.

This matters because a crew-side `calibrate` task needs the human-readable
MD sibling for Lars to review. An MCP response that returns only JSON
forces the crew to re-render review context that already exists on disk.

### 3.2 `jobpipe_run_pipeline` needs a cost-estimate pre-tool

§2 says `run_pipeline` should "log cost estimate before running". That's not
enough when the caller is an autonomous agent. Agents don't read logs — they
call tools and act on returned values.

**Fix:** Add a companion tool:

```
jobpipe_estimate_run_cost(batch_size, max_loops) → {
  estimated_usd: 0.42,
  estimated_duration_min: 18,
  jobs_to_process: 100,
  model_breakdown: { "triage": "nano", "parse": "nano", "profile_match": "mini" }
}
```

Crew calls `estimate_run_cost` first, shows Lars, then `run_pipeline` with
`confirm=true` only after approval. Without this, `confirm=true` is a rubber
stamp with no numbers attached.

### 3.3 Async `run_pipeline` — spec the full pattern, not just "return run_id"

§5 row 5 says "return a run_id immediately, expose `jobpipe_run_status(run_id)`
for polling". Good instinct, but not enumerated in §2.

**Fix:** Add to §2 as first-class tools:

```
jobpipe_run_pipeline(batch_size, max_loops, confirm) → { run_id, status: "queued" }
jobpipe_run_status(run_id)   → { status, progress, decisions_so_far, eta_min }
jobpipe_run_cancel(run_id)   → { cancelled: bool, note }
```

Three tools, not one. Otherwise crews will hang on the synchronous version
or poll `jobpipe_status` and guess at "is this the run I started".

Also specify: what happens if crew disconnects mid-run? Run continues
server-side? Is `run_id` persisted across MCP-server respawns (Claude Desktop
restarts its stdio server)? If not, crew loses track of its own run.

**Recommend:** persist `run_id` → run-state mapping to a small JSON file in
`runs/` so server respawns can resume tracking.

---

## 4. Design refinements (not blocking)

### 4.1 `jobpipe_add_override` semantics

§2 "Write operations" lists `jobpipe_add_override` as Phase 1 scope. OK,
but think about replay semantics:

- If the same `job_id` gets an override twice (Lars changes his mind), does
  the JSONL append both or replace? Append is simpler; replace requires
  re-reading the file. Suggest: append-only, last-write-wins on read.
- Should overrides trigger any re-scoring downstream, or are they pure
  log entries for calibration feedback?

Document the intended semantics explicitly in the tool description so the
crew can design around it.

### 4.2 `jobpipe_update_profile_pack` is correctly deferred

§2 marks this as Phase 5. Good — it should not be a callable tool from the
crew until the human-in-the-loop diff approval flow is designed. Keep it
deferred.

When it does land, the write shape should be:

```
jobpipe_propose_profile_pack_diff(section, before, after, reason) →
  { diff_id, path_to_diff_file }
```

Lars reviews the diff file, runs a separate `apply` CLI (not an MCP tool)
to commit. This keeps profile_pack write authority explicitly out of
autonomous-agent reach.

### 4.3 Tool namespace — prefix consistency

All tools prefixed `jobpipe_*`. Good. Consider sub-prefixes for
discoverability: `jobpipe_read_*`, `jobpipe_pull_*`, `jobpipe_run_*`,
`jobpipe_write_*`. Agents use tool names to predict behavior; hierarchical
prefixes reduce the chance of calling `run_pipeline` when they meant
`get_keeps`.

### 4.4 `jobpipe_get_keeps` — pagination and filter parameters

Not specified. If crew filter is APPLY only, batch size is small. If
REVIEW_* included, could be thousands. Default should be APPLY only,
opt-in for REVIEW_*. Add explicit `limit` and `offset` (or cursor) params
to avoid accidental 10k-row returns.

### 4.5 `jobpipe_get_job` — explicit artifact selection

§2 says it returns "triage, parsed, profile_match, pivot, application_pack
JSON blobs." That's a lot per job. Let crew request specific artifacts:

```
jobpipe_get_job(job_id, include=["triage", "profile_match"]) → { ... }
```

Otherwise crew pulls 50 KB per job when it only wanted the triage verdict.

### 4.6 CrewAI version question (§7 q2)

This is the critical unknown. CrewAI MCP adapter support varies by version.
If the crew's CrewAI doesn't support MCP natively, the crew side needs a
`BaseTool` wrapper per MCP tool — multiplies integration cost.

**Recommend:** before building MCP server, confirm crew's CrewAI version
and test MCP adapter with a single stub tool (`ping`). Don't build the full
server then discover adapter mismatch.

### 4.7 Worktree vs core-repo location (§7 q3)

Agree with the instinct that MCP server belongs in the main `Jobpipe` repo,
not the orchestrator worktree. Orchestrator worktree is planning/state;
MCP is runtime capability. This also keeps the MCP surface stable across
worktree churn.

---

## 5. What's missing

### 5.1 No write-back path from crew → JobPipe

Proposal is consumer-side-only. Eventually the crew will emit application
outcomes (interview rate, rejection reasons, silence rate) that should
feed calibration. Proposal should at least name this as Phase N:

```
Phase N — Write-back tools (after crew Phase 5)
  jobpipe_record_application_outcome(job_id, outcome, date, note)
  jobpipe_record_voice_feedback(job_id, voice_match_score, notes)
```

Doesn't need to be designed now, but should be listed so the architecture
leaves room for it.

### 5.2 No auth / audit roadmap

§3 says "No auth for local stdio. If exposed over network, simple API key".
Fine for now. But if MCP server is ever shared across machines or exposed
to a remote crew runner, need:

- Token-based auth
- Audit log of every tool call (tool name, params, caller, timestamp)
- Rate limits on `run_pipeline` (max 1/hour regardless of caller)

Flag as Phase N, don't build now.

### 5.3 No versioning story

MCP tool signatures will change. How does the crew know which version
it's talking to? Add:

```
jobpipe_server_info() → { version, api_version, tools_available }
```

Crew calls this once on connection and adapts behavior to available tools.

### 5.4 Error contract

No mention of error shapes. Each tool should document its error modes:
- `jobpipe_pull_finn` outside 09:00-19:00 → what error code?
- `jobpipe_run_pipeline` when another run is in progress → rejected, queued, or error?
- `jobpipe_get_job` with unknown job_id → empty or error?

Specify in tool descriptions. Agents can't handle what they can't detect.

---

## 6. Recommended sequencing (revised)

Proposal §6 is close, but I'd insert a validation step:

| Step | What | Owner |
|---|---|---|
| 0 | Filesystem calibration contract active, crew consuming artifact files | Both |
| 1 | **Validate** CrewAI MCP adapter with `ping` stub server | Orchestrator + crew |
| 2 | Read-only tools (`status`, `get_keeps`, `get_calibration`, `get_job`, `server_info`) with pagination + filters | Orchestrator |
| 3 | Crew migrates file-reading to MCP tool calls, filesystem remains canonical | Crew |
| 4 | Pull triggers (`pull_nav`, `pull_finn`, `pull_suggested`) | Orchestrator |
| 5 | Write: `add_override` + documented replay semantics | Orchestrator |
| 6 | Async run: `estimate_run_cost` → `run_pipeline` → `run_status` → `run_cancel` | Orchestrator |
| 7 | Phase 5+: profile_pack diff propose/apply, write-back tools | Both |

Step 1 is the blocker nobody has answered. Do it first.

---

## 7. Open questions back to orchestrator

1. **MCP adapter validation** — can you stand up a trivial `ping` MCP server
   and have the crew's CrewAI instance call it? This answers §7 q2 and
   de-risks everything downstream. Suggest a half-day spike.
2. **Run persistence** — where does `run_id` state live across MCP server
   respawns? (See §3.3 above.)
3. **Artifact co-location** — will `jobpipe_add_override` write to *both*
   DB and `calibration/overrides.jsonl`, or just one? (See §3.1 truth principle.)
4. **Cost estimates** — is there existing per-stage cost telemetry we can
   use for `jobpipe_estimate_run_cost`, or does that require new
   instrumentation? If new, flag in plan.

---

## 8. Bottom line

Green light on direction. Merge the proposal with the three blocking fixes
and 4.1–4.7 refinements, then start Phase 1 validation. Filesystem contract
from `crew-calibration-contract.md` stays canonical regardless of MCP
implementation timing — don't let MCP build become an excuse to skip
filesystem-artifact discipline.

---

## 9. Change log

- **2026-04-24 v1** — Initial review by crew side.

# T001 Slice 1 — Inspect persisted claim layer

Status: **approved by coordinator 2026-04-21 — handed off to Codex on `codex/job-catalog-foundation-v2`.** Tracked on
[GitHub Project #6](https://github.com/users/larsvaerland/projects/6) as draft
item `PVTI_lAHOCSFbLc4BJUdazgqjqHU`.

Owning planning file: [../docs/execplans/T001.md](../docs/execplans/T001.md)
(see §"Decomposition — Slice 1").

This spec is the design detail companion for the first decomposed slice of
T001 "Job Catalog Foundation". It is intentionally small.

## One-sentence objective

Extend the existing `inspect-db` CLI with three read-only views
(`job_claims`, `job_selection_signals`, `job_selection_assessments`) and an
optional `--job-id` filter, so the already-persisted claim and selection layer
becomes auditable from the operator console without any schema, extractor, or
pipeline change.

## Why this slice is first

- `PRODUCT_VISION.md` lists `job claims` as the near-term foundation item 1.
- The claim layer is already modeled and persisted:
  - pydantic models in `jobpipe/decision/models.py`
    (`JobClaim`, `JobSelectionSignal`, `JobSelectionAssessment`)
  - DB tables in `jobpipe/core/primary_db.py`
    (`job_claims`, `job_selection_signals`, `job_selection_assessments`
    around lines 386–475)
  - deterministic derivation in `jobpipe/decision/derive.py`
    (`derive_job_claims`, `derive_selection_signals`,
    `derive_selection_assessment`, `build_decision_context`)
  - write path in `jobpipe/decision/persistence.py`
    (`replace_job_claims` etc., invoked via `sync-evaluations`)
- The remaining gap in `specs/job-claims-model.md` §"First implementation
  slice" item 7 is *"inspection output so the extracted claims can be
  audited"*. That gap is also the cheapest candidate-first, local-first
  step to make the foundation legible to the operator, which is a direct
  `Now` priority on `ROADMAP.md` (public loop hardening / dashboard
  trustworthiness).
- The change does not touch schema, extractor, writer, pipeline semantics,
  auth, billing, deploy, secrets, or the OSS/Workbench boundary, which
  matches `CLAUDE.md` escalation rules and `DEPENDENCY_POLICY.md`.

## Design

### Scope

Only the existing `inspect-db` CLI is modified. That CLI is already:

- registered as `inspect-db` in `jobpipe/cli/main.py` via `MODULE_COMMANDS`
- implemented in `jobpipe/cli/inspect_primary_db.py`
- using stdlib only: `argparse`, `sqlite3`, `json`, `io`, `sys`
- connecting through `connect_primary_db` and reading rows via a common
  `_rows` helper

Three new view helpers are added following the existing pattern:

| Helper | Reads | Notes |
|---|---|---|
| `_job_claims_view(conn, *, job_id, limit)` | `job_claims` | Default order: `importance_score DESC, updated_at DESC`. |
| `_job_selection_signals_view(conn, *, job_id, limit)` | `job_selection_signals` | Default order: `importance_score DESC, updated_at DESC`. |
| `_job_selection_assessments_view(conn, *, job_id, limit)` | `job_selection_assessments` | Default order: the closest stable analogue available (e.g., `updated_at DESC`). |

Each helper returns a `list[dict[str, Any]]`, consistent with existing view
helpers in `inspect_primary_db.py`.

### CLI surface

Add to `inspect-db`:

- three new `--show` choices: `job_claims`, `job_selection_signals`,
  `job_selection_assessments`
- one new optional argument: `--job-id <id>`

`--job-id` must only influence the three new views. Existing views
(`summary`, `profile`, `applications`, `events`, `candidates`, `documents`,
`calibration`, `feedback`, `suggestions`, `gaps`, `gap_assessments`, `jobs`,
`source_records`, `runs`, `evaluations`, `job_events`) must continue to
behave exactly as they do today.

### Error handling

- If `--job-id` is provided but that id is not present in `jobs`, print a
  clear stderr error (for example,
  `[inspect-db] job_id <id> not found in jobs`) and exit with a non-zero
  status. This avoids the common failure mode of silently returning an
  empty list for a typo.
- If the job exists but the requested view has zero rows, print a single
  informational line (for example, `[job_claims] no rows for job_id <id>`)
  and continue with exit 0.

### Output shape

- Text mode: render a compact table with
  `claim_type | claim_strength | normalized_label | confidence | importance | evidence_span`
  (truncate `evidence_span` to ~120 chars).
- JSON mode (`--json`): emit a dict keyed by view name whose value is a
  list of row dicts, consistent with how existing views are emitted.

### Dependency impact

None. All additions use stdlib plus already-imported jobpipe modules.
`DEPENDENCY_POLICY.md` "Use OSS directly for generic concerns" is respected
by reusing the existing `connect_primary_db` path; no OSS wrapping or new
dependency is introduced.

## Tests

New file: `tests/test_inspect_primary_db_claims.py`.

Minimum covered cases:

1. **Happy path (text + JSON).** Seed a temporary SQLite DB with one job in
   `jobs` and two claim rows in `job_claims`. Invoke the CLI with
   `--show job_claims --job-id <id>` and assert each claim_type appears in
   text output. Invoke again with `--json` and assert the JSON payload
   contains a `job_claims` key with two row dicts.
2. **Empty-but-valid-job path.** Seed a job in `jobs`, no rows in
   `job_claims`. Invoke the CLI and assert exit 0 and an informational
   line like `[job_claims] no rows for job_id <id>` on stdout.
3. **Unknown-job path.** Invoke `--show job_claims --job-id bogus` against
   a DB whose `jobs` table does not contain that id. Assert non-zero exit
   and a stderr message identifying the missing job.
4. **Parity.** Same three cases applied at least once each to
   `--show job_selection_signals` and `--show job_selection_assessments`
   to confirm the argparse plumbing dispatches consistently.

Validation harness should mirror the conventions of
`tests/test_sync_evaluations_primary_db.py` (temporary DB under `tmp_path`,
no network, no external services).

## Validation commands Codex must run

- `python -m pytest tests/test_inspect_primary_db_claims.py -q`
- `python compile_check.py`
- `python -m jobpipe.cli.main inspect-db --help`
  (smoke: confirm the new `--show` choices and `--job-id` are listed)

Not required for this slice:

- `jobpipe run --dry-run` — this slice is read-only and does not affect
  the pipeline runtime path.

## Risk label

**Green.**

- Read-only CLI extension inside an already-registered subcommand.
- No schema, auth, billing, secret, deploy, pipeline-semantic, or
  model-cost surface is touched.
- No new runtime dependency is introduced.

## Mismatches between docs and code (flagged, not fixed in this slice)

- `specs/job-claims-model.md` §"First implementation slice" item 2 still
  asserts "a first-class `job_claims` table in the primary DB" as pending.
  In fact that table exists in `jobpipe/core/primary_db.py` (lines
  ~386–407) and rows are written by `replace_job_claims` from
  `jobpipe/decision/persistence.py`. `specs/canonical-data-model.md` §4
  already correctly reflects this.
- `specs/job-claims-model.md` §"First implementation slice" items 1–6 are
  effectively complete in code; item 7 ("inspection output so the extracted
  claims can be audited") is the only remaining item from that first-slice
  list and is the gap this slice closes.

These docs-vs-code drifts should be reconciled in a separate docs-hygiene
slice, not here.

## Proposed Codex worker prompt

See `docs/execplans/T001.md` §"Decomposition — Slice 1" → "PROPOSED Codex
worker prompt". That prompt is authoritative. This spec should not be
interpreted as a separate instruction channel for Codex.

## Approval status

Approved by coordinator on 2026-04-21. Codex implementation handed off on
`codex/job-catalog-foundation-v2`. Escalation gates in the proposed Codex
worker prompt (see `docs/execplans/T001.md`) remain in force during
implementation.

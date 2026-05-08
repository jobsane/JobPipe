# Application Workspace Hub

## Decision

The backend-side common connection point for JobDesk and the surrounding
JobPipe ecosystem is named **ApplicationWorkspaceHub**.

The hub is not a new product UI and not a replacement for JobPipe, JobSane,
JobData, or Reactive Resume. It is the backend contract layer that turns
ecosystem-specific state and actions into stable workspace capabilities for
JobDesk and future API/MCP wrappers.

Target architecture:

```text
JobDesk UI
-> JobDeskIntegrationGateway
-> future HTTP/MCP/API wrapper
-> ApplicationWorkspaceHub
-> capability adapters
   -> JobPipe
   -> JobSane
   -> JobData
   -> Reactive Resume
   -> SQLite/artifacts now
   -> Supabase/object storage later
```

## What The Hub Owns

ApplicationWorkspaceHub owns:

- Backend-facing contracts for JobDesk capabilities.
- Read projections that are safe for frontend/workspace use.
- Command boundaries for writes that require explicit user approval.
- Adapter routing to JobPipe, JobSane, JobData, Reactive Resume, and storage.
- Provenance-safe payloads that do not expose raw private paths.
- Capability versioning and migration compatibility.
- The distinction between read models, command models, and audit records.
- Stable API/MCP-wrapper entrypoints once wrappers are approved.

The hub is the contract owner. It should be possible to change storage,
runtime, or adapter implementation without changing JobDesk UI contracts.

## What The Hub Does Not Own

ApplicationWorkspaceHub does not own:

- JobDesk UI workflow, screens, or user-facing interaction model.
- JobPipe ingestion, source cataloging, triage, scoring, source artifacts, or
  pipeline history.
- JobSane generation, rewrite, validation, or application-prep orchestration.
- JobData private profile storage, evidence store, or profile-context authoring.
- Reactive Resume document editing, visual builder state, export, or live resume
  variants.
- Supabase schema design as a first-order source of truth.
- Old dashboard rendering or dashboard rescue/refactor work.
- Agent trace viewing, queue running, or generic orchestration UI.

## Capability Groups

### cases

Read-only case queue and case detail projection.

Initial operations:

- `cases.list()`
- `cases.get(case_id)`

Case payloads include job identity, recommendation, decision signals, evidence
references, gaps, tailoring effort, current application status, and safe artifact
IDs.

### evidence

Evidence references used to support claims, strengths, gaps, and rewrite
decisions.

The hub exposes provenance-safe references and excerpts. It must not expose raw
private file paths or unrestricted profile data.

### profile

Candidate profile snapshots and workspace-safe context used for review,
tailoring, and authoring.

JobData owns the private source of truth. The hub owns the projection boundary.

### documents

Generated artifacts, document refs, previews, statuses, and artifact ownership.

Second implementation slice:

- list generated artifacts for a case
- expose safe document IDs and preview/status metadata
- no raw `storage_path` or private path leakage

### resume

Reactive Resume variant and export handoff state.

Reactive Resume owns resume authoring/export. The hub records variant IDs,
builder URLs, export metadata, screenshot/PDF refs, and patch history only after
explicit approval flows are defined.

### valueDrafts

Value proposition draft read/write contract.

Second implementation slice defines the contract. Implementation waits until
write ownership is explicit. Seed drafts may be read; approval/lock state must
not be inferred from generated text.

### applications

Application readiness and submitted/application status state.

JobPipe owns current ledger/history. The hub owns the workspace-safe status
projection and future command boundary for status changes.

### followUps

Follow-up due dates, next actions, and follow-up outcomes.

The hub projects due dates and next actions. Write persistence is deferred until
the application/follow-up owner and command model are explicit.

### integrations

Connector configuration/status surfaces for JobPipe, JobSane, JobData, Reactive
Resume, MCP/API wrappers, and future Supabase/object storage.

No secrets are exposed through this capability. Secrets remain in the owning
runtime/integration layer.

### audit/provenance

Traceability for source systems, generated artifacts, approvals, rejects,
overrides, and adapter actions.

The hub exposes safe provenance IDs, timestamps, source labels, and sanitized
excerpts. It does not expose raw artifact paths or private data roots.

## Ownership Model

- **JobPipe** owns ingestion, triage, scoring, source artifacts, generated
  application packet outputs, ledger/history, and current SQLite/artifact source
  state.
- **JobSane** owns generation, rewrite, validation, and application-prep
  orchestration.
- **JobData** owns private profile/context/evidence data.
- **Reactive Resume** owns resume authoring, visual editing, export, and live
  resume variants.
- **JobDesk** owns the human-facing workflow, decision surfaces, manual edits,
  approvals, locks, accepts, rejects, and overrides.
- **ApplicationWorkspaceHub** owns backend contracts, projections, command
  boundaries, adapter routing, and provenance-safe payloads.

## First Implementation Slice

First slice: **cases read projection**.

Operations:

- `cases.list()`
- `cases.get(case_id)`

Rules:

- No old dashboard dependency.
- No dashboard-server dependency.
- No endpoint wiring.
- No writes.
- No Supabase.
- No direct JobDesk database access.
- No raw private paths.

Implementation should add a focused lower-level read model for case projection
if existing projection-store/boundary objects do not expose enough source data.
That read helper must be read-only, narrow, and owned by the hub pathway rather
than by the old dashboard.

Contract modules:

- `jobpipe.workspace.contracts` owns storage-agnostic read model value objects.
- `jobpipe.workspace.hub` owns the hub and capability protocols.
- Implementations and adapters must live outside the contract layer.

## Second Implementation Slice

Second slice: **documents and value draft contract**.

Scope:

- `documents.listForCase(case_id)`
- value draft read/write contract definition
- document/value draft ownership rules
- no value draft implementation unless explicitly approved

This slice defines how generated artifacts and value-proposition drafts connect
to JobDesk without creating a generic document store or exposing private paths.

## Migration Sequence

1. Lock this hub architecture and guardrails.
2. Add `ApplicationWorkspaceHub` contract documentation and case read model.
3. Implement `cases.list()` and `cases.get(case_id)` behind the hub using current
   SQLite/artifacts through a narrow read-only helper.
4. Add contract tests against sanitized fixture data.
5. Add future HTTP/MCP wrapper only after the hub contract is stable.
6. Wire JobDesk backend adapter to the wrapper, not to SQLite/Supabase.
7. Define documents/valueDrafts contract and ownership.
8. Add write commands only when approval, locking, audit, and owner boundaries
   are explicit.
9. Migrate storage internals to Supabase/object storage behind the same hub
   contracts.
10. Retire or isolate dashboard-era dependencies from new JobDesk pathways.

## Supabase-Later Strategy

Supabase is a storage/runtime implementation behind the hub, not a UI-facing or
JobDesk-facing dependency.

Rules:

- No direct JobDesk Supabase access.
- No direct JobDesk database access.
- No Supabase migration before cases projection and ownership contracts are
  stable.
- Supabase tables/object storage must preserve the same hub capability contract.
- RLS/auth concerns are handled in the API/hub/storage layer, not in JobDesk
  components.
- SQLite/artifacts remain current source of truth until migration is explicitly
  approved.

## Old Dashboard Treatment

The old dashboard is legacy operational UI/projection code.

It may be used as historical reference for behavior, but it must not become the
JobDesk dependency. New JobDesk backend pathways must not import:

- `jobpipe/projections/dashboard.py`
- `jobpipe/cli/dashboard_server.py`

No dashboard rescue, refactor, or dependency expansion is part of the hub first
slices.

## API And MCP Wrapper Fit

HTTP and MCP wrappers are transport layers around ApplicationWorkspaceHub.

They should:

- expose hub capabilities without adding business logic;
- translate transport errors to stable error responses;
- preserve read/write command boundaries;
- avoid direct storage access;
- avoid direct JobPipe/JobSane/JobData/Reactive Resume imports in JobDesk;
- remain replaceable by another transport later.

They should not:

- become a second hub;
- duplicate projection logic;
- expose raw storage paths;
- bypass approval/audit boundaries for write commands.

## Agent Guardrails

Future agents must follow these rules:

- Do not apply either S5-02E stash wholesale.
- Do not import old dashboard modules into JobDesk hub code.
- Do not add endpoint wiring until hub contracts and tests exist.
- Do not add writes until ownership and approval semantics are explicit.
- Do not expose `storage_path`, private data roots, `.env` values, or raw
  artifact paths in hub responses.
- Do not start Supabase migration as part of cases projection.
- Do not implement Reactive Resume, MCP, or JobSane execution in the cases slice.
- Use small read-only fixtures for tests.
- Keep generated context bundles ignored and unstaged.
- Record every durable architecture decision in `docs/decisions.md`.

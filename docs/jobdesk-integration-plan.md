# JobDesk Integration Plan

## Purpose

This plan defines how JobDesk connects to JobPipe ecosystem capabilities without
depending on the legacy dashboard or directly reading backend storage.

JobDesk already has a frontend `JobDeskIntegrationGateway`. The backend
counterpart is `ApplicationWorkspaceHub`.

## Integration Direction

```text
JobDesk UI
-> JobDeskIntegrationGateway
-> HTTP/MCP/API wrapper
-> ApplicationWorkspaceHub
-> capability adapters
```

JobDesk components and routes must never import JobPipe, JobSane, JobData,
Reactive Resume, MCP, Sema, SQLite, Supabase, or old dashboard clients directly.

## Contract Boundaries

### JobDeskIntegrationGateway

Frontend-owned contract for UI-facing capabilities.

Responsibilities:

- keeps JobDesk route/component imports repo-neutral;
- preserves manual approval, accept/reject, lock/override, and evidence display;
- remains mockable;
- calls a backend wrapper later.

### ApplicationWorkspaceHub

Backend-owned contract for workspace capabilities.

Responsibilities:

- owns stable backend capability contracts;
- maps ecosystem state into provenance-safe payloads;
- routes reads/commands to owning systems;
- shields JobDesk from storage and internal repo structures;
- keeps Supabase and MCP/API transports replaceable.

### Capability Adapters

Adapters implement hub capabilities by delegating to the owning system:

- JobPipe adapter for cases, scoring, source artifacts, generated packets, and
  application ledger/history.
- JobSane adapter for generation, rewrite, validation, and application-prep
  orchestration.
- JobData adapter for private profile/context/evidence projections.
- Reactive Resume adapter for variant/export metadata and approved patch
  execution.
- Storage adapters for SQLite/artifacts now and Supabase/object storage later.

## Initial Capability Plan

### Slice 1: cases

Operations:

- `cases.list()`
- `cases.get(case_id)`

Payload requirements:

- case ID
- job company, title/role, location, deadline, source/application URLs
- recommendation
- score from `should_want` when available
- decision signals: `can_do`, `can_get`, `should_want`, `can_explain`
- strengths/supporting points
- gaps/risk points
- evidence/provenance refs
- ATS/requirement keywords
- tailoring effort
- application status
- generated document/draft refs where safe

Non-goals:

- no dashboard dependency
- no endpoint wiring
- no writes
- no Supabase
- no Reactive Resume execution
- no JobSane generation

### Slice 2: documents and valueDrafts contract

Operations:

- `documents.listForCase(case_id)`
- value draft read/write contract

Non-goals:

- no write implementation unless explicitly approved
- no embedded document editor
- no Reactive Resume implementation
- no raw private artifact paths

## Migration Plan

1. Lock ApplicationWorkspaceHub architecture.
2. Define hub capability interfaces and payload conventions.
3. Implement `cases.list()` / `cases.get(case_id)` using a narrow read-only
   JobPipe source helper owned by the hub pathway.
4. Add fixture-based contract tests.
5. Add a thin API/MCP wrapper only after hub tests pass.
6. Point JobDesk backend adapter at the wrapper.
7. Define documents/valueDrafts write contract and approval model.
8. Add write implementations only after owner and audit rules are explicit.
9. Move storage from SQLite/artifacts to Supabase/object storage behind the same
   hub capabilities.

## Dashboard Boundary

The legacy dashboard is not the JobDesk backend. It can remain for operational
inspection or historical reference, but new JobDesk integration code must not
depend on:

- `jobpipe/projections/dashboard.py`
- `jobpipe/cli/dashboard_server.py`

If behavior is useful, move it into a lower-level hub-owned helper with tests.

## Supabase Deferral

Supabase is deferred until:

- case projection shape is stable;
- owner boundaries are explicit;
- write commands are designed;
- privacy/provenance rules are tested.

JobDesk must never be wired directly to Supabase. Supabase replaces underlying
storage adapters behind ApplicationWorkspaceHub.

## Open Questions

- Which package should own the first `ApplicationWorkspaceHub` implementation:
  `jobpipe/workspace`, `jobpipe/runtime`, or a new shared package?
- Should the first hub object be a plain Python service class or protocol plus
  functions?
- Which case fields are required for list payloads versus detail payloads?
- What is the canonical safe ID format for source artifacts and generated
  document refs?
- Which service owns accepted value draft persistence: JobPipe, JobSane, or a
  hub-owned command store?
- What audit record is required for manual override, accept/reject, and lock?

## Next Implementation Task

`S5-HUB-01 — Define ApplicationWorkspaceHub Contracts`

Goal:
Create the initial Python contract layer for ApplicationWorkspaceHub without
storage implementation or endpoint wiring.

Allowed:

- add typed protocols/dataclasses or Pydantic models for hub capabilities;
- define `cases.list()` and `cases.get(case_id)` request/response contracts;
- define safe artifact/document reference types;
- add fixture-based contract tests;
- document any missing source fields.

Not allowed:

- no dashboard dependency;
- no endpoint wiring;
- no writes;
- no Supabase;
- no Reactive Resume execution;
- no MCP implementation;
- no JobDesk frontend changes.


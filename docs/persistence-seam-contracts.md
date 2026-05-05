# JobPipe Persistence Seam Contracts

Defines the database as a replaceable infrastructure boundary. Domain modules must not depend on SQLite, table names, or raw SQL — they depend on these repository contracts.

**Principle:** JobPipe owns meaning. The database owns storage. Adapters own translation.

---

## Architecture

```
Domain / service layer
        │
        ▼
  Repository contract  ◄── this document defines these
  (protocol / ABC)
        │
        ├─► SQLiteAdapter  (current — connects via connect_primary_db)
        ├─► InMemoryAdapter (test / smoke corpus)
        └─► PostgresAdapter (future — Supabase or bare Postgres)
```

The current codebase has no explicit seam: domain code calls `connect_primary_db()` directly and operates on `sqlite3.Connection`. The contracts below describe the target seam. The hotspot inventory (`docs/persistence-hotspot-inventory.md`) identifies which callers must migrate.

---

## Repository Contracts

Each repository is a protocol/ABC with a concrete `SqliteAdapter` backed by `connect_primary_db`. No schema migration is required to define these contracts — migration happens incrementally as callers are moved behind the seam.

---

### JobRepository

Owns job records, source records, and replay inputs.

**Tables:** `jobs`, `job_source_records`, `job_replay_inputs`

**Operations:**

```python
class JobRepository(Protocol):
    def save_job(self, row: Mapping[str, Any]) -> None: ...
    def save_source_record(self, row: Mapping[str, Any]) -> None: ...
    def mark_source_records_inactive(
        self, source_name: str, source_job_keys: Iterable[str], *, seen_at: str
    ) -> None: ...
    def save_replay_input(self, row: Mapping[str, Any]) -> None: ...
    def get_job(self, job_id: str) -> dict[str, Any] | None: ...
    def list_open_jobs(self, candidate_id: str) -> list[dict[str, Any]]: ...
```

**Current hotspots that must migrate:**
- `run_feed.py:173` (connect_primary_db → upsert_job / upsert_job_source_record)
- `drain_queue.py:40` (sqlite3.connect direct — highest priority to seal)
- `pull_sheets_csv.py:367` (connect_primary_db → upsert_job)
- `runtime/catalog.py:448` (sqlite3.connect direct)

---

### EvaluationRepository

Owns triage/scoring decisions, pipeline runs, and all per-job assessment tables.

**Tables:** `job_evaluations`, `job_run_events`, `pipeline_runs`, `job_claims`, `job_selection_signals`, `job_selection_assessments`, `job_decision_tables`, `job_narrative_assessments`

**Operations:**

```python
class EvaluationRepository(Protocol):
    def save_evaluation(self, row: Mapping[str, Any]) -> None: ...
    def save_run_event(self, row: Mapping[str, Any]) -> None: ...
    def save_pipeline_run(self, row: Mapping[str, Any]) -> None: ...
    def mark_pipeline_run_finished(self, *, run_id: str, **kwargs: Any) -> None: ...
    def replace_job_claims(self, job_id: str, rows: Iterable[Mapping[str, Any]]) -> None: ...
    def replace_job_selection_signals(self, job_id: str, rows: Iterable[Mapping[str, Any]]) -> None: ...
    def save_selection_assessment(self, row: Mapping[str, Any]) -> None: ...
    def save_decision_table(self, row: Mapping[str, Any]) -> None: ...
    def save_narrative_assessment(self, row: Mapping[str, Any]) -> None: ...
    def get_evaluation(self, candidate_id: str, job_id: str) -> dict[str, Any] | None: ...
    def list_evaluated_job_ids(self, candidate_id: str) -> set[str]: ...
```

**Current hotspots:**
- `run_feed.py:173` (write path — dual role with JobRepository)
- `sync_evaluations.py:522` (connect_primary_db → upsert_job_evaluation)
- `core/evaluation_state.py:13` (sqlite3.connect direct — own internal state)

---

### ApplicationRepository

Owns application lifecycle events, canonical status, and generated documents.

**Tables:** `application_events`, `application_summary`, `generated_documents`

**Operations:**

```python
class ApplicationRepository(Protocol):
    def insert_application_event(self, row: Mapping[str, Any]) -> None: ...
    def upsert_application_summary(self, row: Mapping[str, Any]) -> None: ...
    def delete_application_tracking(self, candidate_id: str, job_id: str) -> None: ...
    def replace_imported_application_state(
        self,
        candidate_id: str,
        events: list[Mapping[str, Any]],
        summaries: list[Mapping[str, Any]],
    ) -> None: ...
    def insert_generated_document(self, row: Mapping[str, Any]) -> None: ...
    def get_application_summary(self, candidate_id: str, job_id: str) -> dict[str, Any] | None: ...
    def list_documents(self, candidate_id: str, job_id: str) -> list[dict[str, Any]]: ...
```

**Current hotspots:**
- `stages/application_pack.py:330` (generated document write — critical path)
- `authoring/author_cli.py:71` (application pack write — critical path)
- `cli/mark_status.py:187` (status write — critical path)
- `runtime/reactive_resume.py:19` (RR document write)
- `runtime/jobsync.py:59` (jobsync export read)

---

### CandidateProfileRepository

Owns the candidate record, profile versions, evidence units, narrative, and calibration settings.

**Tables:** `candidates`, `candidate_profiles`, `candidate_evidence_units`, `candidate_narrative_profiles`, `narrative_fragments`, `narrative_evidence_links`, `candidate_calibration_settings`, `capability_gaps`, `gap_evidence`, `gap_assessments`

**Operations:**

```python
class CandidateProfileRepository(Protocol):
    def ensure_candidate(self, candidate_id: str, **kwargs: Any) -> None: ...
    def upsert_candidate(self, row: Mapping[str, Any]) -> None: ...
    def upsert_candidate_profile(self, row: Mapping[str, Any]) -> None: ...
    def get_active_profile(self, candidate_id: str) -> dict[str, Any] | None: ...
    def replace_candidate_evidence_units(
        self, candidate_id: str, rows: Iterable[Mapping[str, Any]]
    ) -> None: ...
    def upsert_capability_gap(self, row: Mapping[str, Any]) -> None: ...
    def insert_gap_evidence(self, row: Mapping[str, Any]) -> None: ...
    def upsert_gap_assessment(self, row: Mapping[str, Any]) -> None: ...
    def replace_candidate_gap_state(self, candidate_id: str) -> None: ...
    def upsert_candidate_narrative_profile(self, row: Mapping[str, Any]) -> None: ...
    def upsert_candidate_calibration_setting(self, row: Mapping[str, Any]) -> None: ...
```

**Current hotspots:**
- `core/candidate_data.py:36` (sqlite3.connect direct — profile read)
- `cli/bootstrap_state_db.py:163` (connect_primary_db — setup/migration)
- `cli/import_reactive_resume.py:80` (connect_primary_db — profile import)

---

### SourceEventRepository

Owns email-sourced suggestion leads and candidate feedback events.

**Tables:** `suggestion_leads`, `candidate_feedback_events`

**Operations:**

```python
class SourceEventRepository(Protocol):
    def upsert_suggestion_lead(self, row: Mapping[str, Any]) -> None: ...
    def mark_suggestion_lead_status(
        self, suggestion_id: str, *, status: str, updated_at: str, **kwargs: Any
    ) -> None: ...
    def list_suggestion_leads(
        self,
        candidate_id: str,
        *,
        statuses: Iterable[str] | None = None,
        platform: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    def insert_candidate_feedback_event(self, row: Mapping[str, Any]) -> None: ...
```

**Current hotspots:**
- `cli/scan_gmail.py:491,578,705` (connect_primary_db — email/suggestion write)
- `cli/pull_suggested.py:127,591` (connect_primary_db — suggestion lead r/w)
- `cli/record_feedback.py:68` (connect_primary_db — feedback write)

---

### SignalRepository

Owns watchlists and change event signals. Not on the critical path — seal after core repositories.

**Tables:** `watchlists`, `change_events`

**Operations:**

```python
class SignalRepository(Protocol):
    def replace_watchlists(self, candidate_id: str, rows: Iterable[Mapping[str, Any]]) -> None: ...
    def upsert_change_event(self, row: Mapping[str, Any]) -> None: ...
    def list_change_events(
        self, candidate_id: str, *, limit: int | None = None
    ) -> list[dict[str, Any]]: ...
```

---

## Migration Strategy

The seam does not need to be introduced all at once. Safe incremental order:

1. **Read paths first:** wrap `core/candidate_data.py` and `runtime/catalog.py` (both currently use direct `sqlite3.connect`) — low blast radius, easy to test
2. **Critical write path:** `ApplicationRepository` for `application_pack.py`, `mark_status.py`, `author_cli.py` — required before Apply Workbench
3. **Intake path:** `JobRepository` for `drain_queue.py` and `run_feed.py` — high call frequency, must not break triage
4. **Evaluation path:** `EvaluationRepository` for `sync_evaluations.py` and `evaluation_state.py`
5. **Profile and source events:** `CandidateProfileRepository`, `SourceEventRepository`
6. **Projections last:** `projections/dashboard.py` has 7 direct `sqlite3.connect` calls — read-only, safe to migrate last or leave as projection-layer exception

---

## Preserving Local-First SQLite

The `SqliteAdapter` for each repository calls `connect_primary_db()` as its connection factory. The WAL mode, foreign keys, and busy timeout pragmas stay in `connect_primary_db`. No repository contract leaks SQLite primitives.

A future `PostgresAdapter` or `InMemoryAdapter` implements the same protocol. The adapter is injected at startup (e.g. via `config.py` or CLI entry point). No domain module imports `sqlite3` or `connect_primary_db`.

**What stays local:** All candidate data. All SQLite files. No cloud egress of candidate PII except through explicitly approved seams (JobSync export, Reactive Resume export).

**What a future Supabase adapter enables:** Remote access and team features — only if and when the candidate chooses. The adapter swap does not change domain logic.

---

## Out of Scope

- Schema migration (no DDL changes in this doc)
- Supabase implementation (no cloud dependency added)
- Refactoring any hotspot (mapping only — see hotspot inventory)
- Test adapter implementation (follows after contract is ratified)

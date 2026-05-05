# Application Lifecycle Contract

Defines the canonical lifecycle states, allowed transitions, artifact contract, and event integration that JobSane, JobSync, email sync, and application pack generation must all share.

---

## Lifecycle States

```
discovered
  └─► enriched
        └─► curated
              └─► shortlisted
                    └─► apply_ready
                          └─► applying
                                └─► applied
                                      ├─► interview
                                      │     ├─► rejected
                                      │     └─► withdrawn
                                      ├─► rejected
                                      └─► withdrawn
                    └─► skipped
              └─► skipped
        └─► skipped
  └─► archived (terminal — any state may transition to archived)
```

### State Definitions

| State | Meaning |
|-------|---------|
| `discovered` | Job seen from a source (NAV, Finn, Gmail suggestion). Not yet evaluated. |
| `enriched` | Job fetched and description available. Pipeline has run triage. |
| `curated` | Candidate has reviewed triage output. Job is in the active decision queue. |
| `shortlisted` | Candidate has decided this job is worth applying to. |
| `apply_ready` | Tailored CV and cover letter have been prepared and are awaiting final approval. |
| `applying` | Candidate is actively filling in the recruiter portal / applying. |
| `applied` | Application has been submitted. Tracking begins. |
| `interview` | Candidate has been invited to or is in interview process. |
| `rejected` | Application rejected (by recruiter or by candidate). |
| `withdrawn` | Candidate has withdrawn the application. |
| `skipped` | Candidate dismissed the job from the queue (no application intended). |
| `archived` | Job is no longer active in any queue. Terminal state. |

### Allowed Transitions

| From | To | Trigger |
|------|----|---------|
| `discovered` | `enriched` | Pipeline run completes triage |
| `discovered` | `archived` | Job closed at source before evaluation |
| `enriched` | `curated` | Candidate reviews triage output in dashboard |
| `enriched` | `skipped` | Candidate dismisses at triage review |
| `curated` | `shortlisted` | Candidate marks as shortlisted |
| `curated` | `skipped` | Candidate dismisses from curated queue |
| `shortlisted` | `apply_ready` | `jobpipe trigger-authoring JOB_ID` — authoring pack complete |
| `shortlisted` | `skipped` | Candidate changes mind |
| `apply_ready` | `applying` | Candidate opens recruiter portal |
| `apply_ready` | `skipped` | Candidate decides not to apply |
| `applying` | `applied` | `jobpipe mark-status JOB_ID applied` |
| `applying` | `withdrawn` | Candidate abandons mid-apply |
| `applied` | `interview` | `jobpipe mark-status JOB_ID interview` (email signal or manual) |
| `applied` | `rejected` | Rejection email/signal or manual mark |
| `applied` | `withdrawn` | Candidate withdraws |
| `interview` | `rejected` | Post-interview rejection |
| `interview` | `withdrawn` | Candidate withdraws from process |
| `* (any)` | `archived` | Manual archive, or source-closed job |

---

## Persistence

States are stored in `application_summary` (canonical) and derived from `application_events` (audit log).

| Field | Location | Role |
|-------|----------|------|
| `effective_status` | `application_summary` | Canonical current state — what other systems read |
| `current_stage` | `application_summary` | Active process stage (e.g. `applied`, `interview`) |
| `current_outcome` | `application_summary` | Final outcome if terminal (e.g. `rejected`, `withdrawn`) |
| `event_type` | `application_events` | Each transition event (append-only audit log) |
| `last_event_at` | `application_summary` | Timestamp of most recent transition |

Write path: `insert_application_event()` → `upsert_application_summary()` in `jobpipe/core/primary_db.py`.

---

## Application Artifact Contract

For each job that reaches `apply_ready` or beyond, Jobpipe tracks these artifacts:

| Artifact | Kind | Storage | Source |
|----------|------|---------|--------|
| Tailored CV projection | `tailored_cv` | `generated_documents` table (`document_json`) | CV Tailoring Crew or manual edit |
| Cover letter draft | `cover_letter` | `generated_documents` table (`document_json`) | Cover Letter Crew or manual edit |
| Application pack JSON | `application_pack` | `generated_documents` table + `out_runs/` artifact | `application_pack.py` + `author_cli.py` |
| Source job ad | — | `jobs.description_text`, `jobs.source_url` | Run-feed intake |
| Portal application URL | — | `jobs.application_url` | Run-feed intake |
| Generated timestamps | — | `generated_documents.created_at`, `updated_at` | DB |
| Status history | — | `application_events` (append-only) | All write paths |

### Document Status Values

`generated_documents.status`: `draft` → `approved` → `submitted`

- `draft`: produced by crew or manually authored; not yet reviewed by candidate
- `approved`: candidate has reviewed and saved in Reactive Resume or JobSync editor
- `submitted`: included in a submitted application

---

## Email-Derived Event Integration

Gmail scan (`scan_gmail.py`) maps inbound email signals to `application_events`:

| Email signal | event_type written | Effect on application_summary |
|--------------|--------------------|-------------------------------|
| Recruiter acknowledgement | `email_ack` | No status change; notes updated |
| Interview invitation | `email_interview_invite` | `effective_status` → `interview` |
| Rejection notice | `email_rejection` | `effective_status` → `rejected` |
| Offer received | `email_offer` | `current_outcome` → `offer_received` (sub-state of `interview`) |

Source field on all email-derived events: `gmail_scan`.

Manual overrides always win — if a candidate sets status via `mark-status`, that event takes precedence regardless of email signals.

---

## Integration Points

| System | Reads | Writes |
|--------|-------|--------|
| JobSync | `application_summary.effective_status`, job metadata | `record-jobsync-event` → `insert_application_event` |
| Email sync (Gmail) | Inbox | `scan_gmail.py` → `insert_application_event` |
| Apply Workbench | All artifact fields | `mark-status`, `record-reactive-resume-document`, `record-jobsync-event` |
| Dashboard | All | — (read-only projection) |
| Gap analysis | `job_evaluations`, `gap_evidence` | — (read-only report) |

All new jobs must be curated in Jobpipe first. JobSync is a candidate-facing view of Jobpipe's curated queue, not a separate source of truth.

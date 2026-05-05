# Status Reconciliation Policy

Defines which source events update canonical lifecycle status automatically, which require human review, and where the human approval boundaries are.

**Principle:** Source events are evidence. Canonical state is owned by JobPipe. Events may propose state changes; policy decides which proposals auto-apply and which need review.

See also: `docs/source-event-contract.md` (event envelope), `docs/application-lifecycle-contract.md` (lifecycle states).

---

## Reconciliation Decision Tree

For each incoming source event, apply these rules in order:

```
1. Is this a human-initiated action?
   (jobsync_apply_clicked, mark-status CLI, manual record-jobsync-event)
   → Auto-apply immediately. No review needed.

2. Is confidence >= 0.9 AND event_type in the auto-apply list?
   → Apply suggested_effect.status_suggestion.
   → Write insert_application_event + upsert_application_summary.

3. Is confidence >= 0.6 AND confidence < 0.9?
   → Create needs_review suggestion.
   → Surface to candidate in daily brief.

4. Is confidence < 0.6?
   → Append as evidence note only. No status change proposed.

5. Does the proposed transition conflict with a manual override from the last 24h?
   → Downgrade to needs_review regardless of confidence.
   → Human decisions always win.
```

---

## Auto-Apply Events

These events apply their status suggestion automatically when confidence ≥ 0.9.

| event_type | Status transition | Guard condition |
|------------|------------------|-----------------|
| `new_lead_detected` | → `discovered` | Only if job not already known |
| `job_source_expired` | → `archived` | Only if current stage is `discovered`, `enriched`, or `curated` — never archive past `shortlisted` automatically |
| `jobsync_apply_clicked` | → `apply_ready` | Only if current stage is `shortlisted` |
| `application_submitted_observed` | → `applied` | Only if current stage is `applying` |

---

## Needs-Review Events

These events create a `needs_review` suggestion that is presented to the candidate. The candidate must confirm before the status changes.

| event_type | Suggested status | Action hint | Notes |
|------------|-----------------|-------------|-------|
| `rejection_detected` | `rejected` | `review_rejection` | Even at high confidence — rejection is high stakes |
| `interview_invite_detected` | `interview` | `confirm_interview_date` | Candidate must confirm date/format |
| `portal_status_changed` | (no change) | `note_portal_status` | Portal state noted but not mapped 1:1 to lifecycle |
| `email_reply_detected` | (no change) | `check_reply` | May contain rejection, invite, or neutral acknowledgement |
| `followup_due_detected` | (no change) | `schedule_followup` | Triggers action item, not status change |
| `duplicate_candidate_detected` | (no change) | `review_duplicate` | Human decides which record is canonical |
| `employer_info_enriched` | (no change) | (none) | Stored as evidence; no lifecycle effect |
| `recruiter_identified` | (no change) | (none) | Stored as evidence; no lifecycle effect |

---

## Human Approval Hard Stops

The following transitions must **never** happen automatically regardless of confidence:

| Transition | Why |
|-----------|-----|
| Any stage → `applied` from email signal alone | Only the candidate knows if they actually submitted |
| Any stage → `withdrawn` or `rejected` from email | Even clear rejections need candidate acknowledgement |
| Any backwards transition (e.g. `applied` → `apply_ready`) | Lifecycle is append-only; rollbacks are manual only |
| `archived` → any active stage | `archived` is terminal; unarchiving is a manual action only |
| Any status change from `recruiter_page` or `company_page` enrichment events | Enrichment events carry no lifecycle authority |

---

## Conflict Resolution

| Scenario | Resolution |
|----------|-----------|
| Manual `mark-status` conflicts with incoming event | Manual wins; event stored as evidence only |
| Two conflicting events arrive within 1 hour | Both become `needs_review` |
| High-confidence event proposed within 24h of a manual override | Downgraded to `needs_review` |
| `archived` job receives any event | Event stored; status unchanged; `needs_review` note added |

---

## Storage

**Confirmed status changes** (auto-apply or human-confirmed):
- `insert_application_event(event_type, source, notes, metadata_json)` — audit log
- `upsert_application_summary(effective_status, current_stage, last_event_at)` — canonical status

**Pending suggestions** (needs_review):
- `insert_application_event` with `metadata_json = {"needs_review": true, "suggested_status": "...", "action_suggestion": "..."}`
- No separate table required; the event record carries the pending state

**Evidence-only** (confidence < 0.6):
- `insert_application_event` with `metadata_json = {"evidence_only": true}` and `notes` containing the observation

---

## Examples

### Gmail rejection at confidence 0.87 → needs-review

Confidence is below 0.9, and `rejection_detected` is always needs-review regardless. Event written with `needs_review: true`. Candidate sees "Possible rejection from Acme AS — confirm?" in daily brief.

### Gmail interview invite at confidence 0.92 → needs-review

`interview_invite_detected` is on the needs-review list regardless of confidence — the candidate must confirm the date, format (phone/video/onsite), and interviewers. Auto-applying `interview` status without this information would lose context.

### Finn.no job_source_expired at confidence 1.0 → auto-archive (conditional)

Guard condition: current stage must be `discovered`, `enriched`, or `curated`. If the job is `shortlisted` or further along, the expiry becomes a `needs_review` note ("Job posting expired — still pursuing?") rather than an auto-archive.

### JobSync apply clicked → auto apply_ready

Human-initiated action at source confidence 1.0. Immediately transitions `shortlisted` → `apply_ready`. Triggers `jobpipe trigger-authoring JOB_ID`.

### Recruiter portal "Under review" status at confidence 0.8 → needs-review note

`portal_status_changed` never auto-applies. Stored as evidence note. Candidate can manually update to `applied` if the portal observation confirms they submitted.

---

## Not In Scope

- DB schema migration
- Runtime `SourceEvent` Python dataclass
- Automatic email-send or recruiter portal submit (blocked by Apply Workbench hard stops)
- Final reconciliation of suggestion_leads table (covered by SourceEventRepository in #163)

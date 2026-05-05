# Trigger Policy for Event-Driven Actions and Decision Briefs

Defines how source events translate into safe action triggers, so JobSane surfaces only the decisions Lars can make best — without taking risky actions automatically.

**North Star alignment:** "Only surface the most important decisions Lars can make best: apply, skip, research, follow up, prepare, or improve profile strategy."

See also: `docs/source-event-contract.md`, `docs/status-reconciliation-policy.md`, `docs/apply-workbench-contract.md`.

---

## Trigger Classes

### 1. `automatic_internal_update`

Safe internal state change. No candidate input required. Never shown to the user.

| Trigger condition | Action |
|------------------|--------|
| `new_lead_detected` at confidence ≥ 0.9 | Mark job `discovered` in Jobpipe |
| `job_source_seen` | Update `last_seen_at` on job source record |
| `job_source_expired` at confidence = 1.0, stage ≤ `curated` | Archive job silently |
| `employer_info_enriched` / `recruiter_identified` | Store evidence; no status change |
| `jobsync_apply_clicked` | Transition `shortlisted` → `apply_ready`; trigger authoring |

---

### 2. `needs_review`

Candidate must confirm before status changes. Shown as a decision card in JobSync.

| Trigger condition | Suggested status | Action hint |
|------------------|-----------------|-------------|
| `rejection_detected` | `rejected` | "Confirm rejection from [employer]?" |
| `interview_invite_detected` | `interview` | "Confirm interview invite — date/format?" |
| `job_source_expired` at stage ≥ `shortlisted` | (no auto-change) | "Job posting expired — still pursuing?" |
| `duplicate_candidate_detected` | (no change) | "Same job on Finn + NAV — merge or keep separate?" |
| `portal_status_changed` | (no change) | "Portal shows [status] — update Jobpipe status?" |
| Any event with confidence 0.6–0.89 | (suggested only) | "Possible [status] — review signal?" |

Card format in JobSync:
```
[DECISION NEEDED] Possible rejection — Acme AS
Source: Gmail · 87% confidence
→ [Mark rejected]  [Dismiss]  [View email]
```

---

### 3. `decision_brief_item`

Surfaces in the daily/session decision brief. No immediate status change. Represents a decision only Lars can make.

A source event or internal state becomes a `decision_brief_item` when **any** of these is true:

| Condition | Brief label | Why Lars needs to decide |
|-----------|------------|--------------------------|
| New lead with `final_decision = apply` or fit score ≥ triage threshold | "New match: [title] at [employer]" | Only Lars knows if it's worth pursuing |
| Application in `applied` state ≥ 14 days, no `email_reply_detected` | "No response from [employer] in 14 days" | Lars decides: follow up, wait, or withdraw |
| `followup_due_detected` event | "Follow-up due: [employer]" | Lars must send the message manually |
| `needs_review` item unacknowledged for > 24h | "Unreviewed: [label]" | Escalate to brief if card ignored |
| Job in `shortlisted`/`apply_ready` receives `job_ad_updated` | "Job posting updated — re-read before applying" | Requirements may have changed |
| Application in `applied` ≥ 30 days, no activity | "Stale application: [employer] — withdraw or keep tracking?" | Lars decides disposition |
| `followup_due_detected` after `interview` state, ≥ 7 days | "Post-interview follow-up due" | Lars sends manually |

Brief item format in JobSync:
```
[BRIEF] New match: Senior PM · Acme AS
Fit score: 82 · Deadline: 2026-05-20
→ [Add to queue]  [Skip]  [Research]
```

---

### 4. `human_approved_external_action`

Requires explicit, in-session candidate confirmation before any outbound action. Presented as an action prompt only when the candidate has already expressed intent.

| Action | Trigger | Display |
|--------|---------|---------|
| Send follow-up email | Candidate clicks "Send follow-up" in JobSync | Show draft; candidate edits and sends manually |
| Submit application | Candidate clicks "Apply" in JobSync → Apply Workbench → final confirmation | Show portal URL; candidate submits manually |
| Contact recruiter | Candidate requests contact | Show recruiter info; no auto-send |

---

## Forbidden Actions (Hard Stops)

These must **never** happen automatically, regardless of event confidence or trigger class:

| Action | Why forbidden |
|--------|--------------|
| Auto-submit to any recruiter portal | Only the candidate can decide to apply |
| Send any outbound email or message | No outbound without candidate approval |
| Open or interact with external portal on behalf of candidate | Candidate controls the browser |
| Mark status as `applied` from event signal alone | Candidate may not have actually submitted |
| Mark status as `rejected` or `withdrawn` from email alone | High-stakes — requires acknowledgement |
| Any backwards lifecycle transition | Lifecycle is append-only; rollbacks are manual |
| Trigger `human_approved_external_action` without in-session intent | Candidate must initiate; no background prompts |

---

## Trigger Record Shape

When Jobpipe creates a trigger, it produces a structured record consumed by JobSync:

```json
{
  "trigger_id": "string — UUID",
  "trigger_class": "automatic_internal_update | needs_review | decision_brief_item | human_approved_external_action",
  "related_job_id": "string | null",
  "related_event_id": "string | null — source_event.event_id",
  "action_label": "string — short label shown to candidate",
  "action_hint": "string — what the candidate should do",
  "urgency": "low | medium | high",
  "expires_at": "ISO-8601 | null — null means no expiry",
  "auto_resolved": false,
  "created_at": "ISO-8601"
}
```

`auto_resolved: true` is set only by `automatic_internal_update` after the update completes. All other classes require explicit candidate action to resolve.

---

## JobSync Display Rules

| Trigger class | Where shown | Interaction |
|--------------|-------------|-------------|
| `automatic_internal_update` | Not shown | Silent |
| `needs_review` | Decision card (prominent, top of queue) | Accept / Dismiss / View source |
| `decision_brief_item` | Daily brief / session brief panel | Add to queue / Skip / Research / Follow up |
| `human_approved_external_action` | Action prompt (shown only after candidate intent) | Candidate acts manually; Jobpipe records the outcome |

Urgency mapping:
- `high` → shown at top of brief, highlighted — interview invite, rejection, follow-up due
- `medium` → shown in brief — promising new lead, stale application
- `low` → shown in brief backlog — duplicate, enrichment update, expired job reminder

---

## Worked Examples

### 1. Interview invite detected

Event: `interview_invite_detected`, confidence 0.92 → `needs_review` card.
```
[DECISION NEEDED] Interview invite — Acme AS
Source: Gmail · 92% confidence
→ [Confirm interview]  [Dismiss]  [View email]
```
After confirm: status → `interview`, `decision_brief_item` created: "Prepare for interview with Acme AS."

### 2. Rejection detected

Event: `rejection_detected`, confidence 0.87 → `needs_review` card.
```
[DECISION NEEDED] Possible rejection — Widgets Norway
Source: Gmail · 87% confidence
→ [Mark rejected]  [Dismiss]  [View email]
```
After confirm: status → `rejected`. Brief item cleared.

### 3. Follow-up due (applied 14+ days, no reply)

Internal state: `applied` since 2026-04-20, no email reply → `decision_brief_item`.
```
[BRIEF] No response from Widgets Norway in 15 days
→ [Send follow-up]  [Keep tracking]  [Withdraw]
```
"Send follow-up" shows a draft; Lars edits and sends manually. Jobpipe records `followup_sent` event.

### 4. Promising new lead

Event: `new_lead_detected`, fit score ≥ triage threshold → `automatic_internal_update` (mark discovered) + `decision_brief_item`.
```
[BRIEF] New match: Senior Product Manager · Acme AS
Fit score: 82 · Deadline: 2026-05-20
→ [Add to queue]  [Skip]  [Research]
```

### 5. Stale application (30 days, no activity)

Internal state: `applied` since 2026-04-04, no signals → `decision_brief_item`.
```
[BRIEF] Stale — Acme AS (31 days, no reply)
→ [Send follow-up]  [Withdraw]  [Keep tracking]
```

### 6. Duplicate job detected

Event: `duplicate_candidate_detected` → `needs_review` card.
```
[DECISION NEEDED] Same job on Finn + NAV — merge records?
→ [Merge]  [Keep separate]  [View both]
```

---

## Out of Scope

- Runtime `Trigger` dataclass or DB table definition
- Push notification / email delivery of briefs (UI concern)
- Scoring or ranking logic for brief item ordering
- Any JobSync UI implementation details beyond the display contract above

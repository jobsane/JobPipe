# Source Event Contract

Defines the envelope for all external signals that feed into JobPipe, so JobSane, JobSync, email scanners, browser/portal observers, and future connectors can provide evidence without bypassing canonical reconciliation.

**Principle:** External systems produce observations. JobPipe reconciles truth.

A source event is evidence, not final lifecycle state. No external system writes canonical status directly.

---

## Event Envelope

```json
{
  "event_id": "string — UUID, globally unique",
  "source": "gmail | jobsync | nav | finn | linkedin | company_page | recruiter_page | portal | manual | jobsane | other",
  "source_kind": "job_board | email | ui_action | portal | web_enrichment | manual | agent",
  "event_type": "string — see Event Classes below",
  "observed_at": "ISO-8601 — when the external system observed it",
  "received_at": "ISO-8601 — when JobPipe received it",
  "confidence": 0.0,
  "dedupe_key": "string — deterministic hash of (source, source_kind, event_type, raw_ref.external_id or content hash)",
  "related_job_id": "string | null",
  "related_application_id": "string | null",
  "candidate_id": "string | null",
  "raw_ref": {
    "url": "string | null",
    "message_id": "string | null — Gmail message ID",
    "external_id": "string | null — platform-specific ID (NAV job ID, Finn ad ID, etc.)",
    "source_record_id": "string | null — JobPipe source_records row ID if already ingested"
  },
  "evidence": [
    {
      "kind": "text | url | field | snippet | classification | attachment_ref",
      "label": "string — human-readable description of what this evidence is",
      "value": "string",
      "confidence": 0.0
    }
  ],
  "suggested_effect": {
    "status_suggestion": "string | null — lifecycle state from application-lifecycle-contract.md",
    "action_suggestion": "string | null — e.g. 'schedule_followup', 'open_job_ad', 'review_rejection'",
    "requires_review": true
  },
  "metadata": {}
}
```

### Required Fields

| Field | Notes |
|-------|-------|
| `event_id` | UUID — must be stable across retries |
| `source` | One of the defined values above |
| `source_kind` | One of the defined values above |
| `event_type` | One of the event classes below |
| `observed_at` | When the signal was observed externally |
| `received_at` | When JobPipe received/processed the event |
| `confidence` | 0.0–1.0 float |
| `dedupe_key` | Deterministic string to prevent double-processing |
| `evidence` | At least one entry; empty array not valid for most event types |

### Optional but Preferred

`related_job_id`, `related_application_id`, `candidate_id`, `raw_ref`, `suggested_effect`, `metadata`

---

## Event Classes

### Lead Discovery

| event_type | Trigger | Typical source |
|------------|---------|---------------|
| `new_lead_detected` | New job posting found | NAV, Finn, pull_suggested |
| `job_source_seen` | Known job re-observed on a source | NAV, Finn |
| `job_source_expired` | Job posting no longer active at source | NAV, Finn |
| `job_ad_updated` | Job posting content changed | NAV, Finn |
| `duplicate_candidate_detected` | Same job found on multiple sources | de-dupe logic |

### Enrichment

| event_type | Trigger | Typical source |
|------------|---------|---------------|
| `employer_info_enriched` | Company page data fetched | LinkedIn, company_page |
| `recruiter_identified` | Recruiter name/contact found | LinkedIn, recruiter_page |

### Email Signals

| event_type | Trigger | Typical source |
|------------|---------|---------------|
| `email_reply_detected` | Any reply to application | gmail |
| `rejection_detected` | Rejection signal in email | gmail |
| `interview_invite_detected` | Interview invitation in email | gmail |
| `followup_due_detected` | No response within follow-up window | gmail / manual |

### Application Signals

| event_type | Trigger | Typical source |
|------------|---------|---------------|
| `application_submitted_observed` | Application submitted at portal | portal, manual |
| `portal_status_changed` | Recruiter portal status update | portal |
| `jobsync_apply_clicked` | Candidate clicked Apply in JobSync | jobsync |

---

## Confidence Guidelines

| Confidence | Meaning | Reconciliation effect |
|------------|---------|----------------------|
| 0.9–1.0 | High — unambiguous signal (structured field, direct API) | May propose auto-status update; see #166 for policy |
| 0.6–0.89 | Medium — inferred or partially structured | Creates `needs_review` item |
| 0.0–0.59 | Low — heuristic, keyword match, ambiguous | Adds evidence note; no status proposal |

---

## Examples

### NAV / Finn.no — Lead Discovered

```json
{
  "event_id": "evt-nav-20260505-abc123",
  "source": "nav",
  "source_kind": "job_board",
  "event_type": "new_lead_detected",
  "observed_at": "2026-05-05T08:00:00+02:00",
  "received_at": "2026-05-05T08:01:12+02:00",
  "confidence": 1.0,
  "dedupe_key": "nav:new_lead_detected:1234567",
  "related_job_id": null,
  "raw_ref": { "external_id": "1234567", "url": "https://www.nav.no/arbeid/stillinger/1234567" },
  "evidence": [
    { "kind": "field", "label": "title", "value": "Senior Product Manager", "confidence": 1.0 },
    { "kind": "field", "label": "employer", "value": "Acme AS", "confidence": 1.0 }
  ],
  "suggested_effect": { "status_suggestion": "discovered", "action_suggestion": null, "requires_review": false },
  "metadata": {}
}
```

### Finn.no — Source Record Expired

```json
{
  "event_id": "evt-finn-exp-20260506-xyz",
  "source": "finn",
  "source_kind": "job_board",
  "event_type": "job_source_expired",
  "observed_at": "2026-05-06T06:00:00+02:00",
  "received_at": "2026-05-06T06:05:00+02:00",
  "confidence": 1.0,
  "dedupe_key": "finn:job_source_expired:9876543",
  "related_job_id": "job-xyz",
  "raw_ref": { "external_id": "9876543", "url": "https://www.finn.no/job/fulltime/ad.html?finnkode=9876543" },
  "evidence": [],
  "suggested_effect": { "status_suggestion": "archived", "action_suggestion": null, "requires_review": false },
  "metadata": {}
}
```

### Gmail — Rejection Detected

```json
{
  "event_id": "evt-gmail-rej-20260510-def",
  "source": "gmail",
  "source_kind": "email",
  "event_type": "rejection_detected",
  "observed_at": "2026-05-10T14:22:00+02:00",
  "received_at": "2026-05-10T14:23:00+02:00",
  "confidence": 0.87,
  "dedupe_key": "gmail:rejection_detected:msg_id_abc",
  "related_job_id": "job-xyz",
  "related_application_id": null,
  "raw_ref": { "message_id": "msg_id_abc", "url": null },
  "evidence": [
    { "kind": "snippet", "label": "email subject", "value": "Re: Søknad — Senior PM", "confidence": 0.9 },
    { "kind": "snippet", "label": "body excerpt", "value": "vi har valgt en annen kandidat", "confidence": 0.85 }
  ],
  "suggested_effect": { "status_suggestion": "rejected", "action_suggestion": "review_rejection", "requires_review": true },
  "metadata": {}
}
```

### Gmail — Interview Invite Detected

```json
{
  "event_id": "evt-gmail-inv-20260512-ghi",
  "source": "gmail",
  "source_kind": "email",
  "event_type": "interview_invite_detected",
  "observed_at": "2026-05-12T09:10:00+02:00",
  "received_at": "2026-05-12T09:11:00+02:00",
  "confidence": 0.92,
  "dedupe_key": "gmail:interview_invite_detected:msg_id_def",
  "related_job_id": "job-xyz",
  "raw_ref": { "message_id": "msg_id_def" },
  "evidence": [
    { "kind": "snippet", "label": "email subject", "value": "Invitasjon til intervju — Acme AS", "confidence": 0.95 },
    { "kind": "field", "label": "proposed_date", "value": "2026-05-15", "confidence": 0.8 }
  ],
  "suggested_effect": { "status_suggestion": "interview", "action_suggestion": "confirm_interview_date", "requires_review": true },
  "metadata": {}
}
```

### Recruiter Page — Enrichment Found

```json
{
  "event_id": "evt-recruiter-enrich-20260505-jkl",
  "source": "recruiter_page",
  "source_kind": "web_enrichment",
  "event_type": "recruiter_identified",
  "observed_at": "2026-05-05T10:30:00+02:00",
  "received_at": "2026-05-05T10:31:00+02:00",
  "confidence": 0.75,
  "dedupe_key": "recruiter_page:recruiter_identified:job-xyz:kari.nordmann",
  "related_job_id": "job-xyz",
  "raw_ref": { "url": "https://acme.no/team/kari-nordmann" },
  "evidence": [
    { "kind": "field", "label": "name", "value": "Kari Nordmann", "confidence": 0.9 },
    { "kind": "field", "label": "title", "value": "HR Manager", "confidence": 0.75 }
  ],
  "suggested_effect": null,
  "metadata": {}
}
```

### JobSync — Apply Clicked

```json
{
  "event_id": "evt-jobsync-apply-20260513-mno",
  "source": "jobsync",
  "source_kind": "ui_action",
  "event_type": "jobsync_apply_clicked",
  "observed_at": "2026-05-13T11:05:00+02:00",
  "received_at": "2026-05-13T11:05:01+02:00",
  "confidence": 1.0,
  "dedupe_key": "jobsync:jobsync_apply_clicked:job-xyz:20260513",
  "related_job_id": "job-xyz",
  "candidate_id": "default",
  "raw_ref": null,
  "evidence": [],
  "suggested_effect": { "status_suggestion": "apply_ready", "action_suggestion": "trigger_authoring", "requires_review": false },
  "metadata": {}
}
```

### Recruiter Portal — Status Changed

```json
{
  "event_id": "evt-portal-status-20260514-pqr",
  "source": "portal",
  "source_kind": "portal",
  "event_type": "portal_status_changed",
  "observed_at": "2026-05-14T08:00:00+02:00",
  "received_at": "2026-05-14T08:05:00+02:00",
  "confidence": 0.8,
  "dedupe_key": "portal:portal_status_changed:job-xyz:under_review",
  "related_job_id": "job-xyz",
  "raw_ref": { "url": "https://portal.example.com/apply/12345" },
  "evidence": [
    { "kind": "field", "label": "portal_status", "value": "Under review", "confidence": 0.8 }
  ],
  "suggested_effect": { "status_suggestion": null, "action_suggestion": "note_portal_status", "requires_review": true },
  "metadata": {}
}
```

---

## Hotspot Alignment

These existing modules produce events that must conform to this contract:

| Module | Current event type(s) | Notes |
|--------|-----------------------|-------|
| `jobpipe/cli/scan_gmail.py` | email reply, rejection, interview invite | Writes to `suggestion_leads` + `application_events` |
| `jobpipe/cli/pull_suggested.py` | new_lead_detected (Gmail suggestion) | Writes to `suggestion_leads` |
| `jobpipe/cli/pull_finn_search.py` | new_lead_detected, job_source_seen | Writes to `jobs`, `job_source_records` |
| `jobpipe/cli/pull_finn_ext.py` | job_ad_updated, job_source_expired | Writes to `job_source_records` |
| `jobpipe/cli/pull_sheets_csv.py` | new_lead_detected | Writes to `jobs` |
| `jobpipe/runtime/jobsync.py` | jobsync_apply_clicked | Writes to `application_events` |
| `jobpipe/cli/record_jobsync_event.py` | portal_status_changed, application_submitted_observed | Writes to `application_events` |

These modules do not yet emit structured `SourceEvent` objects — they write directly to the DB. The seam (#163) is a prerequisite for migrating them behind the event contract.

---

## Out of Scope

- DB schema migration
- Runtime `SourceEvent` dataclass or Python model
- Status reconciliation rules (defined in `docs/status-reconciliation-policy.md`)
- No direct JobSane DB writes
- No Supabase adapter

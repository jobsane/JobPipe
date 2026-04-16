from __future__ import annotations

from jobpipe.cli.bootstrap_state_db import import_application_snapshot, parse_profile_pack


PROFILE_SAMPLE = """# PROFILE_PACK — Lars

## 0) Candidate snapshot (quick facts)
- Name: Lars Værland
- Base: Oslo
- Languages: Norwegian + English
- Level: Mid-Senior
- Positioning: Product owner with service delivery depth

### Strategic direction (priority signal for triage)
Find broader digital delivery roles where cross-functional execution matters.

## 1) Target roles (TITLE ANCHORS) — keep if close match
### Primary targets (highest priority)
- Product Owner
- Service Owner

### Secondary targets
- Project Manager

### Hard NO (even as stepping stone)
- Retail sales

## 2) Must-haves (constraints)
### Location (OK if any)
- Oslo
- Drammen
Remote/Hybrid: always OK

## 3) Geo whitelist
Allowed postnummer prefix:
- "0" Oslo
- "3" Vestfold

## 4) Hard NO (auto-SKIP) — role types
Auto-SKIP if role is clearly:
- Nurse
- Cashier

## 5) Keyword signals (weighted)
### Tier A — Role anchors (highest weight)
- product owner | service owner

### Tier B — Domain anchors
- digital transformation | stakeholder management

## 6) Negative keywords (noise signals)
- cashier | retail

## 7) Evidence bullets (real achievements — STAR format)
### Example Employer — Role (2020-2022)
- Improved operations
- Led cross-functional team

## 8) Education
- MA, Example University, 2012
"""


def test_parse_profile_pack_extracts_core_fields():
    parsed = parse_profile_pack(PROFILE_SAMPLE)

    assert parsed["snapshot"]["name"] == "Lars Værland"
    assert parsed["snapshot"]["base"] == "Oslo"
    assert parsed["snapshot"]["level"] == "Mid-Senior"
    assert parsed["strategic_direction"] == "Find broader digital delivery roles where cross-functional execution matters."
    assert parsed["target_roles"]["primary"] == ["Product Owner", "Service Owner"]
    assert parsed["constraints"]["location_ok"] == ["Oslo", "Drammen"]
    assert parsed["geo_whitelist_prefixes"] == ["0", "3"]
    assert parsed["hard_no_roles"] == ["Nurse", "Cashier"]
    assert parsed["education"] == ["MA, Example University, 2012"]


def test_import_application_snapshot_builds_events_and_summary():
    state = {
        "updated_at": "2026-04-16T20:00:00Z",
        "applications": {
            "job-1": {
                "stages": ["shortlisted", "applied", "interview"],
                "outcome": "rejected",
                "notes": "Strong fit but no next round",
                "source": "gmail_scan",
                "email_subject": "Takk for praten",
                "email_date": "2026-04-15T10:00:00Z",
                "updated_at": "2026-04-15T10:00:00Z",
                "status": "rejected",
            },
            "job-2": {
                "stages": [],
                "outcome": "",
                "notes": "Needs manual follow-up",
                "source": "manual",
                "updated_at": "2026-04-14T09:00:00Z",
                "status": "",
            },
        },
    }

    events, summaries = import_application_snapshot("default", state)

    assert len(events) == 5
    assert len(summaries) == 2

    job1_events = [e for e in events if e["job_id"] == "job-1"]
    assert [e["event_type"] for e in job1_events] == ["shortlisted", "applied", "interview", "rejected"]
    assert job1_events[-1]["notes"] == "Strong fit but no next round"
    assert job1_events[-1]["source"] == "state_import:gmail_scan"

    job2_events = [e for e in events if e["job_id"] == "job-2"]
    assert [e["event_type"] for e in job2_events] == ["note_added"]
    assert job2_events[0]["notes"] == "Needs manual follow-up"

    summary1 = next(s for s in summaries if s["job_id"] == "job-1")
    assert summary1["current_stage"] == "interview"
    assert summary1["current_outcome"] == "rejected"
    assert summary1["effective_status"] == "rejected"

    summary2 = next(s for s in summaries if s["job_id"] == "job-2")
    assert summary2["current_stage"] == ""
    assert summary2["current_outcome"] == ""
    assert summary2["notes_latest"] == "Needs manual follow-up"

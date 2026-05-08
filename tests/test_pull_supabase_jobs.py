from __future__ import annotations

from datetime import datetime, timezone

import pytest

from jobpipe.cli import pull_supabase_jobs


def test_map_row_preserves_jobpipe_intake_fields_and_nav_metadata() -> None:
    row = {
        "id": "nav-123",
        "title": "Vil du lede produktarbeid?",
        "role": "Produktleder",
        "employer": "Acme AS",
        "municipality": "Oslo",
        "county": "Oslo",
        "counties": ["Oslo", "Viken"],
        "location": "Oslo sentrum",
        "postal_code": "0150",
        "description": "<p>Lead product work.</p>",
        "application_url": "https://apply.example/nav-123",
        "published_at": "2026-05-01T08:00:00Z",
        "updated_at": "2026-05-02T09:30:00Z",
        "expires_at": "2026-06-01T23:59:00Z",
        "application_due": "Snarest",
        "sector": "Privat",
        "occupation_level1": "IT",
        "occupation_level2": "Produktledelse",
        "extent": "Heltid",
        "engagement_type": "Fast",
        "position_count": 2,
        "status": "ACTIVE",
    }

    job = pull_supabase_jobs._map_row(row)

    assert job["uuid"] == "nav-123"
    assert job["job_id"] == "nav-123"
    assert job["title"] == "Vil du lede produktarbeid?"
    assert job["normalized_title"] == "Produktleder"
    assert job["employer_name"] == "Acme AS"
    assert job["description_html"] == "<p>Lead product work.</p>"
    assert job["applicationUrl"] == "https://apply.example/nav-123"
    assert job["applicationDue"] == "Snarest"
    assert job["work_city"] == "Oslo"
    assert job["work_county"] == "Oslo"
    assert job["work_postalCode"] == "0150"
    assert job["workLocations_json"] == '["Oslo", "Viken"]'
    assert job["sector"] == "Privat"
    assert job["occ_level1"] == "IT"
    assert job["occ_level2"] == "Produktledelse"
    assert job["extent"] == "Heltid"
    assert job["engagement_type"] == "Fast"
    assert job["position_count"] == "2"
    assert job["published_at"] == "2026-05-01T08:00:00Z"
    assert job["updated_at"] == "2026-05-02T09:30:00Z"
    assert job["expires_at"] == "2026-06-01T23:59:00Z"
    assert job["ad_updated"] == "2026-05-02T09:30:00Z"
    assert job["sourceurl"] == "https://arbeidsplassen.nav.no/stillinger/stilling/nav-123"
    assert pull_supabase_jobs._missing_required_fields(job) == []


def test_map_row_falls_back_to_expiry_date_for_application_due() -> None:
    job = pull_supabase_jobs._map_row(
        {
            "id": "nav-456",
            "title": "Designer",
            "employer": "Example AS",
            "description": "Design services.",
            "expires_at": "2026-06-15T12:00:00Z",
        }
    )

    assert job["applicationDue"] == "2026-06-15"


def test_map_row_normalizes_counties_string_and_sanitizes_raw_json() -> None:
    job = pull_supabase_jobs._map_row(
        {
            "id": "nav-789",
            "title": "Analyst",
            "employer": "Example AS",
            "description": "Analyze things.",
            "counties": '["Oslo"]',
            "raw_json": {
                "ad": {"title": "Analyst"},
                "service_role_key": "must-not-leak",
                "nested": {"authorization": "Bearer secret", "safe": "ok"},
            },
        }
    )

    assert job["workLocations_json"] == '["Oslo"]'
    assert job["source_raw_json"] == {"ad": {"title": "Analyst"}, "nested": {"safe": "ok"}}


def test_missing_required_fields_blocks_incomplete_rows() -> None:
    job = pull_supabase_jobs._map_row({"id": "nav-missing", "title": "Only title"})

    assert pull_supabase_jobs._missing_required_fields(job) == ["employer", "description"]


def test_fetch_all_active_jobs_defaults_to_public_jobs_with_active_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    def fake_fetch(url: str, headers: dict, retries: int = 4) -> list[dict]:
        urls.append(url)
        assert headers["apikey"] == "key"
        return []

    monkeypatch.setattr(pull_supabase_jobs, "_fetch_json", fake_fetch)
    monkeypatch.setattr(
        pull_supabase_jobs,
        "_utc_now",
        lambda: datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
    )

    rows = pull_supabase_jobs.fetch_all_active_jobs(
        "https://example.supabase.co",
        "key",
        since="2026-05-01T00:00:00Z",
        only_changed=True,
    )

    assert rows == []
    assert len(urls) == 1
    assert "/rest/v1/jobs?" in urls[0]
    assert "status=eq.ACTIVE" in urls[0]
    assert "expires_at=gt.2026-05-08T10%3A00%3A00Z" in urls[0]
    assert "updated_at=gt.2026-05-01T00%3A00%3A00Z" in urls[0]


def test_fetch_all_active_jobs_can_read_jobs_active_view(monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    def fake_fetch(url: str, headers: dict, retries: int = 4) -> list[dict]:
        urls.append(url)
        return []

    monkeypatch.setattr(pull_supabase_jobs, "_fetch_json", fake_fetch)

    pull_supabase_jobs.fetch_all_active_jobs(
        "https://example.supabase.co",
        "key",
        only_changed=False,
        relation="jobs_active",
    )

    assert "/rest/v1/jobs_active?" in urls[0]
    assert "status=eq.ACTIVE" not in urls[0]


def test_fetch_all_active_jobs_rejects_unknown_relation() -> None:
    with pytest.raises(ValueError, match="Unsupported Supabase jobs relation"):
        pull_supabase_jobs.fetch_all_active_jobs("https://example.supabase.co", "key", relation="jobs;drop")


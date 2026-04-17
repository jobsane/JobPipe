from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

from jobpipe.cli.export_dashboard import build_payload, render_dashboard_html
from jobpipe.cli.sync_ledger import (
    LEDGER_COLUMNS,
    EVENTS_COLUMNS,
    EventRow,
    init_db,
    insert_event,
    main as sync_ledger_main,
    merge_job_details,
    upsert_ledger,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_yaml(path: Path, text: str) -> None:
    path.write_text(dedent(text).strip() + "\n", encoding="utf-8")


def _write_profile_sources(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    state_path = tmp_path / "reports" / "application_state.json"
    _write_json(state_path, {"applications": {}})

    profile_path = tmp_path / "profile_pack.md"
    profile_path.write_text(
        dedent(
            """
            # PROFILE_PACK

            ## 0) Candidate snapshot
            - Base: Arendal
            - Languages: Norwegian + English
            - Positioning: Drives digital services across tech, business, and operations.

            ### Strategic direction
            Long-term goal is strategic ownership.

            ## 1) Target roles
            ### Primary targets
            - Produktleder
            - Tjenesteeier

            ### Secondary targets
            - CRM-ansvarlig

            ### Stepping-stone roles
            - Teamleder IT

            ## 2) Must-haves
            ### Location (OK if any)
            - Agder
            - Oslo
            Remote/Hybrid: always OK

            ## 7b) Market positioning context
            Motivation language core: "Jeg er motivert av roller der jeg kan forbedre digitale tjenester."
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    resume_path = tmp_path / "reports" / "resume.json"
    _write_json(
        resume_path,
        {
            "basics": {
                "name": "Lars Værland",
                "label": "Produkteier",
                "email": "lars@example.test",
                "phone": "+47 12345678",
                "summary": "Experienced product and service owner.",
            },
            "work": [
                {
                    "name": "Avinor",
                    "position": "Produktleder",
                    "startDate": "2024-01-01",
                    "endDate": "2025-01-01",
                    "highlights": ["Ledet produktteam", "Drevet digitalisering"],
                }
            ],
            "education": [
                {
                    "institution": "BI",
                    "area": "Endringsledelse",
                    "startDate": "2025-09-01",
                    "endDate": "2026-06-01",
                }
            ],
            "skills": [
                {
                    "name": "Produkt",
                    "keywords": ["Prioritering", "Backlog"],
                }
            ],
        },
    )

    profile_draft_path = tmp_path / "reports" / "profile_builder_state.json"
    _write_json(
        profile_draft_path,
        {
            "headline": "Endringsleder | Produkteier",
            "summary": "Tailored summary for current applications.",
        },
    )
    return state_path, profile_path, resume_path, profile_draft_path


def test_merge_job_details_carries_taxonomy_and_pack_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "out_runs" / "run_1"
    job_dir = run_dir / "nav_123"
    job_dir.mkdir(parents=True)

    _write_json(
        job_dir / "00_input.json",
        {
            "job_id": "nav_123",
            "status": "ACTIVE",
            "title": "Produktleder",
            "normalized_title": "produktleder",
            "employer_name": "Avinor",
            "work_city": "Oslo",
            "work_county": "Oslo",
            "work_postalCode": "0150",
            "applicationDue": "2026-04-30T00:00:00",
            "link": "https://arbeidsplassen.nav.no/stillinger/stilling/nav_123",
            "applicationUrl": "https://example.test/apply",
            "occ_level1": "IT",
            "occ_level2": "Produktledelse",
            "cat_type": "ESCO",
            "cat_code": "esco:123",
            "cat_name": "Product manager",
            "cat_score": "0.91",
            "suggested_by_platform": True,
        },
    )
    _write_json(
        job_dir / "01_triage.json",
        {
            "triage_decision": "REVIEW",
            "confidence": 0.72,
            "explanation": "Strong title match",
            "signals": ["target_title_match", "platform_suggested"],
        },
    )
    _write_json(job_dir / "03_profile_match.json", {"fit_score": 82, "overlaps": ["produktledelse"]})
    _write_json(job_dir / "04_pivot.json", {"pivot_score": 65})
    _write_json(
        job_dir / "05_moderator.json",
        {
            "final_decision": "APPLY_STRONGLY",
            "confidence": 0.88,
            "recommendation_reason": "fit=82, pivot=65",
        },
    )
    _write_json(
        job_dir / "06_application_pack.json",
        {
            "cover_letter_text": "Kort og konkret søknadsbrev.",
            "cv_highlights": ["Ledet produktteam", "Drevet digitalisering"],
        },
    )
    (job_dir / "07_cv_highlights.docx").write_bytes(b"docx")

    ev = EventRow(
        run_id="run_1",
        run_mtime=1713390000.0,
        job_id="nav_123",
        index_row={"job_id": "nav_123"},
        job_dir=job_dir,
    )

    row = merge_job_details(ev, include_description=False, desc_max_chars=0)
    docs = json.loads(row["generated_documents_json"])

    assert row["job_source"] == "nav"
    assert row["job_status"] == "ACTIVE"
    assert row["suggested_by_platform"] == 1
    assert row["normalized_title"] == "produktleder"
    assert row["occ_level1"] == "IT"
    assert row["occ_level2"] == "Produktledelse"
    assert row["cat_type"] == "ESCO"
    assert row["cat_code"] == "esco:123"
    assert row["cat_name"] == "Product manager"
    assert row["cat_score"] == 0.91
    assert row["pack_ready"] == 1
    assert row["pack_has_cover_letter"] == 1
    assert row["pack_highlight_count"] == 2
    assert row["pack_docx_ready"] == 1
    assert row["pack_generated_at"]
    assert {doc["kind"] for doc in docs} == {"application_pack_json", "cv_highlights_docx"}


def test_merge_job_details_falls_back_to_title_when_normalized_title_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "out_runs" / "run_1"
    job_dir = run_dir / "finn_123"
    job_dir.mkdir(parents=True)

    _write_json(
        job_dir / "00_input.json",
        {
            "job_id": "finn_123",
            "title": "Produktleder",
            "normalized_title": "",
            "employer_name": "Avinor AS",
            "source": "finn_search",
            "sourceurl": "https://www.finn.no/job/ad/123",
        },
    )
    _write_json(job_dir / "01_triage.json", {"triage_decision": "REVIEW", "signals": []})
    _write_json(job_dir / "03_profile_match.json", {"fit_score": 70})
    _write_json(job_dir / "04_pivot.json", {"pivot_score": 70})
    _write_json(job_dir / "05_moderator.json", {"final_decision": "APPLY", "confidence": 0.8})

    ev = EventRow(
        run_id="run_1",
        run_mtime=1713390000.0,
        job_id="finn_123",
        index_row={"job_id": "finn_123"},
        job_dir=job_dir,
    )

    row = merge_job_details(ev, include_description=False, desc_max_chars=0)

    assert row["normalized_title"] == "Produktleder"
    assert row["employer"] == "Avinor AS"
    assert row["job_source"] == "finn_search"


def test_build_payload_exposes_versioned_contract_fields(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "reports" / "ledger.sqlite"
    out_dir = tmp_path / "out_runs"
    out_dir.mkdir(parents=True)

    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(
        config_path,
        """
        pipeline_name: jobpipe_test
        models:
          triage: gpt-4.1-nano
        stages:
          - triage
          - moderate
        thresholds:
          review_min_fit: 30
          apply_fit: 67
          apply_strong_fit: 78
        safety_rules:
          geo_enabled: true
        """,
    )

    conn = init_db(sqlite_path)

    ledger_row = {name: "" for name, _ in LEDGER_COLUMNS}
    ledger_row.update(
        {
            "job_id": "nav_456",
            "run_id": "run_2",
            "run_mtime": 1713390500.0,
            "run_seen_at": "2026-04-17T21:00:00Z",
            "title": "Produktleder",
            "employer": "Avinor",
            "applicationDue": "2026-04-30",
            "source_url": "https://example.test/listing",
            "application_url": "https://example.test/apply",
            "job_source": "nav",
            "job_status": "ACTIVE",
            "suggested_by_platform": 1,
            "normalized_title": "produktleder",
            "occ_level1": "IT",
            "occ_level2": "Produktledelse",
            "cat_type": "ESCO",
            "cat_code": "esco:456",
            "cat_name": "Product manager",
            "cat_score": 0.97,
            "triage_decision": "REVIEW",
            "triage_confidence": 0.8,
            "triage_explanation": "Looks strong",
            "triage_signals": "target_title_match",
            "fit_score": 72,
            "pivot_score": 79,
            "final_decision": "APPLY",
            "final_confidence": 0.84,
            "recommendation_reason": "fit=72, pivot=79",
            "pack_ready": 1,
            "pack_generated_at": "2026-04-17T21:01:00Z",
            "pack_has_cover_letter": 1,
            "pack_highlight_count": 3,
            "pack_docx_ready": 1,
            "generated_documents_json": json.dumps(
                [
                    {
                        "kind": "application_pack_json",
                        "status": "saved",
                        "storage_path": "C:/data/nav_456/06_application_pack.json",
                    }
                ]
            ),
            "skip_reason": "passed",
            "closed_at": "2026-05-01T00:00:00Z",
            "updated_at": "2026-04-17T21:02:00Z",
            "raw_match_json": json.dumps({"overlaps": ["produktledelse"], "gaps": [], "hard_blockers": [], "notes": ""}),
            "raw_pivot_json": json.dumps({"pivot_type": "adjacent", "potential_risk": "low", "why_it_matters": ["Relevant scope"]}),
            "raw_moderator_json": json.dumps({"cv_focus": ["ownership"], "feedback_flags": []}),
        }
    )
    upsert_ledger(conn, ledger_row)

    event_row = {name: "" for name, _ in EVENTS_COLUMNS}
    event_row.update(
        {
            "run_id": "run_2",
            "job_id": "nav_456",
            "run_mtime": 1713390500.0,
            "seen_at": "2026-04-17T21:00:00Z",
            "job_source": "nav",
            "job_status": "ACTIVE",
            "skip_reason": "passed",
            "final_decision": "APPLY",
            "final_confidence": 0.84,
            "triage_decision": "REVIEW",
            "triage_confidence": 0.8,
            "fit_score": 72,
            "pivot_score": 79,
            "applicationDue": "2026-04-30",
            "title": "Produktleder",
            "employer": "Avinor",
        }
    )
    insert_event(conn, event_row)
    conn.commit()
    conn.close()

    state_path, profile_path, resume_path, profile_draft_path = _write_profile_sources(tmp_path)

    payload = build_payload(
        sqlite_path,
        out_dir,
        state_path=state_path,
        config_path=config_path,
        profile_path=profile_path,
        resume_path=resume_path,
        profile_draft_path=profile_draft_path,
    )

    assert payload["schema_version"] == "jobpipe.dashboard.v2"
    assert payload["thresholds"]["apply_fit"] == 67
    assert payload["config_snapshot"]["pipeline_name"] == "jobpipe_test"
    assert payload["config_snapshot"]["stages"] == ["triage", "moderate"]
    assert payload["payload_meta"]["budget_state"] == "ok"
    assert payload["payload_meta"]["event_rows_before"] == 1
    assert payload["payload_meta"]["event_rows_after"] == 1

    job = payload["jobs"][0]
    assert job["job_source"] == "nav"
    assert job["job_status"] == "ACTIVE"
    assert job["suggested_by_platform"] is True
    assert job["normalized_title"] == "produktleder"
    assert job["occ_level1"] == "IT"
    assert job["cat_name"] == "Product manager"
    assert job["pack_ready"] is True
    assert job["pack_has_cover_letter"] is True
    assert job["pack_docx_ready"] is True
    assert job["pack_highlight_count"] == 3
    assert job["generated_documents"][0]["storage_path"] == "C:/data/nav_456/06_application_pack.json"
    assert job["closed_at"] == "2026-05-01T00:00:00Z"

    event = payload["events"][0]
    assert event["job_source"] == "nav"
    assert event["job_status"] == "ACTIVE"
    assert event["skip_reason"] == "passed"

    profile = payload["profile"]
    assert profile["basics"]["name"] == "Lars Værland"
    assert profile["basics"]["base"] == "Arendal"
    assert profile["builder_state"]["headline"] == "Endringsleder | Produkteier"
    assert profile["builder_state"]["summary"] == "Tailored summary for current applications."
    assert profile["builder_state_path"].endswith("profile_builder_state.json")
    assert profile["target_roles"]["primary"] == ["Produktleder", "Tjenesteeier"]
    assert profile["target_geography"]["locations"] == ["Agder", "Oslo"]
    assert profile["target_geography"]["remote_policy"] == "always OK"
    assert profile["strength_areas"][0]["keywords"] == ["Prioritering", "Backlog"]
    assert profile["evidence_highlights"][0]["text"] == "Ledet produktteam"
    assert profile["motivation_language"] == "Jeg er motivert av roller der jeg kan forbedre digitale tjenester."


def test_build_payload_reports_payload_meta_and_prunes_event_history(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "reports" / "ledger.sqlite"
    out_dir = tmp_path / "out_runs"
    out_dir.mkdir(parents=True)
    state_path, profile_path, resume_path, profile_draft_path = _write_profile_sources(tmp_path)

    conn = init_db(sqlite_path)

    ledger_row = {name: "" for name, _ in LEDGER_COLUMNS}
    ledger_row.update(
        {
            "job_id": "nav_hist_1",
            "run_id": "run_hist",
            "run_mtime": 1713390500.0,
            "run_seen_at": "2026-04-17T21:00:00Z",
            "title": "Produktleder",
            "employer": "Avinor",
            "job_source": "nav",
            "job_status": "ACTIVE",
            "triage_decision": "REVIEW",
            "final_decision": "APPLY",
            "skip_reason": "passed",
            "fit_score": 70,
            "pivot_score": 78,
            "updated_at": "2026-04-17T21:02:00Z",
        }
    )
    upsert_ledger(conn, ledger_row)

    for idx in range(25):
        event_row = {name: "" for name, _ in EVENTS_COLUMNS}
        event_row.update(
            {
                "run_id": f"run_{idx:02d}",
                "job_id": "nav_hist_1",
                "run_mtime": 1713390500.0 + idx,
                "seen_at": f"2026-04-17T21:{idx:02d}:00Z",
                "job_source": "nav",
                "job_status": "ACTIVE",
                "skip_reason": "passed",
                "final_decision": "APPLY",
                "triage_decision": "REVIEW",
                "triage_confidence": 0.8,
                "fit_score": 70,
                "pivot_score": 78,
                "title": f"Produktleder {idx}",
                "employer": "Avinor",
            }
        )
        insert_event(conn, event_row)
    conn.commit()
    conn.close()

    payload = build_payload(
        sqlite_path,
        out_dir,
        state_path=state_path,
        profile_path=profile_path,
        resume_path=resume_path,
        profile_draft_path=profile_draft_path,
        max_event_rows=10,
        min_event_rows=3,
    )

    meta = payload["payload_meta"]
    assert meta["event_rows_before"] == 25
    assert meta["event_rows_after"] == 10
    assert meta["pruned_event_count"] == 15
    assert meta["budget_state"] == "ok"
    assert meta["size_bytes"] > 0
    assert len(payload["events"]) == 10
    assert payload["events"][0]["run_id"] == "run_15"


def test_sync_ledger_fixture_round_trip_builds_dashboard_payload(tmp_path: Path) -> None:
    out_dir = tmp_path / "out_runs"
    run_dir = out_dir / "run_fixture"
    job_dir = run_dir / "nav_789"
    job_dir.mkdir(parents=True)

    (run_dir / "index.jsonl").write_text('{"job_id":"nav_789"}\n', encoding="utf-8")
    _write_json(
        job_dir / "00_input.json",
        {
            "job_id": "nav_789",
            "status": "ACTIVE",
            "source": "nav",
            "title": "Tjenesteeier",
            "normalized_title": "tjenesteeier",
            "employer_name": "DIPS",
            "work_city": "Oslo",
            "work_county": "Oslo",
            "work_postalCode": "0150",
            "applicationDue": "2026-05-12T00:00:00",
            "link": "https://example.test/nav_789",
            "applicationUrl": "https://example.test/apply_789",
            "occ_level1": "IT",
            "occ_level2": "Tjenesteforvaltning",
            "cat_type": "ESCO",
            "cat_code": "esco:789",
            "cat_name": "Service owner",
            "cat_score": "0.88",
            "suggested_by_platform": False,
        },
    )
    _write_json(
        job_dir / "01_triage.json",
        {
            "triage_decision": "REVIEW",
            "confidence": 0.74,
            "explanation": "Strong ownership scope",
            "signals": ["target_title_match"],
        },
    )
    _write_json(job_dir / "03_profile_match.json", {"fit_score": 76, "overlaps": ["tjenesteeier"]})
    _write_json(job_dir / "04_pivot.json", {"pivot_score": 61})
    _write_json(
        job_dir / "05_moderator.json",
        {
            "final_decision": "APPLY",
            "confidence": 0.86,
            "recommendation_reason": "fit=76, pivot=61",
        },
    )
    _write_json(
        job_dir / "06_application_pack.json",
        {
            "cover_letter_text": "Kort søknadstekst.",
            "cv_highlights": ["Ledet tjenesteforvaltning"],
        },
    )

    sqlite_path = tmp_path / "reports" / "ledger.sqlite"
    csv_path = tmp_path / "reports" / "ledger_latest.csv"
    sync_ledger_main(
        [
            "--out",
            str(out_dir),
            "--reports",
            str(tmp_path / "reports"),
            "--sqlite",
            str(sqlite_path),
            "--csv",
            str(csv_path),
        ]
    )

    state_path, profile_path, resume_path, profile_draft_path = _write_profile_sources(tmp_path)
    payload = build_payload(
        sqlite_path,
        out_dir,
        state_path=state_path,
        profile_path=profile_path,
        resume_path=resume_path,
        profile_draft_path=profile_draft_path,
    )

    assert csv_path.exists()
    assert len(payload["jobs"]) == 1
    assert len(payload["events"]) == 1
    job = payload["jobs"][0]
    assert job["job_id"] == "nav_789"
    assert job["job_source"] == "nav"
    assert job["normalized_title"] == "tjenesteeier"
    assert job["final_decision"] == "APPLY"
    assert job["applicationDue"] == "2026-05-12"
    assert job["pack_ready"] is True
    assert payload["payload_meta"]["event_rows_before"] == 1


def test_render_dashboard_html_reuses_template_for_server_and_static_modes(tmp_path: Path) -> None:
    template_path = tmp_path / "dashboard_template.html"
    template_path.write_text(
        "<html><head></head><body><script>let DATA = /*__DASHBOARD_DATA__*/;</script></body></html>",
        encoding="utf-8",
    )

    html = render_dashboard_html(
        {
            "schema_version": "jobpipe.dashboard.v2",
            "jobs": [],
            "events": [],
        },
        template_path,
        head_injection='<meta name="jobpipe-server" content="1">',
    )

    assert '<meta name="jobpipe-server" content="1">' in html
    assert '"schema_version": "jobpipe.dashboard.v2"' in html
    assert "/*__DASHBOARD_DATA__*/" not in html

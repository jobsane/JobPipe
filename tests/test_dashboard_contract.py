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
        job_dir / "08_triage_decision_v3.json",
        {
            "label": "shortlist",
            "weighted_score": 77.0,
            "confidence": 78,
            "needs_ambiguity_pass": False,
            "blockers": [],
            "boosts": ["strong_core_tech_match"],
            "summary": "shortlist from weighted feature aggregation.",
        },
    )
    _write_json(
        job_dir / "09_advantage_assessment_v3.json",
        {
            "advantage_type": "strong_fit",
            "advantage_signals": ["produktledelse", "strong_core_tech_alignment"],
            "objection_signals": ["public-sector context"],
            "neutralizing_evidence": ["produktledelse"],
            "stretch_level": "low",
            "review_priority": 84,
            "confidence": 79,
            "summary": "strong fit with minor objection",
        },
    )
    _write_json(
        job_dir / "10_narrative_strategy_v3.json",
        {
            "positioning_angle": "Direkte relevant erfaring som kan levere raskt.",
            "brand_frame": "Brobygger mellom produkt og drift",
            "why_me_now": "Har allerede erfaring som matcher kjernen i rollen.",
            "top_value_props": ["produktledelse", "strong_core_tech_alignment"],
            "objections_to_handle": ["public-sector context"],
            "cv_focus_order": ["ownership", "delivery"],
            "cover_letter_strategy": "Åpne med relevant eierskap.",
            "confidence": 80,
            "summary": "Narrative strategy for Produktleder.",
        },
    )
    _write_json(
        job_dir / "07_moderator.json",
        {
            "final_decision": "APPLY_STRONGLY",
            "confidence": 0.88,
            "recommendation_reason": "fit=82, pivot=65",
        },
    )
    _write_json(
        job_dir / "08_application_pack.json",
        {
            "cover_letter_text": "Kort og konkret søknadsbrev.",
            "cv_highlights": ["Ledet produktteam", "Drevet digitalisering"],
        },
    )
    (job_dir / "09_cv_highlights.docx").write_bytes(b"docx")

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
    assert row["triage_v3_label"] == "shortlist"
    assert row["advantage_type"] == "strong_fit"
    assert row["advantage_review_priority"] == 84
    assert row["narrative_brand_frame"] == "Brobygger mellom produkt og drift"
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
    _write_json(job_dir / "07_moderator.json", {"final_decision": "APPLY", "confidence": 0.8})

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


def test_merge_job_details_synthesizes_v3_detail_from_index_summary_when_artifacts_are_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "out_runs" / "run_1"
    job_dir = run_dir / "nav_idx_1"
    job_dir.mkdir(parents=True)

    _write_json(
        job_dir / "00_input.json",
        {
            "job_id": "nav_idx_1",
            "title": "Produkteier",
            "employer_name": "Avinor",
            "source": "nav",
        },
    )

    ev = EventRow(
        run_id="run_1",
        run_mtime=1713390000.0,
        job_id="nav_idx_1",
        index_row={
            "job_id": "nav_idx_1",
            "triage_v3_label": "shortlist",
            "triage_v3_weighted_score": 73.0,
            "triage_v3_confidence": 77,
            "triage_v3_needs_ambiguity": False,
            "triage_ambiguity_label": "shortlist",
            "triage_ambiguity_reason": "Borderline review upgraded.",
            "advantage_type": "strong_fit",
            "advantage_review_priority": 85,
            "narrative_positioning_angle": "Direkte relevant erfaring som kan levere raskt.",
            "narrative_brand_frame": "Brobygger mellom produkt og drift",
        },
        job_dir=job_dir,
    )

    row = merge_job_details(ev, include_description=False, desc_max_chars=0)

    assert json.loads(row["raw_triage_decision_v3_json"])["label"] == "shortlist"
    assert json.loads(row["raw_triage_ambiguity_v3_json"])["resolved_label"] == "shortlist"
    assert json.loads(row["raw_advantage_assessment_v3_json"])["advantage_type"] == "strong_fit"
    assert json.loads(row["raw_narrative_strategy_v3_json"])["brand_frame"] == "Brobygger mellom produkt og drift"


def test_merge_job_details_reuses_projection_store_when_input_and_stage_artifacts_are_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "out_runs" / "run_proj_ledger"
    job_dir = run_dir / "nav_proj_ledger_1"
    job_dir.mkdir(parents=True)

    ev = EventRow(
        run_id="run_proj_ledger",
        run_mtime=1713390700.0,
        job_id="nav_proj_ledger_1",
        index_row={"job_id": "nav_proj_ledger_1"},
        job_dir=job_dir,
    )

    row = merge_job_details(
        ev,
        include_description=True,
        desc_max_chars=200,
        projection_store={
            "inputEnrichment": {
                "run_proj_ledger::nav_proj_ledger_1": {
                    "employer": "Vy",
                    "normalized_title": "produktleder",
                    "application_url": "https://example.test/apply-proj-ledger",
                    "source_url": "https://example.test/nav-proj-ledger",
                    "applicationDue": "2026-06-10",
                    "work_city": "Oslo",
                    "work_county": "Oslo",
                    "job_source": "nav",
                }
            },
            "detailProjections": {
                "run_proj_ledger::nav_proj_ledger_1": {
                    "decision_brief": {
                        "schema_version": "jobpipe.decision-brief.v1",
                        "final_decision": "APPLY",
                        "fit_score": 83,
                        "pivot_score": 57,
                        "overlaps": ["Produktledelse"],
                        "gaps": ["Ingen kollektivbakgrunn"],
                        "cv_focus": ["Produktansvar"],
                        "rationale": "Sterk produktmatch.",
                    },
                    "application_case_projection": {
                        "schema_version": "jobpipe.application-case-projection.v1",
                        "job_summary": {
                            "title": "Produktleder",
                            "company": "Vy",
                            "location": "Oslo, Oslo",
                            "job_source": "nav",
                            "source_url": "https://example.test/nav-proj-ledger",
                            "application_url": "https://example.test/apply-proj-ledger",
                            "application_due": "2026-06-10",
                            "description_snippet": "Own roadmap and delivery.",
                        },
                    },
                }
            },
        },
    )

    assert row["title"] == "Produktleder"
    assert row["employer"] == "Vy"
    assert row["application_url"] == "https://example.test/apply-proj-ledger"
    assert row["source_url"] == "https://example.test/nav-proj-ledger"
    assert row["applicationDue"] == "2026-06-10"
    assert row["job_source"] == "nav"
    assert row["fit_score"] == 83
    assert row["pivot_score"] == 57
    assert row["final_decision"] == "APPLY"
    assert row["recommendation_reason"] == "Sterk produktmatch."
    assert row["cv_focus"] == "Produktansvar"
    assert row["description_snip"] == "Own roadmap and delivery."
    assert json.loads(row["raw_match_json"])["overlaps"] == ["Produktledelse"]
    assert json.loads(row["raw_pivot_json"])["pivot_score"] == 57
    assert json.loads(row["raw_moderator_json"])["final_decision"] == "APPLY"


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
            "raw_triage_decision_v3_json": json.dumps(
                {
                    "label": "shortlist",
                    "weighted_score": 76.0,
                    "confidence": 78,
                    "needs_ambiguity_pass": False,
                    "blockers": [],
                    "boosts": ["strong_core_tech_match"],
                }
            ),
            "raw_advantage_assessment_v3_json": json.dumps(
                {
                    "advantage_type": "strong_fit",
                    "advantage_signals": ["Produktledelse"],
                    "objection_signals": ["public-sector domain"],
                    "neutralizing_evidence": ["Relevant scope"],
                    "review_priority": 82,
                }
            ),
            "raw_narrative_strategy_v3_json": json.dumps(
                {
                    "positioning_angle": "Direkte relevant erfaring som kan levere raskt.",
                    "brand_frame": "Brobygger mellom produkt og drift",
                    "why_me_now": "Har allerede erfaring som matcher kjernen i rollen.",
                    "top_value_props": ["Produktledelse", "Tverrfaglig samhandling"],
                    "objections_to_handle": ["public-sector domain"],
                    "cv_focus_order": ["ownership", "delivery"],
                    "cover_letter_strategy": "Åpne med relevant eierskap.",
                }
            ),
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
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=test-openai\n",
        encoding="utf-8",
    )
    _write_json(tmp_path / "reports" / "gmail_credentials.json", {"installed": True})
    _write_json(tmp_path / "reports" / "gmail_token.json", {"token": "abc"})
    _write_json(
        tmp_path / "reports" / "settings_state.json",
        {
            "targeting": {
                "primary_roles_text": "Produktleder\nTjenesteeier",
                "domain_focus_text": "Offentlig sektor",
            },
            "integrations": {
                "reactive_resume": {"enabled": True, "base_url": "http://localhost:3000"},
                "document_workspace": {"enabled": True, "base_url": "https://docs.example.test/workspace"},
                "gmail": {"status_detection_enabled": True, "lead_intake_enabled": False},
            },
        },
    )

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
    assert job["triage_v3_label"] == ""
    assert job["advantage_type"] == ""
    assert job["narrative_brand_frame"] == ""
    assert job["generated_documents"][0]["storage_path"] == "C:/data/nav_456/06_application_pack.json"
    assert job["closed_at"] == "2026-05-01T00:00:00Z"
    assert job["detail"]["triage_v3_label"] == "shortlist"
    assert job["detail"]["advantage_type"] == "strong_fit"
    assert job["detail"]["narrative_brand_frame"] == "Brobygger mellom produkt og drift"
    assert job["detail"]["narrative_cv_focus_order"] == ["ownership", "delivery"]
    assert job["detail"]["decision_brief"]["schema_version"] == "jobpipe.decision-brief.v1"
    assert job["detail"]["decision_brief"]["advantage_type"] == "strong_fit"
    assert job["detail"]["application_case_projection"]["schema_version"] == "jobpipe.application-case-projection.v1"
    assert job["detail"]["application_case_projection"]["job_summary"]["title"] == "Produktleder"

    event = payload["events"][0]
    assert event["job_source"] == "nav"
    assert event["job_status"] == "ACTIVE"
    assert event["skip_reason"] == "passed"

    profile = payload["profile"]
    assert profile["schema_version"] == "jobpipe.profile-layer.v2"
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
    assert profile["derived"]["profile_snapshot"]["target_roles"][0] == "Produktleder"
    assert profile["derived"]["triage_profile"]["skill_clusters"][0] == "Produkt"
    assert profile["derived"]["counts"]["role_records"] == 1

    settings = payload["settings"]
    assert settings["schema_version"] == "jobpipe.settings.v1"
    assert settings["targeting"]["primary_roles_text"] == "Produktleder\nTjenesteeier"
    assert settings["targeting"]["domain_focus_text"] == "Offentlig sektor"
    assert settings["targeting"]["profile_defaults"]["primary_roles"] == ["Produktleder", "Tjenesteeier"]
    assert settings["targeting"]["profile_defaults"]["preferred_domains"] == ["Produkt"]
    assert settings["targeting"]["profile_defaults"]["target_title_patterns"][:3] == [
        "Produktleder",
        "Tjenesteeier",
        "CRM-ansvarlig",
    ]
    assert settings["targeting"]["profile_defaults"]["profile_snapshot_id"] == "profile_snapshot:default"
    assert settings["integrations"]["reactive_resume"]["status"] == "ready"
    assert settings["integrations"]["document_workspace"]["status"] == "ready"
    assert settings["integrations"]["document_workspace"]["base_url"] == "https://docs.example.test/workspace"
    assert settings["integrations"]["gmail"]["status"] == "ready"
    assert settings["integrations"]["gmail"]["lead_target_path"] == str(tmp_path / "jobs_delta.jsonl")
    assert settings["integrations"]["gmail"]["status_target_path"] == str(tmp_path / "reports" / "application_state.json")
    assert settings["integrations"]["gmail"]["lead_flow"] == "pre_triage_lead_connector"
    assert settings["integrations"]["gmail"]["status_flow"] == "application_state_updates"
    assert settings["secrets"]["openai_api_key_present"] is True
    assert settings["paths"]["data_root"] == str(tmp_path)
    assert settings["paths"]["profile_layer_state"] == str(tmp_path / "reports" / "profile_layer_state.json")
    assert (tmp_path / "reports" / "profile_layer_state.json").exists()

    automations = payload["automations"]
    assert automations["schema_version"] == "jobpipe.automation.v1"
    assert automations["connector_counts"]["nav_connector_rows"] == 0
    assert automations["connector_counts"]["lead_connector_rows"] == 0
    assert automations["connector_counts"]["merged_queue_rows"] == 0
    assert {action["key"] for action in automations["actions"]} >= {
        "scheduled_full_run",
        "nav_refresh",
        "mailbox_leads_dry_run",
        "merge_connectors",
        "export_dashboard",
    }
    assert automations["scheduled_flow"]["schema_version"] == "jobpipe.scheduled-run-control.v1"
    assert automations["scheduled_flow"]["summary"]["status"] == "never_run"
    assert automations["scheduled_flow"]["entrypoint_command"] == ".\\go.ps1"


def test_build_payload_normalizes_shared_app_status_but_keeps_internal_timeline(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "reports" / "ledger.sqlite"
    out_dir = tmp_path / "out_runs"
    out_dir.mkdir(parents=True)

    config_path = tmp_path / "pipeline.yaml"
    _write_yaml(
        config_path,
        """
        pipeline_name: jobpipe_test
        thresholds:
          review_min_fit: 30
          apply_fit: 67
          apply_strong_fit: 78
        """,
    )

    conn = init_db(sqlite_path)
    ledger_row = {name: "" for name, _ in LEDGER_COLUMNS}
    ledger_row.update(
        {
            "job_id": "nav_shared_1",
            "run_id": "run_shared",
            "run_mtime": 1713390600.0,
            "run_seen_at": "2026-04-18T10:00:00Z",
            "title": "Produktleder",
            "employer": "Avinor",
            "job_source": "nav",
            "job_status": "ACTIVE",
            "triage_decision": "REVIEW",
            "final_decision": "APPLY",
            "skip_reason": "passed",
            "fit_score": 75,
            "pivot_score": 68,
            "updated_at": "2026-04-18T10:00:00Z",
        }
    )
    upsert_ledger(conn, ledger_row)
    conn.commit()
    conn.close()

    state_path, profile_path, resume_path, profile_draft_path = _write_profile_sources(tmp_path)
    _write_json(
        state_path,
        {
            "applications": {
                "nav_shared_1": {
                    "stages": ["shortlisted", "called"],
                    "outcome": None,
                    "updated_at": "2026-04-18T10:00:00Z",
                    "source": "manual",
                }
            }
        },
    )

    payload = build_payload(
        sqlite_path,
        out_dir,
        state_path=state_path,
        config_path=config_path,
        profile_path=profile_path,
        resume_path=resume_path,
        profile_draft_path=profile_draft_path,
    )

    job = payload["jobs"][0]
    assert job["app_status"] == "draft"
    assert json.loads(job["app_stages"]) == ["shortlisted", "called"]
    assert job["app_outcome"] == ""


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
        job_dir / "07_moderator.json",
        {
            "final_decision": "APPLY",
            "confidence": 0.86,
            "recommendation_reason": "fit=76, pivot=61",
        },
    )
    _write_json(
        job_dir / "08_application_pack.json",
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


def test_build_payload_reuses_projection_store_for_input_enrichment(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "reports" / "ledger.sqlite"
    out_dir = tmp_path / "out_runs"
    job_dir = out_dir / "run_proj" / "nav_proj_1"
    job_dir.mkdir(parents=True)

    _write_json(
        job_dir / "00_input.json",
        {
            "job_id": "nav_proj_1",
            "title": "Produktleder",
            "normalized_title": "produktleder",
            "employer_name": "Avinor",
            "work_city": "Oslo",
            "work_county": "Oslo",
            "work_postalCode": "0150",
            "applicationDue": "2026-05-12T00:00:00",
            "link": "https://example.test/nav_proj_1",
            "applicationUrl": "https://example.test/apply_proj_1",
            "source": "nav",
        },
    )

    conn = init_db(sqlite_path)
    ledger_row = {name: "" for name, _ in LEDGER_COLUMNS}
    ledger_row.update(
        {
            "job_id": "nav_proj_1",
            "run_id": "run_proj",
            "run_mtime": 1713390500.0,
            "run_seen_at": "2026-04-17T21:00:00Z",
            "title": "Produktleder",
            "employer": "",
            "normalized_title": "",
            "work_city": "",
            "work_county": "",
            "work_postalCode": "",
            "applicationDue": "",
            "source_url": "",
            "application_url": "",
            "description_snip": "Own roadmap and delivery.",
            "job_source": "",
            "job_status": "ACTIVE",
            "triage_decision": "REVIEW",
            "final_decision": "APPLY",
            "skip_reason": "passed",
            "fit_score": 75,
            "pivot_score": 68,
            "updated_at": "2026-04-18T10:00:00Z",
        }
    )
    upsert_ledger(conn, ledger_row)
    conn.commit()
    conn.close()

    state_path, profile_path, resume_path, profile_draft_path = _write_profile_sources(tmp_path)

    first_payload = build_payload(
        sqlite_path,
        out_dir,
        state_path=state_path,
        profile_path=profile_path,
        resume_path=resume_path,
        profile_draft_path=profile_draft_path,
    )
    first_job = first_payload["jobs"][0]
    assert first_job["employer"] == "Avinor"
    assert first_job["application_url"] == "https://example.test/apply_proj_1"
    assert first_job["source_url"] == "https://example.test/nav_proj_1"
    assert first_job["applicationDue"] == "2026-05-12"

    projection_store_path = tmp_path / "reports" / "projection_store.json"
    projection_store = json.loads(projection_store_path.read_text(encoding="utf-8"))
    assert projection_store["schemaVersion"] == "jobpipe.projection-store.v1"
    assert "run_proj::nav_proj_1" in projection_store["inputEnrichment"]

    (job_dir / "00_input.json").unlink()

    second_payload = build_payload(
        sqlite_path,
        out_dir,
        state_path=state_path,
        profile_path=profile_path,
        resume_path=resume_path,
        profile_draft_path=profile_draft_path,
    )
    second_job = second_payload["jobs"][0]
    assert second_job["employer"] == "Avinor"
    assert second_job["application_url"] == "https://example.test/apply_proj_1"
    assert second_job["source_url"] == "https://example.test/nav_proj_1"
    assert second_job["applicationDue"] == "2026-05-12"


def test_build_payload_prefers_persisted_detail_projection_when_available(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "reports" / "ledger.sqlite"
    out_dir = tmp_path / "out_runs"
    job_dir = out_dir / "run_proj_detail" / "nav_proj_detail_1"
    job_dir.mkdir(parents=True)

    conn = init_db(sqlite_path)
    ledger_row = {name: "" for name, _ in LEDGER_COLUMNS}
    ledger_row.update(
        {
            "job_id": "nav_proj_detail_1",
            "run_id": "run_proj_detail",
            "run_mtime": 1713390600.0,
            "run_seen_at": "2026-04-17T22:00:00Z",
            "title": "Produktleder",
            "employer": "Avinor",
            "job_source": "nav",
            "job_status": "ACTIVE",
            "triage_decision": "REVIEW",
            "final_decision": "APPLY",
            "skip_reason": "passed",
            "fit_score": 61,
            "pivot_score": 42,
            "updated_at": "2026-04-18T11:00:00Z",
            "description_snip": "Thin row snippet.",
        }
    )
    upsert_ledger(conn, ledger_row)
    conn.commit()
    conn.close()

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    projection_store_path = reports_dir / "projection_store.json"
    projection_store_path.write_text(
        json.dumps(
            {
                "schemaVersion": "jobpipe.projection-store.v1",
                "inputEnrichment": {},
                "detailProjections": {
                    "run_proj_detail::nav_proj_detail_1": {
                        "decision_brief": {
                            "schema_version": "jobpipe.decision-brief.v1",
                            "final_decision": "APPLY_STRONGLY",
                            "fit_score": 89,
                            "pivot_score": 64,
                            "advantage_type": "strong_fit",
                            "advantageous_match_score": 83,
                            "review_priority": 1,
                            "positioning_angle": "Projection-first positioning angle.",
                            "brand_frame": "Projection-first brand frame.",
                            "applicant_pool_hypothesis": "Projection-first applicant pool hypothesis.",
                            "recruiter_hook": "Projection-first recruiter hook.",
                            "rationale": "Projection-first recommendation rationale.",
                            "overlaps": ["Projection overlap"],
                            "gaps": ["Projection gap"],
                            "differentiation_signals": ["Projection differentiator"],
                            "top_value_props": ["Projection value"],
                            "cv_focus": ["Projection focus"],
                            "cover_letter_angle": "Projection letter angle.",
                        },
                        "application_case_projection": {
                            "schema_version": "jobpipe.application-case-projection.v1",
                            "external_source": "jobpipe",
                            "external_id": "nav_proj_detail_1",
                            "run_id": "run_proj_detail",
                            "status": "",
                            "updated_at": "2026-04-18T11:00:00Z",
                            "job_summary": {
                                "title": "Produktleder",
                                "company": "Avinor",
                                "location": "Oslo, Oslo",
                                "job_source": "nav",
                                "source_url": "https://example.test/nav-proj-detail",
                                "application_url": "https://example.test/apply-proj-detail",
                                "application_due": "2026-06-05",
                                "description_snippet": "Projection snippet.",
                            },
                            "decision_brief": {},
                            "artifact_plan": {},
                        },
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state_path, profile_path, resume_path, profile_draft_path = _write_profile_sources(tmp_path)
    _write_json(
        state_path,
        {
            "version": 2,
            "updated_at": "2026-04-19T18:40:00Z",
            "applications": {
                "nav_exp_1": {
                    "stages": ["applied"],
                    "outcome": None,
                    "status": "applied",
                    "source": "manual",
                    "updated_at": "2026-04-19T18:36:00Z",
                },
                "nav_exp_2": {
                    "stages": ["applied", "interview"],
                    "outcome": "accepted",
                    "status": "accepted",
                    "source": "manual",
                    "updated_at": "2026-04-19T18:37:00Z",
                },
            },
        },
    )

    payload = build_payload(
        sqlite_path,
        out_dir,
        state_path=state_path,
        profile_path=profile_path,
        resume_path=resume_path,
        profile_draft_path=profile_draft_path,
    )

    job = payload["jobs"][0]
    assert job["detail"]["decision_brief"]["final_decision"] == "APPLY_STRONGLY"
    assert job["detail"]["decision_brief"]["fit_score"] == 89
    assert job["detail"]["decision_brief"]["advantageous_match_score"] == 83
    assert job["detail"]["decision_brief"]["applicant_pool_hypothesis"] == "Projection-first applicant pool hypothesis."
    assert job["detail"]["decision_brief"]["recruiter_hook"] == "Projection-first recruiter hook."
    assert job["detail"]["decision_brief"]["differentiation_signals"] == ["Projection differentiator"]
    assert job["detail"]["decision_brief"]["rationale"] == "Projection-first recommendation rationale."
    assert job["detail"]["application_case_projection"]["job_summary"]["application_url"] == "https://example.test/apply-proj-detail"


def test_build_payload_exposes_latest_experiment_review_queue(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "reports" / "ledger.sqlite"
    out_dir = tmp_path / "out_runs"

    conn = init_db(sqlite_path)
    ledger_row_primary = {name: "" for name, _ in LEDGER_COLUMNS}
    ledger_row_primary.update(
        {
            "job_id": "nav_exp_1",
            "run_id": "run_exp",
            "title": "Produktleder",
            "employer": "Vy",
            "job_source": "nav",
            "final_decision": "APPLY",
            "skip_reason": "passed",
            "fit_score": 75,
            "pivot_score": 58,
            "updated_at": "2026-04-19T18:18:00Z",
            "raw_advantage_assessment_v3_json": json.dumps(
                {
                    "advantage_type": "strong_fit",
                    "advantageous_match_score": 83,
                    "review_priority": 84,
                    "applicant_pool_hypothesis": "Small field of obvious product candidates.",
                    "recruiter_hook": "Looks like someone who can translate product intent into delivery fast.",
                }
            ),
        }
    )
    upsert_ledger(conn, ledger_row_primary)
    ledger_row_secondary = {name: "" for name, _ in LEDGER_COLUMNS}
    ledger_row_secondary.update(
        {
            "job_id": "nav_exp_2",
            "run_id": "run_exp",
            "title": "Tjenesteeier",
            "employer": "Bane NOR",
            "job_source": "nav",
            "final_decision": "REVIEW_HIGH",
            "skip_reason": "passed",
            "fit_score": 69,
            "pivot_score": 62,
            "updated_at": "2026-04-19T18:18:00Z",
            "raw_advantage_assessment_v3_json": json.dumps(
                {
                    "advantage_type": "adjacent_value",
                    "advantageous_match_score": 61,
                    "review_priority": 60,
                    "applicant_pool_hypothesis": "Broader applicant pool with more canonical service-owner profiles.",
                    "recruiter_hook": "Could still stand out through cross-functional delivery breadth.",
                }
            ),
        }
    )
    upsert_ledger(conn, ledger_row_secondary)
    conn.commit()
    conn.close()

    reports_dir = tmp_path / "reports"
    experiments_dir = reports_dir / "experiments"
    experiments_dir.mkdir(parents=True, exist_ok=True)
    detail_path = experiments_dir / "shadow_latest.json"
    _write_json(
        detail_path,
        {
            "schema_version": "jobpipe.experiment-run.v1",
            "experiment_id": "shadow_latest",
            "review_sample": [
                {
                    "run_id": "run_exp",
                    "job_id": "nav_exp_1",
                    "baseline_label": "discard",
                    "candidate_label": "review",
                    "review_reason": "promoted_from_discard",
                    "review_priority": 255,
                    "candidate_weighted_score": 63.0,
                },
                {
                    "run_id": "run_exp",
                    "job_id": "nav_exp_2",
                    "baseline_label": "discard",
                    "candidate_label": "review",
                    "review_reason": "promoted_from_discard",
                    "review_priority": 255,
                    "candidate_weighted_score": 63.0,
                }
            ],
        },
    )
    _write_json(
        reports_dir / "experiment_runs.json",
        [
            {
                "schema_version": "jobpipe.experiment-run.v1",
                "experiment_id": "shadow_older",
                "kind": "shadow_feature_weight_eval",
                "status": "completed",
                "sample_size": 25,
                "changed_count": 4,
                "upgrade_count": 4,
                "downgrade_count": 0,
                "review_sample_count": 1,
                "created_at": "2026-04-19T18:10:00.000000Z",
                "summary": "Feature-weight variant over 25 jobs; 4 upgrades.",
                "baseline": {
                    "name": "triage_v3_default",
                    "review_threshold": 48.0,
                    "shortlist_threshold": 67.0,
                },
                "candidate": {
                    "name": "triage_v3_feature_weight_variant",
                    "review_threshold": 44.0,
                    "shortlist_threshold": 62.0,
                    "feature_weights": {"core_tech_alignment": 0.45},
                },
                "detail_path": str(experiments_dir / "shadow_older.json"),
            },
            {
                "schema_version": "jobpipe.experiment-run.v1",
                "experiment_id": "shadow_latest",
                "kind": "shadow_threshold_eval",
                "status": "completed",
                "sample_size": 25,
                "changed_count": 8,
                "upgrade_count": 8,
                "downgrade_count": 0,
                "review_sample_count": 2,
                "created_at": "2026-04-19T18:17:12.058312Z",
                "summary": "Shadow threshold eval over 25 jobs; 8 label changes, 8 upgrades, 0 downgrades.",
                "baseline": {
                    "name": "triage_v3_default",
                    "review_threshold": 48.0,
                    "shortlist_threshold": 67.0,
                },
                "candidate": {
                    "name": "triage_v3_threshold_variant",
                    "review_threshold": 44.0,
                    "shortlist_threshold": 62.0,
                },
                "detail_path": str(detail_path),
            }
        ],
    )
    _write_json(
        experiments_dir / "shadow_older.json",
        {
            "schema_version": "jobpipe.experiment-run.v1",
            "experiment_id": "shadow_older",
            "review_sample": [
                {
                    "run_id": "run_exp",
                    "job_id": "nav_exp_1",
                    "baseline_label": "discard",
                    "candidate_label": "review",
                    "review_reason": "promoted_from_discard",
                    "review_priority": 255,
                    "candidate_weighted_score": 63.0,
                }
            ],
        },
    )
    _write_json(
        reports_dir / "experiment_review_state.json",
        {
            "schema_version": "jobpipe.experiment-review.v1",
            "updated_at": "2026-04-19T18:30:00Z",
            "reviews": {
                "shadow_older::nav_exp_1": {
                    "experiment_id": "shadow_older",
                    "job_id": "nav_exp_1",
                    "run_id": "run_exp",
                    "verdict": "not_useful",
                    "note": "",
                    "review_reason": "promoted_from_discard",
                    "review_priority": 255,
                    "updated_at": "2026-04-19T18:20:00Z",
                },
                "shadow_latest::nav_exp_1": {
                    "experiment_id": "shadow_latest",
                    "job_id": "nav_exp_1",
                    "run_id": "run_exp",
                    "verdict": "correct_miss",
                    "note": "",
                    "review_reason": "promoted_from_discard",
                    "review_priority": 255,
                    "updated_at": "2026-04-19T18:30:00Z",
                }
            },
            "variant_reviews": {
                "shadow_latest": {
                    "experiment_id": "shadow_latest",
                    "verdict": "worth_promoting",
                    "note": "",
                    "candidate_name": "triage_v3_threshold_variant",
                    "kind": "shadow_threshold_eval",
                    "updated_at": "2026-04-19T18:31:00Z",
                },
                "shadow_older": {
                    "experiment_id": "shadow_older",
                    "verdict": "reject_variant",
                    "note": "",
                    "candidate_name": "triage_v3_feature_weight_variant",
                    "kind": "shadow_feature_weight_eval",
                    "updated_at": "2026-04-19T18:22:00Z",
                },
            }
        },
    )

    state_path, profile_path, resume_path, profile_draft_path = _write_profile_sources(tmp_path)
    _write_json(
        state_path,
        {
            "version": 2,
            "updated_at": "2026-04-19T18:40:00Z",
            "applications": {
                "nav_exp_1": {
                    "stages": ["applied"],
                    "outcome": None,
                    "status": "applied",
                    "source": "manual",
                    "updated_at": "2026-04-19T18:36:00Z",
                },
                "nav_exp_2": {
                    "stages": ["applied", "interview"],
                    "outcome": "accepted",
                    "status": "accepted",
                    "source": "manual",
                    "updated_at": "2026-04-19T18:37:00Z",
                },
            },
        },
    )

    payload = build_payload(
        sqlite_path,
        out_dir,
        state_path=state_path,
        profile_path=profile_path,
        resume_path=resume_path,
        profile_draft_path=profile_draft_path,
    )

    assert payload["experiments"]["schema_version"] == "jobpipe.experiments-dashboard.v1"
    assert payload["experiments"]["latest_shadow_eval"]["experiment_id"] == "shadow_latest"
    assert [item["job_id"] for item in payload["experiments"]["review_queue"][:2]] == ["nav_exp_1", "nav_exp_2"]
    review_item = payload["experiments"]["review_queue"][0]
    assert review_item["job_id"] == "nav_exp_1"
    assert review_item["experiment_id"] == "shadow_latest"
    assert review_item["title"] == "Produktleder"
    assert review_item["employer"] == "Vy"
    assert review_item["final_decision"] == "APPLY"
    assert review_item["advantageous_match_score"] == 83
    assert review_item["advantage_review_priority"] == 84
    assert review_item["recruiter_hook"] == "Looks like someone who can translate product intent into delivery fast."
    assert review_item["adjudication"]["verdict"] == "correct_miss"
    assert payload["experiments"]["adjudication_summary"]["reviewed"] == 1
    assert payload["experiments"]["adjudication_summary"]["pending"] == 1
    calibration = payload["experiments"]["calibration_summary"]
    assert calibration["schema_version"] == "jobpipe.experiment-calibration.v1"
    assert calibration["reviewed"] == 1
    assert calibration["positive"] == 1
    assert calibration["rejected"] == 0
    assert calibration["useful_signal_rate"] == 100.0
    assert calibration["top_positive_reasons"] == [{"reason": "promoted_from_discard", "count": 1}]
    advantage_recommendation = payload["experiments"]["advantage_signal_recommendation"]
    assert advantage_recommendation["schema_version"] == "jobpipe.advantage-signal-recommendation.v1"
    assert advantage_recommendation["status"] == "watch"
    assert advantage_recommendation["confidence"] == "low"
    shortlist_quality = payload["experiments"]["advantage_shortlist_quality_summary"]
    assert shortlist_quality["schema_version"] == "jobpipe.advantage-shortlist-quality.v1"
    assert shortlist_quality["reviewed_variants"] == 2
    assert shortlist_quality["high_advantage_variants"] == 2
    assert shortlist_quality["high_advantage_avg_useful_rate"] == 50.0
    assert shortlist_quality["high_advantage_worth_promoting_rate"] == 50.0
    assert shortlist_quality["lower_advantage_variants"] == 0
    assert shortlist_quality["lower_advantage_avg_useful_rate"] == 0.0
    assert shortlist_quality["quality_delta_useful_rate"] == 50.0
    assert shortlist_quality["status"] == "thin_sample"
    assert shortlist_quality["confidence"] == "low"
    variant_summary = payload["experiments"]["variant_review_summary"]
    assert variant_summary["reviewed"] == 2
    assert variant_summary["worth_promoting"] == 1
    assert variant_summary["reject_variant"] == 1
    promotion_summary = payload["experiments"]["promotion_summary"]
    assert promotion_summary["count"] == 1
    assert promotion_summary["has_feature_weight_candidate"] is False
    assert promotion_summary["outcome_backed_count"] == 0
    assert promotion_summary["waiting_for_outcomes_count"] == 1
    assert promotion_summary["not_outcome_backed_yet_count"] == 0
    promotion_readiness_summary = payload["experiments"]["promotion_readiness_summary"]
    assert promotion_readiness_summary["ready_for_patch_review"] == 0
    assert promotion_readiness_summary["needs_more_shadow_review"] == 1
    promotion_review_summary = payload["experiments"]["promotion_review_summary"]
    assert promotion_review_summary["reviewed"] == 0
    assert promotion_review_summary["pending"] == 1
    promotion_candidate = payload["experiments"]["promotion_candidates"][0]
    assert promotion_candidate["experiment_id"] == "shadow_latest"
    assert promotion_candidate["recommended_config_delta"]["review_threshold"]["delta"] == -4.0
    assert promotion_candidate["recommended_config_delta"]["shortlist_threshold"]["delta"] == -5.0
    assert "triage_v3_review_threshold: 44" in promotion_candidate["patch_recommendation"]["thresholds_overlay_yaml"]
    assert promotion_candidate["patch_recommendation"]["target_config_path"].endswith("configs\\pipeline.v1.yaml")
    assert promotion_candidate["patch_recommendation"]["feature_weights_python_patch"] == ""
    assert promotion_candidate["promotion_review"] == {}
    assert promotion_candidate["avg_advantageous_match_score"] == 72.0
    assert promotion_candidate["high_advantage_count"] == 1
    assert promotion_candidate["top_recruiter_hooks"] == [
        "Looks like someone who can translate product intent into delivery fast.",
        "Could still stand out through cross-functional delivery breadth.",
    ]
    assert promotion_candidate["advantage_signal_fit"]["fit"] == "strong"
    assert promotion_candidate["outcome_shadow_fit"]["fit"] == "waiting"
    assert promotion_candidate["promotion_outcome_status"]["status"] == "waiting_for_outcomes"
    assert promotion_candidate["promotion_readiness"]["status"] == "needs_more_shadow_review"
    variants = payload["experiments"]["variant_comparison"]
    assert [item["experiment_id"] for item in variants[:2]] == ["shadow_latest", "shadow_older"]
    assert variants[0]["candidate_name"] == "triage_v3_threshold_variant"
    assert variants[0]["useful_signal_rate"] == 100.0
    assert variants[0]["avg_advantageous_match_score"] == 72.0
    assert variants[0]["high_advantage_count"] == 1
    assert variants[0]["top_recruiter_hooks"] == [
        "Looks like someone who can translate product intent into delivery fast.",
        "Could still stand out through cross-functional delivery breadth.",
    ]
    assert variants[0]["advantage_signal_fit"]["fit"] == "strong"
    assert variants[0]["outcome_shadow_fit"]["fit"] == "waiting"
    assert variants[0]["variant_review"]["verdict"] == "worth_promoting"
    assert variants[1]["candidate_name"] == "triage_v3_feature_weight_variant"
    assert variants[1]["rejected"] == 1
    assert variants[1]["advantage_signal_fit"]["fit"] == "contested"
    assert variants[1]["outcome_shadow_fit"]["fit"] == "waiting"
    assert variants[1]["variant_review"]["verdict"] == "reject_variant"
    assert payload["experiments"]["leading_variant"]["experiment_id"] == "shadow_latest"
    assert payload["experiments"]["leading_variant"]["advantage_signal_fit"]["fit"] == "strong"
    assert payload["experiments"]["leading_variant"]["outcome_shadow_fit"]["fit"] == "waiting"
    assert payload["experiments"]["leading_variant"]["promotion_outcome_status"]["status"] == "waiting_for_outcomes"
    assert payload["experiments"]["leading_variant"]["promotion_readiness"]["status"] == "needs_more_shadow_review"
    assert payload["experiments"]["outcome_shadow_summary"]["aligned"] == 0
    assert payload["experiments"]["outcome_shadow_summary"]["waiting"] == 2
    assert payload["experiments"]["outcome_ranking_guidance"]["schema_version"] == "jobpipe.outcome-ranking-guidance.v1"
    assert payload["experiments"]["outcome_ranking_guidance"]["reviewed_variants"] == 2
    assert payload["experiments"]["outcome_ranking_guidance"]["supported_variants"] == 0
    assert payload["experiments"]["outcome_ranking_guidance"]["non_supported_variants"] == 0
    assert payload["experiments"]["outcome_ranking_guidance"]["waiting_variants"] == 2
    assert payload["experiments"]["outcome_ranking_guidance"]["status"] == "waiting_for_outcomes"
    assert payload["outcomes"]["schema_version"] == "jobpipe.outcomes-dashboard.v1"
    assert payload["outcomes"]["summary"]["total"] == 2
    assert payload["outcomes"]["summary"]["by_status"]["applied"] == 1
    assert payload["outcomes"]["summary"]["by_status"]["offer"] == 1
    assert payload["outcomes"]["summary"]["artifact_linked"] == 0
    assert payload["outcomes"]["audit_summary"]["schema_version"] == "jobpipe.outcome-feedback-audit.v1"
    assert payload["outcomes"]["audit_summary"]["tracked_total"] == 2
    assert payload["outcomes"]["audit_summary"]["artifact_linked_total"] == 0
    assert payload["outcomes"]["audit_summary"]["decision_status_matrix"]["APPLY"]["offer"] == 1
    assert payload["outcomes"]["audit_summary"]["decision_status_matrix"]["APPLY"]["applied"] == 1
    assert payload["outcomes"]["audit_summary"]["apply_path_summary"]["apply_like_total"] == 2
    assert payload["outcomes"]["audit_summary"]["apply_path_summary"]["progressed_count"] == 1
    assert payload["outcomes"]["audit_summary"]["artifact_effect_summary"]["progressed_without_artifacts"] == 1
    assert payload["outcomes"]["calibration_summary"]["schema_version"] == "jobpipe.outcome-feedback-calibration.v1"
    assert payload["outcomes"]["calibration_summary"]["tracked_total"] == 2
    assert payload["outcomes"]["calibration_summary"]["apply_like_total"] == 2
    assert payload["outcomes"]["calibration_summary"]["apply_like_progressed"] == 1
    assert payload["outcomes"]["calibration_summary"]["apply_like_progression_rate"] == 50.0
    assert payload["outcomes"]["calibration_summary"]["non_apply_total"] == 0
    assert payload["outcomes"]["calibration_summary"]["artifact_linked_total"] == 0
    assert payload["outcomes"]["calibration_summary"]["no_artifact_progression_rate"] == 50.0
    assert payload["outcomes"]["recommendation"]["schema_version"] == "jobpipe.outcome-feedback-recommendation.v1"
    assert payload["outcomes"]["recommendation"]["decision_signal"] == "insufficient_signal"
    assert payload["outcomes"]["recommendation"]["artifact_signal"] == "artifact_effect_unclear"
    assert payload["outcomes"]["recommendation"]["recommended_next_action"] == "collect_more_outcomes"
    assert payload["outcomes"]["shadow_followup"]["schema_version"] == "jobpipe.outcome-feedback-shadow-followup.v1"
    assert payload["outcomes"]["shadow_followup"]["suggested_experiment"] == "collect_more_outcomes"
    assert payload["outcomes"]["shadow_followup"]["ready_for_shadow"] is False
    assert payload["experiments"]["outcome_shadow_handoff"]["schema_version"] == "jobpipe.outcome-shadow-handoff.v1"
    assert payload["experiments"]["outcome_shadow_handoff"]["status"] == "collect_more_outcomes"
    assert payload["experiments"]["outcome_shadow_handoff"]["suggested_experiment"] == "collect_more_outcomes"
    assert payload["experiments"]["outcome_shadow_handoff"]["ready_for_shadow"] is False
    assert payload["experiments"]["outcome_shadow_handoff"]["decision_signal"] == "insufficient_signal"
    assert payload["outcomes"]["recent_feedback"][0]["shared_status"] == "offer"
    assert payload["outcomes"]["recent_feedback"][0]["decision_brief"]["final_decision"] == "APPLY"


def test_build_payload_exposes_feature_weight_promotion_patch(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "reports" / "ledger.sqlite"
    out_dir = tmp_path / "out_runs"

    conn = init_db(sqlite_path)
    ledger_row = {name: "" for name, _ in LEDGER_COLUMNS}
    ledger_row.update(
        {
            "job_id": "nav_exp_2",
            "run_id": "run_exp",
            "title": "Tjenesteeier",
            "employer": "Bane NOR",
            "job_source": "nav",
            "final_decision": "APPLY",
            "skip_reason": "passed",
            "fit_score": 74,
            "pivot_score": 60,
            "updated_at": "2026-04-19T18:18:00Z",
        }
    )
    upsert_ledger(conn, ledger_row)
    conn.commit()
    conn.close()

    reports_dir = tmp_path / "reports"
    experiments_dir = reports_dir / "experiments"
    experiments_dir.mkdir(parents=True, exist_ok=True)
    detail_path = experiments_dir / "shadow_feature.json"
    _write_json(
        detail_path,
        {
            "schema_version": "jobpipe.experiment-run.v1",
            "experiment_id": "shadow_feature",
            "review_sample": [],
        },
    )
    _write_json(
        reports_dir / "experiment_runs.json",
        [
            {
                "schema_version": "jobpipe.experiment-run.v1",
                "experiment_id": "shadow_feature",
                "kind": "shadow_feature_weight_eval",
                "status": "completed",
                "sample_size": 25,
                "changed_count": 6,
                "upgrade_count": 6,
                "downgrade_count": 0,
                "review_sample_count": 0,
                "created_at": "2026-04-19T18:20:00.000000Z",
                "summary": "Feature-weight variant over 25 jobs; 6 upgrades.",
                "baseline": {
                    "name": "triage_v3_default",
                    "review_threshold": 48.0,
                    "shortlist_threshold": 67.0,
                    "feature_weights": {"core_tech_alignment": 0.24, "legacy_burden": 0.14},
                },
                "candidate": {
                    "name": "triage_v3_feature_weight_variant",
                    "review_threshold": 48.0,
                    "shortlist_threshold": 67.0,
                    "feature_weights": {"core_tech_alignment": 0.45, "legacy_burden": 0.08},
                },
                "detail_path": str(detail_path),
            }
        ],
    )
    _write_json(
        reports_dir / "experiment_review_state.json",
        {
            "schema_version": "jobpipe.experiment-review.v1",
            "updated_at": "2026-04-19T18:30:00Z",
            "reviews": {},
            "variant_reviews": {
                "shadow_feature": {
                    "experiment_id": "shadow_feature",
                    "verdict": "worth_promoting",
                    "candidate_name": "triage_v3_feature_weight_variant",
                    "kind": "shadow_feature_weight_eval",
                    "updated_at": "2026-04-19T18:31:00Z",
                }
            },
            "promotion_reviews": {
                "shadow_feature": {
                    "experiment_id": "shadow_feature",
                    "verdict": "accepted_for_promotion",
                    "candidate_name": "triage_v3_feature_weight_variant",
                    "kind": "shadow_feature_weight_eval",
                    "updated_at": "2026-04-19T18:35:00Z",
                }
            }
        },
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

    assert payload["experiments"]["promotion_summary"]["count"] == 1
    assert payload["experiments"]["promotion_summary"]["has_feature_weight_candidate"] is True
    assert payload["experiments"]["promotion_review_summary"]["accepted_for_promotion"] == 1
    promotion_candidate = payload["experiments"]["promotion_candidates"][0]
    assert promotion_candidate["promotion_review"]["verdict"] == "accepted_for_promotion"
    assert promotion_candidate["patch_recommendation"]["requires_code_change"] is True
    assert "TRIAGE_FEATURE_WEIGHTS" in promotion_candidate["patch_recommendation"]["feature_weights_python_patch"]
    assert promotion_candidate["patch_recommendation"]["target_weights_path"].endswith("jobpipe\\core\\triage_v3.py")


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


def test_tracked_dashboard_template_contains_outcome_loop_surface() -> None:
    template_path = Path(__file__).resolve().parents[1] / "reports" / "dashboard_template.html"
    html = render_dashboard_html(
        {
            "schema_version": "jobpipe.dashboard.v2",
            "jobs": [],
            "events": [],
            "experiments": {},
            "outcomes": {
                "schema_version": "jobpipe.outcomes-dashboard.v1",
                "summary": {"total": 0},
                "audit_summary": {},
                "calibration_summary": {},
                "recommendation": {},
                "recent_feedback": [],
            },
        },
        template_path,
    )

    assert "function getOutcomeData()" in html
    assert "Shortlist quality" in html
    assert "Outcome loop" in html
    assert "Outcome ranking" in html
    assert "Outcome verdict" in html
    assert "Outcome-to-shadow handoff" in html


def test_tracked_dashboard_template_contains_scheduled_run_surface() -> None:
    template_path = Path(__file__).resolve().parents[1] / "reports" / "dashboard_template.html"
    html = render_dashboard_html(
        {
            "schema_version": "jobpipe.dashboard.v2",
            "jobs": [],
            "events": [],
            "automations": {
                "schema_version": "jobpipe.automation.v1",
                "actions": [],
                "connector_counts": {},
                "recent_runs": [],
                "summary": {},
                "scheduled_flow": {
                    "schema_version": "jobpipe.scheduled-run-control.v1",
                    "entrypoint_command": ".\\go.ps1",
                    "underlying_cli": "python -m jobpipe.cli.run_scheduled_flow",
                    "summary": {},
                },
            },
            "experiments": {},
            "outcomes": {
                "schema_version": "jobpipe.outcomes-dashboard.v1",
                "summary": {"total": 0},
                "audit_summary": {},
                "calibration_summary": {},
                "recommendation": {},
                "recent_feedback": [],
            },
        },
        template_path,
    )

    assert "Feed freshness" in html
    assert "Companion preflight" in html
    assert "Scheduled flow state" in html
    assert "run_scheduled_flow" in html

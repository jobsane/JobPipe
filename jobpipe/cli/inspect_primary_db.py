from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from jobpipe.core.io import load_env_file
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices

load_env_file(".env")

from jobpipe.core.primary_db import connect_primary_db


DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"

SHOW_CHOICES = [
    "summary",
    "profile",
    "applications",
    "events",
    "candidates",
    "documents",
    "calibration",
    "feedback",
    "suggestions",
    "gaps",
    "gap_assessments",
    "jobs",
    "source_records",
    "runs",
    "evaluations",
    "job_events",
    "job_claims",
    "job_selection_signals",
    "job_selection_assessments",
]
CLAIM_LAYER_VIEWS = {"job_claims", "job_selection_signals", "job_selection_assessments"}


def _configure_stdout() -> None:
    if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _connect(path: Path) -> sqlite3.Connection:
    conn = connect_primary_db(path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn: sqlite3.Connection, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _row(conn: sqlite3.Connection, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> dict[str, Any] | None:
    found = conn.execute(sql, params).fetchone()
    return dict(found) if found is not None else None


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _summary(conn: sqlite3.Connection, candidate_id: str) -> dict[str, Any]:
    candidate = _row(
        conn,
        """
        SELECT candidate_id, display_name, locale, timezone, base_location,
               seniority_label, positioning_summary, strategic_direction, updated_at
        FROM candidates
        WHERE candidate_id = ?
        """,
        [candidate_id],
    )
    active_profile = _row(
        conn,
        """
        SELECT profile_version_id, source_kind, content_hash, created_at, updated_at
        FROM candidate_profiles
        WHERE candidate_id = ? AND is_active = 1
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        [candidate_id],
    )
    status_counts = _rows(
        conn,
        """
        SELECT effective_status, COUNT(*) AS count
        FROM application_summary
        WHERE candidate_id = ?
        GROUP BY effective_status
        ORDER BY count DESC, effective_status ASC
        """,
        [candidate_id],
    )
    schema_meta = _row(conn, "SELECT value, updated_at FROM schema_meta WHERE key = 'schema_version'")

    return {
        "schema_version": (schema_meta or {}).get("value", ""),
        "schema_updated_at": (schema_meta or {}).get("updated_at", ""),
        "db_counts": {
            "candidates": _count(conn, "candidates"),
            "candidate_profiles": _count(conn, "candidate_profiles"),
            "application_events": _count(conn, "application_events"),
            "application_summary": _count(conn, "application_summary"),
            "candidate_calibration_settings": _count(conn, "candidate_calibration_settings"),
            "candidate_feedback_events": _count(conn, "candidate_feedback_events"),
            "capability_gaps": _count(conn, "capability_gaps"),
            "gap_evidence": _count(conn, "gap_evidence"),
            "gap_assessments": _count(conn, "gap_assessments"),
            "generated_documents": _count(conn, "generated_documents"),
            "suggestion_leads": _count(conn, "suggestion_leads"),
            "jobs": _count(conn, "jobs"),
            "job_source_records": _count(conn, "job_source_records"),
            "pipeline_runs": _count(conn, "pipeline_runs"),
            "job_evaluations": _count(conn, "job_evaluations"),
            "job_run_events": _count(conn, "job_run_events"),
        },
        "candidate": candidate,
        "active_profile": active_profile,
        "candidate_application_status_counts": status_counts,
    }


def _profile_view(conn: sqlite3.Connection, candidate_id: str) -> dict[str, Any] | None:
    row = _row(
        conn,
        """
        SELECT profile_version_id, source_kind, content_hash, profile_json, resume_json, created_at, updated_at
        FROM candidate_profiles
        WHERE candidate_id = ? AND is_active = 1
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        [candidate_id],
    )
    if row is None:
        return None

    profile_json = json.loads(row.pop("profile_json"))
    resume_json = json.loads(row.pop("resume_json"))

    return {
        **row,
        "snapshot": profile_json.get("snapshot", {}),
        "strategic_direction": profile_json.get("strategic_direction", ""),
        "target_roles": profile_json.get("target_roles", {}),
        "constraints": profile_json.get("constraints", {}),
        "geo_whitelist_prefixes": profile_json.get("geo_whitelist_prefixes", []),
        "hard_no_roles": profile_json.get("hard_no_roles", []),
        "negative_keywords": profile_json.get("negative_keywords", []),
        "evidence_section_count": len(profile_json.get("evidence_sections", [])),
        "education": profile_json.get("education", []),
        "resume_counts": {
            "work": len(resume_json.get("work", [])),
            "projects": len(resume_json.get("projects", [])),
            "education": len(resume_json.get("education", [])),
            "skills": len(resume_json.get("skills", [])),
        },
    }


def _applications_view(conn: sqlite3.Connection, candidate_id: str, limit: int) -> list[dict[str, Any]]:
    return _rows(
        conn,
        """
        SELECT candidate_id, job_id, current_stage, current_outcome, effective_status,
               last_event_at, notes_latest, updated_at
        FROM application_summary
        WHERE candidate_id = ?
        ORDER BY last_event_at DESC, updated_at DESC, job_id ASC
        LIMIT ?
        """,
        [candidate_id, limit],
    )


def _events_view(conn: sqlite3.Connection, candidate_id: str, limit: int) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        """
        SELECT application_event_id, candidate_id, job_id, event_type, event_at, source,
               notes, metadata_json, created_at
        FROM application_events
        WHERE candidate_id = ?
        ORDER BY event_at DESC, created_at DESC
        LIMIT ?
        """,
        [candidate_id, limit],
    )
    for row in rows:
        try:
            row["metadata_json"] = json.loads(row.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            pass
    return rows


def _candidates_view(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return _rows(
        conn,
        """
        SELECT candidate_id, display_name, email, locale, timezone, base_location,
               seniority_label, is_active, updated_at
        FROM candidates
        ORDER BY updated_at DESC, candidate_id ASC
        """
    )


def _documents_view(conn: sqlite3.Connection, candidate_id: str, limit: int) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        """
        SELECT document_id, candidate_id, job_id, evaluation_id, kind, producer,
               status, storage_path, preview_text, document_json, created_at, updated_at
        FROM generated_documents
        WHERE candidate_id = ?
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        [candidate_id, limit],
    )
    for row in rows:
        try:
            row["document_json"] = json.loads(row.get("document_json") or "{}")
        except json.JSONDecodeError:
            pass
    return rows


def _calibration_view(conn: sqlite3.Connection, candidate_id: str, limit: int) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        """
        SELECT candidate_id, scope, setting_key, value_json, updated_at
        FROM candidate_calibration_settings
        WHERE candidate_id = ?
        ORDER BY updated_at DESC, scope ASC, setting_key ASC
        LIMIT ?
        """,
        [candidate_id, limit],
    )
    for row in rows:
        try:
            row["value_json"] = json.loads(row.get("value_json") or "{}")
        except json.JSONDecodeError:
            pass
    return rows


def _feedback_view(conn: sqlite3.Connection, candidate_id: str, limit: int) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        """
        SELECT feedback_event_id, candidate_id, job_id, evaluation_id, feedback_type,
               feedback_value, source, notes, evidence_json, created_at
        FROM candidate_feedback_events
        WHERE candidate_id = ?
        ORDER BY created_at DESC, job_id ASC
        LIMIT ?
        """,
        [candidate_id, limit],
    )
    for row in rows:
        try:
            row["evidence_json"] = json.loads(row.get("evidence_json") or "{}")
        except json.JSONDecodeError:
            pass
    return rows


def _suggestions_view(conn: sqlite3.Connection, candidate_id: str, limit: int) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        """
        SELECT suggestion_id, candidate_id, platform, external_id, job_url, job_id_hint,
               suggested_at, email_subject, source, status, fetched_at, last_error,
               payload_json, created_at, updated_at
        FROM suggestion_leads
        WHERE candidate_id = ?
        ORDER BY updated_at DESC, suggested_at DESC
        LIMIT ?
        """,
        [candidate_id, limit],
    )
    for row in rows:
        try:
            row["payload_json"] = json.loads(row.get("payload_json") or "{}")
        except json.JSONDecodeError:
            pass
    return rows


def _gaps_view(conn: sqlite3.Connection, candidate_id: str, limit: int) -> list[dict[str, Any]]:
    return _rows(
        conn,
        """
        SELECT gap_id, candidate_id, gap_key, label, gap_type, description, created_at, updated_at
        FROM capability_gaps
        WHERE candidate_id = ?
        ORDER BY updated_at DESC, label ASC
        LIMIT ?
        """,
        [candidate_id, limit],
    )


def _gap_assessments_view(conn: sqlite3.Connection, candidate_id: str, limit: int) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        """
        SELECT candidate_id, gap_id, frequency_score, severity_score, unlock_score,
               opportunity_quality_score, time_to_close, confidence_score, priority,
               assessment_json, updated_at
        FROM gap_assessments
        WHERE candidate_id = ?
        ORDER BY
            CASE priority
                WHEN 'close_now' THEN 0
                WHEN 'monitor' THEN 1
                WHEN 'ignore' THEN 2
                ELSE 3
            END,
            unlock_score DESC,
            updated_at DESC
        LIMIT ?
        """,
        [candidate_id, limit],
    )
    for row in rows:
        try:
            row["assessment_json"] = json.loads(row.get("assessment_json") or "{}")
        except json.JSONDecodeError:
            pass
    return rows


def _evaluations_view(conn: sqlite3.Connection, candidate_id: str, limit: int) -> list[dict[str, Any]]:
    return _rows(
        conn,
        """
        SELECT candidate_id, job_id, run_id, run_seen_at, title, employer,
               final_decision, final_confidence, fit_score, pivot_score,
               triage_decision, applicationDue, closed_at, updated_at
        FROM job_evaluations
        WHERE candidate_id = ?
        ORDER BY updated_at DESC, applicationDue ASC, job_id ASC
        LIMIT ?
        """,
        [candidate_id, limit],
    )


def _jobs_view(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        """
        SELECT job_id, title, employer, work_city, applicationDue, source_url,
               first_seen_at, last_seen_at, closed_at, updated_at
        FROM jobs
        ORDER BY updated_at DESC, last_seen_at DESC, job_id ASC
        LIMIT ?
        """,
        [limit],
    )
    return rows


def _source_records_view(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        """
        SELECT source_record_id, source_name, source_job_key, job_id, is_active,
               seen_at, last_seen_at, applicationDue, source_url, updated_at
        FROM job_source_records
        ORDER BY updated_at DESC, last_seen_at DESC, source_name ASC
        LIMIT ?
        """,
        [limit],
    )
    return rows


def _pipeline_runs_view(conn: sqlite3.Connection, candidate_id: str, limit: int) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        """
        SELECT run_id, candidate_id, profile_version_id, config_version, jobs_path,
               max_jobs, status, started_at, finished_at, jobs_seen, jobs_failed, source_batch_json, updated_at
        FROM pipeline_runs
        WHERE candidate_id = ?
        ORDER BY started_at DESC, updated_at DESC
        LIMIT ?
        """,
        [candidate_id, limit],
    )
    for row in rows:
        try:
            row["source_batch_json"] = json.loads(row.get("source_batch_json") or "{}")
        except json.JSONDecodeError:
            pass
    return rows


def _job_events_view(conn: sqlite3.Connection, candidate_id: str, limit: int) -> list[dict[str, Any]]:
    return _rows(
        conn,
        """
        SELECT candidate_id, run_id, job_id, seen_at, title, employer,
               final_decision, final_confidence, triage_decision, fit_score, pivot_score
        FROM job_run_events
        WHERE candidate_id = ?
        ORDER BY run_mtime DESC, seen_at DESC, job_id ASC
        LIMIT ?
        """,
        [candidate_id, limit],
    )


def _job_exists(conn: sqlite3.Connection, job_id: str) -> bool:
    return conn.execute("SELECT 1 FROM jobs WHERE job_id = ? LIMIT 1", [job_id]).fetchone() is not None


def _job_claims_view(conn: sqlite3.Connection, *, job_id: str | None, limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    limit_clause = ""
    if job_id:
        where = "WHERE job_id = ?"
        params.append(job_id)
    else:
        limit_clause = "LIMIT ?"
        params.append(limit)

    rows = _rows(
        conn,
        f"""
        SELECT job_id, claim_id, source_record_id, claim_type, claim_strength,
               claim_subject_type, normalized_key, normalized_label, claim_text,
               source_basis, source_section, evidence_span, confidence_score,
               importance_score, claim_json, created_at, updated_at
        FROM job_claims
        {where}
        ORDER BY importance_score DESC, updated_at DESC, job_id ASC, claim_id ASC
        {limit_clause}
        """,
        params,
    )
    for row in rows:
        try:
            row["claim_json"] = json.loads(row.get("claim_json") or "{}")
        except json.JSONDecodeError:
            pass
    return rows


def _job_selection_signals_view(conn: sqlite3.Connection, *, job_id: str | None, limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    limit_clause = ""
    if job_id:
        where = "WHERE job_id = ?"
        params.append(job_id)
    else:
        limit_clause = "LIMIT ?"
        params.append(limit)

    rows = _rows(
        conn,
        f"""
        SELECT job_id, signal_id, signal_type, signal_label, selection_stage,
               signal_strength, normalized_key, evidence_required,
               confidence_score, importance_score, source_basis, signal_json,
               created_at, updated_at
        FROM job_selection_signals
        {where}
        ORDER BY importance_score DESC, updated_at DESC, job_id ASC, signal_id ASC
        {limit_clause}
        """,
        params,
    )
    for row in rows:
        try:
            row["signal_json"] = json.loads(row.get("signal_json") or "{}")
        except json.JSONDecodeError:
            pass
    return rows


def _job_selection_assessments_view(conn: sqlite3.Connection, *, job_id: str | None, limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    limit_clause = ""
    if job_id:
        where = "WHERE job_id = ?"
        params.append(job_id)
    else:
        limit_clause = "LIMIT ?"
        params.append(limit)

    rows = _rows(
        conn,
        f"""
        SELECT candidate_id, job_id, evaluation_id, structural_pass,
               screenability_score, title_continuity_score, domain_continuity_score,
               ambiguity_risk_score, evidence_burden_score, selection_risk_level,
               likely_rejection_vectors_json, mitigation_moves_json,
               assessment_reason, assessment_json, updated_at
        FROM job_selection_assessments
        {where}
        ORDER BY screenability_score DESC, updated_at DESC, job_id ASC, candidate_id ASC
        {limit_clause}
        """,
        params,
    )
    for row in rows:
        for field, fallback in (
            ("likely_rejection_vectors_json", "[]"),
            ("mitigation_moves_json", "[]"),
            ("assessment_json", "{}"),
        ):
            try:
                row[field] = json.loads(row.get(field) or fallback)
            except json.JSONDecodeError:
                pass
    return rows


def _print_summary(data: dict[str, Any], db_path: Path) -> None:
    print("=== JobPipe Primary DB ===")
    print(f"DB: {db_path.resolve()}")
    print(f"Schema version: {data.get('schema_version') or '(unknown)'}")

    counts = data.get("db_counts", {})
    print(
        "Counts: "
        f"candidates={counts.get('candidates', 0)}, "
        f"profiles={counts.get('candidate_profiles', 0)}, "
        f"app_events={counts.get('application_events', 0)}, "
        f"app_summary={counts.get('application_summary', 0)}, "
        f"calibration={counts.get('candidate_calibration_settings', 0)}, "
        f"feedback={counts.get('candidate_feedback_events', 0)}, "
        f"gaps={counts.get('capability_gaps', 0)}, "
        f"gap_evidence={counts.get('gap_evidence', 0)}, "
        f"gap_assessments={counts.get('gap_assessments', 0)}, "
        f"documents={counts.get('generated_documents', 0)}, "
        f"suggestions={counts.get('suggestion_leads', 0)}, "
        f"jobs={counts.get('jobs', 0)}, "
        f"source_records={counts.get('job_source_records', 0)}, "
        f"pipeline_runs={counts.get('pipeline_runs', 0)}, "
        f"evaluations={counts.get('job_evaluations', 0)}, "
        f"job_events={counts.get('job_run_events', 0)}"
    )

    candidate = data.get("candidate")
    if candidate:
        print("")
        print(f"Candidate: {candidate.get('display_name')} [{candidate.get('candidate_id')}]")
        print(f"Base: {candidate.get('base_location') or '-'}")
        print(f"Level: {candidate.get('seniority_label') or '-'}")
        print(f"Locale/TZ: {candidate.get('locale')} / {candidate.get('timezone')}")

    profile = data.get("active_profile")
    if profile:
        print(f"Active profile: {profile.get('profile_version_id')} ({profile.get('source_kind')})")

    counts_by_status = data.get("candidate_application_status_counts") or []
    if counts_by_status:
        print("Application statuses:")
        for row in counts_by_status:
            status = row.get("effective_status") or "(empty)"
            print(f"  - {status}: {row.get('count')}")


def _print_profile(data: dict[str, Any] | None) -> None:
    if not data:
        print("No active profile found.")
        return

    snapshot = data.get("snapshot", {})
    print("=== Active Candidate Profile ===")
    print(f"Profile version: {data.get('profile_version_id')}")
    print(f"Source: {data.get('source_kind')}")
    print(f"Name: {snapshot.get('name') or '-'}")
    print(f"Base: {snapshot.get('base') or '-'}")
    print(f"Level: {snapshot.get('level') or '-'}")
    print(f"Positioning: {snapshot.get('positioning') or '-'}")
    print(f"Strategic direction: {data.get('strategic_direction') or '-'}")
    print(f"Primary targets: {', '.join(data.get('target_roles', {}).get('primary', [])) or '-'}")
    print(f"Secondary targets: {', '.join(data.get('target_roles', {}).get('secondary', [])) or '-'}")
    print(f"Geo prefixes: {', '.join(data.get('geo_whitelist_prefixes', [])) or '-'}")

    resume_counts = data.get("resume_counts", {})
    print(
        "Resume counts: "
        f"work={resume_counts.get('work', 0)}, "
        f"projects={resume_counts.get('projects', 0)}, "
        f"education={resume_counts.get('education', 0)}, "
        f"skills={resume_counts.get('skills', 0)}"
    )


def _print_rows(title: str, rows: list[dict[str, Any]]) -> None:
    print(f"=== {title} ===")
    if not rows:
        print("(none)")
        return
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, indent=2))


def main() -> None:
    _configure_stdout()
    ap = argparse.ArgumentParser(
        description="Inspect the primary JobPipe SQLite database used for candidate/profile/application state."
    )
    ap.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="default", help="Runtime profile to resolve DB path from")
    ap.add_argument("--data-root", default="", help="Runtime data root override for live_local profile")
    ap.add_argument("--db", default="", help="Path to primary SQLite DB")
    ap.add_argument("--candidate-id", default=DEFAULT_CANDIDATE_ID, help="Candidate ID to inspect")
    ap.add_argument("--limit", type=int, default=20, help="Row limit for list views")
    ap.add_argument(
        "--show",
        action="append",
        choices=SHOW_CHOICES,
        help="Which view(s) to show. Default: summary",
    )
    ap.add_argument("--job-id", default="", help="Optional job ID filter for claim-layer views")
    ap.add_argument("--json", action="store_true", help="Print output as JSON")
    args = ap.parse_args()

    runtime = resolve_profile_paths(
        args.runtime_profile,
        data_root_override=args.data_root,
        db_override=args.db,
    )
    db_path = runtime.primary_db_path
    views = args.show or ["summary"]
    job_id = str(args.job_id or "").strip() or None

    conn = _connect(db_path)
    try:
        if job_id and any(view in CLAIM_LAYER_VIEWS for view in views) and not _job_exists(conn, job_id):
            print(f"error: job_id {job_id} not found in jobs", file=sys.stderr)
            raise SystemExit(1)

        payload: dict[str, Any] = {}
        for view in views:
            if view == "summary":
                payload["summary"] = _summary(conn, args.candidate_id)
            elif view == "profile":
                payload["profile"] = _profile_view(conn, args.candidate_id)
            elif view == "applications":
                payload["applications"] = _applications_view(conn, args.candidate_id, args.limit)
            elif view == "events":
                payload["events"] = _events_view(conn, args.candidate_id, args.limit)
            elif view == "candidates":
                payload["candidates"] = _candidates_view(conn)
            elif view == "documents":
                payload["documents"] = _documents_view(conn, args.candidate_id, args.limit)
            elif view == "calibration":
                payload["calibration"] = _calibration_view(conn, args.candidate_id, args.limit)
            elif view == "feedback":
                payload["feedback"] = _feedback_view(conn, args.candidate_id, args.limit)
            elif view == "suggestions":
                payload["suggestions"] = _suggestions_view(conn, args.candidate_id, args.limit)
            elif view == "gaps":
                payload["gaps"] = _gaps_view(conn, args.candidate_id, args.limit)
            elif view == "gap_assessments":
                payload["gap_assessments"] = _gap_assessments_view(conn, args.candidate_id, args.limit)
            elif view == "jobs":
                payload["jobs"] = _jobs_view(conn, args.limit)
            elif view == "source_records":
                payload["source_records"] = _source_records_view(conn, args.limit)
            elif view == "runs":
                payload["runs"] = _pipeline_runs_view(conn, args.candidate_id, args.limit)
            elif view == "evaluations":
                payload["evaluations"] = _evaluations_view(conn, args.candidate_id, args.limit)
            elif view == "job_events":
                payload["job_events"] = _job_events_view(conn, args.candidate_id, args.limit)
            elif view == "job_claims":
                payload["job_claims"] = _job_claims_view(conn, job_id=job_id, limit=args.limit)
            elif view == "job_selection_signals":
                payload["job_selection_signals"] = _job_selection_signals_view(conn, job_id=job_id, limit=args.limit)
            elif view == "job_selection_assessments":
                payload["job_selection_assessments"] = _job_selection_assessments_view(conn, job_id=job_id, limit=args.limit)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    for view in views:
        if view == "summary":
            _print_summary(payload.get("summary", {}), db_path)
        elif view == "profile":
            _print_profile(payload.get("profile"))
        elif view == "applications":
            _print_rows("Applications", payload.get("applications", []))
        elif view == "events":
            _print_rows("Application Events", payload.get("events", []))
        elif view == "candidates":
            _print_rows("Candidates", payload.get("candidates", []))
        elif view == "documents":
            _print_rows("Generated Documents", payload.get("documents", []))
        elif view == "calibration":
            _print_rows("Candidate Calibration Settings", payload.get("calibration", []))
        elif view == "feedback":
            _print_rows("Candidate Feedback Events", payload.get("feedback", []))
        elif view == "suggestions":
            _print_rows("Suggestion Leads", payload.get("suggestions", []))
        elif view == "gaps":
            _print_rows("Capability Gaps", payload.get("gaps", []))
        elif view == "gap_assessments":
            _print_rows("Gap Assessments", payload.get("gap_assessments", []))
        elif view == "jobs":
            _print_rows("Canonical Jobs", payload.get("jobs", []))
        elif view == "source_records":
            _print_rows("Job Source Records", payload.get("source_records", []))
        elif view == "runs":
            _print_rows("Pipeline Runs", payload.get("runs", []))
        elif view == "evaluations":
            _print_rows("Job Evaluations", payload.get("evaluations", []))
        elif view == "job_events":
            _print_rows("Job Run Events", payload.get("job_events", []))
        elif view == "job_claims":
            rows = payload.get("job_claims", [])
            if job_id and not rows:
                print(f"[job_claims] no rows for job_id {job_id}")
            else:
                _print_rows("Job Claims", rows)
        elif view == "job_selection_signals":
            rows = payload.get("job_selection_signals", [])
            if job_id and not rows:
                print(f"[job_selection_signals] no rows for job_id {job_id}")
            else:
                _print_rows("Job Selection Signals", rows)
        elif view == "job_selection_assessments":
            rows = payload.get("job_selection_assessments", [])
            if job_id and not rows:
                print(f"[job_selection_assessments] no rows for job_id {job_id}")
            else:
                _print_rows("Job Selection Assessments", rows)
        if view != views[-1]:
            print("")


if __name__ == "__main__":
    main()

"""Export ledger.sqlite to a self-contained dashboard HTML file.

Enriches actionable jobs with URLs/deadlines from per-job 00_input.json files
when the ledger has empty values (common with cross-platform SQLite issues).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from jobpipe.core.io import load_env_file

load_env_file(".env")

from jobpipe.core.paths import application_state_path, primary_db_path

try:
    import yaml as _yaml
    def _load_thresholds() -> Dict[str, Any]:
        try:
            raw = _yaml.safe_load(_CONFIG_PATH.read_bytes())
            return (raw or {}).get("thresholds", {})
        except Exception:
            return {}
except ImportError:
    def _load_thresholds() -> Dict[str, Any]:
        return {}


def _reclassify(fit_score, pivot_score, thr: Dict[str, Any]) -> str:
    """Re-apply current YAML thresholds to produce a fresh final_decision.
    Mirrors the logic in moderate.py exactly."""
    try:
        fit = int(fit_score or 0)
        pivot = int(pivot_score or 0)
    except Exception:
        return "SKIP"

    apply_strong = int(thr.get("apply_strong_fit", 78))
    apply_fit    = int(thr.get("apply_fit", 67))
    pivot_boost  = int(thr.get("pivot_boost_apply", 78))
    review_min   = int(thr.get("review_min_fit", 30))
    review_high  = int(thr.get("review_high_min_fit", 58))

    if fit < review_min:
        return "SKIP"
    if fit < review_high:
        return "REVIEW_LOW"
    if fit >= apply_strong:
        return "APPLY_STRONGLY"
    if fit >= apply_fit:
        return "APPLY"
    return "REVIEW_HIGH" if pivot >= pivot_boost else "REVIEW_LOW"

_APP_STATE_PATH = application_state_path()
_PRIMARY_DB_PATH = primary_db_path()
_CONFIG_PATH = Path("./configs/pipeline.v1.yaml")
_DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"

_DETAIL_COLS = (
    "triage_explanation", "reverse_decision", "reverse_confidence",
    "reverse_rationale", "recommendation_reason", "cv_focus",
    "feedback_flags", "description_snip",
)

_ACTIONABLE = {"APPLY_STRONGLY", "APPLY", "REVIEW_HIGH", "REVIEW_LOW"}
_DATA_PLACEHOLDER = "/*__DASHBOARD_DATA__*/"


def _rows_as_dicts(conn: sqlite3.Connection, sql: str) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql)]


def _parse_raw_json(val: Any) -> Dict[str, Any]:
    if not val:
        return {}
    try:
        return json.loads(val)
    except Exception:
        return {}


def _extract_detail(row: Dict[str, Any]) -> Dict[str, Any]:
    match = _parse_raw_json(row.get("raw_match_json"))
    pivot = _parse_raw_json(row.get("raw_pivot_json"))
    mod = _parse_raw_json(row.get("raw_moderator_json"))
    return {
        "overlaps": match.get("overlaps", []),
        "gaps": match.get("gaps", []),
        "hard_blockers": match.get("hard_blockers", []),
        "match_notes": match.get("notes", ""),
        "pivot_type": pivot.get("pivot_type", ""),
        "pivot_risk": pivot.get("potential_risk", ""),
        "pivot_why": pivot.get("why_it_matters", []),
        "cv_focus_mod": mod.get("cv_focus", []),
        "feedback_flags_mod": mod.get("feedback_flags", []),
    }


def _safe_load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pick(*vals: Any) -> Any:
    for v in vals:
        if v is not None and str(v).strip():
            return v
    return ""


def _enrich_from_input(row: Dict[str, Any], out_dir: Path) -> None:
    """Fill in missing URL/deadline/location fields from per-job 00_input.json."""
    needs_url = (
        not (row.get("application_url") or "").strip()
        and not (row.get("source_url") or "").strip()
    )
    needs_loc = (
        not (row.get("work_city") or "").strip()
        and not (row.get("work_county") or "").strip()
    )
    if not needs_url and not needs_loc:
        return

    run_id = row.get("run_id", "")
    job_id = row.get("job_id", "")
    if not run_id or not job_id:
        return

    input_path = out_dir / run_id / job_id / "00_input.json"
    inp = _safe_load_json(input_path)
    if not inp:
        return

    # The input file can have the job data at root level or nested under "job"
    job = inp.get("job", inp) if isinstance(inp.get("job"), dict) else inp

    if needs_url:
        row["application_url"] = _pick(
            row.get("application_url"), job.get("applicationUrl")
        )
        row["source_url"] = _pick(
            row.get("source_url"), job.get("sourceurl"), job.get("link")
        )
        row["applicationDue"] = _pick(
            row.get("applicationDue"), job.get("applicationDue")
        )
        # Normalize deadline to date only
        due = str(row.get("applicationDue") or "")
        if "T" in due:
            row["applicationDue"] = due[:10]

    if needs_loc:
        row["work_city"] = _pick(
            row.get("work_city"),
            job.get("work_city"),
            job.get("municipal"),
            job.get("municipalName"),
        )
        row["work_county"] = _pick(
            row.get("work_county"),
            job.get("work_county"),
            job.get("county"),
        )


def _load_app_state(state_path: Path) -> Dict[str, Any]:
    """Load application_state.json sidecar. Returns empty dict if missing."""
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data.get("applications", {})
    except Exception:
        return {}


def _load_app_state_from_db(db_path: Path, candidate_id: str) -> Dict[str, Any]:
    """Load application summary from the primary DB and shape it like application_state.json."""
    if not db_path.exists():
        return {}

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        summary_rows = [
            dict(r) for r in conn.execute(
                """
                SELECT job_id, current_stage, current_outcome, effective_status,
                       last_event_at, notes_latest, updated_at
                FROM application_summary
                WHERE candidate_id = ?
                """,
                [candidate_id],
            )
        ]
        event_rows = [
            dict(r) for r in conn.execute(
                """
                SELECT job_id, event_type, event_at, source, notes, metadata_json, created_at
                FROM application_events
                WHERE candidate_id = ?
                ORDER BY event_at DESC, created_at DESC
                """,
                [candidate_id],
            )
        ]
        conn.close()
    except Exception:
        return {}

    latest_event_by_job: Dict[str, Dict[str, Any]] = {}
    for row in event_rows:
        job_id = str(row.get("job_id") or "").strip()
        if job_id and job_id not in latest_event_by_job:
            latest_event_by_job[job_id] = row

    out: Dict[str, Any] = {}
    for row in summary_rows:
        job_id = str(row.get("job_id") or "").strip()
        if not job_id:
            continue

        latest = latest_event_by_job.get(job_id, {})
        try:
            metadata = json.loads(latest.get("metadata_json") or "{}")
        except Exception:
            metadata = {}

        stages = metadata.get("stages", [])
        if not isinstance(stages, list):
            stages = []

        outcome = str(row.get("current_outcome") or metadata.get("outcome") or "").strip()
        out[job_id] = {
            "status": str(row.get("effective_status") or metadata.get("effective_status") or "").strip(),
            "stages": stages,
            "outcome": outcome,
            "updated_at": str(row.get("updated_at") or row.get("last_event_at") or "").strip(),
            "source": str(latest.get("source") or "").strip(),
            "notes": str(row.get("notes_latest") or latest.get("notes") or "").strip(),
            "email_subject": str(metadata.get("email_subject") or "").strip(),
            "email_date": str(metadata.get("email_date") or "").strip(),
        }

    return out


def _load_app_state_merged(
    state_path: Optional[Path],
    db_path: Optional[Path],
    candidate_id: str,
) -> Dict[str, Any]:
    """Read app state from the primary DB first, with JSON fallback for unknown jobs."""
    merged = _load_app_state_from_db(db_path or _PRIMARY_DB_PATH, candidate_id)
    sidecar = _load_app_state(state_path or _APP_STATE_PATH)
    for job_id, entry in sidecar.items():
        merged.setdefault(job_id, entry)
    return merged


def _load_generated_documents_from_db(
    db_path: Path,
    candidate_id: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """Load generated document metadata grouped by job_id."""
    if not db_path.exists():
        return {}

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = [
            dict(r) for r in conn.execute(
                """
                SELECT job_id, kind, producer, status, storage_path, preview_text,
                       created_at, updated_at
                FROM generated_documents
                WHERE candidate_id = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                [candidate_id],
            )
        ]
        conn.close()
    except Exception:
        return {}

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        job_id = str(row.get("job_id") or "").strip()
        if not job_id:
            continue
        grouped.setdefault(job_id, []).append(
            {
                "kind": str(row.get("kind") or "").strip(),
                "producer": str(row.get("producer") or "").strip(),
                "status": str(row.get("status") or "").strip(),
                "storage_path": str(row.get("storage_path") or "").strip(),
                "preview_text": str(row.get("preview_text") or "").strip(),
                "created_at": str(row.get("created_at") or "").strip(),
                "updated_at": str(row.get("updated_at") or "").strip(),
            }
        )
    return grouped


def _load_jobs_and_events_from_primary_db(
    db_path: Path,
    candidate_id: str,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load dashboard job/event rows from the primary DB.

    Returns empty lists when the DB is missing or unreadable. The dashboard can
    then fall back to the legacy ledger.sqlite path.
    """
    if not db_path.exists():
        return [], []

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        jobs = [
            dict(r) for r in conn.execute(
                """
            SELECT job_id, title, employer, work_city, work_county, work_postalCode,
                   applicationDue, source_url, application_url,
                   triage_decision, triage_confidence, triage_explanation, triage_signals,
                   reverse_decision, reverse_confidence, reverse_rationale,
                   fit_score, pivot_score,
                   final_decision, final_confidence, recommendation_reason,
                   cv_focus, feedback_flags, description_snip,
                   skip_reason,
                   run_id, run_seen_at, updated_at,
                   raw_match_json, raw_pivot_json, raw_moderator_json
            FROM job_evaluations
            WHERE candidate_id = ?
            ORDER BY
                CASE final_decision
                    WHEN 'APPLY_STRONGLY' THEN 0
                    WHEN 'APPLY' THEN 1
                    WHEN 'REVIEW_HIGH' THEN 2
                    WHEN 'REVIEW_LOW' THEN 3
                    ELSE 4
                END,
                CASE WHEN fit_score IS NULL THEN 1 ELSE 0 END,
                fit_score DESC
                """,
                [candidate_id],
            )
        ]
        events = [
            dict(r) for r in conn.execute(
                """
            SELECT run_id, job_id, run_mtime, seen_at,
                   final_decision, triage_decision, triage_confidence,
                   fit_score, pivot_score
            FROM job_run_events
            WHERE candidate_id = ?
            ORDER BY run_mtime
                """,
                [candidate_id],
            )
        ]
        conn.close()
    except Exception:
        return [], []

    return jobs, events


def _load_jobs_and_events_from_ledger(sqlite_path: Path) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    conn = sqlite3.connect(str(sqlite_path))
    jobs = _rows_as_dicts(conn, """
        SELECT job_id, title, employer, work_city, work_county, work_postalCode,
               applicationDue, source_url, application_url,
               triage_decision, triage_confidence, triage_explanation, triage_signals,
               reverse_decision, reverse_confidence, reverse_rationale,
               fit_score, pivot_score,
               final_decision, final_confidence, recommendation_reason,
               cv_focus, feedback_flags, description_snip,
               skip_reason,
               run_id, run_seen_at, updated_at,
               raw_match_json, raw_pivot_json, raw_moderator_json
        FROM ledger
        ORDER BY
            CASE final_decision
                WHEN 'APPLY_STRONGLY' THEN 0
                WHEN 'APPLY' THEN 1
                WHEN 'REVIEW_HIGH' THEN 2
                WHEN 'REVIEW_LOW' THEN 3
                ELSE 4
            END,
            fit_score DESC NULLS LAST
    """)
    events = _rows_as_dicts(conn, """
        SELECT run_id, job_id, run_mtime, seen_at,
               final_decision, triage_decision, triage_confidence,
               fit_score, pivot_score
        FROM events
        ORDER BY run_mtime
    """)
    conn.close()
    return jobs, events


def build_payload(
    sqlite_path: Path,
    out_dir: Path,
    state_path: Optional[Path] = None,
    primary_db_path_: Optional[Path] = None,
    candidate_id: str = _DEFAULT_CANDIDATE_ID,
) -> Dict[str, Any]:
    app_state = _load_app_state_merged(
        state_path=state_path,
        db_path=primary_db_path_ or _PRIMARY_DB_PATH,
        candidate_id=candidate_id,
    )
    generated_docs = _load_generated_documents_from_db(
        primary_db_path_ or _PRIMARY_DB_PATH,
        candidate_id,
    )
    thresholds = _load_thresholds()
    jobs_raw, events = _load_jobs_and_events_from_primary_db(
        primary_db_path_ or _PRIMARY_DB_PATH,
        candidate_id,
    )
    if not jobs_raw:
        jobs_raw, events = _load_jobs_and_events_from_ledger(sqlite_path)
    elif not events and sqlite_path.exists():
        _, events = _load_jobs_and_events_from_ledger(sqlite_path)

    jobs = []
    for row in jobs_raw:
        # Re-apply current YAML thresholds so the dashboard always reflects
        # the latest config — even for jobs scored under older threshold values.
        if row.get("fit_score") is not None and thresholds:
            row["final_decision"] = _reclassify(
                row.get("fit_score"), row.get("pivot_score"), thresholds
            )

        is_actionable = row.get("final_decision") in _ACTIONABLE

        if is_actionable:
            row["detail"] = _extract_detail(row)
            _enrich_from_input(row, out_dir)
        else:
            for col in _DETAIL_COLS:
                row.pop(col, None)
            row["detail"] = None

        for k in ("raw_match_json", "raw_pivot_json", "raw_moderator_json"):
            row.pop(k, None)

        # Merge application tracking state
        app_entry = app_state.get(row.get("job_id", ""), {})
        row["app_status"] = app_entry.get("status", "")
        row["app_stages"] = json.dumps(app_entry.get("stages", []), ensure_ascii=False)
        row["app_outcome"] = app_entry.get("outcome") or ""
        row["app_updated_at"] = app_entry.get("updated_at", "")
        row["app_source"] = app_entry.get("source", "")
        row["app_notes"] = app_entry.get("notes", "")
        row["generated_documents"] = generated_docs.get(row.get("job_id", ""), [])

        jobs.append(row)

    return {
        "jobs": jobs,
        "events": events,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def export(sqlite_path: Path, out_dir: Path, template_path: Path, out_path: Path,
           state_path: Optional[Path] = None,
           primary_db_path_: Optional[Path] = None,
           candidate_id: str = _DEFAULT_CANDIDATE_ID) -> None:
    payload = build_payload(
        sqlite_path,
        out_dir,
        state_path=state_path,
        primary_db_path_=primary_db_path_,
        candidate_id=candidate_id,
    )

    template = template_path.read_text(encoding="utf-8")

    data_json = json.dumps(payload, ensure_ascii=False, default=str)
    if _DATA_PLACEHOLDER in template:
        html = template.replace(_DATA_PLACEHOLDER, data_json)
    else:
        raise RuntimeError(
            f"Template {template_path} is missing the data placeholder: {_DATA_PLACEHOLDER}"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    n_action = sum(1 for j in payload["jobs"] if j.get("final_decision") in _ACTIONABLE)
    n_urls = sum(1 for j in payload["jobs"]
                 if j.get("final_decision") in _ACTIONABLE
                 and (j.get("application_url") or j.get("source_url")))
    n_tracked = sum(1 for j in payload["jobs"] if j.get("app_status"))
    print(f"Dashboard exported: {out_path}")
    print(f"  {len(payload['jobs'])} jobs ({n_action} actionable, {n_urls} with URLs), {len(payload['events'])} events")
    if n_tracked:
        print(f"  {n_tracked} jobs with application status tracked")


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Build a self-contained dashboard HTML from ledger SQLite.")
    ap.add_argument("--sqlite", default="./reports/ledger.sqlite", help="Path to ledger.sqlite")
    ap.add_argument("--out-runs", default="./out_runs", help="Path to out_runs directory")
    ap.add_argument("--template", default="./reports/dashboard_template.html", help="HTML template")
    ap.add_argument("--out", default="./reports/dashboard.html", help="Output HTML path")
    ap.add_argument("--app-state", default="", help="Path to application_state.json (default: reports/application_state.json)")
    ap.add_argument("--db", default=str(_PRIMARY_DB_PATH), help="Path to primary jobpipe.sqlite")
    ap.add_argument("--candidate-id", default=_DEFAULT_CANDIDATE_ID, help=f"Candidate ID for primary DB reads (default: {_DEFAULT_CANDIDATE_ID})")
    args = ap.parse_args(argv)
    state_path = Path(args.app_state) if args.app_state else None
    export(
        Path(args.sqlite),
        Path(args.out_runs),
        Path(args.template),
        Path(args.out),
        state_path=state_path,
        primary_db_path_=Path(args.db),
        candidate_id=args.candidate_id,
    )


if __name__ == "__main__":
    main()

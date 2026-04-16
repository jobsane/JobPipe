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

from jobpipe.core.paths import application_state_path

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
_CONFIG_PATH = Path("./configs/pipeline.v1.yaml")

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


def build_payload(sqlite_path: Path, out_dir: Path, state_path: Optional[Path] = None) -> Dict[str, Any]:
    app_state = _load_app_state(state_path or _APP_STATE_PATH)
    thresholds = _load_thresholds()
    conn = sqlite3.connect(str(sqlite_path))

    jobs_raw = _rows_as_dicts(conn, """
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

        jobs.append(row)

    events = _rows_as_dicts(conn, """
        SELECT run_id, job_id, run_mtime, seen_at,
               final_decision, triage_decision, triage_confidence,
               fit_score, pivot_score
        FROM events
        ORDER BY run_mtime
    """)

    conn.close()

    return {
        "jobs": jobs,
        "events": events,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def export(sqlite_path: Path, out_dir: Path, template_path: Path, out_path: Path,
           state_path: Optional[Path] = None) -> None:
    payload = build_payload(sqlite_path, out_dir, state_path=state_path)

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
    args = ap.parse_args(argv)
    state_path = Path(args.app_state) if args.app_state else None
    export(Path(args.sqlite), Path(args.out_runs), Path(args.template), Path(args.out), state_path=state_path)


if __name__ == "__main__":
    main()

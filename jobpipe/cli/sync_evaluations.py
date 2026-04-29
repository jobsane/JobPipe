from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from jobpipe.core.candidate_data import load_candidate_profile_json
from jobpipe.core.io import load_env_file, now_iso, clean, html_to_text, pick, to_float, to_int
from jobpipe.core.no_score_reason import derive_no_score_reason

load_env_file(".env")

from jobpipe.decision import (
    MonitoringContext,
    build_decision_context,
    build_monitoring_context,
    persist_job_decision_state,
    persist_monitoring_state,
)
from jobpipe.runtime.paths import artifacts_root, exports_root, primary_db_path
from jobpipe.runtime.catalog import source_job_key
from jobpipe.core.primary_db import (
    connect_primary_db,
    ensure_candidate,
    upsert_job_evaluation,
    upsert_job_replay_input,
    upsert_job_run_event,
)


DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def _parse_date_maybe(s: str) -> str:
    s = clean(s)
    if not s:
        return ""
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    for sep in (".", "/"):
        if sep in s:
            parts = s.split(sep)
            if len(parts) >= 3:
                dd, mm, yyyy = parts[0].zfill(2), parts[1].zfill(2), parts[2][:4]
                if yyyy.isdigit() and mm.isdigit() and dd.isdigit():
                    return f"{yyyy}-{mm}-{dd}"
    return s


def _truncate(s: str, n: int) -> str:
    s = clean(s)
    if not s:
        return ""
    if n and len(s) > n:
        return s[: max(0, n - 1)] + "…"
    return s


def _safe_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                s = raw.strip()
                if not s:
                    continue
                try:
                    yield json.loads(s)
                except Exception:
                    continue
    except Exception:
        return


def _safe_load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_parse_json_text(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _decision_job_view(row: Dict[str, Any]) -> Dict[str, Any]:
    match = _safe_parse_json_text(row.get("raw_match_json"))
    pivot = _safe_parse_json_text(row.get("raw_pivot_json"))
    return {
        **row,
        "detail": {
            "overlaps": match.get("overlaps", []),
            "gaps": match.get("gaps", []),
            "hard_blockers": match.get("hard_blockers", []),
            "match_notes": match.get("notes", ""),
            "pivot_type": pivot.get("pivot_type", ""),
            "pivot_why": pivot.get("why_it_matters", []),
        },
    }


def _replay_payload(job: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(job or {})
    payload.setdefault("job_id", clean(row.get("job_id")))
    payload.setdefault("title", clean(row.get("title")))
    payload.setdefault("employer_name", clean(row.get("employer")))
    payload.setdefault("work_city", clean(row.get("work_city")))
    payload.setdefault("work_county", clean(row.get("work_county")))
    payload.setdefault("work_postalCode", clean(row.get("work_postalCode")))
    payload.setdefault("applicationDue", clean(row.get("applicationDue")))
    payload.setdefault("sourceurl", clean(row.get("source_url")))
    payload.setdefault("applicationUrl", clean(row.get("application_url")))
    payload.setdefault("description_html", clean(row.get("description_html")))
    if not clean(payload.get("description_text")) and clean(payload.get("description_html")):
        payload["description_text"] = html_to_text(clean(payload.get("description_html")), max_chars=5000)
    return payload


def _replay_input_row(row: Dict[str, Any], *, mirrored_at: str) -> Dict[str, Any]:
    payload = dict(row.get("replay_input_json") or {})
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return {
        "job_id": clean(row.get("job_id")),
        "source_name": clean(payload.get("source")) or clean(payload.get("_source_name")),
        "source_job_key": clean(source_job_key(payload)) if payload else "",
        "source_url": clean(payload.get("sourceurl")) or clean(row.get("source_url")),
        "application_url": clean(payload.get("applicationUrl")) or clean(row.get("application_url")),
        "title": clean(payload.get("title")) or clean(row.get("title")),
        "employer": clean(payload.get("employer_name")) or clean(payload.get("employer")) or clean(row.get("employer")),
        "work_city": clean(payload.get("work_city")) or clean(row.get("work_city")),
        "work_county": clean(payload.get("work_county")) or clean(row.get("work_county")),
        "work_postalCode": clean(payload.get("work_postalCode")) or clean(row.get("work_postalCode")),
        "applicationDue": clean(payload.get("applicationDue")) or clean(row.get("applicationDue")),
        "description_text": clean(payload.get("description_text")) or clean(row.get("description_snip")),
        "description_html": clean(payload.get("description_html")),
        "input_payload_json": payload,
        "input_hash": hashlib.sha1(payload_json.encode("utf-8")).hexdigest() if payload_json else "",
        "captured_from_run_id": clean(row.get("run_id")),
        "captured_at": clean(row.get("run_seen_at")) or mirrored_at,
        "updated_at": mirrored_at,
    }


def _job_evaluation_row(
    row: Dict[str, Any],
    *,
    candidate_id: str,
    mirrored_at: str,
) -> Dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "job_id": clean(row.get("job_id")),
        "run_id": clean(row.get("run_id")),
        "run_mtime": row.get("run_mtime") or 0,
        "run_seen_at": clean(row.get("run_seen_at")),
        "title": clean(row.get("title")),
        "employer": clean(row.get("employer")),
        "sector": clean(row.get("sector")),
        "work_city": clean(row.get("work_city")),
        "work_county": clean(row.get("work_county")),
        "work_postalCode": clean(row.get("work_postalCode")),
        "applicationDue": clean(row.get("applicationDue")),
        "source_url": clean(row.get("source_url")),
        "application_url": clean(row.get("application_url")),
        "triage_decision": clean(row.get("triage_decision")),
        "triage_confidence": row.get("triage_confidence"),
        "triage_explanation": clean(row.get("triage_explanation")),
        "triage_signals": clean(row.get("triage_signals")),
        "reverse_decision": clean(row.get("reverse_decision")),
        "reverse_confidence": row.get("reverse_confidence"),
        "reverse_rationale": clean(row.get("reverse_rationale")),
        "fit_score": row.get("fit_score"),
        "pivot_score": row.get("pivot_score"),
        "final_decision": clean(row.get("final_decision")),
        "final_confidence": row.get("final_confidence"),
        "recommendation_reason": clean(row.get("recommendation_reason")),
        "cv_focus": clean(row.get("cv_focus")),
        "feedback_flags": clean(row.get("feedback_flags")),
        "description_snip": clean(row.get("description_snip")),
        "skip_reason": clean(row.get("skip_reason")),
        "raw_index_json": clean(row.get("raw_index_json")),
        "raw_match_json": clean(row.get("raw_match_json")),
        "raw_pivot_json": clean(row.get("raw_pivot_json")),
        "raw_moderator_json": clean(row.get("raw_moderator_json")),
        "closed_at": clean(row.get("closed_at")),
        "updated_at": clean(row.get("updated_at")) or mirrored_at,
    }


def _job_run_event_row(
    row: Dict[str, Any],
    *,
    candidate_id: str,
    mirrored_at: str,
) -> Dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "run_id": clean(row.get("run_id")),
        "job_id": clean(row.get("job_id")),
        "run_mtime": row.get("run_mtime") or 0,
        "seen_at": clean(row.get("seen_at")),
        "final_decision": clean(row.get("final_decision")),
        "final_confidence": row.get("final_confidence"),
        "triage_decision": clean(row.get("triage_decision")),
        "triage_confidence": row.get("triage_confidence"),
        "fit_score": row.get("fit_score"),
        "pivot_score": row.get("pivot_score"),
        "applicationDue": clean(row.get("applicationDue")),
        "title": clean(row.get("title")),
        "employer": clean(row.get("employer")),
        "work_city": clean(row.get("work_city")),
        "work_county": clean(row.get("work_county")),
        "work_postalCode": clean(row.get("work_postalCode")),
        "source_url": clean(row.get("source_url")),
        "application_url": clean(row.get("application_url")),
        "raw_index_json": clean(row.get("raw_index_json")),
        "updated_at": mirrored_at,
    }


def _persist_latest_row(
    conn,
    *,
    candidate_id: str,
    row: Dict[str, Any],
    event_rows: List[Dict[str, Any]],
    candidate_profile: Dict[str, Any],
    mirrored_at: str,
    watchlists_by_id: Dict[str, Any],
) -> None:
    upsert_job_replay_input(
        conn,
        _replay_input_row(row, mirrored_at=mirrored_at),
    )
    upsert_job_evaluation(
        conn,
        _job_evaluation_row(
            row,
            candidate_id=candidate_id,
            mirrored_at=mirrored_at,
        ),
    )

    job_view = _decision_job_view(row)
    decision_context = build_decision_context(job_view, candidate_profile=candidate_profile)
    evaluation_id = f"{clean(row.get('run_id'))}:{clean(row.get('job_id'))}"
    updated_at = clean(row.get("updated_at")) or mirrored_at
    job_id = clean(row.get("job_id"))

    persist_job_decision_state(
        conn,
        candidate_id=candidate_id,
        job_id=job_id,
        evaluation_id=evaluation_id,
        decision_context=decision_context,
        updated_at=updated_at,
    )

    monitoring_context = build_monitoring_context(
        job_view,
        candidate_id=candidate_id,
        decision_context=decision_context,
        run_history=[event for event in event_rows if clean(event.get("job_id")) == job_id],
    )
    for watch in monitoring_context.watchlists:
        watchlists_by_id[watch.watchlist_id] = watch
    persist_monitoring_state(
        conn,
        candidate_id=candidate_id,
        monitoring_context=monitoring_context.model_copy(
            update={
                "watchlists": [],
            }
        ),
        updated_at=updated_at,
        replace_watchlists_state=False,
    )


@dataclass
class EventRow:
    run_id: str
    run_mtime: float
    job_id: str
    index_row: Dict[str, Any]
    job_dir: Path


def find_runs(out_dir: Path) -> List[Path]:
    if not out_dir.exists():
        return []
    return sorted([p for p in out_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime)


def iter_events(out_dir: Path) -> Iterable[EventRow]:
    for run_dir in find_runs(out_dir):
        run_id = run_dir.name
        run_mtime = run_dir.stat().st_mtime
        index_path = run_dir / "index.jsonl"
        if not index_path.exists():
            continue
        for row in _safe_jsonl(index_path):
            job_id = pick(row.get("job_id"), row.get("id"))
            if not job_id:
                continue
            yield EventRow(run_id, run_mtime, job_id, row, run_dir / job_id)


def merge_job_details(ev: EventRow, include_description: bool, desc_max_chars: int) -> Dict[str, Any]:
    row = dict(ev.index_row)

    input_j = _safe_load_json(ev.job_dir / "00_input.json") if ev.job_dir.exists() else {}
    triage_j = _safe_load_json(ev.job_dir / "01_triage.json") if ev.job_dir.exists() else {}
    rev_j = _safe_load_json(ev.job_dir / "02_reverse_triage.json") if ev.job_dir.exists() else {}
    # Stage file numbering shifted when reverse_triage was disabled (2026-04-13).
    # Try new numbering first (03/04/05/06), fall back to old (04/05/06/07) for
    # any runs produced before the change.
    def _load_stage(new_name: str, old_name: str) -> dict:
        if not ev.job_dir.exists():
            return {}
        d = _safe_load_json(ev.job_dir / new_name)
        if d:
            return d
        return _safe_load_json(ev.job_dir / old_name) or {}

    match_j = _load_stage("03_profile_match.json", "04_profile_match.json")
    pivot_j = _load_stage("04_pivot.json", "05_pivot.json")
    mod_j = _load_stage("05_moderator.json", "06_moderator.json")
    pack_j = _load_stage("06_application_pack.json", "07_application_pack.json")

    # Resolve job data: prefer nested "job" key, fall back to root of input file,
    # then to index row. This handles both pipeline output formats.
    job: Dict[str, Any] = {}
    if isinstance(input_j.get("job"), dict):
        job = input_j["job"]
    elif input_j:
        job = input_j          # data at root level (most common case)
    elif isinstance(row.get("job"), dict):
        job = row["job"]

    title = pick(job.get("title"), job.get("normalized_title"), row.get("title"))
    employer = pick(job.get("employer_name"), job.get("employer"), row.get("employer"), row.get("employer_name"))
    city = pick(job.get("work_city"), job.get("municipal"), job.get("municipalName"), row.get("work_city"))
    county = pick(job.get("work_county"), job.get("county"), row.get("work_county"))
    postal = pick(job.get("work_postalCode"), job.get("postalCode"), row.get("work_postalCode"))
    sector = pick(job.get("sector"), row.get("sector"))
    source_url = pick(job.get("sourceurl"), job.get("link"), row.get("sourceurl"), row.get("link"))
    app_url = pick(job.get("applicationUrl"), row.get("applicationUrl"))
    due = _parse_date_maybe(pick(job.get("applicationDue"), row.get("applicationDue")))

    triage_decision = pick(triage_j.get("triage_decision"), row.get("triage_decision"), (row.get("triage") or {}).get("triage_decision"))
    triage_conf = to_float(pick(triage_j.get("confidence"), row.get("triage_confidence"), (row.get("triage") or {}).get("confidence")))
    triage_expl = pick(triage_j.get("explanation"), row.get("triage_explanation"), (row.get("triage") or {}).get("explanation"))
    triage_signals = triage_j.get("signals") or row.get("triage_signals") or []
    if isinstance(triage_signals, str):
        triage_signals = [triage_signals]

    reverse_decision = pick(rev_j.get("reverse_decision"), row.get("reverse_decision"))
    reverse_conf = to_float(pick(rev_j.get("confidence"), row.get("reverse_confidence")))
    reverse_rationale = pick(rev_j.get("rationale"), row.get("reverse_rationale"))

    fit_score = to_int(pick(match_j.get("fit_score"), row.get("fit_score")))
    pivot_score = to_int(pick(pivot_j.get("pivot_score"), row.get("pivot_score")))
    final_decision = pick(mod_j.get("final_decision"), row.get("final_decision"))
    final_conf = to_float(pick(mod_j.get("confidence"), row.get("confidence")))
    rec_reason = pick(mod_j.get("recommendation_reason"), row.get("recommendation_reason"))

    description_snip = ""
    if include_description:
        description_snip = _truncate(pick(job.get("description_html"), row.get("description_html")), desc_max_chars)

    cv_focus = pack_j.get("cv_focus") or mod_j.get("cv_focus") or []
    if isinstance(cv_focus, str):
        cv_focus = [cv_focus]
    feedback_flags = pack_j.get("feedback_flags") or mod_j.get("feedback_flags") or []
    if isinstance(feedback_flags, str):
        feedback_flags = [feedback_flags]

    # Derive an explicit skip_reason so the dashboard can accurately categorise
    # each job without guessing from partial signals.
    #
    # Priority order (most specific first):
    #   geo          → blocked by geo postal/county filter (pre-AI)
    #   hard_no      → blocked by hard-no title regex (pre-AI)
    #   semantic     → blocked by semantic similarity filter (pre-AI)
    #   triage_llm   → LLM said SKIP at triage stage
    #   fit_floor    → passed triage, fit_score < review_min_fit (30) → moderate SKIP
    #   moderate     → passed triage + fit floor, moderated down to SKIP
    #   passed       → final decision is not SKIP (actionable)
    _sig_set = set(triage_signals) if isinstance(triage_signals, list) else set()
    _fit = fit_score if isinstance(fit_score, int) else None
    _final = final_decision or ""
    _triage = triage_decision or ""

    if _sig_set & {"geo_postal_skip", "geo_county_skip"}:
        _skip_reason = "geo"
    elif "hard_no_title" in _sig_set:
        _skip_reason = "hard_no"
    elif "semantic_filter_skip" in _sig_set:
        _skip_reason = "semantic"
    elif _triage == "SKIP" and _final in ("SKIP", ""):
        _skip_reason = "triage_llm"
    elif _final == "SKIP" and _fit is not None and _fit < 30:
        _skip_reason = "fit_floor"
    elif _final == "SKIP":
        _skip_reason = "moderate"
    elif _final:
        _skip_reason = "passed"
    else:
        _skip_reason = ""

    return {
        "no_score_reason": derive_no_score_reason(
            {
                "fit_score": fit_score,
                "pivot_score": pivot_score,
                "skip_reason": _skip_reason,
                "triage_decision": triage_decision,
            }
        ),
        "job_id": ev.job_id,
        "run_id": ev.run_id,
        "run_mtime": ev.run_mtime,
        "run_seen_at": datetime.fromtimestamp(ev.run_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),

        "title": title,
        "employer": employer,
        "sector": sector,
        "work_city": city,
        "work_county": county,
        "work_postalCode": postal,
        "applicationDue": due,
        "source_url": source_url,
        "application_url": app_url,

        "triage_decision": triage_decision,
        "triage_confidence": triage_conf,
        "triage_explanation": triage_expl,
        "triage_signals": ",".join([clean(x) for x in triage_signals if clean(x)]),

        "reverse_decision": reverse_decision,
        "reverse_confidence": reverse_conf,
        "reverse_rationale": reverse_rationale,

        "fit_score": fit_score,
        "pivot_score": pivot_score,
        "final_decision": final_decision,
        "final_confidence": final_conf,
        "recommendation_reason": rec_reason,

        "cv_focus": " | ".join([clean(x) for x in cv_focus if clean(x)])[:2000],
        "feedback_flags": " | ".join([clean(x) for x in feedback_flags if clean(x)])[:2000],

        "description_snip": description_snip,
        "skip_reason": _skip_reason,

        "raw_index_json": json.dumps(ev.index_row, ensure_ascii=False, sort_keys=True)[:20000],
        "raw_match_json": json.dumps(match_j, ensure_ascii=False, sort_keys=True)[:20000],
        "raw_pivot_json": json.dumps(pivot_j, ensure_ascii=False, sort_keys=True)[:20000],
        "raw_moderator_json": json.dumps(mod_j, ensure_ascii=False, sort_keys=True)[:20000],
        "replay_input_json": _replay_payload(job, row),
    }


CSV_COLUMNS: List[str] = [
    "job_id",
    "run_id",
    "run_mtime",
    "run_seen_at",
    "title",
    "employer",
    "sector",
    "work_city",
    "work_county",
    "work_postalCode",
    "applicationDue",
    "source_url",
    "application_url",
    "triage_decision",
    "triage_confidence",
    "triage_explanation",
    "triage_signals",
    "reverse_decision",
    "reverse_confidence",
    "reverse_rationale",
    "fit_score",
    "pivot_score",
    "final_decision",
    "final_confidence",
    "recommendation_reason",
    "cv_focus",
    "feedback_flags",
    "description_snip",
    "skip_reason",
    "no_score_reason",
    "raw_index_json",
    "raw_match_json",
    "raw_pivot_json",
    "raw_moderator_json",
    "closed_at",
    "updated_at",
]


def mirror_to_primary_db(
    db_path: Path,
    candidate_id: str,
    latest_rows: List[Dict[str, Any]],
    event_rows: List[Dict[str, Any]],
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_primary_db(db_path)
    try:
        ensure_candidate(conn, candidate_id=candidate_id)
        mirrored_at = now_iso()
        watchlists_by_id: Dict[str, Any] = {}
        candidate_profile = load_candidate_profile_json(candidate_id=candidate_id, db_path=db_path)

        for row in latest_rows:
            _persist_latest_row(
                conn,
                candidate_id=candidate_id,
                row=row,
                event_rows=event_rows,
                candidate_profile=candidate_profile,
                mirrored_at=mirrored_at,
                watchlists_by_id=watchlists_by_id,
            )

        for row in event_rows:
            upsert_job_run_event(
                conn,
                _job_run_event_row(
                    row,
                    candidate_id=candidate_id,
                    mirrored_at=mirrored_at,
                ),
            )

        persist_monitoring_state(
            conn,
            candidate_id=candidate_id,
            monitoring_context=MonitoringContext(
                watchlists=list(watchlists_by_id.values()),
                change_events=[],
            ),
            updated_at=mirrored_at,
        )

        conn.commit()
    finally:
        conn.close()


def row_is_newer(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    am, bm = a.get("run_mtime") or 0, b.get("run_mtime") or 0
    if am != bm:
        return am > bm
    priority = {"APPLY_STRONGLY": 3, "APPLY": 2, "REVIEW_HIGH": 1, "REVIEW_LOW": 1, "REVIEW": 1, "SKIP": 0, "": -1, None: -1}
    ap, bp = priority.get(a.get("final_decision"), -1), priority.get(b.get("final_decision"), -1)
    if ap != bp:
        return ap > bp
    return (a.get("final_confidence") or 0) > (b.get("final_confidence") or 0)


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in CSV_COLUMNS})


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Build incremental JobPipe evaluation state and export CSVs from artifact runs and per-job stage artifacts.")
    ap.add_argument("--out", default=str(artifacts_root()), help=f"Artifact runs root (default: {artifacts_root()})")
    ap.add_argument("--reports", default=str(exports_root()), help=f"Exports folder (default: {exports_root()})")
    ap.add_argument("--csv", default="", help="CSV output path (default: <exports>/evaluations_latest.csv)")
    ap.add_argument("--db", default=str(primary_db_path()), help="Primary JobPipe SQLite DB for mirrored evaluation state")
    ap.add_argument("--candidate-id", default=DEFAULT_CANDIDATE_ID, help=f"Candidate ID for primary DB mirroring (default: {DEFAULT_CANDIDATE_ID})")
    ap.add_argument("--include-description", action="store_true", help="Include a truncated description snippet column.")
    ap.add_argument("--desc-max-chars", type=int, default=4000, help="Max chars for description_snip if enabled (default: 4000)")
    # Detailed report options (replaces report_runs.py)
    # Expiry support: mark jobs as closed when they transition ACTIVE→INACTIVE in the sheet
    ap.add_argument("--expired-file", default="", help="JSONL file with expired job events (from pull_sheets_csv.py --expired-out). "
                     "Jobs listed here will have their closed_at timestamp set in the latest evaluation rows.")
    ap.add_argument("--detailed-report", action="store_true", help="Also write a detailed JSON+CSV report (replaces report_runs.py).")
    ap.add_argument("--decisions", default="", help="Comma-separated final_decision filter for detailed report (e.g. APPLY,REVIEW_HIGH). Empty = all.")
    ap.add_argument("--only-non-expired", action="store_true", help="Filter out jobs with applicationDue < today in detailed report.")
    ap.add_argument("--limit", type=int, default=0, help="Limit rows in detailed report (0 = no limit).")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    reports_dir = Path(args.reports)
    csv_path = Path(args.csv) if args.csv else (reports_dir / "evaluations_latest.csv")

    latest_by_job: Dict[str, Dict[str, Any]] = {}
    event_rows: List[Dict[str, Any]] = []
    events_scanned = 0

    for ev in iter_events(out_dir):
        enriched = merge_job_details(ev, include_description=args.include_description, desc_max_chars=args.desc_max_chars)

        event_row = {
            "run_id": enriched.get("run_id"),
            "job_id": enriched.get("job_id"),
            "run_mtime": enriched.get("run_mtime"),
            "seen_at": enriched.get("run_seen_at"),
            "final_decision": enriched.get("final_decision"),
            "final_confidence": enriched.get("final_confidence"),
            "triage_decision": enriched.get("triage_decision"),
            "triage_confidence": enriched.get("triage_confidence"),
            "fit_score": enriched.get("fit_score"),
            "pivot_score": enriched.get("pivot_score"),
            "applicationDue": enriched.get("applicationDue"),
            "title": enriched.get("title"),
            "employer": enriched.get("employer"),
            "work_city": enriched.get("work_city"),
            "work_county": enriched.get("work_county"),
            "work_postalCode": enriched.get("work_postalCode"),
            "source_url": enriched.get("source_url"),
            "application_url": enriched.get("application_url"),
            "raw_index_json": enriched.get("raw_index_json"),
        }
        event_rows.append(event_row)
        events_scanned += 1

        prev = latest_by_job.get(ev.job_id)
        if prev is None or row_is_newer(enriched, prev):
            latest_by_job[ev.job_id] = enriched

    # --- Process expired events (ACTIVE→INACTIVE transitions from the sheet) ---
    expired_count = 0
    expired_file = Path(args.expired_file) if args.expired_file else None
    if expired_file and expired_file.exists():
        for raw in _safe_jsonl(expired_file):
            if raw.get("_event") != "expired":
                continue
            job_id = raw.get("job_id")
            if not job_id:
                continue
            closed_at = raw.get("expired_at") or now_iso()
            if job_id in latest_by_job:
                latest_by_job[job_id]["closed_at"] = closed_at
                latest_by_job[job_id]["updated_at"] = now_iso()
            expired_count += 1

    rows = list(latest_by_job.values())
    mirror_to_primary_db(Path(args.db), args.candidate_id, rows, event_rows)
    rows.sort(key=lambda r: (r.get("applicationDue") or "9999-99-99", -(r.get("final_confidence") or 0), r.get("title") or ""))
    write_csv(csv_path, rows)

    print("=== JobPipe Evaluation Sync ===")
    print(f"Artifacts: {out_dir.resolve()}")
    print(f"CSV:      {csv_path.resolve()}")
    print(f"Primary:  {Path(args.db).resolve()}")
    print(f"Events scanned: {events_scanned}")
    print(f"Unique jobs (latest): {len(rows)}")
    if expired_count:
        print(f"Jobs marked as closed (ACTIVE->INACTIVE): {expired_count}")

    # --- Detailed report (replaces the old report_runs.py) ---
    if args.detailed_report:
        from datetime import date as _date

        detail_rows = list(rows)

        # Filter by decision
        decs = [d.strip().upper() for d in args.decisions.split(",") if d.strip()]
        if decs:
            detail_rows = [r for r in detail_rows if clean(r.get("final_decision")).upper() in set(decs)]

        # Filter non-expired
        if args.only_non_expired:
            today = _date.today()
            kept: List[Dict[str, Any]] = []
            for r in detail_rows:
                due_str = clean(r.get("applicationDue"))
                if not due_str or len(due_str) < 10:
                    kept.append(r)
                    continue
                try:
                    due_date = _date.fromisoformat(due_str[:10])
                    if due_date >= today:
                        kept.append(r)
                except ValueError:
                    kept.append(r)
            detail_rows = kept

        # Sort best first
        detail_rows.sort(
            key=lambda r: (r.get("final_confidence") or 0, r.get("fit_score") or 0, r.get("pivot_score") or 0),
            reverse=True,
        )

        if args.limit and args.limit > 0:
            detail_rows = detail_rows[: args.limit]

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        detail_json = reports_dir / f"jobpipe_detailed_{ts}.json"
        detail_csv = reports_dir / f"jobpipe_detailed_{ts}.csv"

        with detail_json.open("w", encoding="utf-8") as f:
            json.dump(detail_rows, f, ensure_ascii=False, indent=2)

        # CSV: drop large raw blobs
        skip_cols = {"raw_index_json", "raw_match_json", "raw_pivot_json", "raw_moderator_json"}
        flat = [{k: v for k, v in r.items() if k not in skip_cols} for r in detail_rows]
        if flat:
            cols = list(flat[0].keys())
            with detail_csv.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                for r in flat:
                    w.writerow(r)

        print(f"\n=== Detailed Report ===")
        if decs:
            print(f"Decision filter: {', '.join(decs)}")
        if args.only_non_expired:
            print("Filter: only non-expired")
        print(f"Rows: {len(detail_rows)}")
        print(f"JSON: {detail_json}")
        print(f"CSV:  {detail_csv}")


if __name__ == "__main__":
    main()

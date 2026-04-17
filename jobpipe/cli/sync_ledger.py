from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from jobpipe.core.io import now_iso, clean, pick, to_float, to_int
from jobpipe.core.paths import bootstrap_private_data, get_jobpipe_paths

_DEFAULT_PATHS = get_jobpipe_paths()


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


def _resolve_stage_path(job_dir: Path, *names: str) -> Optional[Path]:
    if not job_dir.exists():
        return None
    for name in names:
        path = job_dir / name
        if path.exists():
            return path
    return None


def _load_stage_artifact(job_dir: Path, *names: str) -> Tuple[Dict[str, Any], Optional[Path]]:
    path = _resolve_stage_path(job_dir, *names)
    if not path:
        return {}, None
    return _safe_load_json(path), path


def _truthy_flag(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    text = clean(value).lower()
    if text in {"1", "true", "yes", "y"}:
        return 1
    if text in {"0", "false", "no", "n"}:
        return 0
    return 0


def _derive_job_source(
    job_id: str,
    explicit_source: str,
    source_url: str,
    application_url: str,
    job_status: str = "",
    occ_level1: str = "",
    occ_level2: str = "",
    cat_name: str = "",
) -> str:
    explicit = clean(explicit_source)
    if explicit:
        return explicit

    lowered_job_id = clean(job_id).lower()
    if lowered_job_id.startswith("finn_"):
        return "finn"
    if lowered_job_id.startswith("li_"):
        return "linkedin"

    hay = " ".join([clean(source_url).lower(), clean(application_url).lower()])
    if "arbeidsplassen.nav.no" in hay or "nav.no/stillinger" in hay:
        return "nav"
    if "finn.no" in hay:
        return "finn"
    if "linkedin.com" in hay:
        return "linkedin"
    if clean(job_status) or clean(occ_level1) or clean(occ_level2) or clean(cat_name):
        return "nav"
    return ""


def _collect_generated_documents(job_dir: Path, pack_path: Optional[Path]) -> Tuple[List[Dict[str, Any]], str]:
    docs: List[Dict[str, Any]] = []
    latest_mtime = 0.0

    def add_doc(path: Path, kind: str, status: str) -> None:
        nonlocal latest_mtime
        if not path.exists():
            return
        latest_mtime = max(latest_mtime, path.stat().st_mtime)
        docs.append(
            {
                "kind": kind,
                "status": status,
                "storage_path": str(path.resolve()),
            }
        )

    if pack_path:
        add_doc(pack_path, "application_pack_json", "saved")
    add_doc(job_dir / "application_pack_draft.json", "application_pack_json", "draft")
    add_doc(job_dir / "07_cv_highlights.docx", "cv_highlights_docx", "saved")
    add_doc(job_dir / "cover_letter_draft.txt", "cover_letter_text", "draft")

    generated_at = ""
    if latest_mtime:
        generated_at = datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return docs, generated_at


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
    match_j, _ = _load_stage_artifact(ev.job_dir, "03_profile_match.json", "04_profile_match.json")
    pivot_j, _ = _load_stage_artifact(ev.job_dir, "04_pivot.json", "05_pivot.json")
    mod_j, _ = _load_stage_artifact(ev.job_dir, "05_moderator.json", "06_moderator.json")
    pack_j, pack_path = _load_stage_artifact(ev.job_dir, "06_application_pack.json", "07_application_pack.json")

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
    employer = pick(
        job.get("employer_name"),
        job.get("employer"),
        job.get("company"),
        row.get("employer"),
        row.get("employer_name"),
    )
    city = pick(job.get("work_city"), job.get("municipal"), job.get("municipalName"), row.get("work_city"))
    county = pick(job.get("work_county"), job.get("county"), row.get("work_county"))
    postal = pick(job.get("work_postalCode"), job.get("postalCode"), row.get("work_postalCode"))
    sector = pick(job.get("sector"), row.get("sector"))
    source_url = pick(job.get("source_url"), job.get("sourceurl"), job.get("link"), row.get("source_url"), row.get("sourceurl"), row.get("link"))
    app_url = pick(job.get("application_url"), job.get("applicationUrl"), row.get("application_url"), row.get("applicationUrl"))
    due = _parse_date_maybe(pick(job.get("applicationDue"), row.get("applicationDue")))
    explicit_source = pick(job.get("source"), row.get("source"))
    job_status = pick(job.get("status"), row.get("status"))
    normalized_title = pick(job.get("normalized_title"), row.get("normalized_title"), title)
    occ_level1 = pick(job.get("occ_level1"), row.get("occ_level1"))
    occ_level2 = pick(job.get("occ_level2"), row.get("occ_level2"))
    cat_type = pick(job.get("cat_type"), row.get("cat_type"))
    cat_code = pick(job.get("cat_code"), row.get("cat_code"))
    cat_name = pick(job.get("cat_name"), row.get("cat_name"))
    cat_score = to_float(pick(job.get("cat_score"), row.get("cat_score")))
    job_source = _derive_job_source(
        ev.job_id,
        explicit_source,
        source_url,
        app_url,
        job_status=job_status,
        occ_level1=occ_level1,
        occ_level2=occ_level2,
        cat_name=cat_name,
    )
    suggested_by_platform = _truthy_flag(pick(job.get("suggested_by_platform"), row.get("suggested_by_platform")))

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
    cover_letter_text = clean(pack_j.get("cover_letter_text"))
    cv_highlights = pack_j.get("cv_highlights") or []
    if isinstance(cv_highlights, str):
        cv_highlights = [cv_highlights]
    generated_documents, pack_generated_at = _collect_generated_documents(ev.job_dir, pack_path)
    pack_ready = 1 if pack_j else 0
    pack_has_cover_letter = 1 if cover_letter_text else 0
    pack_highlight_count = len([x for x in cv_highlights if clean(x)])
    pack_docx_ready = 1 if any(doc.get("kind") == "cv_highlights_docx" for doc in generated_documents) else 0

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
        "job_source": job_source,
        "job_status": job_status,
        "suggested_by_platform": suggested_by_platform,
        "normalized_title": normalized_title,
        "occ_level1": occ_level1,
        "occ_level2": occ_level2,
        "cat_type": cat_type,
        "cat_code": cat_code,
        "cat_name": cat_name,
        "cat_score": cat_score,

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
        "pack_ready": pack_ready,
        "pack_generated_at": pack_generated_at,
        "pack_has_cover_letter": pack_has_cover_letter,
        "pack_highlight_count": pack_highlight_count,
        "pack_docx_ready": pack_docx_ready,
        "generated_documents_json": json.dumps(generated_documents, ensure_ascii=False),

        "description_snip": description_snip,
        "skip_reason": _skip_reason,

        "raw_index_json": json.dumps(ev.index_row, ensure_ascii=False, sort_keys=True)[:20000],
        "raw_match_json": json.dumps(match_j, ensure_ascii=False, sort_keys=True)[:20000],
        "raw_pivot_json": json.dumps(pivot_j, ensure_ascii=False, sort_keys=True)[:20000],
        "raw_moderator_json": json.dumps(mod_j, ensure_ascii=False, sort_keys=True)[:20000],
    }


LEDGER_COLUMNS: List[Tuple[str, str]] = [
    ("job_id", "TEXT PRIMARY KEY"),
    ("run_id", "TEXT"),
    ("run_mtime", "REAL"),
    ("run_seen_at", "TEXT"),
    ("title", "TEXT"),
    ("employer", "TEXT"),
    ("sector", "TEXT"),
    ("work_city", "TEXT"),
    ("work_county", "TEXT"),
    ("work_postalCode", "TEXT"),
    ("applicationDue", "TEXT"),
    ("source_url", "TEXT"),
    ("application_url", "TEXT"),
    ("job_source", "TEXT"),
    ("job_status", "TEXT"),
    ("suggested_by_platform", "INTEGER"),
    ("normalized_title", "TEXT"),
    ("occ_level1", "TEXT"),
    ("occ_level2", "TEXT"),
    ("cat_type", "TEXT"),
    ("cat_code", "TEXT"),
    ("cat_name", "TEXT"),
    ("cat_score", "REAL"),
    ("triage_decision", "TEXT"),
    ("triage_confidence", "REAL"),
    ("triage_explanation", "TEXT"),
    ("triage_signals", "TEXT"),
    ("reverse_decision", "TEXT"),
    ("reverse_confidence", "REAL"),
    ("reverse_rationale", "TEXT"),
    ("fit_score", "INTEGER"),
    ("pivot_score", "INTEGER"),
    ("final_decision", "TEXT"),
    ("final_confidence", "REAL"),
    ("recommendation_reason", "TEXT"),
    ("cv_focus", "TEXT"),
    ("feedback_flags", "TEXT"),
    ("pack_ready", "INTEGER"),
    ("pack_generated_at", "TEXT"),
    ("pack_has_cover_letter", "INTEGER"),
    ("pack_highlight_count", "INTEGER"),
    ("pack_docx_ready", "INTEGER"),
    ("generated_documents_json", "TEXT"),
    ("description_snip", "TEXT"),
    ("skip_reason", "TEXT"),
    ("raw_index_json", "TEXT"),
    ("raw_match_json", "TEXT"),
    ("raw_pivot_json", "TEXT"),
    ("raw_moderator_json", "TEXT"),
    ("closed_at", "TEXT"),
    ("updated_at", "TEXT"),
]

EVENTS_COLUMNS: List[Tuple[str, str]] = [
    ("run_id", "TEXT"),
    ("job_id", "TEXT"),
    ("run_mtime", "REAL"),
    ("seen_at", "TEXT"),
    ("job_source", "TEXT"),
    ("job_status", "TEXT"),
    ("skip_reason", "TEXT"),
    ("final_decision", "TEXT"),
    ("final_confidence", "REAL"),
    ("triage_decision", "TEXT"),
    ("triage_confidence", "REAL"),
    ("fit_score", "INTEGER"),
    ("pivot_score", "INTEGER"),
    ("applicationDue", "TEXT"),
    ("title", "TEXT"),
    ("employer", "TEXT"),
    ("work_city", "TEXT"),
    ("work_county", "TEXT"),
    ("work_postalCode", "TEXT"),
    ("source_url", "TEXT"),
    ("application_url", "TEXT"),
    ("raw_index_json", "TEXT"),
]


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    cols = ", ".join([f"{n} {t}" for n, t in LEDGER_COLUMNS])
    conn.execute(f"CREATE TABLE IF NOT EXISTS ledger ({cols});")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_due ON ledger(applicationDue);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_decision ON ledger(final_decision);")

    # Migrate existing databases: add new columns if missing
    existing_ledger_cols = {row[1] for row in conn.execute("PRAGMA table_info(ledger)")}
    for _col, _type in LEDGER_COLUMNS:
        if _col in existing_ledger_cols:
            continue
        conn.execute(f"ALTER TABLE ledger ADD COLUMN {_col} {_type};")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_skip_reason ON ledger(skip_reason);")

    ecols = ", ".join([f"{n} {t}" for n, t in EVENTS_COLUMNS])
    conn.execute(f"CREATE TABLE IF NOT EXISTS events ({ecols}, PRIMARY KEY (run_id, job_id));")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run_mtime ON events(run_mtime);")
    existing_event_cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    for _col, _type in EVENTS_COLUMNS:
        if _col in existing_event_cols:
            continue
        conn.execute(f"ALTER TABLE events ADD COLUMN {_col} {_type};")
    return conn


def upsert_ledger(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    row = dict(row)
    row["updated_at"] = now_iso()

    names = [c[0] for c in LEDGER_COLUMNS]
    placeholders = ", ".join(["?"] * len(names))
    assignments = ", ".join([f"{n}=excluded.{n}" for n in names if n != "job_id"])
    sql = f"INSERT INTO ledger ({', '.join(names)}) VALUES ({placeholders}) ON CONFLICT(job_id) DO UPDATE SET {assignments};"
    conn.execute(sql, [row.get(n) for n in names])


def insert_event(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    names = [c[0] for c in EVENTS_COLUMNS]
    placeholders = ", ".join(["?"] * len(names))
    assignments = ", ".join([f"{n}=excluded.{n}" for n in names if n not in {"run_id", "job_id"}])
    sql = (
        f"INSERT INTO events ({', '.join(names)}) VALUES ({placeholders}) "
        f"ON CONFLICT(run_id, job_id) DO UPDATE SET {assignments};"
    )
    conn.execute(sql, [row.get(n) for n in names])


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
        fieldnames = [c[0] for c in LEDGER_COLUMNS]
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fieldnames})


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Build an incremental JobPipe ledger (CSV + SQLite) from out_runs/*/index.jsonl and per-job stage artifacts.")
    ap.add_argument(
        "--data-root",
        default="",
        help=f"JobPipe user data root (default: {_DEFAULT_PATHS.data_root})",
    )
    ap.add_argument(
        "--out",
        default="",
        help=f"Path to out_runs (default: {_DEFAULT_PATHS.out_runs_dir})",
    )
    ap.add_argument(
        "--reports",
        default="",
        help=f"Reports folder (default: {_DEFAULT_PATHS.reports_dir})",
    )
    ap.add_argument("--csv", default="", help=f"CSV output path (default: {_DEFAULT_PATHS.ledger_csv_path})")
    ap.add_argument("--sqlite", default="", help=f"SQLite output path (default: {_DEFAULT_PATHS.ledger_sqlite_path})")
    ap.add_argument("--include-description", action="store_true", help="Include a truncated description snippet column.")
    ap.add_argument("--desc-max-chars", type=int, default=4000, help="Max chars for description_snip if enabled (default: 4000)")
    # Detailed report options (replaces report_runs.py)
    # Expiry support: mark jobs as closed when they transition ACTIVE→INACTIVE in the sheet
    ap.add_argument("--expired-file", default="", help="JSONL file with expired job events (from pull_sheets_csv.py --expired-out). "
                     "Jobs listed here will have their closed_at timestamp set in the ledger.")
    ap.add_argument("--detailed-report", action="store_true", help="Also write a detailed JSON+CSV report (replaces report_runs.py).")
    ap.add_argument("--decisions", default="", help="Comma-separated final_decision filter for detailed report (e.g. APPLY,REVIEW_HIGH). Empty = all.")
    ap.add_argument("--only-non-expired", action="store_true", help="Filter out jobs with applicationDue < today in detailed report.")
    ap.add_argument("--limit", type=int, default=0, help="Limit rows in detailed report (0 = no limit).")
    args = ap.parse_args(argv)

    paths = get_jobpipe_paths(args.data_root or None)
    bootstrap_private_data(paths, include_artifacts=True)

    out_dir = Path(args.out) if args.out else paths.out_runs_dir
    reports_dir = Path(args.reports) if args.reports else paths.reports_dir
    csv_path = Path(args.csv) if args.csv else paths.ledger_csv_path
    sqlite_path = Path(args.sqlite) if args.sqlite else paths.ledger_sqlite_path

    conn = init_db(sqlite_path)

    latest_by_job: Dict[str, Dict[str, Any]] = {}
    events_scanned = 0

    for ev in iter_events(out_dir):
        enriched = merge_job_details(ev, include_description=args.include_description, desc_max_chars=args.desc_max_chars)

        insert_event(conn, {
            "run_id": enriched.get("run_id"),
            "job_id": enriched.get("job_id"),
            "run_mtime": enriched.get("run_mtime"),
            "seen_at": enriched.get("run_seen_at"),
            "job_source": enriched.get("job_source"),
            "job_status": enriched.get("job_status"),
            "skip_reason": enriched.get("skip_reason"),
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
        })
        events_scanned += 1

        prev = latest_by_job.get(ev.job_id)
        if prev is None or row_is_newer(enriched, prev):
            latest_by_job[ev.job_id] = enriched

    for row in latest_by_job.values():
        upsert_ledger(conn, row)

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
            conn.execute(
                "UPDATE ledger SET closed_at = ?, updated_at = ? "
                "WHERE job_id = ? AND (closed_at IS NULL OR closed_at = '')",
                [closed_at, now_iso(), job_id],
            )
            expired_count += 1

    conn.commit()
    conn.close()

    rows = list(latest_by_job.values())
    rows.sort(key=lambda r: (r.get("applicationDue") or "9999-99-99", -(r.get("final_confidence") or 0), r.get("title") or ""))
    write_csv(csv_path, rows)

    print("=== JobPipe Ledger ===")
    print(f"out_runs: {out_dir.resolve()}")
    print(f"SQLite:   {sqlite_path.resolve()}")
    print(f"CSV:      {csv_path.resolve()}")
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

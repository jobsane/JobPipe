from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _rows_as_dicts(
    sqlite_path: Path,
    sql: str,
    params: Iterable[Any] = (),
) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, list(params))]
    finally:
        conn.close()


def load_job_catalog(
    *,
    primary_db_path: Optional[Path],
    candidate_id: str,
) -> List[Dict[str, Any]]:
    """Load the latest job catalog from the primary DB.

    Prefer canonical jobs, enriched with evaluation data when present.
    Fall back to evaluation-only rows for older DB state.
    """
    if primary_db_path and primary_db_path.exists():
        try:
            rows = _rows_as_dicts(
                primary_db_path,
                """
                SELECT
                    j.job_id,
                    COALESCE(e.title, j.title) AS title,
                    COALESCE(e.employer, j.employer) AS employer,
                    COALESCE(e.work_city, j.work_city) AS work_city,
                    COALESCE(e.applicationDue, j.applicationDue) AS applicationDue,
                    COALESCE(e.source_url, j.source_url) AS source_url,
                    COALESCE(e.application_url, j.application_url) AS application_url,
                    COALESCE(e.final_decision, '') AS final_decision
                FROM jobs j
                LEFT JOIN job_evaluations e
                  ON e.candidate_id = ? AND e.job_id = j.job_id
                WHERE COALESCE(j.closed_at, '') = ''

                UNION ALL

                SELECT
                    e.job_id,
                    e.title,
                    e.employer,
                    e.work_city,
                    e.applicationDue,
                    e.source_url,
                    e.application_url,
                    e.final_decision
                FROM job_evaluations e
                WHERE e.candidate_id = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM jobs j WHERE j.job_id = e.job_id
                  )
                """,
                [candidate_id, candidate_id],
            )
            if rows:
                return rows
        except Exception:
            pass

    return []


def load_processed_job_ids(
    *,
    primary_db_path: Optional[Path],
    candidate_id: str,
) -> set[str]:
    """Return job_ids that have a completed evaluation for this candidate.

    "Processed" = a row exists in job_evaluations. Used by drain_queue's
    skip-already-evaluated filter. For broader catalog dedup (e.g. FINN
    scrapers checking whether a job is already mirrored), use load_job_catalog
    and derive ids from its rows.
    """
    if primary_db_path is None or not primary_db_path.exists():
        return set()
    try:
        rows = _rows_as_dicts(
            primary_db_path,
            "SELECT DISTINCT job_id FROM job_evaluations WHERE candidate_id = ?",
            [candidate_id],
        )
    except Exception:
        return set()
    return {
        str(row.get("job_id") or "").strip()
        for row in rows
        if str(row.get("job_id") or "").strip()
    }

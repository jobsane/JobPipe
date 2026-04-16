from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from jobpipe.core.io import now_iso


SCHEMA_VERSION = "3"


def _json_text(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def connect_primary_db(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            email TEXT NOT NULL DEFAULT '',
            locale TEXT NOT NULL DEFAULT 'nb-NO',
            timezone TEXT NOT NULL DEFAULT 'Europe/Oslo',
            base_location TEXT NOT NULL DEFAULT '',
            seniority_label TEXT NOT NULL DEFAULT '',
            positioning_summary TEXT NOT NULL DEFAULT '',
            strategic_direction TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS candidate_profiles (
            profile_version_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            content_hash TEXT NOT NULL,
            profile_pack_md TEXT NOT NULL,
            profile_json TEXT NOT NULL,
            resume_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
        );
        CREATE INDEX IF NOT EXISTS idx_candidate_profiles_candidate_active
            ON candidate_profiles(candidate_id, is_active);

        CREATE TABLE IF NOT EXISTS application_events (
            application_event_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_at TEXT NOT NULL,
            source TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
        );
        CREATE INDEX IF NOT EXISTS idx_application_events_candidate_job
            ON application_events(candidate_id, job_id);
        CREATE INDEX IF NOT EXISTS idx_application_events_event_at
            ON application_events(event_at);

        CREATE TABLE IF NOT EXISTS application_summary (
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            current_stage TEXT NOT NULL DEFAULT '',
            current_outcome TEXT NOT NULL DEFAULT '',
            effective_status TEXT NOT NULL DEFAULT '',
            last_event_at TEXT NOT NULL DEFAULT '',
            notes_latest TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (candidate_id, job_id),
            FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
        );

        CREATE TABLE IF NOT EXISTS generated_documents (
            document_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            evaluation_id TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL,
            producer TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            storage_path TEXT NOT NULL DEFAULT '',
            preview_text TEXT NOT NULL DEFAULT '',
            document_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
        );
        CREATE INDEX IF NOT EXISTS idx_generated_documents_candidate_job
            ON generated_documents(candidate_id, job_id);

        CREATE TABLE IF NOT EXISTS suggestion_leads (
            suggestion_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            external_id TEXT NOT NULL,
            job_url TEXT NOT NULL DEFAULT '',
            job_id_hint TEXT NOT NULL DEFAULT '',
            suggested_at TEXT NOT NULL DEFAULT '',
            email_subject TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'gmail_suggestions',
            status TEXT NOT NULL DEFAULT 'queued',
            fetched_at TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_suggestion_leads_candidate_platform_external
            ON suggestion_leads(candidate_id, platform, external_id);
        CREATE INDEX IF NOT EXISTS idx_suggestion_leads_candidate_status
            ON suggestion_leads(candidate_id, status, platform, updated_at);

        CREATE TABLE IF NOT EXISTS job_evaluations (
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            run_id TEXT NOT NULL DEFAULT '',
            run_mtime REAL NOT NULL DEFAULT 0,
            run_seen_at TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            employer TEXT NOT NULL DEFAULT '',
            sector TEXT NOT NULL DEFAULT '',
            work_city TEXT NOT NULL DEFAULT '',
            work_county TEXT NOT NULL DEFAULT '',
            work_postalCode TEXT NOT NULL DEFAULT '',
            applicationDue TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            application_url TEXT NOT NULL DEFAULT '',
            triage_decision TEXT NOT NULL DEFAULT '',
            triage_confidence REAL,
            triage_explanation TEXT NOT NULL DEFAULT '',
            triage_signals TEXT NOT NULL DEFAULT '',
            reverse_decision TEXT NOT NULL DEFAULT '',
            reverse_confidence REAL,
            reverse_rationale TEXT NOT NULL DEFAULT '',
            fit_score INTEGER,
            pivot_score INTEGER,
            final_decision TEXT NOT NULL DEFAULT '',
            final_confidence REAL,
            recommendation_reason TEXT NOT NULL DEFAULT '',
            cv_focus TEXT NOT NULL DEFAULT '',
            feedback_flags TEXT NOT NULL DEFAULT '',
            description_snip TEXT NOT NULL DEFAULT '',
            skip_reason TEXT NOT NULL DEFAULT '',
            raw_index_json TEXT NOT NULL DEFAULT '',
            raw_match_json TEXT NOT NULL DEFAULT '',
            raw_pivot_json TEXT NOT NULL DEFAULT '',
            raw_moderator_json TEXT NOT NULL DEFAULT '',
            closed_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (candidate_id, job_id),
            FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
        );
        CREATE INDEX IF NOT EXISTS idx_job_evaluations_candidate_decision
            ON job_evaluations(candidate_id, final_decision, applicationDue);

        CREATE TABLE IF NOT EXISTS job_run_events (
            candidate_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            run_mtime REAL NOT NULL DEFAULT 0,
            seen_at TEXT NOT NULL DEFAULT '',
            final_decision TEXT NOT NULL DEFAULT '',
            final_confidence REAL,
            triage_decision TEXT NOT NULL DEFAULT '',
            triage_confidence REAL,
            fit_score INTEGER,
            pivot_score INTEGER,
            applicationDue TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            employer TEXT NOT NULL DEFAULT '',
            work_city TEXT NOT NULL DEFAULT '',
            work_county TEXT NOT NULL DEFAULT '',
            work_postalCode TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            application_url TEXT NOT NULL DEFAULT '',
            raw_index_json TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (candidate_id, run_id, job_id),
            FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
        );
        CREATE INDEX IF NOT EXISTS idx_job_run_events_candidate_job
            ON job_run_events(candidate_id, job_id, run_mtime);
        """
    )

    ts = now_iso()
    conn.execute(
        """
        INSERT INTO schema_meta (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        ["schema_version", SCHEMA_VERSION, ts],
    )
    return conn


def _upsert(
    conn: sqlite3.Connection,
    table: str,
    row: Mapping[str, Any],
    key_columns: Iterable[str],
) -> None:
    names = list(row.keys())
    placeholders = ", ".join(["?"] * len(names))
    key_set = set(key_columns)
    assignments = ", ".join([f"{name}=excluded.{name}" for name in names if name not in key_set])
    sql = (
        f"INSERT INTO {table} ({', '.join(names)}) VALUES ({placeholders}) "
        f"ON CONFLICT({', '.join(key_columns)}) DO UPDATE SET {assignments};"
    )
    conn.execute(sql, [row.get(name) for name in names])


def upsert_candidate(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    _upsert(conn, "candidates", row, ["candidate_id"])


def ensure_candidate(
    conn: sqlite3.Connection,
    candidate_id: str,
    display_name: str = "Default Candidate",
    email: str = "",
    locale: str = "nb-NO",
    timezone: str = "Europe/Oslo",
) -> None:
    exists = conn.execute(
        "SELECT 1 FROM candidates WHERE candidate_id = ? LIMIT 1",
        [candidate_id],
    ).fetchone()
    if exists:
        return

    ts = now_iso()
    upsert_candidate(
        conn,
        {
            "candidate_id": candidate_id,
            "display_name": display_name,
            "email": email,
            "locale": locale,
            "timezone": timezone,
            "base_location": "",
            "seniority_label": "",
            "positioning_summary": "",
            "strategic_direction": "",
            "is_active": 1,
            "created_at": ts,
            "updated_at": ts,
        },
    )


def upsert_candidate_profile(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    conn.execute(
        "UPDATE candidate_profiles SET is_active = 0, updated_at = ? WHERE candidate_id = ?",
        [row["updated_at"], row["candidate_id"]],
    )
    _upsert(conn, "candidate_profiles", row, ["profile_version_id"])


def replace_imported_application_state(
    conn: sqlite3.Connection,
    candidate_id: str,
    events: list[Mapping[str, Any]],
    summaries: list[Mapping[str, Any]],
) -> None:
    conn.execute(
        "DELETE FROM application_events WHERE candidate_id = ? AND source LIKE 'state_import:%'",
        [candidate_id],
    )
    conn.execute("DELETE FROM application_summary WHERE candidate_id = ?", [candidate_id])

    for row in events:
        payload = dict(row)
        payload["metadata_json"] = _json_text(payload.get("metadata_json"))
        _upsert(conn, "application_events", payload, ["application_event_id"])

    for row in summaries:
        _upsert(conn, "application_summary", row, ["candidate_id", "job_id"])


def insert_application_event(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    payload = dict(row)
    payload["metadata_json"] = _json_text(payload.get("metadata_json"))
    _upsert(conn, "application_events", payload, ["application_event_id"])


def upsert_application_summary(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    _upsert(conn, "application_summary", row, ["candidate_id", "job_id"])


def delete_application_tracking(conn: sqlite3.Connection, candidate_id: str, job_id: str) -> None:
    conn.execute(
        "DELETE FROM application_events WHERE candidate_id = ? AND job_id = ?",
        [candidate_id, job_id],
    )
    conn.execute(
        "DELETE FROM application_summary WHERE candidate_id = ? AND job_id = ?",
        [candidate_id, job_id],
    )


def insert_generated_document(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    payload = dict(row)
    payload["document_json"] = _json_text(payload.get("document_json"))
    _upsert(conn, "generated_documents", payload, ["document_id"])


def upsert_suggestion_lead(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    payload = dict(row)
    payload["payload_json"] = _json_text(payload.get("payload_json"))
    _upsert(conn, "suggestion_leads", payload, ["suggestion_id"])


def list_suggestion_leads(
    conn: sqlite3.Connection,
    candidate_id: str,
    *,
    statuses: Iterable[str] | None = None,
    platform: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    clauses = ["candidate_id = ?"]
    params: list[Any] = [candidate_id]

    normalized_statuses = [str(s).strip() for s in (statuses or []) if str(s).strip()]
    if normalized_statuses:
        placeholders = ", ".join(["?"] * len(normalized_statuses))
        clauses.append(f"status IN ({placeholders})")
        params.extend(normalized_statuses)

    if platform:
        clauses.append("platform = ?")
        params.append(platform)

    sql = """
        SELECT suggestion_id, candidate_id, platform, external_id, job_url, job_id_hint,
               suggested_at, email_subject, source, status, fetched_at, last_error,
               payload_json, created_at, updated_at
        FROM suggestion_leads
        WHERE {where}
        ORDER BY
            CASE status
                WHEN 'queued' THEN 0
                WHEN 'fetched' THEN 1
                WHEN 'failed' THEN 2
                ELSE 3
            END,
            suggested_at DESC,
            updated_at DESC
    """.format(where=" AND ".join(clauses))
    if limit and int(limit) > 0:
        sql += " LIMIT ?"
        params.append(int(limit))

    cursor = conn.execute(sql, params)
    columns = [col[0] for col in (cursor.description or [])]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    for row in rows:
        try:
            row["payload_json"] = json.loads(row.get("payload_json") or "{}")
        except Exception:
            pass
    return rows


def mark_suggestion_lead_status(
    conn: sqlite3.Connection,
    suggestion_id: str,
    *,
    status: str,
    fetched_at: str = "",
    last_error: str = "",
    updated_at: str,
) -> None:
    conn.execute(
        """
        UPDATE suggestion_leads
        SET status = ?, fetched_at = ?, last_error = ?, updated_at = ?
        WHERE suggestion_id = ?
        """,
        [status, fetched_at, last_error, updated_at, suggestion_id],
    )


def upsert_job_evaluation(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    _upsert(conn, "job_evaluations", row, ["candidate_id", "job_id"])


def upsert_job_run_event(conn: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    _upsert(conn, "job_run_events", row, ["candidate_id", "run_id", "job_id"])

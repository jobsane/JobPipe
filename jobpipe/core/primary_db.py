from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from jobpipe.core.io import now_iso


SCHEMA_VERSION = "1"


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

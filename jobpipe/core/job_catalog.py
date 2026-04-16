from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from jobpipe.core.io import clean, html_to_text, pick, stable_job_id


SOURCE_PRIORITIES: dict[str, int] = {
    "nav": 100,
    "nav_sheet": 100,
    "nav_api": 100,
    "finn": 60,
    "linkedin": 40,
}

_SOURCE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("nav_sheet", "nav"),
    ("nav_api", "nav"),
    ("nav", "nav"),
    ("finn", "finn"),
    ("linkedin", "linkedin"),
)


def source_priority(source_name: str) -> int:
    normalized = clean(source_name).lower()
    if normalized in SOURCE_PRIORITIES:
        return SOURCE_PRIORITIES[normalized]
    for prefix, canonical in _SOURCE_PREFIXES:
        if normalized.startswith(prefix):
            return SOURCE_PRIORITIES[canonical]
    return 10


def source_platform(source_name: str) -> str:
    normalized = clean(source_name).lower()
    for prefix, canonical in _SOURCE_PREFIXES:
        if normalized.startswith(prefix):
            return canonical
    return normalized


def _normalize_key_part(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r"\s+", " ", text)
    return text


def canonical_job_dedupe_key(job: Mapping[str, Any]) -> str:
    title = _normalize_key_part(pick(job.get("normalized_title"), job.get("title")))
    employer = _normalize_key_part(pick(job.get("employer_name"), job.get("employer")))
    city = _normalize_key_part(job.get("work_city"))
    postal = _normalize_key_part(job.get("work_postalCode"))
    due = _normalize_key_part(job.get("applicationDue"))
    return "|".join([title, employer, city, postal, due])


def canonical_job_content_hash(job: Mapping[str, Any]) -> str:
    payload = {
        "title": clean(job.get("title")),
        "normalized_title": clean(job.get("normalized_title")),
        "employer_name": clean(job.get("employer_name")),
        "description_html": clean(job.get("description_html")),
        "sourceurl": clean(job.get("sourceurl")),
        "link": clean(job.get("link")),
        "applicationUrl": clean(job.get("applicationUrl")),
        "applicationDue": clean(job.get("applicationDue")),
        "work_city": clean(job.get("work_city")),
        "work_county": clean(job.get("work_county")),
        "work_postalCode": clean(job.get("work_postalCode")),
        "sector": clean(job.get("sector")),
        "status": clean(job.get("status")),
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def source_job_key(job: Mapping[str, Any]) -> str:
    return pick(
        job.get("finnkode"),
        job.get("linkedin_job_id"),
        job.get("external_id"),
        job.get("uuid"),
        job.get("id"),
        job.get("stilling_id"),
        job.get("job_id"),
        job.get("sourceurl"),
        job.get("link"),
        job.get("applicationUrl"),
        stable_job_id(dict(job)),
    )


def source_record_id(source_name: str, source_job_key_value: str) -> str:
    raw = f"{clean(source_name)}|{clean(source_job_key_value)}"
    return "src_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _metadata_json(job: Mapping[str, Any], *, source_name: str = "") -> dict[str, Any]:
    core_keys = {
        "job_id",
        "uuid",
        "id",
        "stilling_id",
        "finnkode",
        "linkedin_job_id",
        "external_id",
        "title",
        "normalized_title",
        "employer_name",
        "employer",
        "description_html",
        "sourceurl",
        "link",
        "applicationUrl",
        "applicationDue",
        "work_city",
        "work_county",
        "work_postalCode",
        "sector",
        "status",
        "sistEndret",
        "ad_updated",
    }
    metadata = {str(k): v for k, v in job.items() if k not in core_keys and v not in ("", None)}
    if source_name:
        metadata["_canonical_source_name"] = clean(source_name)
        metadata["_canonical_source_priority"] = source_priority(source_name)
        metadata["_canonical_source_platform"] = source_platform(source_name)
    return metadata


def canonical_job_row(job: Mapping[str, Any], seen_at: str, *, source_name: str = "") -> dict[str, Any]:
    return {
        "job_id": stable_job_id(dict(job)),
        "dedupe_key": canonical_job_dedupe_key(job),
        "title": pick(job.get("normalized_title"), job.get("title")),
        "employer": pick(job.get("employer_name"), job.get("employer")),
        "work_city": clean(job.get("work_city")),
        "work_county": clean(job.get("work_county")),
        "work_postalCode": clean(job.get("work_postalCode")),
        "applicationDue": clean(job.get("applicationDue")),
        "source_url": pick(job.get("sourceurl"), job.get("link")),
        "application_url": clean(job.get("applicationUrl")),
        "description_text": html_to_text(clean(job.get("description_html")), max_chars=5000),
        "description_html": clean(job.get("description_html")),
        "sector": clean(job.get("sector")),
        "job_metadata_json": _metadata_json(job, source_name=source_name),
        "content_hash": canonical_job_content_hash(job),
        "first_seen_at": seen_at,
        "last_seen_at": seen_at,
        "closed_at": "",
        "updated_at": seen_at,
    }


def job_source_record_row(job: Mapping[str, Any], source_name: str, seen_at: str) -> dict[str, Any]:
    source_key = source_job_key(job)
    return {
        "source_record_id": source_record_id(source_name, source_key),
        "source_name": clean(source_name),
        "source_job_key": source_key,
        "job_id": stable_job_id(dict(job)),
        "seen_at": seen_at,
        "last_seen_at": seen_at,
        "is_active": 0 if clean(job.get("status")).upper() == "INACTIVE" else 1,
        "source_url": pick(job.get("sourceurl"), job.get("link")),
        "work_city": clean(job.get("work_city")),
        "work_county": clean(job.get("work_county")),
        "work_postalCode": clean(job.get("work_postalCode")),
        "applicationDue": clean(job.get("applicationDue")),
        "content_hash": canonical_job_content_hash(job),
        "raw_payload_json": dict(job),
        "updated_at": seen_at,
    }


def _metadata_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _preferred_value(existing: str, incoming: str, *, existing_priority: int, incoming_priority: int) -> str:
    old = clean(existing)
    new = clean(incoming)
    if not old:
        return new
    if not new:
        return old
    if incoming_priority > existing_priority:
        return new
    if existing_priority > incoming_priority:
        return old
    if len(new) > len(old):
        return new
    return old


def job_needs_enrichment(job_row: Mapping[str, Any]) -> bool:
    description = clean(job_row.get("description_html")) or clean(job_row.get("description_text"))
    source_url = clean(job_row.get("source_url"))
    return not (
        description
        and len(description) >= 40
        and source_url
    )


def _fetch_existing_job(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT job_id, dedupe_key, title, employer, work_city, work_county, work_postalCode,
               applicationDue, source_url, application_url, description_text, description_html,
               sector, job_metadata_json, content_hash, first_seen_at, last_seen_at, closed_at, updated_at
        FROM jobs
        WHERE job_id = ?
        LIMIT 1
        """,
        [job_id],
    ).fetchone()
    if not row:
        return None
    columns = [
        "job_id",
        "dedupe_key",
        "title",
        "employer",
        "work_city",
        "work_county",
        "work_postalCode",
        "applicationDue",
        "source_url",
        "application_url",
        "description_text",
        "description_html",
        "sector",
        "job_metadata_json",
        "content_hash",
        "first_seen_at",
        "last_seen_at",
        "closed_at",
        "updated_at",
    ]
    payload = dict(zip(columns, row))
    payload["job_metadata_json"] = _metadata_dict(payload.get("job_metadata_json"))
    return payload


def _find_existing_job_id(conn: sqlite3.Connection, job: Mapping[str, Any], source_name: str) -> str:
    source_key = source_job_key(job)
    if source_key:
        row = conn.execute(
            """
            SELECT job_id
            FROM job_source_records
            WHERE source_name = ? AND source_job_key = ?
            LIMIT 1
            """,
            [clean(source_name), source_key],
        ).fetchone()
        if row and row[0]:
            return str(row[0])

    source_url = pick(job.get("sourceurl"), job.get("link"), job.get("applicationUrl"))
    if source_url:
        row = conn.execute(
            """
            SELECT job_id
            FROM jobs
            WHERE source_url = ? OR application_url = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            [source_url, source_url],
        ).fetchone()
        if row and row[0]:
            return str(row[0])

    dedupe_key = canonical_job_dedupe_key(job)
    if dedupe_key:
        rows = conn.execute(
            """
            SELECT j.job_id, COALESCE(json_extract(j.job_metadata_json, '$._canonical_source_priority'), 0) AS src_priority
            FROM jobs j
            WHERE j.dedupe_key = ?
            ORDER BY src_priority DESC, j.updated_at DESC
            LIMIT 2
            """,
            [dedupe_key],
        ).fetchall()
        if len(rows) == 1 and rows[0][0]:
            return str(rows[0][0])
        if len(rows) > 1 and rows[0][1] != rows[1][1]:
            return str(rows[0][0])

    return ""


def merge_canonical_job_row(
    existing_row: Mapping[str, Any],
    incoming_row: Mapping[str, Any],
    *,
    source_name: str,
    seen_at: str,
) -> dict[str, Any]:
    existing = dict(existing_row)
    incoming = dict(incoming_row)

    existing_meta = _metadata_dict(existing.get("job_metadata_json"))
    incoming_meta = _metadata_dict(incoming.get("job_metadata_json"))
    existing_priority = int(existing_meta.get("_canonical_source_priority") or 0)
    incoming_priority = source_priority(source_name)

    merged = {
        "job_id": clean(existing.get("job_id")) or clean(incoming.get("job_id")),
        "dedupe_key": clean(existing.get("dedupe_key")) or clean(incoming.get("dedupe_key")),
        "title": _preferred_value(existing.get("title", ""), incoming.get("title", ""), existing_priority=existing_priority, incoming_priority=incoming_priority),
        "employer": _preferred_value(existing.get("employer", ""), incoming.get("employer", ""), existing_priority=existing_priority, incoming_priority=incoming_priority),
        "work_city": _preferred_value(existing.get("work_city", ""), incoming.get("work_city", ""), existing_priority=existing_priority, incoming_priority=incoming_priority),
        "work_county": _preferred_value(existing.get("work_county", ""), incoming.get("work_county", ""), existing_priority=existing_priority, incoming_priority=incoming_priority),
        "work_postalCode": _preferred_value(existing.get("work_postalCode", ""), incoming.get("work_postalCode", ""), existing_priority=existing_priority, incoming_priority=incoming_priority),
        "applicationDue": _preferred_value(existing.get("applicationDue", ""), incoming.get("applicationDue", ""), existing_priority=existing_priority, incoming_priority=incoming_priority),
        "source_url": _preferred_value(existing.get("source_url", ""), incoming.get("source_url", ""), existing_priority=existing_priority, incoming_priority=incoming_priority),
        "application_url": _preferred_value(existing.get("application_url", ""), incoming.get("application_url", ""), existing_priority=existing_priority, incoming_priority=incoming_priority),
        "description_text": _preferred_value(existing.get("description_text", ""), incoming.get("description_text", ""), existing_priority=existing_priority, incoming_priority=incoming_priority),
        "description_html": _preferred_value(existing.get("description_html", ""), incoming.get("description_html", ""), existing_priority=existing_priority, incoming_priority=incoming_priority),
        "sector": _preferred_value(existing.get("sector", ""), incoming.get("sector", ""), existing_priority=existing_priority, incoming_priority=incoming_priority),
        "job_metadata_json": {},
        "content_hash": "",
        "first_seen_at": clean(existing.get("first_seen_at")) or clean(incoming.get("first_seen_at")) or seen_at,
        "last_seen_at": seen_at,
        "closed_at": "",
        "updated_at": seen_at,
    }

    merged_meta = {**existing_meta, **incoming_meta}
    if incoming_priority > existing_priority:
        merged_meta["_canonical_source_name"] = clean(source_name)
        merged_meta["_canonical_source_priority"] = incoming_priority
        merged_meta["_canonical_source_platform"] = source_platform(source_name)
    else:
        merged_meta.setdefault("_canonical_source_name", clean(source_name))
        merged_meta.setdefault("_canonical_source_priority", incoming_priority)
        merged_meta.setdefault("_canonical_source_platform", source_platform(source_name))
    merged["job_metadata_json"] = merged_meta
    merged["content_hash"] = canonical_job_content_hash(
        {
            "title": merged["title"],
            "normalized_title": merged["title"],
            "employer_name": merged["employer"],
            "description_html": merged["description_html"],
            "sourceurl": merged["source_url"],
            "link": merged["source_url"],
            "applicationUrl": merged["application_url"],
            "applicationDue": merged["applicationDue"],
            "work_city": merged["work_city"],
            "work_county": merged["work_county"],
            "work_postalCode": merged["work_postalCode"],
            "sector": merged["sector"],
            "status": "ACTIVE",
        }
    )
    return merged


def ingest_catalog_job(
    conn: sqlite3.Connection,
    job: Mapping[str, Any],
    *,
    source_name: str,
    seen_at: str,
) -> dict[str, Any]:
    from jobpipe.core.primary_db import upsert_job, upsert_job_source_record

    existing_job_id = _find_existing_job_id(conn, job, source_name)
    job_row = canonical_job_row(job, seen_at, source_name=source_name)
    source_row = job_source_record_row(job, source_name, seen_at)

    if existing_job_id:
        existing_row = _fetch_existing_job(conn, existing_job_id)
        job_row["job_id"] = existing_job_id
        source_row["job_id"] = existing_job_id
        if existing_row:
            job_row = merge_canonical_job_row(
                existing_row,
                job_row,
                source_name=source_name,
                seen_at=seen_at,
            )

    upsert_job(conn, job_row)
    upsert_job_source_record(conn, source_row)

    persisted = _fetch_existing_job(conn, job_row["job_id"]) or job_row
    return {
        "job_id": job_row["job_id"],
        "matched_existing": bool(existing_job_id),
        "needs_enrichment": job_needs_enrichment(persisted),
    }


def load_source_record_index(db_path: str | Path) -> dict[tuple[str, str], dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT
                r.source_name,
                r.source_job_key,
                r.job_id,
                r.is_active,
                j.title,
                j.employer,
                j.source_url,
                j.application_url,
                j.description_html,
                j.description_text,
                j.closed_at
            FROM job_source_records r
            JOIN jobs j ON j.job_id = r.job_id
            """
        ).fetchall()
    finally:
        conn.close()

    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        payload = {
            "source_name": row[0],
            "source_job_key": row[1],
            "job_id": row[2],
            "is_active": int(row[3] or 0),
            "title": row[4] or "",
            "employer": row[5] or "",
            "source_url": row[6] or "",
            "application_url": row[7] or "",
            "description_html": row[8] or "",
            "description_text": row[9] or "",
            "closed_at": row[10] or "",
        }
        payload["needs_enrichment"] = job_needs_enrichment(payload)
        index[(source_platform(str(row[0] or "")), str(row[1] or ""))] = payload
    return index

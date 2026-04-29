from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jobpipe.cli.mark_status import VALID_STAGES, load_state
from jobpipe.core.io import load_env_file, now_iso
from jobpipe.core.profile_pack import parse_profile_pack
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices
from jobpipe.core.primary_db import (
    connect_primary_db,
    replace_imported_application_state,
    upsert_candidate,
    upsert_candidate_profile,
)


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _profile_content_hash(profile_text: str, resume_json: dict[str, Any]) -> str:
    payload = {
        "profile_pack_md": profile_text,
        "resume_json": resume_json,
    }
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _event_row(
    candidate_id: str,
    job_id: str,
    event_type: str,
    event_at: str,
    source: str,
    notes: str,
    metadata: dict[str, Any],
    ordinal: int,
) -> dict[str, Any]:
    raw = f"{candidate_id}|{job_id}|{event_type}|{ordinal}|{event_at}|{source}"
    event_id = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return {
        "application_event_id": event_id,
        "candidate_id": candidate_id,
        "job_id": job_id,
        "event_type": event_type,
        "event_at": event_at,
        "source": source,
        "notes": notes,
        "metadata_json": metadata,
        "created_at": now_iso(),
    }


def _effective_status(entry: dict[str, Any]) -> str:
    outcome = entry.get("outcome") or ""
    if outcome:
        return outcome
    stages = entry.get("stages") or []
    for stage in reversed(VALID_STAGES):
        if stage in stages:
            return stage
    return ""


def import_application_snapshot(candidate_id: str, state: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    apps = state.get("applications", {})
    for job_id, entry in sorted(apps.items()):
        stages = [stage for stage in entry.get("stages", []) if stage in VALID_STAGES]
        outcome = (entry.get("outcome") or "").strip()
        notes = (entry.get("notes") or "").strip()
        source = f"state_import:{(entry.get('source') or 'manual').strip() or 'manual'}"
        event_at = (entry.get("email_date") or entry.get("updated_at") or state.get("updated_at") or now_iso()).strip()

        ordered: list[str] = list(stages)
        if outcome:
            ordered.append(outcome)
        if not ordered and notes:
            ordered.append("note_added")

        metadata_base = {
            "status_snapshot": entry.get("status", ""),
            "email_subject": entry.get("email_subject", ""),
            "email_date": entry.get("email_date", ""),
        }

        for ordinal, event_type in enumerate(ordered, start=1):
            event_notes = notes if ordinal == len(ordered) else ""
            metadata = dict(metadata_base)
            metadata["import_ordinal"] = ordinal
            events.append(
                _event_row(
                    candidate_id=candidate_id,
                    job_id=job_id,
                    event_type=event_type,
                    event_at=event_at,
                    source=source,
                    notes=event_notes,
                    metadata=metadata,
                    ordinal=ordinal,
                )
            )

        summaries.append(
            {
                "candidate_id": candidate_id,
                "job_id": job_id,
                "current_stage": stages[-1] if stages else "",
                "current_outcome": outcome,
                "effective_status": _effective_status(entry),
                "last_event_at": event_at,
                "notes_latest": notes,
                "updated_at": now_iso(),
            }
        )

    return events, summaries


def bootstrap_primary_db(
    *,
    db_path: Path,
    profile_path: Path,
    resume_path: Path,
    app_state_path: Path,
    candidate_id: str,
    display_name_override: str = "",
    email: str = "",
    locale: str = "nb-NO",
    timezone: str = "Europe/Oslo",
) -> dict[str, Any]:
    profile_text = _read_text(profile_path)
    resume_json = _read_json(resume_path)
    app_state = load_state(app_state_path)

    parsed_profile = parse_profile_pack(profile_text)
    snapshot = parsed_profile.get("snapshot", {})
    display_name = (display_name_override or snapshot.get("name") or "Default Candidate").strip()

    now = now_iso()
    profile_hash = _profile_content_hash(profile_text, resume_json)
    profile_version_id = f"profile_{profile_hash[:12]}"

    conn = connect_primary_db(db_path)
    try:
        upsert_candidate(
            conn,
            {
                "candidate_id": candidate_id,
                "display_name": display_name,
                "email": email,
                "locale": locale,
                "timezone": timezone,
                "base_location": snapshot.get("base", ""),
                "seniority_label": snapshot.get("level", ""),
                "positioning_summary": snapshot.get("positioning", ""),
                "strategic_direction": parsed_profile.get("strategic_direction", ""),
                "is_active": 1,
                "created_at": now,
                "updated_at": now,
            },
        )

        upsert_candidate_profile(
            conn,
            {
                "profile_version_id": profile_version_id,
                "candidate_id": candidate_id,
                "source_kind": "bootstrap_import",
                "is_active": 1,
                "content_hash": profile_hash,
                "profile_pack_md": profile_text,
                "profile_json": json.dumps(parsed_profile, ensure_ascii=False, sort_keys=True),
                "resume_json": json.dumps(resume_json, ensure_ascii=False, sort_keys=True),
                "created_at": now,
                "updated_at": now,
            },
        )

        events, summaries = import_application_snapshot(candidate_id, app_state)
        replace_imported_application_state(conn, candidate_id, events, summaries)
        conn.commit()
    finally:
        conn.close()

    return {
        "db_path": db_path.resolve(),
        "candidate_id": candidate_id,
        "display_name": display_name,
        "profile_path": profile_path.resolve(),
        "resume_path": resume_path.resolve(),
        "app_state_path": app_state_path.resolve(),
        "profile_version_id": profile_version_id,
        "events_stored": len(events),
        "jobs_tracked": len(summaries),
    }


def main() -> None:
    load_env_file(".env")

    ap = argparse.ArgumentParser(
        description="Bootstrap the primary JobPipe SQLite database from current local profile and application state files."
    )
    ap.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="default", help="Runtime profile to resolve DB/input paths from")
    ap.add_argument("--data-root", default="", help="Runtime data root override for live_local profile")
    ap.add_argument("--db", default="", help="Path to primary SQLite DB")
    ap.add_argument("--profile", default="", help="Path to profile_pack.md")
    ap.add_argument("--resume", default="", help="Path to resume.json")
    ap.add_argument("--app-state", default="", help="Path to application_state.json")
    ap.add_argument("--candidate-id", default="default", help="Stable candidate ID to store in the DB")
    ap.add_argument("--display-name", default="", help="Optional display name override")
    ap.add_argument("--email", default="", help="Optional candidate email")
    ap.add_argument("--locale", default="nb-NO", help="Candidate locale")
    ap.add_argument("--timezone", default="Europe/Oslo", help="Candidate timezone")
    args = ap.parse_args()

    runtime = resolve_profile_paths(
        args.runtime_profile,
        data_root_override=args.data_root,
        db_override=args.db,
        profile_override=args.profile,
        resume_override=args.resume,
        app_state_override=args.app_state,
    )

    summary = bootstrap_primary_db(
        db_path=runtime.primary_db_path,
        profile_path=runtime.profile_pack_path,
        resume_path=runtime.resume_json_path,
        app_state_path=runtime.application_state_path,
        candidate_id=args.candidate_id,
        display_name_override=args.display_name,
        email=args.email,
        locale=args.locale,
        timezone=args.timezone,
    )

    print("=== JobPipe Primary DB Bootstrap ===")
    print(f"DB:            {summary['db_path']}")
    print(f"Candidate ID:  {summary['candidate_id']}")
    print(f"Display name:  {summary['display_name']}")
    print(f"Profile path:  {summary['profile_path']}")
    print(f"Resume path:   {summary['resume_path']}")
    print(f"App state:     {summary['app_state_path']}")
    print(f"Profile ver.:  {summary['profile_version_id']}")
    print(f"Events stored: {summary['events_stored']}")
    print(f"Jobs tracked:  {summary['jobs_tracked']}")


if __name__ == "__main__":
    main()

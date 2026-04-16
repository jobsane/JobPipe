from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from jobpipe.cli.mark_status import VALID_STAGES, load_state
from jobpipe.core.io import load_env_file, now_iso
from jobpipe.core.paths import application_state_path, primary_db_path, profile_pack_path, resume_json_path
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


def _clean_line(s: str) -> str:
    return s.strip().strip("\ufeff")


def _markdown_sections(text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_h2: dict[str, Any] | None = None
    current_h3: dict[str, Any] | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            current_h2 = {"title": line[3:].strip(), "lines": [], "subsections": []}
            sections.append(current_h2)
            current_h3 = None
            continue
        if line.startswith("### "):
            if current_h2 is None:
                continue
            current_h3 = {"title": line[4:].strip(), "lines": []}
            current_h2["subsections"].append(current_h3)
            continue
        if current_h3 is not None:
            current_h3["lines"].append(line)
        elif current_h2 is not None:
            current_h2["lines"].append(line)

    return sections


def _bullet_items(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        stripped = _clean_line(line)
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def _parse_label_value_bullets(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if ":" not in item:
            continue
        key, value = item.split(":", 1)
        out[key.strip().lower()] = value.strip()
    return out


def parse_profile_pack(profile_text: str) -> dict[str, Any]:
    sections = _markdown_sections(profile_text)
    parsed: dict[str, Any] = {
        "sections": [],
        "snapshot": {},
        "strategic_direction": "",
        "target_roles": {"primary": [], "secondary": [], "hard_no": []},
        "constraints": {"location_ok": [], "remote_hybrid": ""},
        "geo_whitelist_prefixes": [],
        "hard_no_roles": [],
        "keyword_signals": {"tier_a": [], "tier_b": []},
        "negative_keywords": [],
        "evidence_sections": [],
        "education": [],
    }

    for section in sections:
        title = section["title"]
        title_lower = title.lower()
        bullets = _bullet_items(section["lines"])
        section_record: dict[str, Any] = {
            "title": title,
            "body": "\n".join([ln for ln in section["lines"] if _clean_line(ln)]).strip(),
            "bullets": bullets,
            "subsections": [],
        }

        for subsection in section["subsections"]:
            sub_bullets = _bullet_items(subsection["lines"])
            section_record["subsections"].append(
                {
                    "title": subsection["title"],
                    "body": "\n".join([ln for ln in subsection["lines"] if _clean_line(ln)]).strip(),
                    "bullets": sub_bullets,
                }
            )

        parsed["sections"].append(section_record)

        if "candidate snapshot" in title_lower:
            snapshot = _parse_label_value_bullets(bullets)
            parsed["snapshot"] = {
                "name": snapshot.get("name", ""),
                "base": snapshot.get("base", ""),
                "languages": snapshot.get("languages", ""),
                "level": snapshot.get("level", ""),
                "positioning": snapshot.get("positioning", ""),
            }
            for subsection in section["subsections"]:
                if "strategic direction" in subsection["title"].lower():
                    body = "\n".join([ln for ln in subsection["lines"] if _clean_line(ln)]).strip()
                    parsed["strategic_direction"] = body

        elif "target roles" in title_lower:
            for subsection in section["subsections"]:
                sub_title = subsection["title"].lower()
                items = _bullet_items(subsection["lines"])
                if "primary" in sub_title:
                    parsed["target_roles"]["primary"] = items
                elif "secondary" in sub_title:
                    parsed["target_roles"]["secondary"] = items
                elif "hard no" in sub_title:
                    parsed["target_roles"]["hard_no"] = items

        elif "must-haves" in title_lower:
            for subsection in section["subsections"]:
                sub_title = subsection["title"].lower()
                body = "\n".join([ln for ln in subsection["lines"] if _clean_line(ln)]).strip()
                items = _bullet_items(subsection["lines"])
                if "location" in sub_title:
                    parsed["constraints"]["location_ok"] = items
                    parsed["constraints"]["remote_hybrid"] = body

        elif "geo whitelist" in title_lower:
            prefixes: list[str] = []
            for item in bullets:
                match = re.search(r'"([^"]+)"', item)
                if match:
                    prefixes.append(match.group(1))
                    continue
                prefixes.append(item.split()[0])
            parsed["geo_whitelist_prefixes"] = prefixes

        elif "hard no" in title_lower:
            parsed["hard_no_roles"] = bullets

        elif "keyword signals" in title_lower:
            for subsection in section["subsections"]:
                sub_title = subsection["title"].lower()
                items = _bullet_items(subsection["lines"])
                if "tier a" in sub_title:
                    parsed["keyword_signals"]["tier_a"] = items
                elif "tier b" in sub_title:
                    parsed["keyword_signals"]["tier_b"] = items

        elif "negative keywords" in title_lower:
            parsed["negative_keywords"] = bullets

        elif "evidence bullets" in title_lower:
            evidence_sections: list[dict[str, Any]] = []
            for subsection in section["subsections"]:
                evidence_sections.append(
                    {
                        "label": subsection["title"],
                        "bullets": _bullet_items(subsection["lines"]),
                    }
                )
            parsed["evidence_sections"] = evidence_sections

        elif title_lower.startswith("8)") or "education" in title_lower:
            parsed["education"] = bullets

    return parsed


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


def main() -> None:
    load_env_file(".env")

    ap = argparse.ArgumentParser(
        description="Bootstrap the primary JobPipe SQLite database from current local profile and application state files."
    )
    ap.add_argument("--db", default=str(primary_db_path()), help="Path to primary SQLite DB")
    ap.add_argument("--profile", default=str(profile_pack_path()), help="Path to profile_pack.md")
    ap.add_argument("--resume", default=str(resume_json_path()), help="Path to resume.json")
    ap.add_argument("--app-state", default=str(application_state_path()), help="Path to application_state.json")
    ap.add_argument("--candidate-id", default="default", help="Stable candidate ID to store in the DB")
    ap.add_argument("--display-name", default="", help="Optional display name override")
    ap.add_argument("--email", default="", help="Optional candidate email")
    ap.add_argument("--locale", default="nb-NO", help="Candidate locale")
    ap.add_argument("--timezone", default="Europe/Oslo", help="Candidate timezone")
    args = ap.parse_args()

    db_path = Path(args.db)
    profile_path = Path(args.profile)
    resume_path = Path(args.resume)
    app_state_path = Path(args.app_state)

    profile_text = _read_text(profile_path)
    resume_json = _read_json(resume_path)
    app_state = load_state(app_state_path)

    parsed_profile = parse_profile_pack(profile_text)
    snapshot = parsed_profile.get("snapshot", {})
    display_name = (args.display_name or snapshot.get("name") or "Default Candidate").strip()

    now = now_iso()
    profile_hash = _profile_content_hash(profile_text, resume_json)
    profile_version_id = f"profile_{profile_hash[:12]}"

    conn = connect_primary_db(db_path)
    try:
        upsert_candidate(
            conn,
            {
                "candidate_id": args.candidate_id,
                "display_name": display_name,
                "email": args.email,
                "locale": args.locale,
                "timezone": args.timezone,
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
                "candidate_id": args.candidate_id,
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

        events, summaries = import_application_snapshot(args.candidate_id, app_state)
        replace_imported_application_state(conn, args.candidate_id, events, summaries)

        conn.commit()
    finally:
        conn.close()

    print("=== JobPipe Primary DB Bootstrap ===")
    print(f"DB:            {db_path.resolve()}")
    print(f"Candidate ID:  {args.candidate_id}")
    print(f"Display name:  {display_name}")
    print(f"Profile path:  {profile_path.resolve()}")
    print(f"Resume path:   {resume_path.resolve()}")
    print(f"App state:     {app_state_path.resolve()}")
    print(f"Profile ver.:  {profile_version_id}")
    print(f"Events stored: {len(events)}")
    print(f"Jobs tracked:  {len(summaries)}")


if __name__ == "__main__":
    main()

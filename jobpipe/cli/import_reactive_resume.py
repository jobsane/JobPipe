"""Import a structured Reactive Resume JSON snapshot into canonical candidate_profiles state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

from jobpipe.core.candidate_data import load_candidate_profile_pack
from jobpipe.core.io import now_iso
from jobpipe.core.profile_pack import parse_profile_pack
from jobpipe.core.primary_db import connect_primary_db, upsert_candidate, upsert_candidate_profile
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices

_DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _content_hash(profile_pack: str, resume_json: dict[str, Any]) -> str:
    payload = {"profile_pack_md": profile_pack, "resume_json": resume_json}
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Import a structured Reactive Resume JSON snapshot into canonical candidate_profiles state."
    )
    parser.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="default", help="Runtime profile to resolve DB/profile/resume paths from")
    parser.add_argument("--data-root", default="", help="Runtime data root override for live_local profile")
    parser.add_argument(
        "resume_json_path",
        nargs="?",
        default=None,
        help="Path to the structured resume JSON export (default: resolves via resume_json_path(), which prefers ./profile/resume.json)",
    )
    parser.add_argument("--profile", default="", help="Optional profile_pack.md override")
    parser.add_argument("--candidate-id", default=_DEFAULT_CANDIDATE_ID, help=f"Candidate ID (default: {_DEFAULT_CANDIDATE_ID})")
    parser.add_argument("--db", default="", help="Path to primary jobpipe.sqlite override")
    parser.add_argument("--display-name", default="", help="Optional display name override")
    args = parser.parse_args(argv)

    runtime = resolve_profile_paths(
        args.runtime_profile,
        data_root_override=args.data_root,
        db_override=args.db,
        profile_override=args.profile,
        resume_override=args.resume_json_path or "",
    )
    resume_path = runtime.resume_json_path
    if not resume_path.exists():
        raise SystemExit(
            f"Resume JSON not found at {resume_path}. "
            "Provide a path argument, drop a file at ./profile/resume.json, "
            "or set JOBPIPE_RESUME_JSON."
        )
    resume_json = _read_json(resume_path)
    db_path = runtime.primary_db_path
    profile_pack = load_candidate_profile_pack(str(runtime.profile_pack_path), candidate_id=args.candidate_id, db_path=db_path)
    parsed_profile = parse_profile_pack(profile_pack)
    snapshot = parsed_profile.get("snapshot", {})
    basics = resume_json.get("basics") if isinstance(resume_json.get("basics"), dict) else {}

    display_name = (
        args.display_name
        or str(basics.get("name") or "").strip()
        or str(snapshot.get("name") or "").strip()
        or "Default Candidate"
    )
    email = str(basics.get("email") or "").strip()
    now = now_iso()
    profile_hash = _content_hash(profile_pack, resume_json)
    profile_version_id = f"profile_{profile_hash[:12]}"

    conn = connect_primary_db(db_path)
    try:
        upsert_candidate(
            conn,
            {
                "candidate_id": args.candidate_id,
                "display_name": display_name,
                "email": email,
                "locale": "nb-NO",
                "timezone": "Europe/Oslo",
                "base_location": str(snapshot.get("base") or basics.get("location") or "").strip(),
                "seniority_label": str(snapshot.get("level") or "").strip(),
                "positioning_summary": str(snapshot.get("positioning") or "").strip(),
                "strategic_direction": str(parsed_profile.get("strategic_direction") or "").strip(),
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
                "source_kind": "reactive_resume_import",
                "is_active": 1,
                "content_hash": profile_hash,
                "profile_pack_md": profile_pack,
                "profile_json": json.dumps(parsed_profile, ensure_ascii=False, sort_keys=True),
                "resume_json": json.dumps(resume_json, ensure_ascii=False, sort_keys=True),
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Reactive Resume imported: {resume_path}")
    print(f"  candidate_id: {args.candidate_id}")
    print(f"  profile_version_id: {profile_version_id}")


if __name__ == "__main__":
    main()

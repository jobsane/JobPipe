from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from jobpipe.cli.bootstrap_state_db import bootstrap_primary_db
from jobpipe.cli.reset_runtime import _default_tag, reset_runtime_state
from jobpipe.core.io import load_env_file
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices


def main(argv: Sequence[str] | None = None) -> None:
    load_env_file(".env")

    ap = argparse.ArgumentParser(
        description="Reset generated runtime state for one runtime profile, then rebuild canonical candidate/application state against that same profile."
    )
    ap.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="live_local", help="Runtime profile to refresh")
    ap.add_argument("--data-root", default="", help="Runtime data root override for live_local profile")
    ap.add_argument("--archive-root", default="", help="Archive root override (default: <data-root>/_archives)")
    ap.add_argument("--tag", default="", help="Archive tag override")
    ap.add_argument("--no-restore-app-state", action="store_true", help="Do not restore application_state.json before bootstrap")
    ap.add_argument("--db", default="", help="Primary DB override")
    ap.add_argument("--profile", default="", help="profile_pack.md override")
    ap.add_argument("--resume", default="", help="resume.json override")
    ap.add_argument("--app-state", default="", help="application_state.json override")
    ap.add_argument("--candidate-id", default="default", help="Stable candidate ID to store in the DB")
    ap.add_argument("--display-name", default="", help="Optional display name override")
    ap.add_argument("--email", default="", help="Optional candidate email")
    ap.add_argument("--locale", default="nb-NO", help="Candidate locale")
    ap.add_argument("--timezone", default="Europe/Oslo", help="Candidate timezone")
    args = ap.parse_args(list(argv) if argv is not None else None)

    runtime = resolve_profile_paths(
        args.runtime_profile,
        data_root_override=args.data_root,
        db_override=args.db,
        profile_override=args.profile,
        resume_override=args.resume,
        app_state_override=args.app_state,
    )
    if runtime.data_root is None:
        raise SystemExit("refresh-runtime-state requires an external runtime data root. Use --runtime-profile live_local or --data-root.")

    root = runtime.data_root
    archive_root = Path(args.archive_root).expanduser().resolve() if args.archive_root else root / "_archives"
    tag = args.tag.strip() or _default_tag()

    reset_summary = reset_runtime_state(
        data_root_path=root,
        archive_root_path=archive_root,
        tag=tag,
        restore_app_state=not args.no_restore_app_state,
    )
    bootstrap_summary = bootstrap_primary_db(
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

    print("=== JobPipe Runtime Refresh ===")
    print(f"Runtime profile: {runtime.name}")
    print(f"Data root:       {root}")
    print(f"Archive dir:     {reset_summary['archive_dir']}")
    print(f"Primary DB:      {bootstrap_summary['db_path']}")
    print(f"Candidate ID:    {bootstrap_summary['candidate_id']}")
    print(f"Profile path:    {bootstrap_summary['profile_path']}")
    print(f"Resume path:     {bootstrap_summary['resume_path']}")
    print(f"App state:       {bootstrap_summary['app_state_path']}")
    print(f"Events stored:   {bootstrap_summary['events_stored']}")
    print(f"Jobs tracked:    {bootstrap_summary['jobs_tracked']}")


if __name__ == "__main__":
    main()

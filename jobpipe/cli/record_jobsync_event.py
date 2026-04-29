"""Record one thin JobSync status event back into canonical JobPipe state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from jobpipe.model import JobSyncApplicationStatusEvent
from jobpipe.runtime import record_jobsync_application_status_event
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices

_DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Record one JobSync-style application status event into canonical JobPipe state."
    )
    parser.add_argument("job_id", help="Canonical job_id")
    parser.add_argument("event_type", help="Status event type")
    parser.add_argument(
        "--candidate-id",
        default=_DEFAULT_CANDIDATE_ID,
        help=f"Candidate ID for primary DB writes (default: {_DEFAULT_CANDIDATE_ID})",
    )
    parser.add_argument(
        "--event-at",
        default="",
        help="Optional event timestamp in ISO-8601. Defaults to current UTC time.",
    )
    parser.add_argument(
        "--source",
        default="jobsync",
        help="Bounded source label (default: jobsync)",
    )
    parser.add_argument("--notes", default="", help="Optional note text")
    parser.add_argument(
        "--metadata-json",
        default="",
        help="Optional metadata JSON object",
    )
    parser.add_argument(
        "--db",
        default="",
        help="Path to primary jobpipe.sqlite override",
    )
    parser.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="default", help="Runtime profile to resolve DB path from")
    parser.add_argument("--data-root", default="", help="Runtime data root override for live_local profile")
    args = parser.parse_args(argv)
    runtime = resolve_profile_paths(
        args.runtime_profile,
        data_root_override=args.data_root,
        db_override=args.db,
    )

    metadata = {}
    if args.metadata_json:
        metadata = json.loads(args.metadata_json)
        if not isinstance(metadata, dict):
            raise SystemExit("--metadata-json must decode to an object")

    event = JobSyncApplicationStatusEvent(
        candidate_id=args.candidate_id,
        job_id=args.job_id,
        event_type=args.event_type,
        event_at=args.event_at,
        source=args.source,
        notes=args.notes,
        metadata_json=metadata,
    )
    recorded = record_jobsync_application_status_event(runtime.primary_db_path, event)
    print(json.dumps(recorded.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Export thin JobSync case projections from canonical JobPipe state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable, List, Optional

from jobpipe.projections import build_jobsync_application_case_projections
from jobpipe.projections.dashboard import build_payload
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices

_DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"
_DEFAULT_DECISIONS = ("APPLY_STRONGLY", "APPLY", "REVIEW_HIGH", "REVIEW_LOW")


def _selected_rows(
    rows: Iterable[dict],
    *,
    job_ids: set[str],
    decisions: set[str],
) -> list[dict]:
    selected: list[dict] = []
    for row in rows:
        job_id = str(row.get("job_id") or "").strip()
        decision = str(row.get("final_decision") or "").strip()
        if job_ids and job_id not in job_ids:
            continue
        if decisions and decision not in decisions:
            continue
        selected.append(row)
    return selected


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Export thin JobSync application-case projections from canonical JobPipe state."
    )
    parser.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="default", help="Runtime profile to resolve canonical paths from")
    parser.add_argument("--data-root", default="", help="Runtime data root override for live_local profile")
    parser.add_argument(
        "--artifacts",
        "--out-runs",
        dest="artifacts_dir",
        default="",
        help="Artifact runs directory override",
    )
    parser.add_argument(
        "--db",
        default="",
        help="Path to primary jobpipe.sqlite override",
    )
    parser.add_argument(
        "--candidate-id",
        default=_DEFAULT_CANDIDATE_ID,
        help=f"Candidate ID for primary DB reads (default: {_DEFAULT_CANDIDATE_ID})",
    )
    parser.add_argument(
        "--job-id",
        action="append",
        default=[],
        help="Export only the specified job_id. May be passed multiple times.",
    )
    parser.add_argument(
        "--decision",
        action="append",
        default=list(_DEFAULT_DECISIONS),
        help=(
            "Include only these final decisions. Repeat to override/add. "
            f"Defaults: {', '.join(_DEFAULT_DECISIONS)}"
        ),
    )
    parser.add_argument(
        "--out",
        default="",
        help="Output JSON path override",
    )
    args = parser.parse_args(argv)

    runtime = resolve_profile_paths(
        args.runtime_profile,
        data_root_override=args.data_root,
        db_override=args.db,
        artifacts_override=args.artifacts_dir,
    )
    artifacts_dir = runtime.artifacts_root
    db_path = runtime.primary_db_path
    out_path = Path(args.out) if str(args.out).strip() else (runtime.exports_root / "jobsync_cases.json")

    payload = build_payload(
        artifacts_dir,
        primary_db_path_=db_path,
        candidate_id=args.candidate_id,
    )
    rows = _selected_rows(
        payload.get("jobs", []),
        job_ids={str(job_id).strip() for job_id in args.job_id if str(job_id).strip()},
        decisions={str(decision).strip() for decision in args.decision if str(decision).strip()},
    )
    cases = [case.model_dump(mode="json") for case in build_jobsync_application_case_projections(rows)]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "candidate_id": args.candidate_id,
                "generated_at": payload.get("generated_at"),
                "count": len(cases),
                "cases": cases,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"JobSync cases exported: {out_path}")
    print(f"  {len(cases)} case(s)")


if __name__ == "__main__":
    main()

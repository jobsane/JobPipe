"""Export one thin Reactive Resume tailoring plan from canonical JobPipe state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from jobpipe.core.candidate_data import load_candidate_profile_pack, load_candidate_resume_json
from jobpipe.projections import build_resume_import_projection, build_tailored_cv_plan, build_tailored_cv_projection
from jobpipe.projections.dashboard import build_payload
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices

_DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def _find_job_row(payload: dict, job_id: str) -> dict:
    for row in payload.get("jobs", []):
        if str(row.get("job_id") or "").strip() == job_id:
            return row
    raise SystemExit(f"job_id not found in canonical payload: {job_id}")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Export one thin Reactive Resume tailoring plan from canonical JobPipe state.")
    parser.add_argument("job_id", help="Canonical job_id to target")
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
    parser.add_argument("--profile", default="", help="Optional profile_pack.md override")
    parser.add_argument("--resume-json", default="", help="Optional resume.json override")
    parser.add_argument(
        "--out",
        default="",
        help="Optional output JSON path. Defaults to exports/reactive_resume_<job_id>.json",
    )
    args = parser.parse_args(argv)

    runtime = resolve_profile_paths(
        args.runtime_profile,
        data_root_override=args.data_root,
        db_override=args.db,
        artifacts_override=args.artifacts_dir,
        profile_override=args.profile,
        resume_override=args.resume_json,
    )
    db_path = runtime.primary_db_path
    payload = build_payload(runtime.artifacts_root, primary_db_path_=db_path, candidate_id=args.candidate_id)
    row = _find_job_row(payload, args.job_id)
    profile_pack = load_candidate_profile_pack(str(runtime.profile_pack_path), candidate_id=args.candidate_id, db_path=db_path)
    resume_json = load_candidate_resume_json(str(runtime.resume_json_path), candidate_id=args.candidate_id, db_path=db_path)

    import_projection = build_resume_import_projection(
        resume_json,
        candidate_id=args.candidate_id,
        resume_source_id="candidate_profile",
    )
    plan = build_tailored_cv_plan(
        row,
        profile_pack=profile_pack,
        resume_json=resume_json,
        candidate_id=args.candidate_id,
    )
    projection = build_tailored_cv_projection(
        row,
        plan,
        profile_pack=profile_pack,
        resume_json=resume_json,
        candidate_id=args.candidate_id,
    )

    out_path = Path(args.out) if args.out else (runtime.exports_root / f"reactive_resume_{args.job_id}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "candidate_id": args.candidate_id,
                "job_id": args.job_id,
                "resume_import_projection": import_projection.model_dump(mode="json"),
                "tailored_cv_plan": plan.model_dump(mode="json"),
                "tailored_cv_projection": projection.model_dump(mode="json"),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Reactive Resume plan exported: {out_path}")


if __name__ == "__main__":
    main()

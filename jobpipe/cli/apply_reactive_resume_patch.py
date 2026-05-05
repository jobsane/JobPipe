"""Apply a tailored CV plan to the candidate's Reactive Resume JSON and export an importable patched document."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from jobpipe.core.candidate_data import load_candidate_profile_pack, load_candidate_resume_json
from jobpipe.projections import build_tailored_cv_plan, build_tailored_cv_projection
from jobpipe.projections.rr_patch import build_rr_patch
from jobpipe.projections.dashboard import build_payload
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices

_DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def _find_job_row(payload: dict, job_id: str) -> dict:
    for row in payload.get("jobs", []):
        if str(row.get("job_id") or "").strip() == job_id:
            return row
    raise SystemExit(f"job_id not found in canonical payload: {job_id}")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Apply a tailored CV plan to the candidate's Reactive Resume JSON and export an importable patch."
    )
    parser.add_argument("job_id", help="Canonical job_id to target")
    parser.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="default")
    parser.add_argument("--data-root", default="", help="Runtime data root override for live_local profile")
    parser.add_argument("--artifacts", "--out-runs", dest="artifacts_dir", default="")
    parser.add_argument("--db", default="")
    parser.add_argument("--candidate-id", default=_DEFAULT_CANDIDATE_ID)
    parser.add_argument("--profile", default="", help="Optional profile_pack.md override")
    parser.add_argument("--resume-json", default="", help="Optional resume.json override (must be RR format)")
    parser.add_argument(
        "--out",
        default="",
        help="Optional output JSON path. Defaults to exports/reactive_resume_patched_<job_id>.json",
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

    patched = build_rr_patch(resume_json, plan, projection)

    out_path = Path(args.out) if args.out else (runtime.exports_root / f"reactive_resume_patched_{args.job_id}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(patched, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Tailored CV plan applied.")
    print(f"  Job:         {args.job_id}")
    print(f"  Strategy:    {plan.variant_strategy}")
    print(f"  Evidence:    {len(plan.selected_evidence_unit_ids)} unit(s) selected")
    print(f"  Sections:    {' → '.join(plan.selected_section_order)}")
    print(f"  Suppressed:  {len(plan.suppressed_items)} item(s)")
    print(f"  Output:      {out_path}")
    print()
    print("Import this file into Reactive Resume via:")
    print("  Settings → Import Resume → JSON Resume / Reactive Resume")


if __name__ == "__main__":
    main()

"""Prepare a complete job application: tailored CV patch + cover letter in sequence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from jobpipe.authoring.cover_letter_generator import generate_cover_letter
from jobpipe.authoring.validation import validate_authoring_context
from jobpipe.cli.generate_cover_letter import build_authoring_context, _find_job_row
from jobpipe.core.candidate_data import load_candidate_profile_pack, load_candidate_resume_json
from jobpipe.core.io import load_env_file
from jobpipe.projections import build_tailored_cv_plan, build_tailored_cv_projection
from jobpipe.projections.dashboard import build_payload
from jobpipe.projections.rr_patch import build_rr_patch
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices

_DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def _build_artifact_plan(plan, projection) -> dict:
    """Extract CV plan/projection fields the cover letter needs."""
    return {
        "cv_headline": projection.headline,
        "cv_summary": projection.summary_text or plan.summary_brief,
        "cv_selected_bullets": projection.selected_bullets,
        "cv_suppressed_items": plan.suppressed_items,
        "cv_claim_targets": plan.claim_targets,
        "cv_rewrite_constraints": plan.rewrite_constraints,
        "cv_section_order": plan.selected_section_order,
        "cv_variant_strategy": plan.variant_strategy,
    }


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a complete job application: build the tailored CV patch first, "
            "then generate a cover letter that addresses gaps and is consistent with the CV."
        )
    )
    parser.add_argument("job_id", help="Canonical job_id to prepare application for")
    parser.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="default")
    parser.add_argument("--data-root", default="", help="Runtime data root override for live_local profile")
    parser.add_argument("--artifacts", "--out-runs", dest="artifacts_dir", default="")
    parser.add_argument("--db", default="")
    parser.add_argument("--candidate-id", default=_DEFAULT_CANDIDATE_ID)
    parser.add_argument("--profile", default="", help="Optional profile_pack.md override")
    parser.add_argument("--resume-json", default="", help="Optional resume.json override (must be RR format)")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model to use for cover letter generation")
    parser.add_argument("--out-dir", default="", help="Output directory override (default: exports/)")
    args = parser.parse_args(argv)

    load_env_file(Path(".env"))

    runtime = resolve_profile_paths(
        args.runtime_profile,
        data_root_override=args.data_root,
        db_override=args.db,
        artifacts_override=args.artifacts_dir,
        profile_override=args.profile,
        resume_override=args.resume_json,
    )
    out_dir = Path(args.out_dir) if args.out_dir else runtime.exports_root
    out_dir.mkdir(parents=True, exist_ok=True)

    db_path = runtime.primary_db_path
    payload = build_payload(runtime.artifacts_root, primary_db_path_=db_path, candidate_id=args.candidate_id)
    row = _find_job_row(payload, args.job_id)
    profile_pack = load_candidate_profile_pack(str(runtime.profile_pack_path), candidate_id=args.candidate_id, db_path=db_path)
    resume_json = load_candidate_resume_json(str(runtime.resume_json_path), candidate_id=args.candidate_id, db_path=db_path)

    job_id = args.job_id
    title = str(row.get("title") or job_id)
    employer = str(row.get("employer_name") or "")
    decision = str(row.get("final_decision") or "")

    print()
    print(f"=== prepare-application: {title} ===")
    print(f"  Employer:  {employer}")
    print(f"  Decision:  {decision}")
    print()

    # Step 1: build tailored CV
    print("[1/3] Building tailored CV plan ...")
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
    print(f"  Strategy:   {plan.variant_strategy}")
    print(f"  Evidence:   {len(plan.selected_evidence_unit_ids)} unit(s) selected")
    print(f"  Sections:   {' > '.join(plan.selected_section_order)}")
    print(f"  Suppressed: {len(plan.suppressed_items)} item(s)")

    # Step 2: patch RR JSON and save
    print()
    print("[2/3] Applying CV patch ...")
    patched = build_rr_patch(resume_json, plan, projection)
    cv_path = out_dir / f"reactive_resume_patched_{job_id}.json"
    cv_path.write_text(json.dumps(patched, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  CV output:  {cv_path}")

    # Step 3: generate cover letter with CV context
    print()
    print("[3/3] Generating cover letter ...")
    artifact_plan = _build_artifact_plan(plan, projection)
    ctx = build_authoring_context(
        row,
        profile_pack,
        resume_json,
        args.candidate_id,
        artifact_plan=artifact_plan,
    )
    validation = validate_authoring_context(ctx)
    if not validation.passed:
        for failure in validation.failures:
            print(f"  FAIL: {failure}")
        raise SystemExit(f"Authoring context validation failed ({len(validation.failures)} failure(s)). Aborting.")
    if validation.warnings:
        for warning in validation.warnings:
            print(f"  WARN: {warning}")

    cover_letter = generate_cover_letter(ctx, model=args.model)
    if not cover_letter:
        raise SystemExit("Cover letter generation returned empty output. Check your OPENAI_API_KEY.")

    letter_path = out_dir / f"cover_letter_{job_id}.md"
    letter_path.write_text(cover_letter, encoding="utf-8")
    print(f"  Letter output: {letter_path}")
    print(f"  Length:        {len(cover_letter)} chars")

    print()
    print("=== Done ===")
    print(f"  CV patch:     {cv_path}")
    print(f"  Cover letter: {letter_path}")
    print()
    print("Import the CV patch into Reactive Resume via:")
    print("  Settings > Import Resume > JSON Resume / Reactive Resume")


if __name__ == "__main__":
    main()

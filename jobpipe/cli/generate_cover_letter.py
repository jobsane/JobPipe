"""Generate a tailored Norwegian cover letter for a job, from the dashboard payload."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, List, Mapping, Optional

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.cover_letter_generator import generate_cover_letter
from jobpipe.authoring.validation import validate_authoring_context
from jobpipe.core.candidate_data import load_candidate_profile_pack, load_candidate_resume_json
from jobpipe.core.io import load_env_file
from jobpipe.core.profile_pack import parse_profile_pack
from jobpipe.core.rr_compat import normalize_rr_to_jsonresume
from jobpipe.decision import build_candidate_evidence_context, build_candidate_narrative_context, build_decision_context
from jobpipe.projections.dashboard import build_payload
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices

_DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def _find_job_row(payload: dict, job_id: str) -> dict:
    for row in payload.get("jobs", []):
        if str(row.get("job_id") or "").strip() == job_id:
            return row
    raise SystemExit(f"job_id not found in canonical payload: {job_id}")


def _enum_val(v: object) -> str:
    return v.value if hasattr(v, "value") else str(v)


def build_authoring_context(
    row: Mapping[str, Any],
    profile_pack: str,
    resume_json: Mapping[str, Any],
    candidate_id: str,
    *,
    artifact_plan: dict | None = None,
) -> AuthoringCaseContext:
    """Build an AuthoringCaseContext from a dashboard payload row.

    Pass artifact_plan with CV plan/projection data when calling from
    prepare-application so the cover letter can reference the tailored CV.
    """
    resume_json = normalize_rr_to_jsonresume(dict(resume_json))
    candidate_profile = parse_profile_pack(profile_pack)
    decision_ctx = build_decision_context(row, candidate_profile=candidate_profile)
    focus_terms = list(row.get("cv_focus") or [])
    evidence_ctx = build_candidate_evidence_context(
        row,
        resume_json,
        candidate_id=candidate_id,
        focus_terms=focus_terms,
        limit=8,
    )
    narrative_ctx = build_candidate_narrative_context(
        row,
        profile_pack,
        evidence_ctx.candidate_evidence_units,
        evidence_ctx.selected_evidence_units,
        candidate_id=candidate_id,
        decision_table=decision_ctx.decision_table,
    )

    dt = decision_ctx.decision_table
    job_summary = {
        "title": str(row.get("title") or "").strip(),
        "employer_name": str(row.get("employer_name") or "").strip(),
        "sector": str(row.get("sector") or "").strip(),
        "application_due": row.get("applicationDue"),
        "source_url": str(row.get("source_url") or row.get("application_url") or "").strip(),
        "role_summary": str(row.get("triage_explanation") or row.get("recommendation_reason") or "").strip(),
    }
    decision_brief = {
        "final_decision": str(row.get("final_decision") or "").strip(),
        "recommendation_reason": str(row.get("recommendation_reason") or "").strip(),
        "cv_focus": row.get("cv_focus") or [],
        "act_now": _enum_val(dt.act_now),
        "can_do_score": dt.can_do.score,
        "can_get_score": dt.can_get.score,
        "should_want_score": dt.should_want.score,
        "can_explain_score": dt.can_explain.score,
    }
    selected_evidence = [eu.model_dump() for eu in evidence_ctx.selected_evidence_units]

    np_ = narrative_ctx.narrative_profile
    na = narrative_ctx.job_narrative_assessment
    np_dict = np_.model_dump()
    narrative_brief = {
        "core_identity": np_dict.get("core_identity", ""),
        "future_direction": np_dict.get("future_direction", ""),
        "motivation_themes": np_dict.get("motivation_themes", []),
        "pivot_thesis": np_dict.get("pivot_thesis", ""),
        "direction_fit_score": na.direction_fit_score,
        "motivation_fit_score": na.motivation_fit_score,
        "story_strength_score": na.story_strength_score,
        "motivation_brief": na.motivation_brief,
    }

    return AuthoringCaseContext(
        candidate_id=candidate_id,
        job_id=str(row.get("job_id") or "").strip(),
        evaluation_id=str(row.get("run_id") or "").strip() or None,
        job_summary=job_summary,
        decision_brief=decision_brief,
        selected_evidence=selected_evidence,
        narrative_brief=narrative_brief,
        artifact_plan=artifact_plan,
    )


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate a tailored Norwegian cover letter for a job application."
    )
    parser.add_argument("job_id", help="Canonical job_id to generate a cover letter for")
    parser.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="default")
    parser.add_argument("--data-root", default="", help="Runtime data root override for live_local profile")
    parser.add_argument("--artifacts", "--out-runs", dest="artifacts_dir", default="")
    parser.add_argument("--db", default="")
    parser.add_argument("--candidate-id", default=_DEFAULT_CANDIDATE_ID)
    parser.add_argument("--profile", default="", help="Optional profile_pack.md override")
    parser.add_argument("--resume-json", default="", help="Optional resume.json override (must be RR format)")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model to use for generation")
    parser.add_argument(
        "--out",
        default="",
        help="Optional output path. Defaults to exports/cover_letter_<job_id>.md",
    )
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
    db_path = runtime.primary_db_path
    payload = build_payload(runtime.artifacts_root, primary_db_path_=db_path, candidate_id=args.candidate_id)
    row = _find_job_row(payload, args.job_id)
    profile_pack = load_candidate_profile_pack(str(runtime.profile_pack_path), candidate_id=args.candidate_id, db_path=db_path)
    resume_json = load_candidate_resume_json(str(runtime.resume_json_path), candidate_id=args.candidate_id, db_path=db_path)

    ctx = build_authoring_context(row, profile_pack, resume_json, args.candidate_id)
    validation = validate_authoring_context(ctx)
    if not validation.passed:
        for failure in validation.failures:
            print(f"  FAIL: {failure}")
        raise SystemExit(f"Authoring context validation failed ({len(validation.failures)} failure(s)). Aborting.")
    if validation.warnings:
        for warning in validation.warnings:
            print(f"  WARN: {warning}")

    print(f"Generating cover letter for {args.job_id} ...")
    cover_letter = generate_cover_letter(ctx, model=args.model)

    if not cover_letter:
        raise SystemExit("Cover letter generation returned empty output. Check your OPENAI_API_KEY.")

    out_path = Path(args.out) if args.out else (runtime.exports_root / f"cover_letter_{args.job_id}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(cover_letter, encoding="utf-8")

    print(f"Cover letter generated.")
    print(f"  Job:       {args.job_id}")
    print(f"  Title:     {row.get('title', '')}")
    print(f"  Employer:  {row.get('employer_name', '')}")
    print(f"  Evidence:  {len(ctx.selected_evidence)} unit(s)")
    print(f"  Output:    {out_path}")
    print(f"  Length:    {len(cover_letter)} chars")


if __name__ == "__main__":
    main()

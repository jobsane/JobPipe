"""Thin Reactive Resume plan/projection builders from canonical JobPipe state."""

from __future__ import annotations

from typing import Any, Mapping

from jobpipe.core.profile_pack import parse_profile_pack
from jobpipe.decision import build_candidate_evidence_context, build_candidate_narrative_context, build_decision_context
from jobpipe.model import (
    ReactiveResumeImportProjection,
    ReactiveResumeTailoredCVPlan,
    ReactiveResumeTailoredCVProjection,
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def build_resume_import_projection(
    resume_json: Mapping[str, Any],
    *,
    candidate_id: str,
    resume_source_id: str = "default",
) -> ReactiveResumeImportProjection:
    from jobpipe.core.rr_compat import normalize_rr_to_jsonresume
    resume_json = normalize_rr_to_jsonresume(dict(resume_json))
    return ReactiveResumeImportProjection(
        candidate_id=candidate_id,
        resume_source_id=resume_source_id,
        basics=dict(resume_json.get("basics") or {}),
        work=list(resume_json.get("work") or []),
        projects=list(resume_json.get("projects") or []),
        education=list(resume_json.get("education") or []),
        skills=list(resume_json.get("skills") or []),
        languages=list(resume_json.get("languages") or []),
        metadata={
            "work_count": len(list(resume_json.get("work") or [])),
            "project_count": len(list(resume_json.get("projects") or [])),
            "education_count": len(list(resume_json.get("education") or [])),
        },
    )


def _variant_strategy(row: Mapping[str, Any]) -> str:
    decision = _clean(row.get("final_decision"))
    if decision == "APPLY_STRONGLY":
        return "aggressive"
    if decision == "APPLY":
        return "balanced"
    return "conservative"


def _section_order(selected_source_types: set[str], resume_json: Mapping[str, Any]) -> list[str]:
    order = ["summary", "experience"]
    if "project_case" in selected_source_types and resume_json.get("projects"):
        order.append("projects")
    if resume_json.get("skills"):
        order.append("skills")
    if resume_json.get("education"):
        order.append("education")
    return order


def _suppressed_items(
    selected_refs: set[str],
    selected_ids: set[str],
    resume_json: Mapping[str, Any],
    evidence_context,
) -> list[str]:
    suppressed: list[str] = []

    for work_entry in resume_json.get("work", []) or []:
        company = _clean(work_entry.get("name") or work_entry.get("company"))
        position = _clean(work_entry.get("position"))
        highlights = list(work_entry.get("highlights") or [])
        for index, _ in enumerate(highlights):
            source_ref = f"work:{company or 'unknown'}:{position or 'unknown'}:{index}"
            if source_ref not in selected_refs:
                suppressed.append(source_ref)

    for unit in evidence_context.candidate_evidence_units:
        if unit.evidence_unit_id not in selected_ids and unit.source_type in {"project_case", "education"}:
            suppressed.append(unit.source_ref)
    return suppressed[:12]


def build_tailored_cv_plan(
    row: Mapping[str, Any],
    *,
    profile_pack: str,
    resume_json: Mapping[str, Any],
    candidate_id: str,
) -> ReactiveResumeTailoredCVPlan:
    from jobpipe.core.rr_compat import normalize_rr_to_jsonresume
    resume_json = normalize_rr_to_jsonresume(dict(resume_json))
    candidate_profile = parse_profile_pack(profile_pack)
    decision_context = build_decision_context(row, candidate_profile=candidate_profile)
    focus_terms = list(row.get("cv_focus") or [])
    evidence_context = build_candidate_evidence_context(
        row,
        resume_json,
        candidate_id=candidate_id,
        focus_terms=focus_terms,
        limit=6,
    )
    narrative_context = build_candidate_narrative_context(
        row,
        profile_pack,
        evidence_context.candidate_evidence_units,
        evidence_context.selected_evidence_units,
        candidate_id=candidate_id,
        decision_table=decision_context.decision_table,
    )

    selected_ids = [selection.evidence_unit_id for selection in evidence_context.selected_evidence_units]
    selected_refs = {selection.source_ref for selection in evidence_context.selected_evidence_units}
    source_types = {selection.source_type for selection in evidence_context.selected_evidence_units}
    claim_targets = [claim.claim_text for claim in decision_context.job_claims[:5]]
    rewrite_constraints = sorted(
        {
            "Do not invent experience or stronger seniority than the evidence supports.",
            "Prefer candidate-approved wording and bounded rewriting over paraphrasing everything.",
            *narrative_context.narrative_profile.story_boundaries[:2],
            *narrative_context.narrative_profile.tone_rules[:2],
        }
    )
    summary_brief = (
        narrative_context.job_narrative_assessment.motivation_brief
        or decision_context.decision_table.table_reason
        or _clean(row.get("recommendation_reason"))
    )

    return ReactiveResumeTailoredCVPlan(
        candidate_id=candidate_id,
        job_id=_clean(row.get("job_id")),
        evaluation_id=_clean(row.get("run_id")),
        variant_strategy=_variant_strategy(row),
        selected_evidence_unit_ids=selected_ids,
        selected_section_order=_section_order(source_types, resume_json),
        suppressed_items=_suppressed_items(selected_refs, set(selected_ids), resume_json, evidence_context),
        summary_brief=summary_brief,
        rewrite_constraints=rewrite_constraints[:6],
        claim_targets=claim_targets,
        selection_mitigation_targets=decision_context.selection_assessment.mitigation_moves[:4],
    )


def build_tailored_cv_projection(
    row: Mapping[str, Any],
    plan: ReactiveResumeTailoredCVPlan,
    *,
    profile_pack: str,
    resume_json: Mapping[str, Any],
    candidate_id: str,
) -> ReactiveResumeTailoredCVProjection:
    from jobpipe.core.rr_compat import normalize_rr_to_jsonresume
    resume_json = normalize_rr_to_jsonresume(dict(resume_json))
    candidate_profile = parse_profile_pack(profile_pack)
    evidence_context = build_candidate_evidence_context(
        row,
        resume_json,
        candidate_id=candidate_id,
        focus_terms=list(row.get("cv_focus") or []),
        limit=6,
    )
    decision_context = build_decision_context(row, candidate_profile=candidate_profile)
    narrative_context = build_candidate_narrative_context(
        row,
        profile_pack,
        evidence_context.candidate_evidence_units,
        evidence_context.selected_evidence_units,
        candidate_id=candidate_id,
        decision_table=decision_context.decision_table,
    )

    return ReactiveResumeTailoredCVProjection(
        headline=_clean(row.get("title")) or "Tailored CV",
        summary_text=plan.summary_brief or narrative_context.narrative_profile.narrative_summary,
        section_plan=[{"section": section, "mode": "selected"} for section in plan.selected_section_order],
        selected_bullets=[selection.canonical_text for selection in evidence_context.selected_evidence_units],
        provenance={
            "job_id": plan.job_id,
            "evaluation_id": plan.evaluation_id,
            "selected_evidence_unit_ids": plan.selected_evidence_unit_ids,
            "claim_targets": plan.claim_targets,
        },
        render_target="reactive_resume_json",
    )


__all__ = [
    "build_resume_import_projection",
    "build_tailored_cv_plan",
    "build_tailored_cv_projection",
]

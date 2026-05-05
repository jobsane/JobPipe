"""Apply a tailored CV plan to the original Reactive Resume JSON, producing an importable patched document."""
from __future__ import annotations

import copy
import re
from typing import Any

from jobpipe.core.rr_compat import normalize_rr_to_jsonresume
from jobpipe.model import ReactiveResumeTailoredCVPlan, ReactiveResumeTailoredCVProjection

# Maps plan section names → RR sections keys
_PLAN_TO_RR_SECTION: dict[str, str] = {
    "experience": "experience",
    "projects": "projects",
    "skills": "skills",
    "education": "education",
    "languages": "languages",
}


def build_rr_patch(
    resume_rr_json: dict[str, Any],
    plan: ReactiveResumeTailoredCVPlan,
    projection: ReactiveResumeTailoredCVProjection,
) -> dict[str, Any]:
    """
    Apply the tailored CV plan to the original RR JSON.
    Returns a modified RR document ready for import into Reactive Resume.
    Input must be in Reactive Resume format (has 'sections' key).
    """
    result = copy.deepcopy(resume_rr_json)
    normalized = normalize_rr_to_jsonresume(dict(resume_rr_json))

    _apply_headline(result, projection)
    _apply_summary(result, projection, plan)
    _apply_section_visibility(result, plan)
    _apply_experience_suppression(result, normalized, plan)

    return result


def _apply_headline(result: dict[str, Any], projection: ReactiveResumeTailoredCVProjection) -> None:
    if not projection.headline:
        return
    basics = result.get("basics")
    if isinstance(basics, dict):
        basics["headline"] = projection.headline


def _apply_summary(
    result: dict[str, Any],
    projection: ReactiveResumeTailoredCVProjection,
    plan: ReactiveResumeTailoredCVPlan,
) -> None:
    text = projection.summary_text or plan.summary_brief
    if not text:
        return
    # RR summary is a top-level key, not under sections
    summary = result.get("summary")
    if isinstance(summary, dict):
        # Wrap in paragraph tag if not already HTML
        content = text if text.strip().startswith("<") else f"<p>{text}</p>"
        summary["content"] = content
        summary["hidden"] = False


def _apply_section_visibility(result: dict[str, Any], plan: ReactiveResumeTailoredCVPlan) -> None:
    selected = set(plan.selected_section_order)
    sections = result.get("sections")
    if not isinstance(sections, dict):
        return
    for plan_key, rr_key in _PLAN_TO_RR_SECTION.items():
        if rr_key not in sections:
            continue
        section = sections[rr_key]
        if not isinstance(section, dict):
            continue
        section["hidden"] = plan_key not in selected


def _apply_experience_suppression(
    result: dict[str, Any],
    normalized: dict[str, Any],
    plan: ReactiveResumeTailoredCVPlan,
) -> None:
    suppressed_refs = set(plan.suppressed_items)
    sections = result.get("sections")
    if not isinstance(sections, dict):
        return
    experience = sections.get("experience")
    if not isinstance(experience, dict):
        return
    items = experience.get("items") or []
    work_entries = normalized.get("work") or []

    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("hidden"):
            continue  # already hidden — leave it alone
        company = str(item.get("company") or "").strip()
        position = str(item.get("position") or "").strip()
        matching = _find_work_entry(work_entries, company, position)
        if matching is None:
            continue
        highlights = matching.get("highlights") or []
        if not highlights:
            continue
        all_suppressed = all(
            f"work:{company or 'unknown'}:{position or 'unknown'}:{idx}" in suppressed_refs
            for idx in range(len(highlights))
        )
        if all_suppressed:
            item["hidden"] = True


def _find_work_entry(
    work_entries: list[dict[str, Any]],
    company: str,
    position: str,
) -> dict[str, Any] | None:
    for entry in work_entries:
        if (
            str(entry.get("company") or entry.get("name") or "").strip() == company
            and str(entry.get("position") or "").strip() == position
        ):
            return entry
    return None

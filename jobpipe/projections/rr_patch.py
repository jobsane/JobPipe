"""Apply a tailored CV plan to the original Reactive Resume JSON, producing an importable patched document."""
from __future__ import annotations

import copy
import re
from typing import Any


def _filter_li_items(html: str, keep_indices: set[int]) -> str:
    """Return html with only the <li> elements at the given indices kept.

    RR stores bullets as <li><p>text</p></li> inside the description field.
    We rebuild the outer wrapper (everything before the first <li> and after
    the last </li>) with only the selected bullets.
    """
    # Split into: prefix (everything up to first <li>), li blocks, suffix
    li_pattern = re.compile(r"(<li\b[^>]*>.*?</li>)", re.DOTALL | re.IGNORECASE)
    parts = li_pattern.split(html)
    # parts alternates: [prefix, li_0, between, li_1, between, ..., suffix]
    li_blocks = [p for i, p in enumerate(parts) if i % 2 == 1]
    non_li_parts = [p for i, p in enumerate(parts) if i % 2 == 0]

    if not li_blocks:
        return html  # no bullets — return as-is

    kept = [li_blocks[i] for i in sorted(keep_indices) if i < len(li_blocks)]
    if not kept:
        # All bullets removed — return just the summary paragraph (prefix before <ul>)
        prefix = re.split(r"<ul\b", html, maxsplit=1, flags=re.IGNORECASE)[0]
        return prefix.strip() or ""

    # Rebuild: prefix + <ul> + kept bullets + </ul>
    prefix = non_li_parts[0] if non_li_parts else ""
    # Ensure we have a <ul> wrapper
    has_ul = bool(re.search(r"<ul\b", prefix, re.IGNORECASE))
    if has_ul:
        return prefix + "".join(kept) + "</ul>"
    return prefix + "<ul>" + "".join(kept) + "</ul>"

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
    """Filter individual bullets within each work entry to only selected ones.

    For each visible experience item:
    - count how many <li> bullets it has
    - determine which bullet indices are NOT suppressed (i.e. selected)
    - rewrite item["description"] keeping only selected <li> elements
    - if all bullets are suppressed, hide the entire entry
    """
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
            continue  # no bullets to filter

        c = company or "unknown"
        p = position or "unknown"
        keep_indices: set[int] = {
            idx for idx in range(len(highlights))
            if f"work:{c}:{p}:{idx}" not in suppressed_refs
        }

        if not keep_indices:
            item["hidden"] = True
            continue

        # Surgically rewrite description HTML to only include selected bullets
        description = str(item.get("description") or "")
        if description:
            item["description"] = _filter_li_items(description, keep_indices)


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

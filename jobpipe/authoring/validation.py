"""Deterministic validation rules for AuthoringCaseContext.

All rules are pure, offline, and deterministic: no LLM calls, no network
access, no randomness, no time dependence.

Findings are encoded as prefixed strings in DocumentValidationResult.failures
(errors) and .warnings (warnings/info). The DocumentValidationResult schema is
not modified.

Scoring: score = clamp(1.0 - (errors * 0.2 + warnings * 0.05), 0.0, 1.0)
"""

from __future__ import annotations

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.output_models import DocumentValidationResult


_DECISION_BRIEF_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "final_decision",
        "recommendation_reason",
        "cv_focus",
        "act_now",
        "can_do_score",
        "can_get_score",
        "should_want_score",
        "can_explain_score",
    }
)

_NARRATIVE_BRIEF_EXPECTED_KEYS: frozenset[str] = frozenset(
    {
        "core_identity",
        "future_direction",
        "motivation_themes",
        "pivot_thesis",
        "direction_fit_score",
        "motivation_fit_score",
        "story_strength_score",
        "motivation_brief",
    }
)


def _rule_required_field_absent(ctx: AuthoringCaseContext) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    if not ctx.candidate_id or not ctx.candidate_id.strip():
        failures.append("[required_field_absent] candidate_id is absent or blank")
    if not ctx.job_id or not ctx.job_id.strip():
        failures.append("[required_field_absent] job_id is absent or blank")
    if not ctx.job_summary:
        failures.append("[required_field_absent] job_summary is empty")
    if not ctx.decision_brief:
        failures.append("[required_field_absent] decision_brief is empty")
    if ctx.selected_evidence is None:
        failures.append("[required_field_absent] selected_evidence is None")
    return failures, []


def _rule_missing_decision_context(ctx: AuthoringCaseContext) -> tuple[list[str], list[str]]:
    if not ctx.decision_brief:
        return [], []

    failures = [
        f"[missing_decision_context] decision_brief is missing required key: {key!r}"
        for key in sorted(_DECISION_BRIEF_REQUIRED_KEYS)
        if key not in ctx.decision_brief
    ]
    return failures, []


def _rule_empty_evidence_units(ctx: AuthoringCaseContext) -> tuple[list[str], list[str]]:
    if not ctx.selected_evidence:
        return (
            [
                "[empty_evidence_units] selected_evidence is empty - "
                "no evidence units selected for this job"
            ],
            [],
        )
    return [], []


def _rule_narrative_empty(ctx: AuthoringCaseContext) -> tuple[list[str], list[str]]:
    if ctx.narrative_brief is None:
        return [], []

    has_content = any(ctx.narrative_brief.get(key) for key in _NARRATIVE_BRIEF_EXPECTED_KEYS)
    if not has_content:
        return [], [
            "[narrative_empty] narrative_brief is present but has no content "
            "in any expected key"
        ]
    return [], []


def _selected_evidence_ids(ctx: AuthoringCaseContext) -> set[str]:
    ids: set[str] = set()
    for unit in ctx.selected_evidence or []:
        value = unit.get("evidence_unit_id")
        if isinstance(value, str) and value:
            ids.add(value)
    return ids


def _narrative_evidence_refs(ctx: AuthoringCaseContext) -> set[str]:
    if ctx.narrative_brief is None:
        return set()

    refs: set[str] = set()
    for key in ("evidence_unit_ids", "evidence_refs", "selected_evidence_ids"):
        value = ctx.narrative_brief.get(key)
        if isinstance(value, str) and value:
            refs.add(value)
        elif isinstance(value, list):
            refs.update(item for item in value if isinstance(item, str) and item)
    return refs


def _rule_resume_job_mismatch(ctx: AuthoringCaseContext) -> tuple[list[str], list[str]]:
    failures: list[str] = []

    referenced_ids = _narrative_evidence_refs(ctx)
    missing_ids = sorted(referenced_ids - _selected_evidence_ids(ctx))
    for evidence_id in missing_ids:
        failures.append(
            "[resume_job_mismatch] narrative_brief references evidence_unit_id "
            f"{evidence_id!r} with no counterpart in selected_evidence"
        )

    if (
        ctx.narrative_brief is not None
        and ctx.narrative_brief.get("story_strength_score", 0)
        and not ctx.selected_evidence
    ):
        failures.append(
            "[resume_job_mismatch] narrative_brief claims story evidence "
            "(story_strength_score > 0) but selected_evidence is empty"
        )

    return failures, []


def _compute_score(n_errors: int, n_warnings: int) -> float:
    raw = 1.0 - (n_errors * 0.2 + n_warnings * 0.05)
    return max(0.0, min(1.0, raw))


_RULES = [
    _rule_required_field_absent,
    _rule_missing_decision_context,
    _rule_empty_evidence_units,
    _rule_narrative_empty,
    _rule_resume_job_mismatch,
]


def validate_authoring_context(ctx: AuthoringCaseContext) -> DocumentValidationResult:
    """Run all deterministic validation rules against ctx."""
    all_failures: list[str] = []
    all_warnings: list[str] = []

    for rule in _RULES:
        failures, warnings = rule(ctx)
        all_failures.extend(failures)
        all_warnings.extend(warnings)

    return DocumentValidationResult(
        passed=all_failures == [],
        score=_compute_score(len(all_failures), len(all_warnings)),
        failures=all_failures,
        warnings=all_warnings,
    )

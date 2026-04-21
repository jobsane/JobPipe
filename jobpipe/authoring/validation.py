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

# Required keys per field - verified against builder.py.
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

_JOB_SUMMARY_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "title",
        "employer_name",
        "sector",
        "application_due",
        "source_url",
        "role_summary",
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


# ---------------------------------------------------------------------------
# Rule functions - each returns (failures: list[str], warnings: list[str])
# ---------------------------------------------------------------------------


def _rule_required_field_absent(ctx: AuthoringCaseContext) -> tuple[list[str], list[str]]:
    """required_field_absent: mandatory top-level fields must be non-empty."""
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
    """missing_decision_context: decision_brief must contain all required keys."""
    failures: list[str] = []
    if not ctx.decision_brief:
        # already caught by required_field_absent; skip to avoid duplicate
        return [], []
    for key in sorted(_DECISION_BRIEF_REQUIRED_KEYS):
        if key not in ctx.decision_brief:
            failures.append(
                f"[missing_decision_context] decision_brief is missing required key: {key!r}"
            )
    return failures, []


def _rule_empty_evidence_units(ctx: AuthoringCaseContext) -> tuple[list[str], list[str]]:
    """empty_evidence_units: selected_evidence must contain at least one entry."""
    if not ctx.selected_evidence:
        return (
            ["[empty_evidence_units] selected_evidence is empty - no evidence units selected for this job"],
            [],
        )
    return [], []


def _rule_narrative_empty(ctx: AuthoringCaseContext) -> tuple[list[str], list[str]]:
    """narrative_empty: if narrative_brief is provided, it must have content.

    Severity: warning (not error) - narrative context is optional for the MVP.
    """
    if ctx.narrative_brief is None:
        return [], []
    # Check whether any expected key has a non-empty value.
    has_content = any(
        ctx.narrative_brief.get(k)
        for k in _NARRATIVE_BRIEF_EXPECTED_KEYS
    )
    if not has_content:
        return [], [
            "[narrative_empty] narrative_brief is present but has no content "
            "in any expected key"
        ]
    return [], []


def _rule_resume_job_mismatch(ctx: AuthoringCaseContext) -> tuple[list[str], list[str]]:
    """resume_job_mismatch: evidence referenced by narrative must be selected.

    The narrative_brief dict does not directly carry evidence_unit_ids, so this
    rule checks the structural relationship: if narrative_brief has
    'story_strength_score' > 0 but selected_evidence is empty, the narrative
    is unsupported. It also confirms candidate_id consistency (non-blank),
    which is the primary cross-field identity check available from the context.
    """
    failures: list[str] = []

    # Candidate identity consistency: candidate_id must be non-blank.
    if ctx.candidate_id is not None and not ctx.candidate_id.strip():
        failures.append(
            "[resume_job_mismatch] candidate_id is blank - cannot establish "
            "evidence-candidate identity"
        )

    # Narrative references evidence but selected_evidence is empty.
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


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _compute_score(n_errors: int, n_warnings: int) -> float:
    raw = 1.0 - (n_errors * 0.2 + n_warnings * 0.05)
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


_RULES = [
    _rule_required_field_absent,
    _rule_missing_decision_context,
    _rule_empty_evidence_units,
    _rule_narrative_empty,
    _rule_resume_job_mismatch,
]


def validate_authoring_context(ctx: AuthoringCaseContext) -> DocumentValidationResult:
    """Run all deterministic validation rules against ctx.

    Returns a DocumentValidationResult. The result is:
    - passed=True iff failures is empty (warnings alone do not fail)
    - score computed as clamp(1.0 - errors*0.2 - warnings*0.05, 0.0, 1.0)
    - failures lists all error-severity rule findings (prefixed [rule_id])
    - warnings lists all warning-severity rule findings (prefixed [rule_id])

    All rules are pure and offline. Safe to call without side effects.
    """
    all_failures: list[str] = []
    all_warnings: list[str] = []

    for rule in _RULES:
        rule_failures, rule_warnings = rule(ctx)
        all_failures.extend(rule_failures)
        all_warnings.extend(rule_warnings)

    return DocumentValidationResult(
        passed=len(all_failures) == 0,
        score=_compute_score(len(all_failures), len(all_warnings)),
        failures=all_failures,
        warnings=all_warnings,
    )

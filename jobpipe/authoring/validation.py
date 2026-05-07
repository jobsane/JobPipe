"""Deterministic validation rules for authoring context and generated documents.

All rules are pure, offline, and deterministic: no LLM calls, no network
access, no randomness, no time dependence.

Findings are encoded as prefixed strings in DocumentValidationResult.failures
(errors) and .warnings (warnings/info). The DocumentValidationResult schema is
not modified.

Scoring: score = clamp(1.0 - (errors * 0.2 + warnings * 0.05), 0.0, 1.0)

Two entry points:
- validate_authoring_context(ctx) — validates the input context before generation
- validate_document_content(draft, language, selected_evidence, doc_type) — validates
  the generated document text after generation
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


# ---------------------------------------------------------------------------
# Document content validation (post-generation)
# ---------------------------------------------------------------------------

# Word count limits per document type.
_DOC_WORD_LIMITS: dict[str, tuple[int, int]] = {
    "cover_letter": (150, 600),
    "cv": (100, 1200),
}
_DEFAULT_WORD_LIMITS: tuple[int, int] = (50, 1200)

# English banned phrases — mirror of the Norwegian list in cover_letter_generator.py
# but for English job ads. Patterns that signal generic, non-evidence-based writing.
_HARD_BANNED_EN: list[str] = [
    # Generic team/process clichés
    "cross-functional teams",
    "continuous improvement",
    "stakeholders",
    "change management",
    "user-friendly solutions",
    "create value",
    "deliver value",
    "results-oriented",
    "motivated to contribute",
    "strong technical skills",
    "strong communication skills",
    "strong understanding",
    "public sector",
    # Weak gap apology patterns
    "although i don't have direct experience",
    "although i lack direct experience",
    "quickly adapt to",
    "build the necessary knowledge",
    "acquire the necessary knowledge",
    # Generic closing phrases
    "looking forward to contributing",
    "looking forward to the opportunity",
    "looking forward to bringing my skills",
    "apply my skills",
    "bring my expertise",
    "solid foundation for contributing",
    # Generic goal-support variants
    "support your goals",
    "contribute to the development of",
    "an exciting opportunity for me",
    "combine my experience with",
]

# Norwegian banned phrases — same canonical list as in cover_letter_generator.py.
# Duplicated here so document validation is self-contained (no import from generator).
_HARD_BANNED_NO: list[str] = [
    "tverrfaglige team",
    "tverrfaglig team",
    "tverrfaglig samarbeid",
    "kontinuerlig forbedring",
    "interessenter",
    "endringsprosesser",
    "brukervennlige løsninger",
    "skape verdi",
    "reell verdi",
    "praktisk og resultatorientert",
    "motivert for å bidra",
    "spesielt motivert",
    "cross-functional",
    "sterk teknisk",
    "sterk forståelse",
    "sterk kommunikator",
    "sterke resultater",
    "offentlig sektor",
    "rask tilpasningsevne",
    "vilje til å bygge",
    "tverrfaglig koordinering",
    "brukeren i sentrum",
    "brukerfokus",
    "helhetlige løsninger",
    "selv om jeg ikke har eksplisitt erfaring",
    "selv om jeg ikke har direkte erfaring",
    "selv om jeg mangler direkte erfaring",
    "selv om jeg mangler eksplisitt erfaring",
    "rask til å tilpasse meg",
    "raskt å tilpasse meg",
    "raskt tilpasse meg",
    "bygge nødvendig domenekunnskap",
    "bygge nødvendig kunnskap",
    "tilegne meg ny domenekunnskap",
    "tilegne meg kunnskap om",
    "robuste og fleksible løsninger",
    "ser frem til å bidra med min kompetanse",
    "ser frem til muligheten til å",
    "ser frem til å kunne",
    "ser frem til å bringe",
    "ser frem til å anvende",
    "ser frem til å kombinere",
    "anvende min kompetanse",
    "bringe min kompetanse",
    "solid fundament for å bidra",
    "støtte deres mål om",
    "i deres mål om",
    "bidra til utviklingen av",
    "bidra til deres",
    "i en ny kontekst",
    "en spennende mulighet for meg",
    "kombinere min praktiske erfaring med",
    "kombinere min erfaring med den strategiske",
]

_BANNED_BY_LANGUAGE: dict[str, list[str]] = {
    "no": _HARD_BANNED_NO,
    "en": _HARD_BANNED_EN,
}


def _doc_word_count_rule(
    draft: str, doc_type: str
) -> tuple[list[str], list[str]]:
    lo, hi = _DOC_WORD_LIMITS.get(doc_type, _DEFAULT_WORD_LIMITS)
    count = len(draft.split())
    if count < lo:
        return (
            [f"[word_count_too_short] {doc_type} has {count} words (minimum {lo})"],
            [],
        )
    if count > hi:
        return (
            [f"[word_count_too_long] {doc_type} has {count} words (maximum {hi})"],
            [],
        )
    return [], []


def _doc_banned_phrases_rule(
    draft: str, language: str
) -> tuple[list[str], list[str]]:
    banned = _BANNED_BY_LANGUAGE.get(language, _HARD_BANNED_NO)
    t = draft.lower()
    hits = [p for p in banned if p.lower() in t]
    failures = [
        f"[banned_phrase] document contains forbidden phrase: {p!r}" for p in hits
    ]
    return failures, []


def _doc_evidence_reference_rule(
    draft: str, selected_evidence: list[dict]
) -> tuple[list[str], list[str]]:
    """Warn when no evidence unit name or id appears in the draft."""
    if not selected_evidence:
        return [], []

    evidence_terms: list[str] = []
    for unit in selected_evidence:
        for key in ("employer", "company", "project", "evidence_unit_id", "title", "role"):
            val = unit.get(key)
            if isinstance(val, str) and len(val) > 3:
                evidence_terms.append(val.lower())

    draft_lower = draft.lower()
    if not any(term in draft_lower for term in evidence_terms):
        return [], [
            "[no_evidence_reference] document does not appear to reference any "
            "evidence unit (employer, project, or role name)"
        ]
    return [], []


def validate_document_content(
    draft: str,
    language: str,
    selected_evidence: list[dict],
    doc_type: str = "cover_letter",
) -> DocumentValidationResult:
    """Validate generated document text after generation.

    Args:
        draft: The generated document text.
        language: 'no' or 'en' — determines which banned-phrase list is used.
        selected_evidence: Evidence units from the authoring context (may be empty).
        doc_type: 'cover_letter' or 'cv' — determines word count limits.

    Returns a DocumentValidationResult with the same schema as validate_authoring_context.
    """
    all_failures: list[str] = []
    all_warnings: list[str] = []

    for rule_fn, args in [
        (_doc_word_count_rule, (draft, doc_type)),
        (_doc_banned_phrases_rule, (draft, language)),
        (_doc_evidence_reference_rule, (draft, selected_evidence)),
    ]:
        failures, warnings = rule_fn(*args)
        all_failures.extend(failures)
        all_warnings.extend(warnings)

    return DocumentValidationResult(
        passed=all_failures == [],
        score=_compute_score(len(all_failures), len(all_warnings)),
        failures=all_failures,
        warnings=all_warnings,
    )

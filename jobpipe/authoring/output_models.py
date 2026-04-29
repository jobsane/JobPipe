from __future__ import annotations

from pydantic import BaseModel


class GeneratedApplicationPackage(BaseModel):
    """
    Structured output from the authoring layer for one candidate and one job.

    Fields are populated by the future author/revise step from
    AuthoringCaseContext: job_id preserves the source job identity,
    cover_letter_draft is the generated letter text, tailored_cv_projection
    is the structured CV-tailoring projection, evidence_refs point back to
    selected evidence, gap_notes record disclosed gaps or mitigations, and
    validation may carry a serialized DocumentValidationResult.
    """

    job_id: str
    cover_letter_draft: str
    tailored_cv_projection: dict
    evidence_refs: list[str]
    gap_notes: list[str]
    validation: dict | None = None


class DocumentValidationResult(BaseModel):
    """
    Deterministic validation result for a generated application package.

    Fields are populated by validation rules after package generation:
    passed is the overall gate result, score is the aggregate quality score,
    failures lists blocking problems, and warnings lists non-blocking issues
    for user or revision review.
    """

    passed: bool
    score: float
    failures: list[str]
    warnings: list[str]

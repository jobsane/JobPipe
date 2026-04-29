import dataclasses
import json

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.output_models import GeneratedApplicationPackage
from jobpipe_crewai.crew import build_authoring_crew


class CrewAIAuthor:
    """crewAI implementation of AuthorAdapter. May import crewai freely.
    jobpipe/ must never import this module statically."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self._model = model

    def generate(self, ctx: AuthoringCaseContext) -> GeneratedApplicationPackage:
        try:
            payload = ctx.model_dump()
        except AttributeError:
            payload = dataclasses.asdict(ctx)

        if not payload.get("selected_evidence"):
            return GeneratedApplicationPackage(
                job_id=ctx.job_id,
                cover_letter_draft="",
                tailored_cv_projection={},
                evidence_refs=[],
                gap_notes=["No evidence units were provided for crewAI authoring"],
            )

        crew = build_authoring_crew(payload, self._model)
        result = crew.kickoff()
        raw = str(result) if result else ""

        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return GeneratedApplicationPackage(
                job_id=ctx.job_id,
                cover_letter_draft=raw,
                tailored_cv_projection={},
                evidence_refs=[],
                gap_notes=["crewAI output was not valid JSON - raw text returned"],
            )

        return GeneratedApplicationPackage(
            job_id=ctx.job_id,
            cover_letter_draft=parsed.get("cover_letter_draft", raw),
            tailored_cv_projection=parsed.get("tailored_cv_projection", {}),
            evidence_refs=parsed.get("evidence_refs", []),
            gap_notes=parsed.get("gap_notes", []),
            validation=None,
        )

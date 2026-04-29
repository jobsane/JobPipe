from __future__ import annotations

import json

from agents import Agent
from pydantic import BaseModel

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.output_models import GeneratedApplicationPackage
from jobpipe.stages._common import run_agent


AUTHOR_INSTRUCTIONS = """Du er en norsk søknadsassistent.

Du mottar et AuthoringCaseContext-objekt som JSON og skal produsere et
første utkast til søknadspakke for kandidaten.

Krav:
- Skriv cover_letter_draft på norsk, konkret og troverdig.
- Lag tailored_cv_projection som en dict med:
  - highlights: list[str] med 4-6 relevante punkter.
  - experience_refs: list[str] med samme lengde som highlights.
- Bruk selected_evidence som kildegrunnlag og speil relevante elementer i
  evidence_refs.
- Fyll gap_notes med korte, ærlige noter om mangler eller forbehold.
- Ikke finn opp erfaring, arbeidsgivere, prosjekter eller resultater.
"""


class _AuthorOutput(BaseModel):
    cover_letter_draft: str
    tailored_cv_projection: dict
    evidence_refs: list[str]
    gap_notes: list[str]


class SimpleAgentAuthor:
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self._agent = Agent(
            name="simple_author_agent",
            model=model,
            instructions=AUTHOR_INSTRUCTIONS,
            output_type=_AuthorOutput,
        )

    def generate(self, ctx: AuthoringCaseContext) -> GeneratedApplicationPackage:
        payload = {
            "job_id": ctx.job_id,
            "job_summary": ctx.job_summary,
            "decision_brief": ctx.decision_brief,
            "selected_evidence": ctx.selected_evidence,
            "narrative_brief": ctx.narrative_brief,
        }
        result = run_agent(self._agent, json.dumps(payload, ensure_ascii=False))
        out = result.final_output
        return GeneratedApplicationPackage(
            job_id=ctx.job_id,
            cover_letter_draft=out.cover_letter_draft,
            tailored_cv_projection=out.tailored_cv_projection,
            evidence_refs=out.evidence_refs,
            gap_notes=out.gap_notes,
        )


__all__ = ["SimpleAgentAuthor"]

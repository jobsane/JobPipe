from __future__ import annotations

import json

from agents import Agent

from jobpipe.core.paths import get_jobpipe_paths
from jobpipe.core.profile_layer import build_reverse_triage_context, load_or_build_profile_layer_for_paths
from jobpipe.core.schema import JobContext, ReverseTriageOut
from jobpipe.stages._common import build_job_header, job_excerpt, run_agent

REVERSE_INSTRUCTIONS = """
En annen agent har sortert bort stillingen som SKIP. Nå skal du dobbeltsjekke og finne skjult relevans.

Se etter signaler som ofte skjuler seg i generisk språk (offentlig sektor, rådgiverroller, systeminnføring,
gevinstrealisering, prosess, data/innsikt, plattformansvar).

Svar alltid med én av:
- SKIP_CONFIRMED
- REVIVE_REVIEW
- REVIVE_APPLY

Svar KUN som gyldig JSON iht output_type.
""".strip()


def build_reverse_agent(model: str) -> Agent:
    return Agent(
        name="reverse_triage_agent",
        model=model,
        instructions=REVERSE_INSTRUCTIONS,
        output_type=ReverseTriageOut,
    )


def reverse_triage_stage_factory(model: str, max_ad_text_chars: int, min_conf: float, skip_above: float = 1.0):
    """
    skip_above: if primary triage confidence >= this, skip reverse_triage entirely.
    This avoids calling a more expensive model for obvious mismatches.
    """
    agent = build_reverse_agent(model)

    def should_run(ctx: JobContext) -> bool:
        if not (ctx.triage and ctx.triage.triage_decision == "SKIP"):
            return False
        sigs = set(ctx.triage.signals or [])
        if "geo_postal_skip" in sigs or "hard_no_title" in sigs:
            return False
        # High-confidence SKIPs don't need a second opinion — saves a mini call
        if float(ctx.triage.confidence or 0) >= skip_above:
            return False
        return True

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        job = ctx.job
        text = job_excerpt(job, max_ad_text_chars)
        header = build_job_header(job)
        paths = get_jobpipe_paths()

        payload = {
            "reverse_triage_context": build_reverse_triage_context(load_or_build_profile_layer_for_paths(paths)),
            "triage_explanation": ctx.triage.explanation if ctx.triage else "",
            "job": {"header": header, "text_excerpt": text},
        }

        input_text = "Reverse triage payload (JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=2)
        result = run_agent(agent, input_text, trace={"stage": "reverse_triage", "job_id": ctx.job_id})
        out = result.final_output_as(ReverseTriageOut)
        ctx.reverse_triage = out

        if out.confidence >= min_conf and out.reverse_decision in ("REVIVE_REVIEW", "REVIVE_APPLY"):
            ctx.triage.triage_decision = "APPLY_CANDIDATE" if out.reverse_decision == "REVIVE_APPLY" else "REVIEW"
            ctx.triage.explanation = (ctx.triage.explanation + f" | reverse_triage: {out.rationale}")[:800]
            ctx.triage.confidence = max(float(ctx.triage.confidence or 0), float(out.confidence or 0))

        return ctx

    return should_run, run

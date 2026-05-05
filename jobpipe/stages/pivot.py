from __future__ import annotations
import json
from agents import Agent
from jobpipe.core.paths import get_jobpipe_paths
from jobpipe.core.profile_layer import build_pivot_context, load_or_build_profile_layer_for_paths
from jobpipe.core.schema import JobContext, PivotOut
from jobpipe.stages._common import run_agent

PIVOT_INSTRUCTIONS = """
Kandidaten er i strategisk pivot: fra operativ bredde/plattformansvar → mer overordnede roller
(forvaltning, tjenesteeier, CRM-strategi, prosessledelse, systemansvar, datadrevet kundeutvikling).

Vurder om stillingen er strategisk viktig selv om fit ikke er perfekt:
- pivot_score 0-100
- pivot_type (domene | nivå | tverrfaglighet | styring | systemansvar | offentlig | annet)
- potential_risk low/medium/high (risiko for trivsel/feilretning/for langt unna)
- why_it_matters: 3-6 punkter

Svar KUN som gyldig JSON iht output_type.
"""

def build_pivot_agent(model: str) -> Agent:
    return Agent(
        name="pivot_agent",
        model=model,
        instructions=PIVOT_INSTRUCTIONS,
        output_type=PivotOut,
    )

def pivot_stage_factory(model: str):
    agent = build_pivot_agent(model)

    def should_run(ctx: JobContext) -> bool:
        return bool(ctx.profile_match is not None)

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        paths = get_jobpipe_paths()
        payload = {
            "pivot_context": build_pivot_context(load_or_build_profile_layer_for_paths(paths)),
            "job_parsed": ctx.parsed.model_dump() if ctx.parsed else {},
            "match": ctx.profile_match.model_dump() if ctx.profile_match else {},
        }
        input_text = "Input (JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=2)
        result = run_agent(agent, input_text, trace={"stage": "pivot", "job_id": ctx.job_id})
        ctx.pivot = result.final_output_as(PivotOut)
        return ctx

    return should_run, run

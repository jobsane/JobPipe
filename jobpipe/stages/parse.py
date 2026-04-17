from __future__ import annotations
from agents import Agent
from jobpipe.core.schema import JobContext, JobParse
from jobpipe.stages._common import build_job_header, job_excerpt, run_agent

PARSE_INSTRUCTIONS = """
Du er en 'job ad parser' som strukturerer en stillingsannonse til et kompakt, presist datasett.
Ikke dikt opp fakta. Bruk bare informasjon som finnes i teksten, og vær eksplisitt når noe er uklart.

Returner:
- role_summary (1-3 setninger)
- responsibilities (5-10 punkt)
- requirements_must (hard krav)
- requirements_nice (ønskelig)
- seniority (om mulig)
- domain_tags (korte tags)
- tools_tech (systemer/metoder nevnt)
- org_context (1-2 setninger)
- red_flags (f.eks uklare krav, mye ansvar uten mandat, osv.)
Svar KUN som gyldig JSON iht output_type.
"""

def build_parse_agent(model: str) -> Agent:
    return Agent(
        name="parse_agent",
        model=model,
        instructions=PARSE_INSTRUCTIONS,
        output_type=JobParse,
    )

def parse_stage_factory(model: str, max_ad_text_chars: int):
    agent = build_parse_agent(model)

    def should_run(ctx: JobContext) -> bool:
        return bool(ctx.triage and ctx.triage.triage_decision != "SKIP")

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        job = ctx.job
        text = job_excerpt(job, max_ad_text_chars)
        header = build_job_header(job)

        input_text = (
            "=== STILLING ===\n" + header +
            "\n=== ANNONSETEXT (utdrag) ===\n" + text
        )
        result = run_agent(agent, input_text, trace={"stage": "parse", "job_id": ctx.job_id})
        ctx.parsed = result.final_output_as(JobParse)
        return ctx

    return should_run, run

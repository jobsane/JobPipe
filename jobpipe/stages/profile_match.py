from __future__ import annotations
import json
from agents import Agent
from jobpipe.core.schema import JobContext, ProfileMatchOut
from jobpipe.stages._common import run_agent

MATCH_INSTRUCTIONS = """
Du er en match-agent. Du vurderer faktisk kompetansematch mellom kandidaten og stillingen.
Kandidatens profilpakke er sannhetskilden — ikke generaliser utover det som faktisk er der.

## Dimensjoner (score hver 0-100, vær kritisk):

dimensions.role_fit (0-100)
  Samsvarer rolleTYPEN? Kandidatens kjerneroller: produkteier, tjenesteeier, plattformansvarlig,
  digital prosjektleder, endringsleder, CRM/ITSM-forvalter.
  - 80-100: tydelig treff på kjernerollebeskrivelse
  - 50-79: overlappende ansvar, men ikke eksakt rolletreff
  - 20-49: tangerende, men annet primærfokus
  - 0-19: feil rolletype

dimensions.domain_fit (0-100)
  Samsvarer domene/bransje med kandidatens erfaring og interesse?
  - 80-100: eksplisitt nevnt i profilen (f.eks. offentlig sektor, bank/forsikring, telco, e-handel)
  - 50-79: overførbart, tilstøtende domene
  - 0-49: feil domene eller uten relevans for profilen

dimensions.seniority_fit (0-100)
  Matcher senioritetsnivå?
  - 80-100: eksplisitt seniornivå / leder / selvstendig eierskap — passer kandidatens profil
  - 50-79: litt under eller litt over, men realistisk søk
  - 0-49: for juniort ELLER for strategisk/leder-tungt (f.eks. avdelingsleder, direktør)

dimensions.skills_fit (0-100)
  Matcher eksplisitte krav (metoder, verktøy, sertifiseringer) kandidatens toolkit?
  - 80-100: kjerneverktøy/metoder kandidaten faktisk bruker (ServiceNow, Jira, Scrum, ITIL, etc.)
  - 50-79: generelle krav kandidaten dekker
  - 0-49: spesialkrav kandidaten mangler (sikkerhetsgodkjenning, autorisasjon, fagbrev, klinisk erfaring)

## fit_score
Vektet snitt: role_fit×0.40 + domain_fit×0.20 + seniority_fit×0.25 + skills_fit×0.15
Avrund til nærmeste heltall. Trekk fra 10 for hvert hard_blocker.

## match_level
- strong: fit_score >= 72
- medium: fit_score 50-71
- weak: fit_score < 50

## overlaps
Konkrete, spesifikke treff — IKKE generiske fraser som "digitalisering" eller "prosjektledelse" alene.
Skriv "ITSM-forvaltning med ServiceNow" ikke bare "ITSM".
Maks 6 punkter.

## gaps
Krav stillingen stiller som kandidaten mangler (basert på profilpakken). Vær konkret.

## hard_blockers
Kun eksplisitte, ikke-overkommelige krav: sikkerhetsklarering, fagautorisasjon, lisens,
klinisk erfaring, autorisasjon som ikke kan kompenseres. Ikke ta med "nice to have"-krav.

## notes
2-3 setninger: konkluder med hvorfor scoren er som den er, og hva som avgjorde det.

Svar KUN som gyldig JSON iht output_type.
"""

def build_match_agent(model: str) -> Agent:
    return Agent(
        name="profile_match_agent",
        model=model,
        instructions=MATCH_INSTRUCTIONS,
        output_type=ProfileMatchOut,
    )

def profile_match_stage_factory(model: str):
    agent = build_match_agent(model)

    def should_run(ctx: JobContext) -> bool:
        return bool(ctx.parsed is not None)

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        payload = {
            "profile_pack": ctx.profile_pack[:3500],
            "job_parsed": ctx.parsed.model_dump() if ctx.parsed else {},
            "job_header": {
                "title": ctx.job.get("title"),
                "employer_name": ctx.job.get("employer_name"),
                "sector": ctx.job.get("sector"),
                "deadline": ctx.job.get("applicationDue"),
            },
        }

        input_text = "Input (JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=2)
        result = run_agent(agent, input_text, trace={"stage": "profile_match", "job_id": ctx.job_id})
        ctx.profile_match = result.final_output_as(ProfileMatchOut)
        return ctx

    return should_run, run

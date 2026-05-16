from __future__ import annotations
import json
from agents import Agent
from jobpipe.core.paths import get_jobpipe_paths
from jobpipe.core.profile_layer import build_profile_match_context, load_or_build_profile_layer_for_paths
from jobpipe.core.schema import JobContext, ProfileMatchOut
from jobpipe.stages._common import run_agent

MATCH_INSTRUCTIONS = """
Du er en match-agent. Du vurderer faktisk kompetansematch mellom kandidaten og stillingen.
JobPipe-avledet profile_match_context er sannhetskilden — ikke generaliser utover det som faktisk er der.

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
Du skal trekke ut de viktigste overlaps mellom jobbannonsen og profile_match_context.

Definisjon:
Overlaps = konkrete krav, arbeidsoppgaver, teknologier, domener, metoder, verktøy, sertifiseringer eller erfaringer fra jobbannonsen som er tydelig dekket i profile_match_context.

Regler:
- Bruk kun informasjon som finnes i jobbannonsen og profile_match_context.
- Ikke gjett eller overtolk.
- Skriv korte noun phrases, ikke hele setninger.
- Vær spesifikk: skriv "ITSM-forvaltning med ServiceNow", ikke bare "ITSM".
- Unngå generiske enkeltord som "digitalisering", "prosjektledelse", "kommunikasjon" eller "samarbeid" med mindre de er konkretisert.
- Slå sammen overlappende punkter som handler om samme kompetanse.
- Prioriter harde krav, sentrale arbeidsoppgaver, teknologier, bransjeerfaring og tydelige kvalifikasjoner.
- Ta med alle vesentlige overlaps, men ikke fyll på med svake eller generiske treff.
- Normalt 3-8 punkter, men færre hvis det er få sterke overlaps.
- Output skal være på samme språk som jobbannonsen.

## gaps
Du skal trekke ut de viktigste gaps mellom jobbannonsen og profile_match_context.

Definisjon:
Gaps = konkrete krav, arbeidsoppgaver, teknologier, domener, metoder, verktøy eller erfaringer fra jobbannonsen som ikke er tydelig dekket i profile_match_context.

Regler:
- Bruk kun krav og forventninger som faktisk finnes i jobbannonsen.
- Ikke lag gaps basert på ting som ikke står i annonsen.
- Ikke skriv negative formuleringer.
- Skriv korte noun phrases, ikke hele setninger.
- Skriv "Bachelorutdanning innen IKT", ikke "Mangler bachelorutdanning innen IKT".
- Skriv "Drift av nettverk og infrastruktur", ikke "Erfaring med drift og vedlikehold av nettverk og infrastruktur mangler".
- Vær spesifikk: skriv "Azure DevOps-pipelines", ikke bare "DevOps".
- Slå sammen like eller overlappende gaps.
- Prioriter etter alvorlighetsgrad: må-krav først, deretter sentrale arbeidsoppgaver, teknologi, domene og ønskede kvalifikasjoner.
- Ikke ta med gaps som er svakt antydet eller lite viktige.
- Ta med alle vesentlige gaps, men ikke fyll opp til et bestemt antall.
- Normalt 2-8 punkter, men 0-1 er riktig hvis profilen dekker det meste.
- Output skal være på samme språk som jobbannonsen.

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
        paths = get_jobpipe_paths()
        profile_match_context = build_profile_match_context(load_or_build_profile_layer_for_paths(paths))
        payload = {
            "profile_match_context": profile_match_context,
            "job_parsed": ctx.parsed.model_dump() if ctx.parsed else {},
            "job_header": {
                "title": ctx.job.get("title"),
                "employer_name": ctx.job.get("employer_name"),
                "sector": ctx.job.get("sector"),
                "deadline": ctx.job.get("applicationDue"),
                # Canonical NAV occupation classification — added 2026-05-16
                # to address Cognia-class false positives where the marketing
                # ad ``title`` ("Leder prosjekt og kundesuksess") suggests a
                # digital/product role but the NAV occupation classification
                # ("Arbeidsleder, bygg og anlegg") reveals it's actually
                # manual-trade. The matcher should weight occupation heavily
                # when title and occupation disagree.
                "occupation_level1": ctx.job.get("occupation_level1"),
                "occupation_level2": ctx.job.get("occupation_level2"),
                "role": ctx.job.get("role"),
            },
        }

        input_text = "Input (JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=2)
        result = run_agent(agent, input_text, trace={"stage": "profile_match", "job_id": ctx.job_id})
        ctx.profile_match = result.final_output_as(ProfileMatchOut)
        return ctx

    return should_run, run

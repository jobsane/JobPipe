from __future__ import annotations

import json
import logging
from pathlib import Path

from agents import Agent

from jobpipe.core.profile_layer import build_authoring_context, load_or_build_profile_layer_for_paths
from jobpipe.core.schema import JobContext, ApplicationPackOut
from jobpipe.core.paths import get_jobpipe_paths
from jobpipe.stages._common import run_agent

logger = logging.getLogger(__name__)

PACK_INSTRUCTIONS = """Du er en norsk søknadsassistent for Lars Værland.
Du mottar kontekst som JSON og produserer en komplett søknadspakke.

━━━ STILREGLER — ABSOLUTTE KRAV ━━━

1. SØKNADSBREV (cover_letter_text):
   - Lengde: 230-260 ord. Tell nøyaktig — ikke kortere, ikke lengre.
   - Skriv et KOMPLETT, klart-til-å-sende søknadsbrev på norsk.
   - Bruk ALDRI tankestrek (—). Bruk komma, kolon eller ny setning i stedet.
   - Ikke start brevet med "Jeg" — varièr setningsoppbygging.
   - IKKE si at du er "motivert", "brenner for" eller "drømmer om" stillingen.
     Demonstrer motivasjon gjennom konkrete handlinger og resultater i stedet.
   - IKKE bruk klisjéer: "lidenskap", "dedikert", "team player", "drømmejobb".
   - Skriv handlingsorientert: "Ledet", "Bygde", "Reduserte", ikke "Har erfaring med".
   - Brevet skal ha tre avsnitt:
       Avsnitt 1 (3-4 setninger): Koble kandidatens bakgrunn direkte til stillingens
         kjernutfordring. Konkret kontekst, ikke generell introduksjon.
       Avsnitt 2 (4-5 setninger): To-tre konkrete eksempler fra erfaring som beviser
         at kandidaten leverer det stillingen krever. Bruk tall/resultater der det finnes.
       Avsnitt 3 (2-3 setninger): Avslutning uten klisjé. Si noe konkret om hva
         kandidaten vil bidra med, og inviter til samtale.

2. CV-HIGHLIGHTS (cv_highlights):
   - Velg 4-6 bullets fra resume_work.highlights og/eller resume_projects.
   - Hvert punkt MÅ:
       a) Speile terminologien fra jobbkravene (ikke kandidatens originale ordlyd)
       b) Stå alene og gi mening uten kontekst
       c) Inneholde et verb + kontekst + (helst) resultat
   - IKKE oppfinn erfaring. Bruk kun det som finnes i resume_work/resume_projects.
   - IKKE kopier bullets ordrett — omformuler lett for å matche stillingen.
   - cv_highlights og cv_experience_refs MÅ ha nøyaktig samme antall elementer.

3. TONE:
   - Selvsikker men ikke skrytende. Faktabasert, ikke selvskryt.
   - Norsk, ikke oversatt engelsk. Unngå "leverere på", "drive", "stakeholders".
   - Offentlig sektor: mer vekt på tjenesteutvikling, innbyggerverdi, prosessforbedring.
   - Privat sektor: mer vekt på vekst, ROI, produkt-marked-fit.

━━━ KONTEKST DU FÅR ━━━
- job_header: stillingstittel og arbeidsgiver
- job_parsed: strukturerte jobbkrav (ansvar, must-have, nice-to-have)
- profile_match: fit_score, overlaps, gaps, hard_blockers
- pivot: pivot_score og pivot-vurdering
- moderator: endelig beslutning og cv_focus-anbefalinger
- authoring_context: JobPipe-avledet personmodell for denne kandidaten
  - authoring_profile
  - profile_snapshot
  - resume_master
  - role_records / role_variants
  - project_records / project_variants
  - selected_evidence_atoms

━━━ PRIORITERING ━━━
Overlaps fra profile_match er de sterkeste kortene. Bygg brevet rundt dem.
Gap_mitigations skal adressere de viktigste gapene uten å be om unnskyldning.
cover_letter_angle er din interne analyse av vinkelen — cover_letter_text er
det faktiske brevet basert på den analysen.
"""

def _build_application_pack_payload(ctx: JobContext) -> dict:
    paths = get_jobpipe_paths()
    try:
        authoring_context = build_authoring_context(load_or_build_profile_layer_for_paths(paths))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[application_pack] could not build derived authoring context: %s", exc)
        authoring_context = {
            "schema_version": "jobpipe.profile-layer.v1",
            "profile_snapshot": {},
            "authoring_profile": {},
            "resume_master": {},
            "narrative_profile": {},
            "role_records": [],
            "role_variants": [],
            "project_records": [],
            "project_variants": [],
            "selected_evidence_atoms": [],
            "strength_areas": [],
            "motivation_language": "",
        }

    return {
        "job_header": {
            "title": ctx.job.get("title"),
            "employer_name": ctx.job.get("employer_name"),
            "sector": ctx.job.get("sector"),
            "deadline": ctx.job.get("applicationDue"),
            "source_url": ctx.job.get("sourceurl") or ctx.job.get("link"),
        },
        "job_parsed": ctx.parsed.model_dump() if ctx.parsed else {},
        "profile_match": ctx.profile_match.model_dump() if ctx.profile_match else {},
        "pivot": ctx.pivot.model_dump() if ctx.pivot else {},
        "advantage_assessment": ctx.advantage_assessment_v3.model_dump() if ctx.advantage_assessment_v3 else {},
        "narrative_strategy": ctx.narrative_strategy_v3.model_dump() if ctx.narrative_strategy_v3 else {},
        "moderator": ctx.moderator.model_dump() if ctx.moderator else {},
        "authoring_context": authoring_context,
    }


def _generate_cv_docx(pack_data: dict, job_input: dict, job_path: Path) -> None:
    """Generate a DOCX 'Relevant Experience' supplement from cv_highlights."""
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        logger.warning("[application_pack] python-docx not installed — skipping DOCX generation")
        return

    highlights = pack_data.get("cv_highlights", [])
    refs = pack_data.get("cv_experience_refs", [])
    if not highlights:
        return

    title = (job_input.get("title") or "").strip()
    employer = (job_input.get("employer_name") or job_input.get("company") or "").strip()
    headline = pack_data.get("positioning_headline", "")
    cover_angle = pack_data.get("cover_letter_angle", "")
    interview_prep = pack_data.get("interview_prep", [])

    doc = Document()

    # A4, ~2 cm margins
    for section in doc.sections:
        section.page_width = 11906
        section.page_height = 16838
        margin = int(0.79 * 1440)
        section.left_margin = margin
        section.right_margin = margin
        section.top_margin = margin
        section.bottom_margin = margin

    # Header: name + role
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Lars Værland")
    run.bold = True
    run.font.size = Pt(16)

    if title or employer:
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        label = f"{title}" + (f" — {employer}" if employer else "")
        r2 = p2.add_run(label)
        r2.font.size = Pt(11)
        r2.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

    if headline:
        p3 = doc.add_paragraph()
        p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r3 = p3.add_run(headline)
        r3.italic = True
        r3.font.size = Pt(10)
        r3.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

    doc.add_paragraph()  # spacer

    # Relevant experience
    h1 = doc.add_paragraph()
    rh = h1.add_run("Relevante erfaringspunkter")
    rh.bold = True
    rh.font.size = Pt(13)

    for i, bullet in enumerate(highlights):
        ref = refs[i] if i < len(refs) else ""
        p_b = doc.add_paragraph(style="List Bullet")
        p_b.add_run(bullet)
        if ref:
            p_b.add_run(f"  [{ref}]").font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    doc.add_paragraph()

    # Cover letter angle
    if cover_angle:
        h2 = doc.add_paragraph()
        rh2 = h2.add_run("Søknadsvinkel")
        rh2.bold = True
        rh2.font.size = Pt(13)
        doc.add_paragraph(cover_angle)
        doc.add_paragraph()

    # Interview prep
    if interview_prep:
        h3 = doc.add_paragraph()
        rh3 = h3.add_run("Intervjuforberedelse")
        rh3.bold = True
        rh3.font.size = Pt(13)
        for q in interview_prep:
            p_q = doc.add_paragraph(style="List Bullet")
            p_q.add_run(q)

    out_path = job_path / "07_cv_highlights.docx"
    doc.save(str(out_path))
    logger.info("[application_pack] saved cv_highlights DOCX to %s", out_path)


def application_pack_stage_factory(model: str, web_search: bool = False):  # noqa: ARG001

    agent = Agent(
        name="application_pack_agent",
        model=model,
        instructions=PACK_INSTRUCTIONS,
        output_type=ApplicationPackOut,
    )

    def should_run(ctx: JobContext) -> bool:
        return bool(ctx.moderator and ctx.moderator.final_decision in ("APPLY_STRONGLY", "APPLY"))

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        job_path = Path(job_dir)
        payload = _build_application_pack_payload(ctx)

        input_text = "Kontekst (JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=2)
        logger.info("[application_pack] running for job %s", ctx.job_id)

        result = run_agent(agent, input_text, trace={"stage": "application_pack", "job_id": ctx.job_id})
        pack = result.final_output_as(ApplicationPackOut)
        ctx.application_pack = pack

        # Persist the draft for inspection
        pack_data = pack.model_dump()
        draft_path = job_path / "application_pack_draft.json"
        draft_path.write_text(json.dumps(pack_data, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(
            "[application_pack] done for job %s (%d cv_highlights)",
            ctx.job_id, len(pack_data.get("cv_highlights", [])),
        )

        # Generate DOCX supplement
        _generate_cv_docx(pack_data, ctx.job, job_path)

        return ctx

    return should_run, run

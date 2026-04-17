from __future__ import annotations

import json
import logging
from pathlib import Path

from agents import Agent

from jobpipe.core.schema import JobContext, ApplicationPackOut
from jobpipe.stages._common import run_agent

logger = logging.getLogger(__name__)

# Path to the candidate's JSON Resume (standard jsonresume.org format)
_RESUME_JSON_PATH = Path(__file__).parents[2] / "reports" / "resume.json"

PACK_INSTRUCTIONS = """Du er en norsk søknadsassistent. Du mottar kontekst som JSON og
produserer en komplett søknadspakke for kandidaten.

Du har tilgang til:
- job_header: stillingstittel og arbeidsgiver
- job_parsed: strukturerte jobbkrav (ansvar, must-have, nice-to-have)
- profile_match: fit_score, overlaps, gaps, hard_blockers
- pivot: pivot_score og pivot-vurdering
- moderator: endelig beslutning og cv_focus-anbefalinger
- profile_pack: kandidatens profil og mål (narrativ)
- resume_work: kandidatens arbeidshistorie med highlights (JSON Resume-format)
- resume_projects: kandidatens prosjektportefølje

For cv_highlights: velg 4-6 bullets fra resume_work.highlights og/eller resume_projects
som matcher jobbkravene best. Omformuler lett for å speile stillingens terminologi —
men IKKE oppfinn erfaring. Hvert punkt skal stå alene og si noe konkret.

cv_highlights og cv_experience_refs MÅ ha nøyaktig samme antall elementer.

Vær troverdig og kompakt. Skriv handlingsorientert norsk.
"""


def _load_resume_context() -> dict:
    """Load JSON Resume and extract work + projects for the prompt."""
    if not _RESUME_JSON_PATH.exists():
        return {"resume_work": [], "resume_projects": []}
    try:
        with open(_RESUME_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # Compact work entries: keep name, position, dates, summary, highlights
        work = []
        for w in data.get("work", []):
            work.append({
                "company": w.get("name") or w.get("company", ""),
                "position": w.get("position", ""),
                "start": w.get("startDate", ""),
                "end": w.get("endDate", "present"),
                "summary": (w.get("summary") or "")[:200],
                "highlights": w.get("highlights", []),
            })
        # Compact projects: keep name + description
        projects = [
            {"name": p.get("name", ""), "description": (p.get("description") or "")[:200]}
            for p in data.get("projects", [])
        ]
        return {"resume_work": work, "resume_projects": projects}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[application_pack] could not load resume.json: %s", exc)
        return {"resume_work": [], "resume_projects": []}


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
    resume_ctx = _load_resume_context()

    def should_run(ctx: JobContext) -> bool:
        return bool(ctx.moderator and ctx.moderator.final_decision in ("APPLY_STRONGLY", "APPLY"))

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        job_path = Path(job_dir)

        payload = {
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
            "moderator": ctx.moderator.model_dump() if ctx.moderator else {},
            "profile_pack": ctx.profile_pack[:3000],
            "resume_work": resume_ctx["resume_work"],
            "resume_projects": resume_ctx["resume_projects"],
        }

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

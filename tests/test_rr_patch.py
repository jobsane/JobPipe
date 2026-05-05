from __future__ import annotations

from jobpipe.projections.rr_patch import build_rr_patch
from jobpipe.model import ReactiveResumeTailoredCVPlan, ReactiveResumeTailoredCVProjection

_BASE_RR = {
    "basics": {
        "name": "Lars H. Vaerland",
        "headline": "Endrings- og prosjektleder",
    },
    "summary": {
        "title": "Profil",
        "hidden": False,
        "content": "<p>Original summary text.</p>",
    },
    "sections": {
        "experience": {
            "title": "Arbeidserfaring",
            "hidden": False,
            "items": [
                {
                    "id": "item-1",
                    "hidden": False,
                    "company": "Acme Corp",
                    "position": "Product Manager",
                    "period": "Jan 2020 - Jan 2023",
                    "description": (
                        "<ul>"
                        "<li><p>Led roadmap prioritization across 3 teams.</p></li>"
                        "<li><p>Improved delivery predictability by 30%.</p></li>"
                        "</ul>"
                    ),
                },
                {
                    "id": "item-2",
                    "hidden": False,
                    "company": "Old Corp",
                    "position": "Junior PM",
                    "period": "Jan 2018 - Jan 2020",
                    "description": "<ul><li><p>Assisted with projects.</p></li></ul>",
                },
                {
                    "id": "item-3",
                    "hidden": True,
                    "company": "Ancient Job",
                    "position": "Intern",
                    "period": "Jan 2010 - Jan 2012",
                    "description": "<ul><li><p>Old work.</p></li></ul>",
                },
            ],
        },
        "skills": {
            "title": "Kompetanse",
            "hidden": False,
            "items": [{"id": "skill-1", "hidden": False, "name": "Product Strategy", "keywords": []}],
        },
        "education": {
            "title": "Utdanning",
            "hidden": False,
            "items": [],
        },
        "projects": {
            "title": "Prosjekter",
            "hidden": True,
            "items": [],
        },
    },
}

_PLAN_ALL_SELECTED = ReactiveResumeTailoredCVPlan(
    candidate_id="test",
    job_id="job-001",
    variant_strategy="balanced",
    selected_evidence_unit_ids=["uid-1", "uid-2"],
    selected_section_order=["summary", "experience", "skills", "education"],
    suppressed_items=[],
    summary_brief="Experienced product leader with delivery focus.",
    rewrite_constraints=[],
    claim_targets=[],
)

_PROJECTION = ReactiveResumeTailoredCVProjection(
    headline="Senior Product Manager",
    summary_text="Experienced product leader with delivery focus.",
    section_plan=[{"section": "experience", "mode": "selected"}],
    selected_bullets=["Led roadmap prioritization across 3 teams."],
    provenance={},
    render_target="reactive_resume_json",
)


def test_patch_updates_headline() -> None:
    patched = build_rr_patch(_BASE_RR, _PLAN_ALL_SELECTED, _PROJECTION)
    assert patched["basics"]["headline"] == "Senior Product Manager"


def test_patch_updates_summary_content() -> None:
    patched = build_rr_patch(_BASE_RR, _PLAN_ALL_SELECTED, _PROJECTION)
    assert "Experienced product leader" in patched["summary"]["content"]
    assert patched["summary"]["hidden"] is False


def test_patch_hides_section_not_in_plan() -> None:
    plan = ReactiveResumeTailoredCVPlan(
        candidate_id="test",
        job_id="job-001",
        selected_section_order=["summary", "experience", "skills"],
        suppressed_items=[],
        summary_brief="",
    )
    patched = build_rr_patch(_BASE_RR, plan, _PROJECTION)
    assert patched["sections"]["education"]["hidden"] is True
    assert patched["sections"]["skills"]["hidden"] is False
    assert patched["sections"]["experience"]["hidden"] is False


def test_patch_shows_projects_when_in_plan() -> None:
    plan = ReactiveResumeTailoredCVPlan(
        candidate_id="test",
        job_id="job-001",
        selected_section_order=["summary", "experience", "projects", "skills"],
        suppressed_items=[],
        summary_brief="",
    )
    patched = build_rr_patch(_BASE_RR, plan, _PROJECTION)
    assert patched["sections"]["projects"]["hidden"] is False


def test_patch_suppresses_work_item_when_all_highlights_suppressed() -> None:
    plan = ReactiveResumeTailoredCVPlan(
        candidate_id="test",
        job_id="job-001",
        selected_section_order=["summary", "experience", "skills"],
        suppressed_items=[
            "work:Old Corp:Junior PM:0",
        ],
        summary_brief="",
    )
    patched = build_rr_patch(_BASE_RR, plan, _PROJECTION)
    items = patched["sections"]["experience"]["items"]
    old_corp = next(i for i in items if i["company"] == "Old Corp")
    acme = next(i for i in items if i["company"] == "Acme Corp")
    assert old_corp["hidden"] is True
    assert acme["hidden"] is False


def test_patch_does_not_unhide_already_hidden_items() -> None:
    plan = ReactiveResumeTailoredCVPlan(
        candidate_id="test",
        job_id="job-001",
        selected_section_order=["summary", "experience"],
        suppressed_items=[],
        summary_brief="",
    )
    patched = build_rr_patch(_BASE_RR, plan, _PROJECTION)
    ancient = next(i for i in patched["sections"]["experience"]["items"] if i["company"] == "Ancient Job")
    assert ancient["hidden"] is True


def test_patch_does_not_mutate_original() -> None:
    import copy
    original = copy.deepcopy(_BASE_RR)
    build_rr_patch(_BASE_RR, _PLAN_ALL_SELECTED, _PROJECTION)
    assert _BASE_RR["basics"]["headline"] == original["basics"]["headline"]
    assert _BASE_RR["summary"]["content"] == original["summary"]["content"]


def test_patch_empty_plan_leaves_structure_intact() -> None:
    plan = ReactiveResumeTailoredCVPlan(
        candidate_id="test",
        job_id="job-001",
        selected_section_order=[],
        suppressed_items=[],
        summary_brief="",
    )
    projection = ReactiveResumeTailoredCVProjection(render_target="reactive_resume_json")
    patched = build_rr_patch(_BASE_RR, plan, projection)
    assert "sections" in patched
    assert "basics" in patched

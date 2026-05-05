from __future__ import annotations

from jobpipe.projections import build_resume_import_projection, build_tailored_cv_plan, build_tailored_cv_projection

_MINIMAL_RR = {
    "sections": {
        "experience": {
            "items": [
                {
                    "company": "Acme Corp",
                    "position": "Product Manager",
                    "period": "Jan 2020 - Jan 2023",
                    "description": (
                        "<ul>"
                        "<li>Led roadmap prioritization across 3 teams.</li>"
                        "<li>Improved delivery predictability by 30%.</li>"
                        "</ul>"
                    ),
                    "hidden": False,
                }
            ]
        },
        "skills": {
            "items": [
                {"name": "Product Strategy", "keywords": ["roadmap", "OKR"], "hidden": False}
            ]
        },
        "education": {
            "items": [
                {"institution": "BI", "degree": "Master", "area": "Management", "hidden": False}
            ]
        },
        "projects": {
            "items": [
                {
                    "name": "Platform migration",
                    "description": "<p>Coordinated rollout for new platform.</p>",
                    "hidden": False,
                }
            ]
        },
    }
}

_MINIMAL_JOB_ROW = {
    "job_id": "test-001",
    "title": "Senior Product Manager",
    "sector": "SaaS",
    "description_snip": "Needs product strategy and stakeholder management.",
    "final_decision": "APPLY",
    "cv_focus": ["product strategy", "delivery"],
    "detail": {
        "overlaps": ["Product leadership"],
        "gaps": [],
        "hard_blockers": [],
        "match_notes": "Good overlap.",
    },
    "run_id": "run-test-001",
    "recommendation_reason": "Strong product overlap.",
}

_MINIMAL_PROFILE_PACK = """
## Candidate Snapshot
Name: Lars H. Vaerland
Role Family: Product Owner, Change Lead
"""

_JSONRESUME = {
    "work": [
        {
            "name": "Acme Corp",
            "position": "Product Manager",
            "highlights": [
                "Led roadmap prioritization across 3 teams.",
                "Improved delivery predictability by 30%.",
            ],
        }
    ],
    "skills": [{"name": "Product Strategy", "keywords": ["roadmap"]}],
    "education": [{"institution": "BI", "studyType": "Master", "area": "Management"}],
    "projects": [{"name": "Platform migration", "description": "Coordinated rollout."}],
}


def test_import_projection_with_rr_format() -> None:
    projection = build_resume_import_projection(
        _MINIMAL_RR,
        candidate_id="test",
        resume_source_id="test-source",
    )
    assert len(projection.work) > 0
    assert projection.metadata["work_count"] > 0


def test_tailored_cv_plan_with_rr_format() -> None:
    plan = build_tailored_cv_plan(
        _MINIMAL_JOB_ROW,
        profile_pack=_MINIMAL_PROFILE_PACK,
        resume_json=_MINIMAL_RR,
        candidate_id="test",
    )
    assert len(plan.selected_evidence_unit_ids) > 0
    assert "experience" in plan.selected_section_order
    assert "summary" in plan.selected_section_order


def test_tailored_cv_projection_with_rr_format() -> None:
    plan = build_tailored_cv_plan(
        _MINIMAL_JOB_ROW,
        profile_pack=_MINIMAL_PROFILE_PACK,
        resume_json=_MINIMAL_RR,
        candidate_id="test",
    )
    projection = build_tailored_cv_projection(
        _MINIMAL_JOB_ROW,
        plan,
        profile_pack=_MINIMAL_PROFILE_PACK,
        resume_json=_MINIMAL_RR,
        candidate_id="test",
    )
    assert len(projection.selected_bullets) > 0
    assert len(projection.section_plan) > 0
    assert projection.render_target == "reactive_resume_json"


def test_section_order_includes_skills_when_rr_has_them() -> None:
    plan = build_tailored_cv_plan(
        _MINIMAL_JOB_ROW,
        profile_pack=_MINIMAL_PROFILE_PACK,
        resume_json=_MINIMAL_RR,
        candidate_id="test",
    )
    assert "skills" in plan.selected_section_order


def test_full_pipeline_passthrough_for_jsonresume_format() -> None:
    projection = build_resume_import_projection(
        _JSONRESUME,
        candidate_id="test",
        resume_source_id="test-source",
    )
    assert len(projection.work) > 0

    plan = build_tailored_cv_plan(
        _MINIMAL_JOB_ROW,
        profile_pack=_MINIMAL_PROFILE_PACK,
        resume_json=_JSONRESUME,
        candidate_id="test",
    )
    assert len(plan.selected_section_order) > 0
    assert len(plan.selected_evidence_unit_ids) > 0

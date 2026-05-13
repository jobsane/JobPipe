"""Unit tests for ``jobpipe.workspace.artifact_tailoring``.

Verifies the pipeline-side projection: given a synthetic run directory with
``11_application_pack.json``, ``02_parsed.json``, ``03_profile_match.json``,
``10_moderator.json``, the projection produces a non-empty
``TailoringPlanReadModel`` with the right structure.

Uses tmp_path fixtures rather than real out_runs so tests stay deterministic
and don't depend on which runs exist on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobpipe.workspace.artifact_tailoring import ArtifactTailoringCapability
from jobpipe.workspace.contracts import (
    ClaimStatus,
    TailoringPlanReadModel,
    TailoringPlanSource,
)


def _seed_job(
    run_dir: Path,
    case_id: str,
    *,
    job_dir_name: str | None = None,
    pack: dict | None = None,
    parsed: dict | None = None,
    profile_match: dict | None = None,
    moderator: dict | None = None,
    pack_filename: str = "11_application_pack.json",
) -> Path:
    job_dir = run_dir / (job_dir_name or case_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "00_input.json").write_text(
        json.dumps({"job_id": case_id}), encoding="utf-8"
    )
    if pack is not None:
        (job_dir / pack_filename).write_text(json.dumps(pack), encoding="utf-8")
    if parsed is not None:
        (job_dir / "02_parsed.json").write_text(json.dumps(parsed), encoding="utf-8")
    if profile_match is not None:
        (job_dir / "03_profile_match.json").write_text(
            json.dumps(profile_match), encoding="utf-8"
        )
    if moderator is not None:
        (job_dir / "10_moderator.json").write_text(
            json.dumps(moderator), encoding="utf-8"
        )
    return job_dir


_FULL_PACK: dict = {
    "positioning_headline": "Senior data engineering fit for Acme",
    "top_value_props": [
        "Led data platform migration",
        "Owned SQL pipelines at scale",
        "Mentored junior engineers",
    ],
    "evidence_map": [
        "Migrated 50TB to Snowflake at FooCo",
        "Optimized 200 queries reducing cost 40%",
    ],
    "gap_mitigations": ["AWS certs in progress"],
    "cover_letter_angle": "Lead with the FooCo platform migration",
    "cover_letter_text": (
        "Dear hiring team,\n\nI am writing to apply for the Senior Data "
        "Engineer role. With deep SQL and platform experience..."
    ),
    "interview_prep": ["Discuss FooCo migration", "Show SQL test cases"],
    "cv_highlights": [
        "Led data platform migration to Snowflake",
        "Optimized 200 production queries",
    ],
    "cv_experience_refs": [
        "Senior Engineer, FooCo (2021-2024)",
        "Data Engineer, BarInc (2018-2021)",
    ],
}


def test_returns_none_when_run_dir_missing(tmp_path: Path) -> None:
    cap = ArtifactTailoringCapability(tmp_path / "does-not-exist")
    assert cap.get("case-x") is None


def test_returns_none_when_case_not_in_run(tmp_path: Path) -> None:
    cap = ArtifactTailoringCapability(tmp_path)
    assert cap.get("case-x") is None


def test_returns_none_when_application_pack_absent(tmp_path: Path) -> None:
    """A case with no application_pack hasn't been tailored yet — None is correct."""
    _seed_job(tmp_path, "case-1", pack=None, parsed={"tools_tech": ["Python"]})
    cap = ArtifactTailoringCapability(tmp_path)
    assert cap.get("case-1") is None


def test_projects_full_application_pack(tmp_path: Path) -> None:
    _seed_job(
        tmp_path,
        "case-full",
        pack=_FULL_PACK,
        parsed={
            "tools_tech": ["Python", "SQL", "AWS"],
            "domain_tags": ["data engineering"],
            "requirements_must": ["5y SQL", "AWS"],
        },
        profile_match={
            "fit_score": 80,
            "overlaps": ["SQL pipelines", "Python platform work"],
            "gaps": ["No production AWS"],
            "hard_blockers": [],
        },
        moderator={"feedback_flags": ["Soften claim about scale"]},
    )

    plan = ArtifactTailoringCapability(tmp_path).get("case-full")
    assert plan is not None
    assert isinstance(plan, TailoringPlanReadModel)
    assert plan.case_id == "case-full"
    assert plan.source == TailoringPlanSource.PIPELINE
    assert plan.positioning_angle == "Senior data engineering fit for Acme"

    # Section strategy mirrors cv_highlights
    assert plan.section_strategy[0].startswith("Led data platform")
    assert len(plan.bullet_changes) == 2
    assert plan.bullet_changes[0].proposed.startswith("Led data platform")
    assert "FooCo" in plan.bullet_changes[0].section
    assert plan.bullet_changes[0].original == ""  # additive guidance, not a swap

    # Keyword coverage: SQL is in overlaps (case-insensitive match), AWS is not
    by_kw = {k.keyword.lower(): k for k in plan.keyword_coverage}
    assert by_kw["sql"].present is True
    assert by_kw["aws"].present is False
    assert by_kw["aws"].suggested_placement  # non-empty hint

    # Claims: 1 gap (weak) + 1 moderator flag (weak), no hard blockers
    statuses = [c.status for c in plan.claim_warnings]
    assert ClaimStatus.WEAK in statuses
    assert ClaimStatus.UNSUPPORTED not in statuses
    assert any("AWS" in c.claim for c in plan.claim_warnings)
    assert any("Soften" in c.claim for c in plan.claim_warnings)

    # Value prop
    vp = plan.value_proposition
    assert vp is not None
    assert vp.message_pillars == _FULL_PACK["top_value_props"]
    assert vp.proof_points == _FULL_PACK["evidence_map"]
    assert vp.gap_mitigations == _FULL_PACK["gap_mitigations"]

    # Cover letter
    cl = plan.cover_letter
    assert cl is not None
    assert "hiring team" in cl.text
    assert cl.language == "en"
    assert cl.word_count > 0
    assert cl.angle == "Lead with the FooCo platform migration"

    # Updated_at + provenance
    assert plan.updated_at.endswith("Z")
    assert plan.provenance[0].source_label.startswith("run:")


def test_hard_blocker_becomes_unsupported_claim(tmp_path: Path) -> None:
    _seed_job(
        tmp_path,
        "case-blocked",
        pack=_FULL_PACK,
        profile_match={
            "hard_blockers": ["No security clearance"],
            "gaps": [],
            "fit_score": 30,
        },
    )
    plan = ArtifactTailoringCapability(tmp_path).get("case-blocked")
    assert plan is not None
    assert any(
        c.status == ClaimStatus.UNSUPPORTED and "clearance" in c.claim
        for c in plan.claim_warnings
    )


def test_norwegian_cover_letter_detected(tmp_path: Path) -> None:
    pack = dict(_FULL_PACK)
    pack["cover_letter_text"] = (
        "Kjære ansettelsesteam, jeg søker stillingen som dataingeniør "
        "og har erfaring med plattform og SQL."
    )
    _seed_job(tmp_path, "case-no", pack=pack)
    plan = ArtifactTailoringCapability(tmp_path).get("case-no")
    assert plan is not None
    assert plan.cover_letter is not None
    assert plan.cover_letter.language == "nb"


def test_falls_back_to_legacy_07_pack_filename(tmp_path: Path) -> None:
    _seed_job(
        tmp_path,
        "case-legacy",
        pack=_FULL_PACK,
        pack_filename="07_application_pack.json",
    )
    plan = ArtifactTailoringCapability(tmp_path).get("case-legacy")
    assert plan is not None
    assert plan.positioning_angle == _FULL_PACK["positioning_headline"]


def test_resolves_case_by_input_artifact_when_dir_name_differs(tmp_path: Path) -> None:
    """Job directories don't have to be named ``case_id`` — we look up via 00_input.json."""
    _seed_job(
        tmp_path,
        "case-renamed",
        job_dir_name="some_uuid_abc",
        pack=_FULL_PACK,
    )
    plan = ArtifactTailoringCapability(tmp_path).get("case-renamed")
    assert plan is not None
    assert plan.case_id == "case-renamed"


def test_pipeline_error_case_returns_none(tmp_path: Path) -> None:
    """Cases with pipeline errors don't get application_pack, so None is expected."""
    job_dir = tmp_path / "case-err"
    job_dir.mkdir()
    (job_dir / "00_input.json").write_text(
        json.dumps({"job_id": "case-err"}), encoding="utf-8"
    )
    (job_dir / "pipeline_error.json").write_text("{}", encoding="utf-8")
    assert ArtifactTailoringCapability(tmp_path).get("case-err") is None

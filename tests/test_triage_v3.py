from __future__ import annotations

from jobpipe.core.schema import FeatureScore, HardGates, TriageFeatures
from jobpipe.core.triage_v3 import aggregate_triage_decision, resolve_triage_ambiguity


def _feature(score: int, confidence: int = 80, reason: str = "test") -> FeatureScore:
    return FeatureScore(score=score, confidence=confidence, reason=reason, evidence_spans=[])


def _features(**overrides: int) -> TriageFeatures:
    defaults = {
        "core_tech_alignment": 78,
        "legacy_burden": 68,
        "role_specificity": 72,
        "requirement_density": 66,
        "geospatial_friction": 70,
        "remote_veracity": 68,
        "autonomy_level": 65,
        "stakeholder_complexity": 62,
        "operating_fit": 64,
    }
    defaults.update(overrides)
    return TriageFeatures(**{name: _feature(score) for name, score in defaults.items()})


def test_aggregate_discard_on_failed_hard_gates() -> None:
    decision = aggregate_triage_decision(
        _features(),
        HardGates(geo_gate=False, blocker_reasons=["geo_postal_skip"]),
    )

    assert decision.label == "discard"
    assert decision.blockers == ["geo_postal_skip"]
    assert decision.weighted_score == 0.0


def test_aggregate_shortlist_for_strong_feature_set() -> None:
    decision = aggregate_triage_decision(
        _features(
            core_tech_alignment=92,
            legacy_burden=80,
            role_specificity=86,
            requirement_density=78,
            geospatial_friction=84,
            remote_veracity=88,
            autonomy_level=78,
            stakeholder_complexity=72,
            operating_fit=76,
        ),
        HardGates(),
    )

    assert decision.label == "shortlist"
    assert "strong_core_tech_match" in decision.boosts
    assert "specific_role_signal" in decision.boosts


def test_aggregate_discards_low_core_tech_even_when_other_scores_are_good() -> None:
    decision = aggregate_triage_decision(
        _features(core_tech_alignment=28, role_specificity=82, operating_fit=75),
        HardGates(),
    )

    assert decision.label == "discard"
    assert "core_tech_alignment_too_low" in decision.blockers


def test_aggregate_marks_borderline_case_for_ambiguity_pass() -> None:
    decision = aggregate_triage_decision(
        _features(
            core_tech_alignment=58,
            legacy_burden=56,
            role_specificity=54,
            requirement_density=50,
            geospatial_friction=24,
            remote_veracity=82,
            autonomy_level=48,
            stakeholder_complexity=46,
            operating_fit=50,
        ),
        HardGates(),
    )

    assert decision.label in {"review", "discard"}
    assert decision.needs_ambiguity_pass is True


def test_resolve_triage_ambiguity_can_upgrade_borderline_discard() -> None:
    features = _features(
        core_tech_alignment=74,
        legacy_burden=62,
        role_specificity=70,
        requirement_density=54,
        geospatial_friction=20,
        remote_veracity=84,
        autonomy_level=58,
        stakeholder_complexity=54,
        operating_fit=50,
    )
    decision = aggregate_triage_decision(features, HardGates())
    ambiguity = resolve_triage_ambiguity(features, decision)

    assert ambiguity.final_decision.needs_ambiguity_pass is False
    assert ambiguity.resolved_label in {"review", "discard"}


def test_aggregate_triage_decision_accepts_shadow_threshold_overrides() -> None:
    decision = aggregate_triage_decision(
        _features(
            core_tech_alignment=72,
            legacy_burden=65,
            role_specificity=64,
            requirement_density=60,
            geospatial_friction=58,
            remote_veracity=62,
            autonomy_level=58,
            stakeholder_complexity=54,
            operating_fit=56,
        ),
        HardGates(),
        review_threshold=40.0,
        shortlist_threshold=55.0,
    )

    assert decision.label in {"review", "shortlist"}

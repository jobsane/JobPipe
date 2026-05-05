"""
Tests for the moderate (moderator) stage — the deterministic threshold engine.

No LLM calls. moderate_stage_factory uses only YAML thresholds.
Tests every boundary condition to catch threshold regressions.

Decision zones (with pipeline.v1.yaml thresholds):
  fit < 30                        → SKIP
  30 ≤ fit < 58                   → REVIEW_LOW  (always; pivot ignored)
  58 ≤ fit < 67, pivot < 78       → REVIEW_LOW  (below pivot-boost threshold)
  58 ≤ fit < 67, pivot >= 78      → REVIEW_HIGH (pivot boost)
  67 ≤ fit < 78                   → APPLY
  fit >= 78                       → APPLY_STRONGLY
"""
from __future__ import annotations

from pathlib import Path

import pytest
from jobpipe.stages.moderate import moderate_stage_factory
from jobpipe.core.schema import (
    JobContext, RunMeta, TriageOut, ProfileMatchOut, PivotOut
)
from jobpipe.stages.triage_features import triage_features_artifact_path


# ---------------------------------------------------------------------------
# Thresholds matching pipeline.v1.yaml defaults (as of 2026-04-13)
# ---------------------------------------------------------------------------

THRESHOLDS = {
    "review_min_fit": 30,
    "review_high_min_fit": 58,
    "apply_fit": 67,
    "apply_strong_fit": 78,
    "pivot_boost_apply": 78,
    # Disable v3 demotion so boundary tests isolate pure fit-score logic.
    # v3 integration is tested separately in TestModeratorOutput.
    "v3_discard_demote": False,
}


def _make_ctx(fit: int, pivot: int = 50, triage: str = "REVIEW") -> JobContext:
    ctx = JobContext(
        meta=RunMeta(run_id="test", pipeline_name="test", created_at="2026-01-01T00:00:00Z"),
        job_id="test_job",
        job={"title": "Test Job"},
        profile_pack="",
    )
    ctx.triage = TriageOut(
        triage_decision=triage, confidence=0.8, explanation="test", signals=[]
    )
    ctx.profile_match = ProfileMatchOut(
        fit_score=fit,
        match_level="strong" if fit >= 72 else ("medium" if fit >= 50 else "weak"),
        overlaps=[], gaps=[], hard_blockers=[], notes="test",
    )
    ctx.pivot = PivotOut(
        pivot_score=pivot,
        pivot_type="adjacent",
        potential_risk="low",
        why_it_matters=[],
    )
    return ctx


def _decide(fit: int, pivot: int = 50, triage: str = "REVIEW") -> str:
    should_run, run = moderate_stage_factory(THRESHOLDS)
    ctx = _make_ctx(fit, pivot, triage)
    result = run(ctx, job_dir="/tmp")
    return result.moderator.final_decision


# ---------------------------------------------------------------------------
# Boundary tests
# ---------------------------------------------------------------------------

class TestModerateBoundaries:
    # --- SKIP zone (fit < 30) ---
    def test_fit_0_is_skip(self):
        assert _decide(0) == "SKIP"

    def test_fit_29_is_skip(self):
        assert _decide(29) == "SKIP"

    def test_fit_30_is_not_skip(self):
        assert _decide(30) != "SKIP"

    # --- REVIEW_LOW zone (30 ≤ fit < 58, regardless of pivot) ---
    def test_fit_30_is_review_low(self):
        assert _decide(30) == "REVIEW_LOW"

    def test_fit_57_is_review_low(self):
        assert _decide(57) == "REVIEW_LOW"

    def test_fit_57_with_high_pivot_is_still_review_low(self):
        """Pivot boost only applies in the 58-66 zone; below 58 is always REVIEW_LOW."""
        assert _decide(57, pivot=90) == "REVIEW_LOW"

    # --- REVIEW_LOW zone continues: 58 ≤ fit < 67 WITHOUT pivot boost ---
    def test_fit_58_low_pivot_is_review_low(self):
        """fit=58 with pivot=50 (< boost threshold of 78) → REVIEW_LOW, not REVIEW_HIGH."""
        assert _decide(58, pivot=50) == "REVIEW_LOW"

    def test_fit_66_low_pivot_is_review_low(self):
        """fit=66 with pivot=50 → REVIEW_LOW (pivot not high enough for boost)."""
        assert _decide(66, pivot=50) == "REVIEW_LOW"

    # --- REVIEW_HIGH zone: 58 ≤ fit < 67 WITH pivot boost (pivot >= 78) ---
    def test_fit_58_high_pivot_is_review_high(self):
        """fit=58 with pivot=78 (exactly at boost threshold) → REVIEW_HIGH."""
        assert _decide(58, pivot=78) == "REVIEW_HIGH"

    def test_fit_66_high_pivot_is_review_high(self):
        """fit=66 with pivot=80 → REVIEW_HIGH via pivot boost."""
        assert _decide(66, pivot=80) == "REVIEW_HIGH"

    # --- APPLY zone (67 ≤ fit < 78) — pivot irrelevant here ---
    def test_fit_67_is_apply(self):
        assert _decide(67) == "APPLY"

    def test_fit_77_is_apply(self):
        assert _decide(77) == "APPLY"

    # --- APPLY_STRONGLY zone (fit >= 78) ---
    def test_fit_78_is_apply_strongly(self):
        assert _decide(78) == "APPLY_STRONGLY"

    def test_fit_100_is_apply_strongly(self):
        assert _decide(100) == "APPLY_STRONGLY"


class TestPivotBoost:
    def test_review_zone_with_pivot_boost_becomes_review_high(self):
        """fit=65 (58-66 zone) + pivot=78 → REVIEW_HIGH via pivot boost."""
        result = _decide(fit=65, pivot=78)
        assert result == "REVIEW_HIGH", f"Expected REVIEW_HIGH via pivot boost, got {result}"

    def test_review_zone_without_pivot_boost_stays_review_low(self):
        """fit=65 + pivot=60 (below boost threshold of 78) → REVIEW_LOW."""
        result = _decide(fit=65, pivot=60)
        assert result == "REVIEW_LOW"

    def test_pivot_boost_requires_fit_in_review_high_range(self):
        """fit=55 (below review_high_min_fit=58) + pivot=90 → stays REVIEW_LOW, not boosted."""
        result = _decide(fit=55, pivot=90)
        assert result == "REVIEW_LOW"

    def test_pivot_boost_exact_threshold(self):
        """pivot=78 exactly meets boost threshold → REVIEW_HIGH."""
        assert _decide(fit=62, pivot=78) == "REVIEW_HIGH"

    def test_pivot_boost_one_below_threshold(self):
        """pivot=77 is one below boost threshold → REVIEW_LOW."""
        assert _decide(fit=62, pivot=77) == "REVIEW_LOW"

    def test_apply_strongly_ignores_pivot(self):
        """fit=80 (APPLY_STRONGLY) regardless of pivot score."""
        assert _decide(fit=80, pivot=0) == "APPLY_STRONGLY"
        assert _decide(fit=80, pivot=100) == "APPLY_STRONGLY"

    def test_apply_zone_ignores_pivot(self):
        """fit=70 (APPLY zone) is APPLY regardless of pivot."""
        assert _decide(fit=70, pivot=0) == "APPLY"
        assert _decide(fit=70, pivot=100) == "APPLY"


class TestModeratorShouldRun:
    def test_should_run_always_true(self):
        """should_run always returns True — moderation is unconditional."""
        should_run, _ = moderate_stage_factory(THRESHOLDS)
        ctx = _make_ctx(fit=70)
        assert should_run(ctx) is True

    def test_should_run_true_even_without_profile_match(self):
        """should_run returns True even if profile_match is None; run() handles None gracefully."""
        should_run, _ = moderate_stage_factory(THRESHOLDS)
        ctx = _make_ctx(fit=70)
        ctx.profile_match = None
        assert should_run(ctx) is True

    def test_run_with_no_profile_match_produces_skip(self):
        """If profile_match is None, run() defaults fit to 0 → SKIP."""
        _, run = moderate_stage_factory(THRESHOLDS)
        ctx = _make_ctx(fit=70)
        ctx.profile_match = None
        result = run(ctx, "/tmp")
        assert result.moderator.final_decision == "SKIP"


class TestModeratorOutput:
    def test_moderator_sets_confidence(self):
        should_run, run = moderate_stage_factory(THRESHOLDS)
        ctx = _make_ctx(fit=70)
        result = run(ctx, "/tmp")
        assert result.moderator is not None
        assert 0.0 <= result.moderator.confidence <= 1.0

    def test_moderator_sets_recommendation_reason(self):
        should_run, run = moderate_stage_factory(THRESHOLDS)
        ctx = _make_ctx(fit=70)
        result = run(ctx, "/tmp")
        assert result.moderator.recommendation_reason  # non-empty string

    def test_moderator_confidence_increases_with_fit(self):
        """Higher fit → higher confidence (generally)."""
        _, run = moderate_stage_factory(THRESHOLDS)
        ctx_low = run(_make_ctx(fit=30), "/tmp")
        ctx_high = run(_make_ctx(fit=90), "/tmp")
        assert ctx_high.moderator.confidence > ctx_low.moderator.confidence

    def test_moderator_attaches_triage_v3_snapshot(self):
        _, run = moderate_stage_factory(THRESHOLDS)
        ctx = run(_make_ctx(fit=70, pivot=80), "/tmp")
        assert ctx.moderator.triage_decision_v3 is not None
        assert ctx.moderator.triage_decision_v3.label in {"review", "shortlist", "discard"}

    def test_moderator_persists_triage_features_artifact(self, tmp_path: Path):
        _, run = moderate_stage_factory(THRESHOLDS)
        ctx = run(_make_ctx(fit=70, pivot=80), str(tmp_path))
        assert ctx.triage_features is not None
        assert triage_features_artifact_path(str(tmp_path)).exists()

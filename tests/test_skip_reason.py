"""
Tests for the skip_reason derivation logic in sync_ledger.py.

This verifies that the dashboard geo-classification fix works correctly —
jobs are categorised by their actual stop-reason, not guessed from partial signals.
"""
from __future__ import annotations

import pytest


def _derive_skip_reason(triage_signals, triage_decision, final_decision, fit_score):
    """Mirrors the skip_reason logic from sync_ledger.merge_job_details."""
    _sig_set = set(triage_signals) if triage_signals else set()
    _fit = fit_score if isinstance(fit_score, int) else None
    _final = final_decision or ""
    _triage = triage_decision or ""

    if _sig_set & {"geo_postal_skip", "geo_county_skip"}:
        return "geo"
    elif "hard_no_title" in _sig_set:
        return "hard_no"
    elif "semantic_filter_skip" in _sig_set:
        return "semantic"
    elif _triage == "SKIP" and _final in ("SKIP", ""):
        return "triage_llm"
    elif _final == "SKIP" and _fit is not None and _fit < 30:
        return "fit_floor"
    elif _final == "SKIP":
        return "moderate"
    elif _final:
        return "passed"
    else:
        return ""


class TestSkipReasonDerivation:
    def test_geo_postal_skip(self):
        r = _derive_skip_reason(["geo_postal_skip", "8910"], "SKIP", "SKIP", None)
        assert r == "geo"

    def test_geo_county_skip(self):
        r = _derive_skip_reason(["geo_county_skip", "Nordland"], "SKIP", "SKIP", None)
        assert r == "geo"

    def test_hard_no_title(self):
        r = _derive_skip_reason(["hard_no_title"], "SKIP", "SKIP", None)
        assert r == "hard_no"

    def test_semantic_filter_skip(self):
        r = _derive_skip_reason(["semantic_filter_skip", "sim:0.32"], "SKIP", "SKIP", None)
        assert r == "semantic"

    def test_triage_llm_skip(self):
        r = _derive_skip_reason(["helse/klinisk"], "SKIP", "SKIP", None)
        assert r == "triage_llm"

    def test_fit_floor_skip(self):
        """fit_score=20 < review_min_fit=30 → fit_floor, not moderate."""
        r = _derive_skip_reason([], "REVIEW", "SKIP", 20)
        assert r == "fit_floor"

    def test_fit_exactly_at_floor_is_not_fit_floor(self):
        """fit_score=30 exactly = at threshold, not below it → moderate."""
        r = _derive_skip_reason([], "REVIEW", "SKIP", 30)
        assert r == "moderate"

    def test_moderate_skip(self):
        """Passed triage + fit floor, moderated down."""
        r = _derive_skip_reason([], "REVIEW", "SKIP", 45)
        assert r == "moderate"

    def test_passed_apply(self):
        r = _derive_skip_reason([], "APPLY_CANDIDATE", "APPLY", 72)
        assert r == "passed"

    def test_passed_review(self):
        r = _derive_skip_reason([], "REVIEW", "REVIEW_HIGH", 60)
        assert r == "passed"

    def test_geo_takes_priority_over_hard_no(self):
        """Geo signal wins even if hard_no_title is also present."""
        r = _derive_skip_reason(["geo_postal_skip", "hard_no_title"], "SKIP", "SKIP", None)
        assert r == "geo"

    def test_empty_signals_no_decision(self):
        r = _derive_skip_reason([], "", "", None)
        assert r == ""

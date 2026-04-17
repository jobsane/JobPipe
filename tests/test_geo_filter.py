"""
Tests for the geo postal/county filter in triage.py.

These are pure Python unit tests — no LLM calls, no network, no fastembed.
We exercise the pre-AI filter logic directly by constructing a minimal
triage_stage_factory with geo enabled and no LLM reachable.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from jobpipe.stages.triage import triage_stage_factory, _norm_postal, _get_postals
from jobpipe.core.schema import JobContext, RunMeta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GEO_POSTAL_REGEX = r"^([0134])(00[1-9]|0[1-9]\d|[1-9](0[1-9]|[1-9]\d))$"
_GEO_REMOTE_REGEX = r"(?i)(remote|fjern|hjemmekontor|hybrid)"
_GEO_COUNTY_REGEX = r"(?i)\b(oslo|akershus|viken|vestfold|telemark|agder|aust-agder|vest-agder)\b"

SAFETY_RULES = {
    "geo_enabled": True,
    "geo_postal_regex": _GEO_POSTAL_REGEX,
    "geo_allow_remote_regex": _GEO_REMOTE_REGEX,
    "geo_county_regex": _GEO_COUNTY_REGEX,
    "hard_no_title_regex": "",
    "target_title_regex": "",
    "very_strong_positive_regex": "",
    "weak_positive_regex": "",
    "weak_anchor_regex": "",
    "never_skip_if_title_matches": False,
    "weak_override_max_skip_confidence": 0.45,
    "weak_override_min_hits": 4,
    "weak_override_min_hits_with_anchor": 2,
}


def _make_ctx(job: dict) -> JobContext:
    return JobContext(
        meta=RunMeta(run_id="test", pipeline_name="test", created_at="2026-01-01T00:00:00Z"),
        job_id="test_job",
        job=job,
        profile_pack="",
    )


def _run_triage(job: dict) -> JobContext:
    """Run only the pre-AI geo filter (mocking the LLM agent so it never fires)."""
    with patch("jobpipe.stages.triage.build_triage_agent") as mock_agent_factory, \
         patch("jobpipe.stages.triage.run_agent") as mock_run_agent:
        # If the LLM is somehow reached, fail the test — we only want pre-AI
        mock_run_agent.side_effect = AssertionError("LLM was called — geo filter should have blocked this job")

        should_run, run = triage_stage_factory(
            model="gpt-4.1-nano",
            max_ad_text_chars=2200,
            safety_rules=SAFETY_RULES,
            profile_pack="",
            semantic_threshold=0.0,  # disable semantic filter
        )
        ctx = _make_ctx(job)
        result = run(ctx, job_dir="/tmp/test_job")
        return result


# ---------------------------------------------------------------------------
# _norm_postal
# ---------------------------------------------------------------------------

class TestNormPostal:
    def test_plain_4digit(self):
        assert _norm_postal("0150") == "0150"

    def test_strips_decimal(self):
        """Decimal suffix stripped, then zero-padded to 4 digits → '0151'."""
        assert _norm_postal("151.0") == "0151"

    def test_pads_short(self):
        assert _norm_postal("150") == "0150"

    def test_empty(self):
        assert _norm_postal("") == ""

    def test_none(self):
        assert _norm_postal(None) == ""


# ---------------------------------------------------------------------------
# Allowed postal codes (Oslo / Akershus / Vestfold-Telemark / Agder)
# ---------------------------------------------------------------------------

class TestAllowedPostalCodes:
    @pytest.mark.parametrize("postal", [
        "0150",  # Oslo sentrum
        "0656",  # Oslo
        "0799",  # Oslo edge
        "1337",  # Akershus
        "3211",  # Vestfold
        "4012",  # Agder (Stavanger area — 4xxx covers Agder)
    ])
    def test_allowed_postals_reach_llm_or_pass(self, postal):
        """Jobs with allowed postal codes must NOT be geo-skipped."""
        # We can't run the LLM in tests, so we patch it to return REVIEW
        with patch("jobpipe.stages.triage.build_triage_agent"), \
             patch("jobpipe.stages.triage.run_agent") as mock_run:
            from jobpipe.core.schema import TriageOut
            mock_out = MagicMock()
            mock_out.final_output_as.return_value = TriageOut(
                triage_decision="REVIEW", confidence=0.8, explanation="LLM reached", signals=[]
            )
            mock_run.return_value = mock_out

            should_run, run = triage_stage_factory(
                model="gpt-4.1-nano",
                max_ad_text_chars=2200,
                safety_rules=SAFETY_RULES,
                profile_pack="",
                semantic_threshold=0.0,
            )
            ctx = run(_make_ctx({"work_postalCode": postal, "title": "Prosjektleder"}), "/tmp")
            assert ctx.triage is not None
            assert ctx.triage.triage_decision == "REVIEW", \
                f"postal={postal} should have reached LLM, got {ctx.triage.triage_decision} | signals={ctx.triage.signals}"


# ---------------------------------------------------------------------------
# Blocked postal codes
# ---------------------------------------------------------------------------

class TestBlockedPostalCodes:
    @pytest.mark.parametrize("postal,desc", [
        ("8910", "Brønnøysund — geo false-pass regression"),
        ("2270", "Flisa — geo false-pass regression"),
        ("7000", "Trondheim"),
        ("5000", "Bergen"),
        ("9000", "Tromsø"),
        ("6000", "Møre og Romsdal"),
        ("2000", "Innlandet"),
    ])
    def test_blocked_postals_are_geo_skipped(self, postal, desc):
        """Jobs with non-allowed postal codes must be hard-SKIPped."""
        ctx = _run_triage({"work_postalCode": postal, "title": "Prosjektleder"})
        assert ctx.triage is not None, f"{desc}: triage not set"
        assert ctx.triage.triage_decision == "SKIP", f"{desc}: expected SKIP, got {ctx.triage.triage_decision}"
        assert any("geo" in s for s in ctx.triage.signals), f"{desc}: expected geo signal, got {ctx.triage.signals}"

    @pytest.mark.parametrize("postal", ["0100", "0200", "0300", "1100"])
    def test_xx00_postals_are_blocked(self, postal):
        """xx00 postal codes (non-geographic) must be blocked."""
        ctx = _run_triage({"work_postalCode": postal, "title": "Prosjektleder"})
        assert ctx.triage.triage_decision == "SKIP"
        assert any("geo" in s for s in ctx.triage.signals)


# ---------------------------------------------------------------------------
# Remote / hybrid override
# ---------------------------------------------------------------------------

class TestRemoteOverride:
    def test_remote_field_overrides_blocked_postal(self):
        """A job with remote=True and a blocked postal should NOT be geo-skipped."""
        with patch("jobpipe.stages.triage.build_triage_agent"), \
             patch("jobpipe.stages.triage.run_agent") as mock_run:
            from jobpipe.core.schema import TriageOut
            mock_out = MagicMock()
            mock_out.final_output_as.return_value = TriageOut(
                triage_decision="REVIEW", confidence=0.7, explanation="remote job", signals=[]
            )
            mock_run.return_value = mock_out

            should_run, run = triage_stage_factory(
                model="gpt-4.1-nano", max_ad_text_chars=2200,
                safety_rules=SAFETY_RULES, profile_pack="", semantic_threshold=0.0,
            )
            ctx = run(_make_ctx({
                "work_postalCode": "8910",
                "title": "Remote Prosjektleder",
                "remote": "remote",
            }), "/tmp")
            assert ctx.triage.triage_decision == "REVIEW", \
                "Remote field should bypass geo block"

    def test_hybrid_in_description_intro_overrides(self):
        """Hybrid in first 300 chars of description should bypass geo block."""
        with patch("jobpipe.stages.triage.build_triage_agent"), \
             patch("jobpipe.stages.triage.run_agent") as mock_run:
            from jobpipe.core.schema import TriageOut
            mock_out = MagicMock()
            mock_out.final_output_as.return_value = TriageOut(
                triage_decision="REVIEW", confidence=0.7, explanation="hybrid ok", signals=[]
            )
            mock_run.return_value = mock_out

            should_run, run = triage_stage_factory(
                model="gpt-4.1-nano", max_ad_text_chars=2200,
                safety_rules=SAFETY_RULES, profile_pack="", semantic_threshold=0.0,
            )
            ctx = run(_make_ctx({
                "work_postalCode": "8910",
                "title": "Prosjektleder",
                "description_html": "Hybrid arbeidsform. Vi tilbyr fleksibelt hjemmekontor.",
            }), "/tmp")
            assert ctx.triage.triage_decision == "REVIEW"

    def test_hybrid_deep_in_description_does_NOT_override(self):
        """Hybrid mentioned only deep in description (>300 chars) must NOT bypass geo."""
        prefix = "X" * 350  # push 'hybrid' past the 300-char window
        ctx = _run_triage({
            "work_postalCode": "8910",
            "title": "Prosjektleder",
            "description_html": f"{prefix} hybrid arbeidsform.",
        })
        assert ctx.triage.triage_decision == "SKIP", \
            "Hybrid deep in description should NOT bypass geo block (false-pass regression)"
        assert any("geo" in s for s in ctx.triage.signals)


# ---------------------------------------------------------------------------
# County fallback (no postal code)
# ---------------------------------------------------------------------------

class TestCountyFallback:
    def test_nordland_county_blocked(self):
        """Jobs in Nordland with no postal code must be geo-SKIPped via county fallback."""
        ctx = _run_triage({"title": "Daglig leder", "work_county": "Nordland"})
        assert ctx.triage.triage_decision == "SKIP"
        assert "geo_county_skip" in ctx.triage.signals

    def test_oslo_county_allowed(self):
        """Jobs in Oslo with no postal code must NOT be geo-SKIPped."""
        with patch("jobpipe.stages.triage.build_triage_agent"), \
             patch("jobpipe.stages.triage.run_agent") as mock_run:
            from jobpipe.core.schema import TriageOut
            mock_out = MagicMock()
            mock_out.final_output_as.return_value = TriageOut(
                triage_decision="REVIEW", confidence=0.8, explanation="oslo ok", signals=[]
            )
            mock_run.return_value = mock_out
            should_run, run = triage_stage_factory(
                model="gpt-4.1-nano", max_ad_text_chars=2200,
                safety_rules=SAFETY_RULES, profile_pack="", semantic_threshold=0.0,
            )
            ctx = run(_make_ctx({"title": "Produkteier", "work_county": "Oslo"}), "/tmp")
            assert ctx.triage.triage_decision == "REVIEW"

    def test_no_postal_no_county_passes_to_llm(self):
        """Jobs with no postal code AND no county must pass to LLM (don't hard-block unknowns)."""
        with patch("jobpipe.stages.triage.build_triage_agent"), \
             patch("jobpipe.stages.triage.run_agent") as mock_run:
            from jobpipe.core.schema import TriageOut
            mock_out = MagicMock()
            mock_out.final_output_as.return_value = TriageOut(
                triage_decision="REVIEW", confidence=0.6, explanation="unknown location", signals=[]
            )
            mock_run.return_value = mock_out
            should_run, run = triage_stage_factory(
                model="gpt-4.1-nano", max_ad_text_chars=2200,
                safety_rules=SAFETY_RULES, profile_pack="", semantic_threshold=0.0,
            )
            ctx = run(_make_ctx({"title": "Produkteier"}), "/tmp")
            assert ctx.triage.triage_decision == "REVIEW", \
                "No location info should not hard-block — pass to LLM"

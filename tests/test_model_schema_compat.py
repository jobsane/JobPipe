from jobpipe.core import schema as compat_schema
from jobpipe.model import schema as model_schema


def test_core_schema_reexports_model_schema_symbols() -> None:
    assert compat_schema.JobContext is model_schema.JobContext
    assert compat_schema.RunMeta is model_schema.RunMeta
    assert compat_schema.TriageOut is model_schema.TriageOut


def test_job_context_snapshot_summary_uses_model_schema() -> None:
    ctx = model_schema.JobContext(
        meta=model_schema.RunMeta(run_id="r1", pipeline_name="pipeline.v1", created_at="2026-04-17T00:00:00Z"),
        job_id="job-1",
        job={"title": "Product Manager", "employer_name": "Example Co"},
        profile_pack="default",
    )

    assert ctx.snapshot_summary() == {
        "job_id": "job-1",
        "title": "Product Manager",
        "employer": "Example Co",
        "triage_decision": None,
        "triage_confidence": None,
        "triage_signals": [],
        "final_decision": None,
        "fit_score": None,
        "pivot_score": None,
        "confidence": None,
        # v3 scoring fields
        "triage_v3_label": None,
        "triage_v3_weighted_score": None,
        "triage_v3_confidence": None,
        "triage_v3_needs_ambiguity": None,
        "triage_ambiguity_label": None,
        # advantage assessment
        "advantage_type": None,
        "advantageous_match_score": None,
        "advantage_review_priority": None,
        # narrative strategy
        "narrative_positioning_angle": None,
        "narrative_brand_frame": None,
        # rich list/prose projections (consumed by workspace read model)
        "parsed_role_summary": "",
        "parsed_domain_tags": [],
        "parsed_tools_tech": [],
        "profile_match_overlaps": [],
        "profile_match_gaps": [],
        "profile_match_level": None,
        "pivot_why_it_matters": [],
        "pivot_potential_risk": None,
        "advantage_signals": [],
        "objection_signals": [],
        "differentiation_signals": [],
        "neutralizing_evidence": [],
        "recruiter_hook": "",
        "applicant_pool_hypothesis": "",
    }

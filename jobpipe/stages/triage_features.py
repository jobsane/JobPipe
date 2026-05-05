from __future__ import annotations

import re
from pathlib import Path

from jobpipe.core.io import write_json
from jobpipe.core.schema import FeatureScore, JobContext, TriageFeatures
from jobpipe.core.stage_cache import stable_payload_hash

_REMOTE_RE = re.compile(r"\b(remote|full[\s-]?remote|hjemmekontor|home office)\b", re.I)
_HYBRID_RE = re.compile(r"\b(hybrid|fleksibel|fleksibelt)\b", re.I)
_LEGACY_RE = re.compile(r"\b(legacy|vedlikehold|forvaltning|drift|support|on-?prem)\b", re.I)
_BUILD_RE = re.compile(r"\b(nybygg|bygge|greenfield|produktutvikling|innovasjon|plattform)\b", re.I)


def _clip_score(value: int) -> int:
    return max(0, min(100, int(value)))


def _evidence_text(ctx: JobContext) -> str:
    job = ctx.job or {}
    return "\n".join(
        filter(
            None,
            [
                str(job.get("title") or ""),
                str(job.get("description_html") or ""),
                str(job.get("remote") or ""),
                str(job.get("work_type") or ""),
                str(job.get("workArrangement") or ""),
                str(job.get("work_arrangement") or ""),
            ],
        )
    )


def build_triage_features(ctx: JobContext) -> TriageFeatures:
    fit = int((ctx.profile_match.fit_score if ctx.profile_match else 0) or 0)
    dims = ctx.profile_match.dimensions if ctx.profile_match else None
    parsed = ctx.parsed
    evidence_text = _evidence_text(ctx)

    role_fit = int((dims.role_fit if dims else fit) or 0)
    domain_fit = int((dims.domain_fit if dims else fit) or 0)
    seniority_fit = int((dims.seniority_fit if dims else fit) or 0)
    skills_fit = int((dims.skills_fit if dims else fit) or 0)

    must_count = len(parsed.requirements_must) if parsed else 0
    nice_count = len(parsed.requirements_nice) if parsed else 0
    requirement_density = _clip_score(35 + must_count * 9 + nice_count * 4)

    remote_match = bool(_REMOTE_RE.search(evidence_text))
    hybrid_match = bool(_HYBRID_RE.search(evidence_text))
    if remote_match:
        remote_veracity = 88
        geospatial_friction = 85
    elif hybrid_match:
        remote_veracity = 68
        geospatial_friction = 62
    else:
        remote_veracity = 35
        geospatial_friction = 48

    legacy_hits = len(_LEGACY_RE.findall(evidence_text))
    build_hits = len(_BUILD_RE.findall(evidence_text))
    if legacy_hits > build_hits:
        legacy_burden = _clip_score(55 - legacy_hits * 10)
    elif build_hits > legacy_hits:
        legacy_burden = _clip_score(60 + build_hits * 8)
    else:
        legacy_burden = 55

    stakeholder_complexity = _clip_score(40 + (len(parsed.responsibilities) if parsed else 0) * 6)
    autonomy_level = seniority_fit
    operating_fit = _clip_score(round((domain_fit + seniority_fit) / 2))

    return TriageFeatures(
        core_tech_alignment=FeatureScore(
            score=skills_fit,
            confidence=80 if dims else 55,
            reason="Projected from current profile-match skill fit.",
            evidence_spans=[],
        ),
        legacy_burden=FeatureScore(
            score=legacy_burden,
            confidence=60,
            reason="Keyword heuristic over current job evidence.",
            evidence_spans=[],
        ),
        role_specificity=FeatureScore(
            score=role_fit,
            confidence=80 if dims else 55,
            reason="Projected from current role-fit signal.",
            evidence_spans=[],
        ),
        requirement_density=FeatureScore(
            score=requirement_density,
            confidence=70 if parsed else 45,
            reason="Count-based heuristic from parsed requirements.",
            evidence_spans=[],
        ),
        geospatial_friction=FeatureScore(
            score=geospatial_friction,
            confidence=65,
            reason="Derived from remote/hybrid cues in current job metadata.",
            evidence_spans=[],
        ),
        remote_veracity=FeatureScore(
            score=remote_veracity,
            confidence=65,
            reason="Derived from explicit remote/hybrid wording in current job metadata.",
            evidence_spans=[],
        ),
        autonomy_level=FeatureScore(
            score=autonomy_level,
            confidence=80 if dims else 55,
            reason="Projected from current seniority-fit signal.",
            evidence_spans=[],
        ),
        stakeholder_complexity=FeatureScore(
            score=stakeholder_complexity,
            confidence=65 if parsed else 45,
            reason="Projected from parsed responsibility breadth.",
            evidence_spans=[],
        ),
        operating_fit=FeatureScore(
            score=operating_fit,
            confidence=75 if dims else 50,
            reason="Projected from current domain and seniority fit.",
            evidence_spans=[],
        ),
    )


def triage_features_artifact_path(job_dir: str) -> Path:
    return Path(job_dir) / "bridge_triage_features.json"


def persist_triage_features(job_dir: str, features: TriageFeatures) -> None:
    path = triage_features_artifact_path(job_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(str(path), features.model_dump())


def triage_features_cache_key(ctx: JobContext) -> str:
    job = ctx.job or {}
    payload = {
        "version": "triage_features.v1",
        "job": {
            "title": job.get("title"),
            "description_html": job.get("description_html"),
            "remote": job.get("remote"),
            "work_type": job.get("work_type"),
            "workArrangement": job.get("workArrangement"),
            "work_arrangement": job.get("work_arrangement"),
        },
        "parsed": ctx.parsed.model_dump() if ctx.parsed else None,
        "profile_match": ctx.profile_match.model_dump() if ctx.profile_match else None,
    }
    return stable_payload_hash(payload)


def triage_features_stage_factory():
    def should_run(ctx: JobContext) -> bool:
        return ctx.profile_match is not None or ctx.parsed is not None

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        features = build_triage_features(ctx)
        ctx.triage_features = features
        return ctx

    return should_run, run

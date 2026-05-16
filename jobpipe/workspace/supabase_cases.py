"""Supabase-backed cases capability for the canonical state migration.

Reads from the `v_actionable_cases` view (jobs ⨝ triage_decisions, pre-filtered
to non-SKIP + non-expired in the database). Replaces ArtifactCasesCapability
when the canonical migration is enabled via JOBPIPE_USE_SUPABASE_CASES=1.

Cold-start fast — single indexed SELECT instead of a per-request walk over
out_runs/. JobDesk shortlist no longer hangs on multi-thousand-case runs.

OSS single-user mode reads under the sentinel user_id (decision_sink.get_user_id);
the JobValve overlay swaps that for an auth-resolved user_id.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from jobpipe.core.decision_sink import get_user_id
from jobpipe.core.io import html_to_text

from .contracts import (
    ApplicationCaseReadModel,
    ApplicationStatus,
    CaseListItem,
    DecisionSignal,
    DecisionSignalKey,
    Recommendation,
    TailoringEffort,
    WorkMode,
)


_DEFAULT_TIMEOUT_SEC = 15
_MAX_LIST_LIMIT = 500


def _decision_to_recommendation(decision: str) -> Recommendation:
    d = (decision or "").upper()
    if "STRONG" in d and "APPLY" in d:
        return Recommendation.STRONG_APPLY
    if d == "APPLY":
        return Recommendation.APPLY
    if d.startswith("REVIEW"):
        return Recommendation.MAYBE
    return Recommendation.SKIP


def _truncate(value: Any, limit: int = 160) -> str:
    s = "" if value is None else str(value).strip()
    if len(s) <= limit:
        return s
    return s[:limit].rstrip() + "..."


def _clamp_score(raw: Any) -> int:
    try:
        n = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        n = 0
    return max(0, min(100, n))


def _score_band(score: int) -> str:
    """Match JobDesk's ScoreBand: strong / good / mixed / weak."""
    if score >= 80:
        return "strong"
    if score >= 65:
        return "good"
    if score >= 45:
        return "mixed"
    return "weak"


def _confidence_band(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


# `wk:` prefixed triage_signals are weak-keyword hits from the ad that the
# profile barely covers. Used by _extract_ats_keywords below; the rest of the
# triage_signals list is filter-pass metadata (not strengths) and never reaches
# the workspace read model.
#
# _INTERNAL_SIGNAL_PREFIXES catches the same internal markers when they leak
# into advantage_signals / objection_signals (which mix prose and tags) — see
# _filter_human_strings.
_INTERNAL_SIGNAL_PREFIXES = ("sim:", "safety:", "weak_hits:", "anchor:", "wk:")


def _wk_signals(signals: Any) -> list[str]:
    """`wk:` prefixed signals are 'weak keywords' — text the ad mentions but
    profile barely covers. Useful as ATS keywords / gap hints."""
    if not isinstance(signals, list):
        return []
    return [s[3:].strip() for s in signals if isinstance(s, str) and s.startswith("wk:") and len(s) > 3]


def _filter_human_strings(values: Any) -> list[str]:
    """Return only the prose entries from a list — skip empty strings and the
    internal snake_case markers (`strong_core_tech_alignment`, `wk:foo`, etc.)
    that AdvantageAssessmentV3 mixes into its signal lists alongside real
    prose. Used for both strengths and gaps."""
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if not isinstance(v, str):
            continue
        s = v.strip()
        if not s or s.lower() in seen:
            continue
        # Drop the internal markers — single snake_case token, no spaces.
        if " " not in s and "_" in s and s == s.lower():
            continue
        if any(s.startswith(p) for p in _INTERNAL_SIGNAL_PREFIXES):
            continue
        seen.add(s.lower())
        out.append(s)
    return out


def _rationale_can_do(overlaps: list[str], score: int) -> str:
    """What the profile actually overlaps with in the ad.

    Only real profile_match.overlaps are surfaced as evidence — triage_signals
    tags ("geo", "offentlig") and wk:* weak-keyword hits are filter-pass
    markers, not profile evidence, so they aren't dressed up as can-do
    rationale. When no real overlap exists, return score-based prose.
    """
    if overlaps:
        first = overlaps[0]
        if len(overlaps) >= 2:
            return f"{first}; {overlaps[1]}"
        return first
    if score >= 70:
        return f"Aggregert fit {score} uten konkrete profil-treff å peke på"
    return f"Aggregert fit {score} — under terskel for klar match"


def _rationale_can_get(recruiter_hook: str, advantage_type: str, score: int) -> str:
    """How realistic the case looks against the likely competing field."""
    if recruiter_hook:
        return recruiter_hook
    if advantage_type == "strong_fit":
        return f"Strong fit ({score}) — direkte konkurransedyktig profil"
    if advantage_type == "advantageous_mismatch":
        return f"Advantageous mismatch ({score}) — uvanlig vinkel kan gi forsprang"
    if advantage_type == "stretch_review":
        return f"Stretch ({score}) — må overbevise mot mer åpenbare kandidater"
    if advantage_type == "weak_case":
        return f"Weak case ({score}) — sterkere kandidater finnes sannsynligvis"
    return f"Konkurransebilde uavklart ({score})"


def _rationale_should_want(why_it_matters: list[str], score: int) -> str:
    """Pivot/motivation strength — whether this case moves the candidate in
    the direction they actually want to go."""
    if why_it_matters:
        return why_it_matters[0]
    if score >= 80:
        return f"Pivot-styrke {score} — motivasjonen kan bære saken"
    if score >= 60:
        return f"Pivot-styrke {score} — moderat retningstreff"
    if score >= 40:
        return f"Pivot-styrke {score} — svak retningsstemning"
    return f"Pivot-styrke {score} — utenfor ønsket retning"


def _rationale_can_explain(hypothesis: str, score: int, triage_label: str) -> str:
    """How confidently the triage model thinks the story can be told."""
    if hypothesis:
        return hypothesis
    if score >= 80:
        return f"Modellkonfidans {score} — story bør være lett å ramme inn"
    if score >= 65:
        return f"Modellkonfidans {score} — story trenger en tydelig vinkel"
    if triage_label == "discard":
        return f"Modellkonfidans {score} — modellen ville droppet saken, story må overstyre"
    return f"Modellkonfidans {score} — story-grunnlaget er tynt"


def _build_dimensions(signals: dict[str, Any], score: int) -> list[DecisionSignal]:
    """Derive four distinct rationales from the deterministic triage features.

    Preference order per slot:
      can_do      — profile_match_overlaps → humanized triage_signals → wk: keywords → score prose
      can_get     — recruiter_hook → advantage_type prose → score prose
      should_want — pivot_why_it_matters → pivot_score prose
      can_explain — applicant_pool_hypothesis → triage_v3_confidence prose

    Score mapping unchanged:
      can_do      ← triage_v3_weighted_score
      can_get     ← advantageous_match_score
      should_want ← pivot_score
      can_explain ← triage_v3_confidence

    Pre-2026-05-16 this leaned on narrative_positioning_angle and
    narrative_brand_frame, but those were template strings (no LLM prose)
    that surfaced in 2-3 slots simultaneously — see commit db545d2 disabling
    narrative_strategy_v3 and the snapshot_summary projection upgrade that
    landed the rich fields below.
    """
    def _pick(key: str, fallback: int) -> int:
        return _clamp_score(signals.get(key) if isinstance(signals.get(key), (int, float)) else fallback)

    can_do = _pick("triage_v3_weighted_score", score)
    can_get = _pick("advantageous_match_score", score)
    should_want = _pick("pivot_score", score)
    can_explain = _pick("triage_v3_confidence", score)

    confidence = _confidence_band(_clamp_score(signals.get("triage_v3_confidence")))
    overlaps = _filter_human_strings(signals.get("profile_match_overlaps"))
    why_it_matters = _filter_human_strings(signals.get("pivot_why_it_matters"))
    recruiter_hook = str(signals.get("recruiter_hook") or "").strip()
    applicant_pool_hypothesis = str(signals.get("applicant_pool_hypothesis") or "").strip()
    advantage_type = str(signals.get("advantage_type") or "").lower()
    triage_label = str(signals.get("triage_v3_label") or "").lower()

    return [
        DecisionSignal(
            key=DecisionSignalKey.CAN_DO,
            label="Can do",
            score=can_do,
            band=_score_band(can_do),
            rationale=_rationale_can_do(overlaps, can_do),
            confidence=confidence,
        ),
        DecisionSignal(
            key=DecisionSignalKey.CAN_GET,
            label="Can get",
            score=can_get,
            band=_score_band(can_get),
            rationale=_rationale_can_get(recruiter_hook, advantage_type, can_get),
            confidence=confidence,
        ),
        DecisionSignal(
            key=DecisionSignalKey.SHOULD_WANT,
            label="Should want",
            score=should_want,
            band=_score_band(should_want),
            rationale=_rationale_should_want(why_it_matters, should_want),
            confidence=confidence,
        ),
        DecisionSignal(
            key=DecisionSignalKey.CAN_EXPLAIN,
            label="Can explain",
            score=can_explain,
            band=_score_band(can_explain),
            rationale=_rationale_can_explain(applicant_pool_hypothesis, can_explain, triage_label),
            confidence=confidence,
        ),
    ]


def _extract_ats_keywords(row: dict[str, Any], signals: dict[str, Any]) -> list[str]:
    """Best-available ATS keyword set.

    Preference order:
      1. parsed_domain_tags + parsed_tools_tech — concrete terms extracted by
         the parse stage from the ad itself (e.g. "Nettverk", "ServiceNow",
         "Skole", "Digital eksamen"). These are real ATS-relevant keywords
         that the resume and value proposition should hit.
      2. Legacy fallback for rows decided before the parse projection landed:
         occupation_level1/2 (broad taxonomy) + wk:* weak-keyword triage
         signals (terms the ad mentions but the profile barely covers).
    """
    out: list[str] = []
    seen: set[str] = set()

    parsed_domain = signals.get("parsed_domain_tags") or []
    parsed_tools = signals.get("parsed_tools_tech") or []
    parsed_keywords = [
        kw.strip()
        for kw in [*parsed_domain, *parsed_tools]
        if isinstance(kw, str) and kw.strip()
    ]
    if parsed_keywords:
        for kw in parsed_keywords:
            key = kw.lower()
            if key not in seen:
                seen.add(key)
                out.append(kw)
        return out[:12]

    # Legacy fallback path
    for v in (row.get("occupation_level1"), row.get("occupation_level2")):
        if isinstance(v, str) and v.strip():
            key = v.strip().lower()
            if key not in seen:
                seen.add(key)
                out.append(v.strip())
    for kw in _wk_signals(signals.get("triage_signals")):
        key = kw.lower()
        if key not in seen and len(kw) > 1:
            seen.add(key)
            out.append(kw)
    return out[:12]


def _build_strengths_gaps(signals: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Strengths = concrete profile↔ad overlaps from profile_match.
    Gaps     = concrete profile↔ad gaps from profile_match.

    Only the pipeline's real overlaps/gaps surface. triage_signals tags
    ("geo", "offentlig") and wk:* keywords are filter-pass markers, not
    candidate strengths, so they don't get dressed up as strengths. When
    profile_match data is missing (legacy rows, failed run), both lists
    return empty and the UI shows the honest empty state.

    No truncation cap — the profile_match prompt enforces "Normalt 2-8
    punkter, men 0-1 er riktig hvis profilen dekker det meste". Trust the
    prompt; surface the realistic list to the user.
    """
    overlaps = _filter_human_strings(signals.get("profile_match_overlaps"))
    real_gaps = _filter_human_strings(signals.get("profile_match_gaps"))
    return overlaps, real_gaps


def _resolve_source_url(row: dict[str, Any]) -> str:
    """Canonical "read the ad" URL.

    NAV-sourced jobs link to arbeidsplassen.nav.no (the public NAV listing
    for the same UUID). Jobs from other connectors (finn.no, LinkedIn,
    manual employer pages) use whatever application_url they came with —
    those scrapes typically point at the original posting.
    """
    source = str(row.get("source") or "").lower().strip()
    job_id = str(row.get("job_id") or "").strip()
    if source == "nav" and job_id:
        return f"https://arbeidsplassen.nav.no/stillinger/stilling/{job_id}"
    return str(row.get("application_url") or "")


def _row_to_read_model(row: dict[str, Any]) -> ApplicationCaseReadModel:
    decision = row.get("decision") or ""
    score = _clamp_score(row.get("score"))
    deadline = (row.get("application_due") or "").strip()
    if not deadline and row.get("expires_at"):
        deadline = str(row["expires_at"])[:10]  # ISO date prefix

    raw_signals = row.get("signals") or {}
    if isinstance(raw_signals, str):
        try:
            raw_signals = json.loads(raw_signals)
        except json.JSONDecodeError:
            raw_signals = {}
    if not isinstance(raw_signals, dict):
        raw_signals = {}

    # Preference order for the Job context summary:
    #   1. parse-stage role_summary — concise factual 2-sentence description
    #      crafted from the ad's structured fields. The right answer.
    #   2. raw ad description, HTML-stripped — fallback for legacy rows
    #      decided before the parse projection landed (no parsed_role_summary
    #      in their signals).
    # narrative_strategy_v3.positioning_angle was templated text (not LLM
    # prose) and is now disabled — see commit db545d2.
    role_summary = str(raw_signals.get("parsed_role_summary") or "").strip()
    summary = role_summary or html_to_text(str(row.get("description") or ""), max_chars=500)

    strengths, gaps = _build_strengths_gaps(raw_signals)
    dimensions = _build_dimensions(raw_signals, score)
    ats_keywords = _extract_ats_keywords(row, raw_signals)

    return ApplicationCaseReadModel(
        id=str(row.get("job_id") or ""),
        company=_truncate(row.get("employer"), 80) or "Unknown",
        role=_truncate(row.get("role") or row.get("title"), 80) or "Unknown",
        location=_truncate(row.get("location") or row.get("municipality"), 80),
        work_mode=WorkMode.UNKNOWN,
        deadline=deadline,
        source_url=_resolve_source_url(row),
        application_url=str(row.get("application_url") or ""),
        summary=summary,
        ats_keywords=ats_keywords,
        score=score,
        recommendation=_decision_to_recommendation(decision),
        application_status=ApplicationStatus.DRAFTING,
        tailoring_effort=TailoringEffort.MEDIUM,
        decision_signals=dimensions,
        strengths=strengths,
        gaps=gaps,
        evidence=[],
        artifacts=[],
        next_action="Open review",
        decided_at=str(row.get("decided_at") or ""),
        job_updated_at=str(row.get("job_updated_at") or ""),
        job_posted_at=str(row.get("published_at") or ""),
    )


@dataclass(frozen=True)
class SupabaseCasesCapability:
    """Cases capability backed by the v_actionable_cases Supabase view.

    One indexed SELECT per request. No file walks, no per-case JSON reads.

    Per-instance memoization: when workspace_server's /cases handler calls
    list() then get(item.id) for each row (to enrich the summary), the get()
    calls hit the cached row from the prior list() — avoiding N+1 HTTP
    queries to Supabase. Cache lifetime = one request (one capability
    instance, constructed fresh in _resolve_hub).
    """

    supabase_url: str
    supabase_key: str
    user_id: str = field(default_factory=get_user_id)
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC

    def _query(self, where_extra: str = "", limit: Optional[int] = None) -> list[dict[str, Any]]:
        params = [f"user_id=eq.{self.user_id}"]
        if where_extra:
            params.append(where_extra)
        params.append(f"limit={limit or _MAX_LIST_LIMIT}")
        params.append("order=score.desc.nullslast,decided_at.desc")
        endpoint = f"{self.supabase_url.rstrip('/')}/rest/v1/v_actionable_cases?{'&'.join(params)}"
        req = Request(
            endpoint,
            headers={
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                if resp.status >= 400:
                    return []
                return json.load(resp)
        except (HTTPError, URLError, TimeoutError, OSError):
            return []

    def _list_rows(self) -> list[dict[str, Any]]:
        cached = getattr(self, "_list_cache", None)
        if cached is not None:
            return cached
        rows = self._query()
        # Build job_id index too so get() can hit cache
        index = {str(r.get("job_id") or ""): r for r in rows if r.get("job_id")}
        object.__setattr__(self, "_list_cache", rows)
        object.__setattr__(self, "_list_index", index)
        return rows

    def list(self, candidate_id: str = "default") -> list[CaseListItem]:  # noqa: ARG002
        return [_row_to_read_model(row).to_list_item() for row in self._list_rows()]

    def get(
        self,
        case_id: str,
        candidate_id: str = "default",  # noqa: ARG002
    ) -> ApplicationCaseReadModel | None:
        # Hit the per-request list cache first if present (avoids N+1).
        index = getattr(self, "_list_index", None)
        if index is not None and case_id in index:
            return _row_to_read_model(index[case_id])
        # Cold get (case-detail page hits this directly).
        rows = self._query(where_extra=f"job_id=eq.{quote(case_id, safe='')}", limit=1)
        if not rows:
            return None
        return _row_to_read_model(rows[0])


def from_env() -> Optional[SupabaseCasesCapability]:
    """Construct from JOBPIPE_SUPABASE_URL / KEY env. Returns None if not set."""
    url = os.environ.get("JOBPIPE_SUPABASE_URL")
    key = os.environ.get("JOBPIPE_SUPABASE_KEY")
    if not url or not key:
        return None
    return SupabaseCasesCapability(supabase_url=url, supabase_key=key)


@dataclass(frozen=True)
class SupabaseWorkspaceHub:
    """ApplicationWorkspaceHub backed by Supabase. Parallel to ArtifactWorkspaceHub
    but pulling from the canonical state store instead of file artifacts.

    The single hub instance is reusable across requests — the underlying
    SupabaseCasesCapability holds no per-run cache; each call re-queries
    the view.
    """

    capability: SupabaseCasesCapability

    @property
    def cases(self) -> SupabaseCasesCapability:
        return self.capability


def hub_from_env() -> Optional[SupabaseWorkspaceHub]:
    """Construct a hub from env. Returns None if Supabase isn't configured."""
    cap = from_env()
    if cap is None:
        return None
    return SupabaseWorkspaceHub(capability=cap)

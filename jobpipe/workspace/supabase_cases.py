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


# triage_signals mixes human-readable tags with internal markers like
# "sim:0.59", "safety:weak", "weak_hits:6", "anchor:0", "wk:digitale løsninger".
# Filter to the human ones for display in strengths / mainStrength.
_INTERNAL_SIGNAL_PREFIXES = ("sim:", "safety:", "weak_hits:", "anchor:", "wk:")


def _filter_human_signals(signals: Any) -> list[str]:
    if not isinstance(signals, list):
        return []
    out: list[str] = []
    for s in signals:
        if not isinstance(s, str):
            continue
        s = s.strip()
        if not s or any(s.startswith(p) for p in _INTERNAL_SIGNAL_PREFIXES):
            continue
        out.append(s)
    return out


def _wk_signals(signals: Any) -> list[str]:
    """`wk:` prefixed signals are 'weak keywords' — text the ad mentions but
    profile barely covers. Useful as ATS keywords / gap hints."""
    if not isinstance(signals, list):
        return []
    return [s[3:].strip() for s in signals if isinstance(s, str) and s.startswith("wk:") and len(s) > 3]


def _build_dimensions(signals: dict[str, Any], score: int) -> list[DecisionSignal]:
    """Derive the 4-dimension breakdown from the flat score fields in signals.

    Mapping (approximate — JobPipe's bridge_triage_features had finer
    sub-features per dimension; those aren't yet in Supabase, so we use the
    aggregate scores that ARE available):
      can_do      ← triage_v3_weighted_score (overall technical/role fit)
      can_get     ← advantageous_match_score (likelihood-to-succeed framing)
      should_want ← pivot_score (motivation / pivot strength)
      can_explain ← triage_v3_confidence (story / narrative confidence)
    """
    def _pick(key: str, fallback: int) -> int:
        return _clamp_score(signals.get(key) if isinstance(signals.get(key), (int, float)) else fallback)

    can_do = _pick("triage_v3_weighted_score", score)
    can_get = _pick("advantageous_match_score", score)
    should_want = _pick("pivot_score", score)
    can_explain = _pick("triage_v3_confidence", score)

    rationale = str(signals.get("narrative_positioning_angle") or "").strip()
    brand = str(signals.get("narrative_brand_frame") or "").strip()
    confidence = _confidence_band(_clamp_score(signals.get("triage_v3_confidence")))

    return [
        DecisionSignal(
            key=DecisionSignalKey.CAN_DO,
            label="Can do",
            score=can_do,
            band=_score_band(can_do),
            rationale=brand or rationale,
            confidence=confidence,
        ),
        DecisionSignal(
            key=DecisionSignalKey.CAN_GET,
            label="Can get",
            score=can_get,
            band=_score_band(can_get),
            rationale=str(signals.get("advantage_type") or "").replace("_", " ").title(),
            confidence=confidence,
        ),
        DecisionSignal(
            key=DecisionSignalKey.SHOULD_WANT,
            label="Should want",
            score=should_want,
            band=_score_band(should_want),
            rationale=rationale,
            confidence=confidence,
        ),
        DecisionSignal(
            key=DecisionSignalKey.CAN_EXPLAIN,
            label="Can explain",
            score=can_explain,
            band=_score_band(can_explain),
            rationale=brand or rationale,
            confidence=confidence,
        ),
    ]


def _extract_ats_keywords(row: dict[str, Any], signals: dict[str, Any]) -> list[str]:
    """Best-available ATS keyword set: occupation taxonomy + weak-keyword hints
    from triage. Pipeline doesn't yet do dedicated ATS extraction, so this
    surfaces what we have without LLM cost."""
    out: list[str] = []
    seen: set[str] = set()
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
    return out[:12]  # cap


def _build_strengths_gaps(signals: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Strengths = human-readable triage_signals (what matched).
    Gaps = surfaced from advantage_type + narrative cues when 'weak_case'."""
    strengths = _filter_human_signals(signals.get("triage_signals"))
    advantage = str(signals.get("advantage_type") or "").lower()
    gaps: list[str] = []
    brand = str(signals.get("narrative_brand_frame") or "").strip()
    if advantage in ("weak_case", "weak_fit"):
        if brand:
            gaps.append(brand)
        gaps.append("Profile match is thin — make the relevance case explicit.")
    elif advantage == "strong_fit":
        # Even strong cases sometimes have weak keywords listed; surface them as soft gaps
        wks = _wk_signals(signals.get("triage_signals"))
        if wks:
            gaps.append(f"Less-direct match on: {', '.join(wks[:5])}")
    return strengths[:8], gaps[:4]


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

    # Prefer the pipeline's narrative angle as the case summary when present —
    # it's a 1-2 sentence positioning crafted for this exact match. Fall back
    # to the raw NAV description (HTML, longer).
    narrative = str(raw_signals.get("narrative_positioning_angle") or "").strip()
    summary = narrative if narrative else _truncate(row.get("description"), 500)

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

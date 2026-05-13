"""Artifact-backed tailoring plan projection.

Projects JobPipe's per-case pipeline artifacts (``11_application_pack.json``,
``02_parsed.json``, ``03_profile_match.json``, ``10_moderator.json``) into the
workspace-safe ``TailoringPlanReadModel`` so JobDesk and JobSane can consume
the same shape JobPipe already produces.

This is read-only over the artifact run. JobSane-side write-backs live in
``state_root`` and are merged by the HTTP server, not here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .contracts import (
    BulletChange,
    ClaimStatus,
    ClaimValidation,
    CoverLetterDraftReadModel,
    KeywordCoverage,
    ProvenanceRef,
    TailoringPlanReadModel,
    TailoringPlanSource,
    ValuePropositionReadModel,
)


# Artifact filenames are versioned; we accept older names as fallbacks so
# legacy runs still project. Order = newest first.
_APPLICATION_PACK_FILES = ("11_application_pack.json", "07_application_pack.json")
_PARSED_FILES = ("02_parsed.json",)
_PROFILE_MATCH_FILES = ("03_profile_match.json",)
_MODERATOR_FILES = ("10_moderator.json",)


@dataclass(frozen=True)
class ArtifactTailoringCapability:
    """Per-run tailoring projection."""

    run_dir: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_dir", Path(self.run_dir))

    def get(
        self,
        case_id: str,
        *,
        candidate_id: str = "default",  # noqa: ARG002
    ) -> TailoringPlanReadModel | None:
        """Return the pipeline-projected tailoring plan, or ``None`` if absent.

        Absent here means "no ``application_pack`` artifact exists for this case
        in this run" — typically because the run hasn't reached the
        ``application_pack`` stage yet, or the case was SKIP'd.
        """

        job_dir = _resolve_job_dir(self.run_dir, case_id)
        if job_dir is None:
            return None

        pack = _read_first(job_dir, _APPLICATION_PACK_FILES)
        if not pack:
            return None

        parsed = _read_first(job_dir, _PARSED_FILES)
        profile_match = _read_first(job_dir, _PROFILE_MATCH_FILES)
        moderator = _read_first(job_dir, _MODERATOR_FILES)

        provenance = _pipeline_provenance(self.run_dir, case_id, job_dir)

        return TailoringPlanReadModel(
            case_id=case_id,
            source=TailoringPlanSource.PIPELINE,
            positioning_angle=_clean(pack.get("positioning_headline")),
            section_strategy=_clean_list(pack.get("cv_highlights")),
            bullet_changes=_bullet_changes_from_pack(case_id, pack, provenance),
            keyword_coverage=_keyword_coverage(parsed, profile_match),
            claim_warnings=_claim_warnings(case_id, profile_match, moderator),
            value_proposition=_value_proposition(pack, provenance),
            cover_letter=_cover_letter(pack, provenance),
            reactive_resume_url="",  # populated by JobSane on write-back
            updated_at=_artifact_mtime(job_dir, _APPLICATION_PACK_FILES),
            provenance=provenance,
        )


# ----- internals -----------------------------------------------------------


def _resolve_job_dir(run_dir: Path, case_id: str) -> Path | None:
    """Find the per-job directory for ``case_id`` inside ``run_dir``.

    Matches the artifact_cases convention: prefer a subdirectory whose
    ``00_input.json`` has ``job_id`` or ``uuid`` equal to ``case_id``, then
    fall back to a directory whose name matches ``case_id``.
    """

    if not run_dir.exists() or not run_dir.is_dir():
        return None

    direct = run_dir / case_id
    if direct.is_dir() and (direct / "00_input.json").exists():
        return direct

    for job_dir in run_dir.iterdir():
        if not job_dir.is_dir():
            continue
        input_artifact = _read_json(job_dir / "00_input.json")
        for key in ("job_id", "uuid"):
            value = _clean(input_artifact.get(key))
            if value == case_id:
                return job_dir

    return None


def _read_first(job_dir: Path, filenames: Iterable[str]) -> dict[str, Any]:
    """Return the first existing artifact's parsed JSON, or ``{}``."""

    for name in filenames:
        data = _read_json(job_dir / name)
        if data:
            return data
    return {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_list(value: Any, *, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = _clean(item)
        if text:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _artifact_mtime(job_dir: Path, filenames: Iterable[str]) -> str:
    """ISO timestamp of the newest matching artifact in ``job_dir``."""

    newest = 0.0
    for name in filenames:
        path = job_dir / name
        if path.exists():
            try:
                newest = max(newest, path.stat().st_mtime)
            except OSError:
                continue
    if newest <= 0:
        return ""
    return (
        datetime.fromtimestamp(newest, tz=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _pipeline_provenance(
    run_dir: Path, case_id: str, job_dir: Path
) -> list[ProvenanceRef]:
    """Build a single safe provenance ref pointing at the pipeline run.

    Provenance never carries filesystem paths (workspace contract rule);
    only the run id, job dir name, and a confidence indicator.
    """

    return [
        ProvenanceRef(
            source_system="jobpipe.application_pack",
            source_id=case_id,
            source_label=f"run:{run_dir.name}/{job_dir.name}",
            confidence="pipeline",
        )
    ]


def _bullet_changes_from_pack(
    case_id: str,
    pack: dict[str, Any],
    provenance: list[ProvenanceRef],
) -> list[BulletChange]:
    """JobPipe's ``cv_highlights`` are tailored bullet texts (not diffs).

    We project each highlight as a ``BulletChange`` with no original (it's
    additive / replacement guidance, not a swap). JobSane will replace these
    with concrete original→proposed pairs after a refinement pass.
    """

    highlights = _clean_list(pack.get("cv_highlights"), limit=12)
    refs = _clean_list(pack.get("cv_experience_refs"), limit=12)

    changes: list[BulletChange] = []
    for index, highlight in enumerate(highlights):
        ref = refs[index] if index < len(refs) else ""
        section = f"work:{ref}" if ref else "work"
        changes.append(
            BulletChange(
                id=f"{case_id}-bullet-{index}",
                section=_safe_section(section),
                original="",
                proposed=highlight,
                rationale=ref or "Selected by application_pack",
                confidence="pipeline",
                provenance=provenance,
            )
        )
    return changes


def _safe_section(section: str) -> str:
    """Replace path-like characters so the workspace identifier validator passes."""

    cleaned = (
        section.replace("\\", " ")
        .replace("/", " ")
        .replace(":", " - ")
        .strip()
    )
    return cleaned or "work"


def _keyword_coverage(
    parsed: dict[str, Any], profile_match: dict[str, Any]
) -> list[KeywordCoverage]:
    """Combine job-posting keywords with candidate-overlap signal.

    A keyword is ``present`` if it appears (case-insensitive substring) in any
    overlap from ``profile_match.overlaps``. Otherwise it's a coverage gap and
    we surface a placement hint pointing at the relevant resume section.
    """

    keywords: list[str] = []
    for source in ("tools_tech", "domain_tags", "requirements_must"):
        keywords.extend(_clean_list(parsed.get(source), limit=20))
    # Preserve order but dedupe (case-insensitive).
    seen: set[str] = set()
    deduped: list[str] = []
    for keyword in keywords:
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(keyword)

    overlaps_blob = " ".join(_clean_list(profile_match.get("overlaps"), limit=12)).lower()

    coverage: list[KeywordCoverage] = []
    for keyword in deduped[:20]:
        present = keyword.lower() in overlaps_blob
        coverage.append(
            KeywordCoverage(
                keyword=keyword,
                present=present,
                suggested_placement=(
                    "Already evidenced — keep" if present else "Add to summary or work bullets"
                ),
            )
        )
    return coverage


def _claim_warnings(
    case_id: str,
    profile_match: dict[str, Any],
    moderator: dict[str, Any],
) -> list[ClaimValidation]:
    """Surface gaps + hard_blockers as claim warnings for review.

    ``hard_blockers`` are upgraded to ``unsupported``; soft ``gaps`` come in as
    ``weak`` (the audience reviewing tailoring should consciously accept or
    mitigate them). Moderator ``feedback_flags`` add additional ``weak`` items.
    """

    warnings: list[ClaimValidation] = []
    seen_ids: set[str] = set()

    def _add(value: str, status: ClaimStatus, note: str = "") -> None:
        text = _clean(value)
        if not text:
            return
        # Safe id from a short slug of the claim text — no spaces, lowercase.
        slug = "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")
        if not slug:
            return
        claim_id = f"{case_id}-claim-{slug[:40]}"
        if claim_id in seen_ids:
            return
        seen_ids.add(claim_id)
        warnings.append(
            ClaimValidation(
                id=claim_id,
                claim=text,
                status=status,
                evidence_ids=[],
                note=note,
            )
        )

    for value in _clean_list(profile_match.get("hard_blockers"), limit=4):
        _add(value, ClaimStatus.UNSUPPORTED, "Hard blocker — pipeline flagged.")
    for value in _clean_list(profile_match.get("gaps"), limit=4):
        _add(value, ClaimStatus.WEAK, "Profile-match gap — mitigate or omit.")
    for value in _clean_list(moderator.get("feedback_flags"), limit=4):
        _add(value, ClaimStatus.WEAK, "Moderator flag — review wording.")

    return warnings


def _value_proposition(
    pack: dict[str, Any], provenance: list[ProvenanceRef]
) -> ValuePropositionReadModel | None:
    """Project ApplicationPackOut into the value proposition shape."""

    positioning = _clean(pack.get("positioning_headline"))
    pillars = _clean_list(pack.get("top_value_props"), limit=6)
    proof = _clean_list(pack.get("evidence_map"), limit=6)
    gap_mitigations = _clean_list(pack.get("gap_mitigations"), limit=6)
    angle = _clean(pack.get("cover_letter_angle"))

    if not any((positioning, pillars, proof, gap_mitigations, angle)):
        return None

    return ValuePropositionReadModel(
        positioning_angle=positioning,
        # ``ApplicationPackOut`` doesn't carry employer_problem explicitly — the
        # cover_letter_angle is a close proxy. JobSane refinement can fill in
        # the real value on write-back.
        employer_problem=angle,
        applicant_advantage=positioning,
        message_pillars=pillars,
        proof_points=proof,
        gap_mitigations=gap_mitigations,
        provenance=provenance,
    )


def _cover_letter(
    pack: dict[str, Any], provenance: list[ProvenanceRef]
) -> CoverLetterDraftReadModel | None:
    text = _clean(pack.get("cover_letter_text"))
    if not text:
        return None
    angle = _clean(pack.get("cover_letter_angle"))
    return CoverLetterDraftReadModel(
        text=text,
        language=_guess_language(text),
        angle=angle,
        word_count=len(text.split()),
        provenance=provenance,
    )


def _guess_language(text: str) -> str:
    """Tiny heuristic — Norwegian markers vs. English fallback.

    JobPipe produces Norwegian for nav.no jobs and English for others. We
    only need this accurate enough to set Tiptap's ``lang`` attribute; if
    we get it wrong the human editor corrects on first save.

    Strategy: require at least two distinct signals, where a signal is
    either a Norwegian-specific character (æ, ø, å) or a Norwegian function
    word that does NOT also exist as a common English word. ``for`` is the
    classic false friend — exclude it.
    """

    lower = text.lower()
    no_chars = sum(1 for ch in "æøå" if ch in lower)
    # Function words that are unambiguously Norwegian (not English homographs).
    no_words = (" og ", " som ", " med ", " ikke ", " kan ", " har ", " er ", " på ")
    no_word_hits = sum(1 for word in no_words if word in lower)
    if no_chars >= 1 or no_word_hits >= 2:
        return "nb"
    return "en"

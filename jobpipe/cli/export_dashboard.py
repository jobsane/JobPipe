"""Export ledger.sqlite to a self-contained dashboard HTML file.

Builds the canonical dashboard payload, including:
- actionable-job enrichment from per-job 00_input.json files when the ledger
  still lacks URLs/deadlines/location fields
- a tracked-source profile payload from profile_pack.md and resume.json
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from jobpipe.core.config import load_raw_config
from jobpipe.core.paths import bootstrap_private_data, get_jobpipe_paths

_PAYLOAD_SCHEMA_VERSION = "jobpipe.dashboard.v2"
_PAYLOAD_SOFT_BUDGET_BYTES = 16 * 1024 * 1024
_PAYLOAD_EVENT_HARD_CAP = 10_000
_PAYLOAD_EVENT_MIN_ROWS = 2_000
_PAYLOAD_EVENT_PRUNE_STEP = 500


def _load_config_raw(config_path: Path, overlays: Optional[List[str]] = None) -> Dict[str, Any]:
    try:
        return load_raw_config(config_path, overlays=overlays or [])
    except Exception:
        return {}


def _load_thresholds(config_path: Path, overlays: Optional[List[str]] = None) -> Dict[str, Any]:
    thresholds = _load_config_raw(config_path, overlays=overlays).get("thresholds", {})
    return thresholds if isinstance(thresholds, dict) else {}


def _build_config_snapshot(config_path: Path, overlays: Optional[List[str]] = None) -> Dict[str, Any]:
    raw = _load_config_raw(config_path, overlays=overlays)
    if not raw:
        return {}
    models = raw.get("models", {})
    stages = raw.get("stages", [])
    thresholds = raw.get("thresholds", {})
    safety_rules = raw.get("safety_rules", {})
    return {
        "pipeline_name": raw.get("pipeline_name", "jobpipe"),
        "models": models if isinstance(models, dict) else {},
        "stages": stages if isinstance(stages, list) else [],
        "thresholds": thresholds if isinstance(thresholds, dict) else {},
        "safety_rules": safety_rules if isinstance(safety_rules, dict) else {},
        "config_name": config_path.name,
        "overlay_count": len(overlays or []),
    }


def _reclassify(fit_score, pivot_score, thr: Dict[str, Any]) -> str:
    """Re-apply current YAML thresholds to produce a fresh final_decision.
    Mirrors the logic in moderate.py exactly."""
    try:
        fit = int(fit_score or 0)
        pivot = int(pivot_score or 0)
    except Exception:
        return "SKIP"

    apply_strong = int(thr.get("apply_strong_fit", 78))
    apply_fit    = int(thr.get("apply_fit", 67))
    pivot_boost  = int(thr.get("pivot_boost_apply", 78))
    review_min   = int(thr.get("review_min_fit", 30))
    review_high  = int(thr.get("review_high_min_fit", 58))

    if fit < review_min:
        return "SKIP"
    if fit < review_high:
        return "REVIEW_LOW"
    if fit >= apply_strong:
        return "APPLY_STRONGLY"
    if fit >= apply_fit:
        return "APPLY"
    return "REVIEW_HIGH" if pivot >= pivot_boost else "REVIEW_LOW"

_DETAIL_COLS = (
    "triage_explanation", "reverse_decision", "reverse_confidence",
    "reverse_rationale", "recommendation_reason", "cv_focus",
    "feedback_flags", "description_snip",
)

_ACTIONABLE = {"APPLY_STRONGLY", "APPLY", "REVIEW_HIGH", "REVIEW_LOW"}
_DATA_PLACEHOLDER = "/*__DASHBOARD_DATA__*/"
_DEFAULT_PATHS = get_jobpipe_paths()


def _default_paths():
    return get_jobpipe_paths()


def _rows_as_dicts(conn: sqlite3.Connection, sql: str) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql)]


def _json_size_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _prune_events(
    events: List[Dict[str, Any]],
    payload_base: Dict[str, Any],
    budget_bytes: int,
    max_event_rows: int,
    min_event_rows: int,
) -> tuple[List[Dict[str, Any]], int]:
    kept = list(events)
    pruned = 0

    if max_event_rows > 0 and len(kept) > max_event_rows:
        pruned += len(kept) - max_event_rows
        kept = kept[-max_event_rows:]

    base_size = _json_size_bytes(payload_base)
    while (
        kept
        and len(kept) > min_event_rows
        and (base_size + _json_size_bytes(kept)) > budget_bytes
    ):
        drop = min(_PAYLOAD_EVENT_PRUNE_STEP, len(kept) - min_event_rows)
        if drop <= 0:
            break
        kept = kept[drop:]
        pruned += drop

    return kept, pruned


def _attach_payload_meta(
    payload: Dict[str, Any],
    *,
    budget_bytes: int,
    event_rows_before: int,
    event_rows_after: int,
    pruned_event_count: int,
    max_event_rows: int,
    min_event_rows: int,
) -> None:
    meta = {
        "budget_bytes": int(budget_bytes),
        "budget_mb": round(int(budget_bytes) / 1024 / 1024, 3),
        "event_rows_before": int(event_rows_before),
        "event_rows_after": int(event_rows_after),
        "pruned_event_count": int(pruned_event_count),
        "max_event_rows": int(max_event_rows),
        "min_event_rows": int(min_event_rows),
        "size_bytes": 0,
        "size_mb": 0.0,
        "budget_state": "ok",
    }
    payload["payload_meta"] = meta
    for _ in range(2):
        size_bytes = _json_size_bytes(payload)
        meta["size_bytes"] = size_bytes
        meta["size_mb"] = round(size_bytes / 1024 / 1024, 3)
        meta["budget_state"] = "ok" if size_bytes <= budget_bytes else "over"


def _parse_raw_json(val: Any) -> Dict[str, Any]:
    if not val:
        return {}
    try:
        return json.loads(val)
    except Exception:
        return {}


def _extract_detail(row: Dict[str, Any]) -> Dict[str, Any]:
    match = _parse_raw_json(row.get("raw_match_json"))
    pivot = _parse_raw_json(row.get("raw_pivot_json"))
    mod = _parse_raw_json(row.get("raw_moderator_json"))
    return {
        "overlaps": match.get("overlaps", []),
        "gaps": match.get("gaps", []),
        "hard_blockers": match.get("hard_blockers", []),
        "match_notes": match.get("notes", ""),
        "pivot_type": pivot.get("pivot_type", ""),
        "pivot_risk": pivot.get("potential_risk", ""),
        "pivot_why": pivot.get("why_it_matters", []),
        "cv_focus_mod": mod.get("cv_focus", []),
        "feedback_flags_mod": mod.get("feedback_flags", []),
    }


def _safe_load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _pick(*vals: Any) -> Any:
    for v in vals:
        if v is not None and str(v).strip():
            return v
    return ""


def _job_dir(row: Dict[str, Any], out_dir: Path) -> Optional[Path]:
    run_id = str(row.get("run_id") or "").strip()
    job_id = str(row.get("job_id") or "").strip()
    if not run_id or not job_id:
        return None
    return out_dir / run_id / job_id


def _normalize_due(value: Any) -> str:
    due = str(value or "").strip()
    if not due:
        return ""
    if "T" in due:
        return due[:10]
    return due


def _derive_no_score_reason_label(row: Dict[str, Any]) -> str:
    reason = str(row.get("skip_reason") or "").strip()
    labels = {
        "geo": "filtered by location rules before scoring",
        "hard_no": "filtered by title rules before scoring",
        "semantic": "filtered by semantic pre-filter before scoring",
        "triage_llm": "filtered by AI triage before deeper scoring",
        "fit_floor": "fit score landed below the review floor",
        "moderate": "moderator thresholds kept this role below the action queue",
        "passed": "",
    }
    if reason in labels:
        return labels[reason]
    if row.get("fit_score") is None and row.get("final_decision") == "SKIP":
        return "filtered before deeper scoring"
    return ""


def _parse_json_array(value: Any) -> List[Dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _collect_generated_documents(row: Dict[str, Any], out_dir: Path) -> List[Dict[str, Any]]:
    persisted = _parse_json_array(row.get("generated_documents_json"))
    if persisted:
        return persisted

    job_dir = _job_dir(row, out_dir)
    if not job_dir or not job_dir.exists():
        return []

    docs: List[Dict[str, Any]] = []
    candidates = [
        ("application_pack_draft.json", "application_pack_json", "draft"),
        ("06_application_pack.json", "application_pack_json", "saved"),
        ("07_cv_highlights.docx", "cv_highlights_docx", "draft"),
        ("cover_letter_draft.txt", "cover_letter_text", "draft"),
    ]
    for filename, kind, status in candidates:
        path = job_dir / filename
        if not path.exists():
            continue
        docs.append(
            {
                "kind": kind,
                "status": status,
                "storage_path": str(path.resolve()),
            }
        )
    return docs


def _apply_threshold_view(row: Dict[str, Any], thr: Dict[str, Any]) -> None:
    if row.get("fit_score") is None or not thr:
        return
    final_decision = _reclassify(row.get("fit_score"), row.get("pivot_score"), thr)
    row["final_decision"] = final_decision
    review_min = int(thr.get("review_min_fit", 30))
    if final_decision == "SKIP":
        row["skip_reason"] = "fit_floor" if int(row.get("fit_score") or 0) < review_min else "moderate"
    else:
        row["skip_reason"] = "passed"


def _enrich_from_input(row: Dict[str, Any], out_dir: Path) -> None:
    """Fill in missing URL/deadline/location fields from per-job 00_input.json."""
    needs_employer = not (row.get("employer") or "").strip()
    needs_normalized_title = not (row.get("normalized_title") or "").strip()
    needs_application_url = not (row.get("application_url") or "").strip()
    needs_source_url = not (row.get("source_url") or "").strip()
    needs_due = not (row.get("applicationDue") or "").strip()
    needs_city = not (row.get("work_city") or "").strip()
    needs_county = not (row.get("work_county") or "").strip()
    needs_postal = not (row.get("work_postalCode") or "").strip()
    needs_job_source = not (row.get("job_source") or "").strip()
    if (
        not needs_employer
        and not needs_normalized_title
        and not needs_application_url
        and not needs_source_url
        and not needs_due
        and not needs_city
        and not needs_county
        and not needs_postal
        and not needs_job_source
    ):
        return

    job_dir = _job_dir(row, out_dir)
    if not job_dir:
        return

    input_path = job_dir / "00_input.json"
    inp = _safe_load_json(input_path)
    if not inp:
        return

    # The input file can have the job data at root level or nested under "job"
    job = inp.get("job", inp) if isinstance(inp.get("job"), dict) else inp

    if needs_employer:
        row["employer"] = _pick(
            row.get("employer"),
            job.get("employer_name"),
            job.get("employer"),
            job.get("company"),
        )
    if needs_normalized_title:
        row["normalized_title"] = _pick(
            row.get("normalized_title"),
            job.get("normalized_title"),
            row.get("title"),
            job.get("title"),
        )
    if needs_application_url:
        row["application_url"] = _pick(row.get("application_url"), job.get("applicationUrl"))
    if needs_source_url:
        row["source_url"] = _pick(row.get("source_url"), job.get("sourceurl"), job.get("link"))
    if needs_due:
        row["applicationDue"] = _pick(row.get("applicationDue"), job.get("applicationDue"))
    row["applicationDue"] = _normalize_due(row.get("applicationDue"))

    if needs_city:
        row["work_city"] = _pick(
            row.get("work_city"),
            job.get("work_city"),
            job.get("municipal"),
            job.get("municipalName"),
        )
    if needs_county:
        row["work_county"] = _pick(
            row.get("work_county"),
            job.get("work_county"),
            job.get("county"),
        )
    if needs_postal:
        row["work_postalCode"] = _pick(
            row.get("work_postalCode"),
            job.get("work_postalCode"),
            job.get("postalCode"),
        )
    if needs_job_source:
        row["job_source"] = _pick(
            row.get("job_source"),
            job.get("source"),
            job.get("job_source"),
        )


def _load_app_state(state_path: Path) -> Dict[str, Any]:
    """Load application_state.json sidecar. Returns empty dict if missing."""
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data.get("applications", {})
    except Exception:
        return {}


def _load_profile_builder_state(path: Path) -> Dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, str] = {}
    for key, value in data.items():
        if value is None:
            continue
        out[str(key)] = str(value)
    return out


def _normalize_heading_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _parse_markdown_sections(text: str) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            if current:
                current["content"] = "\n".join(current["lines"]).strip()
                sections.append(current)
            current = {
                "level": len(m.group(1)),
                "title": m.group(2).strip(),
                "key": _normalize_heading_key(m.group(2)),
                "lines": [],
            }
            continue
        if current is not None:
            current["lines"].append(line)
    if current:
        current["content"] = "\n".join(current["lines"]).strip()
        sections.append(current)
    return sections


def _section_by_title(sections: List[Dict[str, Any]], title_fragment: str) -> Dict[str, Any]:
    key = _normalize_heading_key(title_fragment)
    for section in sections:
        if key and key in section.get("key", ""):
            return section
    return {}


def _section_bullets(sections: List[Dict[str, Any]], title_fragment: str) -> List[str]:
    content = str(_section_by_title(sections, title_fragment).get("content") or "")
    items: List[str] = []
    for line in content.splitlines():
        if line.strip().startswith("- "):
            items.append(line.strip()[2:].strip())
    return items


def _section_paragraphs(sections: List[Dict[str, Any]], title_fragment: str) -> List[str]:
    content = str(_section_by_title(sections, title_fragment).get("content") or "")
    parts = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
    return [part for part in parts if not part.startswith("- ")]


def _extract_profile_basics(profile_text: str, resume: Dict[str, Any]) -> Dict[str, Any]:
    basics = resume.get("basics", {}) if isinstance(resume.get("basics"), dict) else {}
    snapshot = {}
    for line in profile_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        payload = stripped[2:]
        if ":" not in payload:
            continue
        key, value = payload.split(":", 1)
        snapshot[_normalize_heading_key(key)] = value.strip()
    return {
        "name": basics.get("name", ""),
        "label": basics.get("label", ""),
        "email": basics.get("email", ""),
        "phone": basics.get("phone", ""),
        "url": basics.get("url", ""),
        "summary": basics.get("summary", ""),
        "base": snapshot.get("base", ""),
        "languages": snapshot.get("languages", ""),
        "level": snapshot.get("level", ""),
        "positioning": snapshot.get("positioning", ""),
        "cognitive": snapshot.get("cognitive", ""),
    }


def _build_profile_payload(
    profile_path: Path,
    resume_path: Path,
    profile_draft_path: Path,
) -> Dict[str, Any]:
    profile_text = _safe_read_text(profile_path)
    resume = _safe_load_json(resume_path)
    builder_state = _load_profile_builder_state(profile_draft_path)
    sections = _parse_markdown_sections(profile_text)
    basics = _extract_profile_basics(profile_text, resume)

    target_geography = []
    for bullet in _section_bullets(sections, "Location (OK if any)"):
        target_geography.append(bullet)
    remote_policy = ""
    for line in str(_section_by_title(sections, "Location (OK if any)").get("content") or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("remote/hybrid:"):
            remote_policy = stripped.split(":", 1)[1].strip()
            break

    work_entries = resume.get("work", []) if isinstance(resume.get("work"), list) else []
    skill_entries = resume.get("skills", []) if isinstance(resume.get("skills"), list) else []
    education_entries = resume.get("education", []) if isinstance(resume.get("education"), list) else []

    evidence_highlights: List[Dict[str, str]] = []
    for entry in work_entries:
        if not isinstance(entry, dict):
            continue
        employer = str(entry.get("name", "")).strip()
        role = str(entry.get("position", "")).strip()
        for highlight in entry.get("highlights", []) or []:
            evidence_highlights.append(
                {
                    "employer": employer,
                    "role": role,
                    "text": str(highlight).strip(),
                }
            )
            if len(evidence_highlights) >= 10:
                break
        if len(evidence_highlights) >= 10:
            break

    strength_areas: List[Dict[str, Any]] = []
    for entry in skill_entries:
        if not isinstance(entry, dict):
            continue
        strength_areas.append(
            {
                "name": str(entry.get("name", "")).strip(),
                "keywords": [str(keyword).strip() for keyword in (entry.get("keywords") or []) if str(keyword).strip()],
            }
        )

    motivation_language = ""
    for section in sections:
        content = str(section.get("content") or "")
        for line in content.splitlines():
            if "Motivation language core" not in line:
                continue
            if ":" in line:
                motivation_language = line.split(":", 1)[1].strip().strip('"')
                break
        if motivation_language:
            break

    return {
        "source_files": [str(profile_path), str(resume_path)],
        "builder_state_path": str(profile_draft_path),
        "builder_state": builder_state,
        "basics": basics,
        "strategic_direction": "\n\n".join(_section_paragraphs(sections, "Strategic direction")),
        "target_roles": {
            "primary": _section_bullets(sections, "Primary targets"),
            "secondary": _section_bullets(sections, "Secondary targets"),
            "stepping_stone": _section_bullets(sections, "Stepping-stone roles"),
        },
        "target_geography": {
            "base": basics.get("base", ""),
            "locations": target_geography,
            "remote_policy": remote_policy,
        },
        "strength_areas": strength_areas,
        "evidence_highlights": evidence_highlights,
        "work": work_entries,
        "education": education_entries,
        "certificates": resume.get("certificates", []) if isinstance(resume.get("certificates"), list) else [],
        "volunteer": resume.get("volunteer", []) if isinstance(resume.get("volunteer"), list) else [],
        "motivation_language": motivation_language,
    }


def build_payload(
    sqlite_path: Path,
    out_dir: Path,
    state_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
    config_overlays: Optional[List[str]] = None,
    profile_path: Optional[Path] = None,
    resume_path: Optional[Path] = None,
    profile_draft_path: Optional[Path] = None,
    payload_budget_bytes: int = _PAYLOAD_SOFT_BUDGET_BYTES,
    max_event_rows: int = _PAYLOAD_EVENT_HARD_CAP,
    min_event_rows: int = _PAYLOAD_EVENT_MIN_ROWS,
) -> Dict[str, Any]:
    paths = _default_paths()
    app_state = _load_app_state(state_path or paths.application_state_path)
    config_path = config_path or paths.default_config_path
    resume_source = resume_path or paths.resume_json_path
    resume_fixed_source = (
        paths.resume_fixed_json_path if resume_path is None else resume_source.with_name("resume_fixed.json")
    )
    if not resume_source.exists() and resume_fixed_source.exists():
        resume_source = resume_fixed_source
    profile = _build_profile_payload(
        profile_path or paths.profile_pack_path,
        resume_source,
        profile_draft_path or paths.profile_builder_state_path,
    )
    thresholds = _load_thresholds(config_path, overlays=config_overlays)
    config_snapshot = _build_config_snapshot(config_path, overlays=config_overlays)
    conn = sqlite3.connect(str(sqlite_path))

    jobs_raw = _rows_as_dicts(conn, """
        SELECT job_id, title, employer, work_city, work_county, work_postalCode,
               applicationDue, source_url, application_url,
               job_source, job_status, suggested_by_platform, normalized_title,
               occ_level1, occ_level2, cat_type, cat_code, cat_name, cat_score,
               triage_decision, triage_confidence, triage_explanation, triage_signals,
               reverse_decision, reverse_confidence, reverse_rationale,
               fit_score, pivot_score,
               final_decision, final_confidence, recommendation_reason,
               cv_focus, feedback_flags,
               pack_ready, pack_generated_at, pack_has_cover_letter,
               pack_highlight_count, pack_docx_ready, generated_documents_json,
               description_snip,
               skip_reason,
               run_id, run_seen_at, updated_at, closed_at,
               raw_match_json, raw_pivot_json, raw_moderator_json
        FROM ledger
        ORDER BY
            CASE final_decision
                WHEN 'APPLY_STRONGLY' THEN 0
                WHEN 'APPLY' THEN 1
                WHEN 'REVIEW_HIGH' THEN 2
                WHEN 'REVIEW_LOW' THEN 3
                ELSE 4
            END,
            fit_score DESC NULLS LAST
    """)

    jobs = []
    for row in jobs_raw:
        # Re-apply current YAML thresholds so the dashboard always reflects
        # the latest config — even for jobs scored under older threshold values.
        _apply_threshold_view(row, thresholds)

        is_actionable = row.get("final_decision") in _ACTIONABLE

        if is_actionable:
            row["detail"] = _extract_detail(row)
            _enrich_from_input(row, out_dir)
        else:
            for col in _DETAIL_COLS:
                row.pop(col, None)
            row["detail"] = None

        for k in ("raw_match_json", "raw_pivot_json", "raw_moderator_json"):
            row.pop(k, None)

        row["suggested_by_platform"] = bool(row.get("suggested_by_platform"))
        row["pack_ready"] = bool(row.get("pack_ready"))
        row["pack_has_cover_letter"] = bool(row.get("pack_has_cover_letter"))
        row["pack_docx_ready"] = bool(row.get("pack_docx_ready"))
        row["no_score_reason_label"] = _derive_no_score_reason_label(row)
        row["generated_documents"] = _collect_generated_documents(row, out_dir)
        row["applicationDue"] = _normalize_due(row.get("applicationDue"))
        row.pop("generated_documents_json", None)

        # Merge application tracking state
        app_entry = app_state.get(row.get("job_id", ""), {})
        row["app_status"] = app_entry.get("status", "")
        row["app_stages"] = json.dumps(app_entry.get("stages", []), ensure_ascii=False)
        row["app_outcome"] = app_entry.get("outcome") or ""
        row["app_updated_at"] = app_entry.get("updated_at", "")
        row["app_source"] = app_entry.get("source", "")
        row["app_notes"] = app_entry.get("notes", "")

        jobs.append(row)

    events = _rows_as_dicts(conn, """
        SELECT run_id, job_id, run_mtime, seen_at,
               job_source, job_status, skip_reason,
               final_decision, triage_decision, triage_confidence,
               fit_score, pivot_score
        FROM events
        ORDER BY run_mtime
    """)

    conn.close()

    payload = {
        "schema_version": _PAYLOAD_SCHEMA_VERSION,
        "jobs": jobs,
        "events": events,
        "profile": profile,
        "thresholds": thresholds,
        "config_snapshot": config_snapshot,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    pruned_events, pruned_event_count = _prune_events(
        payload["events"],
        {k: v for k, v in payload.items() if k != "events"},
        budget_bytes=payload_budget_bytes,
        max_event_rows=max_event_rows,
        min_event_rows=min_event_rows,
    )
    payload["events"] = pruned_events
    _attach_payload_meta(
        payload,
        budget_bytes=payload_budget_bytes,
        event_rows_before=len(events),
        event_rows_after=len(pruned_events),
        pruned_event_count=pruned_event_count,
        max_event_rows=max_event_rows,
        min_event_rows=min_event_rows,
    )
    return payload


def render_dashboard_html(payload: Dict[str, Any], template_path: Path, head_injection: str = "") -> str:
    template = template_path.read_text(encoding="utf-8")
    data_json = json.dumps(payload, ensure_ascii=False, default=str)
    if _DATA_PLACEHOLDER not in template:
        raise RuntimeError(
            f"Template {template_path} is missing the data placeholder: {_DATA_PLACEHOLDER}"
        )
    html = template.replace(_DATA_PLACEHOLDER, data_json)
    if head_injection:
        if "</head>" not in html:
            raise RuntimeError(f"Template {template_path} is missing </head> for head injection")
        html = html.replace("</head>", head_injection + "\n</head>", 1)
    return html


def build_dashboard_html(
    sqlite_path: Path,
    out_dir: Path,
    template_path: Path,
    state_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
    config_overlays: Optional[List[str]] = None,
    profile_path: Optional[Path] = None,
    resume_path: Optional[Path] = None,
    profile_draft_path: Optional[Path] = None,
    head_injection: str = "",
) -> tuple[str, Dict[str, Any]]:
    payload = build_payload(
        sqlite_path,
        out_dir,
        state_path=state_path,
        config_path=config_path,
        config_overlays=config_overlays,
        profile_path=profile_path,
        resume_path=resume_path,
        profile_draft_path=profile_draft_path,
    )
    html = render_dashboard_html(payload, template_path, head_injection=head_injection)
    return html, payload


def export(sqlite_path: Path, out_dir: Path, template_path: Path, out_path: Path,
           state_path: Optional[Path] = None, config_path: Optional[Path] = None,
           config_overlays: Optional[List[str]] = None,
           profile_path: Optional[Path] = None,
           resume_path: Optional[Path] = None,
           profile_draft_path: Optional[Path] = None) -> None:
    html, payload = build_dashboard_html(
        sqlite_path,
        out_dir,
        template_path,
        state_path=state_path,
        config_path=config_path,
        config_overlays=config_overlays,
        profile_path=profile_path,
        resume_path=resume_path,
        profile_draft_path=profile_draft_path,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    n_action = sum(1 for j in payload["jobs"] if j.get("final_decision") in _ACTIONABLE)
    n_urls = sum(1 for j in payload["jobs"]
                 if j.get("final_decision") in _ACTIONABLE
                 and (j.get("application_url") or j.get("source_url")))
    n_tracked = sum(1 for j in payload["jobs"] if j.get("app_status"))
    print(f"Dashboard exported: {out_path}")
    print(f"  {len(payload['jobs'])} jobs ({n_action} actionable, {n_urls} with URLs), {len(payload['events'])} events")
    if n_tracked:
        print(f"  {n_tracked} jobs with application status tracked")
    meta = payload.get("payload_meta") or {}
    if meta:
        print(
            "  payload: "
            f"{meta.get('size_mb', 0)} MB, "
            f"events {meta.get('event_rows_after', 0)}/{meta.get('event_rows_before', 0)} "
            f"(pruned {meta.get('pruned_event_count', 0)})"
        )
        if meta.get("budget_state") != "ok":
            print("  warning: payload is still above the soft budget after event pruning")


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Build a self-contained dashboard HTML from ledger SQLite.")
    ap.add_argument(
        "--data-root",
        default="",
        help=f"JobPipe user data root (default: {_DEFAULT_PATHS.data_root})",
    )
    ap.add_argument(
        "--sqlite",
        default="",
        help=f"Path to ledger.sqlite (default: {_DEFAULT_PATHS.ledger_sqlite_path})",
    )
    ap.add_argument(
        "--out-runs",
        default="",
        help=f"Path to out_runs directory (default: {_DEFAULT_PATHS.out_runs_dir})",
    )
    ap.add_argument(
        "--template",
        default="",
        help=f"HTML template path (default: {_DEFAULT_PATHS.dashboard_template_path})",
    )
    ap.add_argument(
        "--out",
        default="",
        help=f"Output HTML path (default: {_DEFAULT_PATHS.dashboard_export_path})",
    )
    ap.add_argument(
        "--app-state",
        default="",
        help=f"Path to application_state.json (default: {_DEFAULT_PATHS.application_state_path})",
    )
    ap.add_argument(
        "--config",
        default="",
        help=f"Pipeline config YAML (default: {_DEFAULT_PATHS.default_config_path})",
    )
    ap.add_argument("--config-overlay", action="append", default=[], help="Optional config overlay YAML. Can be passed multiple times.")
    args = ap.parse_args(argv)
    paths = get_jobpipe_paths(args.data_root or None)
    bootstrap_private_data(paths, include_artifacts=True)
    export(
        Path(args.sqlite) if args.sqlite else paths.ledger_sqlite_path,
        Path(args.out_runs) if args.out_runs else paths.out_runs_dir,
        Path(args.template) if args.template else paths.dashboard_template_path,
        Path(args.out) if args.out else paths.dashboard_export_path,
        state_path=Path(args.app_state) if args.app_state else paths.application_state_path,
        config_path=Path(args.config) if args.config else paths.default_config_path,
        config_overlays=args.config_overlay,
        profile_path=paths.profile_pack_path,
        resume_path=paths.resume_json_path,
        profile_draft_path=paths.profile_builder_state_path,
    )


if __name__ == "__main__":
    main()

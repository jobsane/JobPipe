from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from agents import Runner, RunConfig

from jobpipe.core.io import html_to_text


def _clean(s: Any) -> str:
    return ("" if s is None else str(s)).strip()


def build_job_header(job: Dict[str, Any]) -> str:
    """Build a compact header used by LLM stages.
    Keep it stable and information-dense so triage/matching gets better recall.
    """
    title = _clean(job.get("title"))
    norm = _clean(job.get("normalized_title"))
    cat_name = _clean(job.get("cat_name"))
    occ1 = _clean(job.get("occ_level1"))
    occ2 = _clean(job.get("occ_level2"))

    employer = _clean(job.get("employer_name"))
    city = _clean(job.get("work_city"))
    county = _clean(job.get("work_county"))
    sector = _clean(job.get("sector"))

    status = _clean(job.get("status"))
    updated = _clean(job.get("sistEndret") or job.get("ad_updated") or job.get("ad_updated"))
    due = _clean(job.get("applicationDue"))
    sourceurl = _clean(job.get("sourceurl") or job.get("link"))
    app_url = _clean(job.get("applicationUrl"))

    lines = []
    if title:
        lines.append(f"Title: {title}")
    if norm and norm.lower() != title.lower():
        lines.append(f"Normalized title: {norm}")
    if cat_name and cat_name.lower() not in {title.lower(), norm.lower()}:
        lines.append(f"Category: {cat_name}")
    if occ1 or occ2:
        lines.append(f"Occupation: {occ1} / {occ2}".rstrip(" /"))
    if employer:
        lines.append(f"Employer: {employer}")
    if sector:
        lines.append(f"Sector: {sector}")
    if city or county:
        loc = ", ".join([x for x in [city, county] if x])
        lines.append(f"Location: {loc}")
    if status:
        lines.append(f"Status: {status}")
    if updated:
        lines.append(f"Updated: {updated}")
    if due:
        lines.append(f"Apply by: {due}")
    if sourceurl:
        lines.append(f"Source URL: {sourceurl}")
    if app_url:
        lines.append(f"Application URL: {app_url}")

    return "\n".join(lines).strip() + "\n"


def job_excerpt(job: Dict[str, Any], max_chars: int = 2200) -> str:
    """Return ad text as plain text (best-effort) and truncate."""
    raw = _clean(job.get("description_html"))
    if not raw:
        raw = _clean(job.get("description") or job.get("text") or "")
    txt = html_to_text(raw) if raw else ""
    txt = re.sub(r"\s+", " ", txt).strip()
    if max_chars and len(txt) > max_chars:
        txt = txt[: max_chars - 1] + "…"
    return txt


def run_agent(agent, input_text: str, trace: Optional[Dict[str, Any]] = None):
    """Run an Agents SDK agent synchronously with optional tracing metadata.

    Tracing can be disabled if the trace backend is flaky:
    - env OPENAI_AGENTS_DISABLE_TRACING=1  (recommended)
    """
    disable_tracing = os.getenv("OPENAI_AGENTS_DISABLE_TRACING", "").strip() in {"1", "true", "TRUE", "yes", "YES"}
    rc = RunConfig(
        # If tracing is disabled, the SDK won't attempt to send trace batches.
        tracing_disabled=disable_tracing,
        trace_metadata=trace or {},
    )
    return Runner.run_sync(agent, input_text, run_config=rc)

"""Scan Gmail for job application emails AND platform job suggestions.

TWO MODES:

1. Status scan (default) — scan for application status emails:
   Classifies emails from Jobbnorge, EasyCruit, Teamtailor, WebCruiter etc.
   as: applied, interview, or rejected.
   Matches emails to known jobs by employer name fuzzy matching.
   Never overwrites manual entries in the application state store.

2. Suggestions scan (--scan-suggestions) — scan for platform job recommendations:
   Finds FINN "Ledige stillinger" and LinkedIn "New jobs for you" alert emails.
   Extracts job URLs and stores unprocessed jobs in the primary DB suggestion queue,
   mirroring them to suggested_jobs.jsonl as a compatibility bridge so
   pull_suggested.py can fetch their full content for the pipeline.
   Platform-suggested jobs carry suggested_by_platform=true — the triage stage
   treats this as a calibration signal (lets LLM decide instead of semantic filter).

First-time setup — you need Gmail API credentials:
    1. Go to https://console.cloud.google.com/
    2. Create/select a project, enable the Gmail API
    3. Create OAuth2 credentials (Desktop app type)
    4. Download credentials.json → save it to the configured Gmail credentials path
    5. Run: jobpipe scan-gmail --setup
       (opens browser for one-time OAuth consent)

Usage:
    jobpipe scan-gmail                               # status scan, last 90 days
    jobpipe scan-gmail --dry-run                     # preview, no writes
    jobpipe scan-gmail --days 30                     # scan last 30 days
    jobpipe scan-gmail --verbose                     # show all processing
    jobpipe scan-gmail --setup                       # OAuth2 first-time setup
    jobpipe scan-gmail --scan-suggestions            # suggestion scan
    jobpipe scan-gmail --scan-suggestions --dry-run  # preview suggestions

Install deps (once):
    pip install google-auth-oauthlib google-api-python-client --break-system-packages
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from jobpipe.cli.mark_status import add_stage
from jobpipe.connectors.mail.gmail_api import (
    build_gmail_service as _build_gmail_service,
    fetch_full_message as _fetch_full_message,
    list_unique_message_ids as _list_unique_message_ids,
    setup_oauth as _setup_oauth,
)
from jobpipe.connectors.mail.messages import parse_message as _parse_message
from jobpipe.connectors.mail.status import (
    build_status_queries as _build_status_queries,
    classify_email as _classify_email,
    extract_employer as _extract_employer,
    extract_title as _extract_title,
    subject_matches_status_email as _subject_matches_status_email,
)
from jobpipe.connectors.mail.suggestions import (
    build_suggestion_queries as _build_suggestion_queries,
    catalog_placeholder_job as _catalog_placeholder_job,
    detect_suggestion_platform as _detect_suggestion_platform,
    extract_job_urls_from_payload as _extract_job_urls_from_payload,
    extract_suggestion_jobs as _extract_suggestion_jobs,
    status_source_refs as _status_source_refs,
    suggestion_external_id as _suggestion_external_id,
    suggestion_id as _suggestion_id,
    suggestion_key as _suggestion_key,
)
from jobpipe.runtime.catalog import ingest_catalog_job, load_source_record_index
from jobpipe.core.evaluation_state import load_job_catalog
from jobpipe.core.io import load_env_file
from jobpipe.core.primary_db import connect_primary_db, ensure_candidate, upsert_suggestion_lead
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices

load_env_file(".env")

DEFAULT_RUNTIME = resolve_profile_paths("default")
DEFAULT_STATE_PATH = DEFAULT_RUNTIME.application_state_path
DEFAULT_DB_PATH = DEFAULT_RUNTIME.primary_db_path
DEFAULT_SUGGESTED_PATH = DEFAULT_RUNTIME.suggested_jobs_path
DEFAULT_TOKEN_PATH = DEFAULT_RUNTIME.secrets_root / "gmail_token.json"
DEFAULT_CREDS_PATH = DEFAULT_RUNTIME.secrets_root / "gmail_credentials.json"
DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def _configure_stdout_for_windows_console() -> None:
    """Avoid cp1252 console crashes without mutating stdout at import time."""
    if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Priority order for status upgrades (higher = more final)
_STATUS_ORDER: Dict[str, int] = {
    "shortlisted": 1,
    "applied": 1,
    "interview": 2,
    "rejected": 3,
    "dismissed": 3,
}

# --- Job catalog matching ---

def _normalize(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    s = (s or "").lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_STOP_WORDS = {
    "as", "sa", "ba", "asa", "ab", "og", "i", "av", "for", "til",
    "the", "and", "of", "in", "for", "ltd", "inc", "gmbh",
}


def _employer_score(a: str, b: str) -> int:
    """Return a match score 0-3 between two employer strings."""
    na = _normalize(a)
    nb = _normalize(b)
    if not na or not nb:
        return 0
    if na == nb:
        return 3
    if na in nb or nb in na:
        return 2
    # Word overlap (ignore stop words)
    wa = set(na.split()) - _STOP_WORDS
    wb = set(nb.split()) - _STOP_WORDS
    if wa and wb:
        overlap = wa & wb
        if len(overlap) >= 2:
            return 1
        if len(overlap) == 1 and len(overlap.pop()) >= 6:
            # Single long word match (e.g. "Digitaliseringsdirektoratet")
            return 1
    return 0


def _title_score(email_title: str, job_title: str) -> int:
    """Return a match score 0-2 between email-extracted title and known job title."""
    na = _normalize(email_title)
    nb = _normalize(job_title)
    if not na or not nb:
        return 0
    if na == nb:
        return 2
    if na in nb or nb in na:
        return 1
    # Word overlap (3+ significant words)
    wa = set(na.split()) - _STOP_WORDS
    wb = set(nb.split()) - _STOP_WORDS
    if len(wa & wb) >= 2:
        return 1
    return 0


def _match_jobs(
    employer: str,
    title: str,
    job_catalog: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return a single high-confidence fuzzy match, or [] if ambiguous."""
    matches = []
    for job in job_catalog:
        escore = _employer_score(employer, job.get("employer") or "")
        tscore = _title_score(title, job.get("title") or "") if title else 0
        total = escore * 2 + tscore

        if escore >= 2:
            matches.append((total, escore, tscore, job))
        elif escore >= 1 and tscore >= 2:
            matches.append((total, escore, tscore, job))

    matches.sort(key=lambda x: (x[0], x[1], x[2], x[3].get("fit_score") or 0), reverse=True)
    if not matches:
        return []

    top = matches[0]
    if top[0] < 4:
        return []
    if len(matches) > 1 and matches[1][0] == top[0]:
        return []
    return [top[3]]


def _match_jobs_by_source_refs(
    source_refs: List[tuple[str, str]],
    source_index: Dict[tuple[str, str], Dict[str, Any]],
    job_catalog: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    resolved: list[Dict[str, Any]] = []
    seen_job_ids: set[str] = set()

    for ref in source_refs:
        row = source_index.get(ref)
        job_id = str((row or {}).get("job_id") or "").strip()
        if not job_id or job_id in seen_job_ids:
            continue
        for job in job_catalog:
            if str(job.get("job_id") or "").strip() == job_id:
                resolved.append(job)
                seen_job_ids.add(job_id)
                break

    if len(resolved) == 1:
        return resolved
    return []


# --- State helpers ---

def _load_state(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            apps = raw.get("applications", {})
            for entry in apps.values():
                if not entry.get("status"):
                    entry["status"] = _entry_effective_status(entry)
            return raw
        except Exception as e:
            print(f"Warning: could not read state file {path}: {e}", file=sys.stderr)
    return {"version": 1, "updated_at": "", "applications": {}}


def _save_state(path: Path, state: Dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _entry_effective_status(entry: Dict[str, Any]) -> str:
    status = (entry.get("status") or "").strip()
    if status:
        return status
    outcome = (entry.get("outcome") or "").strip()
    if outcome:
        return outcome
    stages = entry.get("stages", [])
    if not isinstance(stages, list):
        return ""
    for stage in ("second_interview", "interview", "applied", "called", "shortlisted"):
        if stage in stages:
            return stage
    return ""


def _cache_state_after_write(
    apps: Dict[str, Dict[str, Any]],
    job_id: str,
    status: str,
    parsed: Dict[str, Any],
    existing: Dict[str, Any],
) -> None:
    entry = dict(existing)
    entry["status"] = status
    entry["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    entry["source"] = "gmail"
    entry["email_subject"] = parsed["subject"][:120]
    entry["email_date"] = parsed["date"]
    apps[job_id] = entry


def _persist_gmail_status(
    *,
    apps: Dict[str, Dict[str, Any]],
    job_id: str,
    status: str,
    parsed: Dict[str, Any],
    existing: Dict[str, Any],
    state_path: Path,
    db_path: Path,
    candidate_id: str,
    dry_run: bool,
) -> None:
    if not dry_run:
        add_stage(
            job_id=job_id,
            token=status,
            state_path=state_path,
            notes=existing.get("notes", ""),
            source="gmail",
            email_subject=parsed["subject"][:120],
            email_date=parsed["date"],
            db_path=db_path,
            candidate_id=candidate_id,
            quiet=True,
        )
    _cache_state_after_write(apps, job_id, status, parsed, existing)


# --- Main scan ---

def scan(
    days: int = 90,
    state_path: Path = DEFAULT_STATE_PATH,
    token_path: Path = DEFAULT_TOKEN_PATH,
    creds_path: Path = DEFAULT_CREDS_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Run the Gmail scan. Returns count of new/updated state entries."""
    service = _build_gmail_service(token_path, creds_path)
    if service is None:
        return 0

    after_dt = datetime.now(timezone.utc) - timedelta(days=days)
    after_str = after_dt.strftime("%Y/%m/%d")

    print(f"Scanning Gmail for job emails (last {days} days, since {after_str[:10]})...")

    msg_ids: List[str] = []
    for query in _build_status_queries(after_str):
        try:
            msg_ids.extend(
                msg_id
                for msg_id in _list_unique_message_ids(service, [query], max_results=200)
                if msg_id not in msg_ids
            )
        except Exception as e:
            if verbose:
                print(f"  Query skipped ({query[:60]}): {e}", file=sys.stderr)

    print(f"Found {len(msg_ids)} candidate emails across all queries.")

    # Load job catalog for matching from the primary DB.
    job_catalog = load_job_catalog(
        primary_db_path=db_path,
        candidate_id=candidate_id,
    )
    source_index = load_source_record_index(db_path) if db_path.exists() else {}
    if job_catalog:
        print(f"Loaded {len(job_catalog)} jobs from the primary DB for Gmail matching.")
    else:
        print("Warning: no job catalog found in the primary DB. Gmail matching disabled.")

    state = _load_state(state_path)
    apps = state.setdefault("applications", {})

    written = 0
    skipped_manual = 0
    skipped_no_upgrade = 0
    unclassified = 0
    unmatched = 0

    for i, msg_id in enumerate(msg_ids):
        if verbose:
            print(f"  [{i+1}/{len(msg_ids)}] Fetching {msg_id}...")

        try:
            raw = _fetch_full_message(service, msg_id)
        except Exception as e:
            if verbose:
                print(f"    Error fetching {msg_id}: {e}", file=sys.stderr)
            continue

        parsed = _parse_message(raw)
        status = _classify_email(parsed["subject"], parsed["snippet"], parsed["body"])

        if not status:
            # Special case: Jobbnorge "Du har mottatt en ny melding" —
            # the actual message is behind their login wall so we can't
            # classify it, but we can tell the user to check manually.
            is_jobbnorge_message = (
                "jobbnorge" in parsed["sender"].lower()
                and "melding" in parsed["subject"].lower()
                and "bekreftelse" not in parsed["subject"].lower()
            )
            if is_jobbnorge_message:
                emp = _extract_employer(
                    parsed["subject"], parsed["snippet"], parsed["sender"], parsed["body"]
                )
                print(
                    f"  [!] MANUAL CHECK  {emp or '(unknown employer)':<36}"
                    f"  Jobbnorge message - log in to read it"
                )
                if verbose:
                    print(f"    date={parsed['date']}  subject='{parsed['subject'][:60]}'")
            else:
                unclassified += 1
                if verbose:
                    print(f"    Unclassified: {parsed['subject'][:70]}")
            continue

        employer = _extract_employer(
            parsed["subject"], parsed["snippet"], parsed["sender"], parsed["body"]
        )
        title = _extract_title(parsed["subject"], parsed["body"])
        source_refs = _status_source_refs(raw)
        matched = _match_jobs_by_source_refs(source_refs, source_index, job_catalog)
        if not matched:
            matched = _match_jobs(employer, title, job_catalog)

        if not matched:
            unmatched += 1
            if verbose:
                print(
                    f"    No known-job match: [{status}] '{parsed['subject'][:50]}'"
                    f"  employer='{employer}'  title='{title}' refs={source_refs!r}"
                )
            continue

        for job in matched:
            job_id = job["job_id"]
            existing = apps.get(job_id, {})

            # Preserve all manual entries unconditionally
            if existing.get("source") == "manual":
                skipped_manual += 1
                if verbose:
                    print(f"    Preserve manual: {job_id}")
                continue

            # Only upgrade status (applied→interview→rejected), never downgrade
            existing_order = _STATUS_ORDER.get(existing.get("status", ""), 0)
            new_order = _STATUS_ORDER.get(status, 0)
            if existing.get("status") and new_order <= existing_order:
                skipped_no_upgrade += 1
                if verbose:
                    print(
                        f"    No upgrade: {job_id}  {existing.get('status')} → {status}"
                    )
                continue

            prefix = "[DRY RUN] " if dry_run else ""
            mark = "~" if dry_run else "[OK]"
            print(
                f"  {prefix}{mark} {status.upper():<12}"
                f"  {(job.get('employer') or '')[:32]:<34}"
                f"  {(job.get('title') or '')[:42]}"
            )
            if verbose:
                print(f"    job_id={job_id}  subject='{parsed['subject'][:60]}'  date={parsed['date']}")

            if not dry_run:
                written += 1
            _persist_gmail_status(
                apps=apps,
                job_id=job_id,
                status=status,
                parsed=parsed,
                existing=existing,
                state_path=state_path,
                db_path=db_path,
                candidate_id=candidate_id,
                dry_run=dry_run,
            )

    if not dry_run and written:
        print(f"\n[OK] Saved {written} new/updated entries to {state_path} and {db_path}")

    print(
        f"\nSummary: classified={len(msg_ids)-unclassified}  unclassified={unclassified}  "
        f"unmatched={unmatched}  manual_preserved={skipped_manual}  "
        f"no_upgrade={skipped_no_upgrade}  written={written}"
    )
    return written


# --- Suggestion scan ---


def _load_existing_suggestion_keys(
    suggested_path: Path,
    db_path: Path,
    candidate_id: str,
) -> set[str]:
    """Build the dedup key set for the suggestion queue from canonical state.

    Reads the primary DB's suggestion leads (authoritative) and the legacy
    suggested_jobs.jsonl sidecar (compatibility bridge). This is orchestrator-
    level state access and intentionally lives outside jobpipe/connectors/mail
    to keep the connector slice dependency-free of canonical state.
    """
    from jobpipe.core.primary_db import connect_primary_db, list_suggestion_leads

    keys: set[str] = set()

    if db_path.exists():
        try:
            conn = connect_primary_db(db_path)
            try:
                for row in list_suggestion_leads(conn, candidate_id):
                    platform = str(row.get("platform") or "").strip()
                    external_id = str(row.get("external_id") or "").strip()
                    if platform and external_id:
                        keys.add(_suggestion_key(platform, external_id))
            finally:
                conn.close()
        except Exception:
            pass

    if suggested_path.exists():
        try:
            for line in suggested_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                platform = str(entry.get("platform") or "").strip()
                external_id = _suggestion_external_id(entry)
                if platform and external_id:
                    keys.add(_suggestion_key(platform, external_id))
        except Exception:
            pass

    return keys


def scan_suggestions(
    days: int = 90,
    suggested_path: Path = DEFAULT_SUGGESTED_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    token_path: Path = DEFAULT_TOKEN_PATH,
    creds_path: Path = DEFAULT_CREDS_PATH,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Scan Gmail for FINN/LinkedIn job suggestion emails.

    Extracts job URLs from platform recommendation emails, cross-references with
    known jobs, and queues new/unprocessed suggestions to suggested_jobs.jsonl.

    Calibration value: platform-suggested jobs are ground-truth positives from
    the platform's own recommendation algorithm. Jobs in the queue carry
    suggested_by_platform=true when fed to the pipeline — the triage stage uses
    this to prevent the semantic filter from killing them before the LLM sees them.

    Returns count of new jobs written to the queue.
    """
    service = _build_gmail_service(token_path, creds_path)
    if service is None:
        return 0

    after_dt = datetime.now(timezone.utc) - timedelta(days=days)
    after_str = after_dt.strftime("%Y/%m/%d")

    print(f"Scanning Gmail for job suggestion emails (last {days} days, since {after_str[:10]})...")

    msg_ids: List[str] = []
    for query in _build_suggestion_queries(after_str):
        try:
            msg_ids.extend(
                msg_id
                for msg_id in _list_unique_message_ids(service, [query], max_results=100)
                if msg_id not in msg_ids
            )
        except Exception as e:
            if verbose:
                print(f"  Query skipped ({query[:60]}): {e}", file=sys.stderr)

    print(f"Found {len(msg_ids)} candidate suggestion emails.")

    source_index = load_source_record_index(db_path) if db_path.exists() else {}

    # Load existing queue to avoid duplicates across runs.
    # Prefer the primary DB, but still include the legacy JSONL sidecar as a bridge.
    existing_queue_keys = _load_existing_suggestion_keys(suggested_path, db_path, candidate_id)

    finn_total = 0
    linkedin_total = 0
    already_known = 0
    new_queued: List[Dict[str, Any]] = []
    emails_with_jobs = 0
    catalog_conn = None
    if not dry_run:
        try:
            catalog_conn = connect_primary_db(db_path)
            ensure_candidate(catalog_conn, candidate_id=candidate_id)
        except Exception:
            catalog_conn = None

    for i, msg_id in enumerate(msg_ids):
        if verbose:
            print(f"  [{i+1}/{len(msg_ids)}] Fetching {msg_id}...")

        try:
            raw = _fetch_full_message(service, msg_id)
        except Exception as e:
            if verbose:
                print(f"    Error: {e}", file=sys.stderr)
            continue

        headers = {
            h["name"].lower(): h["value"]
            for h in raw.get("payload", {}).get("headers", [])
        }
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        date_str = headers.get("date", "")

        email_date = ""
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            email_date = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

        detected_platform = _detect_suggestion_platform(sender, subject)
        if not detected_platform:
            if verbose:
                print(f"    Skip (not finn/linkedin sender): '{sender[:40]}'")
            continue

        # Skip known status emails to avoid double-counting
        # (status emails have different subjects; skip if they match status patterns)
        is_status_email = _subject_matches_status_email(subject)
        if is_status_email:
            if verbose:
                print(f"    Skip (status email): '{subject[:60]}'")
            continue

        urls = _extract_job_urls_from_payload(raw.get("payload", {}))
        jobs = _extract_suggestion_jobs(urls)

        if not jobs:
            if verbose:
                print(f"    No job URLs: '{subject[:70]}' from {sender[:40]}")
            continue

        emails_with_jobs += 1
        platform_label = "FINN" if detected_platform == "finn" else "LinkedIn"

        for job in jobs:
            platform = job["platform"]
            if platform == "finn":
                finn_total += 1
            else:
                linkedin_total += 1

            external_id = _suggestion_external_id(job)
            dedup_key = _suggestion_key(platform, external_id)

            if not external_id:
                continue

            source_ref = (platform, external_id)
            known_source = source_index.get(source_ref)

            if not known_source and catalog_conn is not None:
                seen_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                placeholder = _catalog_placeholder_job(
                    platform=platform,
                    external_id=external_id,
                    job_url=str(job.get("job_url") or "").strip(),
                    email_subject=subject[:120],
                    suggested_at=email_date,
                )
                try:
                    ingest_result = ingest_catalog_job(
                        catalog_conn,
                        placeholder,
                        source_name=platform,
                        seen_at=seen_at,
                    )
                    known_source = {
                        "job_id": ingest_result["job_id"],
                        "needs_enrichment": bool(ingest_result["needs_enrichment"]),
                    }
                    source_index[source_ref] = known_source
                except Exception as e:
                    if verbose:
                        print(f"    [{platform_label}] Catalog ingest failed: {e}", file=sys.stderr)

            if known_source and not bool(known_source.get("needs_enrichment")):
                already_known += 1
                if verbose:
                    print(f"    [{platform_label}] Already covered in catalog: {known_source.get('job_id', '')}")
                continue

            if dedup_key in existing_queue_keys:
                if verbose:
                    print(f"    [{platform_label}] Already queued: {job.get('job_url', '')[:60]}")
                continue

            # New, not-yet-processed suggestion — add to queue
            existing_queue_keys.add(dedup_key)
            entry = {
                **job,
                "suggested_at": email_date,
                "email_subject": subject[:120],
            }
            if known_source and known_source.get("job_id"):
                entry["job_id_hint"] = str(known_source["job_id"])
            new_queued.append(entry)
            print(
                f"  [+] {platform_label:<9} {job.get('job_url', '')[:70]}"
                + (f"  (from: {email_date})" if email_date else "")
            )

    # Write to queue
    if new_queued and not dry_run:
        try:
            conn = catalog_conn or connect_primary_db(db_path)
            try:
                ensure_candidate(conn, candidate_id=candidate_id)
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                for entry in new_queued:
                    platform = str(entry.get("platform") or "").strip()
                    external_id = _suggestion_external_id(entry)
                    if not platform or not external_id:
                        continue
                    upsert_suggestion_lead(
                        conn,
                        {
                            "suggestion_id": _suggestion_id(candidate_id, platform, external_id),
                            "candidate_id": candidate_id,
                            "platform": platform,
                            "external_id": external_id,
                            "job_url": str(entry.get("job_url") or "").strip(),
                            "job_id_hint": str(entry.get("job_id_hint") or "").strip(),
                            "suggested_at": str(entry.get("suggested_at") or "").strip(),
                            "email_subject": str(entry.get("email_subject") or "").strip(),
                            "source": "gmail_suggestions",
                            "status": "queued",
                            "fetched_at": "",
                            "last_error": "",
                            "payload_json": entry,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                conn.commit()
            finally:
                if catalog_conn is None:
                    conn.close()
        except Exception as e:
            if verbose:
                print(f"Warning: primary DB suggestion write failed: {e}", file=sys.stderr)
        finally:
            if catalog_conn is not None:
                try:
                    catalog_conn.close()
                except Exception:
                    pass

        suggested_path.parent.mkdir(parents=True, exist_ok=True)
        with open(suggested_path, "a", encoding="utf-8") as f:
            for entry in new_queued:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    elif catalog_conn is not None:
        try:
            catalog_conn.commit()
            catalog_conn.close()
        except Exception:
            pass

    prefix = "[DRY RUN] " if dry_run else ""
    print(
        f"\n{prefix}Suggestion scan summary:\n"
        f"  Emails with job URLs:   {emails_with_jobs}\n"
        f"  FINN jobs found:        {finn_total}\n"
        f"  LinkedIn jobs found:    {linkedin_total}\n"
        f"  Already known:          {already_known}\n"
        f"  New / queued:           {len(new_queued)}\n"
    )
    if new_queued and not dry_run:
        print(
            f"  Stored in DB: {db_path}\n"
            f"  Fallback queue: {suggested_path}\n"
            f"  Next step:  python -m jobpipe.cli.pull_suggested\n"
            f"              (runs 09:00-19:00 Oslo time, max 20 jobs/run)"
        )
    elif new_queued and dry_run:
        print(f"  Would write to: {suggested_path} (dry run)")

    return len(new_queued)


# --- OAuth setup ---

def setup_oauth(creds_path: Path, token_path: Path) -> None:
    """Interactive one-time OAuth2 consent flow."""
    _setup_oauth(creds_path, token_path)


# --- CLI ---

def main(argv: Optional[List[str]] = None) -> None:
    _configure_stdout_for_windows_console()

    ap = argparse.ArgumentParser(
        description="Scan Gmail for job application emails and update JobPipe application state.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="default", help="Runtime profile to resolve DB/state/secret paths from")
    ap.add_argument("--data-root", default="", help="Runtime data root override for live_local profile")
    ap.add_argument("--days", type=int, default=90, help="Days back to scan (default: 90)")
    ap.add_argument("--state", default="", help="Path to the application state compatibility file")
    ap.add_argument("--db", default="", help="Path to primary jobpipe.sqlite")
    ap.add_argument("--candidate-id", default=DEFAULT_CANDIDATE_ID, help=f"Candidate ID for primary DB writes (default: {DEFAULT_CANDIDATE_ID})")
    ap.add_argument("--token", default="", help="OAuth token path (gmail_token.json)")
    ap.add_argument("--creds", default="", help="OAuth credentials path (gmail_credentials.json)")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing")
    ap.add_argument("--verbose", "-v", action="store_true", help="Show all processing details")
    ap.add_argument("--setup", action="store_true", help="Run one-time OAuth2 setup")
    ap.add_argument(
        "--scan-suggestions",
        action="store_true",
        help=(
            "Scan for FINN/LinkedIn job suggestion emails instead of status emails. "
            "Stores new suggestions in the primary DB and mirrors them to suggested_jobs.jsonl."
        ),
    )
    ap.add_argument(
        "--suggested",
        default="",
        help="Path for the suggested_jobs.jsonl compatibility bridge (used with --scan-suggestions)",
    )

    args = ap.parse_args(argv)
    runtime = resolve_profile_paths(
        args.runtime_profile,
        data_root_override=args.data_root,
        db_override=args.db,
        app_state_override=args.state,
    )
    db_path = runtime.primary_db_path
    state_path = runtime.application_state_path
    token_path = Path(args.token).expanduser().resolve() if str(args.token).strip() else (runtime.secrets_root / "gmail_token.json")
    creds_path = Path(args.creds).expanduser().resolve() if str(args.creds).strip() else (runtime.secrets_root / "gmail_credentials.json")
    suggested_path = Path(args.suggested).expanduser().resolve() if str(args.suggested).strip() else runtime.suggested_jobs_path

    if args.setup:
        setup_oauth(creds_path, token_path)
        return

    if args.scan_suggestions:
        scan_suggestions(
            days=args.days,
            suggested_path=suggested_path,
            db_path=db_path,
            candidate_id=args.candidate_id,
            token_path=token_path,
            creds_path=creds_path,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        return

    scan(
        days=args.days,
        state_path=state_path,
        token_path=token_path,
        creds_path=creds_path,
        db_path=db_path,
        candidate_id=args.candidate_id,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()

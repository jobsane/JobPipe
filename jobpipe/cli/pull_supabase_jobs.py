# jobpipe/cli/pull_supabase_jobs.py
"""Pull active jobs from the Supabase jobs table into the NAV connector JSONL.

Replaces pull_sheets_csv.py as the intake source when JOBPIPE_SUPABASE_URL
and JOBPIPE_SUPABASE_KEY are set.

Output format is identical to pull_sheets_csv.py — downstream pipeline
(drain_queue, intake_pipe, triage) is unchanged.

State file tracks the latest updated_at seen so each run is incremental.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from jobpipe.core.intake_pipe import CONNECTOR_NAV, POLICY_FULL_FEED, prepare_connector_record
from jobpipe.core.io import load_env_file, now_iso
from jobpipe.core.paths import bootstrap_private_data, get_jobpipe_paths

_DEFAULT_PATHS = get_jobpipe_paths()

_PAGE_SIZE = 1000  # Supabase default max
_DEFAULT_SUPABASE_RELATION = "jobs"
_ALLOWED_SUPABASE_RELATIONS = {"jobs", "jobs_active"}
_SENSITIVE_RAW_KEYS = ("secret", "token", "apikey", "api_key", "authorization", "service_role", "bearer")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str) -> datetime:
    if not s:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _relation_name(value: str) -> str:
    relation = _clean(value) or _DEFAULT_SUPABASE_RELATION
    if relation not in _ALLOWED_SUPABASE_RELATIONS:
        allowed = ", ".join(sorted(_ALLOWED_SUPABASE_RELATIONS))
        raise ValueError(f"Unsupported Supabase jobs relation '{relation}'. Allowed: {allowed}")
    return relation


def _json_array_text(value: object) -> str:
    if value in ("", None):
        return ""
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return json.dumps([text], ensure_ascii=False)
        if isinstance(parsed, list):
            return json.dumps(parsed, ensure_ascii=False)
        return json.dumps([parsed], ensure_ascii=False)
    return json.dumps([value], ensure_ascii=False)


def _date_prefix(value: object) -> str:
    text = _clean(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text


def _sanitize_raw_json(value: object) -> object:
    if isinstance(value, dict):
        clean: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(marker in key_text.lower() for marker in _SENSITIVE_RAW_KEYS):
                continue
            clean[key_text] = _sanitize_raw_json(item)
        return clean
    if isinstance(value, list):
        return [_sanitize_raw_json(item) for item in value]
    return value


def _latest_iso(existing: str, candidate: object) -> str:
    candidate_text = _clean(candidate)
    if not candidate_text:
        return existing
    if _parse_iso(candidate_text) > _parse_iso(existing):
        return candidate_text
    return existing


def _missing_required_fields(job: dict) -> list[str]:
    missing: list[str] = []
    if not _clean(job.get("uuid")):
        missing.append("id")
    if not (_clean(job.get("normalized_title")) or _clean(job.get("title"))):
        missing.append("title_or_role")
    if not _clean(job.get("employer_name")):
        missing.append("employer")
    if not _clean(job.get("description_html")):
        missing.append("description")
    return missing


def _fetch_json(url: str, headers: dict, retries: int = 4) -> list | dict:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            last_exc = e
            if e.code not in (429, 500, 502, 503, 504):
                break
        except (URLError, TimeoutError, OSError) as e:
            last_exc = e
        if attempt < retries:
            time.sleep(min(10, 2 ** (attempt - 1)))
    assert last_exc is not None
    raise last_exc


def fetch_all_active_jobs(
    supabase_url: str,
    supabase_key: str,
    *,
    since: str = "",
    only_changed: bool = True,
    relation: str = _DEFAULT_SUPABASE_RELATION,
    include_raw_json: bool = False,
    limit: int = 0,
) -> list[dict]:
    """Fetch all ACTIVE, non-expired jobs from Supabase, paginated."""
    base = supabase_url.rstrip("/")
    now_str = _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    relation = _relation_name(relation)
    max_rows = max(0, int(limit or 0))

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Accept": "application/json",
        "Prefer": "count=none",
    }

    # Build filter params (values must be URL-encoded — timestamps contain + signs)
    filters = [
        f"expires_at=gt.{quote(now_str, safe='')}",
    ]
    if relation == "jobs":
        filters.insert(0, "status=eq.ACTIVE")
    if only_changed and since:
        filters.append(f"updated_at=gt.{quote(since, safe='')}")

    select_cols = (
        "id,title,role,employer,municipality,county,counties,"
        "location,postal_code,description,application_url,"
        "published_at,expires_at,application_due,"
        "sector,occupation_level1,occupation_level2,"
        "extent,engagement_type,position_count,updated_at,status"
    )
    if include_raw_json:
        select_cols += ",raw_json"

    all_rows: list[dict] = []
    offset = 0

    while True:
        page_size = _PAGE_SIZE
        if max_rows:
            remaining = max_rows - len(all_rows)
            if remaining <= 0:
                break
            page_size = min(page_size, remaining)
        params = "&".join(filters + [
            f"select={select_cols}",
            "order=updated_at.asc",
            f"limit={page_size}",
            f"offset={offset}",
        ])
        url = f"{base}/rest/v1/{quote(relation, safe='')}?{params}"
        batch = _fetch_json(url, headers)
        if not isinstance(batch, list):
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    return all_rows


def _map_row(row: dict) -> dict:
    """Map a Supabase jobs row to the canonical JobPipe intake field names."""
    job_id = _clean(row.get("id"))
    application_due = _clean(row.get("application_due")) or _date_prefix(row.get("expires_at"))

    job = {
        "uuid": job_id,
        "job_id": job_id,
        # title: display headline
        "title": _clean(row.get("title")),
        # normalized_title: canonical role name — the key improvement over CSV
        "normalized_title": _clean(row.get("role")),
        "employer_name": _clean(row.get("employer")),
        "description_html": _clean(row.get("description")),
        "applicationUrl": _clean(row.get("application_url")),
        "applicationDue": application_due,
        # location fields
        "work_city": _clean(row.get("municipality") or row.get("location")),
        "work_county": _clean(row.get("county")),
        "work_postalCode": _clean(row.get("postal_code")),
        "workLocations_json": _json_array_text(row.get("counties")),
        # taxonomy
        "sector": _clean(row.get("sector")),
        "occ_level1": _clean(row.get("occupation_level1")),
        "occ_level2": _clean(row.get("occupation_level2")),
        # structured fields (bonus — additive, not in current canonical but carried through)
        "extent": _clean(row.get("extent")),
        "engagement_type": _clean(row.get("engagement_type")),
        "position_count": _clean(row.get("position_count")),
        # dates
        "published_at": _clean(row.get("published_at")),
        "updated_at": _clean(row.get("updated_at")),
        "expires_at": _clean(row.get("expires_at")),
        "ad_updated": _clean(row.get("updated_at") or row.get("published_at")),
        "sourceurl": f"https://arbeidsplassen.nav.no/stillinger/stilling/{job_id}",
        "status": _clean(row.get("status")) or "ACTIVE",
    }
    if "raw_json" in row:
        job["source_raw_json"] = _sanitize_raw_json(row.get("raw_json"))
    return job


def main() -> None:
    ap = argparse.ArgumentParser(description="Pull active jobs from Supabase into NAV connector JSONL.")
    ap.add_argument("--supabase-url", default="", help="Supabase project URL (or set JOBPIPE_SUPABASE_URL)")
    ap.add_argument("--supabase-key", default="", help="Supabase service role key (or set JOBPIPE_SUPABASE_KEY)")
    ap.add_argument("--data-root", default="", help=f"JobPipe user data root (default: {_DEFAULT_PATHS.data_root})")
    ap.add_argument("--out", default="", help=f"Output JSONL path (default: {_DEFAULT_PATHS.nav_connector_path})")
    ap.add_argument("--state", default="", help=f"State path for incremental tracking (default: {_DEFAULT_PATHS.jobs_state_path})")
    ap.add_argument("--relation", default="", help="Supabase REST relation to read: jobs or jobs_active (default: jobs; env JOBPIPE_SUPABASE_RELATION)")
    ap.add_argument("--include-raw-json", action="store_true", help="Include sanitized raw_json in local connector metadata when selected from Supabase")
    ap.add_argument("--limit", type=int, default=0, help="Maximum rows to read from Supabase (0 = no limit). Use for smoke tests.")
    ap.add_argument("--dry-run", action="store_true", help="Read and map rows, but do not write connector output or state files.")
    ap.add_argument("--only-changed", action="store_true", default=True, help="Fetch only jobs updated since last run (default: on)")
    ap.add_argument("--no-only-changed", dest="only_changed", action="store_false", help="Fetch all active jobs regardless of updated_at")
    ap.add_argument("--retries", type=int, default=4)
    # Accepted for CLI compatibility with drain_queue (Supabase always filters ACTIVE server-side)
    ap.add_argument("--status-filter", default="ACTIVE", help=argparse.SUPPRESS)
    ap.add_argument("--no-skip-expired-deadline", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    paths = get_jobpipe_paths(args.data_root or None)
    bootstrap_private_data(paths, include_artifacts=False)
    load_env_file(paths.data_root / ".env")

    supabase_url = (args.supabase_url or os.environ.get("JOBPIPE_SUPABASE_URL", "")).strip()
    supabase_key = (args.supabase_key or os.environ.get("JOBPIPE_SUPABASE_KEY", "")).strip()
    relation = _relation_name(args.relation or os.environ.get("JOBPIPE_SUPABASE_RELATION", ""))
    if not supabase_url or not supabase_key:
        raise SystemExit("Provide --supabase-url/--supabase-key or set JOBPIPE_SUPABASE_URL/JOBPIPE_SUPABASE_KEY")

    out_path = Path(args.out) if args.out else paths.nav_connector_path
    state_path = Path(args.state) if args.state else paths.jobs_state_path

    # Load previous state (reuse same state file as pull_sheets_csv for compatibility)
    prev: dict = {}
    if state_path.exists():
        try:
            prev = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

    since = prev.get("last_updated_at", "") if args.only_changed else ""

    print(f"Fetching active jobs from Supabase relation={relation} (since={since or 'all'})...")
    rows = fetch_all_active_jobs(
        supabase_url,
        supabase_key,
        since=since,
        only_changed=args.only_changed,
        relation=relation,
        include_raw_json=args.include_raw_json,
        limit=args.limit,
    )
    print(f"Fetched {len(rows)} rows from Supabase.")

    out_lines: list[str] = []
    latest_updated_at = since
    skipped_rows = 0
    skipped_missing: dict[str, int] = {}

    for row in rows:
        job = _map_row(row)
        missing = _missing_required_fields(job)
        if missing:
            skipped_rows += 1
            for field in missing:
                skipped_missing[field] = skipped_missing.get(field, 0) + 1
            continue

        connector_job = prepare_connector_record(
            job,
            connector_name=CONNECTOR_NAV,
            connector_source="nav",
            intake_channel="supabase",
            pretriage_policy=POLICY_FULL_FEED,
        )
        out_lines.append(json.dumps(connector_job, ensure_ascii=False))

        # Track latest updated_at for next incremental run
        latest_updated_at = _latest_iso(latest_updated_at, row.get("updated_at"))

    if args.dry_run:
        print(f"Dry run: would write {len(out_lines)} records to {out_path}")
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out_lines) + ("\n" if out_lines else ""))

        # Update state
        new_state = {
            "fetched_at": now_iso(),
            "source": "supabase",
            "last_updated_at": latest_updated_at or since,
            "rows": {},  # kept for compatibility with pull_sheets_csv state format
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new_state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {len(out_lines)} records to {out_path}")
    if skipped_missing:
        summary = ", ".join(f"{key}={value}" for key, value in sorted(skipped_missing.items()))
        print(f"Skipped {skipped_rows} incomplete row(s): {summary}")
    if args.dry_run:
        print(f"Dry run: state unchanged; latest_seen_updated_at={latest_updated_at or since}")
    else:
        print(f"State updated: last_updated_at={new_state['last_updated_at']}")


if __name__ == "__main__":
    main()

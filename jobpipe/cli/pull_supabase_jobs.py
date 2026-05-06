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
) -> list[dict]:
    """Fetch all ACTIVE, non-expired jobs from Supabase, paginated."""
    base = supabase_url.rstrip("/")
    now_str = _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Accept": "application/json",
        "Prefer": "count=none",
    }

    # Build filter params (values must be URL-encoded — timestamps contain + signs)
    filters = [
        "status=eq.ACTIVE",
        f"expires_at=gt.{quote(now_str, safe='')}",
    ]
    if only_changed and since:
        filters.append(f"updated_at=gt.{quote(since, safe='')}")

    select_cols = (
        "id,title,role,employer,municipality,county,counties,"
        "location,postal_code,description,application_url,"
        "published_at,expires_at,application_due,"
        "sector,occupation_level1,occupation_level2,"
        "extent,engagement_type,position_count,updated_at,status"
    )

    all_rows: list[dict] = []
    offset = 0

    while True:
        params = "&".join(filters + [
            f"select={select_cols}",
            "order=updated_at.asc",
            f"limit={_PAGE_SIZE}",
            f"offset={offset}",
        ])
        url = f"{base}/rest/v1/jobs?{params}"
        batch = _fetch_json(url, headers)
        if not isinstance(batch, list):
            break
        all_rows.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    return all_rows


def _map_row(row: dict) -> dict:
    """Map a Supabase jobs row to the canonical JobPipe intake field names."""
    job_id = str(row.get("id") or "").strip()
    counties = row.get("counties") or []

    return {
        "uuid": job_id,
        "job_id": job_id,
        # title: display headline
        "title": str(row.get("title") or "").strip(),
        # normalized_title: canonical role name — the key improvement over CSV
        "normalized_title": str(row.get("role") or "").strip(),
        "employer_name": str(row.get("employer") or "").strip(),
        "description_html": str(row.get("description") or "").strip(),
        "applicationUrl": str(row.get("application_url") or "").strip(),
        "applicationDue": str(row.get("application_due") or "").strip(),
        # location fields
        "work_city": str(row.get("municipality") or row.get("location") or "").strip(),
        "work_county": str(row.get("county") or "").strip(),
        "work_postalCode": str(row.get("postal_code") or "").strip(),
        "workLocations_json": json.dumps(counties, ensure_ascii=False) if counties else "",
        # taxonomy
        "sector": str(row.get("sector") or "").strip(),
        "occ_level1": str(row.get("occupation_level1") or "").strip(),
        "occ_level2": str(row.get("occupation_level2") or "").strip(),
        # structured fields (bonus — additive, not in current canonical but carried through)
        "extent": str(row.get("extent") or "").strip(),
        "engagement_type": str(row.get("engagement_type") or "").strip(),
        "position_count": str(row.get("position_count") or "").strip(),
        # dates
        "ad_updated": str(row.get("updated_at") or row.get("published_at") or "").strip(),
        "sourceurl": f"https://arbeidsplassen.nav.no/stillinger/stilling/{job_id}",
        "status": str(row.get("status") or "ACTIVE").strip(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Pull active jobs from Supabase into NAV connector JSONL.")
    ap.add_argument("--supabase-url", default="", help="Supabase project URL (or set JOBPIPE_SUPABASE_URL)")
    ap.add_argument("--supabase-key", default="", help="Supabase service role key (or set JOBPIPE_SUPABASE_KEY)")
    ap.add_argument("--data-root", default="", help=f"JobPipe user data root (default: {_DEFAULT_PATHS.data_root})")
    ap.add_argument("--out", default="", help=f"Output JSONL path (default: {_DEFAULT_PATHS.nav_connector_path})")
    ap.add_argument("--state", default="", help=f"State path for incremental tracking (default: {_DEFAULT_PATHS.jobs_state_path})")
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

    print(f"Fetching active jobs from Supabase (since={since or 'all'})...")
    rows = fetch_all_active_jobs(supabase_url, supabase_key, since=since, only_changed=args.only_changed)
    print(f"Fetched {len(rows)} rows from Supabase.")

    out_lines: list[str] = []
    latest_updated_at = since

    for row in rows:
        job = _map_row(row)
        if not job["uuid"]:
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
        row_updated = str(row.get("updated_at") or "").strip()
        if row_updated and row_updated > (latest_updated_at or ""):
            latest_updated_at = row_updated

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
    print(f"State updated: last_updated_at={new_state['last_updated_at']}")


if __name__ == "__main__":
    main()

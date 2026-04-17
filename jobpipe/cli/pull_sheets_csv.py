# jobpipe/cli/pull_sheets_csv.py
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time
import http.client
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from jobpipe.core.io import now_iso, stable_job_id
from jobpipe.core.paths import bootstrap_private_data, get_jobpipe_paths

_DEFAULT_PATHS = get_jobpipe_paths()


def fetch_text_with_retries(url: str, timeout: int = 120, retries: int = 4) -> str:
    """
    Fetch text from URL with basic retry/backoff. Handles transient network errors
    and IncompleteRead issues sometimes seen with large Google Sheets CSV exports.
    """
    headers = {
        "User-Agent": "jobpipe/1.0 (+pull_sheets_csv)",
        "Accept": "text/csv,text/plain,*/*",
        # identity avoids some proxy/gzip edge cases; chunked may still occur.
        "Accept-Encoding": "identity",
        "Connection": "close",
    }

    last_exc: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                # Stream to avoid one giant .read(); still accumulates in memory.
                buf = bytearray()
                while True:
                    chunk = resp.read(1024 * 1024)  # 1 MiB
                    if not chunk:
                        break
                    buf.extend(chunk)
                return buf.decode("utf-8", errors="replace")
        except http.client.IncompleteRead as e:
            last_exc = e
        except HTTPError as e:
            # Retry only for transient HTTP errors
            last_exc = e
            if e.code not in (429, 500, 502, 503, 504):
                break
        except (URLError, TimeoutError, ConnectionError, OSError) as e:
            last_exc = e

        if attempt < retries:
            # simple exponential backoff: 1s, 2s, 4s, ...
            time.sleep(min(10, 2 ** (attempt - 1)))

    assert last_exc is not None
    raise last_exc


def sheet_to_csv_url(sheet_url: str) -> str:
    # Accepts edit links; returns export CSV URL
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_url)
    if not m:
        raise ValueError("Could not find sheet ID in URL.")
    sheet_id = m.group(1)

    gid = None
    m2 = re.search(r"[?&]gid=(\d+)", sheet_url)
    if m2:
        gid = m2.group(1)
    m3 = re.search(r"#gid=(\d+)", sheet_url)
    if (gid is None) and m3:
        gid = m3.group(1)
    if gid is None:
        gid = "0"

    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def parse_iso(dt: str) -> datetime:
    if not dt:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    s = dt.strip()
    # handle trailing Z
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def stable_fallback_id(job: dict) -> str:
    """Delegate to the canonical stable_job_id (ignores uuid/id fields)."""
    return stable_job_id(job)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-url", required=False, default="", help="Google Sheet URL or leave empty if using --csv-url")
    ap.add_argument("--csv-url", default="", help="Optional direct published CSV URL")
    ap.add_argument(
        "--data-root",
        default="",
        help=f"JobPipe user data root (default: {_DEFAULT_PATHS.data_root})",
    )
    ap.add_argument("--out", default="", help=f"Output JSONL path (default: {_DEFAULT_PATHS.jobs_delta_path})")
    ap.add_argument("--state", default="", help=f"State path for incremental updates (default: {_DEFAULT_PATHS.jobs_state_path})")
    ap.add_argument("--only-changed", action="store_true", help="Write only changed/new rows")
    ap.add_argument("--no-dedupe", action="store_true", help="Disable dedupe by uuid/job_id")
    ap.add_argument("--timeout", type=int, default=120, help="HTTP timeout in seconds")
    ap.add_argument("--retries", type=int, default=4, help="HTTP retries on transient failures")
    ap.add_argument(
        "--status-filter",
        default="ACTIVE",
        metavar="STATUS",
        help="Only include rows where the 'status' column matches this value (default: ACTIVE). "
             "Pass '' or 'ALL' to disable filtering and include all rows.",
    )
    ap.add_argument(
        "--expired-out",
        default=None,
        help=f"Output JSONL for expired (ACTIVE->INACTIVE) job events (default: {_DEFAULT_PATHS.jobs_expired_path}). "
             "Set to '' to disable expiry tracking.",
    )
    ap.add_argument(
        "--skip-expired-deadline",
        action="store_true",
        default=True,
        help="Skip jobs where applicationDue is in the past (default: on).",
    )
    ap.add_argument(
        "--no-skip-expired-deadline",
        dest="skip_expired_deadline",
        action="store_false",
        help="Disable deadline filtering — include jobs with past deadlines.",
    )
    args = ap.parse_args()
    paths = get_jobpipe_paths(args.data_root or None)
    bootstrap_private_data(paths, include_artifacts=False)
    out_path = Path(args.out) if args.out else paths.jobs_delta_path
    state_path = Path(args.state) if args.state else paths.jobs_state_path
    expired_out_path = None if args.expired_out == "" else (Path(args.expired_out) if args.expired_out else paths.jobs_expired_path)

    if not args.csv_url and not args.sheet_url:
        ap.error("Provide either --csv-url or --sheet-url")

    # Determine CSV URL
    csv_url = (args.csv_url or args.sheet_url).strip()
    if "output=csv" not in csv_url and "format=csv" not in csv_url:
        csv_url = sheet_to_csv_url(csv_url)

    prev: dict = {}
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            prev = json.load(f)

    text = fetch_text_with_retries(csv_url, timeout=args.timeout, retries=args.retries)
    reader = csv.DictReader(text.splitlines())

    # Resolve status filter: '' or 'ALL' means no filtering
    status_filter = (args.status_filter or "").strip().upper()
    if status_filter in ("", "ALL"):
        status_filter = ""

    # Resolve deadline filter
    now_utc = datetime.now(timezone.utc)

    # Dedupe bucket: job_id -> best_job
    best: dict[str, dict] = {}
    best_dt: dict[str, datetime] = {}
    status_skipped = 0
    deadline_skipped = 0
    inactive_ids: set[str] = set()   # job_ids that are INACTIVE in current sheet

    for row in reader:
        # --- Status filter (pre-AI, free, eliminates ~30k INACTIVE rows) ---
        if status_filter:
            row_status = (row.get("status") or "").strip().upper()
            if row_status != status_filter:
                # Track INACTIVE job_ids for ACTIVE→INACTIVE transition detection
                uuid = (row.get("uuid") or "").strip()
                if uuid:
                    inactive_ids.add(uuid)
                status_skipped += 1
                continue

        # --- Deadline filter: skip jobs where applicationDue is in the past ---
        if args.skip_expired_deadline:
            due_raw = (row.get("applicationDue") or "").strip()
            if due_raw and due_raw.lower() not in ("snarest", "asap", "fortløpende"):
                due_dt = parse_iso(due_raw)
                # parse_iso returns epoch if unparseable — treat epoch as unknown, don't skip
                if due_dt.year > 1970 and due_dt < now_utc:
                    deadline_skipped += 1
                    continue
        job = {
            "uuid": (row.get("uuid") or "").strip(),
            "ad_updated": (row.get("ad_updated") or "").strip(),
            "sistEndret": (row.get("sistEndret") or "").strip(),
            "status": (row.get("status") or "").strip(),
            "title": (row.get("title") or "").strip(),
            "employer_name": (row.get("employer_name") or "").strip(),
            "description_html": row.get("description_html") or "",
            "sourceurl": (row.get("sourceurl") or "").strip(),
            "link": (row.get("link") or "").strip(),
            "applicationUrl": (row.get("applicationUrl") or "").strip(),
            "applicationDue": (row.get("applicationDue") or "").strip(),
            "work_city": (row.get("work_city") or "").strip(),
            "work_county": (row.get("work_county") or "").strip(),
            "sector": (row.get("sector") or "").strip(),
            # --- IMPORTANT: carry geo fields through to JSONL ---
            "work_postalCode": (
                row.get("work_postalCode")
                or row.get("work_postal_code")
                or row.get("postalCode")
                or row.get("postal_code")
                or ""
            ).strip(),
            "workLocations_json": (
                row.get("workLocations_json")
                or row.get("work_locations_json")
                or row.get("workLocations")
                or ""
            ).strip(),
        }

        # ---- Optional classification / taxonomy fields (if present in sheet) ----
        # These are valuable signals for triage/matching and cost nothing to keep.
        CLASS_KEYS = [
            "occ_level1",
            "occ_level2",
            "cat_type",
            "cat_code",
            "cat_name",
            "cat_description",
            "cat_score",
            # if you already maintain these in the sheet, we keep them too:
            "normalized_title",
            "role_family",
            "seniority",
        ]
        for k in CLASS_KEYS:
            if k in row:
                v = row.get(k)
                if v is None:
                    continue
                if isinstance(v, str):
                    v = v.strip()
                if v != "":
                    job[k] = v

        # If the feed title looks like a marketing sentence, prefer sheet classification as normalized_title.
        if not job.get("normalized_title"):
            t = job.get("title") or ""
            # crude heuristics: question mark / starts with "Vil du" / too long
            if ("?" in t) or t.lower().startswith(("vil du", "vi søker", "bli med")) or len(t) > 85:
                if job.get("cat_name"):
                    job["normalized_title"] = str(job["cat_name"])

        # Use uuid as job_id when present (best for state + idempotence)
        job_id = job["uuid"] or stable_fallback_id(job)
        job["job_id"] = job_id

        # Choose "newest" version per job_id
        dt = parse_iso(job.get("ad_updated") or job.get("sistEndret") or "")

        if args.no_dedupe:
            # keep everything (but still needs unique key in dict -> append counter)
            unique = job_id + "-" + hashlib.sha1(json.dumps(row, sort_keys=True).encode("utf-8")).hexdigest()[:8]
            job["job_id"] = unique
            best[unique] = job
            best_dt[unique] = dt
            continue

        if job_id not in best:
            best[job_id] = job
            best_dt[job_id] = dt
        else:
            # replace if newer, or if equal time but longer description (more complete)
            cur_dt = best_dt[job_id]
            if dt > cur_dt or (dt == cur_dt and len(job["description_html"]) > len(best[job_id]["description_html"])):
                best[job_id] = job
                best_dt[job_id] = dt

    out_lines: list[str] = []
    new_state = {"fetched_at": now_iso(), "rows": {}}

    # Write only changed if requested
    for job_id, job in best.items():
        # --- Normalize title before hashing/state ---
        title = (job.get("title") or "").strip()
        normalized = (job.get("normalized_title") or "").strip()
        cat_name = (job.get("cat_name") or "").strip()

        # If title is empty, fallback to normalized_title, then cat_name
        if not title:
            if normalized:
                job["title"] = normalized
            elif cat_name:
                job["title"] = cat_name

        # Optional: if title looks like marketing headline, prefer normalized_title
        title2 = (job.get("title") or "").strip()
        if normalized and (title2.endswith("?") or len(title2) > 110):
            job["title"] = normalized
        # --- end normalize ---

        blob = json.dumps(job, ensure_ascii=False, sort_keys=True)
        h = hashlib.sha1(blob.encode("utf-8")).hexdigest()
        new_state["rows"][job_id] = h

        old_h = prev.get("rows", {}).get(job_id)
        if args.only_changed and old_h == h:
            continue

        out_lines.append(json.dumps(job, ensure_ascii=False))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + ("\n" if out_lines else ""))

    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)

    # --- Detect ACTIVE → INACTIVE transitions ---
    # If a job_id was in the *previous* state (which only tracks ACTIVE jobs)
    # and is now INACTIVE in the sheet, that job has expired on NAV.
    expired_events: list[dict] = []
    expired_out = str(expired_out_path).strip() if expired_out_path else ""
    if expired_out and inactive_ids:
        prev_rows = prev.get("rows", {})
        for job_id in inactive_ids:
            if job_id in prev_rows:
                expired_events.append({
                    "_event": "expired",
                    "job_id": job_id,
                    "expired_at": now_iso(),
                })

    if expired_out:
        assert expired_out_path is not None
        expired_out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(expired_out, "w", encoding="utf-8") as f:
            for evt in expired_events:
                f.write(json.dumps(evt, ensure_ascii=False) + "\n")

    print(f"CSV URL used: {csv_url}")
    print(f"Status filter: {status_filter or 'none (all rows)'} - skipped {status_skipped} rows")
    print(f"Deadline filter: {'on' if args.skip_expired_deadline else 'off'} - skipped {deadline_skipped} rows with past deadlines")
    print(f"Read rows: {len(best)} (dedupe={'off' if args.no_dedupe else 'on'})")
    print(f"Wrote {len(out_lines)} rows to {out_path}. only_changed={args.only_changed}")
    if expired_out:
        print(f"Expired events: {len(expired_events)} (ACTIVE->INACTIVE transitions) -> {expired_out}")


if __name__ == "__main__":
    main()

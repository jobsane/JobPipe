"""Normalize FINN Chrome Extension job captures to pipeline JSONL format.

The FINN Chrome Extension capture flow writes jobs as you browse FINN.no and POSTs
them to a local Flask server
(server.py, port 5071). The server writes them to a jobs.jsonl file.

This script reads that output, normalizes it to pipeline-compatible JSONL,
deduplicates against the ledger, and writes to jobs_delta.jsonl.

These jobs are from YOUR browsing — not platform suggestions — so they carry
suggested_by_platform=false. The pipeline processes them normally.

Usage:
    python -m jobpipe.cli.pull_finn_ext --finn-jobs "C:/path/to/jobs.jsonl" --out .\\jobs_delta.jsonl
    python -m jobpipe.cli.pull_finn_ext --finn-jobs "C:/path/to/jobs.jsonl" --append
    python -m jobpipe.cli.pull_finn_ext --finn-jobs "C:/path/to/jobs.jsonl" --dry-run

FINN Chrome Extension output dir default (Windows):
    C:\\Users\\larsv\\projects\\Tools\\finn-chrome-extension\\output\\jobs.jsonl
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Windows cp1252 consoles can't encode arbitrary Unicode — wrap stdout.
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DEFAULT_LEDGER_PATH = Path("./reports/ledger.sqlite")
DEFAULT_OUT_PATH = Path("./jobs_delta.jsonl")

# Default location of FINN Chrome Extension output (Lars's machine)
DEFAULT_FINN_EXT_JOBS = (
    r"C:\Users\larsv\projects\Tools\finn-chrome-extension\output\jobs.jsonl"
)


# --- Date parsing ---

def _parse_norwegian_date(s: str) -> str:
    """Convert 'DD.MM.YYYY' or 'DD.MM.YY' → 'YYYY-MM-DD'. Returns '' on failure."""
    s = (s or "").strip()
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2})$", s)
    if m:
        d, mo, y = m.groups()
        year = 2000 + int(y) if int(y) < 50 else 1900 + int(y)
        return f"{year}-{int(mo):02d}-{int(d):02d}"
    # ISO date already?
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    return ""


def _parse_deadline(raw: dict) -> str:
    """Try all deadline field variants in the raw FINN extension record."""
    for field in ("søknadsfrist", "frist", "applicationDue", "deadline"):
        val = str(raw.get(field) or "").strip()
        if val:
            parsed = _parse_norwegian_date(val)
            if parsed:
                return parsed
    return ""


# --- Location parsing ---

def _split_sted(sted: str) -> tuple[str, str]:
    """Split 'Oslo, Akershus' into (city='Oslo', county='Akershus').
    Returns ('', '') if sted is empty."""
    if not sted:
        return "", ""
    parts = [p.strip() for p in sted.split(",")]
    city = parts[0] if parts else ""
    county = parts[1] if len(parts) > 1 else ""
    return city, county


# --- Core normalizer ---

def _normalize(raw: dict) -> Optional[dict]:
    """Convert a FINN Chrome Extension record to pipeline-compatible JSONL format.

    Returns None if no stable job_id can be derived (no finnkode, no URL).
    """
    # --- Job ID: use finnkode as stable identifier ---
    finnkode = str(raw.get("finnkode") or "").strip()
    if not finnkode:
        # Try to extract from URL
        ad_url = raw.get("ad_url") or raw.get("url") or ""
        m = re.search(r"finnkode[=:](\d+)", str(ad_url))
        if m:
            finnkode = m.group(1)
    if not finnkode:
        return None

    job_id = f"finn_{finnkode}"

    # --- Core fields ---
    title = (raw.get("title") or "").strip()
    employer_name = (raw.get("company") or raw.get("employer") or "").strip()

    # Description: prefer HTML, build from plain text if not available
    desc_html = (raw.get("description_html") or "").strip()
    desc_text = (raw.get("description_text") or raw.get("description") or "").strip()
    if not desc_html and desc_text:
        # Wrap plain text in simple HTML paragraphs for pipeline compatibility
        paragraphs = [p.strip() for p in desc_text.split("\n\n") if p.strip()]
        desc_html = "".join(f"<p>{p}</p>" for p in paragraphs) if paragraphs else f"<p>{desc_text}</p>"

    # --- Deadline ---
    application_due = _parse_deadline(raw)

    # --- Location ---
    sted = (raw.get("sted") or raw.get("location") or "").strip()
    city, county = _split_sted(sted)

    # --- Work arrangement (for geo filter remote check) ---
    hjemmekontor = (raw.get("hjemmekontor") or "").strip()
    # Normalize common FINN values: "Ja" → "hjemmekontor", "Delvis" → "hybrid"
    work_arrangement = ""
    if hjemmekontor:
        hj_lower = hjemmekontor.lower()
        if hj_lower in ("ja", "yes", "true"):
            work_arrangement = "hjemmekontor"
        elif hj_lower in ("delvis", "delvis mulig", "hybrid"):
            work_arrangement = "hybrid"
        else:
            work_arrangement = hjemmekontor

    # --- Sector / function ---
    sector = (raw.get("bransje") or "").strip()
    sector_function = (raw.get("stillingsfunksjon") or "").strip()

    # --- Source URL ---
    sourceurl = (
        raw.get("ad_url")
        or raw.get("url")
        or f"https://www.finn.no/job/fulltime/ad.html?finnkode={finnkode}"
    ).strip()

    # --- Received timestamp ---
    received_at = (raw.get("received_at") or "").strip()

    return {
        "job_id": job_id,
        "title": title,
        "employer_name": employer_name,
        "description_html": desc_html,
        "applicationDue": application_due,
        "work_city": city,
        "work_county": county,
        "work_arrangement": work_arrangement,
        "sector": sector,
        "sector_function": sector_function,
        "sourceurl": sourceurl,
        "source": "finn_chrome_ext",
        "suggested_by_platform": False,  # Chrome extension = you were browsing, not platform suggestion
        "captured_at": received_at,
        # No postalCode from Chrome extension — geo filter will use city/county fallback
    }


# --- Ledger deduplication ---

def _load_ledger_ids(ledger_path: Path) -> set:
    """Return set of job_ids already processed in the ledger."""
    if not ledger_path.exists():
        return set()
    try:
        conn = sqlite3.connect(str(ledger_path))
        rows = conn.execute("SELECT job_id FROM ledger").fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception as e:
        print(f"Warning: could not read ledger ({e}). Deduplication disabled.", file=sys.stderr)
        return set()


# --- Main ---

def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(
        description="Normalize FINN Chrome Extension job captures to pipeline JSONL format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--finn-jobs",
        default=DEFAULT_FINN_EXT_JOBS,
        help=f"Path to FINN extension jobs.jsonl (default: {DEFAULT_FINN_EXT_JOBS})",
    )
    ap.add_argument(
        "--out",
        default=str(DEFAULT_OUT_PATH),
        help="Output JSONL path (default: jobs_delta.jsonl)",
    )
    ap.add_argument(
        "--append",
        action="store_true",
        help="Append to output file instead of overwriting",
    )
    ap.add_argument(
        "--ledger",
        default=str(DEFAULT_LEDGER_PATH),
        help="Ledger SQLite path for deduplication (default: reports/ledger.sqlite)",
    )
    ap.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable ledger deduplication (include all jobs, even already processed)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing output",
    )
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    jobs_path = Path(args.finn_jobs)
    if not jobs_path.exists():
        print(f"Error: FINN extension jobs file not found: {jobs_path}", file=sys.stderr)
        print(
            "Make sure the Chrome extension server is running and has captured some jobs.\n"
            "Check the extension's output folder, then pass --finn-jobs <path>.",
            file=sys.stderr,
        )
        sys.exit(1)

    ledger_ids = set() if args.no_dedupe else _load_ledger_ids(Path(args.ledger))
    print(f"Loaded {len(ledger_ids)} job IDs from ledger for deduplication.")

    # Read raw FINN extension records
    raw_jobs: List[dict] = []
    with open(jobs_path, encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw_jobs.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Warning: skipping malformed JSON on line {lineno}: {e}", file=sys.stderr)

    print(f"Read {len(raw_jobs)} raw records from {jobs_path}")

    # Normalize and deduplicate
    normalized: List[dict] = []
    seen_ids: set = set()
    stats = {"no_id": 0, "in_ledger": 0, "duplicate": 0, "new": 0}

    for raw in raw_jobs:
        job = _normalize(raw)
        if job is None:
            stats["no_id"] += 1
            continue

        jid = job["job_id"]

        if jid in seen_ids:
            stats["duplicate"] += 1
            continue
        seen_ids.add(jid)

        if jid in ledger_ids:
            stats["in_ledger"] += 1
            if args.verbose:
                print(f"  [skip-ledger] {jid}  {job['title'][:50]}")
            continue

        normalized.append(job)
        stats["new"] += 1
        if args.verbose:
            print(
                f"  [new] {jid}  {job['title'][:50]:<52}"
                f"  {job.get('employer_name', '')[:30]}"
                f"  {job.get('work_city', '')}"
            )

    # Write output
    if args.dry_run:
        print(f"\n[DRY RUN] Would write {len(normalized)} new jobs to {args.out}")
        for job in normalized[:10]:
            print(f"  {job['job_id']}  {job['title'][:60]}  ({job.get('employer_name', '')})")
        if len(normalized) > 10:
            print(f"  ... and {len(normalized) - 10} more")
    elif normalized:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if args.append else "w"
        with open(out_path, mode, encoding="utf-8") as f:
            for job in normalized:
                f.write(json.dumps(job, ensure_ascii=False) + "\n")
        print(f"\n[OK] Wrote {len(normalized)} jobs to {out_path} (mode={mode})")
    else:
        print("\nNo new jobs to write.")

    print(
        f"\nSummary:\n"
        f"  New (written):           {stats['new']}\n"
        f"  Already in ledger:       {stats['in_ledger']}\n"
        f"  Intra-file duplicates:   {stats['duplicate']}\n"
        f"  No finnkode (skipped):   {stats['no_id']}\n"
    )
    if normalized and not args.dry_run:
        print(f"Next step: run the pipeline on {args.out}")
        print("  .\\go.ps1 -DryRun   (test 2 jobs first)")
        print("  .\\go.ps1           (full run)")


if __name__ == "__main__":
    main()

"""Scrape FINN job search pages by keyword and fetch full content for new jobs.

Unlike pull_suggested.py (which processes suggestion emails), this script
directly queries FINN's public search pages using role-specific keywords.
It is designed to run on a schedule (e.g., daily via go.ps1 -WithSuggestions).

How it works:
  1. For each configured search query, fetches FINN search result pages
  2. Extracts finnkodes from <article id="card-{finnkode}"> elements (public SSR HTML)
  3. Cross-references against ledger.sqlite — skips already-processed jobs
  4. Fetches full job content for new jobs (JSON-LD → Next.js → HTML fallback)
  5. Appends to jobs_delta.jsonl with suggested_by_platform=true, source=finn_search

Jobs from this source are tagged platform_suggested in triage signals, which:
  - Bypasses the semantic pre-filter (let the LLM decide on algorithm-curated jobs)
  - Enables calibration analysis (query ledger for platform_suggested + SKIP)

Anti-bot: time guard 09:00-19:00 Oslo. Random delays (3-9s). Max 40 fetches/run.
Search page fetches have shorter delays (0.5-1.5s) — they're public listing pages.

Usage:
    python -m jobpipe.cli.pull_finn_search                    # use YAML defaults
    python -m jobpipe.cli.pull_finn_search --dry-run          # list new finnkodes only
    python -m jobpipe.cli.pull_finn_search --max 20           # limit fetches
    python -m jobpipe.cli.pull_finn_search --force-daytime    # skip time guard (testing)
    python -m jobpipe.cli.pull_finn_search --verbose          # show fetch details
"""
from __future__ import annotations

import argparse
import io
import json
import random
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from jobpipe.core.config import load_raw_config
from jobpipe.core.paths import bootstrap_private_data, get_jobpipe_paths

# Windows cp1252 consoles can't encode arbitrary Unicode — wrap stdout.
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# BeautifulSoup4 (required — in requirements.txt)
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

# Norwegian timezone
try:
    from zoneinfo import ZoneInfo
    _OSLO_TZ: Any = ZoneInfo("Europe/Oslo")
except Exception:
    _OSLO_TZ = timezone(timedelta(hours=1))

_DEFAULT_PATHS = get_jobpipe_paths()
DEFAULT_OUT_PATH       = _DEFAULT_PATHS.jobs_delta_path
DEFAULT_LEDGER_PATH    = _DEFAULT_PATHS.ledger_sqlite_path
DEFAULT_CONFIG_PATH    = _DEFAULT_PATHS.default_config_path

_DAYTIME_START = 9
_DAYTIME_END   = 19

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Default search queries if not configured in YAML.
# These map to Lars's FINN profile role preferences.
# Format: human-readable label → FINN q= parameter value
DEFAULT_QUERIES: List[Tuple[str, str]] = [
    ("Produktansvarlig/eier/leder", "produktansvarlig OR produkteier OR produktleder"),
    ("Digitaliseringsleder/konsulent", "digitaliseringsleder OR digitaliseringskonsulent"),
    ("IT-rådgiver/konsulent",         "IT-konsulent OR IT-rådgiver OR teknologirådgiver"),
    ("Prosjektleder IT",              "prosjektleder IT"),
]

# No location filter by default — let the pipeline geo filter (triage.py) handle it.
# Using FINN's location codes cuts results too aggressively (Oslo municipality
# drops "produktansvarlig" results from 23 → 2). Remote jobs also need to pass through.
DEFAULT_LOCATION = ""   # empty = no FINN location restriction


# ---------------------------------------------------------------------------
# Time guard
# ---------------------------------------------------------------------------

def _is_daytime() -> bool:
    now = datetime.now(_OSLO_TZ)
    return _DAYTIME_START <= now.hour < _DAYTIME_END


def _oslo_time_str() -> str:
    return datetime.now(_OSLO_TZ).strftime("%H:%M")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch_html(url: str, timeout: int = 15) -> Optional[str]:
    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "no-NO,no;q=0.9,en-US;q=0.8,en;q=0.7",
        # No Accept-Encoding — Python's urlopen doesn't auto-decompress gzip/br,
        # so omit it to receive plain HTML that BeautifulSoup can parse directly.
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "DNT": "1",
    }
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return raw.decode("utf-8", errors="replace")
            except Exception:
                return raw.decode("latin-1", errors="replace")
    except (URLError, HTTPError, OSError, TimeoutError):
        return None


# ---------------------------------------------------------------------------
# FINN search page scraping (extracts finnkodes from listing page HTML)
# ---------------------------------------------------------------------------

_CARD_ID_RE = re.compile(r'^card-(\d{6,12})$')


def scrape_search_page(query: str, location: str, page: int = 1) -> List[str]:
    """Fetch one FINN search results page and return list of finnkodes found.

    Uses BeautifulSoup to parse <article id="card-{finnkode}"> elements.
    Returns empty list on network error or if no results.
    """
    params = {"q": query, "sort": "PUBLISHED_DESC", "page": str(page)}
    if location:
        params["location"] = location
    qs = urlencode(params)
    url = f"https://www.finn.no/job/search?{qs}"

    html = _fetch_html(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    finnkodes = []
    for article in soup.find_all("article", id=_CARD_ID_RE):
        m = _CARD_ID_RE.match(article.get("id", ""))
        if m:
            finnkodes.append(m.group(1))
    return finnkodes


# ---------------------------------------------------------------------------
# FINN job content fetching (3-strategy: JSON-LD → Next.js → HTML fallback)
# Mirrors the logic in pull_suggested.py — kept independent to avoid coupling.
# ---------------------------------------------------------------------------

def _extract_finn_ld(soup: "BeautifulSoup") -> Optional[dict]:
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
            # FINN wraps JSON-LD in {"script:ld+json": {...}} — unwrap if present
            if isinstance(data, dict) and "script:ld+json" in data:
                data = data["script:ld+json"]
            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                if isinstance(entry, dict) and entry.get("@type") == "JobPosting":
                    return entry
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


def _extract_finn_next_data(soup: "BeautifulSoup") -> Optional[dict]:
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag:
        return None
    try:
        next_data = json.loads(tag.string or "")
        props = next_data.get("props", {}).get("pageProps", {})
        for key in ("adData", "ad", "jobAd", "initialState", "data"):
            val = props.get(key)
            if val and isinstance(val, dict):
                return val
    except (json.JSONDecodeError, AttributeError):
        pass
    return None


def _iso_date(s: str) -> str:
    if not s:
        return ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(s))
    return m.group(1) if m else ""


def _normalize_ld(ld: dict, finnkode: str, url: str) -> dict:
    org = ld.get("hiringOrganization") or {}
    if isinstance(org, str):
        org = {"name": org}
    location = ld.get("jobLocation") or {}
    if isinstance(location, list):
        location = location[0] if location else {}
    address = location.get("address") if isinstance(location, dict) else {}
    if isinstance(address, str):
        city, postal = address, ""
    elif isinstance(address, dict):
        city   = address.get("addressLocality") or address.get("addressRegion") or ""
        postal = address.get("postalCode") or ""
    else:
        city, postal = "", ""
    return {
        "job_id": f"finn_{finnkode}",
        "title": ld.get("title") or "",
        "employer_name": (org.get("name") or "") if isinstance(org, dict) else str(org),
        "description_html": ld.get("description") or "",
        "applicationDue": _iso_date(ld.get("validThrough") or ""),
        "work_city": city,
        "work_postalCode": postal,
        "sourceurl": ld.get("url") or url,
        "source": "finn_search",
        "suggested_by_platform": True,
        "parse_method": "json_ld",
    }


def _normalize_next_data(ad: dict, finnkode: str, url: str) -> dict:
    employer = ad.get("employer") or ad.get("company") or {}
    if isinstance(employer, str):
        employer_name = employer
    elif isinstance(employer, dict):
        employer_name = employer.get("name") or employer.get("companyName") or ""
    else:
        employer_name = ""
    location = ad.get("location") or ad.get("workPlace") or ""
    if isinstance(location, dict):
        city   = location.get("city") or location.get("municipality") or ""
        postal = location.get("postalCode") or ""
    else:
        city, postal = str(location), ""
    return {
        "job_id": f"finn_{finnkode}",
        "title": ad.get("title") or ad.get("heading") or "",
        "employer_name": employer_name,
        "description_html": ad.get("description") or ad.get("body") or "",
        "applicationDue": _iso_date(ad.get("applicationDeadline") or ad.get("deadline") or ""),
        "work_city": city,
        "work_postalCode": postal,
        "sourceurl": url,
        "source": "finn_search",
        "suggested_by_platform": True,
        "parse_method": "next_data",
    }


def _normalize_html_fallback(soup: "BeautifulSoup", finnkode: str, url: str) -> Optional[dict]:
    title_tag = soup.find("title")
    raw_title = title_tag.get_text(strip=True) if title_tag else ""
    raw_title = re.sub(r"\s*\|\s*finn\.no\s*$", "", raw_title, flags=re.IGNORECASE).strip()
    employer, title = "", raw_title
    if " - " in raw_title:
        parts = raw_title.split(" - ", 1)
        title, employer = parts[0].strip(), parts[1].strip()
    if not title:
        return None
    meta_desc = soup.find("meta", {"name": "description"})
    description = (meta_desc["content"] if meta_desc and meta_desc.get("content") else "")
    return {
        "job_id": f"finn_{finnkode}",
        "title": title,
        "employer_name": employer,
        "description_html": f"<p>{description}</p>" if description else "",
        "sourceurl": url,
        "source": "finn_search",
        "suggested_by_platform": True,
        "parse_method": "html_fallback",
    }


def fetch_finn_job(finnkode: str, delay: float, verbose: bool = False) -> Optional[dict]:
    """Fetch a FINN job ad page and return normalized pipeline dict or None."""
    url = f"https://www.finn.no/job/fulltime/ad.html?finnkode={finnkode}"
    if verbose:
        print(f"    Sleeping {delay:.1f}s...")
    time.sleep(delay)
    html = _fetch_html(url)
    if html is None:
        return None
    soup = BeautifulSoup(html, "lxml")
    ld = _extract_finn_ld(soup)
    if ld:
        job = _normalize_ld(ld, finnkode, url)
        if job.get("title"):
            if verbose:
                print(f"    Parsed via JSON-LD")
            return job
    ad_data = _extract_finn_next_data(soup)
    if ad_data:
        job = _normalize_next_data(ad_data, finnkode, url)
        if job.get("title"):
            if verbose:
                print(f"    Parsed via Next.js data")
            return job
    job = _normalize_html_fallback(soup, finnkode, url)
    if job:
        if verbose:
            print(f"    Parsed via HTML fallback")
        return job
    return None


# ---------------------------------------------------------------------------
# Ledger helpers
# ---------------------------------------------------------------------------

def _load_ledger_ids(ledger_path: Path) -> set:
    if not ledger_path.exists():
        return set()
    try:
        conn = sqlite3.connect(str(ledger_path))
        rows = conn.execute("SELECT job_id FROM ledger").fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception as e:
        print(f"Warning: could not read ledger: {e}", file=sys.stderr)
        return set()


def _load_finn_search_section(config_path: Path, overlays: List[str]) -> Dict[str, Any]:
    if not config_path.exists():
        return {}
    try:
        cfg = load_raw_config(config_path, overlays=overlays)
    except Exception:
        return {}
    section = cfg.get("finn_search") or {}
    return section if isinstance(section, dict) else {}


def _load_queries_from_section(section: Dict[str, Any]) -> Optional[List[Tuple[str, str]]]:
    queries_raw = section.get("queries") or []
    if not queries_raw:
        return None
    result = []
    for item in queries_raw:
        if isinstance(item, str):
            result.append((item, item))
        elif isinstance(item, dict):
            label = item.get("label") or item.get("q") or str(item)
            q = item.get("q") or item.get("query") or label
            result.append((label, q))
    return result if result else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Scrape FINN job search pages by keyword and fetch content for new jobs. "
            "Only runs 09:00-19:00 Oslo time."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--data-root",
        default="",
        help=f"JobPipe user data root (default: {_DEFAULT_PATHS.data_root})",
    )
    ap.add_argument("--config",   default="", help=f"Pipeline YAML config (default: {DEFAULT_CONFIG_PATH})")
    ap.add_argument("--config-overlay", action="append", default=[], help="Optional config overlay YAML. Can be passed multiple times.")
    ap.add_argument("--out",      default="", help=f"Output JSONL to append to (default: {DEFAULT_OUT_PATH})")
    ap.add_argument("--ledger",   default="", help=f"Ledger SQLite for dedup (default: {DEFAULT_LEDGER_PATH})")
    ap.add_argument("--max",      type=int, default=40,             help="Max full-content fetches per run (default: 40)")
    ap.add_argument("--max-pages",type=int, default=2,              help="Max FINN search result pages per query (default: 2)")
    ap.add_argument("--min-delay",type=float, default=3.0,          help="Min seconds between content fetches")
    ap.add_argument("--max-delay",type=float, default=9.0,          help="Max seconds between content fetches")
    ap.add_argument("--force-daytime", action="store_true",         help="Skip Oslo time guard (testing)")
    ap.add_argument("--dry-run",  action="store_true",              help="List new finnkodes without fetching content")
    ap.add_argument("--verbose",  "-v", action="store_true")
    args = ap.parse_args(argv)
    paths = get_jobpipe_paths(args.data_root or None)
    bootstrap_private_data(paths, include_artifacts=False)
    config_path = Path(args.config) if args.config else paths.default_config_path
    out_path = Path(args.out) if args.out else paths.jobs_delta_path
    ledger_path = Path(args.ledger) if args.ledger else paths.ledger_sqlite_path

    if not BS4_AVAILABLE:
        print(
            "Error: beautifulsoup4 not installed.\n"
            "Run: pip install beautifulsoup4 lxml",
            file=sys.stderr,
        )
        sys.exit(1)

    # Time guard (skip for dry-run)
    if not args.force_daytime and not args.dry_run:
        if not _is_daytime():
            print(
                f"[time-guard] Oslo time: {_oslo_time_str()}. "
                f"FINN scraping only allowed {_DAYTIME_START:02d}:00–{_DAYTIME_END:02d}:00. "
                f"Use --force-daytime to bypass."
            )
            sys.exit(0)

    finn_search = _load_finn_search_section(config_path, args.config_overlay)
    queries = _load_queries_from_section(finn_search) or DEFAULT_QUERIES
    location = finn_search.get("location") or DEFAULT_LOCATION

    ledger_ids = _load_ledger_ids(ledger_path)
    print(f"Ledger: {len(ledger_ids)} known job IDs")

    # --- Phase 1: Scrape search pages for new finnkodes ---
    print(f"\n=== Phase 1: Scraping {len(queries)} FINN search queries (max {args.max_pages} pages each) ===")

    all_new_finnkodes: List[str] = []
    seen: set = set()

    for label, q in queries:
        print(f"\n  Query: '{q}' ({label})")
        query_new = 0
        for page in range(1, args.max_pages + 1):
            delay = random.uniform(0.5, 1.5)
            if args.verbose:
                print(f"    Page {page} (delay {delay:.1f}s)...")
            time.sleep(delay)

            finnkodes = scrape_search_page(q, location, page)

            if not finnkodes:
                print(f"    Page {page}: 0 cards — stopping this query.")
                break

            for fk in finnkodes:
                jid = f"finn_{fk}"
                if fk not in seen and jid not in ledger_ids:
                    seen.add(fk)
                    all_new_finnkodes.append(fk)
                    query_new += 1

            already = len(finnkodes) - query_new
            print(f"    Page {page}: {len(finnkodes)} cards  ({query_new} new, {already} already in ledger)")

            if len(finnkodes) < 10:
                # Last page (short result set)
                break

    print(f"\nTotal new finnkodes found: {len(all_new_finnkodes)}")

    if not all_new_finnkodes:
        print("Nothing new — all jobs already in ledger.")
        return

    if args.dry_run:
        print("\n[DRY RUN] Would fetch content for:")
        for fk in all_new_finnkodes[:args.max]:
            print(f"  finn_{fk}  →  https://www.finn.no/job/fulltime/ad.html?finnkode={fk}")
        if len(all_new_finnkodes) > args.max:
            print(f"  ... and {len(all_new_finnkodes) - args.max} more (limited by --max {args.max})")
        return

    # --- Phase 2: Fetch full job content for new finnkodes ---
    batch = all_new_finnkodes[:args.max]
    remaining = len(all_new_finnkodes) - len(batch)

    print(
        f"\n=== Phase 2: Fetching content for {len(batch)} jobs "
        f"(delay {args.min_delay:.0f}–{args.max_delay:.0f}s, Oslo time: {_oslo_time_str()}) ==="
    )
    if remaining > 0:
        print(f"  {remaining} more found but not fetched — increase --max or run again.")

    fetched: List[dict] = []
    failed:  List[str]  = []

    for i, finnkode in enumerate(batch):
        delay = random.uniform(args.min_delay, args.max_delay)
        print(f"  [{i+1}/{len(batch)}] finn_{finnkode}  (delay={delay:.1f}s)")

        job = fetch_finn_job(finnkode, delay=delay, verbose=args.verbose)
        if job:
            fetched.append(job)
            print(
                f"    [OK] '{job.get('title','?')[:55]}'  "
                f"({job.get('employer_name','?')[:28]})  [{job.get('parse_method','?')}]"
            )
        else:
            failed.append(finnkode)
            print(f"    [FAIL] Could not extract content for finn_{finnkode}")

    # --- Write ---
    if fetched:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "a", encoding="utf-8") as f:
            for job in fetched:
                f.write(json.dumps(job, ensure_ascii=False) + "\n")
        print(f"\n[OK] Appended {len(fetched)} jobs to {out_path}")

    print(
        f"\nSummary:\n"
        f"  Queries run:        {len(queries)}\n"
        f"  New finnkodes:      {len(all_new_finnkodes)}\n"
        f"  Fetched this run:   {len(fetched)}\n"
        f"  Failed:             {len(failed)}\n"
        f"  Remaining queue:    {remaining}\n"
    )
    if fetched:
        print(
            "Next step:\n"
            "  .\\go.ps1 -DryRun   (test 2 jobs)\n"
            "  .\\go.ps1           (full run)"
        )


if __name__ == "__main__":
    main()

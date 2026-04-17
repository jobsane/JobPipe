from __future__ import annotations
import csv
import json
import os
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from html import unescape


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_profile_pack(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Env loader (replaces python-dotenv for our minimal needs)
# ---------------------------------------------------------------------------

def load_env_file(path: str | Path) -> None:
    """Minimal .env loader: KEY=VALUE, ignores comments, does not overwrite."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


# ---------------------------------------------------------------------------
# Value helpers (used across CLI + stages)
# ---------------------------------------------------------------------------

def clean(s: Any) -> str:
    """Normalise any value to a stripped string (None -> '')."""
    return ("" if s is None else str(s)).strip()


def pick(*vals: Any) -> str:
    """Return the first non-empty cleaned value, or ''."""
    for v in vals:
        s = clean(v)
        if s:
            return s
    return ""


def to_float(x: Any) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def to_int(x: Any) -> Optional[int]:
    try:
        if x is None or x == "":
            return None
        return int(float(x))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Job-ID derivation
# ---------------------------------------------------------------------------

def stable_job_id(job: Dict[str, Any]) -> str:
    """Canonical job_id: prefer existing id fields, fallback to content hash."""
    for k in ("job_id", "uuid", "id", "stilling_id"):
        v = job.get(k)
        if v:
            return str(v)
    key = "|".join([
        (job.get("title") or ""),
        (job.get("employer_name") or ""),
        (job.get("sourceurl") or job.get("link") or job.get("applicationUrl") or ""),
        (job.get("applicationDue") or ""),
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# JSONL / JSON / CSV reading
# ---------------------------------------------------------------------------

def read_jsonl_lines(path: str | Path) -> List[str]:
    """Read a JSONL file as raw JSON strings (for drain_queue batch handling)."""
    p = Path(path)
    if not p.exists():
        return []
    lines: List[str] = []
    with p.open("r", encoding="utf-8") as f:
        for raw in f:
            s = raw.strip()
            if s:
                lines.append(s)
    return lines


def write_jsonl_lines(path: str | Path, lines: List[str]) -> None:
    """Write raw JSON strings to a JSONL file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def iter_jobs(path: str) -> Iterable[Dict[str, Any]]:
    """Iterate parsed job dicts from JSONL, JSON, or CSV."""
    if path.lower().endswith(".jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)
        return

    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            for item in data:
                yield item
        elif isinstance(data, dict) and "jobs" in data and isinstance(data["jobs"], list):
            for item in data["jobs"]:
                yield item
        else:
            raise ValueError("JSON must be a list or a dict with key 'jobs' (list).")
        return

    if path.lower().endswith(".csv"):
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield dict(row)
        return

    raise ValueError("Unsupported file type. Use .jsonl, .json, or .csv")


# ---------------------------------------------------------------------------
# JSON writing
# ---------------------------------------------------------------------------

def write_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# HTML → text
# ---------------------------------------------------------------------------

def html_to_text(html: str, max_chars: int = 2500) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]

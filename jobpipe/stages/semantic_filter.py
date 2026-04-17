"""
Semantic pre-filter using local CPU embeddings (fastembed).

Runs AFTER geo/hard-no regex filters, BEFORE any LLM call.
Computes cosine similarity between each job and the candidate profile.
Jobs below the threshold are SKIP'd without spending any API tokens.

Why this saves money
--------------------
In a typical run ~30-35% of jobs reach the nano triage LLM after geo/hard-no
filtering. Of those, ~97-99% are SKIP'd anyway. The semantic filter catches the
obvious mismatches (barnehage, sjåfør, baker, lager) with a free local model so
the LLM only sees jobs with at least some semantic relevance to the profile.
Expected reduction in LLM triage calls: 60-75%.

Model choices
-------------
CALIBRATION FINDINGS (2026-04-13):
  BAAI/bge-small-en-v1.5 (English-only) is NOT effective for Norwegian jobs.
  All Norwegian texts cluster in cosine range 0.52-0.76 — target roles like
  "Systemansvarlig CRM Salesforce" score 0.555 while irrelevant "Montør elektriker"
  scores 0.672. No threshold separates them reliably. Disabled (threshold=0.0).

Recommended for Norwegian:
  sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (~220 MB ONNX)
    - fastembed 0.8.0 supported, proper multilingual model
    - Calibrate threshold empirically: run on 50+ known jobs, find the score
      that separates helse/håndverk/renhold from IT-management roles
    - Expected threshold: 0.55-0.60 after calibration
  intfloat/multilingual-e5-large (~500 MB)
    - Higher quality but slower on CPU

Profile cache
-------------
The profile embedding is computed once and cached to disk.
Delete reports/profile_embedding.npy to force a rebuild (e.g. after editing
profile_pack.md).
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Callable, Tuple

import numpy as np

from jobpipe.core.schema import JobContext, TriageOut
from jobpipe.stages._common import job_excerpt

try:
    from fastembed import TextEmbedding
    _HAS_FASTEMBED = True
except ImportError:
    _HAS_FASTEMBED = False

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
PROFILE_CACHE_PATH = Path("reports/profile_embedding.npy")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 1e-9 else 0.0


def _extract_profile_text(profile_pack: str, max_chars: int = 1400) -> str:
    """
    Pull the most signal-dense sections from profile_pack:
      0) Role identity + career stage
      1) Target roles / job types
      2) Must-have signals

    Falls back to raw profile start if section markers not found.
    """
    lines = profile_pack.split("\n")
    capture: list[str] = []
    in_section = False
    for line in lines:
        if any(line.startswith(f"## {n})") for n in ("0", "1", "2")):
            in_section = True
        elif line.startswith("## 3)"):
            break
        if in_section:
            capture.append(line)
    text = "\n".join(capture).strip()
    return (text or profile_pack)[:max_chars]


def build_or_load_profile_embedding(
    profile_pack: str,
    model: "TextEmbedding",
    cache_path: Path = PROFILE_CACHE_PATH,
) -> np.ndarray:
    """Load cached profile embedding or build it from scratch."""
    if cache_path.exists():
        return np.load(cache_path)
    profile_text = _extract_profile_text(profile_pack)
    emb = np.array(list(model.embed([profile_text]))[0], dtype=np.float32)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache_path, emb)
    print(f"[semantic_filter] Profile embedding built and cached -> {cache_path}")
    return emb


# ---------------------------------------------------------------------------
# Public factory — called by triage_stage_factory
# ---------------------------------------------------------------------------

FilterFn = Callable[[JobContext], JobContext]


def build_semantic_filter(
    threshold: float,
    profile_pack: str,
    model_name: str = DEFAULT_MODEL,
    max_job_text_chars: int = 500,
    cache_path: Path = PROFILE_CACHE_PATH,
) -> FilterFn:
    """
    Returns a function: (ctx: JobContext) -> JobContext

    If fastembed is not installed, returns a no-op (pass-through) function
    with a one-time warning — the pipeline continues without the filter.

    Usage inside triage stage:
        semantic_check = build_semantic_filter(threshold, profile_pack)
        ...
        ctx = semantic_check(ctx)
        if ctx.triage is not None:
            return ctx   # already SKIP'd by semantic filter
    """
    if not _HAS_FASTEMBED:
        warnings.warn(
            "\n[semantic_filter] fastembed not installed — semantic pre-filter DISABLED.\n"
            "  All jobs will reach the LLM triage as before.\n"
            "  To enable: pip install fastembed\n",
            stacklevel=2,
        )
        return lambda ctx: ctx  # no-op

    model = TextEmbedding(model_name)  # fastembed 0.8+ dropped the model_name kwarg
    profile_emb = build_or_load_profile_embedding(profile_pack, model, cache_path)

    def _filter(ctx: JobContext) -> JobContext:
        job = ctx.job
        title = (job.get("normalized_title") or job.get("title") or "").strip()
        desc = job_excerpt(job, max_job_text_chars)
        text = f"{title}\n{desc}".strip()

        job_emb = np.array(list(model.embed([text]))[0], dtype=np.float32)
        score = _cosine(profile_emb, job_emb)

        # Always store the score in ctx.notes — needed for calibration of both
        # passing and failing jobs. Triage stage appends this to final signals.
        ctx.notes["sem_score"] = round(score, 4)

        if score < threshold:
            ctx.triage = TriageOut(
                triage_decision="SKIP",
                confidence=0.88,
                explanation=(
                    f"Semantic pre-filter: cosine similarity {score:.3f} "
                    f"below threshold {threshold:.2f} — job text semantically "
                    "unrelated to candidate profile"
                ),
                signals=["semantic_filter_skip", f"sim:{score:.2f}"],
                forced_safety=False,
            )
        return ctx

    return _filter

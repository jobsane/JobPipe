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
Delete the cached profile embedding in the JobPipe data root cache directory to
force a rebuild (e.g. after editing profile_pack.md).
"""
from __future__ import annotations

import json
from hashlib import sha256
import warnings
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from jobpipe.core.paths import get_jobpipe_paths
from jobpipe.core.profile_layer import build_triage_profile_text, load_or_build_profile_layer_for_paths
from jobpipe.core.schema import JobContext, TriageOut
from jobpipe.stages._common import job_excerpt

try:
    from fastembed import TextEmbedding
    _HAS_FASTEMBED = True
except ImportError:
    _HAS_FASTEMBED = False

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def _default_profile_cache_path() -> Path:
    return get_jobpipe_paths().profile_embedding_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 1e-9 else 0.0


def build_or_load_profile_embedding(
    profile_pack: str,
    model: "TextEmbedding",
    cache_path: Optional[Path] = None,
    meta_path: Optional[Path] = None,
    model_name: str = DEFAULT_MODEL,
) -> np.ndarray:
    """Load cached profile embedding or build it from scratch."""
    cache_path = cache_path or _default_profile_cache_path()
    paths = get_jobpipe_paths()
    meta_path = meta_path or paths.profile_embedding_meta_path
    layer = load_or_build_profile_layer_for_paths(paths)
    profile_text = build_triage_profile_text(layer)
    profile_hash = sha256(profile_text.encode("utf-8")).hexdigest()
    if cache_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
        if (
            isinstance(meta, dict)
            and meta.get("profile_hash") == profile_hash
            and meta.get("model_name") == model_name
        ):
            return np.load(cache_path)
    emb = np.array(list(model.embed([profile_text]))[0], dtype=np.float32)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache_path, emb)
    meta_path.write_text(
        json.dumps(
            {
                "model_name": model_name,
                "profile_hash": profile_hash,
                "profile_layer_schema_version": layer.schema_version,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
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
    cache_path: Optional[Path] = None,
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
    profile_emb = build_or_load_profile_embedding(
        profile_pack,
        model,
        cache_path,
        model_name=model_name,
    )

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

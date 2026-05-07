"""Offline language detection and routing for generated application documents.

Detection is word-frequency based: count Norwegian function words against
total word count. No external dependencies, no network calls, no randomness.

Returns 'no' (Norwegian) or 'en' (English). Default is 'no' when the signal
is ambiguous to match the primary candidate market.
"""
from __future__ import annotations

from jobpipe.authoring.case_context import AuthoringCaseContext

# Norwegian function words that are unlikely in English text.
# Chosen to minimise false positives: words that also appear frequently in English
# ("for", "at", "over", "under", "her", "sin", "de", "var") are excluded.
# Only words that are strong, unambiguous Norwegian signals are kept.
_NO_FUNCTION_WORDS: frozenset[str] = frozenset(
    {
        "og", "eller", "er", "av", "til", "med", "på", "ikke",
        "som", "det", "fra", "men", "om", "seg", "ved",
        "også", "når", "etter", "mot", "vi",
        "du", "din", "deg", "han", "hun", "dem", "nå", "der",
        "alle", "hvilke", "hva", "hvem", "hvor", "hvordan", "hvorfor",
        "kan", "skal", "vil", "har", "bli", "blir", "ble",
        "søker", "stillingen", "arbeidsgiveren", "kandidaten",
    }
)

# Threshold: if ≥ this fraction of words are Norwegian function words, classify as 'no'.
_NO_THRESHOLD: float = 0.06


def detect_job_language(job_title: str, description_excerpt: str) -> str:
    """Return 'no' (Norwegian) or 'en' (English) based on job ad text.

    Uses word-frequency of Norwegian function words. Treats ambiguous or
    very short inputs as Norwegian (the primary candidate market).
    """
    text = f"{job_title} {description_excerpt}"
    words = text.lower().split()
    if len(words) < 10:
        return "no"
    no_count = sum(1 for w in words if w.strip(".,;:!?()[]\"'") in _NO_FUNCTION_WORDS)
    ratio = no_count / len(words)
    return "no" if ratio >= _NO_THRESHOLD else "en"


def get_document_language(ctx: AuthoringCaseContext) -> str:
    """Return effective document language for this authoring context.

    Checks ctx.language_override first; falls back to detect_job_language
    using job_summary fields.
    """
    if ctx.language_override in ("no", "en"):
        return ctx.language_override

    title = ctx.job_summary.get("title", "") if isinstance(ctx.job_summary, dict) else ""
    excerpt = (
        ctx.job_summary.get("description_excerpt", "")
        or ctx.job_summary.get("description", "")[:500]
        if isinstance(ctx.job_summary, dict)
        else ""
    )
    return detect_job_language(title, excerpt)


__all__ = ["detect_job_language", "get_document_language"]

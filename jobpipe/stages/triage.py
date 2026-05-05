from __future__ import annotations

import json
import os
import re

from agents import Agent

from jobpipe.core.profile_pack import parse_profile_pack
from jobpipe.model.schema import HardGates, JobContext, TriageOut
from jobpipe.stages._common import build_job_header, job_excerpt, run_agent
from jobpipe.stages.semantic_filter import build_semantic_filter


def _passing_hard_gates() -> HardGates:
    return HardGates(
        title_gate=True,
        language_gate=True,
        sector_gate=True,
        geo_gate=True,
        remote_gate=True,
        must_have_tech_gate=True,
        duplicate_gate=True,
        blocker_reasons=[],
    )


def _hard_gate_snapshot(**updates: object) -> HardGates:
    return _passing_hard_gates().model_copy(update=updates)


def _normalize_title_text(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _title_matches_targeting_patterns(title: str, patterns: list[str] | None) -> bool:
    if not title or not patterns:
        return False
    normalized_title = f" {_normalize_title_text(title)} "
    for pattern in patterns:
        normalized_pattern = _normalize_title_text(pattern)
        if normalized_pattern and f" {normalized_pattern} " in normalized_title:
            return True
    return False


_TITLE_FAMILY_MARKERS: dict[str, tuple[str, ...]] = {
    "product": ("product", "produkt"),
    "service": ("service owner", "service manager", "service management", "tjenesteeier", "tjenesteleder", "tjenesteansvar"),
    "platform": ("platform", "plattform", "systemansvar", "systemeier", "applikasjonsforvalt", "systemforvalt"),
    "change": ("change", "endrings", "transformation", "transformasjon", "digitalization", "digitalisering"),
    "governance": ("governance", "process owner", "prosess", "pmo", "program", "portfolio", "portefølje"),
    "operations": ("operations", "drift", "forvaltning", "crm", "itsm"),
}


def _uniq_hits(rx: re.Pattern | None, s: str, limit: int = 8) -> list[str]:
    if not rx:
        return []
    hits: list[str] = []
    seen: set[str] = set()
    for m in rx.finditer(s):
        t = (m.group(0) or "").strip().lower()
        if not t or t in seen:
            continue
        seen.add(t)
        hits.append(t)
        if len(hits) >= limit:
            break
    return hits


def _norm_postal(v: object) -> str:
    s = str(v).strip() if v is not None else ""
    if not s:
        return ""
    # handle numbers that became 151.0 etc
    if re.fullmatch(r"\d+(\.0+)?", s):
        s = s.split(".")[0]
    # Norway postal codes are 4 digits; preserve leading zeros
    if s.isdigit() and len(s) < 4:
        s = s.zfill(4)
    return s


def _get_postals(job: dict) -> list[str]:
    postals: list[str] = []
    seen: set[str] = set()

    # 1) direct columns (EXPORT should have work_postalCode)
    for k in (
        "work_postalCode",
        "work_postal_code",
        "postalCode",
        "postal_code",
        "postnr",
        "zip",
        "zipcode",
    ):
        v = _norm_postal(job.get(k))
        if v and v not in seen:
            seen.add(v)
            postals.append(v)

    # 2) fallback: workLocations_json can contain multiple locations
    raw = job.get("workLocations_json") or job.get("workLocations") or job.get("work_locations_json")
    if raw:
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
            locs = obj if isinstance(obj, list) else [obj]
            for loc in locs:
                if not isinstance(loc, dict):
                    continue
                v = _norm_postal(
                    loc.get("postalCode")
                    or loc.get("postal_code")
                    or loc.get("postnr")
                    or loc.get("zip")
                    or loc.get("zipcode")
                )
                if v and v not in seen:
                    seen.add(v)
                    postals.append(v)
        except Exception:
            pass

    return postals


def _get_postal(job: dict) -> str:
    ps = _get_postals(job)
    return ps[0] if ps else ""


TRIAGE_INSTRUCTIONS_TEMPLATE = """
Du er en effektiv førsteinntaksagent. Du filtrerer stillinger for en kandidat.

{profile_summary}

Oppgave: Vurder om stillingen er realistisk relevant og returner én av:
- SKIP: stillingen handler IKKE om produkt/tjeneste-eierskap, digital prosjektledelse,
  plattform-/systemforvaltning, CRM/ITSM, endringsledelse, eller strategisk digital utvikling.
  Eksempler på SKIP: butikk, salg, kundeservice uten eierskap, helse/klinisk,
  undervisning, håndverk, transport, lager, renhold, regnskap, jus, HR uten IT,
  ren markedsføring uten systemeierskap, ren UX/design uten produktansvar.
- REVIEW: stillingen KAN handle om kandidatens kjerneområder — det finnes en
  realistisk kobling til eierskap, forvaltning, prosjektledelse, plattformdrift eller digital utvikling.
- APPLY_CANDIDATE: tydelig treff på en av kandidatens primærroller (produkteier,
  tjenesteeier, plattformansvarlig, digital prosjektleder, endringsleder).

Vær selektiv med REVIEW — bare send videre hvis det finnes en reell kobling.
Tvilstilfeller der stillingen er langt utenfor kjerneområdene skal være SKIP.

confidence — kalibrert sikkerhetsskala (ALDRI 0.0):
- 0.90–0.99: åpenbart/utvilsomt (barnehageassistent, sjåfør, baker = 0.95 SKIP)
- 0.70–0.89: tydelig, men noe rom for tvil
- 0.50–0.69: grensentilfelle, kunne gått begge veier
- signals — maks 4 korte tagger (f.eks. "geo", "helse/klinisk", "ren-salg"), IKKE fulle setninger

noise_level — HR-støyindeks (0.0–1.0):
Hvor mye av annonseteksten er innholdsløse floskler, buzzwords og HR-prat uten konkret informasjon?
- 0.0–0.3: teksten er konkret, spesifikk og informativ
- 0.4–0.6: blanding av substans og generiske fraser
- 0.7–1.0: dominert av HR-klisjeer ("dynamisk miljø", "passion", "team player", vage ansvar)
Høy noise_level betyr ikke automatisk SKIP — men kombinert med lav confidence er det et svakt signal.

Svar KUN som gyldig JSON iht output_type.
""".strip()


def _extract_profile_summary(profile_pack: str, max_chars: int = 900) -> str:
    """Extract sections 0 + 1 from profile_pack.md as a compact summary for instructions.
    Falls back to first max_chars if section markers not found."""
    lines = profile_pack.split("\n")
    capture: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("## 0)") or line.startswith("## 1)"):
            in_section = True
        elif line.startswith("## 2)"):
            break  # stop before must-haves
        if in_section:
            capture.append(line)
    summary = "\n".join(capture).strip()
    if not summary:
        summary = profile_pack[:max_chars]
    return summary[:max_chars]


def _text_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if token}


def _matches_profile_phrase(text: str, phrase: str) -> bool:
    haystack = text.lower()
    needle = str(phrase or "").strip().lower()
    if not needle:
        return False
    if needle in haystack:
        return True
    needle_tokens = _text_tokens(needle)
    haystack_tokens = _text_tokens(haystack)
    return bool(needle_tokens) and needle_tokens.issubset(haystack_tokens)


def _candidate_title_safety_terms(profile_pack: str) -> list[str]:
    if not profile_pack.strip():
        return []
    parsed = parse_profile_pack(profile_pack)
    terms: list[str] = []
    terms.extend(str(value).strip() for value in parsed.get("target_roles", {}).get("primary", []) if str(value).strip())
    terms.extend(str(value).strip() for value in parsed.get("target_roles", {}).get("secondary", []) if str(value).strip())
    keyword_signals = parsed.get("keyword_signals", {})
    for tier in ("tier_a", "tier_b"):
        for item in keyword_signals.get(tier, []):
            for part in str(item).split("|"):
                text = part.strip()
                if text:
                    terms.append(text)
    return terms


def _title_families(text: str) -> set[str]:
    lowered = str(text or "").lower()
    return {
        family
        for family, markers in _TITLE_FAMILY_MARKERS.items()
        if any(marker in lowered for marker in markers)
    }


def _candidate_supports_target_title(title: str, profile_pack: str) -> bool:
    if not profile_pack.strip():
        return True

    terms = _candidate_title_safety_terms(profile_pack)
    if any(_matches_profile_phrase(title, term) for term in terms):
        return True

    title_families = _title_families(title)
    if not title_families:
        return False

    profile_family_text = "\n".join(terms)
    profile_families = _title_families(profile_family_text)
    return bool(title_families & profile_families)


def build_triage_agent(model: str, profile_summary: str) -> Agent:
    instructions = TRIAGE_INSTRUCTIONS_TEMPLATE.format(profile_summary=profile_summary)
    return Agent(
        name="triage_agent",
        model=model,
        instructions=instructions,
        output_type=TriageOut,
    )


def triage_stage_factory(
    model: str,
    max_ad_text_chars: int,
    safety_rules: dict,
    profile_pack: str = "",
    triage_profile_summary: str = "",
    targeting_title_patterns: list[str] | None = None,
    semantic_threshold: float = 0.0,
    semantic_model: str = "BAAI/bge-small-en-v1.5",
):
    sr = safety_rules or {}

    if os.getenv("JOBPIPE_DEBUG_CONFIG") == "1":
        print("TRIAGE safety_rules keys:", sorted(sr.keys()))

    target_pat = sr.get("target_title_regex", "") or ""
    hard_no_pat = sr.get("hard_no_title_regex", "") or ""

    very_strong_pat = sr.get("very_strong_positive_regex", "") or ""
    weak_pat = sr.get("weak_positive_regex", "") or ""
    anchor_pat = sr.get("weak_anchor_regex", "") or ""

    target_re = re.compile(target_pat, re.I) if target_pat else None
    hard_no_re = re.compile(hard_no_pat, re.I) if hard_no_pat else None

    very_strong_re = re.compile(very_strong_pat, re.I) if very_strong_pat else None
    weak_re = re.compile(weak_pat, re.I) if weak_pat else None
    anchor_re = re.compile(anchor_pat, re.I) if anchor_pat else None

    never_skip_title = bool(sr.get("never_skip_if_title_matches", True))

    weak_conf_max = float(sr.get("weak_override_max_skip_confidence", 0.45))
    weak_min_hits = int(sr.get("weak_override_min_hits", 4))
    weak_min_hits_anchor = int(sr.get("weak_override_min_hits_with_anchor", 2))

    geo_enabled = bool(sr.get("geo_enabled", False))
    geo_postal_pat = sr.get("geo_postal_regex", "") or ""
    geo_postal_re = re.compile(geo_postal_pat) if geo_postal_pat else None

    geo_remote_pat = sr.get("geo_allow_remote_regex", "") or ""
    geo_remote_re = re.compile(geo_remote_pat, re.I) if geo_remote_pat else None

    geo_county_pat = sr.get("geo_county_regex", "") or ""
    geo_county_re = re.compile(geo_county_pat, re.I) if geo_county_pat else None

    # Build agent with profile baked into instructions — no need to send profile in user input
    profile_summary = triage_profile_summary or (_extract_profile_summary(profile_pack) if profile_pack else "")
    candidate_supports_target_title = (
        lambda title: _candidate_supports_target_title(title, profile_pack)
        if profile_pack
        else True
    )
    agent = build_triage_agent(model, profile_summary)

    # Semantic pre-filter: free local embeddings before any LLM call.
    # Enabled when semantic_threshold > 0 and fastembed is installed.
    # No-op (pass-through) if fastembed is missing or threshold is 0.
    semantic_check = (
        build_semantic_filter(
            threshold=semantic_threshold,
            profile_pack=profile_pack,
            model_name=semantic_model,
        )
        if semantic_threshold > 0 and profile_pack
        else (lambda ctx: ctx)
    )

    def should_run(ctx: JobContext) -> bool:
        return True

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        job = ctx.job
        title = (job.get("normalized_title") or job.get("title") or "").strip()
        title_matches_targeting = bool(target_re and target_re.search(title)) or _title_matches_targeting_patterns(
            title,
            targeting_title_patterns,
        )
        pretriage_policy = str(job.get("intake_pretriage_policy") or "").strip().lower()
        is_suggested_lead = pretriage_policy == "suggested_lead" or (
            not pretriage_policy and bool(job.get("suggested_by_platform"))
        )

        # --- HARD GEO before AI ---
        if geo_enabled and geo_postal_re and not is_suggested_lead:
            postals = _get_postals(job)
            postal = postals[0] if postals else ""

            # Only check specific work-arrangement fields for remote/hybrid —
            # NOT the full description (too many false positives from e.g. "hybrid culture")
            remote_hay = "\n".join([
                title,
                postal,
                (job.get("work_city") or ""),
                (job.get("work_county") or ""),
                (job.get("remote") or ""),
                (job.get("work_type") or ""),
                (job.get("workType") or ""),
                (job.get("work_arrangement") or ""),
                (job.get("workArrangement") or ""),
                (job.get("homeoffice") or ""),
                # Allow scanning first 300 chars of description (headline/intro only)
                (job.get("description_html") or "")[:300],
            ])

            # allow remote if any remote-signal in targeted fields / intro
            if geo_remote_re and geo_remote_re.search(remote_hay):
                pass
            else:
                if postals and not any(geo_postal_re.search(p) for p in postals):
                    # Postal codes present but none in allowed zones → hard SKIP
                    ctx.triage = TriageOut(
                        triage_decision="SKIP",
                        confidence=0.95,
                        explanation=f"Geo filter: postalCode(s) {postals} ikke tillatt",
                        signals=["geo_postal_skip"] + postals[:3],
                        forced_safety=False,
                        hard_gates=_hard_gate_snapshot(geo_gate=False, blocker_reasons=["geo_postal_skip"]),
                    )
                    return ctx

                if not postals and geo_county_re:
                    # No postal code — fall back to county field.
                    # If county is explicitly set and NOT in the allowed list → SKIP.
                    # If county is absent or unknown, let the AI decide (don't hard-block).
                    county_hay = " ".join(filter(None, [
                        job.get("work_county") or "",
                        job.get("county") or "",
                        job.get("municipality") or "",
                        job.get("work_municipality") or "",
                    ])).strip()
                    if county_hay and not geo_county_re.search(county_hay):
                        ctx.triage = TriageOut(
                            triage_decision="SKIP",
                            confidence=0.90,
                            explanation=f"Geo filter: fylke/kommune '{county_hay[:60]}' ikke i tillatt sone",
                            signals=["geo_county_skip", county_hay[:40]],
                            forced_safety=False,
                            hard_gates=_hard_gate_snapshot(geo_gate=False, blocker_reasons=["geo_county_skip"]),
                        )
                        return ctx

        # --- HARD NO title filter (unless title is target) ---
        if hard_no_re and hard_no_re.search(title):
            if not title_matches_targeting:
                ctx.triage = TriageOut(
                    triage_decision="SKIP",
                    confidence=0.85,
                    explanation="Hard-no role type matched title",
                    signals=["hard_no_title"],
                    forced_safety=False,
                    hard_gates=_hard_gate_snapshot(title_gate=False, blocker_reasons=["hard_no_title"]),
                )
                return ctx

        # --- SEMANTIC PRE-FILTER (free, local embeddings) ---
        # Runs after all free regex checks, before the LLM.
        # Sets ctx.triage if similarity is below threshold — no LLM call needed.
        # Safety override: if title matches a primary target, never let semantic filter kill it.
        ctx = semantic_check(ctx)
        if ctx.triage is not None:
            if title_matches_targeting and candidate_supports_target_title(title):
                # Title is a primary target — override semantic SKIP, let LLM decide
                ctx.triage = None
                pre = list(ctx.notes.get("pre_signals") or [])
                pre.append("semantic_target_override")
                ctx.notes["pre_signals"] = pre
            elif is_suggested_lead:
                # Platform-suggested jobs are a calibration signal:
                # FINN/LinkedIn suggestions are already pre-vetted by the source platform.
                # Never let the semantic filter kill it — let the LLM decide.
                ctx.triage = None
                pre = list(ctx.notes.get("pre_signals") or [])
                pre += ["platform_suggested", "semantic_target_override"]
                ctx.notes["pre_signals"] = pre
            else:
                return ctx

        text = job_excerpt(job, max_ad_text_chars)
        header = build_job_header(job)

        # Profile is already baked into agent instructions — no need to repeat it here
        input_text = (
            "=== STILLING ===\n"
            + header
            + "\n=== ANNONSETEXT (utdrag) ===\n"
            + text
        )

        result = run_agent(agent, input_text, trace={"stage": "triage", "job_id": ctx.job_id})
        out = result.final_output_as(TriageOut)
        # All deterministic hard gates passed — record that the LLM stage was reached.
        out.hard_gates = _passing_hard_gates()

        # Append sem score to signals for calibration visibility (only for jobs that
        # passed the semantic filter — blocked ones already have sim: in their signals)
        sem_score = ctx.notes.get("sem_score")
        if sem_score is not None and not any(s.startswith("sim:") for s in (out.signals or [])):
            out.signals = list(out.signals or []) + [f"sim:{sem_score:.2f}"]

        # Propagate platform_suggested signal from pre-filter stage into LLM output.
        # This survives all the way to the ledger so we can identify calibration mismatches.
        if is_suggested_lead and "platform_suggested" not in (out.signals or []):
            out.signals = list(dict.fromkeys((out.signals or []) + ["platform_suggested"]))

        # Merge any pre-LLM override signals stored in ctx.notes into out.signals.
        pre_signals = ctx.notes.get("pre_signals") or []
        if pre_signals:
            out.signals = list(dict.fromkeys((out.signals or []) + pre_signals))

        joined = f"{title}\n{text}"

        if out.triage_decision == "SKIP":
            conf = float(out.confidence or 0.0)
            target_title_match = bool(target_re and target_re.search(title))
            candidate_title_supported = candidate_supports_target_title(title)

            # 1) Title-target should never SKIP
            if never_skip_title and target_title_match and candidate_title_supported:
                out.triage_decision = "REVIEW"
                out.forced_safety = True
                out.explanation = (out.explanation or "") + " | forced REVIEW (target-title safety)"
                out.signals = list(dict.fromkeys((out.signals or []) + ["safety:target_title"]))
            elif target_title_match and not candidate_title_supported:
                out.signals = list(dict.fromkeys((out.signals or []) + ["candidate_target_title_mismatch"]))

            else:
                # 2) Very-strong override: require >=2 hits unless title itself hits
                vs_hits = _uniq_hits(very_strong_re, joined, limit=6)
                vs_title_hit = bool(very_strong_re.search(title)) if very_strong_re else False

                if vs_title_hit or len(vs_hits) >= 2:
                    out.triage_decision = "REVIEW"
                    out.forced_safety = True
                    out.explanation = (out.explanation or "") + " | forced REVIEW (very-strong safety)"
                    out.signals = list(
                        dict.fromkeys((out.signals or []) + ["safety:very_strong"] + [f"vs:{h}" for h in vs_hits])
                    )

                else:
                    # 3) Weak override:
                    #    - anchor path ignores confidence
                    #    - weak-only path still gated by confidence
                    weak_hits = _uniq_hits(weak_re, joined, limit=12)
                    anchor_hit = bool(anchor_re.search(joined)) if anchor_re else False

                    should_force = (
                        (anchor_hit and len(weak_hits) >= weak_min_hits_anchor)
                        or (conf <= weak_conf_max and len(weak_hits) >= weak_min_hits)
                    )

                    if should_force:
                        out.triage_decision = "REVIEW"
                        out.forced_safety = True
                        out.explanation = (out.explanation or "") + " | forced REVIEW (weak safety)"
                        out.signals = list(
                            dict.fromkeys(
                                (out.signals or [])
                                + ["safety:weak", f"weak_hits:{len(weak_hits)}", f"anchor:{int(anchor_hit)}"]
                                + [f"wk:{h}" for h in weak_hits[:8]]
                            )
                        )

        ctx.triage = out
        return ctx

    return should_run, run

"""Generate a cover letter using the OpenAI API.

Language is determined by the job ad: Norwegian by default, English for English
job ads. Override via ctx.language_override ('no' | 'en').
"""
from __future__ import annotations

import json
import os
from typing import List

import openai

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.language_routing import get_document_language

# Phrases that must never appear in the output — even when they come from input evidence.
# detect-and-retry uses this list.
_HARD_BANNED: List[str] = [
    # Generic team/process clichés
    "tverrfaglige team",
    "tverrfaglig team",
    "tverrfaglig samarbeid",
    "kontinuerlig forbedring",
    "interessenter",
    "endringsprosesser",
    "brukervennlige løsninger",
    "skape verdi",
    "reell verdi",
    "praktisk og resultatorientert",
    "motivert for å bidra",
    "spesielt motivert",
    "cross-functional",
    "sterk teknisk",
    "sterk forståelse",
    "sterk kommunikator",
    "sterke resultater",
    "offentlig sektor",
    "rask tilpasningsevne",
    "vilje til å bygge",
    "tverrfaglig koordinering",
    # User-in-center buzzwords
    "brukeren i sentrum",
    "brukerfokus",
    "helhetlige løsninger",
    # Weak gap apology patterns (all variants)
    "selv om jeg ikke har eksplisitt erfaring",
    "selv om jeg ikke har direkte erfaring",
    "selv om jeg mangler direkte erfaring",
    "selv om jeg mangler eksplisitt erfaring",
    "rask til å tilpasse meg",
    "raskt å tilpasse meg",
    "raskt tilpasse meg",
    "bygge nødvendig domenekunnskap",
    "bygge nødvendig kunnskap",
    "tilegne meg ny domenekunnskap",
    "tilegne meg kunnskap om",
    # Generic closing phrases — "looking forward to" variants
    "robuste og fleksible løsninger",
    "ser frem til å bidra med min kompetanse",
    "ser frem til muligheten til å",
    "ser frem til å kunne",
    "ser frem til å bringe",
    "ser frem til å anvende",
    "ser frem til å kombinere",
    "anvende min kompetanse",
    "bringe min kompetanse",
    "solid fundament for å bidra",
    # Generic "support their goals" variants
    "støtte deres mål om",
    "støtte bane nor",
    "i deres mål om",
    "bidra til utviklingen av",
    "bidra til bane nors",
    "bidra til deres",
    "i en ny kontekst",
    "en spennende mulighet for meg",
    "kombinere min praktiske erfaring med",
    "kombinere min erfaring med den strategiske",
]


_HARD_BANNED_EN: List[str] = [
    "cross-functional teams",
    "continuous improvement",
    "stakeholders",
    "change management",
    "user-friendly solutions",
    "create value",
    "deliver value",
    "results-oriented",
    "motivated to contribute",
    "strong technical skills",
    "strong communication skills",
    "strong understanding",
    "public sector",
    "although i don't have direct experience",
    "although i lack direct experience",
    "quickly adapt to",
    "build the necessary knowledge",
    "acquire the necessary knowledge",
    "looking forward to contributing",
    "looking forward to the opportunity",
    "looking forward to bringing my skills",
    "apply my skills",
    "bring my expertise",
    "solid foundation for contributing",
    "support your goals",
    "contribute to the development of",
    "an exciting opportunity for me",
    "combine my experience with",
]


def _banned_violations(text: str, language: str = "no") -> List[str]:
    banned = _HARD_BANNED_EN if language == "en" else _HARD_BANNED
    t = text.lower()
    return [p for p in banned if p.lower() in t]

_SYSTEM_PROMPT = """Du er en norsk søknadsassistent. Du skriver motivasjonsbrev — ikke CV-oppsummeringer.

CV-en gjør den faktamessige tunge løftingen. Brevets oppgave er å svare på tre spørsmål rekrutterer stiller seg:
1. Hvorfor vil du ha akkurat denne jobben?
2. Hva er det ved denne rollen og denne arbeidsgiveren som treffer deg spesifikt?
3. Hvorfor nå — hva gjør dette til riktig tidspunkt for deg?

Bruk `narrative_why_me_now`, `cover_letter_strategy` og `recruiter_hook` til å svare på disse. Evidens fra `selected_evidence` og `motivation_context` støtter argumentet — men er ikke selve argumentet.

Dersom `voice_guide` er inkludert, følg stilreglene der. Dersom `motivation_context` er inkludert, bruk det som faktabase — men skriv aldri inn noe som ikke er direkte relevant for denne spesifikke stillingen.

## Absolutte regler

1. **Verdiframe — gjelder hele brevet.** Hvert punkt skal svare på spørsmålet «hva får arbeidsgiveren?», ikke «hva har jeg gjort?». Dette betyr to ting i praksis:
   - Setninger starter ikke med «Jeg» — arbeidsgiveren er protagonisten, kandidaten er løsningen som dukker opp.
   - Formuleringen snur fra selvbeskrivelse til levert verdi: ikke «Jeg har syv års erfaring med ePages» men «Syv år med ePages på tvers av 12 markeder gir [arbeidsgiver] en produkteier som ikke trenger onboarding på tjenestestyring».
   «Jeg» er tillatt som grammatisk lim midt i en setning («Som produkteier hos Brownells koordinerte jeg...»), aldri som åpningsord.

2. **Fakta fra konteksten — aldri oppfinn.** Hvert avsnitt MÅ inneholde minst ett konkret navn (selskap, prosjekt, verktøy) fra `selected_evidence` eller `motivation_context`.

3. **Evidens-avsnittet er tett.** 2–4 konkrete navn per avsnitt der evidens brukes — men dette er støtten, ikke hele brevet.

4. **HARD BLOCK — disse frasene er totalforbudt.** De må ALDRI forekomme i output — selv om de finnes i job description, evidence eller motivation_context. Kopier aldri fra inputen.

   **Eksakt forbudte strenger (søk og ødelegg):**
   - «tverrfaglige team» / «tverrfaglig team» / «tverrfaglig samarbeid»
   - «kontinuerlig forbedring»
   - «praktisk og resultatorientert», «skape verdi», «reell verdi», «brukervennlige løsninger»
   - «interessenter», «endringsprosesser»
   - «engasjert», «motivert for å bidra», «brennende opptatt av», «sterk kommunikator»
   - «offentlig sektor» (med mindre det er eksplisitt i profilen), «cross-functional»
   - Aldri oppgi karakterer eller grades — nevn prosjektnavn og tema, ikke resultatet
   - Enhver setning som kunne stå i hvem som helst sitt brev

   **Alternativ når du trenger å uttrykke konseptet:**
   - «tverrfaglige team» → navngi de faktiske teamene/funksjonene: «scrum-teamet hos Brownells», «Merkle og Møller Mobility Group»
   - «kontinuerlig forbedring» → beskriv hva som ble forbedret konkret: «reduserte onboarding-tid», «utrulling av Zendesk i 12 markeder»

5. **Gap nevnes maks én gang, i én setning, aldri i åpningen.** Koble gapet til noe konkret som skjedde i mellomtiden (BI, prosjekter). Ikke unnskylde.

6. **3–4 avsnitt, 300–400 ord.** Ikke kortere, ikke lenger.

7. **Bare brevteksten.** Ingen «Til [selskap]», ingen «Med vennlig hilsen», ingen [Navn]. Kurs er ikke arbeidserfaring. BI Executive Master-moduler med prosjektnavn er substansiell evidens.

## Struktur — "Språklig bue"

Brevet har en gjennomgående bue: hvert avsnitt svarer på det neste spørsmålet rekrutterer stiller seg.

**Avsnitt 1 — Rollen og organisasjonsutfordringen**
IKKE begynn med «Jeg» eller selvintroduksjon. Ramm inn hva rollen faktisk sitter i — hvilken spenning, utfordring eller veikryss denne arbeidsgiveren er i. Bruk `cover_letter_strategy` eller `recruiter_hook`. Slutt med én setning som knytter kandidatprofilen til nettopp dette skjæringspunktet.
Spørsmålet dette svarer: «Forstår du hva jobben faktisk er?»

**Avsnitt 2 — Operasjonelt bevis**
Navngi selskaper, verktøy og prosjekter. Eksempel-tetthet:
> «Som prosjektleder hos Merkle (Dentsu) koordinerte jeg CRM-integrerte løsninger for Møller Mobility Group (Adobe Campaign) og dynamiske kampanjer for Jaguar Land Rover. I Brownells Europe var jeg produkteier for e-handelsplattform og markedsföringsplattform på tvers av 12 land — inkludert utrulling av Zendesk i 12 markeder, fem nye nettbutikker og regulatorisk etterlevelse (GDPR, PSD2, Watchdog Elite).»
Spørsmålet dette svarer: «Kan du faktisk gjøre jobben?»

**Avsnitt 3 — Motivasjon: Hvorfor denne jobben, hvorfor nå**
Dette er hjerteavsnittet. Bruk `narrative_why_me_now` direkte hvis tilgjengelig. Dersom `narrative_why_me_now` er tomt, bygg avsnittets kjerne fra `motivation_context` — finn det som er genuint sant og spesifikt for AKKURAT DENNE arbeidsgiveren og rollen, ikke generisk «samfunnsnytte». Koble BI-studiene (modulnavn, prosjektnavn — aldri karakterer) eksplisitt til det arbeidsgiveren etterspør: ikke bare «jeg studerer X», men «[Prosjekt X] handlet om nettopp [Y] som er det dere trenger her». Nevn gap her hvis nødvendig (én setning, koblet til BI eller annet konkret). Avslutt med initiativ-setning fra `voice_guide`-mønsteret.
Spørsmålet dette svarer: «Hvorfor vil du ha akkurat denne jobben — og hvorfor nå?»

**Avsnitt 4 (valgfritt, maks 2 setninger):** Lokal tilknytning eller personlig kontekst hvis det tilfører noe ekte.

## Bruk av valgfrie felt

- `narrative_why_me_now` → hjerteavsnittet — alltid inkluder hvis tilgjengelig. Dersom tomt: bruk `motivation_context` til å konstruere et genuint, stillingsspecifikt avsnitt 3
- `cover_letter_strategy` → åpningsvinkel, følg den nøye
- `recruiter_hook` → inspirasjon til første setning
- `narrative_positioning_angle` → tonen gjennom hele brevet
- `differentiation_signals` → velg 1–2 å veve inn i evidens-avsnittet
- `neutralizing_evidence` → bruk kun hvis det faktisk nøytraliserer et reelt gap
- `fit_gaps` i decision_brief → adresser bare det viktigste, én setning
- `voice_guide` → stilregler og register (cool er default), åpnings-hooks og avslutninger
- `motivation_context` → faktabase for verktøy, roller og prosjekter — bruk kun det som er relevant
"""

_SYSTEM_PROMPT_EN = """You are an English-language job application assistant. You write cover letters — not CV summaries.

The CV handles the factual heavy lifting. The letter answers three questions the recruiter asks:
1. Why do you want this specific job?
2. What is it about this role and this employer that fits you specifically?
3. Why now — what makes this the right moment for you?

Use `narrative_why_me_now`, `cover_letter_strategy`, and `recruiter_hook` to answer these. Evidence from `selected_evidence` and `motivation_context` supports the argument — it is not the argument itself.

## Absolute rules

1. **Value frame — applies to the whole letter.** Every point answers "what does the employer get?", not "what have I done?".
   - Sentences do not start with "I" — the employer is the protagonist, the candidate is the solution that emerges.
   - Flip from self-description to delivered value: not "I have seven years of experience with ePages" but "Seven years with ePages across 12 markets gives [employer] a product owner who needs no onboarding on service governance".
   "I" is allowed as grammatical glue mid-sentence, never as an opener.

2. **Facts from context — never invent.** Every paragraph MUST contain at least one concrete name (company, project, tool) from `selected_evidence` or `motivation_context`.

3. **Evidence paragraph is dense.** 2–4 concrete names per paragraph where evidence is used.

4. **HARD BLOCK — these phrases are totally forbidden.** They MUST NEVER appear in output.

5. **Gap mentioned at most once, in one sentence, never in the opening.** Link the gap to something concrete that happened in the meantime. Do not apologise.

6. **3–4 paragraphs, 300–450 words.** Not shorter, not longer.

7. **Letter text only.** No "To [company]", no "Yours sincerely", no [Name].

## Structure

**Paragraph 1 — The role and the organisational challenge**
Do NOT start with "I" or self-introduction. Frame what the role actually sits inside. Use `cover_letter_strategy` or `recruiter_hook`.

**Paragraph 2 — Operational evidence**
Name companies, tools, and projects. High example density.

**Paragraph 3 — Motivation: why this job, why now**
This is the core paragraph. Use `narrative_why_me_now` directly if available.

**Paragraph 4 (optional, max 2 sentences):** Local connection or personal context if it adds something genuine.
"""

_COT_PROMPT_EN = """You are an application expert. Do NOT write a letter. Do an internal value assessment in bullet points.

Reply ONLY with short analytical bullets — no paragraphs, no letter text.

1. CHALLENGE: [one sentence about the employer's real problem]
2. VALUE FRAME:
   - [company/project A] → [what the employer concretely gets]
   - [company/project B] → [what the employer concretely gets]
3. POSITIONING: [one sentence on what this candidate has that most applicants lack]
4. OPENER: [one sentence opening the letter with the employer's situation — no "I", no candidate wish]
5. WHAT THE EMPLOYER GETS (summary): [one sentence]

Max 150 words total. Bullets only."""

_COT_PROMPT = """Du er en søknadsekspert. Du skal IKKE skrive et brev. Du skal gjøre en intern verdivurdering i punktform.

Svar KUN med korte analytiske punkter — ikke avsnitt, ikke brevtekst.

1. UTFORDRING: [én setning om arbeidsgiverens egentlige problem/veikryss]
2. VERDIFRAME:
   - [selskap/prosjekt A] → [hva arbeidsgiveren konkret får]
   - [selskap/prosjekt B] → [hva arbeidsgiveren konkret får]
   - [utdanning/modul] → [hva arbeidsgiveren konkret får]
3. POSISJONERING: [én setning om hva denne kandidaten har som de fleste søkere mangler]
4. ÅPNER: [én setning som åpner brevet med arbeidsgiverens situasjon — ingen «Jeg», ingen kandidatønske]
5. HVA ARBEIDSGIVEREN FÅR (oppsummert): [én setning]

Maks 150 ord totalt. Bare punkter."""

_COVER_LETTER_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "cover_letter",
        "description": "Return the generated cover letter text.",
        "parameters": {
            "type": "object",
            "properties": {
                "cover_letter": {
                    "type": "string",
                    "description": "Full cover letter in Norwegian, plain text with paragraph breaks (\\n\\n).",
                }
            },
            "required": ["cover_letter"],
        },
    },
}


def generate_cover_letter(
    ctx: AuthoringCaseContext,
    *,
    model: str = "gpt-4o",
) -> str:
    """Call the OpenAI API to write a cover letter. Language is auto-detected from the job ad.

    Returns the letter text. Language can be forced via ctx.language_override ('no' | 'en').
    """
    language = get_document_language(ctx)
    system_prompt = _SYSTEM_PROMPT_EN if language == "en" else _SYSTEM_PROMPT
    cot_prompt = _COT_PROMPT_EN if language == "en" else _COT_PROMPT

    payload: dict = {
        "job_id": ctx.job_id,
        "job_summary": ctx.job_summary,
        "decision_brief": ctx.decision_brief,
        "selected_evidence": ctx.selected_evidence[:8],
        "narrative_brief": ctx.narrative_brief,
        "artifact_plan": ctx.artifact_plan,
    }
    # v3 signals — include only when present so the model isn't distracted by nulls
    if ctx.cover_letter_strategy:
        payload["cover_letter_strategy"] = ctx.cover_letter_strategy
    if ctx.narrative_positioning_angle:
        payload["narrative_positioning_angle"] = ctx.narrative_positioning_angle
    if ctx.narrative_brand_frame:
        payload["narrative_brand_frame"] = ctx.narrative_brand_frame
    if ctx.narrative_why_me_now:
        payload["narrative_why_me_now"] = ctx.narrative_why_me_now
    if ctx.differentiation_signals:
        payload["differentiation_signals"] = ctx.differentiation_signals
    if ctx.recruiter_hook:
        payload["recruiter_hook"] = ctx.recruiter_hook
    if ctx.neutralizing_evidence:
        payload["neutralizing_evidence"] = ctx.neutralizing_evidence
    if ctx.voice_guide:
        payload["voice_guide"] = ctx.voice_guide
    if ctx.motivation_context:
        payload["motivation_context"] = ctx.motivation_context
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    payload_json = json.dumps(payload, ensure_ascii=False)

    # ── Pass 1: Chain-of-thought value reasoning ──────────────────────────────
    # Ask the model to reason through "what does the employer get?" before writing.
    # The reasoning becomes the assistant turn in the generation conversation,
    # so the value frame is in the model's working context when it writes.
    cot_reasoning = ""
    try:
        cot_response = client.chat.completions.create(
            model=model,
            max_tokens=500,
            temperature=0.3,
            messages=[
                {"role": "system", "content": cot_prompt},
                {"role": "user", "content": payload_json},
            ],
        )
        cot_reasoning = (cot_response.choices[0].message.content or "").strip()
    except Exception:
        pass  # CoT is best-effort; fall through to direct generation

    # ── Pass 2: Letter generation with CoT reasoning in context ───────────────
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": payload_json},
    ]
    if cot_reasoning:
        # Inject reasoning as assistant turn → triggers "write from this" pattern
        messages.append({"role": "assistant", "content": cot_reasoning})
        messages.append({
            "role": "user",
            "content": (
                "Skriv nå motivasjonsbrevet basert på verdivurderingen over. "
                "Følg alle regler i systempromptet nøye."
            ),
        })

    def _extract(response) -> str:
        choice = response.choices[0]
        if choice.message.tool_calls:
            call = choice.message.tool_calls[0]
            try:
                args = json.loads(call.function.arguments)
                return str(args.get("cover_letter", "")).strip()
            except Exception:
                pass
        return ""

    for attempt in range(3):
        response = client.chat.completions.create(
            model=model,
            max_tokens=1500,
            temperature=0.3,
            tools=[_COVER_LETTER_TOOL],
            tool_choice={"type": "function", "function": {"name": "cover_letter"}},
            messages=messages,
        )
        letter = _extract(response)
        violations = _banned_violations(letter, language)
        if not violations:
            return letter
        # Retry: tell the model exactly what to fix
        if language == "en":
            correction = (
                f"Your draft contained these forbidden phrases: {violations}. "
                "These phrases are banned even if they appear in the evidence data. "
                "Rewrite the letter completely. Replace forbidden phrases with concrete "
                "company, team, or project names. "
                "None of the forbidden phrases may appear in the new draft."
            )
        else:
            correction = (
                f"Utkastet ditt inneholdt disse totalforbudte frasene: {violations}. "
                "Disse frasene er forbudt selv om de finnes i evidens-dataene. "
                "Skriv brevet helt om. Erstatt forbudte fraser med konkrete selskaps-, team- eller prosjektnavn "
                "(f.eks. «scrum-teamet hos Brownells», «CRM-teamet hos Møller»). "
                "Ingen av de forbudte frasene skal forekomme i det nye utkastet."
            )
        # Append assistant message (tool call) + correction as user turn
        messages.append(response.choices[0].message)
        messages.append({"role": "user", "content": correction})

    return letter  # return last attempt even if still imperfect


__all__ = ["generate_cover_letter"]

"""Generate a Norwegian cover letter using the OpenAI API."""
from __future__ import annotations

import json
import os

import openai

from jobpipe.authoring.case_context import AuthoringCaseContext

_SYSTEM_PROMPT = """Du er en norsk jobbsøkningsassistent.

Du mottar jobbsøknadskontekst som JSON og skriver et skreddersydd søknadsbrev på norsk.

Regler:
- Skriv på bokmål, direkte og troverdig — ingen klisjeer.
- Brevet skal ha 3–4 korte avsnitt: åpning, kjernekompetanse/erfaring, motivasjon, avslutning.
- Bruk konkrete eksempler fra selected_evidence. Finn ikke opp erfaringer.
- Speil cv_focus fra decision_brief for å understreke det arbeidsgiveren verdsetter.
- Unngå fraser som «engasjert lagspiller», «sterk kommunikator», «brennende opptatt av».
- Avslutt med tydelig initiativ, f.eks. «Ser frem til å høre fra dere.»
- Ikke ta med sted/dato, adresse eller hilsenfrase øverst — bare selve brevteksten.
- Maks 350 ord.
"""

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
    model: str = "gpt-4o-mini",
) -> str:
    """Call the OpenAI API to write a Norwegian cover letter. Returns the letter text."""
    payload = {
        "job_id": ctx.job_id,
        "job_summary": ctx.job_summary,
        "decision_brief": ctx.decision_brief,
        "selected_evidence": ctx.selected_evidence[:8],
        "narrative_brief": ctx.narrative_brief,
    }
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=model,
        max_tokens=1500,
        tools=[_COVER_LETTER_TOOL],
        tool_choice={"type": "function", "function": {"name": "cover_letter"}},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    choice = response.choices[0]
    if choice.message.tool_calls:
        call = choice.message.tool_calls[0]
        try:
            args = json.loads(call.function.arguments)
            return str(args.get("cover_letter", "")).strip()
        except Exception:
            pass
    return ""


__all__ = ["generate_cover_letter"]

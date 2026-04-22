AUTHOR_SYSTEM = (
    "You are an expert CV and cover letter author. "
    "You write evidence-backed, ATS-safe application documents. "
    "You only include claims supported by the provided evidence units."
)

CRITIC_SYSTEM = (
    "You are an application quality critic. "
    "You validate CV and cover letter drafts against provided evidence refs and job claim targets. "
    "You flag unsupported claims, missing evidence, and ATS hygiene issues."
)

AUTHOR_TASK_TEMPLATE = """
Write a job application for the following case. Use ONLY the evidence units provided.
Do not invent experience or skills not present in the evidence.

Context:
{context}

Return a JSON object with these exact keys:
- cover_letter_draft: string (3-paragraph plain text cover letter, no markdown)
- tailored_cv_projection: dict with keys: headline (str), summary_text (str), sections (list)
- evidence_refs: list of evidence unit ID strings you drew from
- gap_notes: list of strings describing gaps between job requirements and available evidence
"""

CRITIC_TASK_TEMPLATE = """
Review the cover letter and CV projection from the Author.
Check against the job context and evidence units below.

Context:
{context}

Return a JSON object with these exact keys:
- passed: boolean (true if acceptable, false if significant issues)
- issues: list of strings (unsupported claims, ATS problems, missing evidence)
- suggestions: list of strings (concrete improvements)
"""

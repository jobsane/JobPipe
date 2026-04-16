"""Scan Gmail for job application emails AND platform job suggestions.

TWO MODES:

1. Status scan (default) — scan for application status emails:
   Classifies emails from Jobbnorge, EasyCruit, Teamtailor, WebCruiter etc.
   as: applied, interview, or rejected.
   Matches emails to ledger jobs by employer name fuzzy matching.
   Never overwrites manual entries in application_state.json.

2. Suggestions scan (--scan-suggestions) — scan for platform job recommendations:
   Finds FINN "Ledige stillinger" and LinkedIn "New jobs for you" alert emails.
   Extracts job URLs and stores unprocessed jobs in the primary DB suggestion queue,
   mirroring them to reports/suggested_jobs.jsonl as a compatibility bridge so
   pull_suggested.py can fetch their full content for the pipeline.
   Platform-suggested jobs carry suggested_by_platform=true — the triage stage
   treats this as a calibration signal (lets LLM decide instead of semantic filter).

First-time setup — you need Gmail API credentials:
    1. Go to https://console.cloud.google.com/
    2. Create/select a project, enable the Gmail API
    3. Create OAuth2 credentials (Desktop app type)
    4. Download credentials.json → save to ./reports/gmail_credentials.json
    5. Run: python -m jobpipe.cli.scan_gmail --setup
       (opens browser for one-time OAuth consent)

Usage:
    python -m jobpipe.cli.scan_gmail                          # status scan, last 90 days
    python -m jobpipe.cli.scan_gmail --dry-run                # preview, no writes
    python -m jobpipe.cli.scan_gmail --days 30                # scan last 30 days
    python -m jobpipe.cli.scan_gmail --verbose                # show all processing
    python -m jobpipe.cli.scan_gmail --setup                  # OAuth2 first-time setup
    python -m jobpipe.cli.scan_gmail --scan-suggestions       # suggestion scan
    python -m jobpipe.cli.scan_gmail --scan-suggestions --dry-run  # preview suggestions

Install deps (once):
    pip install google-auth-oauthlib google-api-python-client --break-system-packages
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from jobpipe.cli.mark_status import add_stage
from jobpipe.core.io import load_env_file
from jobpipe.core.paths import (
    application_state_path,
    gmail_credentials_path,
    gmail_token_path,
    primary_db_path,
    suggested_jobs_path,
)
from jobpipe.core.primary_db import connect_primary_db, ensure_candidate, list_suggestion_leads, upsert_suggestion_lead

load_env_file(".env")

# Windows cp1252 consoles can't encode arbitrary Unicode from email data.
# Wrap stdout so non-encodable chars become '?' instead of crashing.
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Gmail API deps — install with:
#   pip install google-auth-oauthlib google-api-python-client --break-system-packages
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

DEFAULT_STATE_PATH = application_state_path()
DEFAULT_LEDGER_PATH = Path("./reports/ledger.sqlite")
DEFAULT_TOKEN_PATH = gmail_token_path()
DEFAULT_CREDS_PATH = gmail_credentials_path()
DEFAULT_DB_PATH = primary_db_path()
DEFAULT_SUGGESTED_PATH = suggested_jobs_path()
DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def _suggestion_external_id(entry: Dict[str, Any]) -> str:
    return str(entry.get("finnkode") or entry.get("linkedin_job_id") or entry.get("external_id") or "").strip()


def _suggestion_key(platform: str, external_id: str) -> str:
    return f"{platform}:{external_id}"


def _suggestion_id(candidate_id: str, platform: str, external_id: str) -> str:
    raw = f"{candidate_id}|{platform}|{external_id}"
    return "suggestion_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _load_existing_suggestion_keys(
    suggested_path: Path,
    db_path: Path,
    candidate_id: str,
) -> set[str]:
    keys: set[str] = set()

    if db_path.exists():
        try:
            conn = connect_primary_db(db_path)
            try:
                for row in list_suggestion_leads(conn, candidate_id):
                    platform = str(row.get("platform") or "").strip()
                    external_id = str(row.get("external_id") or "").strip()
                    if platform and external_id:
                        keys.add(_suggestion_key(platform, external_id))
            finally:
                conn.close()
        except Exception:
            pass

    if suggested_path.exists():
        try:
            for line in suggested_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                platform = str(entry.get("platform") or "").strip()
                external_id = _suggestion_external_id(entry)
                if platform and external_id:
                    keys.add(_suggestion_key(platform, external_id))
        except Exception:
            pass

    return keys

# Priority order for status upgrades (higher = more final)
_STATUS_ORDER: Dict[str, int] = {
    "shortlisted": 1,
    "applied": 1,
    "interview": 2,
    "rejected": 3,
    "dismissed": 3,
}

# --- Email classification patterns (Norwegian + English) ---

_INTERVIEW_RE = re.compile(
    r"intervju|interview|innkalling|vi\s+ønsker\s+å\s+invitere|samtale\s+til|"
    r"invit\w+\s+til\s+(et\s+)?intervju|we\s+(would\s+like|invite)\s+you\s+to|"
    r"kandidat\s+til\s+intervju|gå\s+videre\s+til|neste\s+runde",
    re.IGNORECASE,
)

_REJECTED_RE = re.compile(
    r"dessverre|ikke\s+gå\s+videre|ikke\s+aktuell|"
    r"har\s+valgt\s+andre|ikke\s+valgt|beklageligvis|"
    r"vi\s+har\s+besluttet|ikke\s+vil\s+gå\s+videre\s+med|"
    r"unfortunately|we\s+regret|not\s+moving\s+forward|"
    r"we\s+have\s+chosen\s+other|we\s+will\s+not\s+be\s+moving|"
    r"not\s+selected|position\s+has\s+been\s+filled",
    re.IGNORECASE,
)

_APPLIED_RE = re.compile(
    r"bekreftelse\s+på\s+(mottatt\s+)?søknad|søknad\s+er\s+mottatt|"
    r"mottatt\s+søknad|vi\s+har\s+mottatt\s+din\s+søknad|"
    r"din\s+søknad\s+er\s+registrert|takk\s+for\s+din\s+søknad|"
    r"takk\s+for\s+søknaden\s+din|"      # FINN exact subject: "Takk for søknaden din"
    r"søknaden\s+din\s+er\s+(mottatt|registrert|sendt)|"
    r"din\s+søknad\s+.{0,40}?er\s+nå\s+sendt\s+til|"  # FINN body: "Din søknad ... er nå sendt til"
    r"application\s+received|received\s+your\s+application|"
    r"thank\s+you\s+for\s+(your\s+)?applying|thanks\s+for\s+applying|"
    r"your\s+application\s+(has\s+been\s+)?(received|submitted|sent)",
    re.IGNORECASE,
)

# Known job portal / ATS sender domains (used for employer extraction hints,
# NOT as the primary filter — we search by content, not by sender)
_PORTAL_DOMAINS = {
    "jobbnorge.no",
    "easycruit.com",
    "teamtailor",         # teamtailor-mail.com, mail.teamtailor.com, etc.
    "webcruitermail.no",  # actual sender domain for WebCruiter emails
    "webcruiter.com",
    "recruitpartner.no",
    "talentech.email",    # Talentech (recruitment@rm.talentech.email)
    "xcruiter.no",        # Xcruiter ATS
    "jobylon.com",        # Jobylon ATS
    "visma.com",          # Visma Recruit
    "reachmee.com",
    "greenhouse.io",
    "lever.co",
    "workday.com",
    "linkedin.com",
    "finn.no",
    "stepstone.no",
    "jobindex.no",
    "jobs2web.com",       # Career sites (Norwegian Air, Orkla, etc.)
}

# --- Suggestion email detection patterns ---
# Job recommendation emails from FINN and LinkedIn carry a platform relevance signal:
# their algorithm already decided this job matches Lars's profile. If our pipeline
# disagrees, that's worth investigating (calibration signal).

_FINN_ALERT_SENDER_RE = re.compile(r"(?:@|\.)\bfinn\.no\b", re.IGNORECASE)
_FINN_ALERT_SUBJECT_RE = re.compile(
    r"ledige\s+stillinger|jobbvarsel|nye\s+jobber|stillinger\s+som\s+(kan\s+)?pass|"
    r"jobb.*anbefal|anbefal.*jobb|ny.*stilling.*for\s+deg",
    re.IGNORECASE,
)
_LINKEDIN_ALERT_SENDER_RE = re.compile(r"linkedin\.com", re.IGNORECASE)
_LINKEDIN_ALERT_SUBJECT_RE = re.compile(
    r"jobs?\s+(you\s+may|matching|for\s+you|we\s+think)|new\s+jobs?\s+matching|"
    r"job\s+alert|\d+\s+new\s+jobs?|recommended\s+jobs?|jobber\s+(for\s+deg|som\s+passer)|"
    r"jobs?\s+in\s+your\s+network",
    re.IGNORECASE,
)

# URL patterns for extracting job IDs from email body/href content.
# IMPORTANT: FINN and LinkedIn use click-tracking redirect URLs, so job IDs
# can appear URL-encoded inside tracking hrefs.
# e.g. https://click.finn.no/track/click?u=https%3A%2F%2Fwww.finn.no%2Fjob%2F...%3Ffinnkode%3D378542101
# We match finnkode wherever it appears (encoded or not).
_FINN_FINNKODE_RE = re.compile(
    r"finnkode(?:[=%3D]|%253D)+(\d{7,10})",   # =, %3D (once-encoded), %253D (twice-encoded)
    re.IGNORECASE,
)
# Also match path-based FINN job URLs (direct or encoded)
_FINN_URL_RE = re.compile(
    r"finn\.no(?:/|%2F)(?:job|stillinger)(?:[^\"'\s]*?)(?:/|%2F)(?:ad\.html[?%]|annonse(?:/|%2F))(?:[^\"'\s]*?finnkode(?:[=%3D]|%253D)+)?(\d{7,10})",
    re.IGNORECASE,
)
_LINKEDIN_URL_RE = re.compile(
    r"linkedin\.com(?:/|%2F)(?:comm(?:/|%2F))?jobs(?:/|%2F)view(?:/|%2F)(\d{6,15})",
    re.IGNORECASE,
)


def _build_suggestion_queries(after_str: str) -> List[str]:
    """Gmail search queries targeting FINN and LinkedIn job alert/recommendation emails.

    Broad queries: we cast wide and let URL extraction + status-email filter decide.
    """
    return [
        # FINN — all emails from finn.no that aren't already-processed status emails
        f"from:finn.no after:{after_str}",
        f"from:jobbvarsel@finn.no after:{after_str}",
        f"from:varsler@finn.no after:{after_str}",
        # LinkedIn — all job-related emails
        f"from:jobalerts-noreply@linkedin.com after:{after_str}",
        f"from:jobs-noreply@linkedin.com after:{after_str}",
        f"from:linkedin.com (jobs OR stillinger OR job) after:{after_str}",
    ]


def _extract_job_urls_from_payload(payload: Dict[str, Any]) -> List[str]:
    """Collect all URLs from HTML/text parts of a Gmail payload (before tag-stripping).

    We need the raw href values before HTML stripping to find FINN/LinkedIn job URLs.
    """
    urls: List[str] = []

    def _walk(part: Dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data", "")
        if data and mime in ("text/html", "text/plain"):
            try:
                text = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                # Extract href="..." values (most reliable for HTML emails)
                for m in re.finditer(r'href=["\']([^"\'>\s]+)', text, re.IGNORECASE):
                    urls.append(m.group(1))
                # Also scan bare https:// URLs (plain text emails and fallback)
                for m in re.finditer(r"https?://[^\s\"'<>\]]+", text):
                    urls.append(m.group(0))
            except Exception:
                pass
        for sub in part.get("parts", []):
            _walk(sub)

    _walk(payload)
    return urls


def _extract_suggestion_jobs(urls: List[str]) -> List[Dict[str, Any]]:
    """Extract FINN finnkodes and LinkedIn job IDs from a list of URLs.

    Handles both direct URLs and click-tracking redirect URLs where the job URL
    is URL-encoded inside the tracking href. We search the raw URL text for
    finnkode/jobId regardless of encoding depth.
    """
    found: Dict[str, Dict[str, Any]] = {}

    for url in urls:
        # Decode the URL once to handle single-level encoding (%3D → =, %2F → /)
        # Keep the original too, so we match both forms.
        try:
            from urllib.parse import unquote
            url_decoded = unquote(url)
        except Exception:
            url_decoded = url

        for candidate in (url, url_decoded):
            # FINN: search for finnkode anywhere in the URL (encoded or plain)
            for m in _FINN_FINNKODE_RE.finditer(candidate):
                fk = m.group(1)
                key = f"finn:{fk}"
                if key not in found:
                    found[key] = {
                        "platform": "finn",
                        "finnkode": fk,
                        "job_url": f"https://www.finn.no/job/fulltime/ad.html?finnkode={fk}",
                        "job_id_hint": f"finn_{fk}",
                    }

            # Also try path-based FINN URL matching (direct links without finnkode param)
            for m in _FINN_URL_RE.finditer(candidate):
                if m.group(1):  # path-based match has the ID in group 1
                    fk = m.group(1)
                    key = f"finn:{fk}"
                    if key not in found:
                        found[key] = {
                            "platform": "finn",
                            "finnkode": fk,
                            "job_url": f"https://www.finn.no/job/fulltime/ad.html?finnkode={fk}",
                            "job_id_hint": f"finn_{fk}",
                        }

            # LinkedIn: job view ID in URL path
            for m in _LINKEDIN_URL_RE.finditer(candidate):
                lid = m.group(1)
                key = f"linkedin:{lid}"
                if key not in found:
                    found[key] = {
                        "platform": "linkedin",
                        "linkedin_job_id": lid,
                        "job_url": f"https://www.linkedin.com/jobs/view/{lid}",
                        "job_id_hint": f"linkedin_{lid}",
                    }

    return list(found.values())


# --- Gmail search queries ---
# Strategy: search primarily by CONTENT (subject keywords), not by sender.
# Portal-specific sender queries are kept as extras to catch edge cases
# where subject lines are vague (e.g. Jobbnorge "Du har mottatt en ny melding").

def _build_queries(after_str: str) -> List[str]:
    return [
        # --- TIER 1: Pre-curated labels (highest precision) ---
        # Application status emails — search full history (no date limit).
        'label:"Jobb/Jobbsøk/Status jobbsøknad"',
        # Broader job search label — still likely to contain application emails
        f'label:"Jobb/Jobbsøk" after:{after_str}',

        # --- TIER 2: Content-based (catches any employer/ATS, any sender) ---
        # Application confirmations
        f"(subject:søknad) (subject:bekreftelse OR subject:mottatt OR subject:registrert) after:{after_str}",
        f"(subject:application) (subject:received OR subject:confirmation OR subject:submitted) after:{after_str}",
        f"subject:\"takk for din søknad\" after:{after_str}",
        f"subject:\"takk for søknaden\" after:{after_str}",
        f"subject:\"thank you for applying\" after:{after_str}",
        f"subject:\"thanks for applying\" after:{after_str}",
        # Interview invitations
        f"subject:intervju (søknad OR stilling OR kandidat) after:{after_str}",
        f"subject:interview (application OR position OR candidate) after:{after_str}",
        f"subject:innkalling after:{after_str}",
        # Rejections
        f"subject:dessverre (søknad OR stilling OR kandidat) after:{after_str}",
        f"(subject:unfortunately OR subject:\"not moving forward\") (application OR position) after:{after_str}",

        # --- TIER 3: Portal-specific (catches vague subject lines) ---
        f"from:jobbnorge.no after:{after_str}",
        f"from:easycruit.com after:{after_str}",
        f"from:teamtailor after:{after_str}",
        f"from:webcruitermail.no after:{after_str}",
        f"from:recruitpartner.no after:{after_str}",
        f"from:talentech.email after:{after_str}",
        f"from:xcruiter.no after:{after_str}",
        f"from:jobylon.com after:{after_str}",
        f"from:linkedin.com (søknad OR application OR intervju OR interview OR dessverre OR unfortunately) after:{after_str}",
        f"from:cmt@finn.no after:{after_str}",
        f"from:noreply@finn.no (søknad OR stilling) after:{after_str}",
    ]


# --- Gmail API helpers ---

def _check_deps() -> bool:
    if not GMAIL_AVAILABLE:
        print(
            "Error: Gmail API packages not installed.\n"
            "Run: pip install google-auth-oauthlib google-api-python-client --break-system-packages",
            file=sys.stderr,
        )
        return False
    return True


def _get_credentials(token_path: Path, creds_path: Path) -> Optional[Any]:
    """Load or refresh OAuth2 credentials, prompting for consent if needed."""
    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Warning: token refresh failed ({e}). Re-running OAuth flow.", file=sys.stderr)
                creds = None

        if not creds:
            if not creds_path.exists():
                print(
                    f"Error: Gmail credentials file not found: {creds_path}\n"
                    "Run:  python -m jobpipe.cli.scan_gmail --setup\n"
                    "See module docstring for setup instructions.",
                    file=sys.stderr,
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def _strip_html(html: str) -> str:
    """Very lightweight HTML tag stripper — good enough for body text matching."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&(?:nbsp|amp|quot|lt|gt|raquo|laquo);", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _decode_body(payload: Dict[str, Any]) -> str:
    """Recursively extract body text from a Gmail payload.

    Prefers text/plain. Falls back to text/html (tags stripped) so that
    HTML-only emails (e.g. Jobbnorge) still yield searchable text.
    """
    plain: list = []
    html: list = []

    def _walk(part: Dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data", "")
        if data:
            try:
                decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                if mime == "text/plain":
                    plain.append(decoded)
                elif mime == "text/html":
                    html.append(decoded)
            except Exception:
                pass
        for sub in part.get("parts", []):
            _walk(sub)

    _walk(payload)
    if plain:
        return plain[0]
    if html:
        return _strip_html(html[0])
    return ""


def _parse_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Extract useful fields from a raw Gmail message object."""
    headers = {
        h["name"].lower(): h["value"]
        for h in msg.get("payload", {}).get("headers", [])
    }
    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    date_str = headers.get("date", "")
    snippet = msg.get("snippet", "")
    body = _decode_body(msg.get("payload", {}))

    email_date = ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        email_date = dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    return {
        "id": msg["id"],
        "subject": subject,
        "sender": sender,
        "date": email_date,
        "snippet": snippet,
        "body": body[:3000],
    }


# --- Classification ---

def _classify_email(subject: str, snippet: str, body: str) -> Optional[str]:
    """Return 'applied', 'interview', 'rejected', or None."""
    # Combine all available text; prioritise subject for classification
    subject_text = subject.lower()
    full_text = f"{subject} {snippet} {body[:500]}".lower()

    # Interview takes highest priority (subject match preferred)
    if _INTERVIEW_RE.search(subject_text) or _INTERVIEW_RE.search(full_text):
        return "interview"

    # Rejected
    if _REJECTED_RE.search(subject_text) or _REJECTED_RE.search(full_text):
        return "rejected"

    # Applied (confirmation)
    if _APPLIED_RE.search(subject_text) or _APPLIED_RE.search(full_text):
        return "applied"

    return None


_PORTAL_NOISE_RE = re.compile(
    r"\s*(?:jobbnorge\.?(?:no|as)?|easycruit|teamtailor|webcruiter(?:mail)?|"
    r"recruitpartner|talentech|xcruiter|jobylon|finn\.?no)\s*",
    re.IGNORECASE,
)


def _clean_employer(name: str) -> str:
    """Strip portal brand noise from an extracted employer string."""
    name = _PORTAL_NOISE_RE.sub(" ", name).strip().strip(".,;:-")
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _extract_employer(subject: str, snippet: str, sender: str, body: str) -> str:
    """Best-effort extraction of employer name from email content.

    Tries multiple strategies in priority order:
    1. Portal-specific body patterns (Jobbnorge, EasyCruit, LinkedIn)
    2. Generic Norwegian body patterns ("søknad hos X", "stilling ved X")
    3. Sender display name (works for Teamtailor, direct employer emails)
    4. Sender domain as last resort
    """
    full_text = f"{body} {snippet}"

    # --- Portal-specific body patterns ---

    # Jobbnorge: "fra: Arkivsenter Sør" or "søknad fra: Employer Name"
    for pat in [
        r"(?:melding|søknad)\s+fra[:\s]+([^\n<]{3,60})",
        r"fra:\s*([A-ZÆØÅ][^\n<]{2,60})",
    ]:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            candidate = _clean_employer(m.group(1))
            if candidate and not re.search(r"jobbnorge|easycruit|teamtailor|webcruiter|linkedin|finn\.no", candidate, re.IGNORECASE):
                return candidate[:80]

    # EasyCruit: 'din søknad på stillingen "TITLE" hos EMPLOYER er mottatt'
    m = re.search(r'hos\s+([A-ZÆØÅ][^\n<"]{2,60}?)\s+er\s+mottatt', full_text, re.IGNORECASE)
    if m:
        return _clean_employer(m.group(1))[:80]

    # FINN.no application confirmation: "Din søknad ... er nå sendt til EMPLOYER."
    m = re.search(r'sendt\s+til\s+([A-ZÆØÅ][^\n<.]{2,60}?)(?:\.\s|\s*Har\s+du)', full_text, re.IGNORECASE)
    if m:
        return _clean_employer(m.group(1))[:80]

    # FINN.no employer response (cmt@finn.no): display name is the contact person,
    # but subject often contains "hos EMPLOYER" or "EMPLOYER"
    if "cmt@finn.no" in sender.lower():
        for pat in [
            r'(?:hos|i)\s+([A-ZÆØÅ][^\n<,.]{2,60}?)(?:\s*$|\s*\.)',
            r'(?:søknad|stilling)\s+.{0,30}?\s+(?:hos|i|ved)\s+([A-ZÆØÅ][^\n<,.]{2,60})',
        ]:
            m = re.search(pat, subject, re.IGNORECASE)
            if m:
                return _clean_employer(m.group(1))[:80]

    # LinkedIn: "Your application was sent to EMPLOYER"
    # or "EMPLOYER has reviewed your application"
    for pat in [
        r"application\s+was\s+sent\s+to\s+([^\n<.]{3,60})",
        r"([^\n<.]{3,60})\s+has\s+(?:reviewed|received)\s+your\s+application",
        r"([^\n<.]{3,60})\s+(?:has\s+)?decided\s+not\s+to\s+move",
    ]:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            candidate = _clean_employer(m.group(1))
            if candidate:
                return candidate[:80]

    # Generic Norwegian: "søknad på stilling(en) [TITLE] (ved|hos|i) EMPLOYER"
    # or "stillingen [TITLE] i EMPLOYER"
    for pat in [
        r"(?:stillingen?|stilling)\s+.{0,60}?\s+(?:ved|hos|i)\s+([A-ZÆØÅ][^\n<,.]{3,60})",
        r"(?:ved|hos)\s+([A-ZÆØÅ][^\n<,.]{3,60}?)(?:\s+er\s+|\s+har\s+|[,\.]|$)",
    ]:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            candidate = _clean_employer(m.group(1))
            if candidate and not re.search(r"jobbnorge|easycruit|teamtailor|webcruiter|linkedin|finn\.no", candidate, re.IGNORECASE):
                return candidate[:80]

    # --- Sender display name ---
    # Works for: Teamtailor ("Statens vegvesen <noreply@teamtailor...>"),
    # direct employer HR systems ("HR Avdeling <hr@employer.no>"),
    # and most well-configured ATS senders.
    m = re.match(r'^"?([^"<]{3,60})"?\s*<', sender)
    if m:
        name = m.group(1).strip()
        skip_names = {
            "noreply", "no-reply", "do not reply", "donotreply",
            "jobbnorge", "easycruit", "teamtailor", "webcruiter",
            "linkedin", "finn.no", "stepstone", "jobindex",
            "hr", "rekruttering", "recruitment", "jobs", "careers",
            "notifications", "varsler",
        }
        if name.lower() not in skip_names and len(name) > 3:
            return _clean_employer(name)[:80]

    # --- Sender domain as last resort ---
    # e.g. "noreply@vegvesen.no" → "vegvesen"
    m = re.search(r"@([\w-]+)\.(no|com|org|gov|net)\b", sender)
    if m:
        domain = m.group(1)
        skip_domains = {
            "jobbnorge", "easycruit", "teamtailor", "webcruiter",
            "linkedin", "finn", "stepstone", "greenhouse", "lever",
            "workday", "visma", "reachmee", "gmail", "outlook",
        }
        if domain.lower() not in skip_domains:
            # Capitalize and return domain as rough employer hint
            return domain.capitalize()[:40]

    return ""


def _extract_title(subject: str, body: str) -> str:
    """Try to extract the job title from email content."""
    full = f"{subject} {body[:1000]}"
    for pat in [
        # Norwegian: "søknad på stilling(en): TITLE" or "søknad på TITLE"
        r'søknad\s+på\s+stillingen?\s*[:\-–]?\s*"?([^"\n<]{5,80})"?',
        r'stillingen?\s+"([^"]{5,80})"',
        # EasyCruit: 'din søknad på stillingen "TITLE"'
        r'stillingen\s+"([^"]{5,80})"',
        # LinkedIn: "Your application to TITLE at EMPLOYER"
        r"application\s+to\s+(.{5,80}?)\s+at\s+",
        # Generic: "position of TITLE" or "role of TITLE"
        r"(?:position|role|stilling)\s+(?:of|as|som)\s+([^\n<,.]{5,60})",
    ]:
        m = re.search(pat, full, re.IGNORECASE)
        if m:
            return m.group(1).strip().strip('"')[:80]
    return ""


# --- Ledger matching ---

def _normalize(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    s = (s or "").lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_STOP_WORDS = {
    "as", "sa", "ba", "asa", "ab", "og", "i", "av", "for", "til",
    "the", "and", "of", "in", "for", "ltd", "inc", "gmbh",
}


def _employer_score(a: str, b: str) -> int:
    """Return a match score 0-3 between two employer strings."""
    na = _normalize(a)
    nb = _normalize(b)
    if not na or not nb:
        return 0
    if na == nb:
        return 3
    if na in nb or nb in na:
        return 2
    # Word overlap (ignore stop words)
    wa = set(na.split()) - _STOP_WORDS
    wb = set(nb.split()) - _STOP_WORDS
    if wa and wb:
        overlap = wa & wb
        if len(overlap) >= 2:
            return 1
        if len(overlap) == 1 and len(overlap.pop()) >= 6:
            # Single long word match (e.g. "Digitaliseringsdirektoratet")
            return 1
    return 0


def _title_score(email_title: str, job_title: str) -> int:
    """Return a match score 0-2 between email-extracted title and ledger job title."""
    na = _normalize(email_title)
    nb = _normalize(job_title)
    if not na or not nb:
        return 0
    if na == nb:
        return 2
    if na in nb or nb in na:
        return 1
    # Word overlap (3+ significant words)
    wa = set(na.split()) - _STOP_WORDS
    wb = set(nb.split()) - _STOP_WORDS
    if len(wa & wb) >= 2:
        return 1
    return 0


def _match_jobs(
    employer: str,
    title: str,
    ledger: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Find ledger jobs by employer name and/or job title.

    Scoring:
      employer=3 + title=2  → perfect (6)
      employer=3            → strong employer match (3)
      employer=1 + title=1  → weak both (2) — only accepted if title is long enough
      title only            → never accepted alone (too noisy)
    """
    matches = []
    for job in ledger:
        escore = _employer_score(employer, job.get("employer") or "")
        tscore = _title_score(title, job.get("title") or "") if title else 0
        total = escore * 2 + tscore  # weight employer more heavily

        # Require at least a meaningful employer signal
        if escore >= 1:
            matches.append((total, job))
        # Title-only match: only if title is very specific (long) and score is high
        elif tscore >= 2 and len(_normalize(title).split()) >= 4:
            matches.append((tscore, job))

    matches.sort(key=lambda x: (x[0], x[1].get("fit_score") or 0), reverse=True)
    return [j for _, j in matches]


# --- State helpers ---

def _load_state(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            apps = raw.get("applications", {})
            for entry in apps.values():
                if not entry.get("status"):
                    entry["status"] = _entry_effective_status(entry)
            return raw
        except Exception as e:
            print(f"Warning: could not read state file {path}: {e}", file=sys.stderr)
    return {"version": 1, "updated_at": "", "applications": {}}


def _save_state(path: Path, state: Dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _entry_effective_status(entry: Dict[str, Any]) -> str:
    status = (entry.get("status") or "").strip()
    if status:
        return status
    outcome = (entry.get("outcome") or "").strip()
    if outcome:
        return outcome
    stages = entry.get("stages", [])
    if not isinstance(stages, list):
        return ""
    for stage in ("second_interview", "interview", "applied", "called", "shortlisted"):
        if stage in stages:
            return stage
    return ""


def _cache_state_after_write(
    apps: Dict[str, Dict[str, Any]],
    job_id: str,
    status: str,
    parsed: Dict[str, Any],
    existing: Dict[str, Any],
) -> None:
    entry = dict(existing)
    entry["status"] = status
    entry["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    entry["source"] = "gmail"
    entry["email_subject"] = parsed["subject"][:120]
    entry["email_date"] = parsed["date"]
    apps[job_id] = entry


def _persist_gmail_status(
    *,
    apps: Dict[str, Dict[str, Any]],
    job_id: str,
    status: str,
    parsed: Dict[str, Any],
    existing: Dict[str, Any],
    state_path: Path,
    db_path: Path,
    candidate_id: str,
    dry_run: bool,
) -> None:
    if not dry_run:
        add_stage(
            job_id=job_id,
            token=status,
            state_path=state_path,
            notes=existing.get("notes", ""),
            source="gmail",
            email_subject=parsed["subject"][:120],
            email_date=parsed["date"],
            db_path=db_path,
            candidate_id=candidate_id,
            quiet=True,
        )
    _cache_state_after_write(apps, job_id, status, parsed, existing)


# --- Main scan ---

def scan(
    days: int = 90,
    state_path: Path = DEFAULT_STATE_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    token_path: Path = DEFAULT_TOKEN_PATH,
    creds_path: Path = DEFAULT_CREDS_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Run the Gmail scan. Returns count of new/updated state entries."""
    if not _check_deps():
        return 0

    creds = _get_credentials(token_path, creds_path)
    if not creds:
        return 0

    service = build("gmail", "v1", credentials=creds)

    after_dt = datetime.now(timezone.utc) - timedelta(days=days)
    after_str = after_dt.strftime("%Y/%m/%d")

    print(f"Scanning Gmail for job emails (last {days} days, since {after_str[:10]})...")

    # Collect unique message IDs across all queries
    found_ids: set = set()
    msg_ids: List[str] = []
    for q in _build_queries(after_str):
        try:
            result = service.users().messages().list(
                userId="me", q=q, maxResults=200
            ).execute()
            for m in result.get("messages", []):
                mid = m["id"]
                if mid not in found_ids:
                    found_ids.add(mid)
                    msg_ids.append(mid)
        except Exception as e:
            if verbose:
                print(f"  Query skipped ({q[:60]}): {e}", file=sys.stderr)

    print(f"Found {len(msg_ids)} candidate emails across all queries.")

    # Load ledger for matching
    ledger = []
    if ledger_path.exists():
        try:
            conn = sqlite3.connect(str(ledger_path))
            conn.row_factory = sqlite3.Row
            ledger = [dict(r) for r in conn.execute(
                "SELECT job_id, title, employer, work_city, final_decision FROM ledger"
            )]
            conn.close()
            print(f"Loaded {len(ledger)} jobs from ledger for employer matching.")
        except Exception as e:
            print(f"Warning: could not read ledger: {e}", file=sys.stderr)
    else:
        print(f"Warning: ledger not found at {ledger_path}. Employer matching disabled.")

    state = _load_state(state_path)
    apps = state.setdefault("applications", {})

    written = 0
    skipped_manual = 0
    skipped_no_upgrade = 0
    unclassified = 0
    unmatched = 0

    for i, msg_id in enumerate(msg_ids):
        if verbose:
            print(f"  [{i+1}/{len(msg_ids)}] Fetching {msg_id}...")

        try:
            raw = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
        except Exception as e:
            if verbose:
                print(f"    Error fetching {msg_id}: {e}", file=sys.stderr)
            continue

        parsed = _parse_message(raw)
        status = _classify_email(parsed["subject"], parsed["snippet"], parsed["body"])

        if not status:
            # Special case: Jobbnorge "Du har mottatt en ny melding" —
            # the actual message is behind their login wall so we can't
            # classify it, but we can tell the user to check manually.
            is_jobbnorge_message = (
                "jobbnorge" in parsed["sender"].lower()
                and "melding" in parsed["subject"].lower()
                and "bekreftelse" not in parsed["subject"].lower()
            )
            if is_jobbnorge_message:
                emp = _extract_employer(
                    parsed["subject"], parsed["snippet"], parsed["sender"], parsed["body"]
                )
                print(
                    f"  [!] MANUAL CHECK  {emp or '(unknown employer)':<36}"
                    f"  Jobbnorge message - log in to read it"
                )
                if verbose:
                    print(f"    date={parsed['date']}  subject='{parsed['subject'][:60]}'")
            else:
                unclassified += 1
                if verbose:
                    print(f"    Unclassified: {parsed['subject'][:70]}")
            continue

        employer = _extract_employer(
            parsed["subject"], parsed["snippet"], parsed["sender"], parsed["body"]
        )
        title = _extract_title(parsed["subject"], parsed["body"])

        matched = _match_jobs(employer, title, ledger)

        if not matched:
            unmatched += 1
            if verbose:
                print(
                    f"    No ledger match: [{status}] '{parsed['subject'][:50]}'"
                    f"  employer='{employer}'  title='{title}'"
                )
            continue

        for job in matched:
            job_id = job["job_id"]
            existing = apps.get(job_id, {})

            # Preserve all manual entries unconditionally
            if existing.get("source") == "manual":
                skipped_manual += 1
                if verbose:
                    print(f"    Preserve manual: {job_id}")
                continue

            # Only upgrade status (applied→interview→rejected), never downgrade
            existing_order = _STATUS_ORDER.get(existing.get("status", ""), 0)
            new_order = _STATUS_ORDER.get(status, 0)
            if existing.get("status") and new_order <= existing_order:
                skipped_no_upgrade += 1
                if verbose:
                    print(
                        f"    No upgrade: {job_id}  {existing.get('status')} → {status}"
                    )
                continue

            prefix = "[DRY RUN] " if dry_run else ""
            mark = "~" if dry_run else "[OK]"
            print(
                f"  {prefix}{mark} {status.upper():<12}"
                f"  {(job.get('employer') or '')[:32]:<34}"
                f"  {(job.get('title') or '')[:42]}"
            )
            if verbose:
                print(f"    job_id={job_id}  subject='{parsed['subject'][:60]}'  date={parsed['date']}")

            if not dry_run:
                written += 1
            _persist_gmail_status(
                apps=apps,
                job_id=job_id,
                status=status,
                parsed=parsed,
                existing=existing,
                state_path=state_path,
                db_path=db_path,
                candidate_id=candidate_id,
                dry_run=dry_run,
            )

    if not dry_run and written:
        print(f"\n[OK] Saved {written} new/updated entries to {state_path} and {db_path}")

    print(
        f"\nSummary: classified={len(msg_ids)-unclassified}  unclassified={unclassified}  "
        f"unmatched={unmatched}  manual_preserved={skipped_manual}  "
        f"no_upgrade={skipped_no_upgrade}  written={written}"
    )
    return written


# --- Suggestion scan ---

def scan_suggestions(
    days: int = 90,
    suggested_path: Path = DEFAULT_SUGGESTED_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    token_path: Path = DEFAULT_TOKEN_PATH,
    creds_path: Path = DEFAULT_CREDS_PATH,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Scan Gmail for FINN/LinkedIn job suggestion emails.

    Extracts job URLs from platform recommendation emails, cross-references with
    the ledger, and queues new/unprocessed suggestions to reports/suggested_jobs.jsonl.

    Calibration value: platform-suggested jobs are ground-truth positives from
    the platform's own recommendation algorithm. Jobs in the queue carry
    suggested_by_platform=true when fed to the pipeline — the triage stage uses
    this to prevent the semantic filter from killing them before the LLM sees them.

    Returns count of new jobs written to the queue.
    """
    if not _check_deps():
        return 0

    creds = _get_credentials(token_path, creds_path)
    if not creds:
        return 0

    service = build("gmail", "v1", credentials=creds)

    after_dt = datetime.now(timezone.utc) - timedelta(days=days)
    after_str = after_dt.strftime("%Y/%m/%d")

    print(f"Scanning Gmail for job suggestion emails (last {days} days, since {after_str[:10]})...")

    # Collect unique message IDs
    found_ids: set = set()
    msg_ids: List[str] = []
    for q in _build_suggestion_queries(after_str):
        try:
            result = service.users().messages().list(userId="me", q=q, maxResults=100).execute()
            for m in result.get("messages", []):
                mid = m["id"]
                if mid not in found_ids:
                    found_ids.add(mid)
                    msg_ids.append(mid)
        except Exception as e:
            if verbose:
                print(f"  Query skipped ({q[:60]}): {e}", file=sys.stderr)

    print(f"Found {len(msg_ids)} candidate suggestion emails.")

    # Build ledger lookup: finnkode/linkedin_id → job_id (for cross-referencing)
    ledger_finnkodes: Dict[str, str] = {}
    ledger_linkedin_ids: Dict[str, str] = {}
    if ledger_path.exists():
        try:
            conn = sqlite3.connect(str(ledger_path))
            for (job_id,) in conn.execute("SELECT job_id FROM ledger").fetchall():
                if job_id.startswith("finn_"):
                    ledger_finnkodes[job_id[5:]] = job_id
                elif job_id.startswith("linkedin_"):
                    ledger_linkedin_ids[job_id[9:]] = job_id
            conn.close()
        except Exception as e:
            if verbose:
                print(f"Warning: ledger read failed: {e}", file=sys.stderr)

    # Load existing queue to avoid duplicates across runs.
    # Prefer the primary DB, but still include the legacy JSONL sidecar as a bridge.
    existing_queue_keys = _load_existing_suggestion_keys(suggested_path, db_path, candidate_id)

    finn_total = 0
    linkedin_total = 0
    already_in_ledger = 0
    new_queued: List[Dict[str, Any]] = []
    emails_with_jobs = 0

    for i, msg_id in enumerate(msg_ids):
        if verbose:
            print(f"  [{i+1}/{len(msg_ids)}] Fetching {msg_id}...")

        try:
            raw = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
        except Exception as e:
            if verbose:
                print(f"    Error: {e}", file=sys.stderr)
            continue

        headers = {
            h["name"].lower(): h["value"]
            for h in raw.get("payload", {}).get("headers", [])
        }
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        date_str = headers.get("date", "")

        email_date = ""
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            email_date = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

        # Classify email by sender (broad check) — subject patterns are hints only.
        # We use URL extraction as the real gate: if we find job URLs in the body,
        # it's a suggestion email regardless of exact subject wording.
        from_finn = _FINN_ALERT_SENDER_RE.search(sender)
        from_linkedin = _LINKEDIN_ALERT_SENDER_RE.search(sender)

        if not (from_finn or from_linkedin):
            if verbose:
                print(f"    Skip (not finn/linkedin sender): '{sender[:40]}'")
            continue

        # Soft subject hints — used only for platform_label, not as a hard gate
        looks_like_finn_suggestion = bool(from_finn and _FINN_ALERT_SUBJECT_RE.search(subject))
        looks_like_linkedin_suggestion = bool(from_linkedin and _LINKEDIN_ALERT_SUBJECT_RE.search(subject))

        # Skip known status emails to avoid double-counting
        # (status emails have different subjects; skip if they match status patterns)
        is_status_email = bool(
            _APPLIED_RE.search(subject)
            or _INTERVIEW_RE.search(subject)
            or _REJECTED_RE.search(subject)
        )
        if is_status_email:
            if verbose:
                print(f"    Skip (status email): '{subject[:60]}'")
            continue

        urls = _extract_job_urls_from_payload(raw.get("payload", {}))
        jobs = _extract_suggestion_jobs(urls)

        if not jobs:
            if verbose:
                print(f"    No job URLs: '{subject[:70]}' from {sender[:40]}")
            continue

        emails_with_jobs += 1
        platform_label = "FINN" if from_finn else "LinkedIn"

        for job in jobs:
            platform = job["platform"]
            if platform == "finn":
                finn_total += 1
                ledger_jid = ledger_finnkodes.get(job.get("finnkode", ""))
            else:
                linkedin_total += 1
                ledger_jid = ledger_linkedin_ids.get(job.get("linkedin_job_id", ""))

            external_id = _suggestion_external_id(job)
            dedup_key = _suggestion_key(platform, external_id)

            if ledger_jid:
                already_in_ledger += 1
                if verbose:
                    print(f"    [{platform_label}] In ledger: {ledger_jid}")
                continue

            if not external_id:
                continue

            if dedup_key in existing_queue_keys:
                if verbose:
                    print(f"    [{platform_label}] Already queued: {job.get('job_url', '')[:60]}")
                continue

            # New, not-yet-processed suggestion — add to queue
            existing_queue_keys.add(dedup_key)
            entry = {**job, "suggested_at": email_date, "email_subject": subject[:120]}
            new_queued.append(entry)
            print(
                f"  [+] {platform_label:<9} {job.get('job_url', '')[:70]}"
                + (f"  (from: {email_date})" if email_date else "")
            )

    # Write to queue
    if new_queued and not dry_run:
        try:
            conn = connect_primary_db(db_path)
            try:
                ensure_candidate(conn, candidate_id=candidate_id)
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                for entry in new_queued:
                    platform = str(entry.get("platform") or "").strip()
                    external_id = _suggestion_external_id(entry)
                    if not platform or not external_id:
                        continue
                    upsert_suggestion_lead(
                        conn,
                        {
                            "suggestion_id": _suggestion_id(candidate_id, platform, external_id),
                            "candidate_id": candidate_id,
                            "platform": platform,
                            "external_id": external_id,
                            "job_url": str(entry.get("job_url") or "").strip(),
                            "job_id_hint": str(entry.get("job_id_hint") or "").strip(),
                            "suggested_at": str(entry.get("suggested_at") or "").strip(),
                            "email_subject": str(entry.get("email_subject") or "").strip(),
                            "source": "gmail_suggestions",
                            "status": "queued",
                            "fetched_at": "",
                            "last_error": "",
                            "payload_json": entry,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            if verbose:
                print(f"Warning: primary DB suggestion write failed: {e}", file=sys.stderr)

        suggested_path.parent.mkdir(parents=True, exist_ok=True)
        with open(suggested_path, "a", encoding="utf-8") as f:
            for entry in new_queued:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    prefix = "[DRY RUN] " if dry_run else ""
    print(
        f"\n{prefix}Suggestion scan summary:\n"
        f"  Emails with job URLs:   {emails_with_jobs}\n"
        f"  FINN jobs found:        {finn_total}\n"
        f"  LinkedIn jobs found:    {linkedin_total}\n"
        f"  Already in ledger:      {already_in_ledger}\n"
        f"  New / queued:           {len(new_queued)}\n"
    )
    if new_queued and not dry_run:
        print(
            f"  Stored in DB: {db_path}\n"
            f"  Fallback queue: {suggested_path}\n"
            f"  Next step:  python -m jobpipe.cli.pull_suggested\n"
            f"              (runs 09:00-19:00 Oslo time, max 20 jobs/run)"
        )
    elif new_queued and dry_run:
        print(f"  Would write to: {suggested_path} (dry run)")

    return len(new_queued)


# --- OAuth setup ---

def setup_oauth(creds_path: Path, token_path: Path) -> None:
    """Interactive one-time OAuth2 consent flow."""
    if not _check_deps():
        return

    if not creds_path.exists():
        print(f"\nGmail credentials file not found: {creds_path}")
        print("\nTo create it:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create or select a project")
        print("  3. Enable the Gmail API")
        print("  4. Create OAuth2 credentials (Application type: Desktop)")
        print("  5. Download the JSON and save it to:")
        print(f"     {creds_path.resolve()}")
        print("\nThen re-run:  python -m jobpipe.cli.scan_gmail --setup")
        return

    print(f"Starting OAuth2 flow using credentials from: {creds_path}")
    print("A browser window will open. Approve Gmail read-only access.")
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"\n[OK] Authorization complete. Token saved to: {token_path}")
    print("You can now run:  python -m jobpipe.cli.scan_gmail --dry-run")


# --- CLI ---

def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(
        description="Scan Gmail for job application emails and update application_state.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--days", type=int, default=90, help="Days back to scan (default: 90)")
    ap.add_argument("--state", default=str(DEFAULT_STATE_PATH), help="Path to application_state.json")
    ap.add_argument("--ledger", default=str(DEFAULT_LEDGER_PATH), help="Path to ledger.sqlite")
    ap.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to primary jobpipe.sqlite")
    ap.add_argument("--candidate-id", default=DEFAULT_CANDIDATE_ID, help=f"Candidate ID for primary DB writes (default: {DEFAULT_CANDIDATE_ID})")
    ap.add_argument("--token", default=str(DEFAULT_TOKEN_PATH), help="OAuth token path (gmail_token.json)")
    ap.add_argument("--creds", default=str(DEFAULT_CREDS_PATH), help="OAuth credentials path (gmail_credentials.json)")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing")
    ap.add_argument("--verbose", "-v", action="store_true", help="Show all processing details")
    ap.add_argument("--setup", action="store_true", help="Run one-time OAuth2 setup")
    ap.add_argument(
        "--scan-suggestions",
        action="store_true",
        help=(
            "Scan for FINN/LinkedIn job suggestion emails instead of status emails. "
            "Stores new suggestions in the primary DB and mirrors them to suggested_jobs.jsonl."
        ),
    )
    ap.add_argument(
        "--suggested",
        default=str(DEFAULT_SUGGESTED_PATH),
        help="Path for suggested_jobs.jsonl output (used with --scan-suggestions)",
    )

    args = ap.parse_args(argv)

    if args.setup:
        setup_oauth(Path(args.creds), Path(args.token))
        return

    if args.scan_suggestions:
        scan_suggestions(
            days=args.days,
            suggested_path=Path(args.suggested),
            ledger_path=Path(args.ledger),
            db_path=Path(args.db),
            candidate_id=args.candidate_id,
            token_path=Path(args.token),
            creds_path=Path(args.creds),
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        return

    scan(
        days=args.days,
        state_path=Path(args.state),
        ledger_path=Path(args.ledger),
        token_path=Path(args.token),
        creds_path=Path(args.creds),
        db_path=Path(args.db),
        candidate_id=args.candidate_id,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()

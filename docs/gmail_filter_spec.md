# Gmail Filter & Label Specification — JobPilot

**Created:** 2026-04-12
**Purpose:** Replace messy SOKNADSPILOT/* labels with a clean, logical structure that routes job emails for both human use and pipeline automation.

---

## New Label Structure

```
Jobb/
  Jobbsøk/                             ← existing (Label_11), keep as-is
    Status jobbsøknad                   ← RENAME from "Svar på jobbsøknad"
    Tiltak                              ← existing, keep as-is
  Varsler/                              ← NEW parent (all job alerts land here)
    LinkedIn                            ← NEW — LinkedIn job alerts + recommendations
    Finn                                ← NEW — Finn.no saved searches, company follows, weekly digest
    Andre                               ← NEW — Indeed, WebCruiter, career sites, other portals
```

### Labels to DELETE (after creating new filters)

| Old label | Replacement |
|-----------|-------------|
| `SOKNADSPILOT` | `Jobb/Varsler/LinkedIn` |
| `SOKNADSPILOT/FINN_AGENT` | `Jobb/Varsler/Finn` |
| `SOKNADSPILOT/FINN_INSPIRASJON` | `Jobb/Varsler/Finn` |
| `SOKNADSPILOT/LINKEDIN_JOBALERT` | `Jobb/Varsler/LinkedIn` |

### Labels to RENAME

| Old name | New name |
|----------|----------|
| `Jobb/Jobbsøk/Svar på jobbsøknad` | `Jobb/Jobbsøk/Status jobbsøknad` |

---

## Gmail Filter Specifications

Create these filters in Gmail → Settings → Filters and Blocked Addresses → Create a new filter.

### Filter 1: LinkedIn Job Alerts (multi-job digests)

**Purpose:** Route LinkedIn job alert emails to Varsler/LinkedIn, skip inbox.

| Field | Value |
|-------|-------|
| From | `jobalerts-noreply@linkedin.com` |
| **Actions** | |
| Skip Inbox | Yes |
| Apply label | `Jobb/Varsler/LinkedIn` |
| Never send to Spam | Yes |
| Mark as read | No (leave unread for script pickup) |

### Filter 2: LinkedIn Job Recommendations (individual listings)

**Purpose:** Route LinkedIn single-job recommendation emails.

| Field | Value |
|-------|-------|
| From | `jobs-listings@linkedin.com` |
| **Actions** | |
| Skip Inbox | Yes |
| Apply label | `Jobb/Varsler/LinkedIn` |
| Never send to Spam | Yes |

### Filter 3: LinkedIn Generic Job Prompts

**Purpose:** Route "er du på jakt etter en ny jobb?" and similar.

| Field | Value |
|-------|-------|
| From | `jobs-noreply@linkedin.com` |
| Has the words | `jobb OR job OR stilling OR career` |
| **Actions** | |
| Skip Inbox | Yes |
| Apply label | `Jobb/Varsler/LinkedIn` |
| Never send to Spam | Yes |

### Filter 4: Finn.no Job Alerts (saved search + company follow)

**Purpose:** Route Finn.no "Nye annonser" and "Nye stillinger i firma du følger" emails.

| Field | Value |
|-------|-------|
| From | `agent@finn.no` |
| **Actions** | |
| Skip Inbox | Yes |
| Apply label | `Jobb/Varsler/Finn` |
| Never send to Spam | Yes |

### Filter 5: Finn.no Weekly Profile Digest

**Purpose:** Route "Ukens stillinger basert på din Jobbprofil" emails.

| Field | Value |
|-------|-------|
| From | `FINN@inspirasjon.finn.no` |
| Has the words | `stillinger OR jobbprofil` |
| **Actions** | |
| Skip Inbox | Yes |
| Apply label | `Jobb/Varsler/Finn` |
| Never send to Spam | Yes |

### Filter 6: Finn.no Application Confirmations

**Purpose:** Route "Takk for søknaden din" application confirmations. These are status updates, not alerts.

| Field | Value |
|-------|-------|
| From | `noreply@finn.no` |
| Subject | `Takk for søknaden` |
| **Actions** | |
| Skip Inbox | No (Lars should see these) |
| Apply label | `Jobb/Jobbsøk/Status jobbsøknad` |
| Never send to Spam | Yes |

### Filter 7: Finn.no Employer Responses

**Purpose:** Route application responses from employers via FINN's messaging (cmt@finn.no).

| Field | Value |
|-------|-------|
| From | `cmt@finn.no` |
| Has the words | `søknad OR stilling OR kandidat OR application` |
| **Actions** | |
| Skip Inbox | No (Lars should see these) |
| Apply label | `Jobb/Jobbsøk/Status jobbsøknad` |
| Never send to Spam | Yes |

### Filter 8: Indeed Job Matches

**Purpose:** Route Indeed job match alert emails.

| Field | Value |
|-------|-------|
| From | `donotreply@match.indeed.com` |
| **Actions** | |
| Skip Inbox | Yes |
| Apply label | `Jobb/Varsler/Andre` |
| Never send to Spam | Yes |

### Filter 9: WebCruiter Notifications

**Purpose:** Route WebCruiter job-related emails.

| Field | Value |
|-------|-------|
| From | `noreply@webcruitermail.no` |
| **Actions** | |
| Skip Inbox | No (could be application status updates) |
| Apply label | `Jobb/Jobbsøk/Status jobbsøknad` |
| Never send to Spam | Yes |

### Filter 10: Career Site Alerts (jobs2web)

**Purpose:** Route career site notifications (Norwegian Air, Orkla, etc.)

| Field | Value |
|-------|-------|
| From | `jobs2web.com` |
| **Actions** | |
| Skip Inbox | Yes |
| Apply label | `Jobb/Varsler/Andre` |
| Never send to Spam | Yes |

### Filter 11: Jobbnorge Notifications

**Purpose:** Route Jobbnorge messages (could be status updates).

| Field | Value |
|-------|-------|
| From | `jobbnorge.no` |
| **Actions** | |
| Skip Inbox | No (could be application status) |
| Apply label | `Jobb/Jobbsøk/Status jobbsøknad` |
| Never send to Spam | Yes |

### Filter 12: Other ATS Platforms

**Purpose:** Catch Teamtailor, EasyCruit, Talentech, Jobylon, Xcruiter, RecruitPartner emails.

| Field | Value |
|-------|-------|
| From | `teamtailor.com OR easycruit.com OR talentech.email OR jobylon.com OR xcruiter.no OR recruitpartner.no` |
| **Actions** | |
| Skip Inbox | No |
| Apply label | `Jobb/Jobbsøk/Status jobbsøknad` |
| Never send to Spam | Yes |

---

## Email Classification Summary

### Flow A — Job Leads (invisible data pipe → pipeline)

These skip the inbox entirely. A scheduled script will pick them up and write to `jobs_leads.jsonl`.

| Source | Sender | Subject pattern | Label |
|--------|--------|----------------|-------|
| LinkedIn alerts | `jobalerts-noreply@linkedin.com` | «Query»: Company – Title og flere | `Jobb/Varsler/LinkedIn` |
| LinkedIn recs | `jobs-listings@linkedin.com` | Title-stilling hos Company | `Jobb/Varsler/LinkedIn` |
| LinkedIn prompts | `jobs-noreply@linkedin.com` | Er du på jakt etter en ny jobb? | `Jobb/Varsler/LinkedIn` |
| Finn saved search | `agent@finn.no` | Nye annonser: Jobb ledig | `Jobb/Varsler/Finn` |
| Finn company follow | `agent@finn.no` | Nye stillinger i firma du følger: X | `Jobb/Varsler/Finn` |
| Finn weekly digest | `FINN@inspirasjon.finn.no` | Ukens stillinger basert på din Jobbprofil | `Jobb/Varsler/Finn` |
| Indeed matches | `donotreply@match.indeed.com` | Job title - Company | `Jobb/Varsler/Andre` |
| Career sites | `*@jobs2web.com` | New jobs from careers.X.com | `Jobb/Varsler/Andre` |

### Flow B — Application Status (visible, tracked by scan_gmail.py)

These stay in the inbox. They update `application_state.json` via scan_gmail.py.

| Source | Sender | Subject pattern | Classification |
|--------|--------|----------------|----------------|
| Finn confirmations | `noreply@finn.no` | Takk for søknaden din | applied |
| Finn employer responses | `cmt@finn.no` | Vedrørende din søknad... | applied/interview/rejected |
| LinkedIn app confirm | `jobs-noreply@linkedin.com` | Søknaden din ble sendt til X | applied |
| Jobbnorge | `*@jobbnorge.no` | Various | applied/interview/rejected |
| WebCruiter | `noreply@webcruitermail.no` | Various | applied/interview/rejected |
| Teamtailor | `*@teamtailor.com` | Various | applied/interview/rejected |
| EasyCruit | `*@easycruit.com` | Various | applied/interview/rejected |
| Talentech | `*@talentech.email` | Various | applied/interview/rejected |
| Jobylon | `*@jobylon.com` | Various | applied/interview/rejected |
| Xcruiter | `*@xcruiter.no` | Various | applied/interview/rejected |
| RecruitPartner | `*@recruitpartner.no` | Various | applied/interview/rejected |

---

## Finn.no Email Formats (for lead extraction)

### Saved search alert (`agent@finn.no`)
```
Subject: Nye annonser: Jobb ledig
Body: "Hei! Du har X nye treff i søket: Jobb ledig
  Title Employer City
  Title Employer City
  ‌ Se annonsene"
```

### Company follow alert (`agent@finn.no`)
```
Subject: Nye stillinger i firma du følger: Company
Body: "Hei Lars Holkestad! Nå har vi fått inn nye stillinger i firma du følger på FINN.no
  Title Company City
  Se annonsene på FINN.no"
```

### Weekly digest (`FINN@inspirasjon.finn.no`)
```
Subject: Ukens stillinger basert på din Jobbprofil
Body: "Title/Company1,Company2,Company3
  Stillinger basert på din Jobbprofil
  Company Title Description City"
```

### Application confirmation (`noreply@finn.no`)
```
Subject: Takk for søknaden din
Body: "Hei Lars Holkestad Værland
  Din søknad på stillingen Title er nå sendt til Company.
  Har du spørsmål angående stillingen kan du kontakte: Contact Name email phone"
```

---

## LinkedIn Email Formats (for lead extraction)

### Job alert digest (`jobalerts-noreply@linkedin.com`)
```
Subject: «Query»: Company – Title og flere
  OR: Company ansetter: Title
  OR: Title hos Company og mer
Body: [HTML with structured job cards, each containing:]
  - Company name
  - Job title
  - Location
  - LinkedIn job URL (contains job ID: linkedin.com/jobs/view/XXXXXXXXXX)
```

### Individual recommendation (`jobs-listings@linkedin.com`)
```
Subject: Title-stilling hos Company: Vær en av de første X søkerne
  OR: Title-stilling hos Company er tilgjengelig
  OR: Company skal ansette en Title
  OR: Åpen søknad-stilling hos Company: Rekrutterer aktivt
Body: [HTML with single job details + LinkedIn job URL]
```

---

## Implementation Order

1. Create new labels in Gmail (Jobb/Varsler/, Jobb/Varsler/LinkedIn, Jobb/Varsler/Finn, Jobb/Varsler/Andre)
2. Rename `Jobb/Jobbsøk/Svar på jobbsøknad` → `Jobb/Jobbsøk/Status jobbsøknad`
3. Create all 12 filters above (in Gmail Settings)
4. Optionally: apply filters to existing messages (Gmail offers this checkbox)
5. Delete old SOKNADSPILOT/* labels
6. Update scan_gmail.py label references

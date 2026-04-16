# Profile Pack

## Purpose

`profile_pack.md` describes what the candidate is actually targeting and what the pipeline should treat as relevant.

It remains a supported working file, even as the canonical candidate-state model moves into the primary DB.

## Starting point

```powershell
copy profile_pack.example.md profile_pack.md
```

Then tailor it to the real search.

## What it should contain

A good profile pack usually covers:

- target role families
- target seniority and scope
- geography or location constraints
- hard-no role patterns
- strong positive signals
- domain context
- evidence from past work that matters for matching

## What makes it useful

The profile pack works best when it is:

- specific
- current
- candid about constraints
- focused on the signals that actually matter

## What not to do

- do not write a full autobiography
- do not turn it into a generic CV dump
- do not hide important hard constraints
- do not let it drift far from the real search target

## Relationship to the primary DB

The current runtime can import and persist candidate profile state in `jobpipe.sqlite`.

That means `profile_pack.md` is best treated as:

- an editable source input
- a compatibility format
- a candidate-facing representation of the profile

rather than the only long-term source of truth.

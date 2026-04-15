# Configuration

Jobpipe relies on a small number of configuration inputs to run safely and predictably.

## Environment file

Start from:

```powershell
copy .env.example .env
```

Typical values include:
- OpenAI API key
- source URLs or feed settings
- optional Google-related credentials or references

Do not commit secrets.

## Candidate profile

Start from:

```powershell
copy profile_pack.example.md profile_pack.md
```

This file defines the job search profile the pipeline evaluates against.

Typical inputs include:
- target role titles
- preferred geography
- hard-no role types
- role and domain signals
- career evidence and positioning

## Pipeline configuration

Key pipeline behavior lives in config files such as:

- `configs/pipeline.v1.yaml`

This is where model choices, thresholds, regex rules, and similar settings are controlled.

## Gmail integration

Gmail support is optional.

If enabled, it can help detect:
- confirmations
- interviews
- rejections

See:
- `docs/cli.md`
- `docs/gmail_filter_spec.md`

## Practical advice

Keep configuration simple:
- make one change at a time
- test after threshold or rule changes
- avoid changing multiple control points at once

# Apps Script Operations

## Purpose

This document tracks operational improvements for the Google Apps Script side of JobPipe intake.

The Apps Script layer is not the product. It is infrastructure for getting cleaner source data into the pipeline.

## Current role

The current feed path is:

```text
NAV feed -> Apps Script / Google Sheet -> pull_sheets_csv.py -> JobPipe pipeline
```

The priorities on the Apps Script side are:

- keep ingestion healthy
- keep the sheet lean enough to export efficiently
- avoid quota-related slowdowns

## Recommended changes

### 1. Raise throughput

Increase:

```javascript
const MAX_ENTRIES_PER_RUN = 50;
```

to:

```javascript
const MAX_ENTRIES_PER_RUN = 200;
```

This improves catch-up speed after gaps without changing downstream behavior.

### 2. Cache the UUID index

`buildIndex_()` should not scan the full sheet on every run. Cache the UUID set in Script Properties and invalidate or refresh it on a controlled cadence.

### 3. Archive stale inactive rows

Old inactive rows should move out of the main sheet into an archive tab. The pipeline already tracks active runtime state elsewhere, so the sheet does not need to remain the long-term store for every expired record.

### 4. Remove dead script paths

Keep the Apps Script project narrowly focused on source ingestion. Delete experimental scoring or dead automation code that is not part of the current intake path.

## Operational rule

Treat the sheet as an intake staging layer, not as the primary source of truth for the full product.

The product state now lives in JobPipe's primary DB and derived artifacts.

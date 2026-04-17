# Apps Script Changes — Copy-Paste Guide

**Date:** 2026-04-12
**Purpose:** Clean up and optimize the Google Apps Script and Sheet for JobPipe

---

## ~~1. Delete `Openai deep scoring.gs`~~ ✅ DONE (2026-04-12)

Deleted from Apps Script editor. Dead code — never configured, never run.

---

## 2. Raise `MAX_ENTRIES_PER_RUN` to 200

In `NAV import main.gs`, find this line:

```javascript
const MAX_ENTRIES_PER_RUN = 50;
```

Change it to:

```javascript
const MAX_ENTRIES_PER_RUN = 200;
```

**Why:** The script is healthy (confirmed Apr 11-12 2026 logs). At 50/run with hourly triggers, catching up after a gap is slow. At 200, one trigger covers most new jobs. The PAUSE reason will still be `max_entries_midpage` — that's the designed cap, not an error.

---

## 3. Cache `buildIndex_()` in Script Properties

Find the `buildIndex_()` function. It currently reads ALL rows from the sheet on every run. Replace it with a cached version:

```javascript
/**
 * buildIndex_() — returns a Set of known UUIDs.
 * Caches in Script Properties to avoid reading all 35,000+ rows every run.
 * Cache is rebuilt when it's older than 24 hours or on demand.
 */
function buildIndex_() {
  var props = PropertiesService.getScriptProperties();
  var cacheJson = props.getProperty('UUID_INDEX_CACHE');
  var cacheTs = props.getProperty('UUID_INDEX_TS');
  
  // Use cache if it's less than 24 hours old
  var now = Date.now();
  if (cacheJson && cacheTs) {
    var age = now - parseInt(cacheTs, 10);
    if (age < 24 * 60 * 60 * 1000) {
      try {
        var arr = JSON.parse(cacheJson);
        Logger.log('buildIndex_: using cached index (' + arr.length + ' uuids, age=' + Math.round(age/60000) + 'min)');
        return new Set(arr);
      } catch(e) {
        // cache corrupted, rebuild
      }
    }
  }
  
  // Rebuild from sheet
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('JobFeed');
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var uuidCol = headers.indexOf('uuid');
  
  if (uuidCol === -1) {
    Logger.log('buildIndex_: uuid column not found!');
    return new Set();
  }
  
  var lastRow = sheet.getLastRow();
  var uuids = sheet.getRange(2, uuidCol + 1, lastRow - 1, 1).getValues();
  var indexSet = new Set();
  for (var i = 0; i < uuids.length; i++) {
    var v = String(uuids[i][0]).trim();
    if (v) indexSet.add(v);
  }
  
  // Save to cache (Script Properties has 500KB limit; UUIDs should fit)
  try {
    var arr = Array.from(indexSet);
    var json = JSON.stringify(arr);
    if (json.length < 400000) {  // Stay under 500KB limit
      props.setProperty('UUID_INDEX_CACHE', json);
      props.setProperty('UUID_INDEX_TS', String(now));
      Logger.log('buildIndex_: rebuilt and cached (' + arr.length + ' uuids, ' + Math.round(json.length/1024) + 'KB)');
    } else {
      Logger.log('buildIndex_: index too large for cache (' + Math.round(json.length/1024) + 'KB), not caching');
    }
  } catch(e) {
    Logger.log('buildIndex_: cache write failed: ' + e);
  }
  
  return indexSet;
}

/**
 * Call this after inserting/updating rows to keep the cache warm.
 * Add UUIDs to the cached index without rebuilding from sheet.
 */
function updateIndexCache_(newUuids) {
  if (!newUuids || newUuids.length === 0) return;
  var props = PropertiesService.getScriptProperties();
  var cacheJson = props.getProperty('UUID_INDEX_CACHE');
  if (!cacheJson) return;  // No cache yet, will rebuild on next run
  
  try {
    var arr = JSON.parse(cacheJson);
    for (var i = 0; i < newUuids.length; i++) {
      arr.push(newUuids[i]);
    }
    var json = JSON.stringify(arr);
    if (json.length < 400000) {
      props.setProperty('UUID_INDEX_CACHE', json);
      props.setProperty('UUID_INDEX_TS', String(Date.now()));
    }
  } catch(e) {
    Logger.log('updateIndexCache_: failed: ' + e);
  }
}
```

**After inserting/updating rows in the main import function**, add this call:

```javascript
// After the batch insert/update loop:
updateIndexCache_(newlyInsertedUuids);
```

**Why:** Currently reads all 35,850 rows every run (O(n), growing). With cache, the index is rebuilt once per 24 hours and kept warm via incremental updates. This eliminates the quota exhaustion that broke the script in Dec 2025.

---

## 4. Add `archiveOldInactive()` cleanup function

Add this new function to `NAV import main.gs`:

```javascript
/**
 * Archive INACTIVE rows older than 14 days to an ARCHIVE tab.
 * Run daily via a time-driven trigger.
 * 
 * Design: INACTIVE jobs are expired on NAV. After 14 days there's zero
 * chance of reactivation. The Python pipeline tracks them in its own
 * ledger (SQLite), so archiving from the sheet is safe.
 */
function archiveOldInactive() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('JobFeed');
  
  // Get or create ARCHIVE tab
  var archive = ss.getSheetByName('ARCHIVE');
  if (!archive) {
    archive = ss.insertSheet('ARCHIVE');
    // Copy headers from JobFeed
    var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues();
    archive.getRange(1, 1, 1, headers[0].length).setValues(headers);
    Logger.log('archiveOldInactive: created ARCHIVE tab');
  }
  
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var statusCol = headers.indexOf('status');
  var updatedCol = headers.indexOf('ad_updated');
  if (updatedCol === -1) updatedCol = headers.indexOf('sistEndret');
  
  if (statusCol === -1) {
    Logger.log('archiveOldInactive: status column not found');
    return;
  }
  
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) return;
  
  var data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  var cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 14);
  
  var toArchive = [];
  var rowsToDelete = [];  // 0-based indices into data array
  
  for (var i = 0; i < data.length; i++) {
    var status = String(data[i][statusCol]).trim().toUpperCase();
    if (status !== 'INACTIVE') continue;
    
    // Check age
    var dateVal = data[i][updatedCol];
    var rowDate;
    if (dateVal instanceof Date) {
      rowDate = dateVal;
    } else {
      rowDate = new Date(String(dateVal));
    }
    
    if (isNaN(rowDate.getTime()) || rowDate < cutoff) {
      toArchive.push(data[i]);
      rowsToDelete.push(i + 2);  // +2 because data is 0-indexed, sheet is 1-indexed + header
    }
  }
  
  if (toArchive.length === 0) {
    Logger.log('archiveOldInactive: nothing to archive');
    return;
  }
  
  // Append to ARCHIVE tab
  var archiveLastRow = archive.getLastRow();
  archive.getRange(archiveLastRow + 1, 1, toArchive.length, toArchive[0].length).setValues(toArchive);
  
  // Delete from JobFeed (bottom-up to preserve row indices)
  rowsToDelete.sort(function(a, b) { return b - a; });
  for (var i = 0; i < rowsToDelete.length; i++) {
    sheet.deleteRow(rowsToDelete[i]);
  }
  
  // Invalidate the UUID index cache (it's now stale)
  PropertiesService.getScriptProperties().deleteProperty('UUID_INDEX_CACHE');
  
  Logger.log('archiveOldInactive: archived ' + toArchive.length + ' rows, JobFeed now has ' + (lastRow - 1 - toArchive.length) + ' data rows');
}
```

**Set up the trigger:**
1. In Apps Script editor, click the clock icon (Triggers)
2. Add trigger → `archiveOldInactive` → Time-driven → Day timer → 3am–4am
3. Save

**Why:** The sheet grows unbounded because nothing removes expired jobs. 30,000+ INACTIVE rows slow down `buildIndex_()`, CSV exports, and the Apps Script triggers. Archiving old INACTIVE rows keeps JobFeed lean. The ARCHIVE tab preserves history if needed.

---

## Summary of changes

| Change | Risk | Time | Impact |
|--------|------|------|--------|
| Delete `Openai deep scoring.gs` | Zero | 30 sec | Removes accidental GPT-5 token burn risk |
| Raise MAX_ENTRIES_PER_RUN to 200 | Very low | 30 sec | 4x throughput per hourly trigger |
| Cache `buildIndex_()` | Low | 10 min | Eliminates quota exhaustion, 10-50x faster index lookup |
| Add `archiveOldInactive()` | Low | 15 min | Keeps sheet lean, improves all downstream performance |

**Recommended order:** Delete dead script → raise MAX → cache index → add archive function.

---

## Fix or delete EXPORT tab

The EXPORT tab has a broken `#VALUE!` formula. It's not used by the pipeline (`pull_sheets_csv.py` reads JobFeed directly). Options:

- **Delete it** (safest — avoids confusion)
- **Fix it** — the ARRAYFORMULA references column names that no longer match JobFeed. You'd need to update the INDEX/MATCH column names.

Recommendation: delete it unless you have a specific use for a filtered view in the sheet.

/*******************************************************
 * NAV → Google Sheets (IMPORT ONLY)
 * - Bevarer ømtålig uthenting (feed -> item.url -> entry -> unwrap -> arrays)
 * - Robust: resumérbar + rate-limited
 * - Resume midt i side (NAV_ITEM_OFFSET) så du ikke mister items (999/page)
 * - Update-guard: skriver ikke update hvis ad_updated ikke er nyere
 * - Quota-safe: stopper pent ved UrlFetch-kvote og lagrer state
 * - Ekstra logging: quota + skip-breakdown
 *
 * CHANGELOG (2026-04-12, API import chat):
 *   - MAX_ENTRIES_PER_RUN: 50 → 200  (4x throughput per trigger)
 *   - buildIndex_: reads only uuid + ad_updated columns (2 cols instead of 59 = ~30x less data)
 *   - Added archiveOldInactive(): moves INACTIVE rows >14 days old to ARCHIVE tab
 *   - Added resetIndexCache_() call when archiving to prevent stale row refs
 *******************************************************/

/* =========================
 * CONFIG
 * ========================= */

// DEBUG
const DEBUG_MODE = false;   // sett true ved feilsøking
const DEBUG_MAX_ENTRIES = 3;

const NAV_FEED_BASE = "https://pam-stilling-feed.nav.no/api/v1";
const SHEET_NAME = "JobFeed";
const LOG_SHEET_NAME = "NAV_LOG";

const DEFAULT_BACKFILL_DAYS = 30;
const MAX_PAGES_PER_RUN = 1;
const MAX_ENTRIES_PER_RUN = 200;     // was 50 — safe to raise now that script is healthy

// Rate limiting
const ENTRY_SLEEP_MS = 80;

// Batch entry-fetch (valgfritt, men anbefalt)
const ENTRY_FETCH_CHUNK = 15; // 10–25 er ofte trygg. Øk/fjern hvis du vil.

// Quota-beskyttelse: stopp før helt tomt (slipper exceptions/spam)
const QUOTA_BUFFER = 5;

// State keys (Script Properties)
const PROP_NEXT_URL = "NAV_NEXT_URL";
const PROP_IF_MODIFIED = "NAV_IF_MODIFIED";
const PROP_ITEM_OFFSET = "NAV_ITEM_OFFSET"; // resume innenfor samme side

/* =========================
 * MAIN: NAV IMPORT
 * ========================= */
function runNavImport() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) {
    logWarn("WARN: Forrige kjøring pågår – skipper denne triggeren");
    return;
  }

  const runId = `run_${new Date().toISOString()}`;

  try {
    logInfo(`START ${runId}${DEBUG_MODE ? " (DEBUG_MODE)" : ""}`);

    const ss = SpreadsheetApp.getActive();
    const sh = ss.getSheetByName(SHEET_NAME);
    if (!sh) throw new Error(`Fant ikke ark: ${SHEET_NAME}`);

    const token = PropertiesService.getScriptProperties().getProperty("NAV_BEARER");
    if (!token) throw new Error("NAV_BEARER mangler i Script Properties");

    const header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
    const col = indexColumns_(header);

    if (col.uuid == null || col.ad_updated == null) {
      throw new Error("Header må inneholde kolonnene 'uuid' og 'ad_updated'");
    }

    const index = buildIndex_(sh, col.uuid, col.ad_updated);

    const props = PropertiesService.getScriptProperties();

    let nextUrl =
      props.getProperty(PROP_NEXT_URL) ||
      `${NAV_FEED_BASE}/feed`;

    let ifModified =
      props.getProperty(PROP_IF_MODIFIED) ||
      new Date(Date.now() - DEFAULT_BACKFILL_DAYS * 86400000).toISOString();

    let itemOffset = parseInt(props.getProperty(PROP_ITEM_OFFSET) || "0", 10);
    if (!Number.isFinite(itemOffset) || itemOffset < 0) itemOffset = 0;

    const maxEntries = DEBUG_MODE ? DEBUG_MAX_ENTRIES : MAX_ENTRIES_PER_RUN;

    let page = 0;
    let processed = 0;
    let inserts = 0;
    let updates = 0;
    let skipped = 0;

    // --- Stats / skip breakdown (kun logging) ---
    const stats = {
      feed_items: 0,
      offset_start: itemOffset,
      offset_end: itemOffset,
      fetchall_calls: 0,
      entry_requests: 0,
      non200: 0,
      parsefail: 0,
      no_uuid: 0,
      new_not_active: 0,
      update_not_newer: 0,
    };

    const qStart = getRemainingUrlFetchQuota_();
    logInfo(
      `RUN_META ${runId} start_url=${nextUrl} ifModified=${ifModified} offset=${itemOffset} quota_start=${qStart == null ? "unknown" : qStart}`
    );

    while (nextUrl && page < MAX_PAGES_PER_RUN) {
      page++;

      // Quota precheck før feed-fetch (1 request + buffer)
      if (!hasEnoughUrlFetchQuota_(1 + QUOTA_BUFFER)) {
        stats.offset_end = itemOffset;
        persistStateAndExit_(
          props, ifModified, nextUrl, itemOffset,
          runId, page, processed, inserts, updates, skipped,
          "quota_precheck",
          formatStats_(stats)
        );
        return;
      }

      const feedResp = UrlFetchApp.fetch(nextUrl, {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json",
          "If-Modified-Since": new Date(ifModified).toUTCString(),
        },
        muteHttpExceptions: true,
      });

      const code = feedResp.getResponseCode();

      // NAV kan svare 304 hvis ingen endringer
      if (code === 304) {
        props.setProperty(PROP_IF_MODIFIED, new Date().toISOString());
        props.deleteProperty(PROP_NEXT_URL);
        props.deleteProperty(PROP_ITEM_OFFSET);

        const qEnd304 = getRemainingUrlFetchQuota_();
        logInfo(
          `No changes (304). END ${runId} pages=${page} processed=${processed} inserts=${inserts} updates=${updates} skipped=${skipped} quota_end=${qEnd304 == null ? "unknown" : qEnd304} ${formatStats_(stats)}`
        );
        return;
      }

      if (code !== 200) {
        throw new Error(`NAV feed HTTP ${code}`);
      }

      const feed = JSON.parse(feedResp.getContentText());
      const items = Array.isArray(feed.items) ? feed.items : [];

      stats.feed_items = items.length;
      stats.offset_start = itemOffset;

      if (items.length === 0) {
        props.setProperty(PROP_IF_MODIFIED, new Date().toISOString());
        props.deleteProperty(PROP_NEXT_URL);
        props.deleteProperty(PROP_ITEM_OFFSET);
        break;
      }

      // Hvis offset er større enn antall items (feed kan endre seg), nullstill
      if (itemOffset >= items.length) {
        itemOffset = 0;
        props.deleteProperty(PROP_ITEM_OFFSET);
        stats.offset_start = 0;
      }

      const newRows = [];

      let hitLimit = false;
      let nextItemOffset = itemOffset;

      // ---- BATCH: hent entry-json i chunks ----
      for (let i = itemOffset; i < items.length; i += ENTRY_FETCH_CHUNK) {
        if (processed >= maxEntries) {
          hitLimit = true;
          nextItemOffset = i;
          break;
        }

        const chunk = items.slice(i, i + ENTRY_FETCH_CHUNK);

        // Quota precheck før batch (chunk requests + buffer)
        if (!hasEnoughUrlFetchQuota_(chunk.length + QUOTA_BUFFER)) {
          nextItemOffset = i;
          stats.offset_end = nextItemOffset;

          persistStateAndExit_(
            props, ifModified, nextUrl, nextItemOffset,
            runId, page, processed, inserts, updates, skipped,
            "quota_precheck_midpage",
            formatStats_(stats)
          );
          return;
        }

        let responses;
        try {
          const reqs = chunk.map(it => ({
            url: absolutize_(it.url),
            headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
            muteHttpExceptions: true,
          }));

          stats.fetchall_calls++;
          stats.entry_requests += reqs.length;

          responses = UrlFetchApp.fetchAll(reqs);
        } catch (e) {
          if (isUrlFetchQuotaError_(e)) {
            nextItemOffset = i;
            stats.offset_end = nextItemOffset;

            persistStateAndExit_(
              props, ifModified, nextUrl, nextItemOffset,
              runId, page, processed, inserts, updates, skipped,
              "quota_exception_fetchAll",
              formatStats_(stats)
            );
            return;
          }
          throw e;
        }

        // Prosesser responsene i samme rekkefølge som chunk
        for (let j = 0; j < responses.length; j++) {
          if (processed >= maxEntries) {
            hitLimit = true;
            nextItemOffset = i + j;
            break;
          }

          const r = responses[j];
          if (r.getResponseCode() !== 200) {
            stats.non200++;
            skipped++;
            continue;
          }

          let entry;
          try {
            entry = JSON.parse(r.getContentText());
          } catch (e) {
            stats.parsefail++;
            skipped++;
            continue;
          }

          // UTHENTING/UNWRAP: UENDRET
          const ad = unwrapAd_(entry);
          if (!ad || !ad.uuid) {
            stats.no_uuid++;
            skipped++;
            continue;
          }

          const status = entry?.status || "";
          const adUpdated = ad.updated || "";

          // EXTRACT FRA ARRAYS: UENDRET
          const flat = extractAdFields_(ad, entry);

          const existing = index.get(ad.uuid);

          // Bevarer original logikk: Skip nye annonser som ikke er ACTIVE
          if (!existing && status !== "ACTIVE") {
            stats.new_not_active++;
            skipped++;
            continue;
          }

          if (!existing || existing.row == null) {
            // INSERT
            const row = new Array(header.length).fill("");
            mapAdToRow_(row, col, flat);
            newRows.push(row);

            index.set(ad.uuid, { row: null, ad_updated: adUpdated });
            inserts++;
          } else {
            // UPDATE (kun hvis ad_updated er nyere)
            if (!isNewerUpdated_(adUpdated, existing.ad_updated)) {
              stats.update_not_newer++;
              skipped++;
              continue;
            }

            const rowIdx = existing.row;
            const row = sh.getRange(rowIdx, 1, 1, header.length).getValues()[0];
            mapAdToRow_(row, col, flat);
            sh.getRange(rowIdx, 1, 1, row.length).setValues([row]);

            existing.ad_updated = adUpdated;
            updates++;
          }

          processed++;
        }

        // liten pause mellom chunks for å være snill mot NAV
        Utilities.sleep(ENTRY_SLEEP_MS);
        if (hitLimit) break;
      }

      // Skriv inn nye rader
      if (newRows.length > 0) {
        const startRow = sh.getLastRow() + 1;
        sh.getRange(startRow, 1, newRows.length, newRows[0].length).setValues(newRows);

        newRows.forEach((r, i) => {
          const uuid = r[col.uuid];
          if (uuid && index.has(uuid)) {
            index.get(uuid).row = startRow + i;
          }
        });
      }

      // Hvis vi traff maxEntries midt i siden: lagre offset og behold samme nextUrl
      if (hitLimit) {
        stats.offset_end = nextItemOffset;

        persistStateAndExit_(
          props, ifModified, nextUrl, nextItemOffset,
          runId, page, processed, inserts, updates, skipped,
          "max_entries_midpage",
          formatStats_(stats)
        );
        return;
      }

      // Ferdig med siden: nullstill offset og gå til neste side
      props.deleteProperty(PROP_ITEM_OFFSET);
      itemOffset = 0;
      stats.offset_end = items.length;

      const pageNextUrl = feed.next_url ? absolutize_(feed.next_url) : null;
      nextUrl = pageNextUrl;

      if (nextUrl) props.setProperty(PROP_NEXT_URL, nextUrl);
      else props.deleteProperty(PROP_NEXT_URL);
    }

    const qEnd = getRemainingUrlFetchQuota_();
    logInfo(
      `END ${runId} pages=${page} processed=${processed} inserts=${inserts} updates=${updates} skipped=${skipped} quota_end=${qEnd == null ? "unknown" : qEnd} ${formatStats_(stats)}`
    );
  } finally {
    lock.releaseLock();
  }
}

/* =========================
 * RESET (NAV)
 * ========================= */
function resetNavState() {
  const p = PropertiesService.getScriptProperties();
  p.deleteProperty(PROP_NEXT_URL);
  p.deleteProperty(PROP_IF_MODIFIED);
  p.deleteProperty(PROP_ITEM_OFFSET);
}

function resetAndRunNav() {
  resetNavState();
  runNavImport();
}

/* =========================
 * ARCHIVE OLD INACTIVE ROWS
 *
 * Moves INACTIVE rows older than 14 days to an ARCHIVE tab.
 * Set up a daily time-driven trigger (e.g. 3am–4am):
 *   Triggers → Add Trigger → archiveOldInactive → Time-driven → Day timer
 *
 * Design: INACTIVE jobs are expired on NAV. After 14 days there's zero
 * chance of reactivation. The Python pipeline tracks them in its own
 * ledger (SQLite), so archiving from the sheet is safe.
 * ========================= */
function archiveOldInactive() {
  const ARCHIVE_SHEET = "ARCHIVE";
  const INACTIVE_AGE_DAYS = 14;

  const ss = SpreadsheetApp.getActive();
  const sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) { logWarn("archiveOldInactive: JobFeed sheet not found"); return; }

  // Get or create ARCHIVE tab
  let archive = ss.getSheetByName(ARCHIVE_SHEET);
  if (!archive) {
    archive = ss.insertSheet(ARCHIVE_SHEET);
    const headers = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues();
    archive.getRange(1, 1, 1, headers[0].length).setValues(headers);
    logInfo("archiveOldInactive: created ARCHIVE tab");
  }

  const header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  const statusCol = header.indexOf("status");
  const updatedCol = header.indexOf("ad_updated");
  const sistEndretCol = header.indexOf("sistEndret");

  if (statusCol === -1) {
    logWarn("archiveOldInactive: 'status' column not found");
    return;
  }

  const lastRow = sh.getLastRow();
  if (lastRow <= 1) return;

  const data = sh.getRange(2, 1, lastRow - 1, sh.getLastColumn()).getValues();
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - INACTIVE_AGE_DAYS);

  const toArchive = [];
  const rowsToDelete = [];  // sheet row numbers (1-indexed)

  for (let i = 0; i < data.length; i++) {
    const status = String(data[i][statusCol]).trim().toUpperCase();
    if (status !== "INACTIVE") continue;

    // Determine date: prefer ad_updated, fall back to sistEndret
    let dateVal = updatedCol >= 0 ? data[i][updatedCol] : null;
    if (!dateVal && sistEndretCol >= 0) dateVal = data[i][sistEndretCol];

    let rowDate;
    if (dateVal instanceof Date) {
      rowDate = dateVal;
    } else {
      rowDate = new Date(String(dateVal || ""));
    }

    // Archive if date is unparseable OR older than cutoff
    if (isNaN(rowDate.getTime()) || rowDate < cutoff) {
      toArchive.push(data[i]);
      rowsToDelete.push(i + 2);  // +2: 0-indexed data + header row
    }
  }

  if (toArchive.length === 0) {
    logInfo("archiveOldInactive: nothing to archive");
    return;
  }

  // Append to ARCHIVE tab (batch write)
  const archiveLastRow = archive.getLastRow();
  archive.getRange(archiveLastRow + 1, 1, toArchive.length, toArchive[0].length).setValues(toArchive);

  // Delete from JobFeed (bottom-up to preserve row indices)
  rowsToDelete.sort((a, b) => b - a);
  for (let i = 0; i < rowsToDelete.length; i++) {
    sh.deleteRow(rowsToDelete[i]);
  }

  logInfo(`archiveOldInactive: archived ${toArchive.length} rows, JobFeed now has ${lastRow - 1 - toArchive.length} data rows`);
}

/* =========================
 * EXTRACT + MAP  (UENDRET DATA-UTHENTING)
 * ========================= */
function unwrapAd_(entry) {
  if (entry?.json && typeof entry.json === "object") return entry.json;
  if (entry?.ad_content && typeof entry.ad_content === "object") return entry.ad_content;
  if (entry?.ad && typeof entry.ad === "object") return entry.ad;
  if (entry?.content && typeof entry.content === "object") return entry.content;
  return entry || null;
}

function extractAdFields_(ad, entry) {
  const wl0  = ad.workLocations?.[0] || {};
  const c0   = ad.contactList?.[0] || {};
  const occ0 = ad.occupationCategories?.[0] || {};
  const cat0 = ad.categoryList?.[0] || {};

  return {
    uuid: ad.uuid,
    status: entry?.status || "",
    sistEndret: entry?.sistEndret || "",

    title: ad.title || "",
    description_html: ad.description || "",

    source: "IMPORTAPI",
    sourceurl: ad.sourceurl || "",

    ad_published: ad.published || "",
    ad_expires: ad.expires || "",
    ad_updated: ad.updated || "",

    work_country: wl0.country || "",
    work_address: wl0.address || "",
    work_city: wl0.city || "",
    work_postalCode: wl0.postalCode || "",
    work_county: wl0.county || "",
    work_municipal: wl0.municipal || "",

    contact_name: c0.name || "",
    contact_email: c0.email || "",
    contact_phone: c0.phone || "",
    contact_role: c0.role || "",
    contact_title: c0.title || "",

    applicationUrl: ad.applicationUrl || "",
    applicationDue: ad.applicationDue || "",

    occ_level1: occ0.level1 || "",
    occ_level2: occ0.level2 || "",

    cat_type: cat0.categoryType || "",
    cat_code: cat0.code || "",
    cat_name: cat0.name || "",
    cat_description: cat0.description || "",
    cat_score: cat0.score ?? "",

    link: ad.link || "",

    employer_name: ad.employer?.name || "",
    employer_orgnr: ad.employer?.orgnr || "",
    employer_description: ad.employer?.description || "",
    employer_homepage: ad.employer?.homepage || "",

    engagementtype: ad.engagementtype || "",
    extent: ad.extent || "",
    starttime: ad.starttime || "",
    positioncount: ad.positioncount || "",
    sector: ad.sector || "",

    workLocations_json: JSON.stringify(ad.workLocations || []),
    contactList_json: JSON.stringify(ad.contactList || []),
    occupationCategories_json: JSON.stringify(ad.occupationCategories || []),
    categoryList_json: JSON.stringify(ad.categoryList || []),
    employer_json: JSON.stringify(ad.employer || {})
  };
}

function mapAdToRow_(row, col, flat) {
  Object.keys(col).forEach(k => {
    if (flat[k] !== undefined) row[col[k]] = flat[k];
  });
}

/* =========================
 * HELPERS (NAV)
 * ========================= */
function absolutize_(u) {
  if (!u) return "";
  if (u.startsWith("http")) return u;
  return "https://pam-stilling-feed.nav.no" + u;
}

function indexColumns_(header) {
  const map = {};
  header.forEach((h, i) => map[h] = i);
  return map;
}

/**
 * buildIndex_ — returns a Map<uuid, {row, ad_updated}>
 *
 * OPTIMIZED: reads only the uuid and ad_updated columns (2 cols)
 * instead of the entire sheet (59 cols). ~30x less data to transfer.
 * This was the root cause of the Dec 2025 quota exhaustion:
 * reading 35,850 × 59 = 2.1M cells consumed too much execution time.
 */
function buildIndex_(sh, uuidCol, updatedCol) {
  const map = new Map();
  const lastRow = sh.getLastRow();
  if (lastRow < 2) return map;

  // Read only the 2 columns we need (not all 59)
  const numRows = lastRow - 1;
  const uuidData = sh.getRange(2, uuidCol + 1, numRows, 1).getValues();
  const updatedData = sh.getRange(2, updatedCol + 1, numRows, 1).getValues();

  for (let i = 0; i < numRows; i++) {
    const uuid = uuidData[i][0];
    if (uuid) {
      map.set(String(uuid).trim(), {
        row: i + 2,
        ad_updated: String(updatedData[i][0] || ""),
      });
    }
  }

  return map;
}

/* =========================
 * UPDATE GUARD
 * ========================= */
function toMillis_(v) {
  if (!v) return NaN;
  const d = new Date(v);
  const ms = d.getTime();
  return Number.isFinite(ms) ? ms : NaN;
}

// true hvis incoming er nyere. Hvis vi ikke kan parse -> oppdater (safe).
function isNewerUpdated_(incomingUpdated, existingUpdated) {
  if (!existingUpdated) return true;
  if (!incomingUpdated) return true;

  const a = toMillis_(incomingUpdated);
  const b = toMillis_(existingUpdated);

  if (Number.isFinite(a) && Number.isFinite(b)) return a > b;
  return true;
}

/* =========================
 * QUOTA + STATE HELPERS
 * ========================= */
function hasEnoughUrlFetchQuota_(needed) {
  try {
    if (typeof UrlFetchApp.getRemainingDailyQuota !== "function") return true;
    const q = UrlFetchApp.getRemainingDailyQuota();
    if (q == null) return true;
    return q >= needed;
  } catch (e) {
    return true;
  }
}

function getRemainingUrlFetchQuota_() {
  try {
    if (typeof UrlFetchApp.getRemainingDailyQuota !== "function") return null;
    const q = UrlFetchApp.getRemainingDailyQuota();
    return (q == null) ? null : q;
  } catch (e) {
    return null;
  }
}

function formatStats_(s) {
  const parts = [
    `feed_items=${s.feed_items}`,
    `offset_start=${s.offset_start}`,
    `offset_end=${s.offset_end}`,
    `fetchAll_calls=${s.fetchall_calls}`,
    `entry_requests=${s.entry_requests}`,
    `non200=${s.non200}`,
    `parsefail=${s.parsefail}`,
    `no_uuid=${s.no_uuid}`,
    `new_not_active=${s.new_not_active}`,
    `update_not_newer=${s.update_not_newer}`
  ];
  return parts.join(" ");
}

function isUrlFetchQuotaError_(e) {
  const s = String(e || "");
  const sl = s.toLowerCase();
  return sl.indexOf("service invoked too many times") !== -1 &&
         sl.indexOf("urlfetch") !== -1;
}

// statsStr er valgfri, kun for logging
function persistStateAndExit_(props, ifModified, nextUrl, itemOffset, runId, page, processed, inserts, updates, skipped, reason, statsStr) {
  // behold cursor slik at vi fortsetter der vi slapp
  if (nextUrl) props.setProperty(PROP_NEXT_URL, nextUrl);
  if (ifModified) props.setProperty(PROP_IF_MODIFIED, ifModified);
  props.setProperty(PROP_ITEM_OFFSET, String(itemOffset || 0));

  const q = getRemainingUrlFetchQuota_();
  const qStr = (q == null) ? "quota=unknown" : `quota=${q}`;

  logWarn(
    `PAUSE(${reason}) ${runId} page=${page} processed=${processed} inserts=${inserts} updates=${updates} skipped=${skipped} resume_offset=${itemOffset} ${qStr}` +
    (statsStr ? ` ${statsStr}` : "")
  );
}

function debugUrlFetchQuota() {
  const q = (typeof UrlFetchApp.getRemainingDailyQuota === "function")
    ? UrlFetchApp.getRemainingDailyQuota()
    : "unknown";
  Logger.log("Remaining UrlFetch daily quota: " + q);
  logInfo("Remaining UrlFetch daily quota: " + q);
}

function listTriggers() {
  const t = ScriptApp.getProjectTriggers();
  t.forEach(tr => Logger.log(`${tr.getHandlerFunction()} | ${tr.getEventType()} | ${tr.getUniqueId()}`));
}

/* =========================
 * LOGGING
 * ========================= */
function getLogSheet_() {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(LOG_SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(LOG_SHEET_NAME);
    sh.appendRow(["timestamp", "level", "message"]);
    sh.setFrozenRows(1);
  }
  return sh;
}

function log_(level, msg) {
  getLogSheet_().appendRow([new Date(), level, msg]);
  Logger.log(`[${level}] ${msg}`);
}
function logInfo(msg) { log_("INFO", msg); }
function logWarn(msg) { log_("WARN", msg); }

/* =========================
 * UI MENU
 * ========================= */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Jobber")
    .addItem("Kjør NAV-import", "runNavImport")
    .addItem("Reset + backfill NAV", "resetAndRunNav")
    .addItem("Arkivér gamle INACTIVE", "archiveOldInactive")
    .addToUi();
}

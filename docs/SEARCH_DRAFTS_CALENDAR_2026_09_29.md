# Search updates, draft recovery and reading-calendar exceptions

The owner selected technical items 2 and 6 and app item 1 from the latest proposal. Only these three features were implemented. The rejected ideas are recorded in AGENTS.md and must not be proposed again; the older product plan does not override that preference.

## Incremental search

Catalog commits enqueue only changed searchable fields or relationships. A title update changes its work document; an author/tag change also updates affected books. Private edits, covers and portraits enqueue no search work. Durable queue generations preserve changes arriving during synchronization; database rollbacks enqueue nothing.

The derived FTS schema is now version 2. Missing/old indexes receive an atomic rebuild once; normal updates replace only changed documents in a transaction. Bulk SQL/import changes remain covered by periodic reconciliation after source changes, at most once per minute during search activity. Reconciliation first compares narrow catalog columns and relationships; an unchanged digest avoids constructing documents or writing FTS rows. A first-observed staleness window keeps the existing index usable while reconciliation begins. Accent folding, aliases, relevance, visibility restrictions and the portable fallback remain intact.

The live disposable index was upgraded and holds **15,129 documents**. A subsequent explicit synchronization checked 25,683 catalog/link rows and rewrote **zero** documents. The authoritative database is separate and unchanged by these operations. Long-running older workers need no restart; bulk/source reconciliation covers their writes.

On an isolated copy of the populated catalog, a full rebuild took **583.05 ms**, a one-title update **2.67 ms** with one document rewritten, and unchanged reconciliation **37.45 ms** with no documents rewritten. These are single local synchronization measurements, not browser latency or universal speedup claims. Private receipt: `data/operations/incremental-search-2026-09-29.json`. See [search details](SEARCH_AND_NAVIGATION.md).

```bash
.venv/bin/python manage.py rebuild_search_index --check
.venv/bin/python manage.py rebuild_search_index --sync
```

## Recovery of unsaved writing

Writing editors keep supplemental recovery copies in this browser, separated by account and editor instance. Library notes, module notes, commonplace writing, essays, recall answers, session reflections, reading-desk notes/exercises and study activity responses participate. Normal saved records remain authoritative in the database.

The app offers explicit **Restore** and **Discard** controls. It shows the recovery text and warns when its saved-record version differs from the current version. Restoring changes the editor only; an ordinary save still uses existing conflict protection. Successful saves clear the applicable copies while retaining independently edited copies from other tabs. Partial activity saves checkpoint the remaining unsaved responses. New writing can be copied even while older recovery choices remain unreviewed.

Copies are debounced after actual edits and flushed on page hide/visibility changes, editor closure and account transitions. Session-generation subscriptions revoke stale callbacks and renew recovery for a same-account session change. Page visibility handling follows the browser lifecycle guidance in [MDN](https://developer.mozilla.org/en-US/docs/Web/API/Document/visibilitychange_event); cross-tab setting changes use [storage events](https://developer.mozilla.org/en-US/docs/Web/API/Window/storage_event).

Profile contains **Unsaved draft recovery** controls to disable recovery or clear this account's device copies. Copies survive sign-out for later recovery by the same account, do not sync between devices and are excluded from private account exports/backups. They are browser-local plaintext; clearing browser data removes them. Storage has explicit count/size limits (40 copies, roughly 1.8 MB total UTF-16, 200,000 serialized characters per copy); failures are shown without blocking editing or silently evicting older copies. A crash can lose edits since the last checkpoint, so normal saving remains necessary.

## Holidays and temporary targets

Planner's **Holidays & temporary targets** opens an editor for inclusive date pauses and monthly percentages from **0% to 300%**. Removing a month override restores the usual target; 100% also normalizes to the usual target. Overlapping pause days count once, including leap years and cross-month ranges.

Python applies `usual month budget × month percentage × available calendar days / calendar days`. This respects the existing flexible reading rhythm: holidays reduce available calendar time without inventing fixed weekdays. Temporary percentages and pauses combine explicitly. The current capacity policy is `reading-capacity-v2-calendar-provisional`; physical page counts and frozen reading assumptions are preserved.

**Preview effect on plan** shows before/after capacity, current allocations, unknown lengths and over-target months before **Save calendar changes** becomes available. Saving changes only the calendar settings. Existing book allocations, locks, recorded progress and history remain in place. Background refresh retains unfinished calendar edits; a changed calendar/rhythm/plan invalidates stale confirmations. Planner suggestions, carryover, shortlist and classical/book allocations use the adjusted capacity. Shortlist previews skip whole books that do not fit; manual allocation remains available for explicit partial or over-target choices. See [reading-capacity details](READING_TIME.md).

Calendar records are private and included in JSON/ZIP exports as `reading_calendar`. No calendar rows or holidays were invented for the real account.

## Persistence and verification

Migration **0019_reading_calendar** creates one private table and is applied to the existing database. Fresh pre-migration database/media snapshot: **manual-20260929T002600390150Z**. Read-only comparison checked **34 original tables and 68,703 original rows**. No original rows were lost; account/private records and shared rankings/history were unchanged. Expected migration/permission metadata and concurrent credited media updates were the only differences. All eight deletion guards match, SQLite integrity passes and there are zero foreign-key violations. The new calendar table remained empty. Private audit: `data/operations/preservation-0019-2026-09-29.json`.

The isolated backend suite passed **207 tests**, domain checks **28**, and frontend unit checks **45**. These cover the new calendar boundaries, incremental-index cases, API/export/cache integration and draft-storage rules. Browser verification remains with the owner; no browser automation was run. The live media worker was left running.

Production build/TypeScript, ESLint, Prettier, Django system and migration-drift checks, generated contracts, Python syntax and whitespace checks passed. Compressed static assets were collected. Twenty calendar/API integration cases were rerun successfully after updating the capacity policy version. Migration and export checks used the current schema; no public deployment or database-engine switch was performed.

Owner walkthrough: refresh the app, type an unsaved library note or essay and refresh again to try Restore/Discard; check Profile's recovery controls; open Planner's calendar settings and preview a holiday plus a 50% month. Saving calendar exceptions should change capacity indicators while leaving existing allocations intact.

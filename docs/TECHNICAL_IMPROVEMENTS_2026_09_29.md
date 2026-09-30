# Technical improvements — 29 September 2026

The owner approved all eight technical improvement areas. The implementation uses the existing SQLite database and account. It adds no catalog fixtures, assessments or research. Shared records and prior revisions remain protected.

This is the receipt for the first technical pass. The [selected follow-up](SELECTED_IMPROVEMENTS_2026_09_29.md) supersedes its remaining study-loading, contract, testing and restore limitations, records measured performance and updates migration state to 0018. Off-device copying still awaits a destination.

## Implemented behavior

1. **Account-scoped requests.** A bounded memory cache deduplicates concurrent GETs, cancels superseded requests and ignores late responses from another account. Successful mutations invalidate their dependent resources; previews do not. The default lifetime is 30 seconds, with longer catalog-facet/curriculum lifetimes and focus revalidation. Logout/account changes clear private results across mounted views; another tab receives a session-change notification containing no private payload. Private results are never persisted to browser storage.
2. **Bounded list responses.** My Library, Read next and reading history use 24-row server pages. Library filters and facets run on the server; notes and attempt details load when opened. Explore uses bounded summaries. Planner selectors and list payloads omit heavy detail while preserving physical pages, frozen reading bases and explicitly unknown lengths. Existing full API representations remain available for detail callers.
3. **Smaller study saves.** Curriculum JSON is cached separately from private state. Migration 0017 adds owned StudyRecord rows for growing module/activity/notebook/essay/recall/reading-desk records, preserving their original paths, unknown fields and revision arrays. Saves change only affected rows and return path deltas. Optimistic timestamps reject stale saves; a refresh action loads current saved work while retaining browser drafts. The initial study-state response still assembles the saved records, and the bounded session journal remains on the profile.
4. **Less repeated backend work.** Parsed curriculum files, shared ranking browse metadata and the catalog-review queue have bounded caches. Permissions and private overlays remain outside shared cached values. SQLite file/WAL changes invalidate cached catalog results; ORM signals invalidate in-process PostgreSQL changes, with a short TTL covering writes by other processes. Historical editions load in batches, and recommendations serialize the selected winners after scoring/deduplication.
5. **Smaller frontend/media transfers.** Routes and major study families load lazily. Visited study families stay mounted while hidden to retain unsaved drafts. Cover/portrait previews are cached, bounded WebP derivatives keyed to the original file version; originals and attribution are preserved. WhiteNoise creates compressed assets and gives fingerprinted JS/CSS immutable caching. The main production JS bundle is approximately 274 KB (86 KB gzip), versus approximately 495 KB (141 KB gzip) before this pass. This measures bundle size, not a browser speed benchmark; opening routes fetches their separate chunks.
6. **Incremental and scheduled backups.** New SQLite snapshots reference shared SHA-256 media objects through versioned manifests instead of duplicating all media into each archive. A completed snapshot validates all database media references; copies and restoration verify checksums. Legacy database/tar pairs remain supported. A macOS LaunchAgent is installed and loaded for 03:15 local time daily, independently of app startup, using the existing database/media paths. It has not yet reached its first scheduled run. Retention is an explicit dry-run report only: manual snapshots and shared objects are protected; nothing was deleted. A configured mounted destination can receive verified additional copies. **No off-device destination has been supplied or configured.**
7. **Operational visibility and bounded exports.** Staff have an Operations page with backup age/storage/copy status, queue/cooldown/worker status, and bounded per-process request statistics. Responses carry request IDs; timings record SQL count/duration and known response size without SQL text, request bodies, credentials or private notes. Slow/error logs are rate limited. Worker status/cooldown writes become atomic and heartbeat-aware on the next worker start; the already-running worker was preserved. Route failures leave navigation available. Private JSON/ZIP exports iterate records into temporary files rather than constructing the entire archive in memory, preserving the existing manifest and assembled legacy study state.
8. **Maintainable boundaries and deliberate checks.** Request transport/cache/policies, topbar search, private profile, study data helpers and work preparation have separate modules. Compact API types describe their actual fields. Serializer-derived TypeScript contracts include a drift check. ESLint, React hook checks and Prettier are installed. The manual GitHub Actions workflow checks build/lint/format/contracts; its optional test input enables disposable SQLite/PostgreSQL suites and cache regressions. It is not triggered automatically and has not been run remotely.

## Saved database and verification

Pre-migration database/media snapshot: `manual-20260928T231749495511Z` (new content-addressed format). Migration **0017_studyrecord** is applied. A read-only audit compared all original private fields and shared rankings/entries/revisions with that snapshot. Reassembled study state matches exactly; the existing profiles contained no growing records to extract, so the new table initially has zero rows. The broader comparison found 23 existing application/auth tables unchanged outside the migrated study profile, concurrently enriched catalog and Django system metadata. Original permission/content-type rows were preserved, with metadata for the new model added. All eight deletion triggers match; SQLite integrity and foreign keys pass.

The production build/TypeScript, ESLint (zero warnings), Prettier, Django system checks, migration drift, serializer-contract drift, Python syntax and whitespace checks passed; static assets were collected with compression. Twenty backend and fifteen cache regression cases are saved but **not run**, respecting the owner's current preference. No browser automation, fresh restore rehearsal, Docker/PostgreSQL run or external CI execution was performed. No runtime speedup or query-count reduction is claimed as measured; Operations now provides the measurements for real usage.

## Owner walkthrough

- Refresh the app. Open My Library, filter it and page through results; Edit should load complete saved notes.
- Open Read next and History; page counts and expanded private history should remain consistent.
- Check Planner selectors and existing locked/frozen allocations.
- Open study tools, type a draft, switch tabs and return. A stale save should be rejected; “Refresh saved work and keep drafts” retains the editor text for comparison.
- Open staff **Operations** to see the installed schedule, recent snapshot, queues and request costs. A worker started before this change correctly reports no heartbeat support until its next start.
- Open Profile and download the private JSON/ZIP export when wanted.

## Maintenance commands

```bash
.venv/bin/python manage.py export_frontend_contracts --check
PATH="$PWD/.node/bin:$PATH" npm --prefix frontend run lint
PATH="$PWD/.node/bin:$PATH" npm --prefix frontend run format:check
PATH="$PWD/.node/bin:$PATH" npm --prefix frontend run build
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py backup_retention
```

Generate contracts after changing serializers with `manage.py export_frontend_contracts`. Generated files are excluded from formatting. Use `npm --prefix frontend run format` for frontend source formatting.

The local retention proposal is saved privately at `data/operations/backup-retention-preview.json`. It currently protects 141 snapshots and proposes two old daily snapshots for later review; deletion remains disabled. Snapshot counts will change as scheduled backups accumulate.

For verified copying, choose an existing mounted/external directory, then run `manage.py backup_local --daily --copy-destination /absolute/destination` and reinstall the schedule with `scripts/install_backup_schedule.py --install --copy-destination /absolute/destination` using the same Python environment. The script preserves configured SQLite/media paths. Do not claim disk-loss protection from a directory on the same filesystem. See [DATA_SAFETY.md](DATA_SAFETY.md) and [operations and backups](OPERATIONS_AND_BACKUPS.md) for formats and restoration; public PostgreSQL backups/deployment remain separate work.

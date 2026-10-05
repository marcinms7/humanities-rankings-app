# Selected speed and bulk book actions — 30 September 2026

The owner approved speed proposals 2 and 3 (prepare thumbnails after ingestion; preload intended navigation) and app proposal 2 (bulk private book actions). The broader catalog-cache invalidation change and quick-preview panel were not selected.

## Image preparation

Normal cover and portrait saves prepare 96/240/480px WebP derivatives after the transaction commits. Preparation reads each source once for missing sizes, handles orientation and bounds image dimensions. Version-specific file locks coordinate concurrent ingestion/request processes; atomic publication prevents partial image responses. Preparation failure leaves the saved original and metadata intact and retains request-time fallback. Existing derivatives are reused without decoding originals. No new service or schema is required.

`manage.py warm_thumbnails --kind covers --limit 500 --after-id 0` prepares a bounded page of existing cover references; use `--kind portraits` for people. Continue from the reported `next_after_id` while `has_more` is true. Failed record IDs are reported without changing originals. The command reads catalog records and writes only derived cache files. Existing running media work was left in place; newly started processes acquire the save hook automatically.

The implementation backfill writes a resumable completion receipt at `data/operations/thumbnail-warming-2026-09-30.json`, using an explicitly query-only connection. Its final counts are recorded in HANDOVER.md.

## Navigation intent

Hovering or keyboard-focusing an internal application link for 140ms starts its shared lazy route loader and up to two bounded GET requests with the screen's actual query keys. Clicking starts that preparation immediately and preserves useful requests while the screen attaches. Catalog/book/author pages, ranking indexes/details, the atlas, published comparisons, library, Explore and Today have data plans; remaining supported screens preload code only.

Prefetch reuses the existing account-scoped cache, deduplication and invalidation. Leaving an unselected link cancels its speculative observer without aborting active screen consumers. Speculation is bounded to two concurrent reads/two module imports and an eight-second request lifetime. Hidden/offline pages, reduced-data connections and known slow links do not speculate; account changes invalidate outstanding work. External links, downloads and new-tab links are excluded. No all-pages reads, writes or extra dependencies were introduced. These changes remove preparation work from some navigation paths; no browser speedup percentage was measured.

## Bulk actions

Signed-in readers can choose **Select books** on the catalog, ranking/collection pages and My Library. Selection persists across pages and filters within that view, in click order, with a maximum of 200 distinct books. Repeated country placements select the same work once. **Review selected books** allows removing off-page selections; **Cancel selection** clears them. Selection resets across accounts and different ranking routes.

- **Add to My Library** creates only missing Want to read rows and captures their current edition basis. Existing status, ratings, editions, reading dates, notes and progress are preserved.
- **Add to Read next** saves missing library rows and appends new choices in selection order. Existing shortlist positions and finished attempts remain intact; adding a finished book does not silently start a reread.
- **Add to a private list** appends missing entries to an owned, active private book list. Published/shared rankings, other accounts' lists, person lists and personal lists with sharing enabled are not destinations. Existing positions, source ranks, entry annotations and prior revisions are preserved. List scope and stale revisions are checked.
- My Library also offers **Add shelves** and **Add private tags**. Names append to existing labels; they never replace them. All selected books must already belong to that reader, with at most 50 labels per field.

The destination picker is paginated. A new list can be created in My lists in a separate tab, then loaded with **Refresh lists**, preserving the book selection. Successful actions clear selection and report added/unchanged counts. Errors preserve selection for correction/retry.

`POST /api/library/bulk/` validates the entire bounded command before committing. The existing mutation receipt mechanism makes retries safe; unkeyed repeat additions also produce no duplicates. Private-list revisions and all private additions commit together or roll back together. Generated TypeScript request/response contracts and the runtime result guard cover the endpoint. Cache invalidation refreshes affected private overlays or lists.

## Validation and owner walkthrough

- 21 focused bulk backend tests passed on disposable database/media/search paths: ownership, preservation, revisions, replay, rollback, label limits, malformed commands and a 100-book batch bounded to 15 SQL queries.
- Nine thumbnail tests passed with isolated database/media/search/cache paths: after-commit handling, rollback, corrupt/missing files, fallback, source changes, concurrent requests and resumable backfill.
- All 65 frontend unit tests passed, including nine prefetch cases and four selection/cache cases.
- Production build/TypeScript, ESLint, Prettier, Django system/migration-drift checks and generated-contract drift checks passed. Static assets were collected. No schema changes; the existing database remains at migration 0019.

No browser automation or live test accounts/fixtures were used. The app's private records and rankings were not changed by verification. PostgreSQL/Docker and browser interaction were not exercised in this pass.

Refresh the app and try selecting books across two pages of a ranking, reviewing the selection, and adding it to Read next or a private list. In My Library, select several books and add a shelf/tag. Check that existing progress and ratings stay present. Keyboard-focus or hover book/sidebar links before opening them to exercise navigation preparation. The normal launch command remains `./scripts/run_local.sh`.

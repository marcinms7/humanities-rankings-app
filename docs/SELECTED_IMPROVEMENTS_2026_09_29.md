# Selected follow-up improvements — 29 September 2026

The owner selected technical items **2–7** and app items **1, 2 and 8** from the next-improvements proposal. This pass covers remaining pagination, search, safe ordinary edits/retries, API contracts, measured performance, backup verification, private recommendations/feedback and navigation. It does not start ranking research or add numerical assessments.

## Technical behavior

- Ranking indexes, country placements, personal lists, weighted previews, source lists, candidate selectors and public shares now use pages of 24. Weighted positions are computed before filtering/pagination; country placements retain their local source positions. Personal adjacent moves check the saved revision. Existing full representations remain available for compatibility/export.
- Study entry loads a small summary. Selected tools request pages of 24 current records, with explicit Load more; prior essay/recall/desk histories load 12 at a time when expanded. Unvisited families and revision bodies are not downloaded initially. Saved counts, progress, optimistic revisions, drafts and complete exports remain intact.
- Shared catalog search has a disposable SQLite FTS index with Unicode/accent folding, prefix matching, weighted title/author relevance and explicit ID-based aliases. Inputs are debounced. Catalog changes mark freshness, imports are detected, rebuilds replace the index atomically and an unavailable index has a portable fallback. No private reading data is indexed. The initial index contains 15,129 identities. The aliases file starts empty; verified aliases can be added without changing catalog names. See [search and navigation](SEARCH_AND_NAVIGATION.md).
- Ordinary library, plan and catalog edits expose edit versions; current editors submit them and reject stale writes with the saved values for comparison. Library/catalog forms retain local edits and require an explicit review before trying against the newer version. Existing ranking/study/preview revisions remain authoritative. Legacy API clients without an edit token remain compatible.
- Authenticated JSON mutations use per-account transactional request receipts. An explicit retry after an unknown network/server outcome reuses the request key and receives the saved result rather than creating a second change. Success and definite client errors clear the browser key. No writes retry automatically. Keys stay only in bounded, account-scoped browser memory for ten minutes; file upload requests use version checks but do not get automatic browser replay keys.
- Serializer-derived TypeScript now describes actual catalog/library/plan responses and complex ranking, recommendation, preview and study payloads. The transport validates the selected complex envelopes before caching/merging them. Deliberately open research/study JSON remains `unknown`. Drift checking covers both TypeScript and runtime schemas; this is not an exhaustive OpenAPI specification.

## App behavior

Discover for me now offers an explained three-book bundle: a familiar interest/author, a new author and a shorter commitment where supported. Private interests, bookmarked rankings, saved filters and explicit feedback inform choices. Each slot has bounded substitutions and honest Python time estimates; unknown length does not qualify as short. More like, Not interested and Later are reversible. A removed saved filter is flagged for review rather than silently broadening the preferences. See [recommendation behavior](PRIVATE_RECOMMENDATIONS.md).

Browse filters, search and page are represented in the URL. Opening a detail page and using Back restores the previous location/scroll, including after lazy content loads. Navigation includes document titles, skip-to-content, active-link announcements, main-content focus and a mobile drawer with focus containment, Escape and an inert background. The owner should verify these flows in their browser; no browser automation was launched.

## Measured performance

`manage.py profile_performance --enforce` measures allowlisted GET preparation/rendering with SQLite writes disabled. Reports contain counts/timings/response sizes and query plans, never private response bodies. Three samples include one cold sample and two warm samples. Budgets are deliberately generous: 1,500 ms warm preparation, 60 queries and 400 KB per screen; all 13 profiled screens passed.

Before/after measurements use the same restored catalog/private snapshot, with only the new empty schema tables and a derived search index added to the isolated copy. The discovery query avoids an unnecessary whole-catalog DISTINCT/annotation operation and uses an existence predicate for authors.

| Local measurement | Before | Final |
| --- | ---: | ---: |
| Discovery warm preparation | 338.44 ms | 12.28 ms |
| Discovery response / queries | 12,449 bytes / 6 | 12,449 bytes / 6 |
| Catalog search warm preparation | 13.20 ms | 6.85 ms |
| Ranking index response, full summary versus paged | 92,041 bytes | 22,525 bytes |
| New recommendation bundle | — | 204.01 ms / 15 queries / 16,957 bytes |

Timings vary by machine/cache and are not browser/network benchmarks. Accent-aware search has broader semantics than the old substring search. Existing study profiles were empty, so their live-size timing cannot demonstrate savings for large notebooks; isolated regression fixtures verify bounded records/history behavior. Reports are saved privately in `data/operations/performance-{before,after-queries,final}-2026-09-29.json`.

## Saved data and recovery

Migration **0018_safe_mutations_and_recommendations** creates only owned recommendation feedback/preferences and mutation-receipt tables. It is applied to the existing `data/db.sqlite3`. The pre-migration snapshot is **manual-20260928T234844923075Z**. A read-only audit compared all 33 original tables and 68,711 original rows: no originals disappeared, private/account/reading/study data and shared rankings/revisions were unchanged. Only expected Django metadata and concurrent credited media enrichment differed; both new tables remained empty. All eight deletion triggers match and integrity/foreign keys pass. Aggregate receipt: `data/operations/preservation-0018-2026-09-29.json`.

An isolated restore of that snapshot verified **6,884 media files**, database integrity, foreign keys and eight deletion guards. Report: `data/operations/restore-drill-2026-09-29.json`. The existing 03:15 macOS LaunchAgent was triggered through `launchctl`; its execution completed with exit code 0. This verifies the scheduler execution path, not an observed natural 03:15 wake-up. Nothing was pruned and the live media worker was preserved.

**Off-device copying remains unconfigured: the owner has not supplied a destination.** The copy/scheduler options are ready in [operations and backups](OPERATIONS_AND_BACKUPS.md). Local restore success does not provide disk-loss protection. PostgreSQL/Docker, hosted operation and remote CI remain unverified.

## Maintenance and owner walkthrough

Final validation: **176 backend tests, 28 domain tests and 30 frontend unit tests passed**. Backend suites used temporary database/media/search paths. Production build/TypeScript, ESLint, formatting, Django system/migration-drift checks and generated contract checks passed; compressed static assets were collected. This run covers the previously deferred suites. No browser automation, PostgreSQL/Docker execution or remote CI run was performed.

```bash
.venv/bin/python manage.py rebuild_search_index --check
.venv/bin/python manage.py export_frontend_contracts --check
.venv/bin/python manage.py profile_performance --enforce
PATH="$PWD/.node/bin:$PATH" npm --prefix frontend run test:unit
```

Set `SQLITE_PATH`, `MEDIA_ROOT` and `CATALOG_SEARCH_INDEX` to disposable paths for backend suites. Current tests never need fixtures in the owner's database. The manual CI workflow supports isolated SQLite/PostgreSQL suites; browser checks remain owner-driven.

Refresh the app and try an accented catalog search; page a country/personal ranking; open a book and use Back; edit the same library item in two tabs to see a conflict; try the recommendation preferences, a substitution and reversible feedback; open a study panel and expand its saved history. Launch remains `./scripts/run_local.sh`.

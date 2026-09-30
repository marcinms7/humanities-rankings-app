# Application code review — 28 September 2026

This review followed the owner's request to understand the project documentation and code, find bugs and fix them. Existing uncommitted maintenance, imported research, and concurrent media-completion work were preserved. The review itself performed no database writes, imports, network research or enrichment runs.

## Scope and current application

Marginalia is a populated Django/React application, with SQLite for this local workspace and PostgreSQL/Docker configuration for later deployment. Shared researched rankings, publisher rankings and reading collections have distinct behavior. Private library records, attempts, ratings, plans, study notes and personal ranking copies remain owned by the reader. Numerical personalized assessments still require agreed criteria; broad editorial rankings already exist.

Detailed review covered the runtime backend (models, serializers, views, accounts, permissions, domain rules, discovery and study modules), every frontend source file, management commands, active enrichment workers/queues, launch/backup configuration and relevant current documentation. Research target documents and historical records were scanned for implementation contracts and stale instructions. Historical receipts were retained rather than rewritten as present-day claims.

The initial documentation scan covered 294 Markdown files and 11,555 lines; all unresolved relative links were within historical copies or generated prompt material. The integration syntax sweep parsed 171 project Python files, including operational/historical scripts. These counts describe those sweeps, not a fixed repository size: another task added media-completion files during the review. Static inventory/syntax coverage of historical scripts is not a line-by-line semantic audit of every old script, and this was not a re-verification of external research evidence.

## Fixed behavior

### Plans and reading records

- Planner suggestions previously recalculated on confirmation without checking the reviewed state. Suggestions, Read next additions and classical allocations now return a signed, user-bound `preview_token`, valid for 30 minutes. Applying requires the token and unchanged relevant library/plan/proposal state; stale confirmations return HTTP 409 before modifying records.
- Planner library/progress reads now happen under the same user lock as applying allocations. Profile updates and classical plan writes use that lock too; planner/classical writes refresh the locked profile before using its settings.
- Frontend preview responses are scoped to their inputs; inputs are disabled during requests and failed applies clear the preview. Unrelated refreshes no longer reset manually selected planner books.
- SQLite JSON null page counts no longer become zero in discovery filters. Unknown lengths stay unknown and cannot qualify as short books.
- Legacy plan-basis capture uses a reader's selected edition when its snapshot is absent. The edition-change dialog displays the frozen saved length.
- Duration responses retain the estimator's `length_basis` (`word_count`, `page_count_estimate` or null); page provenance is a separate `page_count_basis` field.

### Catalog, privacy and navigation

- Shared-list book/sidebar links can navigate away from the shared page. Archived personal lists no longer resolve through sharing URLs.
- New library selections and personal-list additions reject archived catalog records/editions. Existing private references remain editable; archiving does not erase reading history.
- Changing accounts remounts page state, preventing one reader's cached page state from remaining visible for another.
- One shared unsaved-study guard covers module/activity notes, reading-desk work, essays and commonplace drafts through hash navigation, browser history, page exit and logout.
- Catalog edits preserve genres when options load asynchronously, preserve unchanged contributor IDs (including ambiguous names or names containing commas), retain an existing edition's language and save attribution-only edits.
- Browser number inputs accept any valid saved effort multiplier. Reading-rhythm controls follow saved profile settings instead of overwriting a newly saved pace with stale form values.
- Date-only reading values display without timezone shifts. Personal-list labels and unranked shared-person rows respect their list type. Request errors are visible in affected author/edition/history flows, modal focus skips unavailable controls, and over-capacity bars use the existing danger color.
- Vite development now proxies `/accounts` so registration/recovery links reach Django.
- The API rejects whitespace-only criterion IDs consistently with model validation. Provenance reports the canonical underlying source identity.

### Imports, enrichment and recovery

- Import receipt replacement preserves the previous bytes under a content hash; the conventional receipt filename continues to identify the current input for downstream ID mapping. Five import/publication commands share this behavior.
- Reviewed cover imports retain their cover source URL and provenance separately from bibliographic metadata.
- Page enrichment includes edition identity in lookup fingerprints and rechecks the default edition/ISBN under lock before writing. A nullable joined lock that would fail on PostgreSQL was removed; PostgreSQL runtime behavior remains unverified.
- Provider failures consume the portrait retry budget for due retries. Public cover downloads are bounded and raster-validated; title-only searches still require author agreement. Workers recheck concurrent archival and preserve existing covers.
- The exact-edition collector no longer mistakes “unabridged” for “abridged.” Its existing staged-review policy remains.
- Concurrent local backups serialize writes to their database/media pair. Alternate explicitly configured SQLite files use separate daily completion markers.
- The obsolete web-enrichment shell wrapper now exits with an actionable maintained command; the old cover monitor delegates to the queue-aware monitor. Historical Python workers remain retained and should not be used to bypass the current documented workflows.

### Documentation

README and PROJECT_PLAN no longer present the empty-catalog phase, completed imports or implemented email-recovery forms as outstanding implementation. They retain incomplete edition verification, SMTP/deployment work and the distinction between editorial rankings and personalized numerical assessment. Import/workflow documentation now describes current revision updates and cover-provenance fields. Historical reports and the separate media-completion task remain intact.

## Verification and limits

Passed for this review:

- Django system check: no issues.
- Migration drift check: no changes; schema remains through migration 0015.
- Python syntax sweep: 171 files parsed.
- Operational shell syntax and changed-file whitespace checks.
- TypeScript/Vite production build and Django static collection.
- Read-only SQLite integrity check: `ok`; zero foreign-key violations; all eight shared deletion guards present.

Thirteen new backend regression cases were saved, and the existing planner-confirmation case was updated for the token contract. **No automated test suite or browser automation was run by this review**, following the saved development preference. Prior test counts in the maintenance/content reports predate these fixes and do not validate this change set. Concurrent media work has its own verification record.

Manual checks for the owner: navigate from a shared list to a book and back; edit a book's genres/attribution without changing contributors; preview and save a planner/Read next/classical allocation; edit an allocation in another tab and confirm that the old preview is rejected; try leaving an unsaved study draft. Use existing records intentionally rather than creating fixtures in the live database.

Remaining limits: the new regression cases await an authorized isolated suite run; Docker/PostgreSQL, SMTP, hosted deployment and live provider behavior were not exercised here. This review does not claim the catalog metadata or research backlog is complete or that every historical script is safe for a new run.

# Seven application improvements · 28 September 2026

The owner approved implementing all seven proposed improvements. These additions use the existing account and database, with no new ranking research, invented scores or imported catalog content.

## Daily reading and monthly follow-through

**Today** is in Your reading space. It shows current books with quick progress updates, the current month's allocations and the Read next shortlist. Its home-page toggle is saved to the account; Explore remains the default until the reader opts in. Updates reject stale progress from another window.

The planner now records **pages read in each allocation** explicitly. These totals are separate from a book's current page: old schedules cannot establish how many pages were actually read in a particular month. Existing allocations therefore begin with reading totals unset.

**Preview carryover** moves explicitly unfinished pages into the following month, with capacity, locks, saved edition/effort conflicts and partial transfers shown before confirmation. Original allocated pages remain saved; each transfer has a receipt. Locked allocations are skipped. Allocations for selected classical passages retain their separate study workflow. Suggestions preserve allocations with recorded reading or carryover history, as well as locks. A mistaken monthly reading total can be cleared before carryover; transferred history is retained.

See [daily reading and carryover](DAILY_READING_AND_CARRYOVER.md) for the complete behavior and manual checks.

## Choose an edition, save, and plan

Book pages include **Your next steps** with the reader's saved edition, length, progress and remaining time. The reader can choose an edition before saving, add/remove the work from Read next, or save it and preview a monthly allocation. Changing an existing reading edition uses the established edition-change preview and adjustment receipt. Catalog updates never silently rewrite the saved reading basis.

Scheduling displays the monthly budget and warns about over-capacity allocations and unfinished/unrecorded allocations of the same book in other months. The backend signs the preview against the relevant library record, edition assumptions and plan state. Finished or abandoned readings require a new reading attempt before this scheduling action. Unknown lengths remain visibly unknown.

## Reusable private discovery filters

**Discover for me** can save, rename, update or delete named filter combinations. Saved filters appear in the catalog, My Library and the planner's book picker. They are private database records. Cross-screen links preserve the chosen filter.

The combinations cover search, subject, genre, country, ranked-list membership counts, page limits, unread books, wishlist, unfamiliar authors and bookmarked rankings. They are evaluated against current private history/bookmarks each time. Page limits use a saved reading length when one exists, including an explicitly unknown length. Filtering the planner's available books does not hide or delete existing allocations.

## Ranking perspective comparison and bounded browsing

Eligible researched rankings offer a side-by-side comparison of **standing** and **reading value**, including recorded positions, differences and existing explanations/evidence. Coinciding orders are labelled honestly; the feature does not manufacture separate assessments. Published lists retain publisher order, and country-local rankings retain their grouping rather than acquiring global positions.

Normal ranking browsing uses compact metadata and server-paginated entries, with only the visible page's book details and personal context. Grouped, personal-editing and weighted views retain their specialized paths. This improves ordinary browsing without changing saved rankings or their revisions.

## Staff catalog review

**Catalog review** is a separate staff-only workspace. It groups missing/uncredited covers and portraits, identity signals, staged editions and incomplete page-count evidence. Its priority indicators use existing list appearances and aggregate library saves; they do not claim to measure views or reveal individual readers.

Staff can inspect saved evidence, batch-prioritize/defer/reopen issues and record research needs or evidenced identity checks. Decisions have actor, timestamp, content fingerprint and batch receipts; stale decisions are rejected. An identity check is not an automatic merge. Missing media remain unresolved until actual credited media exist.

Staged edition approval requires explicit identity, publisher/language/abridgement and pagination confirmation with sources. Approval preserves the original candidate provenance, current default edition and private reading snapshots. This workspace supports the metadata backlog; creating it does not complete that research.

## Full private export

**Profile → Your data** downloads either JSON or a ZIP archive. API URLs are `/api/export/` and `/api/export/?download=zip`. The `download` parameter avoids DRF's reserved renderer-selection parameter.

The versioned JSON includes the profile, current library, previous reading attempts, goals, edition adjustments, all plans and carryover receipts, bookmarks/weights/overrides, saved discovery filters, personal lists with entries and revision history, complete classical study profiles and the reader's catalog review decisions. Study state includes saved notes, answers, commonplace entries, essay drafts/revisions and other persisted study work. Referenced work/person/edition records make IDs interpretable outside the application. The manifest records coverage and exclusions.

The ZIP contains `private-data.json`, `study-state.json`, `reading-notes.md` and a README. Passwords, sessions, active sharing tokens, other readers' private data and image bytes are excluded. Unsaved browser drafts are not persisted records and are not exported. This is a portable export, not an automatic restore/import feature; retain database/media backups for recovery.

## Persistence and validation

Migration **0016_catalogreviewdecision_plancarryover_and_more** adds the home preference, monthly reading/carryover fields, private saved filters, carryover receipts and review audit records. Database constraints keep recorded reading and carried pages within the original allocation.

Pre-migration database/media backup: `manual-20260928T224830666133Z`. Migration applied to the existing `data/db.sqlite3`. A read-only comparison against that backup verified every original field in the eight account/reading/study tables, all ranking records/entries/revisions and all eight deletion guards. SQLite integrity/foreign-key checks, Django system checks and migration-drift checks passed.

The final frontend build/typecheck and static collection passed, along with Python syntax and whitespace checks. Forty-two backend and four domain regression cases are saved for isolated future execution. The staff review screen loads separately from the main bundle. The suites and browser automation were **not run** during this implementation, following the owner's preference. PostgreSQL/Docker remain unverified.

## Suggested owner walkthrough

1. Open Today, try the optional home setting and update one current book.
2. On a book page, choose a reading edition, save to Read next and preview a month allocation.
3. Record a monthly pages-read total in the planner and inspect a carryover preview, including skipped/partial items, before choosing whether to apply it.
4. Save a discovery filter and follow its Catalog, Library and Plan links.
5. Open a researched ranking with two perspectives and compare their explanations/order; confirm published lists still use source order.
6. As staff, open Catalog review and inspect existing issues and evidence before making any decisions.
7. Download the private archive from Profile and inspect its manifest, study state and notes.

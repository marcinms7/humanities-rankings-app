# Catalog atlas and published-list comparison

The owner selected proposals **2 and 3**: a catalog atlas/timeline with personal reading overlays, and comparisons between saved published rankings. Question-led discovery was not selected. Previously rejected improvement ideas remain excluded.

## Atlas & timeline

Open **Atlas & timeline** in the sidebar or from **Book catalog** (`#/atlas`).

- A local interactive world map supports country selection, regional views, zoom, pan, reset and keyboard navigation. Choose an exact saved country label to filter books.
- The century timeline links to the map and book results. BCE and CE centuries have no zero; empty centuries retain their spacing. Undated and invalid dates have a separate selectable group.
- Search, subject, country, century, reading overlay and result page are URL-backed. Book results load 24 at a time. Map zoom and keyboard focus survive filter requests; a loading notice distinguishes retained results from the incoming view.
- **In my library** and **Books I have read** use only the signed-in account. Read means a current finished item or a previous finished reading attempt, so starting a reread does not erase a completion. Repeated completions count once per book.
- Country/century facets respect the other filters and show catalog, saved and read counts. Each facet ignores its own selected value, allowing a different country or century to be chosen. Summary saved/read/date coverage describes the matching catalog before the overlay; the result count includes the overlay.

Country strings remain exact literary/cultural associations, including separate England and United Kingdom labels. Multiple associations can count a book in more than one place; the overall book total stays unique. Exact geographic aliases can share a map marker, but the chooser retains their separate labels and counts. Marker size uses the largest individual label count at that point, not a potentially duplicated sum.

Broad traditions, historical labels, mixed associations, prose and missing locations remain accessible under **Browse all places and traditions**. The app does not guess coordinates for them. The date field is the saved original year; displaying it does not verify an exact composition/publication date. No date or country metadata was rewritten.

The map uses bundled public-domain Natural Earth geometry and label points; attribution, source hashes and transformation details are in [atlas-LICENSE.md](../frontend/src/assets/atlas-LICENSE.md). It makes no external map-service requests. Modern reference geography does not imply historical borders, birthplace or book setting. Both map and timeline are lazy-loaded with this screen.

## Compare published lists

Open **Published rankings → Compare published lists** (`#/published-comparison`). Choose List A and List B, then browse shared choices, entries only in A or entries only in B. A list detail page can preselect that list for comparison.

- Eligible lists are visible, active, shared `origin=external`, `presentation=ranked` rankings. Researched rankings, personal copies and unranked/sequence reading collections are excluded. Book lists compare with book lists; people lists compare with people lists.
- Each side shows its publisher, saved size, source link and available method/scope/limitations. Saved import omissions are identified when recorded. The summary counts all active saved identities before search.
- Publisher `source_rank` is authoritative. Ties retain their numbers. Missing/invalid ranks and positions confined to a group do not gain a global rank from display order.
- Shared entries show both original positions and the absolute position difference, indicating which list places the entry higher. Sorting by either publisher rank, largest difference or title never renumbers the source ranks. Missing ranks remain unknown; absence from a list is distinct from an unrecorded rank.
- Different scopes and list lengths remain visible. A positional difference is not a normalized merit score or evidence that one publisher rejected a book. Series and individual volumes keep their catalog identities.
- The selected pair, view, search, sort and 24-entry page are URL-backed. Swapping the pair reverses the comparison without changing stored lists.

## Data and implementation boundary

These are read-only views over saved data. No schema migration, ranking research, imports, personal assessments, edits to private records or rewrites of publisher lists are needed. The existing `data/db.sqlite3` and real account remain in use, at migration **0019**. The running media worker was not changed.

Only public atlas metadata enters the shared backend cache. Reading overlays are queried for the current account on every request. Both endpoints return `Cache-Control: private, no-store`; frontend memory caching is account-scoped and invalidates with relevant catalog, ranking and reading changes. New response contracts are generated from explicit serializers and checked at the frontend API boundary. Work/person cards omit archived content.

## Owner walkthrough

1. Open Atlas & timeline. Choose Europe, zoom in, select England, then choose a century. Use **All places** or **All dates** to clear either dimension.
2. Try saved/read overlays, including a previously completed book now being reread. Open undated books and the unplaced-label list. Check Back/Forward and the mobile layout.
3. Compare two published book lists. Switch between shared/unique entries, sort by position difference, search, swap the lists and open a book or source. Confirm the original publisher positions remain unchanged.

Browser verification remains with the owner; no browser automation was launched.

## Validation

- **229 Django backend tests, 28 domain tests and 52 frontend unit tests passed** (309 total). Backend database, media and search files were isolated under a temporary directory. The new cases cover century boundaries, unavailable metadata, account isolation, completed rereads, original ranks/ties, list visibility, pagination/query bounds, map coordinates, cache invalidation and response validation.
- Production frontend build/TypeScript, ESLint, Prettier, Django system checks, migration drift, generated-contract drift and whitespace checks passed. Static assets were collected for the local launch.
- A separate isolated snapshot of the existing catalog passed the new response contracts for country/date/search/reading filters and comparisons. Its atlas contains **8,491 active books**, of which **4,060 have saved valid years**. The 434 nonempty saved association labels include **202 mapped geographic labels**; 232 contextual/historical/mixed labels remain unplaced, alongside the unknown-association bucket. These are dated observations of saved data, not a new research completeness claim.
- No schema or live catalog/private-data writes were performed by this implementation. PostgreSQL/Docker and browser layout remain outside this pass’s verification.

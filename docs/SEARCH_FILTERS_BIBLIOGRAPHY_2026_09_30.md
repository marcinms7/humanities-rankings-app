# App search, catalog filters and bibliography — 30 September 2026

The owner accepted all three app suggestions in this round. All are implemented. The accompanying broad search SQL optimization, lazy editing forms and SQLite WAL/runtime work was not selected.

## App-wide search

Open **Search anything…** in the top bar or press **Cmd/Ctrl+K**. Results appear in separate groups for books, authors/thinkers, researched rankings, published rankings, reading collections, the signed-in reader's personal lists, accessible research sources and classical study pages. Up/down selects suggestions, Enter opens one and Escape closes; Tab also reaches group continuation links. Requests are debounced and cancelled when superseded. Dialog typing stays separate from the underlying reading screen.

`GET /api/app-search/?q=…` returns at most five items per group, plus continuation information. Book/author matching uses the existing Unicode/alias-aware index. Ranking/source matching uses recorded text; study matching covers static section/module/glossary titles and descriptions. It does not search private notes, study answers or other readers' personal lists. Study results follow the existing owner-only syllabus permission; research sources require sign-in. Responses and frontend cache entries remain account-scoped. Clicking source and study results also works while already on those screens.

## Catalog filters

The catalog's **Subjects**, **Genres**, **Forms** and **Countries & associations** controls support multiple includes and excludes. A book may match any included value within a facet, must satisfy every selected facet and must avoid excluded values. Overlapping genre memberships do not duplicate books or inflate totals.

Each button's number is the total that would result from clicking that button, including deselection and replacing the opposite include/exclude mode. Options are searchable; large selections remain reachable through search. Controls retain focus and option-search text during requests; stale count actions are disabled. Up to 50 values per include/exclude selection are supported.

`field_any`, `genre_any`, `form_any`, `country_any` and matching `_not` parameters use JSON arrays, preserving commas in exact labels. Old single-value links still work. Omitted include arrays inherit existing singular/saved defaults; explicit `[]` clears them. Search, author and saved private constraints also apply to counts. New combinations live in the catalog URL and browser history; existing saved presets retain their prior fields/schema.

`GET /api/works/facets/` returns prospective counts computed from two lightweight SQL queries and sets, without a query per option. A query-only snapshot of the saved catalog matched 72 toggle totals to actual filtered results. On 8,491 books with 434 country options, the focused local preparation measurement was approximately 80 ms; this is not browser timing or a hosted performance guarantee.

## Bibliography export

In the catalog, a ranking/collection or My Library, choose **Select books**, then **Export bibliography**. Up to 200 unique selected books retain their selection order across pages and filters. The dialog previews, copies or downloads plain references (`.txt`), RIS (`.ris`) and BibTeX (`.bib`). Export does not clear the selection or modify records.

The default preference uses edition metadata frozen with the reader's saved reading record. Explicitly unknown frozen details remain unknown even if a newer catalog default exists. Older records with a selected edition use that edition; otherwise an active catalog default is used. Unchecking the preference requests catalog defaults explicitly. Review each entry's edition source and missing information in the dialog.

Edition publication years are not currently stored. They therefore remain missing rather than borrowing a work's original date; original dates, including BCE, appear only in contextual notes. Translator attribution remains a recorded-text note, not a fabricated editor role. Non-book forms use generic RIS/BibTeX types. Plain references are neutral metadata references, not a promised citation style. Author names are preserved as recorded; their parts and order have not been editorially verified.

`POST /api/bibliography/` is an authenticated, bounded read with no mutation receipt or invalidation. It rejects missing/archived selections as a whole. It reads only the requesting reader's edition metadata and never includes private reading notes, ratings or other users' records. RIS control characters and BibTeX syntax characters are escaped, including unmatched braces. The dialog loads separately when opened.

## Verification and preservation

- All **295 backend tests and 80 frontend unit tests passed**. Backend suites used temporary database, media and search storage; no live fixtures were created.
- New coverage exercises account/list visibility, study/source destinations, filter inheritance and prospective counts, edition snapshots, missing metadata, read-only exports and format escaping. Installed BibTeX parser checks passed for unmatched braces and preserved subsequent fields.
- TypeScript/production build, ESLint, formatting, Django system/migration-drift checks, generated contracts and whitespace checks passed. Static assets were collected.
- No schema change or research import was needed. The live database stays at migration **0019**; account/private records, shared ranking history and ongoing media work were preserved.
- No browser automation was run. Docker/PostgreSQL and browser performance were not verified in this pass.

## Owner walkthrough

1. Refresh the app. Open search, try an author, a publisher and a study term, then use keyboard navigation and follow a result.
2. In the catalog, include two countries, exclude a form and check the prospective totals. Search the options; use Back to restore an earlier combination. With a saved filter selected, compare **Allow any** and **Use saved**.
3. Select books across two catalog pages or filters, then export each bibliography format. Check the preview and missing details; toggle saved editions versus catalog defaults. The same export action is available from rankings/collections and My Library.

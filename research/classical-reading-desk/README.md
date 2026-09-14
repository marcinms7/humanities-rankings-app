# Reading trails, personal discovery and classical reading desk — 14 September 2026

## Implemented scope

- Sidebar **Reading trails** (`#/trails`): three editorial sequences, 13 steps, with explicit suggested selections/questions/bridges, current permission-visible list links and account reading status. Drama, Chinese literature and scientific thought. These are versioned application content, not new Ranking rows, not external publisher collections, and not merit rankings. No books or personal allocations are created by browsing. Completed whole books provide continuation context, not a claim that partial assignments were completed.
- **Discover for me** in the private navigation (`#/discover`): three presets and combinable server-side filters for unread, wishlist, unexplored authors, minimum distinct rankings, maximum edition pages, title/author and catalog field. Results are paginated at 24. Finished current/archived attempts count as read. Author exploration considers started/reading/paused/finished/abandoned attempts, including current-page progress; a wishlist alone does not mark an author explored. Unknown authors are excluded from the new-author filter. Any explored coauthor excludes a book. No title/author aliases are silently merged.
- Classical **Reading desk**: two passage units (Iliad 1.1–7 and Aeneid 1.1–7), Greek/Latin with two selectable English translations each, translation reveal, larger type, source/rights credits, glossary/module/book links and revisioned private notes per passage/translation. Responsive parallel columns stack on small screens. Not a complete online text library or word-aligned interlinear edition.
- **Translation lab**: six original comparison prompts across those two passages, two translations side-by-side, optional guidance, saved answers with revisions and export. No automated grades or fabricated accuracy scores.
- Existing **Context & glossary** extended from six to ten terms: Stoicism, patronage, elegy/elegiac couplet and epic. Search normalizes accents; term index, related-term links and deep links from the desk/reception cards. Original six entries and context cards remain untouched.
- **Reception trails**: four explicitly labelled branches across drama, art and film. Sophocles–Anouilh adaptation; Ovid–Gérôme reception; Odyssey allusions in Coen films; Antigone–Ibsen as an expressly thematic comparison with no historical influence claim. The older Connections tab and its records remain available.

## Files and persistence

Content: `backend/core/content/reading_trails.json` and `classical_reading_desk.json`. Reviewed existing work IDs are explicit, never automatically matched from ambiguous titles. All 13 trail steps currently have active catalog identities and visible list memberships. Missing future catalog records retain their step labels rather than causing a silent replacement.

APIs: `reading_trails.py` supplies authenticated read-only `/api/reading-trails/` and `/api/personal-discovery/`. Classical content and saves retain the existing owner-only `/api/classical-education/` boundary. All new responses/exports are private/no-store.

`ClassicalStudyProfile.state.reading_desk` is additive; `note` keys are passage:translation, `exercise` keys are passage. Each update checks an expected revision inside the existing profile transaction/lock; earlier revisions remain stored. Up to 20,000 note characters, 10,000 per answer and 100 earlier revisions per record; the server rejects overflow rather than trimming history. Notes are private and completion-independent. No migrations, live database writes, imports, reseeding, account creation, planner changes, ranking edits or media changes were necessary. Future edits must preserve passage IDs, content revisions and all historical private records.

Short-book filtering uses a reader-selected edition if one exists, otherwise the default catalog edition. Unknown selected-edition length is NOT replaced with another edition's length. Unknown lengths do not pass a maximum-page filter. Page counts are physical edition metadata, not an effort calculation. Ranking counts include only ranked visible shared lists, exclude reading collections/sequences, and are neither independent votes nor quality scores. Content duplication in the existing catalog remains an explicit limitation.

## Source and reuse audit

This was bounded study-content verification, not a new ranking research run. Nothing was imported into any ranking's source ledger or used to revise its research date. Eight reference records with narrow evidence/access notes are saved in the desk JSON and visible in the relevant glossary/reception screens; translation credits/direct URLs are stored per passage. Previous companion source records retain their original access dates/limitations.

Text sources checked on 14 September 2026:

- Greek opening and Monro/Allen header: https://raw.githubusercontent.com/PerseusDL/canonical-greekLit/master/data/tlg0012/tlg001/tlg0012.tlg001.perseus-grc2.xml
- Perseus provider terms: https://github.com/PerseusDL/canonical-greekLit — README specifies CC BY-SA 4.0 unless otherwise indicated. Seven-line extraction removes TEI markup, retains wording and is explicitly credited/licensed accordingly. No newly authored commentary is copied. The initially attempted uppercase LICENSE.md URL failed; the repository uses lowercase license.md.
- Samuel Butler: https://www.gutenberg.org/cache/epub/2199/pg2199-images.html and https://www.gutenberg.org/ebooks/2199 — opening and translator identity/life dates checked.
- Alexander Pope: https://www.gutenberg.org/cache/epub/6130/pg6130-images.html and https://www.gutenberg.org/ebooks/6130 — opening eight English lines and translator identity checked. Notes not copied.
- Latin opening/modern commentary reference: https://dcc.dickinson.edu/vergil-aeneid/vergil-aeneid-i-1-11 — ancient text with displayed macrons retained; modern notes are linked and briefly paraphrased, not reproduced. No wholesale commentary reuse/license claim.
- John Dryden: https://classics.mit.edu/Virgil/aeneid.1.i.html and https://www.gutenberg.org/ebooks/228 — ten-line opening and translator identity checked.
- J. W. Mackail: https://www.gutenberg.org/cache/epub/22456/pg22456-images.html and https://www.gutenberg.org/ebooks/22456 — opening prose paragraph, 1885 edition and translator identity/life dates checked.

These four English translations are old public-domain texts; the linked Gutenberg records identify public-domain status in the USA. The selected translators all died before 1956; no modern copyrighted translation, modern introduction or scholarly annotation has been embedded. This is not a universal rights guarantee for arbitrary material at linked sites. Source text pages include their own transcription credits and territorial/access caveats. No images, film clips or remote tracking embeds were added.

New definitions and reception descriptions are original short paraphrases. Their URLs and precise use notes are in the JSON: SEP Stoicism; Wikipedia patronage and elegiac couplet reference overviews; Bloomsbury's Anouilh description; Met object 436483; Sight and Sound's Inside Llewyn Davis review. The latter explicitly discusses Odyssey references in both Coen films; it is not a claim to have watched them in this task. Anouilh's publisher description is not an independent full critical reading. Community glossary sources are labelled as such.

Failed/unused leads: Poetry Foundation elegy and elegiac-couplet URLs returned errors; a Heidelberg patronage PDF was bot-blocked; an older BFI O Brother review timed out; IFI's O Brother page returned 404. None counted as consulted evidence. Gutenberg Buckley and Derby landing pages were inspected but not used for passage text. Reading trails reuse existing catalog/ranking context and original editorial assignments; they are not comprehensive histories, translations or new source-backed Top lists.

## Verification and manual handoff

Django system check and TypeScript/Vite build passed. Read-only authenticated checks returned 200 for the three routes and desk export; anonymous requests returned 403. Invalid filters and invalid desk updates returned 400. Trial query counts at check time: unread in 2+ rankings 1,776; unexplored authors/unread 8,454; at most 200 pages 26; short wishlist empty (an honest result from the real account, not populated for testing). All 13 steps had active books/list links. Content passage/module/glossary/source IDs validated.

In-memory-only note/exercise calls verified saved history, stale-edit rejection, export and preservation of existing state. No diagnostic notes were saved to the live database; private row counts stayed unchanged. No automated browser checks or test suites were run, per owner preference. PostgreSQL and valid browser-save flows remain untested.

Ask the owner to refresh and try: open a trail/book, combine discovery filters, switch Greek/Latin and translation, save/edit/export a real passage note, answer/save a comparison, follow a glossary link, and filter reception cards. Verify the phone column stack and keyboard controls in their browser. Starter sets are intentionally bounded: two passages, ten glossary terms and four reception branches; complete-text ingestion/custom passage management is not implemented.

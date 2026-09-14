# Ranking research queue

## Catalogue covers — active continuation, 14 September 2026

The current owner target is at least 3,000 additions from the 3,687 missing-cover snapshot. This run has so far moved the live catalogue from 8,508 works / 4,821 visible covers to **8,478 active works / 5,625 visible / 2,853 missing**: +804 valid covers, with 30 provably malformed reversed horror rows archived after their current ranking entries were rewired to existing correct covered works. New strict Open Library title-only, exact-duplicate, representative-series, Internet Archive and Wikipedia HTML/API fallbacks save accepted images and outcomes immediately. A frequency-ranked popular-first audit now precedes the long tail and has repaired many conspicuous omissions. Provider throttling and catalogue structure still dominate the queue: Google Books 429, Gutendex 403, Archive bulk timeouts, Wikipedia rate limits; roughly 353 unresolved records are standalone component works, and further reversed title/author imports remain. Continue the popular-first canonical-title pass, then rate-limited Wikipedia HTML and transient Open Library batches, map component works to containing editions, and repair affected intake families. Never count/attach author portraits or unrelated title-only images.

## New York Times readers' 21st-century Top 100 — imported 14 September 2026

**The New York Times · Readers' 100 Best Books of the 21st Century (2024)** is now a 100-entry revision-2 Published ranking, separate from the existing NYT expert survey. All positions 1–100 are retained. The primary interactive was blocked to automated access during this run, so its record is preserved as ineligible for row-level support; a previously saved complete transcription supplies the eligible row evidence. Artifacts and limitations are under `research/new-york-times-readers-best-books-21st-century-2024/`; consolidated audit: `research/_runs/2026-09-14/nyt-readers-2024/publication-audit.json`.

Catalog reconciliation reused 68 records and created 32 works plus 19 people. Edition, cover and genre enrichment for those new identities remains separate work. Do not merge this public-vote order with the NYT expert ranking or treat either as Marginalia's assessment. Pre-write backup: `manual-20260914T124228192437Z`; final checkpoint: `manual-20260914T124346180175Z`.

## Classical education owner Top 250 — 14 September 2026

**Classical education · Guide** is published at revision **2** with **250** entries, **311** retained target-local source records and **287** report-designated substantive sources. It appears only in the dedicated Classical education tab, alongside—but separate from—the private Paideia syllabus and study tools. Its original structured report, receipt, normalized ledger, candidate map, catalog input, selection payload and publication receipt are in `research/incoming/classical-education-guide/2026-09-14-owner-chat-attachment/` and `research/classical-education-guide/`.

The report’s P/R access classification is visible source-by-source: 24 metadata, duplicate or unverified records are deliberately uncounted. The 287 reported substantive consultations are not a fresh local rereading of all linked pages. Future work is direct verification, editions/covers and a separately argued reading-value order; retain the ranking separately from the private curriculum-progress state.

## Fantasy and science-fiction owner Top 150s — 14 September 2026

**Fantasy books · All time** (150 entries / 267 report-designated consulted sources) and **Science fiction · All time** (150 / 289) are published at revision **2** as separate Literature targets. They do not replace Science books, Horror, Manga or the Published r/Fantasy lists. Preserved originals, ledgers, candidate maps, catalog inputs and publication receipts live under `research/incoming/{books-fantasy-all-time,books-science-fiction-all-time}/2026-09-14-owner-chat-attachments/` and their matching target folders.

The reports’ stated source access/dependency limits are stored per source but have not been independently rechecked page-by-page during this file-driven import. Future work: direct evidence verification, edition/translation and cover enrichment, and separately argued reading-value orders; do not cross-credit either ledger to other science, fantasy or horror targets.

## Four owner-supplied genre/style Top 150s — 14 September 2026

Published at revision **2**: **Most beautifully written books · All time** (150 entries / 320 report-designated consulted sources), **Science books · All time** (150 / 270), **Biography & autobiography · All time** (150 / 277), and **Horror books · All time** (150 / 267). Each is a distinct curated target with its own preserved owner report, source ledger, candidate map, catalog input, selection payload and publication receipt under `research/incoming/{target}/2026-09-14-owner-chat-attachments/` and `research/{target}/`.

The reports' source-access, dependence and limitation notes appear in the app and are externally reported consultation metadata, not fresh source-by-source local verification. Their supplied orders are used in both views pending separately supported reading-value orders. Further work is direct source verification, exact edition/translation and media enrichment, and any owner-approved editorial revisions; do not cross-credit these ledgers to other targets.

## Catalogue cover enrichment — specialist manga pass — 14 September 2026

Latest cover continuation: **8,508 active works / 4,821 visible covers / 3,687 missing** after 182 additional verified covers. The public matcher now supports bounded ID ranges and transient-only retries, which recovered a high proportion of recent fantasy, science-fiction, science and biography failures. Further blind Open Library retrying is low yield; continue with publisher/national-library adapters and repair the reversed author/title intake families first.

Follow-on: concurrent imports expanded the catalogue to **8,476 active works**. The alias/initial/romanisation-aware bibliographic sweeps added **173 covers**, bringing the live total to **4,639 visible / 3,837 missing**. A fresh backup precedes the matcher change: `manual-20260914T115802567937Z`. The sweep also revealed reversed author/title records in some history and horror imports; these must be repaired from preserved intake files before their covers can be matched safely. A 309-record heuristic is only an audit pool because it includes genuine title/person-name coincidences; do not bulk-swap it.

The catalogue has **7,689 active works, 4,446 visible covers and 3,243 missing covers** at the latest checkpoint. Manga is now **814/881 covered (92.4%)**, up from 85/881: AniList supplied 685 strictly matched covers and Kitsu supplied 43 additional exact-title covers; 67 ambiguous/unmatched manga records remain for alternate-title/manual source review. MyAnimeList/Jikan was attempted but its API consistently returned HTTP 504 during this run. Don Quixote now has an attributed Project Gutenberg cover. An alias-aware comics pass added 11 covers and exact-identity reuse added four more. Existing covers were never overwritten.

The remaining general-book queue has already been attempted against Open Library; its latest 649-record tranche added 116 covers. Internet Archive is currently timing out and is not productive. The comics ranking is now 200/250 covered. Next cover work should use source-specific publisher, comics and national-library adapters rather than repeatedly rerunning exhausted providers. Durable logs are under `research/_runs/2026-09-14/catalog-manga-{anilist,kitsu,jikan}/` and the existing public/web cover ledgers. Pre-run backup: `manual-20260914T100726244870Z`.

## Asia Weekly, BookLive, Modern Library nonfiction and PBS — imported 14 September 2026

Four owner-approved lists are now Published rankings at revision 2: **Asia Weekly 20th-Century 100 Best Chinese Fictions** 100/100, **BookLive Readers’ Best 100 Novels** 99/100 verified, **Modern Library Board's 100 Best Nonfiction** 100/100, and **PBS The Great American Read** 100/100. Their reviewed rows, receipts, source ledgers and method notes are under the four matching `research/` target directories; consolidated audit: `research/_runs/2026-09-14/recommended-published-rankings/publication-audit.json`.

The BookLive poll is dated **2018**, per its official corporate method notice (1,835 respondents; 26 April–6 May 2018), rather than 2021. Position 92 is hidden for signed-out visitors on the current page and every located archived copy, so it remains an explicit one-row source gap. Ranks 93–100 retain their published numbers. Do not guess #92; fill it only from an accessible BookLive-authorized result or another trustworthy complete contemporary transcription. Edition, cover and genre enrichment for the 186 new catalog identities is a separate queue and must use safe identity evidence. Backups: `manual-20260914T093508463854Z`, final `manual-20260914T093719706287Z`.

## Top 3 books by country — initial grouped selection published — 14 September 2026

`books-every-country` is public at revision **2** with **208 sections / 624 local positions / 617 distinct works / 1,395 retained source records**. The page preserves report-region order, local 1–3 numbering and cross-country overlaps, with country filtering and section-specific confidence, language/form, affiliation and source-reference notes. It reused 207 catalog identities and created 410 works; 16 new collective/anonymous records remain authorless. The original, receipt, normalized ledger, country records, reconciliation and publication receipt are under `research/incoming/books-every-country/` and `research/books-every-country/`.

Research remains explicitly incomplete: only 12 supplied records say a page extract was checked and count as eligible; 1,383 search-returned-text/metadata records remain visible unverified leads. English titles do not establish purchasable English editions. Future work is targeted source qualification, English-availability/edition review and media enrichment, not repopulating the ranking.

## Manga 800 demographic rankings — four Top 200s published — 14 September 2026

All four demographic templates are now public at revision **2**: **Shōnen** 200 entries / 276 target-local sources; **Seinen** 200 / 253; **Shōjo** 200 / 273; and **Josei** 200 / 304. Original report copies, per-target ledgers, catalog batches and publication receipts are stored under `research/{incoming/,}manga-*-all-time/`. The report's supplied demographic order is visible in both views, with its explicit access limits and contested/mixed-category caveats preserved. Manga · All time remains separate and unchanged.

## Funniest books · All time — laughter-weighted revision published — 14 September 2026

**Funniest books · All time** is public at revision **3** with **150 entries / 354 retained target-local sources / 281 eligible**. The owner’s revised report is under `research/incoming/books-funniest-all-time/2026-09-14-laughter-70-revision/`; it retains the existing 150 works and 351 report documents while recalculating its order with laughter at 70% of the stated editorial weighting. All report URLs match the retained ledger; the report’s limited-access links remain displayed separately rather than being counted as eligible evidence. No fresh exhaustive source search or page-by-page local rereading was claimed. Editions, media and more granular entry review remain future work.

## Most addictive books and Most mainstream-loved books — owner Top 150s published — 14 September 2026

**Most addictive books · All time** is public at revision **2** with **150 entries / 281 retained target-local sources / 274 eligible**. **Most mainstream-loved books · All time** is public at revision **3** with **150 / 281 / 200**. Their preserved reports, source ledgers, candidate maps, catalog inputs and selection receipts are under `research/incoming/books-{addictive,mainstream-loved}-all-time/2026-09-14-owner-chat-attachments/` and `research/books-{addictive,mainstream-loved}-all-time/`. The source-access labels are supplied-report assertions, not a local rereading of every page; three narrow direct entry validations are recorded separately. Both current alternate views retain the supplied order pending separately reasoned alternatives. Editions, media and finer evidence review remain future work.

## Books · Chinese-language tradition — audited Top 100 revision published — 14 September 2026

**Books · Chinese-language tradition** is now public at revision **3** with **100 entries / 245 retained target-local sources / 147 eligible**. The owner report is preserved in `research/incoming/books-china/2026-09-14-owner-chat-audited-revision/`; revised sources, catalog reconciliation, anonymous-corpus receipt and publication receipt are in `research/books-china/`. It retains 244 supplied audited records (30 earlier directly-read plus 116 directly inspected additions eligible) and one direct MCLC entry-validation review. Earlier revisions, sources and catalog identities remain preserved. A separately reasoned reading-value order, editions and media are still future work.

## Benjamin McEvoy TIME/Goodreads Top 50 — completed 14 September 2026

The owner-linked YouTube video is imported as a distinct 50-entry revision-2 Published ranking: **Benjamin McEvoy · TIME novels by Goodreads reception (Top 50)**. It preserves every explicitly announced rank and reuses all 50 established work identities from TIME's separate unranked 100-novel Reading collection. No catalog or private records were created or changed.

The video describes a reverse ranking based on Goodreads readership/number of ratings and rating levels. It is not TIME's original alphabetical order, an objective literary ranking, or McEvoy's personal ordering. Because the source provides neither a reproducible formula/data snapshot nor a complete enumeration of ranks 51–100, only the fully spoken top 50 is published. The video's 1923–2010 wording conflicts with TIME's actual 1923–2005 scope and is recorded as a limitation. Artifacts are under `research/mcevoy-time-novels-goodreads-top-50/`; consolidated audit: `research/_runs/2026-09-14/mcevoy-time-goodreads-top-50/publication-audit.json`.

## Books · Scotland — Top 50 published after focused source qualification — 14 September 2026

**Books · Scotland** is now a public revision-2 selection with **50 entries / 270 retained target-local sources / 50 eligible**. The owner report’s source pool originally used prospective wording, so 220 sources remain uncounted leads. A direct 50-source qualification subset covers Scottish literary institutions, scholarship, poetry/corpus material, prize records, published-list reporting and editorial sources. The supplied Top 50 is visible in both app views pending a separately argued reading-value order. Raw report, qualification ledger, source-ID receipt, catalog inputs, selection and publication receipt are in `research/incoming/books-scotland/` and `research/books-scotland/`.

## Japan and Poland audited country-ranking revisions — completed 14 September 2026

**Books · Japan** now has a revised public Top 100 at revision 3 and **259 retained target-local sources / 153 eligible**. **Books · Poland** now has a revised public Top 100 at revision 4 and **241 / 149**. Both supplied reports retain the old source identifiers, add audited references and record the access limits that determine eligible counts. Their original reports, receipts, revised ledgers, candidate maps, catalog inputs and publication receipts live under `research/incoming/books-{japan,poland}/2026-09-14-owner-chat-audited-revision/` and `research/books-{japan,poland}/`.

Japan's C/B records and Poland's TEXT/ABSTRACT records are stored as eligible reported consultations; all other audit-status records remain retained but uncounted. The reports' new placement order is shown in both app views pending a distinct reading-value argument. Japan retains three and Poland one collective/anonymous work without inventing authors. Earlier revisions remain preserved; no personal scores, criteria or overrides were changed.

## Most important literary works · All time — owner-supplied global Top 250 — completed 14 September 2026

Published as a public revision-2 initial selection: **250 entries / 611 eligible target-local sources**. The report's broad cross-form scope includes books, collections, essays, short stories, poems and plays across global literary traditions. Its supplied historical-literary-importance order is retained in both app views because no separately reasoned reading-value order was provided.

The raw report, SHA-256 receipt, source ledger, candidate map, catalog inputs and publication receipts are under `research/incoming/other-works-all-time/` and `research/other-works-all-time/`. Its source-access claims are recorded as externally reported bibliography metadata, rather than as local source-by-source rereading. Fifteen collective or anonymous works remain authorless by design; editions, media, direct source verification and a distinct reading-value order are future work.

## OCLC and TIME external lists — completed 14 September 2026

Fully imported at revision 2: **OCLC · The Library 100** as a 100-entry Published ranking with exact WorldCat holdings positions; **TIME · 100 Best Novels (1923–2005)** as a 100-entry unranked Reading collection; and **TIME · 100 Best Mystery and Thriller Books (2023)** as a 100-entry unranked Reading collection. TIME's alphabetical and chronological display sequences are not represented as merit ranks, so all 200 TIME `source_rank` values are null. Target-local evidence ledgers, reviewed rows, payloads, receipts and limitations are under `research/{oclc-library-100,time-100-best-novels-2005,time-100-mystery-thriller-books-2023}/`; consolidated audit: `research/_runs/2026-09-14/oclc-time-collections/publication-audit.json`.

Catalog reconciliation reused 202 identities and created 98 works plus 80 people. A safe Open Library pass produced 92 exact title/author matches, with 4 ambiguous and 2 no-safe-match outcomes retained for later manual enrichment; it added 7 covers, 58 provider-sourced years, 32 summaries and 61 genre links. Missing covers are a metadata queue, not missing list membership.

## Empty owner-requested templates — 14 September 2026

This historical template note is superseded by the later published reports above. Do not treat **Funniest books · All time** as empty or start a new source-gathering run merely because the initial template record once existed.

## Comics and graphic novels · All time — owner-supplied worldwide Top 250 — 14 September 2026

Published as a public revision-2 initial selection: **250 entries / 827 eligible target-local sources**. It covers comics, graphic novels, manga, manhwa, manhua, comic strips and wordless novels, while keeping the existing **Manga · All time** ranking distinct and unchanged. The supplied order is retained in both app views because no independent reading-value ordering was provided.

The original report, receipt, source ledger, prior metadata snapshot, candidate map, catalog batch and publication receipts are in `research/incoming/comics-graphic-novels-all-time/` and `research/comics-graphic-novels-all-time/`. The report claims 599 non-encyclopedic and 228 bibliographic/encyclopedic references over 237 hosts; its persisted access labels are 536 retrieved-page records, 54 excerpt records and 237 contextual/bibliographic records. Those are externally reported consultations, not a local rereading of every cited page. It explicitly records thinner coverage for African, Arabic, South Asian and digital-first Asian traditions. Editions, covers, direct source verification and a separately reasoned reading-value order remain future work.

## Arabic, Russian and Caribbean literature intake — 13 September 2026

Published from owner-supplied cross-source reports: **Books · Arabic tradition** 98 entries / 207 eligible sources; **Books · Russian literary tradition** 99 / 220; **Books · Caribbean** 50 / 225, all revision 2. Each retains its report order in both views and stores target-local sources. Arabic’s two and Russian’s one collective/anonymous works remain explicit unresolved candidates, not invented author records. The supplied bibliographies’ access claims are externally reported; editions, covers, direct verification and separately reasoned reading-value orders remain future work.

## Manga · All time — owner-supplied international Top 250 — 13 September 2026

Published as a revision-2 initial selection: **250 entries / 596 eligible target-local sources**. The raw report, normalized source ledger, candidate map, catalog import and selection receipts are in `research/incoming/manga-all-time/` and `research/manga-all-time/`. It includes series, short manga, autobiographies, strips and expressly named connected sequences; Korean manhwa, Chinese manhua, prose light novels and anime are outside its recorded scope. Creator credits, editorial rationales, demographic/audience labels, themes and source references are preserved per entry.

The supplied report records 162 full-text, 408 excerpt and 26 metadata-only consultations across 12 source languages. These are externally reported access claims, not newly performed local source-by-source verification; the limitation is persisted in the app. Both displayed orders retain the supplied editorial order. English editions/covers, deeper candidate-level verification and a separately reasoned reading-value order remain future work.

## Reddit, 4chan and established published rankings — expanded 13 September 2026

The Published rankings section now holds the first community batch unchanged — r/TrueLit 2023 (100), r/classicliterature 2025 (100), r/Fantasy 2023 (266), r/printSF 2023 (115), 4chan /lit/ 2025 (100), and the /lit/ 2014–2024 decade transcription (100) — plus 26 new revision-2 lists / 3,005 active entries. The new community coverage is r/TrueLit 2019–2022 and 2024–2025; r/Fantasy 2014, 2015, 2017, 2019, 2021 and 2025; and /lit/ every year 2014–2021 plus 2023–2024. Exact source ranks/ties, vote cutoffs and source-defined series/composite entries are retained. The 2021 r/Fantasy sheet's acknowledged lower duplicate was excluded without renumbering later source ranks. The 2025 r/TrueLit Hall of Fame is not silently mixed into its Top 100.

The four previously prioritized institutional/public lists are also complete: Modern Library Board 1998 (100), New York Times critics/expert survey 2024 (100), BBC Big Read 2003 (200), and Le Monde/Fnac 1999 (100). These are external lists, not Marginalia assessments; criteria, weights and personal scores remain empty. Their 34 target-local source records distinguish original publications from transcription mirrors. Edition/cover enrichment for the newly created catalog identities is separate and must use exact title-and-author evidence.

Known gap: do not publish a /lit/ 2022 Top 100 unless a stable final result image/table is recovered. The located thread was affected by spam and disputed counting; the annual archive's general claim that lists exist is not row-level evidence. Preserve the existing 2025 poll and decade aggregate independently.

High-value Asian follow-ups still awaiting owner authorization: *Literary Thought*'s **100 Korean Masterpiece Novels** expert poll (2004, 145 writers/critics/professors, with ties); the Korean Creative Writing Society/*Literary People* **100 Novels of the Twentieth Century** survey (2002, 109 literature professionals); and *Shūkan Bunshun*'s 1985 **100 Best Mystery Novels** as a genre ranking. The Asia Weekly and BookLive lists are now imported above. The Asahi millennium vote ranks Japanese literary figures rather than books and belongs with person rankings. Iwanami's 1974 *100 Books* is a selection, so classify it as a Reading collection unless its source establishes ordinal merit positions.

Other Western follow-ups still worth considering: Modern Library's reader Top 100 and the Bokklubben World Library. The New York Times reader companion, PBS's Great American Read and Modern Library's nonfiction board list are now imported above. Bokklubben is an unranked selection and must remain a Reading collection unless a source supplies real positions. TIME's 100 English-language novels is already imported with that distinction preserved.

## England, Ireland, Scotland and essays report intake — 13 September 2026

Published as initial revision-2 selections: **Books · England** (100 entries / 167 eligible sources / 247 retained source records), **Books · Ireland** (49 / 131 / 239), and **Essays · All time** (100 / 224 / 225). Their two visible app views retain the owner-supplied synthesis order because no separate reading-value order was supplied. The reports preserve corpus-level reported consultation rather than candidate-level citations; editions, media, direct verification and independently reasoned reading order remain outstanding. Ireland's collectively attributed *Táin Bó Cúailnge* remains unresolved rather than receiving an invented person.

**Books · Scotland** has 50 reconciled catalogue candidates and 270 retained source leads, but remains unpublished. The attached report calls them sources it *would use* to cross-check the list, not consulted sources, so they are intentionally unverified/uneligible. Qualify a sufficiently relevant Scotland-specific subset only if the owner asks for that verification work. The concurrently supplied Chinese-language report and the duplicate England attachment were exact duplicate deliveries and caused no duplicate writes.

## Social History and philosophy-topic report intake — 13 September 2026

Published as revision-2 initial selections: **Social history · Books** (50 entries / 123 eligible sources; 243 total retained records) and **Philosophy of mathematics · Works** (20 / 132). Both preserve the supplied order in both views and require direct verification, candidate-level citations, editions/images, and an independently reasoned reading-value view.

**Philosophy of language · Works** is now published as a 20-entry revision-2 initial selection after independently qualifying 53 relevant sources from the 135 preserved URLs. The other 82 remain explicitly unverified leads. The report order is retained in both views; candidate-level evidence, editions/images, and a separate reading-value order remain future work.

## Catalogue media/details enrichment — 13 September 2026

Open Library exact-match enrichment completed for the current catalogue: 289 covers from 1,975 distinct attempts, including a late-arrival catch-up. A later canonical-record pass for recent History/London/World History and philosophy additions added 49 more safe covers. The visible default-cover count rose **840 → 1,182**. Database/API audit confirms every stored cover is on the `default_edition` returned to and rendered by the app; no cover is present but invisible. Ambiguous records were deliberately skipped; exact records with no provider cover, anonymous works and recoverable provider failures remain queued for a reviewed publisher/web-search fallback. Metadata is deliberately limited to missing original years/descriptions from exact work records; publisher/ISBN/pages are not claimed as edition-specific. Google Books returned unauthenticated HTTP 429 and Goodreads is not a reliable metadata API. Source cache, results and preservation audits: `research/_runs/2026-09-13/new-catalog-openlibrary/` and `research/_runs/2026-09-13/new-catalog-openlibrary-canonical/`. Do not treat no-match as a rejected work or attach a title-only cover. Latest pre-write backup: `manual-20260913T202911489216Z`.

Catalogue presentation now tells the owner both the current page and total page count, so all 4,367 active works are discoverable through the existing search/filters/Next control rather than being mistaken for the first 24-card page. TypeScript/Vite build and Django system check passed; final checkpoint: `manual-20260913T203436673989Z`. Browser validation remains with the owner.

## Full catalogue cover request — active, 13 September 2026

Owner requested covers for all 4,367 works via public APIs, then a sourced online fallback. The run is partial: `research/enrich_catalog_covers_public.py` retained **831** unique outcomes and attached **207** exact title-and-author matches, increasing visible default-edition covers 1,182 → **1,389**. **3,159** works still have no visible cover. Open Library and Internet Archive outcomes are incremental in `research/_runs/2026-09-13/catalog-public-cover-fallback/outcomes.jsonl`. Google Books has unauthenticated 429 responses; Open Library works at controlled six-worker batches after rate-limit recovery; Internet Archive remains timeout-prone; a direct generic image-search test returned unrelated images and was rejected. Resume controlled Open Library batches, then perform reviewed publisher/source-page lookups for remaining works. Never attach title-only thumbnails or overwrite verified covers. Backup `manual-20260913T220123501394Z`.

Continuation checkpoint: a persistent controlled-rate run has now processed at least 3,755 unique outcomes / 1,272 exact fallback covers. Concurrent imports expanded the live catalogue to 5,810 works; latest known visible cover count is 2,454, with 3,356 still uncovered. The append-only run is active. The final web-source fallback must target saved no-safe-cover/error rows, not rerun already covered works.

## London and World History report intake — 13 September 2026

Two new owner-chat attachments are now published as revision-2 initial selections: **History of London · Books** has 50 entries and 266 target-local, externally reported source records; **World history · Books** has 150 entries and 228. Their originals, hashes, ledgers, candidate maps, catalog batches and publication receipts are retained in their target folders. The reports’ corpus-level source claims are preserved with explicit limitations; direct source verification, candidate-level mappings, English editions/media, and separate reading-value orders remain future work.

## Full owner-report reconciliation — 13 September 2026

All 29 preserved owner-report targets now have active entries in the live research-ranking API. The final omissions were published as Ancient works 130/221, Plays 149/266, and Medieval history 50/137 (entries/eligible sources), each at revision 2. Ancient retains 20 anonymous/composite candidates and Plays retains *Everyman* as explicit unresolved records; no authors were invented. See each target’s `INTAKE.md` and the processing log.

## Named collections repaired — 13 September 2026

Saved: McEvoy suggested programme 101 entries/rev5; favourites 11/rev4; lecture catalogue 152/rev3; Great Books **1990** 384/rev3 across all 60 volumes. Annual club reading collections added: 2021=14, 2022=28, 2023=45, 2024=33, 2025=19. Current 2026 schedule expanded to23 named assignments. Annual counts include supporting works, not only main novels; these are reading sequences, not merit rankings. Source-order and identity audits passed; previous entries/revisions and private records preserved. Sources and full provenance are saved in `research/_runs/2026-09-13/collection-repair/` and each target's `sources.json`/`RESEARCH.md`.

Remaining: 2021 is a partial public-header reconstruction; public sitemap stops February 2022, so January coverage is incomplete. Original member-only syllabi were not read. 2026's secret Dickens novel is still unnamed. Obtain original assignments if supplied, and enrich new catalog editions/images. Do not re-run historical span-based McEvoy or title-only matching scripts; they caused author/identity errors. Named-list imports do not require 50 independent quality sources.

## Latest five-target publication — 13 September 2026

Saved in the app: all books 250 (rev4), philosophy books 250 (rev4), nonfiction 250 (rev6), history 234 (rev2), poetry 162 (rev2). Both orders and target-local source links are present. All 959 supplied references/925 distinct URLs were attempted, with cached content and failures retained. Full artifacts and source coverage audit: `research/_runs/2026-09-13/supplied-corpus/`.

Next refine the initial history/poetry pools toward 250 with broader non-English and scholarly selections, strengthen candidate-level evidence, and review uncertain title/translation matches. Existing automatic consulted counts overstate substantive review: HTTP success/text length is not consultation. The current entry-linked source counts are 132 all-books, 100 philosophy, 63 nonfiction, 33 history and 38 poetry, including retained earlier evidence. Research remains partial; no numerical personal criteria or scores were invented. New catalog editions and images remain pending.

## Country-ranking intake checkpoint — 13 September 2026

Owner-supplied Top 100 syntheses are now published as initial revision-2 selections: Japan 98 entries / 132 externally reported source records; Chinese-language tradition 97 / 128; Poland 100 / 125; France 100 / 130. See each target's `research/books-*/RESEARCH.md`. The stable `books-china` slug has an explicit China/Hong Kong/Taiwan Chinese-language scope; Poland is now an initialized country target. Five collective-attribution works are retained as unresolved, not represented with invented people. All four require direct source verification, candidate-level evidence maps, English-edition and image enrichment, and a separately reasoned reading-value order.

## Population checkpoint — 13 September 2026, broad expansion

**Saved in the existing database: books-all-time 250 entries, revision 3; literature-all-time 250 entries, revision 3.** Both editorial orders preserved. All original entry identities, source ranks/assessments and historical revisions retained. Catalog now 423 works; only the original 14 have verified editions/covers, so new metadata and portraits are explicitly pending. This supersedes the old tiny-selection counts below. Nonfiction/philosophy expansion is next in the active run.

423-candidate factual compilation, source tables, exclusions and review TSVs: `research/_runs/2026-09-13/compilation/`. Publication inputs/receipts: each target's `expanded-selection-v3.json`. Catalog expansion batches 01–05 imported. Evidence batch 33 imported: A215/L99/N118/B98/P99; 629 target-source records, no new global source identity. New source ID remains R202, next batch34. Backup before changes: manual-20260913T123644525950Z. Do not run the historical refresh_checkpoint.py unchanged.


**Latest owner correction, 13 September:** prioritize approximately **250 entries per broad all-time ranking**, compiled quickly from established published lists and the existing evidence, then iterate. The current tiny app selections are inadequate coverage, not finished global rankings. Read [the corrected workflow](RANKING_RESEARCH_WORKFLOW.md). Keep both orderings and the picture requirement, but batch image/edition enrichment separately from comparative candidate inclusion.

All five current targets already exceed the earlier 50-source floor. Additional sources should resolve specific gaps; 100–200 sources is not a publication prerequisite. Count only actually consulted material, preserve diversity and target-specific relevance, and save/import progress continually.

Criteria and weights remain to be designed per ranking. The owner requested actual draft rankings and chose **both critical standing/enduring influence and reading value today**. [Five two-lens pilot comparisons](../research/RANKING_DRAFTS.md) now order 25 candidates each with evidence links and caveats. The v1 files are historical proposals, not completed worldwide Top 25s. Current illustrated v2 selections are linked from the ranking index. Final criterion values and personalized positions stay unset. Publisher source positions remain separate; Penguin’s numbered classics selection is explicitly unordered.

| Target | Intended length | State |
| --- | --- | --- |
| Books · All time | Approximately 250 | 215 eligible sources; 14 illustrated app entries, both orders, revision 2; expansion incomplete |
| Literary fiction · All time | Approximately 250 | 99 eligible sources; 8 illustrated app entries, both orders, revision 2; expansion incomplete |
| Nonfiction · All time | Approximately 250 | 117 eligible sources; 6 illustrated app entries, both orders, revision 2; expansion incomplete |
| Philosophy books · All time | Approximately 250 | 97 eligible sources; 4 illustrated app entries, both orders, revision 2; expansion incomplete |
| Philosophers · All time | Approximately 250 | 99 eligible sources; 23 illustrated app entries, both orders, revision 2; expansion incomplete |
| Most important literary works, all time | 100–200 with form filters | Queued; cross-form literary importance, distinct from the individual poetry, plays, essays and short-story rankings. |
| Short stories, essays, and poems separately | 100–200 where justified | Short stories published: 150 entries / 227 target-local sources, revision 2; essays remain queued; retain the single Poetry ranking |
| Books by major country/literary tradition | 100–200 where justified | Queued; one target per country |
| Books by century | 100–200 where justified | Removed/archived at owner request; do not recreate without new authorization |
| BCE works | Variable, up to broad-list range | Queued as an initial navigation grouping |
| Major philosophy topics: epistemology, metaphysics, ethics, political philosophy, aesthetics, logic, mind, language, science | Approximately 100 per major topic | Epistemology published: 100 entries / 163 sources, revision 2. Ethics published: 98 / 138, revision 2 (two collective candidates unresolved). Political philosophy published: 50 / 133, revision 2. Metaphysics published: 100 / 153, revision 2. Philosophy of mind published: 50 / 153, revision 2. Philosophy of science published: 50 / 120, revision 2. All have explicit mixed book/essay scope where report-supported; Aesthetics remains archived |
| Narrow philosophy topics, including philosophy of mathematics | Approximately 10 initially, adjustable | Queued; one target per topic |
| Genres, styles, eras, and custom themes/tags | 50–100 where justified | On-demand targets |
| An author's books / all eligible works | Usually 10–15 | On-demand targets |
| Top 3 books by country | 3 per country/section | Initial selection published: 208 sections, 624 positions, 617 distinct works; direct source qualification and edition/media enrichment remain |

Current country priorities explicitly named: England, Ireland, United States, Germany, France, Poland, China and Japan. Further countries can be added without schema changes. Do not treat this starting set as the complete set of major traditions.

Immediate synthesis work: extract full relevant published lists into a broad candidate pool, normalize works/authors in batches, check major omissions, and compile the two orderings. Ulysses and The Brothers Karamazov must be considered before treating The Doll's subset position as an all-time placement. Keep all-subject books genuinely cross-subject and philosophy worldwide. Reuse the existing source register; defer long dossiers and marginal source gathering until broad usable rankings are delivered. Catalog/image and safe revision-update work should enable population, not constrain merit selection. Actual current catalog remains 14 works, 34 people and 55 entries until the next database import.

The bootstrap command creates empty database definitions for these initial country scopes, the broad/form scopes, centuries 1–21 and BCE, major philosophy topics (books and philosophers), mathematics, the world reading collection and named external collections. Each has its own stable slug and source relationships. Author-specific and custom-tag rankings are created as requested. The 51-source survey supplies no automatic source credit to these other rankings. A source about an unrelated subject does not count merely because it shares a domain or platform with useful material.

Save each consulted batch to its target ledger and import it with `manage.py import_research <file> --target <slug>`. Preserve `updated_at`, completed-research dates and source-check dates as distinct concepts. A partial batch or metadata edit never makes a ranking appear freshly researched; see [ranking freshness](RANKING_FRESHNESS.md).

Country membership follows a documented literary/cultural association and may be multiple. Keep England and the UK distinct. Separate country, original language, setting, and historical polity; do not derive one blindly from another. The every-country ranking stores its 208 explicit sections and cross-country placements on the ranking entries; its source-access and English-edition gaps remain tracked. Separately researched countries each need their own corpus with 50 as the hard minimum and many, many more sources as the desired breadth. A world overview cannot supply 50 loosely related sources to every country automatically.

English availability is an eligibility requirement for recommendations now. Works from any original language or country may qualify when an English translation exists. For first-pass ranking inclusion, establish English availability from a reliable bibliographic or list source. Verify specific reading editions and printing details in the enrichment pass; an English title alone is not proof. When availability cannot be verified, retain the candidate as unresolved rather than claiming the country has no literature.

Use original composition/publication dates for historical scopes, not the English translation date. Record uncertain dates/ranges. BCE is an initial grouping, not a claim that few ancient works survive. Century filters must use documented boundaries and handle no year zero. Distinguish the 1900–1909 decade from the twentieth century.

List sizes are targets, not permission to pad. If an author has fewer than ten eligible books, show the complete eligible set and its count. An author with three books must not gain invented titles or have individual essays inserted into a books-only list. Topic-specific depth and the availability of evidence determine whether a target of 50 or 100 is defensible.

Books-only rankings contain complete book-length works, with literary fiction and nonfiction available separately. All-works and other-works rankings can include individually identifiable stories, essays, poems, and other supported forms. Record collections and their contents separately so a collected edition and an individual story do not become accidental duplicates. Mixed-form eligibility is always explicit in the scope.

Translations deserve their own recommendation records: translator, edition, complete/abridged status, readability, style/fidelity tradeoffs, notes/apparatus, and sources. Consult translators, scholars, reviewers, forums, reader discussions, and Benjamin McEvoy's recommendations. A standalone requested translation-comparison research target carries the same hard minimum of 50 sources and the same explicit aim of many, many more than 50.
# Owner-pasted source universes — 13 September 2026

Preserved, reconciled and displayed in the app: all books 200 URLs (196 new leads, 4 existing matches), philosophy 159 (158/1), history 200 (200/0), poetry 200 (200/0), nonfiction 200 (196/4). The 950 new records are explicitly `Discovery lead`, so they do not inflate consulted counts; all previous sources remain. Promote useful records in small reviewed/imported batches while retaining their owner provenance, then revise rankings without waiting for every lead.

First reviewed batch imported: books +10 consulted, philosophy +10, history +9, poetry +9, nonfiction +8. These are excerpt-level page reviews with limitations recorded in each source metadata and batch receipts; continue with deeper list-content review before using positions for ranking revisions.

Full owner-lead URL/content validation is now persisted: books 369 consulted, philosophy 235, history 155, poetry 177, nonfiction 290. The remaining supplied pages remain visible as discovery leads with validation failure/insubstantial-content metadata. These counts establish accessible source evidence, not exhaustive reading of every list or final ranking criteria.

Named-list extraction is complete: Guardian critics 100/100, Guardian readers 100/100, McEvoy reading list 103/103 and McEvoy favourites 7/7. Next review the supplied universes in owner order: all books, philosophy, history, poetry, nonfiction, promoting useful leads in small batches and using their lists to iterate the rankings. History and poetry definitions exist; their synthesis remains unresearched/unpopulated.

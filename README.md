# Marginalia — humanities rankings

A local first version of the humanities reading and rankings app, built with Django, React and TypeScript. “Marginalia” is a working name. A fresh setup creates 75 ranking/collection definitions, including 13 empty manga templates ready for later research and publication. The existing workspace contains populated researched rankings and external collections; personal numerical scores remain unset. See [current database counts](docs/CURRENT_STATE.md) and [HANDOVER.md](HANDOVER.md) for saved state. The owner has requested approximately 250-entry broad rankings using a faster compilation-and-refinement workflow; see [the current instructions](docs/RANKING_RESEARCH_WORKFLOW.md).

## Launch locally

**Search anything…** in the top bar (Cmd/Ctrl+K) finds books, authors, rankings, collections, sources and accessible study pages in separate groups. The catalog supports multiple included/excluded subjects, genres, forms and countries, with counts showing the total after each click. **Select books → Export bibliography** copies or downloads plain references, RIS or BibTeX using recorded edition details. See [the search, filters and bibliography walkthrough](docs/SEARCH_FILTERS_BIBLIOGRAPHY_2026_09_30.md).

**Select books** in the catalog, ranking/collection pages or My Library to add a batch to your library, Read next or a private book list; library selections also support adding shelves and private tags. Image previews are prepared after ingestion, and hovering/focusing navigation links preloads their destination. See [the selected speed and bulk-action changes](docs/SPEED_AND_BULK_ACTIONS_2026_09_30.md).

**Atlas & timeline** explores the saved catalog by place and century, with private saved/read overlays. **Published rankings → Compare published lists** shows shared/unique choices and original publisher positions side by side. Both are read-only; unknown metadata remains explicit. See [behavior and walkthrough](docs/ATLAS_AND_PUBLISHED_COMPARISON_2026_09_29.md).

The [seven application improvements](docs/APP_IMPROVEMENTS_2026_09_28.md) add **Today** with an optional home setting, explicit monthly reading totals and previewed carryover, an edition/save/Read next/plan workflow on book pages, reusable private discovery filters, side-by-side ranking perspectives, a separate staff **Catalog review** queue, and complete private JSON/ZIP exports from Profile. Normal shared-ranking detail pages now fetch 24 entries at a time. Migration 0016 preserves existing account/reading data and shared records; these features do not perform new ranking research.

**Reading trails** connects existing books in three editorial study sequences, separate from merit rankings. **Discover for me** adds personal unread/multiple-rankings, short-wishlist and unexplored-author filters. Classical education now has a **Reading desk**, **Translation lab**, expanded linked **Context & glossary**, and evidence-labelled **Reception trails**. The desk starts with two Greek/Latin passage units and four credited older translations, with private revisioned notes/answers and text export; it is not a complete-text library. See [scope and provenance](research/classical-reading-desk/README.md).

New discovery/study tools: **Source explorer** in the sidebar searches existing source registers and shows exact-URL reuse without merging target-specific evidence. Book pages have a compact **Across the rankings** profile, keeping list types and country-local placements separate. Classical education opens on **Today’s study**, with **Recall & review**, a sourced **Historical atlas**, and a private **Essay workshop** with evidence snapshots, saved revisions and text export. These features preserve book/module completion and shared rankings; see `research/classical-learning/README.md` for access and verification limits.

Classical education now includes **Start here**, **Works & preparation**, **My classical plan**, **Context & glossary**, **Connections**, **Commonplace book**, **Courses & materials**, and **Listening guide**. It connects the existing Top 250 to the syllabus, offers university study resources and History of Philosophy without any gaps episode pairings, and keeps personal progress/notes private. Classical planner additions are preview-first and distinguish selected passages from whole-book completion. The syllabus export includes saved notes and resource references. See `research/classical-education-companion/README.md` for access limits and manual checks.

Newest library tools: **Read next** provides a saved, reorderable shortlist with preview-before-append to the monthly plan. **Shelves & tags** on each book lets you organise private categories such as Own a copy or Book club. **Goals & years** shows annual completions (including rereads), unique books and optional book/page goals. Pages are counted in completed books by finish year, not as daily reading sessions. Manga is available in catalog and list categories. Collection overviews use lighter queries/responses; normal detail pages load 24 entries at a time and defer sources/history until requested. Specialized grouped, personal and weighted views retain their separate rendering paths.

Latest development: books and manga share a controlled genre/category taxonomy, kept separate from private shelves and tags. Genre filters are available in the catalog, ranking/collection entries, shared lists, My Library, Read next, and collection overlap. My Library also supports rating filters/sorting, reading dates and preserved reread attempts. Book pages provide quick ratings and reading history. Catalog/author browsing uses server-side search with pagination. Registration/email recovery and deployment infrastructure are prepared; see [public-release preparation and transfer instructions](docs/PUBLIC_RELEASE.md). The local database remains SQLite. Public services have not been deployed.

My Library also includes **Reading insights** (finished books, rereads, monthly trends, favourite authors and rating distribution) and **Collection overlap** (books appearing in multiple shared lists, with already-read filters). A compact row of ten stars appears on library rows, book pages and signed-in ranking/collection book entries, with one score label and no highlighted panel. Click a star to save your private rating automatically.

The fastest launch in the prepared workspace is:

```bash
./scripts/run_local.sh
```

Open **http://127.0.0.1:8000/**, or **http://127.0.0.1:8001/** when launched with `PORT=8001 ./scripts/run_local.sh`. Sign in with your existing account. Only a new database shows the first-run account screen; that initial account can maintain the catalog and access **http://127.0.0.1:8000/admin/**. Stop the server with Ctrl+C; your data stays in `data/db.sqlite3` and uploaded images stay in `media/`.

For a fresh checkout, install Python 3.11+ and Node.js 24 with npm, then run:

```bash
./scripts/setup_local.sh
./scripts/run_local.sh
```

Setup installs the pinned Python dependencies, builds the frontend using its lockfile, applies migrations, creates missing empty definitions, imports the saved research, and collects static files. Repeating it preserves existing ranking edits and existing source notes. If `.node/bin/node` exists, the scripts use that project-local Node installation.

The repository also includes the owner-authorized **5 October cover snapshot**: 6,633 downloaded originals under `media/covers/`, with public book/edition associations, original source fields, credits and SHA-256 checksums in [the catalog media manifest](media/catalog-manifest.json). A normal Git clone retrieves the images. The manifest records 51 unreferenced historical downloads without inventing book matches, and flags 14 known placeholder files (13 catalog associations) separately. Raster validation does not establish edition identity or licensing beyond the recorded source metadata.

This image snapshot does not export accounts, private reading records or the database, and does not automatically populate database image fields. Original media paths and catalog IDs are recorded for reconciliation; a different database must also match book/author identities before applying them. Portraits are not included in this covers-only publication. To refresh the public manifest without changing catalog records or originals:

```bash
.venv/bin/python manage.py export_catalog_media_manifest --output media/catalog-manifest.json
```

The command reports missing, corrupt or unsafe references and exits unsuccessfully when the snapshot is incomplete. It can include portraits with `--include-portraits` when deliberately publishing those too. New media remain ignored by default; review and stage only the manifest's image paths for a later publication. The current background enrichment worker does not automatically push future downloads.

This convenience workflow deliberately uses SQLite because Docker is unavailable in the current workspace. PostgreSQL remains the intended shared and hosted database. Moving existing SQLite data to PostgreSQL is a separate data migration; changing a database setting alone does not move your library.

## Docker with PostgreSQL

With Docker Desktop/Engine and Compose installed:

```bash
docker compose up --build
```

Compose runs PostgreSQL 17, builds the React assets, migrates Django and starts Gunicorn. Startup does not bootstrap or import content. Create the administrative account with `docker compose exec app python manage.py createsuperuser`; use the deliberate transfer workflow in [PUBLIC_RELEASE.md](docs/PUBLIC_RELEASE.md) to move existing data. The PostgreSQL and media volumes persist when containers stop. `docker compose down` preserves those volumes; do not add `--volumes` unless you intend to delete the stored database and images. The host port is bound to loopback for local use.

Compose reads optional overrides from `.env`; `.env.example` shows the supported local values. Plain Django commands read exported environment variables and do not automatically load `.env`. A host-run backend uses PostgreSQL when `POSTGRES_HOST`, `POSTGRES_PASSWORD`, and optionally `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PORT` are exported.

**Docker configuration has not been executed in this workspace because Docker is not installed.** The direct local workflow and SQLite-backed application are the validated launch route.

## What this version provides

- Ranking and collection browsing, bookmarks, personal copies/lists, revision history, explicit list sharing, and separate private user preferences.
- Main ranking pages are read-only: agents populate them from relevant online research. Bookmarked views offer private scoring preferences and personal copies; shared entries and source order stay intact.
- Navigation separates **Researched rankings** (multi-source synthesis), **Published rankings** (e.g. Guardian, original ordering), and **Reading collections** (e.g. McEvoy and Great Books, unranked or reading sequence). The database stores each item's origin and presentation explicitly.
- Database-backed source ledgers per ranking, source counts, update/research dates, refresh intervals and saved refresh requests.
- A catalog with people, works, English editions/translations, forms, topics and indexed shared genre/category assignments; local cover and portrait uploads with attribution fields.
- A dedicated Top 3 books by country view with local 1–3 numbering, country filtering and explicit cross-country literary affiliations, kept separate from standalone country rankings.
- A personal library with reading statuses, page progress, private 1–10-star ratings and notes; monthly plans with per-month add buttons and a Python planner using weekly/monthly or per-reading-day targets, flexible reading days, effort/density adjustments, and locked allocations.
- Approximate reading hours based on length, reader pace and reading difficulty, with the uncalibrated algorithm and its assumptions exposed.
- Criterion/weight and assessment plumbing with score breakdowns and personal overrides; scores remain absent until real criteria and assessments are supplied.
- A responsive interface with light, dark and system themes, a scrollable sidebar, compact expandable planner settings, and Django administration for content maintenance.
- Shared-data deletion guards at API/admin, ORM and database layers; reversible archives, local backups, and a terminal password-reset helper.

The existing database has populated rankings and collections, including the Guardian lists, Great Books and McEvoy reading programmes. Some starter definitions remain empty. The [dated checkpoint](docs/CURRENT_STATE.md) records actual entry counts; imported collection membership does not establish an exact reading edition, translation recommendation or complete access to lectures.

This is an initial usable implementation, not the complete public release. Automatic web research, automatic source-list population, comprehensive translation comparison, calibrated reading estimates, automated recommendation curation, a world-country coverage registry, publication approval workflows, and deployed email recovery/production operations remain work in the [product plan](PROJECT_PLAN.md). A refresh request records your intent for subsequent research; it does not run a background agent. Reading estimates cannot be computed when length is unknown. Uploaded images are served locally; public media storage is not configured yet.

## Research is saved per ranking

The **51-source survey is an initial evidence ledger for `books-all-time` only**. It is not a universal pool assigned to every ranking. It includes different subjects because that target covers book-length works across subjects. Philosophy, countries, centuries and every other separately requested ranking each need their own corpus of relevant, diverse, consulted sources. The 50-source floor applies to completed target research, never to every candidate. The current priority is broad source-backed publication followed by refinement; additional source quotas must not delay existing supported rankings. Sources may overlap only where their actual relevance is documented independently for both targets; unrelated material never qualifies.

The initial 51-source survey belongs to `books-all-time`. The live database now has many separately populated target ledgers and published lists; consult [current state](docs/CURRENT_STATE.md). Source counts include supplied consultations and reused records. They do not establish independent judgments, completed candidate assessment or verified editions.

Future agents must save each small batch to `research/<target>/sources.json` and then persist it to the database:

```bash
.venv/bin/python manage.py import_research research/books-all-time/sources.json --target books-all-time
```

For another target, use that target's own file and exact ranking slug. The importer rejects target mismatches, missing target-specific relevance, duplicate underlying sources, invalid dependencies and ineligible access claims. It imports evidence only, never ranking entries. Repeated imports preserve existing records; use `--update-existing` only after reviewing an intentional correction. This does not delete earlier sources, publish rankings or reset completed-research dates. Keep the versioned research files as the audit trail for corrections.

Create any missing starter definitions with:

```bash
.venv/bin/python manage.py bootstrap_rankings
```

The initial build-time research pause is historical. Current research and owner-file intake are authorized; continue from the saved ledgers and [research queue](docs/RESEARCH_QUEUE.md), following the [research skill](docs/skills/humanities-ranking-research/SKILL.md).

## Development and verification

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test backend.core
.venv/bin/python -m unittest discover -s tests
PATH="$PWD/.node/bin:$PATH" npm --prefix frontend run build
```

The owner generally prefers personal browser checks. The 28 September continuation explicitly authorized the deferred suites and isolated browser checks; their results are in [CONTENT_REPAIR_2026_09_28.md](docs/CONTENT_REPAIR_2026_09_28.md). Do not infer ongoing browser automation from that one verification request. The frontend build also checks TypeScript. Python tests cover domain rules, database/API boundaries and evidence imports. The runtime requirements and frontend lockfile are saved in the repository; browser-testing tools are optional in `requirements-dev.txt`.

Schema changes require saved migrations (and version-control commits when requested):

```bash
.venv/bin/python manage.py makemigrations
.venv/bin/python manage.py migrate
```

The application uses Django sessions and CSRF protection. Catalog edits require staff access; library items, plans, weights and notes belong to the signed-in user. Additional local accounts can be created through Django admin or `manage.py createsuperuser`; a public registration flow is implemented and controlled by `PUBLIC_REGISTRATION` (disabled by default). SMTP delivery and hosted account recovery remain deployment-dependent.

## Data and later hosting

The launch/setup scripts take a daily local snapshot before migrations. Run `.venv/bin/python manage.py backup_local` for an extra database/media backup under `data/backups/`. See [data safeguards, backups and password recovery](docs/DATA_SAFETY.md). Research JSON files are an additional readable evidence record, not a replacement for database backups. The profile's library export also does not include the full database or image files. PostgreSQL deployments need database dumps and separate media backups; verify restoration before public launch.

The current scripts and Compose configuration are for local access. Public deployment needs HTTPS, a fresh secret, `DJANGO_DEBUG=0`, specific `DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, production media storage, account recovery/registration decisions, request limits, monitoring and tested backups. Initial browser account setup is disabled outside debug mode; create the first administrative account with `manage.py createsuperuser`. Public search-engine pages and broader audience scaling remain planned rather than promised by the local container.


## Forgotten password

From the project directory, run:

```bash
bash scripts/reset_password.sh YOUR_USERNAME
```

Enter a new password twice at the hidden prompts. Your existing account and saved data remain. Passwords are already stored as one-way hashes; recovering access means resetting the password, not reading the original. This command must point to the same database as the app. Email recovery is implemented at `/accounts/password-reset/` but requires configured and verified SMTP delivery.

## Continue in a new chat

Start with [HANDOVER.md](HANDOVER.md) and [AGENTS.md](AGENTS.md). The handover contains copyable prompts for development and research, exact current state, and next steps. Use [the development skill](docs/skills/humanities-app-development/SKILL.md) for code changes and [the research skill](docs/skills/humanities-ranking-research/SKILL.md) for ranking work. These are repository-local instructions; mention their paths rather than assuming a fresh chat has installed them as global skills.

Latest verification and migration status is recorded in [HANDOVER.md](HANDOVER.md). The later 5 October media checkpoint/retry follow-up passed 346 domain and 18 isolated backend ingestion/thumbnail tests; the earlier full backend pass was 304 tests. The unchanged frontend's last pass was 80 tests on 30 September. Browser verification remains with the owner. Keep test data isolated from the owner's database.

The [28 September code review](docs/CODE_REVIEW_2026_09_28.md) records the latest bug fixes, static/build checks, saved regression cases and manual browser checks. Plan confirmations now require the signed token returned by their preview; stale previews must be regenerated.


To use a separate AI researcher, copy [EXTERNAL_AGENT_RESEARCH_BRIEF.md](docs/EXTERNAL_AGENT_RESEARCH_BRIEF.md) and specify the target. Ask it to return the full Word `.docx` research document, then bring that document back here with [EXTERNAL_AGENT_RESULTS_INTAKE.md](docs/EXTERNAL_AGENT_RESULTS_INTAKE.md). The latter explains how to convert the Word results into audited database records; JSON attachments are optional.

The external-agent brief includes covers/portraits and an image appendix with source URLs, edition identity and attribution. Images can be embedded in Microsoft Word where permitted, with optional original files for later app import.

To supply existing research directly, drop files in [pending_rankings_to_process/](pending_rankings_to_process/README.md), or attach them in a chat if the interface supports uploads. Ask the agent to follow the file-processing prompt in [HANDOVER.md](HANDOVER.md). The folder persists across chats and does not import files automatically. Original files and processing outcomes are retained; you do not need to convert Word documents to JSON yourself.

To resume catalog cover/portrait completion across the supported providers, run `./scripts/complete_catalog_media.sh --background`. Check progress with `./scripts/complete_catalog_media.sh --status`. The [5 October improvements](docs/MEDIA_PIPELINE_IMPROVEMENTS_2026_10_05.md) add Unicode/library-name matching, saved identifier/candidate reuse, automatic provider recovery, LoC/Gallica APIs, targeted publisher metadata and live file-validated coverage. The [later portrait follow-up](docs/PORTRAIT_SOURCES_2026_10_05.md) adds Wellcome/Nobel sources and corrects Wikimedia thumbnail-host and maxlag handling. Google Books needs an exported `GOOGLE_BOOKS_API_KEY`. See [the media completion guide](docs/CATALOG_MEDIA_COMPLETION.md) for stop/resume commands, source checks, rate limits and unresolved reports. Implemented lookups do not mean the image backlog is complete.

The [29 September technical improvements](docs/TECHNICAL_IMPROVEMENTS_2026_09_29.md) add bounded request caching and list payloads, smaller study saves, lazy screens, image previews, incremental scheduled backups and staff Operations. The [selected follow-up improvements](docs/SELECTED_IMPROVEMENTS_2026_09_29.md) add remaining ranking/study pagination, indexed search, save conflicts and retry protection, fuller contracts, measured query optimization, verified recovery, private recommendation bundles/feedback and accessible browsing navigation. Migration **0018** is applied locally. External backup copying still needs a destination. Frontend lint/format and contract checks are available; the optional CI workflow runs only when manually dispatched.

The [latest three selected improvements](docs/SEARCH_DRAFTS_CALENDAR_2026_09_29.md) add incremental search updates, browser-local recovery of unsaved writing and previewed holidays/temporary monthly targets. The current schema is **0019**, applied to the existing database. Planner has the calendar controls; Profile manages device draft recovery. Latest feature selections and rejected proposals are recorded in [AGENTS.md](AGENTS.md).

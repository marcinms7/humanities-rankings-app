# Marginalia — continuation handover

## Active checkpoint — 13 September 2026

Latest owner instruction: populate supported rankings now and include a picture for every book and author. Do not wait for a full 100-entry release before showing reviewed initial selections. Preserve both critical-standing and reading-value orders; personal numeric scores remain unset. Save after every small batch.

Actual database: **14 works, 34 people, 14 English editions, 31 ranking entries**. Catalog batches 01 and 02 imported successfully, with receipts in `research/catalog/`. Eligible sources through batch 31: **214 all books / 99 literary fiction / 116 nonfiction / 97 philosophy books / 99 philosophers**. Existing ledgers and evidence are preserved. Fresh backup: `manual-20260913T020144236169Z`.

In progress: reviewed image manifest and first illustrated ranking release; **16 verified images are now imported: a cover for each of eight books and a portrait/credited historical depiction for each author.** `research/catalog/images-01.json` preserves URLs, licenses, image hashes and review notes; the import receipt records media paths. Wikipedia/Commons metadata for the eight authors was consulted, including licenses. Network access via escalated curl works. **Literary fiction now has eight published initial-selection entries, revision 2, with both orders, target-local citations and caveats saved in scope.editorial.** The earlier empty revision is preserved. Both orderings now display through an Order by selector, with entry-specific evidence links and uncertainty. Image credits display on author and edition pages. TypeScript/Vite build and collectstatic succeeded. Continue with the philosopher selection and broader books; no complete-global research date was set. The older counts and zero-catalog statements farther below are historical and pending consolidation. Countries and philosophy branches follow the five broad rankings. Next new evidence batch 32; next new source ID R201.

Updated 12 September 2026. This file is the short entrypoint for a new chat in this project directory. Read `AGENTS.md` as well. The user wants an eventual public humanities rankings/reading app, beginning with one persistent local account. Python/Django backend, React/TypeScript frontend, responsive desktop/phone site. Preserve the existing visual style; the owner likes the colours.

## What is saved

- Runnable Django/React app with local authentication, shared catalog, three discovery sections, bookmarks, personal lists/copies, private library/progress/notes, reading plans, English edition selection, image uploads, theme settings, update/research dates and research evidence.
- Database `data/db.sqlite3`: the research continuation preserves **1 real user, 65 ranking/collection definitions, 0 works, 0 people and 0 ranking entries**. Research evidence now covers five separately maintained targets; inspect current counts below and the database rather than assuming the earlier 51-source state. Never reset or replace this database.
- The original 51-source all-books survey is preserved within a much larger continuation. Each additional target has individually recorded relevance; no corpus was copied wholesale. Source collection and ranking synthesis remain incomplete.
- No final criteria, assessed scores, invented ranks, books or author biographies were seeded. Source discovery can continue before the owner settles criteria. Named publisher lists can be faithfully imported independently of personal criteria.
- Migrations `0001_initial`, `0002_flexible_reading_and_archives`, and `0003_shared_deletion_guards` are applied to the local database.
- This workspace's implementation files remain uncommitted/untracked. No version-control commit was requested. Database/media/backups and local dependency folders are ignored by git; preserve them when moving the project.

## Latest completed changes

**New authorization after the pilot:** the owner asked to do the remaining comparative work, complete and publish the five broad rankings with both selected orderings, and then move to England, Ireland, USA, Germany, France, Poland, China and Japan book rankings and philosophy by branch/topic. See [the completion sequence](research/COMPLETION_PLAN.md). The older “five targets only / no population” boundary below describes the earlier phase, not a current prohibition. Publication is authorized once evidence, method and English-edition checks are ready; no further generic permission request is needed. Numeric personal scores and weights remain unset.

**Research continuation, 12 September 2026:** the owner resumed research for `books-all-time`, `literature-all-time`, `nonfiction-all-time`, `philosophy-books-all-time`, and `philosophers-all-time` only, then requested actual rankings. They selected **both critical standing/enduring influence and reading value today**. See [the draft index](research/RANKING_DRAFTS.md): five 25-candidate pilot comparisons, each with two proposed orders, reasons, target-specific source links and uncertainty. These are saved research proposals, not completed worldwide Top 25s or published app entries. Intended full lengths remain 100–200; final criteria, weights and scores remain unset. Most specific English editions still need verification.

Through batch 25, successfully imported eligible source counts are **191 all books; 85 literary fiction; 103 nonfiction; 91 philosophy books; 93 philosophers** (563 target-source records; cross-target reuse is not a global unique count). The owner explicitly criticized homogeneity and wants worldwide, non-English, substantially greater depth—over 100 and toward 200 or more where useful. Do not stop at a threshold. Ledgers, batch logs, per-target RESEARCH.md, proposal JSON and diversity/claim audits are saved. The first pilot still has thin candidate dossiers, reference/platform concentration, and insufficient science/history/other-subject coverage.

Continuation inputs and immutable batch notes are in `research/_runs/2026-09-12/`; the original ledger/notes, queue, handover and protected-table digests were snapshotted there. A local backup was taken before continuation (`manual-20260912T010723414041Z`). Imports used the existing `import_research` without `--update-existing`. No source corrections, catalog population, private preference edits or publication were performed. Completed-research dates remain null. Preserve v1 proposals when revising them; `build_drafts.py` renders the recorded inputs and does not write the database.

Verification: all 21 snapshotted protected tables match their prior row counts and content digests, including the real account and existing private ranking preference. All 51 original source records remain identical as JSON values. Each draft has two valid permutations of the same 25 candidates, only target-local source references, null final scores and a source count matching the database. Local document links resolve. These were read-only artifact/database checks, not an app test-suite or browser run. See `research/_runs/2026-09-12/after-database-preservation-check.json` and `CONTINUATION_LEADS.md`. Next batch: 26; next new source ID: R178.

1. **Reading rhythm:** weekly/monthly targets, optional per-reading-day mode, and a flexible number of reading days per week. Profile settings persist in the database. Python calculates both monthly capacity and suggestions; physical pages stay distinct from provisional effort equivalents. Classic/demanding/philosophy presets, optional per-work multiplier and edition density share the reading-time policy. See `docs/READING_TIME.md`.
2. **Planner UI:** per-month plus button opens a form preselected to that month; saved plans can be moved/unlocked as before. Reading rhythm is a compact summary with an **Adjust** button, collapsed by default so months stay near the top. Expanded inputs, selects and Save have matching heights. The owner requested this after finding the original panel too tall.
3. **Navigation/layout:** Reading collections immediately follows Published rankings. Search icon/input spacing and the personal-section gap were fixed. The left sidebar scrolls independently in short windows, including the phone navigation drawer. Preserve this when adding links.
4. **Data protection:** shared catalog/source/ranking records have archive flags and API/admin, Django ORM and database DELETE guards. Personal library/list removals do not delete shared books. Launch/setup make a daily local database/media snapshot before migrations; extra snapshots use `manage.py backup_local`. See `docs/DATA_SAFETY.md` for limits and trigger maintenance.
5. **Password recovery:** `bash scripts/reset_password.sh USERNAME` uses Django's hidden interactive password-reset prompt. Passwords already use one-way hashes; the original is not retrievable. No password was reset during implementation. Saved account data survives a password change. Email recovery remains future public-release work.
6. **Documentation:** development and research skills, AGENTS, README, this handover, product plan, reading-time rules and data-safety instructions reflect the current choices.

## Running and verification

Current preview: **http://127.0.0.1:8001/**, launched with `PORT=8001 ./scripts/run_local.sh`. A new chat should check whether that process is still running; a closing chat does not guarantee it survives. Normal `./scripts/run_local.sh` uses port 8000. Reuse the running server where possible rather than starting conflicting instances. Both commands use the same default `data/db.sqlite3`.

Python dependencies are installed in `.venv`; Node is installed locally in `.node/bin` because global Node/Docker were unavailable. For frontend changes:

```bash
PATH="$PWD/.node/bin:$PATH" npm --prefix frontend run build
.venv/bin/python manage.py collectstatic --noinput
```

Latest TypeScript/Vite build succeeded and static assets were collected after the compact-panel and sidebar fixes. Required migrations and local backup creation succeeded. **No additional test-suite or automated browser run was performed for these changes:** the owner asked to do browser checks themselves. Ask them to try changed flows. Historical domain/API tests predate these refinements; do not claim they verify the new behavior. No test accounts or books were added to the live database. PostgreSQL/Docker configuration, PostgreSQL triggers and backup restoration have not been exercised here. Password reset was not run against the owner's account.

Skill frontmatter and linked local paths were inspected separately. The system skill validator could not run because this app's virtual environment does not include PyYAML; no application dependency was added just for that validator.

## Important product boundaries

- **Researched rankings** (`curated`) are synthesized from a hard minimum of 50 consulted, diverse, relevant sources for each requested target, **ideally many, many more than 50**. Reaching 50 is not a stopping rule or proof of comprehensive coverage. Sources need target-specific relevance; do not copy one corpus to all rankings.
- **Published rankings** (`external` + `ranked`) preserve an original publisher's ordering, e.g. Guardian.
- **Reading collections** (`external` + `unranked`/`reading_sequence`) hold McEvoy lists/programmes and Great Books. Reading sequence is not a merit ranking.
- Main shared rankings are read-only in the ordinary UI, including for the local owner. Bookmarks hold private weights/overrides; personal copies hold custom membership/order.
- All accounts share catalog/research data. Private user records are owned rows in the same server database, not separate per-user browser databases. Optional sharing applies only to selected personal lists.
- Worldwide coverage, English reading editions, documented literary/cultural country associations, multiple associations allowed; England distinct from UK. All-books/all-time includes all subjects; literary-fiction and nonfiction lists are separate.
- Suggested additional discovery categories, not seeded yet: History; Biography & Memoir; Religion & Mythology; Arts & Criticism; Science & Ideas; Society & Politics. Poetry/Drama are useful form-based categories. Use overlapping tags/scopes, without duplicating works.

## Next work

- Let the owner verify compact planner controls, sidebar scrolling, month-add preselection and reading rhythm in their browser. React to their feedback while preserving the palette. Do not automatically run browser checks.
- The five-target research continuation **is authorized and active**. Priorities/scopes are in `docs/RESEARCH_QUEUE.md`. Continue from the saved ledgers and two-lens pilot proposals: strengthen weak placement arguments, expand toward 100–200 candidates and substantially deeper diverse sources, and verify complete English editions. Final criterion design remains separate. Other queued targets are not authorized by this continuation.
- Faithful Guardian imports and McEvoy/Great Books collection imports remain pending. Verify original sources and exact editions. Great Books edition choice and McEvoy month-to-book lecture assignments remain unresolved. `import_research` imports evidence only; there is no completed general publisher-entry importer.
- Public release remains future work: registration/email recovery, HTTPS/deployment config, public SEO pages, scalable querying, hosted media, tested PostgreSQL migration and backup restoration, rate limits and production operations. Local access does not automatically make the app reachable on a phone outside this machine.

## Prompts for a new chat

**Update rankings from files I provide (no fresh broad research):**

> Read AGENTS.md, HANDOVER.md and docs/EXTERNAL_AGENT_RESULTS_INTAKE.md. Process my attached files, or the unprocessed files in pending_rankings_to_process/, and update the relevant rankings using the supplied material. Preserve originals, read the full source register and image appendix, reconcile sources/catalog identities with existing records, and import supported evidence and scope-consistent ranking/collection updates into the existing database with provenance and revisions. Keep private user data intact. Do not invent missing criteria, scores or sources. Do only necessary verification, not a new broad research project. Record processed file hashes, successful writes, partial batches and remaining questions in the inbox processing log, then update HANDOVER.md.

Use accessible chat attachments when the interface supports them, or place files in the project [pending_rankings_to_process/](pending_rankings_to_process/README.md) folder. The folder is the durable option across fresh chats; attachment availability should not be assumed. Files are processed only when requested, not by a background watcher. `.docx` is preferred, with other readable formats accepted. The receiving agent converts documents; the owner need not prepare JSON. Inbox documents/logs are gitignored, except its README.

**Continue app development:**

> Continue this project. Read AGENTS.md, HANDOVER.md, README.md and docs/skills/humanities-app-development/SKILL.md first; consult PROJECT_PLAN.md for the full scope. Preserve the existing database/account and visual style. My next requested change is: [describe it]. Build changes as needed and ask me to check the browser; don't run automated browser tests or start ranking research unless I ask.

**Research and save a ranking:**

> Work on ranking research only for [exact target, or books-all-time]. Read AGENTS.md, HANDOVER.md, docs/RESEARCH_QUEUE.md and docs/skills/humanities-ranking-research/SKILL.md. Inspect the target's current database records and saved ledger, then continue. Use 50 distinct relevant consulted sources per target as the hard minimum, but aim for **many, many more than 50**, with substantial diversity. Continue beyond 50 wherever additional sources improve coverage, evidence or understanding of disagreements; never pad the count with irrelevant, duplicate or unexamined sources. Save every small batch to research/<target>/sources.json and import it into the existing database with .venv/bin/python manage.py import_research research/<target>/sources.json --target <target>. Preserve existing evidence, private data and revisions. Do not invent final criteria or scores. Update the research notes, queue and HANDOVER.md before finishing.

**Import an original list:**

> Faithfully import [exact publisher list and URL] into Published rankings, or [reading programme/collection] into Reading collections. Read AGENTS.md, HANDOVER.md and the research skill's named-list import rules. Preserve original order or unranked status, verify catalog identities and English editions, save incrementally to the existing database with provenance/revisions, and keep it separate from synthesized rankings and personal lists.

The skill files are repository-local Markdown instructions. These prompts work without installing a plugin or assuming the new chat remembers this conversation. A new chat can usually be started in this same project folder with just “Read AGENTS.md and HANDOVER.md, then …”.


## Research performed by a separate AI agent

The owner prefers a Word document from the external researcher. Give that agent the complete [external research brief](docs/EXTERNAL_AGENT_RESEARCH_BRIEF.md), with a target specified. It is self-contained and requests many, many more than the hard minimum of 50 relevant diverse sources, incremental checkpoints, and a complete `.docx` containing report, source register and candidate records. Optional JSON is supported but is not required.

When the owner brings the Word document back, follow [the results intake guide](docs/EXTERNAL_AGENT_RESULTS_INTAKE.md). Read the entire source register and candidate sections, preserve URLs/IDs and the original document, convert to normalized research files, reconcile existing sources/catalog identities, and import supported evidence into the existing database. Do not imply receiving a document publishes a ranking or that the source importer imports catalog entries. These two documents were prepared as instructions; no external research was commissioned or imported by preparing them.

The external research brief also requests book covers and author portraits, with embedded previews where permitted, stable image IDs, original URLs, edition matching and attribution/reuse notes. The intake guide explains how to map these to app media; image-only pages do not inflate research source counts. Microsoft Word `.docx` is preferred; similar editable document formats are accepted.

Image checkpoint: `images-02.json` holds 26 reviewed-metadata portrait candidates (23 philosophers plus Darwin, Carson and Du Bois). Downloads partially succeeded; Wikimedia returned HTTP 429 for others. Do not mark these images identity-reviewed/imported until local files are visually checked. Kwasi Wiredu and Xunzi lacked page images and remain unresolved.

People checkpoint: `research/catalog/people-01.json` imported 23 philosopher identities with target-local provenance; receipt saved. Philosopher publication and their image attachment are pending.

13 September checkpoint: six more books/editions imported in catalog batch 03. All **34 people now have verified portraits** (images-02 imported 26). Eight existing books have covers; six new covers are pending. Publisher HTML returned 403 after the usage-limit rejection cleared on retry; fetching covers by verified ISBN from publisher/Open Library. Philosopher publication is next.

Publication checkpoint: **23 philosophers published in revision 2**, alongside eight novels. Both orders, citations and caveats are visible; all included people have images. Six additional book covers are now downloaded and reviewed, awaiting image import. Source batch 32 added Asa Gray’s historical Darwin review: counts **215 / 99 / 117 / 97 / 99**. Next new source R202; next batch 33.

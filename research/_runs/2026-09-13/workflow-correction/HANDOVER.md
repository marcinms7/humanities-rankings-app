# Marginalia — continuation handover

Updated 13 September 2026. Read AGENTS.md and the project research skill before continuing. Preserve the existing database, account and owner-approved visual style.

## Current saved state

The owner explicitly asked to **populate rankings now, retain both critical standing/enduring influence and reading value today, and provide a picture for every book and author**. They also asked for frequent saved checkpoints in case context runs out. These instructions supersede the earlier research-only/no-population phase. Do not ask again for generic publication permission or wait for 100 entries before showing a supported incremental selection.

**All five broad rankings are populated in the running app.** They are honestly labeled initial researched selections, not finished worldwide Top lists. Both orders, per-entry explanations, target-local evidence links and uncertainty are visible. Numeric personal criteria, weights and scores remain unset.

| Target | Consulted sources | Illustrated entries | Revision |
| --- | ---: | ---: | ---: |
| [Books · All time](research/books-all-time/RESEARCH.md) | 215 | 14 | 2 |
| [Literary fiction · All time](research/literature-all-time/RESEARCH.md) | 99 | 8 | 2 |
| [Nonfiction · All time](research/nonfiction-all-time/RESEARCH.md) | 117 | 6 | 2 |
| [Philosophy books · All time](research/philosophy-books-all-time/RESEARCH.md) | 97 | 4 | 2 |
| [Philosophers · All time](research/philosophers-all-time/RESEARCH.md) | 99 | 23 | 2 |

Existing `data/db.sqlite3`: **1 real user, 65 ranking/collection definitions, 14 works, 34 people, 14 English editions, 55 ranking entries and 10 ranking revisions**. Every catalog book has a cover and every person has a credited portrait or historical depiction: **48 local images, none missing**. Shared rankings remain read-only in the normal UI. No private preference or account was edited by research.

Evidence through **batch 32**: **627 target-source records, representing 217 underlying source identities across the five ledgers**. Cross-target reuse is individually justified; these counts are not 627 globally independent sources. The original all-books 51-source ledger remains unchanged as JSON values. No source corrections used --update-existing. Next batch: **33**; next new source ID: **R202**.

## Publication and image artifacts

- Each target has `initial-selection-v2.json`, its import receipt, `INITIAL_SELECTION.md`, updated `RESEARCH.md` and `evidence-audit-v2.json`. The earlier five 25-candidate v1 pilots and v1 audits remain historical artifacts; do not overwrite them or confuse their orders with the published v2 selection.
- Catalog imports: `research/catalog/batch-01.json` through `batch-03.json`, with receipts. Work identities, specific English editions, ISBNs and physical page counts are recorded. Publisher metadata verification does not count as additional critical evidence. Completeness confidence and edition limitations are explicit.
- People: `people-01.json` and receipt; `profile-notes-01.json` preserves the reviewed replacement of initial editorial wording with factual introductions.
- Images: `images-01.json` through `images-03.json` and receipts. Manifests save identity review, source page, artist/license information, original image URL and SHA-256. Downloaded originals are retained under matching directories; attached files live in `media/`. Ancient/medieval representations are labeled as historical depictions. Covers match the recorded editions; the Hume cover comes from the matching Google Books record after publisher access/Open Library failed.
- `research/catalog/REVIEW_NOTES.md`: the old Genji candidate mapping incorrectly included S37; publication excludes it because the consulted excerpt does not support Genji. Original catalog batch and receipt remain preserved.
- Publication importer: `manage.py publish_researched_selection <input> [--dry-run]`. It validates target-local evidence, both permutations, images and English editions, records the previous empty revision, and publishes revision 2 atomically. It is **first-publication only**: exact reruns are no-ops; changes to populated targets require a reviewed update workflow that preserves IDs, historical revisions, source positions and private overrides. Do not bypass this guard by deleting entries or recreating targets.
- Catalog and image commands: `import_catalog_research`, `import_person_research`, `import_research_images`. They preserve existing identities and images. Save a fresh backup before any reviewed updates.

## Research method and remaining work

The source minimum remains **50 distinct relevant consulted sources per target, aiming many, many more**, with substantive worldwide/non-English and scholarly/editorial/reader diversity. The owner specifically wants over 100 and toward 200 or more useful sources for major scopes. Current source counts are not a reason to stop; three targets are still just below 100 and all dossiers need expansion.

The app selections are much smaller than the intended 100–200 entries. Their membership currently reflects completed evidence, edition and image verification; omission is not a judgment against an unlisted candidate. Exact adjacent ranks remain uncertain. Critical standing and reading value are separate editorial judgments, not computed scores or source-vote totals. The earlier pilot over-penalized difficult books and thinkers under reading value; v2 corrects this for Mann, Kant, Wittgenstein and others. Further comparisons must deepen the arguments, not just add names.

Immediate continuation:

1. Strengthen thin individual dossiers and expand the five illustrated selections using a reviewed revision-update command. Keep saving every small source batch to each cumulative ledger and run the existing `import_research` command. `research/save_batch.py` now accepts `consulted_on`; do not backdate new consultations to 12 September.
2. Expand philosophy books beyond the four Greek/Anglophone entries using the existing worldwide pilot: Chinese, Indian, Islamic, African and Latin American work-level evidence and complete English editions. Philosopher profiles are not a substitute for verified book identities. Wiredu and Xunzi remain in the candidate pool; their Wikipedia pages lacked a suitable primary image, so their inclusion still needs a credited image from another source.
3. Expand fiction beyond eight novels: the saved pilot and later criticism cover major challengers. Genji, Moby-Dick, Beloved and Kokoro need deeper independent comparative dossiers. All books/nonfiction particularly need history, biography, economics, religion, arts and further science, not more philosophy under another label.
4. After the five broad rankings are properly expanded, research country book rankings for **England, Ireland, USA, Germany, France, Poland, China and Japan**, then philosophy by branch/topic (ethics, political philosophy, epistemology, metaphysics, aesthetics, logic, mind, language, science). This sequence is authorized. Each new target needs its own evidence ledger and the full diversity/minimum requirement; no wholesale corpus copying.

See [the queue](docs/RESEARCH_QUEUE.md), [completion plan](research/COMPLETION_PLAN.md), and [ranking index](research/RANKING_DRAFTS.md). Sources/images that fail to load are leads, not counted evidence. Keep source selection, bibliographic verification, image provenance and published entries separate.

## Preservation and verification

- Fresh pre-publication backup: `manual-20260913T020144236169Z`; post-publication database/media backup: **`manual-20260913T055334636936Z`**. Earlier snapshots remain in `data/backups/`.
- Read-only checks verified ledger counts, two valid permutations per selection, target-local evidence links, 48 media files, null scores/source ranks, and preservation of all five empty revision-1 snapshots. See `research/_runs/2026-09-13/publication-audit.json`.
- The real account and existing ranking preference match their original digests. **One library item appeared during the live session and is retained**; do not claim the private library is still empty or restore an old snapshot over it. See `preservation-audit.json` in the same run directory. Catalog and publication tables changed intentionally; DELETE guards and migrations remain intact.
- TypeScript/Vite build and `collectstatic` succeeded after the two-order display, visible image credits and personal-copy perspective changes. Creating a personal copy carries the selected editorial order into the private copy. No personal copy or test data was created for verification.
- **No automated browser run or test suite was run**, respecting the owner’s preference to check the browser themselves. Read-only data/manifest checks are not a substitute for browser validation. No new migrations. PostgreSQL/Docker, restoration and public deployment remain unverified.
- Network image retrieval uses approved escalated curl. A temporary automatic-review usage-limit rejection cleared on retry; later publisher 403s and Wikimedia 429s were handled with alternative verified image records and slower requests. No image task remains blocked.

## Running the app

Current preview: **http://127.0.0.1:8001/**. Ranking detail URLs are `/#/rankings/1` (all books), `/2` (fiction), `/3` (nonfiction), `/4` (philosophy books), `/5` (philosophers). Reuse the running process; check its state before launching another. A new chat does not guarantee process survival.

Initial setup: `./scripts/setup_local.sh`; normal launch: `./scripts/run_local.sh` (port 8000), or `PORT=8001 ./scripts/run_local.sh`. Preserve `data/db.sqlite3` and `media/`. Docker is not installed. Build with `PATH="$PWD/.node/bin:$PATH" npm --prefix frontend run build`, then `.venv/bin/python manage.py collectstatic --noinput`.

Files remain uncommitted/untracked; no commit was requested. Local dependencies, database, media and backups are ignored by git. Research files do not substitute for database/media backups.

## Product boundaries and other work

Keep three discovery sections: researched rankings (`curated`), original publisher rankings (`external` + `ranked`), and reading collections (`external` + `unranked`/`reading_sequence`). Guardian contents, McEvoy programmes and Great Books imports remain pending; the latter require exact edition/programme mapping. Personal copies are separate from shared originals.

Preserve the compact reading-rhythm controls, visible month cards, scrollable sidebar and approved colours. Python remains authoritative for scheduling, permissions and scoring. Physical pages are separate from provisional effort multipliers. No planner changes were made during this research publication.

Owner files go in `pending_rankings_to_process/` or accessible attachments; follow its README and `docs/EXTERNAL_AGENT_RESULTS_INTAKE.md`, preserve originals and hashes, and do not turn file intake into unsolicited broad web research. The separate-agent Word brief is `docs/EXTERNAL_AGENT_RESEARCH_BRIEF.md`; no separate agents were used in this continuation.

Public registration, email recovery, deployment/HTTPS, hosted media, PostgreSQL migration, restoration drills and other production operations remain future work. Password recovery is `bash scripts/reset_password.sh USERNAME`; never store plaintext passwords.

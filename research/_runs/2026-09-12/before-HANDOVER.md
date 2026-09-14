# Marginalia — continuation handover

Updated 12 September 2026. This file is the short entrypoint for a new chat in this project directory. Read `AGENTS.md` as well. The user wants an eventual public humanities rankings/reading app, beginning with one persistent local account. Python/Django backend, React/TypeScript frontend, responsive desktop/phone site. Preserve the existing visual style; the owner likes the colours.

## What is saved

- Runnable Django/React app with local authentication, shared catalog, three discovery sections, bookmarks, personal lists/copies, private library/progress/notes, reading plans, English edition selection, image uploads, theme settings, update/research dates and research evidence.
- Database `data/db.sqlite3`: **1 real user, 65 ranking/collection definitions, 51 research sources, 0 works, 0 people, 0 ranking entries, 0 library items, 0 plan items** when read for this handoff. The owner may add data afterward; inspect current state rather than assuming these counts remain unchanged. Never reset or replace this database.
- Every saved source belongs to **`books-all-time` only**. Its readable ledger and research notes are in `research/books-all-time/`. Other requested targets need their own relevant, diverse corpus. The 51-source survey is preliminary research, not a completed Top 100/200 or evidence of full candidate coverage.
- No final criteria, assessed scores, invented ranks, books or author biographies were seeded. Source discovery can continue before the owner settles criteria. Named publisher lists can be faithfully imported independently of personal criteria.
- Migrations `0001_initial`, `0002_flexible_reading_and_archives`, and `0003_shared_deletion_guards` are applied to the local database.
- This workspace's implementation files remain uncommitted/untracked. No version-control commit was requested. Database/media/backups and local dependency folders are ignored by git; preserve them when moving the project.

## Latest completed changes

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

- **Researched rankings** (`curated`) are synthesized from at least 50 consulted, diverse, relevant sources for each requested target. Sources need target-specific relevance; do not copy one corpus to all rankings.
- **Published rankings** (`external` + `ranked`) preserve an original publisher's ordering, e.g. Guardian.
- **Reading collections** (`external` + `unranked`/`reading_sequence`) hold McEvoy lists/programmes and Great Books. Reading sequence is not a merit ranking.
- Main shared rankings are read-only in the ordinary UI, including for the local owner. Bookmarks hold private weights/overrides; personal copies hold custom membership/order.
- All accounts share catalog/research data. Private user records are owned rows in the same server database, not separate per-user browser databases. Optional sharing applies only to selected personal lists.
- Worldwide coverage, English reading editions, documented literary/cultural country associations, multiple associations allowed; England distinct from UK. All-books/all-time includes all subjects; literary-fiction and nonfiction lists are separate.
- Suggested additional discovery categories, not seeded yet: History; Biography & Memoir; Religion & Mythology; Arts & Criticism; Science & Ideas; Society & Politics. Poetry/Drama are useful form-based categories. Use overlapping tags/scopes, without duplicating works.

## Next work

- Let the owner verify compact planner controls, sidebar scrolling, month-add preselection and reading rhythm in their browser. React to their feedback while preserving the palette. Do not automatically run browser checks.
- Resume requested ranking research only when asked. Priorities/scopes are in `docs/RESEARCH_QUEUE.md`. Continue the saved all-time survey with candidate/source mapping, diversity gaps and English editions; criteria remain an owner decision before final personalized assessments.
- Faithful Guardian imports and McEvoy/Great Books collection imports remain pending. Verify original sources and exact editions. Great Books edition choice and McEvoy month-to-book lecture assignments remain unresolved. `import_research` imports evidence only; there is no completed general publisher-entry importer.
- Public release remains future work: registration/email recovery, HTTPS/deployment config, public SEO pages, scalable querying, hosted media, tested PostgreSQL migration and backup restoration, rate limits and production operations. Local access does not automatically make the app reachable on a phone outside this machine.

## Prompts for a new chat

**Continue app development:**

> Continue this project. Read AGENTS.md, HANDOVER.md, README.md and docs/skills/humanities-app-development/SKILL.md first; consult PROJECT_PLAN.md for the full scope. Preserve the existing database/account and visual style. My next requested change is: [describe it]. Build changes as needed and ask me to check the browser; don't run automated browser tests or start ranking research unless I ask.

**Research and save a ranking:**

> Work on ranking research only for [exact target, or books-all-time]. Read AGENTS.md, HANDOVER.md, docs/RESEARCH_QUEUE.md and docs/skills/humanities-ranking-research/SKILL.md. Inspect the target's current database records and saved ledger, then continue. Use at least 50 (**preferably many more**) distinct relevant consulted sources per target, with substantial diversity; prefer more useful evidence. Save every small batch to research/<target>/sources.json and import it into the existing database with .venv/bin/python manage.py import_research research/<target>/sources.json --target <target>. Preserve existing evidence, private data and revisions. Do not invent final criteria or scores. Update the research notes, queue and HANDOVER.md before finishing.

**Import an original list:**

> Faithfully import [exact publisher list and URL] into Published rankings, or [reading programme/collection] into Reading collections. Read AGENTS.md, HANDOVER.md and the research skill's named-list import rules. Preserve original order or unranked status, verify catalog identities and English editions, save incrementally to the existing database with provenance/revisions, and keep it separate from synthesized rankings and personal lists.

The skill files are repository-local Markdown instructions. These prompts work without installing a plugin or assuming the new chat remembers this conversation. A new chat can usually be started in this same project folder with just “Read AGENTS.md and HANDOVER.md, then …”.

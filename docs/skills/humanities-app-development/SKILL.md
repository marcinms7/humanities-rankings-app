---
name: humanities-app-development
description: Continue implementation or maintenance of the Marginalia humanities rankings app in this repository, preserving shared research data and private reading profiles. Use for app work and local recovery, not to start ranking research.
---

# Marginalia development

Read the repository's [AGENTS.md](../../../AGENTS.md) and [HANDOVER.md](../../../HANDOVER.md) first. Use [PROJECT_PLAN.md](../../../PROJECT_PLAN.md) for intended scope and [README.md](../../../README.md) for runnable commands; distinguish implemented features from future public-release work.

- Keep Python/Django authoritative for permissions, research/scoring, reading time and scheduling. React/TypeScript handles the responsive UI; preserve the owner-approved warm ivory/moss and charcoal palette.
- Keep Researched rankings, Published rankings, and Reading collections distinct. Reading collections belongs directly below Published rankings in navigation. Main editorial rankings are read-only in normal browsing, including for the local owner; bookmarks hold private preferences and personal copies hold custom order/membership.
- Use the existing database and account. No reset, reseeding over edits, new "test" account in the live database, or silent database switching. Shared catalog and user-owned private rows occupy the same database. Browser cache is not the source of truth.
- Follow [data safeguards and recovery](../../DATA_SAFETY.md). Archive shared content instead of deleting it. Back up before migrations/imports that change existing data. Preserve database DELETE triggers when rebuilding tables. Passwords remain hashed; local recovery is `bash scripts/reset_password.sh USERNAME`, never plaintext storage or disclosure.
- Scheduling uses weekly/monthly targets, optional targets per reading day, and a flexible number of reading days. [Reading-time and capacity rules](../../READING_TIME.md) define the provisional effort/density algorithm. Preserve physical page counts, selected editions, locks, and preview-before-save behavior. Do not maintain a conflicting scheduling formula in TypeScript.
- The owner asked to stop automated testing for this iteration and prefers browser verification themselves. Build/typecheck frontend edits, apply required migrations and collect static assets. Ask the owner to try changed browser flows. Do not run browser automation or the suites unless requested; when authorized, isolate test data from the owner's database.
- Ordinary UI/backend work does not authorize fresh web research. For ranking research, use the separate project research skill and its hard per-target minimum of 50 relevant diverse sources, with the explicit aim of many, many more than 50. The minimum must not become a target cap or automatic completion signal. Never seed invented catalog content or scores to make empty views look finished.

At handoff, update `HANDOVER.md` with actual completed work, current database/migration/build status, unresolved issues and next steps. Keep launch/recovery instructions in README and detailed invariants in their linked documents. Never claim unrun browser, Docker, PostgreSQL or recovery checks passed.

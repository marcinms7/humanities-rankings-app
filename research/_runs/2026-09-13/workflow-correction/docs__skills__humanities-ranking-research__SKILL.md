---
name: humanities-ranking-research
description: Research and synthesize philosophy or literature rankings for this project using 50 diverse sources as a hard minimum per requested target and aiming for many, many more, with evidence-backed criterion assessments and user-controlled weights. Also use for importing named source lists; ordinary app implementation does not trigger research.
---

# Humanities ranking research

Use the project plan and the owner's latest instructions to identify the requested target and deliverable. A target can be an overall field ranking, a named author or philosopher, a work, an era/decade, a genre, a philosophical topic, a literary technique, or a custom theme/tag. Criteria are designed with the owner for each ranking; do not assume they have already been agreed.

For a fresh chat, first read [HANDOVER.md](../../../HANDOVER.md), [the research queue](../../RESEARCH_QUEUE.md) and this skill. Inspect the target's existing database records and `research/<target>/` ledger before collecting new evidence. Preserve the running app's configured database and existing account. The current local file is `data/db.sqlite3`; a new database is not a fresh research workspace. A request to resume research authorizes research and incremental database imports, not an application redesign or a database reset.

## Mandatory research breadth

**For every requested research target, 50 distinct, relevant, consulted sources is the hard minimum. Ideally gather many, many more than 50: substantially deeper research is the explicit goal, especially for broad rankings. Fifty is not the target count, a cap, a stopping rule, or evidence that research is complete. Sources must be diverse.** This is an explicit owner requirement.

Continue well beyond 50 while additional sources contribute useful candidate coverage, scholarship, criticism, reader perspectives, counterarguments or underrepresented traditions. Plan research for substantive breadth and depth rather than merely clearing the threshold. There is no new fixed upper limit or universal higher quota. Do not inflate counts with duplicates, weak repetitions, irrelevant material or unopened links. Explain remaining gaps and the basis for stopping even when the minimum is exceeded.

Treat each separately requested author, era, topic, or other target as its own research unit. A combined report does not pool 50 sources across otherwise separate targets. A source may support multiple targets only when its actual content is relevant to each and that relevance is recorded separately. Distinguish global unique-source count from per-target counts.

A candidate inside a broad ranking is not automatically a separate 50-source research assignment. It still needs evidence for its inclusion and assessments. If the owner specifically requests research on that candidate, it becomes its own target with the full minimum and the same aim of many, many more than 50 sources. Make target boundaries explicit in the research brief.

Search across a substantive mixture of:

- Academic papers, scholarly books or accessible chapters, critical studies, academic reviews, and bibliographies.
- University reading lists, syllabi, scholarly reference works, and specialist institutions.
- Independent rankings, critics' selections, literary publications, newspapers, and magazines.
- Specialist websites, independent blogs, essays, and detailed reviews.
- Reader discussions, reading groups, forums, and Reddit threads.
- Goodreads and other reader-review or recommendation communities.
- Other useful perspectives, including relevant non-English sources when their contents can be reliably understood.

The mix must meaningfully include scholarly/critical evidence, independent editorial material, and reader discussion when available for the target. Actively fill gaps in the source mix. **Many Reddit threads, Goodreads pages, or pages from one publisher do not satisfy the diversity requirement on their own.** Do not invent fixed numerical family quotas as though the owner requested them. Report the actual distribution by family, domain/platform, and independent author/publisher.

## Source counting and evidence

Maintain a source ledger using [the evidence record template](references/research-record-template.md). Count a source only when its relevant content has been accessed and examined, its identity/URL is recorded, and an evidence note explains how it informs the target.

**Save progress as research proceeds.** After each small batch of consulted sources, write or update the target's `research/<target>/sources.json` and research notes. Record counts, limitations, candidate links and the next unresolved step before switching tasks. Do not leave evidence only in conversation or tool memory, and do not wait until fifty sources have been reached to save it. Keep partial research visibly incomplete. App refinement does not itself resume research; when the owner requests research, continue from the saved ledger rather than starting over.

The application database is authoritative for displayed rankings and research evidence. After saving each batch, persist it with `manage.py import_research <ledger-path> --target <exact-ranking-slug>`. The ledger's `target_id`, each source's `target_ids`, and its `relevance_by_target` must name that specific target. The existing `books-all-time` survey must never be assigned wholesale to another ranking. The importer preserves previously saved records by default; review intentional corrections before using `--update-existing`, and retain earlier ledger versions. Importing a batch does not complete the research or publish a ranking.

The repository-local command is `.venv/bin/python manage.py import_research research/<target>/sources.json --target <target>`. Inspect its result: a saved JSON file alone is not a successful database import. If persistence fails, retain the ledger and report the exact unapplied batch; do not claim it is displayed in the app. Preserve stable `source_id` and `underlying_source_id` values. Follow [data safeguards](../../DATA_SAFETY.md): back up before changing existing records, archive instead of deleting, do not remove guards, and do not overwrite private preferences or reading data. For source corrections, preserve an earlier ledger snapshot before `--update-existing`.

- Search-result snippets, search pages, link directories, and unopened references are discovery leads; they do not count as consulted evidence.
- A paper, DOI page, preprint, and repository copy of the same study count once. Reprints, mirrors, syndicated articles, and lists copied from the same original count once for that underlying source.
- A discussion thread counts as one source; its comments are evidence within that source. Different substantive threads can count separately, with their common platform still visible in the diversity audit.
- A Goodreads work/reviews page counts as one source; rating totals and individual comments do not inflate the source count. Assess distinct standalone reviews on their actual independence and substance.
- An aggregation site may provide a useful source, but its underlying lists count additionally only when independently consulted. Avoid double-counting their votes during synthesis.
- An abstract supports only what it actually states. If that is sufficient for a recorded narrow claim, label the limited access; otherwise retain the paper as an uncounted lead until relevant text is available. Never present an unread full paper as reviewed.
- Count independently authored substantive articles separately even on one domain, while recording shared ownership and any dependence on the same original argument or dataset.
- An irrelevant or repetitive source is not useful padding. Keep rejected leads and reasons separate from eligible evidence.

Below 50 eligible sources, the target remains incomplete. Continue searching useful source families, reference chains, terminology variants, and relevant languages. If access or available evidence prevents the minimum, report the achieved count, search coverage, and exact limitation, save the research as incomplete, and seek a revised scope if necessary. Never silently reduce the minimum or label an incomplete draft comprehensive.

## Synthesis and scoring

Combine evidence from the internet into a reasoned assessment. The owner wants a broad synthesis of independent rankings, scholarship, criticism, blogs, and discussions, with traceable judgments.

Keep bibliographic facts, frequency of recommendation, scholarly influence, critical interpretation, reader response, and personal fit distinguishable. Frequency and popularity are evidence about reception; they do not automatically establish quality or personal relevance. Preserve disagreement, minority views, historical context, and gaps in geographic/language coverage.

Use source-list positions only in a way appropriate to their scope, candidate set, and methodology. A title missing from a list is not automatically its lowest-ranked item. Do not aggregate positions from different-length lists or nested aggregators without an explicit method and treatment of dependence.

Agents propose criterion scores with explanations, citations, and uncertainty; the owner controls criteria and weights and can review or override values. The Python scoring module computes the final weighted score. Preserve criterion definitions, assessment versions, weight versions, source provenance, and prior published results. New research must not overwrite personal overrides.

Until criteria are agreed, a requested research phase may collect sources, identify candidates, compare existing lists, and document arguments. Leave final criterion values, weights, scores, and personalized rank positions unset. Do not invent preferences to finish a ranking.

Use the target's agreed criteria and scope. Different item types or subjects can use different criteria. A philosopher's rank is not implicitly an average of their works. Rank intellectual works separately from editions/translations unless editions are explicitly the target.

## Importing a named existing list

When the task is a faithful import of a specific publisher list or classics collection, verify that original source and edition, preserve its order or unranked status, and resolve catalog identities. Importing its stated contents does not require inventing 50 sources to validate the publisher's own ordering. The 50-source rule applies when researching or synthesizing a target ranking, including a personalized reassessment of an imported collection.

Keep the original list distinct from personal reordering or weighted views. Store source links and original summaries rather than copying entire publisher descriptions. Represent volumes, selected excerpts, and grouped works accurately when a collection needs them.

The three app sections map to explicit database values:

- Researched rankings: `origin=curated`, with separately gathered target evidence and an explained synthesis.
- Published rankings: `origin=external`, `presentation=ranked`, keeping exact publisher positions (Guardian).
- Reading collections: `origin=external`, `presentation=unranked` or `reading_sequence` (McEvoy, monthly lecture programmes, Great Books). Reading order does not imply merit rank; `source_rank` stays null for these collections.

The existing `import_research` command imports evidence only into a curated target. It does not import publisher entries, catalog works or final assessments. For a requested faithful-list import, use a reviewed idempotent Django import or the editorial administration/API, with a database transaction and revision snapshot. Resolve work/author/edition identities before insertion, retain source URLs and original positions, and never fabricate missing entries. Choose the exact Great Books edition and resolve McEvoy month-to-book assignments when needed. If those choices are unresolved, progress other requested research and save the unresolved mapping instead of guessing. Faithful publisher ordering does not require the owner's personal scoring criteria.

## Research deliverables

Produce a target brief, evidence ledger, candidate/claim-to-source mapping, source-diversity audit, synthesis, unresolved issues, and the requested draft assessments/ranking when its criteria are defined. Show at least:

- Eligible unique-source count for each target and whether it meets the hard minimum of 50, plus the depth achieved beyond that floor, remaining useful evidence and the rationale for stopping. Aim for many, many more than 50.
- Counts by source family and domain/platform, with dependence or concentration explained.
- Access limitations, excluded duplicates, and important gaps or disagreements.
- Evidence for each candidate's proposed assessments, without implying every source supports every candidate.
- Methodology and preference versions, proposed changes from the prior result, and preserved overrides.

Database entry creation, source imports, and publication follow the current task's authorized scope. Reading this skill does not itself start ranking population. Ranking entries stay empty until their evidence and methodology are ready. Consult `docs/RESEARCH_QUEUE.md` for requested scope, length, country and English-edition rules. Preserve separate books-only, literary-fiction, nonfiction and mixed-form lists.

Every ranking records update and research dates. Metadata edits, weight changes and failed or partial refreshes must not reset `last_researched_at`. Save each research run separately, preserve previous published versions and personal overrides, and record the proposed changes. See `docs/RANKING_FRESHNESS.md`.

Before handing over, update the target's `RESEARCH.md`, the research queue and root `HANDOVER.md` with the counts actually persisted, completed candidates/assessments, limitations, and the next useful source families or decisions. Do not leave progress solely in the chat. Research can stop at an honest saved partial state when the session ends; the next chat should be able to continue without repeating consulted sources.


## Separate-agent Word handoffs

For a copy-paste brief that works outside this repository, use [EXTERNAL_AGENT_RESEARCH_BRIEF.md](../../EXTERNAL_AGENT_RESEARCH_BRIEF.md). The owner prefers a complete Word `.docx` with report, source register and candidate records; JSON is optional. When receiving the output, use [EXTERNAL_AGENT_RESULTS_INTAKE.md](../../EXTERNAL_AGENT_RESULTS_INTAKE.md) to extract all sections and hyperlink targets, preserve the original, reconcile IDs, audit evidence and persist supported records. Do not require the owner to manually convert Word into JSON.

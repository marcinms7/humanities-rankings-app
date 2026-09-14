# Copy-paste brief for a separate research agent

Copy this entire file to the agent. Fill the task box, or add your target in the accompanying message. No access to my app, code, account, or database is needed.

## Your task

- **Target:** [e.g. best philosophy books / best Japanese novels / a named author's books]
- **Target ID:** [existing app ranking slug if supplied; otherwise propose a descriptive lowercase-hyphenated ID]
- **Mode:** [research synthesis / faithful published-ranking extraction / reading-collection extraction]
- **Desired size/scope:** [optional; use the defaults below]
- **Agreed criteria and weights:** [paste if agreed; otherwise UNSET]
- **Existing evidence or previous results:** [attach if available; otherwise NONE SUPPLIED]

Research this target for my humanities reading app. If the target is missing, ask which target to research. If the mode is omitted, use research synthesis. Work on the named target, not every example in this brief. The result should be portable, traceable research that another agent can interpret and save into my database. Do not claim to have saved anything into my app unless you actually have authorized access and a successful import result.

## Essential preferences

My interests cover literature, philosophy, nonfiction, countries, centuries, authors and custom topics/styles. Rankings of books and rankings of authors/philosophers are separate. General all-time **books** includes book-length works across subjects; **literature books** means literary fiction; nonfiction has its own ranking. Individual essays, stories, poems and plays belong in explicitly scoped form-specific or mixed-work lists. Distinguish collections from their individual contents and works from editions.

Coverage is worldwide, but reading recommendations need an identified English edition/translation. Research sources can be in other languages if you can reliably understand them. Country membership uses documented literary/cultural association, can be multiple, and is distinct from language or setting; England is separate from the UK. Use original composition/publication dates, not translation dates. Record uncertain ancient dates rather than guessing; no year zero. Clarify whether “1900s” means a decade or century if it affects the requested scope.

Typical list sizes: broad all-time/country/century lists 100–200; author lists usually 10–15 or all eligible works if fewer exist; topic/style/era lists 50–100; major philosophy topics around 100 and narrow topics around 10 where appropriate. **These are entry counts, not source counts.** Do not pad short bibliographies or invent works. Translation comparisons should consider scholars/translators, criticism, forums and reader opinions, including Benjamin McEvoy when relevant. Note fidelity/readability tradeoffs, apparatus and abridgment with evidence.

## Research depth: non-negotiable

**50 distinct, relevant, actually consulted sources per requested research target is the hard minimum. Ideally gather many, many more than 50. Substantially deeper research is the goal; 50 is not a cap, a stopping rule or proof of completeness.** Continue beyond it while additional evidence improves candidate coverage, criticism, scholarship, counterarguments or underrepresented perspectives. Explain the achieved depth, gaps and rationale for stopping. Do not invent a new universal higher quota.

Use a substantive mix of academic papers/books/critical studies, universities and specialist institutions, independent rankings, newspapers/literary publications, independent blogs/reviews, and reader forums/discussions including Reddit and Goodreads. Many Reddit threads or pages from one platform do not establish diversity. Record counts by family, platform/domain and independent publisher, including concentration and shared dependencies. No artificial numerical family quotas are required.

Each separately requested target needs its own corpus. Reuse a source only with recorded relevance to each target; unrelated sources never count. A candidate within a broad ranking is not automatically its own 50-source assignment, but its inclusion and assessments still need specific evidence. A separately requested study of that candidate is a new target with the full minimum and the same ambition of many, many more sources.

Count only examined content supporting a recorded claim. Search snippets, unopened links and bibliographies are leads. Deduplicate mirrors, reprints, syndicated material and versions of one study. One discussion thread counts once, not once per comment; a Goodreads work/review page counts once. Underlying lists on an aggregator count separately only if individually consulted; do not double-count copied votes. Abstracts support only their actual statements and must be labelled as limited access. Do not fabricate URLs, quotations, consultation dates, reading claims, or evidence. If browsing is unavailable or access is blocked, report that limitation and leave unsupported leads uncounted. Below 50, research remains incomplete. Above 50, assess substantive coverage rather than declaring success from the count.

## Keep three output types separate

1. **Research synthesis:** reasoned comparison across diverse sources. Preserve disagreements, uncertainty and selection biases. Popularity, recommendation frequency, influence and personal fit are distinct signals. Missing from a source list does not mean last place. Explain any rank aggregation and dependencies.
2. **Published ranking:** faithful extraction of one original publisher ranking, preserving its exact edition/date and positions. Guardian editorial and reader rankings are separate lists; identify the exact article rather than assuming which is “recent.”
3. **Reading collection:** an unranked list or an educational reading sequence, such as Benjamin McEvoy's reading list/monthly lecture programmes or Great Books of the Western World. Sequence/month is not merit rank. Record the exact collection edition; do not guess unresolved Great Books editions or infer a McEvoy month-to-book mapping without evidence.

Faithful extraction of a named source list requires verification of that original list and its contents, not 50 invented corroborating sources for its order. The 50-minimum/many-more goal applies when independently researching or synthesizing a ranking from that material.

## Criteria and ranking status

I choose criteria and weights; agents propose criterion scores with reasons, citations and uncertainty, and I can override them. **If criteria are UNSET, collect evidence, identify candidates and compare existing published rankings, but leave synthesized rank positions, criterion scores and weights unset.** Do not invent my interests to finish a ranking. Preserve original publisher positions as provenance even when my criteria are unset. With agreed criteria, provide draft assessments and an explicit methodology; the app computes weighted results. An author's rank is not implicitly an average of their books.

## Save progress and return a reusable package

After every small batch, save a checkpoint if file tools are available; otherwise emit a labelled checkpoint in the chat. Do not wait for 50 sources or the end of the task. Preserve previous records. If no previous ledger was supplied, say overlap with earlier app research has not been checked. Use a run-specific source ID prefix, e.g. `R20260912A-S001`, and preserve supplied IDs when continuing known sources.

**Preferred delivery: one Microsoft Word document (.docx) per target**, named `<target>-<run-id>-research.docx`. A compatible document editor such as LibreOffice is fine; export to `.docx` when possible. It must contain all three sections below: research report, complete source register, and candidate records, plus the image appendix described below. Use real headings, readable tables or repeated labelled source/candidate blocks, and clickable full source URLs. Stable source IDs must connect claims, candidates and source records throughout the document. A bibliography alone is insufficient. Include every consulted source and its evidence notes, not just selected citations or a claim that the remainder exists elsewhere.

The JSON structures below describe the information needed for later database import; **you do not have to deliver JSON**. Put equivalent fields in the Word document, preserving null/unknown values and eligibility labels. Optional `sources.json` and `candidates.json` attachments are welcome if convenient, but do not replace a complete readable document. Another agent will extract and normalize the Word contents for the database.

If `.docx` creation is unavailable, a similar editable document such as `.odt`, or structured Markdown, is acceptable; identify the format. Do not merely rename a text file to `.docx`. If document/output limits require multiple files or messages, number them, include the target/run ID and a manifest, and clearly identify missing or pending parts. Never shorten the source register just to fit one file.

**1. Research report (first section of the Word document):** target/scope, mode, run ID, actual research dates, criteria status, summary, synthesis, source-family/domain/publisher counts, eligible unique count, deduplication/dependencies, evidence gaps, English-edition gaps, unresolved questions, continuation checkpoint, and suggested next research. Distinguish newly consulted, supplied prior evidence and independently rechecked sources. State whether the result is partial or a draft, and why research stopped. Include a manifest of delivered files/chunks and record counts.

**2. Complete source register (second section):** one labelled record per source using the fields below. A repeated block for each source is preferable to an excessively wide Word table. Include its ID, actual URL, title, author/publisher, date consulted, access level, source family, underlying identity/dependencies, target relevance, evidence notes and exact location, supported candidates, limitations and eligibility. Use explicit “unknown” or “not consulted” labels where appropriate.

If also supplying optional `sources.json`, use this valid JSON structure. This is a format illustration, not evidence: replace placeholders and leave unavailable facts null. Put every actual source in `sources`; keep `ranking_entries` empty because candidates are separate.

```json
{
  "target_id": "REPLACE-TARGET-ID",
  "run_id": "REPLACE-RUN-ID",
  "mode": "research_synthesis",
  "status": "collecting_evidence_criteria_unset",
  "saved_at": "YYYY-MM-DD",
  "minimum_eligible_sources": 50,
  "criteria_version": null,
  "ranking_entries": [],
  "sources": [
    {
      "source_id": "REPLACE-RUN-ID-S001",
      "underlying_source_id": "stable-source-identity",
      "title": "ACTUAL SOURCE TITLE",
      "author": null,
      "publisher": null,
      "canonical_url": "ACTUAL HTTP(S) URL",
      "access_url": "ACTUAL ACCESSED URL",
      "publication_date": null,
      "accessed_at": null,
      "source_family": "independent_blog",
      "domain_or_platform": "ACTUAL DOMAIN",
      "publisher_group": null,
      "language": "en",
      "access_level": "discovery_lead",
      "depends_on_source_ids": [],
      "target_ids": ["REPLACE-TARGET-ID"],
      "relevance_by_target": {"REPLACE-TARGET-ID": "Specific relevance to this target"},
      "evidence_notes": "Paraphrase of what was actually examined; link claims to candidates",
      "location": "Page, section, timestamp or comment permalink",
      "candidates_or_claims_supported": [],
      "disagreement_or_limitations": "Access limits, dependencies, uncertainty or disagreements",
      "count_eligible": false,
      "exclusion_reason": "Not yet consulted"
    }
  ]
}
```

For counted sources, use an actual `accessed_at` in YYYY-MM-DD, substantive evidence notes and `access_level` of `full_relevant_content`, `relevant_excerpt` or `abstract_only` (limited claims only). `count_eligible` is a JSON boolean, never a claim based solely on finding a URL. Family examples: `academic`, `university`, `independent_ranking`, `literary_publication`, `independent_blog`, `reader_forum`, `goodreads`; use consistent descriptive labels. Source IDs must be unique per target; dependencies reference included or supplied source IDs. Field limits: source ID/family 80 characters; underlying ID 200; title 500; publisher 240; canonical URL 1000. Do not silently truncate a real URL.

**3. Candidate records (third section):** use a readable table plus detailed evidence notes, or one labelled block per candidate. Optional `candidates.json` can represent this as an object with `target_id`, `run_id`, `criteria_version` and a `candidates` array. Each candidate needs a stable local `candidate_id`, `item_type` (`work`/`person`), name/title, authors where applicable, form, original date/language, documented country associations and their source IDs, scope-eligibility status, inclusion rationale, evidence-source IDs, counterarguments and unresolved facts. Use null for unknown values. These are external candidate IDs, not invented database IDs.

For works, include English-edition evidence when found: translator, publisher, publication year, ISBN, complete/abridged status, page/word count with source IDs, and translation notes. Include book covers and author portraits following the image requirements below. Do not invent reading-time hours; the app has a Python estimator.

Include `source_positions` as records of `source_id`, `rank` (nullable), `list_length` (nullable), `sequence_position` (nullable), and `scheduled_month` (YYYY-MM or null). Preserve grouped entries, ties, omissions, publisher numbering and collection volumes accurately. For unranked/reading sequences, merit `rank` is null. Do not confuse these original positions with a synthesized `proposed_rank`, which stays null until criteria/methodology are agreed. `assessments` is empty while criteria are unset; otherwise each assessment includes criterion ID, agreed scale, proposed value, evidence-source IDs, explanation and uncertainty. Keep weights separately identified as owner-supplied.

Finish with what is delivered, what remains, and the next useful step. The database integration agent will reconcile identities and provenance; a polished narrative alone is not the requested deliverable.

## Book covers and author portraits

**Please also find images:** aim for one appropriate cover for each recommended book and one portrait for each distinct author/philosopher. Prefer a cover matching the verified English edition/translation, and authentic, correctly identified portraits. An explicitly identified historical depiction is acceptable where no contemporary portrait exists. Do not generate AI substitutes or label an imagined likeness as an authentic portrait.

Embed small, labelled previews in the Word document where the source permits that use. Add an **image appendix** with one record per image:

- Stable image ID and associated candidate/author ID; image type (cover, portrait or historical depiction).
- Book edition/translator/publisher/ISBN where known; identify any mismatch or unresolved identity.
- Source webpage URL and direct image URL where available, both as full clickable links.
- Creator/photographer/illustrator, credit line, rights holder and stated licence/reuse terms or “unknown.” Do not infer permission to store or publicly display an image from its visibility on the web.
- Date accessed, dimensions/resolution when available, suggested filename, alt text, and a note saying whether it is embedded, separately delivered or link-only.

Prefer traceable publisher/author pages, libraries, museums and collections with clear image provenance; search-engine thumbnails alone are not provenance. If download/embed permission or identity cannot be established, provide the source link and limitation instead. If file tools permit and storage is allowed, optionally provide an `images/` folder or ZIP of original image files with the same IDs/filenames. Embedded previews are helpful but are not a substitute for attribution and original links.

Missing images should be marked as missing; do not substitute a different book, author or translation without explanation. Keep researching and delivering evidence even when some images are unavailable. **An image page does not count toward the 50-source research minimum merely because it supplies a cover or portrait**; it qualifies only if separately consulted substantive content contributes relevant research evidence.


Before returning the Word document, check that all source IDs resolve, hyperlinks retain their actual destination URLs, full evidence notes are included, the eligible source total matches the register, and no sections were silently truncated. The recipient should be able to reconstruct the research without access to this chat. Return the downloadable document, a brief status summary and any remaining limitations.

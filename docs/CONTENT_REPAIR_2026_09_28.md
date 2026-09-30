# Catalog repair and verification, 28 September 2026

This continuation follows the owner's request to perform the remaining work, including the previously deferred checks. Current counts are generated in [CURRENT_STATE.md](CURRENT_STATE.md); the [completion receipts](../research/_runs/2026-09-28/completion/) distinguish applied changes from unresolved lookups.

## Applied identity repairs

- 359 reversed title/author pairs were corrected against exact lines in the preserved history and horror reports. Existing canonical identities were used only when unambiguous and without collapsing positions. Shared entry IDs and source ranks were retained; private references were untouched.
- 18 records with multiple contributors, editor roles or series scope received a separate review. Two initially abbreviated author lists were subsequently completed from publisher/library records. The full and brief *Ancient Greece* textbooks remain distinct, and the Cambridge multivolume histories are not attributed to invented people.
- 19 further annotated history records were corrected after checking date, translation and primary-source annotations. Ronald Syme's book *Tacitus* was explicitly distinguished from Tacitus as author of *The Annals*.
- An older repair had already redirected 30 horror entries but left their editorial order/explanation IDs pointing at archived records. Both arrays were reconciled against the current identities and a new revision saved. All 66 curated targets now have complete, duplicate-free editorial permutations of their active entries.

These are 396 newly corrected records in this continuation, in addition to the four initial maintenance repairs. The 30 historical order-reference corrections are separate. This does not certify every identity in the catalog.

The history/horror parsers now respect each report's column direction. Regression checks use the actual preserved reports. Generated candidate/catalog/selection inputs were reconciled; previous input files and SHA-256 manifests are retained under `completion/pre-repair-generated-inputs/`. Earlier import receipts remain historical. Do not rerun old publication payloads against a newer revision.

## Evidence and editions

Six locally examined bibliographic sources were appended to `history-books-ancient-world/sources.json` and imported. They verify contributor roles, series scope and specific editions. They are explicitly **ineligible as independent merit judgments**, so the target's eligible count remains 230. Existing reported consultations were retained.

Publisher/library records identify English editions for *The Oxford History of Ancient Egypt*, *The Rise of Civilization in India and Pakistan*, *Ancient Egypt: A Social History* and the full fourth edition of *Ancient Greece*. Numbered page counts are recorded only where the examined record supplies them; preliminary and unnumbered plates are distinguished in notes.

`research/enrich_exact_english_editions.py` collected 96 ISBN-specific English candidates from matched Open Library work/edition records. The audit found unreliable scope/pagination, including shortened texts and individual volumes linked to broader works. **All 96 automated candidates were retained as archived review records**, invisible in the reader's edition choices, pending publisher/library confirmation. Their original provider records remain in `research/_runs/2026-09-28/exact-editions/outcomes.jsonl`; the disposition receipt is `completion/edition-candidate-review.json`. The collector now stages archived candidates by default. No existing default, library choice, progress or plan assumption was changed. The four directly checked publisher/library edition records remain available.

## Images and page enrichment

Corrected identities have been processed through bounded cover/page batches. Work-level page medians remain labelled estimates; representative covers remain distinct from edition-matched images. Outcomes and operational queue state are persisted after each item.

`research/enrich_catalog_portraits.py` requires a matching catalog work or a ranked philosopher's corroborating biography, a Wikidata human identity and a credited Commons image. It retains file metadata and credits, labels historical depictions, uses standard thumbnails and stops on HTTP 429 with a persisted cooldown. Wikimedia repeatedly rate-limited image requests; unresolved portraits are not replaced with generic/generated images. A completed or stopped run is not an automatic background schedule.

## Verification

- 44 backend tests and 13 domain/queue tests pass, including the corrected bootstrap expectation, shared-reader permissions, edition transitions, grouping and report parser regressions.
- Automated browser checks passed against an isolated SQLite copy: edition preview/apply (50/200 to 100/400), country-copy editing/reordering, grouped public sharing, and a 390-pixel mobile layout without horizontal overflow or JavaScript errors. No test user or book was created in the live database.
- The live account, private preferences, library, reading history, adjustments and plan match the pre-continuation backup `manual-20260928T193031987090Z` exactly. All eight deletion guards remain; SQLite integrity and foreign-key checks pass. The reproducible read-only audit is `research/audit_maintenance_completion.py`.
- System/migration checks pass. The prior frontend build/static collection remains applicable; this continuation did not change frontend source. Docker/PostgreSQL and hosted operations have not been tested.

## Saved batch totals

Compared with backup `manual-20260928T193031987090Z`, the active catalog gained **208 default covers, 86 portraits and 267 default page counts**. Page estimates retain their uncertainty labels. Four publisher/library-identified editions remain available; 96 automated candidates are archived pending confirmation. The saved checkpoint contains **2,219 missing default covers and 5,565 missing portraits**. All workers are stopped at durable checkpoints; no automatic continuation timer is installed.

Post-continuation SQLite/media backup: **`manual-20260928T201243979775Z`**. The [summary receipt](../research/_runs/2026-09-28/completion/summary.json) and [final integrity audit](../research/_runs/2026-09-28/completion/final-integrity-audit.json) record the actual saved outcome.

## Still incomplete

The complete catalog is not fully illustrated or edition-verified. The current checkpoint lists the remaining records, including active ISBN-specific options separately from default-edition gaps. Archived automated candidates are excluded from those active-option counts. Bibliographic-source imports do not resolve comparative judgments. The app discloses matching standing/reading orders; a separately argued reading-value assessment is still needed where the same supplied order is used. No different order or personal numerical assessment was fabricated to make this task appear complete.

The reviewed history imports also contained a generic `literature` field. This was corrected to `nonfiction` on 255 identified history works and in their generated catalog inputs; reading-effort assumptions were preserved. Queue checks now exercise terminal outcomes, fair selection of unattempted records, three-attempt retry exhaustion, exclusive worker locks and lossless audit rotation/reconstruction.

A read-only media audit opened and verified all 6,392 active edition/portrait image references present at that checkpoint; no missing or invalid image files were found. This verifies stored files, not the identity of every historical image assignment.

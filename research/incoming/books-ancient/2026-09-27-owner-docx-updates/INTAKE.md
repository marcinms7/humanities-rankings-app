# Owner DOCX research intake — 27 September 2026

Processed eight supplied Word documents for seven rankings. Original files, SHA-256 hashes, all paragraphs/tables and hyperlink destinations are preserved under each target's `research/incoming/<target>/2026-09-27-owner-docx-updates/` directory. Document text was treated as research data, not as instructions overriding the owner's request.

The owner's requested operation was file ingestion with overall structural/identity checks, not source-by-source web verification. New consultation/access claims are recorded as externally reported. No new online research, browser automation, application test suites or account changes were performed.

All existing source IDs, URLs, evidence, eligibility flags and archive state were preserved exactly. New sources were merged by target-local source identity and normalized URL; duplicate incoming IDs/URLs were mapped to retained canonical IDs. Additional report reviews of old sources were appended to metadata. No existing source was deleted, archived, demoted or overwritten.

| Ranking | Entries before → after | Added / superseded entries | Sources before → after | Added source records |
|---|---:|---:|---:|---:|
| Ancient works · All time | 130 → 150 | +20 / 0 | 221 → 353 | +132 |
| Top 3 books by country | 617 → 617 | +0 / 0 | 1395 → 1707 | +312 |
| Philosophy books · All time | 250 → 250 | +41 / 41 | 256 → 622 | +366 |
| Literary fiction · All time | 250 → 250 | +69 / 69 | 101 → 451 | +350 |
| Philosophers · All time | 23 → 297 | +274 / 0 | 100 → 517 | +417 |
| History books · All time | 234 → 266 | +32 / 0 | 200 → 609 | +409 |
| Comics and graphic novels · All time | 250 → 250 | +1 / 1 | 827 → 1178 | +351 |

## Reconciliation and limits

- Philosophers: the complete 297-person report supplies the displayed standing/reading orders. The alternative 189-person report is preserved, and its nonduplicate evidence is merged. Both retain the original 23 philosophers.
- Ancient works: expanded to 150. The report contains cross-wired bibliographic/rationale fragments (for example, Horace/Odes details on the Analects row). Those fragments did not overwrite catalog metadata. Orders were matched by title AND author, and explicit source-to-candidate mappings were recovered from the source register. New entries retain provisional notes and supplied attribution; anonymous/collective works do not receive invented people.
- Top-three country selection: all 208 sections, 624 placements and 617 distinct works retained. Local standing orders, confidence notes, candidate-source mappings and separate local reading positions are saved. Historical section source bundles remain alongside candidate-specific evidence. The existing interface displays local standing order; the new local reading positions are preserved in grouped data and report artifacts.
- Philosophy books and literary fiction: reports propose replacements while preserving displaced records. Superseded ranking entries were archived, not deleted; catalog records, source records, previous revisions and private references remain intact. Both active orders contain 250 items. All 250 separately supplied philosophy reading rationales are persisted.
- Comics: Gasoline Alley replaces The Many Deaths of Laila Starr in the active 250; the displaced catalog work, historical ranking entry and evidence remain saved.
- Exact-source URL reconciliation changes register totals relative to naive sums of the documents' claimed totals. Added record counts include noncounting supplementary/limited-access records; reported qualifying additions are recorded separately in `final-summary.json`. Counts are not a new independent research certification.
- Six explicit catalog form repairs distinguish complete story collections from individual stories and identify two novels correctly. No existing editions, covers, portraits or author credits were overwritten. Additional report-level bibliographic/creator corrections remain visible in the candidate records; they were not blindly applied to shared catalog objects.
- New catalog identities have edition/media tasks outstanding. Existing metadata was preserved. Personal criteria/weights/scores remain unset and research-completion/source-check dates were not reset by the intake.

## Preservation and artifacts

Pre-import database/media backup: `data/backups/manual-20260927T220522217168Z.*`.

Run artifacts: `research/_runs/2026-09-27/owner-docx-updates/`. These include extraction delivery manifest, normalized reports, reviewed import plan, exact source/candidate ID maps, per-target import receipts, source additions and final summary. Each target's `sources.json` was merged from the resulting database, with the previous file saved before replacement. Full raw report records remain in source metadata and candidate artifacts.

Verified: every prior source's stable fields are unchanged; both editorial orders cover their full active candidate sets; candidate source references resolve; all country placements and historical source bundles remain; private-table fingerprints match; SQLite foreign keys and all eight deletion guards are intact. These are import-integrity checks, not source-by-source validation or app test suites.

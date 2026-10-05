# Media pipeline improvements — 5 October 2026

**Later morning correction:** the owner challenged the poor portrait coverage. [The follow-up](PORTRAIT_COVERAGE_FIX_2026_10_05.md) records real-data defects missed by this pass, their fixes and the measured increase. The earlier tests/counts below are historical; they did not establish adequate coverage.

The owner approved all six improvements from the [30 September review](MEDIA_PIPELINE_REVIEW_2026_09_30.md). Implementation resumed after interruption and is now saved, validated and running. This completes the software changes; it does not complete the catalog's image backlog.

## Implemented behavior

1. **Unicode and library-name matching.** Shared matching preserves non-Latin names, folds Latin accents, handles inverted library headings and life-date suffixes, and supports compatible initials and saved verified aliases. Partial titles, unrelated authors and ambiguous author identities are rejected.
2. **Automatic provider recovery.** Provider outages have a separate queue state and no longer consume individual matching attempts. Persistent cooldowns and exponential backoff allow sparse one-record recovery probes. Other providers continue. Corrected publisher/identity/edition inputs reopen relevant lookups; stale rows for covered records cannot suppress pending retries.
3. **Identifier and candidate reuse.** Workers reuse valid stored ISBNs and Open Library IDs, rechecking remote title/author identity. Public responses and verified candidate lists survive restarts. Broken images advance to bounded alternatives, including additional Open Library photos and Wikidata images. Downloaded images must pass format/dimension checks and pixel decoding before saving.
4. **Library sources.** Library of Congress JSON and BnF/Gallica SRU/IIIF adapters support covers and portraits. Portraits need identity corroboration beyond a bare name. Gallica historical bindings, title pages and depictions are labelled explicitly and retain source/rights evidence.
5. **Targeted publisher metadata.** Known publisher pages and limited publisher/ISBN-specific discovery routes use structured Book metadata, title/author checks and available ISBN agreement. Exact host allowlists, robots rules, public-address validation, redirects, request spacing and size limits apply. Credential-bearing source links are rejected. Goodreads scraping is not included.
6. **Useful priority and live reporting.** Fresh gaps in shared lists precede other fresh records; item retries cannot starve untouched records. Counts refresh after every batch. `--status` checks the process lock and current database/files, including actual pixel decoding. Missing, invalid, ambiguous, blocked and unattempted records remain distinct in the unresolved report.

The runner guide documents [commands, provider names and limits](CATALOG_MEDIA_COMPLETION.md). Existing images and selected editions are preserved. Saves recheck current catalog identity, edition ownership and applicable shared-ranking membership. Cover-only display editions explicitly retain unknown bibliographic metadata. No personal reading data, ranking order, source position or numerical assessment is inferred from an illustration.

## Validation and real-provider results

**304 backend tests and 125 domain tests passed (429 total)** using temporary SQLite, media and search storage. This includes provider fixtures, public-address/redirect/robots/cache checks, outage recovery, truncated JPEG rejection, candidate fallback, Unicode names and private/edition preservation. Django system checks, migration-drift checks, Python parsing/compilation and whitespace checks passed. No migration was needed; the existing database remains at **0019**. No browser automation or frontend changes/build were needed for this pass.

Read-only provider trials during implementation found a valid Gallica historical binding (600×836), a corroborated Victor Hugo depiction (600×713) and a matched Penguin Random House cover (274×450). These probes downloaded valid JPEGs into temporary caches and did not replace catalog images. Library of Congress returned HTTP 403; successful live acceptance from that API remains unverified.

On 5 October, a bounded runner trial exercised all five new provider paths against actual missing catalog records: five Gallica portrait records, five Gallica cover records, five publisher cover records and one deferred record for each LoC path. **No safe images were accepted in that small trial.** LoC's denial entered cooldown; the cover path reused the host cooldown instead of repeating the denied HTTP request. Receipt: `data/operations/media-provider-trial-2026-10-05.json`.

The unrestricted background runner was then restarted. Its lock and advancing heartbeat were verified, and it saved a new Open Library portrait for **P. F. Strawson**, corroborated by *Individuals: An Essay in Descriptive Metaphysics*. Google Books is `credential_required` because `GOOGLE_BOOKS_API_KEY` was absent; no anonymous requests were sent. Wikipedia returned HTTP 429 during the resumed pass and was deferred. Provider availability is reported separately from match exhaustion.

## Saved state and preservation

File-decoded live snapshot at **00:12:30 UTC on 5 October**:

| Active catalog | Ready files | Missing images |
|---|---:|---:|
| 8,491 works, default covers | 6,532 | 1,959 |
| 5,685 people, portraits | 1,066 | 4,619 |

All referenced default covers and portraits in that snapshot decoded successfully. Shared lists still contained **1,898 missing covers and 69 missing ranked-person portraits**. The worker was active, processing the public cover queue after three completed provider batches. These are dated counts; `./scripts/complete_catalog_media.sh --status` is authoritative for later progress. Receipt: `data/operations/media-live-status-2026-10-05.json`.

By the **00:15:50 UTC** handoff checkpoint, the restarted worker had saved **seven covers and two portraits**. Coverage was **6,539/8,491 covers and 1,067/5,685 portraits**, leaving 1,952 covers and 4,618 portraits (1,891 shared-list cover gaps and 68 ranked-person portrait gaps). The process lock and current heartbeat remained active. Receipt: `data/operations/media-handoff-status-2026-10-05.json`.

Fresh pre-write snapshot: **manual-20261005T000054950466Z**, following the earlier implementation-start snapshot **manual-20260930T095421855466Z**. The runner also completed/reused **daily-20261005** before its writes.

A read-only comparison against the fresh snapshot checked **35 tables / 68,755 original rows**, repeated at **00:16:17 UTC** after the new cover writes. Private/account/reading/study data and shared rankings/revisions were unchanged. Permitted changes were two portraits, covers on two existing editions, and five new explicitly unverified display editions selected only for works that previously had no default edition. All **7,613 original media files** retained their SHA-256 hashes. Eight deletion guards remained unchanged, SQLite integrity passed and foreign-key checks returned no errors. Receipt: `data/operations/media-pipeline-preservation-2026-10-05.json`. No live test accounts or books were created.

The worker is intentionally left running. It persists accepted images and unresolved outcomes incrementally. Historical people, anonymous traditions, individual poems/essays and series may still lack a safe available standalone image; those records must remain explicit review tasks. Publisher coverage is limited by saved identifiers/source pages. Source attribution does not itself establish reuse rights, visual correctness or a verified edition. Do not reset queues or claim finished coverage from implemented adapters or a passing test suite.

# Media completion review — 30 September 2026

**Follow-up, 5 October:** the owner approved the six proposed improvements and they are now implemented. See [the implementation, validation and restart receipt](MEDIA_PIPELINE_IMPROVEMENTS_2026_10_05.md). The review-only findings and counts below remain a historical snapshot.

Read-only investigation requested by the owner: establish whether covers/portraits have finished and identify better APIs, matching and collection methods. No enrichment code, live database rows, queues or workers were changed by this review. The background process remained active. These are recommendations, not implemented improvements.

## Actual saved state

SQLite read-only snapshot at **09:39:30 UTC / 10:39:30 BST**:

| Active catalog records | Image referenced | Missing | Coverage |
|---|---:|---:|---:|
| 8,491 works, using their default edition | 6,532 | 1,959 | 76.93% |
| 5,685 people | 1,037 | 4,648 | 18.24% |

Every referenced cover/portrait file exists under local media storage. All have attribution; covers have a cover-specific or older edition source URL. This confirms file presence and recorded provenance, not visual accuracy, verified edition identity or image reuse rights. Images are files; the database stores their paths and related metadata.

Missing covers comprise 1,349 books, 331 collections, 119 poems, 103 essays, 40 plays and 17 short stories. Shared lists contain 8,237 unique active works, of which 1,898 lack covers. Researched lists contain 6,885 unique active works, of which 1,432 lack covers. Shared person rankings contain 297 people, of whom 71 lack portraits.

Among the 1,959 missing covers, 282 works have detectable Open Library identifiers in active-edition provenance/description; 11 have an ISBN on an active edition (none on the default edition). There are 1,674 without any active edition and no cases with an already-covered active alternative edition. Identifiers need validation before reuse; their presence is not proof that an image is available.

The runner advanced from 195 to 196 batches and from 1,163 to 1,164 additions during inspection. Portraits subsequently increased to 1,038. Active exclusive locks and advancing logs confirm ongoing work; process-table access was unavailable in the sandbox. Only the Open Library portrait worker was progressing. Google Books, Wikipedia covers and Wikimedia portraits were blocked after repeated failures; their saved failures include HTTP 429. The Open Library/Internet Archive cover queue was drained for the current policy: 1,893 unresolved missing works, 65 without credited authors and one exhausted transient failure.

`--status` reads saved JSON, and missing totals refresh only every ten batches or on normal shutdown. The currently running process predates the heartbeat code now on disk. Do not equate a stale `running` flag or exhausted queue with a fully illustrated catalog.

## Highest-value changes

1. **Separate provider outages from failed book matches.** In `complete_catalog_media.py:128–167`, three failed probes disable a provider for the rest of the invocation. `enrichment_queue.py:153–163` also consumes record retry budgets on provider errors. Use persisted provider cooldowns with sparse recovery probes, distinguish quota/authentication/service failures, and avoid consuming a book's match budget during a global outage. Preserve no-match decisions; reopen only eligible failed attempts after a provider/matcher change.
2. **Fix matching before broadening sources.** `enrich_catalog_covers_public.py:46–109` strips non-Latin text. Pure-function checks rejected identical Chinese and Cyrillic titles, identical Chinese author names, and Jane Austen versus “Austen, Jane” or “Austen, Jane, 1775–1817.” Alternative providers import these helpers. Use Unicode-preserving comparisons, parsed library name forms and verified aliases; keep ambiguity checks instead of accepting loose surname matches.
3. **Reuse saved identifiers and candidate responses.** Cover lookup items omit edition IDs/ISBNs and start with title/author searches. Validate existing Open Library provenance, cache matched work/author identities and reuse candidate metadata for subsequent image attempts. ISBN-first is useful where present, but only 11 currently missing works have any recorded ISBN; it cannot solve most of this backlog alone. Include relevant edition/identifier changes in queue fingerprints.
4. **Try the next valid image candidate.** The Google path returns the first matching volume with an image, and the Open Library portrait path selects the first photo. A missing/invalid image should advance to another verified candidate; a global rate limit should defer the provider. This avoids repeating the same broken image lookup and discarding other valid choices.
5. **Add complementary library sources.** Trial Library of Congress digital collections for identified portraits/historical material, and BnF/Gallica search plus IIIF for digitized books, title pages and historical depictions. Keep title-page/representative images labelled accurately. Evaluate a bounded sample of unresolved records and measure accepted images per request before a wider run.
6. **Use focused publisher-page extraction when appropriate.** Parse bibliographic JSON-LD or page metadata on a verified publisher page, checking title/author and ISBN where present. The legacy web fallback is not ready: `enrich_catalog_covers_web.py:83–86` compares a complete title-plus-URL string using an exact-title matcher and checks trusted hosts by substring. Replace those checks, validate the final page/redirect host and image, and retain source/credit. Respect each site's supported access methods and restrictions.
7. **Make progress reports distinguish causes.** Report fresh saved/file counts, unattempted records, provider-blocked records, ambiguous identities and genuine no-match outcomes separately. Keep useful image validation and transactional saves; prioritize books/people appearing in shared rankings before obscure catalog-only entries without permanently starving the rest.

## Current source options, checked against provider documentation

- **Already integrated:** Open Library and Internet Archive covers, Google Books, Wikipedia book covers, Wikimedia/Wikidata portraits and Open Library author photos. Legacy manga adapters exist separately; they are not jobs in the current completion runner.
- **Google Books:** the script supports `GOOGLE_BOOKS_API_KEY`, but the current run's saved requests returned 429. Official documentation requires an API key or OAuth identifier for public-data requests. Verify configured access/quota; a key is not a promise of unlimited requests. [Google Books documentation](https://developers.google.com/books/docs/v1/using).
- **Open Library:** use caching and supported batch/bulk access for this catalog-sized job. The API guidance discourages HTML scraping and bulk harvesting through individual requests; cover documentation directs bulk downloads to archives. Faster repeated single-item calls are not the appropriate optimization. [API guidance](https://openlibrary.org/developers/api), [cover access and bulk downloads](https://openlibrary.org/dev/docs/api/covers).
- **Library of Congress:** public JSON/YAML endpoints expose digitized items, image URLs and descriptive metadata, without an API key but with rate limits. This is a candidate for historical material, not a complete modern-cover catalog. [Documentation](https://www.loc.gov/apis/json-and-yaml/).
- **BnF/Gallica:** SRU searches digitized collections, and IIIF exposes image/manifest resources. Preserve item-specific reuse conditions and distinguish a scanned title page from a modern cover. [Search API](https://api.bnf.fr/fr/api-gallica-de-recherche), [IIIF API](https://api.bnf.fr/fr/api-iiif-de-recuperation-des-images-de-gallica).
- **Hardcover:** an additional API candidate requiring an account token. Coverage, image reuse/storage conditions and actual yield need checking before integration. [Official API entry point](https://api.hardcover.app/).
- **Goodreads:** not the first fallback to build. Its current robots file excludes automated search and API paths, and the old API page redirected to the homepage during review. No bulk Goodreads scraper was started. [Robots file](https://www.goodreads.com/robots.txt).
- **Wikimedia:** current documentation includes **500 px** among standard thumbnail widths. Current code already requests 500; old thumbnail-size error receipts must not be misreported as a current 500-pixel defect. [Standard sizes](https://www.mediawiki.org/wiki/Common_thumbnail_sizes).

Recommended first implementation: matching fixes, identifier/candidate reuse, provider recovery and accurate progress reporting; then small Library of Congress/Gallica trials and targeted publisher adapters. Preserve existing saved images, personal data, source credits and the distinction between a work illustration and a verified reading edition. No completion date or 100% image availability is established by this audit.

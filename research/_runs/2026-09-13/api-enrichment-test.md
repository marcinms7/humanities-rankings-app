# Book metadata and cover API trial

Tested before bulk enrichment to minimize network calls and agent processing.

| Service | Trial | Result | Decision |
| --- | --- | --- | --- |
| Google Books Volumes API | Title/author query for *Emma* | HTTP 429 in the current unauthenticated environment | Do not use for bulk work without an API key/quota and cached retry handling. |
| Open Library Covers API | ISBN `9780141180144`, large cover, `default=false` | Valid 386×500 JPEG returned | Preferred cover fallback when a specific ISBN has already been verified. |
| Open Library Search API | Sequential title lookups for unresolved Guardian works | Too slow; batch did not complete within two minutes | Do not perform naive one-request-per-title searches. Use resumable caching or verified ISBNs. |
| Goodreads | Metadata API availability review | No dependable current public books metadata API suitable for this importer | Use its public lists/pages as reader-ranking evidence, not as the catalog metadata service. |

Cover retrieval remains separate from title identity. A cover can be attached only after its ISBN/edition match and source attribution are recorded. Existing missing-cover work should use cached, resumable batches so a failed provider does not block ranking population.

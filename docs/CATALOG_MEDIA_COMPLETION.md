# Completing catalog covers and portraits

Run from the project directory:

```bash
./scripts/complete_catalog_media.sh --background
```

This starts a detached, resumable process with **no batch limit**. Keep the computer awake and connected to the internet. On macOS, `caffeinate -i ./scripts/complete_catalog_media.sh` instead runs in the foreground and prevents idle sleep while it runs. Closing a foreground terminal stops that foreground process; a background process continues, but neither mode survives a restart. Run the same command again to resume after a restart.

```bash
./scripts/complete_catalog_media.sh --status
tail -f research/_runs/media-completion/worker.log
./scripts/complete_catalog_media.sh --stop
```

A daily database/media backup precedes writes. Each accepted image is saved immediately. Existing images, personal reading records, notes, ranking orders, page counts and bibliographic verification are preserved. New cover-only display editions explicitly have unverified language/edition metadata.

The runner alternates Google Books covers, Open Library author photos, Wikipedia book covers, existing Open Library/Internet Archive covers, and Wikipedia/Wikidata/Commons portraits. Google Books supports an optional `GOOGLE_BOOKS_API_KEY` environment variable; the key is never included in logs. A key may be needed when anonymous quota is exhausted. No paid service is automatically enabled. Goodreads scraping is not implemented or claimed.

Cover matches require a matching title and credited author. Wikipedia fallback additionally requires a book infobox and a cover/first-edition caption. Open Library portraits require an exact or compatible full author name, a matching catalog work, and an unambiguous author record. Open Library credits identify the source but do **not** establish a reusable image licence or original photographer; these limitations remain explicit in image attribution. Commons metadata, licences and historical-depiction labels are retained. A representative cover never establishes a particular edition or page count.

Each provider has a durable queue. Unattempted records are processed before retries. Temporary errors receive bounded retries; rate limits create cooldowns while other providers continue. Three consecutive provider outage probes without an image addition block that provider for the remainder of the invocation, rather than wasting thousands of requests. Restart after the provider recovers. No-match results are retained, not retried forever. Corrected identity inputs reopen affected work automatically. The runner does not bypass rate limits, authentication or access restrictions.

Status `complete` means no missing covers or portraits. `needs_review` means automatic sources are exhausted or blocked **and records remain unresolved**. `stopped` is an intentional stop; `batch_limit` is only used when the optional verification flag `--max-batches N` was supplied. The default has no such limit.

`research/_runs/media-completion/unresolved.json` lists missing IDs, titles/names and provider outcomes. It updates initially, every ten batches and on a normal stop/completion. Per-image audit JSONL records, provider cooldowns and status are in the same folder; older Wikimedia portrait details remain in `research/_runs/2026-09-28/portraits/`. Operational queue indexes live in `data/enrichment/`. Logs rotate into verified compressed archives. Do not delete the queues to force retries: that discards progress and can repeat the original looping problem.

This runner exhausts supported sources; it cannot guarantee that an identifiable, available portrait or standalone cover exists for every historical person, anonymous contributor, poem, essay, or series. Such records remain explicit review tasks instead of receiving unrelated or generated images.

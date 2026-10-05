# Portrait coverage correction — 5 October 2026

The owner correctly challenged the low coverage after the earlier media implementation. At inspection the catalog still had only **1,070/5,685 portraits (18.82%)** and **6,564/8,491 covers**. The prior runner had added five portraits over roughly eight elapsed hours; thousands remained unprocessed. Passing software checks did not establish adequate coverage.

## Defects corrected

- Open Library author images can redirect through `archive.org/download/olcovers…` to numbered Internet Archive storage servers. The previous exact-host allowlist rejected that valid chain. A live Samuel Butler request demonstrated the rejection; the corrected chain saved his portrait. Only the explicit Open Library image policy permits `archive.org` and numbered `ia…us.archive.org` / `ia…eu.archive.org` storage hosts. Private-address, credential, redirect and image-decoding checks remain enforced. Lookalike domains and arbitrary archive subdomains are rejected.
- The Wikimedia philosopher occupation was mistyped as `Q496418`. The correct [Wikidata philosopher entity is Q4964182](https://www.wikidata.org/wiki/Q4964182). The earlier fixture repeated the typo, so its passing test missed the real-data failure. Both now use the verified identifier.
- Work corroboration rejected titles shorter than eight normalized characters. Titles such as *Ragtime* and *Loving* now qualify with exact casing and a nearby publication year; ordinary prose and two-letter generic words do not qualify.
- Exact person names could lead to Wikipedia disambiguation pages. The worker now tries bounded occupation-qualified page titles, retains human/work checks, and refuses unresolved competing identities.

## Existing evidence and processing

The audit found **2,615 missing-portrait people with saved Open Library book identifiers**. Portrait inputs now include linked works. The resolver rechecks remote book titles and author names before using author photos. An old URL or surname alone never establishes identity.

The new `linked-wikidata-portraits` provider follows verified work → author → Wikidata links. It requires a human entity and either a reciprocal Open Library ID or matching Wikidata name, rejecting conflicting reciprocal IDs. Images retain Commons attribution/licence metadata. Its first live batch deferred to an existing Wikidata cooldown; successful image ingestion from this provider has **not** yet been established. A later Wikidata recovery probe succeeded; image downloads still respect actual rate limits.

The runner allocates 60 records per Open Library portrait batch, 30 per linked-Wikidata batch and 15 per public-cover batch, alongside other sources. Request spacing, cooldowns and single-record recovery probes remain enforced. This gives the larger portrait backlog more processing time without increasing concurrency. Policy versions reopen relevant failed matches while preserving audit history.

Eight duplicate catalog identities were filled from existing credited portraits, requiring compatible full names, a shared exact work title and one unambiguous source person. Original attribution was retained; no people were merged or renamed. Receipt: `data/operations/portrait-duplicate-reuse-2026-10-05.json`.

## Saved result and verification

At **09:04:14 UTC**, file-decoded coverage was **1,093/5,685 portraits (19.23%)**, an increase of **23 portraits** in this follow-up. Covers remained **6,564/8,491**. Missing portraits numbered **4,592**, including **65** in shared person rankings. Additions included Samuel Butler, Xunzi, Donna Haraway, M. F. K. Fisher, Haruki Murakami, Banana Yoshimoto, Kenzaburō Ōe and Sophie Bósèdé Olúwọlé. This is a measured improvement, **not satisfactory or completed coverage**.

The unrestricted runner was restarted (PID 30136 at launch), with its lock/status confirmed. Use `./scripts/complete_catalog_media.sh --status` for current progress. Dated snapshot: `data/operations/portrait-followup-status-2026-10-05.json`.

**139 domain and 304 backend tests passed**, with backend database/media/search storage isolated. Additional focused runner and ingestion checks passed. No browser automation, migration or frontend changes were needed. Tests cover the real redirect-chain shape, lookalike/private host rejection, work-linked identities and conflicting IDs, short titles and disambiguation. API errors retain known diagnostic codes without logging arbitrary messages that could echo credentials.

Pre-write backup: **manual-20261005T084058025584Z**. Preservation checked **35 tables / 68,781 original rows** and **7,650 original media hashes**. Only 23 intended person illustration/attribution updates differed; private data, ranking history, existing images and eight deletion guards remained unchanged. SQLite integrity and foreign keys passed. Receipt: `data/operations/portrait-coverage-preservation-2026-10-05.json`.

Remaining constraints include rate limits, names/aliases and incomplete identities, missing source images and ambiguous people. Anonymous/group credits remain unresolved instead of receiving unrelated faces. Do not change the denominator or equate an implemented provider with achieved coverage. The worker continues saving supported images incrementally.

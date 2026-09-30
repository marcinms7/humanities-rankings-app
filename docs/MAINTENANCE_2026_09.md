# September maintenance: behavior and remaining work

Implemented 27–28 September 2026. [Current database checkpoint](CURRENT_STATE.md) contains dated counts; historical intake receipts remain intact.

## Enrichment

The legacy infinite supervisor was stopped. Its cover outcomes and supervisor log were gzip-compressed, reread to verify SHA-256, and retained with manifests in their original directories' `archives/` folders. No research outcomes were discarded.

`research/enrichment_queue.py` maintains reconstructible operational indexes under private `data/enrichment/`. Workers import the old ledger once, stream bounded active audit logs for crash recovery, prioritize unattempted work, and distinguish complete, unresolved, identity review, retryable and exhausted work. Transient failures get exponential backoff and at most three automatic attempts. Changing matching inputs/policy or explicitly requesting a retry creates a fresh attempt budget. Unresolved matches and missing authors require correction or deliberate retry; they do not spin forever.

The coordinator and workers hold separate exclusive locks. The coordinator reads structured batch summaries, stops after a bounded number of batches, records provider cooldowns, and accepts a cooperative stop. Public requests are throttled across worker threads. Safe matches require title and author agreement; surname-only matches and broad title-substring matches are no longer accepted. A final database check preserves an existing cover. Cover provenance is stored separately from bibliographic sources; new display-only editions explicitly say their language/edition is unverified. This is matching evidence, not a claim that every previously downloaded cover depicts the reader's exact printing.

```bash
./scripts/run_catalog_enrichment.sh both --max-batches 10
./scripts/start_catalog_enrichment.sh covers --max-batches 2 --batch-size 25
./scripts/stop_catalog_enrichment.sh
.venv/bin/python research/catalog_enrichment_status.py
```

Normal starts respect a recorded provider cooldown. Direct worker retry flags are deliberate operator overrides and should be scoped to reviewed records. A stopped run has no automatic timer: restart when provider access is available. The coordinator's PID in a completed status record is historical, not proof of a running process.

A restricted-network batch failed DNS and stopped in cooldown. A permitted three-record page batch reached the provider and retained all three as no safe match. A single-record cover batch added an attributed representative cover to the repaired *Pompeii* record. The later owner-authorized content continuation is recorded in [CONTENT_REPAIR_2026_09_28.md](CONTENT_REPAIR_2026_09_28.md); its bounded worker logs supersede these initial diagnostic results.

## Reading editions and personal copies

Reader ranking writes now require a personal list owned by the authenticated user. Staff have the same reader boundary; editorial administration/imports remain separate.

Country grouping and original local positions survive personal copies, shared links and exports. Personal order/membership editing has its own view; ungrouped additions remain visible. Removing a work removes all of that copy's country appearances. Historical source counts are not copied as fresh evidence. The backfill command only recovers missing grouping from the exact copied revision; no existing personal copies needed repair at this maintenance checkpoint.

Edition changes use `POST /api/library/{id}/edition-change/`: choose manual page, reset, same page or approximate percentage; preview first and apply with its signed, expiring token. Changed progress or edition metadata invalidates the preview. Percentage mapping requires both lengths and rejects differing abridgement flags. Translation/pagination differences still make it approximate. Generic library PATCH/upsert cannot silently change editions.

Migrations 0014–0015 add page/cover provenance, frozen reading assumptions and private adjustment receipts. Existing private records are explicitly labelled as captured at upgrade, not historically reconstructed. Future attempt snapshots preserve the recorded edition basis. A catalog length change raises a review flag instead of changing saved progress/history totals. Edition-change receipts are distinct from completed attempts and included in private exports.

Plans retain physical page allocations and frozen edition/effort assumptions. Unlock before explicitly accepting current assumptions; this changes the effort basis, not allocated pages. Suggestions, shortlist, classical planning, annual history and personal length filters use the saved basis. Reader pace remains adjustable and time estimates remain provisional.

## Provenance and catalog repair

Eligible source records are labelled as ledger classifications, with recorded consultation origin, access extent and evidence role. Unknown provenance remains unknown. Supplied reports and exact-URL reuse do not become independent votes. Matching standing/reading arrays are explicitly disclosed; positions were not invented to make them differ.

`manage.py reconcile_maintenance --apply` matched saved ledger edition IDs, work IDs and lengths before adding provenance: 3,627 cross-edition estimates, 454 ISBN-provider counts and 3,832 representative-cover references. Existing page numbers, private progress and allocations were unchanged. Later enrichment writes these fields directly. Unknown older provenance remains a tracked task.

`manage.py repair_reviewed_identities` previews four reviewed reciprocal title/author errors; `--apply` checks the expected identities, corrects them, preserves shared entry IDs/source positions, updates editorial arrays and saves ranking revisions. Existing canonical identities are used for SPQR and Tender Is the Flesh; Pompeii and The Roman Triumph retain their work IDs. Old duplicate catalog IDs remain archived and private references unchanged. Receipts are under `research/_runs/2026-09-27/maintenance/`. The older revisionless horror repair script is disabled and archived.

## Verification and outstanding work

Django system/migration checks, TypeScript/Vite build and static collection pass. Read-only SQLite integrity/foreign-key checks pass; all eight deletion guards remain. Original fields in private account/library/attempt/plan/preference/study tables match backup `manual-20260927T222105796513Z`. New snapshot fields are intentional. The owner subsequently authorized the deferred checks: **44 backend tests and 13 domain/queue tests pass**, and browser verification passed on an isolated database for edition transitions, country-copy editing/sharing and mobile layout. See [the continuation report](CONTENT_REPAIR_2026_09_28.md).

Edition preview/apply and country-copy/share flows were browser-verified in isolation; locked plan-assumption behavior is covered by backend checks. Docker/PostgreSQL deployment remains unverified. The earlier SQLite/media restoration rehearsal is documented in PUBLIC_RELEASE.md and does not validate PostgreSQL restoration.

Remaining editorial work is explicit in the [checkpoint backlog](../research/_runs/current-state/checkpoint.json): missing covers/portraits, unresolved identities, unverified editions/lengths, source-role/access gaps and independently supported reading-value judgments. Completing these requires evidence and reviewed batches; labels and software safeguards do not constitute completion of worldwide research.

Refresh the dated database report with `manage.py project_checkpoint` (or `research/refresh_checkpoint.py`). It does not rewrite historical publication receipts or perform database writes.

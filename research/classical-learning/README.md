# Classical learning and discovery — 14 September 2026

## Implemented scope

Four additions to the existing Classical education space:

- **Today's study:** route-aware next assignment, optional existing listening/course pairing, reflection question, due counts, private session journal. Full-assignment hours are never presented as a daily requirement. Logging a session changes no module/library/planner completion.
- **Recall & review:** 72 stable prompts (three for each of 24 modules), answers attempted before revealing syllabus-based review guidance, source links, retained attempt history and explicit reader-selected 1/3/7/14-day revisit intervals. This is a reminder policy, not a scientifically calibrated adaptive learning algorithm or an automated assessment. Server dates are explicitly UTC.
- **Historical atlas:** eight cards across six locations (Athens, Delphi, Troy, Rome, Pompeii, Carthage), separating historical places/events from Troy/Dido literary layers. Keyboard-accessible coordinate diagram and list, type/search/date filters, dates, authors/works via module links and citations. Rounded orientation markers, not borders, routes, a surveyed map or precise ancient city boundaries. Undated/mythic entries are excluded from dated filters.
- **Essay workshop:** question, thesis, argument, counterargument, response, conclusion, prose draft and manually verified bibliography; selected commonplace evidence snapshots; private saved revisions and individual plain-text export. No generated quotations or scores. Optimistic revision checks reject stale edits. All earlier snapshots remain in the full syllabus export.

Private state is additive under `ClassicalStudyProfile.state.learning`; the existing owner-only endpoint enforces access and validates individual actions. No new model or migration. Notes/session drafts remain mounted across subtabs and warn before page unload/link navigation. Saves do not alter shared records or personal scores. Journal/attempt/essay/revision caps reject excess writes rather than silently trimming history; see validators for limits.

## Atlas sources and limitations

Six official UNESCO site descriptions were opened for relevant historical/heritage passages on 14 September 2026. Direct URLs, access descriptions and dates are saved in `backend/core/content/classical_atlas.json`. This is study content, not an import into the classical ranking's research ledger. Existing syllabus and companion resources supply work/author pairings. The Carthage source's opening correctly gives 146 BCE; a later AD typo is explicitly identified rather than adopted. Three attempted Pleiades pages returned bot challenges and were not treated as consulted evidence. A mistaken UNESCO ID returned a Qin site and was excluded. No images or map tiles were copied; no external tracking player is embedded.

## General discovery additions

`backend/core/discovery.py` provides read-only endpoints for `/api/works/<id>/placements/` and `/api/source-explorer/`. A book's compact profile replaces its simpler membership list; it keeps curated, published and unranked/sequence memberships separate, shows current standing order for curated works, country-local groupings without a global position, publisher/revision/date and source-register links. Each group initially shows three rows with expansion. No average or universal score is calculated. Public profiles include only visible public lists; staff retains existing access to ownerless shared drafts. Personal lists and overrides are excluded.

The source explorer is an authenticated, paginated sidebar view (24 rows/page) with search, publication, source-type, language, reported geography, saved eligibility, ranking and exact-URL reuse filters. Language/region metadata is sparse and heterogeneous; raw reported geography is retained, missing fields stay unknown, and a target's country or a source's topic is never used as publication geography. 'Unknown' language means no separately recorded language field; a combined region/language field may still contain useful information. Eligibility/access labels reproduce existing local/owner-supplied ledgers and do not assert a fresh consultation.

Reuse means the exact stored URL appears in multiple permission-visible targets. It is not independent evidence, not fuzzy deduplication, and does not catch alternate URLs. Each record retains its target-specific evidence and limitations; repeated URLs are not merged or reimported. If one target has several same-URL records, its reuse summary says whether any is eligible, while individual records remain separate.

## Verification

Django check and TypeScript/Vite builds passed. Read-only owner API checks: source listing and reused/Japan/English/unknown-geography/lead filters returned 200 (roughly 0.5–1.5 seconds on the local corpus); 28 visible placements for Iliad; 72 learning prompts and eight atlas cards. Invalid learning requests returned 400 before writes. Pure in-memory checks exercised sessions, recall scheduling/conflict rejection, essay revision retention and export, without saving diagnostic data. Atlas source/module references and undated mythic invariants validated.

No database writes, migration, accounts, catalog records, automatic browser checks or test-suite runs. Current live-save flows should be tried manually with real content: record a study session; answer/revisit a prompt; filter/select an atlas location; save/edit/export an essay with one commonplace; open a book's grouped placements; compare source records sharing a URL. PostgreSQL/Docker remain untested.

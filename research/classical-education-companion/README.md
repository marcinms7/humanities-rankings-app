# Classical education companion — 14 September 2026

## Birkbeck addendum

At the owner's request, four Birkbeck course/material cards and six source records were added: Classical Studies BA, Classics BA, 2026–27 Classics short-course directory, introductory Greek module outline, library database directory and its linked Free Access guide. Five provider pages were consulted; the Free Access guide returned 429 and is explicitly unverified. Current totals are 12 course/material cards and 33 URL records (30 accessed pages/excerpts, three blocked leads). Original implementation counts below are historical. No paid course, licensed database, textbook or student-only material is presented as free open courseware. Existing rankings, source ledgers and private state are unchanged. JSON content/reference validation and Django check passed; no browser automation or test suite ran.

Owner-authorized study-resource research and implementation, not a new ranking synthesis or ranking/source import.

## Saved research

The versioned UI-served source register and editorial cards are in `backend/core/content/classical_companion.json` (`companion-v1`). It contains 27 URL records: 25 page/excerpt accesses and 2 access-blocked/unverified leads (Hackett Five Dialogues; Columbia Digital Dante). This is a URL register, not 25 independent sources or complete books/courses heard/read. Several records are related pages of the same provider; several revisit resources already present in `classical_study_tools.json`. No deduplicated aggregate research count is claimed. No sources were added to the Top 250 ranking evidence ledger.

Provider coverage: Yale Greek history and Roman architecture archives; MIT Tragedy syllabus; Balliol/Oxford preparatory reading guide; OpenLearn Ancient Greek and Classical Latin introductions; Dickinson annotated texts; MIT-hosted Internet Classics Archive; translator and BMCR review pages; Stanford Encyclopedia articles; primary texts hosted by Theoi; History of Philosophy without any gaps. Every UI source record carries a direct URL, check date, access label and evidence/limitation note.

The podcast homepage and six episode pages were checked. Audio was not auditioned in full, durations were not invented, and no external player or tracking iframe is embedded. Episodes 15, 25, 55, 66, 110 and 122 are optional editorial pairings. The main website link preserves access to its wider traditions rather than restricting it to ancient Greece/Rome.

Editorial additions: five starting routes; four context cards; six glossary entries; four reception/transmission comparisons; three translation/reading-aid comparisons; eight course/material cards. Definitions are contextual aids, not a historical lexicon. Courses are archived/open-study resources, not claims of current enrolment or accreditation. The modern tragedy pairing explicitly distinguishes separate adaptation branches. Blocked Dante and Hackett pages remain labelled leads; no commentary or full-edition access is claimed.

## Identity and preservation

All 250 work identities and starter passages derive from the audited `research/classical-education-guide/owner-chat-catalog-2026-09-14.json`. Active ranking membership/order is checked against the database. Explicit W-key-to-module mappings cover all 24 syllabus modules; unmapped works remain independent extensions with their starter notes intact. No matching by title, new books, changed positions, changed editions or research-source writes occur.

Private state uses the existing owner-only `ClassicalStudyProfile.state.companion` namespace. Existing module notes, both versioned assignment paths, activity progress and private data remain intact. GET and preview do not create a profile. Plain-text syllabus export includes new content, sources, saved private notes and current classical allocations.

Planner additions require a preview and explicit confirmation. They append one locked allocation and save the existing book to the owner's library only if absent. Existing library status/edition and allocations are not overwritten. Physical pages are supplied by the reader; Python uses the existing provisional effort policy. Same-work/same-month conflicts are rejected. Allocation completion never marks a whole book finished. Classical scope labels also appear in the main planner. Metadata is keyed by allocation and work identity; if an allocation is deleted/reassigned, old metadata remains in export but is not presented as a live match.

The commonplace book stores work, reference, translator/edition, optional short passage, reflection, up to ten related works and optional revisit date. Notes can be edited and marked revisited; no destructive shared-record operations are exposed. Drafts survive subtab changes and warn before link navigation/page unload. Other unsaved module/tool drafts follow their pre-existing safeguards.

## Verification and limits

Django check and TypeScript/Vite build passed. Content validation found 250 distinct active work IDs, all 24 module IDs mapped, and no dangling source/module references. Read-only owner API checks passed for full content, work-specific preparation, export and non-saving plan preview. Malformed/unconfirmed updates returned 400; anonymous access returned 403. Counts before and after the check were unchanged: 0 study profiles, 1 library item, 0 plan items, 163 rankings, 14,883 ranking entries, 17,229 research sources (all rows, not active-only counts).

No schema migration, database writes, test account, browser automation or test suite run. Valid save flows are implemented but deliberately not exercised against the owner's live data. Please manually try: save a starting route; open a ranked book's study guide; preview/confirm one real selection; check its label/lock in Reading plan; save/reload/edit a commonplace; mark/revisit it; mark an episode listened; export. An existing allocation in the chosen month should be refused without changes.

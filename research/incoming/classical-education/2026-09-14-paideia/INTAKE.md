# Paideia content integration — 14 September 2026

Owner supplied the complete content/product handoff and requested integration within Marginalia's existing Classical education tab. Original report preserved byte for byte; SHA-256: 40b94ecd4b2cd3405e19af11c3e0db4460beb7ce2d389ceff7a7673e8ac0c921.

Structured curriculum: backend/core/content/classical_education.json. All 24 stable module IDs, exact Lighter/Rigorous assignments, prerequisite references, 4 courses and 13 resources retained. Module totals independently sum to 178 and 604 hours. Prerequisites resolve and precede dependants. All 51 numbered sections F–K retained for proposed curriculum and approach/reference views. The complete original, including original app behavior, is included in the private TXT export.

This is a syllabus integration, not a ranked synthesis or a new source qualification exercise. Provider/resource check dates remain externally reported (13 September 2026), not newly verified. Proposed areas remain unassigned and do not acquire progress, workload, proficiency, accreditation or assessment claims. No prior browser notes/completions were supplied.

The curriculum is served from a private backend endpoint; it is not bundled in the public frontend assets. Access is restricted to the existing first account (the local owner). Private notes and assignment-version/path completion are stored on demand in ClassicalStudyProfile in the existing database. Notes use an explicit Save action; completion also saves the current notes. No record is created by browsing. No public deployment was performed.

Backup before migration: manual-20260914T094214577296Z. Migration 0013 only adds the private study-profile table. Owner GET/export returned 200; anonymous access returned 403; all 8 shared deletion triggers remain, foreign-key check has no violations. Frontend build and Django system check passed. No browser automation or test suites ran. Owner browser verification remains outstanding.

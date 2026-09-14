# Research record template

Use this structure for each separately requested target. It is a documentation template; no research has been performed or sources counted in this file.

## Target brief

- Target ID and label:
- Requested output: evidence survey / weighted ranking / criterion assessment / source import.
- Item type and candidate scope:
- Included traditions, languages, eras, forms, and custom tags:
- Explicit exclusions:
- Research status: not started / collecting / evidence complete / awaiting criteria / draft / published.
- Criteria and interest-profile versions: unset until agreed.
- Hard minimum eligible sources: **50 for research/synthesis targets**.
- Intended research depth: **ideally many, many more than 50 relevant, diverse consulted sources; 50 is not a stopping rule or completion signal**.
- Plan for useful coverage beyond the minimum:
- Eligible consulted sources: **0**.
- Diversity audit: not started.
- Saved at / database imported at:
- Ranking metadata updated at:
- Last completed substantive research at: unset until genuinely completed.
- Last successful source check at: unset until that check is completed.
- Requested refresh interval / pending refresh request:
- Prior revision and proposed change summary:

## Source ledger

Use one record per underlying source with fields suitable for export to structured data:

| Field | Meaning |
| --- | --- |
| source_id | Stable identifier used in citations and candidate evidence |
| title, author, publisher | Source identity; do not infer unknown authors |
| canonical_url, access_url, doi | Original identity and where the content was actually read |
| publication_date, accessed_at | Date/version context; distinguish unknown dates |
| source_family | Primary category for the diversity count; optional secondary labels |
| domain_or_platform, publisher_group | Shows concentration and common ownership |
| language | Language of the consulted content |
| access_level | Full relevant content, relevant excerpt, abstract only, or discovery lead |
| underlying_source_id | Deduplicates mirrors, reprints, threads, and study versions |
| depends_on_source_ids | Lists copied from or derived from other evidence sources |
| target_ids | Research targets to which the source materially contributes |
| relevance_by_target | Specific contribution for each target; reuse needs separate justification |
| evidence_notes | Paraphrased findings, arguments, or reception evidence |
| location | Page, section, timestamp, or comment permalink where useful |
| candidates_or_claims_supported | Exact works/people/claims informed by the source |
| disagreement_or_limitations | Contradictory views, limited access, bias, scope, or uncertainty |
| count_eligible | False until examined, relevant, and deduplicated |
| exclusion_reason | Duplicate, inaccessible content, irrelevant, or another concrete reason |

## Completion audit

- Per-target eligible unique-source total:
- Global unique-source total, if reporting multiple targets:
- Source-family counts:
- Domain/platform and independent publisher counts:
- Dependence and duplicate exclusions:
- Scholarly, editorial, and reader-discussion coverage:
- Geographic, language, and historical coverage limitations:
- Hard minimum met: yes/no, evaluated separately for every target; this alone does not establish completion.
- Depth beyond 50, remaining useful evidence, and rationale for stopping:
- Diversity requirement met: yes/no, with a short justification based on the actual mix.
- Outstanding research or criteria decisions:

## Candidate assessment record

- Canonical work/person ID, or an unresolved identity record:
- Scope eligibility and evidence:
- Criterion definition/version:
- Proposed value: unset until the criterion and scale are agreed.
- Explanation and source IDs:
- Disagreement, uncertainty, and limits:
- Assessor and assessment date/version:
- Personal override and owner: separate from the proposed shared assessment.
- Weight-profile and algorithm versions: unset until applicable.

Count audited evidence; a bibliography's length alone does not establish completion.

Save this record and `research/<target>/sources.json` after every small consulted batch. Persist the ledger with `manage.py import_research <file> --target <exact-ranking-slug>`. The ledger's `target_id` must match that slug; each counted source must name the target and explain its actual relevance. Database import does not complete research or publish scores. Use an intentional, reviewed update when correcting already imported evidence, and keep earlier versions in the audit trail.

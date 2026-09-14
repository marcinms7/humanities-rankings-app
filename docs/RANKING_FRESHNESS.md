# Ranking dates and refreshes

Each ranking card and detail page shows an Updated date. Its research date is separate, allowing readers to judge the age of the evidence. Unresearched templates display “Not researched”; initial published selections display “Research continuing”. Do not substitute creation or initial-selection publication for a completed research date.

The first implementation stores `created_at`, `updated_at`, `last_researched_at` and `last_sources_checked_at` on each ranking, and refresh intervals/requests in per-user preferences. It preserves snapshots of list edits. The initial illustrated selections record their version publication day in `scope.editorial.published_on`; a dedicated published_at field and research-job attempt records in the full design below are not implemented yet. Source imports leave completed-research and source-check dates unchanged, including the initial 51-source books survey.

| Field | Meaning |
| --- | --- |
| `created_at` | First creation of the list definition |
| `updated_at` | Most recent saved edit; API uses UTC timestamps |
| `published_at` | Publication date of the revision readers are viewing |
| `last_researched_at` | Successful completed substantive research for that revision |
| `last_sources_checked_at` | Successful check of its source set, possibly with no changes |
| `refresh_interval_days` | Optional preference for when the user wants a reminder |
| refresh requested/started/failed/completed dates | Audit of attempts, separate from successful research |

Display dates in the viewer's locale, with an exact timestamp available. Draft edits do not advance the published revision's date. Metadata, images, personal reordering and weight changes never reset research age. A failed job, partial source batch or automatic recalculation is not new completed research.

Sort saved rankings by research age and show “Refresh suggested” when the selected interval has passed. No automatic obsolescence claim: older criticism can remain valuable. With no successful research date, show “Not researched” rather than calculating age from creation. A user can request a refresh at any time; deduplicate outstanding requests and show their state.

Refreshing saves new evidence and a draft revision, summarizes added/removed candidates and changed assessments, and preserves prior versions and private overrides. Apply the hard per-target minimum of 50 consulted diverse sources, while aiming for many, many more than 50. A refresh should deepen useful coverage rather than stop when that minimum is met. Separate a completed survey from a completed assessed ranking. Merely revisiting the same URLs does not demonstrate that old claims were re-evaluated.

The first application records refresh requests for later agent work. Requesting a refresh does not launch an automated researcher; that integration remains future work.

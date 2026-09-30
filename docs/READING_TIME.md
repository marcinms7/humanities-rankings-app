# Reading-time estimation

The app should show an estimated total reading duration on every book page and alongside books in rankings and reading plans. Where length is unknown, display that the estimate needs a page/word count rather than inventing a number.

The implementation is [the framework-independent Python module](../backend/domain/reading_time.py). Django serializers already use it for catalog durations and total/remaining library durations. The planner shares its effort policy through [reading_capacity.py](../backend/domain/reading_capacity.py).

## Placeholder behavior

### Difficulty refinement (15 September 2026)

The catalog edit form now accepts optional 0–4 editorial assessments of prose complexity, conceptual density and structural difficulty. Python combines them: `d = (0.4 × prose + 0.4 × concepts + 0.2 × structure) / 4`; multiplier = `1 + d + 2d²` (rounded to three decimals). This yields 1× for all-zero, 2× for all-moderate and 4× for all-exceptional demands. Weights and curve are provisional design assumptions, not measured literary assessments. The result replaces the work's existing effort override; only the scalar result is stored, not the three component ratings. Existing works retain their profiles until explicitly reviewed. Age, genre tags and nationality never automatically assign these ratings.

The existing shared Python planner uses the saved override and edition density, so difficulty is applied once. Current allocations are never rewritten. Reading rhythm offers slower (180), typical starting estimate (250) and faster (320 WPM) presets while preserving custom rates. No timed sessions are required. Dedicated personal reading modes and book-specific feedback remain future work.

Estimator v1 widens its illustrative range by 0.10 on each side for page-inferred length and up to 0.20 more for higher difficulty. These are planning bounds, not confidence intervals. Manga and poetry still require format-specific models in future; the present prose estimator should be treated cautiously for those forms.

```text
estimated hours = words / reader words per minute / 60
                  × reading-load multiplier
                  × (1 + study overhead)
```

Use verified edition-specific word count where possible. Otherwise estimate words from the selected edition's page count. The initial assumptions are 300 words per page, 250 baseline words per minute, and the following load multipliers:

| Reading profile | Provisional multiplier |
| --- | --- |
| Leisure | 1.0 |
| Classic literature | 1.5 |
| Demanding literature | 2.0 |
| Philosophy | 2.5 |

**Every number here is an uncalibrated placeholder, not a measured population average.** The configurable output range (0.75–1.5 times the central estimate) is illustrative and is not a statistical confidence interval. Keep the algorithm version, length basis, assumptions, and `calibrated=false` with the result.

Select a profile per work/edition and permit overrides. Do not assume that age, nationality, or every book within a genre determines difficulty. A philosophy introduction may be easier than experimental fiction. One load override replaces the preset; overlapping tags must not multiply the same difficulty repeatedly.

The placeholder supports additional annotation/rereading overhead and an individual reading rate. A later model can use conceptual density, prose complexity, unfamiliar terminology, translation, prior subject knowledge, rereading, and observed reading sessions. Collect explicit feedback before fitting those factors; do not present a speculative model as advanced research.

## Relationship to the planner

The owner prefers flexible weekly or monthly page targets, with optional targets per reading day. `User.reading_target_period` selects the active target; each period retains its own value. Weekly is the default. `reading_days_per_week` describes a flexible number of sessions, not compulsory weekdays.

- Weekly target: month budget = weekly pages × days in month / 7.
- Monthly target: month budget = the selected monthly pages.
- Per-reading-day target: month budget = daily pages × reading days per week × days in month / 7.

For weekly/monthly targets, reading days affect the suggested session size, not the total budget. Existing users' weekly/monthly values are initialized from their old daily target (×7 and ×30). The default difficulty adjustment is visibly labelled in the UI and can be switched off.

With difficulty adjustment enabled, targets mean **baseline pages** (lighter-reading equivalents): effort cost = physical pages × work multiplier × edition word density. Density is edition words / edition pages / 300 when both verified values exist, otherwise 1. `Work.reading_effort_override` (0.25–10) replaces the preset multiplier; it does not multiply it again. A leisure page costs 1 baseline page, a demanding-literature page 2, and a philosophy page 2.5 before any density adjustment. These are placeholders, not researched measurements of Ulysses, Kant, or any other named book. Assign and refine profiles per work instead of inferring difficulty from tags alone.

`GET /api/plan/capacity/` supplies the authoritative month budgets, effort used, physical pages, and approximate session sizes. `POST /api/plan/suggest/` uses the same calculations, floors allocations to whole physical pages, and reserves the difficulty-adjusted cost of locked allocations. Saved progress and `PlanItem.pages` always use actual edition pages. Unknown lengths remain unscheduled; locked items with unknown allocations require a page count before suggestions. Suggestions must be previewed and explicitly saved; changed settings do not rewrite an existing plan. Current algorithm version: `reading-capacity-v2-calendar-provisional`, adding the optional calendar adjustment described below; prior frozen reading bases remain unchanged.

Lecture listening time is a separate activity from reading time.

Keep total-book duration separate from remaining-reading duration. The library API provides both using the selected edition and progress. Changing editions invalidates page-based progress assumptions and requires an explicit mapping or reset.

## Verification

The initial estimator checks cover equal-length difficulty differences, word-count precedence, missing lengths, overrides and invalid inputs. The owner asked to pause automated testing on 12 September 2026; this planner refinement was built and migrated, without running the test suites or browser automation. Ask the owner to try the new controls. When testing is requested later, use an isolated database and cover weekly/monthly budgets, density, overrides, locked allocations, and preservation of physical page counts.


## Frozen edition assumptions — September 2026

Library records, archived attempts and monthly allocations retain their edition/length basis. Catalog corrections raise a review flag rather than silently changing saved progress or historical lengths. Use the previewed edition-change flow to enter/reset/keep a page or approximate its percentage in the new edition; this creates a private adjustment receipt, not a completed attempt. Locked allocations preserve their pages and effort basis until separately unlocked and explicitly refreshed. Older records are labelled as captured at upgrade, without claiming historically verified editions. See [maintenance details](MAINTENANCE_2026_09.md).

Page counts labelled `estimated_across_editions` are approximate provider medians. `isbn_matched` means the provider returned pages for that ISBN, not independent inspection of the physical book. Unknown and manually recorded values retain their distinct labels. Cover provenance is separate from bibliographic provenance; representative work images do not prove the reader's edition.

Planner suggestions, Read next additions and classical allocations now return a signed `preview_token`. Confirmations must return it within 30 minutes with the same proposed inputs; changed library/progress/settings or relevant saved allocations require a new preview. A rejected confirmation does not replace saved allocations. See [the code review](CODE_REVIEW_2026_09_28.md) for verification limits.

Duration responses keep `length_basis` for the arithmetic input (`word_count`, `page_count_estimate` or null) and expose edition page provenance separately as `page_count_basis`.

## Private holidays and temporary targets — 29 September 2026

Reading plan now offers **Holidays & temporary targets**. A private `ReadingCalendar` stores inclusive date pauses and month percentages separately from the usual reading rhythm. A temporary 50% target halves that month's usual budget; 0% pauses the whole month. Removing an override restores the usual target. Percentages are whole numbers from 0 through 300; 100 is normalized to no override. Each pause can span up to 366 days, including across years. Overlapping pauses count each date once, including leap days. These are flexible calendar-day reductions, not assignments to particular weekdays.

Python calculates `adjusted budget = usual month budget × temporary percent / 100 × available calendar days / total calendar days`, for all day/week/month target modes. The weekly equivalent averages the adjusted budget over the month; suggested pages per available reading day use the remaining flexible reading sessions. A full pause has zero budget and zero suggested session pages. Physical edition pages and the existing effort/density convention remain unchanged. The calendar is loaded once per request's reader, not once per month.

Every change requires a signed preview and explicit save. The preview covers the displayed months plus all months affected by existing/proposed exceptions, including removal, and shows old/new budgets, booked effort, over-capacity and unchanged allocations with lock/history labels. Previewing creates no calendar row. Saving writes only private calendar preferences and a revision; it does not move, shorten, remove or unlock existing allocations, rewrite reading totals, or change normal profile targets. Calendar edits, normal rhythm changes and relevant allocation changes invalidate stale confirmations. Background refreshes retain the open calendar form's original revision and edits; a conflict requires reopening it.

Planner suggestions and ordinary carryover obey adjusted room, including zero-capacity months; locked or recorded allocations remain reserved and can be reported over target. Read next now fits whole remaining books into available room, explaining skipped books or missing lengths. Explicit single-book/classical allocations still allow a consciously reviewed over-target commitment and show the adjusted budget/overage. Every reading-plan confirmation is bound to the current calendar and rhythm. Existing calendar records are included in the private portable export. The frontend leaves all budget calculations to Python.

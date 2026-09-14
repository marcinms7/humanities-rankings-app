# Reading-time estimation

The app should show an estimated total reading duration on every book page and alongside books in rankings and reading plans. Where length is unknown, display that the estimate needs a page/word count rather than inventing a number.

The implementation is [the framework-independent Python module](../backend/domain/reading_time.py). Django serializers already use it for catalog durations and total/remaining library durations. The planner shares its effort policy through [reading_capacity.py](../backend/domain/reading_capacity.py).

## Placeholder behavior

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

`GET /api/plan/capacity/` supplies the authoritative month budgets, effort used, physical pages, and approximate session sizes. `POST /api/plan/suggest/` uses the same calculations, floors allocations to whole physical pages, and reserves the difficulty-adjusted cost of locked allocations. Saved progress and `PlanItem.pages` always use actual edition pages. Unknown lengths remain unscheduled; locked items with unknown allocations require a page count before suggestions. Suggestions must be previewed and explicitly saved; changed settings do not rewrite an existing plan. Algorithm version: `reading-capacity-v1-provisional`.

Lecture listening time is a separate activity from reading time.

Keep total-book duration separate from remaining-reading duration. The library API provides both using the selected edition and progress. Changing editions invalidates page-based progress assumptions and requires an explicit mapping or reset.

## Verification

The initial estimator checks cover equal-length difficulty differences, word-count precedence, missing lengths, overrides and invalid inputs. The owner asked to pause automated testing on 12 September 2026; this planner refinement was built and migrated, without running the test suites or browser automation. Ask the owner to try the new controls. When testing is requested later, use an isolated database and cover weekly/monthly budgets, density, overrides, locked allocations, and preservation of physical page counts.

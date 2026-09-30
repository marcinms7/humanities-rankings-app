# Daily reading and monthly carryover

Implemented 28 September 2026 as part of the owner's requested app improvements.

**Today** is a private reading page showing current books, quick page updates,
this month's scheduled/read/remaining totals, monthly allocations and the next
five eligible books in Read next. Readers can choose Today or Explore as their
saved home page. Large sections link to the full library or planner rather than
loading an entire personal library into the dashboard.

Quick page updates check the library item's last saved timestamp. A stale tab
must reload before overwriting more recent progress. Finishing is an explicit
action. These updates do not invent a daily session log or change monthly totals.

## Scheduled pages and pages read

`PlanItem.pages` is the original physical-page allocation. `pages_read` is an
explicit monthly total entered by the reader; `null` means unrecorded. Existing
allocations are not assigned historical progress from a book's current page.
Enter 0 when no pages were read. `carried_pages` records how many pages have
already been transferred into a following month's allocation.

Remaining pages are `pages - pages_read - carried_pages` when the page count is
known; the dashboard clearly flags unrecorded totals. A reading total can be
corrected within the original allocation, and reset to unrecorded before any
pages have been carried out. Monthly totals do not change the book's lifetime
current page. Locks constrain scheduling, so recording reading remains available
for a locked allocation.

Allocations with recorded reading or incoming/outgoing carryover history are
preserved by replacement suggestions and cannot be deleted or moved through the
ordinary planner actions. A mistaken unused reading record can be cleared first.
Incoming carryover receipts also preserve their destination allocations.

## Carryover preview

Each month offers a preview of unfinished allocations into the immediately
following month. The reader chooses allocations, sees destination capacity,
compatible merges, conflicts, and pages that will stay behind, then confirms the
specific proposal. By default only whole physical pages fitting the remaining
effort-adjusted capacity are transferred. An explicit option can include pages
above the monthly target; the resulting overage remains visible.

Unrecorded monthly reading totals, unknown allocation sizes, source/destination
locks, incompatible saved editions/effort, and classical study allocations are
shown as conflicts. Classical passage allocations must be managed in their own
study workflow. Unknown page counts already in the destination raise a visible
capacity warning. The Python planner remains authoritative for budget and effort.

Carryover preserves the source's original pages, monthly reading, and frozen
edition basis. It appends pages to a compatible unlocked destination or creates a
new allocation with the same saved basis. A private `PlanCarryover` receipt keeps
the work, source/destination months, page count and basis. No shared catalog,
rankings, library page progress or locked schedule is rewritten.

Confirmation uses a signed 30-minute preview bound to the user, chosen rows,
allocations, reading progress, relevant study scope and capacity/settings.
Concurrent changes invalidate the preview; successful carryover changes the
source state and prevents replay. Writes hold the user row lock inside a database
transaction, including PostgreSQL-compatible locking of the allocation itself.

## Owner browser checks

- Visit Today, change the home preference, and return through the home link.
- Update a current book's page and check that the monthly reading total remains
  independent; use Record monthly pages read to enter that month's actual total.
- In Planner, preview a partly read allocation into next month. Review capacity,
  confirm, then check that the source retains its original scheduled/read totals
  and the destination receives only the carried pages.
- Check a locked destination and a source without recorded progress: the preview
  explains the conflict without changing either allocation.
- Preview, change source progress or reading rhythm in another tab, then confirm:
  the old preview should be rejected and require a new preview.
- Select a saved discovery filter in the planner and verify the suggestion book
  choices follow it, while existing monthly allocations remain visible.

Ten focused API regression cases are saved in
`backend/core/test_reading_workflow.py`, with four reservation cases in
`tests/test_planning_history.py`, for the next authorized isolated suite run.
No automated browser or test-suite run was performed for this feature work.
Overall migration, build and verification status belongs in `HANDOVER.md`.

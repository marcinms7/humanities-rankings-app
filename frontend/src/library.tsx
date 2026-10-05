import { DraftRecoveryNotice, useDraftRecovery } from './draftRecovery'
import { BookSelectionCheckbox, BulkBookActions, useBookSelection } from './bulkBooks'
import { SaveConflict, savedConflict } from './saveConflict'
import { useEffect, useRef, useState } from 'react'
import {
  BookOpen,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  LockKeyhole,
  Pencil,
  Plus,
  Sparkles,
  Star,
  Trash2,
  UnlockKeyhole,
} from 'lucide-react'
import { api, useResource } from './api'
import { useApp } from './context'
import {
  BookRow,
  Empty,
  ErrorNotice,
  Loading,
  Modal,
  PageHeader,
  duration,
  label,
  localMonth,
  monthLabel,
} from './components'
import { BookRating } from './starRating'
import { LibraryNavigation, ReadingInsights, CollectionOverlap } from './libraryInsights'
import { ReadNext, ReadingGoals } from './readingTools'
import { ReadingHistory } from './readingHistory'
import { ReadingPaceForm } from './readingPace'
import { ReadingCalendar } from './readingCalendar'
import { AllocationProgress, PlannerCarryover } from './plannerCarryover'
import { SavedFilterPicker } from './savedFilters'
import type { LibraryItem, Page, PlanSuggestion, MonthCapacity } from './types'
import type { LibraryFacets, LibrarySelector, LibrarySummary, PlanSummary } from './libraryData'
import { Pager } from './pagination'
import { positivePage, useBrowseSearch, useBrowseState } from './navigation'

const statuses = ['want_to_read', 'reading', 'paused', 'finished', 'abandoned']
const statusName = (status: string) =>
  status === 'want_to_read' ? 'Want to read' : status === 'reading' ? 'Currently reading' : label(status)

export function MyLibrary() {
  const { user, version, requireLogin, mutate } = useApp()
  const selection = useBookSelection('library')
  const [browse, patch] = useBrowseState({
    view: 'books',
    shelf: '',
    tag: '',
    genre: '',
    rating: '',
    ordering: 'updated',
    saved_filter: '',
    status: 'all',
    q: '',
    page: '1',
  })
  const {
    shelf,
    tag,
    genre,
    rating: ratingFilter,
    ordering: order,
    saved_filter: savedFilter,
    status: filter,
    q: query,
  } = browse
  const view = ['books', 'insights', 'overlap', 'next', 'goals'].includes(browse.view) ? browse.view : 'books'
  const setView = (value: string) => patch({ view: value, page: 1 })
  const setShelf = (value: string) => patch({ shelf: value, page: 1 })
  const setTag = (value: string) => patch({ tag: value, page: 1 })
  const setRatingFilter = (value: string) => patch({ rating: value, page: 1 })
  const setOrder = (value: string) => patch({ ordering: value, page: 1 })
  const setSavedFilter = (value: string) => patch({ saved_filter: value, page: 1 })
  const setFilter = (value: string) => patch({ status: value, page: 1 })
  const [search, setSearch] = useBrowseSearch(query, patch)
  const page = positivePage(browse.page)
  const setPage = (value: number) => patch({ page: value })
  const [edit, setEdit] = useState<number | null>(null)
  const params = new URLSearchParams({ compact: '1', page: String(page), ordering: order })
  for (const [key, value] of Object.entries({
    search: query,
    status: filter === 'all' ? '' : filter,
    shelf,
    tag,
    rating: ratingFilter,
    genre,
    saved_filter: savedFilter,
  }))
    if (value) params.set(key, value)
  const resource = useResource<Page<LibrarySummary>>(
    user && view === 'books' ? `/api/library/?${params}` : null,
    version,
  )
  const facetParams = new URLSearchParams(params)
  facetParams.delete('page')
  facetParams.delete('compact')
  const facets = useResource<LibraryFacets>(
    user && view === 'books' ? `/api/library/facets/?${facetParams}` : null,
    version,
  )
  useEffect(() => {
    if (page > 1 && resource.error.includes('Invalid page')) patch({ page: 1 }, { replace: true })
  }, [resource.error, page, patch])
  if (!user)
    return (
      <Empty
        title="A reading space of your own."
        action={
          <button className="button primary" onClick={requireLogin}>
            Sign in
          </button>
        }
      >
        Sign in to save books and keep your reading progress private.
      </Empty>
    )
  if (view !== 'books')
    return (
      <>
        <LibraryNavigation view={view} setView={setView} />
        {view === 'next' ? (
          <ReadNext />
        ) : view === 'goals' ? (
          <ReadingGoals />
        ) : view === 'insights' ? (
          <ReadingInsights />
        ) : (
          <CollectionOverlap />
        )}
      </>
    )
  const rows = resource.data?.results || []
  return (
    <>
      <PageHeader
        eyebrow="Your personal reading life"
        title="Keep your next chapter close."
        actions={
          <a className="button primary" href="#/catalog">
            <Plus size={17} /> Find a book
          </a>
        }
      >
        The books you’re reading, the ones waiting patiently, and the works you keep returning to.
      </PageHeader>
      <LibraryNavigation view={view} setView={setView} />
      <p className="small-text muted">
        Rate any book using the ten stars beneath its title. Changes save automatically.
      </p>
      <div className="tabs library-tabs">
        {['all', ...statuses].map((s) => (
          <button
            className={`tab ${filter === s ? 'active' : ''}`}
            aria-pressed={filter === s}
            key={s}
            onClick={() => setFilter(s)}
          >
            {s === 'all' ? 'All books' : statusName(s)}{' '}
            <span className="tab-count">
              {s === 'all' ? facets.data?.total || 0 : facets.data?.statuses[s] || 0}
            </span>
          </button>
        ))}
      </div>
      <div className="toolbar">
        <SavedFilterPicker value={savedFilter} onChange={setSavedFilter} context="library" />
        <input
          className="search-input"
          aria-label="Search my library"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search your saved works…"
        />
        <div className="rating-filter" role="group" aria-label="Filter by rating">
          <span className="small-text muted">Show:</span>
          {[
            ['', 'All ratings'],
            ['unrated', 'Unrated'],
            ...Array.from({ length: 10 }, (_, i) => [String(i + 1), `★ ${i + 1}`]),
          ].map(([value, text]) => (
            <button
              key={value}
              className={`button secondary small ${ratingFilter === value ? 'selected' : ''}`}
              aria-pressed={ratingFilter === value}
              onClick={() => setRatingFilter(value)}
            >
              {text}
            </button>
          ))}
        </div>
        <select
          className="filter-select"
          aria-label="Sort library"
          value={order}
          onChange={(e) => setOrder(e.target.value)}
        >
          <option value="updated">Recently updated</option>
          <option value="-rating">Highest rated</option>
          <option value="rating">Lowest rated</option>
          <option value="title">Title</option>
        </select>
        <select
          className="filter-select"
          aria-label="Filter personal shelf"
          value={shelf}
          onChange={(e) => setShelf(e.target.value)}
        >
          <option value="">All shelves</option>
          {Array.from(new Set([shelf, ...(facets.data?.shelves || [])]))
            .filter(Boolean)
            .sort()
            .map((value) => (
              <option key={value}>{value}</option>
            ))}
        </select>
        <select
          className="filter-select"
          aria-label="Filter private tag"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
        >
          <option value="">All private tags</option>
          {Array.from(new Set([tag, ...(facets.data?.tags || [])]))
            .filter(Boolean)
            .sort()
            .map((value) => (
              <option key={value}>{value}</option>
            ))}
        </select>
        <a href="#/planner" className="button secondary">
          <CalendarDays size={16} />
          Reading plan
        </a>
      </div>
      {resource.error && <ErrorNotice>{resource.error}</ErrorNotice>}
      {facets.error && <ErrorNotice>{facets.error}</ErrorNotice>}
      <BulkBookActions
        selection={selection}
        visible={rows.map((item) => item.book)}
        loading={resource.loading}
        library
      />
      {resource.loading ? (
        <Loading />
      ) : rows.length ? (
        <section className="panel">
          {rows.map((item) => {
            const pages = item.reading_basis.pages
            const percent =
              item.status === 'finished' ? 100 : pages ? Math.min(100, (item.current_page / pages) * 100) : 0
            return (
              <div key={item.id} className="library-item">
                <BookRow
                  work={item.book}
                  action={
                    <>
                      <BookSelectionCheckbox selection={selection} book={item.book} />
                      <select
                        className="filter-select"
                        aria-label={`Reading status for ${item.book.title}`}
                        value={item.status}
                        onChange={(e) =>
                          void mutate(
                            () =>
                              api(`/api/library/${item.id}/`, 'PATCH', {
                                expected_version: item.edit_version,
                                status: e.target.value,
                                ...(e.target.value === 'finished' && pages ? { current_page: pages } : {}),
                              }),
                            'Reading status saved',
                          )
                        }
                      >
                        {statuses.map((s) => (
                          <option key={s} value={s}>
                            {statusName(s)}
                          </option>
                        ))}
                      </select>
                      <button
                        className="icon-button"
                        aria-label={`Edit progress and rating for ${item.book.title}`}
                        onClick={() => setEdit(item.id)}
                      >
                        <Pencil size={16} />
                      </button>
                    </>
                  }
                />
                <BookRating work={item.work} title={item.book.title} rating={item.rating} />
                <div className="library-details">
                  <button
                    className="button secondary small"
                    onClick={() =>
                      void mutate(
                        () =>
                          api('/api/read-next/', 'POST', {
                            item: item.id,
                            action: item.read_next_position == null ? 'add' : 'remove',
                          }),
                        'Read next saved',
                      )
                    }
                  >
                    {item.read_next_position == null
                      ? '+ Read next'
                      : `✓ Read next · ${item.read_next_position}`}
                  </button>
                  <button className="button secondary small" onClick={() => setEdit(item.id)}>
                    Shelves & tags
                  </button>
                  {item.shelves.map((value) => (
                    <span className="pill gold" key={`s-${value}`}>
                      {value}
                    </span>
                  ))}
                  {item.personal_tags.map((value) => (
                    <span className="pill muted" key={`t-${value}`}>
                      #{value}
                    </span>
                  ))}
                  <div className="reading-progress">
                    <div className="progress-track">
                      <div className="progress-fill" style={{ width: `${percent}%` }} />
                    </div>
                    <span>
                      {item.current_page}
                      {pages ? ` / ${pages}` : ''} pages
                    </span>
                    <span className="muted">
                      {duration(item.remaining_reading_time?.estimated_hours)} remaining
                    </span>
                  </div>
                  {['finished', 'abandoned'].includes(item.status) && (
                    <button
                      className="button secondary small"
                      onClick={() =>
                        void mutate(
                          () => api(`/api/library/${item.id}/reread/`, 'POST'),
                          'New reading attempt started',
                        )
                      }
                    >
                      Start reread
                    </button>
                  )}
                  {item.rating != null && (
                    <span className="rating-summary" aria-label={`Rated ${item.rating} out of 10 stars`}>
                      <Star size={13} fill="currentColor" />
                      {item.rating}/10
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </section>
      ) : (
        <Empty
          title={
            resource.data?.count || savedFilter || query || filter !== 'all' || shelf || tag || ratingFilter
              ? 'No books in this view yet.'
              : 'Your library is waiting for you.'
          }
          action={
            <a className="button primary" href="#/catalog">
              <BookOpen size={16} />
              Explore the catalog
            </a>
          }
        >
          Save a work from a ranking or the catalog. Your reading status, notes, and progress belong only to
          you.
        </Empty>
      )}
      <Pager page={page} data={resource.data} setPage={setPage} loading={resource.loading} />
      <ReadingHistory />
      {edit != null && <LibraryEditor id={edit} close={() => setEdit(null)} />}
    </>
  )
}

function LibraryEditor({ id, close }: { id: number; close: () => void }) {
  const { version } = useApp()
  const resource = useResource<LibraryItem>(`/api/library/${id}/`, version)
  if (!resource.data)
    return (
      <Modal title="Reading details" close={close}>
        {resource.error ? <ErrorNotice>{resource.error}</ErrorNotice> : <Loading />}
      </Modal>
    )
  return <LibraryForm item={resource.data} close={close} />
}

function LibraryForm({ item, close }: { item: LibraryItem; close: () => void }) {
  const { mutate } = useApp()
  const [editVersion, setEditVersion] = useState(item.edit_version)
  const [notes, setNotes] = useState(item.notes)
  const recovery = useDraftRecovery({
    scope: `library-notes:${item.id}`,
    label: `${item.book.title}: reading notes`,
    value: notes,
    dirty: notes !== item.notes,
    baseVersion: editVersion,
    restore: (value, version) => {
      setNotes(value)
      setEditVersion(version || item.edit_version)
    },
  })
  const [conflict, setConflict] = useState<Record<string, unknown> | null>(null)
  const [busy, setBusy] = useState(false),
    [rating, setRating] = useState<number | null>(item.rating)
  return (
    <Modal title={`Reading: ${item.book.title}`} close={close}>
      <form
        onSubmit={async (e) => {
          e.preventDefault()
          setBusy(true)
          const f = new FormData(e.currentTarget)
          if (
            await mutate(
              () =>
                api(`/api/library/${item.id}/`, 'PATCH', {
                  expected_version: editVersion,
                  status: f.get('status'),
                  current_page: Number(f.get('page')),
                  rating,
                  shelves: String(f.get('shelves') || '')
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean),
                  personal_tags: String(f.get('personal_tags') || '')
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean),
                  notes,
                  started_on: f.get('started_on') || null,
                  finished_on: f.get('finished_on') || null,
                }).catch((error) => {
                  setConflict(savedConflict(error))
                  throw error
                }),
              'Book details saved',
            )
          ) {
            recovery.saved()
            close()
          }
          setBusy(false)
        }}
      >
        <SaveConflict
          current={conflict}
          accept={(value) => {
            setEditVersion(value)
            setConflict(null)
          }}
        />
        <label className="field">
          <span>Status</span>
          <select className="select" name="status" defaultValue={item.status}>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {statusName(s)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Current page</span>
          <input
            className="input"
            name="page"
            type="number"
            min={0}
            max={item.reading_basis.pages ?? undefined}
            defaultValue={item.current_page}
            required
          />
        </label>
        <div className="form-grid">
          <label className="field">
            <span>Started on</span>
            <input className="input" type="date" name="started_on" defaultValue={item.started_on || ''} />
          </label>
          <label className="field">
            <span>Finished on</span>
            <input className="input" type="date" name="finished_on" defaultValue={item.finished_on || ''} />
          </label>
        </div>
        <fieldset className="rating-field">
          <legend>Your rating</legend>
          <div className="rating-picker">
            {Array.from({ length: 10 }, (_, index) => index + 1).map((value) => (
              <label
                key={value}
                className={`rating-star ${rating != null && value <= rating ? 'selected' : ''}`}
                title={`${value} out of 10`}
              >
                <input
                  className="sr-only"
                  type="radio"
                  name="personal-rating"
                  value={value}
                  checked={rating === value}
                  onChange={() => setRating(value)}
                  aria-label={`${value} out of 10 stars`}
                />
                <Star fill="currentColor" />
              </label>
            ))}
            <span aria-live="polite">{rating == null ? 'Not rated' : `${rating}/10`}</span>
          </div>
          {rating != null && (
            <button className="text-button" type="button" onClick={() => setRating(null)}>
              Clear rating
            </button>
          )}
        </fieldset>
        <label className="field">
          <span>Personal shelves (comma-separated)</span>
          <input
            className="input"
            name="shelves"
            defaultValue={item.shelves.join(', ')}
            placeholder="Own a copy, Buy later, Book club, Read again"
          />
          <small className="muted">Use any names you like. These shelves belong only to you.</small>
        </label>
        <label className="field">
          <span>Private tags (comma-separated)</span>
          <input
            className="input"
            name="personal_tags"
            defaultValue={item.personal_tags.join(', ')}
            placeholder="summer, gift, recommendations"
          />
        </label>
        <DraftRecoveryNotice recovery={recovery} baseVersion={item.edit_version} busy={busy} />
        <label className="field">
          <span>Private reading notes</span>
          <textarea
            className="textarea"
            name="notes"
            rows={5}
            disabled={busy}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>
        <div className="form-actions">
          <button
            type="button"
            className="button secondary danger"
            onClick={async () => {
              if (
                await mutate(
                  () =>
                    api(`/api/library/${item.id}/`, 'DELETE', { expected_version: editVersion }).catch(
                      (error) => {
                        setConflict(savedConflict(error))
                        throw error
                      },
                    ),
                  'Removed from your library',
                )
              ) {
                recovery.saved()
                close()
              }
            }}
          >
            Remove from library
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? 'Saving…' : 'Save details'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

const shiftMonth = (month: string, offset: number) => {
  const [year, m] = month.split('-').map(Number)
  const d = new Date(year, m - 1 + offset, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

export function Planner() {
  const { user, version, requireLogin, mutate, notify } = useApp()
  const [browse, patch] = useBrowseState({ saved_filter: '', month: '', months: '3' })
  const savedFilter = browse.saved_filter
  const setSavedFilter = (value: string) => patch({ saved_filter: value })
  const start = /^\d{4}-(0[1-9]|1[0-2])$/.test(browse.month) ? browse.month : localMonth()
  const count = ['1', '3', '6', '12'].includes(browse.months) ? Number(browse.months) : 3
  const setStart = (value: string) => patch({ month: value })
  const setCount = (value: number) => patch({ months: value })
  const [adding, setAdding] = useState<string | null>(null),
    [auto, setAuto] = useState(false),
    [calendarOpen, setCalendarOpen] = useState(false),
    [carrying, setCarrying] = useState<string | null>(null)
  const library = useResource<LibrarySelector[]>(
    user ? `/api/library/selector/?saved_filter=${encodeURIComponent(savedFilter)}` : null,
    version,
  )
  const plan = useResource<PlanSummary[]>(
    user ? `/api/plan/?start_month=${start}-01&months=${count}&compact=1` : null,
    version,
    true,
  )
  const capacities = useResource<MonthCapacity[]>(
    user ? `/api/plan/capacity/?start_month=${start}-01&months=${count}` : null,
    version,
  )
  const [selected, setSelected] = useState<number[]>([]),
    [previewResult, setPreview] = useState<{ context: string; plan: PlanSuggestion } | null>(null),
    [busy, setBusy] = useState(false)
  const selectionInitialized = useRef(false)
  useEffect(() => {
    selectionInitialized.current = false
  }, [savedFilter])
  useEffect(() => {
    if (!library.data || library.loading) return
    const eligible = library.data
      .filter((i) => !['finished', 'abandoned'].includes(i.status))
      .map((i) => i.work)
    if (!selectionInitialized.current) {
      selectionInitialized.current = true
      setSelected(eligible)
    } else setSelected((current) => current.filter((id) => eligible.includes(id)))
  }, [library.data, library.loading])
  useEffect(() => {
    setPreview(null)
  }, [start, count, selected, savedFilter, version, user])
  if (!user)
    return (
      <Empty
        title="Make time for your next great read."
        action={
          <button className="button primary" onClick={requireLogin}>
            Sign in
          </button>
        }
      >
        Create a private monthly plan with page goals and books you can lock in place.
      </Empty>
    )
  const months = Array.from({ length: count }, (_, i) => shiftMonth(`${start}-01`, i))
  const payload = { start_month: `${start}-01`, months: count, work_ids: selected }
  const previewContext = JSON.stringify([payload, savedFilter, version, user.id])
  const preview = previewResult?.context === previewContext ? previewResult.plan : null
  const suggest = async (apply = false) => {
    if (busy || library.loading || (apply && !preview)) return
    setBusy(true)
    try {
      const result = await api<PlanSuggestion>('/api/plan/suggest/', 'POST', {
        ...payload,
        apply,
        confirm_replace: apply,
        ...(apply ? { preview_token: preview!.preview_token } : {}),
      })
      setPreview({ context: previewContext, plan: result })
      if (apply) {
        await mutate(async () => null, 'Reading plan saved')
        setAuto(false)
      }
    } catch (e) {
      setPreview(null)
      notify((e as Error).message, true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="Good books deserve a little time"
        title="A reading life, one month at a time."
        actions={
          <>
            <button className="button secondary" onClick={() => setAuto(true)}>
              <Sparkles size={16} />
              Suggest a plan
            </button>
            <button className="button primary" onClick={() => setAdding(`${start}-01`)}>
              <Plus size={17} />
              Plan a book
            </button>
          </>
        }
      >
        Set a comfortable pace, choose your months, and leave room to change your mind.
      </PageHeader>
      <div className="toolbar">
        <div className="inline-form">
          <button
            className="icon-button"
            aria-label="Previous month"
            onClick={() => setStart(shiftMonth(`${start}-01`, -1).slice(0, 7))}
          >
            <ChevronLeft size={18} />
          </button>
          <input
            className="input"
            aria-label="Start month"
            type="month"
            value={start}
            required
            onChange={(e) => {
              if (e.target.value) setStart(e.target.value)
            }}
          />
          <button
            className="icon-button"
            aria-label="Next month"
            onClick={() => setStart(shiftMonth(`${start}-01`, 1).slice(0, 7))}
          >
            <ChevronRight size={18} />
          </button>
        </div>
        <select
          className="filter-select"
          aria-label="Months to show"
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
        >
          {[1, 3, 6, 12].map((n) => (
            <option key={n} value={n}>
              {n} {n === 1 ? 'month' : 'months'}
            </option>
          ))}
        </select>
        <SavedFilterPicker value={savedFilter} onChange={setSavedFilter} context="planner" />
        <button className="button secondary" onClick={() => setCalendarOpen(true)}>
          Holidays & temporary targets
        </button>
      </div>
      {calendarOpen && (
        <ReadingCalendar start={`${start}-01`} months={count} close={() => setCalendarOpen(false)} />
      )}
      <section className="panel pace-panel">
        <ReadingPaceForm user={user} compact />
      </section>
      {library.error && <ErrorNotice>{library.error}</ErrorNotice>}
      {capacities.error && <ErrorNotice>{capacities.error}</ErrorNotice>}
      {plan.error && <ErrorNotice>{plan.error}</ErrorNotice>}
      {plan.loading && !plan.data ? (
        <Loading />
      ) : (
        <div className="month-grid">
          {months.map((month) => {
            const items = plan.data?.filter((i) => i.month === month) || []
            const summary = capacities.data?.find((c) => c.month === month)
            const used = summary?.used || 0,
              capacity = summary?.budget || 0
            const year = Number(month.slice(0, 4))
            const unit = summary?.unit === 'baseline_pages' ? 'baseline pages' : 'pages'
            const number = (value: number) => Math.round(value).toLocaleString()
            return (
              <section className="month-card" key={month}>
                <div className="month-header">
                  <div>
                    <span className="eyebrow">{year}</span>
                    <h2>{monthLabel(month).replace(String(year), '').trim()}</h2>
                  </div>
                  <div className="month-actions">
                    <span className="pill muted">
                      {items.length} {items.length === 1 ? 'work' : 'works'}
                    </span>
                    <button
                      className="icon-button month-add"
                      aria-label={`Add a book to ${monthLabel(month)}`}
                      title={`Add a book to ${monthLabel(month)}`}
                      onClick={() => setAdding(month)}
                    >
                      <Plus size={19} />
                    </button>
                  </div>
                </div>
                <div className="month-capacity">
                  {summary ? (
                    <>
                      <span>
                        {number(used)} / {number(capacity)} {unit}
                        {summary.unknown_allocations ? ' + unallocated works' : ''}
                      </span>
                      <div className="progress-track">
                        <div
                          className={`progress-fill ${used > capacity ? 'over-capacity' : ''}`}
                          style={{
                            width: `${capacity ? Math.min(100, (used / capacity) * 100) : used > 0 ? 100 : 0}%`,
                          }}
                        />
                      </div>
                      <small className="muted">
                        {summary.physical_pages.toLocaleString()} scheduled ·{' '}
                        {summary.pages_read.toLocaleString()} recorded as read ·{' '}
                        {summary.remaining_pages.toLocaleString()} remaining
                        {summary.unrecorded_allocations
                          ? ` · ${summary.unrecorded_allocations} reading totals unrecorded`
                          : ''}
                        <br />
                        About {number(summary.per_reading_day)} {unit} per available reading day
                        {summary.calendar_adjusted && (
                          <>
                            <br />
                            {summary.month_percent}% of usual target · {summary.paused_days} days paused
                          </>
                        )}
                      </small>
                      {used > capacity && (
                        <small className="source-limit">
                          {number(used - capacity)} {unit} over your target
                        </small>
                      )}
                    </>
                  ) : (
                    <span className="muted">
                      {capacities.loading ? 'Calculating capacity…' : 'Capacity unavailable'}
                    </span>
                  )}
                </div>
                {items.length > 0 && (
                  <button
                    className="button secondary small month-carryover"
                    onClick={() => setCarrying(month)}
                  >
                    Preview carryover
                  </button>
                )}
                {items.length ? (
                  items.map((item) => (
                    <article className="plan-book" key={item.id}>
                      <div className="plan-book-top">
                        <a className="book-title" href={`#/books/${item.work}`}>
                          {item.book.title}
                        </a>
                        <button
                          className="icon-button"
                          aria-label={`${item.locked ? 'Unlock' : 'Lock'} ${item.book.title}`}
                          onClick={() =>
                            void mutate(
                              () =>
                                api(`/api/plan/${item.id}/`, 'PATCH', {
                                  locked: !item.locked,
                                  expected_version: item.edit_version,
                                }),
                              item.locked ? 'Book unlocked' : 'Book locked in place',
                            )
                          }
                        >
                          {item.locked ? <LockKeyhole size={16} /> : <UnlockKeyhole size={16} />}
                        </button>
                      </div>
                      <p className="book-author">{item.book.authors.map((a) => a.name).join(', ')}</p>
                      <div className="book-meta">
                        <span>
                          {item.pages == null ? 'Pages not allocated' : `${item.pages} pages scheduled`}
                        </span>
                        {user.difficulty_aware_planning && item.pages != null && (
                          <span title="Provisional effort relative to lighter reading">
                            ≈ {Math.round(item.effort_pages ?? 0)} baseline pages ·{' '}
                            {item.effort_multiplier.toFixed(2)}× effort
                          </span>
                        )}
                        {item.locked && <span className="locked-badge">Locked</span>}
                      </div>
                      <AllocationProgress item={item} />
                      <div className="small-text">
                        {item.classical_study && (
                          <p>
                            <a className="text-link" href="#/classical-education?tab=plan">
                              {item.classical_study.mode === 'selections'
                                ? 'Classical selections only'
                                : 'Classical whole-work route'}
                            </a>
                            {item.classical_study.done
                              ? ' · Allocation completed'
                              : ' · Allocation unfinished'}
                            <br />
                            {item.classical_study.passages}
                          </p>
                        )}
                      </div>
                      <div className="row-actions">
                        {item.basis_needs_review && (
                          <span className="notice">
                            Edition or effort assumptions changed.{' '}
                            {item.has_history ? (
                              'Saved monthly history preserves these assumptions.'
                            ) : item.locked ? (
                              'Unlock to review; saved pages remain fixed.'
                            ) : (
                              <button
                                className="text-link"
                                onClick={() => {
                                  if (
                                    window.confirm(
                                      'Use the current reading edition and effort for this allocation? Its physical page allocation will stay unchanged.',
                                    )
                                  )
                                    void mutate(
                                      () =>
                                        api(`/api/plan/${item.id}/`, 'PATCH', {
                                          refresh_basis: true,
                                          expected_version: item.edit_version,
                                        }),
                                      'Allocation assumptions updated; pages preserved',
                                    )
                                }}
                              >
                                Use current assumptions
                              </button>
                            )}
                          </span>
                        )}
                        <button
                          className="icon-button"
                          disabled={item.locked || item.has_history}
                          aria-label={`Move ${item.book.title} to previous month`}
                          onClick={() =>
                            void mutate(
                              () =>
                                api(`/api/plan/${item.id}/`, 'PATCH', {
                                  month: shiftMonth(month, -1),
                                  expected_version: item.edit_version,
                                }),
                              'Book moved',
                            )
                          }
                        >
                          <ChevronLeft size={16} />
                        </button>
                        <button
                          className="icon-button"
                          disabled={item.locked || item.has_history}
                          aria-label={`Move ${item.book.title} to next month`}
                          onClick={() =>
                            void mutate(
                              () =>
                                api(`/api/plan/${item.id}/`, 'PATCH', {
                                  month: shiftMonth(month, 1),
                                  expected_version: item.edit_version,
                                }),
                              'Book moved',
                            )
                          }
                        >
                          <ChevronRight size={16} />
                        </button>
                        <button
                          className="icon-button"
                          disabled={item.locked || item.has_history}
                          aria-label={`Remove ${item.book.title} from plan`}
                          onClick={() =>
                            void mutate(
                              () =>
                                api(`/api/plan/${item.id}/`, 'DELETE', {
                                  expected_version: item.edit_version,
                                }),
                              'Allocation removed',
                            )
                          }
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="month-empty">
                    <BookOpen size={23} strokeWidth={1.2} />
                    <p>A little space for a good book.</p>
                  </div>
                )}
              </section>
            )
          })}
        </div>
      )}
      <p className="small-text muted">
        Weekly targets are spread proportionally across months. Difficulty adjustment uses provisional
        reading-effort and edition-density factors. Books can span months; locked allocations stay in place.
      </p>
      {carrying && (
        <PlannerCarryover
          month={carrying}
          items={plan.data?.filter((item) => item.month === carrying) || []}
          close={() => setCarrying(null)}
        />
      )}
      {adding && <PlanForm library={library.data || []} month={adding} close={() => setAdding(null)} />}
      {auto && (
        <Modal title="Suggest a reading plan" close={() => setAuto(false)} wide>
          <p>
            Choose books from your library for {monthLabel(`${start}-01`)} and the following {count - 1}{' '}
            {count - 1 === 1 ? 'month' : 'months'}. Remaining pages, your saved reading rhythm, effort
            settings, and locked allocations determine capacity.
          </p>
          <div className="check-list">
            {library.data
              ?.filter((i) => !['finished', 'abandoned'].includes(i.status))
              .map((item) => (
                <label className="check-item" key={item.id}>
                  <input
                    type="checkbox"
                    disabled={busy}
                    checked={selected.includes(item.work)}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked ? [...selected, item.work] : selected.filter((i) => i !== item.work),
                      )
                    }
                  />
                  <span>
                    {item.title}
                    <small className="muted">{item.current_page} pages read</small>
                  </span>
                </label>
              ))}
          </div>
          {!library.data?.length && <p className="notice">Save books to your library first.</p>}
          {preview && (
            <div className="panel panel-body">
              <h3>Proposed allocations</h3>
              {preview.items.map((i, n) => (
                <p key={n}>
                  {library.data?.find((l) => l.work === i.work)?.title} — {monthLabel(i.month)} · {i.pages}{' '}
                  pages
                </p>
              ))}
              {!preview.items.length && <p>No new allocations fit the selected books and months.</p>}
              {preview.unscheduled.map((i, n) => (
                <p className="source-limit" key={n}>
                  {library.data?.find((l) => l.work === i.work)?.title}: {i.reason}
                </p>
              ))}
              {preview.warnings.map((w) => (
                <p className="source-limit" key={w}>
                  {w}
                </p>
              ))}
              <p className="notice">
                Saving replaces allocations without recorded reading or carryover history in these months.
                Locked allocations and saved reading history stay in place.
              </p>
            </div>
          )}
          <div className="form-actions">
            <button
              className="button secondary"
              disabled={busy || library.loading || !selected.length}
              onClick={() => void suggest()}
            >
              {busy ? 'Calculating…' : 'Preview plan'}
            </button>
            {preview && (
              <button
                className="button primary"
                disabled={busy || library.loading}
                onClick={() => void suggest(true)}
              >
                Save this plan
              </button>
            )}
          </div>
        </Modal>
      )}
    </>
  )
}

function PlanForm({
  library,
  month,
  close,
}: {
  library: LibrarySelector[]
  month: string
  close: () => void
}) {
  const { mutate } = useApp()
  const [selected, setSelected] = useState(''),
    [busy, setBusy] = useState(false)
  const item = library.find((i) => i.work === Number(selected)),
    total = item?.pages
  const remaining = total != null && item ? Math.max(0, total - item.current_page) : ''
  return (
    <Modal title={`Plan a book · ${monthLabel(month)}`} close={close}>
      <form
        onSubmit={async (e) => {
          e.preventDefault()
          setBusy(true)
          const f = new FormData(e.currentTarget)
          if (
            await mutate(
              () =>
                api('/api/plan/', 'POST', {
                  work: Number(selected),
                  month: `${f.get('month')}-01`,
                  pages: f.get('pages') ? Number(f.get('pages')) : null,
                  locked: f.get('locked') === 'on',
                }),
              'Book added to your plan',
            )
          )
            close()
          setBusy(false)
        }}
      >
        <label className="field">
          <span>From your library</span>
          <select className="select" required value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="">Choose a work</option>
            {library.map((i) => (
              <option key={i.id} value={i.work}>
                {i.title}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Reading month</span>
          <input className="input" name="month" type="month" defaultValue={month.slice(0, 7)} required />
        </label>
        <label className="field">
          <span>Pages to read this month</span>
          <input
            className="input"
            key={selected}
            name="pages"
            type="number"
            min={1}
            defaultValue={remaining}
            placeholder="Leave blank if not yet known"
          />
        </label>
        <label className="checkbox-field">
          <input name="locked" type="checkbox" />
          Lock this allocation in place
        </label>
        {!library.length && (
          <p className="notice">
            Add works to{' '}
            <a href="#/library" onClick={close}>
              your library
            </a>{' '}
            before scheduling them.
          </p>
        )}
        <div className="form-actions">
          <button className="button primary" disabled={busy || !selected}>
            {busy ? 'Saving…' : 'Save allocation'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

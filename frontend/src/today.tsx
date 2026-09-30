import { useState } from 'react'
import { ArrowRight, BookOpen, CalendarDays } from 'lucide-react'
import { api, useResource } from './api'
import {
  BookRow,
  Empty,
  ErrorNotice,
  Loading,
  PageHeader,
  duration,
  localMonth,
  monthLabel,
} from './components'
import { useApp } from './context'
import { AllocationProgress, PlannerCarryover } from './plannerCarryover'
import type { LibraryItem, MonthCapacity, PlanItem, User } from './types'
import './readingWorkflow.css'

type TodayData = {
  month: string
  currently_reading: LibraryItem[]
  currently_reading_count: number
  next_books: LibraryItem[]
  next_books_count: number
  plan: PlanItem[]
  plan_count: number
  capacity: MonthCapacity & {
    pages_read: number
    carried_pages: number
    remaining_pages: number
    unrecorded_allocations: number
  }
}

function QuickProgress({ item }: { item: LibraryItem }) {
  const { mutate } = useApp()
  const [page, setPage] = useState(String(item.current_page)),
    [busy, setBusy] = useState(false)
  const total = item.reading_basis.pages
  const save = async (finish = false) => {
    setBusy(true)
    await mutate(
      () =>
        api('/api/today/progress/', 'POST', {
          item: item.id,
          current_page: finish && total ? total : Number(page),
          finish,
          expected_updated_at: item.updated_at,
        }),
      finish ? 'Book marked finished' : 'Reading progress saved',
    )
    setBusy(false)
  }
  return (
    <article className="today-book">
      <BookRow work={item.book} />
      <div className="today-book-details">
        <p className="small-text muted">
          {item.current_page.toLocaleString()}
          {total ? ` / ${total.toLocaleString()}` : ''} pages ·{' '}
          {duration(item.remaining_reading_time?.estimated_hours)} remaining
        </p>
        {item.basis_needs_review && (
          <p className="small-text source-limit">
            Edition details changed. Your saved page count is preserved; review it on the book page.
          </p>
        )}
        <form
          className="today-progress-form"
          onSubmit={(e) => {
            e.preventDefault()
            void save()
          }}
        >
          <label className="field">
            <span>Current page</span>
            <input
              className="input"
              type="number"
              min={0}
              max={total || undefined}
              value={page}
              onChange={(e) => setPage(e.target.value)}
              required
              disabled={busy}
              aria-label={`Current page in ${item.book.title}`}
            />
          </label>
          <button
            className="button secondary small"
            disabled={busy || page === '' || Number(page) === item.current_page}
          >
            Save progress
          </button>
          <button
            className="text-link"
            type="button"
            disabled={busy || page === ''}
            onClick={() => void save(true)}
          >
            Finished
          </button>
        </form>
      </div>
    </article>
  )
}

export function Today() {
  const { user, version, requireLogin, setUser, notify } = useApp()
  const [month] = useState(`${localMonth()}-01`),
    [carryover, setCarryover] = useState(false),
    [savingHome, setSavingHome] = useState(false)
  const resource = useResource<TodayData>(user ? `/api/today/?month=${month}` : null, version)
  if (!user)
    return (
      <Empty
        title="Your reading, today."
        action={
          <button className="button primary" onClick={requireLogin}>
            Sign in
          </button>
        }
      >
        Return to your current books, record progress and see what is next.
      </Empty>
    )
  const data = resource.data
  const setHome = async () => {
    setSavingHome(true)
    try {
      const updated = await api<User>('/api/profile/', 'PATCH', {
        home_page: user.home_page === 'today' ? 'explore' : 'today',
      })
      setUser(updated)
      notify(updated.home_page === 'today' ? 'Today is now your home page' : 'Explore is now your home page')
    } catch (error) {
      notify((error as Error).message, true)
    } finally {
      setSavingHome(false)
    }
  }
  return (
    <>
      <PageHeader
        eyebrow={monthLabel(month)}
        title="A little reading, today."
        actions={
          <button className="button secondary" disabled={savingHome} onClick={() => void setHome()}>
            {user.home_page === 'today' ? 'Use Explore as home' : 'Make Today my home'}
          </button>
        }
      >
        Your current books, this month’s plan and the next works you have saved.
      </PageHeader>
      {resource.error && <ErrorNotice>{resource.error}</ErrorNotice>}
      {!data && resource.loading ? (
        <Loading />
      ) : (
        data && (
          <>
            <div className="today-grid">
              <section className="panel today-reading">
                <div className="panel-header">
                  <h2>Currently reading</h2>
                  <a className="text-link" href="#/library">
                    My library <ArrowRight size={14} />
                  </a>
                </div>
                {data.currently_reading.length ? (
                  data.currently_reading.map((item) => (
                    <QuickProgress item={item} key={`${item.id}-${item.updated_at}`} />
                  ))
                ) : (
                  <Empty
                    title="Choose your next chapter."
                    action={
                      <a className="button secondary" href="#/library">
                        Open my library
                      </a>
                    }
                  >
                    Set a book to Currently reading in your library to keep it close here.
                  </Empty>
                )}
                {data.currently_reading_count > data.currently_reading.length && (
                  <p className="panel-body small-text">
                    <a href="#/library">See all {data.currently_reading_count} current books</a>
                  </p>
                )}
              </section>
              <section className="panel today-plan">
                <div className="panel-header">
                  <h2>This month</h2>
                  <a className="text-link" href="#/planner">
                    <CalendarDays size={15} /> Planner
                  </a>
                </div>
                <div className="panel-body">
                  <div className="today-totals">
                    <div>
                      <strong>{data.capacity.physical_pages.toLocaleString()}</strong>
                      <span>pages scheduled</span>
                    </div>
                    <div>
                      <strong>{data.capacity.pages_read.toLocaleString()}</strong>
                      <span>pages recorded as read</span>
                    </div>
                    <div>
                      <strong>{data.capacity.remaining_pages.toLocaleString()}</strong>
                      <span>pages left in this month</span>
                    </div>
                  </div>
                  {data.capacity.carried_pages > 0 && (
                    <p className="small-text muted">
                      {data.capacity.carried_pages} pages carried into a later month.
                    </p>
                  )}
                  <p className="small-text muted">
                    Monthly reading totals are recorded separately from your current page in each book.
                    {data.capacity.unrecorded_allocations > 0 &&
                      ` ${data.capacity.unrecorded_allocations} allocations have no reading total yet.`}
                    {data.capacity.unknown_allocations > 0 &&
                      ` ${data.capacity.unknown_allocations} allocations still need page counts.`}
                  </p>
                  {data.plan.length ? (
                    data.plan.map((item) => (
                      <article className="today-allocation" key={item.id}>
                        <a className="book-title" href={`#/books/${item.work}`}>
                          {item.book.title}
                        </a>
                        <p className="small-text muted">
                          {item.pages ?? '?'} pages scheduled{item.locked ? ' · locked' : ''}
                        </p>
                        <AllocationProgress item={item} />
                      </article>
                    ))
                  ) : (
                    <p className="notice">
                      No books are scheduled this month. <a href="#/planner">Make a reading plan.</a>
                    </p>
                  )}
                  {data.plan_count > data.plan.length && (
                    <p className="small-text">
                      <a href="#/planner">See all {data.plan_count} allocations in the planner</a>
                    </p>
                  )}
                  {!!data.plan_count && (
                    <button className="button secondary small" onClick={() => setCarryover(true)}>
                      Preview carryover to next month
                    </button>
                  )}
                </div>
              </section>
              <section className="panel today-next">
                <div className="panel-header">
                  <h2>Read next</h2>
                  <a className="text-link" href="#/library?view=next">
                    Your shortlist <ArrowRight size={14} />
                  </a>
                </div>
                {data.next_books.length ? (
                  data.next_books.map((item) => (
                    <BookRow
                      key={item.id}
                      work={item.book}
                      action={
                        <a className="button secondary small" href={`#/books/${item.work}`}>
                          <BookOpen size={14} />
                          Open book
                        </a>
                      }
                    />
                  ))
                ) : (
                  <div className="panel-body">
                    <p className="muted">Add books to Read next from your library or a book page.</p>
                  </div>
                )}
                {data.next_books_count > data.next_books.length && (
                  <p className="panel-body small-text">
                    <a href="#/library?view=next">See all {data.next_books_count} saved books</a>
                  </p>
                )}
              </section>
            </div>
            {carryover &&
              (data.plan_count > data.plan.length ? (
                <div className="notice">
                  Open the <a href="#/planner">planner</a> to review all this month’s allocations before
                  carryover.{' '}
                  <button className="text-link" onClick={() => setCarryover(false)}>
                    Dismiss
                  </button>
                </div>
              ) : (
                <PlannerCarryover month={month} items={data.plan} close={() => setCarryover(false)} />
              ))}
          </>
        )
      )}
    </>
  )
}

import { BookRating } from './starRating'
import { useState } from 'react'
import { api, useResource } from './api'
import { useApp } from './context'
import { ErrorNotice, Loading, label } from './components'
import { Pager } from './pagination'
import { positivePage, useBrowseState } from './navigation'
import type { ReadingHistorySummary } from './libraryData'
import type { LibraryItem, Page, Work, ReadingBasis } from './types'

type Attempt = {
  reading_basis: ReadingBasis
  id: number
  work_id: number
  work__title: string
  status: string
  current_page: number
  rating: number | null
  notes: string
  started_on: string | null
  finished_on: string | null
  edition_id: number | null
}

function AttemptDetails({ attempt }: { attempt: ReadingHistorySummary }) {
  const { version } = useApp()
  const [open, setOpen] = useState(false)
  const details = useResource<Attempt>(open ? `/api/library/history/${attempt.id}/` : null, version)
  const row = details.data
  return (
    <details className="source-card" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        {attempt.work__title} · {label(attempt.status)}
        {attempt.rating != null ? ` · ★ ${attempt.rating}/10` : ''}
        {attempt.has_notes ? ' · Notes saved' : ''}
      </summary>
      <p>
        {attempt.started_on || 'Start date not recorded'} —{' '}
        {attempt.finished_on || 'Finish date not recorded'} · {attempt.current_page} pages
      </p>
      {open &&
        (details.error ? (
          <ErrorNotice>{details.error}</ErrorNotice>
        ) : !row ? (
          <Loading />
        ) : (
          <>
            <p>{row.edition_id ? `Edition #${row.edition_id}` : 'Edition not recorded'}</p>
            <p className="small-text muted">
              Saved length: {row.reading_basis?.pages ?? 'unknown'} pages ·{' '}
              {label(row.reading_basis?.pages_basis || 'unknown')}.{' '}
              {row.reading_basis?.origin?.includes('upgrade') &&
                'Captured at upgrade; historical edition not independently verified.'}
            </p>
            <p style={{ whiteSpace: 'pre-wrap' }}>{row.notes || 'No notes recorded'}</p>
          </>
        ))}
    </details>
  )
}

export function ReadingHistory({ work }: { work?: number }) {
  const { user, version } = useApp()
  const [browse, patch] = useBrowseState({ hpage: '1' })
  const page = positivePage(browse.hpage)
  const setPage = (value: number) => patch({ hpage: value })
  const history = useResource<Page<ReadingHistorySummary>>(
    user ? `/api/library/history/?paged=1&page=${page}${work ? `&work=${work}` : ''}` : null,
    version,
  )
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Previous reading attempts</h2>
      </div>
      <div className="panel-body">
        {history.error && <ErrorNotice>{history.error}</ErrorNotice>}
        {history.loading ? (
          <Loading />
        ) : (
          history.data?.results.map((attempt) => <AttemptDetails key={attempt.id} attempt={attempt} />)
        )}
        {!history.loading && !history.error && !history.data?.count && (
          <p className="muted">
            Previous attempts appear here when you start a reread or remove a book from your library.
          </p>
        )}
        <Pager page={page} data={history.data} setPage={setPage} loading={history.loading} />
      </div>
    </section>
  )
}

export function QuickReading({ work, item }: { work: Work; item?: LibraryItem }) {
  const { mutate } = useApp()
  const [busy, setBusy] = useState(false)

  return (
    <>
      <section className="panel">
        <div className="panel-header">
          <h2>Your reading</h2>
        </div>
        <div className="panel-body">
          <BookRating work={work.id} title={work.title} rating={item?.rating ?? null} />
          {item && (
            <>
              <p className="small-text">
                {label(item.status)} · {item.current_page} pages
              </p>
              <p className="small-text">
                Started: {item.started_on || 'Not recorded'}
                <br />
                Finished: {item.finished_on || 'Not recorded'}
              </p>
              {item.basis_needs_review && (
                <p className="notice">
                  Edition metadata changed. Your progress still uses the saved length; review an edition below
                  to update it.
                </p>
              )}
              {['finished', 'abandoned'].includes(item.status) && (
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true)
                    await mutate(
                      () => api(`/api/library/${item.id}/reread/`, 'POST'),
                      'New reading attempt started; previous attempt saved',
                    )
                    setBusy(false)
                  }}
                >
                  Start reread
                </button>
              )}
              <a className="button secondary" href="#/library">
                Edit progress and dates
              </a>
            </>
          )}
        </div>
      </section>
      <ReadingHistory work={work.id} />
    </>
  )
}

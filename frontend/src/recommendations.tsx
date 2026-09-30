import { useState, type FormEvent } from 'react'
import { api, APIError, useResource } from './api'
import { useApp } from './context'
import { Empty, ErrorNotice, label, Loading } from './components'
import { queryCache } from './queryCache'
import type { SavedDiscoveryFilter } from './savedFilters'
import type {
  ApiRecommendationBundle,
  ApiRecommendationPreferences,
  ApiRecommendationFeedbackPage,
  ApiRecommendationFeedback,
} from './generated/apiContracts'
import './recommendations.css'

type Bundle = ApiRecommendationBundle
type Candidate = NonNullable<Bundle['slots'][number]['selected']>
type Action = ApiRecommendationFeedback['action']
type Slot = Bundle['slots'][number]['key']
type Undo = { work: number; title: string; revision: number; action: Action; days?: number }
const fields = ['literature', 'philosophy', 'nonfiction', 'manga'] as const
const actionLabel: Record<Action, string> = {
  neutral: 'Cleared',
  more_like: 'More like',
  not_interested: 'Not interested',
  later: 'Later',
}
const hours = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 1 })

function PreferencesForm({
  initial,
  onSaved,
}: {
  initial: ApiRecommendationPreferences
  onSaved: () => void
}) {
  const { version, notify } = useApp()
  const [draft, setDraft] = useState(initial)
  const [topics, setTopics] = useState(initial.topics.join(', '))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const filters = useResource<SavedDiscoveryFilter[]>('/api/saved-filters/', version)
  const facets = useResource<{ genres: string[] }>('/api/works/facets/', version)
  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api('/api/recommendations/preferences/', 'PATCH', {
        expected_revision: draft.revision,
        fields: draft.fields,
        genres: draft.genres,
        topics: topics
          .split(',')
          .map((term) => term.trim())
          .filter(Boolean),
        short_pages: draft.short_pages,
        saved_filter: draft.saved_filter,
      })
      notify('Discovery preferences saved.')
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save your preferences.')
      setConflict(caught instanceof APIError && caught.status === 409)
    } finally {
      setSaving(false)
    }
  }
  async function loadSaved() {
    setSaving(true)
    try {
      queryCache.invalidate(['recommendations'])
      const saved = await api<ApiRecommendationPreferences>('/api/recommendations/preferences/')
      setDraft(saved)
      setTopics(saved.topics.join(', '))
      setConflict(false)
      setError('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load your preferences.')
    } finally {
      setSaving(false)
    }
  }
  return (
    <form className="panel panel-body recommendation-preferences" onSubmit={(event) => void submit(event)}>
      <h3>Your discovery interests</h3>
      <p className="small-text muted">
        Choose the subjects you want to explore. These private signals guide suggestions and leave every
        ranking’s scores and order intact.
      </p>
      <fieldset disabled={saving}>
        <legend>Fields you enjoy</legend>
        <div className="recommendation-checks">
          {fields.map((field) => (
            <label key={field}>
              <input
                type="checkbox"
                checked={draft.fields.includes(field)}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    fields: event.target.checked
                      ? [...draft.fields, field]
                      : draft.fields.filter((value) => value !== field),
                  })
                }
              />{' '}
              {label(field)}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="recommendation-form-grid">
        <label className="field">
          <span>Genres · choose up to 12</span>
          <select
            className="select"
            multiple
            size={5}
            value={draft.genres}
            disabled={saving || facets.loading}
            onChange={(event) =>
              setDraft({
                ...draft,
                genres: Array.from(event.target.selectedOptions, (option) => option.value),
              })
            }
          >
            {[...new Set([...(facets.data?.genres || []), ...draft.genres])].sort().map((genre) => (
              <option key={genre} value={genre}>
                {genre}
              </option>
            ))}
          </select>
          <small className="muted">
            Use your device’s multiple-selection controls; no selection includes every genre.
          </small>
        </label>
        <div>
          <label className="field">
            <span>Topic terms · comma-separated, up to 8</span>
            <input
              className="input"
              value={topics}
              maxLength={500}
              disabled={saving}
              onChange={(event) => setTopics(event.target.value)}
              placeholder="e.g. memory, ethics, travel"
            />
            <small className="muted">
              Matches saved titles and tags. Broader themes may have incomplete catalog coverage.
            </small>
          </label>
          <label className="field">
            <span>Short book limit · pages</span>
            <input
              className="input"
              type="number"
              min={25}
              max={1000}
              required
              value={draft.short_pages}
              disabled={saving}
              onChange={(event) => setDraft({ ...draft, short_pages: Number(event.target.value) })}
            />
          </label>
          <label className="field">
            <span>Keep every suggestion inside a saved filter</span>
            <select
              className="select"
              value={draft.saved_filter || ''}
              disabled={saving || filters.loading}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  saved_filter: event.target.value ? Number(event.target.value) : null,
                  missing_saved_filter: false,
                })
              }
            >
              <option value="">No saved filter restriction</option>
              {filters.data?.map((filter) => (
                <option key={filter.id} value={filter.id}>
                  {filter.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {draft.missing_saved_filter && (
        <p className="notice">
          The previous filter “{draft.saved_filter_name}” was deleted. Saving with no filter explicitly
          removes that restriction.
        </p>
      )}
      {(error || facets.error || filters.error) && (
        <ErrorNotice>{error || facets.error || filters.error}</ErrorNotice>
      )}
      <div className="toolbar">
        <button className="button primary" disabled={saving || conflict}>
          {saving ? 'Saving…' : 'Save discovery preferences'}
        </button>
        {conflict && (
          <button
            className="button secondary"
            type="button"
            disabled={saving}
            onClick={() => void loadSaved()}
          >
            Replace this draft with saved preferences
          </button>
        )}
      </div>
      {conflict && (
        <p className="small-text muted">
          Your draft is still here. Copy anything you want to keep before loading the saved version.
        </p>
      )}
    </form>
  )
}

function BookSuggestion({
  candidate,
  busy,
  onFeedback,
}: {
  candidate: Candidate
  busy: boolean
  onFeedback: (work: number, action: Action, revision: number, previous: Action, title: string) => void
}) {
  return (
    <>
      <h3>
        <a className="text-link" href={`#/books/${candidate.id}`}>
          {candidate.title}
        </a>
      </h3>
      <p className="small-text muted">{candidate.authors.join(' · ') || 'Author not recorded'}</p>
      <ul className="recommendation-reasons">
        {candidate.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      <p className="recommendation-length">
        {candidate.pages == null ? 'Length not recorded' : `${candidate.pages.toLocaleString()} pages`}
        {candidate.estimate.estimated_hours != null
          ? ` · about ${hours(candidate.estimate.estimated_hours)} hours`
          : ' · time unavailable'}
      </p>
      <details className="small-text recommendation-basis">
        <summary>Edition and time assumptions</summary>
        <p>
          {candidate.edition_basis} · {label(candidate.page_basis)}
        </p>
        {candidate.estimate.low_hours != null && candidate.estimate.high_hours != null && (
          <p>
            Illustrative range: {hours(candidate.estimate.low_hours)}–{hours(candidate.estimate.high_hours)}{' '}
            hours.
          </p>
        )}
        {candidate.estimate.assumptions.map((assumption) => (
          <p key={assumption}>{assumption}</p>
        ))}
      </details>
      {candidate.lists.length > 0 && (
        <details className="small-text recommendation-basis">
          <summary>Bookmarked ranking context</summary>
          {candidate.lists.map((ranking) => (
            <p key={ranking.id}>
              <a className="text-link" href={`#/rankings/${ranking.id}`}>
                {ranking.title}
              </a>{' '}
              · {ranking.kind}
            </p>
          ))}
        </details>
      )}
      <div className="recommendation-actions">
        <button
          className="button secondary"
          disabled={busy}
          aria-pressed={candidate.feedback === 'more_like'}
          onClick={() =>
            onFeedback(
              candidate.id,
              candidate.feedback === 'more_like' ? 'neutral' : 'more_like',
              candidate.feedback_revision,
              candidate.feedback,
              candidate.title,
            )
          }
        >
          More like{candidate.feedback === 'more_like' ? ' ✓' : ''}
        </button>
        <button
          className="button secondary"
          disabled={busy}
          onClick={() =>
            onFeedback(
              candidate.id,
              'not_interested',
              candidate.feedback_revision,
              candidate.feedback,
              candidate.title,
            )
          }
        >
          Not interested
        </button>
        <button
          className="button secondary"
          disabled={busy}
          onClick={() =>
            onFeedback(
              candidate.id,
              'later',
              candidate.feedback_revision,
              candidate.feedback,
              candidate.title,
            )
          }
        >
          Later · 30 days
        </button>
      </div>
      <a className="text-link small-text" href={`#/books/${candidate.id}`}>
        Choose edition, save or plan →
      </a>
    </>
  )
}

export function Recommendations() {
  const { user, version, notify } = useApp()
  const [picks, setPicks] = useState<Partial<Record<Slot, number>>>({})
  const [refresh, setRefresh] = useState(0)
  const [editing, setEditing] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [undo, setUndo] = useState<Undo | null>(null)
  const query = new URLSearchParams(Object.entries(picks).map(([key, value]) => [key, String(value)]))
  const bundle = useResource<Bundle>(user ? `/api/recommendations/?${query}` : null, version + refresh)
  const feedback = useResource<ApiRecommendationFeedbackPage>(
    user && historyOpen ? `/api/recommendations/feedback/?page=${page}` : null,
    version + refresh,
  )
  function reload() {
    queryCache.invalidate(['recommendations'])
    setPicks({})
    setRefresh((value) => value + 1)
  }
  async function choose(
    work: number,
    action: Action,
    revision: number,
    previous: Action,
    title: string,
    days?: number,
  ) {
    setBusy(true)
    setError('')
    try {
      const result = await api<ApiRecommendationFeedback>('/api/recommendations/feedback/', 'POST', {
        work,
        action,
        expected_revision: revision,
        ...(days ? { days } : {}),
      })
      setUndo(previous === 'later' ? null : { work, title, revision: result.revision, action: previous })
      notify(`${actionLabel[action]} saved for ${title}.`)
      reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save your feedback.')
      if (caught instanceof APIError && caught.status === 409) reload()
    } finally {
      setBusy(false)
    }
  }
  async function undoLast() {
    if (!undo) return
    const previous = undo
    setBusy(true)
    setError('')
    try {
      await api('/api/recommendations/feedback/', 'POST', {
        work: previous.work,
        action: previous.action,
        expected_revision: previous.revision,
        ...(previous.days ? { days: previous.days } : {}),
      })
      setUndo(null)
      notify(`Feedback restored for ${previous.title}.`)
      reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not undo this feedback.')
      if (caught instanceof APIError && caught.status === 409) {
        setUndo(null)
        reload()
      }
    } finally {
      setBusy(false)
    }
  }
  function substitute(key: Slot, work: number) {
    if (!bundle.data) return
    setPicks(
      Object.fromEntries(
        bundle.data.slots
          .filter((slot) => slot.selected)
          .map((slot) => [slot.key, slot.key === key ? work : slot.selected!.id]),
      ),
    )
  }
  if (!user) return null
  const data = bundle.data
  return (
    <section className="recommendations" aria-labelledby="recommendations-title">
      <div className="recommendation-heading">
        <div>
          <span className="eyebrow">Your next reading bundle</span>
          <h2 id="recommendations-title">Three ways into your next book.</h2>
        </div>
        <div className="toolbar">
          <button className="button secondary" onClick={() => setEditing((value) => !value)}>
            {editing ? 'Close preferences' : 'Your interests'}
          </button>
          <button className="button secondary" disabled={busy || bundle.loading} onClick={reload}>
            Refresh bundle
          </button>
        </div>
      </div>
      <p className="small-text muted">
        A familiar direction, an author to discover, and a shorter read. Swap any book to shape a small,
        varied choice.
      </p>
      {data && (editing || data.needs_preferences_review) && (
        <PreferencesForm
          initial={data.preferences}
          onSaved={() => {
            setEditing(false)
            reload()
          }}
        />
      )}
      {(error || bundle.error) && (
        <ErrorNotice>
          {error || bundle.error}{' '}
          {bundle.error && (
            <button className="text-link" onClick={reload}>
              Refresh bundle choices
            </button>
          )}
        </ErrorNotice>
      )}
      {undo && (
        <p className="notice" role="status">
          Feedback saved for {undo.title}.{' '}
          <button className="text-link" disabled={busy} onClick={() => void undoLast()}>
            Undo
          </button>
        </p>
      )}
      {bundle.loading ? (
        <Loading />
      ) : (
        data && (
          <>
            <p className="small-text muted">{data.note}</p>
            {!data.personalized && !data.needs_preferences_review && (
              <p className="notice">
                These are catalog starting points. Save interests, bookmark rankings or use More like to make
                the next bundle more personal.
              </p>
            )}
            <div className="recommendation-grid">
              {data.slots.map((slot) => (
                <article className="panel panel-body recommendation-card" key={slot.key}>
                  <span className="eyebrow">{slot.title}</span>
                  <p className="small-text muted">{slot.explanation}</p>
                  {slot.selected ? (
                    <BookSuggestion
                      candidate={slot.selected}
                      busy={busy}
                      onFeedback={(...args) => void choose(...args)}
                    />
                  ) : (
                    <Empty title="No matching book">
                      Broaden your saved filter or interests, or review hidden books below. Missing lengths
                      never qualify as short books.
                    </Empty>
                  )}
                  {slot.alternatives.length > 0 && (
                    <details className="recommendation-alternatives">
                      <summary>Choose a substitute · {slot.alternatives.length}</summary>
                      {slot.alternatives.map((alternative) => (
                        <div className="recommendation-alternative" key={alternative.id}>
                          <a className="text-link" href={`#/books/${alternative.id}`}>
                            {alternative.title}
                          </a>
                          <p className="small-text muted">
                            {alternative.authors.join(' · ') || 'Author not recorded'} ·{' '}
                            {alternative.pages == null ? 'Length unknown' : `${alternative.pages} pages`}
                            {alternative.estimate.estimated_hours == null
                              ? ''
                              : ` · about ${hours(alternative.estimate.estimated_hours)} hours`}
                          </p>
                          <p className="small-text">{alternative.reasons[0]}</p>
                          <button
                            className="button secondary"
                            disabled={busy || bundle.loading}
                            onClick={() => substitute(slot.key, alternative.id)}
                          >
                            Use this book
                          </button>
                        </div>
                      ))}
                    </details>
                  )}
                </article>
              ))}
            </div>
            {data.commitment.books > 0 && (
              <div className="notice recommendation-commitment">
                <strong>For these {data.commitment.books} books:</strong>{' '}
                {data.commitment.known_pages.toLocaleString()} recorded pages
                {data.commitment.unknown_pages
                  ? ` + ${data.commitment.unknown_pages} unknown length${data.commitment.unknown_pages === 1 ? '' : 's'}`
                  : ''}
                .{' '}
                {data.commitment.unknown_estimates === data.commitment.books ? (
                  'Reading time is unavailable.'
                ) : (
                  <>
                    About {hours(data.commitment.known_estimated_hours)} hours
                    {data.commitment.unknown_estimates
                      ? ` for the ${data.commitment.books - data.commitment.unknown_estimates} books with known time`
                      : ''}
                    , with an illustrative {hours(data.commitment.known_low_hours)}–
                    {hours(data.commitment.known_high_hours)} hour range.
                  </>
                )}{' '}
                <span className="small-text">
                  This bundle is a choice to explore; it does not add books or allocations to your plan.
                </span>
              </div>
            )}
          </>
        )
      )}
      <button
        className="text-link"
        aria-expanded={historyOpen}
        onClick={() => setHistoryOpen((value) => !value)}
      >
        {historyOpen ? 'Hide' : 'Review'} private feedback and deferred books
      </button>
      {historyOpen && (
        <div className="panel panel-body recommendation-history">
          <h3>Your saved discovery feedback</h3>
          <p className="small-text muted">
            Clear any signal to reverse it. Later lasts 30 days from the action and returns automatically when
            that period ends. These choices are private.
          </p>
          {feedback.error && <ErrorNotice>{feedback.error}</ErrorNotice>}
          {feedback.loading ? (
            <Loading />
          ) : (
            <>
              {feedback.data?.results.map((row) => (
                <div className="recommendation-feedback-row" key={row.work}>
                  <div>
                    <a className="text-link" href={`#/books/${row.work}`}>
                      {row.title}
                    </a>
                    <p className="small-text muted">
                      {actionLabel[row.action]}
                      {row.deferred_until
                        ? ` until ${row.deferred_until}${row.active ? '' : ' · expired'}`
                        : ''}
                      {row.archived ? ' · archived catalog record' : ''}
                    </p>
                  </div>
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => void choose(row.work, 'neutral', row.revision, row.action, row.title)}
                  >
                    Clear signal
                  </button>
                </div>
              ))}
              {feedback.data && !feedback.data.results.length && (
                <p className="muted">No saved feedback on this page.</p>
              )}
              <div className="toolbar">
                <button
                  className="button secondary"
                  disabled={page <= 1}
                  onClick={() => setPage((value) => value - 1)}
                >
                  Previous
                </button>
                <span className="small-text">
                  Page {page} of {feedback.data?.pages || 1} · {feedback.data?.count || 0} signals
                </span>
                <button
                  className="button secondary"
                  disabled={page >= (feedback.data?.pages || 1)}
                  onClick={() => setPage((value) => value + 1)}
                >
                  Next
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  )
}

import { useEffect, useState } from 'react'
import { useResource } from './api'
import { useApp } from './context'
import { Empty, ErrorNotice, Loading, PageHeader, label } from './components'
import { Pager } from './pagination'
import type { Page } from './types'
import { Recommendations } from './recommendations'
import {
  SavedFilterManager,
  blankDiscoveryFilters,
  initialSavedFilter,
  normalizeDiscoveryFilters,
  type DiscoveryFilters,
} from './savedFilters'

type Membership = { id: number; title: string; kind: string; slug: string }
type Step = {
  work: number
  title: string
  authors: string[]
  reading: string
  question: string
  bridge: string
  available: boolean
  read: boolean
  status: string | null
  lists: Membership[]
}
type Trail = {
  id: string
  title: string
  theme: string
  scope: string
  steps: Step[]
  next_work: number | null
}
function ListLinks({ lists }: { lists: Membership[] }) {
  return (
    <details className="small-text">
      <summary>
        {lists.length} related visible list{lists.length === 1 ? '' : 's'}
      </summary>
      {lists.map((r) => (
        <p key={r.id}>
          <a
            className="text-link"
            href={`#/rankings/${r.id}${r.slug === 'classical-education-guide' ? '?group=classical-education' : ''}`}
          >
            {r.title}
          </a>{' '}
          · {r.kind}
        </p>
      ))}
    </details>
  )
}

export function ReadingTrails() {
  const { user, version } = useApp()
  const r = useResource<{ note: string; trails: Trail[] }>(user ? '/api/reading-trails/' : null, version)
  const [selected, setSelected] = useState(
      new URLSearchParams(location.hash.split('?')[1]).get('trail') || '',
    ),
    [search, setSearch] = useState('')
  if (!user)
    return <Empty title="Reading trails">Sign in to connect these sequences with your reading history.</Empty>
  const trail = r.data?.trails.find((t) => t.id === selected)
  return (
    <>
      <PageHeader
        eyebrow="Connections, not rankings"
        title="Reading trails."
        actions={
          <a className="button secondary" href="#/discover">
            Discover for me →
          </a>
        }
      >
        Follow a question across books, traditions and existing lists. Step numbers express reading order—not
        merit.
      </PageHeader>
      {r.error && <ErrorNotice>{r.error}</ErrorNotice>}
      {r.loading ? (
        <Loading />
      ) : (
        <>
          <p className="notice">{r.data?.note}</p>
          {!trail ? (
            <>
              <input
                className="search-input"
                aria-label="Search reading trails"
                placeholder="Search themes and trails…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <div className="rankings-grid">
                {r.data?.trails
                  .filter((t) =>
                    `${t.title} ${t.theme} ${t.scope}`.toLowerCase().includes(search.toLowerCase()),
                  )
                  .map((t) => (
                    <article className="panel panel-body" key={t.id}>
                      <span className="eyebrow">{t.theme}</span>
                      <h2>{t.title}</h2>
                      <p>{t.scope}</p>
                      <p className="small-text muted">
                        {t.steps.length} reading steps · {t.steps.filter((s) => s.read).length} whole books
                        recorded finished
                      </p>
                      <button className="button primary" onClick={() => setSelected(t.id)}>
                        Explore this trail
                      </button>
                    </article>
                  ))}
              </div>
              {r.data &&
                !r.data.trails.some((t) =>
                  `${t.title} ${t.theme} ${t.scope}`.toLowerCase().includes(search.toLowerCase()),
                ) && <Empty title="No matching trails">Try a broader term.</Empty>}
            </>
          ) : (
            <>
              <button className="text-link" onClick={() => setSelected('')}>
                ← All trails
              </button>
              <h2>{trail.title}</h2>
              <p>{trail.scope}</p>
              <p className="small-text muted">
                {trail.next_work
                  ? 'Suggested continuation highlights the first book not recorded finished; skip freely if you are only reading the suggested selections.'
                  : 'All linked books are recorded finished. Revisit any passage you like.'}
              </p>
              <ol className="reading-trail-steps">
                {trail.steps.map((s, index) => (
                  <li className="panel panel-body" key={s.work}>
                    <span className="eyebrow">
                      Step {index + 1} ·{' '}
                      {s.read ? 'Book recorded finished' : s.status ? label(s.status) : 'Not in your library'}
                      {trail.next_work === s.work && ' · Suggested continuation'}
                    </span>
                    <h3>
                      {s.available ? (
                        <a className="text-link" href={`#/books/${s.work}`}>
                          {s.title}
                        </a>
                      ) : (
                        s.title
                      )}
                    </h3>
                    <p className="small-text muted">{s.authors.join(', ')}</p>
                    <p>{s.bridge}</p>
                    <p>
                      <strong>Read:</strong> {s.reading}
                    </p>
                    <p className="notice">{s.question}</p>
                    <ListLinks lists={s.lists} />
                    {s.available ? (
                      <p>
                        <a className="text-link" href={`#/books/${s.work}`}>
                          Open book, editions & library actions →
                        </a>
                      </p>
                    ) : (
                      <p className="muted">Catalog record unavailable; this step is preserved.</p>
                    )}
                  </li>
                ))}
              </ol>
            </>
          )}
        </>
      )}
    </>
  )
}

type DiscoveryRow = {
  id: number
  title: string
  authors: string[]
  ranking_count: number
  pages: number | null
  page_basis: string
  status: string | null
  read: boolean
  lists: Membership[]
}
const presets = [
  {
    title: 'Unread · several rankings',
    filters: { ...blankDiscoveryFilters(), unread: 'yes', minimum: '2' },
  },
  {
    title: 'Short books on my wishlist',
    filters: { ...blankDiscoveryFilters(), wishlist: 'yes', max_pages: '250' },
  },
  {
    title: 'Authors I haven’t explored',
    filters: { ...blankDiscoveryFilters(), new_authors: 'yes', unread: 'yes' },
  },
  {
    title: 'Unread · my bookmarked rankings',
    filters: { ...blankDiscoveryFilters(), bookmarked: 'yes', unread: 'yes' },
  },
]
export function PersonalDiscovery() {
  const { user, version } = useApp()
  const [selected, setSelected] = useState(initialSavedFilter)
  const [draft, setDraft] = useState<DiscoveryFilters>(presets[0].filters),
    [filters, setFilters] = useState<DiscoveryFilters>(presets[0].filters),
    [page, setPage] = useState(1)
  const [loadSaved, setLoadSaved] = useState(Boolean(initialSavedFilter()))
  const r = useResource<Page<DiscoveryRow> & { note: string; filters: DiscoveryFilters }>(
    user
      ? `/api/personal-discovery/?${new URLSearchParams({ ...(loadSaved ? { saved_filter: selected } : filters), page: String(page) })}`
      : null,
    version,
  )
  const facets = useResource<{ countries: string[]; genres: string[] }>(
    user ? '/api/works/facets/' : null,
    version,
  )
  useEffect(() => {
    if (loadSaved && r.data && !r.loading && !r.error) {
      const next = normalizeDiscoveryFilters(r.data.filters)
      setDraft(next)
      setFilters(next)
      setLoadSaved(false)
    }
  }, [r.data, r.loading, r.error, loadSaved])
  function apply(f: DiscoveryFilters, id = selected) {
    setDraft(f)
    setFilters(f)
    setPage(1)
    setLoadSaved(false)
    setSelected(id)
  }
  if (!user)
    return (
      <Empty title="Discover for me">Sign in to filter using your own wishlist and reading history.</Empty>
    )
  return (
    <>
      <PageHeader
        eyebrow="Your library, a different lens"
        title="Discover for me."
        actions={
          <a className="button secondary" href="#/trails">
            Reading trails →
          </a>
        }
      >
        Combine catalog details with your own reading history and bookmarks, and save useful discoveries for
        later.
      </PageHeader>
      <Recommendations />
      <h2>Browse with your own filters</h2>
      <div className="toolbar">
        {presets.map((p) => (
          <button className="button secondary" key={p.title} onClick={() => apply(p.filters, '')}>
            {p.title}
          </button>
        ))}
      </div>
      <form
        className="panel panel-body"
        onSubmit={(e) => {
          e.preventDefault()
          apply(draft)
        }}
      >
        <div className="form-grid">
          <label className="field">
            <span>Title or author</span>
            <input
              className="input"
              maxLength={300}
              value={draft.search}
              onChange={(e) => setDraft({ ...draft, search: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Minimum distinct rankings</span>
            <input
              className="input"
              type="number"
              min={0}
              max={1000}
              required
              value={draft.minimum}
              onChange={(e) => setDraft({ ...draft, minimum: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Maximum pages · 0 means any length</span>
            <input
              className="input"
              type="number"
              min={0}
              max={100000}
              required
              value={draft.max_pages}
              onChange={(e) => setDraft({ ...draft, max_pages: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Catalog field</span>
            <select
              className="select"
              value={draft.field}
              onChange={(e) => setDraft({ ...draft, field: e.target.value })}
            >
              <option value="">All fields</option>
              {['literature', 'philosophy', 'nonfiction', 'manga'].map((f) => (
                <option key={f} value={f}>
                  {label(f)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Genre</span>
            <select
              className="select"
              value={draft.genre}
              onChange={(e) => setDraft({ ...draft, genre: e.target.value })}
            >
              <option value="">All genres</option>
              {draft.genre && !facets.data?.genres.includes(draft.genre) && <option>{draft.genre}</option>}
              {facets.data?.genres.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Country association</span>
            <select
              className="select"
              value={draft.country}
              onChange={(e) => setDraft({ ...draft, country: e.target.value })}
            >
              <option value="">Every country</option>
              {draft.country && !facets.data?.countries.includes(draft.country) && (
                <option>{draft.country}</option>
              )}
              {facets.data?.countries.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="toolbar">
          {(['unread', 'wishlist', 'new_authors', 'bookmarked'] as const).map((key) => (
            <label className="checkbox-field" key={key}>
              <input
                type="checkbox"
                checked={draft[key] === 'yes'}
                onChange={(e) => setDraft({ ...draft, [key]: e.target.checked ? 'yes' : '' })}
              />
              {
                {
                  unread: 'Not recorded finished',
                  wishlist: 'On my wishlist',
                  new_authors: 'Authors not yet explored',
                  bookmarked: 'In my bookmarked rankings',
                }[key]
              }
            </label>
          ))}
        </div>
        <div className="toolbar">
          <button className="button primary" disabled={r.loading}>
            Apply filters
          </button>
          <button
            type="button"
            className="button secondary"
            onClick={() => apply(blankDiscoveryFilters(), '')}
          >
            Clear filters
          </button>
        </div>
      </form>
      <SavedFilterManager filters={draft} onApply={apply} selected={selected} onSelect={setSelected} />
      {r.error && <ErrorNotice>{r.error}</ErrorNotice>}
      {facets.error && <ErrorNotice>{facets.error}</ErrorNotice>}
      <details className="panel panel-body">
        <summary>How these filters work</summary>
        <p>{r.data?.note}</p>
        <p>
          Results are alphabetical, or shortest first when a page limit is set. A wishlist can be empty;
          reading history outside Marginalia is unknown. Applying a saved filter in your library or planner
          limits it to books already saved there.
        </p>
      </details>
      {r.loading ? (
        <Loading />
      ) : (
        <div className="rankings-grid">
          {r.data?.results.map((w) => (
            <article className="panel panel-body" key={w.id}>
              <h3>
                <a className="text-link" href={`#/books/${w.id}`}>
                  {w.title}
                </a>
              </h3>
              <p>{w.authors.join(', ') || 'Author not recorded'}</p>
              <p className="small-text muted">
                {w.ranking_count} rankings ·{' '}
                {w.read ? 'Recorded finished' : w.status ? label(w.status) : 'No recorded library status'}
                <br />
                {w.pages ? `${w.pages} pages · ${w.page_basis}` : `Length unknown · ${w.page_basis}`}
              </p>
              <ListLinks lists={w.lists} />
              <p>
                <a className="text-link" href={`#/books/${w.id}`}>
                  Open book & library actions →
                </a>
              </p>
            </article>
          ))}
          {r.data && !r.data.count && (
            <Empty title="No books match these filters">
              Try increasing the page limit or clearing a filter. Unknown lengths are excluded only when a
              page limit is set.
            </Empty>
          )}
        </div>
      )}
      <Pager page={page} data={r.data} setPage={setPage} loading={r.loading} />
    </>
  )
}

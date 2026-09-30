import { useEffect, useRef, useState } from 'react'
import { Globe2, RotateCcw } from 'lucide-react'
import { useResource } from './api'
import { useApp } from './context'
import { BookRow, Empty, ErrorNotice, Loading, PageHeader, label } from './components'
import AtlasMap, { isMappedCountry } from './atlasMap'
import { positivePage, useBrowseSearch, useBrowseState } from './navigation'
import { Pager } from './pagination'
import { queryCache } from './queryCache'
import type { ApiCatalogAtlas } from './generated/apiContracts'
import './catalogAtlas.css'

type Metric = 'all' | 'saved' | 'read'
type Facet = ApiCatalogAtlas['centuries'][number]
const countFor = (row: Facet, metric: Metric) => (metric === 'all' ? row.count : row[metric])

function CenturyTimeline({
  centuries,
  selected,
  metric,
  onSelect,
}: {
  centuries: Facet[]
  selected: string
  metric: Metric
  onSelect: (century: string) => void
}) {
  const known = centuries.filter((row) => row.key !== 'unknown')
  const unknown = centuries.find((row) => row.key === 'unknown')
  const keys = known.map((row) => Number(row.key)).filter(Number.isFinite)
  const first = Math.min(...keys),
    last = Math.max(...keys)
  const byKey = new Map(known.map((row) => [row.key, row]))
  const slots: { key: string; label: string; count: number; saved: number; read: number }[] = []
  for (let century = first; century <= last; century++) {
    if (!century) continue
    const key = String(century)
    slots.push(
      byKey.get(key) || {
        key,
        label: `${Math.abs(century)} century ${century < 0 ? 'BCE' : 'CE'}`,
        count: 0,
        saved: 0,
        read: 0,
      },
    )
  }
  const max = Math.max(1, ...known.map((row) => row.count))
  return (
    <section className="panel atlas-timeline">
      <div className="panel-header">
        <h2>Through the centuries</h2>
        <button className="text-button" disabled={!selected} onClick={() => onSelect('')}>
          All dates
        </button>
      </div>
      <div className="panel-body">
        <p className="small-text muted" id="atlas-timeline-help">
          Select a century to explore it on the map. Bars use saved original publication dates; blank
          centuries stay in place.
          {metric !== 'all' &&
            ' The pale bars show the catalog; solid bars show your selected reading overlay.'}
        </p>
        {slots.length ? (
          <div
            className="atlas-timeline-scroll"
            tabIndex={0}
            role="region"
            aria-label="Scrollable century timeline"
            aria-describedby="atlas-timeline-help"
          >
            <div
              className="atlas-century-bars"
              style={{ gridTemplateColumns: `repeat(${slots.length}, minmax(38px, 1fr))` }}
            >
              {slots.map((row) => (
                <button
                  key={row.key}
                  className={`atlas-century ${selected === row.key ? 'selected' : ''}`}
                  aria-pressed={selected === row.key}
                  aria-label={`${row.label}: ${countFor(row, metric)} ${metric === 'all' ? 'catalog books' : metric === 'read' ? 'books read' : 'saved books'}${metric !== 'all' ? ` of ${row.count} catalog books` : ''}`}
                  title={`${row.label}: ${countFor(row, metric).toLocaleString()} books`}
                  onClick={() => onSelect(selected === row.key ? '' : row.key)}
                >
                  <span className="atlas-century-value">{countFor(row, metric) || '·'}</span>
                  <span className="atlas-century-track" aria-hidden="true">
                    <span className="atlas-century-total" style={{ height: `${(100 * row.count) / max}%` }} />
                    <span
                      className="atlas-century-overlay"
                      style={{ height: `${(100 * countFor(row, metric)) / max}%` }}
                    />
                  </span>
                  <span>
                    {Math.abs(Number(row.key))}
                    <small>{Number(row.key) < 0 ? 'BCE' : 'CE'}</small>
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <p className="muted">No dated books match these filters.</p>
        )}
        {!!unknown && (
          <button
            className={`button secondary small ${selected === 'unknown' ? 'selected' : ''}`}
            aria-pressed={selected === 'unknown'}
            onClick={() => onSelect(selected === 'unknown' ? '' : 'unknown')}
          >
            Date not established · {countFor(unknown, metric).toLocaleString()}
          </button>
        )}
      </div>
    </section>
  )
}

export function CatalogAtlas() {
  const { user, version } = useApp()
  const [browse, patch] = useBrowseState({
    q: '',
    field: '',
    country: '',
    century: '',
    overlay: 'all',
    page: '1',
  })
  const [search, setSearch] = useBrowseSearch(browse.q, patch)
  const [countrySearch, setCountrySearch] = useState('')
  const page = positivePage(browse.page)
  const metric: Metric =
    user && (browse.overlay === 'saved' || browse.overlay === 'read') ? browse.overlay : 'all'
  const params = new URLSearchParams({ ...browse, overlay: metric, page: String(page) })
  const atlas = useResource<ApiCatalogAtlas>(`/api/catalog-atlas/?${params}`, version)
  // Keep the map mounted during a filter request so zoom, focus and scroll survive.
  // Retained results are shown only within the same account/session generation.
  const generation = queryCache.generation
  const [previous, setPrevious] = useState<{ generation: number; data: ApiCatalogAtlas } | null>(null)
  const filterFocus = useRef<HTMLDivElement>(null)
  const selectedControl = useRef<Element | null>(null)
  useEffect(() => {
    if (atlas.data) {
      setPrevious({ generation, data: atlas.data })
      if (
        selectedControl.current &&
        !selectedControl.current.isConnected &&
        document.activeElement === document.body
      )
        filterFocus.current?.focus({ preventScroll: true })
      selectedControl.current = null
    } else setPrevious((old) => (old?.generation === generation ? old : null))
  }, [atlas.data, generation])
  const data = atlas.data || (atlas.loading && previous?.generation === generation ? previous.data : null)
  const setCountry = (value: string) => {
    selectedControl.current = document.activeElement
    patch({ country: value, page: 1 })
  }
  const setCentury = (value: string) => {
    selectedControl.current = document.activeElement
    patch({ century: value, page: 1 })
  }
  const reset = () => {
    setSearch('')
    setCountrySearch('')
    patch({ q: '', field: '', country: '', century: '', overlay: 'all', page: 1 })
  }
  const countries = data?.countries || []
  const countryRows = countries.filter((row) =>
    row.label.toLocaleLowerCase().includes(countrySearch.toLocaleLowerCase()),
  )
  const unplaced = countries.filter((row) => !isMappedCountry(row.key))
  const chosenCountry =
    countries.find((row) => row.key === browse.country)?.label ||
    (browse.country === '__unknown__' ? 'Country not recorded' : browse.country)
  const chosenCentury =
    data?.centuries.find((row) => row.key === browse.century)?.label ||
    (browse.century === 'unknown' ? 'Date not established' : browse.century)
  return (
    <>
      <PageHeader
        eyebrow="Books across place & time"
        title="Atlas & timeline."
        actions={
          <a className="button secondary" href="#/catalog">
            Book catalog
          </a>
        }
      >
        Follow a place or a century into the catalog, and see where your own reading has taken you.
      </PageHeader>
      <div className="toolbar atlas-filters">
        <input
          className="search-input"
          aria-label="Search atlas books"
          placeholder="Search books, authors, or topics…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <select
          className="filter-select"
          aria-label="Atlas subject"
          value={browse.field}
          onChange={(event) => patch({ field: event.target.value, page: 1 })}
        >
          <option value="">All subjects</option>
          {['literature', 'philosophy', 'nonfiction', 'manga'].map((field) => (
            <option key={field} value={field}>
              {label(field)}
            </option>
          ))}
        </select>
        <select
          className="filter-select"
          aria-label="Reading overlay"
          value={metric}
          onChange={(event) => patch({ overlay: event.target.value, page: 1 })}
        >
          <option value="all">All catalog books</option>
          <option value="saved" disabled={!user}>
            In my library
          </option>
          <option value="read" disabled={!user}>
            Books I have read
          </option>
        </select>
        <button className="button secondary small" onClick={reset}>
          <RotateCcw size={14} /> Reset
        </button>
      </div>
      {!user && <p className="small-text muted">Sign in to overlay your saved and finished books.</p>}
      <div
        ref={filterFocus}
        tabIndex={-1}
        className="atlas-active-filters"
        role="group"
        aria-label="Selected atlas filters"
      >
        {browse.country && (
          <button className="button secondary small" onClick={() => setCountry('')}>
            {chosenCountry} ×
          </button>
        )}
        {browse.century && (
          <button className="button secondary small" onClick={() => setCentury('')}>
            {chosenCentury} ×
          </button>
        )}
      </div>
      {atlas.error && <ErrorNotice>{atlas.error}</ErrorNotice>}
      {atlas.loading && !data && <Loading />}
      {atlas.loading && data && (
        <p className="small-text muted" role="status">
          Updating the atlas… Previous results remain visible until the new view is ready.
        </p>
      )}
      {data && (
        <div className="atlas-content" aria-busy={atlas.loading}>
          <div className="atlas-summary" aria-live="polite">
            <div>
              <strong>{data.count.toLocaleString()}</strong>
              <span>Books matching your view</span>
            </div>
            <div>
              <strong>{data.summary.saved.toLocaleString()}</strong>
              <span>In your library</span>
            </div>
            <div>
              <strong>{data.summary.read.toLocaleString()}</strong>
              <span>Read at least once</span>
            </div>
            <div>
              <strong>{data.summary.undated.toLocaleString()}</strong>
              <span>Catalog books without a date</span>
            </div>
          </div>
          <section className="panel">
            <div className="panel-header">
              <h2>
                <Globe2 size={18} /> A world of writing
              </h2>
              <button className="text-button" disabled={!browse.country} onClick={() => setCountry('')}>
                All places
              </button>
            </div>
            <div className="panel-body">
              <p className="small-text muted">
                Places reflect the catalog’s literary and cultural associations, not necessarily a book’s
                setting or an author’s birthplace. A book may appear in several places. Exact labels stay
                separate, including England and the United Kingdom.
              </p>
              <AtlasMap
                countries={countries}
                selected={browse.country}
                metric={metric}
                onSelect={(key) => setCountry(key === browse.country ? '' : key)}
              />
              <details className="atlas-places">
                <summary>
                  Browse all places and traditions · {countries.length} labels, {unplaced.length} without map
                  markers
                </summary>
                <p className="small-text muted">
                  Regional, historical, mixed and unrecorded associations remain available here. They are not
                  assigned to a modern country. Labels are preserved as recorded.
                </p>
                <input
                  className="input"
                  aria-label="Find a place or tradition"
                  placeholder="Find a country, region, or tradition…"
                  value={countrySearch}
                  onChange={(event) => setCountrySearch(event.target.value)}
                />
                <div className="atlas-place-list">
                  {countryRows.map((row) => (
                    <button
                      key={row.key}
                      aria-pressed={browse.country === row.key}
                      className={browse.country === row.key ? 'selected' : ''}
                      onClick={() => setCountry(row.key === browse.country ? '' : row.key)}
                    >
                      <span>
                        {row.label}
                        {!isMappedCountry(row.key) && <small>Not placed on map</small>}
                      </span>
                      <strong>{countFor(row, metric).toLocaleString()}</strong>
                    </button>
                  ))}
                  {!countryRows.length && <p className="muted">No matching labels.</p>}
                </div>
              </details>
            </div>
          </section>
          <CenturyTimeline
            centuries={data.centuries}
            selected={browse.century}
            metric={metric}
            onSelect={setCentury}
          />
          <section className="panel">
            <div className="panel-header">
              <h2>Explore these books</h2>
              <span className="small-text muted">{data.count.toLocaleString()} results</span>
            </div>
            <p className="atlas-reading-note small-text muted">
              “Read” includes completed earlier readings, even if you are reading a book again. Dates use the
              saved original year and may be approximate; this view does not establish exact composition
              dates. Counts describe the saved catalog’s coverage.
            </p>
            {!!(data.summary.invalid_year || data.summary.invalid_countries) && (
              <p className="atlas-reading-note small-text muted">
                Some stored metadata needs review: {data.summary.invalid_year} invalid dates and{' '}
                {data.summary.invalid_countries} malformed country records. Those records stay accessible
                without invented metadata.
              </p>
            )}
            {data.results.map((row) => (
              <article className="atlas-book" key={row.book.id}>
                <BookRow
                  work={row.book}
                  action={
                    <span className="atlas-book-date">
                      {row.date_status === 'known' && row.original_year !== null
                        ? `${Math.abs(row.original_year)} ${row.original_year < 0 ? 'BCE' : 'CE'}`
                        : 'Date not established'}
                      {row.read ? <small>✓ Read</small> : row.saved ? <small>In your library</small> : null}
                    </span>
                  }
                />
                <div className="atlas-book-places">
                  {row.book.countries.length ? (
                    row.book.countries.map((country) => (
                      <button key={country} className="text-button" onClick={() => setCountry(country)}>
                        {country}
                      </button>
                    ))
                  ) : (
                    <button className="text-button" onClick={() => setCountry('__unknown__')}>
                      Country not recorded
                    </button>
                  )}
                </div>
              </article>
            ))}
            {!data.results.length && (
              <Empty
                title="No books in this view."
                action={
                  <button className="button secondary" onClick={reset}>
                    Show the whole catalog
                  </button>
                }
              >
                Try another place, century, or reading overlay.
              </Empty>
            )}
          </section>
          <Pager
            page={page}
            data={data}
            setPage={(value) => patch({ page: value })}
            loading={atlas.loading}
          />
        </div>
      )}
    </>
  )
}

import { useEffect, useState } from 'react'
import { api, useResource } from './api'
import { useApp } from './context'
import { ErrorNotice } from './components'
import './discoveryImprovements.css'

export type DiscoveryFilters = {
  search: string
  field: string
  genre: string
  country: string
  minimum: string
  max_pages: string
  unread: string
  wishlist: string
  new_authors: string
  bookmarked: string
}
export type SavedDiscoveryFilter = {
  id: number
  name: string
  filters: DiscoveryFilters
  created_at: string
  updated_at: string
}
type FilterContext = 'discovery' | 'library' | 'planner' | 'catalog'
export const blankDiscoveryFilters = (): DiscoveryFilters => ({
  search: '',
  field: '',
  genre: '',
  country: '',
  minimum: '0',
  max_pages: '0',
  unread: '',
  wishlist: '',
  new_authors: '',
  bookmarked: '',
})
export const normalizeDiscoveryFilters = (filters: Partial<DiscoveryFilters>): DiscoveryFilters =>
  Object.fromEntries(
    Object.entries({ ...blankDiscoveryFilters(), ...filters }).map(([key, value]) => [key, String(value)]),
  ) as DiscoveryFilters
export const initialSavedFilter = () =>
  new URLSearchParams(window.location.hash.split('?')[1] || '').get('saved_filter') || ''

function FilterLinks({ id, context }: { id: string; context: FilterContext }) {
  return (
    <span className="saved-filter-links">
      {(
        [
          ['discovery', 'discover', 'Discover'],
          ['catalog', 'catalog', 'Catalog'],
          ['library', 'library', 'Library'],
          ['planner', 'planner', 'Plan'],
        ] as const
      )
        .filter(([key]) => key !== context)
        .map(([key, route, title]) => (
          <a
            className="text-link small-text"
            key={key}
            href={`#/${route}?saved_filter=${encodeURIComponent(id)}`}
          >
            {title} →
          </a>
        ))}
    </span>
  )
}

function filterDescription(filters: DiscoveryFilters): string {
  const values = normalizeDiscoveryFilters(filters)
  return (
    [
      values.search && `Search: ${values.search}`,
      values.field,
      values.genre,
      values.country,
      Number(values.minimum) > 0 && `At least ${values.minimum} rankings`,
      Number(values.max_pages) > 0 && `Up to ${values.max_pages} pages`,
      values.unread && 'Not recorded finished',
      values.wishlist && 'Wishlist only',
      values.new_authors && 'Authors not yet explored',
      values.bookmarked && 'My bookmarked rankings',
    ]
      .filter(Boolean)
      .join(' · ') || 'No restrictions saved'
  )
}

export function SavedFilterPicker({
  value,
  onChange,
  context = 'catalog',
}: {
  value: string
  onChange: (id: string) => void
  context?: FilterContext
}) {
  const { user, version } = useApp()
  const r = useResource<SavedDiscoveryFilter[]>(user ? '/api/saved-filters/' : null, version)
  if (!user) return null
  const current = r.data?.find((item) => String(item.id) === value)
  return (
    <div className="saved-filter-picker">
      <label className="field">
        <span>Saved discovery filter</span>
        <select
          className="select"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={r.loading}
        >
          <option value="">All books · no saved filter</option>
          {value && !current && (
            <option value={value}>{r.loading ? 'Loading saved filter…' : 'Filter unavailable'}</option>
          )}
          {r.data?.map((item) => (
            <option value={item.id} key={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {current && <p className="small-text muted">{filterDescription(current.filters)}</p>}
      {value && <FilterLinks id={value} context={context} />}
      <a
        className="text-link small-text"
        href={value ? `#/discover?saved_filter=${encodeURIComponent(value)}` : '#/discover'}
      >
        Create or edit filters
      </a>
      {r.error && <ErrorNotice>{r.error}</ErrorNotice>}
    </div>
  )
}

export function SavedFilterManager({
  filters,
  onApply,
  selected = '',
  onSelect,
}: {
  filters: DiscoveryFilters
  onApply: (filters: DiscoveryFilters, id: string) => void
  selected?: string
  onSelect?: (id: string) => void
}) {
  const { user, version, mutate } = useApp()
  const r = useResource<SavedDiscoveryFilter[]>(user ? '/api/saved-filters/' : null, version)
  const [name, setName] = useState(''),
    [busy, setBusy] = useState(false),
    [confirmDelete, setConfirmDelete] = useState(false)
  const current = r.data?.find((item) => String(item.id) === selected)
  useEffect(() => {
    setName(current?.name || '')
    setConfirmDelete(false)
  }, [current?.id, current?.name])
  if (!user) return null
  const save = async (replace: boolean) => {
    setBusy(true)
    let saved: SavedDiscoveryFilter | null = null
    const okay = await mutate(
      async () => {
        saved = await api<SavedDiscoveryFilter>(
          replace && current ? `/api/saved-filters/${current.id}/` : '/api/saved-filters/',
          replace ? 'PATCH' : 'POST',
          { name: name.trim(), filters },
        )
      },
      replace ? 'Saved filter updated' : 'Discovery filter saved',
    )
    if (okay && saved) {
      const value = saved as SavedDiscoveryFilter
      onApply(normalizeDiscoveryFilters(value.filters), String(value.id))
      onSelect?.(String(value.id))
    }
    setBusy(false)
  }
  return (
    <section className="panel panel-body saved-filter-manager" aria-label="Saved discovery filters">
      <h2>Your saved filters</h2>
      <p className="small-text muted">
        Save a combination here, then use it in the catalog, library or planner. Your finished books,
        bookmarks and selected editions are checked each time.
      </p>
      <div className="toolbar">
        <label className="field">
          <span>Load a saved combination</span>
          <select
            className="select"
            value={selected}
            disabled={r.loading || busy}
            onChange={(e) => {
              const item = r.data?.find((row) => String(row.id) === e.target.value)
              if (item) onApply(normalizeDiscoveryFilters(item.filters), String(item.id))
              else onApply(blankDiscoveryFilters(), '')
              onSelect?.(e.target.value)
            }}
          >
            <option value="">New filter</option>
            {selected && !current && <option value={selected}>Loading saved filter…</option>}
            {r.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        {selected && current && <FilterLinks id={selected} context="discovery" />}
      </div>
      <div className="toolbar">
        <label className="field">
          <span>Filter name</span>
          <input
            className="input"
            value={name}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
            placeholder="Unread philosophy under 250 pages"
          />
        </label>
        <button
          type="button"
          className="button secondary"
          disabled={busy || !name.trim()}
          onClick={() => void save(false)}
        >
          Save as new
        </button>
        {current && (
          <>
            <button
              type="button"
              className="button primary"
              disabled={busy || !name.trim()}
              onClick={() => void save(true)}
            >
              Update saved filter
            </button>
            <button
              type="button"
              className="button secondary"
              disabled={busy}
              onClick={() => setConfirmDelete(true)}
            >
              Delete
            </button>
          </>
        )}
      </div>
      {confirmDelete && current && (
        <div className="notice">
          <p>Delete “{current.name}”? Your books, plans and reading history stay saved.</p>
          <div className="toolbar">
            <button className="button secondary" disabled={busy} onClick={() => setConfirmDelete(false)}>
              Keep filter
            </button>
            <button
              className="button secondary"
              disabled={busy}
              onClick={async () => {
                setBusy(true)
                if (
                  await mutate(
                    () => api(`/api/saved-filters/${current.id}/`, 'DELETE'),
                    'Saved filter deleted',
                  )
                ) {
                  onApply(filters, '')
                  onSelect?.('')
                  setConfirmDelete(false)
                  setName('')
                }
                setBusy(false)
              }}
            >
              Delete saved filter
            </button>
          </div>
        </div>
      )}
      {r.error && <ErrorNotice>{r.error}</ErrorNotice>}
      {selected && !r.loading && !current && !r.error && (
        <ErrorNotice>
          This saved filter is unavailable. Choose another filter or save a new combination.
        </ErrorNotice>
      )}
    </section>
  )
}

import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowUpRight, Search } from 'lucide-react'
import { useApp } from './context'
import { api } from './api'
import { Modal } from './components'
import { useDebouncedValue } from './navigation'
import { appSearchDestination, appSearchFocusIndex, isAppSearchShortcut } from './appSearch'
import type { ApiAppSearchResponse } from './generated/apiContracts'
import './appSearch.css'

function SearchDialog({ close }: { close: () => void }) {
  const input = useRef<HTMLInputElement>(null)
  const results = useRef<HTMLDivElement>(null)
  const [search, setSearch] = useState('')
  const query = search.trim()
  const settled = useDebouncedValue(query)
  const [retry, setRetry] = useState(0)
  const [response, setResponse] = useState<{
    query: string
    data: ApiAppSearchResponse | null
    error: string
  }>({ query: '', data: null, error: '' })

  useEffect(() => {
    const frame = requestAnimationFrame(() => input.current?.focus())
    return () => cancelAnimationFrame(frame)
  }, [])

  useEffect(() => {
    if (!settled || settled !== query) return
    const controller = new AbortController()
    api<ApiAppSearchResponse>(
      `/api/app-search/?q=${encodeURIComponent(settled)}`,
      'GET',
      undefined,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setResponse({ query: settled, data, error: '' })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setResponse({
            query: settled,
            data: null,
            error: error instanceof Error ? error.message : 'Search could not be loaded. Please try again.',
          })
      })
    return () => controller.abort()
  }, [settled, query, retry])

  const current = response.query === query ? response : null
  const groups = current?.data?.groups || []
  const pending = !!query && !current
  const total = groups.reduce((sum, group) => sum + group.items.length, 0)

  return createPortal(
    <div className="app-search-layer">
      <Modal title="Search Marginalia" close={close}>
        <div
          className="app-search"
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) {
              // Escape belongs to the IME until composition is complete.
              event.stopPropagation()
              return
            }
            if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
            const links = Array.from(
              results.current?.querySelectorAll<HTMLAnchorElement>(
                '.app-search-result, .app-search-catalog',
              ) || [],
            )
            const index = links.indexOf(document.activeElement as HTMLAnchorElement)
            if (document.activeElement !== input.current && index < 0) return
            event.preventDefault()
            const next = appSearchFocusIndex(index, event.key === 'ArrowDown' ? 1 : -1, links.length)
            const target = next < 0 ? input.current : links[next]
            target?.focus()
            target?.scrollIntoView({ block: 'nearest' })
          }}
        >
          <form
            role="search"
            aria-label="Search the app"
            onSubmit={(event) => {
              event.preventDefault()
              if (!query) return
              window.location.hash = appSearchDestination(query, groups)
              close()
            }}
          >
            <label className="app-search-input">
              <Search size={19} aria-hidden="true" />
              <input
                ref={input}
                type="search"
                aria-label="Search books, authors, rankings and study"
                aria-describedby="app-search-help"
                maxLength={300}
                autoComplete="off"
                placeholder="Books, authors, rankings…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === 'Enter' &&
                    (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229)
                  )
                    event.preventDefault()
                }}
              />
            </label>
            <p id="app-search-help" className="app-search-help">
              ↑ ↓ to choose · Enter to open · Esc to close
            </p>
          </form>

          <div className="app-search-results" ref={results} aria-busy={pending}>
            <p className="sr-only" role="status">
              {pending
                ? 'Searching…'
                : query && current?.data
                  ? `${total} suggestions in ${groups.length} groups.`
                  : ''}
            </p>
            {!query && (
              <p className="app-search-message">
                Find books and authors, jump to a ranking or collection, or search your study material. Try an
                author’s name or a publisher such as Guardian.
              </p>
            )}
            {pending && <p className="app-search-message">Searching…</p>}
            {current?.error && (
              <div className="notice danger" role="alert">
                <p>{current.error}</p>
                <button
                  className="button small"
                  onClick={() => {
                    setResponse({ query: '', data: null, error: '' })
                    setRetry((value) => value + 1)
                  }}
                >
                  Try again
                </button>
              </div>
            )}
            {!!query && current?.data && !total && (
              <p className="app-search-message">No matches. Try a shorter title, author or publisher name.</p>
            )}
            {groups.map((group) => (
              <section
                className="app-search-group"
                key={group.key}
                aria-labelledby={`app-search-${group.key}`}
              >
                <div className="app-search-group-heading">
                  <h3 id={`app-search-${group.key}`}>{group.label}</h3>
                  {group.has_more && group.more_href && (
                    <a className="text-link" href={group.more_href} onClick={close}>
                      Show more <span className="sr-only">{group.label}</span>
                    </a>
                  )}
                </div>
                <ul>
                  {group.items.map((item) => (
                    <li key={item.id}>
                      <a className="app-search-result" href={item.href} onClick={close}>
                        <span>
                          <strong>{item.title}</strong>
                          <small>{item.subtitle}</small>
                        </span>
                        <ArrowUpRight size={16} aria-hidden="true" />
                      </a>
                    </li>
                  ))}
                </ul>
                {group.has_more && !group.more_href && (
                  <p className="app-search-help">
                    More matches are available. Narrow your search to find them.
                  </p>
                )}
              </section>
            ))}
            {!!query && (
              <a
                className="app-search-catalog"
                href={`#/catalog?q=${encodeURIComponent(query)}`}
                onClick={close}
              >
                Search the book catalog for “{query}” <ArrowUpRight size={16} aria-hidden="true" />
              </a>
            )}
          </div>
        </div>
      </Modal>
    </div>,
    document.body,
  )
}

/** Dialog typing stays local to search rather than rerendering the reading screen. */
export const TopbarSearch = memo(function TopbarSearch() {
  const { user } = useApp()
  const [open, setOpen] = useState(false)
  const close = useCallback(() => setOpen(false), [])

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      const dialog = document.querySelector('[aria-modal="true"]')
      const otherDialog = !!dialog && !dialog.closest('.app-search-layer')
      if (!isAppSearchShortcut(event, otherDialog)) return
      event.preventDefault()
      setOpen(true)
      document.querySelector<HTMLInputElement>('.app-search input')?.focus()
    }
    window.addEventListener('keydown', shortcut)
    window.addEventListener('marginalia-session-changed', close)
    window.addEventListener('hashchange', close)
    return () => {
      window.removeEventListener('keydown', shortcut)
      window.removeEventListener('marginalia-session-changed', close)
      window.removeEventListener('hashchange', close)
    }
  }, [close])

  return (
    <>
      <button
        className="topbar-search app-search-trigger"
        type="button"
        aria-label="Search the app (Command or Control K)"
        aria-haspopup="dialog"
        aria-keyshortcuts="Meta+K Control+K"
        onClick={() => setOpen(true)}
      >
        <Search size={16} aria-hidden="true" />
        <span>Search anything…</span>
        <kbd>⌘ / Ctrl K</kbd>
      </button>
      {open && <SearchDialog key={user?.id || 'anonymous'} close={close} />}
    </>
  )
})

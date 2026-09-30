import { useEffect, useState } from 'react'
import { ArrowLeftRight, ExternalLink, Search } from 'lucide-react'
import { useResource } from './api'
import { BookRow, Empty, ErrorNotice, Loading, PageHeader } from './components'
import { useApp } from './context'
import type { ApiPublishedComparison } from './generated/apiContracts'
import { positivePage, useBrowseSearch, useBrowseState } from './navigation'
import { Pager } from './pagination'
import { queryCache } from './queryCache'
import './publishedComparison.css'

type ListDetail = NonNullable<ApiPublishedComparison['left']>
type ComparisonRow = ApiPublishedComparison['results'][number]

function sourceLink(value: string) {
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined
  } catch {
    return undefined
  }
}

function ListContext({ list, side }: { list: ListDetail; side: string }) {
  const url = sourceLink(list.source_url)
  return (
    <section className="panel panel-body published-list-context">
      <span className="eyebrow">List {side}</span>
      <h2>
        <a href={`#/rankings/${list.id}?group=published-rankings`}>{list.title}</a>
      </h2>
      <p className="small-text muted">
        {list.publisher || 'Publisher not recorded'} · {list.total.toLocaleString()} saved entries
      </p>
      <div className="published-scope-labels">
        {list.scope_labels.map((scope, index) => (
          <span className="pill" key={`${scope}-${index}`}>
            {scope}
          </span>
        ))}
      </div>
      <p className="small-text">{list.method || list.description || 'Method not recorded.'}</p>
      {list.limitation && <p className="small-text muted">{list.limitation}</p>}
      {list.known_ranks < list.total && (
        <p className="small-text muted">
          {list.total - list.known_ranks} saved entries have no recorded global publisher rank.
        </p>
      )}
      {list.unresolved_count != null && list.unresolved_count > 0 && (
        <p className="small-text muted">
          The saved import reports {list.unresolved_count} unresolved entries. Overlap may be incomplete.
        </p>
      )}
      {url ? (
        <a className="text-button" href={url} target="_blank" rel="noreferrer">
          Publisher source <ExternalLink size={13} aria-hidden="true" />
        </a>
      ) : (
        <span className="small-text muted">Source link not recorded</span>
      )}
    </section>
  )
}

function Rank({ rank, tied, included }: { rank: number | null; tied: boolean; included: boolean }) {
  return (
    <>
      <strong>{!included ? '—' : rank == null ? '?' : `#${rank}`}</strong>
      <span className="small-text muted">
        {!included
          ? 'Not in saved list'
          : rank == null
            ? 'Rank not recorded'
            : tied
              ? 'Tied'
              : 'Publisher rank'}
      </span>
    </>
  )
}

function ComparedEntry({ row }: { row: ComparisonRow }) {
  return (
    <article className="published-comparison-entry">
      {row.book ? (
        <BookRow work={row.book} />
      ) : row.person ? (
        <div className="book-row">
          <div className="book-info">
            <a className="book-title" href={`#/authors/${row.person.id}`}>
              {row.person.name}
            </a>
            <span className="book-author">{row.person.countries.join(' · ')}</span>
          </div>
        </div>
      ) : null}
      <div className="published-rank-pair">
        <div>
          <span className="eyebrow">List A</span>
          <Rank rank={row.left_rank} tied={row.left_tied} included={row.in_left} />
        </div>
        <div>
          <span className="eyebrow">List B</span>
          <Rank rank={row.right_rank} tied={row.right_tied} included={row.in_right} />
        </div>
        <div className="published-rank-difference">
          <span className="eyebrow">Position difference</span>
          <span>
            {row.delta == null
              ? 'Not comparable'
              : row.delta === 0
                ? 'Same position'
                : `${Math.abs(row.delta)} higher in ${row.delta > 0 ? 'A' : 'B'}`}
          </span>
        </div>
      </div>
    </article>
  )
}

export function PublishedComparison() {
  const { version } = useApp()
  const [browse, patch] = useBrowseState({
    left: '',
    right: '',
    view: 'shared',
    sort: 'left',
    q: '',
    page: '1',
  })
  const [search, setSearch] = useBrowseSearch(browse.q, patch)
  const page = positivePage(browse.page)
  // Keep selectors available when a stale shared URL points at a removed list.
  const choices = useResource<ApiPublishedComparison>('/api/published-comparison/', version)
  const params = new URLSearchParams({
    left: browse.left,
    right: browse.right,
    view: browse.view,
    sort: browse.sort,
    search: browse.q,
    page: String(page),
  })
  const result = useResource<ApiPublishedComparison>(
    `/api/published-comparison/?${params.toString()}`,
    version,
  )
  const options = choices.data?.options || result.data?.options || []
  const generation = queryCache.generation
  const pair = `${browse.left}|${browse.right}`
  const [previous, setPrevious] = useState<{
    generation: number
    pair: string
    data: ApiPublishedComparison
  } | null>(null)
  useEffect(() => {
    if (result.data) setPrevious({ generation, pair, data: result.data })
    else setPrevious((old) => (old?.generation === generation && old.pair === pair ? old : null))
  }, [result.data, generation, pair])
  // Keep search and view controls mounted during a filter request. A session
  // change or different pair never reuses another comparison's response.
  const data =
    result.data ||
    (result.loading && previous?.generation === generation && previous.pair === pair ? previous.data : null)
  const summary = data?.summary
  const choose = (side: 'left' | 'right', value: string) => {
    const other = side === 'left' ? 'right' : 'left'
    const picked = options.find((item) => String(item.id) === value)
    const partner = options.find((item) => String(item.id) === browse[other])
    patch({
      [side]: value,
      [other]:
        picked && partner && (picked.id === partner.id || picked.item_type !== partner.item_type)
          ? ''
          : browse[other],
      page: 1,
    })
  }
  return (
    <>
      <PageHeader
        eyebrow="Published rankings"
        title="Compare published lists."
        actions={
          <a className="button secondary" href="#/published-rankings">
            Browse published rankings
          </a>
        }
      >
        Shared choices, distinct inclusions and original publisher positions, side by side.
      </PageHeader>
      <div className="panel panel-body published-comparison-selectors">
        {(['left', 'right'] as const).map((side) => (
          <label key={side}>
            <span>List {side === 'left' ? 'A' : 'B'}</span>
            <select value={browse[side]} onChange={(event) => choose(side, event.target.value)}>
              <option value="">Choose a published list</option>
              {browse[side] && !options.some((item) => String(item.id) === browse[side]) && (
                <option value={browse[side]}>Unavailable list</option>
              )}
              {options.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title} · {item.total} {item.item_type === 'work' ? 'entries' : 'people'}
                </option>
              ))}
            </select>
          </label>
        ))}
        <button
          className="button secondary published-swap"
          disabled={!browse.left || !browse.right}
          onClick={() => patch({ left: browse.right, right: browse.left, page: 1 })}
        >
          <ArrowLeftRight size={16} aria-hidden="true" /> Swap lists
        </button>
      </div>
      {(choices.error || result.error) && <ErrorNotice>{result.error || choices.error}</ErrorNotice>}
      {result.error && (
        <button
          className="button secondary"
          onClick={() => patch({ left: '', right: '', page: 1, view: 'shared', sort: 'left', q: '' })}
        >
          Reset comparison
        </button>
      )}
      {result.loading &&
        (data ? (
          <p className="small-text muted" role="status">
            Updating comparison… Previous results remain visible until the new results arrive.
          </p>
        ) : (
          <Loading />
        ))}
      {data && !summary && (
        <Empty title="Choose two published lists">
          Compare books or people by their shared catalog identities. Reading collections and personal copies
          have their own sections and are not publisher rankings.
        </Empty>
      )}
      {data?.left && data.right && summary && (
        <>
          <div className="published-list-contexts">
            <ListContext list={data.left} side="A" />
            <ListContext list={data.right} side="B" />
          </div>
          <section className="panel panel-body published-overlap" aria-label="List overlap">
            <div className="published-overlap-stats">
              <div>
                <strong>{summary.left_only.toLocaleString()}</strong>
                <span>Only in A</span>
              </div>
              <div>
                <strong>{summary.shared.toLocaleString()}</strong>
                <span>In both lists</span>
              </div>
              <div>
                <strong>{summary.right_only.toLocaleString()}</strong>
                <span>Only in B</span>
              </div>
            </div>
            {summary.union > 0 && (
              <div className="published-overlap-bar" aria-hidden="true">
                <span style={{ width: `${(100 * summary.left_only) / summary.union}%` }} />
                <span style={{ width: `${(100 * summary.shared) / summary.union}%` }} />
                <span style={{ width: `${(100 * summary.right_only) / summary.union}%` }} />
              </div>
            )}
            <p className="small-text muted">
              {summary.union.toLocaleString()} distinct saved entries. Of {summary.comparable} shared entries
              with known ranks, {summary.different} have different positions. These totals cover the full
              saved lists, before search.
            </p>
          </section>
          <nav className="tabs" aria-label="Comparison membership">
            {[
              ['shared', 'In both', summary.shared],
              ['left_only', 'Only in A', summary.left_only],
              ['right_only', 'Only in B', summary.right_only],
            ].map(([value, label, count]) => (
              <button
                key={value}
                className={`tab ${browse.view === value ? 'active' : ''}`}
                aria-pressed={browse.view === value}
                onClick={() =>
                  patch({
                    view: value,
                    page: 1,
                    sort: value === 'right_only' ? 'right' : value === 'left_only' ? 'left' : browse.sort,
                  })
                }
              >
                {label} · {count}
              </button>
            ))}
          </nav>
          <div className="toolbar">
            <div className="search-box">
              <Search size={16} aria-hidden="true" />
              <input
                aria-label="Search comparison entries"
                placeholder="Search titles or authors…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <select
              className="filter-select"
              aria-label="Sort comparison"
              value={browse.sort}
              onChange={(event) => patch({ sort: event.target.value, page: 1 })}
            >
              <option value="left">List A position</option>
              <option value="right">List B position</option>
              <option value="difference">Largest position difference</option>
              <option value="title">Title / name</option>
            </select>
          </div>
          <p className="small-text muted">{data.note}</p>
          <section className="panel" aria-label="Compared entries" aria-busy={result.loading}>
            {data.results.map((row) => (
              <ComparedEntry key={row.id} row={row} />
            ))}
            {!data.results.length && (
              <Empty title="No matching entries">
                {browse.q
                  ? 'Try another search or comparison view.'
                  : 'There are no saved entries in this comparison view.'}
              </Empty>
            )}
          </section>
          <Pager page={page} data={data} setPage={(next) => patch({ page: next })} loading={result.loading} />
        </>
      )}
    </>
  )
}

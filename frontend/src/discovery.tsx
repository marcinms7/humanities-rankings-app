import { useState } from 'react'
import { useResource } from './api'
import { useApp } from './context'
import { Empty, ErrorNotice, Loading, PageHeader, label } from './components'
import { Pager } from './pagination'
import type { Page } from './types'

type Placement = {
  id: number
  title: string
  slug: string
  origin: string
  presentation: string
  domain: string
  publisher: string
  revision: number
  updated: string | null
  position: number | null
  total: number
  groupings: { country: string; local_rank: number }[]
}
const kind = (r: Placement) =>
  r.origin === 'curated' ? 'curated' : r.presentation !== 'ranked' ? 'collections' : 'published'
const names: Record<string, string> = {
  curated: 'Researched rankings',
  published: 'Published rankings',
  collections: 'Reading collections',
}
export function CrossRankingProfile({ work }: { work: number }) {
  const { version } = useApp()
  const r = useResource<{ placements: Placement[]; note: string }>(`/api/works/${work}/placements/`, version)
  const [search, setSearch] = useState(''),
    [domain, setDomain] = useState(''),
    [group, setGroup] = useState('')
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const all = r.data?.placements || []
  const rows = all.filter(
    (p) =>
      (!group || kind(p) === group) &&
      (!domain || p.domain === domain) &&
      `${p.title} ${p.publisher}`.toLowerCase().includes(search.toLowerCase()),
  )
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Across the rankings</h2>
        <span className="pill muted">{all.length} lists</span>
      </div>
      <div className="panel-body">
        <p className="small-text muted">
          Each placement belongs to its own scope. No combined score or average rank.
        </p>
        <div className="tag-row">
          {Object.keys(names).map((k) => (
            <span className="pill muted" key={k}>
              {all.filter((p) => kind(p) === k).length} {names[k].toLowerCase()}
            </span>
          ))}
        </div>
        <div className="toolbar">
          <input
            className="search-input"
            aria-label="Search book placements"
            placeholder="Search list or publication…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="filter-select"
            aria-label="Placement type"
            value={group}
            onChange={(e) => setGroup(e.target.value)}
          >
            <option value="">All list types</option>
            {Object.entries(names).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </select>
          <select
            className="filter-select"
            aria-label="Placement subject"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
          >
            <option value="">All subjects</option>
            {[...new Set(all.map((p) => p.domain))].sort().map((d) => (
              <option key={d} value={d}>
                {label(d)}
              </option>
            ))}
          </select>
        </div>
        {r.error && <ErrorNotice>{r.error}</ErrorNotice>}
        {r.loading && !r.data ? (
          <Loading />
        ) : !rows.length ? (
          <p className="muted">No matching visible lists.</p>
        ) : (
          Object.entries(names)
            .filter(([k]) => rows.some((p) => kind(p) === k))
            .map(([key, name]) => (
              <div key={key}>
                <h3>{name}</h3>
                {rows
                  .filter((p) => kind(p) === key)
                  .slice(0, expanded[key] ? undefined : 3)
                  .map((p) => (
                    <div className="placement-row" key={p.id}>
                      <a
                        className="text-link"
                        href={`#/rankings/${p.id}${p.slug === 'classical-education-guide' ? '?group=classical-education' : ''}`}
                      >
                        <strong>{p.title}</strong>
                      </a>
                      <div className="small-text">
                        {p.groupings.length ? (
                          <details>
                            <summary>
                              {p.groupings.length} country-local placement
                              {p.groupings.length === 1 ? '' : 's'} — no global rank
                            </summary>
                            {p.groupings.map((g) => (
                              <span className="pill muted" key={`${g.country}-${g.local_rank}`}>
                                {g.country} · #{g.local_rank}
                              </span>
                            ))}
                          </details>
                        ) : p.presentation === 'ranked' ? (
                          `#${p.position} · ${p.total} entries in this list`
                        ) : p.presentation === 'reading_sequence' ? (
                          `Reading sequence position ${p.position} · not a merit rank`
                        ) : (
                          'Included · unranked collection'
                        )}
                      </div>
                      <details className="small-text">
                        <summary>Scope, revision & sources</summary>
                        <p className="source-meta">
                          {label(p.domain)}
                          {p.publisher && ` · ${p.publisher}`} · revision {p.revision}
                          {p.updated && ` · Researched ${p.updated.slice(0, 10)}`}
                        </p>
                        <a className="text-link small-text" href={`#/sources?ranking=${p.id}`}>
                          Explore this list's source register →
                        </a>
                      </details>
                    </div>
                  ))}
                {rows.filter((p) => kind(p) === key).length > 3 && (
                  <button
                    className="text-link small-text"
                    onClick={() => setExpanded({ ...expanded, [key]: !expanded[key] })}
                  >
                    {expanded[key]
                      ? 'Show fewer'
                      : `Show all ${rows.filter((p) => kind(p) === key).length} placements`}
                  </button>
                )}
              </div>
            ))
        )}
      </div>
    </section>
  )
}

type SourceRow = {
  provenance: { consultation_origin: string; evidence_role: string }
  id: number
  source_id: string
  title: string
  url: string
  publisher: string
  family: string
  language: string
  geography: string
  access: string
  eligible: boolean
  evidence: string
  limitations: string
  consulted_on: string | null
  ranking: { id: number; title: string }
  reuse_count: number
  reused_in: { id: number; title: string; eligible: boolean }[]
}
type SourcesPage = Page<SourceRow> & {
  families: string[]
  rankings: { id: number; title: string }[]
  note: string
}
const initial = () => ({
  search: new URLSearchParams(location.hash.split('?')[1]).get('search') || '',
  publisher: '',
  language: '',
  country: '',
  family: '',
  status: '',
  reused: '',
  ranking: new URLSearchParams(location.hash.split('?')[1]).get('ranking') || '',
  url: new URLSearchParams(location.hash.split('?')[1]).get('url') || '',
})
export function SourceExplorer() {
  const { user, version } = useApp()
  const [draft, setDraft] = useState(initial),
    [filters, setFilters] = useState(initial),
    [page, setPage] = useState(1)
  const query = new URLSearchParams({ ...filters, page: String(page), page_size: '24' })
  const r = useResource<SourcesPage>(user ? `/api/source-explorer/?${query}` : null, version)
  function apply(values: ReturnType<typeof initial>) {
    setDraft(values)
    setFilters(values)
    setPage(1)
  }
  if (!user)
    return (
      <Empty title="Explore the research">Sign in to browse the sources available to your account.</Empty>
    )
  return (
    <>
      <PageHeader eyebrow="Evidence behind the lists" title="Source explorer.">
        Search saved source records across rankings. Reused pages keep separate target-specific evidence and
        limitations.
      </PageHeader>
      <form
        className="panel panel-body"
        onSubmit={(e) => {
          e.preventDefault()
          apply(draft)
        }}
      >
        <div className="form-grid">
          {(['search', 'publisher', 'language', 'country'] as const).map((key) => (
            <label className="field" key={key}>
              <span>
                {
                  {
                    search: 'Title, source ID or URL',
                    publisher: 'Publication / publisher',
                    language: 'Language (or “unknown”)',
                    country: 'Reported country / region (or “unknown”)',
                  }[key]
                }
              </span>
              <input
                className="input"
                maxLength={240}
                value={draft[key]}
                onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
              />
            </label>
          ))}
          <label className="field">
            <span>Source type</span>
            <select
              className="select"
              value={draft.family}
              onChange={(e) => setDraft({ ...draft, family: e.target.value })}
            >
              <option value="">Every source type</option>
              {r.data?.families.map((f) => (
                <option key={f} value={f}>
                  {label(f)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Saved evidence status</span>
            <select
              className="select"
              value={draft.status}
              onChange={(e) => setDraft({ ...draft, status: e.target.value })}
            >
              <option value="">All access levels</option>
              <option value="consulted">Eligible record in saved ledger</option>
              <option value="lead">Leads, metadata or ineligible evidence</option>
            </select>
          </label>
          <label className="field">
            <span>Reuse</span>
            <select
              className="select"
              value={draft.reused}
              onChange={(e) => setDraft({ ...draft, reused: e.target.value })}
            >
              <option value="">Any reuse status</option>
              <option value="yes">Same URL in multiple rankings</option>
            </select>
          </label>
          <label className="field">
            <span>Ranking / collection</span>
            <select
              className="select"
              value={draft.ranking}
              onChange={(e) => setDraft({ ...draft, ranking: e.target.value })}
            >
              <option value="">All visible lists</option>
              {r.data?.rankings.map((p) => (
                <option value={p.id} key={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
        </div>
        {filters.url && <p className="small-text">Exact URL filter: {filters.url}</p>}
        <div className="toolbar">
          <button className="button primary" disabled={r.loading}>
            Search sources
          </button>
          <button
            type="button"
            className="button secondary"
            onClick={() => apply({ ...initial(), ranking: '' })}
          >
            Clear filters
          </button>
        </div>
      </form>
      <p className="notice">
        {r.data?.note ||
          'Source metadata can be incomplete. No country is inferred from a domain name or a ranking’s subject.'}
      </p>
      {r.error && <ErrorNotice>{r.error}</ErrorNotice>}
      {r.loading ? (
        <Loading />
      ) : (
        <div className="source-list">
          {r.data?.results.map((s) => (
            <article className="source-card" key={s.id}>
              <div className="source-meta">
                <span>{s.source_id}</span>
                <span>{label(s.family)}</span>
                <span>{s.eligible ? 'Eligible record in saved ledger' : 'Lead / metadata / ineligible'}</span>
              </div>
              <a className="source-title" href={s.url} target="_blank" rel="noreferrer">
                {s.title} ↗
              </a>
              <p className="small-text">
                {s.publisher || 'Publication not recorded'} · Language:{' '}
                {s.language || 'Not separately recorded'} · Country/region: {s.geography || 'Not recorded'}
              </p>
              <p className="small-text muted">
                {label(s.provenance.consultation_origin)} · {label(s.provenance.evidence_role)} · Saved
                access: {s.access || 'Not recorded'} ·{' '}
                {s.consulted_on ? `Recorded consultation ${s.consulted_on}` : 'No consultation date'}
              </p>
              <p>
                <a className="text-link" href={`#/rankings/${s.ranking.id}`}>
                  {s.ranking.title}
                </a>
              </p>
              <p className="source-note">{s.evidence}</p>
              {s.limitations && <p className="source-limit">{s.limitations}</p>}
              <details>
                <summary>
                  Same saved URL in {s.reuse_count} visible ranking{s.reuse_count === 1 ? '' : 's'}
                </summary>
                <p className="small-text muted">
                  Exact URL matching only: alternate URLs can be missed; matching URLs are not independent
                  votes.
                </p>
                {s.reused_in.map((t) => (
                  <p key={t.id}>
                    <a className="text-link" href={`#/rankings/${t.id}`}>
                      {t.title}
                    </a>{' '}
                    · {t.eligible ? 'At least one eligible record here' : 'Lead / ineligible records here'}
                  </p>
                ))}
                <button
                  className="button secondary small"
                  onClick={() => apply({ ...initial(), ranking: '', url: s.url })}
                >
                  Compare all records for this URL
                </button>
              </details>
            </article>
          ))}
          {r.data && !r.data.count && (
            <Empty title="No matching source records">
              Try fewer filters. Missing geography is searchable as “unknown”.
            </Empty>
          )}
        </div>
      )}
      <Pager page={page} data={r.data} setPage={setPage} loading={r.loading} />
    </>
  )
}

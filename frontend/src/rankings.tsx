import { useCallback, useEffect, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  Bookmark,
  Copy,
  ExternalLink,
  Plus,
  RefreshCw,
  Share2,
  SlidersHorizontal,
  Trash2,
  Clock3,
} from 'lucide-react'
import { BookRating } from './starRating'
import { MembershipLinks, type CollectionContext } from './libraryInsights'
import { api, useResource } from './api'
import { useApp } from './context'
import {
  BookRow,
  Empty,
  ErrorNotice,
  Loading,
  Modal,
  NewList,
  PageHeader,
  RankingCard,
  dateLabel,
  label,
} from './components'
import type {
  Criterion,
  EditorialLens,
  EditorialSelection,
  Entry,
  Page,
  Person,
  Ranking,
  Score,
  Source,
} from './types'
import { Pager } from './pagination'
import { positivePage, useBrowseSearch, useBrowseState, useDebouncedValue } from './navigation'
import type { WorkCard } from './libraryData'
import './discoveryImprovements.css'

type RankingMode = 'all' | 'classical-education' | 'published' | 'collections' | 'my-lists' | 'saved'

export function Rankings({ mode = 'all' }: { mode?: RankingMode }) {
  const { user, version, requireLogin } = useApp()
  const isClassicalEducation = mode === 'classical-education'
  const [browse, patchBrowse] = useBrowseState({
    rsearch: '',
    rfield: 'all',
    rcountry: 'all',
    rsort: 'title',
    rpage: '1',
  })
  const [search, setSearch] = useBrowseSearch(browse.rsearch, patchBrowse, 'rsearch', 'rpage')
  const field = browse.rfield,
    country = browse.rcountry,
    sort = browse.rsort,
    page = positivePage(browse.rpage)
  const setField = (value: string) => patchBrowse({ rfield: value, rpage: 1 })
  const setCountry = (value: string) => patchBrowse({ rcountry: value, rpage: 1 })
  const setSort = (value: string) => patchBrowse({ rsort: value, rpage: 1 })
  const [newList, setNewList] = useState(false)
  const query = new URLSearchParams({
    paged: '1',
    mode,
    search: browse.rsearch,
    ordering: sort,
    page: String(page),
    ...(field !== 'all' ? { field } : {}),
    ...(country !== 'all' ? { country } : {}),
  })
  const ranks = useResource<Page<Ranking> & { facets: { countries: string[] } }>(
    `/api/rankings/?${query}`,
    version,
  )
  const titles: Record<RankingMode, string> = {
    all: 'Researched rankings.',
    'classical-education': 'Classical education.',
    published: 'Published rankings.',
    collections: 'Reading collections.',
    'my-lists': 'Your lists, your way.',
    saved: 'Keep good discoveries close.',
  }
  const countries = ranks.data?.facets.countries || []
  const rows = ranks.data?.results || []
  const description = isClassicalEducation
    ? 'Greek and Latin texts across poetry, prose, philosophy, history, rhetoric and drama, with ranked works and a companion study programme.'
    : mode === 'collections'
      ? 'Unranked selections and reading programmes, including Benjamin McEvoy and Great Books. Study order is preserved without assigning merit ranks.'
      : mode === 'published'
        ? 'Rankings from named publishers, including the Guardian. Each preserves its source, edition, and original positions.'
        : mode === 'all'
          ? 'Rankings synthesized from many relevant sources, with a separate evidence trail for each subject, country, form, or era.'
          : 'Your saved discoveries and personal reading lists. Customize your own view while shared originals stay intact.'
  return (
    <>
      <PageHeader
        eyebrow={
          isClassicalEducation
            ? 'Greek & Latin texts'
            : mode === 'collections'
              ? 'Independent voices & reading programmes'
              : mode === 'my-lists'
                ? 'Your private reading space'
                : 'Literature, philosophy & beyond'
        }
        title={titles[mode]}
        actions={
          mode === 'published' ? (
            <a className="button secondary" href="#/published-comparison">
              Compare published lists
            </a>
          ) : (
            (mode === 'my-lists' || mode === 'saved') && (
              <button
                className="button primary"
                onClick={() => {
                  if (requireLogin()) setNewList(true)
                }}
              >
                <Plus size={17} /> Create a personal list
              </button>
            )
          )
        }
      >
        {description}
      </PageHeader>
      {!isClassicalEducation && user && (
        <a className="button secondary" href="#/library?view=overlap">
          Compare collection overlap & books read
        </a>
      )}
      {!isClassicalEducation && (
        <>
          <div className="tabs">
            {[
              'all',
              'literature',
              'philosophy',
              'nonfiction',
              'history',
              'poetry',
              'manga',
              'graphic_novels',
            ].map((f) => (
              <button className={`tab ${field === f ? 'active' : ''}`} onClick={() => setField(f)} key={f}>
                {f === 'all' ? 'All subjects' : label(f)}
              </button>
            ))}
          </div>
          <div className="toolbar">
            <input
              className="search-input"
              aria-label="Search rankings"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search rankings, topics, centuries…"
            />
            <select
              className="filter-select"
              aria-label="Ranking country"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
            >
              <option value="all">Every country</option>
              {countries.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
            <select
              className="filter-select"
              aria-label="Sort rankings"
              value={sort}
              onChange={(e) => setSort(e.target.value)}
            >
              <option value="title">Title A–Z</option>
              <option value="updated">Recently updated</option>
              <option value="age">Oldest research first</option>
            </select>
          </div>
        </>
      )}
      {ranks.error && <ErrorNotice>{ranks.error}</ErrorNotice>}
      {ranks.loading && !ranks.data ? (
        <Loading />
      ) : rows.length ? (
        <>
          <div className="section-header">
            <span className="muted small-text">
              {ranks.data?.count || 0} {mode === 'collections' ? 'collections' : 'lists'}
            </span>
            <span className="muted small-text">
              {mode === 'collections'
                ? 'Unranked selections & reading sequences'
                : mode === 'published'
                  ? 'Original publisher order'
                  : 'Research saved per ranking'}
            </span>
          </div>
          <div className="rankings-grid">
            {rows.map((r) => (
              <RankingCard
                key={r.id}
                ranking={r}
                personalView={mode === 'saved'}
                detailGroup={isClassicalEducation ? 'classical-education' : undefined}
              />
            ))}
          </div>
        </>
      ) : (
        <Empty
          title={
            mode === 'my-lists'
              ? 'A list can be the start of something.'
              : mode === 'saved'
                ? 'Nothing bookmarked yet.'
                : 'No matching rankings.'
          }
          action={
            mode === 'my-lists' && (
              <button
                className="button primary"
                onClick={() => {
                  if (requireLogin()) setNewList(true)
                }}
              >
                Create your first list
              </button>
            )
          }
        >
          {mode === 'saved'
            ? 'Use the bookmark on any ranking to save it here.'
            : 'Create a personal list or explore another subject.'}
        </Empty>
      )}
      <Pager
        page={page}
        data={ranks.data}
        setPage={(value) => patchBrowse({ rpage: value })}
        loading={ranks.loading}
      />
      {newList && <NewList close={() => setNewList(false)} />}
    </>
  )
}

export function RankingDetail({
  id,
  personalView = false,
  returnGroup,
}: {
  id: string
  personalView?: boolean
  returnGroup?: string
}) {
  const [simpleView, setSimpleView] = useState(false)
  const { user, version, mutate, requireLogin, notify } = useApp()
  const [browse, patchBrowse] = useBrowseState({
    rlens: 'standing',
    rweighted: 'no',
    rtab: 'works',
    spage: '1',
  })
  const lens: EditorialLens = browse.rlens === 'reading' ? 'reading' : 'standing'
  const setLens = (value: EditorialLens) => patchBrowse({ rlens: value, rpage: 1 })
  const weighted = browse.rweighted === 'yes'
  const setWeighted = (value: boolean) => patchBrowse({ rweighted: value ? 'yes' : 'no', rpage: 1 })
  const tab = browse.rtab,
    setTab = (value: string) => patchBrowse({ rtab: value })
  const sourcePage = positivePage(browse.spage)
  const resource = useResource<Ranking>(`/api/rankings/${id}/?compact=1`, version)
  const sources = useResource<Page<Source>>(
    tab === 'sources' ? `/api/rankings/${id}/sources/?paged=1&page=${sourcePage}` : null,
    version,
  )
  const history = useResource<{ number: number; created_at: string; note: string }[]>(
    tab === 'history' ? `/api/rankings/${id}/history/` : null,
    version,
  )
  const [add, setAdd] = useState(false),
    [criteriaEdit, setCriteriaEdit] = useState(false)
  const [weights, setWeights] = useState<Record<string, number>>({}),
    [overrides, setOverrides] = useState<Record<string, Record<string, number>>>({})
  const ranking = resource.data
  useEffect(() => {
    if (ranking) {
      setWeights(ranking.preference?.weights || {})
      setOverrides(ranking.preference?.overrides || {})
    }
  }, [ranking])
  if (resource.loading && !ranking) return <Loading />
  if (!ranking) return <ErrorNotice>{resource.error || 'Ranking not found.'}</ErrorNotice>
  const editorial =
    ranking.origin === 'curated' && ranking.presentation === 'ranked' ? ranking.scope.editorial : undefined
  const isPersonal = ranking.origin === 'personal'
  const showPersonalScoring = isPersonal || personalView
  const isExternal = ranking.origin === 'external'
  // This is deliberately opt-in for the single around-the-world target. Other
  // country rankings retain their existing global-order presentation.
  const isCountryGrouped = ranking.scope.group_by === 'country'
  const sourceKind = isExternal
    ? ranking.presentation === 'ranked'
      ? 'Published ranking'
      : 'Reading collection'
    : 'Researched ranking'
  const backLink = personalView
    ? '#/saved'
    : isPersonal
      ? '#/my-lists'
      : returnGroup === 'classical-education'
        ? '#/classical-education?tab=rankings'
        : isExternal
          ? ranking.presentation === 'ranked'
            ? '#/published-rankings'
            : '#/collections'
          : '#/rankings'
  const refreshPending =
    !!ranking.preference?.refresh_requested_at &&
    (!ranking.last_researched_at ||
      Date.parse(ranking.preference.refresh_requested_at) > Date.parse(ranking.last_researched_at))
  const savePreferences = (data: unknown) =>
    mutate(() => api(`/api/rankings/${id}/preference/`, 'PATCH', data), 'Preferences saved')
  return (
    <>
      <a href={backLink} className="text-link">
        ← Back to{' '}
        {personalView ? 'bookmarked rankings' : isPersonal ? 'my lists' : sourceKind.toLowerCase() + 's'}
      </a>
      <PageHeader
        eyebrow={`${label(ranking.domain)} · ${label(ranking.presentation)}${isPersonal ? ' · Personal list' : personalView ? ' · Bookmarked view' : ` · ${sourceKind}`}`}
        title={ranking.title}
        actions={
          <>
            {isExternal && ranking.presentation === 'ranked' && (
              <a className="button secondary" href={`#/published-comparison?left=${id}`}>
                Compare published lists
              </a>
            )}
            <button
              className="button secondary"
              onClick={() => {
                if (requireLogin()) void savePreferences({ bookmarked: !ranking.preference?.bookmarked })
              }}
            >
              <Bookmark size={16} fill={ranking.preference?.bookmarked ? 'currentColor' : 'none'} />
              {ranking.preference?.bookmarked ? 'Bookmarked' : 'Bookmark'}
            </button>
            <button
              className="button secondary"
              onClick={async () => {
                if (!requireLogin()) return
                try {
                  const copy = await api<Ranking>(
                    `/api/rankings/${id}/copy/`,
                    'POST',
                    editorial?.orders[lens] && !isCountryGrouped ? { editorial_lens: lens } : {},
                  )
                  window.location.hash = `/rankings/${copy.id}`
                  notify('Personal copy created')
                } catch (e) {
                  notify((e as Error).message, true)
                }
              }}
            >
              <Copy size={16} />
              Create personal copy
            </button>
          </>
        }
      >
        {ranking.description}
      </PageHeader>
      <div className="ranking-summary">
        <span className="pill muted">
          {isCountryGrouped && typeof ranking.scope.position_count === 'number'
            ? `${ranking.scope.position_count} positions · ${ranking.entry_count || 0} distinct works`
            : `${ranking.entry_count || 0} ${ranking.item_type === 'person' ? 'people' : 'works'}`}
        </span>
        <span className="pill gold">
          {isCountryGrouped && typeof ranking.scope.source_record_count === 'number'
            ? `${ranking.source_count || 0} eligible · ${ranking.scope.source_record_count} retained source records`
            : `${ranking.source_count || 0} eligible source records`}
        </span>
        <span className="small-text muted" title={ranking.updated_at}>
          Updated {dateLabel(ranking.updated_at)}
        </span>
        <span className="small-text muted">Research: {dateLabel(ranking.last_researched_at)}</span>
        <span className="small-text muted">Revision {ranking.revision}</span>
        {ranking.source_url && (
          <a className="text-link small-text" href={ranking.source_url} target="_blank" rel="noreferrer">
            Original source <ExternalLink size={13} />
          </a>
        )}
      </div>
      {editorial && (
        <div className="notice">
          {editorial.notice}
          {ranking.order_status && <p>{ranking.order_status}</p>}
        </div>
      )}
      {personalView && !isPersonal && (
        <div className="notice">
          Your weights and assessments are private. Create a personal copy to add, remove, or reorder works.
        </div>
      )}
      <div className="detail-grid">
        <div className={`detail-main ${simpleView ? 'ranking-simple-view' : ''}`}>
          <div className="tabs detail-tabs">
            {[
              ['works', ranking.item_type === 'person' ? 'People' : 'Works'],
              [
                'sources',
                `Sources (${isCountryGrouped && typeof ranking.scope.source_record_count === 'number' ? ranking.scope.source_record_count : ranking.source_count || 0})`,
              ],
              ['history', 'History'],
            ].map(([key, text]) => (
              <button key={key} className={`tab ${tab === key ? 'active' : ''}`} onClick={() => setTab(key)}>
                {text}
              </button>
            ))}
          </div>
          {tab === 'works' && (
            <div className="toolbar" role="group" aria-label="Ranking display">
              <button
                className={`button ${simpleView ? 'primary' : 'secondary'} small`}
                aria-pressed={simpleView}
                onClick={() => setSimpleView(true)}
              >
                Simple view
              </button>
              <button
                className={`button ${!simpleView ? 'primary' : 'secondary'} small`}
                aria-pressed={!simpleView}
                onClick={() => setSimpleView(false)}
              >
                Detailed view
              </button>
            </div>
          )}
          {tab === 'works' && (
            <PagedRankingEntries
              ranking={ranking}
              lens={lens}
              setLens={setLens}
              simpleView={simpleView}
              weighted={weighted}
              weights={weights}
              overrides={overrides}
              setOverrides={setOverrides}
              addEntry={() => setAdd(true)}
            />
          )}
          {tab === 'sources' && (
            <>
              <div className="notice">
                Evidence belongs to this ranking. At least 50 relevant, diverse sources are required for
                synthesis; a faithful publisher-list import follows its original source. Counts include
                report-declared consultations and relevant reused records. They are not counts of
                independently verified judgments; eligibility is the saved ledger classification.
              </div>
              {sources.error && <ErrorNotice>{sources.error}</ErrorNotice>}
              {sources.loading ? (
                <Loading />
              ) : sources.data?.results.length ? (
                <div className="source-list">
                  {sources.data.results.map((source) => (
                    <article key={source.id} className="source-card">
                      <div className="source-meta">
                        <span>{source.source_id}</span>
                        <span>{label(source.family)}</span>
                        <span>{source.eligible ? 'Eligible record' : 'Retained record'}</span>
                      </div>
                      <a className="source-title" href={source.url} target="_blank" rel="noreferrer">
                        {source.title}
                        <ArrowUpRight size={16} />
                      </a>
                      <p className="small-text muted">
                        {label(source.provenance.consultation_origin)} ·{' '}
                        {label(source.provenance.access_extent)} · {label(source.provenance.evidence_role)}
                      </p>
                      <p className="source-note">{source.evidence}</p>
                      {source.limitations && <p className="source-limit">{source.limitations}</p>}
                      <div className="source-meta">
                        {source.publisher} · Recorded consultation {dateLabel(source.consulted_on)}
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <Empty title="This ranking’s evidence starts here.">
                  No consulted sources are recorded for this target yet. Sources from unrelated rankings are
                  not counted toward it.
                </Empty>
              )}
              <Pager
                page={sourcePage}
                data={sources.data}
                setPage={(value) => patchBrowse({ spage: value })}
                loading={sources.loading}
              />
            </>
          )}
          {tab === 'history' && (
            <section className="panel">
              <div className="panel-header">
                <h2>Revision history</h2>
              </div>
              <div className="panel-body">
                {history.error ? (
                  <ErrorNotice>{history.error}</ErrorNotice>
                ) : history.loading ? (
                  <Loading />
                ) : history.data?.length ? (
                  history.data.map((h) => (
                    <div className="source-card" key={h.number}>
                      <strong>Revision {h.number}</strong>
                      <p>{h.note}</p>
                      <span className="small-text muted">{dateLabel(h.created_at)}</span>
                    </div>
                  ))
                ) : (
                  <p className="muted">Changes to entries and list definitions will appear here.</p>
                )}
              </div>
            </section>
          )}
        </div>
        <aside className="detail-aside">
          <section className="panel weights-panel">
            <div className="panel-header">
              <h2>
                <SlidersHorizontal size={17} />{' '}
                {showPersonalScoring
                  ? 'Your perspective'
                  : isExternal
                    ? 'About the source'
                    : 'Research & methodology'}
              </h2>
            </div>
            <div className="panel-body">
              <p className="small-text muted">
                {showPersonalScoring
                  ? 'Choose what matters to you. Scores use researched assessments or your private overrides.'
                  : isExternal
                    ? 'This collection preserves the original source. Importing it does not create a new synthesized ranking or assign scores to an unranked list.'
                    : 'This shared ranking is populated from online research. Its entries, order, and assessments are maintained through the editorial workflow.'}
              </p>
              {!showPersonalScoring ? (
                <>
                  <p className="notice">{sourceKind} · read-only</p>
                  {editorial && (
                    <>
                      <p className="small-text">{editorial.method}</p>
                      <p className="small-text muted">
                        Selection published {dateLabel(editorial.published_on)}
                      </p>
                    </>
                  )}
                  {ranking.criteria.length > 0 && (
                    <ul className="small-text">
                      {ranking.criteria.map((c) => (
                        <li key={c.id}>{c.label}</li>
                      ))}
                    </ul>
                  )}
                  <a className="text-link" href="#/saved">
                    Open bookmarked rankings for personal preferences
                  </a>
                </>
              ) : ranking.criteria.length ? (
                <>
                  <label className="checkbox-field">
                    <input
                      type="checkbox"
                      checked={weighted}
                      onChange={(e) => {
                        if (!e.target.checked || requireLogin()) setWeighted(e.target.checked)
                      }}
                    />{' '}
                    Preview my weighted ranking
                  </label>
                  {ranking.criteria.map((c) => (
                    <div className="score-control" key={c.id}>
                      <label className="score-label" htmlFor={`weight-${c.id}`}>
                        <span>{c.label}</span>
                        <strong>{weights[c.id] || 0}</strong>
                      </label>
                      <input
                        id={`weight-${c.id}`}
                        className="range-input"
                        type="range"
                        min={0}
                        max={100}
                        value={weights[c.id] || 0}
                        onChange={(e) => setWeights({ ...weights, [c.id]: Number(e.target.value) })}
                      />
                    </div>
                  ))}
                  <button
                    className="button primary small"
                    onClick={() => {
                      if (requireLogin()) void savePreferences({ weights, overrides })
                    }}
                  >
                    Save my scoring
                  </button>
                  <p className="small-text muted">
                    Missing assessments stay unscored. This preview preserves the original order.
                  </p>
                </>
              ) : (
                <p className="notice">
                  Criteria haven’t been defined yet. We’ll design them before assigning scores.
                </p>
              )}
              {ranking.can_edit && (
                <button className="text-link" onClick={() => setCriteriaEdit(true)}>
                  {ranking.criteria.length ? 'Edit criterion definitions' : 'Define criteria'}
                </button>
              )}
            </div>
          </section>
          <section className="panel">
            <div className="panel-header">
              <h2>
                <Clock3 size={17} /> Keep it current
              </h2>
            </div>
            <div className="panel-body">
              <p className="small-text">
                Last researched
                <br />
                <strong>{dateLabel(ranking.last_researched_at)}</strong>
              </p>
              <p className="small-text">
                Sources last checked
                <br />
                <strong>
                  {ranking.last_sources_checked_at
                    ? dateLabel(ranking.last_sources_checked_at)
                    : 'No complete check recorded'}
                </strong>
              </p>
              <label className="field">
                <span>Suggest a refresh after</span>
                <select
                  className="select"
                  value={ranking.preference?.refresh_interval_days || ''}
                  onChange={(e) => {
                    if (requireLogin())
                      void savePreferences({
                        refresh_interval_days: e.target.value ? Number(e.target.value) : null,
                      })
                  }}
                >
                  <option value="">No interval set</option>
                  <option value="90">3 months</option>
                  <option value="180">6 months</option>
                  <option value="365">1 year</option>
                  <option value="730">2 years</option>
                </select>
              </label>
              <button
                className="button secondary small"
                disabled={refreshPending}
                onClick={() => {
                  if (requireLogin())
                    void mutate(
                      () => api(`/api/rankings/${id}/refresh/`, 'POST'),
                      'Refresh request saved for later research',
                    )
                }}
              >
                <RefreshCw size={14} />
                {refreshPending ? 'Refresh requested' : 'Request refresh'}
              </button>
              <p className="small-text muted">
                Saves a request for later research. A title, cover, or weight edit never resets the research
                date.
              </p>
            </div>
          </section>
          {ranking.owner === user?.id && (
            <section className="panel">
              <div className="panel-header">
                <h2>
                  <Share2 size={16} /> Share this list
                </h2>
              </div>
              <div className="panel-body">
                <p className="small-text muted">
                  Share the list’s works and order. Private notes, reading progress, and scoring preferences
                  stay private.
                </p>
                <button
                  className="button secondary small"
                  onClick={() =>
                    void mutate(
                      () =>
                        api(`/api/rankings/${id}/sharing/`, 'POST', { enabled: !ranking.sharing_enabled }),
                      ranking.sharing_enabled ? 'Sharing disabled; old link revoked' : 'Sharing enabled',
                    )
                  }
                >
                  {ranking.sharing_enabled ? 'Disable sharing' : 'Create a share link'}
                </button>
                {ranking.share_url && (
                  <label className="field">
                    <span>Anyone with this link can view the list</span>
                    <input
                      className="input"
                      readOnly
                      value={`${location.origin}${ranking.share_url}`}
                      onFocus={(e) => e.target.select()}
                    />
                  </label>
                )}
              </div>
            </section>
          )}
        </aside>
      </div>
      {add && <AddEntry ranking={ranking} close={() => setAdd(false)} />}
      {criteriaEdit && <CriteriaForm ranking={ranking} close={() => setCriteriaEdit(false)} />}
    </>
  )
}

type BrowseEntry = Omit<Entry, 'book' | 'author'> & {
  book: WorkCard | null
  author: Pick<Person, 'id' | 'name' | 'portrait' | 'portrait_thumbnail' | 'countries'> | null
  grouping: Entry['groupings'][number] | null
  score: Score | null
  can_move_up: boolean
  can_move_down: boolean
  display_position: number | null
  explanation: EditorialSelection['entries'][string] | null
  context: CollectionContext[string] | null
  comparison: { standing_rank: number | null; reading_rank: number | null; delta: number | null } | null
}
type BrowsePage = Page<BrowseEntry> & {
  revision: number
  grouped: boolean
  count_unit: 'entries' | 'placements'
  facets: { countries: string[]; genres: string[] }
  comparison: {
    available: boolean
    identical: boolean
    compared: number
    different: number
    unpositioned: number
    status: string
  }
}

function EvidenceDetails({ explanation }: { explanation: NonNullable<BrowseEntry['explanation']> }) {
  return (
    <details>
      <summary>Evidence & uncertainty</summary>
      <p className="small-text muted">
        {explanation.caveat || 'No additional uncertainty note is recorded.'}
      </p>
      <ul className="small-text">
        {(explanation.sources || []).map((source) => (
          <li key={source.source_id}>
            <a href={source.url} target="_blank" rel="noreferrer">
              {source.source_id} · {source.title}
            </a>
          </li>
        ))}
      </ul>
      {!!explanation.reported_sources?.length && (
        <>
          <p className="small-text muted">
            Other report-cited documents retained in the register; not counted as eligible evidence:
          </p>
          <ul className="small-text">
            {explanation.reported_sources.map((source) => (
              <li key={source.source_id}>
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.source_id} · {source.title}
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </details>
  )
}

function PagedRankingEntries({
  ranking,
  lens,
  setLens,
  simpleView,
  weighted = false,
  weights = {},
  overrides = {},
  setOverrides,
  addEntry,
  sharedToken,
}: {
  ranking: Ranking
  lens: EditorialLens
  setLens: (lens: EditorialLens) => void
  simpleView: boolean
  weighted?: boolean
  weights?: Record<string, number>
  overrides?: Record<string, Record<string, number>>
  setOverrides?: (value: Record<string, Record<string, number>>) => void
  addEntry?: () => void
  sharedToken?: string
}) {
  const { user, version, mutate, requireLogin } = useApp()
  const [browse, patchBrowse] = useBrowseState({
    rsearch: '',
    rgenre: '',
    rform: '',
    rcountry: '',
    rpage: '1',
    rcompare: 'no',
    rdifferences: 'no',
    rmode: 'grouped',
  })
  const [draftSearch, setDraftSearch] = useBrowseSearch(browse.rsearch, patchBrowse, 'rsearch', 'rpage')
  const page = positivePage(browse.rpage),
    compare = browse.rcompare === 'yes' && !weighted
  const differences = compare && browse.rdifferences === 'yes'
  const setPage = useCallback((value: number) => patchBrowse({ rpage: value }), [patchBrowse])
  const filter = (key: string, value: string) => patchBrowse({ [key]: value, rpage: 1 })
  const editorial =
    ranking.origin === 'curated' && ranking.presentation === 'ranked' ? ranking.scope.editorial : undefined
  const canCompare =
    !weighted &&
    ranking.scope.group_by !== 'country' &&
    !!editorial?.orders.standing &&
    !!editorial?.orders.reading
  const params = new URLSearchParams({
    search: browse.rsearch,
    genre: browse.rgenre,
    form: browse.rform,
    country: browse.rcountry,
    lens,
    view: browse.rmode,
    page: String(page),
    ...(differences ? { differences: 'yes' } : {}),
  })
  const normal = useResource<BrowsePage>(
    !weighted && !sharedToken ? `/api/ranking-browse/${ranking.id}/?${params}` : null,
    version,
  )
  const shared = useResource<{ ranking: Ranking; page: BrowsePage }>(
    sharedToken ? `/api/shared/${sharedToken}/?paged=1&${params}` : null,
    version,
  )
  const previewPath = `/api/rankings/${ranking.id}/preview/?paged=1&${params}`
  const previewKey = JSON.stringify([previewPath, weights, overrides, version, ranking.revision])
  const [preview, setPreview] = useState<{
    key: string
    data: BrowsePage | null
    loading: boolean
    error: string
  }>({ key: '', data: null, loading: false, error: '' })
  useEffect(() => {
    if (!weighted || sharedToken) return
    const controller = new AbortController()
    let alive = true
    setPreview({ key: previewKey, data: null, loading: true, error: '' })
    const timer = setTimeout(() => {
      api<BrowsePage>(previewPath, 'POST', { weights, overrides }, controller.signal)
        .then((data) => {
          if (alive) setPreview({ key: previewKey, data, loading: false, error: '' })
        })
        .catch((error) => {
          if (alive && error.name !== 'AbortError')
            setPreview({ key: previewKey, data: null, loading: false, error: error.message })
        })
    }, 250)
    return () => {
      alive = false
      clearTimeout(timer)
      controller.abort()
    }
  }, [weighted, sharedToken, previewKey, previewPath, weights, overrides])
  const r = sharedToken
    ? { data: shared.data?.page || null, loading: shared.loading, error: shared.error }
    : weighted
      ? preview.key === previewKey
        ? preview
        : { data: null, loading: true, error: '' }
      : normal
  useEffect(() => {
    if (page > 1 && r.error.toLowerCase().includes('invalid page')) setPage(1)
  }, [r.error, page, setPage])
  const comparison = r.data?.comparison
  const edit = ranking.can_edit && !sharedToken
  const move = (entry: BrowseEntry, direction: number) =>
    mutate(
      () =>
        api(`/api/rankings/${ranking.id}/reorder/`, 'POST', {
          entry_id: entry.id,
          direction,
          expected_revision: r.data?.revision ?? ranking.revision,
        }),
      'Order saved',
    )
  return (
    <>
      {canCompare && (
        <>
          <div className="toolbar" role="group" aria-label="Compare ranking perspectives">
            <button
              className={`button ${compare ? 'secondary' : 'primary'} small`}
              aria-pressed={!compare}
              onClick={() => patchBrowse({ rcompare: 'no', rdifferences: 'no', rpage: 1 })}
            >
              One perspective
            </button>
            <button
              className={`button ${compare ? 'primary' : 'secondary'} small`}
              aria-pressed={compare}
              onClick={() => patchBrowse({ rcompare: 'yes', rpage: 1 })}
            >
              Compare side by side
            </button>
          </div>
          <div className="toolbar">
            <label className="field">
              <span>{compare ? 'Arrange comparison by' : 'Order by'}</span>
              <select
                className="select"
                aria-label="Editorial ranking perspective"
                value={lens}
                onChange={(e) => setLens(e.target.value as EditorialLens)}
              >
                {(['standing', 'reading'] as const).map((key) => (
                  <option key={key} value={key}>
                    {editorial.orders[key].label}
                  </option>
                ))}
              </select>
            </label>
            <p className="small-text muted">{editorial.orders[lens].description}</p>
          </div>
        </>
      )}
      {compare && comparison?.available && (
        <div className="notice">
          <strong>
            {comparison.identical
              ? 'These perspectives currently use the same supplied order.'
              : comparison.compared === 0
                ? 'No entries have usable positions in both perspectives yet.'
                : `${comparison.different} of ${comparison.compared} comparable entries have different positions.`}
          </strong>
          <p>{comparison.status}</p>
          <p className="small-text">
            Each number is its saved position in the full ranking; filters keep those positions.
            {comparison.unpositioned > 0 &&
              ` ${comparison.unpositioned} entries lack a usable position in one or both orders.`}
          </p>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={differences}
              onChange={(e) => filter('rdifferences', e.target.checked ? 'yes' : 'no')}
            />
            Show only different positions
          </label>
        </div>
      )}
      <div className="toolbar">
        <input
          className="search-input"
          aria-label="Filter ranking entries"
          placeholder="Find a work or author…"
          value={draftSearch}
          onChange={(e) => setDraftSearch(e.target.value)}
        />
        {ranking.item_type === 'work' && (
          <>
            <select
              className="filter-select"
              aria-label="Ranking work form"
              value={browse.rform}
              onChange={(e) => filter('rform', e.target.value)}
            >
              <option value="">All eligible forms</option>
              {['book', 'collection', 'essay', 'short_story', 'poem', 'play'].map((value) => (
                <option key={value} value={value}>
                  {label(value)}
                </option>
              ))}
            </select>
            <select
              className="filter-select"
              aria-label="Filter ranking entries by genre"
              value={browse.rgenre}
              onChange={(e) => filter('rgenre', e.target.value)}
            >
              <option value="">All genres</option>
              {r.data?.facets.genres.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </>
        )}
        <select
          className="filter-select"
          aria-label="Filter entries by country association"
          value={browse.rcountry}
          onChange={(e) => filter('rcountry', e.target.value)}
        >
          <option value="">Every country</option>
          {r.data?.facets.countries.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        {edit && addEntry && (
          <button className="button secondary small" onClick={addEntry}>
            <Plus size={15} />
            Add entry
          </button>
        )}
      </div>
      {ranking.scope.group_by === 'country' && !weighted && (
        <>
          <p className="small-text muted">
            Country positions retain their documented source order. A work can appear in more than one
            country; each appearance counts as one placement on these pages.
          </p>
          {ranking.origin === 'personal' && (
            <>
              <p className="notice">
                Country ranks describe the copied source. Personal order is separate; removing a work removes
                all its country appearances.
              </p>
              <button
                className="button secondary small"
                onClick={() => filter('rmode', browse.rmode === 'grouped' ? 'manual' : 'grouped')}
              >
                {browse.rmode === 'grouped' ? 'Show personal order' : 'Show country groups'}
              </button>
            </>
          )}
        </>
      )}
      {r.error && <ErrorNotice>{r.error}</ErrorNotice>}
      {r.loading ? (
        <Loading />
      ) : r.data?.results.length ? (
        <section className="panel">
          {r.data.results.map((entry, index) => {
            const personal = entry.context,
              explanation = entry.explanation,
              ranks = entry.comparison,
              scored = entry.score
            const delta = ranks?.delta
            const movement =
              delta == null
                ? 'A position is not recorded in both views'
                : delta === 0
                  ? 'Same position'
                  : `${delta > 0 ? '↑' : '↓'} ${Math.abs(delta)} ${Math.abs(delta) === 1 ? 'place' : 'places'} in reading value`
            const actions = (
              <>
                {weighted && (
                  <span
                    className={`pill ${scored?.score != null ? 'gold' : 'muted'}`}
                    title={scored?.reason || 'Personal weighted score'}
                  >
                    {scored?.score != null ? scored.score.toFixed(1) : 'Unassessed'}
                  </span>
                )}
                {!sharedToken && entry.book && (
                  <button
                    className="icon-button"
                    aria-label={`Save ${entry.book.title} to library`}
                    onClick={() => {
                      if (requireLogin())
                        void mutate(
                          () => api('/api/library/', 'POST', { work: entry.work }),
                          'Saved to your library',
                        )
                    }}
                  >
                    <Plus size={17} />
                  </button>
                )}
                {edit && !weighted && !r.data?.grouped && (
                  <>
                    <button
                      className="icon-button"
                      aria-label="Move entry up"
                      disabled={!entry.can_move_up}
                      onClick={() => void move(entry, -1)}
                    >
                      <ArrowUp size={15} />
                    </button>
                    <button
                      className="icon-button"
                      aria-label="Move entry down"
                      disabled={!entry.can_move_down}
                      onClick={() => void move(entry, 1)}
                    >
                      <ArrowDown size={15} />
                    </button>
                    <button
                      className="icon-button"
                      aria-label="Remove entry"
                      onClick={() =>
                        void mutate(
                          () =>
                            api(`/api/rankings/${ranking.id}/entries/?compact=1`, 'DELETE', {
                              entry_id: entry.id,
                              expected_revision: r.data?.revision ?? ranking.revision,
                            }),
                          'Entry removed',
                        )
                      }
                    >
                      <Trash2 size={14} />
                    </button>
                  </>
                )}
              </>
            )
            const grouping = entry.grouping
            const startsCountry =
              r.data?.grouped &&
              (index === 0 || r.data.results[index - 1].grouping?.country !== grouping?.country)
            return (
              <article key={`${entry.id}:${grouping?.country || ''}`} className="ranking-comparison-entry">
                {startsCountry && (
                  <div className="panel-header">
                    <h2>{grouping?.country || 'Ungrouped additions'}</h2>
                    {grouping && (
                      <span className="pill muted">
                        {grouping.region} · {grouping.confidence?.toLowerCase()}
                      </span>
                    )}
                  </div>
                )}
                {ranking.slug === 'classical-education-guide' && entry.work && (
                  <p className="small-text">
                    <a className="text-link" href={`#/classical-education?work=${entry.work}`}>
                      Study this work · starter reading, syllabus & preparation →
                    </a>
                  </p>
                )}
                {entry.book ? (
                  <BookRow
                    work={entry.book}
                    index={compare ? undefined : (entry.display_position ?? undefined)}
                    action={actions}
                  />
                ) : (
                  <div className="book-row">
                    {!compare && (
                      <span className="rank-number">
                        {ranking.presentation === 'unranked' ? '' : (entry.display_position ?? '—')}
                      </span>
                    )}
                    {entry.author?.portrait ? (
                      <img
                        className="avatar"
                        src={entry.author.portrait_thumbnail || entry.author.portrait}
                        alt=""
                      />
                    ) : (
                      <div className="avatar">{entry.author?.name[0]}</div>
                    )}
                    <a className="book-title" href={`#/authors/${entry.person}`}>
                      {entry.author?.name}
                    </a>
                    <div className="row-actions">{actions}</div>
                  </div>
                )}
                {grouping && (
                  <div className="entry-rationale">
                    {ranking.origin === 'personal' && (
                      <p className="small-text muted">
                        Source country position {grouping.local_rank} · Personal position {entry.position}.
                      </p>
                    )}
                    {!simpleView && (
                      <>
                        <p>{grouping.affiliation_note}</p>
                        <p className="small-text muted">
                          Original language/version: {grouping.language} · Reported form:{' '}
                          {grouping.form_reported} · Sources: {grouping.source_ids.join(', ')}
                        </p>
                      </>
                    )}
                  </div>
                )}
                {!sharedToken && entry.book && user && (
                  <div className="collection-personal">
                    <BookRating
                      work={entry.book.id}
                      title={entry.book.title}
                      rating={personal?.rating ?? null}
                    />
                    {personal && (
                      <>
                        <span className={`pill ${personal.read ? 'green' : 'muted'}`}>
                          {personal.read
                            ? '✓ Already read'
                            : personal.status
                              ? label(personal.status)
                              : 'Not in your library'}
                        </span>
                        {personal.lists.length > 1 && (
                          <details className="entry-memberships">
                            <summary>Appears in {personal.lists.length} shared lists</summary>
                            <MembershipLinks lists={personal.lists} />
                          </details>
                        )}
                      </>
                    )}
                  </div>
                )}
                {compare && ranks ? (
                  <div className="perspective-comparison">
                    <span className={`perspective-delta ${delta ? 'changed' : ''}`}>{movement}</span>
                    <div className="perspective-columns">
                      {(['standing', 'reading'] as const).map((key) => (
                        <section className="perspective-column" key={key}>
                          <h3>
                            {editorial?.orders[key].label ||
                              (key === 'standing' ? 'Critical standing' : 'Reading value')}
                          </h3>
                          <strong className="pill muted">
                            {ranks[`${key}_rank`] == null
                              ? 'Position not recorded'
                              : `#${ranks[`${key}_rank`]}`}
                          </strong>
                          {!simpleView && (
                            <p className="small-text">
                              {explanation?.[key] ||
                                'A separate explanation is not recorded for this perspective.'}
                            </p>
                          )}
                        </section>
                      ))}
                    </div>
                    {!simpleView && explanation && <EvidenceDetails explanation={explanation} />}
                  </div>
                ) : (
                  !simpleView &&
                  (explanation ? (
                    <div className="entry-rationale">
                      <p>{explanation[lens]}</p>
                      <EvidenceDetails explanation={explanation} />
                    </div>
                  ) : (
                    entry.rationale && <p className="entry-rationale">{entry.rationale}</p>
                  ))
                )}
                {weighted && setOverrides && ranking.criteria.length > 0 && (
                  <details className="assessment-details">
                    <summary>My assessments & score breakdown</summary>
                    <div className="form-grid">
                      {ranking.criteria.map((criterion) => (
                        <label className="field" key={criterion.id}>
                          <span>{criterion.label} (0–10)</span>
                          <input
                            className="input"
                            type="number"
                            min={0}
                            max={10}
                            step={0.1}
                            value={overrides[String(entry.id)]?.[criterion.id] ?? ''}
                            placeholder={
                              entry.assessments[criterion.id] == null
                                ? 'Not assessed'
                                : `Shared: ${entry.assessments[criterion.id]}`
                            }
                            onChange={(event) => {
                              const next = { ...overrides[String(entry.id)] }
                              if (event.target.value === '') delete next[criterion.id]
                              else next[criterion.id] = Number(event.target.value)
                              setOverrides({ ...overrides, [String(entry.id)]: next })
                            }}
                          />
                          <small className="muted">
                            Contribution: {scored?.contributions[criterion.id]?.toFixed(2) ?? '—'}
                          </small>
                        </label>
                      ))}
                    </div>
                    <p className="small-text muted">
                      Your overrides remain private. Empty values use the shared assessment when one exists.
                    </p>
                  </details>
                )}
              </article>
            )
          })}
        </section>
      ) : (
        !r.error && (
          <Empty title={differences ? 'No different positions match.' : 'No matching entries.'}>
            {ranking.entry_count
              ? 'Try another title, form, genre or country. Saved positions remain unchanged.'
              : edit
                ? 'Add real works from the catalog, or make a personal copy of another list.'
                : 'This list has no entries yet.'}
          </Empty>
        )
      )}
      {r.data && (
        <p className="small-text muted">
          {r.data.count} {r.data.count_unit} match · up to 24 per page.
        </p>
      )}
      <Pager page={page} data={r.data} setPage={setPage} loading={r.loading} />
    </>
  )
}

function AddEntry({ ranking, close }: { ranking: Ranking; close: () => void }) {
  const { version, mutate } = useApp()
  const [search, setSearch] = useState(''),
    [page, setPage] = useState(1)
  const debounced = useDebouncedValue(search)
  const [selected, setSelected] = useState(''),
    [busy, setBusy] = useState(false)
  const resource = useResource<Page<{ id: number; title: string }>>(
    `/api/rankings/${ranking.id}/candidates/?search=${encodeURIComponent(debounced)}&page=${page}`,
    version,
  )
  return (
    <Modal title="Add from the catalog" close={close}>
      <form
        onSubmit={async (event) => {
          event.preventDefault()
          setBusy(true)
          if (
            await mutate(
              () =>
                api(`/api/rankings/${ranking.id}/entries/?compact=1`, 'POST', {
                  [ranking.item_type]: Number(selected),
                  expected_revision: ranking.revision,
                }),
              'Entry added',
            )
          )
            close()
          setBusy(false)
        }}
      >
        <label className="field">
          <span>Search eligible catalog items</span>
          <input
            className="input"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setPage(1)
              setSelected('')
            }}
          />
        </label>
        {resource.error && <ErrorNotice>{resource.error}</ErrorNotice>}
        {resource.loading ? (
          <Loading />
        ) : (
          <label className="field">
            <span>{ranking.item_type === 'work' ? 'Work' : 'Person'}</span>
            <select
              className="select"
              value={selected}
              required
              onChange={(event) => setSelected(event.target.value)}
            >
              <option value="">Choose an item</option>
              {resource.data?.results.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.title}
                </option>
              ))}
            </select>
          </label>
        )}
        <Pager
          page={page}
          data={resource.data}
          setPage={(value) => {
            setPage(value)
            setSelected('')
          }}
          loading={resource.loading}
        />
        {!resource.loading && resource.data?.count === 0 && (
          <p className="muted">
            No new eligible items match. Books already in this list are excluded. Try a broader search or{' '}
            <a href="#/catalog" onClick={close}>
              open the catalog
            </a>
            .
          </p>
        )}
        <div className="form-actions">
          <button className="button primary" disabled={busy || resource.loading || !selected}>
            Add entry
          </button>
        </div>
      </form>
    </Modal>
  )
}

function CriteriaForm({ ranking, close }: { ranking: Ranking; close: () => void }) {
  const { mutate } = useApp()
  const [text, setText] = useState(ranking.criteria.map((c) => c.label).join('\n'))
  return (
    <Modal title="Define ranking criteria" close={close}>
      <p className="muted">
        One criterion per line. Each assessment will use 0–10, where higher means a stronger match. No scores
        are created by defining criteria.
      </p>
      <textarea
        className="textarea"
        aria-label="Criterion definitions, one per line"
        rows={7}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Enter the criteria you want to use"
      />
      <div className="form-actions">
        <button
          className="button primary"
          onClick={async () => {
            const criteria: Criterion[] = text
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean)
              .map((name) => ({
                id:
                  ranking.criteria.find((c) => c.label === name)?.id ||
                  name
                    .toLowerCase()
                    .replace(/[^a-z0-9]+/g, '-')
                    .replace(/^-|-$/g, ''),
                label: name,
              }))
            if (
              await mutate(
                () =>
                  api(`/api/rankings/${ranking.id}/`, 'PATCH', {
                    criteria,
                    expected_revision: ranking.revision,
                  }),
                'Criteria saved',
              )
            )
              close()
          }}
        >
          Save definitions
        </button>
      </div>
    </Modal>
  )
}

export function SharedList({ token }: { token: string }) {
  const r = useResource<Ranking>(`/api/shared/${token}/?compact=1`)
  if (r.loading) return <Loading />
  if (!r.data) return <ErrorNotice>This link is unavailable or its owner has disabled sharing.</ErrorNotice>
  return (
    <>
      <div className="share-banner">
        <Share2 size={17} /> A shared reading list
      </div>
      <PageHeader title={r.data.title}>{r.data.description}</PageHeader>
      <PagedRankingEntries
        ranking={r.data}
        lens="standing"
        setLens={() => {}}
        simpleView={false}
        sharedToken={token}
      />
    </>
  )
}

import { BookWorkflow } from './bookWorkflow'
import { BookSelectionCheckbox, BulkBookActions, useBookSelection } from './bulkBooks'
import { SavedFilterPicker } from './savedFilters'
import { CatalogFilters } from './catalogFilters'
import { catalogBrowseDefaults, catalogRequestParams } from './catalogFilterState'
import type { ApiCatalogFacets } from './generated/apiContracts'
import { useState } from 'react'
import {
  ArrowRight,
  BookOpen,
  Plus,
  BookmarkPlus,
  Pencil,
  Clock3,
  ExternalLink,
  CalendarDays,
  Layers3,
  Globe2,
} from 'lucide-react'
import { api, useResource } from './api'
import { useApp } from './context'
import { paceValue, paceLabel } from './readingPace'
import {
  AddBook,
  BookRow,
  Cover,
  Empty,
  ErrorNotice,
  ImageCredit,
  Loading,
  Modal,
  PageHeader,
  RankingCard,
  duration,
  label,
} from './components'
import { EditionChange } from './editionChange'
import { QuickReading } from './readingHistory'
import { ClassicalWorkPreparation } from './classicalWorkPreparation'
import { CrossRankingProfile } from './discovery'
import { Pager } from './pagination'
import { positivePage, useBrowseSearch, useBrowseState } from './navigation'
import type { Page, Edition, LibraryItem, Person, Ranking, Work, WorkRankingMembership } from './types'
import type { ReadingOverview, WorkCard } from './libraryData'

export function Explore() {
  const { user, version, mutate } = useApp()
  const ranks = useResource<{ rankings: Ranking[]; bookmarked_count: number }>(
    '/api/rankings/explore/',
    version,
  )
  const library = useResource<ReadingOverview>(user ? '/api/library/overview/' : null, version)
  const recs = useResource<{ results: { book: WorkCard; score: number; ranking_title: string }[] }>(
    user ? '/api/rankings/recommendations/?compact=1' : null,
    version,
  )
  const [adding, setAdding] = useState(false)
  const general = ranks.data?.rankings || []
  const reading = library.data?.currently_reading || []
  const goRank = (slug: string) => {
    const ranking = ranks.data?.rankings.find((r) => r.slug === slug)
    window.location.hash = ranking ? `/rankings/${ranking.id}` : '/rankings'
  }
  return (
    <>
      <PageHeader
        eyebrow="A considered reading life"
        title={
          user?.display_name
            ? `Make room for wonder, ${user.display_name.split(' ')[0]}.`
            : 'Make room for wonder.'
        }
        actions={
          user?.is_staff && (
            <button className="button secondary" onClick={() => setAdding(true)}>
              <Plus size={16} /> Add a book
            </button>
          )
        }
      >
        Explore lasting ideas, discover great writing, and build a library that feels like you.
      </PageHeader>
      <div className="hero-grid">
        <button className="hero-card featured literature" onClick={() => goRank('literature-all-time')}>
          <div className="hero-copy">
            <span className="eyebrow">Literature</span>
            <h2>
              Lives beyond
              <br />
              your own.
            </h2>
            <p>
              Stories across centuries,
              <br />
              countries, and ways of seeing.
            </p>
            <span className="text-link">
              Explore literature <ArrowRight size={16} />
            </span>
          </div>
          <div className="hero-art" aria-hidden="true">
            <span className="spine spine1" />
            <span className="spine spine2" />
            <span className="spine spine3" />
          </div>
        </button>
        <button className="hero-card philosophy" onClick={() => goRank('philosophy-books-all-time')}>
          <div className="hero-copy">
            <span className="eyebrow">Philosophy</span>
            <h2>
              Questions worth
              <br />
              living with.
            </h2>
            <p>
              Find your way through
              <br />
              the ideas that shape us.
            </p>
            <span className="text-link">
              Explore philosophy <ArrowRight size={16} />
            </span>
          </div>
          <div className="hero-art philosophy-art" aria-hidden="true">
            <Layers3 size={130} strokeWidth={0.55} />
          </div>
        </button>
      </div>
      <div className="stats-row">
        <div className="stat">
          <BookOpen size={20} />
          <div>
            <span className="stat-value">{library.data?.count || 0}</span>
            <span className="stat-label">In your library</span>
          </div>
        </div>
        <div className="stat">
          <BookmarkPlus size={20} />
          <div>
            <span className="stat-value">{ranks.data?.bookmarked_count || 0}</span>
            <span className="stat-label">Saved rankings</span>
          </div>
        </div>
        <div className="stat">
          <Globe2 size={20} />
          <div>
            <span className="stat-value">Worldwide</span>
            <span className="stat-label">English editions</span>
          </div>
        </div>
        <div className="stat">
          <CalendarDays size={20} />
          <div>
            <span className="stat-value">
              {user ? paceValue(user) : 175} {user?.difficulty_aware_planning ? 'baseline pages' : 'pages'}
            </span>
            <span className="stat-label">{user ? paceLabel(user) : 'Weekly reading target'}</span>
          </div>
        </div>
      </div>
      <div className="section-header">
        <div>
          <span className="eyebrow">Start exploring</span>
          <h2>Great works. Your perspective.</h2>
        </div>
        <a className="text-link" href="#/rankings">
          All rankings <ArrowRight size={16} />
        </a>
      </div>
      {ranks.error && <ErrorNotice>{ranks.error}</ErrorNotice>}
      {ranks.loading && !ranks.data ? (
        <Loading />
      ) : (
        <div className="rankings-grid">
          {general.map((r) => (
            <RankingCard key={r.id} ranking={r} />
          ))}
        </div>
      )}
      <div className="two-column">
        <section className="panel">
          <div className="panel-header">
            <h2>On your nightstand</h2>
            <a className="text-link" href="#/library">
              My library <ArrowRight size={15} />
            </a>
          </div>
          {reading.length ? (
            reading
              .slice(0, 3)
              .map((i) => (
                <BookRow
                  key={i.id}
                  work={i.book}
                  action={<span className="pill green">Page {i.current_page}</span>}
                />
              ))
          ) : (
            <Empty
              title="Your next chapter starts here."
              action={
                <a className="button secondary small" href="#/catalog">
                  Browse the catalog
                </a>
              }
            >
              Save a book and mark it as currently reading to keep it close.
            </Empty>
          )}
        </section>
        <section className="panel">
          <div className="panel-header">
            <h2>Chosen for your interests</h2>
            <span className="pill gold">Personal</span>
          </div>
          {recs.data?.results.length ? (
            recs.data.results.slice(0, 3).map((r, i) => (
              <BookRow
                key={`${r.book.id}-${i}`}
                work={r.book}
                action={
                  <button
                    className="icon-button"
                    aria-label={`Save ${r.book.title}`}
                    onClick={() =>
                      void mutate(
                        () => api('/api/library/', 'POST', { work: r.book.id }),
                        'Saved to your library',
                      )
                    }
                  >
                    <Plus size={18} />
                  </button>
                }
              />
            ))
          ) : (
            <Empty title="Recommendations with a reason.">
              Once works have researched assessments and you choose your weights, your recommendations will
              appear here.
            </Empty>
          )}
        </section>
      </div>
      {adding && <AddBook close={() => setAdding(false)} />}
    </>
  )
}

export function Catalog() {
  const { user, version, mutate, requireLogin } = useApp()
  const selection = useBookSelection('catalog')
  const [browse, patch] = useBrowseState(catalogBrowseDefaults)
  const { q: query, saved_filter: savedFilter } = browse
  const [search, setSearch] = useBrowseSearch(query, patch)
  const [adding, setAdding] = useState(false)
  const page = positivePage(browse.page)
  const setPage = (value: number) => patch({ page: value })
  const commonParams = catalogRequestParams(browse)
  const params = new URLSearchParams(commonParams)
  params.set('page', String(page))
  params.set('compact', '1')
  const works = useResource<Page<WorkCard>>(`/api/works/?${params}`, version)
  const facets = useResource<ApiCatalogFacets>(`/api/works/facets/?${commonParams}`, version)
  const filtered = works.data?.results || []
  const filterActive = commonParams.size > 0
  return (
    <>
      <PageHeader
        eyebrow="The shared catalog"
        title="A world of books."
        actions={
          <>
            <a className="button secondary" href="#/atlas">
              <Globe2 size={17} /> Atlas & timeline
            </a>
            {user?.is_staff && (
              <button className="button primary" onClick={() => setAdding(true)}>
                <Plus size={17} /> Add a book
              </button>
            )}
          </>
        }
      >
        Literature, philosophy, nonfiction, manga, and everything they touch. Keep the works that speak to
        you.
      </PageHeader>
      <div className="toolbar">
        <SavedFilterPicker
          value={savedFilter}
          onChange={(id) => patch({ saved_filter: id, page: 1 })}
          context="catalog"
        />
        <input
          className="search-input"
          aria-label="Search catalog"
          placeholder="Search titles, authors, topics, or genres…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <CatalogFilters
        key={`${user?.id || 'anonymous'}:${savedFilter}`}
        data={facets.data}
        loading={facets.loading}
        saved={!!savedFilter}
        patch={patch}
      />
      {facets.error && <ErrorNotice>{facets.error}</ErrorNotice>}
      <div className="catalog-count" aria-live="polite">
        {works.data?.count
          ? `Showing ${filtered.length} books on page ${page} of ${Math.ceil(works.data.count / 24)} (${works.data.count.toLocaleString()} total)`
          : 'Showing 0 books'}
      </div>
      {works.error && <ErrorNotice>{works.error}</ErrorNotice>}
      <BulkBookActions selection={selection} visible={filtered} loading={works.loading} />
      {works.loading ? (
        <Loading />
      ) : filtered.length ? (
        <div className="book-grid">
          {filtered.map((work) => (
            <article className="book-card" key={work.id}>
              <BookSelectionCheckbox selection={selection} book={work} />
              <a href={`#/books/${work.id}`}>
                <Cover work={work} large />
              </a>
              <a className="book-title" href={`#/books/${work.id}`}>
                {work.title}
              </a>
              <div className="book-author">
                {work.authors.map((a) => a.name).join(', ') || 'Author not recorded'}
              </div>
              <div className="book-meta">
                {work.genres.slice(0, 2).map((value) => (
                  <span className="pill gold" key={value}>
                    {value}
                  </span>
                ))}
                <span>
                  <Clock3 size={13} />
                  {duration(work.reading_time.estimated_hours)}
                </span>
              </div>
              <div className="row-actions">
                <button
                  className="button secondary small"
                  onClick={() => {
                    if (requireLogin())
                      void mutate(
                        () => api('/api/library/', 'POST', { work: work.id }),
                        'Saved to your library',
                      )
                  }}
                >
                  <Plus size={15} /> My library
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          title={
            filterActive || works.data?.count
              ? 'No works match these filters.'
              : 'An open shelf, ready for your books.'
          }
          action={
            !filterActive &&
            user?.is_staff && (
              <button className="button primary" onClick={() => setAdding(true)}>
                <Plus size={16} />
                Add your first book
              </button>
            )
          }
        >
          {filterActive || works.data?.count
            ? 'Try another title, genre, form, country, or subject.'
            : 'Ranking templates and research are saved separately. Add a book now, or build the catalog as each ranking is researched.'}
        </Empty>
      )}
      <Pager page={page} data={works.data} setPage={setPage} loading={works.loading} />
      {adding && <AddBook close={() => setAdding(false)} />}
    </>
  )
}

export function WorkDetail({ id }: { id: string }) {
  const { user, version, mutate, reload } = useApp()
  const resource = useResource<Work>(`/api/works/${id}/`, version)
  const editions = useResource<Edition[]>(`/api/works/${id}/editions/`, version)
  const memberships = useResource<WorkRankingMembership[]>(`/api/works/${id}/rankings/`, version)
  const library = useResource<LibraryItem[]>(user ? `/api/library/?work=${id}` : null, version, true)
  const lists = useResource<Ranking[]>('/api/rankings/', version, true)
  const [edit, setEdit] = useState(false),
    [listId, setListId] = useState(''),
    [newEdition, setNewEdition] = useState(false)
  const [changingEdition, setChangingEdition] = useState<Edition | null>(null)
  const work = resource.data,
    item = library.data?.find((i) => i.work === Number(id))
  if (resource.loading && !work) return <Loading />
  if (!work) return <ErrorNotice>{resource.error || 'Work not found.'}</ErrorNotice>
  const personalLists = lists.data?.filter((r) => r.owner === user?.id && r.item_type === 'work') || []
  return (
    <>
      <a href="#/catalog" className="text-link">
        ← Back to catalog
      </a>
      <div className="book-detail-head">
        <Cover work={work} large />
        <div>
          <div className="eyebrow">
            {label(work.field)} · {label(work.form)}
          </div>
          <h1>{work.title}</h1>
          <div className="book-author">
            {work.authors.map((a, index) => (
              <span key={a.id}>
                {index > 0 && ', '}
                <a href={`#/authors/${a.id}`}>{a.name}</a>
              </span>
            ))}
          </div>
          <div className="tag-row">
            {work.genres.map((genre) => (
              <span className="pill gold" key={`g-${genre}`}>
                {genre}
              </span>
            ))}
            {work.tags.map((tag) => (
              <span className="pill muted" key={tag}>
                {tag}
              </span>
            ))}
          </div>
          <div className="header-actions">
            <button
              className="button primary"
              onClick={() =>
                document
                  .getElementById('reading-workflow')
                  ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }
            >
              <BookmarkPlus size={17} />
              {item ? 'Your reading edition' : 'Choose edition & save'}
            </button>
            {user?.is_staff && (
              <button className="button secondary" onClick={() => setEdit(true)}>
                <Pencil size={15} />
                Edit
              </button>
            )}
          </div>
        </div>
      </div>
      <div className="detail-grid">
        <div className="detail-main">
          {library.error ? (
            <ErrorNotice>{library.error}</ErrorNotice>
          ) : (
            (!user || library.data !== null) &&
            editions.data !== null && <BookWorkflow work={work} item={item} editions={editions.data || []} />
          )}
          {user && memberships.data?.some((m) => m.slug === 'classical-education-guide') && (
            <ClassicalWorkPreparation id={work.id} />
          )}
          <section className="panel">
            <div className="panel-header">
              <h2>About this work</h2>
            </div>
            <div className="panel-body">
              <p>{work.description || 'No description has been added yet.'}</p>
              <dl className="metadata-grid">
                <div>
                  <dt>Originally published</dt>
                  <dd>
                    {work.original_year == null
                      ? 'Not recorded'
                      : work.original_year < 0
                        ? `${-work.original_year} BCE`
                        : work.original_year}
                  </dd>
                </div>
                <div>
                  <dt>Literary / cultural association</dt>
                  <dd>{work.countries.join(', ') || 'Not recorded'}</dd>
                </div>
                <div>
                  <dt>Original language</dt>
                  <dd>{work.original_language || 'Not recorded'}</dd>
                </div>
                <div>
                  <dt>Reading effort</dt>
                  <dd>
                    {label(work.reading_load)}
                    {work.reading_effort_override != null
                      ? ` · ${work.reading_effort_override}× override`
                      : ''}
                  </dd>
                </div>
              </dl>
            </div>
          </section>
          <CrossRankingProfile work={work.id} />
          <section className="panel">
            <div className="panel-header">
              <h2>Editions & translation records</h2>
              {user?.is_staff && (
                <button className="button secondary small" onClick={() => setNewEdition(true)}>
                  <Plus size={14} />
                  Add edition
                </button>
              )}
            </div>
            <div className="panel-body">
              {editions.error ? (
                <ErrorNotice>{editions.error}</ErrorNotice>
              ) : editions.loading ? (
                <Loading />
              ) : editions.data?.length ? (
                editions.data.map((e) => (
                  <div className="source-card" key={e.id}>
                    <h3>
                      {e.translator
                        ? `Translated by ${e.translator}`
                        : e.publisher || `${e.language} edition`}
                    </h3>
                    <div className="source-meta">
                      {[
                        e.publisher,
                        e.pages ? `${e.pages} pages` : 'Pages not recorded',
                        e.abridged ? 'Abridged' : 'Not marked abridged',
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </div>
                    <p>
                      {e.translation_notes ||
                        'Translation research and comparison notes have not been added.'}
                    </p>
                    <p className="small-text muted">
                      Page count: {label(e.pages_basis || 'unknown')}
                      {e.pages_source_url && (
                        <>
                          {' '}
                          ·{' '}
                          <a href={e.pages_source_url} target="_blank" rel="noreferrer">
                            Length source
                          </a>
                        </>
                      )}
                      . Cover: {label(e.cover_basis || 'unknown')}.
                    </p>
                    <ImageCredit text={e.image_attribution} />
                    {e.source_url && (
                      <a href={e.source_url} target="_blank" rel="noreferrer" className="text-link">
                        Edition source <ExternalLink size={13} />
                      </a>
                    )}
                    {item && (
                      <button
                        className="button secondary small"
                        onClick={() => setChangingEdition(e)}
                        disabled={item.selected_edition?.id === e.id && !item.basis_needs_review}
                      >
                        {item.selected_edition?.id === e.id
                          ? item.basis_needs_review
                            ? 'Review updated edition'
                            : 'Your reading edition'
                          : 'Read this edition'}
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <p className="muted">
                  No English edition recorded. Add one to estimate reading time and plan pages.
                </p>
              )}
            </div>
          </section>
        </div>
        <aside className="detail-aside">
          {user && <QuickReading work={work} item={item} />}
          <section className="panel">
            <div className="panel-header">
              <h2>
                <Clock3 size={18} /> Time to read
              </h2>
            </div>
            <div className="panel-body">
              <div className="stat-value">{duration(work.reading_time.estimated_hours)}</div>
              {work.reading_time.low_hours != null && (
                <p className="muted">
                  Illustrative range: {work.reading_time.low_hours.toFixed(1)}–
                  {work.reading_time.high_hours?.toFixed(1)} hours
                </p>
              )}
              <p className="small-text">
                Based on the default edition, your reading pace, and the selected effort level. This is an
                adjustable estimate, not a measured prediction.
              </p>
              <details>
                <summary>How this is estimated</summary>
                <ul className="small-text">
                  {work.reading_time.assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </details>
            </div>
          </section>
          <section className="panel">
            <div className="panel-header">
              <h2>Add to a personal list</h2>
            </div>
            <div className="panel-body">
              {personalLists.length ? (
                <div className="inline-form">
                  <select
                    className="select"
                    aria-label="Choose a personal list"
                    value={listId}
                    onChange={(e) => setListId(e.target.value)}
                  >
                    <option value="">Choose a list</option>
                    {personalLists.map((l) => (
                      <option value={l.id} key={l.id}>
                        {l.title}
                      </option>
                    ))}
                  </select>
                  <button
                    className="button primary"
                    disabled={!listId}
                    onClick={() =>
                      void mutate(
                        () => api(`/api/rankings/${listId}/entries/`, 'POST', { work: work.id }),
                        'Added to your list',
                      )
                    }
                  >
                    <Plus size={16} />
                    Add
                  </button>
                </div>
              ) : (
                <p className="muted">
                  <a href="#/my-lists">Create a personal list</a> to collect works from across rankings.
                </p>
              )}
            </div>
          </section>
          {item && (
            <a className="button secondary" href="#/library">
              Update reading progress <ArrowRight size={16} />
            </a>
          )}
        </aside>
      </div>
      {changingEdition && item && (
        <EditionChange item={item} edition={changingEdition} close={() => setChangingEdition(null)} />
      )}
      {edit && <AddBook existing={work} close={() => setEdit(false)} />}
      {newEdition && <EditionForm work={work} close={() => setNewEdition(false)} saved={reload} />}
    </>
  )
}

function EditionForm({ work, close, saved }: { work: Work; close: () => void; saved: () => void }) {
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false)
  return (
    <Modal title="Add an English edition" close={close}>
      <form
        onSubmit={async (event) => {
          event.preventDefault()
          setBusy(true)
          const f = new FormData(event.currentTarget)
          try {
            await api('/api/editions/', 'POST', {
              work: work.id,
              language: 'English',
              translator: f.get('translator'),
              publisher: f.get('publisher'),
              pages: f.get('pages') ? Number(f.get('pages')) : null,
              translation_notes: f.get('notes'),
              source_url: f.get('source'),
              abridged: f.get('abridged') === 'on',
            })
            saved()
            close()
          } catch (e) {
            setError((e as Error).message)
          } finally {
            setBusy(false)
          }
        }}
      >
        {error && <ErrorNotice>{error}</ErrorNotice>}
        <label className="field">
          <span>Translator</span>
          <input className="input" name="translator" />
        </label>
        <label className="field">
          <span>Publisher</span>
          <input className="input" name="publisher" />
        </label>
        <label className="field">
          <span>Pages</span>
          <input className="input" name="pages" type="number" min={1} />
        </label>
        <label className="field">
          <span>Edition source</span>
          <input className="input" name="source" type="url" />
        </label>
        <label className="field">
          <span>Translation notes and evidence</span>
          <textarea className="textarea" name="notes" rows={3} />
        </label>
        <label className="checkbox-field">
          <input type="checkbox" name="abridged" /> Abridged edition
        </label>
        <div className="form-actions">
          <button className="button primary" disabled={busy}>
            {busy ? 'Saving…' : 'Save edition'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export function Authors({ id }: { id?: string }) {
  const { user, version, reload, notify } = useApp()
  const [browse, patch] = useBrowseState({ q: '', page: '1' })
  const page = positivePage(browse.page)
  const setPage = (value: number) => patch({ page: value })
  const [search, setSearch] = useBrowseSearch(browse.q, patch)
  const people = useResource<Page<Person>>(
    id ? null : `/api/people/?page=${page}&search=${encodeURIComponent(browse.q)}`,
    version,
  )
  const person = useResource<Person>(id ? `/api/people/${id}/` : null, version)
  const works = useResource<Page<Work>>(id ? `/api/works/?author=${id}&page=${page}` : null, version)
  if (id)
    return person.data ? (
      <>
        <PageHeader eyebrow="Authors & thinkers" title={person.data.name}>
          {person.data.countries.join(' · ') || 'Literary associations not recorded'}
        </PageHeader>
        <div className="two-column">
          <div className="panel">
            <div className="panel-body">
              {person.data.portrait && (
                <img
                  className="author-portrait"
                  src={person.data.portrait_thumbnail || person.data.portrait}
                  alt={person.data.name}
                />
              )}
              <ImageCredit text={person.data.image_attribution} />
              <p>{person.data.biography || 'No biographical note has been added yet.'}</p>
              {person.data.source_url && (
                <a className="text-link" href={person.data.source_url} target="_blank" rel="noreferrer">
                  Biographical source <ExternalLink size={14} />
                </a>
              )}
              {user?.is_staff && (
                <label className="field">
                  <span>Upload a portrait</span>
                  <input
                    className="input"
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={async (e) => {
                      if (!e.target.files?.[0]) return
                      const form = new FormData()
                      form.set('portrait', e.target.files[0])
                      form.set('expected_version', person.data!.edit_version)
                      try {
                        await api(`/api/people/${id}/`, 'PATCH', form)
                        reload()
                        notify('Portrait saved')
                      } catch (err) {
                        notify((err as Error).message, true)
                      }
                    }}
                  />
                </label>
              )}
            </div>
          </div>
          <div className="panel">
            <div className="panel-header">
              <h2>Works in the catalog</h2>
            </div>
            {works.error ? (
              <ErrorNotice>{works.error}</ErrorNotice>
            ) : works.loading ? (
              <Loading />
            ) : works.data?.count ? (
              works.data.results.map((w) => <BookRow key={w.id} work={w} />)
            ) : (
              <Empty title="No works recorded yet.">Their works will appear as the catalog grows.</Empty>
            )}
            <Pager page={page} data={works.data} setPage={setPage} loading={works.loading} />
          </div>
        </div>
      </>
    ) : person.loading ? (
      <Loading />
    ) : (
      <ErrorNotice>{person.error}</ErrorNotice>
    )
  return (
    <>
      <PageHeader eyebrow="The people behind the pages" title="Authors & thinkers.">
        Follow a mind across its works, subjects, and traditions.
      </PageHeader>
      <div className="toolbar">
        <input
          className="search-input"
          aria-label="Search authors"
          placeholder="Search authors and philosophers…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      {people.error ? (
        <ErrorNotice>{people.error}</ErrorNotice>
      ) : people.loading ? (
        <Loading />
      ) : (
        <div className="rankings-grid">
          {people.data?.results.map((p) => (
            <a className="ranking-card" key={p.id} href={`#/authors/${p.id}`}>
              <div className="card-top">
                {p.portrait ? (
                  <img className="avatar" src={p.portrait_thumbnail || p.portrait} alt="" />
                ) : (
                  <span className="avatar">{p.name[0]}</span>
                )}
                <ArrowRight size={18} />
              </div>
              <h2>{p.name}</h2>
              <p className="muted">{p.countries.join(', ') || 'View works and profile'}</p>
            </a>
          ))}
        </div>
      )}
      {!people.loading && !people.error && !people.data?.count && (
        <Empty title="Meet a mind through its works.">
          Authors and philosophers will appear here when you add their books to the catalog.
        </Empty>
      )}
      <Pager page={page} data={people.data} setPage={setPage} loading={people.loading} />
    </>
  )
}

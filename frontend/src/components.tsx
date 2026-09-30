import { SaveConflict, savedConflict } from './saveConflict'
import type { WorkCard } from './libraryData'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { BookOpen, Plus, X, Clock3, Bookmark, ArrowUpRight, Library, Feather, Layers3 } from 'lucide-react'
import { api, useResource } from './api'
import { useApp } from './context'
import type { Ranking, Work } from './types'

export const label = (text: string) => text.replaceAll('_', ' ').replace(/^./, (s) => s.toUpperCase())
export const dateLabel = (value?: string | null) =>
  value
    ? new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00` : value).toLocaleDateString(
        undefined,
        { day: 'numeric', month: 'short', year: 'numeric' },
      )
    : 'Not researched'
export const duration = (hours?: number | null) =>
  hours == null
    ? 'Time not estimated'
    : hours < 1
      ? `≈ ${Math.max(1, Math.round(hours * 60))} min`
      : `≈ ${hours.toFixed(1)} hours`
export const monthLabel = (month: string) =>
  new Date(`${month.slice(0, 7)}-01T12:00:00`).toLocaleDateString(undefined, {
    month: 'long',
    year: 'numeric',
  })
export const localMonth = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function Empty({
  title,
  children,
  action,
}: {
  title: string
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <BookOpen size={26} strokeWidth={1.3} />
      </div>
      <h3 className="empty-title">{title}</h3>
      <div className="empty-description">{children}</div>
      {action && <div className="empty-actions">{action}</div>}
    </div>
  )
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <span className="spinner" /> Opening your library…
    </div>
  )
}
export function ErrorNotice({ children }: { children: ReactNode }) {
  return (
    <div className="error-banner" role="alert">
      {children}
    </div>
  )
}
export function PageHeader({
  eyebrow,
  title,
  children,
  actions,
}: {
  eyebrow?: string
  title: string
  children?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {children && <p className="page-description">{children}</p>}
      </div>
      {actions && <div className="header-actions">{actions}</div>}
    </div>
  )
}

export function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string
  children: ReactNode
  close: () => void
  wide?: boolean
}) {
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const oldOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    panel.current?.focus()
    return () => {
      document.body.style.overflow = oldOverflow
      previous?.focus()
    }
  }, [])
  return (
    <div
      className="modal-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <div
        ref={panel}
        tabIndex={-1}
        className={`modal ${wide ? 'wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onKeyDown={(event) => {
          if (event.key === 'Escape') close()
          if (event.key === 'Tab') {
            const focusable = Array.from(
              panel.current?.querySelectorAll<HTMLElement>(
                'button:not(:disabled), input:not(:disabled):not([type="hidden"]), select:not(:disabled), textarea:not(:disabled), a[href], summary, [tabindex="0"]',
              ) || [],
            ).filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0)
            if (!focusable?.length) return
            const first = focusable[0],
              last = focusable[focusable.length - 1]
            if (
              event.shiftKey &&
              (document.activeElement === first || document.activeElement === panel.current)
            ) {
              event.preventDefault()
              last.focus()
            }
            if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault()
              first.focus()
            }
          }
        }}
      >
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="icon-button" aria-label="Close dialog" onClick={close}>
            <X size={20} />
          </button>
        </div>
        <div className="modal-content">{children}</div>
      </div>
    </div>
  )
}

export function Cover({ work, large = false }: { work: Work | WorkCard; large?: boolean }) {
  return (
    <div className={`book-cover ${large ? 'large' : ''}`}>
      {work.edition?.cover ? (
        <img
          src={work.edition.cover_thumbnail || work.edition.cover}
          alt={`${work.title} cover`}
          loading="lazy"
          decoding="async"
          onError={(event) => {
            if (event.currentTarget.dataset.fallback) return
            event.currentTarget.dataset.fallback = 'true'
            event.currentTarget.src = work.edition!.cover!
          }}
        />
      ) : (
        <div className="cover-placeholder">
          <BookOpen size={large ? 34 : 18} strokeWidth={1.2} />
          {large && <span>{work.title}</span>}
        </div>
      )}
    </div>
  )
}

export function ImageCredit({ text }: { text?: string }) {
  if (!text) return null
  return (
    <p className="small-text muted" style={{ overflowWrap: 'anywhere' }}>
      {text.split(/(https?:\/\/[^\s]+)/g).map((part, index) =>
        /^https?:\/\//.test(part) ? (
          <a key={index} href={part} target="_blank" rel="noreferrer">
            Image source / license
          </a>
        ) : (
          part
        ),
      )}
    </p>
  )
}

export function RankingCard({
  ranking,
  personalView = false,
  detailGroup,
}: {
  ranking: Ranking
  personalView?: boolean
  detailGroup?: string
}) {
  const { mutate, requireLogin } = useApp()
  const Icon = ranking.domain === 'philosophy' ? Layers3 : ranking.origin === 'external' ? Library : Feather
  const bookmarked = ranking.preference?.bookmarked
  const detailQuery = new URLSearchParams()
  if (personalView) detailQuery.set('view', 'bookmarked')
  if (ranking.origin === 'external')
    detailQuery.set('group', ranking.presentation === 'ranked' ? 'published-rankings' : 'collections')
  if (detailGroup) detailQuery.set('group', detailGroup)
  const category =
    ranking.origin === 'personal'
      ? 'Personal list'
      : ranking.origin === 'external'
        ? ranking.presentation === 'ranked'
          ? 'Published ranking'
          : 'Reading collection'
        : ranking.item_type === 'person'
          ? 'Thinkers'
          : 'Researched ranking'
  const stale =
    ranking.last_researched_at &&
    ranking.preference?.refresh_interval_days &&
    Date.now() - Date.parse(ranking.last_researched_at) > ranking.preference.refresh_interval_days * 86400000
  const groupedPositions =
    ranking.scope.group_by === 'country' && typeof ranking.scope.position_count === 'number'
      ? ranking.scope.position_count
      : null
  const retainedSources =
    ranking.scope.group_by === 'country' && typeof ranking.scope.source_record_count === 'number'
      ? ranking.scope.source_record_count
      : null
  return (
    <article className="ranking-card">
      <div className="card-top">
        <div className={`card-icon ${ranking.domain}`}>
          <Icon size={22} strokeWidth={1.5} />
        </div>
        <div className="card-actions">
          <span className="pill muted">{category}</span>
          <button
            className={`icon-button ${bookmarked ? 'selected' : ''}`}
            aria-label={`${bookmarked ? 'Unbookmark' : 'Bookmark'} ${ranking.title}`}
            onClick={() => {
              if (requireLogin())
                void mutate(
                  () => api(`/api/rankings/${ranking.id}/preference/`, 'PATCH', { bookmarked: !bookmarked }),
                  bookmarked ? 'Bookmark removed' : 'Ranking bookmarked',
                )
            }}
          >
            <Bookmark size={18} fill={bookmarked ? 'currentColor' : 'none'} />
          </button>
        </div>
      </div>
      <a className="card-title" href={`#/rankings/${ranking.id}${detailQuery.size ? `?${detailQuery}` : ''}`}>
        {ranking.title}
        <ArrowUpRight size={18} />
      </a>
      <p className="card-description">
        {ranking.description ||
          `A ${ranking.presentation === 'unranked' ? 'reading collection' : 'ranking'} shaped by careful research and your interests.`}
      </p>
      <div className="card-meta">
        <span>
          {groupedPositions
            ? `${groupedPositions} positions · ${ranking.entry_count || 0} distinct works`
            : `${ranking.entry_count || 0} ${ranking.item_type === 'person' ? 'people' : 'works'}`}
        </span>
        <span>
          {retainedSources
            ? `${retainedSources} source records`
            : `${ranking.source_count || 0} eligible records`}
        </span>
        {(ranking.source_count > 0 || retainedSources) && (
          <span className="pill gold">
            {(ranking.has_editorial || ranking.scope.editorial) && ranking.origin === 'curated'
              ? 'Initial selection'
              : 'Evidence saved'}
          </span>
        )}
      </div>
      <div className="card-footer">
        <span title={ranking.updated_at}>Updated {dateLabel(ranking.updated_at)}</span>
        <span className={stale ? 'pill gold' : 'muted'}>
          {stale
            ? 'Refresh suggested'
            : ranking.last_researched_at
              ? `Researched ${dateLabel(ranking.last_researched_at)}`
              : (ranking.has_editorial || ranking.scope.editorial) && ranking.origin === 'curated'
                ? 'Research continuing'
                : 'Not researched'}
        </span>
      </div>
    </article>
  )
}

export function BookRow({
  work,
  action,
  index,
}: {
  work: Work | WorkCard
  action?: ReactNode
  index?: ReactNode
}) {
  return (
    <div className="book-row">
      {index != null && <div className="rank-number">{index}</div>}
      <a href={`#/books/${work.id}`} aria-label={`Open ${work.title}`}>
        <Cover work={work} />
      </a>
      <div className="book-info">
        <a href={`#/books/${work.id}`} className="book-title">
          {work.title}
        </a>
        <div className="book-author">
          {work.authors.map((a) => a.name).join(', ') || 'Author not recorded'}
        </div>
        <div className="book-meta">
          <span>{label(work.form)}</span>
          {work.genres.slice(0, 2).map((genre) => (
            <span className="pill gold" key={genre}>
              {genre}
            </span>
          ))}
          <span>
            <Clock3 size={12} />
            {duration(work.reading_time.estimated_hours)}
          </span>
        </div>
      </div>
      {action && <div className="row-actions">{action}</div>}
    </div>
  )
}

export function AddBook({ close, existing }: { close: () => void; existing?: Work }) {
  const { reload, notify } = useApp()
  const facets = useResource<{ genre_catalog: string[] }>('/api/works/facets/')
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false)
  const [editVersion, setEditVersion] = useState(existing?.edit_version)
  const [conflict, setConflict] = useState<Record<string, unknown> | null>(null)
  const [genres, setGenres] = useState(existing?.genres || [])
  const genreOptions = [...new Set([...(facets.data?.genre_catalog || []), ...(existing?.genres || [])])]
  return (
    <Modal title={existing ? 'Edit work' : 'Add a book or work'} close={close} wide>
      <form
        onSubmit={async (event) => {
          event.preventDefault()
          setBusy(true)
          setError('')
          const data = new FormData(event.currentTarget)
          const split = (key: string) =>
            String(data.get(key) || '')
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean)
          const authors =
            existing && data.get('authors') === existing.authors.map((author) => author.name).join(', ')
              ? { author_ids: existing.authors.map((author) => author.id) }
              : { author_names: split('authors') }
          const payload = {
            expected_version: editVersion,
            title: data.get('title'),
            ...authors,
            form: data.get('form'),
            field: data.get('field'),
            original_year: data.get('year') ? Number(data.get('year')) : null,
            countries: split('countries'),
            tag_names: split('tags'),
            genre_names: data.getAll('genres').map(String),
            reading_load: data.get('reading_load'),
            reading_effort_override: data.get('effort_override') ? Number(data.get('effort_override')) : null,
            description: data.get('description'),
            edition_input: {
              pages: data.get('pages') ? Number(data.get('pages')) : null,
              language: existing?.edition?.language ?? 'English',
              translator: data.get('translator') || '',
              publisher: data.get('publisher') || '',
              isbn: data.get('isbn') || '',
            },
          }
          try {
            const factors = ['prose', 'concepts', 'structure'].map((key) =>
              String(data.get(`difficulty_${key}`) ?? ''),
            )
            if (factors.some(Boolean) && !factors.every(Boolean))
              throw new Error('Choose all three difficulty levels, or leave all three unassessed.')
            const { reading_effort_override, ...withoutOverride } = payload
            const requestPayload = factors.every(Boolean)
              ? {
                  ...withoutOverride,
                  difficulty_factors: {
                    prose: Number(factors[0]),
                    concepts: Number(factors[1]),
                    structure: Number(factors[2]),
                  },
                }
              : { ...withoutOverride, reading_effort_override }
            const book = await api<Work>(
              existing ? `/api/works/${existing.id}/` : '/api/works/',
              existing ? 'PATCH' : 'POST',
              requestPayload,
            )
            const cover = data.get('cover') as File
            const attribution = String(data.get('attribution') || '')
            if (
              book.edition &&
              (cover?.size || attribution !== (existing?.edition?.image_attribution || ''))
            ) {
              const upload = new FormData()
              if (book.edition.edit_version) upload.set('expected_version', book.edition.edit_version)
              if (cover?.size) upload.set('cover', cover)
              upload.set('image_attribution', attribution)
              try {
                await api(`/api/editions/${book.edition.id}/`, 'PATCH', upload)
              } catch (e) {
                notify(`Work saved, but cover or attribution update failed: ${(e as Error).message}`, true)
              }
            }
            reload()
            close()
            window.location.hash = `/books/${book.id}`
          } catch (e) {
            setError((e as Error).message)
            setConflict(savedConflict(e))
          } finally {
            setBusy(false)
          }
        }}
      >
        <p className="muted">
          Add a real work to the shared catalog. You can save it to your library and lists next.
        </p>
        {error && <ErrorNotice>{error}</ErrorNotice>}
        <SaveConflict
          current={conflict}
          accept={(value) => {
            setEditVersion(value)
            setConflict(null)
            setError('')
          }}
        />
        <div className="form-grid">
          <label className="field full">
            <span>Title</span>
            <input
              className="input"
              name="title"
              required
              maxLength={300}
              defaultValue={existing?.title}
              placeholder="Book or work title"
            />
          </label>
          <label className="field full">
            <span>Author or authors</span>
            <input
              className="input"
              name="authors"
              defaultValue={existing?.authors.map((a) => a.name).join(', ')}
              placeholder="Separate multiple names with commas"
            />
          </label>
          <label className="field">
            <span>Form</span>
            <select className="select" name="form" defaultValue={existing?.form || 'book'}>
              {['book', 'collection', 'essay', 'short_story', 'poem', 'play'].map((v) => (
                <option key={v} value={v}>
                  {label(v)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Field</span>
            <select className="select" name="field" defaultValue={existing?.field || 'literature'}>
              {['literature', 'philosophy', 'nonfiction', 'manga'].map((v) => (
                <option key={v} value={v}>
                  {label(v)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Original publication year</span>
            <input
              className="input"
              name="year"
              type="number"
              min={-10000}
              max={3000}
              defaultValue={existing?.original_year ?? ''}
              placeholder="Negative for BCE; leave unknown blank"
            />
          </label>
          <label className="field">
            <span>English edition pages</span>
            <input
              className="input"
              name="pages"
              type="number"
              min={1}
              defaultValue={existing?.edition?.pages ?? ''}
              placeholder="Used for your reading plan"
            />
          </label>
          <label className="field">
            <span>Literary / cultural countries</span>
            <input
              className="input"
              name="countries"
              defaultValue={existing?.countries.join(', ')}
              placeholder="e.g. England, France"
            />
          </label>
          <label className="field">
            <span>Topics</span>
            <input
              className="input"
              name="tags"
              defaultValue={existing?.tags.join(', ')}
              placeholder="e.g. Ethics, Modernism"
            />
          </label>
          <fieldset className="field full">
            <legend>Estimate difficulty from the work</legend>
            <p className="small-text muted">
              Optional editorial assessment. Select all three to calculate a new effort multiplier. The saved
              multiplier affects reading estimates and difficulty-aware planning for this book. Leave blank to
              retain its existing profile or override.
            </p>
            <div className="form-grid">
              {[
                ['prose', 'Prose complexity'],
                ['concepts', 'Conceptual density'],
                ['structure', 'Structural difficulty'],
              ].map(([key, title]) => (
                <label className="field" key={key}>
                  <span>{title}</span>
                  <select className="select" name={`difficulty_${key}`} defaultValue="">
                    <option value="">Not assessed</option>
                    {['Straightforward', 'Mild', 'Moderate', 'Demanding', 'Exceptionally demanding'].map(
                      (label, value) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ),
                    )}
                  </select>
                </label>
              ))}
            </div>
            <small>
              Assess the text itself; publication age and genre alone do not determine difficulty. Only the
              resulting multiplier is saved.
            </small>
          </fieldset>
          <label className="field full">
            <span>Genres / categories</span>
            <select
              className="select taxonomy-select"
              name="genres"
              multiple
              value={genres}
              onChange={(event) =>
                setGenres(Array.from(event.target.selectedOptions, (option) => option.value))
              }
              aria-label="Genres or categories"
            >
              {genreOptions.map((genre) => (
                <option value={genre} key={genre}>
                  {genre}
                </option>
              ))}
            </select>
            <small className="muted">Choose any that apply. Use Ctrl/Command-click to select several.</small>
          </label>
          <label className="field">
            <span>Translator</span>
            <input className="input" name="translator" defaultValue={existing?.edition?.translator} />
          </label>
          <label className="field">
            <span>Publisher</span>
            <input className="input" name="publisher" defaultValue={existing?.edition?.publisher} />
          </label>
          <label className="field">
            <span>ISBN</span>
            <input className="input" name="isbn" defaultValue={existing?.edition?.isbn} />
          </label>
          <label className="field">
            <span>Reading effort</span>
            <select
              className="select"
              name="reading_load"
              defaultValue={existing?.reading_load || 'classic_literature'}
            >
              <option value="leisure">Leisure reading</option>
              <option value="classic_literature">Classic literature</option>
              <option value="demanding_literature">Demanding literature</option>
              <option value="philosophy">Philosophy / close study</option>
            </select>
          </label>
          <label className="field full">
            <span>Custom effort multiplier (optional)</span>
            <input
              className="input"
              name="effort_override"
              type="number"
              min={0.25}
              max={10}
              step="any"
              defaultValue={existing?.reading_effort_override ?? ''}
              placeholder="Use the selected reading effort by default"
            />
            <small>
              Provisional defaults: leisure 1×, classics 1.5×, demanding literature 2×, philosophy 2.5×. An
              override replaces the default for this work.
            </small>
          </label>
          <label className="field full">
            <span>Description or catalog note</span>
            <textarea className="textarea" name="description" rows={3} defaultValue={existing?.description} />
          </label>
          <label className="field">
            <span>Cover image</span>
            <input className="input" name="cover" type="file" accept="image/jpeg,image/png,image/webp" />
            <small className="muted">JPEG, PNG or WebP, up to 8 MB.</small>
          </label>
          <label className="field">
            <span>Image source / attribution</span>
            <input className="input" name="attribution" defaultValue={existing?.edition?.image_attribution} />
          </label>
        </div>
        <div className="form-actions">
          <button type="button" className="button secondary" onClick={close}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? 'Saving…' : existing ? 'Save changes' : 'Add to catalog'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export function NewList({ close }: { close: () => void }) {
  const { reload } = useApp()
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false)
  return (
    <Modal title="Create a personal list" close={close}>
      <form
        onSubmit={async (event) => {
          event.preventDefault()
          setBusy(true)
          const form = new FormData(event.currentTarget)
          try {
            const list = await api<Ranking>('/api/rankings/', 'POST', {
              title: form.get('title'),
              description: form.get('description'),
              presentation: form.get('presentation'),
              item_type: form.get('item_type'),
              domain: form.get('domain'),
            })
            reload()
            close()
            window.location.hash = `/rankings/${list.id}`
          } catch (e) {
            setError((e as Error).message)
          } finally {
            setBusy(false)
          }
        }}
      >
        {error && <ErrorNotice>{error}</ErrorNotice>}
        <label className="field">
          <span>List name</span>
          <input
            className="input"
            name="title"
            required
            maxLength={240}
            placeholder="A year of thoughtful reading"
          />
        </label>
        <label className="field">
          <span>Description</span>
          <textarea className="textarea" name="description" rows={3} />
        </label>
        <div className="form-grid">
          <label className="field">
            <span>Order</span>
            <select className="select" name="presentation">
              <option value="ranked">Ranked list</option>
              <option value="unranked">Unranked collection</option>
              <option value="reading_sequence">Reading sequence</option>
            </select>
          </label>
          <label className="field">
            <span>Items</span>
            <select className="select" name="item_type">
              <option value="work">Books and other works</option>
              <option value="person">Authors and philosophers</option>
            </select>
          </label>
          <label className="field">
            <span>Field</span>
            <select className="select" name="domain">
              <option value="literature">Literature</option>
              <option value="philosophy">Philosophy</option>
              <option value="nonfiction">Nonfiction</option>
              <option value="history">History</option>
              <option value="manga">Manga</option>
              <option value="all">All subjects</option>
            </select>
          </label>
        </div>
        <div className="notice">Private by default. You can share a selected list with a link later.</div>
        <div className="form-actions">
          <button className="button primary" disabled={busy}>
            <Plus size={16} />
            {busy ? 'Creating…' : 'Create list'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

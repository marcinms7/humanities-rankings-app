import type { ApiAllocationPreview } from './generated/apiContracts'
import { useEffect, useState } from 'react'
import { BookmarkPlus, CalendarDays, ListPlus } from 'lucide-react'
import { api } from './api'
import { useApp } from './context'
import { duration, Empty, ErrorNotice, label, localMonth, Modal } from './components'
import { EditionChange } from './editionChange'
import type { Edition, LibraryItem, Work } from './types'
import './bookWorkflow.css'

type AllocationPreview = ApiAllocationPreview

function editionName(edition: Edition) {
  return [
    edition.translator ? `${edition.translator}, translator` : edition.publisher || edition.language,
    edition.pages == null ? 'length unknown' : `${edition.pages} pages`,
    edition.isbn ? `ISBN ${edition.isbn}` : '',
  ]
    .filter(Boolean)
    .join(' · ')
}

export function BookWorkflow({
  work,
  item,
  editions,
}: {
  work: Work
  item?: LibraryItem
  editions: Edition[]
}) {
  const { user, requireLogin, reload, notify } = useApp()
  const [localItem, setLocalItem] = useState(item)
  const [selection, setSelection] = useState(
    String(
      item?.selected_edition?.id ||
        (editions.some((e) => e.id === work.edition?.id) ? work.edition?.id : '') ||
        '',
    ),
  )
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [change, setChange] = useState<Edition | null>(null),
    [planning, setPlanning] = useState(false)
  useEffect(() => {
    setLocalItem(item)
    if (item) setSelection(String(item.selected_edition?.id || ''))
  }, [item])
  const saved = localItem
  const defaultEdition = editions.find((e) => e.id === work.edition?.id)
  const chosen = selection ? editions.find((e) => e.id === Number(selection)) : defaultEdition
  const selected = saved?.selected_edition || chosen
  const pages = saved ? saved.reading_basis.pages : chosen?.pages
  async function save(): Promise<LibraryItem> {
    if (saved) return saved
    const record = await api<LibraryItem>('/api/library/', 'POST', {
      work: work.id,
      ...(selection ? { edition: Number(selection) } : {}),
    })
    setLocalItem(record)
    return record
  }
  async function action(kind: 'save' | 'next' | 'plan') {
    if (!requireLogin() || busy) return
    setBusy(true)
    setError('')
    try {
      const record = await save()
      if (kind === 'next') {
        await api('/api/read-next/', 'POST', {
          item: record.id,
          action: record.read_next_position == null ? 'add' : 'remove',
        })
        setLocalItem(await api<LibraryItem>(`/api/library/${record.id}/`))
        notify(record.read_next_position == null ? 'Added to Read next' : 'Removed from Read next')
      } else if (kind === 'plan') setPlanning(true)
      else notify('Reading edition saved to your library')
      reload()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="panel book-workflow" id="reading-workflow">
      <div className="panel-header">
        <h2>Your next steps</h2>
        <span className="pill muted">{saved ? label(saved.status) : 'Private reading'}</span>
      </div>
      <div className="panel-body">
        {!user && (
          <p>Choose a reading edition, then sign in to save it, add it to Read next or make time for it.</p>
        )}
        <label className="field">
          <span>{saved ? 'Your saved reading edition' : 'Choose your reading edition'}</span>
          <select
            className="select"
            value={selection}
            disabled={busy}
            onChange={(event) => {
              const value = event.target.value
              if (saved) {
                const edition = editions.find((e) => e.id === Number(value))
                if (edition) setChange(edition)
              } else setSelection(value)
            }}
          >
            {!saved && (
              <option value="">
                {defaultEdition
                  ? `Catalog default · ${editionName(defaultEdition)}`
                  : 'No catalog default · length unknown'}
              </option>
            )}
            {saved?.selected_edition && !editions.some((e) => e.id === saved.selected_edition!.id) && (
              <option value={saved.selected_edition.id}>
                {editionName(saved.selected_edition)} · saved historical edition
              </option>
            )}
            {saved && !saved.selected_edition && <option value="">No edition saved yet</option>}
            {editions.map((edition) => (
              <option value={edition.id} key={edition.id}>
                {editionName(edition)}
              </option>
            ))}
          </select>
        </label>
        {selected && (
          <p className="small-text muted">
            {selected.language || 'Language not recorded'}
            {selected.abridged ? ' · abridged' : ''}
            {selected.source_url && (
              <>
                {' '}
                ·{' '}
                <a href={selected.source_url} target="_blank" rel="noreferrer">
                  Edition source ↗
                </a>
              </>
            )}
          </p>
        )}
        <dl className="reading-facts">
          <div>
            <dt>{saved ? 'Saved length' : 'Selected length'}</dt>
            <dd>{pages == null ? 'Unknown' : `${pages} pages`}</dd>
          </div>
          <div>
            <dt>Current page</dt>
            <dd>{saved ? saved.current_page : 'Not started'}</dd>
          </div>
          <div>
            <dt>Remaining time</dt>
            <dd>
              {saved ? duration(saved.remaining_reading_time.estimated_hours) : 'Available after saving'}
            </dd>
          </div>
        </dl>
        <p className="small-text muted">
          {label((saved?.reading_basis.pages_basis || chosen?.pages_basis) ?? 'unknown')} ·{' '}
          {saved
            ? 'Progress and planning use your saved edition.'
            : 'A cover or ISBN alone does not establish translation quality.'}
        </p>
        {saved?.basis_needs_review && (
          <p className="notice">
            The catalog edition changed. Your reading still uses its saved length.{' '}
            <button
              className="text-link"
              disabled={busy || !chosen}
              onClick={() => chosen && setChange(chosen)}
            >
              Review edition changes
            </button>
          </p>
        )}
        {error && <ErrorNotice>{error}</ErrorNotice>}
        <div className="reading-actions">
          {!saved && (
            <button className="button primary" disabled={busy} onClick={() => void action('save')}>
              <BookmarkPlus size={16} />
              Save to my library
            </button>
          )}
          <button className="button secondary" disabled={busy} onClick={() => void action('next')}>
            <ListPlus size={16} />
            {saved?.read_next_position != null
              ? 'Remove from Read next'
              : saved
                ? 'Add to Read next'
                : 'Save & read next'}
          </button>
          <button
            className="button secondary"
            disabled={busy || (!!saved && ['finished', 'abandoned'].includes(saved.status))}
            onClick={() => void action('plan')}
          >
            <CalendarDays size={16} />
            {saved ? 'Schedule reading' : 'Save & plan'}
          </button>
        </div>
        {saved && ['finished', 'abandoned'].includes(saved.status) && (
          <p className="small-text muted">
            Start a reread in Your reading below before scheduling this work again.
          </p>
        )}
        {saved && (
          <p className="small-text">
            <a className="text-link" href="#/library?view=next">
              Read next →
            </a>{' '}
            ·{' '}
            <a className="text-link" href="#/planner">
              Reading plan →
            </a>
          </p>
        )}
      </div>
      {change && saved && <EditionChange item={saved} edition={change} close={() => setChange(null)} />}
      {planning && saved && <BookAllocation item={saved} close={() => setPlanning(false)} />}
    </section>
  )
}

function BookAllocation({ item, close }: { item: LibraryItem; close: () => void }) {
  const { reload, notify } = useApp()
  const remaining =
    item.reading_basis.pages == null ? null : Math.max(0, item.reading_basis.pages - item.current_page)
  const [month, setMonth] = useState(localMonth()),
    [pages, setPages] = useState(remaining == null ? '' : String(remaining))
  const [locked, setLocked] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [preview, setPreview] = useState<AllocationPreview | null>(null)
  useEffect(() => setPreview(null), [month, pages, locked, item.updated_at])
  async function submit(apply = false) {
    if (busy || (apply && !preview)) return
    setBusy(true)
    setError('')
    try {
      const result = await api<AllocationPreview>('/api/reading-allocation/', 'POST', {
        work: item.work,
        month: `${month}-01`,
        pages: pages === '' ? null : Number(pages),
        locked,
        apply,
        ...(apply ? { preview_token: preview!.preview_token } : {}),
      })
      if (apply) {
        reload()
        notify('Reading allocation saved')
        close()
      } else setPreview(result)
    } catch (e) {
      setError((e as Error).message)
      setPreview(null)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal title={`Make time for ${item.book.title}`} close={close}>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <p>
          {remaining == null
            ? 'Your saved edition has no page count. You can enter a manual allocation or leave pages unallocated.'
            : `${remaining} pages remain in your saved edition. Choose how much to read this month.`}
        </p>
        <div className="form-grid">
          <label className="field">
            <span>Month</span>
            <input
              className="input"
              type="month"
              min="1900-01"
              max="2200-12"
              required
              value={month}
              disabled={busy}
              onChange={(event) => setMonth(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Physical pages to schedule</span>
            <input
              className="input"
              type="number"
              min={1}
              max={remaining ?? 100000}
              value={pages}
              disabled={busy}
              onChange={(event) => setPages(event.target.value)}
              placeholder="Unallocated"
            />
          </label>
        </div>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={locked}
            disabled={busy}
            onChange={(event) => setLocked(event.target.checked)}
          />
          Lock this allocation
        </label>
        {error && <ErrorNotice>{error}</ErrorNotice>}
        {preview && (
          <div className="notice">
            <p>
              {preview.pages == null
                ? 'Pages unallocated'
                : `${preview.pages} physical pages · ${Math.round(preview.effort_pages || 0)} ${preview.capacity.unit === 'baseline_pages' ? 'baseline pages' : 'pages'}`}{' '}
              for {preview.month.slice(0, 7)}.
            </p>
            <p>
              {Math.round(preview.capacity.used)} / {Math.round(preview.capacity.budget)} already scheduled.
            </p>
            {preview.over_capacity > 0 && (
              <p className="source-limit">
                This adds {Math.round(preview.over_capacity)} pages of effort beyond your monthly target.
              </p>
            )}
            {preview.capacity.unknown_allocations > 0 && (
              <p>Existing unallocated books are not included in the capacity total.</p>
            )}
            {preview.warnings.map((warning) => (
              <p key={warning}>{warning}</p>
            ))}
            {preview.other_allocations.length > 0 && (
              <ul className="small-text">
                {preview.other_allocations.map((row) => (
                  <li key={row.month}>
                    {row.month.slice(0, 7)} ·{' '}
                    {row.remaining_pages == null
                      ? 'Page allocation unknown'
                      : `${row.remaining_pages} pages remaining in that allocation`}
                    {row.pages_read == null ? ' · reading total unrecorded' : ''}
                    {row.locked ? ' · locked' : ''}
                    {!row.same_reading_basis ? ' · different saved reading edition' : ''}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {remaining === 0 ? (
          <Empty title="No remaining pages">
            Update your reading record before scheduling another attempt.
          </Empty>
        ) : (
          <div className="form-actions">
            <button className="button secondary" disabled={busy}>
              Preview allocation
            </button>
            {preview && (
              <button
                type="button"
                className="button primary"
                disabled={busy}
                onClick={() => void submit(true)}
              >
                Confirm & schedule
              </button>
            )}
          </div>
        )}
      </form>
    </Modal>
  )
}

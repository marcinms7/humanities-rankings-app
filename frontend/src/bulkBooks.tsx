import { lazy, Suspense, useState } from 'react'
import { APIError, api, useResource } from './api'
import { useApp } from './context'
import { ErrorNotice, Loading, Modal } from './components'
import { Pager } from './pagination'
import { queryCache } from './queryCache'
import { addSelectedBooks, parsePrivateLabels, selectionLimit, type SelectedBook } from './bookSelection'
import type { Page, Ranking } from './types'
import type { ApiBulkBookActionResult } from './generated/apiContracts'
import './bulkBooks.css'

type BulkAction = 'library' | 'read_next' | 'personal_list' | 'shelves' | 'personal_tags'
type SelectionState = { key: string; active: boolean; books: SelectedBook[] }
const BibliographyDialog = lazy(() => import('./bibliography'))

export function useBookSelection(scope: string) {
  const { user } = useApp()
  const key = `${queryCache.generation}:${user?.id ?? 'anonymous'}:${scope}`
  const empty: SelectionState = { key, active: false, books: [] }
  const [saved, setSaved] = useState<SelectionState>(empty)
  const state = saved.key === key ? saved : empty
  const update = (change: (previous: SelectionState) => SelectionState) =>
    setSaved((previous) => change(previous.key === key ? previous : empty))
  return {
    ...state,
    available: !!user,
    start: () => update((previous) => ({ ...previous, active: true })),
    clear: () => setSaved(empty),
    remove: (id: number) =>
      update((previous) => ({ ...previous, books: previous.books.filter((b) => b.id !== id) })),
    add: (books: SelectedBook[]) =>
      update((previous) => ({ ...previous, books: addSelectedBooks(previous.books, books) })),
    toggle: (book: SelectedBook) =>
      update((previous) => ({
        ...previous,
        books: previous.books.some((b) => b.id === book.id)
          ? previous.books.filter((b) => b.id !== book.id)
          : addSelectedBooks(previous.books, [book]),
      })),
  }
}

type BookSelection = ReturnType<typeof useBookSelection>

export function BookSelectionCheckbox({ selection, book }: { selection: BookSelection; book: SelectedBook }) {
  if (!selection.available || !selection.active) return null
  const checked = selection.books.some((item) => item.id === book.id)
  return (
    <label className="book-selection-checkbox">
      <input
        type="checkbox"
        checked={checked}
        disabled={!checked && selection.books.length >= selectionLimit}
        onChange={() => selection.toggle(book)}
        aria-label={`Select ${book.title}`}
      />
      <span>Select</span>
    </label>
  )
}

export function BulkBookActions({
  selection,
  visible,
  loading = false,
  library = false,
}: {
  selection: BookSelection
  visible: SelectedBook[]
  loading?: boolean
  library?: boolean
}) {
  const [dialog, setDialog] = useState<{ key: string; action: BulkAction } | null>(null)
  const [exportKey, setExportKey] = useState<string | null>(null)
  if (!selection.available) return null
  if (!selection.active)
    return (
      <div className="bulk-book-start">
        <button className="button secondary small" onClick={selection.start}>
          Select books
        </button>
      </div>
    )
  const ids = new Set(selection.books.map((book) => book.id))
  const remaining = [...new Set(visible.map((book) => book.id))].filter((id) => !ids.has(id)).length
  const open = (action: BulkAction) => setDialog({ key: selection.key, action })
  return (
    <section className="bulk-book-actions panel" aria-label="Selected book actions">
      <div className="bulk-book-controls">
        <strong role="status">{selection.books.length} selected</strong>
        <button
          className="button secondary small"
          disabled={loading || !remaining || ids.size + remaining > selectionLimit}
          onClick={() => selection.add(visible)}
        >
          Select this page
        </button>
        <button className="button secondary small" onClick={selection.clear}>
          Cancel selection
        </button>
      </div>
      <p className="small-text muted">
        Selections stay selected across pages and filters. Choose up to {selectionLimit} books.
      </p>
      <div className="bulk-book-controls">
        {!library && (
          <button className="button secondary small" disabled={!ids.size} onClick={() => open('library')}>
            Add to My Library
          </button>
        )}
        <button className="button secondary small" disabled={!ids.size} onClick={() => open('read_next')}>
          Add to Read next
        </button>
        <button className="button secondary small" disabled={!ids.size} onClick={() => open('personal_list')}>
          Add to a private list
        </button>
        <button
          className="button secondary small"
          disabled={!ids.size}
          onClick={() => setExportKey(selection.key)}
        >
          Export bibliography
        </button>
        {library && (
          <>
            <button className="button secondary small" disabled={!ids.size} onClick={() => open('shelves')}>
              Add shelves
            </button>
            <button
              className="button secondary small"
              disabled={!ids.size}
              onClick={() => open('personal_tags')}
            >
              Add private tags
            </button>
          </>
        )}
      </div>
      {!!ids.size && (
        <details className="bulk-selected-books">
          <summary>Review selected books</summary>
          <ul>
            {selection.books.map((book) => (
              <li key={book.id}>
                <span>{book.title}</span>
                <button
                  className="button secondary small"
                  aria-label={`Deselect ${book.title}`}
                  onClick={() => selection.remove(book.id)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
      {dialog?.key === selection.key && (
        <BulkBookDialog
          key={`${selection.key}:${dialog.action}`}
          action={dialog.action}
          books={selection.books}
          close={() => setDialog(null)}
          saved={() => {
            setDialog(null)
            selection.clear()
          }}
        />
      )}
      {exportKey === selection.key && !!ids.size && (
        <Suspense
          fallback={
            <Modal title="Export bibliography" close={() => setExportKey(null)}>
              <Loading />
            </Modal>
          }
        >
          <BibliographyDialog books={selection.books} close={() => setExportKey(null)} />
        </Suspense>
      )}
    </section>
  )
}

const actionNames: Record<BulkAction, string> = {
  library: 'Add to My Library',
  read_next: 'Add to Read next',
  personal_list: 'Add to a private list',
  shelves: 'Add shelves',
  personal_tags: 'Add private tags',
}

function BulkBookDialog({
  action,
  books,
  close,
  saved,
}: {
  action: BulkAction
  books: SelectedBook[]
  close: () => void
  saved: () => void
}) {
  const { version, reload, notify } = useApp()
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [labels, setLabels] = useState(''),
    [page, setPage] = useState(1)
  const [destination, setDestination] = useState<Ranking | null>(null)
  const lists = useResource<Page<Ranking>>(
    action === 'personal_list' ? `/api/rankings/?paged=1&mode=my-lists&ordering=title&page=${page}` : null,
    version,
  )
  const choices =
    lists.data?.results.filter(
      (list) => list.can_edit && list.item_type === 'work' && !list.sharing_enabled,
    ) || []
  const isLabels = action === 'shelves' || action === 'personal_tags'
  const values = parsePrivateLabels(labels)
  const canSave =
    books.length > 0 && (action !== 'personal_list' || !!destination) && (!isLabels || values.length > 0)
  const submit = async () => {
    if (busy || !canSave) return
    setBusy(true)
    setError('')
    const generation = queryCache.generation
    try {
      const result = await api<ApiBulkBookActionResult>('/api/library/bulk/', 'POST', {
        action,
        work_ids: books.map((book) => book.id),
        ...(destination ? { ranking_id: destination.id, expected_revision: destination.revision } : {}),
        ...(isLabels ? { values } : {}),
      })
      if (generation !== queryCache.generation) return
      reload()
      const changed =
        action === 'library'
          ? result.added_to_library
          : action === 'read_next'
            ? result.added_to_read_next
            : action === 'personal_list'
              ? result.added_to_list
              : result.updated_labels
      notify(
        `${changed} ${changed === 1 ? 'book' : 'books'} ${isLabels ? 'updated' : 'added'}${result.unchanged_count ? `; ${result.unchanged_count} already included` : ''}.`,
      )
      saved()
    } catch (err) {
      if (generation === queryCache.generation && (err as Error).name !== 'AbortError') {
        setError((err as Error).message)
        // A stale destination must be selected again from the refreshed list.
        if (action === 'personal_list' && err instanceof APIError && err.status === 409) {
          setDestination(null)
          queryCache.invalidate(['rankings'])
        }
      }
    } finally {
      if (generation === queryCache.generation) setBusy(false)
    }
  }
  return (
    <Modal
      title={actionNames[action]}
      close={() => {
        if (!busy) close()
      }}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <p>
          {books.length} {books.length === 1 ? 'book selected' : 'books selected'}.
        </p>
        {action === 'library' && (
          <p className="small-text muted">
            New books will be saved as Want to read. Books already in your library keep their progress,
            editions and ratings.
          </p>
        )}
        {action === 'read_next' && (
          <p className="small-text muted">
            New choices will be appended in selection order. Books missing from My Library will also be saved
            there.
          </p>
        )}
        {action === 'personal_list' && (
          <>
            <p className="small-text muted">
              Append missing books in selection order to one of your private book lists.
            </p>
            <button
              className="button secondary small"
              type="button"
              disabled={busy || lists.loading}
              onClick={() => {
                setDestination(null)
                queryCache.invalidate(['rankings'])
              }}
            >
              Refresh lists
            </button>
            {lists.error && <ErrorNotice>{lists.error}</ErrorNotice>}
            {lists.loading ? (
              <Loading />
            ) : (
              <div className="bulk-list-choices">
                {choices.map((list) => (
                  <label key={list.id}>
                    <input
                      type="radio"
                      name="bulk-destination"
                      checked={destination?.id === list.id}
                      disabled={busy}
                      onChange={() => setDestination(list)}
                    />
                    <span>{list.title}</span>
                  </label>
                ))}
                {!choices.length && (
                  <p className="small-text muted">
                    No private book lists on this page. You can create one in{' '}
                    <a href="#/my-lists" target="_blank" rel="noopener noreferrer">
                      My lists (new tab)
                    </a>
                    .
                  </p>
                )}
              </div>
            )}
            <Pager page={page} data={lists.data} setPage={setPage} loading={lists.loading || busy} />
            {destination && (
              <p className="small-text">
                Selected list: <strong>{destination.title}</strong>
              </p>
            )}
          </>
        )}
        {isLabels && (
          <label className="field">
            <span>{action === 'shelves' ? 'Shelf names' : 'Private tags'} (comma-separated)</span>
            <input
              className="input"
              value={labels}
              disabled={busy}
              maxLength={4000}
              onChange={(event) => setLabels(event.target.value)}
              placeholder={action === 'shelves' ? 'Own a copy, Book club' : 'History, Revisit'}
            />
            <small className="muted">Add these to every selected book. Existing labels stay in place.</small>
          </label>
        )}
        {error && <ErrorNotice>{error}</ErrorNotice>}
        <div className="form-actions">
          <button className="button secondary" type="button" disabled={busy} onClick={close}>
            Cancel
          </button>
          <button className="button primary" disabled={busy || !canSave}>
            {busy ? 'Saving…' : actionNames[action]}
          </button>
        </div>
      </form>
    </Modal>
  )
}

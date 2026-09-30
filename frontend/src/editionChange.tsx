import { useState } from 'react'
import { api } from './api'
import { useApp } from './context'
import { ErrorNotice, Modal } from './components'
import type { Edition, LibraryItem, ReadingBasis } from './types'

type Preview = {
  token: string
  before: ReadingBasis
  after: ReadingBasis
  old_page: number
  page: number
  plan_items: number
  note: string
}

export function EditionChange({
  item,
  edition,
  close,
}: {
  item: LibraryItem
  edition: Edition
  close: () => void
}) {
  const { reload, notify } = useApp()
  const [mode, setMode] = useState('manual'),
    [page, setPage] = useState('')
  const [preview, setPreview] = useState<Preview | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  async function submit(apply = false) {
    setBusy(true)
    setError('')
    try {
      const result = await api<Preview>(`/api/library/${item.id}/edition-change/`, 'POST', {
        edition: edition.id,
        mode,
        ...(mode === 'manual' ? { page: Number(page) } : {}),
        apply,
        ...(apply ? { token: preview?.token } : {}),
      })
      if (apply) {
        reload()
        notify('Reading edition and progress updated')
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
    <Modal title="Change reading edition" close={close}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <p>
          Your saved progress is page {item.current_page} of {item.reading_basis.pages ?? 'unknown'}. The
          selected edition has {edition.pages ?? 'unknown'} pages.
        </p>
        <label className="field">
          <span>Progress in the selected edition</span>
          <select
            className="select"
            value={mode}
            disabled={busy}
            onChange={(e) => {
              setMode(e.target.value)
              setPreview(null)
            }}
          >
            <option value="manual">Enter the page using your chapter or passage</option>
            <option value="reset">Reset page to zero</option>
            <option value="keep">Keep the same page number</option>
            <option value="proportional">Approximate by percentage</option>
          </select>
        </label>
        {mode === 'manual' && (
          <label className="field">
            <span>Page in selected edition</span>
            <input
              className="input"
              type="number"
              min={0}
              max={edition.pages ?? undefined}
              required
              value={page}
              disabled={busy}
              onChange={(e) => {
                setPage(e.target.value)
                setPreview(null)
              }}
            />
          </label>
        )}
        {error && <ErrorNotice>{error}</ErrorNotice>}
        {preview && (
          <div className="notice">
            <p>
              Page {preview.old_page} → page {preview.page}. {preview.plan_items} saved allocations retain
              their original pages and assumptions.
            </p>
            <p>{preview.note}</p>
          </div>
        )}
        <div className="form-actions">
          <button className="button secondary" disabled={busy}>
            Preview change
          </button>
          {preview && (
            <button
              type="button"
              className="button primary"
              disabled={busy}
              onClick={() => void submit(true)}
            >
              Confirm edition & page
            </button>
          )}
        </div>
      </form>
    </Modal>
  )
}

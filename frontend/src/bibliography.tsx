import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { ErrorNotice, Loading, Modal } from './components'
import { bibliographyFile, bibliographyFormats, type BibliographyFormat } from './bibliographyFiles'
import type { SelectedBook } from './bookSelection'
import type { ApiBibliographyExport } from './generated/apiContracts'
import './bibliography.css'

const editionLabels = {
  library_snapshot: 'Saved reading edition',
  library_edition: 'Your library edition',
  catalog_default: 'Catalog default edition',
  none: 'Work only; no edition',
}

export default function BibliographyDialog({ books, close }: { books: SelectedBook[]; close: () => void }) {
  const [preferLibrary, setPreferLibrary] = useState(true)
  const [format, setFormat] = useState<BibliographyFormat>('plain_text')
  const [retry, setRetry] = useState(0)
  const [state, setState] = useState<{ data: ApiBibliographyExport | null; error: string }>({
    data: null,
    error: '',
  })
  const [copyStatus, setCopyStatus] = useState('')
  const preview = useRef<HTMLTextAreaElement>(null)
  const ids = JSON.stringify(books.map((book) => book.id))
  useEffect(() => {
    const controller = new AbortController()
    setState({ data: null, error: '' })
    setCopyStatus('')
    void api<ApiBibliographyExport>(
      '/api/bibliography/',
      'POST',
      { work_ids: JSON.parse(ids), prefer_library_editions: preferLibrary },
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setState({ data, error: '' })
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted && error.name !== 'AbortError')
          setState({ data: null, error: error.message })
      })
    return () => controller.abort()
  }, [ids, preferLibrary, retry])

  const file = state.data ? bibliographyFile(state.data, format) : null
  const copy = async () => {
    if (!file) return
    try {
      await navigator.clipboard.writeText(file.text)
      setCopyStatus('Copied to clipboard.')
    } catch {
      preview.current?.focus()
      preview.current?.select()
      setCopyStatus('Automatic copying is unavailable. The text is selected; use your usual Copy command.')
    }
  }
  const download = () => {
    if (!file) return
    const url = URL.createObjectURL(new Blob([file.text], { type: file.mime }))
    const link = document.createElement('a')
    link.href = url
    link.download = file.name
    document.body.appendChild(link)
    link.click()
    link.remove()
    // Let the browser consume the object URL before releasing it.
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <Modal title="Export bibliography" close={close} wide>
      <div className="bibliography-export">
        <p>
          {books.length} selected {books.length === 1 ? 'book' : 'books'}. Copy references or download a file
          for your reference manager.
        </p>
        <label className="bibliography-preference">
          <input
            type="checkbox"
            checked={preferLibrary}
            onChange={(event) => setPreferLibrary(event.target.checked)}
          />
          <span>Use my saved reading editions when available</span>
        </label>
        <p className="small-text muted">
          Otherwise, the catalog default is used. Missing details stay marked. Edition publication years are
          not recorded; original work dates are shown separately.
        </p>
        {state.error ? (
          <>
            <ErrorNotice>{state.error}</ErrorNotice>
            <button className="button secondary" onClick={() => setRetry((value) => value + 1)}>
              Try again
            </button>
          </>
        ) : !state.data ? (
          <Loading />
        ) : (
          <>
            <label className="field">
              <span>Export format</span>
              <select
                value={format}
                onChange={(event) => {
                  setFormat(event.target.value as BibliographyFormat)
                  setCopyStatus('')
                }}
              >
                {Object.entries(bibliographyFormats).map(([value, option]) => (
                  <option key={value} value={value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Preview</span>
              <textarea ref={preview} className="bibliography-preview" value={file?.text || ''} readOnly />
            </label>
            <div className="bibliography-buttons">
              <button className="button primary" onClick={() => void copy()}>
                Copy {bibliographyFormats[format].label}
              </button>
              <button className="button secondary" onClick={download}>
                Download .{bibliographyFormats[format].extension}
              </button>
            </div>
            <p className="small-text" role="status">
              {copyStatus}
            </p>
            <details className="bibliography-details">
              <summary>Review editions and missing information ({state.data.count} books)</summary>
              <ol>
                {state.data.references.map((reference) => (
                  <li key={reference.work_id}>
                    <strong>{reference.title}</strong>
                    <p className="small-text">{editionLabels[reference.edition_source]}</p>
                    <p className="small-text">Not recorded: {reference.missing_fields.join(', ')}.</p>
                    {reference.notices.map((notice) => (
                      <p className="small-text muted" key={notice}>
                        {notice}
                      </p>
                    ))}
                  </li>
                ))}
              </ol>
            </details>
            <p className="small-text muted">{state.data.notes.join(' ')}</p>
          </>
        )}
      </div>
    </Modal>
  )
}

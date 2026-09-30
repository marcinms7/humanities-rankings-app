import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Check, ExternalLink, History, Search, ShieldCheck } from 'lucide-react'
import { api, useResource } from './api'
import { dateLabel, Empty, ErrorNotice, label, Loading, Modal, PageHeader } from './components'
import { useApp } from './context'
import './catalogReview.css'

type EditionRecord = {
  id: number
  isbn: string
  publisher: string
  pages: number | null
  language: string
  translator: string
  abridged: boolean
  source_url: string
  pages_source_url: string
  pages_basis: string
  cover_source_url: string
  image_attribution: string
  translation_notes: string
}
type Snapshot = Partial<EditionRecord> & {
  authors?: { id: number; name: string }[]
  name?: string
  title?: string
  countries?: string[]
  edition?: EditionRecord | null
  work?: { title: string; authors: { id: number; name: string }[] }
}
type ReviewReceipt = {
  id: number
  batch_id: string
  entity_type: string
  entity_id: number
  issue: string
  action: string
  title: string
  note: string
  evidence_url: string
  deferred_until: string | null
  created_at: string
}
type Source = {
  title: string
  url: string
  evidence: string
  limitations: string
  consulted_on: string | null
}
type ReviewRow = {
  key: string
  entity_type: 'work' | 'person' | 'edition'
  entity_id: number
  work_id: number | null
  title: string
  category: string
  issue: string
  reason: string
  fingerprint: string
  review_version: number
  status: string
  decision: ReviewReceipt | null
  snapshot: Snapshot
  library_saves: number
  list_appearances: number
  image_url: string
  prioritized: boolean
  related: { id: number; title: string; entity_type: string }[]
  evidence: {
    ranking_id: number
    title: string
    url: string
    presentation: string
    position: number
    source_rank: number | null
    rationale: string
    excerpt_truncated: boolean
    sources: Source[]
  }[]
}
type Queue = {
  count: number
  page: number
  page_size: number
  results: ReviewRow[]
  totals: Record<string, number>
  priority_basis: string
}
type HistoryPage = { count: number; page: number; page_size: number; results: ReviewReceipt[] }
const selection = (row: ReviewRow) => ({
  key: row.key,
  fingerprint: row.fingerprint,
  review_version: row.review_version,
})
const recordLink = (row: ReviewRow) =>
  row.entity_type === 'person' ? `#/authors/${row.entity_id}` : `#/books/${row.work_id}`
const safeUrl = (url?: string) => (/^https?:\/\//i.test(url || '') ? url : undefined)

function EvidenceLink({ url, children }: { url?: string; children: ReactNode }) {
  return safeUrl(url) ? (
    <a href={url} target="_blank" rel="noreferrer">
      {children} <ExternalLink size={12} />
    </a>
  ) : null
}

function Evidence({ row }: { row: ReviewRow }) {
  const record = row.snapshot
  const edition = row.entity_type === 'edition' ? (record as EditionRecord) : record.edition
  const authors = record.authors || record.work?.authors || []
  return (
    <div className="catalog-review-evidence">
      <p>{row.reason}</p>
      {row.image_url && (
        <img
          className="catalog-review-image"
          src={row.image_url}
          alt={`Saved image for ${row.title}`}
          loading="lazy"
        />
      )}
      {authors.length > 0 && (
        <p>
          <strong>Saved attribution:</strong> {authors.map((a) => a.name).join(', ')}
        </p>
      )}
      {edition && (
        <>
          <dl className="catalog-review-metadata">
            <div>
              <dt>Publisher / translator</dt>
              <dd>
                {edition.publisher || 'Not recorded'}
                {edition.translator && ` · ${edition.translator}`}
              </dd>
            </div>
            <div>
              <dt>ISBN / language</dt>
              <dd>
                {edition.isbn || 'No ISBN'} · {edition.language}
              </dd>
            </div>
            <div>
              <dt>Physical length</dt>
              <dd>
                {edition.pages ? `${edition.pages} pages` : 'Not recorded'} · {label(edition.pages_basis)}
              </dd>
            </div>
            <div>
              <dt>Completeness</dt>
              <dd>
                {edition.abridged
                  ? 'Marked abridged'
                  : 'Not marked abridged; completeness still needs evidence'}
              </dd>
            </div>
          </dl>
          <div className="catalog-review-links">
            <EvidenceLink url={edition.source_url}>Edition record</EvidenceLink>
            <EvidenceLink url={edition.pages_source_url}>Length source</EvidenceLink>
            <EvidenceLink url={edition.cover_source_url}>Image source</EvidenceLink>
          </div>
          {edition.translation_notes && <p className="catalog-review-excerpt">{edition.translation_notes}</p>}
          {edition.image_attribution && (
            <p className="small-text">Image credit: {edition.image_attribution}</p>
          )}
        </>
      )}
      {row.entity_type === 'person' && (
        <>
          <EvidenceLink url={record.source_url}>Person source</EvidenceLink>
          {record.image_attribution && <p>Image credit: {record.image_attribution}</p>}
        </>
      )}
      {row.related.length > 0 && (
        <div>
          <strong>Other matching records</strong>
          <ul>
            {row.related.map((other) => (
              <li key={other.id}>
                <a href={`#/${other.entity_type === 'person' ? 'authors' : 'books'}/${other.id}`}>
                  {other.title} · record {other.id}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      <h4>Saved list context</h4>
      <p className="small-text muted">
        Up to three appearances and two source-register excerpts per list. List-level evidence provides
        context; it does not itself verify this identity, image or edition.
      </p>
      {row.evidence.length ? (
        row.evidence.map((entry) => (
          <div className="catalog-review-source" key={entry.ranking_id}>
            <a href={`#/rankings/${entry.ranking_id}`}>{entry.title}</a>{' '}
            <span className="small-text muted">
              {entry.presentation === 'ranked'
                ? `Position ${entry.position}`
                : `Collection entry ${entry.position}`}
              {entry.source_rank != null ? ` · publisher rank ${entry.source_rank}` : ''}
            </span>
            {entry.rationale && (
              <p className="catalog-review-excerpt">
                {entry.rationale}
                {entry.excerpt_truncated ? '… [excerpt]' : ''}
              </p>
            )}
            <EvidenceLink url={entry.url}>List source</EvidenceLink>
            {entry.sources.map((source, index) => (
              <details key={index}>
                <summary>{source.title}</summary>
                <p className="small-text">Recorded consultation: {dateLabel(source.consulted_on)}</p>
                <p>{source.evidence || 'No evidence excerpt recorded.'}</p>
                {source.limitations && <p className="small-text muted">Limitations: {source.limitations}</p>}
                <EvidenceLink url={source.url}>Source record</EvidenceLink>
              </details>
            ))}
          </div>
        ))
      ) : (
        <p className="muted">No public shared-list appearance is recorded for this item.</p>
      )}
      {row.decision && (
        <p className="notice">
          Latest review: {label(row.decision.action)} · {row.decision.note}
          {row.decision.deferred_until && ` · until ${dateLabel(row.decision.deferred_until)}`}
        </p>
      )}
    </div>
  )
}

function ReviewPager({
  page,
  count,
  busy,
  setPage,
  noun = 'issues',
}: {
  page: number
  count: number
  busy: boolean
  setPage: (n: number) => void
  noun?: string
}) {
  const pages = Math.max(1, Math.ceil(count / 24))
  return (
    <div className="catalog-review-pagination">
      <button
        className="button secondary small"
        disabled={busy || page <= 1}
        onClick={() => setPage(page - 1)}
      >
        Previous
      </button>
      <span>
        Page {page} of {pages} · {count.toLocaleString()} {noun}
      </span>
      <button
        className="button secondary small"
        disabled={busy || page >= pages}
        onClick={() => setPage(page + 1)}
      >
        Next
      </button>
    </div>
  )
}

export function CatalogReview() {
  const { user, version, reload, notify } = useApp()
  const [category, setCategory] = useState('all'),
    [status, setStatus] = useState('active'),
    [search, setSearch] = useState('')
  const [query, setQuery] = useState(''),
    [page, setPage] = useState(1),
    [history, setHistory] = useState(false),
    [historyPage, setHistoryPage] = useState(1)
  const [selected, setSelected] = useState<string[]>([]),
    [action, setAction] = useState('needs_research')
  const [note, setNote] = useState(''),
    [url, setUrl] = useState(''),
    [deferredUntil, setDeferredUntil] = useState('')
  const [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [approval, setApproval] = useState<ReviewRow | null>(null),
    [receipt, setReceipt] = useState<{ batch_id: string; count: number } | null>(null)
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search)
      setPage(1)
    }, 250)
    return () => clearTimeout(timer)
  }, [search])
  const params = new URLSearchParams({ category, status, search: query, page: String(page) })
  const queue = useResource<Queue>(
    user?.is_staff && !history ? `/api/catalog-review/?${params}` : null,
    version,
  )
  const audit = useResource<HistoryPage>(
    user?.is_staff && history ? `/api/catalog-review/history/?page=${historyPage}` : null,
    version,
  )
  useEffect(() => {
    setSelected([])
    setConfirmed(false)
  }, [queue.data, category, status, page, history])
  useEffect(() => {
    if (queue.data && page > 1 && !queue.data.results.length)
      setPage(Math.max(1, Math.ceil(queue.data.count / 24)))
  }, [queue.data, page])
  const rows = queue.data?.results || []
  const chosen = rows.filter((row) => selected.includes(row.key))
  const canCheck = chosen.length > 0 && chosen.every((row) => row.category === 'identity')
  const setFilter = (callback: (value: string) => void, value: string) => {
    callback(value)
    setPage(1)
    setSelected([])
  }
  if (!user?.is_staff)
    return <Empty title="Catalog administration">This workspace is available to catalog staff.</Empty>
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    setReceipt(null)
    try {
      const result = await api<{ batch_id: string; count: number }>('/api/catalog-review/batch/', 'POST', {
        action,
        items: chosen.map(selection),
        note,
        evidence_url: url,
        deferred_until: deferredUntil,
        identity_confirmed: confirmed,
      })
      setReceipt(result)
      setSelected([])
      setNote('')
      setConfirmed(false)
      reload()
      notify(`${result.count} catalog review decisions saved`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="Catalog administration"
        title="Review the catalog."
        actions={
          <button
            className="button secondary"
            onClick={() => {
              setHistory(!history)
              setSelected([])
              setError('')
            }}
          >
            <History size={16} />
            {history ? 'Back to queue' : 'Decision history'}
          </button>
        }
      >
        Resolve uncertain identities, image gaps and edition records using the evidence already saved. Reader
        interest helps put frequently encountered items first.
      </PageHeader>
      {receipt && (
        <p className="notice" role="status">
          <Check size={15} /> Saved {receipt.count} decisions. Receipt: <code>{receipt.batch_id}</code>
        </p>
      )}
      {history ? (
        <>
          {audit.error && <ErrorNotice>{audit.error}</ErrorNotice>}
          {audit.loading ? (
            <Loading />
          ) : (
            <>
              <div className="panel catalog-review-history">
                {audit.data?.results.length ? (
                  audit.data.results.map((row) => (
                    <article key={row.id}>
                      <h3>{row.title || `${label(row.entity_type)} ${row.entity_id}`}</h3>
                      <p>
                        <span className="pill muted">{label(row.action)}</span> · {label(row.issue)} ·{' '}
                        {dateLabel(row.created_at)}
                      </p>
                      <p>{row.note}</p>
                      <EvidenceLink url={row.evidence_url}>Recorded evidence</EvidenceLink>
                      {row.deferred_until && <p>Deferred until {dateLabel(row.deferred_until)}</p>}
                      <p className="small-text muted">Receipt {row.batch_id}</p>
                    </article>
                  ))
                ) : (
                  <Empty title="No review decisions yet.">
                    Batch decisions and edition approvals will leave a durable receipt here.
                  </Empty>
                )}
              </div>
              <ReviewPager
                page={historyPage}
                count={audit.data?.count || 0}
                busy={false}
                setPage={setHistoryPage}
                noun="decisions"
              />
            </>
          )}
        </>
      ) : (
        <>
          <div className="catalog-review-totals">
            {(['identity', 'images', 'editions'] as const).map((key) => (
              <button
                key={key}
                className={`panel catalog-review-total ${category === key ? 'selected' : ''}`}
                onClick={() => setFilter(setCategory, category === key ? 'all' : key)}
              >
                <strong>{queue.data?.totals[key]?.toLocaleString() ?? '—'}</strong>
                <span>{label(key)} issues</span>
              </button>
            ))}
          </div>
          <p className="small-text muted">
            {queue.data?.priority_basis ||
              'Priority uses saved library interest and appearances in shared public lists.'}
          </p>
          <div className="toolbar">
            <label className="catalog-review-search">
              <Search size={16} />
              <input
                className="search-input"
                aria-label="Search review queue"
                placeholder="Find a title or person…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <select
              className="filter-select"
              aria-label="Review category"
              value={category}
              onChange={(e) => setFilter(setCategory, e.target.value)}
            >
              <option value="all">All categories</option>
              <option value="identity">Identities</option>
              <option value="images">Images</option>
              <option value="editions">Editions</option>
            </select>
            <select
              className="filter-select"
              aria-label="Review status"
              value={status}
              onChange={(e) => setFilter(setStatus, e.target.value)}
            >
              <option value="active">Active queue</option>
              <option value="needs_research">Needs research</option>
              <option value="deferred">Deferred</option>
              <option value="checked">Identity checked</option>
              <option value="all">All current issues</option>
            </select>
          </div>
          {queue.error && <ErrorNotice>{queue.error}</ErrorNotice>}
          {error && <ErrorNotice>{error}</ErrorNotice>}
          {queue.loading ? (
            <Loading />
          ) : rows.length ? (
            <>
              <label className="checkbox-field catalog-review-select">
                <input
                  type="checkbox"
                  checked={selected.length === rows.length}
                  onChange={(e) => setSelected(e.target.checked ? rows.map((row) => row.key) : [])}
                />{' '}
                Select all {rows.length} issues on this page
              </label>
              <div className="catalog-review-grid">
                {rows.map((row) => (
                  <article className="panel catalog-review-card" key={row.key}>
                    <div className="catalog-review-card-head">
                      <input
                        type="checkbox"
                        aria-label={`Select ${row.title}: ${label(row.issue)}`}
                        checked={selected.includes(row.key)}
                        onChange={(e) =>
                          setSelected((old) =>
                            e.target.checked ? [...old, row.key] : old.filter((key) => key !== row.key),
                          )
                        }
                      />
                      <div>
                        <a className="book-title" href={recordLink(row)}>
                          {row.title}
                        </a>
                        <div className="tag-row">
                          <span className="pill gold">{label(row.issue)}</span>
                          {row.status !== 'active' && <span className="pill muted">{label(row.status)}</span>}
                          {row.prioritized && <span className="pill muted">Prioritized</span>}
                        </div>
                      </div>
                    </div>
                    <p>{row.reason}</p>
                    <p className="small-text muted">
                      {row.library_saves} library saves · {row.list_appearances} list appearances
                    </p>
                    <details>
                      <summary>Review saved evidence</summary>
                      <Evidence row={row} />
                    </details>
                    <div className="catalog-review-links">
                      <a className="text-link" href={recordLink(row)}>
                        Open catalog record →
                      </a>
                      {row.issue === 'staged_edition' && (
                        <button className="button secondary small" onClick={() => setApproval(row)}>
                          <ShieldCheck size={15} />
                          Review edition approval
                        </button>
                      )}
                      <a
                        className="small-text"
                        href={`/admin/core/${row.entity_type}/${row.entity_id}/change/`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Edit catalog metadata
                      </a>
                    </div>
                  </article>
                ))}
              </div>
              <ReviewPager page={page} count={queue.data?.count || 0} busy={busy} setPage={setPage} />
            </>
          ) : (
            !queue.error && (
              <Empty title="No matching review issues.">
                Try another category, status or search. Completed metadata fixes disappear from the live queue
                automatically.
              </Empty>
            )
          )}
          {chosen.length > 0 && !queue.loading && (
            <form className="panel catalog-review-batch" onSubmit={submit}>
              <h2>Decide on {chosen.length} selected issues</h2>
              <p className="small-text muted">
                Every decision records the catalog snapshot and your explanation. A later metadata change
                reopens the issue for review.
              </p>
              <div className="form-grid">
                <label className="field">
                  <span>Decision</span>
                  <select
                    className="select"
                    value={action}
                    onChange={(e) => {
                      setAction(e.target.value)
                      setConfirmed(false)
                    }}
                  >
                    <option value="needs_research">Needs further research</option>
                    <option value="prioritize">Prioritize for the next pass</option>
                    <option value="defer">Defer until a date</option>
                    <option value="reopen">Reopen / clear prior triage</option>
                    <option value="identity_checked" disabled={!canCheck}>
                      Identity signal checked with evidence
                    </option>
                  </select>
                </label>
                {action === 'defer' && (
                  <label className="field">
                    <span>Return to queue on</span>
                    <input
                      className="input"
                      type="date"
                      required
                      value={deferredUntil}
                      onChange={(e) => setDeferredUntil(e.target.value)}
                    />
                  </label>
                )}
                <label className="field full">
                  <span>
                    Review note
                    {action === 'identity_checked'
                      ? ' — explain the attribution or why matching records are distinct'
                      : ''}
                  </span>
                  <textarea
                    className="textarea"
                    required
                    minLength={action === 'identity_checked' ? 20 : 3}
                    maxLength={3000}
                    rows={3}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
                <label className="field full">
                  <span>
                    Evidence URL{' '}
                    {action === 'identity_checked' ? '(required for every selected identity)' : '(optional)'}
                  </span>
                  <input
                    className="input"
                    type="url"
                    required={action === 'identity_checked'}
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                  />
                </label>
              </div>
              {action === 'identity_checked' && (
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    required
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />{' '}
                  I checked every selected identity against this evidence; their saved attribution or distinct
                  identity is supported.
                </label>
              )}
              <div className="form-actions">
                <button
                  type="button"
                  className="button secondary"
                  disabled={busy}
                  onClick={() => setSelected([])}
                >
                  Clear selection
                </button>
                <button
                  className="button primary"
                  disabled={busy || (action === 'identity_checked' && !canCheck)}
                >
                  {busy ? 'Saving decisions…' : `Save ${chosen.length} decisions`}
                </button>
              </div>
            </form>
          )}
        </>
      )}
      {approval && <EditionApproval row={approval} close={() => setApproval(null)} />}
    </>
  )
}

function EditionApproval({ row, close }: { row: ReviewRow; close: () => void }) {
  const { reload, notify } = useApp()
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const edition = row.snapshot as EditionRecord
  const ready = Boolean(edition.isbn && edition.publisher && edition.pages && edition.language)
  return (
    <Modal
      title={`Review edition: ${row.title}`}
      close={() => {
        if (!busy) close()
      }}
      wide
    >
      <Evidence row={row} />
      <form
        onSubmit={async (event) => {
          event.preventDefault()
          setBusy(true)
          setError('')
          const form = new FormData(event.currentTarget)
          try {
            await api('/api/catalog-review/edition/', 'POST', {
              items: [selection(row)],
              evidence_url: form.get('evidence_url'),
              note: form.get('note'),
              identity_confirmed: form.get('identity_confirmed') === 'on',
              scope_confirmed: form.get('scope_confirmed') === 'on',
              pagination_confirmed: form.get('pagination_confirmed') === 'on',
              confirmed_metadata: {
                isbn: form.get('isbn'),
                pages: Number(form.get('pages')),
                publisher: edition.publisher,
                language: edition.language,
                abridged: edition.abridged,
              },
            })
            reload()
            notify('Edition approved and audit receipt saved')
            close()
          } catch (e) {
            setError((e as Error).message)
          } finally {
            setBusy(false)
          }
        }}
      >
        {error && <ErrorNotice>{error}</ErrorNotice>}
        <p className="notice">
          Approval makes this edition available to readers. The work’s default edition and all saved reading
          progress and plans retain their existing values.
        </p>
        {!ready && (
          <ErrorNotice>
            ISBN, publisher, language and page count must be recorded before approval. Correct the candidate
            in catalog administration first.
          </ErrorNotice>
        )}
        <div className="form-grid">
          <label className="field">
            <span>Type the exact ISBN you verified</span>
            <input className="input" name="isbn" required autoComplete="off" />
          </label>
          <label className="field">
            <span>Type the verified physical page count</span>
            <input className="input" type="number" name="pages" min={1} required />
          </label>
          <label className="field full">
            <span>Publisher or library evidence URL</span>
            <input className="input" type="url" name="evidence_url" required maxLength={1000} />
          </label>
          <label className="field full">
            <span>What supports the work identity, edition scope and pagination?</span>
            <textarea className="textarea" name="note" rows={4} required minLength={30} maxLength={3000} />
          </label>
        </div>
        <div className="catalog-review-confirmations">
          <label className="checkbox-field">
            <input type="checkbox" name="identity_confirmed" required /> This ISBN, publisher, language and
            translation match the named work.
          </label>
          <label className="checkbox-field">
            <input type="checkbox" name="scope_confirmed" required /> I checked volume scope, completeness and
            the recorded abridgement status against the evidence.
          </label>
          <label className="checkbox-field">
            <input type="checkbox" name="pagination_confirmed" required /> The page count describes this
            physical edition, including its recorded volume scope.
          </label>
        </div>
        <div className="form-actions">
          <button className="button secondary" type="button" onClick={close} disabled={busy}>
            Cancel
          </button>
          <button className="button primary" disabled={busy || !ready}>
            {busy ? 'Saving approval…' : 'Approve this edition'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

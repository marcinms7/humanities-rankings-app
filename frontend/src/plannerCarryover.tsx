import { useEffect, useState } from 'react'
import { ArrowRight, Check } from 'lucide-react'
import { api } from './api'
import { useApp } from './context'
import { ErrorNotice, Modal, monthLabel } from './components'
import type { MonthCapacity, PlanItem } from './types'
import type { PlanSummary } from './libraryData'
import './readingWorkflow.css'

type CarryoverPreview = {
  preview_token: string
  source_month: string
  target_month: string
  items: {
    id: number
    work: number
    title: string
    pages: number
    remaining_before: number
    action: string
    effort_pages: number
  }[]
  skipped: { id: number; title: string; reason: string }[]
  left_in_source: { id: number; title: string; pages: number; reason: string }[]
  capacity: MonthCapacity & { committed_before: number; committed_after: number; remaining_after: number }
  warnings: string[]
}

export function AllocationProgress({ item }: { item: PlanItem | PlanSummary }) {
  const { mutate } = useApp()
  const [editing, setEditing] = useState(false),
    [busy, setBusy] = useState(false)
  const [value, setValue] = useState(item.pages_read == null ? '' : String(item.pages_read))
  useEffect(() => {
    setValue(item.pages_read == null ? '' : String(item.pages_read))
  }, [item.id, item.pages_read])
  const remaining =
    item.pages == null ? null : Math.max(0, item.pages - (item.pages_read || 0) - item.carried_pages)
  const save = async (pages: number | null) => {
    setBusy(true)
    if (
      await mutate(
        () =>
          api(`/api/plan/${item.id}/progress/`, 'POST', {
            pages_read: pages,
            expected_updated_at: item.updated_at,
          }),
        'Monthly reading recorded',
      )
    )
      setEditing(false)
    setBusy(false)
  }
  return (
    <div className="allocation-progress">
      <p className="small-text">
        {item.pages_read == null
          ? 'Pages read this month: not recorded'
          : `${item.pages_read.toLocaleString()} pages read this month`}
        {item.carried_pages > 0 && <> · {item.carried_pages.toLocaleString()} carried forward</>}
        {remaining != null && item.pages_read != null && <> · {remaining.toLocaleString()} remaining</>}
      </p>
      {item.pages != null && !editing && (
        <button className="text-link" onClick={() => setEditing(true)}>
          {item.pages_read == null ? 'Record monthly pages read' : 'Correct reading total'}
        </button>
      )}
      {editing && (
        <form
          className="allocation-progress-form"
          onSubmit={(e) => {
            e.preventDefault()
            if (value !== '') void save(Number(value))
          }}
        >
          <label className="field">
            <span>Pages actually read from this allocation</span>
            <input
              className="input"
              type="number"
              min={0}
              max={(item.pages || 0) - item.carried_pages}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
              disabled={busy}
              aria-label={`Pages read in ${monthLabel(item.month)} for ${item.book.title}`}
            />
          </label>
          <p className="small-text muted">
            Enter 0 if none were read. This records monthly reading separately from your current page in the
            book. Locked scheduling stays unchanged.
          </p>
          <div className="row-actions">
            <button className="button secondary small" disabled={busy || value === ''}>
              <Check size={14} />
              Save total
            </button>
            <button
              className="button secondary small"
              type="button"
              disabled={busy}
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
            {item.pages_read != null && !item.carried_pages && (
              <button className="text-link" type="button" disabled={busy} onClick={() => void save(null)}>
                Mark unrecorded
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  )
}

export function PlannerCarryover({
  month,
  items,
  close,
}: {
  month: string
  items: (PlanItem | PlanSummary)[]
  close: () => void
}) {
  const { version, user, mutate } = useApp()
  const [selected, setSelected] = useState(items.map((item) => item.id))
  const [overCapacity, setOverCapacity] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [result, setResult] = useState<{ context: string; value: CarryoverPreview } | null>(null)
  const context = JSON.stringify([month, selected, overCapacity, version, user?.id])
  const preview = result?.context === context ? result.value : null
  useEffect(() => {
    setResult(null)
  }, [context])
  const submit = async (apply = false) => {
    if (busy || (apply && !preview)) return
    setBusy(true)
    setError('')
    try {
      const value = await api<CarryoverPreview>('/api/plan/carryover/', 'POST', {
        source_month: month,
        plan_ids: selected,
        allow_over_capacity: overCapacity,
        apply,
        ...(apply ? { preview_token: preview!.preview_token } : {}),
      })
      if (apply) {
        await mutate(async () => null, 'Unfinished pages carried forward')
        close()
      } else setResult({ context, value })
    } catch (caught) {
      setResult(null)
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal
      title={`Carry forward · ${monthLabel(month)}`}
      close={() => {
        if (!busy) close()
      }}
      wide
    >
      <p>
        Review unfinished pages for the following month. Your original scheduled pages and recorded reading
        stay in this month, with a receipt for pages carried forward.
      </p>
      <p className="small-text muted">
        Record monthly pages read first, including 0 when none were read. Locked allocations and incompatible
        editions are shown as conflicts. Existing compatible allocations receive extra pages.
      </p>
      <div className="check-list">
        {items.map((item) => (
          <label className="check-item" key={item.id}>
            <input
              type="checkbox"
              disabled={busy}
              checked={selected.includes(item.id)}
              onChange={(e) =>
                setSelected(
                  e.target.checked ? [...selected, item.id] : selected.filter((id) => id !== item.id),
                )
              }
            />
            <span>
              {item.book.title}
              <small className="muted">
                {item.pages ?? '?'} scheduled ·{' '}
                {item.pages_read == null ? 'reading unrecorded' : `${item.pages_read} read`}
                {item.carried_pages ? ` · ${item.carried_pages} already carried` : ''}
                {item.locked ? ' · locked' : ''}
              </small>
            </span>
          </label>
        ))}
      </div>
      {!items.length && <p className="notice">There are no allocations in this month.</p>}
      <label className="checkbox-field">
        <input
          type="checkbox"
          checked={overCapacity}
          disabled={busy}
          onChange={(e) => setOverCapacity(e.target.checked)}
        />
        Include all unfinished pages even if the next month exceeds my target
      </label>
      {error && <ErrorNotice>{error}</ErrorNotice>}
      {preview && (
        <section className="panel panel-body carryover-preview" aria-live="polite">
          <h3>{monthLabel(preview.target_month)}</h3>
          <p>
            {Math.round(preview.capacity.committed_before).toLocaleString()} →{' '}
            {Math.round(preview.capacity.committed_after).toLocaleString()} /{' '}
            {Math.round(preview.capacity.budget).toLocaleString()}{' '}
            {preview.capacity.unit === 'baseline_pages' ? 'baseline pages' : 'pages'} committed
          </p>
          {preview.capacity.remaining_after < 0 && (
            <p className="source-limit">
              {Math.ceil(-preview.capacity.remaining_after).toLocaleString()} above your monthly target
            </p>
          )}
          {preview.items.map((item) => (
            <p key={item.id}>
              <strong>{item.title}</strong> <ArrowRight size={14} /> {item.pages} pages{' '}
              {item.action === 'append' ? 'added to the existing allocation' : 'in a new allocation'}
            </p>
          ))}
          {!preview.items.length && <p>No unfinished pages can be carried forward with these choices.</p>}
          {preview.skipped.map((item) => (
            <p className="small-text source-limit" key={item.id}>
              <strong>{item.title}:</strong> {item.reason}
            </p>
          ))}
          {preview.left_in_source.map((item) => (
            <p className="small-text source-limit" key={item.id}>
              <strong>{item.title}:</strong> {item.pages} pages stay in {monthLabel(month)} because they do
              not fit.
            </p>
          ))}
          {preview.warnings.map((warning) => (
            <p className="source-limit" key={warning}>
              {warning}
            </p>
          ))}
        </section>
      )}
      <div className="form-actions">
        <button
          className="button secondary"
          disabled={busy || !selected.length}
          onClick={() => void submit()}
        >
          {busy ? 'Working…' : 'Preview carryover'}
        </button>
        {preview && (
          <button
            className="button primary"
            disabled={busy || !preview.items.length}
            onClick={() => void submit(true)}
          >
            Confirm carryover
          </button>
        )}
      </div>
    </Modal>
  )
}

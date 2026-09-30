import { useState } from 'react'
import './readingCalendar.css'
import { api, useResource } from './api'
import { useApp } from './context'
import { ErrorNotice, Loading, Modal, monthLabel } from './components'
import type { ApiCalendarPreview, ApiCalendarState } from './generated/apiContracts'

type Props = { start: string; months: number; close: () => void }

export function ReadingCalendar({ start, months, close }: Props) {
  const { version } = useApp()
  const saved = useResource<ApiCalendarState>('/api/reading-calendar/', version)
  return (
    <Modal title="Holidays & temporary targets" close={close} wide>
      {saved.error && <ErrorNotice>{saved.error}</ErrorNotice>}
      {saved.data ? (
        <CalendarEditor saved={saved.data} start={start} months={months} close={close} />
      ) : (
        <Loading />
      )}
    </Modal>
  )
}

function CalendarEditor({ saved, start, months, close }: Props & { saved: ApiCalendarState }) {
  const { mutate, notify } = useApp()
  const [initialRevision] = useState(saved.revision)
  const [pauses, setPauses] = useState(saved.pauses)
  const [targets, setTargets] = useState(saved.month_targets)
  const [preview, setPreview] = useState<ApiCalendarPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [startYear, startNumber] = start.split('-').map(Number)
  const nextTargetMonth = Array.from({ length: 241 }, (_, offset) => {
    const month = new Date(startYear, startNumber - 1 + offset, 1)
    return `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, '0')}-01`
  }).find((month) => month <= '2199-12-01' && !targets.some((row) => row.month === month))
  const changePauses = (value: typeof pauses) => {
    setPauses(value)
    setPreview(null)
    setError('')
  }
  const changeTargets = (value: typeof targets) => {
    setTargets(value)
    setPreview(null)
    setError('')
  }
  const submit = async (apply: boolean) => {
    if (busy || (apply && !preview)) return
    setBusy(true)
    setError('')
    try {
      const result = await api<ApiCalendarPreview>('/api/reading-calendar/', 'POST', {
        revision: initialRevision,
        pauses,
        month_targets: targets,
        start_month: start,
        months,
        apply,
        ...(apply ? { preview_token: preview!.preview_token } : {}),
      })
      if (apply) {
        await mutate(async () => null, 'Reading calendar saved')
        close()
      } else setPreview(result)
    } catch (failure) {
      setPreview(null)
      setError((failure as Error).message)
      notify((failure as Error).message, true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form
      className="reading-calendar"
      onSubmit={(event) => {
        event.preventDefault()
        void submit(false)
      }}
    >
      <p className="muted">
        Keep your usual reading rhythm and adjust particular months. Pauses include both dates and reduce the
        target by their share of the month; overlapping days count once. Your saved books, pages, locks and
        reading history stay in place.
      </p>
      <fieldset disabled={busy}>
        <legend>Days away from reading</legend>
        {pauses.map((pause, index) => (
          <div className="panel" key={index}>
            <div className="form-grid">
              <label className="field">
                <span>First day · pause {index + 1}</span>
                <input
                  className="input"
                  type="date"
                  required
                  min="1900-01-01"
                  max="2199-12-31"
                  value={pause.start}
                  onChange={(event) =>
                    changePauses(
                      pauses.map((row, i) => (i === index ? { ...row, start: event.target.value } : row)),
                    )
                  }
                />
              </label>
              <label className="field">
                <span>Last day · pause {index + 1}</span>
                <input
                  className="input"
                  type="date"
                  required
                  min={pause.start || '1900-01-01'}
                  max="2199-12-31"
                  value={pause.end}
                  onChange={(event) =>
                    changePauses(
                      pauses.map((row, i) => (i === index ? { ...row, end: event.target.value } : row)),
                    )
                  }
                />
              </label>
            </div>
            <label className="field">
              <span>Label (optional) · pause {index + 1}</span>
              <input
                className="input"
                maxLength={100}
                value={pause.label}
                placeholder="Holiday, busy week…"
                onChange={(event) =>
                  changePauses(
                    pauses.map((row, i) => (i === index ? { ...row, label: event.target.value } : row)),
                  )
                }
              />
            </label>
            <button
              type="button"
              className="text-button"
              onClick={() => changePauses(pauses.filter((_, i) => i !== index))}
            >
              Remove pause {index + 1}
            </button>
          </div>
        ))}
        <button
          type="button"
          className="button secondary small"
          disabled={pauses.length >= 100}
          onClick={() => changePauses([...pauses, { start, end: start, label: '' }])}
        >
          Add reading pause
        </button>
      </fieldset>
      <fieldset disabled={busy}>
        <legend>Temporary month targets</legend>
        <p className="small-text muted">
          50% means half your usual target; 0% means a month off. Pauses reduce this temporary target further.
          Removing a month restores its usual target.
        </p>
        {targets.map((target, index) => (
          <div className="form-grid" key={index}>
            <label className="field">
              <span>Month · target {index + 1}</span>
              <input
                className="input"
                type="month"
                required
                min="1900-01"
                max="2199-12"
                value={target.month.slice(0, 7)}
                onChange={(event) =>
                  changeTargets(
                    targets.map((row, i) =>
                      i === index ? { ...row, month: `${event.target.value}-01` } : row,
                    ),
                  )
                }
              />
            </label>
            <label className="field">
              <span>Percent of usual target · {index + 1}</span>
              <input
                className="input"
                type="number"
                required
                min={0}
                max={300}
                step={1}
                value={target.percent}
                onChange={(event) =>
                  changeTargets(
                    targets.map((row, i) =>
                      i === index ? { ...row, percent: Number(event.target.value) } : row,
                    ),
                  )
                }
              />
            </label>
            <button
              type="button"
              className="text-button"
              onClick={() => changeTargets(targets.filter((_, i) => i !== index))}
            >
              Remove target {index + 1}
            </button>
          </div>
        ))}
        <button
          type="button"
          className="button secondary small"
          disabled={targets.length >= 240 || !nextTargetMonth}
          onClick={() => {
            if (nextTargetMonth) changeTargets([...targets, { month: nextTargetMonth, percent: 50 }])
          }}
        >
          Add temporary month target
        </button>
      </fieldset>
      {error && <ErrorNotice>{error}</ErrorNotice>}
      <div className="form-actions">
        <button className="button secondary" disabled={busy}>
          {busy ? 'Checking…' : 'Preview effect on plan'}
        </button>
      </div>
      {preview && (
        <section aria-live="polite">
          <h3>Review your calendar</h3>
          <p className="small-text muted">
            These targets take effect only when saved. Existing allocations remain in their current months;
            use Suggest a plan separately if you want to reschedule eligible books.
          </p>
          {preview.months.map((month) => {
            const unit = month.unit === 'baseline_pages' ? 'baseline pages' : 'pages'
            return (
              <div className="panel" key={month.month}>
                <h4>{monthLabel(month.month)}</h4>
                <p>
                  {Math.round(month.before_budget).toLocaleString()} →{' '}
                  <strong>
                    {Math.round(month.after_budget).toLocaleString()} {unit}
                  </strong>
                </p>
                <p className="small-text muted">
                  Usual target {Math.round(month.base_budget).toLocaleString()} · {month.month_percent}% for
                  this month · {month.paused_days} of {month.calendar_days} days paused ·{' '}
                  {Math.round(month.used).toLocaleString()} already allocated
                </p>
                {month.over_capacity > 0 && (
                  <p className="source-limit">
                    {Math.round(month.over_capacity).toLocaleString()} {unit} over the new target. Saved
                    allocations stay in place.
                  </p>
                )}
                {month.unknown_allocations > 0 && (
                  <p className="source-limit">
                    {month.unknown_allocations} allocations have no page count and are outside this
                    calculation.
                  </p>
                )}
                {month.allocations.length > 0 && (
                  <details>
                    <summary>Review {month.allocations.length} unchanged allocations</summary>
                    <ul>
                      {month.allocations.map((item) => (
                        <li key={item.id}>
                          {item.title} · {item.pages ?? 'Unknown'} pages{item.locked ? ' · locked' : ''}
                          {item.has_history ? ' · preserves reading history' : ''}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )
          })}
          <div className="form-actions">
            <button
              type="button"
              className="button primary"
              disabled={busy}
              onClick={() => void submit(true)}
            >
              {busy ? 'Saving…' : 'Save calendar changes'}
            </button>
          </div>
        </section>
      )}
    </form>
  )
}

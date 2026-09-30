import { useEffect, useId, useState } from 'react'
import { api } from './api'
import { useApp } from './context'
import type { User } from './types'

export function paceValue(user: User) {
  return user.reading_target_period === 'month'
    ? user.pages_per_month
    : user.reading_target_period === 'day'
      ? user.pages_per_day
      : user.pages_per_week
}

export function paceLabel(user: User) {
  return user.reading_target_period === 'month'
    ? 'Monthly reading target'
    : user.reading_target_period === 'day'
      ? 'Per reading day'
      : 'Weekly reading target'
}

export function ReadingPaceForm({ user, compact = false }: { user: User; compact?: boolean }) {
  const { setUser, notify } = useApp()
  const [period, setPeriod] = useState(user.reading_target_period)
  const [adjusted, setAdjusted] = useState(user.difficulty_aware_planning)
  const [busy, setBusy] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const formId = useId()
  const [targets, setTargets] = useState({
    day: user.pages_per_day,
    week: user.pages_per_week,
    month: user.pages_per_month,
  })
  const [days, setDays] = useState(user.reading_days_per_week),
    [speed, setSpeed] = useState(user.words_per_minute)
  useEffect(() => {
    setPeriod(user.reading_target_period)
    setAdjusted(user.difficulty_aware_planning)
    setTargets({ day: user.pages_per_day, week: user.pages_per_week, month: user.pages_per_month })
    setDays(user.reading_days_per_week)
    setSpeed(user.words_per_minute)
  }, [
    user.reading_target_period,
    user.difficulty_aware_planning,
    user.pages_per_day,
    user.pages_per_week,
    user.pages_per_month,
    user.reading_days_per_week,
    user.words_per_minute,
  ])
  return (
    <>
      {compact && (
        <div className="rhythm-summary">
          <div>
            <strong>Your reading rhythm</strong>
            <span>
              {paceValue(user).toLocaleString()} {user.difficulty_aware_planning ? 'baseline pages' : 'pages'}{' '}
              / {user.reading_target_period === 'day' ? 'reading day' : user.reading_target_period} ·{' '}
              {user.reading_days_per_week} reading days a week
            </span>
          </div>
          <button
            className="button secondary small"
            aria-expanded={expanded}
            aria-controls={formId}
            disabled={busy}
            onClick={() => {
              if (!expanded) {
                setPeriod(user.reading_target_period)
                setAdjusted(user.difficulty_aware_planning)
                setTargets({
                  day: user.pages_per_day,
                  week: user.pages_per_week,
                  month: user.pages_per_month,
                })
                setDays(user.reading_days_per_week)
                setSpeed(user.words_per_minute)
              }
              setExpanded(!expanded)
            }}
          >
            {expanded ? 'Close' : 'Adjust'}
          </button>
        </div>
      )}
      {(!compact || expanded) && (
        <form
          id={formId}
          className={`reading-pace-form ${compact ? 'rhythm-expanded' : ''}`}
          onSubmit={async (event) => {
            event.preventDefault()
            setBusy(true)
            try {
              const updated = await api<User>('/api/profile/', 'PATCH', {
                reading_target_period: period,
                pages_per_day: targets.day,
                pages_per_week: targets.week,
                pages_per_month: targets.month,
                reading_days_per_week: days,
                difficulty_aware_planning: adjusted,
                words_per_minute: speed,
              })
              setUser(updated)
              notify('Reading rhythm saved')
              setExpanded(false)
            } catch (error) {
              notify((error as Error).message, true)
            } finally {
              setBusy(false)
            }
          }}
        >
          <div className="pace-controls">
            <label className="field">
              <span>Set a target per</span>
              <select
                className="select"
                disabled={busy}
                value={period}
                onChange={(e) => setPeriod(e.target.value as User['reading_target_period'])}
              >
                <option value="week">Week</option>
                <option value="month">Month</option>
                <option value="day">Reading day</option>
              </select>
            </label>
            <label className="field">
              <span>
                {adjusted ? 'Baseline pages' : 'Pages'} / {period === 'day' ? 'reading day' : period}
              </span>
              <input
                className="input"
                disabled={busy}
                type="number"
                min={1}
                max={period === 'month' ? 62000 : period === 'week' ? 14000 : 2000}
                value={targets[period] || ''}
                required
                onChange={(e) => setTargets({ ...targets, [period]: Number(e.target.value) })}
              />
            </label>
            <label className="field">
              <span>Reading days / week</span>
              <select
                className="select"
                name="days"
                disabled={busy}
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              >
                {[1, 2, 3, 4, 5, 6, 7].map((n) => (
                  <option value={n} key={n}>
                    {n} {n === 1 ? 'day' : 'days'}
                  </option>
                ))}
              </select>
            </label>
            <button className="button secondary" disabled={busy}>
              {busy ? 'Saving…' : 'Save rhythm'}
            </button>
          </div>
          <label className="field">
            <span>Your reading pace for time estimates</span>
            <select
              className="select"
              name="speed"
              disabled={busy}
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
            >
              <option value={180}>Slower / deliberate</option>
              <option value={250}>Typical starting estimate</option>
              <option value={320}>Faster</option>
              {![180, 250, 320].includes(user.words_per_minute) && (
                <option value={user.words_per_minute}>
                  Keep my custom pace ({user.words_per_minute} words/min)
                </option>
              )}
            </select>
            <small>
              No timer needed. These are approximate starting speeds; each book’s effort adjustment is applied
              separately. Changing speed affects hours, not your page target.
            </small>
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              disabled={busy}
              checked={adjusted}
              onChange={(e) => setAdjusted(e.target.checked)}
            />
            <span>
              Allow more time for demanding books
              <small>
                One baseline page means a page of lighter reading. A harder page uses more of your budget;
                page progress stays unchanged.
              </small>
            </span>
          </label>
          <p className="small-text muted">
            Read on whichever days suit you. Weekly and monthly targets can be spread flexibly; reading days
            help estimate a comfortable session.
          </p>
        </form>
      )}
    </>
  )
}

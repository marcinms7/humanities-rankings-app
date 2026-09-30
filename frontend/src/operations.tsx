import { useEffect, useState } from 'react'
import { Activity, RefreshCw } from 'lucide-react'
import { useResource } from './api'
import { queryCache } from './queryCache'
import { Empty, ErrorNotice, label, Loading, PageHeader } from './components'
import { useApp } from './context'
import './operations.css'

type OperationsData = {
  checked_at: string
  sampled_at: number
  backup: {
    latest_name: string | null
    completed_at: number | null
    age_hours: number | null
    completed_snapshots: number
    stored_bytes: number
    media_bytes: number
    last_attempt_status: string
    last_attempt_at: string | null
    copy: {
      configured: boolean | null
      status: string | null
      finished_at: string | null
      separate_device: boolean | null
    }
    schedule_installed: boolean
    schedule_prepared: boolean
  }
  disk: { total_bytes: number; free_bytes: number; used_percent: number }
  workers: {
    name: string
    status: string
    updated_at: number | null
    heartbeat_at: number | null
    heartbeat_age_seconds: number | null
    heartbeat_supported: boolean
    process_present: boolean | null
    batches: number
    current_provider?: string
    added_this_run?: number
    missing_covers?: number
    missing_portraits?: number
    retry_at: number | null
  }[]
  providers: {
    name: string
    cooldown_until: number | null
    cooldown_active: boolean
    state_unreadable: boolean
  }[]
  queues: { name: string; states: Record<string, number>; unavailable?: boolean }[]
  requests: {
    scope: string
    started_at: number
    sample_count: number
    sample_limit: number
    routes: {
      method: string
      route: string
      requests: number
      errors: number
      duration_ms_mean: number
      duration_ms_p95: number
      sql_count_mean: number
      sql_ms_mean: number
      response_bytes_mean: number
      unknown_response_sizes: number
    }[]
    slow_or_failed: {
      at: number
      request_id: string
      route: string
      method: string
      status: number
      duration_ms: number
      sql_count: number
      sql_ms: number
      response_bytes: number | null
    }[]
  }
}
const bytes = (value: number) =>
  value < 1024 * 1024
    ? `${(value / 1024).toFixed(1)} KB`
    : value < 1024 ** 3
      ? `${(value / 1024 ** 2).toFixed(1)} MB`
      : `${(value / 1024 ** 3).toFixed(2)} GB`
const when = (value: number | string | null) =>
  value ? new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString() : 'Not recorded'

export function Operations() {
  const { user, version } = useApp()
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setRefresh((value) => value + 1), 30000)
    return () => clearInterval(timer)
  }, [])
  const resource = useResource<OperationsData>(user?.is_staff ? '/api/operations/' : null, version + refresh)
  if (!user?.is_staff) return <Empty title="Operations">This workspace is available to staff.</Empty>
  const data = resource.data
  return (
    <>
      <PageHeader
        eyebrow="Application health"
        title="Operations."
        actions={
          <button
            className="button secondary"
            onClick={() => {
              queryCache.invalidate(['operations'])
              setRefresh((value) => value + 1)
            }}
            disabled={resource.loading}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        }
      >
        Check backup coverage, storage, enrichment queues and recent request costs. Operational summaries omit
        private notes, request bodies, credentials and raw SQL.
      </PageHeader>
      {resource.error && <ErrorNotice>{resource.error}</ErrorNotice>}
      {!data ? (
        resource.loading && <Loading />
      ) : (
        <>
          <p className="small-text muted">
            Updated {when(data.checked_at)}. Refreshes every 30 seconds; storage measurements are cached for
            up to one minute.
          </p>
          <div className="operations-stats">
            <section className="panel panel-body">
              <h2>Latest backup</h2>
              <strong className="operations-value">
                {data.backup.age_hours == null
                  ? 'None recorded'
                  : data.backup.age_hours < 1
                    ? 'Under 1 hour old'
                    : `${data.backup.age_hours.toFixed(1)} hours old`}
              </strong>
              <p>{when(data.backup.completed_at)}</p>
              {(data.backup.age_hours == null || data.backup.age_hours > 36) && (
                <p className="notice">A new backup is due.</p>
              )}
              <p className="small-text">
                {data.backup.latest_name || 'No completed local snapshot'} · {data.backup.completed_snapshots}{' '}
                retained snapshots
              </p>
              <p className="small-text">Latest attempt: {label(data.backup.last_attempt_status)}</p>
            </section>
            <section className="panel panel-body">
              <h2>Storage</h2>
              <strong className="operations-value">{bytes(data.disk.free_bytes)} free</strong>
              <p>
                {data.disk.used_percent}% of {bytes(data.disk.total_bytes)} used
              </p>
              <dl>
                <dt>Backup store, including legacy snapshots</dt>
                <dd>{bytes(data.backup.stored_bytes)}</dd>
                <dt>Original media</dt>
                <dd>{bytes(data.backup.media_bytes)}</dd>
              </dl>
              {data.disk.used_percent > 90 && (
                <p className="notice">
                  Storage is nearly full. Review the retention proposal before removing anything.
                </p>
              )}
            </section>
            <section className="panel panel-body">
              <h2>Backup coverage</h2>
              <p>
                <strong>Daily schedule:</strong>{' '}
                {data.backup.schedule_installed
                  ? 'LaunchAgent file installed'
                  : data.backup.schedule_prepared
                    ? 'Prepared; installation still needed'
                    : 'Not installed'}
              </p>
              <p className="small-text muted">
                An installed file does not prove a scheduler ran; check backup age and latest attempt above.
                Local launch remains an additional backup trigger.
              </p>
              <p>
                <strong>Additional copy:</strong>{' '}
                {data.backup.copy.configured
                  ? label(data.backup.copy.status || 'not_recorded')
                  : 'Destination not configured'}
              </p>
              {data.backup.copy.finished_at && (
                <p className="small-text">Last copied {when(data.backup.copy.finished_at)}</p>
              )}
              {data.backup.copy.separate_device === false && (
                <p className="notice">
                  The configured copy is on the same detected filesystem. A separate disk or remote copy is
                  still needed for disk-loss protection.
                </p>
              )}
              <p className="small-text muted">
                Retention is a dry-run report. Manual snapshots and shared media objects are protected from
                automatic deletion.
              </p>
            </section>
          </div>
          <section className="panel">
            <div className="panel-header">
              <h2>
                <Activity size={18} /> Enrichment workers
              </h2>
            </div>
            <div className="panel-body operations-workers">
              {data.workers.map((worker) => (
                <article key={worker.name}>
                  <h3>{label(worker.name)}</h3>
                  <p>
                    <span className="pill muted">{label(worker.status)}</span>
                    {worker.current_provider && ` · ${worker.current_provider}`}
                  </p>
                  <p>
                    {worker.batches} batches
                    {worker.added_this_run != null && ` · ${worker.added_this_run} images added this run`}
                  </p>
                  <p className="small-text">Last saved status: {when(worker.updated_at)}</p>
                  <p className="small-text">
                    {worker.heartbeat_supported
                      ? `Heartbeat: ${worker.heartbeat_age_seconds}s ago`
                      : 'Heartbeat unavailable for this run; older workers gain it at their next start.'}
                  </p>
                  {worker.process_present === false &&
                    ['running', 'waiting_for_provider', 'backing_up'].includes(worker.status) && (
                      <p className="notice">
                        The recorded process is no longer present; inspect the worker log before resuming.
                      </p>
                    )}
                  {worker.heartbeat_supported &&
                    (worker.heartbeat_age_seconds || 0) > 90 &&
                    ['running', 'backing_up'].includes(worker.status) && (
                      <p className="notice">Heartbeat is overdue. The saved status may be stale.</p>
                    )}
                  {worker.retry_at && <p>Next retry: {when(worker.retry_at)}</p>}
                  {worker.missing_covers != null && (
                    <p className="small-text">
                      Last backlog snapshot: {worker.missing_covers} covers ·{' '}
                      {worker.missing_portraits ?? 'unknown'} portraits. New metadata can change these totals.
                    </p>
                  )}
                </article>
              ))}
            </div>
          </section>
          <div className="two-column">
            <section className="panel">
              <div className="panel-header">
                <h2>Provider cooldowns</h2>
              </div>
              <div className="panel-body">
                {data.providers.map((provider) => (
                  <p key={provider.name}>
                    <strong>{provider.name}</strong>
                    <br />
                    {provider.state_unreadable
                      ? 'Saved cooldown is unreadable; provider requests remain paused.'
                      : provider.cooldown_active
                        ? `Waiting until ${when(provider.cooldown_until)}`
                        : 'No active saved cooldown'}
                  </p>
                ))}
              </div>
            </section>
            <section className="panel">
              <div className="panel-header">
                <h2>Durable queues</h2>
              </div>
              <div className="panel-body">
                {data.queues.length ? (
                  data.queues.map((queue) => (
                    <div key={queue.name}>
                      <h3>{queue.name}</h3>
                      <p className="small-text">
                        {queue.unavailable
                          ? 'Queue index temporarily unavailable'
                          : Object.entries(queue.states)
                              .map(([state, count]) => `${label(state)}: ${count.toLocaleString()}`)
                              .join(' · ')}
                      </p>
                    </div>
                  ))
                ) : (
                  <p>No durable queue indexes exist yet.</p>
                )}
              </div>
            </section>
          </div>
          <section className="panel">
            <div className="panel-header">
              <h2>Request performance</h2>
              <span className="pill muted">
                {data.requests.sample_count} / {data.requests.sample_limit} samples
              </span>
            </div>
            <div className="panel-body">
              <p className="small-text muted">
                {data.requests.scope} SQL times measure execution; byte averages use the response’s known
                size.
              </p>
              {data.requests.routes.length ? (
                <div className="operations-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Route</th>
                        <th>Requests</th>
                        <th>Mean / p95</th>
                        <th>Queries / SQL time</th>
                        <th>Response</th>
                        <th>Errors</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.requests.routes.map((row) => (
                        <tr key={`${row.method}:${row.route}`}>
                          <td>
                            <code>
                              {row.method} {row.route}
                            </code>
                          </td>
                          <td>{row.requests}</td>
                          <td>
                            {row.duration_ms_mean} / {row.duration_ms_p95} ms
                          </td>
                          <td>
                            {row.sql_count_mean} / {row.sql_ms_mean} ms
                          </td>
                          <td>
                            {bytes(row.response_bytes_mean)}
                            {row.unknown_response_sizes > 0 && ' (some unknown)'}
                          </td>
                          <td>{row.errors}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p>Open an app screen to collect its request timing.</p>
              )}
              <details>
                <summary>Recent slow or failed requests</summary>
                {data.requests.slow_or_failed.length ? (
                  data.requests.slow_or_failed.map((row) => (
                    <p className="small-text" key={row.request_id}>
                      {when(row.at)} · {row.method} {row.route} · HTTP {row.status} · {row.duration_ms} ms
                      <br />
                      Request ID: <code>{row.request_id}</code>
                    </p>
                  ))
                ) : (
                  <p>No slow or failed requests in this process’s current sample window.</p>
                )}
              </details>
            </div>
          </section>
        </>
      )}
    </>
  )
}

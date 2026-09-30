import { useEffect, useMemo, useReducer, useRef, useState, useSyncExternalStore } from 'react'
import { useApp } from './context'
import {
  draftGeneration,
  subscribeDraftAccount,
  clearDrafts,
  compatibleDraft,
  draftLease,
  draftsEnabled,
  readDrafts,
  registerDraftFlush,
  removeDraft,
  setDraftsEnabled,
  writeDraft,
  type DraftRecord,
} from './draftStore'

function storageError(error: unknown) {
  return error instanceof Error && !['QuotaExceededError', 'SecurityError'].includes(error.name)
    ? error.message
    : 'Device recovery is unavailable in this browser. Keep writing and save to your account before leaving.'
}
type Recovery<T> = {
  candidates: DraftRecord<T>[]
  error: string
  savedAt: string
  enabled: boolean
  restoredVersion: string | null
  restore: (row: DraftRecord<T>) => void
  discard: () => void
  saved: () => void
  checkpoint: (value: T) => void
}
export function useDraftRecovery<T>({
  scope,
  label,
  value,
  dirty,
  baseVersion = '',
  ready = true,
  restore,
}: {
  scope: string
  label: string
  value: T
  dirty: boolean
  baseVersion?: string
  ready?: boolean
  restore: (value: T, baseVersion: string) => void
}): Recovery<T> {
  const { user } = useApp()
  const userId = user?.id
  const serialized = JSON.stringify(value)
  const accountGeneration = useSyncExternalStore(subscribeDraftAccount, draftGeneration, draftGeneration)
  const [, refresh] = useReducer((n) => n + 1, 0)
  const current = useRef({ value, dirty, baseVersion, restore, ready })
  current.current = { value, dirty, baseVersion, restore, ready }
  const holder = useMemo(() => {
    const state = {
      candidates: [] as DraftRecord<T>[],
      error: '',
      savedAt: '',
      enabled: true,
      own: null as DraftRecord<T> | null,
      restored: null as DraftRecord<T> | null,
      slot: crypto.randomUUID(),
      epoch: accountGeneration,
      restoredVersion: null as string | null,
      active: userId ? draftLease(userId) : () => false,
      pending: null as { value: T; baseVersion: string } | null,
      dismissed: false,
      editBase: null as string | null,
    }
    if (userId && scope && state.active()) {
      try {
        state.enabled = draftsEnabled(localStorage, userId)
        if (state.enabled)
          state.candidates = readDrafts(localStorage, userId, scope).filter((row) =>
            compatibleDraft(row.value, current.current.value),
          ) as DraftRecord<T>[]
        if (current.current.dirty) {
          const matching = state.candidates.find(
            (row) => JSON.stringify(row.value) === JSON.stringify(current.current.value),
          )
          if (matching) {
            state.restored = matching
            state.editBase = matching.baseVersion
            state.candidates = state.candidates.filter((row) => row.key !== matching.key)
          }
        }
      } catch (error) {
        state.error = storageError(error)
      }
    }
    return state
  }, [userId, scope, accountGeneration])
  const flush = useMemo(
    () => () => {
      if (!userId || !scope || !holder.active() || !holder.pending) return
      try {
        const row = writeDraft(
          localStorage,
          userId,
          scope,
          holder.slot,
          holder.pending.value,
          holder.pending.baseVersion,
          label,
          holder.active,
        )
        if (row) {
          holder.own = row
          holder.savedAt = row.savedAt
          holder.error = ''
          holder.pending = null
          if (holder.restored) {
            removeDraft(localStorage, holder.restored)
            holder.restored = null
          }
        }
      } catch (error) {
        holder.error = storageError(error)
      }
    },
    [holder, userId, scope, label],
  )
  useEffect(() => {
    if (!ready || !scope || !dirty || holder.dismissed || !holder.enabled) {
      holder.pending = null
      return
    }
    if (holder.editBase === null) holder.editBase = baseVersion
    holder.pending = { value: JSON.parse(serialized) as T, baseVersion: holder.editBase }
    const timer = setTimeout(() => {
      flush()
      refresh()
    }, 350)
    return () => clearTimeout(timer)
  }, [serialized, dirty, ready, baseVersion, holder, scope, flush])
  useEffect(() => {
    const finish = () => {
      flush()
      refresh()
    }
    const hidden = () => {
      if (document.visibilityState === 'hidden') finish()
    }
    const settings = () => {
      if (!userId || !holder.active()) return
      try {
        const wasEnabled = holder.enabled
        holder.enabled = draftsEnabled(localStorage, userId)
        holder.candidates = holder.candidates.filter((row) => localStorage.getItem(row.key))
        if (!holder.enabled || (holder.own && !localStorage.getItem(holder.own.key))) {
          holder.pending = null
          holder.own = null
          holder.savedAt = ''
        }
        if (holder.restored && !localStorage.getItem(holder.restored.key)) holder.restored = null
        if (
          !wasEnabled &&
          holder.enabled &&
          current.current.ready &&
          current.current.dirty &&
          !holder.dismissed
        ) {
          holder.pending = {
            value: current.current.value,
            baseVersion: holder.editBase ?? current.current.baseVersion,
          }
          flush()
        }
        refresh()
      } catch (error) {
        holder.error = storageError(error)
        refresh()
      }
    }
    window.addEventListener('pagehide', finish)
    window.addEventListener('beforeunload', finish)
    document.addEventListener('visibilitychange', hidden)
    window.addEventListener('marginalia-draft-settings', settings)
    window.addEventListener('storage', settings)
    const unregister = registerDraftFlush(flush)
    return () => {
      flush()
      unregister()
      window.removeEventListener('pagehide', finish)
      window.removeEventListener('beforeunload', finish)
      document.removeEventListener('visibilitychange', hidden)
      window.removeEventListener('marginalia-draft-settings', settings)
      window.removeEventListener('storage', settings)
    }
  }, [flush, holder, userId])
  const saved = () => {
    if (!holder.active()) return
    holder.pending = null
    holder.editBase = null
    holder.dismissed = true // Prevent an in-flight render from recreating a successfully saved copy.
    try {
      if (holder.own) removeDraft(localStorage, holder.own)
      if (holder.restored) removeDraft(localStorage, holder.restored)
      holder.own = null
      holder.restored = null
      holder.restoredVersion = null
      holder.savedAt = ''
      holder.error = ''
    } catch (error) {
      holder.error = storageError(error)
    }
    refresh()
  }
  // A later edit in the same mounted editor begins a fresh recovery cycle.
  useEffect(() => {
    if (!dirty) holder.dismissed = false
  }, [dirty, holder])
  return {
    candidates: ready ? holder.candidates : [],
    error: holder.error,
    savedAt: holder.savedAt,
    enabled: holder.enabled,
    restoredVersion: holder.restoredVersion,
    saved,
    checkpoint: (next) => {
      holder.dismissed = false
      holder.pending = { value: next, baseVersion: holder.editBase ?? current.current.baseVersion }
      flush()
      refresh()
    },
    restore: (row) => {
      if (!holder.active() || !ready) return
      if (
        current.current.dirty &&
        !window.confirm('Replace the text in this editor with this recovered draft?')
      )
        return
      holder.restored = row
      holder.restoredVersion = row.baseVersion
      holder.editBase = row.baseVersion
      holder.candidates = holder.candidates.filter((candidate) => candidate.key !== row.key)
      // Other copies stay safely stored; they can be reviewed on the next opening.
      holder.candidates = []
      holder.dismissed = false
      current.current.restore(row.value, row.baseVersion)
      refresh()
    },
    discard: () => {
      if (!holder.active()) return
      try {
        holder.candidates.forEach((row) => removeDraft(localStorage, row))
        holder.candidates = []
        holder.error = ''
        flush()
      } catch (error) {
        holder.error = storageError(error)
      }
      refresh()
    },
  }
}
function draftPreview(value: unknown): string {
  if (typeof value === 'string') return value
  if (!value || typeof value !== 'object') return String(value ?? '')
  if (Array.isArray(value)) return value.map(draftPreview).join(', ')
  const internal = new Set([
    'noteId',
    'essayId',
    'essayRevision',
    'promptId',
    'sessionModule',
    'work',
    'module',
    'commonplaces',
    'related',
  ])
  return Object.entries(value)
    .filter(([key, field]) => !internal.has(key) && field !== '')
    .map(([key, field]) => {
      const text = draftPreview(field)
      if (key === 'essay') return text
      return `${key.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/_/g, ' ')}\n${text}`
    })
    .join('\n\n')
}
export function DraftRecoveryNotice<T>({
  recovery,
  baseVersion = '',
  busy = false,
}: {
  recovery: Recovery<T>
  baseVersion?: string
  busy?: boolean
}) {
  return (
    <div className="draft-recovery" aria-label="Unsaved draft recovery">
      {recovery.restoredVersion !== null && recovery.restoredVersion !== baseVersion && (
        <p className="notice" role="status">
          This recovered draft was written against an earlier saved record. Review the saved version before
          saving; normal conflict checks still apply.
        </p>
      )}
      {recovery.error && (
        <p className="notice" role="alert">
          {recovery.error}
        </p>
      )}
      {recovery.candidates.length > 0 ? (
        <div className="notice">
          <strong>Unsaved writing is available on this device.</strong>
          <p>
            Review a recovery copy before restoring it. Your saved account record stays unchanged until you
            save.
          </p>
          {recovery.candidates.map((row) => (
            <details key={row.key}>
              <summary>
                {row.label} · {new Date(row.savedAt).toLocaleString()}
              </summary>
              {row.baseVersion !== baseVersion && (
                <p role="status">
                  The saved record has changed since this draft began. Compare the current saved text before
                  saving a recovered copy.
                </p>
              )}
              <pre
                style={{
                  whiteSpace: 'pre-wrap',
                  overflowWrap: 'anywhere',
                  maxHeight: '14rem',
                  overflow: 'auto',
                }}
              >
                {draftPreview(row.value)}
              </pre>
              <button
                type="button"
                className="button secondary small"
                disabled={busy}
                onClick={() => recovery.restore(row)}
              >
                Restore this draft
              </button>
            </details>
          ))}
          <button type="button" className="text-button" disabled={busy} onClick={recovery.discard}>
            Discard listed recovery copies; keep this editor
          </button>
        </div>
      ) : (
        <p className="small-text muted" role="status">
          {!recovery.enabled
            ? 'Device draft recovery is off. Save to your account before leaving.'
            : recovery.savedAt
              ? 'Unsaved draft copied to this device. Save to your account when ready.'
              : 'Unsaved writing can be recovered on this device. Manage or clear copies in Profile.'}
        </p>
      )}
    </div>
  )
}
export function DraftRecoverySettings() {
  const { user } = useApp()
  const [enabled, setEnabled] = useState(true),
    [copies, setCopies] = useState<DraftRecord[]>([]),
    [error, setError] = useState('')
  useEffect(() => {
    if (!user) return
    const refresh = () => {
      try {
        setEnabled(draftsEnabled(localStorage, user.id))
        setCopies(readDrafts(localStorage, user.id))
      } catch (e) {
        setError(storageError(e))
      }
    }
    refresh()
    window.addEventListener('storage', refresh)
    return () => window.removeEventListener('storage', refresh)
  }, [user])
  if (!user) return null
  const update = (next: boolean, clearOnly = false) => {
    try {
      if (clearOnly) clearDrafts(localStorage, user.id)
      else setDraftsEnabled(localStorage, user.id, next)
      setEnabled(next)
      setCopies(readDrafts(localStorage, user.id))
      setError('')
      window.dispatchEvent(new Event('marginalia-draft-settings'))
    } catch (e) {
      setError(storageError(e))
    }
  }
  return (
    <section aria-label="Device draft recovery">
      <h3>Unsaved draft recovery</h3>
      <p className="small-text muted">
        Recovery copies stay in this browser for this account, including after sign-out. They are separate
        from saved records and exports; they do not sync between devices. Shared-device users can switch
        recovery off and clear their copies.
      </p>
      {error && (
        <p className="notice" role="alert">
          {error}
        </p>
      )}
      <label className="checkbox">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => {
            if (
              !e.target.checked &&
              !window.confirm(
                'Turn off draft recovery and clear this account’s device copies? Saved account records stay intact.',
              )
            )
              return
            update(e.target.checked)
          }}
        />{' '}
        Keep recovery copies of unsaved writing on this device
      </label>
      <p className="small-text muted">
        {copies.length} recovery {copies.length === 1 ? 'copy' : 'copies'} · bounded storage; existing copies
        are never silently evicted.
      </p>
      {copies.length > 0 && (
        <details>
          <summary>Review device copies</summary>
          <p className="small-text muted">
            Open the corresponding writing editor to restore a copy. You can also select and copy its text
            here.
          </p>
          {copies.map((row) => (
            <details key={row.key}>
              <summary>
                {row.label} · {new Date(row.savedAt).toLocaleString()}
              </summary>
              <pre
                style={{
                  whiteSpace: 'pre-wrap',
                  overflowWrap: 'anywhere',
                  maxHeight: '14rem',
                  overflow: 'auto',
                }}
              >
                {draftPreview(row.value)}
              </pre>
              <button
                type="button"
                className="text-button"
                onClick={() => {
                  try {
                    removeDraft(localStorage, row)
                    setCopies(readDrafts(localStorage, user.id))
                    window.dispatchEvent(new Event('marginalia-draft-settings'))
                  } catch (e) {
                    setError(storageError(e))
                  }
                }}
              >
                Discard this device copy
              </button>
            </details>
          ))}
        </details>
      )}
      <button
        type="button"
        className="button secondary small"
        onClick={() => {
          if (
            window.confirm(
              'Clear this account’s recovery copies on this device? Saved account records stay intact.',
            )
          )
            update(enabled, true)
        }}
      >
        Clear device recovery copies
      </button>
    </section>
  )
}

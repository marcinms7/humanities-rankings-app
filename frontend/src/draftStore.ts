/** Device-only recovery copies. Saved account records remain authoritative. */
export type DraftRecord<T = unknown> = {
  version: 1
  account: number
  scope: string
  label: string
  savedAt: string
  baseVersion: string
  value: T
  key: string
}
export type DraftStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem' | 'key' | 'length'>
const PREFIX = 'marginalia:draft:v1:'
const MAX_RECORD = 200_000
const MAX_TOTAL = 900_000
const MAX_COUNT = 40
let account: number | null = null
let generation = 0
const beforeAccountChange = new Set<() => void>()
const accountListeners = new Set<() => void>()
export const draftGeneration = () => generation
export function subscribeDraftAccount(listener: () => void) {
  accountListeners.add(listener)
  return () => {
    accountListeners.delete(listener)
  }
}
export function setDraftAccount(next: number | null, force = false) {
  if (next === account && !force) return
  beforeAccountChange.forEach((flush) => flush())
  account = next
  generation += 1
  accountListeners.forEach((listener) => listener())
}
export function draftLease(user: number) {
  const captured = generation
  return () => account === user && captured === generation
}
export function registerDraftFlush(flush: () => void) {
  beforeAccountChange.add(flush)
  return () => {
    beforeAccountChange.delete(flush)
  }
}
function prefix(user: number) {
  return `${PREFIX}${user}:`
}
function preference(user: number) {
  return `marginalia:draft-preference:v1:${user}`
}
export function draftsEnabled(storage: DraftStorage, user: number) {
  return storage.getItem(preference(user)) !== 'off'
}
export function readDrafts(storage: DraftStorage, user: number, scope?: string): DraftRecord[] {
  const rows: DraftRecord[] = []
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i)
    if (!key?.startsWith(prefix(user))) continue
    const raw = storage.getItem(key)
    if (!raw || raw.length > MAX_RECORD) continue
    try {
      const row = JSON.parse(raw) as DraftRecord
      if (
        row.version === 1 &&
        row.account === user &&
        row.key === key &&
        typeof row.scope === 'string' &&
        typeof row.label === 'string' &&
        typeof row.baseVersion === 'string' &&
        typeof row.savedAt === 'string' &&
        Number.isFinite(Date.parse(row.savedAt)) &&
        'value' in row &&
        (scope === undefined || row.scope === scope)
      )
        rows.push(row)
    } catch {
      /* An invalid copy is never applied to an editor. */
    }
  }
  return rows.sort((a, b) => b.savedAt.localeCompare(a.savedAt))
}
export function writeDraft<T>(
  storage: DraftStorage,
  user: number,
  scope: string,
  slot: string,
  value: T,
  baseVersion: string,
  label: string,
  active: () => boolean,
): DraftRecord<T> | null {
  if (!active() || !draftsEnabled(storage, user)) return null
  const key = `${prefix(user)}${encodeURIComponent(scope)}:${slot}`
  const row: DraftRecord<T> = {
    version: 1,
    account: user,
    scope,
    label,
    baseVersion,
    value,
    key,
    savedAt: new Date().toISOString(),
  }
  const raw = JSON.stringify(row)
  if (raw.length > MAX_RECORD)
    throw new Error(
      'This draft is too large for device recovery. Save it to your account or copy it elsewhere.',
    )
  let total = raw.length,
    count = 1
  for (let i = 0; i < storage.length; i++) {
    const other = storage.key(i)
    if (other?.startsWith(PREFIX) && other !== key) {
      total += storage.getItem(other)?.length || 0
      count += 1
    }
  }
  if (count > MAX_COUNT || total > MAX_TOTAL)
    throw new Error(
      'Device recovery storage is full. Save your work, then clear old recovery copies in Profile.',
    )
  storage.setItem(key, raw)
  return row
}
export function removeDraft(storage: DraftStorage, row: DraftRecord) {
  // A different tab may have updated this exact copy since it was reviewed.
  const raw = storage.getItem(row.key)
  if (raw === JSON.stringify(row)) storage.removeItem(row.key)
}
export function clearDrafts(storage: DraftStorage, user: number) {
  const keys: string[] = []
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i)
    if (key?.startsWith(prefix(user))) keys.push(key)
  }
  keys.forEach((key) => storage.removeItem(key))
}
export function setDraftsEnabled(storage: DraftStorage, user: number, enabled: boolean) {
  storage.setItem(preference(user), enabled ? 'on' : 'off')
  if (!enabled) clearDrafts(storage, user)
}
export function compatibleDraft(value: unknown, sample: unknown): boolean {
  if (sample === null) return value === null
  if (Array.isArray(sample)) return Array.isArray(value)
  if (typeof sample === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false
    const entries = Object.entries(sample as object)
    return entries.length
      ? entries.every(([key, field]) => compatibleDraft((value as Record<string, unknown>)[key], field))
      : Object.values(value).every((field) => typeof field === 'string')
  }
  return typeof value === typeof sample
}

/** Equality marker, not a security checksum; avoids storing another copy of saved prose. */
export function draftBaseVersion(value: unknown): string {
  const text = JSON.stringify(value)
  let hash = 2166136261
  for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619)
  return `${text.length}:${(hash >>> 0).toString(16)}`
}

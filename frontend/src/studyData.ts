import type { ApiStudyChange } from './generated/apiContracts'
export type StudyChange = ApiStudyChange

/** The backend sends only changed paths; untouched drafts and records stay put. */
export function applyStudyChanges<T extends object>(state: T, changes: StudyChange[]): T {
  const result = structuredClone(state)
  for (const change of changes) {
    if (
      !change.path.length ||
      change.path.some((key) => ['__proto__', 'constructor', 'prototype'].includes(key))
    ) {
      throw new Error('The study response contains an invalid record path. Reload before saving again.')
    }
    let target = result as Record<string, unknown>
    for (const [index, key] of change.path.slice(0, -1).entries()) {
      if (target[key] === null || typeof target[key] !== 'object')
        target[key] = /^\d+$/.test(change.path[index + 1]) ? [] : {}
      target = target[key] as Record<string, unknown>
    }
    const key = change.path.at(-1)!
    if (change.remove) delete target[key]
    else target[key] = change.value
  }
  // Session pages use stable numeric positions; a delta can introduce the
  // whole journal object when saving its first session.
  const learning = (result as { learning?: { sessions?: unknown } }).learning
  if (learning?.sessions && typeof learning.sessions === 'object' && !Array.isArray(learning.sessions)) {
    const sessions: unknown[] = []
    for (const [key, value] of Object.entries(learning.sessions)) {
      if (!/^\d+$/.test(key) || Number(key) >= 2000) throw new Error('Invalid saved study session position.')
      sessions[Number(key)] = value
    }
    learning.sessions = sessions
  }
  return result
}

/** Summary projections refresh progress without erasing already loaded notes. */
export function mergeStudySummary<T extends object>(current: T, summary: T): T {
  const merged = structuredClone(current) as Record<string, unknown>
  for (const [key, value] of Object.entries(summary)) {
    if (['__proto__', 'constructor', 'prototype'].includes(key))
      throw new Error('Invalid saved study summary key.')
    const prior = merged[key]
    merged[key] =
      prior &&
      value &&
      typeof prior === 'object' &&
      typeof value === 'object' &&
      !Array.isArray(prior) &&
      !Array.isArray(value)
        ? mergeStudySummary(prior, value)
        : structuredClone(value)
  }
  return merged as T
}

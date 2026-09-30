/** Retain retry keys in account memory only, never retry writes automatically. */
import { queryCache } from './queryCache.ts'

const pending = new Map<string, { key: string; at: number; generation: number }>()
queryCache.subscribe((event) => {
  if (event.accountChanged) pending.clear()
})

export function mutationRequest(path: string, method: string, data: unknown) {
  if (
    ['GET', 'HEAD', 'OPTIONS'].includes(method) ||
    path.startsWith('/api/session/') ||
    data instanceof FormData
  )
    return null
  const fingerprint = JSON.stringify([path, method, data ?? null])
  const generation = queryCache.generation
  const now = Date.now()
  for (const [key, request] of pending) {
    if (request.at < now - 10 * 60_000 || request.generation !== generation) pending.delete(key)
  }
  const prior = pending.get(fingerprint)
  if (prior) return { fingerprint, ...prior }
  const request = { key: crypto.randomUUID(), at: now, generation }
  pending.set(fingerprint, request)
  while (pending.size > 25) pending.delete(pending.keys().next().value!)
  return { fingerprint, ...request }
}

export function finishMutation(request: ReturnType<typeof mutationRequest>, status: number) {
  // Unknown network/server outcomes keep their key so an explicit retry can
  // replay the committed response. Corrected 4xx requests get a fresh key.
  if (request && ((status >= 200 && status < 300) || (status >= 400 && status < 500))) {
    const current = pending.get(request.fingerprint)
    if (current?.key === request.key && current.generation === request.generation)
      pending.delete(request.fingerprint)
  }
}

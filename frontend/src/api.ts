import { setDraftAccount } from './draftStore'
import { useEffect, useState } from 'react'
import { abortError, canonicalQueryKey, queryCache } from './queryCache'
import { cacheLifetime, mutationTags, queryTags } from './queryPolicies'
import { mutationRequest, finishMutation } from './mutationRequests'
import { responseContractIssue } from './responseValidation'

function errorText(data: unknown): string {
  if (typeof data === 'string') return data
  if (data && typeof data === 'object' && 'code' in data && data.code === 'edit_conflict' && 'detail' in data)
    return typeof data.detail === 'string'
      ? data.detail
      : 'This record changed. Review the saved values before retrying.'
  if (Array.isArray(data)) return data.map(errorText).join(' ')
  if (data && typeof data === 'object')
    return Object.entries(data)
      .map(
        ([key, value]) =>
          `${key === 'detail' || key === 'non_field_errors' ? '' : `${key}: `}${errorText(value)}`,
      )
      .join(' ')
  return 'The request could not be completed.'
}

export class APIError extends Error {
  readonly status: number
  readonly requestId: string | null
  readonly details: unknown

  constructor(message: string, status = 0, requestId: string | null = null, details?: unknown) {
    super(requestId && status >= 500 ? `${message} Request reference: ${requestId}.` : message)
    this.name = 'APIError'
    this.status = status
    this.requestId = requestId
    this.details = details
  }
}

export function setQueryAccount(userId: number | null, force = false): void {
  setDraftAccount(userId, force)
  queryCache.setAccount(userId == null ? 'anonymous' : `user:${userId}`, force)
}

export function installQueryLifecycle(): () => void {
  const refresh = () => {
    if (document.visibilityState !== 'hidden') queryCache.expire()
  }
  window.addEventListener('focus', refresh)
  document.addEventListener('visibilitychange', refresh)
  return () => {
    window.removeEventListener('focus', refresh)
    document.removeEventListener('visibilitychange', refresh)
  }
}

async function transport<T>(path: string, method: string, data?: unknown, signal?: AbortSignal): Promise<T> {
  const url = new URL(path, window.location.origin)
  if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/'))
    throw new APIError('Choose an application API address.')
  const headers: Record<string, string> = { Accept: 'application/json' }
  const mutation = mutationRequest(`${url.pathname}${url.search}`, method, data)
  if (mutation) headers['Idempotency-Key'] = mutation.key
  const csrf = document.cookie
    .split('; ')
    .find((row) => row.startsWith('csrftoken='))
    ?.split('=')[1]
  if (csrf && method !== 'GET') headers['X-CSRFToken'] = decodeURIComponent(csrf)
  const multipart = data instanceof FormData
  if (data !== undefined && !multipart) headers['Content-Type'] = 'application/json'
  const controller = new AbortController()
  let timedOut = false
  const cancel = () => controller.abort()
  signal?.addEventListener('abort', cancel, { once: true })
  if (signal?.aborted) controller.abort()
  const timeout = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, 30_000)
  try {
    const response = await fetch(`${url.pathname}${url.search}`, {
      signal: controller.signal,
      method,
      headers,
      credentials: 'same-origin',
      cache: 'no-store',
      body: data === undefined ? undefined : multipart ? data : JSON.stringify(data),
    })
    const requestId = response.headers.get('X-Request-ID')
    const raw = await response.text()
    let parsed: unknown
    try {
      parsed = raw ? JSON.parse(raw) : null
    } catch {
      throw new APIError(
        `Server returned ${response.status}. Please reload and try again.`,
        response.status,
        requestId,
      )
    }
    if (!response.ok) {
      finishMutation(mutation, response.status)
      throw new APIError(errorText(parsed), response.status, requestId, parsed)
    }
    const contractIssue = responseContractIssue(path, method, parsed)
    if (contractIssue)
      throw new APIError(
        `The server returned an unexpected response (${contractIssue}). Refresh the app before continuing.`,
        response.status,
        requestId,
      )
    finishMutation(mutation, response.status)
    return parsed as T
  } catch (error) {
    if (timedOut)
      throw new APIError(
        'The server took too long to respond. Check the saved result before retrying a change.',
      )
    if (controller.signal.aborted) throw abortError()
    if (error instanceof APIError) throw error
    throw new APIError('Cannot reach the server. Check your connection and try again.')
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', cancel)
  }
}

export async function api<T>(path: string, method = 'GET', data?: unknown, signal?: AbortSignal): Promise<T> {
  const url = new URL(path, window.location.origin)
  if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/'))
    throw new APIError('Choose an application API address.')
  const verb = method.toUpperCase(),
    key = canonicalQueryKey(path),
    lifetime = cacheLifetime(path)
  const generation = queryCache.generation
  if (verb === 'GET' && lifetime > 0) {
    return queryCache.read(
      key,
      queryTags(path),
      (activeSignal) => transport<T>(path, verb, data, activeSignal),
      lifetime,
      signal,
    )
  }
  const value = await transport<T>(path, verb, data, signal)
  if (key === '/api/session/') {
    if (generation !== queryCache.generation) throw abortError()
    const session = value as { user?: { id: number } | null }
    if ('user' in session) setQueryAccount(session.user?.id ?? null, verb !== 'GET')
    if (verb !== 'GET') window.dispatchEvent(new Event('marginalia-session-changed'))
  } else {
    if (generation !== queryCache.generation) throw abortError()
    if (!['GET', 'HEAD', 'OPTIONS'].includes(verb)) queryCache.invalidate(mutationTags(path, data))
  }
  return value
}

export async function all<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const load = async (activeSignal: AbortSignal) => {
    const first = await api<{ results: T[]; next: string | null } | T[]>(path, 'GET', undefined, activeSignal)
    if (Array.isArray(first)) return first
    const rows = [...first.results]
    let next = first.next
    const visited = new Set([canonicalQueryKey(path)])
    while (next) {
      const url = new URL(next, window.location.origin)
      if (url.origin !== window.location.origin)
        throw new APIError('The next page points outside this application.')
      const nextPath = `${url.pathname}${url.search}`
      if (visited.has(canonicalQueryKey(nextPath)))
        throw new APIError('The server repeated a page. Please reload and try again.')
      visited.add(canonicalQueryKey(nextPath))
      const page = await api<{ results: T[]; next: string | null }>(nextPath, 'GET', undefined, activeSignal)
      rows.push(...page.results)
      next = page.next
    }
    return rows
  }
  return queryCache.read(`all:${canonicalQueryKey(path)}`, queryTags(path), load, cacheLifetime(path), signal)
}

type ResourceState<T> = {
  key: string | null
  generation: number
  data: T | null
  error: string
  loading: boolean
  apiError: APIError | null
}

export function useResource<T>(path: string | null, version = 0, paginated = false) {
  const key = path ? `${paginated ? 'all:' : ''}${canonicalQueryKey(path)}` : null
  const [revision, setRevision] = useState(0)
  const [state, set] = useState<ResourceState<T>>(() => {
    const cached = key ? queryCache.peek<T>(key) : null
    return {
      key,
      generation: queryCache.generation,
      data: cached?.data ?? null,
      error: '',
      loading: !!path && !cached,
      apiError: null,
    }
  })
  useEffect(() => {
    const tags = path ? queryTags(path) : new Set<string>()
    return queryCache.subscribe((event) => {
      if (event.accountChanged || event.revalidate || [...tags].some((tag) => event.tags.has(tag)))
        setRevision((value) => value + 1)
    })
  }, [path])
  useEffect(() => {
    let cancelled = false
    const controller = new AbortController(),
      generation = queryCache.generation
    if (!path || !key) {
      set({ key, generation, data: null, error: '', loading: false, apiError: null })
      return
    }
    const cached = queryCache.peek<T>(key)
    if (cached) {
      set((old) =>
        old.key === key &&
        old.generation === generation &&
        old.data === cached.data &&
        !old.loading &&
        !old.error
          ? old
          : { key, generation, data: cached.data, error: '', loading: false, apiError: null },
      )
      return
    }
    set((old) => ({
      key,
      generation,
      data: old.key === key && old.generation === generation ? old.data : null,
      loading: true,
      error: '',
      apiError: null,
    }))
    const request = paginated
      ? (all(path, controller.signal) as Promise<T>)
      : api<T>(path, 'GET', undefined, controller.signal)
    request
      .then((data) => {
        if (!cancelled && generation === queryCache.generation)
          set({ key, generation, data, error: '', loading: false, apiError: null })
      })
      .catch((error) => {
        if (!cancelled && generation === queryCache.generation && error?.name !== 'AbortError')
          set({
            key,
            generation,
            data: null,
            error: error instanceof Error ? error.message : String(error),
            loading: false,
            apiError: error instanceof APIError ? error : null,
          })
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [path, key, version, paginated, revision])
  // Do not expose a prior URL/account's data during the render before effects run.
  if (state.key !== key || state.generation !== queryCache.generation)
    return { data: null, error: '', loading: !!path, apiError: null }
  return state
}

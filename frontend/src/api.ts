import { useEffect, useState } from 'react'

function errorText(data: unknown): string {
  if (typeof data === 'string') return data
  if (Array.isArray(data)) return data.map(errorText).join(' ')
  if (data && typeof data === 'object') return Object.entries(data).map(([key, value]) => `${key === 'detail' || key === 'non_field_errors' ? '' : `${key}: `}${errorText(value)}`).join(' ')
  return 'The request could not be completed.'
}

export async function api<T>(path: string, method = 'GET', data?: unknown, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = {}
  const csrf = document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1]
  if (csrf) headers['X-CSRFToken'] = decodeURIComponent(csrf)
  const multipart = data instanceof FormData
  if (data !== undefined && !multipart) headers['Content-Type'] = 'application/json'
  const response = await fetch(path, { signal, method, headers, credentials: 'same-origin', body: data === undefined ? undefined : multipart ? data : JSON.stringify(data) })
  const raw = await response.text()
  let parsed: unknown
  try { parsed = raw ? JSON.parse(raw) : null } catch { throw new Error(`Server returned ${response.status}. Please reload and try again.`) }
  if (!response.ok) throw new Error(errorText(parsed))
  return parsed as T
}

export async function all<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const first = await api<{ results: T[]; next: string | null } | T[]>(path, 'GET', undefined, signal)
  if (Array.isArray(first)) return first
  const rows = [...first.results]
  let next = first.next
  while (next) {
    const url = new URL(next, window.location.origin)
    const page = await api<{ results: T[]; next: string | null }>(`${url.pathname}${url.search}`, 'GET', undefined, signal)
    rows.push(...page.results); next = page.next
  }
  return rows
}

export function useResource<T>(path: string | null, version = 0, paginated = false) {
  const [state, set] = useState<{ data: T | null; error: string; loading: boolean }>({ data: null, error: '', loading: true })
  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    if (!path) { set({ data: null, error: '', loading: false }); return }
    set(old => ({ ...old, loading: true, error: '' }))
    const request = paginated ? all(path, controller.signal) as Promise<T> : api<T>(path, 'GET', undefined, controller.signal)
    request.then(data => { if (!cancelled) set({ data, error: '', loading: false }) }).catch(error => { if (!cancelled) set({ data: null, error: String(error.message), loading: false }) })
    return () => { cancelled = true; controller.abort() }
  }, [path, version, paginated])
  return state
}

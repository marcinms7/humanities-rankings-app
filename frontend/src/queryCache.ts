/** Short-lived, account-scoped JSON cache. Nothing is written to browser storage. */
export type QueryEvent = { tags: ReadonlySet<string>; accountChanged: boolean; revalidate?: boolean }
type Entry = {
  tags: Set<string>
  data?: unknown
  hasData: boolean
  expires: number
  touched: number
  bytes: number
  invalidated: boolean
  promise?: Promise<unknown>
  controller: AbortController
  observers: number
  releaseTimer?: ReturnType<typeof setTimeout>
}

export function abortError(): DOMException {
  return new DOMException('The request was superseded.', 'AbortError')
}

export function canonicalQueryKey(path: string): string {
  const url = new URL(path, 'https://marginalia.local')
  url.searchParams.sort()
  return `${url.pathname}${url.search}`
}

export class QueryCache {
  private entries = new Map<string, Entry>()
  private listeners = new Set<(event: QueryEvent) => void>()
  private account = 'unresolved'
  private epoch = 0
  private readonly maxEntries: number
  private readonly maxBytes: number
  private readonly now: () => number

  constructor(options: { maxEntries?: number; maxBytes?: number; now?: () => number } = {}) {
    this.maxEntries = options.maxEntries ?? 80
    this.maxBytes = options.maxBytes ?? 8 * 1024 * 1024
    this.now = options.now ?? Date.now
  }

  get generation(): number {
    return this.epoch
  }

  setAccount(account: string, force = false): void {
    if (account === this.account && !force) return
    this.account = account
    this.epoch += 1
    for (const entry of this.entries.values()) this.dispose(entry)
    this.entries.clear()
    this.emit({ tags: new Set(), accountChanged: true })
  }

  subscribe(listener: (event: QueryEvent) => void): () => void {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  invalidate(tags: Iterable<string>): void {
    const changed = new Set(tags)
    if (!changed.size) return
    for (const [key, entry] of this.entries) {
      if ([...entry.tags].some((tag) => changed.has(tag))) {
        this.entries.delete(key)
        this.dispose(entry)
      }
    }
    this.emit({ tags: changed, accountChanged: false })
  }

  peek<T>(key: string): { data: T } | null {
    const entry = this.entries.get(key)
    if (!entry?.hasData || entry.expires <= this.now()) return null
    entry.touched = this.now()
    return { data: entry.data as T }
  }

  read<T>(
    key: string,
    tags: Iterable<string>,
    loader: (signal: AbortSignal) => Promise<T>,
    ttl: number,
    signal?: AbortSignal,
  ): Promise<T> {
    if (signal?.aborted) return Promise.reject(abortError())
    const cached = this.peek<T>(key)
    if (cached) {
      const epoch = this.epoch,
        current = this.entries.get(key)
      return Promise.resolve().then(() => {
        if (signal?.aborted || epoch !== this.epoch || current?.invalidated) throw abortError()
        return cached.data
      })
    }
    let entry = this.entries.get(key)
    if (entry?.promise && entry.controller.signal.aborted) {
      this.entries.delete(key)
      entry = undefined
    }
    if (!entry?.promise) {
      if (entry) this.dispose(entry)
      entry = {
        tags: new Set(tags),
        hasData: false,
        expires: 0,
        touched: this.now(),
        bytes: 0,
        invalidated: false,
        controller: new AbortController(),
        observers: 0,
      }
      this.entries.set(key, entry)
      const current = entry,
        epoch = this.epoch
      const request = Promise.resolve()
        .then(() => loader(current.controller.signal))
        .then((data) => {
          // A late response must never restore a previous account or pre-mutation value.
          if (epoch !== this.epoch || this.entries.get(key) !== current || current.controller.signal.aborted)
            throw abortError()
          current.data = data
          current.hasData = true
          current.expires = this.now() + ttl
          current.touched = this.now()
          current.bytes = JSON.stringify(data)?.length * 2 || 0
          current.promise = undefined
          this.prune()
          return data
        })
        .catch((error) => {
          if (this.entries.get(key) === current) this.entries.delete(key)
          throw error
        })
      current.promise = request
    }
    for (const tag of tags) entry.tags.add(tag)
    return this.observe<T>(key, entry, signal)
  }

  /** Revalidate active views after inactivity, without polling hidden pages. */
  expire(): void {
    const tags = new Set<string>()
    for (const [key, entry] of this.entries) {
      if (!entry.promise && entry.expires <= this.now()) {
        this.entries.delete(key)
        for (const tag of entry.tags) tags.add(tag)
        this.dispose(entry)
      }
    }
    this.emit({ tags, accountChanged: false, revalidate: true })
  }

  private observe<T>(key: string, entry: Entry, signal?: AbortSignal): Promise<T> {
    clearTimeout(entry.releaseTimer)
    entry.observers += 1
    return new Promise<T>((resolve, reject) => {
      let settled = false
      const finish = (value?: T, error?: unknown) => {
        if (settled) return
        settled = true
        signal?.removeEventListener('abort', cancelled)
        entry.observers -= 1
        if (!entry.observers && entry.promise) {
          // A quick remount may reuse the request. One departing observer never
          // aborts a request still needed by another component.
          entry.releaseTimer = setTimeout(() => {
            if (!entry.observers && entry.promise && this.entries.get(key) === entry) {
              this.entries.delete(key)
              this.dispose(entry)
            }
          }, 50)
        }
        if (entry.invalidated) reject(abortError())
        else if (error !== undefined) reject(error)
        else resolve(value as T)
      }
      const cancelled = () => finish(undefined, abortError())
      signal?.addEventListener('abort', cancelled, { once: true })
      if (signal?.aborted) cancelled()
      entry.promise!.then(
        (value) => finish(value as T),
        (error) => finish(undefined, error),
      )
    })
  }

  private prune(): void {
    const complete = [...this.entries]
      .filter(([, entry]) => !entry.promise)
      .sort((a, b) => a[1].touched - b[1].touched)
    let bytes = complete.reduce((total, [, entry]) => total + entry.bytes, 0)
    let count = complete.length
    for (const [key, entry] of complete) {
      if (entry.expires > this.now() && count <= this.maxEntries && bytes <= this.maxBytes) continue
      this.entries.delete(key)
      this.dispose(entry, false)
      bytes -= entry.bytes
      count -= 1
    }
  }

  private dispose(entry: Entry, invalidate = true): void {
    if (invalidate) entry.invalidated = true
    clearTimeout(entry.releaseTimer)
    entry.controller.abort()
  }

  private emit(event: QueryEvent): void {
    for (const listener of this.listeners) listener(event)
  }
}

export const queryCache = new QueryCache()

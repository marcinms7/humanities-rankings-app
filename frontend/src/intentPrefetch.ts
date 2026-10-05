import type { PrefetchModule, PrefetchPlan } from './prefetchPlan.ts'

type CurrentIntent = { plan: PrefetchPlan; controller: AbortController; committed: boolean; started: boolean }
type ReadTask = { path: string; signal: AbortSignal }

/** One intended destination; module downloads and GET concurrency stay bounded. */
export class IntentPrefetch {
  private current: CurrentIntent | null = null
  private timer?: ReturnType<typeof setTimeout>
  private deadline?: ReturnType<typeof setTimeout>
  private warming = new Set<PrefetchModule>()
  private ready = new Set<PrefetchModule>()
  private reads: ReadTask[] = []
  private activeReads = 0
  private readonly loadModule: (name: PrefetchModule) => Promise<unknown>
  private readonly read: (path: string, signal: AbortSignal) => Promise<unknown>
  private readonly allowed: () => boolean
  private readonly delay: number

  constructor(options: {
    loadModule: (name: PrefetchModule) => Promise<unknown>
    read: (path: string, signal: AbortSignal) => Promise<unknown>
    allowed: () => boolean
    delay?: number
  }) {
    this.loadModule = options.loadModule
    this.read = options.read
    this.allowed = options.allowed
    this.delay = options.delay ?? 140
  }

  intend(plan: PrefetchPlan): void {
    if (!this.allowed()) return this.reset()
    if (this.current?.plan.key === plan.key) return
    this.reset()
    this.current = { plan, controller: new AbortController(), committed: false, started: false }
    this.timer = setTimeout(() => this.start(), this.delay)
  }

  leave(key: string): void {
    if (this.current?.plan.key === key && !this.current.committed) this.reset()
  }

  /** Keep a clicked destination alive while its lazy screen attaches cache observers. */
  commit(key: string): void {
    if (this.current?.plan.key !== key) return
    this.current.committed = true
    clearTimeout(this.timer)
    this.start()
  }

  navigated(key: string): void {
    if (this.current?.plan.key === key) this.commit(key)
    else this.reset()
  }

  reset(): void {
    clearTimeout(this.timer)
    clearTimeout(this.deadline)
    this.current?.controller.abort()
    this.current = null
    this.reads = []
  }

  private start(): void {
    const intent = this.current
    if (!intent || intent.started) return
    if (!this.allowed()) return this.reset()
    intent.started = true
    // A module import cannot be aborted; allow only two speculative imports at once.
    const module = intent.plan.module
    if (!this.ready.has(module) && !this.warming.has(module) && this.warming.size < 2) {
      this.warming.add(module)
      void Promise.resolve()
        .then(() => this.loadModule(module))
        .then(
          () => this.ready.add(module),
          () => {
            /* Navigation itself will retry and report a real loading failure. */
          },
        )
        .finally(() => this.warming.delete(module))
    }
    this.reads.push(
      ...intent.plan.paths.slice(0, 2).map((path) => ({ path, signal: intent.controller.signal })),
    )
    this.drain()
    this.deadline = setTimeout(() => this.reset(), 8_000)
  }

  private drain(): void {
    while (this.activeReads < 2 && this.reads.length) {
      const task = this.reads.shift()!
      if (task.signal.aborted || !this.allowed()) continue
      this.activeReads += 1
      // api() attaches this signal to only the speculative cache observer. A
      // screen using the same GET keeps its shared transport when we cancel.
      void Promise.resolve()
        .then(() => {
          if (!task.signal.aborted && this.allowed()) return this.read(task.path, task.signal)
        })
        .catch(() => {
          /* Speculation never displays errors or changes navigation. */
        })
        .finally(() => {
          this.activeReads -= 1
          this.drain()
        })
    }
  }
}

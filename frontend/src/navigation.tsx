import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { browseTarget, type BrowseChanges } from './browseState'
export { positivePage } from './browseState'

export const navigationEvent = 'marginalia-navigation'
type BrowsePatch = (values: BrowseChanges, options?: { replace?: boolean }) => void
const subscribe = (listener: () => void) => {
  window.addEventListener('hashchange', listener)
  window.addEventListener('popstate', listener)
  window.addEventListener(navigationEvent, listener)
  return () => {
    window.removeEventListener('hashchange', listener)
    window.removeEventListener('popstate', listener)
    window.removeEventListener(navigationEvent, listener)
  }
}
const snapshot = () => window.location.hash

/** Query state belongs to the URL; unrelated route parameters are preserved. */
export function useBrowseState<T extends Record<string, string>>(defaults: T): [T, BrowsePatch] {
  const hash = useSyncExternalStore(subscribe, snapshot)
  const defaultsKey = JSON.stringify(defaults)
  const params = new URLSearchParams(hash.split('?')[1] || '')
  const values = Object.fromEntries(
    Object.entries(defaults).map(([key, value]) => [key, params.get(key) ?? value]),
  ) as T
  const patch = useCallback<BrowsePatch>(
    (changes, options) => {
      const next = browseTarget(window.location.hash, changes, JSON.parse(defaultsKey))
      if (next === window.location.hash) return
      rememberScroll()
      if (options?.replace) history.replaceState(history.state, '', next)
      else history.pushState(null, '', next)
      window.dispatchEvent(new Event(navigationEvent))
    },
    [defaultsKey],
  )
  return [values, patch]
}

export function useDebouncedValue<T>(value: T, delay = 250): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return settled
}

/** Draft typing stays local. Back/Forward restores the committed query. */
export function useBrowseSearch(value: string, patch: BrowsePatch, key = 'q', pageKey = 'page') {
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  useEffect(() => {
    if (draft === value) return
    const timer = setTimeout(() => patch({ [key]: draft, [pageKey]: 1 }, { replace: true }), 250)
    return () => clearTimeout(timer)
  }, [draft, value, patch, key, pageKey])
  return [draft, setDraft] as const
}

const positions = new Map<string, number>()
let pendingBack: { hash: string; offset: number } | null = null
let scrollRoute = ''
function rememberScroll() {
  if (!scrollRoute) scrollRoute = window.location.hash
  positions.delete(scrollRoute)
  positions.set(scrollRoute, window.scrollY)
  if (positions.size > 150) positions.delete(positions.keys().next().value!)
}

/** Only scroll offsets are retained in memory; no private document text is stored. */
export function installScrollHistory() {
  const previous = history.scrollRestoration
  history.scrollRestoration = 'manual'
  scrollRoute = window.location.hash
  const changed = () => {
    scrollRoute = window.location.hash
  }
  const back = () => {
    pendingBack = { hash: window.location.hash, offset: positions.get(window.location.hash) ?? 0 }
    changed()
  }
  window.addEventListener('scroll', rememberScroll, { passive: true })
  document.addEventListener('click', rememberScroll, true)
  window.addEventListener('popstate', back)
  window.addEventListener('hashchange', changed)
  window.addEventListener(navigationEvent, changed)
  return () => {
    history.scrollRestoration = previous
    window.removeEventListener('scroll', rememberScroll)
    document.removeEventListener('click', rememberScroll, true)
    window.removeEventListener('popstate', back)
    window.removeEventListener('hashchange', changed)
    window.removeEventListener(navigationEvent, changed)
  }
}

export function useRouteAccessibility(hash: string, ready: boolean) {
  const previousPath = useRef('')
  useEffect(() => {
    if (!ready) return
    const path = hash.split('?')[0]
    const changedPath = path !== previousPath.current
    previousPath.current = path
    const restore = pendingBack?.hash === hash
    const offset = restore ? pendingBack!.offset : 0
    if (restore) pendingBack = null
    const main = document.getElementById('main-content')
    if (!main) return
    let focused = false,
      cancelled = false,
      frame = 0
    const started = performance.now()
    const stop = () => {
      cancelled = true
      cancelAnimationFrame(frame)
    }
    const update = () => {
      cancelAnimationFrame(frame)
      const heading = main.querySelector<HTMLElement>('h1')
      if (heading) {
        document.title = `${heading.textContent?.trim() || 'Reading room'} · Marginalia`
        if (!focused && changedPath) {
          heading.tabIndex = -1
          heading.focus({ preventScroll: true })
          focused = true
        }
      }
      if (!cancelled && (changedPath || restore)) {
        window.scrollTo({ top: offset, behavior: 'instant' })
        // Lazy routes and paged results may need time to establish their height.
        if (
          (!heading || document.documentElement.scrollHeight < offset + innerHeight) &&
          performance.now() - started < 2500
        ) {
          frame = requestAnimationFrame(update)
        } else cancelled = true
      }
    }
    const observer = new MutationObserver(() => {
      if (!cancelled) update()
    })
    observer.observe(main, { childList: true, subtree: true })
    frame = requestAnimationFrame(update)
    window.addEventListener('wheel', stop, { passive: true, once: true })
    window.addEventListener('touchstart', stop, { passive: true, once: true })
    window.addEventListener('keydown', stop, { once: true })
    return () => {
      stop()
      observer.disconnect()
      window.removeEventListener('wheel', stop)
      window.removeEventListener('touchstart', stop)
      window.removeEventListener('keydown', stop)
    }
  }, [hash, ready])
}

export function useMobileNavigation(open: boolean, close: () => void, ready = true) {
  useEffect(() => {
    const sidebar = document.getElementById('site-navigation')
    const content = document.querySelector<HTMLElement>('.main-shell')
    if (!sidebar || !content) return
    const small = matchMedia('(max-width: 760px)')
    const previous = document.activeElement as HTMLElement | null
    const oldOverflow = document.body.style.overflow
    const apply = () => {
      sidebar.inert = small.matches && !open
      content.inert = small.matches && open
      if (small.matches && open) {
        document.body.style.overflow = 'hidden'
        sidebar.querySelector<HTMLElement>('a, button')?.focus()
      } else document.body.style.overflow = oldOverflow
    }
    const keydown = (event: KeyboardEvent) => {
      if (!small.matches || !open) return
      if (event.key === 'Escape') {
        event.preventDefault()
        close()
        return
      }
      if (event.key !== 'Tab') return
      const nodes = [
        ...sidebar.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), [tabindex="0"]'),
      ].filter((node) => node.getClientRects().length > 0)
      const first = nodes[0],
        last = nodes[nodes.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first?.focus()
      }
    }
    apply()
    small.addEventListener('change', apply)
    document.addEventListener('keydown', keydown)
    return () => {
      sidebar.inert = false
      content.inert = false
      document.body.style.overflow = oldOverflow
      small.removeEventListener('change', apply)
      document.removeEventListener('keydown', keydown)
      if (open && previous?.isConnected) previous.focus({ preventScroll: true })
    }
  }, [open, close, ready])
}

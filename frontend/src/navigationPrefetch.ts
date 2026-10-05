import { api } from './api'
import { IntentPrefetch } from './intentPrefetch'
import { navigationEvent } from './navigation'
import { canPrefetch, internalPrefetchHash, prefetchPlan } from './prefetchPlan'
import type { PrefetchConnection } from './prefetchPlan'
import { queryCache } from './queryCache'
import { routeLoaders } from './routeLoaders'

/** Delegation covers dynamically rendered book links and the sidebar equally. */
export function installNavigationPrefetch(signedIn: boolean, staff: boolean): () => void {
  const generation = queryCache.generation
  const connection = (navigator as Navigator & { connection?: PrefetchConnection & EventTarget }).connection
  const allowed = () =>
    generation === queryCache.generation &&
    canPrefetch(navigator.onLine !== false, document.visibilityState !== 'hidden', connection)
  const prefetch = new IntentPrefetch({
    allowed,
    loadModule: (name) => routeLoaders[name](),
    read: (path, signal) => api(path, 'GET', undefined, signal),
  })
  let hovered: HTMLAnchorElement | null = null
  let focused: HTMLAnchorElement | null = null
  const link = (target: EventTarget | null) =>
    target instanceof Element ? target.closest<HTMLAnchorElement>('a[href]') : null
  const hashFor = (anchor: HTMLAnchorElement | null) => {
    if (
      !anchor ||
      anchor.hasAttribute('download') ||
      (anchor.target && anchor.target !== '_self') ||
      anchor.dataset.prefetch === 'off'
    )
      return null
    return internalPrefetchHash(anchor.href, location.href)
  }
  const intend = (anchor: HTMLAnchorElement | null) => {
    const hash = hashFor(anchor)
    const plan = hash ? prefetchPlan(hash, signedIn, staff) : null
    if (plan) prefetch.intend(plan)
  }
  const over = (event: PointerEvent) => {
    if (event.pointerType === 'touch') return
    const anchor = link(event.target)
    if (anchor === hovered) return
    hovered = anchor
    intend(anchor)
  }
  const out = (event: PointerEvent) => {
    const anchor = link(event.target)
    if (!anchor || (event.relatedTarget instanceof Node && anchor.contains(event.relatedTarget))) return
    hovered = null
    const hash = hashFor(anchor)
    if (hash && focused !== anchor) prefetch.leave(hash)
  }
  const focus = (event: FocusEvent) => {
    focused = link(event.target)
    intend(focused)
  }
  const blur = (event: FocusEvent) => {
    const anchor = link(event.target)
    focused = null
    const hash = hashFor(anchor)
    if (hash && hovered !== anchor) prefetch.leave(hash)
  }
  const click = (event: MouseEvent) => {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.altKey ||
      event.shiftKey ||
      event.defaultPrevented
    )
      return
    const anchor = link(event.target)
    const hash = hashFor(anchor)
    if (!hash) return
    // Pressing a link also covers touch users without predicting taps while scrolling.
    intend(anchor)
    prefetch.commit(hash)
  }
  const navigated = () => {
    hovered = null
    focused = null
    prefetch.navigated(location.hash)
  }
  const resetIfUnavailable = () => {
    if (!allowed()) prefetch.reset()
  }
  const unsubscribe = queryCache.subscribe((event) => {
    if (event.accountChanged) prefetch.reset()
  })
  document.addEventListener('pointerover', over)
  document.addEventListener('pointerout', out)
  document.addEventListener('focusin', focus)
  document.addEventListener('focusout', blur)
  document.addEventListener('click', click)
  document.addEventListener('visibilitychange', resetIfUnavailable)
  window.addEventListener('offline', resetIfUnavailable)
  window.addEventListener('hashchange', navigated)
  window.addEventListener('popstate', navigated)
  window.addEventListener(navigationEvent, navigated)
  connection?.addEventListener('change', resetIfUnavailable)
  return () => {
    prefetch.reset()
    unsubscribe()
    document.removeEventListener('pointerover', over)
    document.removeEventListener('pointerout', out)
    document.removeEventListener('focusin', focus)
    document.removeEventListener('focusout', blur)
    document.removeEventListener('click', click)
    document.removeEventListener('visibilitychange', resetIfUnavailable)
    window.removeEventListener('offline', resetIfUnavailable)
    window.removeEventListener('hashchange', navigated)
    window.removeEventListener('popstate', navigated)
    window.removeEventListener(navigationEvent, navigated)
    connection?.removeEventListener('change', resetIfUnavailable)
  }
}

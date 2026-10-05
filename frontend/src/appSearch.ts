import type { ApiAppSearchGroup } from './generated/apiContracts'

export function isAppSearchShortcut(
  event: {
    key: string
    metaKey: boolean
    ctrlKey: boolean
    altKey: boolean
    shiftKey: boolean
    isComposing: boolean
    repeat: boolean
    keyCode?: number
    defaultPrevented?: boolean
  },
  otherDialogOpen: boolean,
): boolean {
  return (
    !otherDialogOpen &&
    !event.defaultPrevented &&
    !event.isComposing &&
    event.keyCode !== 229 &&
    !event.repeat &&
    !event.altKey &&
    !event.shiftKey &&
    (event.metaKey || event.ctrlKey) &&
    event.key.toLowerCase() === 'k'
  )
}

export function appSearchDestination(query: string, groups: ApiAppSearchGroup[]): string {
  return groups[0]?.items[0]?.href || `#/catalog?q=${encodeURIComponent(query.trim().slice(0, 300))}`
}

/** The input occupies -1; Arrow Up from it reaches the final result. */
export function appSearchFocusIndex(current: number, direction: 1 | -1, count: number): number {
  if (count < 1) return -1
  if (current === -1 && direction === -1) return count - 1
  return Math.max(-1, Math.min(count - 1, current + direction))
}

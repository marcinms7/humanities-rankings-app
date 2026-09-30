export type BrowseChanges = Record<string, string | number | boolean | null>

/** Preserve unrelated query parameters, including private saved-filter references. */
export function browseTarget(hash: string, changes: BrowseChanges, defaults: Record<string, string>) {
  const url = new URL(hash.replace(/^#/, '') || '/explore', 'https://marginalia.local')
  for (const [key, value] of Object.entries(changes)) {
    if (value === null || String(value) === (defaults[key] ?? '')) url.searchParams.delete(key)
    else url.searchParams.set(key, String(value))
  }
  return `#${url.pathname}${url.search}`
}

export function positivePage(value: string): number {
  return /^\d+$/.test(value) ? Math.max(1, Math.min(1000000, Number(value))) : 1
}

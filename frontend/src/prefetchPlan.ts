import { positivePage } from './browseState.ts'
import { catalogBrowseDefaults, catalogRequestParams } from './catalogFilterState.ts'

export type PrefetchModule =
  | 'catalog'
  | 'rankings'
  | 'library'
  | 'classicalEducation'
  | 'discovery'
  | 'readingTrails'
  | 'catalogAtlas'
  | 'publishedComparison'
  | 'today'
  | 'profile'
  | 'catalogReview'
  | 'operations'

export type PrefetchPlan = { key: string; module: PrefetchModule; paths: string[] }
export type PrefetchConnection = { saveData?: boolean; effectiveType?: string; downlink?: number }

export function canPrefetch(online: boolean, visible: boolean, connection?: PrefetchConnection): boolean {
  return (
    online &&
    visible &&
    !connection?.saveData &&
    !['slow-2g', '2g', '3g'].includes(connection?.effectiveType || '') &&
    !(connection?.downlink != null && connection.downlink < 1.5)
  )
}

/** Only application hash links can initiate speculative requests. */
export function internalPrefetchHash(href: string, current: string): string | null {
  try {
    const base = new URL(current),
      target = new URL(href, base)
    if (
      target.origin !== base.origin ||
      target.pathname !== base.pathname ||
      target.search !== base.search ||
      !target.hash.startsWith('#/') ||
      target.hash === base.hash ||
      target.hash.length > 2048
    )
      return null
    return target.hash
  } catch {
    return null
  }
}

/** At most two of the destination's real GET keys, never an all-pages read. */
export function prefetchPlan(
  hash: string,
  signedIn: boolean,
  staff = false,
  now = new Date(),
): PrefetchPlan | null {
  if (!hash.startsWith('#/')) return null
  const route = new URL(hash.slice(1), 'https://marginalia.local')
  const [name, id, extra] = route.pathname.split('/').filter(Boolean)
  if (extra || (id && !/^\d+$/.test(id))) return null
  const q = route.searchParams
  const value = (key: string, fallback = '') => q.get(key) ?? fallback
  const page = String(positivePage(value('page', '1')))
  const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
  const plan = (module: PrefetchModule, paths: string[] = []): PrefetchPlan => ({ key: hash, module, paths })
  switch (name) {
    case 'books':
    case 'catalog': {
      if (name === 'books' && id) return plan('catalog', [`/api/works/${id}/`, `/api/works/${id}/editions/`])
      const filters = catalogRequestParams({ ...catalogBrowseDefaults, ...Object.fromEntries(q) })
      const params = new URLSearchParams(filters)
      params.set('page', page)
      params.set('compact', '1')
      return plan('catalog', [`/api/works/?${params}`, `/api/works/facets/?${filters}`])
    }
    case 'authors':
      return plan(
        'catalog',
        id
          ? [`/api/people/${id}/`, `/api/works/?author=${id}&page=${page}`]
          : [`/api/people/?page=${page}&search=${encodeURIComponent(value('q'))}`],
      )
    case 'rankings':
    case 'published-rankings':
    case 'collections':
    case 'my-lists':
    case 'saved': {
      if (name === 'rankings' && id) return plan('rankings', [`/api/rankings/${id}/?compact=1`])
      if (['my-lists', 'saved'].includes(name) && !signedIn) return null
      const mode = name === 'rankings' ? 'all' : name === 'published-rankings' ? 'published' : name
      const params = new URLSearchParams({
        paged: '1',
        mode,
        search: value('rsearch'),
        ordering: value('rsort', 'title'),
        page: String(positivePage(value('rpage', '1'))),
      })
      for (const key of ['field', 'country'])
        if (value(`r${key}`, 'all') !== 'all') params.set(key, value(`r${key}`))
      return plan('rankings', [`/api/rankings/?${params}`])
    }
    case 'explore':
      return plan('catalog', ['/api/rankings/explore/', ...(signedIn ? ['/api/library/overview/'] : [])])
    case 'atlas': {
      const overlay = signedIn && ['saved', 'read'].includes(value('overlay')) ? value('overlay') : 'all'
      const params = new URLSearchParams({
        q: value('q'),
        field: value('field'),
        country: value('country'),
        century: value('century'),
        overlay,
        page,
      })
      return plan('catalogAtlas', [`/api/catalog-atlas/?${params}`])
    }
    case 'published-comparison': {
      const params = new URLSearchParams({
        left: value('left'),
        right: value('right'),
        view: value('view', 'shared'),
        sort: value('sort', 'left'),
        search: value('q'),
        page,
      })
      return plan('publishedComparison', [
        '/api/published-comparison/',
        `/api/published-comparison/?${params}`,
      ])
    }
    case 'library': {
      if (!signedIn) return null
      if (value('view', 'books') !== 'books') return plan('library')
      const params = new URLSearchParams({ compact: '1', page, ordering: value('ordering', 'updated') })
      for (const key of ['shelf', 'tag', 'genre', 'rating', 'saved_filter'])
        if (value(key)) params.set(key, value(key))
      if (value('q')) params.set('search', value('q'))
      if (value('status', 'all') !== 'all') params.set('status', value('status'))
      const facets = new URLSearchParams(params)
      facets.delete('page')
      facets.delete('compact')
      return plan('library', [`/api/library/?${params}`, `/api/library/facets/?${facets}`])
    }
    case 'today':
      return signedIn ? plan('today', [`/api/today/?month=${month}`]) : null
    case 'planner':
      return signedIn ? plan('library') : null
    case 'profile':
      return signedIn ? plan('profile') : null
    case 'classical-education':
      return signedIn ? plan('classicalEducation') : null
    case 'sources':
      return signedIn ? plan('discovery') : null
    case 'trails':
    case 'discover':
      return signedIn ? plan('readingTrails') : null
    case 'catalog-review':
      return signedIn && staff ? plan('catalogReview') : null
    case 'operations':
      return signedIn && staff ? plan('operations') : null
    default:
      return null
  }
}

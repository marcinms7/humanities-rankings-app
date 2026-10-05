/** API relationships, kept separate from transport and React subscriptions. */
export function queryTags(path: string): Set<string> {
  const url = new URL(path, 'https://marginalia.local')
  const segments = url.pathname.split('/').filter(Boolean)
  const resource = segments[1] || 'other'
  let tags: string[]
  switch (resource) {
    case 'app-search':
      tags = ['catalog', 'rankings', 'study-content']
      break
    case 'library':
    case 'read-next':
      tags = ['library']
      break
    case 'today':
      tags = ['library', 'plan', 'reading-estimates']
      break
    case 'plan':
    case 'reading-allocation':
      tags = ['plan', 'library', 'reading-estimates']
      break
    case 'reading-calendar':
      tags = ['reading-calendar', 'plan', 'reading-estimates']
      break
    case 'works':
      tags =
        segments.includes('rankings') || segments.includes('placements')
          ? ['rankings', 'catalog']
          : segments.includes('facets')
            ? ['catalog']
            : ['catalog', 'reading-estimates']
      break
    case 'people':
    case 'editions':
      tags = ['catalog', 'reading-estimates']
      break
    case 'rankings':
      tags = segments.includes('recommendations')
        ? ['rankings', 'catalog', 'library', 'reading-estimates']
        : segments.includes('entries')
          ? ['rankings', 'catalog', 'reading-estimates']
          : ['rankings']
      break
    case 'ranking-browse':
      tags = ['rankings', 'catalog', 'library', 'reading-estimates']
      break
    case 'catalog-atlas':
      tags = ['catalog', 'library', 'reading-estimates']
      break
    case 'published-comparison':
      tags = ['rankings', 'catalog', 'reading-estimates']
      break
    case 'shared':
      tags = ['rankings', 'catalog', 'reading-estimates']
      break
    case 'collection-context':
    case 'collection-overlap':
    case 'personal-discovery':
    case 'reading-trails':
      tags = ['rankings', 'catalog', 'library']
      break
    case 'reading-insights':
    case 'annual-reading':
      tags = ['library', 'reading-goals']
      break
    case 'saved-filters':
      tags = ['saved-filters']
      break
    case 'classical-education':
      tags =
        url.searchParams.get('part') === 'content' || url.searchParams.has('work')
          ? ['study-content', 'catalog', 'rankings']
          : ['study-state', 'library', 'plan']
      break
    case 'source-explorer':
      tags = ['rankings', 'catalog']
      break
    case 'profile':
      tags = ['profile']
      break
    case 'catalog-review':
      tags = ['catalog-review', 'catalog']
      break
    case 'recommendations':
      tags = [
        'recommendations',
        'library',
        'rankings',
        'catalog',
        'saved-filters',
        'profile',
        'reading-estimates',
      ]
      break
    case 'operations':
      tags = ['operations']
      break
    default:
      tags = [`api:${resource}`]
  }
  if (url.searchParams.get('saved_filter')) tags.push('saved-filters', 'library', 'rankings')
  if (resource === 'library') tags.push('reading-estimates', 'catalog')
  return new Set(tags)
}

export function mutationTags(path: string, payload?: unknown): Set<string> {
  const pathname = new URL(path, 'https://marginalia.local').pathname
  const data =
    payload && typeof payload === 'object' && !(payload instanceof FormData)
      ? (payload as Record<string, unknown>)
      : {}
  if (pathname === '/api/bibliography/') return new Set()
  if (/\/rankings\/[^/]+\/preview\/$/.test(pathname)) return new Set()
  if (/\/library\/[^/]+\/edition-change\/$/.test(pathname) && data.apply !== true) return new Set()
  if (
    [
      '/api/plan/suggest/',
      '/api/plan/carryover/',
      '/api/reading-allocation/',
      '/api/read-next/plan/',
      '/api/reading-calendar/',
    ].includes(pathname) &&
    data.apply !== true
  )
    return new Set()
  if (pathname === '/api/reading-calendar/') return new Set(['reading-calendar', 'plan', 'study-state'])
  if (pathname === '/api/library/bulk/')
    return new Set(data.action === 'personal_list' ? ['rankings'] : ['library', 'plan', 'study-state'])
  if (pathname === '/api/classical-education/') {
    const companion = data.companion as { action?: string } | undefined
    if (companion?.action === 'plan-preview') return new Set()
    return new Set(companion?.action === 'plan-add' ? ['study-state', 'plan', 'library'] : ['study-state'])
  }
  if (/^\/api\/(library|read-next|today\/progress)\//.test(pathname))
    return new Set(['library', 'plan', 'study-state'])
  if (/^\/api\/(plan|reading-allocation)\//.test(pathname)) return new Set(['plan', 'study-state'])
  if (pathname === '/api/profile/') {
    const estimates = Object.keys(data).some((key) =>
      [
        'words_per_minute',
        'reading_target_period',
        'reading_days_per_week',
        'difficulty_aware_planning',
        'pages_per_day',
        'pages_per_week',
        'pages_per_month',
      ].includes(key),
    )
    return new Set(estimates ? ['profile', 'reading-estimates', 'study-state'] : ['profile'])
  }
  if (/^\/api\/(works|people|editions|catalog-review)\//.test(pathname))
    return new Set(['catalog', 'catalog-review', 'reading-estimates'])
  if (/^\/api\/rankings\//.test(pathname)) return new Set(['rankings'])
  if (/^\/api\/annual-reading\//.test(pathname)) return new Set(['reading-goals'])
  if (/^\/api\/saved-filters\//.test(pathname)) return new Set(['saved-filters'])
  if (/^\/api\/recommendations\//.test(pathname)) return new Set(['recommendations'])
  return queryTags(path)
}

export function cacheLifetime(path: string): number {
  const url = new URL(path, 'https://marginalia.local')
  if (
    url.pathname === '/api/session/' ||
    url.pathname === '/api/export/' ||
    url.searchParams.has('export') ||
    url.searchParams.has('essay')
  )
    return 0
  if (url.pathname.startsWith('/api/operations/')) return 15_000
  if (url.pathname.endsWith('/facets/') || url.searchParams.get('part') === 'content') return 5 * 60_000
  return 30_000
}

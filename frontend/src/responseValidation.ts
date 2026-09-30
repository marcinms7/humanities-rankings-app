import { responseSchemas } from './generated/responseSchemas.ts'

type Shape = {
  kind: string
  nullable?: boolean
  fields?: Readonly<Record<string, Shape>>
  required?: readonly string[]
  item?: Shape
  values?: readonly unknown[]
}

function check(shape: Shape, value: unknown, path: string): string | null {
  if (shape.kind === 'unknown' || (value === null && shape.nullable)) return null
  if (shape.kind === 'object' || shape.kind === 'record') {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return path
    const record = value as Record<string, unknown>
    for (const name of shape.required || []) if (!Object.hasOwn(record, name)) return `${path}.${name}`
    for (const [name, child] of Object.entries(record)) {
      const field = shape.kind === 'record' ? shape.item : shape.fields?.[name]
      if (field) {
        const issue = check(field, child, `${path}.${name}`)
        if (issue) return issue
      }
    }
    return null
  }
  if (shape.kind === 'array') {
    if (!Array.isArray(value)) return path
    for (let index = 0; index < value.length; index++) {
      const issue = check(shape.item!, value[index], `${path}[${index}]`)
      if (issue) return issue
    }
    return null
  }
  if (shape.kind === 'enum') return shape.values?.includes(value) ? null : path
  if (typeof value !== shape.kind || (shape.kind === 'number' && !Number.isFinite(value))) return path
  return null
}

export function responseContractIssue(path: string, method: string, value: unknown): string | null {
  const url = new URL(path, 'https://marginalia.local')
  let name: keyof typeof responseSchemas | undefined
  const record = value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
  if (url.pathname === '/api/catalog-atlas/') name = 'ApiCatalogAtlas'
  else if (url.pathname === '/api/published-comparison/') name = 'ApiPublishedComparison'
  else if (url.pathname === '/api/reading-calendar/')
    name = method === 'GET' ? 'ApiCalendarState' : 'ApiCalendarPreview'
  else if (url.pathname === '/api/recommendations/') name = 'ApiRecommendationBundle'
  else if (url.pathname === '/api/recommendations/preferences/') name = 'ApiRecommendationPreferences'
  else if (url.pathname === '/api/recommendations/feedback/')
    name = method === 'GET' ? 'ApiRecommendationFeedbackPage' : 'ApiRecommendationFeedback'
  else if (/^\/api\/ranking-browse\/\d+\/$/.test(url.pathname)) name = 'ApiRankingBrowsePage'
  else if (/^\/api\/rankings\/\d+\/preview\/$/.test(url.pathname) && url.searchParams.get('paged') === '1')
    name = 'ApiRankingBrowsePage'
  else if (url.pathname === '/api/plan/suggest/' && record.applied !== true && 'preview_token' in record)
    name = 'ApiPlanSuggestion'
  else if (url.pathname === '/api/reading-allocation/' && record.applied === false)
    name = 'ApiAllocationPreview'
  else if (
    url.pathname === '/api/classical-education/' &&
    method === 'GET' &&
    url.searchParams.get('part') === 'records'
  )
    name = url.searchParams.has('record') ? 'ApiStudyHistoryPage' : 'ApiStudyRecordsPage'
  else if (
    url.pathname === '/api/classical-education/' &&
    method === 'PATCH' &&
    url.searchParams.get('part') === 'delta' &&
    !('preview' in record)
  )
    name = 'ApiStudyDelta'
  return name ? check(responseSchemas[name] as Shape, value, name) : null
}

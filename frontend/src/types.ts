import type {
  ApiUser,
  ApiPerson,
  ApiEdition,
  ApiWork,
  ApiPlanSuggestion,
  ApiMonthCapacity,
  ApiLibrary,
  ApiPlan,
} from './generated/apiContracts'
export type Theme = 'light' | 'dark' | 'system'
export type User = ApiUser
export type Person = ApiPerson
export type ReadingBasis = {
  edition_id: number | null
  pages: number | null
  pages_basis: string
  isbn: string
  origin: string
}
export type Edition = ApiEdition
export type Estimate = {
  status: string
  estimated_hours: number | null
  low_hours: number | null
  high_hours: number | null
  assumptions: string[]
  algorithm_version: string
}
export type Work = ApiWork
export type WorkRankingMembership = {
  slug: string
  id: number
  title: string
  kind: string
  origin: string
  presentation: string
  position: number
  source_rank: number | null
}
export type Preference = {
  bookmarked: boolean
  refresh_interval_days: number | null
  refresh_requested_at: string | null
  weights: Record<string, number>
  overrides: Record<string, Record<string, number>>
}
export type Criterion = { id: string; label: string }
export type EditorialLens = 'standing' | 'reading'
export type EditorialSelection = {
  version: string
  published_on: string
  notice: string
  method: string
  orders: Record<EditorialLens, { label: string; description: string; item_ids: number[] }>
  entries: Record<
    string,
    {
      standing: string
      reading: string
      caveat: string
      sources: { source_id: string; title: string; url: string }[]
      reported_sources?: { source_id: string; title: string; url: string; eligible: boolean }[]
    }
  >
}
export type Ranking = {
  order_status?: string
  has_editorial?: boolean
  id: number
  slug: string
  title: string
  description: string
  domain: string
  item_type: 'work' | 'person'
  presentation: string
  origin: string
  owner: number | null
  scope: {
    editorial?: EditorialSelection
    forms?: string[]
    countries?: string[]
    tags?: string[]
    [key: string]: unknown
  }
  target_size: number
  status: string
  source_url: string
  publisher: string
  criteria: Criterion[]
  revision: number
  updated_at: string
  created_at: string
  last_researched_at: string | null
  last_sources_checked_at: string | null
  entry_count: number
  source_count: number
  preference: Preference | null
  can_edit: boolean
  sharing_enabled: boolean
  share_url: string | null
}
export type EntryGrouping = {
  country: string
  local_rank: 1 | 2 | 3
  section_index: number
  region: string
  confidence: string
  language: string
  form_reported: string
  affiliation_note: string
  source_ids: string[]
}
export type Entry = {
  id: number
  work: number | null
  person: number | null
  book: Work | null
  author: Person | null
  position: number
  source_rank: number | null
  rationale: string
  assessments: Record<string, number>
  groupings: EntryGrouping[]
}
export type Source = {
  provenance: { consultation_origin: string; access_extent: string; evidence_role: string }
  id: number
  source_id: string
  title: string
  url: string
  family: string
  publisher: string
  evidence: string
  limitations: string
  consulted_on: string | null
  eligible: boolean
}
export type LibraryItem = Omit<ApiLibrary, 'reading_basis'> & { reading_basis: ReadingBasis }
export type PlanItem = Omit<ApiPlan, 'reading_basis' | 'classical_study'> & {
  reading_basis: ReadingBasis
  classical_study?: { mode: string; passages: string; done: boolean } | null
}
export type Score = {
  entry_id: number
  score: number | null
  reason: string | null
  contributions: Record<string, number>
}
export type PlanSuggestion = ApiPlanSuggestion

export type MonthCapacity = ApiMonthCapacity

export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] }

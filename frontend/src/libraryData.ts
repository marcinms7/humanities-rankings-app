import type { ApiWorkCard, ApiLibrarySummary, ApiPlanSummary } from './generated/apiContracts'
import type { LibraryItem, PlanItem } from './types'

export type WorkCard = ApiWorkCard

export type LibrarySummary = Omit<ApiLibrarySummary, 'reading_basis'> & Pick<LibraryItem, 'reading_basis'>
export type PlanSummary = Omit<ApiPlanSummary, 'reading_basis' | 'classical_study'> &
  Pick<PlanItem, 'reading_basis' | 'classical_study'>

export type LibrarySelector = {
  id: number
  work: number
  title: string
  status: string
  current_page: number
  pages: number | null
}
export type LibraryFacets = {
  total: number
  statuses: Record<string, number>
  shelves: string[]
  tags: string[]
}
export type ReadingOverview = { count: number; reading_count: number; currently_reading: LibrarySummary[] }
export type ReadingHistorySummary = {
  id: number
  work_id: number
  work__title: string
  status: string
  current_page: number
  rating: number | null
  started_on: string | null
  finished_on: string | null
  has_notes: boolean
}

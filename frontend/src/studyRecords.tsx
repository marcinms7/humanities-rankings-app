import type { ApiStudyRecordsPage, ApiStudyHistoryPage } from './generated/apiContracts'
import { useState, type ReactNode } from 'react'
import { useResource } from './api'
import { ErrorNotice, Loading } from './components'
import { useApp } from './context'

export type StudyFamily = 'modules' | 'activities' | 'companion' | 'essays' | 'recall' | 'desk' | 'sessions'
export type StudyRecord = { key: string; path: string[]; value: unknown }
export type StudyRecordsPage = ApiStudyRecordsPage
export type RecordHistoryMetadata = {
  _record_key?: string
  _history_count?: number
  _attempts_count?: number
}

export function studyDependencies(tab: string, selected: string): StudyFamily[] {
  const groups: Record<string, StudyFamily[]> = {
    'Today’s study': ['sessions'],
    'Recall & review': ['recall'],
    'Essay workshop': ['essays', 'companion'],
    'Commonplace book': ['companion'],
    Notebook: ['modules', 'activities'],
    Languages: ['activities'],
    'Passage exercises': ['activities'],
    'Art & archaeology': ['activities'],
    'Reading desk': ['desk'],
    'Translation lab': ['desk'],
  }
  return [...new Set([...(groups[tab] || []), ...(selected ? ['modules' as const] : [])])]
}

export function StudyHistory<T>({
  record,
  family,
  fallback,
  title,
  children,
}: {
  record: RecordHistoryMetadata | undefined
  family: StudyFamily
  fallback: T[]
  title: string
  children: (rows: T[]) => ReactNode
}) {
  const { version } = useApp()
  const [open, setOpen] = useState(false),
    [page, setPage] = useState(1)
  const count = record?._history_count ?? record?._attempts_count ?? fallback.length
  const resource = useResource<Omit<ApiStudyHistoryPage, 'results'> & { results: T[] }>(
    open && record?._record_key
      ? `/api/classical-education/?part=records&family=${family}&record=${record._record_key}&page=${page}`
      : null,
    version,
  )
  const rows = record?._record_key ? resource.data?.results || [] : [...fallback].reverse()
  return (
    <details onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        {title} ({count})
      </summary>
      {open && (
        <>
          {resource.error && <ErrorNotice>{resource.error}</ErrorNotice>}
          {resource.loading ? <Loading /> : children(rows)}
          {record?._record_key && count > 12 && (
            <nav className="toolbar" aria-label={`${title} pages`}>
              <button
                className="button secondary small"
                disabled={page === 1 || resource.loading}
                onClick={() => setPage((value) => value - 1)}
              >
                Previous
              </button>
              <span>Page {page}</span>
              <button
                className="button secondary small"
                disabled={!resource.data?.next_page || resource.loading}
                onClick={() => setPage((value) => value + 1)}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </details>
  )
}

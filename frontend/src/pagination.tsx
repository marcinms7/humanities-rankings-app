import type { Page } from './types'

export function Pager({
  page,
  data,
  setPage,
  loading,
}: {
  page: number
  data: Pick<Page<unknown>, 'count' | 'next' | 'previous'> | null
  setPage: (page: number) => void
  loading: boolean
}) {
  const totalPages = Math.max(1, Math.ceil((data?.count ?? 0) / 24))
  return (
    <nav className="toolbar" aria-label="Pagination">
      <button
        type="button"
        className="button secondary"
        disabled={loading || page <= 1}
        onClick={() => setPage(page - 1)}
      >
        Previous
      </button>
      <span className="small-text muted">
        Page {page} of {totalPages} · {(data?.count ?? 0).toLocaleString()} results
      </span>
      <button
        type="button"
        className="button secondary"
        disabled={loading || !data?.next}
        onClick={() => setPage(page + 1)}
      >
        Next
      </button>
    </nav>
  )
}

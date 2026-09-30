import { memo, useState } from 'react'
import { Search } from 'lucide-react'

/** Typing in the global search must not rerender the active reading screen. */
export const TopbarSearch = memo(function TopbarSearch() {
  const [search, setSearch] = useState('')
  return (
    <form
      className="topbar-search"
      role="search"
      aria-label="Catalog search"
      onSubmit={(event) => {
        event.preventDefault()
        window.location.hash = `/catalog?q=${encodeURIComponent(search)}`
      }}
    >
      <Search size={16} />
      <input
        aria-label="Search all books"
        type="search"
        maxLength={300}
        placeholder="Find a book…"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
    </form>
  )
})

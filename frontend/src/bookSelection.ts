export type SelectedBook = { id: number; title: string }
export const selectionLimit = 200

/** Keep click order across pages and collapse repeated country placements. */
export function addSelectedBooks(current: SelectedBook[], incoming: SelectedBook[]): SelectedBook[] {
  const books = new Map(current.map((book) => [book.id, book]))
  for (const book of incoming) {
    if (!books.has(book.id) && books.size < selectionLimit) books.set(book.id, book)
  }
  return [...books.values()]
}

export function parsePrivateLabels(value: string): string[] {
  return [
    ...new Set(
      value
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean),
    ),
  ]
}

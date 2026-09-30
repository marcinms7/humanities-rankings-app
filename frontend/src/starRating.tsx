import { useEffect, useId, useState } from 'react'
import { Star } from 'lucide-react'
import { api } from './api'
import { useApp } from './context'

export function BookRating({ work, title, rating }: { work: number; title: string; rating: number | null }) {
  const { mutate } = useApp()
  const name = useId()
  const [hover, setHover] = useState<number | null>(null)
  const [value, setValue] = useState(rating),
    [busy, setBusy] = useState(false)
  useEffect(() => setValue(rating), [rating])
  async function save(next: number | null) {
    setBusy(true)
    if (
      await mutate(
        () => api('/api/library/', 'POST', { work, rating: next }),
        next == null ? 'Rating cleared' : `Rated ${next} out of 10 stars · marked as read`,
      )
    )
      setValue(next)
    setBusy(false)
  }
  return (
    <fieldset className="visible-rating" disabled={busy}>
      <legend className="sr-only">Your private rating for {title}, out of 10</legend>
      <div className="visible-rating-row">
        <div className="visible-rating-stars" onMouseLeave={() => setHover(null)}>
          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
            <label
              className={`visible-star ${n <= (hover ?? value ?? 0) ? 'filled' : ''}`}
              key={n}
              onMouseEnter={() => setHover(n)}
              title={`Rate ${title} ${n} out of 10`}
            >
              <input
                className="sr-only"
                type="radio"
                name={name}
                checked={value === n}
                onChange={() => void save(n)}
                aria-label={`${title}: ${n} out of 10 stars`}
              />
              <Star
                size={16}
                aria-hidden="true"
                fill={n <= (hover ?? value ?? 0) ? 'currentColor' : 'none'}
              />
            </label>
          ))}
        </div>
        <div className="visible-rating-caption">
          <span role="status">{busy ? 'Saving…' : value == null ? 'Rate / 10' : `${value}/10`}</span>
          {value != null && (
            <button
              className="text-button"
              type="button"
              aria-label={`Clear rating for ${title}`}
              onClick={() => void save(null)}
            >
              Clear
            </button>
          )}
        </div>
      </div>
    </fieldset>
  )
}

import { APIError } from './api'

export function savedConflict(error: unknown): Record<string, unknown> | null {
  if (
    !(error instanceof APIError) ||
    error.status !== 409 ||
    !error.details ||
    typeof error.details !== 'object'
  )
    return null
  const value = error.details as { code?: string; current?: unknown }
  return value.code === 'edit_conflict' && value.current && typeof value.current === 'object'
    ? (value.current as Record<string, unknown>)
    : null
}

export function SaveConflict({
  current,
  accept,
}: {
  current: Record<string, unknown> | null
  accept: (version: string) => void
}) {
  if (!current || typeof current.edit_version !== 'string') return null
  const fields = [
    'title',
    'name',
    'status',
    'current_page',
    'rating',
    'notes',
    'started_on',
    'finished_on',
    'shelves',
    'personal_tags',
    'description',
    'authors',
    'form',
    'field',
    'original_year',
    'countries',
    'tags',
    'genres',
    'reading_load',
    'reading_effort_override',
    'difficulty_factors',
    'edition',
    'month',
    'pages',
    'locked',
  ]
  return (
    <section className="notice" role="alert">
      <strong>Saved values changed. Your form still contains your edits.</strong>
      <details>
        <summary>Compare with the currently saved values</summary>
        <dl>
          {fields
            .filter((key) => key in current)
            .map((key) => (
              <div key={key}>
                <dt>{key.replaceAll('_', ' ')}</dt>
                <dd style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                  {current[key] == null
                    ? 'Not set'
                    : typeof current[key] === 'object'
                      ? JSON.stringify(current[key], null, 2)
                      : String(current[key])}
                </dd>
              </div>
            ))}
        </dl>
      </details>
      <p>
        Review these values and edit your form as needed. Continuing keeps your form; the next save replaces
        the fields you submit.
      </p>
      <button
        type="button"
        className="button secondary"
        onClick={() => accept(current.edit_version as string)}
      >
        I reviewed the changes — keep my form
      </button>
    </section>
  )
}

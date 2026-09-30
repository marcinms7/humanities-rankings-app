import { DraftRecoveryNotice, useDraftRecovery } from './draftRecovery'
import { StudyHistory, type RecordHistoryMetadata } from './studyRecords'
import { useUnsavedChanges } from './unsavedChanges'
import { useEffect, useState } from 'react'
import type { Companion } from './classicalCompanion'
import { Empty } from './components'

type Translation = { id: string; name: string; credit: string; url: string; text: string }
type Passage = {
  id: string
  title: string
  work: number
  module: string
  reference: string
  language: string
  original: string
  original_credit: string
  original_url: string
  rights_url: string
  translations: Translation[]
  glossary: string[]
  prompts: { id: string; question: string }[]
  guidance: string
}
type Reception = {
  id: string
  title: string
  medium: string
  relationship: string
  from_work: number
  from_title: string
  to_work: number | null
  to_title: string
  body: string
  task: string
  sources: string[]
  modules: string[]
  glossary: string[]
}
export type DeskContent = {
  revision: string
  rights_note: string
  passages: Passage[]
  reception: Reception[]
  sources: Companion['sources']
}
type RecordValue = RecordHistoryMetadata & {
  revision: number
  translation: string
  notes?: string
  answers?: Record<string, string>
  updated_at: string
  history: Omit<RecordValue, 'history'>[]
}
export type DeskState = {
  reading_desk?: { note?: Record<string, RecordValue>; exercise?: Record<string, RecordValue> }
}
export { deskTabs } from './studyTabs'
const initialPassage = (content: DeskContent) =>
  content.passages.find((p) => p.id === new URLSearchParams(location.hash.split('?')[1]).get('passage')) ||
  content.passages[0]
const glossaryLinks = (ids: string[]) => (
  <div className="classical-links">
    {ids.map((id) => (
      <a className="text-link" key={id} href={`#/classical-education?tab=glossary&term=${id}`}>
        {id === 'arete' ? 'Aretē' : id} → glossary
      </a>
    ))}
  </div>
)
function History({ record }: { record?: RecordValue }) {
  return record ? (
    <details className="panel panel-body">
      <summary>
        Saved revision {record.revision} · {record._history_count ?? record.history.length} earlier revision
        {(record._history_count ?? record.history.length) === 1 ? '' : 's'}
      </summary>
      <p className="small-text muted">
        Saved {new Date(record.updated_at).toLocaleString()}. Previous text is retained, not overwritten.
      </p>
      <StudyHistory record={record} family="desk" fallback={record.history} title="Earlier revisions">
        {(rows) =>
          rows.map((r) => (
            <details key={r.revision}>
              <summary>
                Revision {r.revision} · {r.translation}
              </summary>
              <p className="classical-text">
                {r.notes ||
                  Object.entries(r.answers || {})
                    .map(([key, text]) => `${key}: ${text}`)
                    .join('\n\n')}
              </p>
            </details>
          ))
        }
      </StudyHistory>
    </details>
  ) : null
}

export function ClassicalReadingDesk({
  tab,
  content,
  state,
  busy,
  save,
  open,
  changeTab,
}: {
  tab: string
  content: DeskContent
  state: DeskState
  busy: boolean
  save: (update: object) => Promise<boolean>
  open: (id: string) => void
  changeTab: (tab: string) => void
}) {
  const [passageId, setPassageId] = useState(() => initialPassage(content).id)
  const passage = content.passages.find((p) => p.id === passageId) || content.passages[0]
  const [translationId, setTranslationId] = useState(passage.translations[0].id)
  const translation = passage.translations.find((t) => t.id === translationId) || passage.translations[0]
  const alternate = passage.translations.find((t) => t.id !== translation.id)!
  const note = state.reading_desk?.note?.[`${passage.id}:${translation.id}`]
  const exercise = state.reading_desk?.exercise?.[passage.id]
  const [notes, setNotes] = useState(note?.notes || ''),
    [answers, setAnswers] = useState<Record<string, string>>(exercise?.answers || {})
  const [noteDirty, setNoteDirty] = useState(false),
    [exerciseDirty, setExerciseDirty] = useState(false)
  const [noteRevision, setNoteRevision] = useState(note?.revision || 0),
    [exerciseRevision, setExerciseRevision] = useState(exercise?.revision || 0)
  const [reveal, setReveal] = useState(false),
    [hideTranslation, setHideTranslation] = useState(false),
    [large, setLarge] = useState(false),
    [message, setMessage] = useState('')
  const [search, setSearch] = useState(''),
    [medium, setMedium] = useState(''),
    [relationship, setRelationship] = useState('')
  const dirty = noteDirty || exerciseDirty
  useEffect(() => {
    if (!noteDirty) {
      setNotes(note?.notes || '')
      setNoteRevision(note?.revision || 0)
    }
  }, [note, noteDirty])
  useEffect(() => {
    if (!exerciseDirty) {
      setAnswers(exercise?.answers || {})
      setExerciseRevision(exercise?.revision || 0)
    }
  }, [exercise, exerciseDirty])
  const noteRecovery = useDraftRecovery({
    scope: `study-desk-note:${passage.id}:${translation.id}`,
    label: `${passage.title} · ${translation.name}: notes`,
    value: notes,
    dirty: noteDirty,
    baseVersion: String(noteRevision),
    restore: (value, revision) => {
      setNotes(value)
      setNoteRevision(Number(revision) || 0)
      setNoteDirty(true)
    },
  })
  const exerciseRecovery = useDraftRecovery({
    scope: `study-desk-exercise:${passage.id}`,
    label: `${passage.title}: translation comparison`,
    value: answers,
    dirty: exerciseDirty,
    baseVersion: String(exerciseRevision),
    restore: (value, revision) => {
      setAnswers(value)
      setExerciseRevision(Number(revision) || 0)
      setExerciseDirty(true)
    },
  })
  useUnsavedChanges(dirty)
  function choose(id: string, translator?: string) {
    if (busy || (dirty && !window.confirm('Discard unsaved passage notes and comparison answers?'))) return
    if (noteDirty) noteRecovery.saved()
    if (exerciseDirty) exerciseRecovery.saved()
    const p = content.passages.find((p) => p.id === id)!
    setPassageId(id)
    setTranslationId(translator || p.translations[0].id)
    setNoteDirty(false)
    setExerciseDirty(false)
    setReveal(false)
    setMessage('')
  }
  async function commit(action: 'note' | 'exercise') {
    const okay = await save({
      desk: {
        action,
        passage: passage.id,
        translation: translation.id,
        expected_revision: action === 'note' ? noteRevision : exerciseRevision,
        ...(action === 'note' ? { notes } : { answers }),
      },
    })
    if (okay) {
      if (action === 'note') {
        noteRecovery.saved()
        setNoteDirty(false)
      } else {
        exerciseRecovery.saved()
        setExerciseDirty(false)
      }
      setMessage('Saved privately. Reading completion and shared rankings are unchanged.')
    }
  }
  const rows = content.reception.filter(
    (r) =>
      (!medium || r.medium === medium) &&
      (!relationship || r.relationship === relationship) &&
      `${r.title} ${r.from_title} ${r.to_title} ${r.body}`.toLowerCase().includes(search.toLowerCase()),
  )
  return (
    <section aria-label="Classical reading desk and reception">
      {message && (
        <p className="notice" role="status">
          {message}
        </p>
      )}
      {['Reading desk', 'Translation lab'].includes(tab) && (
        <>
          <div className="section-header">
            <h2>{tab === 'Reading desk' ? 'Read beside the original' : 'Compare the same passage'}</h2>
            <a className="text-link" download href="/api/classical-education/?export=desk">
              Export passages & saved responses (.txt)
            </a>
          </div>
          <details className="panel panel-body">
            <summary>Passage scope, credits & reuse</summary>
            <p>{content.rights_note}</p>
          </details>
          <div className="toolbar">
            <label className="field">
              <span>Passage</span>
              <select
                className="select"
                disabled={busy}
                value={passage.id}
                onChange={(e) => choose(e.target.value)}
              >
                {content.passages.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title} · {p.reference}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Primary translation</span>
              <select
                className="select"
                disabled={busy}
                value={translation.id}
                onChange={(e) => choose(passage.id, e.target.value)}
              >
                {passage.translations.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={large} onChange={(e) => setLarge(e.target.checked)} /> Larger
              passage text
            </label>
            <button className="text-link" onClick={() => open(passage.module)}>
              Open syllabus module
            </button>
            <a className="text-link" href={`#/books/${passage.work}`}>
              Book & editions
            </a>
          </div>
          <p className="small-text muted">
            {passage.reference} · passage-level alignment, not word-for-word or line-for-line equivalence.
          </p>
          {tab === 'Reading desk' ? (
            <>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={hideTranslation}
                  onChange={(e) => setHideTranslation(e.target.checked)}
                />{' '}
                Hide translation while reading
              </label>
              <div className={`parallel-desk ${large ? 'large-text' : ''}`}>
                <article className="panel panel-body">
                  <h3>{passage.language === 'grc' ? 'Greek' : 'Latin'} original</h3>
                  <p className="parallel-text" lang={passage.language}>
                    {passage.original}
                  </p>
                  <details>
                    <summary>Original text credit</summary>
                    <p className="small-text muted">{passage.original_credit}</p>
                    <a className="text-link" target="_blank" rel="noreferrer" href={passage.original_url}>
                      Read source ↗
                    </a>{' '}
                    ·{' '}
                    <a className="text-link" target="_blank" rel="noreferrer" href={passage.rights_url}>
                      License / provider ↗
                    </a>
                  </details>
                </article>
                <article className="panel panel-body">
                  <h3>{translation.name}</h3>
                  {hideTranslation ? (
                    <button className="button secondary" onClick={() => setHideTranslation(false)}>
                      Reveal translation
                    </button>
                  ) : (
                    <p className="parallel-text" lang="en">
                      {translation.text}
                    </p>
                  )}
                  <p className="small-text muted">{translation.credit}</p>
                  <a className="text-link" target="_blank" rel="noreferrer" href={translation.url}>
                    Continue at the legal text source ↗
                  </a>
                </article>
              </div>
              {glossaryLinks(passage.glossary)}
              <form
                className="panel panel-body"
                onSubmit={(e) => {
                  e.preventDefault()
                  void commit('note')
                }}
              >
                <DraftRecoveryNotice
                  recovery={noteRecovery}
                  baseVersion={String(note?.revision || 0)}
                  busy={busy}
                />
                <label className="field">
                  <span>Your private passage notes · {translation.name}</span>
                  <textarea
                    className="input classical-notes"
                    maxLength={20000}
                    required
                    disabled={busy}
                    value={notes}
                    onChange={(e) => {
                      setNotes(e.target.value)
                      setNoteDirty(true)
                      setMessage('')
                    }}
                  />
                </label>
                <div className="toolbar">
                  <button className="button primary" disabled={busy || !noteDirty || !notes.trim()}>
                    Save passage notes
                  </button>
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => changeTab('Translation lab')}
                  >
                    Compare both translations →
                  </button>
                </div>
              </form>
              <History record={note} />
            </>
          ) : (
            <>
              <div className={`parallel-desk ${large ? 'large-text' : ''}`}>
                {[translation, alternate].map((t) => (
                  <article className="panel panel-body" key={t.id}>
                    <h3>{t.name}</h3>
                    <p className="parallel-text" lang="en">
                      {t.text}
                    </p>
                    <p className="small-text muted">{t.credit}</p>
                    <a className="text-link" href={t.url} target="_blank" rel="noreferrer">
                      Source ↗
                    </a>
                  </article>
                ))}
              </div>
              <button className="text-link" onClick={() => changeTab('Reading desk')}>
                ← Consult the original
              </button>
              <form
                className="panel panel-body"
                onSubmit={(e) => {
                  e.preventDefault()
                  void commit('exercise')
                }}
              >
                <p>
                  Write your observations before opening the discussion guidance. These are self-directed
                  exercises, not automatically graded translations.
                </p>
                <DraftRecoveryNotice
                  recovery={exerciseRecovery}
                  baseVersion={String(exercise?.revision || 0)}
                  busy={busy}
                />
                {passage.prompts.map((p) => (
                  <label className="field" key={p.id}>
                    <span>{p.question}</span>
                    <textarea
                      className="input"
                      rows={4}
                      required
                      maxLength={10000}
                      disabled={busy}
                      value={answers[p.id] || ''}
                      onChange={(e) => {
                        setAnswers({ ...answers, [p.id]: e.target.value })
                        setExerciseDirty(true)
                        setMessage('')
                      }}
                    />
                  </label>
                ))}
                <div className="toolbar">
                  <button
                    className="button primary"
                    disabled={busy || !exerciseDirty || passage.prompts.some((p) => !answers[p.id]?.trim())}
                  >
                    Save comparison
                  </button>
                  <button type="button" className="button secondary" onClick={() => setReveal(!reveal)}>
                    {reveal ? 'Hide' : 'Reveal'} discussion guidance
                  </button>
                </div>
                {reveal && <p className="notice">{passage.guidance}</p>}
              </form>
              <History record={exercise} />
            </>
          )}
        </>
      )}
      {tab === 'Reception trails' && (
        <>
          <h2>Ancient works, later transformations</h2>
          <p>
            Each connection has its own evidence label. Adaptation, allusion and thematic comparison are not
            interchangeable; these are branches, not a universal chain of influence.
          </p>
          <div className="toolbar">
            <input
              className="search-input"
              aria-label="Search reception trails"
              placeholder="Search works, creators or ideas…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select
              className="filter-select"
              aria-label="Reception medium"
              value={medium}
              onChange={(e) => setMedium(e.target.value)}
            >
              <option value="">All media</option>
              {[...new Set(content.reception.map((r) => r.medium))].map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
            <select
              className="filter-select"
              aria-label="Reception evidence type"
              value={relationship}
              onChange={(e) => setRelationship(e.target.value)}
            >
              <option value="">All relationship types</option>
              {[...new Set(content.reception.map((r) => r.relationship))].map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
            <button
              className="text-link"
              onClick={() => {
                setSearch('')
                setMedium('')
                setRelationship('')
              }}
            >
              Clear filters
            </button>
          </div>
          <div className="rankings-grid">
            {rows.map((r) => (
              <article className="panel panel-body" key={r.id}>
                <span className="pill muted">
                  {r.relationship} · {r.medium}
                </span>
                <h3>{r.title}</h3>
                <p>
                  <a className="text-link" href={`#/books/${r.from_work}`}>
                    {r.from_title}
                  </a>
                  <br />
                  {r.relationship === 'Thematic comparison only' ? '↔' : '→'}{' '}
                  {r.to_work ? (
                    <a className="text-link" href={`#/books/${r.to_work}`}>
                      {r.to_title}
                    </a>
                  ) : (
                    r.to_title
                  )}
                </p>
                <p>{r.body}</p>
                <p className="notice">{r.task}</p>
                {glossaryLinks(r.glossary)}
                {r.modules.map((m) => (
                  <button className="text-link" key={m} onClick={() => open(m)}>
                    Open {m} module
                  </button>
                ))}
                <details>
                  <summary>Evidence & access</summary>
                  {r.sources.length ? (
                    r.sources.map((id) => {
                      const s = content.sources.find((s) => s.id === id)!
                      return (
                        <p key={id}>
                          <a className="text-link" href={s.url} target="_blank" rel="noreferrer">
                            {s.title} ↗
                          </a>
                          <br />
                          <span className="small-text muted">
                            {s.access} · {s.checked}
                            <br />
                            {s.evidence}
                          </span>
                        </p>
                      )
                    })
                  ) : (
                    <p>
                      No historical influence evidence is claimed. This is a Marginalia editorial exercise.
                    </p>
                  )}
                </details>
              </article>
            ))}
          </div>
          {!rows.length && (
            <Empty title="No matching reception trails">Clear a filter to see the starter connections.</Empty>
          )}
          <p>
            <a className="text-link" href="#/trails?trail=tragedy-modern">
              Follow the connected drama reading trail →
            </a>
          </p>
        </>
      )}
    </section>
  )
}

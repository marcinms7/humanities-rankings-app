import { DraftRecoveryNotice, useDraftRecovery } from './draftRecovery'
import { useUnsavedChanges } from './unsavedChanges'
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { api, useResource } from './api'
import { useApp } from './context'
import { Empty, ErrorNotice, Loading, PageHeader, RankingCard } from './components'
import type { Ranking } from './types'
import type { StudyTools, ToolState } from './classicalStudyTools'
import type { Companion, CompanionState, StartingRoute, ClassicalPlan } from './classicalCompanion'
import type { LearningContent, LearningState, LearningSummary } from './classicalLearning'
import type { DeskContent, DeskState } from './classicalReadingDesk'
import { ClassicalNavigation } from './classicalNavigation'
import { companionTabs, learningTabs, deskTabs, toolsTabs } from './studyTabs'
import { applyStudyChanges, mergeStudySummary, type StudyChange } from './studyData'
import { queryCache } from './queryCache'
import { studyDependencies, type StudyFamily, type StudyRecordsPage } from './studyRecords'
const ClassicalStudyTools = lazy(() =>
  import('./classicalStudyTools').then((m) => ({ default: m.ClassicalStudyTools })),
)
const ClassicalCompanion = lazy(() =>
  import('./classicalCompanion').then((m) => ({ default: m.ClassicalCompanion })),
)
const ClassicalLearningTools = lazy(() =>
  import('./classicalLearning').then((m) => ({ default: m.ClassicalLearningTools })),
)
const ClassicalReadingDesk = lazy(() =>
  import('./classicalReadingDesk').then((m) => ({ default: m.ClassicalReadingDesk })),
)

type Path = 'light' | 'rigorous'
type Assignment = { hours: number; reading: string; exercise: string }
type Module = {
  id: string
  number: number
  title: string
  author: string
  subtitle: string
  stage: string
  periods: string[]
  subjects: string[]
  era: string
  language: string
  rationale: string
  prerequisites: string[]
  light: Assignment
  rigorous: Assignment
  support: string
  question: string
  refs: string[]
}
type Resource = { id: string; title: string; description: string; url: string }
type Course = {
  id: string
  title: string
  provider: string
  type: string
  summary: string
  description: string
  modules: string[]
  note: string
  url: string
}
type Study = {
  updated_at: string | null
  content: {
    revision: string
    modules: Module[]
    resources: Resource[]
    courses: Course[]
    expanded: { id: string; title: string; body: string }[]
    tools: StudyTools
    companion: Companion
    learning: LearningContent
    desk: DeskContent
  }
  state: ToolState & CompanionState & LearningState & DeskState
  path: Path
  pace: number
  completed: string[]
  ready: string[]
  total_hours: number
  total_weeks: number
  remaining_hours: number
  route: StartingRoute
  classical_plans: ClassicalPlan[]
  learning_summary: LearningSummary
}
const normalize = (s: string) =>
  s
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()

export function ClassicalEducation() {
  const { user } = useApp()
  const userId = user?.id
  const [data, setData] = useState<Study | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false)
  const [refreshNotice, setRefreshNotice] = useState('')
  const recordGeneration = useRef(0)
  const dataRef = useRef(data)
  dataRef.current = data
  const [recordPages, setRecordPages] = useState<
    Partial<
      Record<
        StudyFamily,
        { page: number; next: number | null; count: number; loading: boolean; error?: string }
      >
    >
  >({})
  const recordPagesRef = useRef(recordPages)
  recordPagesRef.current = recordPages
  const loadRecords = useCallback(async (family: StudyFamily, page = 1) => {
    if (!dataRef.current || recordPagesRef.current[family]?.loading) return
    const generation = recordGeneration.current
    const snapshot = dataRef.current.updated_at
    setRecordPages((old) => ({
      ...old,
      [family]: { page: old[family]?.page || 0, next: page, count: old[family]?.count || 0, loading: true },
    }))
    try {
      const params = new URLSearchParams({
        part: 'records',
        family,
        page: String(page),
        snapshot: snapshot || '',
      })
      const result = await api<StudyRecordsPage>(`/api/classical-education/?${params}`)
      if (generation !== recordGeneration.current) return
      if (!dataRef.current || dataRef.current.updated_at !== result.updated_at)
        throw new Error(
          'Saved study work changed during loading. Refresh saved work; your drafts remain here.',
        )
      setData((current) =>
        current
          ? {
              ...current,
              state: applyStudyChanges(
                current.state,
                result.results.map((row) => ({ path: row.path, value: row.value })),
              ),
            }
          : current,
      )
      setRecordPages((old) => ({
        ...old,
        [family]: { page, next: result.next_page, count: result.count, loading: false },
      }))
    } catch (error) {
      if (generation !== recordGeneration.current) return
      setError((error as Error).message)
      setRecordPages((old) => ({
        ...old,
        [family]: {
          page: old[family]?.page || 0,
          next: page,
          count: old[family]?.count || 0,
          loading: false,
          error: (error as Error).message,
        },
      }))
    }
  }, [])

  const [tab, setTab] = useState(() => {
      const q = new URLSearchParams(window.location.hash.split('?')[1])
      const tabs: Record<string, string> = {
        desk: 'Reading desk',
        translation: 'Translation lab',
        reception: 'Reception trails',
        glossary: 'Context & glossary',
        rankings: 'Rankings',
        plan: 'My classical plan',
        listening: 'Listening guide',
        courses: 'Courses & materials',
        recall: 'Recall & review',
        atlas: 'Historical atlas',
        essay: 'Essay workshop',
      }
      return q.has('work')
        ? 'Works & preparation'
        : tabs[q.get('tab') || ''] || (q.has('module') ? 'Syllabus' : 'Today’s study')
    }),
    [search, setSearch] = useState(''),
    [subject, setSubject] = useState(''),
    [period, setPeriod] = useState(''),
    [progress, setProgress] = useState('')
  const [selected, setSelected] = useState(
      new URLSearchParams(window.location.hash.split('?')[1]).get('module') || '',
    ),
    [notes, setNotes] = useState(''),
    [dirty, setDirty] = useState(false)
  useEffect(() => {
    let alive = true
    setData(null)
    setRecordPages({})
    setError('')
    if (userId)
      Promise.all([
        api<Pick<Study, 'content'>>('/api/classical-education/?part=content'),
        api<Omit<Study, 'content'>>('/api/classical-education/?part=summary'),
      ])
        .then(([content, state]) => ({ ...content, ...state }))
        .then((d) => {
          if (alive) {
            setData(d)
            const id = new URLSearchParams(window.location.hash.split('?')[1]).get('module')
            if (id) setNotes(d.state.modules?.[id]?.notes || '')
          }
        })
        .catch((e) => {
          if (alive) setError(e.message)
        })
    return () => {
      alive = false
      recordGeneration.current += 1
    }
  }, [userId])
  const hasData = !!data
  useEffect(() => {
    if (selected) document.querySelector('.classical-module')?.scrollIntoView({ block: 'start' })
  }, [selected, hasData])
  const family = deskTabs.includes(tab)
    ? 'desk'
    : learningTabs.includes(tab)
      ? 'learning'
      : companionTabs.includes(tab)
        ? 'companion'
        : toolsTabs.includes(tab)
          ? 'tools'
          : ''
  const [visited, setVisited] = useState<string[]>([])
  useEffect(() => {
    if (family) setVisited((old) => (old.includes(family) ? old : [...old, family]))
    if (tab === 'Edition guide')
      setVisited((old) => (old.includes('companion') ? old : [...old, 'companion']))
  }, [family, tab])
  const show = (name: string) =>
    family === name || visited.includes(name) || (name === 'companion' && tab === 'Edition guide')
  const dependencies = studyDependencies(tab, selected)
  const dependencyKey = dependencies.join(',')
  useEffect(() => {
    if (!hasData) return
    for (const family of dependencyKey.split(',').filter(Boolean) as StudyFamily[]) {
      if (!recordPagesRef.current[family]) void loadRecords(family)
    }
  }, [dependencyKey, hasData, loadRecords, recordPages])
  const recordsBusy = dependencies.some(
    (name) =>
      !recordPages[name]?.page ||
      recordPages[name]?.next != null ||
      recordPages[name]?.loading ||
      recordPages[name]?.error,
  )
  const moduleReady =
    !!recordPages.modules?.page &&
    recordPages.modules.next == null &&
    !recordPages.modules.loading &&
    !recordPages.modules.error
  useEffect(() => {
    if (!dirty && selected && moduleReady) setNotes(data?.state.modules?.[selected]?.notes || '')
  }, [data?.state.modules, selected, dirty, moduleReady])
  const moduleRecovery = useDraftRecovery({
    scope: selected ? `study-module:${selected}` : '',
    label: `${data?.content.modules.find((module) => module.id === selected)?.title || 'Module'}: notes`,
    value: notes,
    dirty,
    baseVersion: data?.updated_at || '',
    ready: moduleReady,
    restore: (value) => {
      setNotes(value)
      setDirty(true)
    },
  })
  useUnsavedChanges(dirty)
  async function save(update: object, savesNotes = false) {
    if (recordsBusy) {
      setError('Load the remaining saved records below before saving. Your draft is still here.')
      return false
    }
    setBusy(true)
    setError('')
    setRefreshNotice('')
    try {
      const d = await api<Omit<Study, 'content' | 'state'> & { changes: StudyChange[] }>(
        '/api/classical-education/?part=delta',
        'PATCH',
        { ...update, expected_updated_at: data?.updated_at ?? null },
      )
      setData((current) =>
        current ? { ...current, ...d, state: applyStudyChanges(current.state, d.changes) } : current,
      )
      if (savesNotes) {
        moduleRecovery.saved()
        setDirty(false)
      }
      return true
    } catch (e) {
      setError((e as Error).message)
      return false
    } finally {
      setBusy(false)
    }
  }
  async function refreshSaved() {
    recordGeneration.current += 1
    setBusy(true)
    setRefreshNotice('')
    try {
      queryCache.invalidate(['study-state'])
      const latest = await api<Omit<Study, 'content'>>('/api/classical-education/?part=summary')
      setData((current) =>
        current ? { ...current, ...latest, state: mergeStudySummary(current.state, latest.state) } : current,
      )
      setRecordPages({})
      // Module bodies reload separately; retained local drafts are never cleared.
      setError('')
      setRefreshNotice(
        'Saved study work refreshed. Your unsaved drafts are still here. Review the saved versions before saving a retained draft; essays and passage notes also check their own saved revision.',
      )
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  function open(id: string) {
    if (busy || (dirty && !window.confirm('Discard unsaved changes to this module’s notes?'))) return
    if (dirty) moduleRecovery.saved()
    setSelected(id)
    setNotes(data?.state.modules?.[id]?.notes || '')
    setDirty(false)
  }
  if (!user)
    return (
      <Empty title="Your private classical education">Sign in to open your syllabus and study notes.</Empty>
    )
  if (!data) return error ? <ErrorNotice>{error}</ErrorNotice> : <Loading />
  const { content, path, completed, ready } = data
  const modules = content.modules
  const active = modules.find((m) => m.id === selected)
  const next =
    modules.find((m) => ready.includes(m.id)) || modules.find((m) => !completed.includes(m.id)) || modules[0]
  const filtered = modules.filter(
    (m) =>
      (!subject || m.subjects.includes(subject)) &&
      (!period || m.periods.includes(period)) &&
      (!progress ||
        (progress === 'ready'
          ? ready.includes(m.id)
          : progress === 'complete'
            ? completed.includes(m.id)
            : !completed.includes(m.id))) &&
      normalize(JSON.stringify(m)).includes(normalize(search)),
  )
  const moduleLink = (id: string) => (
    <button className="text-link" key={id} onClick={() => open(id)}>
      {modules.find((m) => m.id === id)?.title || id}
    </button>
  )
  return (
    <>
      <PageHeader
        eyebrow="Your private study space"
        title="A classical education."
        actions={
          <a className="button secondary" href="/api/classical-education/?export=txt">
            Export syllabus & saved notes
          </a>
        }
      >
        Greek and Roman texts, and their afterlives. A guided path through reading, reflection and close study
        in English translation.
      </PageHeader>
      <ClassicalNavigation tab={tab} change={setTab} disabled={busy} />
      <div className="panel panel-body classical-intro">
        <div>
          <h2>A path of your own.</h2>
          <p>24 modules across six stages. Preparation is recommended, never a barrier to exploring.</p>
          <button className="button primary" onClick={() => open(next.id)}>
            {completed.length === modules.length
              ? 'Review'
              : completed.length
                ? 'Continue with'
                : 'Begin with'}{' '}
            {next.title}
          </button>
        </div>
        <div>
          <strong>
            {completed.length} / {modules.length} assignments completed
          </strong>
          <progress aria-label="Study progress" value={completed.length} max={modules.length} />
          <p className="small-text muted">
            {data.total_hours} estimated hours · about {data.total_weeks} weeks at {data.pace} hours/week
            <br />
            {data.remaining_hours} estimated hours remaining
          </p>
        </div>
      </div>
      <div className="toolbar">
        <label className="field">
          <span>Study path</span>
          <select
            className="select"
            value={path}
            disabled={busy}
            onChange={(e) => void save({ path: e.target.value })}
          >
            <option value="light">Lighter</option>
            <option value="rigorous">Rigorous</option>
          </select>
        </label>
        <label className="field">
          <span>Weekly study hours</span>
          <select
            className="select"
            value={data.pace}
            disabled={busy}
            onChange={(e) => void save({ pace: Number(e.target.value) })}
          >
            {[3, 4, 6, 8].map((n) => (
              <option key={n} value={n}>
                {n} hours
              </option>
            ))}
          </select>
        </label>
        <p className="small-text muted">
          Estimates include assigned study activities, but exclude optional courses and sustained language
          learning. This is an independent syllabus, without accreditation or external marking.
        </p>
      </div>
      {error && (
        <>
          <ErrorNotice>{error}</ErrorNotice>
          <button className="button secondary" disabled={busy} onClick={() => void refreshSaved()}>
            Refresh saved work and keep drafts
          </button>
        </>
      )}
      {refreshNotice && (
        <p className="notice" role="status">
          {refreshNotice}
        </p>
      )}
      {refreshNotice && dirty && selected && moduleReady && (
        <details className="panel panel-body">
          <summary>Latest saved notes for this module</summary>
          <p className="classical-text">{data.state.modules?.[selected]?.notes || 'No saved notes yet.'}</p>
          <p className="small-text muted">
            Your editor still contains your unsaved draft. Saving it replaces these notes.
          </p>
        </details>
      )}
      {dependencies.map((name) => {
        const status = recordPages[name]
        return (
          (!status || status.loading || status.next != null || status.error) && (
            <section className="panel panel-body" key={name} aria-live="polite">
              <p>
                {status?.loading
                  ? `Loading saved ${name}…`
                  : `Saved ${name}: ${Math.min((status?.page || 0) * 24, status?.count || 0)} of ${status?.count || 0} records loaded.`}{' '}
                Earlier revisions open separately.
              </p>
              {status?.error && <ErrorNotice>{status.error}</ErrorNotice>}
              {!status?.loading && (
                <button
                  className="button secondary"
                  onClick={() => void loadRecords(name, status?.next || 1)}
                >
                  {status?.error ? 'Retry saved records' : 'Load more saved records'}
                </button>
              )}
            </section>
          )
        )
      })}
      <div hidden={!deskTabs.includes(tab)}>
        {show('desk') && (
          <Suspense fallback={<Loading />}>
            <ClassicalReadingDesk
              tab={tab}
              content={content.desk}
              state={data.state}
              busy={busy || recordsBusy}
              save={save}
              open={open}
              changeTab={setTab}
            />
          </Suspense>
        )}
      </div>
      {tab === 'Rankings' && <ClassicalRankings />}
      <div hidden={!learningTabs.includes(tab)}>
        {show('learning') && (
          <Suspense fallback={<Loading />}>
            <ClassicalLearningTools
              tab={tab}
              content={content.learning}
              companion={content.companion}
              state={data.state}
              summary={data.learning_summary}
              modules={modules}
              resources={content.resources}
              busy={busy || recordsBusy}
              save={save}
              open={open}
              changeTab={setTab}
            />
          </Suspense>
        )}
      </div>
      <div
        hidden={
          ![
            'Edition guide',
            'Timeline',
            'Languages',
            'Notebook',
            'Passage exercises',
            'Art & archaeology',
            'Study sources',
          ].includes(tab)
        }
      >
        {show('tools') && (
          <Suspense fallback={<Loading />}>
            <ClassicalStudyTools
              tab={tab}
              tools={content.tools}
              modules={modules}
              state={data.state}
              busy={busy || recordsBusy}
              save={save}
              open={open}
            />
          </Suspense>
        )}
      </div>
      <div hidden={!companionTabs.includes(tab) && tab !== 'Edition guide'}>
        {show('companion') && (
          <Suspense fallback={<Loading />}>
            <ClassicalCompanion
              tab={tab}
              content={content.companion}
              state={data.state}
              modules={modules}
              route={data.route}
              plans={data.classical_plans}
              pace={data.pace}
              busy={busy || recordsBusy}
              save={save}
              open={open}
            />
          </Suspense>
        )}
      </div>
      {active && (
        <section className="panel panel-body">
          <h3>Ranked works connected to {active.title}</h3>
          <p className="small-text muted">
            Related readings, not a claim that every work below is assigned in full.
          </p>
          <div className="classical-links">
            {content.companion.works
              .filter((w) => w.modules.includes(active.id))
              .map((w) => (
                <a key={w.id} className="text-link" href={`#/books/${w.id}`}>
                  #{w.position} · {w.title}
                </a>
              ))}
          </div>
          <p>
            <a
              className="text-link"
              href={`#/rankings/${content.companion.ranking_id}?group=classical-education`}
            >
              Open ranking, evidence & revisions
            </a>
          </p>
        </section>
      )}
      {active && (
        <section className="panel classical-module" aria-label={`Study module: ${active.title}`}>
          <div className="panel-header">
            <h2>
              {active.number}. {active.title}
            </h2>
            <button className="button secondary small" onClick={() => open('')}>
              Close module
            </button>
          </div>
          <div className="panel-body">
            <p>
              {active.author} · {active.subtitle}
            </p>
            <p className="small-text muted">
              {active.era} · {active.language}
            </p>
            <p>{active.rationale}</p>
            <div className="notice">
              <strong>
                {path === 'light' ? 'Lighter' : 'Rigorous'} assignment · {active[path].hours} estimated hours
              </strong>
              <p>{active[path].reading}</p>
            </div>
            <h3>Supporting study</h3>
            <p>{active.support}</p>
            <h3>Study question</h3>
            <p>{active.question}</p>
            <h3>Written work & practice</h3>
            <p>{active[path].exercise}</p>
            <p className="small-text muted">Self-directed work; no external assessment is included.</p>
            <h3>Recommended preparation</h3>
            <div className="classical-links">
              {active.prerequisites.length
                ? active.prerequisites.map(moduleLink)
                : 'No prior module recommended.'}
            </div>
            <h3>Prepares you for</h3>
            <div className="classical-links">
              {modules.filter((m) => m.prerequisites.includes(active.id)).map((m) => moduleLink(m.id))}
            </div>
            <h3>Reading resources</h3>
            {active.refs.map((id) => {
              const r = content.resources.find((r) => r.id === id)!
              return (
                <p key={id}>
                  <a className="text-link" href={r.url} target="_blank" rel="noreferrer">
                    {r.title} ↗
                  </a>
                  <br />
                  <span className="small-text muted">{r.description}</span>
                </p>
              )
            })}
            <DraftRecoveryNotice recovery={moduleRecovery} baseVersion={data.updated_at || ''} busy={busy} />
            <label className="field">
              <span>Your private notes · shared between paths</span>
              <textarea
                className="input classical-notes"
                maxLength={20000}
                value={notes}
                disabled={busy || !moduleReady}
                onChange={(e) => {
                  setNotes(e.target.value)
                  setDirty(true)
                }}
              />
            </label>
            <div className="toolbar">
              <button
                className="button secondary"
                disabled={busy || !moduleReady || !dirty}
                onClick={() => void save({ module: active.id, notes }, true)}
              >
                {busy ? 'Saving…' : dirty ? 'Save notes' : 'Notes saved'}
              </button>
              <button
                className="button primary"
                disabled={busy || !moduleReady}
                onClick={() =>
                  void save(
                    { module: active.id, path, completed: !completed.includes(active.id), notes },
                    true,
                  )
                }
              >
                {completed.includes(active.id) ? 'Mark assignment unfinished' : 'Mark assignment complete'}
              </button>
              <span className="small-text muted">
                Completion applies only to this {path === 'light' ? 'Lighter' : 'Rigorous'} assignment, not
                every work in it.
              </span>
            </div>
            <div className="toolbar">
              <button
                className="button secondary small"
                disabled={active.number === 1 || busy}
                onClick={() => open(modules[active.number - 2].id)}
              >
                ← Previous module
              </button>
              <button
                className="button secondary small"
                disabled={active.number === modules.length || busy}
                onClick={() => open(modules[active.number].id)}
              >
                Next module →
              </button>
            </div>
          </div>
        </section>
      )}
      {(tab === 'Syllabus' || tab === 'Reading order') && (
        <>
          <div className="toolbar">
            <input
              className="search-input"
              aria-label="Search syllabus"
              placeholder="Search authors, assignments, questions…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select
              className="filter-select"
              aria-label="Syllabus subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            >
              <option value="">All subjects</option>
              {[...new Set(modules.flatMap((m) => m.subjects))].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
            <select
              className="filter-select"
              aria-label="Syllabus period"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              <option value="">All periods</option>
              {[...new Set(modules.flatMap((m) => m.periods))].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
            <select
              className="filter-select"
              aria-label="Syllabus progress"
              value={progress}
              onChange={(e) => setProgress(e.target.value)}
            >
              <option value="">All progress</option>
              <option value="ready">Ready to read</option>
              <option value="unfinished">Not completed</option>
              <option value="complete">Completed</option>
            </select>
            <button
              className="text-link"
              onClick={() => {
                setSearch('')
                setSubject('')
                setPeriod('')
                setProgress('')
              }}
            >
              Clear filters
            </button>
          </div>
          {!filtered.length && (
            <Empty title="No matching modules">Clear the filters to explore the full syllabus.</Empty>
          )}
          {[...new Set(filtered.map((m) => m.stage))].map((stage) => (
            <section key={stage}>
              <div className="section-header">
                <h2>{stage}</h2>
              </div>
              <div className={tab === 'Syllabus' ? 'rankings-grid' : 'classical-order'}>
                {filtered
                  .filter((m) => m.stage === stage)
                  .map((m) => (
                    <article className="panel panel-body" key={m.id}>
                      <span className="small-text muted">
                        {String(m.number).padStart(2, '0')} · {m[path].hours} hours ·{' '}
                        {completed.includes(m.id)
                          ? 'Completed'
                          : ready.includes(m.id)
                            ? 'Ready to read'
                            : 'Preparation suggested'}
                      </span>
                      <h3>{moduleLink(m.id)}</h3>
                      <p>
                        {m.author} · {m.subtitle}
                      </p>
                      {tab === 'Syllabus' ? (
                        <p className="small-text muted">{m[path].reading}</p>
                      ) : (
                        <div className="classical-links">
                          <span className="small-text muted">Preparation:</span>
                          {m.prerequisites.length ? m.prerequisites.map(moduleLink) : 'Start here'}
                        </div>
                      )}
                    </article>
                  ))}
              </div>
            </section>
          ))}
        </>
      )}
      {tab === 'Course options' && (
        <>
          <p className="notice">
            Four external options from the handoff. Provider details were reportedly checked on 13 September
            2026; current availability and fees have not been rechecked here. Courses do not automatically
            complete modules.
          </p>
          <div className="rankings-grid">
            {content.courses.map((c) => (
              <article className="panel panel-body" key={c.id}>
                <span className="small-text muted">
                  {c.provider} · {c.type}
                </span>
                <h2>{c.title}</h2>
                <p>{c.summary}</p>
                <p>{c.description}</p>
                <p className="small-text muted">{c.note}</p>
                <div className="classical-links">{c.modules.map(moduleLink)}</div>
                <p>
                  <a className="text-link" href={c.url} target="_blank" rel="noreferrer">
                    Visit course provider ↗
                  </a>
                </p>
              </article>
            ))}
          </div>
        </>
      )}
      {tab === 'Expanded curriculum' && (
        <>
          <p className="notice">
            Proposed expansion. These areas preserve the draft’s full content, but new assignments, textbooks,
            feedback arrangements and workload still need development. The introductory 24-module route
            remains available above.
          </p>
          {content.expanded
            .filter((s) => /^[FGH]/.test(s.id))
            .map((s) => (
              <details className="panel panel-body classical-proposal" key={s.id}>
                <summary>
                  {s.id} · {s.title} <span className="pill muted">Proposed</span>
                </summary>
                <div className="classical-text">{s.body}</div>
              </details>
            ))}
        </>
      )}
      {tab === 'Sources & approach' && (
        <>
          <p>
            The Paideia handoff supplies this editorial syllabus and its exact passage assignments. Original
            resource links retain the handoff’s access limitations. The Study sources tab records the separate
            checks for the new study tools. Your notes and assignment progress are saved privately in your
            Marginalia account. Progress from the former app was not included in the handoff.
          </p>
          <div className="rankings-grid">
            {content.resources.map((r) => (
              <article className="panel panel-body" key={r.id}>
                <a className="text-link" href={r.url} target="_blank" rel="noreferrer">
                  {r.title} ↗
                </a>
                <p>{r.description}</p>
              </article>
            ))}
          </div>
          {content.expanded
            .filter((s) => /^[IJK]/.test(s.id))
            .map((s) => (
              <details className="panel panel-body classical-proposal" key={s.id}>
                <summary>
                  {s.id} · {s.title}
                </summary>
                <div className="classical-text">{s.body}</div>
              </details>
            ))}
        </>
      )}
    </>
  )
}

function ClassicalRankings() {
  const { version } = useApp()
  const resource = useResource<Ranking[]>('/api/rankings/?group=research', version, true)
  const rankings = resource.data?.filter((r) => r.slug === 'classical-education-guide') || []
  const published = rankings.some((r) => r.entry_count)
  return (
    <section aria-label="Classical education rankings">
      <div className="section-header">
        <h2>Works for a classical education</h2>
      </div>
      <p>
        {published
          ? 'A research-led ranking of Greek and Roman works and their later reception. Open it to browse the entries, sources and revision history.'
          : 'A home for the forthcoming researched ranking of Greek and Roman works and their later reception. Open a ranking to browse its entries, sources and revision history.'}
      </p>
      {!published && (
        <p className="notice">
          Awaiting your ranking report. The syllabus provides a study sequence; this ranking will compare the
          works’ importance and educational value.
        </p>
      )}
      {resource.error && <ErrorNotice>{resource.error}</ErrorNotice>}
      {resource.loading ? (
        <Loading />
      ) : (
        <div className="rankings-grid">
          {rankings.map((r) => (
            <RankingCard key={r.id} ranking={r} detailGroup="classical-education" />
          ))}
        </div>
      )}
    </section>
  )
}

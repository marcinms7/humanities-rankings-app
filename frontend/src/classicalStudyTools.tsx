import { DraftRecoveryNotice, useDraftRecovery } from './draftRecovery'
import { draftBaseVersion } from './draftStore'
import { useUnsavedChanges } from './unsavedChanges'
import { useEffect, useState } from 'react'
import { Empty } from './components'

type Source = {
  id: string
  title: string
  url: string
  access: string
  evidence: string
  limitations: string
  checked: string
}
type Item = { id: string; title: string; modules: string[]; sources: string[] }
type Activity = Item & {
  task: string
  rubric: string[]
  scope?: string
  language?: string
  level?: string
  prerequisites?: string[]
  skill?: string
  date?: string
  culture?: string
  material?: string
  image?: string
  credit?: string
  context?: string
}
export type StudyTools = {
  revision: string
  sources: Source[]
  editions: (Item & { format: string; use: string; caveat: string })[]
  timeline: (Item & { year: number; date: string; kind: string; description: string })[]
  language: Activity[]
  exercises: Activity[]
  gallery: Activity[]
}
export type ToolState = {
  activities?: Record<string, Record<string, { response?: string; done?: boolean }>>
  modules?: Record<string, { notes?: string }>
}
type Module = {
  id: string
  title: string
  author: string
  era: string
  stage: string
  support: string
  subjects: string[]
  refs: string[]
}
type Props = {
  tab: string
  tools: StudyTools
  modules: Module[]
  state: ToolState
  busy: boolean
  save: (update: object) => Promise<boolean>
  open: (id: string) => void
}
const normalize = (s: string) =>
  s
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
const years: Record<string, number> = {
  iliad: -750,
  odyssey: -725,
  hesiod: -700,
  herodotus: -450,
  tragedy: -458,
  comedy: -431,
  thucydides: -400,
  socrates: -380,
  republic: -375,
  aristotle: -350,
  rhetoric: -335,
  hellenistic: -300,
  alexander: -150,
  'republic-history': -50,
  cicero: -63,
  aeneid: -29,
  ovid: -50,
  stoics: 50,
  empire: 100,
  augustine: 397,
  dante: 1300,
  shakespeare: 1599,
  milton: 1667,
  walcott: 1990,
}

export function ClassicalStudyTools({ tab, tools, modules, state, busy, save, open }: Props) {
  const [search, setSearch] = useState(''),
    [filter, setFilter] = useState('all')
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const stored = state.activities?.[tools.revision] || {}
  const dirty = Object.keys(drafts).some((id) => drafts[id] !== (stored[id]?.response || ''))
  const draftRecovery = useDraftRecovery({
    scope: `study-activities:${tools.revision}`,
    label: 'Study activity responses',
    value: drafts,
    dirty,
    baseVersion: draftBaseVersion(stored),
    restore: (value) => setDrafts(value),
  })
  useUnsavedChanges(dirty)
  useEffect(() => {
    setFilter('all')
    setSearch('')
  }, [tab])
  const matches = (value: unknown) => normalize(JSON.stringify(value)).includes(normalize(search))
  const links = (ids: string[]) => (
    <div className="classical-links">
      {ids.map((id) => (
        <button className="text-link" key={id} onClick={() => open(id)}>
          {modules.find((m) => m.id === id)?.title || id}
        </button>
      ))}
    </div>
  )
  const refs = (ids: string[]) => (
    <details className="classical-citations">
      <summary>Sources & access notes</summary>
      {ids.map((id) => {
        const s = tools.sources.find((s) => s.id === id)
        return (
          s && (
            <p key={id}>
              <a className="text-link" href={s.url} target="_blank" rel="noreferrer">
                {s.title} ↗
              </a>
              <br />
              <span className="small-text muted">
                {s.access} · Checked {s.checked}
                <br />
                {s.evidence}
                <br />
                {s.limitations}
              </span>
            </p>
          )
        )
      })}
    </details>
  )
  async function storeActivity(item: Activity, done?: boolean) {
    const response = drafts[item.id] ?? stored[item.id]?.response ?? ''
    const ok = await save({ activity: item.id, response, ...(done === undefined ? {} : { done }) })
    if (ok) {
      const next = { ...drafts }
      delete next[item.id]
      if (Object.keys(next).length) draftRecovery.checkpoint(next)
      else draftRecovery.saved()
      setDrafts(next)
    }
  }
  const editor = (item: Activity) => (
    <details className="classical-response">
      <summary>Your response & self-check {stored[item.id]?.done ? '· Completed' : ''}</summary>
      <ul>
        {item.rubric.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <label className="field">
        <span>Private response · save before leaving this page</span>
        <textarea
          className="input classical-notes"
          maxLength={20000}
          disabled={busy}
          value={drafts[item.id] ?? stored[item.id]?.response ?? ''}
          onChange={(e) => setDrafts((old) => ({ ...old, [item.id]: e.target.value }))}
        />
      </label>
      <div className="toolbar">
        <button
          className="button secondary small"
          disabled={
            busy || drafts[item.id] === undefined || drafts[item.id] === (stored[item.id]?.response || '')
          }
          onClick={() => void storeActivity(item)}
        >
          Save response
        </button>
        <button
          className="button primary small"
          disabled={busy}
          onClick={() => void storeActivity(item, !stored[item.id]?.done)}
        >
          {stored[item.id]?.done ? 'Mark unfinished' : 'Mark activity complete'}
        </button>
      </div>
      <p className="small-text muted">
        Self-reported practice only. This does not certify proficiency or complete a syllabus module.
      </p>
    </details>
  )
  const activityCard = (item: Activity) => (
    <article key={item.id} className="panel panel-body">
      <span className="pill muted">
        {item.language || item.skill || item.culture}
        {stored[item.id]?.done ? ' · Completed' : ''}
      </span>
      <h3>{item.title}</h3>
      {item.image ? (
        <figure className="classical-art">
          <img src={item.image} alt={item.title} loading="lazy" />
          <figcaption>{item.credit}</figcaption>
        </figure>
      ) : (
        item.credit && <p className="small-text muted">{item.credit}</p>
      )}
      {item.date && (
        <p>
          {item.date} · {item.material}
        </p>
      )}
      {item.level && <p className="small-text muted">{item.level}</p>}
      {item.prerequisites?.length ? (
        <p className="small-text muted">
          Suggested preparation:{' '}
          {item.prerequisites.map((id) => tools.language.find((i) => i.id === id)?.title).join(', ')}.{' '}
          {item.prerequisites.every((id) => stored[id]?.done)
            ? 'Preparation marked complete.'
            : 'You can explore ahead.'}
        </p>
      ) : null}
      {item.scope && (
        <p>
          <strong>Assignment:</strong> {item.scope}
        </p>
      )}
      {item.context && <p>{item.context}</p>}
      <p>{item.task}</p>
      {links(item.modules)}
      {refs(item.sources)}
      {editor(item)}
    </article>
  )
  const activityRows =
    tab === 'Languages' ? tools.language : tab === 'Passage exercises' ? tools.exercises : tools.gallery
  const notebook = [
    ...modules
      .filter((m) => state.modules?.[m.id]?.notes)
      .map((m) => ({
        id: m.id,
        title: m.title,
        type: 'Module notes',
        text: state.modules![m.id].notes!,
        module: m.id,
      })),
    ...[...tools.language, ...tools.exercises, ...tools.gallery]
      .filter((i) => stored[i.id]?.response)
      .map((i) => ({
        id: i.id,
        title: i.title,
        type: i.language ? 'Language practice' : i.skill ? 'Passage exercise' : 'Museum study',
        text: stored[i.id].response!,
        module: i.modules[0],
      })),
  ]
  return (
    <section aria-label={tab}>
      <div className="section-header">
        <h2>{tab}</h2>
      </div>
      <DraftRecoveryNotice recovery={draftRecovery} baseVersion={draftBaseVersion(stored)} busy={busy} />
      {dirty && (
        <p className="notice">
          You have unsaved activity responses. Switching these study tabs keeps drafts here; save them before
          leaving Classical education.
        </p>
      )}
      <div className="toolbar">
        <input
          className="search-input"
          aria-label={`Search ${tab}`}
          placeholder={`Search ${tab.toLowerCase()}…`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {tab === 'Languages' && (
          <select
            className="filter-select"
            aria-label="Language route"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">Both languages</option>
            <option>Greek</option>
            <option>Latin</option>
          </select>
        )}
        {tab === 'Timeline' && (
          <select
            className="filter-select"
            aria-label="Timeline type"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">Works & events</option>
            <option value="works">Works and authors</option>
            <option value="events">Historical events & objects</option>
          </select>
        )}
        {tab === 'Notebook' && (
          <select
            className="filter-select"
            aria-label="Notebook type"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All notes</option>
            {[...new Set(notebook.map((n) => n.type))].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        )}
      </div>
      {tab === 'Edition guide' && (
        <>
          <p>
            Practical starting choices and comparison resources. Check that your edition includes the exact
            assigned passages and stable book, line or section references. The recommendations below are
            editorial judgments based on the cited edition descriptions.
          </p>
          <div className="rankings-grid">
            {tools.editions.filter(matches).map((e) => (
              <article className="panel panel-body" key={e.id}>
                <h3>{e.title}</h3>
                <span className="small-text muted">{e.format}</span>
                <p>{e.use}</p>
                <p className="small-text muted">{e.caveat}</p>
                {links(e.modules)}
                {refs(e.sources)}
              </article>
            ))}
          </div>
          <details className="panel panel-body">
            <summary>Edition checklist for the other syllabus modules</summary>
            <p>
              Before obtaining a copy: confirm complete versus selected contents, translator, annotation
              level, reference numbering and the edition named in your assignment. Poetry needs line
              references; philosophy often uses standard section references; fragmentary works need an
              explained numbering system.
            </p>
            {modules.filter(matches).map((m) => (
              <p key={m.id}>
                <button className="text-link" onClick={() => open(m.id)}>
                  {m.title}
                </button>
                <br />
                <span className="small-text muted">{m.support}</span>
              </p>
            ))}
          </details>
        </>
      )}
      {tab === 'Timeline' && (
        <>
          <p>
            Chronological overview, separate from the recommended reading order. Work dates below come from
            the supplied syllabus and may cover multiple authors; placement is approximate. Historical events
            have separately checked sources.
          </p>
          <ol className="classical-timeline">
            {[
              ...(filter !== 'events'
                ? modules.map((m) => ({
                    id: m.id,
                    year: years[m.id] || 1,
                    date: m.era,
                    title: `${m.author} · ${m.title}`,
                    kind: 'Work / composition context',
                    description:
                      'Date/context retained from the Paideia handoff. Some combined modules span several dates; this sorting point is only an approximate aid.',
                    modules: [m.id],
                    sources: [] as string[],
                  }))
                : []),
              ...(filter !== 'works' ? tools.timeline : []),
            ]
              .filter(matches)
              .sort((a, b) => a.year - b.year)
              .map((t) => (
                <li key={t.id}>
                  <span className="small-text muted">
                    {t.kind} · {t.date}
                  </span>
                  <h3>{t.title}</h3>
                  <p>{t.description}</p>
                  {links(t.modules)}
                  {t.sources.length > 0 && refs(t.sources)}
                </li>
              ))}
          </ol>
        </>
      )}
      {tab === 'Languages' && (
        <p className="notice">
          Two independent routes: linked introductory lessons, sustained textbook study, then guided reading.
          The short introductions are not complete language courses. Provider materials contain the teaching
          and exercises; use these cards to plan, record corrections and track practice. Hours are additional
          to the syllabus estimates.
        </p>
      )}
      {tab === 'Passage exercises' && (
        <p>
          Original Marginalia activities using the cited texts. Read the specified passage externally, then
          save your response and use the self-check criteria. These activities offer practice, not external
          marking.
        </p>
      )}
      {tab === 'Art & archaeology' && (
        <p>
          Study objects and sites as evidence: begin with observation, then test an interpretation against
          context. Museum photography and reconstructions are not substitutes for the original setting.
        </p>
      )}
      {['Languages', 'Passage exercises', 'Art & archaeology'].includes(tab) && (
        <div className="rankings-grid">
          {activityRows
            .filter((i) => matches(i) && (tab !== 'Languages' || filter === 'all' || i.language === filter))
            .map(activityCard)}
        </div>
      )}
      {tab === 'Notebook' && (
        <>
          <p>
            Search saved module notes and study responses together. Edit module notes through the linked
            module; edit activity responses in their study tab. Your TXT export includes all saved notes.
          </p>
          {notebook.filter((n) => matches(n) && (filter === 'all' || n.type === filter)).length ? (
            notebook
              .filter((n) => matches(n) && (filter === 'all' || n.type === filter))
              .map((n) => (
                <article className="panel panel-body" key={n.type + n.id}>
                  <span className="small-text muted">{n.type}</span>
                  <h3>{n.title}</h3>
                  <p className="classical-text">{n.text}</p>
                  {links([n.module])}
                </article>
              ))
          ) : (
            <Empty title="No matching saved notes">
              Save a module note or study response and it will appear here.
            </Empty>
          )}
        </>
      )}
      {tab === 'Study sources' && (
        <>
          {tools.sources.filter(matches).map((s) => (
            <article className="panel panel-body" key={s.id}>
              <a className="text-link" href={s.url} target="_blank" rel="noreferrer">
                {s.title} ↗
              </a>
              <p>{s.evidence}</p>
              <p className="small-text muted">
                {s.access} · Checked {s.checked}
                <br />
                {s.limitations}
              </p>
            </article>
          ))}
        </>
      )}
    </section>
  )
}

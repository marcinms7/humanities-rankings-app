import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react'
import { api, useResource } from './api'
import { useApp } from './context'
import { BookRow, Empty, ErrorNotice, Loading, PageHeader, localMonth } from './components'
import { BookRating } from './starRating'
import type { LibraryItem } from './types'

type QueuePreview = {items: {work: number; title: string; pages: number | null}[]; skipped: {title: string; reason: string}[]; applied: boolean}
export function ReadNext() {
  const {version, mutate, notify} = useApp()
  const [genre] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] || '').get('genre') || '')
  const library = useResource<LibraryItem[]>(`/api/library/?genre=${encodeURIComponent(genre)}`, version, true)
  const [month, setMonth] = useState(localMonth()), [preview, setPreview] = useState<QueuePreview | null>(null), [busy, setBusy] = useState(false)
  useEffect(() => setPreview(null), [month, version])
  const rows = (library.data || []).filter(i => i.read_next_position != null).sort((a,b) => a.read_next_position! - b.read_next_position!)
  async function change(item: number, action: string) {
    setBusy(true)
    await mutate(() => api('/api/read-next/', 'POST', {item, action}), 'Read next saved')
    setBusy(false)
  }
  async function send(apply: boolean) {
    setBusy(true)
    try {
      const result = await api<QueuePreview>('/api/read-next/plan/', 'POST', {month: `${month}-01`, apply, genre})
      if (apply) await mutate(async () => null, `${result.items.length} books added to your plan`)
      setPreview(result)
    } catch (e) { notify((e as Error).message, true) } finally { setBusy(false) }
  }
  return <><PageHeader eyebrow="A little intention" title="Read next.">Choose books using “Read next” in My books, then put your shortlist in order here.</PageHeader>{library.error && <ErrorNotice>{library.error}</ErrorNotice>}{library.loading && !library.data ? <Loading/> : !rows.length ? <Empty title="What would you like to read next?">Open My books and add a few favourites to your shortlist.</Empty> : <><section className="panel">{rows.map((item,index) => <div className="library-item" key={item.id}><BookRow work={item.book} index={index + 1} action={<><button className="icon-button" disabled={busy || index === 0} aria-label={`Move ${item.book.title} up`} onClick={() => void change(item.id,'up')}><ArrowUp size={18}/></button><button className="icon-button" disabled={busy || index === rows.length - 1} aria-label={`Move ${item.book.title} down`} onClick={() => void change(item.id,'down')}><ArrowDown size={18}/></button><button className="icon-button" disabled={busy} aria-label={`Remove ${item.book.title} from shortlist`} onClick={() => void change(item.id,'remove')}><Trash2 size={18}/></button></>}/><BookRating work={item.work} title={item.book.title} rating={item.rating}/></div>)}</section><section className="panel panel-body"><h2>Send to your reading plan</h2><p>Append this order to the month below. Existing allocations, including locked books, stay untouched. Books already planned in any month are skipped. Your shortlist stays saved.</p><p className="small-text muted">This is a manual allocation of remaining pages, not a capacity-balanced suggestion. Check your monthly budget in the planner afterwards. Unknown page counts remain unallocated.</p><div className="toolbar"><label className="field"><span>Reading month</span><input className="input" type="month" required value={month} onChange={e => {setMonth(e.target.value); setPreview(null)}}/></label><button className="button secondary" disabled={busy || !month} onClick={() => void send(false)}>Preview additions</button><a className="button secondary" href="#/planner">Open reading plan</a></div>{preview && <div aria-live="polite">{preview.items.map(i => <p key={i.work}>{i.title} · {i.pages == null ? 'pages not allocated' : `${i.pages} pages`}</p>)}{preview.skipped.map(i => <p className="small-text muted" key={i.title}>{i.title}: {i.reason}</p>)}{!preview.items.length && <p>No new books to add.</p>}{!preview.applied && preview.items.length > 0 && <button className="button primary" disabled={busy} onClick={() => void send(true)}>Add {preview.items.length} books in this order</button>}{preview.applied && <p>Saved. Open your reading plan to review capacity.</p>}</div>}</section></>}</>
}

type AnnualRow = {year: number; books: number; unique_books: number; pages: number; unknown_pages: number; book_goal: number | null; page_goal: number | null}
type Annual = {years: AnnualRow[]; undated_completions: number}
export function ReadingGoals() {
  const {version, mutate} = useApp()
  const resource = useResource<Annual>('/api/annual-reading/', version)
  const [year, setYear] = useState(String(new Date().getFullYear())), [busy, setBusy] = useState(false)
  const selected = resource.data?.years.find(row => row.year === Number(year))
  return <><PageHeader eyebrow="Your own pace" title="Goals & reading years.">Optional targets, with room for a reading life that changes.</PageHeader>{resource.error && <ErrorNotice>{resource.error}</ErrorNotice>}{!resource.data ? <Loading/> : <><section className="panel panel-body"><h2>Set a yearly goal</h2><label className="field"><span>Year</span><input className="input" type="number" min={1900} max={2200} value={year} onChange={e => setYear(e.target.value)}/></label><form key={`${year}-${version}`} onSubmit={async e => {e.preventDefault(); const f = new FormData(e.currentTarget); setBusy(true); await mutate(() => api('/api/annual-reading/', 'PATCH', {year: Number(year), books: f.get('books') ? Number(f.get('books')) : null, pages: f.get('pages') ? Number(f.get('pages')) : null}), 'Yearly goals saved'); setBusy(false)}}><div className="form-grid"><label className="field"><span>Books to finish (optional)</span><input className="input" name="books" type="number" min={1} max={1000000} defaultValue={selected?.book_goal ?? ''} placeholder="No target"/></label><label className="field"><span>Pages in completed books (optional)</span><input className="input" name="pages" type="number" min={1} max={100000000} defaultValue={selected?.page_goal ?? ''} placeholder="No target"/></label></div><p className="small-text muted">Leave either target blank to turn it off. Rereads count as completed readings. Pages are credited in the finish year, not logged daily; unfinished books are excluded. Missing lengths use the recorded final page where available.</p><button className="button primary" disabled={busy || Number(year) < 1900 || Number(year) > 2200}>Save goals</button></form></section><section className="panel panel-body"><h2>How much you read each year</h2><p className="small-text muted">{resource.data.undated_completions} completed readings have no finish date and cannot be assigned to a year. Edit the dates of current library entries in My books; undated archived attempts remain excluded.</p><div className="annual-table-wrap"><table className="annual-table"><thead><tr><th>Year</th><th>Books finished</th><th>Unique books</th><th>Pages in finished books</th><th>Goal progress</th></tr></thead><tbody>{resource.data.years.map(row => <tr key={row.year}><th scope="row">{row.year}</th><td>{row.books}</td><td>{row.unique_books}</td><td>{row.pages.toLocaleString()}{row.unknown_pages > 0 && <small className="muted"> + {row.unknown_pages} unknown lengths</small>}</td><td>{row.book_goal != null && <GoalProgress current={row.books} goal={row.book_goal} unit="books"/>}{row.page_goal != null && <GoalProgress current={row.pages} goal={row.page_goal} unit="pages"/>}{row.book_goal == null && row.page_goal == null && <span className="muted">No target</span>}</td></tr>)}</tbody></table></div></section></>}</>
}
function GoalProgress({current, goal, unit}: {current: number; goal: number; unit: string}) {
  return <div className="year-goal"><span>{current.toLocaleString()} / {goal.toLocaleString()} {unit} · {Math.round(current / goal * 100)}%</span><progress aria-label={`${unit} goal`} max={goal} value={Math.min(current,goal)}/></div>
}

import { BookRating } from './starRating'
import { useState } from 'react'
import { api, useResource } from './api'
import { useApp } from './context'
import { ErrorNotice, label } from './components'
import type { LibraryItem, Work } from './types'

type Attempt = {id: number; work_id: number; work__title: string; status: string; current_page: number; rating: number | null; notes: string; started_on: string | null; finished_on: string | null; edition_id: number | null}

export function ReadingHistory({work}: {work?: number}) {
  const {user, version} = useApp()
  const history = useResource<Attempt[]>(user ? `/api/library/history/${work ? `?work=${work}` : ''}` : null, version)
  return <section className="panel"><div className="panel-header"><h2>Previous reading attempts</h2></div><div className="panel-body">{history.error && <ErrorNotice>{history.error}</ErrorNotice>}{history.data?.map(a => <details className="source-card" key={a.id}><summary>{a.work__title} · {label(a.status)}{a.rating != null ? ` · ★ ${a.rating}/10` : ''}</summary><p>{a.started_on || 'Start date not recorded'} — {a.finished_on || 'Finish date not recorded'} · {a.current_page} pages</p><p>{a.edition_id ? `Edition #${a.edition_id}` : 'Edition not recorded'}</p><p style={{whiteSpace: 'pre-wrap'}}>{a.notes || 'No notes recorded'}</p></details>)}{!history.loading && !history.data?.length && <p className="muted">Previous attempts appear here when you start a reread or remove a book from your library.</p>}</div></section>
}

export function QuickReading({work, item}: {work: Work; item?: LibraryItem}) {
  const {mutate} = useApp()
  const [busy, setBusy] = useState(false)

  return <><section className="panel"><div className="panel-header"><h2>Your reading</h2></div><div className="panel-body"><BookRating work={work.id} title={work.title} rating={item?.rating ?? null}/>{item && <><p className="small-text">{label(item.status)} · {item.current_page} pages</p><p className="small-text">Started: {item.started_on || 'Not recorded'}<br/>Finished: {item.finished_on || 'Not recorded'}</p>{['finished', 'abandoned'].includes(item.status) && <button className="button secondary" disabled={busy} onClick={async () => {setBusy(true); await mutate(() => api(`/api/library/${item.id}/reread/`, 'POST'), 'New reading attempt started; previous attempt saved'); setBusy(false)}}>Start reread</button>}<a className="button secondary" href="#/library">Edit progress and dates</a></>}</div></section><ReadingHistory work={work.id} /></>
}

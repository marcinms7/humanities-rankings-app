import { useResource } from './api'
import type { ClassicalWork } from './classicalCompanion'

export function ClassicalWorkPreparation({ id }: { id: number }) {
  const resource = useResource<{
    work: ClassicalWork
    modules: { id: string; title: string; prerequisites: string[] }[]
    module_titles: Record<string, string>
  }>(`/api/classical-education/?work=${id}`, 0)
  if (!resource.data) return null
  const { work, modules, module_titles } = resource.data
  return (
    <section className="panel panel-body">
      <h2>Classical study guide</h2>
      <p>{work.beginner_start}</p>
      <p className="small-text muted">
        Starter guidance from your supplied Top 250; recommended preparation is optional.
      </p>
      {modules.map((m) => (
        <p key={m.id}>
          <a className="text-link" href={`#/classical-education?module=${m.id}`}>
            {m.title} →
          </a>
          <br />
          <span className="small-text muted">
            Preparation:{' '}
            {m.prerequisites.map((id) => module_titles[id]).join(', ') || 'No prior module recommended'}
          </span>
        </p>
      ))}
      {!modules.length && (
        <p className="small-text muted">Independent extension: no syllabus module assigned yet.</p>
      )}
      <a className="text-link" href={`#/classical-education?work=${id}`}>
        Open study space & plan this reading →
      </a>
    </section>
  )
}

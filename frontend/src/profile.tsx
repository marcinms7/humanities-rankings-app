import { DraftRecoverySettings } from './draftRecovery'
import { useState } from 'react'
import { api } from './api'
import { useApp } from './context'
import { Empty, PageHeader } from './components'
import { ReadingPaceForm } from './readingPace'
import type { User } from './types'

export function Profile() {
  const { user, setUser, notify, requireLogin } = useApp()
  const [busy, setBusy] = useState(false)
  if (!user)
    return (
      <Empty
        title="Your reading profile."
        action={
          <button className="button primary" onClick={requireLogin}>
            Sign in
          </button>
        }
      >
        Keep your pace, preferences, and lists in one place.
      </Empty>
    )
  return (
    <>
      <PageHeader eyebrow="Your own way of reading" title="A little more like you.">
        Set your reading pace and keep your personal space comfortable.
      </PageHeader>
      <div className="profile-grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Reading profile</h2>
            <span className="pill muted">Private</span>
          </div>
          <div className="panel-body">
            <form
              onSubmit={async (e) => {
                e.preventDefault()
                setBusy(true)
                const f = new FormData(e.currentTarget)
                try {
                  const updated = await api<User>('/api/profile/', 'PATCH', {
                    display_name: f.get('name'),
                    words_per_minute: Number(f.get('words')),
                  })
                  setUser(updated)
                  notify('Profile saved')
                } catch (error) {
                  notify((error as Error).message, true)
                } finally {
                  setBusy(false)
                }
              }}
            >
              <label className="field">
                <span>Display name</span>
                <input className="input" name="name" defaultValue={user.display_name} />
              </label>
              <label className="field">
                <span>Baseline reading speed · words per minute</span>
                <input
                  className="input"
                  name="words"
                  key={user.words_per_minute}
                  type="number"
                  min={20}
                  max={2000}
                  defaultValue={user.words_per_minute}
                  required
                />
                <small className="muted">
                  A starting pace for lighter reading. The estimator adjusts for a work’s reading effort.
                </small>
              </label>
              <div className="form-actions">
                <button className="button primary" disabled={busy}>
                  {busy ? 'Saving…' : 'Save profile'}
                </button>
              </div>
            </form>
            <hr />
            <h3>Your reading rhythm</h3>
            <ReadingPaceForm user={user} />
          </div>
        </section>
        <section className="panel">
          <div className="panel-header">
            <h2>Your data</h2>
          </div>
          <div className="panel-body">
            <p>
              Your library, bookmarks, lists, progress, notes, reading plan, and settings are saved to your
              account in the database. They persist when you close the app. Sharing a list gives access only
              to that selected list. The shared catalog is protected from deletion; administrators can archive
              records.
            </p>
            <p>
              Download your full private record, including reading history, planner carryovers, saved filters,
              personal list revisions and classical study notes, essays and exercises.
            </p>
            <div className="reading-actions">
              <a className="button primary" href="/api/export/?download=zip" download>
                Download private archive
              </a>
              <a className="button secondary" href="/api/export/" download>
                Download JSON
              </a>
            </div>
            <p className="small-text muted">
              The archive includes a manifest and catalog references. It excludes passwords, sharing tokens,
              other readers’ data and image files. Keep database backups for restoration.
            </p>
            <hr />
            <DraftRecoverySettings />
            {user.is_staff && (
              <>
                <hr />
                <h3>Catalog administration</h3>
                <p className="small-text muted">
                  Manage editions, people, source records, and other catalog details.
                </p>
                <div className="reading-actions">
                  <a className="button secondary" href="#/catalog-review">
                    Review catalog issues
                  </a>
                  <a className="button secondary" href="/admin/">
                    Open administration
                  </a>
                </div>
              </>
            )}
          </div>
        </section>
      </div>
    </>
  )
}

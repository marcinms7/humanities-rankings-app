import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  BookOpen,
  Bookmark,
  CalendarDays,
  Check,
  Compass,
  Feather,
  Globe2,
  Landmark,
  Library,
  ListOrdered,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Search,
  Settings2,
  Sun,
  Users,
  X,
} from 'lucide-react'
import { api, installQueryLifecycle, setQueryAccount } from './api'
import { RouteErrorBoundary } from './errorBoundary'
import { TopbarSearch } from './topbar'
import { AppContext } from './context'
import { ErrorNotice, Loading, Modal } from './components'
const ClassicalEducation = lazy(() =>
  import('./classicalEducation').then((module) => ({ default: module.ClassicalEducation })),
)
const SourceExplorer = lazy(() =>
  import('./discovery').then((module) => ({ default: module.SourceExplorer })),
)
const ReadingTrails = lazy(() =>
  import('./readingTrails').then((module) => ({ default: module.ReadingTrails })),
)
const PersonalDiscovery = lazy(() =>
  import('./readingTrails').then((module) => ({ default: module.PersonalDiscovery })),
)
const Authors = lazy(() => import('./catalog').then((module) => ({ default: module.Authors })))
const Catalog = lazy(() => import('./catalog').then((module) => ({ default: module.Catalog })))
const CatalogAtlas = lazy(() => import('./catalogAtlas').then((module) => ({ default: module.CatalogAtlas })))
const PublishedComparison = lazy(() =>
  import('./publishedComparison').then((module) => ({ default: module.PublishedComparison })),
)
const Explore = lazy(() => import('./catalog').then((module) => ({ default: module.Explore })))
const WorkDetail = lazy(() => import('./catalog').then((module) => ({ default: module.WorkDetail })))
const Rankings = lazy(() => import('./rankings').then((module) => ({ default: module.Rankings })))
const RankingDetail = lazy(() => import('./rankings').then((module) => ({ default: module.RankingDetail })))
const SharedList = lazy(() => import('./rankings').then((module) => ({ default: module.SharedList })))
const MyLibrary = lazy(() => import('./library').then((module) => ({ default: module.MyLibrary })))
const Planner = lazy(() => import('./library').then((module) => ({ default: module.Planner })))
const Today = lazy(() => import('./today').then((module) => ({ default: module.Today })))
const Profile = lazy(() => import('./profile').then((module) => ({ default: module.Profile })))
const CatalogReview = lazy(() =>
  import('./catalogReview').then((module) => ({ default: module.CatalogReview })),
)
const Operations = lazy(() => import('./operations').then((module) => ({ default: module.Operations })))
import type { Theme, User } from './types'
import { confirmDiscardUnsavedChanges } from './unsavedChanges'
import './styles.css'
import './accessibility.css'
import {
  installScrollHistory,
  navigationEvent,
  useMobileNavigation,
  useRouteAccessibility,
} from './navigation'

function Authentication({ setup, done }: { setup: boolean; done: (user: User) => void }) {
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false)
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        const f = new FormData(e.currentTarget)
        try {
          const response = await api<{ user: User }>('/api/session/', 'POST', {
            action: setup ? 'setup' : 'login',
            username: f.get('username'),
            password: f.get('password'),
            display_name: f.get('display_name') || '',
          })
          done(response.user)
        } catch (err) {
          setError((err as Error).message)
        } finally {
          setBusy(false)
        }
      }}
    >
      {error && <ErrorNotice>{error}</ErrorNotice>}
      {setup && (
        <label className="field">
          <span>What should we call you?</span>
          <input
            className="input"
            name="display_name"
            autoComplete="given-name"
            placeholder="Your name"
            maxLength={100}
          />
        </label>
      )}
      <label className="field">
        <span>Username</span>
        <input
          className="input"
          name="username"
          autoComplete="username"
          required
          maxLength={150}
          placeholder="Choose your username"
        />
      </label>
      <label className="field">
        <span>Password</span>
        <input
          className="input"
          name="password"
          type="password"
          autoComplete={setup ? 'new-password' : 'current-password'}
          minLength={setup ? 8 : undefined}
          required
          placeholder={setup ? 'At least 8 characters' : 'Your password'}
        />
      </label>
      {setup && (
        <p className="small-text muted">
          This creates your local owner account. Reading notes, plans, and preferences are private by default.
        </p>
      )}
      <div className="form-actions">
        <button className="button primary" disabled={busy}>
          {busy ? 'Opening your library…' : setup ? 'Create my reading space' : 'Sign in'}
        </button>
      </div>
      {!setup && (
        <p className="small-text">
          <a href="/accounts/password-reset/">Forgot password?</a> ·{' '}
          <a href="/accounts/register/">Create an account</a>
        </p>
      )}
    </form>
  )
}

function App() {
  const [user, setUserState] = useState<User | null>(null),
    [setup, setSetup] = useState(false),
    [loaded, setLoaded] = useState(false),
    [fatal, setFatal] = useState('')
  const [version, setVersion] = useState(0),
    [hash, setHash] = useState(location.hash),
    [loginOpen, setLoginOpen] = useState(false),
    [mobileOpen, setMobileOpen] = useState(false)
  const [toast, setToast] = useState<{ message: string; error: boolean } | null>(null)
  const accountRef = useRef<number | null>(null)
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem('marginalia-theme') as Theme) || 'system'
    } catch {
      return 'system'
    }
  })
  const reload = useCallback(() => setVersion((v) => v + 1), [])
  const notify = useCallback((message: string, error = false) => setToast({ message, error }), [])
  const setUser = useCallback(
    (value: User | null) => {
      if (accountRef.current !== (value?.id ?? null)) setToast(null)
      accountRef.current = value?.id ?? null
      setQueryAccount(value?.id ?? null)
      setUserState(value)
      if (value) setTheme(value.theme)
      reload()
    },
    [reload],
  )
  useEffect(installQueryLifecycle, [])
  useEffect(installScrollHistory, [])
  const closeMobile = useCallback(() => setMobileOpen(false), [])
  useMobileNavigation(mobileOpen, closeMobile, loaded)
  useRouteAccessibility(hash, loaded && !fatal)
  useEffect(() => {
    let alive = true
    const channel =
      typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('marginalia-session')
    const sync = () => {
      api<{ user: User | null; setup_required: boolean }>('/api/session/')
        .then((response) => {
          if (!alive) return
          setUser(response.user)
          setSetup(response.setup_required)
          setLoaded(true)
          setFatal('')
        })
        .catch((error) => {
          if (alive && error.name !== 'AbortError') {
            setFatal(error.message)
            setLoaded(true)
          }
        })
    }
    const changedHere = () => channel?.postMessage('session-changed')
    if (channel)
      channel.onmessage = () => {
        // A different tab signed in/out. Hide the previous private view before
        // asking the server which account now owns this browser session.
        setQueryAccount(null, true)
        accountRef.current = null
        setUserState(null)
        setLoaded(false)
        sync()
      }
    window.addEventListener('marginalia-session-changed', changedHere)
    sync()
    return () => {
      alive = false
      channel?.close()
      window.removeEventListener('marginalia-session-changed', changedHere)
    }
  }, [setUser])
  useEffect(() => {
    const listener = () => {
      if (location.hash === hash) return
      if (!confirmDiscardUnsavedChanges()) {
        history.replaceState(null, '', `${location.pathname}${location.search}${hash}`)
        return
      }
      setHash(location.hash)
      setMobileOpen(false)
    }
    window.addEventListener('hashchange', listener)
    window.addEventListener('popstate', listener)
    window.addEventListener(navigationEvent, listener)
    return () => {
      window.removeEventListener('hashchange', listener)
      window.removeEventListener('popstate', listener)
      window.removeEventListener(navigationEvent, listener)
    }
  }, [hash])
  useEffect(() => {
    const media = matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      document.documentElement.dataset.theme = theme === 'system' ? (media.matches ? 'dark' : 'light') : theme
      try {
        localStorage.setItem('marginalia-theme', theme)
      } catch {
        /* Optional storage can be unavailable in private browsing. */
      }
    }
    apply()
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [theme])
  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 6500)
    return () => clearTimeout(timer)
  }, [toast])
  const requireLogin = useCallback(() => {
    if (user) return true
    setLoginOpen(true)
    return false
  }, [user])
  const mutate = useCallback(
    async (operation: () => Promise<unknown>, message?: string) => {
      const account = accountRef.current
      try {
        await operation()
        if (account !== accountRef.current) return false
        reload()
        if (message) notify(message)
        return true
      } catch (error) {
        if (account === accountRef.current && (error as Error).name !== 'AbortError')
          notify((error as Error).message, true)
        return false
      }
    },
    [notify, reload],
  )
  const contextValue = useMemo(
    () => ({ user, version, reload, setUser, notify, requireLogin, mutate }),
    [user, version, reload, setUser, notify, requireLogin, mutate],
  )
  const changeTheme = (value: Theme) => {
    setTheme(value)
    if (user)
      void api<User>('/api/profile/', 'PATCH', { theme: value })
        .then(setUserState)
        .catch((e) => notify(e.message, true))
  }
  const done = (value: User) => {
    setUser(value)
    setSetup(false)
    setLoginOpen(false)
  }
  const route = useMemo(
    () =>
      new URL(
        hash.slice(1) || (user?.home_page === 'today' ? '/today' : '/explore'),
        'https://marginalia.local',
      ),
    [hash, user?.home_page],
  )
  const segments = route.pathname.split('/').filter(Boolean),
    current = segments[0] || 'explore',
    id = segments[1]
  const sharedToken =
    !hash || hash === '#' ? location.pathname.match(/^\/shared\/([a-f0-9-]+)\/?$/)?.[1] : undefined
  const nav = [
    { route: 'explore', title: 'Explore', icon: Compass },
    { route: 'rankings', title: 'Researched rankings', icon: ListOrdered },
    { route: 'published-rankings', title: 'Published rankings', icon: ListOrdered },
    { route: 'collections', title: 'Reading collections', icon: Library },
    { route: 'trails', title: 'Reading trails', icon: Compass },
    { route: 'sources', title: 'Source explorer', icon: Search },
    { route: 'catalog', title: 'Book catalog', icon: BookOpen },
    { route: 'atlas', title: 'Atlas & timeline', icon: Globe2 },
    { route: 'authors', title: 'Authors & thinkers', icon: Users },
    { route: 'classical-education', title: 'Classical education', icon: Landmark },
  ]
  const activeNav =
    current === 'published-comparison'
      ? 'published-rankings'
      : current === 'rankings' && id
        ? route.searchParams.get('group') || 'rankings'
        : current
  const personalNav = [
    { route: 'today', title: 'Today', icon: Sun },
    { route: 'library', title: 'My library', icon: BookOpen },
    { route: 'discover', title: 'Discover for me', icon: Search },
    { route: 'my-lists', title: 'My lists', icon: ListOrdered },
    { route: 'saved', title: 'Bookmarked rankings', icon: Bookmark },
    { route: 'planner', title: 'Reading plan', icon: CalendarDays },
  ]
  const adminNav = user?.is_staff
    ? [
        { route: 'catalog-review', title: 'Catalog review', icon: Settings2 },
        { route: 'operations', title: 'Operations', icon: Settings2 },
      ]
    : []
  const routePage = useMemo(() => {
    if (sharedToken) return <SharedList token={sharedToken} />
    switch (current) {
      case 'rankings':
        return id ? (
          <RankingDetail
            key={id}
            id={id}
            personalView={route.searchParams.get('view') === 'bookmarked'}
            returnGroup={route.searchParams.get('group') || undefined}
          />
        ) : (
          <Rankings />
        )
      case 'classical-education':
        return <ClassicalEducation key={route.search} />
      case 'published-rankings':
        return <Rankings key="published" mode="published" />
      case 'published-comparison':
        return <PublishedComparison />
      case 'collections':
        return <Rankings key="collections" mode="collections" />
      case 'my-lists':
        return <Rankings key="my-lists" mode="my-lists" />
      case 'saved':
        return <Rankings key="saved" mode="saved" />
      case 'sources':
        return <SourceExplorer key={route.search} />
      case 'catalog':
        return <Catalog />
      case 'atlas':
        return <CatalogAtlas />
      case 'books':
        return id ? <WorkDetail key={id} id={id} /> : <Catalog />
      case 'authors':
        return <Authors key={id || 'index'} id={id} />
      case 'library':
        return <MyLibrary />
      case 'planner':
        return <Planner />
      case 'profile':
        return <Profile />
      case 'trails':
        return <ReadingTrails key={route.search} />
      case 'discover':
        return <PersonalDiscovery key={route.search} />
      case 'today':
        return <Today />
      case 'catalog-review':
        return <CatalogReview />
      case 'operations':
        return <Operations />
      default:
        return <Explore />
    }
  }, [current, id, route, sharedToken])
  let page = routePage
  if (!loaded) return <Loading />
  if (fatal)
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <ErrorNotice>{fatal}</ErrorNotice>
          <button className="button primary" onClick={() => location.reload()}>
            Try again
          </button>
        </div>
      </div>
    )
  if (setup && !sharedToken)
    page = (
      <div className="auth-shell">
        <section className="auth-aside">
          <div className="auth-brand">
            <Feather size={24} />
            Marginalia
          </div>
          <span className="eyebrow">A considered reading life</span>
          <h1>
            Great books.
            <br />
            Lasting ideas.
            <br />
            Your own way.
          </h1>
          <p>A quiet place to discover, collect, and make time for the works that matter to you.</p>
          <div className="hero-art auth-book-art" aria-hidden="true">
            <span className="spine spine1" />
            <span className="spine spine2" />
            <span className="spine spine3" />
          </div>
        </section>
        <section className="auth-card">
          <span className="eyebrow">Welcome to your first chapter</span>
          <h2>Make yourself at home.</h2>
          <p className="muted">Create your account to begin.</p>
          <Authentication setup done={done} />
        </section>
      </div>
    )
  return (
    <AppContext.Provider value={contextValue}>
      {setup && !sharedToken ? (
        page
      ) : (
        <div className="app-shell">
          <a
            className="skip-link"
            href="#main-content"
            onClick={(event) => {
              event.preventDefault()
              document.getElementById('main-content')?.focus()
            }}
          >
            Skip to main content
          </a>
          {mobileOpen && (
            <button className="scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />
          )}
          <aside id="site-navigation" className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
            <button
              className="icon-button mobile-nav-close"
              aria-label="Close navigation"
              onClick={closeMobile}
            >
              <X size={20} />
            </button>
            <a className="brand" href="#/explore">
              <span className="brand-mark">
                <Feather size={25} strokeWidth={1.4} />
              </span>
              <span>
                <span className="brand-name">Marginalia</span>
                <span className="brand-caption">A considered reading life</span>
              </span>
            </a>
            <nav className="nav-list" aria-label="Main navigation">
              {nav.map((n) => (
                <a
                  className={`nav-link ${activeNav === n.route ? 'active' : ''}`}
                  key={n.route}
                  href={`#/${n.route}`}
                  aria-current={activeNav === n.route ? 'page' : undefined}
                >
                  <n.icon size={18} strokeWidth={1.6} />
                  {n.title}
                </a>
              ))}
              <div className="nav-section-label">Your reading space</div>
              {personalNav.map((n) => (
                <a
                  className={`nav-link ${activeNav === n.route ? 'active' : ''}`}
                  key={n.route}
                  href={`#/${n.route}`}
                  aria-current={activeNav === n.route ? 'page' : undefined}
                >
                  <n.icon size={18} strokeWidth={1.6} />
                  {n.title}
                </a>
              ))}
              {adminNav.length > 0 && (
                <>
                  <div className="nav-section-label">Administration</div>
                  {adminNav.map((n) => (
                    <a
                      className={`nav-link ${activeNav === n.route ? 'active' : ''}`}
                      key={n.route}
                      href={`#/${n.route}`}
                      aria-current={activeNav === n.route ? 'page' : undefined}
                    >
                      <n.icon size={18} strokeWidth={1.6} />
                      {n.title}
                    </a>
                  ))}
                </>
              )}
            </nav>
            <div className="sidebar-footer">
              <div className="theme-toggle" role="group" aria-label="Color theme">
                {(
                  [
                    { key: 'light', icon: Sun, text: 'Light mode' },
                    { key: 'dark', icon: Moon, text: 'Dark mode' },
                    { key: 'system', icon: Monitor, text: 'System theme' },
                  ] as const
                ).map((t) => (
                  <button
                    key={t.key}
                    className={theme === t.key ? 'active' : ''}
                    aria-label={t.text}
                    aria-pressed={theme === t.key}
                    onClick={() => changeTheme(t.key)}
                  >
                    <t.icon size={16} />
                  </button>
                ))}
              </div>
              {user ? (
                <a className="user-chip" href="#/profile">
                  <span className="avatar">{(user.display_name || user.username)[0].toUpperCase()}</span>
                  <span>
                    <strong>{user.display_name || user.username}</strong>
                    <small>Your reading profile</small>
                  </span>
                  <Settings2 size={16} />
                </a>
              ) : (
                <button className="button primary" onClick={() => setLoginOpen(true)}>
                  Sign in
                </button>
              )}
            </div>
          </aside>
          <div className="main-shell">
            <header className="topbar">
              <div className="breadcrumbs">
                <button
                  className="icon-button mobile-menu-button"
                  aria-label="Open navigation"
                  aria-expanded={mobileOpen}
                  aria-controls="site-navigation"
                  onClick={() => setMobileOpen(true)}
                >
                  <Menu size={21} />
                </button>
                <span>Your reading room</span>
                <span>/</span>
                <strong>
                  {sharedToken
                    ? 'Shared list'
                    : [...nav, ...personalNav, ...adminNav].find((n) => n.route === activeNav)?.title ||
                      (current === 'profile' ? 'Profile' : 'Details')}
                </strong>
              </div>
              <div className="topbar-actions">
                <TopbarSearch />
                <button
                  className="icon-button"
                  aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                  onClick={() =>
                    changeTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark')
                  }
                >
                  {document.documentElement.dataset.theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
                </button>
                {user && (
                  <button
                    className="icon-button"
                    aria-label="Sign out"
                    onClick={() => {
                      if (confirmDiscardUnsavedChanges())
                        void mutate(async () => {
                          await api('/api/session/', 'POST', { action: 'logout' })
                          setUser(null)
                        }, 'Signed out')
                    }}
                  >
                    <LogOut size={17} />
                  </button>
                )}
              </div>
            </header>
            <main className="page" id="main-content" tabIndex={-1} key={user?.id ?? 'guest'}>
              <RouteErrorBoundary key={`${route.pathname}${route.search}`}>
                <Suspense fallback={<Loading />}>{page}</Suspense>
              </RouteErrorBoundary>
            </main>
          </div>
        </div>
      )}
      {loginOpen && (
        <Modal title="Welcome back" close={() => setLoginOpen(false)}>
          <Authentication setup={false} done={done} />
        </Modal>
      )}
      {toast && (
        <div className={`toast ${toast.error ? 'error' : ''}`} role={toast.error ? 'alert' : 'status'}>
          {toast.error ? <X size={17} /> : <Check size={17} />}
          <span>{toast.message}</span>
          <button className="icon-button" aria-label="Dismiss notification" onClick={() => setToast(null)}>
            <X size={14} />
          </button>
        </div>
      )}
    </AppContext.Provider>
  )
}

createRoot(document.getElementById('root')!).render(<App />)

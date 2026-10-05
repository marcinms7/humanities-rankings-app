import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

/** A failed route/chunk keeps navigation and account controls available. */
export class RouteErrorBoundary extends Component<
  { children: ReactNode; resetKey: string },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep diagnostics local. Never transmit private study content to a logger.
    console.error('Unable to render the current screen.', error, info.componentStack)
  }

  componentDidUpdate(previous: Readonly<{ children: ReactNode; resetKey: string }>) {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) this.setState({ failed: false })
  }

  render() {
    if (this.state.failed)
      return (
        <section className="panel panel-body" role="alert">
          <h2>This screen could not be opened.</h2>
          <p>
            Your saved data remains in the app. Open another section, or reload to fetch the latest
            application files.
          </p>
          <button className="button secondary" onClick={() => window.location.reload()}>
            Reload application
          </button>
        </section>
      )
    return this.props.children
  }
}

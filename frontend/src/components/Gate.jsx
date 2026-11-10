import { RotateCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { SERVER_DOWN } from '../lib/api'
import { useApp } from '../state/AppContext'
import { useAuth } from '../state/AuthContext'
import { EmptyState, Notice, Spinner } from './ui'

// Retry for "the server did not answer": checks the server and the sign-in again; the session is kept meanwhile.
export function RetryButton() {
  const { retry } = useAuth()
  const { checkHealth } = useApp() || {}
  return (
    <button type="button" className="btn" onClick={() => { checkHealth?.(); retry() }}>
      <RotateCw size={16} aria-hidden="true" />Retry
    </button>
  )
}

// What a tenant page shows until the sign-in is known: checking, server not answering, or signed out.
// Returns null when signed in, so the page renders itself.
export function SignInGate({ what = 'this page' }) {
  const { state } = useAuth()
  if (state === 'in') return null
  if (state === 'checking') return <Spinner label="Signing in" />
  if (state === 'offline') {
    return <Notice kind="error" title="Can't reach the server">{SERVER_DOWN} You stay signed in.<div className="mt-3"><RetryButton /></div></Notice>
  }
  return <EmptyState title="Sign in first"><Link className="link" to="/login">Sign in with an API key</Link> to use {what}.</EmptyState>
}

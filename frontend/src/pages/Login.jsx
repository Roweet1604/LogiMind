import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Field, Notice, PageHeader, Panel, Spinner } from '../components/ui'
import { useAuth } from '../state/AuthContext'

export default function Login() {
  const { login, me, logout } = useAuth()
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await login(key)
      navigate('/plans')
    } catch (err) {
      setError(err.status === 401 ? 'This API key was not accepted (missing, wrong or revoked).' : err.message)
    } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Sign in with an API key">
        Plans, imports and replans belong to one tenant. Ask your admin for a key
        (<code className="font-mono">python manage.py create-tenant "Name"</code> prints one once).
      </PageHeader>
      <Panel className="max-w-xl">
        {me ? (
          <div className="space-y-3">
            <Notice kind="ok" title={`Signed in as ${me.tenant_name || me.tenant_id}`}>Key {me.key_id}</Notice>
            <button type="button" className="btn" onClick={logout}>Sign out</button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <Field label="API key" htmlFor="api-key" hint="Kept only for this browser tab (sessionStorage, cleared when the tab closes) and sent as X-API-Key.">
              <input id="api-key" className="input font-mono" type="password" autoComplete="off" value={key}
                onChange={(e) => setKey(e.target.value)} placeholder="lm_..." />
            </Field>
            {error && <Notice kind="error" title="Sign-in failed">{error}</Notice>}
            <button type="submit" className="btn btn-primary" disabled={busy || !key.trim()}>
              {busy ? <Spinner label="Checking key" /> : 'Sign in'}
            </button>
          </form>
        )}
      </Panel>
    </>
  )
}

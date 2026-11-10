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
      setError(err.status === 401 ? 'This API key was not accepted. Check that you copied all of it, or ask for a new one.' : err.message)
    } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Account">
        Plans, imports and replans belong to one company account. Sign in with the API key you were given by the person
        who runs LogiMind.
      </PageHeader>
      <Panel className="max-w-xl">
        {me ? (
          <div className="space-y-3">
            <Notice kind="ok" title={`Signed in as ${me.tenant_name || me.tenant_id}`}>
              {me.demo ? 'Demo mode: signed in automatically to the local demo tenant. All its data is synthetic. Sign out to use your own API key.' : `Key ${me.key_id}`}
            </Notice>
            <button type="button" className="btn" onClick={logout}>Sign out</button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <Field label="API key" htmlFor="api-key" hint="Kept only in this browser tab and forgotten when you close it.">
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

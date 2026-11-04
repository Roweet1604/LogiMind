import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, EmptyState, Notice, PageHeader, Panel, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../state/AuthContext'

const KIND = {
  answer: ['ok', 'answer'], clarify: ['warn', 'question'], confirm: ['warn', 'needs confirmation'],
  refuse: ['neutral', 'not supported'], error: ['bad', 'error'], unavailable: ['bad', 'no model'],
}

// Plan ids in tool outputs become links; nothing else in a reply is interpreted.
function PlanLinks({ calls }) {
  const ids = new Set()
  const walk = (v) => {
    if (typeof v === 'string' && /^plan-[0-9a-f]{12}$/.test(v)) ids.add(v)
    else if (v && typeof v === 'object') Object.values(v).forEach(walk)
  }
  calls.forEach((c) => walk(c.output))
  if (!ids.size) return null
  return <p className="mt-1 text-xs">Plans: {[...ids].map((id) => <Link key={id} className="mr-2 font-mono underline" to={`/plans/${id}`}>{id}</Link>)}</p>
}

function Reply({ m, onConfirm, busy }) {
  const [kind, label] = KIND[m.kind] || ['neutral', m.kind]
  return (
    <div className="rounded-md border border-rule bg-white px-4 py-3">
      <div className="mb-1 flex items-center gap-2"><span className="text-xs font-medium text-ink2">Copilot</span><Badge kind={kind}>{label}</Badge></div>
      <p className="whitespace-pre-wrap">{m.text}</p>
      {m.tool_calls?.length > 0 && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-ink2">Tool results used: {m.tool_calls.map((t) => t.tool).join(', ')}</summary>
          <pre className="mt-1 max-h-64 overflow-auto rounded bg-rule2 p-2 font-mono">{JSON.stringify(m.tool_calls, null, 2)}</pre>
        </details>
      )}
      {m.tool_calls && <PlanLinks calls={m.tool_calls} />}
      {m.kind === 'confirm' && m.open && (
        <div className="mt-3 flex gap-2">
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => onConfirm(m, true)}>Confirm replan</button>
          <button type="button" className="btn" disabled={busy} onClick={() => onConfirm(m, false)}>Cancel</button>
        </div>
      )}
    </div>
  )
}

export default function Copilot() {
  const { state } = useAuth()
  const [status, setStatus] = useState(null)
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [session, setSession] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const end = useRef(null)

  useEffect(() => {
    if (state !== 'in') return
    api.copilotStatus().then(setStatus).catch((e) => setStatus({ available: false, reason: e.message }))
  }, [state])
  useEffect(() => { end.current?.scrollIntoView?.({ block: 'nearest' }) }, [messages])

  const closeConfirms = (list) => list.map((m) => (m.kind === 'confirm' ? { ...m, open: false } : m))

  async function send(e) {
    e.preventDefault()
    const msg = text.trim()
    if (!msg) return
    setBusy(true); setError(null); setText('')
    setMessages((l) => [...closeConfirms(l), { role: 'user', text: msg }])  // a new message drops a pending change
    try {
      const r = await api.copilotChat(msg, session)
      setSession(r.session_id)
      setMessages((l) => [...l, { role: 'copilot', ...r, open: r.kind === 'confirm' }])
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  async function confirm(m, approve) {
    setBusy(true); setError(null)
    setMessages((l) => closeConfirms(l))
    try {
      const r = await api.copilotConfirm(session, m.pending_id, approve)
      setMessages((l) => [...l, { role: 'user', text: approve ? 'Confirmed.' : 'Cancelled.' }, { role: 'copilot', ...r }])
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  if (state !== 'in') {
    return <><PageHeader title="Copilot" /><EmptyState title="Sign in first"><Link className="underline" to="/login">Sign in with an API key</Link> to use the copilot.</EmptyState></>
  }
  const off = status && !status.available
  return (
    <>
      <PageHeader title="Copilot">
        Ask in plain words: re-solve, validate, compare or explain a plan, or replan after a breakdown, failed delivery or
        urgent order. The model only reads your request; plans come from the solvers and the validator, and replies are
        built from their results.
      </PageHeader>
      {!status && <Spinner label="Checking for a local model" />}
      {off && <Notice kind="error" title="No local model is available">{status.reason}. Plans, imports and replans still work from the Plans page.</Notice>}
      {status?.available && <p className="mb-3 text-xs text-ink2">Model: {status.provider} · {status.model}</p>}
      <Panel className="mt-4">
        <div className="mb-4 space-y-3" aria-live="polite">
          {messages.length === 0 && <p className="text-ink2">Example: “Truck 1 broke down after two stops on the latest plan.”</p>}
          {messages.map((m, i) => (m.role === 'user'
            ? <div key={i} className="ml-auto max-w-[80%] rounded-md bg-accent-soft px-4 py-2 text-right"><span className="sr-only">You: </span>{m.text}</div>
            : <Reply key={i} m={m} onConfirm={confirm} busy={busy} />))}
          {busy && <Spinner label="Working (solver runs can take a few seconds)" />}
          <div ref={end} />
        </div>
        {error && <div className="mb-3"><Notice kind="error" title="Request failed" errors={error.errors}>{error.message}</Notice></div>}
        <form onSubmit={send} className="flex gap-2">
          <label htmlFor="copilot-input" className="sr-only">Message to the copilot</label>
          <input id="copilot-input" className="input" value={text} onChange={(e) => setText(e.target.value)} disabled={busy || off || !status}
            placeholder={off ? 'No local model available' : 'Type a request'} maxLength={2000} />
          <button type="submit" className="btn btn-primary" disabled={busy || off || !status || !text.trim()}>Send</button>
        </form>
      </Panel>
    </>
  )
}

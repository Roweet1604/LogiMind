import { Ban, Bot, HelpCircle, MessageSquare, ShieldCheck, Wrench } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { loadLlmSettings } from '../lib/llmSettings'
import { useAuth } from '../state/AuthContext'
import { Badge, Notice, Spinner } from './ui'

// Reply kinds from the backend, shown as icon + word.
const KIND = {
  answer: ['neutral', 'answer', MessageSquare], clarify: ['warn', 'question', HelpCircle],
  confirm: ['draft', 'needs confirmation', undefined], refuse: ['neutral', 'not supported', Ban],
  error: ['bad', 'error', undefined], unavailable: ['bad', 'not available', undefined],
}

// Copilot model providers (decision 0032). Hosted ones run on the provider's servers; the key never reaches the console.
export const PROVIDERS = { ollama: 'Ollama', groq: 'Groq', gemini: 'Gemini', openrouter: 'OpenRouter', openai: 'the OpenAI-compatible service', fake: 'Fake model', none: 'None' }
export const isHosted = (status) => ['groq', 'gemini', 'openai', 'openrouter'].includes(status?.provider)
const nameOf = (status) => PROVIDERS[status?.provider] || status?.provider || 'Model'

// One conversation per signed-in key, shared by the docked panel and the /copilot page.
// The conversation is cleared when the signed-in key changes, so a session never crosses tenants.
const Ctx = createContext(null)
export const useCopilot = () => useContext(Ctx)

export function CopilotProvider({ children }) {
  const { state, me } = useAuth()
  const owner = me?.key_id
  const [status, setStatus] = useState(null)
  const [messages, setMessages] = useState([])
  const [session, setSession] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => { setMessages([]); setSession(null); setStatus(null); setError(null) }, [owner])

  const loadStatus = useCallback(() => {
    if (state !== 'in') return
    api.copilotStatus().then(setStatus).catch((e) => {
      // e.g. a 400 for Copilot settings the server refused: say so, with the provider chosen in this tab
      const s = loadLlmSettings()
      setStatus({ available: false, provider: s.provider || 'server', model: s.model || null, reason: e.message,
        problem: e.status === 400 ? 'Copilot settings not accepted' : '' })
    })
  }, [state])

  const closeConfirms = (list) => list.map((m) => (m.kind === 'confirm' ? { ...m, open: false } : m))

  const send = useCallback(async (msg) => {
    setBusy(true); setError(null)
    setMessages((l) => [...closeConfirms(l), { role: 'user', text: msg }])  // a new message drops a pending change
    try {
      const r = await api.copilotChat(msg, session)
      setSession(r.session_id)
      setMessages((l) => [...l, { role: 'copilot', ...r, open: r.kind === 'confirm' }])
    } catch (err) { setError(err) } finally { setBusy(false) }
  }, [session])

  const confirm = useCallback(async (m, approve) => {
    setBusy(true); setError(null)
    setMessages((l) => closeConfirms(l))
    try {
      const r = await api.copilotConfirm(session, m.pending_id, approve)
      setMessages((l) => [...l, { role: 'user', text: approve ? 'Confirmed.' : 'Cancelled.' }, { role: 'copilot', ...r }])
    } catch (err) { setError(err) } finally { setBusy(false) }
  }, [session])

  // Copilot settings changed in this tab: ask the server again which model is in use.
  const settingsChanged = useCallback(() => { setStatus(null); loadStatus() }, [loadStatus])
  // A connection test just worked: show the model as ready at once (no stale "not available" badge).
  const markReady = useCallback((provider, model) => {
    setStatus({ available: true, provider, model, reason: 'tested just now', problem: '' })
  }, [])

  const value = useMemo(() => ({ status, messages, busy, error, loadStatus, send, confirm, settingsChanged, markReady }),
    [status, messages, busy, error, loadStatus, send, confirm, settingsChanged, markReady])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
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
  return <p className="mt-2 text-xs">Plans: {[...ids].map((id) => <Link key={id} className="link mr-2 font-mono" to={`/plans/${id}`}>{id}</Link>)}</p>
}

function Reply({ m, onConfirm, busy }) {
  const [kind, label, icon] = KIND[m.kind] || ['neutral', m.kind, undefined]
  const pending = m.kind === 'confirm' && m.open
  return (
    <div className={`rounded-md border bg-panel px-3.5 py-3 ${pending ? 'border-2 border-ink' : 'border-rule'}`}>
      <div className="mb-1.5 flex items-center gap-2">
        <Bot size={15} className="text-ink2" aria-hidden="true" />
        <span className="text-xs font-medium text-ink2">Copilot</span><Badge kind={kind} icon={icon}>{label}</Badge>
      </div>
      <p className="whitespace-pre-wrap">{m.text}</p>
      {m.tool_calls?.length > 0 && (
        <div className="mt-2.5 rounded border border-rule bg-sunken px-3 py-2 text-xs">
          <p className="flex items-center gap-1.5 font-medium">
            <Wrench size={13} aria-hidden="true" />Tool results used: {m.tool_calls.map((t) => t.tool).join(', ')}
          </p>
          <details className="mt-1">
            <summary className="cursor-pointer text-ink2">Show the raw tool output</summary>
            <pre className="mt-1 max-h-64 overflow-auto rounded bg-panel p-2 font-mono text-2xs">{JSON.stringify(m.tool_calls, null, 2)}</pre>
          </details>
        </div>
      )}
      {m.tool_calls && <PlanLinks calls={m.tool_calls} />}
      {pending && (
        <div className="mt-3 rounded border border-warn-soft bg-warn-soft p-3 text-warn-body">
          <p className="mb-2 text-xs font-medium text-warn">Nothing changes until you confirm. The new plan is solved and checked by the validator.</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => onConfirm(m, true)}>Confirm replan</button>
            <button type="button" className="btn btn-on-dark" disabled={busy} onClick={() => onConfirm(m, false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

// The server's reason is written for developers; the console leaves out the setup commands it suggests.
const withoutCommands = (reason) => String(reason).replace(/[;,]?\s*\b(install|run)\b[^;]*`[^`]*`.*$/i, '').trim()

// Always names the active provider and model, also when it is not available.
export function ModelStatus({ status }) {
  if (!status) return <Spinner label="Checking the copilot model" />
  const label = `${status.provider}${status.model ? ` · ${status.model}` : ''}`
  if (!status.available) return <Badge kind="bad">{label}: not available</Badge>
  return <Badge kind="ok" icon={ShieldCheck}>{label}</Badge>
}

function UnavailableNotice({ status }) {
  if (!isHosted(status)) {
    return (
      <Notice kind="error" title={status.problem || 'No local model is available'}>
        The copilot needs a language model running on this computer, and none was found. Plans, imports and replans
        still work from the Plans page.
        {status.reason && <details className="mt-2 text-xs"><summary className="cursor-pointer">Technical details</summary>{withoutCommands(status.reason)}</details>}
      </Notice>
    )
  }
  return (
    <Notice kind="error" title={status.problem || `${nameOf(status)} is not available`}>
      {status.reason}{/[.!?]$/.test(status.reason || '') ? '' : '.'} Plans, imports and replans still work from the Plans page.
    </Notice>
  )
}

// The conversation and the input. `compact` is the docked side panel; the /copilot page uses the full width.
export default function CopilotChat({ compact = false }) {
  const { state } = useAuth()
  const { status, messages, busy, error, loadStatus, send, confirm } = useCopilot()
  const [text, setText] = useState('')
  const end = useRef(null)

  useEffect(() => { loadStatus() }, [loadStatus])
  useEffect(() => { end.current?.scrollIntoView?.({ block: 'nearest' }) }, [messages])

  function submit(e) {
    e.preventDefault()
    const msg = text.trim()
    if (!msg) return
    setText('')
    send(msg)
  }

  if (state !== 'in') {
    return <p className="p-4 text-ink2"><Link className="link" to="/login">Sign in with an API key</Link> to use the copilot.</p>
  }
  const off = status && !status.available
  return (
    <div className={`flex min-h-0 flex-col ${compact ? 'h-full' : ''}`}>
      {off && (
        <div className={compact ? 'px-4 pt-3' : 'mb-3'}>
          <UnavailableNotice status={status} />
        </div>
      )}
      <div className={`space-y-3 ${compact ? 'min-h-0 flex-1 overflow-y-auto px-4 py-3' : 'mb-4 min-h-[16rem]'}`} aria-live="polite">
        {messages.length === 0 && <p className="text-ink2">Example: “Truck 1 broke down after two stops on the latest plan.”</p>}
        {messages.map((m, i) => (m.role === 'user'
          ? <div key={i} className="ml-auto max-w-[85%] rounded-md bg-accent-soft px-3.5 py-2 text-right"><span className="sr-only">You: </span>{m.text}</div>
          : <Reply key={i} m={m} onConfirm={confirm} busy={busy} />))}
        {busy && <Spinner label="Working (solver runs can take a few seconds)" />}
        <div ref={end} />
      </div>
      <div className={compact ? 'border-t border-rule bg-sunken px-4 py-3' : ''}>
        {error && <div className="mb-3"><Notice kind="error" title="Request failed" errors={error.errors}>{error.message}</Notice></div>}
        <form onSubmit={submit} className="flex gap-2">
          <label htmlFor={compact ? 'copilot-dock-input' : 'copilot-input'} className="sr-only">Message to the copilot</label>
          <input id={compact ? 'copilot-dock-input' : 'copilot-input'} className="input" value={text} onChange={(e) => setText(e.target.value)}
            disabled={busy || off || !status} placeholder={off ? 'Copilot not available' : 'Type a request'} maxLength={2000} />
          <button type="submit" className="btn btn-primary" disabled={busy || off || !status || !text.trim()}>Send</button>
        </form>
      </div>
    </div>
  )
}

import { KeyRound, ListChecks, PlugZap, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '../lib/api'
import { NEEDS_KEY, PROVIDER_OPTIONS, last4, loadLlmSettings, saveLlmSettings } from '../lib/llmSettings'
import { useCopilot } from './CopilotChat'
import { Field, Notice, Spinner } from './ui'

// Plain headline per result kind from POST /api/copilot/test (decision 0033).
const RESULT = {
  ok: ['ok', 'Works'], auth: ['error', 'Key rejected'], model: ['error', 'Model not found'],
  rate_limit: ['warn', 'Rate limit reached'], network: ['error', 'Not reachable'], blocked: ['error', 'Address not allowed'],
  server: ['error', 'The provider had a problem'], none: ['error', 'No model configured'],
}
const MODEL_HINT = { ollama: 'e.g. llama3.2:3b', groq: 'a model id from Groq’s model list', gemini: 'e.g. gemini-2.5-flash',
  openai: 'the model id the service expects' }

// "Copilot settings": choose the provider for THIS tab and paste a key without editing backend\.env. The key stays in
// sessionStorage for this tab only; afterwards only its last 4 characters are shown.
export default function CopilotSettings({ compact = false }) {
  const copilot = useCopilot()
  const [saved, setSaved] = useState(loadLlmSettings)
  const [form, setForm] = useState(() => ({ provider: saved.provider || '', model: saved.model || '', baseUrl: saved.baseUrl || '' }))
  const [keyInput, setKeyInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [models, setModels] = useState(null)        // the provider's chat models after "Load models"
  const [listResult, setListResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const set = (k) => (e) => {
    setForm((f) => ({ ...f, [k]: e.target.value })); setResult(null)
    if (k !== 'model') { setModels(null); setListResult(null) }  // another provider or address: list again
  }
  const needsKey = NEEDS_KEY.has(form.provider)
  const sameProvider = saved.provider === form.provider
  const keyNow = keyInput || (sameProvider ? saved.key : '')
  const idp = compact ? 'dock-llm' : 'page-llm'

  function apply(f = form) {
    const s = saveLlmSettings({ ...f, key: keyNow || '' })
    setSaved(s); setKeyInput('')
    copilot?.settingsChanged()
    return s
  }

  async function runTest(s) {
    setBusy(true); setResult(null)
    try {
      const r = await api.copilotTest(s)
      if (r.ok && r.model && !s.model) {  // no model name was given: keep the one the server chose (it says which)
        const f = { ...form, ...s, model: r.model }
        setForm((old) => ({ ...old, model: r.model }))
        setSaved(saveLlmSettings({ ...f, key: s.key }))
        copilot?.settingsChanged()
      }
      setResult({ kind: r.ok ? 'ok' : r.kind, message: r.message })
    } catch (err) {
      setResult({ kind: err.unreachable ? 'network' : 'settings', message: err.message })
    } finally { setBusy(false) }
  }

  function test(e) {
    e.preventDefault()
    runTest(apply())
  }

  // "Load models": the provider's list through our server (same key header, guard and limits as every call).
  async function loadModels() {
    const s = apply()
    setLoading(true); setListResult(null); setResult(null)
    try {
      const r = await api.copilotModels(s)
      setModels(r.ok ? r.models : null)
      setListResult({ kind: r.ok ? 'ok' : r.kind, message: r.ok ? r.message : `${r.message} You can still type the model name.` })
    } catch (err) {
      setModels(null)
      setListResult({ kind: err.unreachable ? 'network' : 'settings', message: `${err.message} You can still type the model name.` })
    } finally { setLoading(false) }
  }

  function pick(e) {
    const model = e.target.value
    if (!model) return
    const f = { ...form, model }
    setForm(f)
    runTest(apply(f))  // picking a model tests it at once
  }

  function clearKey() {
    const s = saveLlmSettings({ ...form, key: '' })
    setSaved(s); setKeyInput(''); setResult(null)
    copilot?.settingsChanged()
  }

  const summary = saved.provider
    ? `${PROVIDER_OPTIONS.find(([v]) => v === saved.provider)?.[1]}${saved.model ? ` · ${saved.model}` : ''}${saved.key ? ` · key ${last4(saved.key)}` : ''}`
    : 'Server settings'
  const headlineOf = (r) => (RESULT[r.kind] || ['error', r.kind === 'settings' ? 'Settings not accepted' : 'Did not work'])
  const [kind, headline] = result ? headlineOf(result) : []
  const [listKind, listHeadline] = listResult ? (listResult.kind === 'ok' ? ['ok', 'Models loaded'] : headlineOf(listResult)) : []
  return (
    <details className={`rounded border border-rule bg-panel ${compact ? 'mx-4 mt-3' : ''}`}>
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
        Copilot settings <span className="font-normal text-ink2">({summary})</span>
      </summary>
      <form onSubmit={test} className="space-y-3 border-t border-rule2 px-3 py-3 text-sm" aria-label="Copilot settings">
        <Field label="Provider" htmlFor={`${idp}-provider`}>
          <select id={`${idp}-provider`} className="input" value={form.provider} onChange={set('provider')}>
            {PROVIDER_OPTIONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </Field>
        {form.provider && (
          <Field label="Model name" htmlFor={`${idp}-model`} hint={form.provider === 'ollama' ? 'Empty: the server’s default model.' : 'Empty: the model in backend\\.env, or else the first chat model in the provider’s list.'}>
            <input id={`${idp}-model`} className="input" value={form.model} onChange={set('model')} placeholder={MODEL_HINT[form.provider]}
              autoComplete="off" spellCheck={false} maxLength={200} />
          </Field>
        )}
        {form.provider === 'openai' && (
          <Field label="Base URL" htmlFor={`${idp}-base`} hint="https only, the service’s public address (for example https://…/v1). Private and internal addresses are refused.">
            <input id={`${idp}-base`} className="input" value={form.baseUrl} onChange={set('baseUrl')} placeholder="https://"
              autoComplete="off" spellCheck={false} maxLength={500} />
          </Field>
        )}
        {needsKey && (
          <Field label="Key" htmlFor={`${idp}-key`} hint="Kept only in this browser tab and sent to our server with each copilot request. Never shared, never in a link.">
            <input id={`${idp}-key`} className="input font-mono" type="password" value={keyInput} onChange={(e) => { setKeyInput(e.target.value); setResult(null) }}
              autoComplete="off" spellCheck={false} maxLength={512} placeholder={sameProvider && saved.key ? 'Saved; type to replace' : 'Paste the key'} />
          </Field>
        )}
        {needsKey && sameProvider && saved.key && (
          <p className="flex items-center gap-2 text-xs"><KeyRound size={14} aria-hidden="true" />Key saved for this tab: <span className="font-mono">{last4(saved.key)}</span></p>
        )}
        {models && models.length > 0 && (
          <Field label={`Available models (${models.length})`} htmlFor={`${idp}-models`} hint="Picking one fills in the model name and tests it.">
            <select id={`${idp}-models`} className="input" value={models.includes(form.model) ? form.model : ''} onChange={pick} disabled={busy}>
              <option value="">Pick a model…</option>
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </Field>
        )}
        {listResult && <Notice kind={listKind} title={listHeadline}>{listResult.message}</Notice>}
        {needsKey && (
          <p className="text-xs text-ink2">Paid services charge for every message. Your messages and your plans’ names and ids are sent to
            the provider (routes are not). Use synthetic data.</p>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? <Spinner label="Testing" /> : <><PlugZap size={16} aria-hidden="true" />Test connection</>}
          </button>
          {form.provider && (
            <button type="button" className="btn" onClick={loadModels} disabled={loading || busy}>
              {loading ? <Spinner label="Loading models" /> : <><ListChecks size={16} aria-hidden="true" />Load models</>}
            </button>
          )}
          {needsKey && sameProvider && saved.key && (
            <button type="button" className="btn" onClick={clearKey}><Trash2 size={16} aria-hidden="true" />Clear key</button>
          )}
        </div>
        {result && <Notice kind={kind} title={headline}>{result.message}</Notice>}
      </form>
    </details>
  )
}

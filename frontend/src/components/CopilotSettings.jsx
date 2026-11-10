import { KeyRound, PlugZap, Trash2 } from 'lucide-react'
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
  const set = (k) => (e) => { setForm((f) => ({ ...f, [k]: e.target.value })); setResult(null) }
  const needsKey = NEEDS_KEY.has(form.provider)
  const sameProvider = saved.provider === form.provider
  const keyNow = keyInput || (sameProvider ? saved.key : '')
  const idp = compact ? 'dock-llm' : 'page-llm'

  function apply() {
    const s = saveLlmSettings({ ...form, key: keyNow || '' })
    setSaved(s); setKeyInput('')
    copilot?.settingsChanged()
    return s
  }

  async function test(e) {
    e.preventDefault()
    const s = apply()
    setBusy(true); setResult(null)
    try {
      const r = await api.copilotTest(s)
      setResult({ kind: r.ok ? 'ok' : r.kind, message: r.message })
    } catch (err) {
      setResult({ kind: err.unreachable ? 'network' : 'settings', message: err.message })
    } finally { setBusy(false) }
  }

  function clearKey() {
    const s = saveLlmSettings({ ...form, key: '' })
    setSaved(s); setKeyInput(''); setResult(null)
    copilot?.settingsChanged()
  }

  const summary = saved.provider
    ? `${PROVIDER_OPTIONS.find(([v]) => v === saved.provider)?.[1]}${saved.model ? ` · ${saved.model}` : ''}${saved.key ? ` · key ${last4(saved.key)}` : ''}`
    : 'Server settings'
  const [kind, headline] = result ? (RESULT[result.kind] || ['error', result.kind === 'settings' ? 'Settings not accepted' : 'Did not work']) : []
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
          <Field label="Model name" htmlFor={`${idp}-model`} hint={form.provider === 'ollama' ? 'Empty: the server’s default model.' : 'Empty: the model in backend\\.env, if any.'}>
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
        {needsKey && (
          <p className="text-xs text-ink2">Paid services charge for every message. Your messages and your plans’ names and ids are sent to
            the provider (routes are not). Use synthetic data.</p>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? <Spinner label="Testing" /> : <><PlugZap size={16} aria-hidden="true" />Test connection</>}
          </button>
          {needsKey && sameProvider && saved.key && (
            <button type="button" className="btn" onClick={clearKey}><Trash2 size={16} aria-hidden="true" />Clear key</button>
          )}
        </div>
        {result && <Notice kind={kind} title={headline}>{result.message}</Notice>}
      </form>
    </details>
  )
}

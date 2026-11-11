import { KeyRound, ListChecks, PlugZap, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { KEY_PROVIDERS, cleanKey, detectProvider } from '../lib/keyDetect'
import { NEEDS_KEY, PROVIDER_OPTIONS, last4, loadLlmSettings, saveLlmSettings } from '../lib/llmSettings'
import { useCopilot } from './CopilotChat'
import { Field, Spinner } from './ui'

// "Copilot settings" (decisions 0033, 0035, 0036): by default ONE "API key" field. The service is detected from the
// key's prefix in this browser before anything is sent, the key is tested a moment after pasting (or on Enter), a
// model is chosen from the provider's list, and the result is one plain sentence. Everything else is under
// "Advanced (optional)". The key stays in sessionStorage for this tab only and travels to our server in a header.
const TEST_DELAY_MS = 700
const SERVER_DOWN = "LogiMind's own server is not answering, so the key could not be tested. Start LogiMind with start-dev.bat, then try again."
const MODEL_HINT = { ollama: 'e.g. llama3.2:3b', groq: 'a model id from Groq’s list', gemini: 'e.g. gemini-2.5-flash',
  openrouter: 'e.g. a model id ending in :free', openai: 'e.g. gpt-4o-mini' }
const UNKNOWN_CHOICES = [['', 'Choose the service…'], ['groq', 'Groq'], ['gemini', 'Gemini'], ['openrouter', 'OpenRouter'],
  ['openai', 'OpenAI'], ['custom', 'Another OpenAI-compatible service (needs its base URL)']]
const TONE = { ok: 'text-ok', error: 'text-err', warn: 'text-warn-body', info: 'text-ink2' }

function labelOf(provider, baseUrl) {
  if (provider === 'openai' && baseUrl) return 'The OpenAI-compatible service'
  return { groq: 'Groq', gemini: 'Gemini', openrouter: 'OpenRouter', openai: 'OpenAI', ollama: 'Ollama' }[provider] || provider
}

export default function CopilotSettings({ compact = false }) {
  const copilot = useCopilot()
  const [saved, setSaved] = useState(loadLlmSettings)
  const [openAtStart] = useState(() => !loadLlmSettings().provider)
  const [keyInput, setKeyInput] = useState('')
  const [choice, setChoice] = useState('')  // service picked by hand for a key with an unknown prefix
  const [adv, setAdv] = useState(() => ({ provider: saved.provider || '', model: saved.model || '', baseUrl: saved.baseUrl || '' }))
  const [busy, setBusy] = useState(false)
  const [sentence, setSentence] = useState(null)  // { tone, text }: always ONE plain sentence
  const [chosenLine, setChosenLine] = useState(null)
  const [models, setModels] = useState(null)
  const [loading, setLoading] = useState(false)
  const advRef = useRef(null)
  const lastSent = useRef('')
  const idp = compact ? 'dock-llm' : 'page-llm'

  const key = cleanKey(keyInput)
  const detected = detectProvider(keyInput)

  // Where this key would go: the detected service, or the one picked for an unknown prefix. null = send nothing.
  function target() {
    if (detected.kind === 'known') return { provider: detected.provider, baseUrl: '' }
    if (detected.kind !== 'unknown' || !choice) return null
    if (choice === 'custom') return adv.baseUrl.trim() ? { provider: 'openai', baseUrl: adv.baseUrl.trim() } : null
    return { provider: KEY_PROVIDERS[choice].provider, baseUrl: '' }
  }

  async function runTest(s) {
    setBusy(true); setSentence(null); setChosenLine(null)
    lastSent.current = `${s.provider}|${s.baseUrl}|${s.key}`
    try {
      const r = await api.copilotTest(s)
      if (r.ok) {
        const kept = saveLlmSettings({ ...s, model: r.model || s.model })  // remember the model for this tab
        setSaved(kept); setKeyInput(''); setAdv((a) => ({ ...a, provider: kept.provider, model: kept.model, baseUrl: kept.baseUrl }))
        setSentence({ tone: 'ok', text: `Works: ${labelOf(kept.provider, kept.baseUrl)} is ready.` })
        if (r.model) {
          const free = r.model.endsWith(':free') ? ', free' : ''
          setChosenLine(`Model: ${r.model}${r.chosen_automatically ? ` (chosen automatically${free})` : ''}`)
        }
        copilot?.markReady(r.provider || kept.provider, r.model || kept.model)
      } else {
        setSentence({ tone: r.kind === 'rate_limit' ? 'warn' : 'error', text: r.message })
        copilot?.settingsChanged()
      }
    } catch (err) {
      setSentence({ tone: 'error', text: err.unreachable ? SERVER_DOWN : err.message })
      if (!err.unreachable) copilot?.settingsChanged()
    } finally { setBusy(false) }
  }

  // The key field: test the detected service only (never several).
  function submitKey() {
    if (!key || busy) return
    if (detected.kind === 'unsupported') return
    const t = target()
    if (!t) {
      if (detected.kind === 'unknown' && choice === 'custom') {
        if (advRef.current) advRef.current.open = true
        setSentence({ tone: 'info', text: 'Enter the service’s https base URL under Advanced; nothing is sent until then.' })
      }
      return
    }
    const sameService = saved.provider === t.provider && (saved.baseUrl || '') === t.baseUrl
    const s = saveLlmSettings({ provider: t.provider, baseUrl: t.baseUrl, key, model: sameService ? saved.model || '' : '' })
    setSaved(s)
    runTest(s)
  }

  // A moment after pasting (or typing stops), test once.
  useEffect(() => {
    if (!key || detected.kind === 'unsupported' || detected.kind === 'empty') return undefined
    const t = target()
    if (!t || lastSent.current === `${t.provider}|${t.baseUrl}|${key}`) return undefined
    const timer = setTimeout(submitKey, TEST_DELAY_MS)
    return () => clearTimeout(timer)
  })

  function onKeyChange(e) {
    setKeyInput(e.target.value); setChosenLine(null); setModels(null)
    const d = detectProvider(e.target.value)
    if (d.kind === 'unsupported') {
      setSentence({ tone: 'warn', text: `${d.label} keys are not supported yet: LogiMind has no ${d.label} adapter, so nothing was sent.` })
    } else if (d.kind === 'unknown') {
      setSentence({ tone: 'info', text: 'This key’s service is not recognised from its start: choose it below; nothing is sent until you do.' })
    } else {
      setSentence(null)
    }
  }

  // Advanced: the explicit provider, model and base URL, with the saved key (or the one in the field).
  function advancedSettings(model = adv.model) {
    const keyNow = key || (saved.provider === adv.provider ? saved.key : '')
    return saveLlmSettings({ ...adv, model, key: NEEDS_KEY.has(adv.provider) ? keyNow || '' : '' })
  }

  function testAdvanced() {
    const s = advancedSettings()
    setSaved(s)
    if (!s.provider) {
      setSentence({ tone: 'info', text: 'The server’s own settings (backend\\.env) are used.' })
      copilot?.settingsChanged()
      return
    }
    runTest(s)
  }

  async function loadModels() {
    const s = advancedSettings()
    setSaved(s); setLoading(true); setModels(null)
    try {
      const r = await api.copilotModels(s)
      if (r.ok) { setModels(r.models); setSentence({ tone: 'info', text: r.message }) } else {
        setSentence({ tone: 'error', text: `${r.message} You can still type the model name.` })
      }
    } catch (err) {
      setSentence({ tone: 'error', text: err.unreachable ? SERVER_DOWN : `${err.message} You can still type the model name.` })
    } finally { setLoading(false) }
  }

  function pick(e) {
    const model = e.target.value
    if (!model) return
    setAdv((a) => ({ ...a, model }))
    const s = advancedSettings(model)
    setSaved(s); runTest(s)  // picking a model tests it at once
  }

  function clearKey() {
    const s = saveLlmSettings({ ...saved, key: '' })
    setSaved(s); setKeyInput(''); setSentence(null); setChosenLine(null); setModels(null); lastSent.current = ''
    copilot?.settingsChanged()
  }

  const summary = saved.provider
    ? `${labelOf(saved.provider, saved.baseUrl)}${saved.model ? ` · ${saved.model}` : ''}${saved.key ? ` · key ${last4(saved.key)}` : ''}`
    : 'Server settings'
  const savedKeyHere = saved.key && NEEDS_KEY.has(saved.provider)
  return (
    <details open={openAtStart} className={`rounded border border-rule bg-panel ${compact ? 'mx-4 mt-3' : ''}`}>
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
        Copilot settings <span className="font-normal text-ink2">({summary})</span>
      </summary>
      <form onSubmit={(e) => { e.preventDefault(); submitKey() }} className="space-y-2 border-t border-rule2 px-3 py-3 text-sm"
        aria-label="Copilot settings" autoComplete="off">
        <Field label="API key" htmlFor={`${idp}-key`}>
          <input id={`${idp}-key`} name={`${idp}-llm-key`} className="input font-mono" type="password" value={keyInput}
            onChange={onKeyChange} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submitKey() } }}
            autoComplete="new-password" autoCorrect="off" autoCapitalize="off" spellCheck={false} maxLength={512}
            data-lpignore="true" data-1p-ignore="true" data-bwignore="true" data-form-type="other"
            placeholder={savedKeyHere ? `Saved for this tab (${last4(saved.key)}); paste to replace` : 'Paste your API key'} />
        </Field>
        {detected.kind === 'known' && <p className="text-xs text-ink2">Detected: {detected.label}</p>}
        {detected.kind === 'unknown' && (
          <Field label="Which service is this key for?" htmlFor={`${idp}-choice`}>
            <select id={`${idp}-choice`} className="input" value={choice} onChange={(e) => { setChoice(e.target.value); setSentence(null) }}>
              {UNKNOWN_CHOICES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            </select>
          </Field>
        )}
        {busy && <Spinner label="Testing the key" />}
        {sentence && !busy && <p role={sentence.tone === 'error' ? 'alert' : 'status'} className={`text-sm ${TONE[sentence.tone]}`}>{sentence.text}</p>}
        {chosenLine && !busy && <p className="text-xs text-ink2">{chosenLine}</p>}
        {!chosenLine && !busy && saved.model && saved.provider && !sentence && <p className="text-xs text-ink2">Model: {saved.model}</p>}
        {savedKeyHere && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <KeyRound size={14} aria-hidden="true" />Key saved for this tab: <span className="font-mono">{last4(saved.key)}</span>
            <button type="button" className="btn px-2 py-1 text-xs" onClick={clearKey}><Trash2 size={14} aria-hidden="true" />Clear key</button>
          </div>
        )}
        <p className="text-xs text-ink2">Paid services charge for every message. Your messages and your plans’ names and ids go to the
          provider (routes do not). Use synthetic data.</p>
        <details ref={advRef} className="rounded border border-rule2">
          <summary className="cursor-pointer px-2 py-1.5 text-xs font-medium">Advanced (optional)</summary>
          <div className="space-y-3 px-2 pb-3 pt-1">
            <Field label="Provider" htmlFor={`${idp}-provider`}>
              <select id={`${idp}-provider`} className="input" value={adv.provider}
                onChange={(e) => { setAdv((a) => ({ ...a, provider: e.target.value, model: '' })); setModels(null) }}>
                {PROVIDER_OPTIONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
              </select>
            </Field>
            {adv.provider && (
              <Field label="Model" htmlFor={`${idp}-model`} hint="Empty: chosen automatically from the provider’s list.">
                <input id={`${idp}-model`} className="input" value={adv.model} onChange={(e) => setAdv((a) => ({ ...a, model: e.target.value }))}
                  placeholder={MODEL_HINT[adv.provider]} autoComplete="off" spellCheck={false} maxLength={200} />
              </Field>
            )}
            {models && models.length > 0 && (
              <Field label={`Available models (${models.length})`} htmlFor={`${idp}-models`} hint="Picking one tests it at once.">
                <select id={`${idp}-models`} className="input" value={models.includes(adv.model) ? adv.model : ''} onChange={pick} disabled={busy}>
                  <option value="">Pick a model…</option>
                  {models.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </Field>
            )}
            {(adv.provider === 'openai' || adv.provider === 'openrouter' || choice === 'custom') && (
              <Field label="Base URL" htmlFor={`${idp}-base`} hint="Only for another OpenAI-compatible service: its public https address. Empty: the service’s own address.">
                <input id={`${idp}-base`} className="input" value={adv.baseUrl} onChange={(e) => setAdv((a) => ({ ...a, baseUrl: e.target.value }))}
                  placeholder="https://" autoComplete="off" spellCheck={false} maxLength={500} />
              </Field>
            )}
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn" onClick={testAdvanced} disabled={busy}><PlugZap size={16} aria-hidden="true" />Test connection</button>
              {adv.provider && (
                <button type="button" className="btn" onClick={loadModels} disabled={loading || busy}>
                  {loading ? <Spinner label="Loading models" /> : <><ListChecks size={16} aria-hidden="true" />Load models</>}
                </button>
              )}
            </div>
          </div>
        </details>
      </form>
    </details>
  )
}

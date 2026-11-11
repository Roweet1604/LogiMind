// Copilot settings typed in the console (decision 0033): provider, model, base URL and key.
// Kept ONLY in sessionStorage for this tab (gone when the tab closes), never in localStorage and never in a URL.
// They travel to our own server as headers with each copilot request; the server never stores or returns them.
const STORE = 'logimind.llm'

export const PROVIDER_OPTIONS = [
  ['', 'Server settings (backend\\.env)'],
  ['ollama', 'Ollama (local, free)'],
  ['groq', 'Groq'],
  ['gemini', 'Gemini'],
  ['openrouter', 'OpenRouter'],
  ['openai', 'Another OpenAI-compatible service (needs its base URL)'],  // OpenAI itself is not offered (decision 0036)
]
export const NEEDS_KEY = new Set(['groq', 'gemini', 'openai', 'openrouter'])
const HAS_BASE_URL = new Set(['openai', 'openrouter'])  // empty = the service's own address (decision 0036)

export function loadLlmSettings() {
  try {
    const v = JSON.parse(sessionStorage.getItem(STORE) || 'null')
    return v && typeof v === 'object' ? v : {}
  } catch { return {} }
}

export function saveLlmSettings({ provider = '', model = '', baseUrl = '', key = '' } = {}) {
  const s = { provider, model: model.trim(), baseUrl: HAS_BASE_URL.has(provider) ? baseUrl.trim() : '',
    key: NEEDS_KEY.has(provider) ? key.trim() : '' }
  try {
    if (s.provider) sessionStorage.setItem(STORE, JSON.stringify(s))
    else sessionStorage.removeItem(STORE)
  } catch { /* storage blocked: settings last only until the page reloads */ }
  return s
}

export function clearLlmSettings() {
  try { sessionStorage.removeItem(STORE) } catch { /* blocked */ }
}

// Headers for a copilot request. Nothing at all when the server's own settings are used.
export function llmHeaders(s = loadLlmSettings()) {
  if (!s.provider) return {}
  const h = { 'X-LLM-Provider': s.provider }
  if (s.model) h['X-LLM-Model'] = s.model
  if (HAS_BASE_URL.has(s.provider) && s.baseUrl) h['X-LLM-Base-URL'] = s.baseUrl
  if (NEEDS_KEY.has(s.provider) && s.key) h['X-LLM-Key'] = s.key
  return h
}

export const last4 = (key) => (key ? `••••${key.slice(-4)}` : '')

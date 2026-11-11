// Which service an API key belongs to, from its prefix only (decision 0036). Runs in the browser before anything is
// sent; a key is only ever sent to the ONE provider it matches (or the one the user picks for an unknown prefix).
// OpenAI is not offered (no free tier; CLAUDE.md invariant 12): its keys are refused here and nothing is sent.
export const KEY_PROVIDERS = {
  groq: { provider: 'groq', label: 'Groq' },
  gemini: { provider: 'gemini', label: 'Gemini' },
  openrouter: { provider: 'openrouter', label: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1' },
}

// Removes what copying often adds around a key: spaces, line breaks and one pair of surrounding quotes.
export function cleanKey(raw) {
  let k = String(raw || '').trim()
  const q = k[0]
  if ((q === '"' || q === "'" || q === '`') && k.endsWith(q) && k.length > 1) k = k.slice(1, -1).trim()
  return k
}

// { kind: 'empty' | 'known' | 'unsupported' | 'unknown', ...KEY_PROVIDERS entry, label, message (unsupported) }
export function detectProvider(raw) {
  const k = cleanKey(raw)
  if (!k) return { kind: 'empty' }
  if (k.startsWith('gsk_')) return { kind: 'known', ...KEY_PROVIDERS.groq }
  if (k.startsWith('AIza')) return { kind: 'known', ...KEY_PROVIDERS.gemini }
  if (k.startsWith('sk-or-')) return { kind: 'known', ...KEY_PROVIDERS.openrouter }
  if (k.startsWith('sk-ant-')) {
    return { kind: 'unsupported', label: 'Anthropic', message: 'Anthropic keys are not supported yet: LogiMind has no Anthropic adapter, so nothing was sent.' }
  }
  if (k.startsWith('sk-')) {
    return { kind: 'unsupported', label: 'OpenAI', message: 'OpenAI keys are not offered: OpenAI has no free tier and LogiMind stays free to run, so nothing was sent. Use Groq, Gemini or OpenRouter.' }
  }
  return { kind: 'unknown' }
}

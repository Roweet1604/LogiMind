// Which service an API key belongs to, from its prefix only (decision 0036). Runs in the browser before anything is
// sent; a key is only ever sent to the ONE provider it matches (or the one the user picks for an unknown prefix).
export const KEY_PROVIDERS = {
  groq: { provider: 'groq', label: 'Groq' },
  gemini: { provider: 'gemini', label: 'Gemini' },
  openrouter: { provider: 'openrouter', label: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1' },
  openai: { provider: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1' },
}

// Removes what copying often adds around a key: spaces, line breaks and one pair of surrounding quotes.
export function cleanKey(raw) {
  let k = String(raw || '').trim()
  const q = k[0]
  if ((q === '"' || q === "'" || q === '`') && k.endsWith(q) && k.length > 1) k = k.slice(1, -1).trim()
  return k
}

// { kind: 'empty' | 'known' | 'unsupported' | 'unknown', ...KEY_PROVIDERS entry, label }
export function detectProvider(raw) {
  const k = cleanKey(raw)
  if (!k) return { kind: 'empty' }
  if (k.startsWith('gsk_')) return { kind: 'known', ...KEY_PROVIDERS.groq }
  if (k.startsWith('AIza')) return { kind: 'known', ...KEY_PROVIDERS.gemini }
  if (k.startsWith('sk-or-')) return { kind: 'known', ...KEY_PROVIDERS.openrouter }
  if (k.startsWith('sk-ant-')) return { kind: 'unsupported', label: 'Anthropic' }  // no Anthropic adapter yet
  if (k.startsWith('sk-proj-') || k.startsWith('sk-')) return { kind: 'known', ...KEY_PROVIDERS.openai }
  return { kind: 'unknown' }
}

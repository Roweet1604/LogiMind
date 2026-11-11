import '@testing-library/jest-dom/vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockFetch, renderPage } from './helpers'
import Copilot from '../pages/Copilot'
import Login from '../pages/Login'
import { setApiKey } from '../lib/api'
import { cleanKey, detectProvider } from '../lib/keyDetect'
import { loadLlmSettings } from '../lib/llmSettings'

// Key-only Copilot settings (decisions 0033, 0036): one "API key" field; the service is detected from the prefix in
// the browser before anything is sent; the key is tested a moment after pasting (or on Enter), stays in
// sessionStorage for the tab only, travels only as a header, and the result is one plain sentence.
const BASE = {
  'GET /api/health': { status: 'ok', environment: {}, research_endpoints: false },
  'GET /api/whoami': { tenant_id: 't', tenant_name: 'Acme', key_id: 'k' },
  'GET /api/copilot/status': { available: false, provider: 'none', model: null, reason: 'no model', problem: '' },
}
const KEYS = { groq: 'gsk_FAKE_test_key_WXYZ', gemini: 'AIzaFAKE_test_key_WXYZ', openrouter: 'sk-or-v1-FAKE_WXYZ',
  openai: 'sk-proj-FAKE_test_WXYZ' }
const LABEL = { groq: 'Groq', gemini: 'Gemini', openrouter: 'OpenRouter', openai: 'OpenAI' }

function recording(table) {
  const calls = []
  mockFetch(Object.fromEntries(Object.entries(table).map(([k, v]) => [k, (opts) => {
    calls.push({ key: k, headers: { ...(opts.headers || {}) } })
    return typeof v === 'function' ? v(opts) : v
  }])))
  return calls
}

const works = (opts) => ({ ok: true, kind: 'ok', provider: opts.headers['X-LLM-Provider'], model: 'auto-model-1',
  chosen_automatically: true, message: 'Works: … is ready, using auto-model-1 (chosen automatically: a common chat model).' })

async function openBox() {
  renderPage(<Copilot />)
  return screen.findByRole('form', { name: 'Copilot settings' })  // open by default while nothing is set
}

const keyField = (box) => within(box).getByLabelText('API key')
const sent = (calls, path) => calls.filter((c) => c.key === path)

beforeEach(() => { sessionStorage.clear(); localStorage.clear(); setApiKey('lm_x_y') })

test('the prefix decides the service, locally', () => {
  expect(detectProvider('gsk_abc')).toMatchObject({ kind: 'known', provider: 'groq', label: 'Groq' })
  expect(detectProvider('AIzaSyabc')).toMatchObject({ kind: 'known', provider: 'gemini' })
  expect(detectProvider('sk-or-v1-abc')).toMatchObject({ kind: 'known', provider: 'openrouter', baseUrl: 'https://openrouter.ai/api/v1' })
  expect(detectProvider('sk-proj-abc')).toMatchObject({ kind: 'known', provider: 'openai', baseUrl: 'https://api.openai.com/v1' })
  expect(detectProvider('sk-abc')).toMatchObject({ kind: 'known', provider: 'openai' })
  expect(detectProvider('sk-ant-api03-abc')).toMatchObject({ kind: 'unsupported', label: 'Anthropic' })
  expect(detectProvider('xyz-123')).toMatchObject({ kind: 'unknown' })
  expect(detectProvider('  ')).toMatchObject({ kind: 'empty' })
  expect(cleanKey('  "gsk_abc"\n')).toBe('gsk_abc')
})

test.each(Object.keys(KEYS))('a %s key is tested by itself a moment after pasting, with ONE provider only', async (p) => {
  const calls = recording({ ...BASE, 'POST /api/copilot/test': works })
  const box = await openBox()
  await userEvent.click(keyField(box))
  await userEvent.paste(KEYS[p])
  expect(within(box).getByText(`Detected: ${LABEL[p]}`)).toBeInTheDocument()
  expect(await within(box).findByText(`Works: ${LABEL[p]} is ready.`, {}, { timeout: 3000 })).toBeInTheDocument()
  const tests = sent(calls, 'POST /api/copilot/test')
  expect(tests).toHaveLength(1)  // never the same key against several providers
  expect(tests[0].headers).toMatchObject({ 'X-LLM-Provider': p, 'X-LLM-Key': KEYS[p] })
  expect(tests[0].headers['X-LLM-Model']).toBeUndefined()  // the model is chosen automatically
  expect(tests[0].headers['X-LLM-Base-URL']).toBeUndefined()  // the server knows the service's own address
  expect(within(box).getByText('Model: auto-model-1 (chosen automatically)')).toBeInTheDocument()
  expect(loadLlmSettings()).toMatchObject({ provider: p, model: 'auto-model-1', key: KEYS[p] })
  expect(globalThis.fetch.mock.calls.every(([url]) => !String(url).includes(KEYS[p]))).toBe(true)
  expect(localStorage.length).toBe(0)
  expect(keyField(box)).toHaveValue('')
  expect(document.body.textContent).not.toContain(KEYS[p])
  expect(within(box).getByText('••••WXYZ')).toBeInTheDocument()
})

test('a free OpenRouter model is named as free', async () => {
  recording({ ...BASE, 'POST /api/copilot/test': { ok: true, kind: 'ok', provider: 'openrouter',
    model: 'deepseek/deepseek-chat-v3:free', chosen_automatically: true, message: 'Works' } })
  const box = await openBox()
  await userEvent.type(keyField(box), `${KEYS.openrouter}{Enter}`)
  expect(await within(box).findByText('Model: deepseek/deepseek-chat-v3:free (chosen automatically, free)')).toBeInTheDocument()
})

test('an unknown prefix sends nothing until a service is chosen, then exactly one test to it', async () => {
  const calls = recording({ ...BASE, 'POST /api/copilot/test': works })
  const box = await openBox()
  await userEvent.type(keyField(box), 'xyz-FAKE-key-WXYZ{Enter}')
  expect(within(box).getByText(/not recognised from its start: choose it below; nothing is sent until you do/)).toBeInTheDocument()
  await new Promise((r) => setTimeout(r, 900))  // longer than the auto-test delay
  expect(sent(calls, 'POST /api/copilot/test')).toHaveLength(0)
  await userEvent.selectOptions(within(box).getByLabelText('Which service is this key for?'), 'gemini')
  expect(await within(box).findByText('Works: Gemini is ready.', {}, { timeout: 3000 })).toBeInTheDocument()
  const tests = sent(calls, 'POST /api/copilot/test')
  expect(tests).toHaveLength(1)
  expect(tests[0].headers).toMatchObject({ 'X-LLM-Provider': 'gemini', 'X-LLM-Key': 'xyz-FAKE-key-WXYZ' })
})

test('"another OpenAI-compatible service" needs its base URL before anything is sent', async () => {
  const calls = recording({ ...BASE, 'POST /api/copilot/test': works })
  const box = await openBox()
  await userEvent.type(keyField(box), 'xyz-FAKE-key-WXYZ')
  await userEvent.selectOptions(within(box).getByLabelText('Which service is this key for?'), 'custom')
  await userEvent.click(keyField(box)); await userEvent.keyboard('{Enter}')
  expect(within(box).getByText(/Enter the service’s https base URL under Advanced; nothing is sent until then/)).toBeInTheDocument()
  expect(sent(calls, 'POST /api/copilot/test')).toHaveLength(0)
  await userEvent.type(within(box).getByLabelText(/^Base URL/), 'https://llm.example.com/v1')
  expect(await within(box).findByText('Works: The OpenAI-compatible service is ready.', {}, { timeout: 3000 })).toBeInTheDocument()
  expect(sent(calls, 'POST /api/copilot/test')[0].headers).toMatchObject({ 'X-LLM-Provider': 'openai', 'X-LLM-Base-URL': 'https://llm.example.com/v1' })
})

test('an Anthropic key is refused plainly and nothing is sent', async () => {
  const calls = recording({ ...BASE, 'POST /api/copilot/test': works })
  const box = await openBox()
  await userEvent.type(keyField(box), 'sk-ant-api03-FAKE-WXYZ{Enter}')
  expect(within(box).getByText('Anthropic keys are not supported yet: LogiMind has no Anthropic adapter, so nothing was sent.')).toBeInTheDocument()
  await new Promise((r) => setTimeout(r, 900))
  expect(sent(calls, 'POST /api/copilot/test')).toHaveLength(0)
})

test.each([
  [{ ok: false, kind: 'auth', message: 'Groq rejected this key. Check that the whole key was copied, with no spaces or quotes.' }],
  [{ ok: false, kind: 'rate_limit', message: 'Groq rate limit reached (HTTP 429); try again in 20 s, because free tiers allow only a few requests per minute.' }],
  [{ ok: false, kind: 'network', message: 'Groq could not be reached from the LogiMind server (ConnectError); check the internet connection or try again later.' }],
  [{ ok: false, kind: 'model', message: 'Groq lists no chat models for this key; type a model name in Copilot settings.' }],
])('a failed test (%#) is shown as the one plain sentence from the server', async (answer) => {
  recording({ ...BASE, 'POST /api/copilot/test': { provider: 'groq', model: null, ...answer } })
  const box = await openBox()
  await userEvent.type(keyField(box), `${KEYS.groq}{Enter}`)
  expect(await within(box).findByText(answer.message)).toBeInTheDocument()
  expect(within(box).queryByText(/^Works/)).not.toBeInTheDocument()
})

test('LogiMind’s own server being down is told apart from the provider being unreachable', async () => {
  globalThis.fetch = vi.fn(async (url) => {
    if (String(url).startsWith('/api/copilot/test')) throw new TypeError('Failed to fetch')
    const table = { '/api/health': BASE['GET /api/health'], '/api/whoami': BASE['GET /api/whoami'], '/api/copilot/status': BASE['GET /api/copilot/status'] }
    const hit = Object.entries(table).find(([k]) => String(url).startsWith(k))
    return { ok: true, status: 200, json: async () => hit[1] }
  })
  const box = await openBox()
  await userEvent.type(keyField(box), `${KEYS.groq}{Enter}`)
  expect(await within(box).findByText("LogiMind's own server is not answering, so the key could not be tested. Start LogiMind with start-dev.bat, then try again.")).toBeInTheDocument()
})

test('a successful test clears a stale "not available" badge at once', async () => {
  recording({ ...BASE, 'POST /api/copilot/test': works })
  renderPage(<Copilot />)
  expect(await screen.findByText(/^none: not available$/)).toBeInTheDocument()
  const box = screen.getByRole('form', { name: 'Copilot settings' })
  await userEvent.type(keyField(box), `${KEYS.groq}{Enter}`)
  expect(await screen.findByText('groq · auto-model-1')).toBeInTheDocument()
  expect(screen.queryByText(/not available/)).not.toBeInTheDocument()
})

test('the key field turns browser autofill off and is a password field', async () => {
  recording({ ...BASE })
  const box = await openBox()
  const f = keyField(box)
  expect(f).toHaveAttribute('type', 'password')
  expect(f).toHaveAttribute('autocomplete', 'new-password')
  expect(f).toHaveAttribute('data-lpignore', 'true')
  expect(f).toHaveAttribute('data-1p-ignore', 'true')
  expect(box).toHaveAttribute('autocomplete', 'off')
  expect(within(box).queryByLabelText('Provider')).not.toBeVisible()  // under "Advanced (optional)", closed
})

test('a refused base URL in Advanced is shown as the server’s sentence', async () => {
  sessionStorage.setItem('logimind.llm', JSON.stringify({ provider: 'openai', model: '', baseUrl: '', key: KEYS.openai }))
  const calls = recording({ ...BASE, 'POST /api/copilot/test': { __status: 400, body: { detail:
    'Copilot settings: OpenAI-compatible base URL: the base URL must start with https:// (plain http is allowed only for the local Ollama).' } } })
  renderPage(<Copilot />)
  await userEvent.click(await screen.findByText(/^Copilot settings/))
  const box = screen.getByRole('form', { name: 'Copilot settings' })
  await userEvent.click(within(box).getByText('Advanced (optional)'))
  await userEvent.type(within(box).getByLabelText(/^Base URL/), 'http://llm.example.com/v1')
  await userEvent.click(within(box).getByRole('button', { name: /test connection/i }))
  expect(await within(box).findByText(/must start with https:\/\//)).toBeInTheDocument()
  expect(sent(calls, 'POST /api/copilot/test')[0].headers['X-LLM-Base-URL']).toBe('http://llm.example.com/v1')
  expect(within(box).getByText(/paid services charge for every message/i)).toBeInTheDocument()
})

test('Clear key removes it from the tab, and later requests no longer carry it', async () => {
  const calls = recording({ ...BASE, 'POST /api/copilot/test': works,
    'GET /api/copilot/status': { available: true, provider: 'gemini', model: 'auto-model-1', reason: '', problem: '' },
    'POST /api/copilot/chat': { session_id: 's', kind: 'clarify', text: 'Which plan?', tool_calls: [] } })
  const box = await openBox()
  await userEvent.type(keyField(box), `${KEYS.gemini}{Enter}`)
  await within(box).findByText('••••WXYZ')
  await userEvent.click(within(box).getByRole('button', { name: /clear key/i }))
  expect(loadLlmSettings().key).toBe('')
  expect(within(box).queryByText('••••WXYZ')).not.toBeInTheDocument()
  await userEvent.type(screen.getByLabelText(/message to the copilot/i), 'hello')
  await userEvent.click(screen.getByRole('button', { name: /^send$/i }))
  await screen.findByText('Which plan?')
  const chat = sent(calls, 'POST /api/copilot/chat')[0]
  expect(chat.headers['X-LLM-Provider']).toBe('gemini')
  expect(chat.headers['X-LLM-Key']).toBeUndefined()
})

test('signing out clears the copilot settings with the sign-in', async () => {
  recording({ ...BASE })
  sessionStorage.setItem('logimind.llm', JSON.stringify({ provider: 'groq', model: 'm', baseUrl: '', key: KEYS.groq }))
  renderPage(<Login />)
  await userEvent.click(await screen.findByRole('button', { name: /sign out/i }))
  expect(sessionStorage.getItem('logimind.llm')).toBeNull()
})

test('settings the server refuses are shown as "Copilot settings not accepted", not as a missing local model', async () => {
  sessionStorage.setItem('logimind.llm', JSON.stringify({ provider: 'openai', model: 'm-1', baseUrl: 'http://x', key: KEYS.openai }))
  recording({ ...BASE, 'GET /api/copilot/status': { __status: 400, body: { detail:
    'Copilot settings: OpenAI-compatible base URL: the base URL must start with https://.' } } })
  renderPage(<Copilot />)
  expect(await screen.findByText('Copilot settings not accepted')).toBeInTheDocument()
  expect(screen.getByText('openai · m-1: not available')).toBeInTheDocument()
  expect(screen.queryByText(/no local model is available/i)).not.toBeInTheDocument()
  await waitFor(() => expect(document.body.textContent).not.toContain(KEYS.openai))
})

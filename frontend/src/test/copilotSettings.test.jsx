import '@testing-library/jest-dom/vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockFetch, renderPage } from './helpers'
import Copilot from '../pages/Copilot'
import Login from '../pages/Login'
import { setApiKey } from '../lib/api'
import { loadLlmSettings } from '../lib/llmSettings'

// Copilot settings box (decision 0033): the key stays in sessionStorage for the tab only, goes out as a header (never
// in a URL), shows only its last 4 characters, and every test result has a plain headline.
const KEY = 'sk-test-SECRET-abcd1234WXYZ'
const BASE = {
  'GET /api/health': { status: 'ok', environment: {}, research_endpoints: false },
  'GET /api/whoami': { tenant_id: 't', tenant_name: 'Acme', key_id: 'k' },
  'GET /api/copilot/status': { available: true, provider: 'fake', model: 'fake-deterministic', reason: '', problem: '' },
}

function recording(table) {
  const calls = []
  mockFetch(Object.fromEntries(Object.entries(table).map(([k, v]) => [k, (opts) => {
    calls.push({ key: k, headers: { ...(opts.headers || {}) } })
    return typeof v === 'function' ? v(opts) : v
  }])))
  return calls
}

async function openSettings() {
  renderPage(<Copilot />)
  await userEvent.click(await screen.findByText('Copilot settings'))
  return screen.getByRole('form', { name: 'Copilot settings' })
}

beforeEach(() => { sessionStorage.clear(); localStorage.clear(); setApiKey('lm_x_y') })

test('a pasted key is sent only as a header, kept only in sessionStorage, and shown as its last 4 characters', async () => {
  const calls = recording({ ...BASE, 'POST /api/copilot/test': { ok: true, kind: 'ok', provider: 'groq', model: 'm-1',
    message: 'Works: Groq accepted the key and offers the model m-1.' } })
  const box = await openSettings()
  await userEvent.selectOptions(within(box).getByLabelText('Provider'), 'groq')
  await userEvent.type(within(box).getByLabelText(/^Model name/), 'm-1')
  await userEvent.type(within(box).getByLabelText(/^Key/), KEY)
  expect(within(box).getByLabelText(/^Key/)).toHaveAttribute('type', 'password')
  await userEvent.click(within(box).getByRole('button', { name: /test connection/i }))
  expect(await within(box).findByText('Works')).toBeInTheDocument()
  const test = calls.find((c) => c.key === 'POST /api/copilot/test')
  expect(test.headers).toMatchObject({ 'X-LLM-Provider': 'groq', 'X-LLM-Model': 'm-1', 'X-LLM-Key': KEY })
  expect(globalThis.fetch.mock.calls.every(([url]) => !String(url).includes(KEY))).toBe(true)  // never in a URL
  expect(loadLlmSettings().key).toBe(KEY)
  expect(localStorage.length).toBe(0)
  expect(within(box).getByLabelText(/^Key/)).toHaveValue('')
  expect(within(box).getByText('••••WXYZ')).toBeInTheDocument()
  expect(document.body.textContent).not.toContain(KEY)
  // the status is asked again with the new settings, and chats carry them as headers
  await waitFor(() => expect(calls.filter((c) => c.key === 'GET /api/copilot/status' && c.headers['X-LLM-Key'] === KEY).length).toBeGreaterThan(0))
})

test.each([
  [{ ok: true, kind: 'ok', message: 'Works: …' }, 'Works'],
  [{ ok: false, kind: 'auth', message: 'Groq key missing or rejected (HTTP 401). Check the key in Copilot settings.' }, 'Key rejected'],
  [{ ok: false, kind: 'model', message: "Groq: model 'm-1' not found in its model list." }, 'Model not found'],
  [{ ok: false, kind: 'rate_limit', message: 'Groq rate limit reached (HTTP 429); try again in 20 s.' }, 'Rate limit reached'],
  [{ ok: false, kind: 'network', message: 'Groq could not be reached (ConnectError).' }, 'Not reachable'],
  [{ ok: false, kind: 'blocked', message: 'x points to a private or internal network address (10.0.0.5)' }, 'Address not allowed'],
])('test result %#: %s has a plain headline', async (answer, headline) => {
  recording({ ...BASE, 'POST /api/copilot/test': { provider: 'groq', model: 'm-1', ...answer } })
  const box = await openSettings()
  await userEvent.selectOptions(within(box).getByLabelText('Provider'), 'groq')
  await userEvent.type(within(box).getByLabelText(/^Key/), KEY)
  await userEvent.click(within(box).getByRole('button', { name: /test connection/i }))
  expect(await within(box).findByText(headline)).toBeInTheDocument()
  expect(within(box).getByText(answer.message)).toBeInTheDocument()
})

test('OpenAI-compatible asks for a base URL, and a refused URL is shown as "Settings not accepted"', async () => {
  const calls = recording({ ...BASE, 'POST /api/copilot/test': { __status: 400, body: { detail:
    'Copilot settings: OpenAI-compatible base URL: the base URL must start with https:// (plain http is allowed only for the local Ollama).' } } })
  const box = await openSettings()
  await userEvent.selectOptions(within(box).getByLabelText('Provider'), 'openai')
  await userEvent.type(within(box).getByLabelText(/^Base URL/), 'http://llm.example.com/v1')
  await userEvent.type(within(box).getByLabelText(/^Key/), KEY)
  await userEvent.click(within(box).getByRole('button', { name: /test connection/i }))
  expect(await within(box).findByText('Settings not accepted')).toBeInTheDocument()
  expect(within(box).getByText(/must start with https:\/\//)).toBeInTheDocument()
  expect(calls.find((c) => c.key === 'POST /api/copilot/test').headers['X-LLM-Base-URL']).toBe('http://llm.example.com/v1')
  expect(within(box).getByText(/paid services charge for every message/i)).toBeInTheDocument()
})

test('Clear key removes it from the tab, and later requests no longer carry it', async () => {
  const calls = recording({ ...BASE, 'POST /api/copilot/test': { ok: true, kind: 'ok', message: 'Works' },
    'POST /api/copilot/chat': { session_id: 's', kind: 'clarify', text: 'Which plan?', tool_calls: [] } })
  const box = await openSettings()
  await userEvent.selectOptions(within(box).getByLabelText('Provider'), 'gemini')
  await userEvent.type(within(box).getByLabelText(/^Key/), KEY)
  await userEvent.click(within(box).getByRole('button', { name: /test connection/i }))
  await within(box).findByText('••••WXYZ')
  await userEvent.click(within(box).getByRole('button', { name: /clear key/i }))
  expect(loadLlmSettings().key).toBe('')
  expect(within(box).queryByText('••••WXYZ')).not.toBeInTheDocument()
  await userEvent.type(screen.getByLabelText(/message to the copilot/i), 'hello')
  await userEvent.click(screen.getByRole('button', { name: /^send$/i }))
  await screen.findByText('Which plan?')
  const chat = calls.find((c) => c.key === 'POST /api/copilot/chat')
  expect(chat.headers['X-LLM-Provider']).toBe('gemini')
  expect(chat.headers['X-LLM-Key']).toBeUndefined()
})

test('signing out clears the copilot settings with the sign-in', async () => {
  recording({ ...BASE })
  sessionStorage.setItem('logimind.llm', JSON.stringify({ provider: 'groq', model: 'm', baseUrl: '', key: KEY }))
  renderPage(<Login />)
  await userEvent.click(await screen.findByRole('button', { name: /sign out/i }))
  expect(sessionStorage.getItem('logimind.llm')).toBeNull()
})

test('settings the server refuses are shown as "Copilot settings not accepted", not as a missing local model', async () => {
  sessionStorage.setItem('logimind.llm', JSON.stringify({ provider: 'openai', model: 'm-1', baseUrl: 'http://x', key: KEY }))
  recording({ ...BASE, 'GET /api/copilot/status': { __status: 400, body: { detail:
    'Copilot settings: OpenAI-compatible base URL: the base URL must start with https://.' } } })
  renderPage(<Copilot />)
  expect(await screen.findByText('Copilot settings not accepted')).toBeInTheDocument()
  expect(screen.getByText('openai · m-1: not available')).toBeInTheDocument()
  expect(screen.queryByText(/no local model is available/i)).not.toBeInTheDocument()
  expect(document.body.textContent).not.toContain(KEY)
})

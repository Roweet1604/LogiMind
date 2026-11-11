import '@testing-library/jest-dom/vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockFetch, renderPage } from './helpers'
import Copilot from '../pages/Copilot'
import { setApiKey } from '../lib/api'
import { loadLlmSettings } from '../lib/llmSettings'

// "Load models" under Advanced (decisions 0035, 0036): the list comes through our server with the key in a header;
// picking a model tests it at once; a list that cannot be fetched gives a plain reason and the text field stays.
const KEY = 'gsk_FAKE_test_key_WXYZ'
const BASE = {
  'GET /api/health': { status: 'ok', environment: {}, research_endpoints: false },
  'GET /api/whoami': { tenant_id: 't', tenant_name: 'Acme', key_id: 'k' },
  'GET /api/copilot/status': { available: true, provider: 'fake', model: 'fake-deterministic', reason: '', problem: '' },
}
const MODELS = { ok: true, kind: 'ok', provider: 'groq', models: ['llama-3.1-8b-instant', 'openai/gpt-oss-20b'],
  message: '2 chat models found. Pick one.' }

function recording(table) {
  const calls = []
  mockFetch(Object.fromEntries(Object.entries(table).map(([k, v]) => [k, (opts) => {
    calls.push({ key: k, headers: { ...(opts.headers || {}) } })
    return typeof v === 'function' ? v(opts) : v
  }])))
  return calls
}

// Groq chosen under Advanced, with the key in the main field (no automatic test: the advanced buttons decide).
async function advancedGroq() {
  sessionStorage.setItem('logimind.llm', JSON.stringify({ provider: 'groq', model: '', baseUrl: '', key: KEY }))
  renderPage(<Copilot />)
  await userEvent.click(await screen.findByText(/^Copilot settings/))
  const box = screen.getByRole('form', { name: 'Copilot settings' })
  await userEvent.click(within(box).getByText('Advanced (optional)'))
  return box
}

beforeEach(() => { sessionStorage.clear(); localStorage.clear(); setApiKey('lm_x_y') })

test('Load models fills a dropdown; picking a model fills the name and tests it at once', async () => {
  const calls = recording({ ...BASE, 'POST /api/copilot/models': MODELS,
    'POST /api/copilot/test': (opts) => ({ ok: true, kind: 'ok', provider: 'groq', model: opts.headers['X-LLM-Model'],
      message: 'Works' }) })
  const box = await advancedGroq()
  await userEvent.click(within(box).getByRole('button', { name: /load models/i }))
  const list = await within(box).findByLabelText(/^Available models \(2\)/)
  expect(within(box).getByText('2 chat models found. Pick one.')).toBeInTheDocument()
  expect(calls.find((c) => c.key === 'POST /api/copilot/models').headers).toMatchObject({ 'X-LLM-Provider': 'groq', 'X-LLM-Key': KEY })
  expect(globalThis.fetch.mock.calls.every(([url]) => !String(url).includes(KEY))).toBe(true)
  await userEvent.selectOptions(list, 'openai/gpt-oss-20b')
  expect(await within(box).findByText('Works: Groq is ready.')).toBeInTheDocument()
  expect(within(box).getByText('Model: openai/gpt-oss-20b')).toBeInTheDocument()
  expect(within(box).getByLabelText(/^Model/)).toHaveValue('openai/gpt-oss-20b')
  const test = calls.filter((c) => c.key === 'POST /api/copilot/test').at(-1)
  expect(test.headers).toMatchObject({ 'X-LLM-Model': 'openai/gpt-oss-20b', 'X-LLM-Key': KEY })
  expect(loadLlmSettings().model).toBe('openai/gpt-oss-20b')
  expect(localStorage.length).toBe(0)
  expect(document.body.textContent).not.toContain(KEY)
})

test.each([
  [{ ok: false, kind: 'auth', models: [], message: 'Groq rejected this key. Check that the whole key was copied, with no spaces or quotes.' }],
  [{ ok: false, kind: 'rate_limit', models: [], message: 'Groq rate limit reached (HTTP 429); try again in 20 s.' }],
  [{ ok: false, kind: 'network', models: [], message: 'Groq could not be reached from the LogiMind server (ConnectError).' }],
  [{ ok: false, kind: 'model', models: [], message: 'The provider answered, but its list has no chat models.' }],
])('a list that cannot be fetched (%#) gives a plain reason and keeps the text field', async (answer) => {
  recording({ ...BASE, 'POST /api/copilot/models': answer })
  const box = await advancedGroq()
  await userEvent.click(within(box).getByRole('button', { name: /load models/i }))
  expect(await within(box).findByText(`${answer.message} You can still type the model name.`)).toBeInTheDocument()
  expect(within(box).queryByLabelText(/^Available models/)).not.toBeInTheDocument()
  const field = within(box).getByLabelText(/^Model/)
  await userEvent.type(field, 'typed-model')
  expect(field).toHaveValue('typed-model')
})

test('a refused address for the list is said plainly, with the text field as fallback', async () => {
  recording({ ...BASE, 'POST /api/copilot/models': { __status: 400, body: { detail:
    'Copilot settings: OpenAI-compatible base URL: the base URL must start with https://.' } } })
  const box = await advancedGroq()
  await userEvent.selectOptions(within(box).getByLabelText('Provider'), 'openai')
  await userEvent.type(within(box).getByLabelText(/^Base URL/), 'http://llm.example.com/v1')
  await userEvent.click(within(box).getByRole('button', { name: /load models/i }))
  expect(await within(box).findByText(/must start with https:\/\/\. You can still type the model name/)).toBeInTheDocument()
})

test('with no model name, the model the server chose is kept for the tab and named', async () => {
  recording({ ...BASE, 'POST /api/copilot/test': { ok: true, kind: 'ok', provider: 'groq', model: 'openai/gpt-oss-20b',
    chosen_automatically: true, message: 'Works' } })
  const box = await advancedGroq()
  await userEvent.click(within(box).getByRole('button', { name: /test connection/i }))
  expect(await within(box).findByText('Model: openai/gpt-oss-20b (chosen automatically)')).toBeInTheDocument()
  expect(within(box).getByLabelText(/^Model/)).toHaveValue('openai/gpt-oss-20b')
  expect(loadLlmSettings()).toMatchObject({ provider: 'groq', model: 'openai/gpt-oss-20b', key: KEY })
})

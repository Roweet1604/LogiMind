import '@testing-library/jest-dom/vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockFetch, renderPage } from './helpers'
import Copilot from '../pages/Copilot'
import { setApiKey } from '../lib/api'
import { loadLlmSettings } from '../lib/llmSettings'

// "Load models" (decision 0035): the list comes through our server with the key in a header; picking a model tests it
// at once; a list that cannot be fetched gives a plain reason and the text field stays usable.
const KEY = 'sk-test-SECRET-abcd1234WXYZ'
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

async function groqWithKey() {
  renderPage(<Copilot />)
  await userEvent.click(await screen.findByText('Copilot settings'))
  const box = screen.getByRole('form', { name: 'Copilot settings' })
  await userEvent.selectOptions(within(box).getByLabelText('Provider'), 'groq')
  await userEvent.type(within(box).getByLabelText(/^Key/), KEY)
  return box
}

beforeEach(() => { sessionStorage.clear(); localStorage.clear(); setApiKey('lm_x_y') })

test('Load models fills a dropdown; picking a model fills the name and tests it at once', async () => {
  const calls = recording({ ...BASE, 'POST /api/copilot/models': MODELS,
    'POST /api/copilot/test': (opts) => ({ ok: true, kind: 'ok', provider: 'groq', model: opts.headers['X-LLM-Model'],
      message: `Works: Groq accepted the key and offers the model ${opts.headers['X-LLM-Model']}.` }) })
  const box = await groqWithKey()
  await userEvent.click(within(box).getByRole('button', { name: /load models/i }))
  const list = await within(box).findByLabelText(/^Available models \(2\)/)
  expect(within(box).getByText('Models loaded')).toBeInTheDocument()
  const load = calls.find((c) => c.key === 'POST /api/copilot/models')
  expect(load.headers).toMatchObject({ 'X-LLM-Provider': 'groq', 'X-LLM-Key': KEY })
  expect(globalThis.fetch.mock.calls.every(([url]) => !String(url).includes(KEY))).toBe(true)
  expect(within(box).getByText('••••WXYZ')).toBeInTheDocument()  // the key was kept for the tab, not shown

  await userEvent.selectOptions(list, 'openai/gpt-oss-20b')
  expect(await within(box).findByText('Works')).toBeInTheDocument()
  expect(within(box).getByText(/offers the model openai\/gpt-oss-20b/)).toBeInTheDocument()
  expect(within(box).getByLabelText(/^Model name/)).toHaveValue('openai/gpt-oss-20b')
  const test = calls.filter((c) => c.key === 'POST /api/copilot/test').at(-1)
  expect(test.headers).toMatchObject({ 'X-LLM-Model': 'openai/gpt-oss-20b', 'X-LLM-Key': KEY })
  expect(loadLlmSettings().model).toBe('openai/gpt-oss-20b')
  expect(localStorage.length).toBe(0)
  expect(document.body.textContent).not.toContain(KEY)
})

test.each([
  [{ ok: false, kind: 'auth', models: [], message: 'Groq key missing or rejected (HTTP 401). Check the key in Copilot settings.' }, 'Key rejected'],
  [{ ok: false, kind: 'rate_limit', models: [], message: 'Groq rate limit reached (HTTP 429); try again in 20 s.' }, 'Rate limit reached'],
  [{ ok: false, kind: 'network', models: [], message: 'Groq could not be reached (ConnectError).' }, 'Not reachable'],
  [{ ok: false, kind: 'model', models: [], message: 'The provider answered, but its list has no chat models.' }, 'Model not found'],
])('a list that cannot be fetched (%#) gives a plain reason and keeps the text field', async (answer, headline) => {
  recording({ ...BASE, 'POST /api/copilot/models': answer })
  const box = await groqWithKey()
  await userEvent.click(within(box).getByRole('button', { name: /load models/i }))
  expect(await within(box).findByText(headline)).toBeInTheDocument()
  expect(within(box).getByText(/you can still type the model name/i)).toBeInTheDocument()
  expect(within(box).queryByLabelText(/^Available models/)).not.toBeInTheDocument()
  const field = within(box).getByLabelText(/^Model name/)
  await userEvent.type(field, 'typed-model')
  expect(field).toHaveValue('typed-model')
})

test('a refused address for the list is "Settings not accepted", with the text field as fallback', async () => {
  recording({ ...BASE, 'POST /api/copilot/models': { __status: 400, body: { detail:
    'Copilot settings: OpenAI-compatible base URL: the base URL must start with https://.' } } })
  renderPage(<Copilot />)
  await userEvent.click(await screen.findByText('Copilot settings'))
  const box = screen.getByRole('form', { name: 'Copilot settings' })
  await userEvent.selectOptions(within(box).getByLabelText('Provider'), 'openai')
  await userEvent.type(within(box).getByLabelText(/^Base URL/), 'http://llm.example.com/v1')
  await userEvent.type(within(box).getByLabelText(/^Key/), KEY)
  await userEvent.click(within(box).getByRole('button', { name: /load models/i }))
  expect(await within(box).findByText('Settings not accepted')).toBeInTheDocument()
  expect(within(box).getByText(/must start with https:\/\/\. You can still type the model name/)).toBeInTheDocument()
})

test('with no model name, the model the server chose is written into the field and named in the result', async () => {
  recording({ ...BASE, 'POST /api/copilot/test': { ok: true, kind: 'ok', provider: 'groq', model: 'llama-3.1-8b-instant',
    chosen_automatically: true,
    message: 'Works: Groq accepted the key. No model name was given, so llama-3.1-8b-instant was chosen (the first chat model in its list).' } })
  const box = await groqWithKey()
  await userEvent.click(within(box).getByRole('button', { name: /test connection/i }))
  expect(await within(box).findByText(/so llama-3\.1-8b-instant was chosen/)).toBeInTheDocument()
  await waitFor(() => expect(within(box).getByLabelText(/^Model name/)).toHaveValue('llama-3.1-8b-instant'))
  expect(loadLlmSettings()).toMatchObject({ provider: 'groq', model: 'llama-3.1-8b-instant', key: KEY })
})

import '@testing-library/jest-dom/vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockFetch, renderPage } from './helpers'
import Copilot from '../pages/Copilot'
import { setApiKey } from '../lib/api'

// Optional hosted copilot providers (decision 0032): the panel names the provider and model, says plainly when a key
// is missing or rejected, and shows rate-limit and network errors as what they are. The key never reaches the console.
const BASE = {
  'GET /api/health': { status: 'ok', environment: {}, research_endpoints: false },
  'GET /api/whoami': { tenant_id: 't', tenant_name: 'Acme', key_id: 'k' },
}

beforeEach(() => { sessionStorage.clear(); localStorage.clear(); setApiKey('lm_x_y') })

test('a working hosted provider shows its name and model, and says what is sent to it', async () => {
  mockFetch({ ...BASE, 'GET /api/copilot/status': { available: true, provider: 'groq', model: 'openai/gpt-oss-20b',
    reason: 'hosted Groq model (optional free tier)', problem: '' } })
  renderPage(<Copilot />)
  expect(await screen.findByText('groq · openai/gpt-oss-20b')).toBeInTheDocument()
  expect(screen.getByText(/runs on groq's servers/i)).toHaveTextContent(/routes are not/i)
  expect(screen.getByLabelText(/message to the copilot/i)).toBeEnabled()
})

test('a missing or rejected key is a plain message in the panel, and the input is disabled', async () => {
  mockFetch({ ...BASE, 'GET /api/copilot/status': { available: false, provider: 'groq', model: 'openai/gpt-oss-20b',
    reason: 'Groq key missing or rejected: GROQ_API_KEY is empty in backend\\.env', problem: 'Groq key missing or rejected' } })
  renderPage(<Copilot />)
  expect(await screen.findByText('Groq key missing or rejected')).toBeInTheDocument()
  expect(screen.getByText(/GROQ_API_KEY is empty in backend\\\.env/)).toBeInTheDocument()
  expect(screen.getByText('groq · openai/gpt-oss-20b: not available')).toBeInTheDocument()
  expect(screen.queryByText(/no local model is available/i)).not.toBeInTheDocument()
  expect(screen.getByLabelText(/message to the copilot/i)).toBeDisabled()
})

test('a rate limit from the provider is shown as a rate limit, and nothing is stored in localStorage', async () => {
  mockFetch({ ...BASE,
    'GET /api/copilot/status': { available: true, provider: 'gemini', model: 'gemini-2.5-flash', reason: '', problem: '' },
    'POST /api/copilot/chat': { session_id: 's1', kind: 'error', llm_error: 'rate_limit', tool_calls: [],
      text: 'Gemini rate limit reached (HTTP 429); try again in 20 s. Free tiers allow only a few requests per minute.' } })
  renderPage(<Copilot />)
  await screen.findByText('gemini · gemini-2.5-flash')
  await userEvent.type(screen.getByLabelText(/message to the copilot/i), 'explain the latest plan')
  await userEvent.click(screen.getByRole('button', { name: /send/i }))
  expect(await screen.findByText(/rate limit reached \(HTTP 429\); try again in 20 s/)).toBeInTheDocument()
  expect(screen.getAllByText('error').length).toBeGreaterThan(0)
  expect(localStorage.length).toBe(0)
})

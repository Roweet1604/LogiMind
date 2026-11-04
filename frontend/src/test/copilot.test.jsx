import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockFetch, renderPage } from './helpers'
import Copilot from '../pages/Copilot'
import { setApiKey } from '../lib/api'

const BASE = {
  'GET /api/health': { status: 'ok', environment: {}, research_endpoints: false },
  'GET /api/instances': [], 'GET /api/whoami': { tenant_id: 't', tenant_name: 'Acme', key_id: 'k' },
}
const UP = { 'GET /api/copilot/status': { available: true, provider: 'ollama', model: 'llama3.2:3b' } }
const PID = 'plan-0123456789ab'

function recording(table) {
  const bodies = []
  mockFetch(Object.fromEntries(Object.entries(table).map(([k, v]) => [k, (opts) => {
    if (opts.body) bodies.push({ key: k, body: JSON.parse(opts.body) })
    return typeof v === 'function' ? v(opts) : v
  }])))
  return bodies
}

beforeEach(() => { sessionStorage.clear(); setApiKey('lm_x_y') })

test('Copilot: with no local model it says so plainly and the input is disabled', async () => {
  recording({ ...BASE, 'GET /api/copilot/status': { available: false, provider: 'ollama', reason: 'no local model available: Ollama is not running at http://localhost:11434' } })
  renderPage(<Copilot />)
  expect(await screen.findByText(/no local model is available/i)).toBeInTheDocument()
  expect(screen.getByText(/ollama is not running/i)).toBeInTheDocument()
  expect(screen.getByLabelText(/message to the copilot/i)).toBeDisabled()
  expect(screen.getByRole('button', { name: /send/i })).toBeDisabled()
})

test('Copilot: an answer shows its text, the tools used and links to plans', async () => {
  const bodies = recording({
    ...BASE, ...UP,
    'POST /api/copilot/chat': { session_id: 'chat-1', kind: 'answer', text: `Plan ${PID} (OR-Tools): accepted.`,
      tool_calls: [{ tool: 'validate_routes', args: { plan_id: PID }, output: { plan_id: PID, feasible: true } }] },
  })
  renderPage(<Copilot />)
  const input = await screen.findByLabelText(/message to the copilot/i)
  await waitFor(() => expect(input).not.toBeDisabled())
  await userEvent.type(input, 'is the latest plan valid?')
  await userEvent.click(screen.getByRole('button', { name: /send/i }))
  expect(await screen.findByText(/accepted\./)).toBeInTheDocument()
  expect(screen.getByText(/tool results used: validate_routes/i)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: PID })).toHaveAttribute('href', `/plans/${PID}`)
  expect(bodies[0].body).toEqual({ message: 'is the latest plan valid?', session_id: null })
})

test('Copilot: a replan waits for Confirm and sends the pending id once', async () => {
  const bodies = recording({
    ...BASE, ...UP,
    'POST /api/copilot/chat': { session_id: 'chat-1', kind: 'confirm', pending_id: 'pend-1', text: 'This replans active plan. Confirm?', tool_calls: [] },
    'POST /api/copilot/confirm': { session_id: 'chat-1', kind: 'answer', text: 'Replanned. Plan feasible.', tool_calls: [] },
  })
  renderPage(<Copilot />)
  const input = await screen.findByLabelText(/message to the copilot/i)
  await waitFor(() => expect(input).not.toBeDisabled())
  await userEvent.type(input, 'truck 1 broke down')
  await userEvent.click(screen.getByRole('button', { name: /send/i }))
  await userEvent.click(await screen.findByRole('button', { name: /confirm replan/i }))
  expect(await screen.findByText('Replanned. Plan feasible.')).toBeInTheDocument()
  expect(bodies.find((b) => b.key === 'POST /api/copilot/confirm').body).toEqual({ session_id: 'chat-1', pending_id: 'pend-1', approve: true })
  expect(screen.queryByRole('button', { name: /confirm replan/i })).not.toBeInTheDocument()  // used once
})

test('Copilot: cancel sends approve=false; a clarifying question is shown as a question', async () => {
  let n = 0
  const bodies = recording({
    ...BASE, ...UP,
    'POST /api/copilot/chat': () => (n++ === 0
      ? { session_id: 'chat-1', kind: 'confirm', pending_id: 'pend-2', text: 'Confirm?', tool_calls: [] }
      : { session_id: 'chat-1', kind: 'clarify', text: 'Which vehicle broke down?', tool_calls: [] }),
    'POST /api/copilot/confirm': { session_id: 'chat-1', kind: 'answer', text: 'Cancelled. The plan was not changed.', tool_calls: [] },
  })
  renderPage(<Copilot />)
  const input = await screen.findByLabelText(/message to the copilot/i)
  await waitFor(() => expect(input).not.toBeDisabled())
  await userEvent.type(input, 'replan')
  await userEvent.click(screen.getByRole('button', { name: /send/i }))
  await userEvent.click(await screen.findByRole('button', { name: /cancel/i }))
  expect(await screen.findByText(/not changed/)).toBeInTheDocument()
  expect(bodies.find((b) => b.key === 'POST /api/copilot/confirm').body.approve).toBe(false)
  await userEvent.type(input, 'a truck broke')
  await userEvent.click(screen.getByRole('button', { name: /send/i }))
  expect(await screen.findByText('Which vehicle broke down?')).toBeInTheDocument()
  expect(screen.getByText('question')).toBeInTheDocument()
  expect(bodies.filter((b) => b.key === 'POST /api/copilot/chat')[1].body.session_id).toBe('chat-1')
})

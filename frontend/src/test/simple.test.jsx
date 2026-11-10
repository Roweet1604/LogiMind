import '@testing-library/jest-dom/vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { mockFetch, renderPage } from './helpers'
import Layout from '../components/Layout'
import Drivers from '../pages/Drivers'
import Overview from '../pages/Overview'
import Plans from '../pages/Plans'
import { getApiKey, setApiKey } from '../lib/api'

// Simpler console (decision 0031): short sidebar, Research only in research mode, plain errors, Retry on outage.
const ME = { tenant_id: 'ten-1', tenant_name: 'Acme Fleet', key_id: 'key-1' }
const health = (research) => ({ 'GET /api/health': { status: 'ok', environment: {}, research_endpoints: research } })
const PLANS = [
  { plan_id: 'plan-ok', name: 'Morning (synthetic demo)', state: 'completed', engine: 'ortools', feasible: true, n_customers: 4 },
  { plan_id: 'plan-bad', name: 'Broken', state: 'completed', engine: 'ga', feasible: false, n_customers: 4 },
  { plan_id: 'plan-q', name: 'Waiting', state: 'queued', engine: 'ortools', feasible: null, n_customers: 3 },
]

const shell = (route = '/') => renderPage(
  <Routes><Route element={<Layout />}>
    <Route index element={<Overview />} /><Route path="/plans" element={<Plans />} /><Route path="/setup" element={<p>setup page</p>} />
  </Route></Routes>, { route })

beforeEach(() => { sessionStorage.clear(); localStorage.clear(); setApiKey('') })

test('sidebar in normal mode: Overview, Plans, Drivers, Copilot and Account only', async () => {
  setApiKey('lm_k_s')
  mockFetch({ ...health(false), 'GET /api/whoami': ME, 'GET /api/plans': [] })
  shell()
  const nav = screen.getByRole('navigation', { name: 'Main' })
  await waitFor(() => expect(screen.getByText('server connected')).toBeInTheDocument())
  expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['Overview', 'Plans', 'Drivers', 'Copilot', 'Account'])
  expect(screen.queryByText(/current research instance/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/benchmark lab/i)).not.toBeInTheDocument()
})

test('sidebar in research mode: one Research link; its pages appear inside it', async () => {
  mockFetch({ ...health(true), 'GET /api/instances': [] })
  const { unmount } = shell()
  const nav = screen.getByRole('navigation', { name: 'Main' })
  expect(await within(nav).findByRole('link', { name: 'Research' })).toHaveAttribute('href', '/research')
  expect(within(nav).queryByRole('link', { name: /benchmark lab/i })).not.toBeInTheDocument()
  unmount()
  shell('/setup')
  const nav2 = screen.getByRole('navigation', { name: 'Main' })
  expect(await within(nav2).findByRole('link', { name: /benchmark lab/i })).toBeInTheDocument()
  expect(within(nav2).getByRole('link', { name: /methodology/i })).toBeInTheDocument()
  expect(screen.getByText(/current research instance/i)).toBeInTheDocument()
})

test('server not running: the session is kept, the message is plain, and Retry signs back in', async () => {
  setApiKey('lm_k_s')
  let up = false
  globalThis.fetch = vi.fn(async (url) => {
    if (!up) throw new TypeError('Failed to fetch')
    const body = String(url).startsWith('/api/whoami') ? ME : String(url).startsWith('/api/plans') ? [] : { status: 'ok', environment: {}, research_endpoints: false }
    return { ok: true, status: 200, json: async () => body }
  })
  shell('/plans')
  const alert = await screen.findByText(/the server isn't running\. run start-dev\.bat/i, { selector: 'span' })
  expect(alert).toBeInTheDocument()
  expect(document.body.textContent).not.toMatch(/uvicorn|port 8000|LOGIMIND_/)
  expect(screen.queryByText(/sign in first/i)).not.toBeInTheDocument()
  expect(getApiKey()).toBe('lm_k_s')                       // not signed out
  up = true
  await userEvent.click(screen.getAllByRole('button', { name: /retry/i })[0])
  expect(await screen.findByText(/no plans yet/i)).toBeInTheDocument()
  expect(screen.getByText('Acme Fleet')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
})

test('the dev proxy answering 502 without a body also counts as "server not running"', async () => {
  setApiKey('lm_k_s')
  globalThis.fetch = vi.fn(async () => ({ ok: false, status: 502, json: async () => { throw new SyntaxError('empty') } }))
  shell('/plans')
  expect((await screen.findAllByRole('button', { name: /retry/i })).length).toBeGreaterThan(0)
  expect(getApiKey()).toBe('lm_k_s')
})

test('a rejected key still signs the tab out', async () => {
  setApiKey('lm_revoked_s')
  mockFetch({ ...health(false), 'GET /api/whoami': { __status: 401, body: { detail: 'missing, invalid or revoked API key' } } })
  shell('/plans')
  expect(await screen.findByText(/sign in first/i)).toBeInTheDocument()
  expect(getApiKey()).toBe('')
})

test('Overview shows the plan counts from the validator verdicts', async () => {
  setApiKey('lm_k_s')
  mockFetch({ ...health(false), 'GET /api/whoami': ME, 'GET /api/plans': PLANS })
  shell('/')
  expect(await screen.findByText('Morning (synthetic demo)')).toBeInTheDocument()
  const stat = (label) => screen.getByText(label, { selector: 'dt' }).nextElementSibling.textContent
  expect(stat('Plans')).toBe('3')
  expect(stat('Feasible')).toBe('1')
  expect(stat('Being solved')).toBe('1')
  expect(stat('Need attention')).toBe('1')
})

test('Drivers offers only feasible plans and shows that plan\'s driver links', async () => {
  setApiKey('lm_k_s')
  const plan = { ...PLANS[0], instance: { customers: [] }, result: { solve: { routes: [[1, 2], [3]] } } }
  mockFetch({
    ...health(false), 'GET /api/whoami': ME,
    'GET /api/plans/plan-ok/driver-links': [], 'GET /api/plans/plan-ok/stop-reports': { events: [], photos: [] },
    'GET /api/plans/plan-ok': plan, 'GET /api/plans': PLANS,
  })
  renderPage(<Drivers />)
  const select = await screen.findByLabelText('Plan')
  expect(within(select).getAllByRole('option').map((o) => o.value)).toEqual(['plan-ok'])
  expect(await screen.findByRole('button', { name: 'Driver link for route 1' })).toBeInTheDocument()
})

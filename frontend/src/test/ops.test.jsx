import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { mockFetch, renderPage } from './helpers'
import Layout from '../components/Layout'
import Login from '../pages/Login'
import Plans from '../pages/Plans'
import PlanDetail from '../pages/PlanDetail'
import { getApiKey, setApiKey } from '../lib/api'

vi.mock('../components/RouteMap', () => ({ default: () => <div data-testid="map" /> }))

const KEY = 'lm_abc123_secret'
const HEALTH = { 'GET /api/health': { status: 'ok', environment: {}, research_endpoints: false } }
const ME = { tenant_id: 'ten-1', tenant_name: 'Acme Fleet', key_id: 'key-1' }
const INST = {
  instance_id: 'inst-1', name: 'orders.csv', metric: 'euclidean', depot: { x: 50, y: 50 }, has_time_windows: false,
  customers: [1, 2, 3, 4].map((id) => ({ id, x: id * 10, y: 5, demand: 1 })), vehicle_count: 2, vehicle_capacity: 10,
}
const PLAN = {
  plan_id: 'plan-1', state: 'completed', engine: 'ortools', requested_engine: 'auto', status: 'solved', feasible: true,
  instance: INST, selection: { method: 'model', explanation: 'Chose OR-Tools because of tight windows.' },
  result: { solve: { routes: [[1, 2], [3, 4]] }, validation: { feasible: true, violations: [] },
    metrics: { total_distance: 123.4, vehicles_used: 2 } },
}

// Records each request's headers and body so tests can check what the console sent.
function recordingFetch(table) {
  const calls = []
  mockFetch(Object.fromEntries(Object.entries(table).map(([k, v]) => [k, (opts) => {
    calls.push({ key: k, headers: opts.headers || {}, body: opts.body })
    return typeof v === 'function' ? v(opts) : v
  }])))
  return calls
}

beforeEach(() => { sessionStorage.clear(); localStorage.clear(); setApiKey('') })

test('Login: a rejected key shows a clear error and is not kept', async () => {
  recordingFetch({ ...HEALTH, 'GET /api/instances': [], 'GET /api/whoami': { __status: 401, body: { detail: 'missing, invalid or revoked API key' } } })
  renderPage(<Login />)
  await userEvent.type(screen.getByLabelText(/api key/i), 'lm_bad_key')
  await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
  expect(await screen.findByRole('alert')).toHaveTextContent(/not accepted/i)
  expect(getApiKey()).toBe('')
  expect(sessionStorage.getItem('logimind.apiKey')).toBeNull()
})

test('Login: a good key is sent as X-API-Key, kept for the tab only, and used for plans', async () => {
  const calls = recordingFetch({ ...HEALTH, 'GET /api/instances': [], 'GET /api/whoami': ME, 'GET /api/plans': [] })
  renderPage(<Routes><Route path="/" element={<Login />} /><Route path="/plans" element={<Plans />} /></Routes>)
  await userEvent.type(screen.getByLabelText(/api key/i), KEY)
  await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
  expect(await screen.findByText(/no plans yet/i)).toBeInTheDocument()
  expect(calls.find((c) => c.key === 'GET /api/whoami').headers['X-API-Key']).toBe(KEY)
  expect(calls.find((c) => c.key === 'GET /api/plans').headers['X-API-Key']).toBe(KEY)
  expect(sessionStorage.getItem('logimind.apiKey')).toBe(KEY)
  expect(localStorage.getItem('logimind.apiKey')).toBeNull()
})

test('Plans: import shows the row-level report and blocks the plan until the file is fixed', async () => {
  setApiKey(KEY)
  recordingFetch({
    ...HEALTH, 'GET /api/instances': [], 'GET /api/whoami': ME, 'GET /api/plans': [],
    'POST /api/orders/import': { ok: false, rows: 2, valid_rows: 1, invalid_rows: 1, coordinates: 'xy', customers: [],
      issues: [{ row: 3, field: 'demand', message: 'must be a whole number > 0' }] },
  })
  renderPage(<Plans />)
  await userEvent.upload(await screen.findByLabelText(/order file/i), new File(['id,x,y,demand'], 'o.csv', { type: 'text/csv' }))
  expect(await screen.findByText(/1 of 2 rows have problems/i)).toBeInTheDocument()
  expect(screen.getByText('must be a whole number > 0')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /create plan/i })).toBeDisabled()
})

test('Plans: a valid import creates a plan with the chosen engine and the fleet from the form', async () => {
  setApiKey(KEY)
  const calls = recordingFetch({  // the mock matches by prefix, so the specific plan comes before the list
    ...HEALTH, 'GET /api/instances': [], 'GET /api/whoami': ME,
    'GET /api/plans/plan-9': { ...PLAN, plan_id: 'plan-9', state: 'queued', result: null }, 'GET /api/plans': [],
    'POST /api/orders/import': { ok: true, rows: 1, valid_rows: 1, invalid_rows: 0, coordinates: 'xy', issues: [],
      customers: [{ id: 1, x: 1, y: 2, demand: 3 }] },
    'POST /api/plans': { plan_id: 'plan-9', state: 'queued' },
  })
  renderPage(<Routes><Route path="/" element={<Plans />} /><Route path="/plans/:id" element={<PlanDetail />} /></Routes>)
  await userEvent.upload(await screen.findByLabelText(/order file/i), new File(['x'], 'o.csv', { type: 'text/csv' }))
  await screen.findByText(/1 orders ready/i)
  await userEvent.selectOptions(screen.getByLabelText(/^engine/i), 'ortools')
  await userEvent.click(screen.getByRole('button', { name: /create plan/i }))
  await waitFor(() => expect(calls.some((c) => c.key === 'POST /api/plans')).toBe(true))
  const body = JSON.parse(calls.find((c) => c.key === 'POST /api/plans').body)
  expect(body.engine).toBe('ortools')
  expect(body.instance.customers).toEqual([{ id: 1, x: 1, y: 2, demand: 3 }])
  expect(body.instance.vehicle_count).toBe(3)
  expect(await screen.findByText(/this page updates by itself/i)).toBeInTheDocument()
})

test('Plan detail: shows the validator verdict, the engine explanation and the routes', async () => {
  setApiKey(KEY)
  recordingFetch({ ...HEALTH, 'GET /api/instances': [], 'GET /api/whoami': ME, 'GET /api/plans/plan-1': PLAN })
  renderPage(<Routes><Route path="/plans/:id" element={<PlanDetail />} /></Routes>, { route: '/plans/plan-1' })
  expect(await screen.findByText('feasible')).toBeInTheDocument()
  expect(screen.getByText(/tight windows/)).toBeInTheDocument()
  expect(screen.getByText('123.40')).toBeInTheDocument()
  expect(screen.getByText('1 → 2')).toBeInTheDocument()
})

test('Plan detail: an infeasible plan says so and cannot be replanned', async () => {
  setApiKey(KEY)
  const bad = { ...PLAN, feasible: false, result: { ...PLAN.result, validation: { feasible: false, violations: [{ detail: 'route 0 load 12 exceeds capacity 10' }] } } }
  recordingFetch({ ...HEALTH, 'GET /api/instances': [], 'GET /api/whoami': ME, 'GET /api/plans/plan-1': bad })
  renderPage(<Routes><Route path="/plans/:id" element={<PlanDetail />} /></Routes>, { route: '/plans/plan-1' })
  expect(await screen.findByText(/not a feasible plan/i)).toBeInTheDocument()
  expect(screen.getByText(/exceeds capacity 10/)).toBeInTheDocument()
  expect(screen.getByText(/replanning needs a completed, feasible plan/i)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /^replan$/i })).not.toBeInTheDocument()
})

async function openReplan(calls) {
  renderPage(<Routes><Route path="/plans/:id" element={<PlanDetail />} /></Routes>, { route: '/plans/plan-1' })
  await screen.findByText('Replan after a disruption')
  await userEvent.clear(screen.getByLabelText(/vehicle 0 \(of 2\)/i))
  await userEvent.type(screen.getByLabelText(/vehicle 0 \(of 2\)/i), '1')
  return () => JSON.parse(calls.find((c) => c.key === 'POST /api/plans/plan-1/replan').body)
}

const replanTable = () => ({
  ...HEALTH, 'GET /api/instances': [], 'GET /api/whoami': ME, 'GET /api/plans/plan-1': PLAN,
  'POST /api/plans/plan-1/replan': { plan_id: 'plan-2', state: 'queued' },
  'GET /api/plans/plan-2': { ...PLAN, plan_id: 'plan-2', state: 'running', result: null },
})

test('Replan: vehicle breakdown sends the broken vehicle and the completed stops', async () => {
  setApiKey(KEY)
  const calls = recordingFetch(replanTable())
  const body = await openReplan(calls)
  await userEvent.selectOptions(screen.getByLabelText(/broken-down vehicle/i), '1')
  await userEvent.click(screen.getByRole('button', { name: /^replan$/i }))
  await waitFor(() => expect(calls.some((c) => c.key === 'POST /api/plans/plan-1/replan')).toBe(true))
  expect(body()).toEqual({ event: { type: 'vehicle_breakdown', vehicle: 1, completed: { 0: 1 } }, engine: 'ortools', time_limit_s: 3 })
  expect(await screen.findByText(/this page updates by itself/i)).toBeInTheDocument()
})

test('Replan: failed delivery offers only unfinished stops and sends retry', async () => {
  setApiKey(KEY)
  const calls = recordingFetch(replanTable())
  const body = await openReplan(calls)
  await userEvent.click(screen.getByRole('tab', { name: /failed delivery/i }))
  const select = screen.getByLabelText(/customer whose delivery failed/i)
  expect([...select.options].map((o) => o.value)).toEqual(['', '2', '3', '4'])  // customer 1 is completed
  await userEvent.selectOptions(select, '3')
  await userEvent.click(screen.getByRole('checkbox', { name: /visit again later/i }))
  await userEvent.click(screen.getByRole('button', { name: /^replan$/i }))
  await waitFor(() => expect(calls.some((c) => c.key === 'POST /api/plans/plan-1/replan')).toBe(true))
  expect(body().event).toEqual({ type: 'failed_delivery', customer_id: 3, retry: false, completed: { 0: 1 } })
})

test('Replan: urgent order sends the new customer; GA is disabled while stops are completed', async () => {
  setApiKey(KEY)
  const calls = recordingFetch(replanTable())
  const body = await openReplan(calls)
  await userEvent.click(screen.getByRole('tab', { name: /urgent order/i }))
  expect(screen.getByRole('option', { name: /ga \+ local search/i })).toBeDisabled()
  await userEvent.clear(screen.getByLabelText(/^demand/i))
  await userEvent.type(screen.getByLabelText(/^demand/i), '2')
  await userEvent.click(screen.getByRole('button', { name: /^replan$/i }))
  await waitFor(() => expect(calls.some((c) => c.key === 'POST /api/plans/plan-1/replan')).toBe(true))
  expect(body().event).toEqual({ type: 'urgent_order', customer: { id: 5, x: 50, y: 50, demand: 2 }, completed: { 0: 1 } })
})

test('Replan: a refused replan shows the backend reason', async () => {
  setApiKey(KEY)
  recordingFetch({ ...replanTable(), 'POST /api/plans/plan-1/replan': { __status: 422, body: { detail: 'vehicle 9 does not exist (0..1)' } } })
  await openReplan([])
  await userEvent.click(screen.getByRole('button', { name: /^replan$/i }))
  expect(await screen.findByText(/does not exist/)).toBeInTheDocument()
})

test('Layout: research pages explain that they are off and point to Plans', async () => {
  recordingFetch({ ...HEALTH, 'GET /api/instances': { __status: 403, body: { detail: 'research endpoints are disabled' } } })
  renderPage(<Routes><Route element={<Layout />}><Route path="/setup" element={<p>setup page</p>} /></Route></Routes>, { route: '/setup' })
  expect(await screen.findByText(/research pages are switched off/i)).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: /plans/i }).length).toBeGreaterThan(0)
})

test('Plan detail: a dispatcher makes a driver link per route, sees reports and can revoke', async () => {
  setApiKey(KEY)
  const link = { link_id: 'dlk-1', plan_id: 'plan-1', route_index: 1, expires_at: '2027-01-15T20:00:00+00:00', revoked_at: null }
  let links = []
  const calls = recordingFetch({
    ...HEALTH, 'GET /api/instances': [], 'GET /api/whoami': ME,
    'GET /api/plans/plan-1/driver-links': () => links,
    'GET /api/plans/plan-1/stop-reports': { plan_id: 'plan-1', photos: [{ customer_id: 3 }],
      events: [{ customer_id: 3, route_index: 1, status: 'failed', reason: 'not_home', note: '', received_at: '2027-01-15T09:00:00Z' }] },
    'POST /api/plans/plan-1/driver-links': () => { links = [link]; return { ...link, token: 'dl1.x.y', url: 'http://localhost:5174/#t=dl1.x.y' } },
    'DELETE /api/driver-links/dlk-1': () => { links = [{ ...link, revoked_at: '2027-01-15T10:00:00Z' }]; return links[0] },
    'GET /api/plans/plan-1': PLAN,
  })
  renderPage(<Routes><Route path="/plans/:id" element={<PlanDetail />} /></Routes>, { route: '/plans/plan-1' })
  expect(await screen.findByText(/failed \(nobody home\)/)).toBeInTheDocument()
  expect(screen.getByText('1 of 2')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Driver link for route 1' }))
  expect(await screen.findByLabelText('Driver link')).toHaveValue('http://localhost:5174/#t=dl1.x.y')
  expect(JSON.parse(calls.find((c) => c.key === 'POST /api/plans/plan-1/driver-links').body)).toEqual({ route_index: 1 })
  await userEvent.click(await screen.findByRole('button', { name: 'Revoke link for route 1' }))
  await waitFor(() => expect(calls.some((c) => c.key === 'DELETE /api/driver-links/dlk-1')).toBe(true))
  await waitFor(() => expect(screen.queryByLabelText('Driver link')).not.toBeInTheDocument())
})

test('Plan detail: an infeasible plan offers no driver links', async () => {
  setApiKey(KEY)
  const bad = { ...PLAN, feasible: false, result: { ...PLAN.result, validation: { feasible: false, violations: [] } } }
  recordingFetch({ ...HEALTH, 'GET /api/instances': [], 'GET /api/whoami': ME, 'GET /api/plans/plan-1': bad })
  renderPage(<Routes><Route path="/plans/:id" element={<PlanDetail />} /></Routes>, { route: '/plans/plan-1' })
  expect(await screen.findByText(/not a feasible plan/i)).toBeInTheDocument()
  expect(screen.queryByText('Drivers')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /driver link/i })).not.toBeInTheDocument()
})

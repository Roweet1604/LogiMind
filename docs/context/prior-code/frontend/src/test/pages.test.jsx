import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { INSTANCE, mockFetch, renderPage } from './helpers'
import ProblemSetup from '../pages/ProblemSetup'
import Compare from '../pages/Compare'

vi.mock('../components/RouteMap', () => ({ default: () => <div data-testid="map" /> }))
vi.mock('recharts', () => {
  const Stub = ({ children }) => <div>{children}</div>
  return {
    ResponsiveContainer: Stub, BarChart: Stub, Bar: Stub, Cell: Stub, LineChart: Stub, Line: Stub, XAxis: Stub, YAxis: Stub,
    CartesianGrid: Stub, Tooltip: Stub, Legend: Stub, ReferenceLine: Stub, ErrorBar: Stub,
  }
})

beforeEach(() => localStorage.clear())

const BASE = {
  'GET /api/health': { status: 'ok', environment: { python: '3', ortools: '9', cpu_count: 1 } },
  'GET /api/instances/inst-test000001': INSTANCE,
}

test('Problem setup: shows the backend validation reasons on error', async () => {
  mockFetch({
    ...BASE, 'GET /api/instances': [],
    'POST /api/instances/generate': { __status: 422, body: { detail: { message: 'invalid instance', errors: ['total demand 99 exceeds total fleet capacity 40'] } } },
  })
  renderPage(<ProblemSetup />)
  await userEvent.click(await screen.findByRole('button', { name: /generate and load/i }))
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('invalid instance')
  expect(alert).toHaveTextContent('exceeds total fleet capacity')
})

test('Problem setup: shows loading then the inspected scenario on success', async () => {
  mockFetch({
    ...BASE, 'GET /api/instances': [], 'POST /api/instances/generate': INSTANCE,
  })
  renderPage(<ProblemSetup />)
  expect(screen.getByText(/no instance loaded/i)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: /generate and load/i }))
  expect(await screen.findByText('inst-test000001', { selector: 'span' })).toBeInTheDocument()
  expect(screen.getByText('1 × 4')).toBeInTheDocument()
  expect(screen.getByText(/vehicle × capacity/)).toBeInTheDocument()
  expect(screen.getByTestId('map')).toBeInTheDocument()
})

test('Problem setup: bad CSV is rejected client-side with row messages', async () => {
  mockFetch({ ...BASE, 'GET /api/instances': [] })
  renderPage(<ProblemSetup />)
  await userEvent.click(screen.getByRole('tab', { name: /import csv/i }))
  const file = new File(['id,x,y,demand\n1,2'], 'c.csv', { type: 'text/csv' })
  await userEvent.upload(screen.getByLabelText(/csv file/i), file)
  expect(await screen.findByText(/Row 2/)).toBeInTheDocument()
})

const run = (id, algo, extra = {}) => ({
  run_id: id, instance_id: 'inst-test000001', algorithm: algo, state: 'completed', created_at: '2026-10-12T10:00:00+00:00',
  row: { feasible: true, total_distance: 12, seed: algo === 'ga' ? 0 : null }, ...extra,
})

test('Compare: empty state when the instance has no runs', async () => {
  localStorage.setItem('routeopt.currentInstance', 'inst-test000001')
  mockFetch({ ...BASE, 'GET /api/instances': [], 'GET /api/runs?instance_id': [] })
  renderPage(<Compare />)
  expect(await screen.findByText(/nothing to compare yet/i)).toBeInTheDocument()
})

test('Compare: shows measured values, a dash for a failed solver, and no winner without two feasible runs', async () => {
  localStorage.setItem('routeopt.currentInstance', 'inst-test000001')
  const detailOr = {
    ...run('r1', 'ortools'), result: { status: 'solved', runtime_seconds: 3.01, routes: [[1, 2]], config: { time_limit_s: 3 }, diagnostics: {} },
    validation: { feasible: true, violations: [] },
    metrics: { total_distance: 12, estimated_cost: 12, vehicles_used: 1, unserved_customers: 0, capacity_violations: 0, other_violations: 0 },
  }
  const detailGa = {
    ...run('r2', 'ga', { row: { feasible: null, total_distance: null, seed: 0 } }),
    result: { status: 'no_solution', runtime_seconds: 1, routes: null, seed: 0, config: {}, diagnostics: {}, message: 'none' },
    validation: null, metrics: null,
  }
  mockFetch({
    ...BASE, 'GET /api/instances': [],
    'GET /api/runs?instance_id': [run('r1', 'ortools'), run('r2', 'ga', { row: { feasible: null, total_distance: null, seed: 0 } })],
    'GET /api/runs/r1': detailOr, 'GET /api/runs/r2': detailGa,
  })
  renderPage(<Compare />)
  await waitFor(() => expect(screen.getByText('Total distance', { selector: 'td' })).toBeInTheDocument())
  const row = screen.getByText('Total distance', { selector: 'td' }).closest('tr')
  expect(row).toHaveTextContent('12.00')
  expect(row).toHaveTextContent('—')
  expect(row).not.toHaveTextContent('↓')
  expect(screen.getByText(/returned no solution/i)).toBeInTheDocument()
})

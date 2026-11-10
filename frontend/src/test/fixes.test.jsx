import '@testing-library/jest-dom/vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { mockFetch, renderPage } from './helpers'
import Plans, { centreOf } from '../pages/Plans'
import PlanDetail from '../pages/PlanDetail'
import { asUtc, fmtTime } from '../lib/format'
import { setApiKey } from '../lib/api'

// Bugs found in the browser walk-through of 10 Nov 2026 (docs/report/demo/README.md).
vi.mock('../components/RouteMap', () => ({ default: () => <div data-testid="map" /> }))
const ME = { tenant_id: 't', tenant_name: 'Acme', key_id: 'k' }
const BASE = { 'GET /api/health': { status: 'ok', environment: {}, research_endpoints: false }, 'GET /api/whoami': ME }

beforeEach(() => { sessionStorage.clear(); setApiKey('lm_x_y') })

test('a database timestamp without a zone is read as UTC, not as local time', () => {
  expect(asUtc('2026-11-10T10:08:26')).toBe('2026-11-10T10:08:26Z')
  expect(asUtc('2026-11-10T10:08:26.123456')).toBe('2026-11-10T10:08:26.123456Z')
  expect(asUtc('2026-11-10T10:08:26+00:00')).toBe('2026-11-10T10:08:26+00:00')  // already has a zone
  expect(asUtc('2026-11-10T10:08:26Z')).toBe('2026-11-10T10:08:26Z')
  expect(fmtTime('2026-11-10T10:08:26')).toBe(fmtTime('2026-11-10T10:08:26+00:00'))
})

test('lon/lat orders move a far-away depot to the middle of the orders, and say so', async () => {
  const customers = [{ id: 1, x: 77.5, y: 12.9, demand: 1 }, { id: 2, x: 77.7, y: 13.1, demand: 1 }]
  expect(centreOf(customers)).toEqual({ x: 77.6, y: 13 })
  mockFetch({ ...BASE, 'GET /api/plans': [],
    'POST /api/orders/import': { ok: true, rows: 2, valid_rows: 2, invalid_rows: 0, coordinates: 'lonlat', issues: [], customers } })
  renderPage(<Plans />)
  expect(await screen.findByLabelText(/depot x/i)).toHaveValue(50)
  await userEvent.upload(await screen.findByLabelText(/order file/i), new File(['id,lon,lat,demand'], 'o.csv', { type: 'text/csv' }))
  expect(await screen.findByText(/depot set to the middle of the orders/i)).toBeInTheDocument()
  expect(screen.getByLabelText(/depot x/i)).toHaveValue(77.6)
  expect(screen.getByLabelText(/depot y/i)).toHaveValue(13)
})

test('planar orders keep the depot the user typed', async () => {
  mockFetch({ ...BASE, 'GET /api/plans': [] })
  renderPage(<Plans />)
  await userEvent.click(await screen.findByRole('button', { name: /synthetic sample/i }))
  expect(screen.getByLabelText(/depot x/i)).toHaveValue(50)
  expect(screen.queryByText(/depot set to the middle/i)).not.toBeInTheDocument()
})

test('a plan that timed out without a solution says so in the replan box (not "completed")', async () => {
  const plan = { plan_id: 'plan-t', state: 'completed', status: 'timeout_no_solution', feasible: null, engine: 'ortools',
    instance: { name: 'big', customers: [{ id: 1, x: 1, y: 1, demand: 1 }], vehicle_count: 1, depot: { x: 0, y: 0 } },
    result: { solve: { routes: null }, validation: null, metrics: null }, selection: null }
  mockFetch({ ...BASE, 'GET /api/plans/plan-t': plan })
  renderPage(<Routes><Route path="/plans/:id" element={<PlanDetail />} /></Routes>, { route: '/plans/plan-t' })
  expect(await screen.findByText(/replanning needs a completed, feasible plan/i)).toBeInTheDocument()
  expect(screen.getByText('This plan is without a solution.')).toBeInTheDocument()
})

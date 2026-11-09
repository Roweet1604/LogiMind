import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { mockFetch, renderPage } from './helpers'
import Layout from '../components/Layout'
import { ALGOS } from '../lib/algos'
import { StatusStrip } from '../pages/PlanDetail'
import { setApiKey } from '../lib/api'

vi.mock('../components/RouteMap', () => ({ default: () => <div data-testid="map" /> }))

const strip = (plan) => render(<MemoryRouter><StatusStrip plan={plan} /></MemoryRouter>)
const BASE = { plan_id: 'plan-1', state: 'completed', engine: 'ortools', status: 'solved', feasible: true }

test('engine styles: OR-Tools solid blue, GA dashed orange, hybrid its own colour and pattern', () => {
  expect(ALGOS.ortools.dash).toBeUndefined()
  expect(ALGOS.ga.dash).toBeTruthy()
  expect(ALGOS.ga_ls).toMatchObject({ color: ALGOS.ga.color, dash: ALGOS.ga.dash })
  expect(ALGOS.hybrid.color).not.toBe(ALGOS.ortools.color)
  expect(ALGOS.hybrid.color).not.toBe(ALGOS.ga.color)
  expect(ALGOS.hybrid.dash).not.toBe(ALGOS.ga.dash)
  expect(ALGOS.hybrid.label).toMatch(/hybrid/i)
})

test('status strip: the validator verdict comes first, as a word, not only a colour', () => {
  strip(BASE)
  const region = screen.getByRole('region', { name: 'Plan status' })
  expect(within(region).getByText('Validator')).toBeInTheDocument()
  expect(within(region).getByText('feasible')).toBeInTheDocument()
  expect(within(region).getByText('feasible').closest('span').querySelector('svg')).not.toBeNull() // icon too
})

test('status strip: a timeout, fallback distances and a replan are each flagged', () => {
  strip({
    ...BASE, status: 'hard_timeout', feasible: false, parent_plan_id: 'plan-0',
    distance_source: { provider: 'haversine_detour', fallback: true, reason: 'OSRM not configured' },
  })
  const region = screen.getByRole('region', { name: 'Plan status' })
  expect(within(region).getByText('infeasible')).toBeInTheDocument()
  expect(within(region).getByText('timeout')).toBeInTheDocument()
  expect(within(region).getByText('fallback estimate')).toBeInTheDocument()
  expect(within(region).getByText('replanned')).toBeInTheDocument()
  expect(within(region).getByRole('link', { name: /from plan-0/ })).toHaveAttribute('href', '/plans/plan-0')
})

test('status strip: a straight-line plan with no flags shows no warning badges', () => {
  strip({ ...BASE, distance_source: { provider: 'haversine', fallback: false } })
  const region = screen.getByRole('region', { name: 'Plan status' })
  expect(within(region).getByText('straight line')).toBeInTheDocument()
  expect(within(region).queryByText('timeout')).not.toBeInTheDocument()
  expect(within(region).queryByText('fallback estimate')).not.toBeInTheDocument()
  expect(within(region).queryByText('replanned')).not.toBeInTheDocument()
})

test('Layout: the copilot opens as a docked panel with the model status, and closes again', async () => {
  sessionStorage.clear(); setApiKey('lm_x_y')
  mockFetch({
    'GET /api/health': { status: 'ok', environment: {}, research_endpoints: false }, 'GET /api/instances': [],
    'GET /api/whoami': { tenant_id: 't', tenant_name: 'Acme Fleet', key_id: 'k' },
    'GET /api/copilot/status': { available: true, provider: 'ollama', model: 'llama3.2:3b' },
  })
  renderPage(<Routes><Route element={<Layout />}><Route path="/plans" element={<p>plans page</p>} /></Route></Routes>, { route: '/plans' })
  expect(await screen.findByText('Acme Fleet')).toBeInTheDocument()
  expect(screen.queryByRole('complementary', { name: 'Copilot panel' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Copilot' }))
  const dock = screen.getByRole('complementary', { name: 'Copilot panel' })
  expect(await within(dock).findByText('ollama · llama3.2:3b')).toBeInTheDocument()
  expect(within(dock).getByLabelText(/message to the copilot/i)).toBeInTheDocument()
  expect(screen.getByText('plans page')).toBeInTheDocument() // the page stays beside the panel
  await userEvent.click(within(dock).getByRole('button', { name: /close the copilot panel/i }))
  expect(screen.queryByRole('complementary', { name: 'Copilot panel' })).not.toBeInTheDocument()
  setApiKey('')
})

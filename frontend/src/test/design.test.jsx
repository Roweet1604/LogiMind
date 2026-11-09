import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { mockFetch, renderPage } from './helpers'
import Layout from '../components/Layout'
import { ALGOS } from '../lib/algos'
import { colors } from '../../../design/tokens.js'
import { StatusStrip } from '../pages/PlanDetail'
import { setApiKey } from '../lib/api'

vi.mock('../components/RouteMap', () => ({ default: () => <div data-testid="map" /> }))

// WCAG 2.1 contrast ratio between two #RRGGBB colours.
const lum = (hex) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
}
const contrast = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }

test('Freight Yard tokens: every text/background pair used by both apps passes 4.5:1', () => {
  const c = colors
  const pairs = [
    ['text on page', c.ink, c.paper], ['text on panel', c.ink, c.panel], ['muted on page', c.ink2, c.paper],
    ['muted on panel', c.ink2, c.panel], ['muted on sunken', c.ink2, c.sunken],
    ['primary button', c.ink, c.accent.DEFAULT], ['primary hover', c.ink, c.accent.dark], ['selected tint', c.ink, c.accent.soft],
    ['nav text', c.nav.text, c.nav.DEFAULT], ['nav muted', c.nav.muted, c.nav.DEFAULT], ['brand / active on nav', c.accent.DEFAULT, c.nav.DEFAULT],
    ['feasible', c.ok.DEFAULT, c.panel], ['ok tint', c.ink, c.ok.soft], ['delivered button', '#FFFFFF', c.ok.DEFAULT],
    ['warning', c.warn.DEFAULT, c.warn.soft], ['warning body', c.warn.body, c.warn.soft], ['draft', c.draft.DEFAULT, c.draft.soft],
    ['infeasible / timeout badge', '#FFFFFF', c.err.DEFAULT], ['failed text on white', c.err.DEFAULT, c.panel],
    ['error title on tint', c.err.text, c.err.soft], ['text on error tint', c.ink, c.err.soft],
    ['OR-Tools label', c.ortools.DEFAULT, c.panel], ['GA label', c.ga.text, c.panel], ['GA label on tint', c.ga.text, c.ga.soft],
    ['hybrid label', c.hybrid.DEFAULT, c.panel],
  ]
  const failing = pairs.filter(([, fg, bg]) => contrast(fg, bg) < 4.5).map(([n, fg, bg]) => `${n} ${contrast(fg, bg).toFixed(2)}`)
  expect(failing).toEqual([])
  expect(contrast(c.accent.DEFAULT, c.paper)).toBeLessThan(3) // why yellow is never text on a light surface
})

test('engine lines: yellow is never a data line', () => {
  for (const a of Object.values(ALGOS)) expect(a.color.toUpperCase()).not.toBe(colors.accent.DEFAULT.toUpperCase())
  expect([ALGOS.ortools.color, ALGOS.ga.color, ALGOS.hybrid.color]).toEqual(['#1D4ED8', '#C2410C', '#57606A'])
})

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
  expect(within(dock).getByRole('button', { name: /close the copilot panel/i })).toHaveFocus() // keyboard lands in the panel
  await userEvent.click(within(dock).getByRole('button', { name: /close the copilot panel/i }))
  expect(screen.queryByRole('complementary', { name: 'Copilot panel' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Copilot' }))
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('complementary', { name: 'Copilot panel' })).not.toBeInTheDocument()
  setApiKey('')
})

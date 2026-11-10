import '@testing-library/jest-dom/vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { mockFetch, renderPage } from './helpers'
import Layout from '../components/Layout'
import Login from '../pages/Login'
import Plans from '../pages/Plans'
import { getApiKey, setApiKey } from '../lib/api'

// Demo mode (decision 0029): the local backend hands out the demo tenant's key; when it is off the request is 404.
const HEALTH = { 'GET /api/health': { status: 'ok', environment: {}, research_endpoints: false, demo_mode: true } }
const DEMO_KEY = 'lm_demo01_secret'
const DEMO = { demo: true, tenant_id: 'ten-demo-local', tenant_name: 'Demo Fleet (synthetic)', api_key: DEMO_KEY }
const DEMO_ME = { tenant_id: 'ten-demo-local', tenant_name: 'Demo Fleet (synthetic)', key_id: 'key-d' }
const PLANS = [{ plan_id: 'plan-d1', name: 'Morning deliveries (synthetic demo)', state: 'completed', engine: 'ortools',
  status: 'solved', feasible: true, n_customers: 12, total_distance: 41.2, created_at: '2026-11-10T08:00:00' }]

const app = (route = '/plans') => renderPage(
  <Routes><Route element={<Layout />}><Route path="/plans" element={<Plans />} /><Route path="/login" element={<Login />} /></Route></Routes>,
  { route })

beforeEach(() => { sessionStorage.clear(); localStorage.clear(); setApiKey('') })

test('demo mode off: no automatic sign-in and no demo label', async () => {
  const seen = []
  mockFetch({
    'GET /api/health': { status: 'ok', environment: {}, research_endpoints: false, demo_mode: false },
    'GET /api/demo/session': () => { seen.push('demo'); return { __status: 404, body: { detail: 'demo mode is off' } } },
    'GET /api/whoami': () => { seen.push('whoami'); return DEMO_ME },
  })
  app()
  expect(await screen.findByText(/sign in first/i)).toBeInTheDocument()
  expect(seen).toEqual(['demo'])        // asked once, got 404, never signed in
  expect(getApiKey()).toBe('')
  expect(sessionStorage.getItem('logimind.apiKey')).toBeNull()
  expect(screen.queryByText(/demo mode/i)).not.toBeInTheDocument()
})

test('demo mode on: signs in to the demo tenant by itself and shows a visible "Demo mode" label', async () => {
  mockFetch({ ...HEALTH, 'GET /api/demo/session': DEMO, 'GET /api/whoami': DEMO_ME, 'GET /api/plans': PLANS })
  app()
  expect(await screen.findByText('Morning deliveries (synthetic demo)')).toBeInTheDocument()
  expect(screen.getByText('Demo mode')).toBeInTheDocument()
  expect(screen.getAllByText('Demo Fleet (synthetic)').length).toBeGreaterThan(0)
  expect(getApiKey()).toBe(DEMO_KEY)
  expect(localStorage.getItem('logimind.apiKey')).toBeNull()  // still tab-only storage
})

test('a valid normal key is kept even when demo mode is on', async () => {
  setApiKey('lm_acme_secret')
  mockFetch({ ...HEALTH, 'GET /api/demo/session': DEMO, 'GET /api/plans': [],
    'GET /api/whoami': { tenant_id: 'ten-a', tenant_name: 'Acme Fleet', key_id: 'key-a' } })
  app()
  expect(await screen.findByText(/no plans yet/i)).toBeInTheDocument()
  expect(screen.getByText('Acme Fleet')).toBeInTheDocument()
  expect(screen.queryByText('Demo mode')).not.toBeInTheDocument()
  expect(getApiKey()).toBe('lm_acme_secret')
})

test('signing out of the demo keeps the tab signed out, so a normal key can be used', async () => {
  mockFetch({ ...HEALTH, 'GET /api/demo/session': DEMO, 'GET /api/whoami': DEMO_ME, 'GET /api/plans': PLANS })
  const { unmount } = app('/login')
  await userEvent.click(await screen.findByRole('button', { name: /sign out/i }))
  expect(getApiKey()).toBe('')
  unmount()
  app('/plans')
  expect(await screen.findByText(/sign in first/i)).toBeInTheDocument()
  await waitFor(() => expect(getApiKey()).toBe(''))
})

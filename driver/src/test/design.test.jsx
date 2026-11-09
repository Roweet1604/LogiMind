import { render, screen, within } from '@testing-library/react'
import App from '../App'
import { saveRoute, saveToken } from '../lib/store'
import { ROUTE, fakeToken, mockFetch } from './helpers'

const TOKEN = fakeToken()
const card = (cid) => screen.getByRole('listitem', { name: new RegExp(`customer ${cid}$`) })

beforeEach(() => {
  localStorage.clear()
  window.history.replaceState(null, '', `/#t=${TOKEN}`)
})

test('the next stop has the largest Navigate, Delivered and Failed targets; other stops keep large ones', async () => {
  mockFetch({ 'GET /api/driver/route': ROUTE })
  render(<App />)
  await screen.findByText('Customer 3')
  const next = within(card(3))
  expect(next.getByRole('link', { name: 'Navigate' })).toHaveClass('tap', 'tap-lg')
  expect(next.getByRole('button', { name: 'Delivered' })).toHaveClass('tap', 'tap-lg')
  expect(next.getByRole('button', { name: 'Failed' })).toHaveClass('tap', 'tap-lg')
  const later = within(card(9))
  expect(later.getByRole('button', { name: 'Delivered' })).toHaveClass('tap')
  expect(later.getByRole('button', { name: 'Delivered' })).not.toHaveClass('tap-lg')
})

test('a server error with a network still shows the saved copy and says the server is unreachable', async () => {
  saveToken(TOKEN)
  saveRoute(TOKEN, ROUTE, '2027-01-15T09:30:00Z')
  mockFetch({ 'GET /api/driver/route': { __status: 502, detail: 'Bad Gateway' } })
  render(<App />)
  expect(await screen.findByText(/offline copy saved at/i)).toBeInTheDocument()
  expect(screen.getByText('Server unreachable')).toBeInTheDocument()
  expect(screen.queryByText('Online')).not.toBeInTheDocument()
})

test('stop status and connection status are words with an icon, not colour alone', async () => {
  mockFetch({ 'GET /api/driver/route': ROUTE })
  render(<App />)
  await screen.findByText('Customer 3')
  const done = within(card(7)).getByText('Delivered', { selector: 'span' })
  expect(done.querySelector('svg')).not.toBeNull()
  expect(within(card(3)).getByText('To do')).toBeInTheDocument()
  const online = screen.getByText('Online')
  expect(online.querySelector('svg')).not.toBeNull()
})

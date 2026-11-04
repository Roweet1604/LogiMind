import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App, { RETRY_MS } from '../App'
import { loadQueue, loadRoute, saveRoute, saveToken } from '../lib/store'
import { ROUTE, fakeToken, mockFetch } from './helpers'

const TOKEN = fakeToken()
const GET = 'GET /api/driver/route'
const post = (cid) => `POST /api/driver/stops/${cid}/status`
const card = (cid) => screen.getByRole('listitem', { name: new RegExp(`customer ${cid}$`) })
const bodies = (net, key) => net.calls.filter((c) => c.key === key).map((c) => JSON.parse(c.opts.body))

beforeEach(() => {
  localStorage.clear()
  window.history.replaceState(null, '', `/#t=${TOKEN}`)
})

test('without a link it asks the driver to open the dispatcher link', () => {
  window.history.replaceState(null, '', '/')
  mockFetch({})
  render(<App />)
  expect(screen.getByText(/open the link your dispatcher sent you/i)).toBeInTheDocument()
})

test('shows the stops in order with the next stop, navigation links and a cached copy', async () => {
  const net = mockFetch({ [GET]: ROUTE })
  render(<App />)
  expect(await screen.findByText('Customer 3')).toBeInTheDocument()
  expect(net.calls[0].opts.headers['X-Driver-Token']).toBe(TOKEN)
  expect(window.location.hash).toBe('') // token removed from the address bar
  expect(screen.getByText(/1 of 3 stops done/)).toBeInTheDocument()
  expect(within(card(3)).getByText('Next')).toBeInTheDocument()
  expect(within(card(3)).getByText(/window 60–120 min/)).toBeInTheDocument()
  expect(within(card(3)).getByRole('link', { name: 'Navigate' }))
    .toHaveAttribute('href', 'https://www.google.com/maps/dir/?api=1&destination=28.650000,77.250000&travelmode=driving')
  expect(within(card(9)).queryByRole('link', { name: 'Navigate' })).not.toBeInTheDocument()
  expect(within(card(9)).getByText('No map')).toBeInTheDocument()
  expect(within(card(3)).getByRole('button', { name: 'Delivered' })).toHaveClass('tap') // large touch target
  expect(loadRoute(TOKEN).route.stops).toHaveLength(3)
})

test('offline: the saved stop list is shown, reports are queued and sent when back online', async () => {
  saveToken(TOKEN)
  saveRoute(TOKEN, ROUTE, '2027-01-15T09:30:00Z')
  const net = mockFetch({ [GET]: ROUTE, [post(3)]: { event_id: 1, duplicate: false } })
  net.offline = true
  render(<App />)
  expect(await screen.findByText(/offline copy saved at/i)).toBeInTheDocument()
  expect(screen.getByText('Offline')).toBeInTheDocument()
  await userEvent.click(within(card(3)).getByRole('button', { name: 'Delivered' }))
  expect(within(card(3)).getByText(/delivered · waiting to sync/i)).toBeInTheDocument()
  expect(screen.getByText(/1 update waiting to sync/)).toBeInTheDocument()
  const queued = loadQueue(TOKEN)
  expect(queued).toHaveLength(1)

  const attempts = bodies(net, post(3)) // tried once while offline; the fetch failed
  expect(attempts.every((b) => b.client_event_id === queued[0].body.client_event_id)).toBe(true)

  net.offline = false
  const before = net.calls.length
  await act(async () => { window.dispatchEvent(new Event('online')) })
  await waitFor(() => expect(loadQueue(TOKEN)).toEqual([]))
  const sent = net.calls.slice(before).filter((c) => c.key === post(3)).map((c) => JSON.parse(c.opts.body))
  expect(sent).toHaveLength(1) // sent once, with the same id, so a resend could not double-count
  expect(sent[0]).toMatchObject({ status: 'delivered', client_event_id: queued[0].body.client_event_id })
  await waitFor(() => expect(screen.queryByText(/waiting to sync/)).not.toBeInTheDocument())
  expect(screen.getByText('Online')).toBeInTheDocument()
})

test('a failed stop needs a reason, and "other" needs a note', async () => {
  const net = mockFetch({ [GET]: ROUTE, [post(3)]: { event_id: 2, duplicate: false } })
  render(<App />)
  await screen.findByText('Customer 3')
  await userEvent.click(within(card(3)).getByRole('button', { name: 'Failed' }))
  const submit = within(card(3)).getByRole('button', { name: 'Report failed' })
  expect(submit).toBeDisabled()
  await userEvent.click(within(card(3)).getByRole('button', { name: 'Other (add a note)' }))
  expect(submit).toBeDisabled()
  await userEvent.type(within(card(3)).getByLabelText('Note'), 'Gate locked')
  await userEvent.click(submit)
  await waitFor(() => expect(bodies(net, post(3))).toHaveLength(1))
  expect(bodies(net, post(3))[0]).toMatchObject({ status: 'failed', reason: 'other', note: 'Gate locked' })
})

test('a report the server refuses is dropped and the driver is told why', async () => {
  mockFetch({ [GET]: ROUTE, [post(3)]: { __status: 404, detail: 'customer 3 is not on this route' } })
  render(<App />)
  await screen.findByText('Customer 3')
  await userEvent.click(within(card(3)).getByRole('button', { name: 'Delivered' }))
  expect(await screen.findByText(/could not be saved: customer 3 is not on this route/)).toBeInTheDocument()
  expect(loadQueue(TOKEN)).toEqual([])
})

test('an expired or revoked link says so, and mentions unsent reports', async () => {
  saveToken(TOKEN)
  localStorage.setItem('logimind.driver.queue.dlk-aaaaaaaaaaaa', JSON.stringify([
    { customerId: 3, body: { status: 'delivered', reason: null, note: '', client_event_id: 'evt-00000001' } }]))
  const expired = { __status: 401, detail: 'driver link has expired' }
  mockFetch({ [GET]: expired, [post(3)]: expired })
  render(<App />)
  expect(await screen.findByText(/expired or was revoked/i)).toBeInTheDocument()
  expect(await screen.findByText(/1 report on this phone was not sent/)).toBeInTheDocument()
  expect(loadQueue(TOKEN)).toHaveLength(1) // kept, never silently dropped
})

test('photos upload when online and are refused offline', async () => {
  const net = mockFetch({ [GET]: ROUTE, 'POST /api/driver/stops/3/photo': { photo_id: 'pod-1' } })
  render(<App />)
  await screen.findByText('Customer 3')
  const file = new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], 'cam.jpg', { type: 'image/jpeg' })
  await userEvent.upload(screen.getByLabelText('Photo for customer 3'), file)
  expect(await within(card(3)).findByText('Photo saved.')).toBeInTheDocument()
  const call = net.calls.find((c) => c.key === 'POST /api/driver/stops/3/photo')
  expect(call.opts.body).toBeInstanceOf(FormData)
  expect(call.opts.body.get('file')).toBeTruthy()
  await act(async () => { window.dispatchEvent(new Event('offline')) })
  expect(screen.getByLabelText('Photo for customer 3')).toBeDisabled()
  expect(screen.getAllByText(/photos need a connection/i).length).toBeGreaterThan(0)
})

test('a replanned route tells the driver to get the new link', async () => {
  mockFetch({ [GET]: { ...ROUTE, superseded_by: 'plan-y' } })
  render(<App />)
  expect(await screen.findByText(/this route was replanned/i)).toBeInTheDocument()
})

test('queued reports are retried on a timer when the server comes back without an online event', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  try {
    saveToken(TOKEN)
    saveRoute(TOKEN, ROUTE, '2027-01-15T09:30:00Z')
    const net = mockFetch({ [GET]: ROUTE, [post(3)]: { event_id: 3, duplicate: false } })
    net.offline = true
    render(<App />)
    await screen.findByText(/offline copy saved at/i)
    await userEvent.click(within(card(3)).getByRole('button', { name: 'Delivered' }))
    expect(loadQueue(TOKEN)).toHaveLength(1)
    net.offline = false // server reachable again; the browser fires no "online" event
    await act(async () => { await vi.advanceTimersByTimeAsync(RETRY_MS + 100) })
    await waitFor(() => expect(loadQueue(TOKEN)).toEqual([]))
    expect(screen.getByText('Online')).toBeInTheDocument()
  } finally {
    vi.useRealTimers()
  }
})

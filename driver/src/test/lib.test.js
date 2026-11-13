import { manifest } from '../../pwa.manifest.js'
import { pickApiBase } from '../lib/api'
import { navUrl } from '../lib/nav'
import { linkKey, loadQueue, loadToken, saveQueue, takeTokenFromLocation } from '../lib/store'
import { flushQueue, makeReport, withQueued } from '../lib/sync'
import { fakeToken } from './helpers'

beforeEach(() => localStorage.clear())

test('the token is taken from the link fragment, stored, and removed from the address bar', () => {
  const tok = fakeToken()
  const hist = { replaceState: vi.fn() }
  expect(takeTokenFromLocation({ hash: `#t=${tok}`, pathname: '/', search: '' }, hist)).toBe(tok)
  expect(hist.replaceState).toHaveBeenCalledWith(null, '', '/')
  expect(loadToken()).toBe(tok)
  // the installed app opens at "/" without the fragment and still finds its link
  expect(takeTokenFromLocation({ hash: '', pathname: '/', search: '' }, hist)).toBe(tok)
})

test('queues are kept per link, so two links never mix their reports', () => {
  const a = fakeToken('dlk-aaaaaaaaaaaa')
  const b = fakeToken('dlk-bbbbbbbbbbbb')
  expect(linkKey(a)).toBe('dlk-aaaaaaaaaaaa')
  saveQueue(a, [makeReport(1, 'delivered')])
  expect(loadQueue(a)).toHaveLength(1)
  expect(loadQueue(b)).toEqual([])
})

test('reports carry a unique client_event_id; failed keeps its reason, delivered has none', () => {
  const f = makeReport(3, 'failed', 'not_home')
  const d = makeReport(3, 'delivered', 'not_home')
  expect(f.body).toMatchObject({ status: 'failed', reason: 'not_home' })
  expect(d.body.reason).toBeNull()
  expect(f.body.client_event_id).not.toBe(d.body.client_event_id)
  expect(f.body.client_event_id).toMatch(/^[A-Za-z0-9_-]{8,64}$/)
})

test('flushQueue sends in order, stops at a lost connection and keeps the rest', async () => {
  const q = [makeReport(1, 'delivered'), makeReport(2, 'delivered'), makeReport(3, 'delivered')]
  const send = vi.fn()
    .mockResolvedValueOnce({})
    .mockRejectedValueOnce(Object.assign(new Error('No connection'), { status: 0 }))
  const res = await flushQueue('tok', q, send)
  expect(res.synced).toEqual([q[0]])
  expect(res.remaining).toEqual([q[1], q[2]])
  expect(send).toHaveBeenCalledTimes(2)
  expect(send.mock.calls[1][2].client_event_id).toBe(q[1].body.client_event_id) // resent unchanged
})

test('flushQueue drops reports the server rejects for good, keeps them on expiry and server errors', async () => {
  const q = [makeReport(1, 'delivered'), makeReport(99, 'delivered'), makeReport(2, 'delivered')]
  const rejecting = vi.fn(async (_t, cid) => {
    if (cid === 99) throw Object.assign(new Error('customer 99 is not on this route'), { status: 404 })
    return {}
  })
  const res = await flushQueue('tok', q, rejecting)
  expect(res.rejected.map((r) => r.error)).toEqual(['customer 99 is not on this route'])
  expect(res.synced).toEqual([q[0], q[2]])
  expect(res.remaining).toEqual([])
  for (const status of [401, 429, 503]) {
    const r = await flushQueue('tok', q, vi.fn().mockRejectedValue(Object.assign(new Error('x'), { status })))
    expect(r.remaining).toHaveLength(3)
  }
})

test('queued reports override the server status until they are synced', () => {
  const stops = [{ customer_id: 1, status: 'pending' }, { customer_id: 2, status: 'delivered' }]
  const out = withQueued(stops, [makeReport(1, 'failed', 'refused')])
  expect(out[0]).toMatchObject({ status: 'failed', reason: 'refused', queued: true })
  expect(out[1]).toMatchObject({ status: 'delivered', queued: false })
})

test('navigation links only for real coordinates', () => {
  expect(navUrl({ lat: 28.6139, lon: 77.209 }))
    .toBe('https://www.google.com/maps/dir/?api=1&destination=28.613900,77.209000&travelmode=driving')
  expect(navUrl({ lat: null, lon: null })).toBeNull()
})

test('the web app manifest makes the app installable', () => {
  expect(manifest).toMatchObject({ display: 'standalone', start_url: '/', short_name: 'Driver' })
  expect(manifest.icons.map((i) => i.sizes)).toEqual(expect.arrayContaining(['192x192', '512x512']))
  expect(manifest.icons.some((i) => i.purpose === 'maskable')).toBe(true)
})

// Run-time API address from the driver link (decision 0041): ?api=<tunnel> before #t=, kept for the installed app.
test('the driver app takes the tunnel from the link and keeps it for the installed app', () => {
  const t = 'https://bold-cat-12.trycloudflare.com'
  const built = 'https://x.onrender.com'
  expect(pickApiBase({ search: `?api=${t}`, hash: '#t=dl1.a.b', built })).toEqual({ base: t, store: t })
  expect(pickApiBase({ search: '', hash: '', stored: t, built })).toEqual({ base: t, store: undefined })  // opened at start_url
})

test('the driver app ignores other servers, and a new link without ?api= forgets an old tunnel', () => {
  const built = 'https://x.onrender.com'
  for (const bad of ['https://evil.example.com', 'http://a.trycloudflare.com', 'https://a.trycloudflare.com.evil.io']) {
    expect(pickApiBase({ search: `?api=${encodeURIComponent(bad)}`, hash: '#t=dl1.a.b', built })).toEqual({ base: built, store: undefined })
  }
  expect(pickApiBase({ search: '', hash: '#t=dl1.a.b', stored: 'https://old-1.trycloudflare.com', built })).toEqual({ base: built, store: '' })
})

// Hosted API as the default (decision 0045): a console link carries ?api=<VITE_API_URL>; that is this build's default.
test('the driver app accepts its own hosted API from the link and forgets an old tunnel', () => {
  const built = 'https://rohti-logimind.hf.space'
  expect(pickApiBase({ search: `?api=${built}`, hash: '#t=dl1.a.b', stored: 'https://old-1.trycloudflare.com', built }))
    .toEqual({ base: built, store: '' })
  expect(pickApiBase({ search: `?api=${built}`, hash: '#t=dl1.a.b', built })).toEqual({ base: built, store: undefined })
  expect(pickApiBase({ search: '?api=https://other-x.hf.space', hash: '#t=dl1.a.b', built })).toEqual({ base: built, store: undefined })
})

import { ApiError, api, driverLinkUrl, parseErrorBody, pickApiBase } from '../lib/api'
import { fmt, fmtInt, fmtSeconds, isNum } from '../lib/format'

test('missing values are shown as a dash, never as zero', () => {
  expect(fmt(null)).toBe('—')
  expect(fmt(NaN)).toBe('—')
  expect(fmtInt(undefined)).toBe('—')
  expect(fmtSeconds(null)).toBe('—')
  expect(fmt(0)).toBe('0.00')
  expect(isNum(0)).toBe(true)
})

test('formats numbers with fixed digits', () => {
  expect(fmt(1234.5678)).toBe('1,234.57')
  expect(fmtSeconds(2.5)).toBe('2.50 s')
})

test('parseErrorBody handles all FastAPI error shapes', () => {
  const a = parseErrorBody(422, { detail: { message: 'invalid instance', errors: ['x', 'y'] } })
  expect(a).toBeInstanceOf(ApiError)
  expect(a.errors).toEqual(['x', 'y'])
  const b = parseErrorBody(422, { detail: [{ loc: ['body', 'n_customers'], msg: 'too small' }] })
  expect(b.errors[0]).toBe('n_customers: too small')
  expect(parseErrorBody(404, { detail: 'run not found' }).message).toBe('run not found')
  expect(parseErrorBody(500, null).message).toMatch(/went wrong on the server/)
  expect(parseErrorBody(500, null).status).toBe(500)
})

test('network failure becomes a readable ApiError', async () => {
  globalThis.fetch = vi.fn(async () => { throw new TypeError('failed') })
  await expect(api.health()).rejects.toThrow(/The server isn't running\. Run start-dev\.bat/)
  await expect(api.health()).rejects.toMatchObject({ unreachable: true, status: 0 })
})

// Run-time API address from ?api= (decision 0040): only quick-tunnel and localhost addresses, remembered until ?api=default.
test('pickApiBase takes a quick-tunnel address from ?api= and remembers it', () => {
  const t = 'https://bold-cat-12.trycloudflare.com'
  expect(pickApiBase({ search: `?api=${t}/`, built: 'https://x.onrender.com' })).toEqual({ base: t, override: true, store: t })
  expect(pickApiBase({ search: '', stored: t, built: '' })).toEqual({ base: t, override: true, store: undefined })
  expect(pickApiBase({ search: '?api=http://localhost:8000' })).toMatchObject({ base: 'http://localhost:8000', override: true })
})

test('pickApiBase ignores other servers and forgets the address on ?api=default', () => {
  const built = 'https://x.onrender.com'
  for (const bad of ['https://evil.example.com', 'http://bold-cat.trycloudflare.com', 'https://a.trycloudflare.com.evil.io', 'javascript:alert(1)']) {
    expect(pickApiBase({ search: `?api=${encodeURIComponent(bad)}`, built })).toEqual({ base: built, override: false, store: undefined })
  }
  expect(pickApiBase({ search: '?api=default', stored: 'https://a.trycloudflare.com', built })).toEqual({ base: built, override: false, store: '' })
  expect(pickApiBase({ stored: 'https://evil.example.com', built })).toEqual({ base: built, override: false, store: '' })
  expect(pickApiBase({ built })).toEqual({ base: built, override: false, store: undefined })
})

// Driver links (decision 0041): built from the console's own address when it serves the driver app, with the
// laptop tunnel as ?api= before #t=; the signed token is the backend's, unchanged.
test('driverLinkUrl uses the console address and carries the tunnel before #t=', () => {
  const link = { token: 'dl1.abc-DEF_1.sig', url: 'http://localhost:5174/#t=dl1.abc-DEF_1.sig' }
  const tunnel = 'https://bold-cat-12.trycloudflare.com'
  const origin = 'https://logi-mind-ten.vercel.app'
  expect(driverLinkUrl(link, { origin, driverPath: '/driver/', api: tunnel }))
    .toBe('https://logi-mind-ten.vercel.app/driver/?api=https://bold-cat-12.trycloudflare.com#t=dl1.abc-DEF_1.sig')
  expect(driverLinkUrl(link, { origin, driverPath: '/driver/', api: '' })).toBe('https://logi-mind-ten.vercel.app/driver/#t=dl1.abc-DEF_1.sig')
  const u = new URL(driverLinkUrl(link, { origin, driverPath: 'driver', api: tunnel }))
  expect(u.pathname).toBe('/driver/')
  expect(u.searchParams.get('api')).toBe(tunnel)
  expect(u.hash).toBe(`#t=${link.token}`)
})

test('driverLinkUrl keeps the backend address when the console does not serve the driver app', () => {
  const link = { token: 'dl1.x.y', url: 'http://localhost:5174/#t=dl1.x.y' }
  expect(driverLinkUrl(link, { origin: 'http://localhost:5173', driverPath: '', api: '' })).toBe('http://localhost:5174/#t=dl1.x.y')
  expect(driverLinkUrl(link, { origin: 'http://localhost:5173', driverPath: '', api: 'https://a-b.trycloudflare.com' }))
    .toBe('http://localhost:5174/?api=https://a-b.trycloudflare.com#t=dl1.x.y')
})

// Hosted API as the default (decision 0045): VITE_API_URL at build time; ?api=<that address> means the default too,
// and driver links carry the API in use even when it is the default.
test('pickApiBase treats ?api=<the built API> as the default and forgets a remembered tunnel', () => {
  const built = 'https://rohti-logimind.hf.space'
  expect(pickApiBase({ search: `?api=${built}/`, stored: 'https://a-b.trycloudflare.com', built }))
    .toEqual({ base: built, override: false, store: '' })
  expect(pickApiBase({ search: '?api=https://other-logimind.hf.space', built })).toEqual({ base: built, override: false, store: undefined })
})

test('driverLinkUrl carries the hosted API address', () => {
  const link = { token: 'dl1.abc.sig', url: 'http://localhost:5174/#t=dl1.abc.sig' }
  expect(driverLinkUrl(link, { origin: 'https://logi-mind-ten.vercel.app', driverPath: '/driver/', api: 'https://rohti-logimind.hf.space' }))
    .toBe('https://logi-mind-ten.vercel.app/driver/?api=https://rohti-logimind.hf.space#t=dl1.abc.sig')
})

import { ApiError, api, parseErrorBody, pickApiBase } from '../lib/api'
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

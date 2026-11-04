// Fake driver tokens and a fetch mock that can be switched offline.
export function fakeToken(linkId = 'dlk-aaaaaaaaaaaa') {
  const body = btoa(JSON.stringify({ l: linkId, t: 'ten-x', p: 'plan-x', r: 0, e: 9e9 }))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `dl1.${body}.sig`
}

export function mockFetch(table) {
  const net = { offline: false, calls: [] }
  globalThis.fetch = vi.fn(async (url, opts = {}) => {
    const key = `${opts.method || 'GET'} ${String(url)}`
    net.calls.push({ key, opts })
    if (net.offline) throw new TypeError('Failed to fetch')
    const hit = Object.entries(table).find(([k]) => key === k)
    if (!hit) return { ok: false, status: 404, json: async () => ({ detail: `unmocked ${key}` }) }
    const v = typeof hit[1] === 'function' ? hit[1](opts) : hit[1]
    if (v && v.__status) return { ok: false, status: v.__status, json: async () => ({ detail: v.detail }) }
    return { ok: true, status: 200, json: async () => v }
  })
  return net
}

export const ROUTE = {
  plan_id: 'plan-x', route_index: 1, plan_name: 'Tuesday north', company: 'Acme Couriers',
  expires_at: '2027-01-15T20:00:00+00:00', coordinates: 'lon/lat', time_unit: 'min', superseded_by: null,
  fail_reasons: ['not_home', 'refused', 'wrong_address', 'access_problem', 'damaged', 'other'],
  stops: [
    { seq: 1, customer_id: 7, demand: 2, x: 77.21, y: 28.61, lat: 28.61, lon: 77.21, ready_time: 0, due_time: null,
      service_time: 0, status: 'delivered', reason: null, reported_at: null, photos: 0 },
    { seq: 2, customer_id: 3, demand: 1, x: 77.25, y: 28.65, lat: 28.65, lon: 77.25, ready_time: 60, due_time: 120,
      service_time: 5, status: 'pending', reason: null, reported_at: null, photos: 0 },
    { seq: 3, customer_id: 9, demand: 1, x: 5, y: 5, lat: null, lon: null, ready_time: 0, due_time: null,
      service_time: 0, status: 'pending', reason: null, reported_at: null, photos: 0 },
  ],
}

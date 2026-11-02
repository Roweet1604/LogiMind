import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppProvider } from '../state/AppContext'

// Routes fetch calls by "METHOD /path" prefix to canned JSON (or {status, body} for errors).
export function mockFetch(table) {
  globalThis.fetch = vi.fn(async (url, opts = {}) => {
    const key = `${opts.method || 'GET'} ${String(url)}`
    const hit = Object.entries(table).find(([k]) => key.startsWith(k))
    if (!hit) return { ok: false, status: 404, json: async () => ({ detail: `unmocked ${key}` }) }
    const v = typeof hit[1] === 'function' ? hit[1](opts) : hit[1]
    if (v && v.__status) return { ok: false, status: v.__status, json: async () => v.body }
    return { ok: true, status: 200, json: async () => v }
  })
}

export const renderPage = (ui) =>
  render(<MemoryRouter><AppProvider>{ui}</AppProvider></MemoryRouter>)

export const INSTANCE = {
  instance_id: 'inst-test000001', name: 'tiny', source: 'synthetic', metric: 'euclidean', distance_unit: 'km',
  depot: { x: 0, y: 0 }, customers: [{ id: 1, x: 3, y: 0, demand: 2 }, { id: 2, x: 3, y: 4, demand: 2 }],
  vehicle_count: 1, vehicle_capacity: 4, fixed_vehicle_cost: 0, cost_per_distance: 1,
}

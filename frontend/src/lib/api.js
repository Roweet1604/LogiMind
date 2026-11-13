import { llmHeaders } from './llmSettings'

// Thin client for the FastAPI backend. Errors keep the server's reasons so the UI can show them.
// VITE_API_URL: the deployed API, e.g. https://logimind-api.onrender.com (decision 0039). Empty: same origin / dev proxy.
const BUILT = (import.meta.env?.VITE_API_URL ?? import.meta.env?.VITE_API_BASE ?? '').replace(/\/+$/, '')

// Run-time API address (decision 0040): `npm run dev` on the team's PC opens a Cloudflare quick tunnel and prints
// <console>/?api=https://<name>.trycloudflare.com. The address is remembered in this browser until ?api=default.
// Only quick-tunnel and localhost addresses are accepted, so a link cannot point the console at any other server.
const API_STORE = 'logimind.apiUrl'
const ALLOWED_API = /^(https:\/\/[a-z0-9-]+\.trycloudflare\.com|http:\/\/(localhost|127\.0\.0\.1)(:\d{1,5})?)$/

// -> {base, override, store}: store is the value to remember ('' forgets it, undefined leaves storage alone).
export function pickApiBase({ search = '', stored = '', built = '' } = {}) {
  const asked = new URLSearchParams(search).get('api')
  if (asked !== null) {
    const url = asked.trim().replace(/\/+$/, '')
    if (url === 'default' || url === '') return { base: built, override: false, store: '' }
    if (ALLOWED_API.test(url)) return { base: url, override: true, store: url }
  }
  if (stored && ALLOWED_API.test(stored)) return { base: stored, override: true, store: undefined }
  return { base: built, override: false, store: stored ? '' : undefined }
}

function resolveBase() {
  let stored = ''
  try { stored = localStorage.getItem(API_STORE) || '' } catch { /* storage blocked */ }
  const search = typeof window === 'undefined' ? '' : window.location.search
  const pick = pickApiBase({ search, stored, built: BUILT })
  try {
    if (pick.store === '') localStorage.removeItem(API_STORE)
    else if (pick.store) localStorage.setItem(API_STORE, pick.store)
    // Server changed: this tab's tenant key and copilot settings belonged to the other server, never send them here.
    if (pick.store !== undefined && pick.store !== stored) sessionStorage.clear()
  } catch { /* storage blocked */ }
  if (search && new URLSearchParams(search).has('api')) {
    const u = new URL(window.location.href)
    u.searchParams.delete('api')
    window.history.replaceState(window.history.state, '', u.pathname + u.search + u.hash)
  }
  return pick
}

const PICK = resolveBase()
const BASE = PICK.base
// The tunnel host name when the console talks to a PC via ?api=, else null (shown in the header).
export const API_OVERRIDE = PICK.override ? BASE.replace(/^https?:\/\//, '') : null

// Driver link shown to the dispatcher (decision 0041). The signed token is the backend's, unchanged. When this
// console build also serves the driver app (VITE_DRIVER_PATH, set by the Vercel build to /driver/), the link uses
// the address the console is served from, so it opens on a phone. Otherwise the backend's address
// (LOGIMIND_DRIVER_APP_URL) is kept. Either way a laptop tunnel in use goes along as ?api=, before #t=.
const DRIVER_PATH = import.meta.env?.VITE_DRIVER_PATH || ''
export function driverLinkUrl(link, {
  origin = typeof window === 'undefined' ? '' : window.location.origin,
  driverPath = DRIVER_PATH,
  api = PICK.override ? BASE : '',
} = {}) {
  const query = api ? `?api=${api}` : ''
  const root = driverPath
    ? `${origin.replace(/\/+$/, '')}/${driverPath.replace(/^\/+|\/+$/g, '')}/`
    : (link.url || '').split('#')[0].split('?')[0]
  return `${root}${query}#t=${link.token}`
}

export class ApiError extends Error {
  constructor(message, { status = 0, errors = [], unreachable = false } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.errors = errors
    this.unreachable = unreachable  // no answer from the server (not running, or the dev proxy could not reach it)
  }
}

// Plain words for people who run the demo, not developers.
export const SERVER_DOWN = API_OVERRIDE
  ? "The server on the team's PC isn't answering. Start it there with npm run dev and open the new link it prints."
  : BASE
  ? "The server isn't answering yet. The free hosting sleeps when idle and takes about a minute to wake up; press Retry."
  : "The server isn't running. Run start-dev.bat, then press Retry."
const PLAIN = {
  401: 'Your sign-in key was not accepted. Sign in again.',
  403: 'This part of LogiMind is switched off on this server.',
  404: 'That item was not found. It may have been removed, or it belongs to another account.',
  429: 'Too many requests in a short time. Wait a few seconds and try again.',
}
const plain = (status) => PLAIN[status] || (status >= 500 ? 'Something went wrong on the server. Please try again.' : 'The request could not be completed.')

// FastAPI returns either {detail: {message, errors}}, {detail: "text"}, or {detail: [pydantic issues]}.
export function parseErrorBody(status, body) {
  const d = body?.detail
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    return new ApiError(d.message || plain(status), { status, errors: d.errors || [] })
  }
  if (Array.isArray(d)) {
    const errors = d.map((e) => `${(e.loc || []).filter((p) => p !== 'body').join('.')}: ${e.msg}`)
    return new ApiError('Some fields are not valid', { status, errors })
  }
  if (typeof d === 'string') return new ApiError(status === 401 ? PLAIN[401] : d, { status })
  return new ApiError(plain(status), { status })
}

// Tenant API key: kept in memory and in sessionStorage only (gone when the tab closes), never in localStorage.
const KEY_STORE = 'logimind.apiKey'
let apiKey = (() => { try { return sessionStorage.getItem(KEY_STORE) || '' } catch { return '' } })()
export const getApiKey = () => apiKey
export function setApiKey(key) {
  apiKey = key || ''
  try { if (apiKey) sessionStorage.setItem(KEY_STORE, apiKey); else sessionStorage.removeItem(KEY_STORE) } catch { /* storage blocked */ }
}

async function request(path, { method = 'GET', body, form, raw = false, key, extra } = {}) {
  let res
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'
  const k = key ?? apiKey
  if (k) headers['X-API-Key'] = k
  Object.assign(headers, extra || {})  // e.g. the copilot settings (headers, never the URL)
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: Object.keys(headers).length ? headers : undefined,
      body: form || (body ? JSON.stringify(body) : undefined),
    })
  } catch {
    throw new ApiError(SERVER_DOWN, { status: 0, unreachable: true })
  }
  if (!res.ok) {
    let parsed = null
    try { parsed = await res.json() } catch { /* non-JSON error body */ }
    // The dev proxy answers 500/502/503/504 with no JSON body when the API is not running.
    if (parsed === null && res.status >= 500) throw new ApiError(SERVER_DOWN, { status: res.status, unreachable: true })
    throw parseErrorBody(res.status, parsed)
  }
  return raw ? res : res.json()
}

export const api = {
  health: () => request('/api/health'),
  listInstances: () => request('/api/instances'),
  getInstance: (id) => request(`/api/instances/${id}`),
  createInstance: (body) => request('/api/instances', { method: 'POST', body }),
  generateInstance: (body) => request('/api/instances/generate', { method: 'POST', body }),
  startRun: (body) => request('/api/runs', { method: 'POST', body }),
  getRun: (id) => request(`/api/runs/${id}`),
  listRuns: (instanceId) => request(`/api/runs${instanceId ? `?instance_id=${instanceId}` : ''}`),
  startExperiment: (body) => request('/api/experiments', { method: 'POST', body }),
  getExperiment: (id) => request(`/api/experiments/${id}`),
  listExperiments: () => request('/api/experiments'),
  // Tenant API (needs an API key)
  whoami: (key) => request('/api/whoami', { key }),
  demoSession: () => request('/api/demo/session', { key: '' }),  // local demo mode only (decision 0029)
  listPlans: () => request('/api/plans'),
  getPlan: (id) => request(`/api/plans/${id}`),
  createPlan: (body) => request('/api/plans', { method: 'POST', body }),
  replan: (id, body) => request(`/api/plans/${id}/replan`, { method: 'POST', body }),
  createDriverLink: (id, body) => request(`/api/plans/${id}/driver-links`, { method: 'POST', body }),
  listDriverLinks: (id) => request(`/api/plans/${id}/driver-links`),
  revokeDriverLink: (linkId) => request(`/api/driver-links/${linkId}`, { method: 'DELETE' }),
  stopReports: (id) => request(`/api/plans/${id}/stop-reports`),
  copilotStatus: () => request('/api/copilot/status', { extra: llmHeaders() }),
  copilotTest: (settings) => request('/api/copilot/test', { method: 'POST', extra: llmHeaders(settings) }),
  copilotModels: (settings) => request('/api/copilot/models', { method: 'POST', extra: llmHeaders(settings) }),
  copilotChat: (message, sessionId) => request('/api/copilot/chat', { method: 'POST', body: { message, session_id: sessionId || null }, extra: llmHeaders() }),
  copilotConfirm: (sessionId, pendingId, approve) =>
    request('/api/copilot/confirm', { method: 'POST', body: { session_id: sessionId, pending_id: pendingId, approve } }),
  importOrders: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/api/orders/import', { method: 'POST', form })
  },
}

export const exportUrl = {
  runs: () => `${BASE}/api/runs/export`,
  experiment: (id, kind = 'raw') => `${BASE}/api/experiments/${id}/export?kind=${kind}`,
}

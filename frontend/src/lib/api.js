import { llmHeaders } from './llmSettings'

// Thin client for the FastAPI backend. Errors keep the server's reasons so the UI can show them.
const BASE = import.meta.env?.VITE_API_BASE ?? ''

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
export const SERVER_DOWN = "The server isn't running. Run start-dev.bat, then press Retry."
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

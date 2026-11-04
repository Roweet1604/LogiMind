// Thin client for the FastAPI backend. Errors keep the server's reasons so the UI can show them.
const BASE = import.meta.env?.VITE_API_BASE ?? ''

export class ApiError extends Error {
  constructor(message, { status = 0, errors = [] } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.errors = errors
  }
}

// FastAPI returns either {detail: {message, errors}}, {detail: "text"}, or {detail: [pydantic issues]}.
export function parseErrorBody(status, body) {
  const d = body?.detail
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    return new ApiError(d.message || `Request failed (${status})`, { status, errors: d.errors || [] })
  }
  if (Array.isArray(d)) {
    const errors = d.map((e) => `${(e.loc || []).filter((p) => p !== 'body').join('.')}: ${e.msg}`)
    return new ApiError('Request has invalid fields', { status, errors })
  }
  if (typeof d === 'string') return new ApiError(d, { status })
  return new ApiError(`Request failed (${status})`, { status })
}

// Tenant API key: kept in memory and in sessionStorage only (gone when the tab closes), never in localStorage.
const KEY_STORE = 'logimind.apiKey'
let apiKey = (() => { try { return sessionStorage.getItem(KEY_STORE) || '' } catch { return '' } })()
export const getApiKey = () => apiKey
export function setApiKey(key) {
  apiKey = key || ''
  try { if (apiKey) sessionStorage.setItem(KEY_STORE, apiKey); else sessionStorage.removeItem(KEY_STORE) } catch { /* storage blocked */ }
}

async function request(path, { method = 'GET', body, form, raw = false, key } = {}) {
  let res
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'
  const k = key ?? apiKey
  if (k) headers['X-API-Key'] = k
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: Object.keys(headers).length ? headers : undefined,
      body: form || (body ? JSON.stringify(body) : undefined),
    })
  } catch {
    throw new ApiError('Cannot reach the backend. Is it running on port 8000?', { status: 0 })
  }
  if (!res.ok) {
    let parsed = null
    try { parsed = await res.json() } catch { /* non-JSON error body */ }
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
  listPlans: () => request('/api/plans'),
  getPlan: (id) => request(`/api/plans/${id}`),
  createPlan: (body) => request('/api/plans', { method: 'POST', body }),
  replan: (id, body) => request(`/api/plans/${id}/replan`, { method: 'POST', body }),
  createDriverLink: (id, body) => request(`/api/plans/${id}/driver-links`, { method: 'POST', body }),
  listDriverLinks: (id) => request(`/api/plans/${id}/driver-links`),
  revokeDriverLink: (linkId) => request(`/api/driver-links/${linkId}`, { method: 'DELETE' }),
  stopReports: (id) => request(`/api/plans/${id}/stop-reports`),
  copilotStatus: () => request('/api/copilot/status'),
  copilotChat: (message, sessionId) => request('/api/copilot/chat', { method: 'POST', body: { message, session_id: sessionId || null } }),
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

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

async function request(path, { method = 'GET', body, raw = false } = {}) {
  let res
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
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
}

export const exportUrl = {
  runs: () => `${BASE}/api/runs/export`,
  experiment: (id, kind = 'raw') => `${BASE}/api/experiments/${id}/export?kind=${kind}`,
}

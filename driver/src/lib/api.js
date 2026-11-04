// Driver API client. The link token goes in X-Driver-Token; nothing else identifies the driver.
const BASE = import.meta.env?.VITE_API_BASE ?? ''

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status // 0 = no connection
  }
}

async function request(token, path, { method = 'GET', body, form } = {}) {
  const headers = { 'X-Driver-Token': token }
  if (body) headers['Content-Type'] = 'application/json'
  let res
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body: form || (body ? JSON.stringify(body) : undefined) })
  } catch {
    throw new ApiError('No connection', 0)
  }
  if (!res.ok) {
    let detail = ''
    try { const j = await res.json(); detail = typeof j.detail === 'string' ? j.detail : '' } catch { /* not JSON */ }
    throw new ApiError(detail || `Request failed (${res.status})`, res.status)
  }
  return res.json()
}

export const getRoute = (token) => request(token, '/api/driver/route')
export const postStatus = (token, customerId, body) =>
  request(token, `/api/driver/stops/${customerId}/status`, { method: 'POST', body })
export function postPhoto(token, customerId, file) {
  const form = new FormData()
  form.append('file', file)
  return request(token, `/api/driver/stops/${customerId}/photo`, { method: 'POST', form })
}

// Driver API client. The link token goes in X-Driver-Token; nothing else identifies the driver.
const BUILT = (import.meta.env?.VITE_API_URL ?? import.meta.env?.VITE_API_BASE ?? '').replace(/\/+$/, '')

// Run-time API address (decision 0041, as in the console, decision 0040): a link made while the console used a
// laptop tunnel reads <console>/driver/?api=https://<name>.trycloudflare.com#t=<token>. The address is kept in
// localStorage because the installed app opens at its start URL without it; a new link without ?api= forgets it.
// Only quick-tunnel and localhost addresses are accepted.
const API_STORE = 'logimind.driver.apiUrl'
const ALLOWED_API = /^(https:\/\/[a-z0-9-]+\.trycloudflare\.com|http:\/\/(localhost|127\.0\.0\.1)(:\d{1,5})?)$/

// -> {base, store}: store is the value to remember ('' forgets it, undefined leaves storage alone).
export function pickApiBase({ search = '', hash = '', stored = '', built = '' } = {}) {
  const asked = (new URLSearchParams(search).get('api') || '').trim().replace(/\/+$/, '')
  if (ALLOWED_API.test(asked)) return { base: asked, store: asked }
  const newLink = /(?:^#|&)t=/.test(hash)
  if (!newLink && ALLOWED_API.test(stored)) return { base: stored, store: undefined }
  return { base: built, store: stored ? '' : undefined }
}

function resolveBase() {
  if (typeof window === 'undefined') return BUILT
  let stored = ''
  try { stored = localStorage.getItem(API_STORE) || '' } catch { /* storage blocked */ }
  const { search, hash } = window.location
  const pick = pickApiBase({ search, hash, stored, built: BUILT })
  try {
    if (pick.store === '') localStorage.removeItem(API_STORE)
    else if (pick.store) localStorage.setItem(API_STORE, pick.store)
  } catch { /* storage blocked */ }
  if (new URLSearchParams(search).has('api')) {
    const u = new URL(window.location.href)
    u.searchParams.delete('api')
    try { window.history.replaceState(window.history.state, '', u.pathname + u.search + u.hash) } catch { /* not allowed */ }
  }
  return pick.base
}

const BASE = resolveBase()

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

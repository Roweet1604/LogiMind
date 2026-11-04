// Local storage for the driver app. Every access is wrapped: storage can be blocked or full, and the app must
// still work (it then simply has no offline copy). Keys are per link, so two links never mix their data.
const TOKEN = 'logimind.driver.token'

function read(key, fallback) {
  try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v) } catch { return fallback }
}
function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true } catch { return false }
}
function remove(key) { try { localStorage.removeItem(key) } catch { /* storage blocked */ } }

// The token is short-lived (at most 24 h) and covers one route. It is kept so the installed app, which opens
// at "/" without the link's #t=..., still knows its route, and so the stop list works offline.
export const loadToken = () => read(TOKEN, '')
export const saveToken = (t) => write(TOKEN, t)
export const clearToken = () => remove(TOKEN)

// A stable per-link key without storing the token twice: the link id is the first claim.
export function linkKey(token) {
  try {
    const body = token.split('.')[1]
    const claims = JSON.parse(atob(body.replace(/-/g, '+').replace(/_/g, '/')))
    return claims.l || 'unknown'
  } catch { return 'unknown' }
}

export const loadRoute = (token) => read(`logimind.driver.route.${linkKey(token)}`, null)
export const saveRoute = (token, route, savedAt = new Date().toISOString()) =>
  write(`logimind.driver.route.${linkKey(token)}`, { route, savedAt })

export const loadQueue = (token) => read(`logimind.driver.queue.${linkKey(token)}`, [])
export const saveQueue = (token, queue) => write(`logimind.driver.queue.${linkKey(token)}`, queue)

// Reads "#t=<token>" from the link, stores it and removes it from the address bar and history.
export function takeTokenFromLocation(loc = window.location, hist = window.history) {
  const m = /(?:^#|&)t=([A-Za-z0-9._-]+)/.exec(loc.hash || '')
  if (!m) return loadToken()
  saveToken(m[1])
  try { hist.replaceState(null, '', loc.pathname + loc.search) } catch { /* not allowed in some contexts */ }
  return m[1]
}

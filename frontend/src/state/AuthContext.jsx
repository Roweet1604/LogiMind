import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, getApiKey, setApiKey } from '../lib/api'

const Ctx = createContext(null)
export const useAuth = () => useContext(Ctx)

// Per-tab flags (sessionStorage, like the key): whether the key came from demo mode, and whether the user signed
// out of the demo (then the tab stays signed out so a normal key can be tried).
const DEMO_FLAG = 'logimind.demo'
const NO_DEMO = 'logimind.noDemo'
const flag = (k) => { try { return sessionStorage.getItem(k) === '1' } catch { return false } }
const setFlag = (k, on) => { try { if (on) sessionStorage.setItem(k, '1'); else sessionStorage.removeItem(k) } catch { /* blocked */ } }

// Tenant login with an API key. The key is checked against GET /api/whoami before it is kept.
// Demo mode (local development server only, decision 0029): with no usable key, the console asks the backend for
// the demo tenant's key and signs in by itself. When demo mode is off, that request gets 404 and nothing happens.
export function AuthProvider({ children }) {
  const [me, setMe] = useState(null)              // {tenant_id, tenant_name, key_id, demo}
  const [state, setState] = useState('checking')

  const start = useCallback(async () => {
    setState('checking')
    if (getApiKey()) {
      try {
        const m = await api.whoami()
        setMe({ ...m, demo: flag(DEMO_FLAG) }); setState('in')
        return
      } catch {
        setApiKey('')
      }
    }
    if (!flag(NO_DEMO)) {
      try {
        const d = await api.demoSession()
        const m = await api.whoami(d.api_key)
        setApiKey(d.api_key); setFlag(DEMO_FLAG, true)
        setMe({ ...m, demo: true }); setState('in')
        return
      } catch { /* demo mode is off (404) or not allowed: normal sign-in */ }
    }
    setFlag(DEMO_FLAG, false); setMe(null); setState('out')
  }, [])

  useEffect(() => { start() }, [start])

  const login = useCallback(async (key) => {
    const m = await api.whoami(key.trim())     // throws ApiError (401) for a bad key
    setApiKey(key.trim()); setFlag(DEMO_FLAG, false)
    setMe({ ...m, demo: false })
    setState('in')
    return m
  }, [])

  const logout = useCallback(() => {
    if (flag(DEMO_FLAG)) setFlag(NO_DEMO, true)
    setApiKey(''); setFlag(DEMO_FLAG, false); setMe(null); setState('out')
  }, [])

  const value = useMemo(() => ({ me, state, login, logout }), [me, state, login, logout])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

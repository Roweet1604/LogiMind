import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, getApiKey, setApiKey } from '../lib/api'

const Ctx = createContext(null)
export const useAuth = () => useContext(Ctx)

// Tenant login with an API key. The key is checked against GET /api/whoami before it is kept.
export function AuthProvider({ children }) {
  const [me, setMe] = useState(null)              // {tenant_id, tenant_name, key_id}
  const [state, setState] = useState(getApiKey() ? 'checking' : 'out')

  useEffect(() => {
    if (!getApiKey()) return
    api.whoami().then((m) => { setMe(m); setState('in') })
      .catch(() => { setApiKey(''); setState('out') })
  }, [])

  const login = useCallback(async (key) => {
    const m = await api.whoami(key.trim())     // throws ApiError (401) for a bad key
    setApiKey(key.trim())
    setMe(m)
    setState('in')
    return m
  }, [])

  const logout = useCallback(() => { setApiKey(''); setMe(null); setState('out') }, [])

  const value = useMemo(() => ({ me, state, login, logout }), [me, state, login, logout])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

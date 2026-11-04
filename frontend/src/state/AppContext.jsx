import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'

const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

const KEY = 'routeopt.currentInstance'

export function AppProvider({ children }) {
  const [instances, setInstances] = useState([])
  const [currentId, setCurrentId] = useState(() => localStorage.getItem(KEY) || '')
  const [instance, setInstance] = useState(null)       // full detail of the current instance
  const [runs, setRuns] = useState([])                 // run summaries for the current instance
  const [selected, setSelected] = useState({ ortools: '', ga: '' }) // chosen run id per algorithm
  const [health, setHealth] = useState({ state: 'checking' })

  const refreshInstances = useCallback(async () => {
    const list = await api.listInstances()
    setInstances(list)
    return list
  }, [])

  const refreshRuns = useCallback(async () => {
    if (!currentId) { setRuns([]); return [] }
    const list = await api.listRuns(currentId)
    setRuns(list)
    return list
  }, [currentId])

  const selectInstance = useCallback((id) => {
    setCurrentId(id || '')
    setSelected({ ortools: '', ga: '' })
    if (id) localStorage.setItem(KEY, id); else localStorage.removeItem(KEY)
  }, [])

  // Initial load + health.
  useEffect(() => {
    api.health().then((h) => setHealth({ state: 'ok', env: h.environment, research: h.research_endpoints !== false }))
      .catch((e) => setHealth({ state: 'down', message: e.message }))
    refreshInstances().catch(() => {})
  }, [refreshInstances])

  // Load the current instance and its runs.
  useEffect(() => {
    if (!currentId) { setInstance(null); setRuns([]); return }
    let alive = true
    api.getInstance(currentId).then((i) => alive && setInstance(i)).catch(() => {
      if (alive) { setInstance(null); selectInstance('') } // stale id (e.g. data folder was cleared)
    })
    refreshRuns().catch(() => {})
    return () => { alive = false }
  }, [currentId, refreshRuns, selectInstance])

  // Default selection = most recent completed run per algorithm, including runs that found no solution
  // (a failed run must stay visible rather than being silently skipped).
  useEffect(() => {
    setSelected((prev) => {
      const next = { ...prev }
      for (const a of ['ortools', 'ga']) {
        const stillValid = runs.some((r) => r.run_id === prev[a])
        if (!stillValid) next[a] = runs.find((r) => r.algorithm === a && r.state === 'completed')?.run_id || ''
      }
      return next.ortools === prev.ortools && next.ga === prev.ga ? prev : next
    })
  }, [runs])

  const value = useMemo(() => ({
    instances, instance, currentId, selectInstance, refreshInstances, runs, refreshRuns,
    selected, setSelected, health,
  }), [instances, instance, currentId, selectInstance, refreshInstances, runs, refreshRuns, selected, health])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

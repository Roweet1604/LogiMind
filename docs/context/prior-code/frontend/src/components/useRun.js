import { useEffect, useState } from 'react'
import { api } from '../lib/api'

// Loads the full detail (routes, validation, metrics) of one run.
export function useRunDetail(runId) {
  const [state, setState] = useState({ run: null, loading: false, error: null })
  useEffect(() => {
    if (!runId) { setState({ run: null, loading: false, error: null }); return }
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    api.getRun(runId)
      .then((run) => alive && setState({ run, loading: false, error: null }))
      .catch((error) => alive && setState({ run: null, loading: false, error }))
    return () => { alive = false }
  }, [runId])
  return state
}

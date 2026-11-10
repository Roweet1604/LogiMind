import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import DriverLinks from '../components/DriverLinks'
import { SignInGate } from '../components/Gate'
import { EmptyState, Field, Notice, PageHeader, Panel, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../state/AuthContext'
import { planRoutes } from './PlanDetail'

// Driver links for one plan at a time. Only completed plans the validator accepted can get links
// (the backend refuses the others as well).
export default function Drivers() {
  const { state } = useAuth()
  const [plans, setPlans] = useState(null)
  const [chosen, setChosen] = useState('')
  const [plan, setPlan] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (state !== 'in') return
    api.listPlans().then((list) => {
      const ok = list.filter((p) => p.state === 'completed' && p.feasible === true)
      setPlans(ok)
      setChosen((c) => c || ok[0]?.plan_id || '')
    }).catch(setError)
  }, [state])

  useEffect(() => {
    if (!chosen) { setPlan(null); return undefined }
    let alive = true
    setPlan(null)
    api.getPlan(chosen).then((p) => alive && setPlan(p)).catch((e) => alive && setError(e))
    return () => { alive = false }
  }, [chosen])

  const routes = planRoutes(plan)
  return (
    <>
      <PageHeader title="Drivers">
        Make a link for each route and send it to the driver. The driver opens it on a phone, sees the stops in order and
        marks each one delivered or failed. Their reports appear here.
      </PageHeader>
      <SignInGate what="driver links" />
      {state === 'in' && (
        <div className="space-y-5">
          {error && <Notice kind="error" title="Could not load the plans">{error.message}</Notice>}
          {!plans && !error && <Spinner label="Loading plans" />}
          {plans && plans.length === 0 && (
            <EmptyState title="No feasible plan yet">Driver links need a finished plan that the validator accepted. <Link className="link" to="/plans">Go to Plans</Link>.</EmptyState>
          )}
          {plans && plans.length > 0 && (
            <Panel className="max-w-xl">
              <Field label="Plan" htmlFor="driver-plan">
                <select id="driver-plan" className="input" value={chosen} onChange={(e) => setChosen(e.target.value)}>
                  {plans.map((p) => <option key={p.plan_id} value={p.plan_id}>{p.name || p.plan_id} ({p.plan_id})</option>)}
                </select>
              </Field>
            </Panel>
          )}
          {chosen && !plan && !error && <Spinner label="Loading plan" />}
          {plan && routes && <DriverLinks key={plan.plan_id} plan={plan} routes={routes} />}
        </div>
      )}
    </>
  )
}

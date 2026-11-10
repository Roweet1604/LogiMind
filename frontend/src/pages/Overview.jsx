import { ArrowRight, ClipboardList, MessageSquare, Truck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { SignInGate } from '../components/Gate'
import { AlgoTag, EmptyState, Notice, PageHeader, Panel, Spinner, Stats, TableWrap } from '../components/ui'
import { api } from '../lib/api'
import { fmt, fmtTime } from '../lib/format'
import { useAuth } from '../state/AuthContext'
import { PlanBadge } from './Plans'

// Start page for dispatchers: the tenant's plans at a glance and where to go next.
// The research comparison (OR-Tools vs GA) lives under Research (dev only).
export default function Overview() {
  const { state, me } = useAuth()
  const [plans, setPlans] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    if (state !== 'in') return
    api.listPlans().then(setPlans).catch(setError)
  }, [state])

  const count = (f) => (plans ? plans.filter(f).length : null)
  return (
    <>
      <PageHeader title="Overview"
        actions={state === 'in' && <Link className="btn btn-primary" to="/plans">Open plans<ArrowRight size={16} aria-hidden="true" /></Link>}>
        Plan delivery routes for your fleet. Every route comes from a solver and is checked by an independent validator
        before it is called feasible.
      </PageHeader>
      <SignInGate what="the overview" />
      {state === 'in' && (
        <div className="space-y-6">
          {me?.demo && (
            <Notice kind="warn" title="Demo mode">
              You are signed in to the local demo account. Its orders are synthetic (made up for the demo), not real customers.
            </Notice>
          )}
          {error && <Notice kind="error" title="Could not load plans">{error.message}</Notice>}
          {!plans && !error && <Spinner label="Loading plans" />}
          {plans && (
            <Stats items={[
              { label: 'Plans', value: String(plans.length) },
              { label: 'Feasible', value: String(count((p) => p.state === 'completed' && p.feasible === true)), sub: 'checked by the validator' },
              { label: 'Being solved', value: String(count((p) => p.state === 'queued' || p.state === 'running')) },
              { label: 'Need attention', value: String(count((p) => p.state === 'failed' || (p.state === 'completed' && p.feasible !== true))), sub: 'failed or not feasible' },
            ]} />
          )}
          <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <Panel title="Latest plans">
              {plans && plans.length === 0 && <EmptyState title="No plans yet"><Link className="link" to="/plans">Create the first plan</Link> from an order file.</EmptyState>}
              {plans && plans.length > 0 && (
                <TableWrap>
                  <thead><tr><th>Plan</th><th>Validator</th><th>Engine</th><th className="num">Orders</th><th className="num">Distance</th><th>Created</th></tr></thead>
                  <tbody>
                    {plans.slice(0, 6).map((p) => (
                      <tr key={p.plan_id} className="hover:bg-sunken">
                        <td><Link className="link" to={`/plans/${p.plan_id}`}>{p.name || p.plan_id}</Link></td>
                        <td><PlanBadge plan={p} /></td>
                        <td><AlgoTag algo={p.engine} /></td>
                        <td className="num">{p.n_customers}</td>
                        <td className="num">{fmt(p.total_distance)}</td>
                        <td className="whitespace-nowrap text-xs">{fmtTime(p.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              )}
            </Panel>
            <Panel title="What you can do">
              <ul className="space-y-4 text-sm">
                <li className="flex gap-3"><ClipboardList size={18} aria-hidden="true" className="mt-0.5 shrink-0" />
                  <span><Link className="link font-medium" to="/plans">Plans</Link>: import orders, plan routes, and replan after a breakdown, a failed delivery or an urgent order.</span></li>
                <li className="flex gap-3"><Truck size={18} aria-hidden="true" className="mt-0.5 shrink-0" />
                  <span><Link className="link font-medium" to="/drivers">Drivers</Link>: send each driver a link to their stop list and see what they report.</span></li>
                <li className="flex gap-3"><MessageSquare size={18} aria-hidden="true" className="mt-0.5 shrink-0" />
                  <span><Link className="link font-medium" to="/copilot">Copilot</Link>: ask in plain words. It never writes routes itself.</span></li>
              </ul>
            </Panel>
          </div>
        </div>
      )}
    </>
  )
}

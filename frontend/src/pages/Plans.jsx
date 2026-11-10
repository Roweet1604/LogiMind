import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlgoTag, Badge, EmptyState, Field, Notice, NumberInput, PageHeader, Panel, Spinner, TableWrap } from '../components/ui'
import { fmt, fmtTime } from '../lib/format'
import { api } from '../lib/api'
import { sampleOrders } from '../lib/sample'
import { useAuth } from '../state/AuthContext'

// The validator's verdict (never the solver's own status), as icon + word.
export function PlanBadge({ plan, size }) {
  if (plan.state === 'queued' || plan.state === 'running') return <Badge kind="busy" size={size}>{plan.state}</Badge>
  if (plan.state === 'failed') return <Badge kind="bad" size={size}>failed</Badge>
  if (plan.feasible === true) return <Badge kind="ok" size={size}>feasible</Badge>
  if (plan.feasible === false) return <Badge kind="bad" size={size}>infeasible</Badge>
  return <Badge kind="bad" size={size}>no plan</Badge>
}

const isSynthetic = (name) => /^synthetic/i.test(name || '')

const ENGINES = [
  ['auto', 'Auto (selector explains its choice)'], ['ortools', 'OR-Tools'], ['hybrid', 'Hybrid (OR-Tools seed + GA)'],
  ['ga', 'GA + local search'],
]

// Step 1: orders from a CSV/Excel file (validated row by row by the backend) or a synthetic sample.
function OrdersInput({ orders, setOrders }) {
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function upload(file) {
    if (!file) return
    setBusy(true); setError(null); setReport(null)
    try {
      const r = await api.importOrders(file)
      setReport(r)
      setOrders(r.ok ? { name: file.name, customers: r.customers, coordinates: r.coordinates } : null)
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-3">
      <Field label="Order file (.csv or .xlsx)" htmlFor="orders-file"
        hint="Columns: id, demand, x/y or lon/lat; optional ready_time, due_time, service_time. Every row is checked.">
        <input id="orders-file" type="file" accept=".csv,.xlsx" className="input" onChange={(e) => upload(e.target.files?.[0])} />
      </Field>
      <button type="button" className="btn" onClick={() => { setReport(null); setError(null); setOrders(sampleOrders()) }}>
        Use a synthetic sample (12 orders)
      </button>
      {busy && <Spinner label="Checking file" />}
      {error && <Notice kind="error" title="File rejected" errors={error.errors}>{error.message}</Notice>}
      {report && !report.ok && (
        <Notice kind="error" title={`${report.invalid_rows} of ${report.rows} rows have problems; nothing was imported`}>
          <TableWrap>
            <thead><tr><th className="text-left">Row</th><th className="text-left">Column</th><th className="text-left">Problem</th></tr></thead>
            <tbody>{report.issues.map((i, k) => <tr key={k}><td className="num">{i.row}</td><td>{i.field}</td><td>{i.message}</td></tr>)}</tbody>
          </TableWrap>
        </Notice>
      )}
      {orders && (
        <Notice kind="ok" title={`${orders.customers.length} orders ready`}>
          {orders.name}{isSynthetic(orders.name) && <> <Badge kind="draft">synthetic data</Badge></>}
        </Notice>
      )}
    </div>
  )
}

const DISTANCE_SOURCES = [
  ['straight_line', 'Straight line (no road data)'],
  ['osrm', 'Road network (OSRM)'],
  ['estimate', 'Estimate: straight line × detour factor'],
]

function NewPlan({ onCreated }) {
  const [orders, setOrders] = useState(null)
  const [f, setF] = useState({ depot_x: 50, depot_y: 50, vehicle_count: 3, vehicle_capacity: 20, engine: 'auto', time_limit_s: 3, distance_source: 'straight_line' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: v }))

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    const metric = orders.coordinates === 'lonlat' ? 'haversine' : 'euclidean'
    const instance = {
      name: orders.name, metric, distance_unit: metric === 'haversine' ? 'km' : 'unit', depot_x: f.depot_x, depot_y: f.depot_y,
      vehicle_count: f.vehicle_count, vehicle_capacity: f.vehicle_capacity, fixed_vehicle_cost: 0, customers: orders.customers,
    }
    try {
      const body = { instance, engine: f.engine, time_limit_s: f.time_limit_s }
      if (metric === 'haversine') body.distance_source = f.distance_source
      const r = await api.createPlan(body)
      onCreated(r.plan_id)
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <Panel title="New plan" note="Orders, then fleet and engine">
      <div className="grid gap-6 lg:grid-cols-2 lg:divide-x lg:divide-rule2">
        <div>
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink2">1 · Orders</h3>
          <OrdersInput orders={orders} setOrders={setOrders} />
        </div>
        <form onSubmit={submit} className="grid grid-cols-2 content-start gap-3 lg:pl-6">
          <h3 className="col-span-2 text-xs font-semibold uppercase tracking-wider text-ink2">2 · Fleet and engine</h3>
          <Field label="Depot x (or lon)" htmlFor="depot-x"><NumberInput id="depot-x" value={f.depot_x} onChange={set('depot_x')} step="any" /></Field>
          <Field label="Depot y (or lat)" htmlFor="depot-y"><NumberInput id="depot-y" value={f.depot_y} onChange={set('depot_y')} step="any" /></Field>
          <Field label="Vehicles" htmlFor="vehicles"><NumberInput id="vehicles" value={f.vehicle_count} onChange={set('vehicle_count')} min={1} /></Field>
          <Field label="Capacity per vehicle" htmlFor="capacity"><NumberInput id="capacity" value={f.vehicle_capacity} onChange={set('vehicle_capacity')} min={1} /></Field>
          <Field label="Engine" htmlFor="engine">
            <select id="engine" className="input" value={f.engine} onChange={(e) => set('engine')(e.target.value)}>
              {ENGINES.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
            </select>
          </Field>
          <Field label="Time budget (s)" htmlFor="budget"><NumberInput id="budget" value={f.time_limit_s} onChange={set('time_limit_s')} min={0.5} step={0.5} /></Field>
          {orders?.coordinates === 'lonlat' && (
            <div className="col-span-2">
              <Field label="Distances and travel times" htmlFor="distances"
                hint="Road network uses the self-hosted OSRM. If it is not available, the plan uses straight line × detour factor and says so.">
                <select id="distances" className="input" value={f.distance_source} onChange={(e) => set('distance_source')(e.target.value)}>
                  {DISTANCE_SOURCES.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
                </select>
              </Field>
            </div>
          )}
          <div className="col-span-2">
            {error && <div className="mb-3"><Notice kind="error" title="Plan not created" errors={error.errors}>{error.message}</Notice></div>}
            <button type="submit" className="btn btn-primary" disabled={!orders || busy}>{busy ? <Spinner label="Submitting" /> : 'Create plan'}</button>
          </div>
        </form>
      </div>
    </Panel>
  )
}

export default function Plans() {
  const { state } = useAuth()
  const [plans, setPlans] = useState(null)
  const [error, setError] = useState(null)
  const navigate = useNavigate()
  const refresh = useCallback(() => api.listPlans().then(setPlans).catch(setError), [])
  useEffect(() => { if (state === 'in') refresh() }, [state, refresh])
  // Keep the list fresh while a plan is still queued or being solved (e.g. the demo plans right after start-up).
  const waiting = plans?.some((p) => p.state === 'queued' || p.state === 'running')
  useEffect(() => {
    if (!waiting) return undefined
    const t = setInterval(refresh, 2000)
    return () => clearInterval(t)
  }, [waiting, refresh])

  if (state !== 'in') {
    return (
      <>
        <PageHeader title="Plans" />
        {state === 'checking' ? <Spinner label="Checking key" />
          : <EmptyState title="Sign in first">Plans belong to a tenant. <Link className="underline" to="/login">Sign in with an API key</Link>.</EmptyState>}
      </>
    )
  }
  return (
    <>
      <PageHeader title="Plans">Each plan is solved by the chosen engine and checked by the independent validator. Only the validator decides “feasible”.</PageHeader>
      <NewPlan onCreated={(id) => navigate(`/plans/${id}`)} />
      <Panel title="Your plans" className="mt-6">
        {error && <Notice kind="error" title="Could not load plans">{error.message}</Notice>}
        {!plans && !error && <Spinner />}
        {plans && plans.length === 0 && <EmptyState title="No plans yet">Import orders above to create the first one.</EmptyState>}
        {plans && plans.length > 0 && (
          <TableWrap>
            <thead><tr><th>Plan</th><th>Validator</th><th>Engine</th><th className="num">Orders</th><th className="num">Distance</th><th>Replan of</th><th>Created</th></tr></thead>
            <tbody>
              {plans.map((p) => (
                <tr key={p.plan_id} className="hover:bg-sunken">
                  <td><Link className="link font-mono" to={`/plans/${p.plan_id}`}>{p.plan_id}</Link>
                    <span className="block text-xs text-ink2">{p.name}{isSynthetic(p.name) && <> <Badge kind="draft">synthetic</Badge></>}</span></td>
                  <td><PlanBadge plan={p} /></td>
                  <td><AlgoTag algo={p.engine} /></td>
                  <td className="num">{p.n_customers}</td>
                  <td className="num">{fmt(p.total_distance)}</td>
                  <td>{p.parent_plan_id
                    ? <span className="inline-flex flex-wrap items-center gap-1.5"><Badge kind="replanned">{p.event_type?.replace('_', ' ')}</Badge><span className="font-mono text-xs">{p.parent_plan_id}</span></span>
                    : '—'}</td>
                  <td className="whitespace-nowrap text-xs">{fmtTime(p.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Panel>
    </>
  )
}

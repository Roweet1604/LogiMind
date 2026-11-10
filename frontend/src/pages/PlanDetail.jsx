import { Clock, GitBranch } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import DriverLinks from '../components/DriverLinks'
import RouteMap from '../components/RouteMap'
import { AlgoTag, Badge, Field, Notice, NumberInput, PageHeader, Panel, Segmented, Spinner, Stats } from '../components/ui'
import { ALGOS } from '../lib/algos'
import { api } from '../lib/api'
import { fmt, fmtInt, fmtSeconds, SOLVER_STATUS_TEXT } from '../lib/format'
import { useAuth } from '../state/AuthContext'
import { SignInGate } from '../components/Gate'
import { PlanBadge } from './Plans'

export const planRoutes = (p) => p?.result?.routes ?? p?.result?.solve?.routes ?? null
const busy = (p) => p && (p.state === 'queued' || p.state === 'running')

const EVENTS = [['vehicle_breakdown', 'Vehicle breakdown'], ['failed_delivery', 'Failed delivery'], ['urgent_order', 'Urgent order']]

// Replan form: the backend freezes the completed stops and checks the new plan with the validator.
export function ReplanPanel({ plan, onReplanned }) {
  const routes = planRoutes(plan) || []
  const inst = plan.instance
  const used = routes.map((r, v) => ({ r, v })).filter((x) => x.r.length)
  const [type, setType] = useState('vehicle_breakdown')
  const [completed, setCompleted] = useState(() => Object.fromEntries(used.map(({ v }) => [v, 0])))
  const [vehicle, setVehicle] = useState(used[0]?.v ?? 0)
  const [failed, setFailed] = useState('')
  const [retry, setRetry] = useState(true)
  const nextId = Math.max(0, ...inst.customers.map((c) => c.id)) + 1
  const [urgent, setUrgent] = useState({ id: nextId, x: inst.depot.x, y: inst.depot.y, demand: 1, ready_time: 0, due_time: '', service_time: 0 })
  const [now, setNow] = useState('')
  const [engine, setEngine] = useState('ortools')
  const [budget, setBudget] = useState(3)
  const [error, setError] = useState(null)
  const [sending, setSending] = useState(false)

  if (plan.state !== 'completed' || plan.feasible !== true) {
    const why = plan.state !== 'completed' ? `still ${plan.state}` : plan.feasible === false ? 'not feasible' : 'without a solution'
    return <Notice title="Replanning needs a completed, feasible plan">This plan is {why}.</Notice>
  }
  const pending = used.flatMap(({ r, v }) => r.slice(completed[v] || 0))
  const anyFrozen = Object.values(completed).some((n) => n > 0)

  async function submit(e) {
    e.preventDefault()
    setSending(true); setError(null)
    const event = { type, completed: Object.fromEntries(Object.entries(completed).filter(([, n]) => n > 0)) }
    if (now !== '' && inst.has_time_windows) event.now = now
    if (type === 'vehicle_breakdown') event.vehicle = Number(vehicle)
    if (type === 'failed_delivery') Object.assign(event, { customer_id: Number(failed), retry })
    if (type === 'urgent_order') {
      const c = { id: urgent.id, x: urgent.x, y: urgent.y, demand: urgent.demand }
      if (inst.has_time_windows) Object.assign(c, { ready_time: urgent.ready_time, due_time: urgent.due_time === '' ? null : urgent.due_time, service_time: urgent.service_time })
      event.customer = c
    }
    try {
      const r = await api.replan(plan.plan_id, { event, engine, time_limit_s: budget })
      onReplanned(r.plan_id)
    } catch (err) { setError(err) } finally { setSending(false) }
  }

  const setU = (k) => (v) => setUrgent((p) => ({ ...p, [k]: v }))
  return (
    <Panel title="Replan after a disruption" note="Completed stops stay fixed; the current plan is the warm start">
      <form onSubmit={submit} className="space-y-4">
        <Segmented label="Disruption" value={type} onChange={setType} options={EVENTS} />
        <fieldset>
          <legend className="label">Stops already completed per vehicle</legend>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {used.map(({ r, v }) => (
              <Field key={v} label={`Vehicle ${v} (of ${r.length})`} htmlFor={`done-${v}`}>
                <NumberInput id={`done-${v}`} value={completed[v]} min={0} max={r.length}
                  onChange={(n) => setCompleted((p) => ({ ...p, [v]: n === '' ? 0 : Math.max(0, Math.min(r.length, n)) }))} />
              </Field>
            ))}
          </div>
        </fieldset>
        {type === 'vehicle_breakdown' && (
          <div className="max-w-sm"><Field label="Broken-down vehicle" htmlFor="broken">
            <select id="broken" className="input" value={vehicle} onChange={(e) => setVehicle(e.target.value)}>
              {used.map(({ v }) => <option key={v} value={v}>Vehicle {v}</option>)}
            </select>
          </Field></div>
        )}
        {type === 'failed_delivery' && (
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Customer whose delivery failed" htmlFor="failed">
              <select id="failed" className="input" value={failed} onChange={(e) => setFailed(e.target.value)}>
                <option value="">Choose a customer</option>
                {pending.map((c) => <option key={c} value={c}>Customer {c}</option>)}
              </select>
            </Field>
            <label className="mt-6 flex items-center gap-2 text-sm">
              <input type="checkbox" checked={retry} onChange={(e) => setRetry(e.target.checked)} />
              Visit again later (unticked: drop it from the plan; it is reported as dropped)
            </label>
          </div>
        )}
        {type === 'urgent_order' && (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Field label="Order id" htmlFor="u-id"><NumberInput id="u-id" value={urgent.id} onChange={setU('id')} min={1} /></Field>
            <Field label="x (or lon)" htmlFor="u-x"><NumberInput id="u-x" value={urgent.x} onChange={setU('x')} step="any" /></Field>
            <Field label="y (or lat)" htmlFor="u-y"><NumberInput id="u-y" value={urgent.y} onChange={setU('y')} step="any" /></Field>
            <Field label="Demand" htmlFor="u-d"><NumberInput id="u-d" value={urgent.demand} onChange={setU('demand')} min={1} /></Field>
            {inst.has_time_windows && <>
              <Field label="Ready time" htmlFor="u-r"><NumberInput id="u-r" value={urgent.ready_time} onChange={setU('ready_time')} min={0} /></Field>
              <Field label="Due time" htmlFor="u-due"><NumberInput id="u-due" value={urgent.due_time} onChange={setU('due_time')} min={0} /></Field>
              <Field label="Service time" htmlFor="u-s"><NumberInput id="u-s" value={urgent.service_time} onChange={setU('service_time')} min={0} /></Field>
            </>}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {inst.has_time_windows && (
            <Field label="Current time (optional)" htmlFor="now" hint="No unfinished stop starts earlier">
              <NumberInput id="now" value={now} onChange={setNow} min={0} step="any" />
            </Field>
          )}
          <Field label="Engine" htmlFor="re-engine" hint={anyFrozen ? 'The GA cannot keep completed stops; OR-Tools only.' : undefined}>
            <select id="re-engine" className="input" value={engine} onChange={(e) => setEngine(e.target.value)}>
              <option value="ortools">OR-Tools (warm start)</option>
              <option value="ga" disabled={anyFrozen}>GA + local search (seeded with this plan)</option>
            </select>
          </Field>
          <Field label="Time budget (s)" htmlFor="re-budget"><NumberInput id="re-budget" value={budget} onChange={setBudget} min={0.5} step={0.5} /></Field>
        </div>
        {error && <Notice kind="error" title="Replan not accepted" errors={error.errors}>{error.message}</Notice>}
        <button type="submit" className="btn btn-primary"
          disabled={sending || (type === 'failed_delivery' && !failed) || (engine === 'ga' && anyFrozen)}>
          {sending ? <Spinner label="Submitting" /> : 'Replan'}
        </button>
      </form>
    </Panel>
  )
}

export function DistanceSource({ source }) {
  if (!source) return null
  if (source.fallback) {
    return (
      <Notice kind="warn" title="Fallback distances: not road data">
        Road distances were requested, but OSRM was not available: {source.reason}. This plan uses straight-line
        distance × {source.detour_factor} at {source.speed_kmh} km/h instead.
      </Notice>
    )
  }
  return (
    <Notice title="Distances and travel times">
      {source.label}{source.provider === 'osrm' && source.fetched_at ? `, fetched ${source.fetched_at}${source.cache === 'hit' ? ' (from the cache)' : ''}` : ''}.
      {source.warning && ` ${source.warning}.`}
    </Notice>
  )
}

const TIMEOUTS = new Set(['hard_timeout', 'timeout_no_solution'])

// Always at the top of a plan: the validator's verdict, then every flag that changes how far the plan can be trusted.
export function StatusStrip({ plan }) {
  const src = plan.distance_source
  return (
    <section aria-label="Plan status" className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-3 rounded-lg border border-rule bg-panel px-4 py-3 shadow-panel">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-ink2">Validator</span>
        <PlanBadge plan={plan} size="lg" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-ink2">Engine</span><AlgoTag algo={plan.engine} />
      </div>
      {plan.state === 'completed' && TIMEOUTS.has(plan.status) && (
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-ink2">Solver</span><Badge kind="timeout">timeout</Badge>
        </div>
      )}
      {src && (
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-ink2">Distances</span>
          {src.fallback ? <Badge kind="warn">fallback estimate</Badge> : <span className="text-sm">{src.provider === 'osrm' ? 'road network (OSRM)' : src.provider === 'haversine_detour' ? 'estimate' : 'straight line'}</span>}
        </div>
      )}
      {plan.parent_plan_id && (
        <div className="flex items-center gap-2">
          <Badge kind="replanned">replanned</Badge>
          <Link className="link font-mono text-xs" to={`/plans/${plan.parent_plan_id}`}>from {plan.parent_plan_id}</Link>
        </div>
      )}
    </section>
  )
}

// Route list beside the map. Selecting a route highlights it on the map; the sequence is the solver's, unchanged.
function RouteList({ routes, engine, focus, setFocus }) {
  const a = ALGOS[engine]
  return (
    <Panel title="Routes" note={`${routes.filter((r) => r.length).length} in use`}
      actions={focus != null && <button type="button" className="btn btn-ghost min-h-0 px-2 py-1 text-xs" onClick={() => setFocus(null)}>Show all</button>}>
      <ul className="-mx-1 space-y-1 overflow-y-auto xl:max-h-[31rem]">
        {routes.map((r, i) => (
          <li key={i}>
            <button type="button" disabled={!r.length} aria-pressed={focus === i} onClick={() => setFocus(focus === i ? null : i)}
              className={`w-full rounded-md border px-3 py-2 text-left disabled:cursor-default ${focus === i ? 'border-ink bg-accent-soft' : 'border-transparent hover:border-rule hover:bg-sunken'}`}>
              <span className="flex items-center gap-2">
                {a && <svg width="20" height="8" aria-hidden="true"><line x1="1" y1="4" x2="19" y2="4" stroke={a.color} strokeWidth="3" strokeDasharray={a.dash} /></svg>}
                <span className="font-medium">Vehicle {i}</span>
                <span className="num ml-auto text-xs text-ink2">{r.length} {r.length === 1 ? 'stop' : 'stops'}</span>
              </span>
              <span className="mt-0.5 block break-words font-mono text-xs text-ink2">{r.length ? r.join(' → ') : '(unused)'}</span>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

export default function PlanDetail() {
  const { id } = useParams()
  const { state } = useAuth()
  const [plan, setPlan] = useState(null)
  const [error, setError] = useState(null)
  const [focus, setFocus] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (state !== 'in') return
    let alive = true
    let timer
    const load = () => api.getPlan(id).then((p) => {
      if (!alive) return
      setPlan(p)
      if (busy(p)) timer = setTimeout(load, 1000)
    }).catch((e) => alive && setError(e))
    setPlan(null); setError(null); setFocus(null); load()
    return () => { alive = false; clearTimeout(timer) }
  }, [id, state])

  if (state !== 'in') return <SignInGate what="plans" />
  if (error) return <Notice kind="error" title="Could not load the plan">{error.message}</Notice>
  if (!plan) return <Spinner label="Loading plan" />

  const routes = planRoutes(plan)
  const m = plan.result?.metrics
  const v = plan.result?.validation
  const timing = plan.replan?.timing
  const timeout = TIMEOUTS.has(plan.status)
  return (
    <>
      <PageHeader title={<span className="font-mono">{plan.plan_id}</span>}
        actions={<Link className="btn" to="/plans">All plans</Link>}>
        {plan.instance?.name}{plan.instance && <> · <span className="num">{plan.instance.customers.length}</span> orders · <span className="num">{plan.instance.vehicle_count}</span> vehicles</>}
      </PageHeader>
      <StatusStrip plan={plan} />
      {busy(plan) && <Notice title="Solving">The plan is {plan.state}; this page updates by itself.</Notice>}
      {plan.state === 'failed' && <Notice kind="error" title="The run failed">{plan.error}</Notice>}
      {plan.state === 'completed' && (
        <div className="space-y-5">
          {(plan.feasible === false || timeout || plan.distance_source?.fallback) && (
            <div className="space-y-3">
              {timeout && <Notice kind="warn" icon={Clock} title="Timeout">{SOLVER_STATUS_TEXT[plan.status]}.</Notice>}
              {plan.feasible === false && (
                <Notice kind="error" title="Not a feasible plan"
                  errors={[...(v?.violations || []).map((x) => x.detail), ...(plan.result?.replan_violations || [])]}>
                  {routes ? 'The validator rejected these routes; they are shown for diagnosis only.' : 'The solver returned no routes.'}
                </Notice>
              )}
              {plan.distance_source?.fallback && <DistanceSource source={plan.distance_source} />}
            </div>
          )}
          <Stats items={[
            { label: 'Total distance', value: fmt(m?.total_distance) },
            { label: 'Vehicles used', value: fmtInt(m?.vehicles_used), sub: `of ${plan.instance.vehicle_count}` },
            { label: 'Time to feasible plan', value: timing ? fmtSeconds(timing.disruption_to_feasible_s) : '—', sub: timing ? 'from the replan request' : 'replans only' },
            { label: 'Solver status', value: SOLVER_STATUS_TEXT[plan.status] || plan.status || '—' },
          ]} />
          {routes && (
            <div className="plan-grid">
              <Panel title="Map" note={focus != null ? `Vehicle ${focus} highlighted` : undefined}>
                <RouteMap instance={plan.instance} routes={routes} algo={plan.engine} focus={focus} height={520} />
              </Panel>
              <RouteList routes={routes} engine={plan.engine} focus={focus} setFocus={setFocus} />
            </div>
          )}
          <div className="grid gap-3 lg:grid-cols-2">
            {plan.distance_source && !plan.distance_source.fallback && <DistanceSource source={plan.distance_source} />}
            {plan.selection?.explanation && <Notice title={plan.selection.method === 'model' ? 'Why this engine' : 'Engine'}>{plan.selection.explanation}</Notice>}
            {plan.replan && (
              <Notice icon={GitBranch} title={`Replan of ${plan.parent_plan_id} after ${plan.event?.type?.replace('_', ' ')}`}
                errors={plan.replan.notes}>
                <Link className="link" to={`/plans/${plan.parent_plan_id}`}>Open the previous plan</Link>.
                Warm start: {plan.replan.warm_start}{timing?.warm_start_result ? ` (${timing.warm_start_result})` : ''}.
                {plan.replan.dropped_customers?.length > 0 && ` Dropped: ${plan.replan.dropped_customers.join(', ')}.`}
              </Notice>
            )}
          </div>
          {routes && plan.feasible === true && <DriverLinks key={`d-${plan.plan_id}`} plan={plan} routes={routes} />}
          <ReplanPanel key={plan.plan_id} plan={plan} onReplanned={(nid) => navigate(`/plans/${nid}`)} />
        </div>
      )}
    </>
  )
}

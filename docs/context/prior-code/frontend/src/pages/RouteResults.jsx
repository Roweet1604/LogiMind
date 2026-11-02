import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ALGOS } from '../lib/algos'
import { fmt, fmtInt, fmtSeconds, SOLVER_STATUS_TEXT } from '../lib/format'
import { useApp } from '../state/AppContext'
import { useRunDetail } from '../components/useRun'
import RouteMap from '../components/RouteMap'
import RunPicker from '../components/RunPicker'
import { AlgoTag, EmptyState, FeasibilityBadge, Notice, PageHeader, Panel, Segmented, Spinner, Stats, TableWrap } from '../components/ui'

function VehicleTable({ run, instance, focus, setFocus }) {
  const routes = run.result.routes
  const m = run.metrics
  const unit = instance.distance_unit
  const byId = Object.fromEntries(instance.customers.map((c) => [c.id, c]))
  return (
    <div>
      <TableWrap>
        <thead><tr>
          <th className="th">Vehicle</th><th className="th">Stops in visit order</th><th className="th text-right">Load / cap.</th><th className="th text-right">Dist. ({unit})</th>
        </tr></thead>
        <tbody>
          {routes.map((r, i) => (
            <tr key={i} className={focus === i ? 'bg-accent-soft' : ''}>
              <td className="td">
                {r.length
                  ? <button className="rounded border border-rule bg-white px-2.5 py-0.5 font-medium hover:bg-rule2" onClick={() => setFocus(focus === i ? null : i)} aria-pressed={focus === i}>{i + 1}</button>
                  : <span className="px-2.5 text-ink2">{i + 1}</span>}
              </td>
              <td className="td break-words font-mono text-[13px]">{r.length ? `depot → ${r.join(' → ')} → depot` : <span className="font-sans text-ink2">unused</span>}</td>
              <td className="td text-right num">{r.length ? `${r.reduce((s, id) => s + (byId[id]?.demand || 0), 0)} / ${instance.vehicle_capacity}` : '—'}</td>
              <td className="td text-right num">{r.length ? fmt(m?.route_distances?.[i]) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
      <p className="mt-2 text-xs text-ink2">Select a vehicle number to highlight its route on the map. Distances are recomputed by the shared evaluator.</p>
    </div>
  )
}

function RunPanel({ algo, runId, instance, focus, setFocus, split }) {
  const { run, loading, error } = useRunDetail(runId)
  const unit = instance.distance_unit
  if (!runId) return <EmptyState title={`No ${ALGOS[algo].label} run yet`}><Link className="underline" to="/run">Run it from the optimization page.</Link></EmptyState>
  if (loading) return <Spinner label="Loading run" />
  if (error) return <Notice kind="error" title="Could not load the run">{error.message}</Notice>
  if (!run) return null
  const routes = run.result?.routes
  const v = run.validation
  const m = run.metrics

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1">
        <AlgoTag algo={algo} /><FeasibilityBadge run={run} />
        <span className="text-xs text-ink2">solver status: {SOLVER_STATUS_TEXT[run.result?.status] || run.result?.status || run.error} · runtime {fmtSeconds(run.result?.runtime_seconds)}{run.result?.seed != null ? ` · seed ${run.result.seed}` : ''}</span>
      </div>

      {!routes && <Notice kind="error" title="No routes to show">{run.result?.message || run.error || 'The solver returned no solution; metrics are not available.'}</Notice>}

      {routes && (
        <>
          {v && !v.feasible && (
            <div className="mb-4"><Notice kind="error" title="The independent validator rejected this solution" errors={v.violations.map((x) => x.detail)} /></div>
          )}
          <div className={split ? 'grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]' : 'space-y-5'}>
            <Panel className="!p-3 md:!p-4">
              <RouteMap instance={instance} routes={routes} algo={algo} focus={focus} height={split ? 620 : 460} />
            </Panel>
            <div className="space-y-5">
              {m && (
                <Stats cols={2} items={[
                  { label: `Distance (${unit})`, value: fmt(m.total_distance) },
                  { label: 'Est. cost', value: fmt(m.estimated_cost), sub: 'synthetic units' },
                  { label: 'Vehicles used', value: fmtInt(m.vehicles_used), sub: `of ${instance.vehicle_count}` },
                  { label: 'Unserved / violations', value: `${fmtInt(m.unserved_customers)} / ${fmtInt(m.capacity_violations + m.other_violations)}` },
                ]} />
              )}
              <Panel title="Vehicles" className="!p-4"><VehicleTable run={run} instance={instance} focus={focus} setFocus={setFocus} /></Panel>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default function RouteResults() {
  const { instance, selected } = useApp()
  const [view, setView] = useState('ortools')
  const [focus, setFocus] = useState(null)
  if (!instance) return (<><PageHeader title="Route results" /><EmptyState title="No instance loaded"><Link className="underline" to="/setup">Create or load an instance first.</Link></EmptyState></>)
  return (
    <>
      <PageHeader title="Route results">Inspect stop order, load and feasibility per vehicle. Feasibility is decided by the independent validator, not by the solver.</PageHeader>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <RunPicker />
        <Segmented label="Algorithm view" value={view} onChange={(k) => { setView(k); setFocus(null) }}
          options={[['ortools', 'OR-Tools'], ['ga', 'Genetic Algorithm'], ['both', 'Side by side']]} />
      </div>
      {view === 'both' ? (
        <div className="grid gap-8 2xl:grid-cols-2">
          <RunPanel algo="ortools" runId={selected.ortools} instance={instance} focus={focus} setFocus={setFocus} />
          <RunPanel algo="ga" runId={selected.ga} instance={instance} focus={focus} setFocus={setFocus} />
        </div>
      ) : (
        <RunPanel split algo={view} runId={selected[view]} instance={instance} focus={focus} setFocus={setFocus} />
      )}
    </>
  )
}

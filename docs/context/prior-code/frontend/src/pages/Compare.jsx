import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ALGOS } from '../lib/algos'
import { fmt, fmtInt, isNum, SOLVER_STATUS_TEXT } from '../lib/format'
import { useApp } from '../state/AppContext'
import { useRunDetail } from '../components/useRun'
import RunPicker from '../components/RunPicker'
import { AlgoTag, EmptyState, FeasibilityBadge, Notice, PageHeader, Panel, Spinner, TableWrap } from '../components/ui'

const TICK = { fontSize: 12, fill: '#596067' }

function Value({ v, digits = 2, better, both }) {
  if (!isNum(v)) return <span className="text-ink2" title="not available">—</span>
  const txt = digits === 0 ? fmtInt(v) : fmt(v, digits)
  return <span className={better && both ? 'font-semibold' : ''}>{txt}{better && both ? <span className="sr-only"> (lower)</span> : null}{better && both ? ' ↓' : ''}</span>
}

function MiniBar({ title, unit, data }) {
  const vals = data.filter((d) => isNum(d.value))
  if (!vals.length) return null
  return (
    <figure>
      <figcaption className="mb-2 text-xs font-medium text-ink2">{title} ({unit})</figcaption>
      <div style={{ height: 230 }}>
        <ResponsiveContainer>
          <BarChart data={vals} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#EEEBE2" vertical={false} />
            <XAxis dataKey="name" tick={TICK} stroke="#D6D1C3" />
            <YAxis tick={TICK} stroke="#D6D1C3" width={48} />
            <Tooltip formatter={(v) => [`${fmt(v)} ${unit}`, title]} />
            <Bar dataKey="value" isAnimationActive={false} maxBarSize={72} radius={[3, 3, 0, 0]}>
              {vals.map((d) => <Cell key={d.key} fill={ALGOS[d.key].color} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

export default function Compare() {
  const { instance, selected } = useApp()
  const a = useRunDetail(selected.ortools)
  const b = useRunDetail(selected.ga)
  if (!instance) return (<><PageHeader title="Compare algorithms" /><EmptyState title="No instance loaded"><Link className="underline" to="/setup">Create or load an instance first.</Link></EmptyState></>)
  const unit = instance.distance_unit
  const loading = a.loading || b.loading
  const ro = a.run, rg = b.run
  const m = (r) => r?.metrics
  const both = Boolean(ro?.validation?.feasible && rg?.validation?.feasible)
  const lower = (x, y) => (isNum(x) && isNum(y) ? (x < y ? 'a' : y < x ? 'b' : '') : '')
  const rows = [
    ['Total distance', unit, m(ro)?.total_distance, m(rg)?.total_distance, 2, true],
    ['Estimated cost', 'cost units', m(ro)?.estimated_cost, m(rg)?.estimated_cost, 2, true],
    ['Vehicles used', 'count', m(ro)?.vehicles_used, m(rg)?.vehicles_used, 0, true],
    ['Unserved customers', 'count', m(ro)?.unserved_customers, m(rg)?.unserved_customers, 0, false],
    ['Capacity violations', 'count', m(ro)?.capacity_violations, m(rg)?.capacity_violations, 0, false],
    ['Other violations', 'count', m(ro)?.other_violations, m(rg)?.other_violations, 0, false],
    ['Runtime (measured)', 's', ro?.result?.runtime_seconds, rg?.result?.runtime_seconds, 2, false],
  ]
  const gap = both && isNum(m(ro)?.estimated_cost) && m(ro).estimated_cost > 0 ? ((m(rg).estimated_cost - m(ro).estimated_cost) / m(ro).estimated_cost) * 100 : null

  const hist = rg?.result?.diagnostics?.fitness_history
  const gens = rg?.result?.diagnostics?.generations_run
  const step = hist && isNum(gens) ? Math.max(1, Math.floor((gens + 1) / 200)) : 1
  const histData = hist?.map((f, i) => ({ generation: i * step, cost: f }))
  const budget = ro?.result?.config?.time_limit_s

  return (
    <>
      <PageHeader title="Compare algorithms">
        Metrics from the shared evaluator, on one instance and one cost model. Values come from the runs selected below; nothing here is simulated.
      </PageHeader>
      <div className="mb-5"><RunPicker /></div>
      {loading && <Spinner label="Loading runs" />}
      {(a.error || b.error) && <Notice kind="error" title="Could not load a run">{(a.error || b.error).message}</Notice>}
      {!loading && !ro && !rg && <EmptyState title="Nothing to compare yet"><Link className="underline" to="/run">Run at least one algorithm.</Link></EmptyState>}

      {(ro || rg) && (
        <div className="space-y-6">
          <Panel title="Metrics">
            <TableWrap>
              <thead><tr>
                <th className="th">Metric</th><th className="th">Unit</th>
                <th className="th text-right"><AlgoTag algo="ortools" /></th><th className="th text-right"><AlgoTag algo="ga" /></th>
              </tr></thead>
              <tbody>
                <tr><td className="td font-medium">Solver status</td><td className="td" /><td className="td text-right">{ro ? SOLVER_STATUS_TEXT[ro.result?.status] || ro.result?.status : 'no run'}</td><td className="td text-right">{rg ? SOLVER_STATUS_TEXT[rg.result?.status] || rg.result?.status : 'no run'}</td></tr>
                <tr><td className="td font-medium">Feasible (validator)</td><td className="td" /><td className="td text-right"><FeasibilityBadge run={ro} /></td><td className="td text-right"><FeasibilityBadge run={rg} /></td></tr>
                {rows.map(([label, u, x, y, d, cmp]) => {
                  const w = cmp ? lower(x, y) : ''
                  return (
                    <tr key={label}>
                      <td className="td font-medium">{label}</td><td className="td text-ink2">{u}</td>
                      <td className="td text-right num"><Value v={x} digits={d} better={w === 'a'} both={both} /></td>
                      <td className="td text-right num"><Value v={y} digits={d} better={w === 'b'} both={both} /></td>
                    </tr>
                  )
                })}
                <tr><td className="td font-medium">Seed</td><td className="td" /><td className="td text-right text-ink2">n/a</td><td className="td text-right num">{rg?.result?.seed ?? '—'}</td></tr>
              </tbody>
            </TableWrap>
            <p className="mt-3 text-xs text-ink2">↓ marks the lower value, shown only when both solutions are feasible. A dash means the metric is not available, not zero. Costs are synthetic units: {instance.fixed_vehicle_cost} per used vehicle + {instance.cost_per_distance} per {unit}.</p>
            {gap != null && (
              <p className="mt-3 text-base">
                {Math.abs(gap) < 0.05
                  ? <>On this single instance and run, both solutions have the same estimated cost (within 0.05%).</>
                  : <>On this single instance and run, the GA's estimated cost is <strong className="num">{fmt(Math.abs(gap), 1)}%</strong> {gap > 0 ? 'higher' : 'lower'} than OR-Tools'.</>}
                {' '}One run does not establish which method is better; see the Benchmark lab for repeated runs.
              </p>
            )}
            {((ro && !ro.validation) || (rg && !rg.validation)) && (
              <div className="mt-4"><Notice kind="warn" title="A solver returned no solution">Its metrics are shown as unavailable and are excluded from comparisons.</Notice></div>
            )}
          </Panel>

          <Panel title="Charts" note="from the runs above">
            <div className="grid gap-8 md:grid-cols-3">
              <MiniBar title="Total distance" unit={unit} data={[{ key: 'ortools', name: 'OR-Tools', value: m(ro)?.total_distance }, { key: 'ga', name: 'GA', value: m(rg)?.total_distance }]} />
              <MiniBar title="Estimated cost" unit="cost units" data={[{ key: 'ortools', name: 'OR-Tools', value: m(ro)?.estimated_cost }, { key: 'ga', name: 'GA', value: m(rg)?.estimated_cost }]} />
              <MiniBar title="Runtime" unit="s" data={[{ key: 'ortools', name: 'OR-Tools', value: ro?.result?.runtime_seconds }, { key: 'ga', name: 'GA', value: rg?.result?.runtime_seconds }]} />
            </div>
            {isNum(budget) && (
              <p className="mt-3 text-xs text-ink2">Both solvers were limited by wall-clock time (budget {budget} s), so runtime mostly reflects the budget, not speed. Compare solution quality at equal time.</p>
            )}
          </Panel>

          {histData && histData.length > 1 && (
            <Panel title="GA convergence" note="best cost per generation, cost units (same objective as the table)">
              <div style={{ height: 300 }}>
                <ResponsiveContainer>
                  <LineChart data={histData} margin={{ top: 8, right: 16, bottom: 20, left: 0 }}>
                    <CartesianGrid stroke="#EEEBE2" />
                    <XAxis dataKey="generation" type="number" domain={[0, 'dataMax']} tickCount={8} tick={TICK} stroke="#D6D1C3" label={{ value: 'generation', position: 'insideBottom', offset: -12, fontSize: 12, fill: '#596067' }} />
                    <YAxis tick={TICK} stroke="#D6D1C3" domain={['auto', 'auto']} width={56} />
                    <Tooltip formatter={(v) => [fmt(v), 'GA best cost']} labelFormatter={(g) => `generation ${g}`} />
                    <Line type="monotone" dataKey="cost" stroke={ALGOS.ga.color} strokeDasharray={ALGOS.ga.dash} dot={false} strokeWidth={2.5} isAnimationActive={false} />
                    {isNum(m(ro)?.estimated_cost) && <ReferenceLine y={m(ro).estimated_cost} stroke={ALGOS.ortools.color} strokeWidth={2} label={{ value: 'OR-Tools final cost', position: 'insideTopRight', fontSize: 12, fill: ALGOS.ortools.color }} />}
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-1 text-xs text-ink2">{gens} generations, stopped by {rg.result.diagnostics.stop_reason.replace('_', ' ')}. The GA's penalised fitness equals its cost when the fleet limit is respected.</p>
            </Panel>
          )}
        </div>
      )}
    </>
  )
}

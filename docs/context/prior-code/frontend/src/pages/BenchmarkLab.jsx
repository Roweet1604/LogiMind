import { useCallback, useEffect, useMemo, useState } from 'react'
import { CartesianGrid, ErrorBar, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, exportUrl } from '../lib/api'
import { ALGOS } from '../lib/algos'
import { fmt, fmtInt, fmtSeconds, fmtTime, isNum } from '../lib/format'
import { useApp } from '../state/AppContext'
import { Download } from 'lucide-react'
import { Badge, EmptyState, Field, Notice, NumberInput, PageHeader, Panel, Spinner, TableWrap } from '../components/ui'

const TICK = { fontSize: 12, fill: '#596067' }

const SIZES = [10, 25, 50, 100]

function SizeChart({ title, unit, metric, data, selectedBudgets }) {
  const pts = data.filter((r) => isNum(r[`ortools_${metric}_mean`]) || isNum(r[`ga_${metric}_mean`]))
  if (!pts.length) return null
  return (
    <figure>
      <figcaption className="mb-2 text-xs font-medium text-ink2">{title} ({unit}), mean over feasible runs; GA bars = ±1 standard deviation</figcaption>
      <div style={{ height: 280 }}>
        <ResponsiveContainer>
          <LineChart data={pts} margin={{ top: 6, right: 16, bottom: 18, left: 0 }}>
            <CartesianGrid stroke="#EEEBE2" />
            <XAxis dataKey="n" type="number" domain={['dataMin', 'dataMax']} tick={TICK} stroke="#D6D1C3" label={{ value: 'customers', position: 'insideBottom', offset: -12, fontSize: 12, fill: '#596067' }} />
            <YAxis tick={TICK} stroke="#D6D1C3" width={56} />
            <Tooltip formatter={(v, n) => [`${fmt(v)} ${unit}`, n]} labelFormatter={(n) => `${n} customers`} />
            <Legend verticalAlign="top" height={24} />
            <Line name="OR-Tools" type="monotone" dataKey={`ortools_${metric}_mean`} stroke={ALGOS.ortools.color} strokeWidth={2.5} dot={{ r: 4 }} isAnimationActive={false} connectNulls />
            <Line name="Genetic Algorithm" type="monotone" dataKey={`ga_${metric}_mean`} stroke={ALGOS.ga.color} strokeDasharray={ALGOS.ga.dash} strokeWidth={2.5} dot={{ r: 4 }} isAnimationActive={false} connectNulls>
              <ErrorBar dataKey={`ga_${metric}_err`} stroke={ALGOS.ga.color} width={4} />
            </Line>
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

export default function BenchmarkLab() {
  const { refreshInstances } = useApp()
  const [sizes, setSizes] = useState([10, 25])
  const [budget, setBudget] = useState(10)
  const [seeds, setSeeds] = useState(5)
  const [orRepeats, setOrRepeats] = useState(1)
  const [metric, setMetric] = useState('haversine')
  const [error, setError] = useState(null)
  const [launching, setLaunching] = useState(false)
  const [exps, setExps] = useState([])
  const [checked, setChecked] = useState({})
  const [loadError, setLoadError] = useState(null)

  const load = useCallback(async () => {
    try { setExps(await api.listExperiments()); setLoadError(null) } catch (e) { setLoadError(e) }
  }, [])
  useEffect(() => { load() }, [load])

  const anyRunning = exps.some((e) => e.state === 'running')
  useEffect(() => {
    if (!anyRunning) return undefined
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [anyRunning, load])

  // `checked` holds only explicit user overrides; otherwise finished experiments are included by default.
  const isIncluded = (e) => checked[e.experiment_id] ?? e.state !== 'running'

  const totalSeconds = sizes.length * (orRepeats + seeds) * budget

  async function launch() {
    setError(null); setLaunching(true)
    try {
      for (const n of sizes) {
        const inst = await api.generateInstance({ n_customers: n, seed: n * 1000, metric })
        await api.startExperiment({ instance_id: inst.instance_id, time_budget_s: budget, ga_seeds: seeds, ortools_repeats: orRepeats })
      }
      await refreshInstances().catch(() => {})
      await load()
    } catch (e) { setError(e) } finally { setLaunching(false) }
  }

  const chosen = exps.filter((e) => isIncluded(e) && e.summary?.length)
  const budgets = [...new Set(chosen.map((e) => e.time_budget_s))]

  // Long form: one row per (experiment, algorithm), then pivot by n.
  const table = useMemo(() => chosen.flatMap((e) => e.summary.map((s) => ({ ...s, experiment_id: e.experiment_id, budget: e.time_budget_s }))).sort((x, y) => x.n_customers - y.n_customers || x.algorithm.localeCompare(y.algorithm)), [chosen])
  const chartData = useMemo(() => {
    const by = {}
    table.forEach((s) => {
      const row = (by[s.n_customers] ||= { n: s.n_customers })
      for (const k of ['total_distance', 'estimated_cost', 'runtime_seconds']) {
        row[`${s.algorithm}_${k}_mean`] = s[`${k}_mean`]
        row[`${s.algorithm}_${k}_err`] = s[`${k}_std`]
      }
    })
    return Object.values(by).sort((a, b) => a.n - b.n)
  }, [table])

  const toggleSize = (n) => setSizes((s) => (s.includes(n) ? s.filter((x) => x !== n) : [...s, n].sort((a, b) => a - b)))

  return (
    <>
      <PageHeader title="Benchmark lab"
        actions={<a className="btn" href={exportUrl.runs()} download><Download size={16} aria-hidden="true" />Export all runs (CSV)</a>}>
        Repeat both algorithms across instance sizes under one time budget and read aggregates. Each size uses one generated instance (seed = size × 1000); GA runs repeat over seeds 0 to k−1.
      </PageHeader>

      <Panel title="Run a benchmark" className="mb-6">
        {error && <div className="mb-3"><Notice kind="error" title={error.message} errors={error.errors} /></div>}
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-5">
          <fieldset>
            <legend className="label">Customer counts</legend>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
              {SIZES.map((n) => (
                <label key={n} className="inline-flex items-center gap-1.5"><input type="checkbox" checked={sizes.includes(n)} onChange={() => toggleSize(n)} />{n}</label>
              ))}
            </div>
          </fieldset>
          <Field label="Distance metric" htmlFor="b-metric">
            <select id="b-metric" className="input" value={metric} onChange={(e) => setMetric(e.target.value)}>
              <option value="haversine">haversine (lat/lon)</option><option value="euclidean">euclidean (planar)</option>
            </select>
          </Field>
          <Field label="Time budget per run (s)" htmlFor="b-budget" hint="identical for OR-Tools and every GA run"><NumberInput id="b-budget" value={budget} min={0.5} step="any" onChange={setBudget} /></Field>
          <Field label="GA seeds per instance" htmlFor="b-seeds"><NumberInput id="b-seeds" value={seeds} min={1} max={50} onChange={setSeeds} /></Field>
          <Field label="OR-Tools repeats per instance" htmlFor="b-or"><NumberInput id="b-or" value={orRepeats} min={1} max={10} onChange={setOrRepeats} /></Field>
        </div>
        <p className="mt-4 text-xs text-ink2">Runs execute one at a time. Estimated total: {fmtSeconds(totalSeconds)} ({sizes.length} sizes × {orRepeats + seeds} runs × {budget} s). Results appear below as runs finish.</p>
        <button className="btn btn-primary mt-5" disabled={!sizes.length || launching || anyRunning} onClick={launch}>
          {launching ? <Spinner label="Queuing" /> : anyRunning ? <Spinner label="Benchmark running" /> : 'Start benchmark'}
        </button>
      </Panel>

      <Panel title="Experiments" note="select which to include in the aggregates below" className="mb-6">
        {loadError && <Notice kind="error" title="Could not load experiments">{loadError.message}</Notice>}
        {!exps.length && !loadError && <EmptyState title="No experiments yet">Start a benchmark above. Nothing is shown until real runs exist.</EmptyState>}
        {exps.length > 0 && (
          <TableWrap>
            <thead><tr><th className="th">Include</th><th className="th">Started</th><th className="th text-right">Customers</th><th className="th">State</th><th className="th text-right">Budget</th><th className="th text-right">GA seeds</th><th className="th">Instance</th><th className="th">CSV</th></tr></thead>
            <tbody>
              {exps.map((e) => (
                <tr key={e.experiment_id}>
                  <td className="td"><input type="checkbox" aria-label={`Include ${e.experiment_id}`} checked={isIncluded(e)} onChange={(ev) => setChecked((c) => ({ ...c, [e.experiment_id]: ev.target.checked }))} /></td>
                  <td className="td">{fmtTime(e.created_at)}</td>
                  <td className="td text-right num">{fmtInt(e.n_customers)}</td>
                  <td className="td"><Badge kind={e.state === 'completed' ? 'ok' : e.state === 'running' ? 'warn' : 'bad'}>{e.state.replaceAll('_', ' ')}</Badge></td>
                  <td className="td text-right num">{e.time_budget_s} s</td>
                  <td className="td text-right num">{e.ga_seeds}</td>
                  <td className="td font-mono text-xs">{e.instance_id}</td>
                  <td className="td whitespace-nowrap"><a className="underline" href={exportUrl.experiment(e.experiment_id, 'raw')} download>raw</a> · <a className="underline" href={exportUrl.experiment(e.experiment_id, 'summary')} download>summary</a></td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Panel>

      {chosen.length > 0 && (
        <Panel title="Aggregates across sizes">
          {budgets.length > 1 && <div className="mb-3"><Notice kind="warn" title="Selected experiments used different time budgets">Budgets: {budgets.join(', ')} s. Compare sizes only within one budget.</Notice></div>}
          <TableWrap>
            <thead><tr>
              <th className="th text-right">Customers</th><th className="th">Algorithm</th><th className="th text-right">Budget (s)</th><th className="th text-right">Feasible / runs</th>
              <th className="th text-right">Distance mean (km)</th><th className="th text-right">median</th><th className="th text-right">std</th>
              <th className="th text-right">Cost mean</th><th className="th text-right">Vehicles mean</th>
            </tr></thead>
            <tbody>
              {table.map((s) => (
                <tr key={`${s.experiment_id}-${s.algorithm}`}>
                  <td className="td text-right num">{s.n_customers}</td>
                  <td className="td">{ALGOS[s.algorithm]?.label || s.algorithm}</td>
                  <td className="td text-right num">{s.budget}</td>
                  <td className="td text-right num">{s.feasible_runs} / {s.runs}</td>
                  <td className="td text-right num">{fmt(s.total_distance_mean)}</td>
                  <td className="td text-right num">{fmt(s.total_distance_median)}</td>
                  <td className="td text-right num">{fmt(s.total_distance_std)}</td>
                  <td className="td text-right num">{fmt(s.estimated_cost_mean)}</td>
                  <td className="td text-right num">{fmt(s.vehicles_used_mean, 1)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <p className="mt-1 text-xs text-ink2">Statistics use feasible runs only; infeasible or failed runs are counted in "runs" but never averaged in. A dash means no feasible run (or, for std, a single run). With one OR-Tools run per instance there is no OR-Tools variability estimate. Cost is in synthetic cost units.</p>
          <div className="mt-6 grid gap-8 xl:grid-cols-2">
            <SizeChart title="Total distance" unit="km" metric="total_distance" data={chartData} />
            <SizeChart title="Estimated cost" unit="cost units" metric="estimated_cost" data={chartData} />
          </div>
          <div className="mt-8 grid gap-8 xl:grid-cols-2">
            <SizeChart title="Runtime" unit="s" metric="runtime_seconds" data={chartData} />
          </div>
          <p className="mt-2 text-xs text-ink2">Both algorithms stop at the same time limit, so runtime curves track the budget. Scalability shows up in solution quality and feasibility as the instance grows.</p>
        </Panel>
      )}
    </>
  )
}

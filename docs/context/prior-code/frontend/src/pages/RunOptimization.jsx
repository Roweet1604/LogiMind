import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { ALGOS } from '../lib/algos'
import { fmtSeconds, SOLVER_STATUS_TEXT } from '../lib/format'
import { useApp } from '../state/AppContext'
import { AlgoTag, Badge, EmptyState, Field, Notice, NumberInput, PageHeader, Panel, Spinner, TableWrap } from '../components/ui'

const FIRST = ['PATH_CHEAPEST_ARC', 'PARALLEL_CHEAPEST_INSERTION', 'SAVINGS']
const META = ['GUIDED_LOCAL_SEARCH', 'SIMULATED_ANNEALING', 'TABU_SEARCH']
const TERMINAL = ['completed', 'failed']

function AlgoBlock({ algo, checked, onToggle, blurb, children }) {
  const a = ALGOS[algo]
  return (
    <section className={`panel border-l-4 ${checked ? '' : 'opacity-60'}`} style={{ borderLeftColor: a.color }}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2><AlgoTag algo={algo} /></h2>
          <p className="mt-1 text-xs text-ink2">{blurb}</p>
        </div>
        <label className="inline-flex items-center gap-2 text-sm font-medium">
          <input type="checkbox" checked={checked} onChange={(e) => onToggle(e.target.checked)} aria-label={`Run ${a.label}`} />
          Include
        </label>
      </div>
      <fieldset disabled={!checked} className="contents">{children}</fieldset>
    </section>
  )
}

export default function RunOptimization() {
  const { instance, refreshRuns, setSelected } = useApp()
  const [use, setUse] = useState({ ortools: true, ga: true })
  const [budget, setBudget] = useState(10)
  const [orp, setOrp] = useState({ first_solution: FIRST[0], metaheuristic: META[0] })
  const [gap, setGap] = useState({ population_size: 100, max_generations: 500, stagnation_generations: 100, elite_count: 2, tournament_size: 3, crossover_rate: 0.9, mutation_rate: 0.2, nn_seed_fraction: 0.1, seed: 0 })
  const [timeOnly, setTimeOnly] = useState(true)
  const [jobs, setJobs] = useState([])   // [{algo, runId, run, startedMs}]
  const [error, setError] = useState(null)
  const [now, setNow] = useState(Date.now())
  const jobsRef = useRef(jobs)
  jobsRef.current = jobs

  const active = jobs.some((j) => !j.run || !TERMINAL.includes(j.run.state))

  useEffect(() => {
    if (!active) return undefined
    const t = setInterval(async () => {
      setNow(Date.now())
      const next = await Promise.all(jobsRef.current.map(async (j) => {
        if (j.run && TERMINAL.includes(j.run.state)) return j
        try { return { ...j, run: await api.getRun(j.runId) } } catch { return j }
      }))
      setJobs(next)
      if (next.every((j) => j.run && TERMINAL.includes(j.run.state))) {
        await refreshRuns().catch(() => {})
        setSelected((s) => {
          const out = { ...s }
          next.forEach((j) => { if (j.run.state === 'completed') out[j.algo] = j.runId })
          return out
        })
      }
    }, 1000)
    return () => clearInterval(t)
  }, [active, refreshRuns, setSelected])

  async function start() {
    setError(null)
    const algos = ['ortools', 'ga'].filter((a) => use[a])
    try {
      const started = []
      for (const algo of algos) {
        const body = { instance_id: instance.instance_id, algorithm: algo, time_limit_s: budget, ortools: orp, ga: { ...gap, ...(timeOnly ? { max_generations: 1000000, stagnation_generations: null } : {}) } }
        const r = await api.startRun(body)
        started.push({ algo, runId: r.run_id, run: null, startedMs: Date.now() })
      }
      setJobs(started)
    } catch (e) { setError(e) }
  }

  if (!instance) {
    return (
      <>
        <PageHeader title="Run optimization" />
        <EmptyState title="No instance loaded"><Link className="underline" to="/setup">Create or load an instance first.</Link></EmptyState>
      </>
    )
  }

  const nSel = Number(use.ortools) + Number(use.ga)
  const gs = (k) => (v) => setGap((g) => ({ ...g, [k]: v }))

  return (
    <>
      <PageHeader title="Run optimization">
        Instance <span className="font-mono text-[15px]">{instance.instance_id}</span> · {instance.customers.length} customers · {instance.vehicle_count} vehicles.
        Runs execute one at a time on the backend, so timing is not distorted by parallel jobs.
      </PageHeader>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-6">
          <AlgoBlock algo="ortools" checked={use.ortools} onToggle={(v) => setUse((u) => ({ ...u, ortools: v }))}
            blurb="Google OR-Tools routing solver with a capacity dimension. Search stops at the time budget.">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="First solution strategy" htmlFor="or-first">
                <select id="or-first" className="input" value={orp.first_solution} onChange={(e) => setOrp({ ...orp, first_solution: e.target.value })}>{FIRST.map((x) => <option key={x}>{x}</option>)}</select>
              </Field>
              <Field label="Local search metaheuristic" htmlFor="or-meta">
                <select id="or-meta" className="input" value={orp.metaheuristic} onChange={(e) => setOrp({ ...orp, metaheuristic: e.target.value })}>{META.map((x) => <option key={x}>{x}</option>)}</select>
              </Field>
            </div>
          </AlgoBlock>

          <AlgoBlock algo="ga" checked={use.ga} onToggle={(v) => setUse((u) => ({ ...u, ga: v }))}
            blurb="Our own population-based search: giant-tour permutation, split decoder, order crossover, tournament selection, elitism.">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <Field label="Population size" htmlFor="ga-pop"><NumberInput id="ga-pop" value={gap.population_size} min={4} onChange={gs('population_size')} /></Field>
              <Field label="Elite count" htmlFor="ga-elite"><NumberInput id="ga-elite" value={gap.elite_count} min={0} onChange={gs('elite_count')} /></Field>
              <Field label="Tournament size" htmlFor="ga-tour"><NumberInput id="ga-tour" value={gap.tournament_size} min={1} onChange={gs('tournament_size')} /></Field>
              <Field label="Crossover rate" htmlFor="ga-cx"><NumberInput id="ga-cx" value={gap.crossover_rate} min={0} max={1} step={0.05} onChange={gs('crossover_rate')} /></Field>
              <Field label="Mutation rate" htmlFor="ga-mut"><NumberInput id="ga-mut" value={gap.mutation_rate} min={0} max={1} step={0.05} onChange={gs('mutation_rate')} /></Field>
              <Field label="Nearest-neighbour seeds" htmlFor="ga-nn" hint="fraction of initial population"><NumberInput id="ga-nn" value={gap.nn_seed_fraction} min={0} max={1} step={0.05} onChange={gs('nn_seed_fraction')} /></Field>
              <Field label="Random seed" htmlFor="ga-seed"><NumberInput id="ga-seed" value={gap.seed} onChange={gs('seed')} /></Field>
              <Field label="Max generations" htmlFor="ga-gen"><NumberInput id="ga-gen" value={gap.max_generations} min={1} disabled={timeOnly} onChange={gs('max_generations')} /></Field>
              <Field label="Stagnation limit (generations)" htmlFor="ga-stag"><NumberInput id="ga-stag" value={gap.stagnation_generations} min={1} disabled={timeOnly} onChange={gs('stagnation_generations')} /></Field>
            </div>
            <label className="mt-4 inline-flex items-center gap-2">
              <input type="checkbox" checked={timeOnly} onChange={(e) => setTimeOnly(e.target.checked)} />
              Stop on the time budget only (ignore generation and stagnation limits)
            </label>
          </AlgoBlock>
        </div>

        <div className="xl:sticky xl:top-8 xl:self-start">
          <Panel title="Budget and execution">
            <div className="max-w-xs">
              <Field label="Time budget per run (seconds, wall clock)" htmlFor="budget" hint="Applied to both algorithms. Use the same value for a fair comparison.">
                <NumberInput id="budget" value={budget} min={0.5} step="any" onChange={setBudget} />
              </Field>
            </div>
            {error && <div className="mt-4"><Notice kind="error" title={error.message} errors={error.errors} /></div>}
            <div className="mt-5">
              <button className="btn btn-primary w-full sm:w-auto" disabled={!nSel || active} onClick={start}>
                {active ? <Spinner label="Running" /> : `Run ${nSel === 2 ? 'both algorithms' : nSel === 1 ? 'selected algorithm' : '(select an algorithm)'}`}
              </button>
              <p className="mt-2 text-xs text-ink2">Expected duration: about {fmtSeconds(budget * nSel)} (queued and executed in sequence).</p>
            </div>

            {jobs.length > 0 && (
              <div className="mt-6 border-t border-rule pt-5">
                <TableWrap>
                  <thead><tr><th className="th">Algorithm</th><th className="th">State</th><th className="th">Elapsed</th><th className="th">Runtime</th></tr></thead>
                  <tbody>
                    {jobs.map((j) => {
                      const st = j.run?.state || 'queued'
                      const done = TERMINAL.includes(st)
                      return (
                        <tr key={j.runId}>
                          <td className="td"><AlgoTag algo={j.algo} /></td>
                          <td className="td"><Badge kind={st === 'completed' ? 'ok' : st === 'failed' ? 'bad' : 'warn'}>{st}</Badge>
                            <span className="mt-1 block text-xs text-ink2">{j.run?.result ? SOLVER_STATUS_TEXT[j.run.result.status] || j.run.result.status : j.run?.error || ''}</span></td>
                          <td className="td num">{done ? '—' : fmtSeconds((now - j.startedMs) / 1000)}</td>
                          <td className="td num">{fmtSeconds(j.run?.result?.runtime_seconds)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </TableWrap>
                <p className="mt-1 text-xs text-ink2">Elapsed is the browser's stopwatch (includes queueing); runtime is measured by the solver run itself.</p>
                {!active && jobs.every((j) => j.run?.state === 'completed') && (
                  <p className="mt-4 flex flex-wrap gap-2"><Link className="btn btn-primary" to="/results">Inspect routes</Link><Link className="btn" to="/compare">Compare</Link></p>
                )}
                {jobs.some((j) => j.run?.state === 'failed' || (j.run?.result && j.run.result.status !== 'solved')) && !active && (
                  <div className="mt-4"><Notice kind="warn" title="At least one run did not return a solution">
                    {jobs.filter((j) => j.run?.result?.message).map((j) => <p key={j.runId}>{ALGOS[j.algo].label}: {j.run.result.message}</p>)}
                  </Notice></div>
                )}
              </div>
            )}
          </Panel>
        </div>
      </div>
    </>
  )
}

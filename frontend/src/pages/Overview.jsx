import { ArrowRight, Download } from 'lucide-react'
import { Link } from 'react-router-dom'
import { exportUrl } from '../lib/api'
import { fmt, fmtTime } from '../lib/format'
import { useApp } from '../state/AppContext'
import { AlgoTag, Badge, EmptyState, PageHeader, Panel, TableWrap } from '../components/ui'

export default function Overview() {
  const { instance, runs, health } = useApp()
  const done = runs.filter((r) => r.state === 'completed')
  const hasBoth = done.some((r) => r.algorithm === 'ortools') && done.some((r) => r.algorithm === 'ga')
  const next = !instance
    ? { to: '/setup', label: 'Set up a problem' }
    : !done.length ? { to: '/run', label: 'Run optimization' }
    : !hasBoth ? { to: '/run', label: 'Run the other algorithm' }
    : { to: '/compare', label: 'Compare algorithms' }

  const steps = [
    ['/setup', '1', 'Problem setup', instance ? `${instance.customers.length} customers loaded` : 'No instance yet', Boolean(instance)],
    ['/run', '2', 'Run optimization', done.length ? `${done.length} completed run${done.length > 1 ? 's' : ''} on this instance` : 'No runs yet', done.length > 0],
    ['/results', '3', 'Route results', 'Stop order, load and feasibility per vehicle', done.length > 0],
    ['/compare', '4', 'Compare algorithms', 'Metrics from the shared evaluator', hasBoth],
    ['/benchmark', '5', 'Benchmark lab', 'Repeated runs across instance sizes', null],
  ]
  return (
    <>
      <PageHeader title="Supply chain route optimization"
        actions={<Link className="btn btn-primary" to={next.to}>{next.label}<ArrowRight size={16} aria-hidden="true" /></Link>}>
        A comparison of Google OR-Tools and a custom genetic algorithm on the capacitated vehicle routing problem (CVRP).
        Both solve the same instance under the same cost model, and one independent validator checks every solution.
      </PageHeader>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Panel title="Workflow">
          <ol>
            {steps.map(([to, n, label, status, ok]) => (
              <li key={to} className="flex items-center gap-4 border-b border-rule2 py-3 last:border-0">
                <span className="w-5 font-mono text-ink2">{n}</span>
                <div className="min-w-0 flex-1">
                  <Link className="font-medium underline decoration-rule underline-offset-4 hover:decoration-ink" to={to}>{label}</Link>
                  <p className="text-xs text-ink2">{status}</p>
                </div>
                {ok !== null && <Badge kind={ok ? 'ok' : 'neutral'}>{ok ? 'done' : 'open'}</Badge>}
              </li>
            ))}
          </ol>
          {health.state === 'ok' && (
            <p className="mt-3 text-xs text-ink2">Backend: Python {health.env.python}, OR-Tools {health.env.ortools}, {health.env.cpu_count} CPU(s). Measured runtimes depend on this machine.</p>
          )}
        </Panel>

        <Panel title="Recent runs on the current instance" note="real runs only"
          actions={runs.length > 0 && <a className="btn" href={exportUrl.runs()} download><Download size={16} aria-hidden="true" />Export CSV</a>}>
          {!runs.length ? (
            <EmptyState title="No runs yet">{instance ? <Link className="underline" to="/run">Run an algorithm</Link> : <Link className="underline" to="/setup">Load an instance first</Link>}. Results appear here as they are produced.</EmptyState>
          ) : (
            <TableWrap>
              <thead><tr><th className="th">Started</th><th className="th">Algorithm</th><th className="th">Feasible</th><th className="th text-right">Distance ({instance?.distance_unit || 'km'})</th><th className="th text-right">Cost</th><th className="th text-right">Runtime (s)</th></tr></thead>
              <tbody>
                {runs.slice(0, 10).map((r) => (
                  <tr key={r.run_id}>
                    <td className="td">{fmtTime(r.created_at)}</td>
                    <td className="td"><AlgoTag algo={r.algorithm} /></td>
                    <td className="td">{r.state !== 'completed' ? <Badge kind="warn">{r.state}</Badge> : r.row?.feasible == null ? <Badge kind="bad">no solution</Badge> : r.row.feasible ? <Badge kind="ok">feasible</Badge> : <Badge kind="bad">infeasible</Badge>}</td>
                    <td className="td text-right num">{fmt(r.row?.total_distance)}</td>
                    <td className="td text-right num">{fmt(r.row?.estimated_cost)}</td>
                    <td className="td text-right num">{fmt(r.row?.runtime_seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
        </Panel>
      </div>
    </>
  )
}

import { useApp } from '../state/AppContext'
import { ALGOS } from '../lib/algos'
import { fmt, fmtTime } from '../lib/format'

// Lets the user choose which completed run of each algorithm is shown.
export default function RunPicker({ algos = ['ortools', 'ga'] }) {
  const { runs, selected, setSelected, instance } = useApp()
  const unit = instance?.distance_unit || 'km'
  return (
    <div className="flex flex-wrap gap-4">
      {algos.map((a) => {
        const list = runs.filter((r) => r.algorithm === a && r.state === 'completed')
        return (
          <label key={a} className="block min-w-[17rem]">
            <span className="label">{ALGOS[a].label} run</span>
            <select className="input" value={selected[a]} disabled={!list.length}
              onChange={(e) => setSelected((s) => ({ ...s, [a]: e.target.value }))}>
              {!list.length && <option value="">no completed runs</option>}
              {list.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {fmtTime(r.created_at)}{r.row?.seed != null ? ` · seed ${r.row.seed}` : ''} · {r.row?.feasible == null ? 'no solution' : `${fmt(r.row?.total_distance)} ${unit}`}
                </option>
              ))}
            </select>
          </label>
        )
      })}
    </div>
  )
}

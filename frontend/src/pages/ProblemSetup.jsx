import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { parseCustomersCsv } from '../lib/csv'
import { fmt } from '../lib/format'
import { useApp } from '../state/AppContext'
import { EmptyState, Field, Notice, NumberInput, PageHeader, Panel, Segmented, Spinner, Stats, TableWrap } from '../components/ui'
import RouteMap from '../components/RouteMap'

const DEFAULT_GEN = { n_customers: 25, seed: 1, metric: 'haversine', demand_min: 1, demand_max: 10, vehicle_capacity: '', vehicle_count: '', fixed_vehicle_cost: 50, cost_per_distance: 1 }
const MetricSelect = ({ id, value, onChange }) => (
  <select id={id} className="input" value={value} onChange={(e) => onChange(e.target.value)}>
    <option value="haversine">haversine (lat/lon)</option><option value="euclidean">euclidean (planar)</option>
  </select>
)

export default function ProblemSetup() {
  const { instances, instance, selectInstance, refreshInstances } = useApp()
  const [tab, setTab] = useState('generate')
  const [gen, setGen] = useState(DEFAULT_GEN)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [imp, setImp] = useState({ metric: 'haversine', depot_x: '', depot_y: '', vehicle_count: '', vehicle_capacity: '', fixed_vehicle_cost: 50, cost_per_distance: 1, name: '' })
  const [csvText, setCsvText] = useState('')
  const [csvErrors, setCsvErrors] = useState([])

  const set = (k) => (v) => setGen((g) => ({ ...g, [k]: v }))
  const setI = (k) => (v) => setImp((g) => ({ ...g, [k]: v }))

  async function submit(call) {
    setBusy(true); setError(null)
    try {
      const inst = await call()
      await refreshInstances()
      selectInstance(inst.instance_id)
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  const generate = (e) => {
    e.preventDefault()
    const body = { ...gen }
    for (const k of ['vehicle_capacity', 'vehicle_count']) if (body[k] === '') delete body[k]
    submit(() => api.generateInstance(body))
  }

  function loadFile(e) {
    const f = e.target.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => {
      const t = String(reader.result || '')
      setCsvText(t)
      const { depot, errors } = parseCustomersCsv(t)
      setCsvErrors(errors)
      if (depot) setImp((g) => ({ ...g, depot_x: depot.x, depot_y: depot.y }))
    }
    reader.readAsText(f)
  }

  const importInstance = (e) => {
    e.preventDefault()
    const { customers, depot, errors } = parseCustomersCsv(csvText)
    setCsvErrors(errors)
    if (errors.length) return
    const dx = imp.depot_x === '' ? depot?.x : imp.depot_x
    const dy = imp.depot_y === '' ? depot?.y : imp.depot_y
    if (dx == null || dy == null) { setError({ message: 'Provide the depot coordinates (or a row with id 0 in the CSV).', errors: [] }); return }
    submit(() => api.createInstance({ ...imp, depot_x: dx, depot_y: dy, customers, name: imp.name || 'imported-instance' }))
  }

  const totalDemand = instance ? instance.customers.reduce((s, c) => s + c.demand, 0) : 0
  const fleetCap = instance ? instance.vehicle_count * instance.vehicle_capacity : 0
  const unit = instance?.distance_unit || 'km'

  return (
    <>
      <PageHeader title="Problem setup">
        Define one routing instance. Both algorithms receive exactly this instance, including the same distance matrix.
      </PageHeader>

      {error && <div className="mb-5"><Notice kind="error" title={error.message} errors={error.errors} /></div>}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <Panel title="Create an instance">
          <div className="mb-5"><Segmented label="Source" value={tab} onChange={setTab} options={[['generate', 'Generate synthetic'], ['import', 'Import CSV']]} /></div>
          {tab === 'generate' ? (
            <form onSubmit={generate} className="grid gap-4 sm:grid-cols-2">
              <Field label="Customers" htmlFor="g-n"><NumberInput id="g-n" value={gen.n_customers} min={1} max={1000} onChange={set('n_customers')} /></Field>
              <Field label="Random seed" htmlFor="g-seed" hint="same settings + seed = same instance"><NumberInput id="g-seed" value={gen.seed} onChange={set('seed')} /></Field>
              <Field label="Distance metric" htmlFor="g-metric" hint={gen.metric === 'haversine' ? 'lon/lat, great-circle km' : 'planar, 100 × 100 km area'}>
                <MetricSelect id="g-metric" value={gen.metric} onChange={set('metric')} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Demand min" htmlFor="g-dmin"><NumberInput id="g-dmin" value={gen.demand_min} min={1} onChange={set('demand_min')} /></Field>
                <Field label="Demand max" htmlFor="g-dmax"><NumberInput id="g-dmax" value={gen.demand_max} min={1} onChange={set('demand_max')} /></Field>
              </div>
              <Field label="Vehicle capacity (units)" htmlFor="g-cap" hint="blank = about 10 average customers"><NumberInput id="g-cap" value={gen.vehicle_capacity} min={1} onChange={set('vehicle_capacity')} /></Field>
              <Field label="Vehicles" htmlFor="g-veh" hint="blank = needed + 25% + 1"><NumberInput id="g-veh" value={gen.vehicle_count} min={1} onChange={set('vehicle_count')} /></Field>
              <Field label="Fixed cost per used vehicle" htmlFor="g-fc" hint="synthetic cost units"><NumberInput id="g-fc" value={gen.fixed_vehicle_cost} min={0} step="any" onChange={set('fixed_vehicle_cost')} /></Field>
              <Field label="Cost per km" htmlFor="g-cpk" hint="synthetic cost units"><NumberInput id="g-cpk" value={gen.cost_per_distance} min={0} step="any" onChange={set('cost_per_distance')} /></Field>
              <div className="sm:col-span-2"><button className="btn btn-primary w-full sm:w-auto" disabled={busy}>{busy ? <Spinner label="Generating" /> : 'Generate and load'}</button></div>
            </form>
          ) : (
            <form onSubmit={importInstance} className="grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Field label="CSV file" htmlFor="i-file" hint="Columns id, x, y, demand (x = longitude, y = latitude for haversine). A row with id 0 is the depot. Header optional.">
                  <input id="i-file" type="file" accept=".csv,text/csv,text/plain" className="input" onChange={loadFile} />
                </Field>
              </div>
              <Field label="Distance metric" htmlFor="i-metric"><MetricSelect id="i-metric" value={imp.metric} onChange={setI('metric')} /></Field>
              <Field label="Instance name" htmlFor="i-name"><input id="i-name" className="input" value={imp.name} onChange={(e) => setI('name')(e.target.value)} /></Field>
              <Field label="Depot x" htmlFor="i-dx"><NumberInput id="i-dx" value={imp.depot_x} step="any" onChange={setI('depot_x')} /></Field>
              <Field label="Depot y" htmlFor="i-dy"><NumberInput id="i-dy" value={imp.depot_y} step="any" onChange={setI('depot_y')} /></Field>
              <Field label="Vehicles" htmlFor="i-veh"><NumberInput id="i-veh" value={imp.vehicle_count} min={1} onChange={setI('vehicle_count')} /></Field>
              <Field label="Vehicle capacity (units)" htmlFor="i-cap"><NumberInput id="i-cap" value={imp.vehicle_capacity} min={1} onChange={setI('vehicle_capacity')} /></Field>
              <Field label="Fixed cost per vehicle" htmlFor="i-fc"><NumberInput id="i-fc" value={imp.fixed_vehicle_cost} min={0} step="any" onChange={setI('fixed_vehicle_cost')} /></Field>
              <Field label="Cost per km" htmlFor="i-cpk"><NumberInput id="i-cpk" value={imp.cost_per_distance} min={0} step="any" onChange={setI('cost_per_distance')} /></Field>
              {csvErrors.length > 0 && <div className="sm:col-span-2"><Notice kind="error" title="CSV problems" errors={csvErrors} /></div>}
              <div className="sm:col-span-2"><button className="btn btn-primary w-full sm:w-auto" disabled={busy || !csvText}>Validate and load</button></div>
            </form>
          )}
        </Panel>

        <Panel title="Scenario"
          actions={instances.length > 0 && (
            <label className="flex items-center gap-2">
              <span className="label !mb-0">Saved instances</span>
              <select aria-label="Switch instance" className="input !w-auto max-w-[22rem]" value={instance?.instance_id || ''} onChange={(e) => selectInstance(e.target.value)}>
                <option value="">none</option>
                {instances.map((i) => <option key={i.instance_id} value={i.instance_id}>{i.name || i.instance_id} · {i.n_customers} customers</option>)}
              </select>
            </label>
          )}>
          {!instance ? (
            <EmptyState title="No instance loaded">Generate or import one. The backend validates it before it is saved.</EmptyState>
          ) : (
            <>
              <Stats items={[
                { label: 'Customers', value: instance.customers.length },
                { label: 'Total demand', value: totalDemand, sub: 'units' },
                { label: 'Fleet', value: `${instance.vehicle_count} × ${instance.vehicle_capacity}`, sub: `${instance.vehicle_count === 1 ? 'vehicle' : 'vehicles'} × capacity (units)` },
                { label: 'Capacity needed', value: `${fmt((totalDemand / fleetCap) * 100, 0)}%`, sub: `of ${fleetCap} units` },
              ]} />
              <div className="mt-4"><RouteMap instance={instance} routes={[]} height={430} /></div>
              <dl className="mt-4 grid gap-x-8 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
                <dt className="text-ink2">Instance ID</dt><dd><span className="font-mono text-[13px]">{instance.instance_id}</span> <span className="text-ink2">({instance.source}{instance.name ? `, ${instance.name}` : ''})</span></dd>
                <dt className="text-ink2">Distance</dt><dd>{instance.metric === 'haversine' ? 'great-circle (haversine)' : 'Euclidean'}, straight-line, in {unit}</dd>
                <dt className="text-ink2">Cost model</dt><dd>{instance.fixed_vehicle_cost} per used vehicle + {instance.cost_per_distance} per {unit} (synthetic units, not currency)</dd>
              </dl>
              <details className="mt-4">
                <summary className="cursor-pointer text-ink2 hover:text-ink">Customer table ({instance.customers.length})</summary>
                <div className="mt-2 max-h-72 overflow-y-auto">
                  <TableWrap>
                    <thead><tr><th className="th">ID</th><th className="th">x</th><th className="th">y</th><th className="th">Demand</th></tr></thead>
                    <tbody>{instance.customers.map((c) => <tr key={c.id}><td className="td">{c.id}</td><td className="td">{c.x}</td><td className="td">{c.y}</td><td className="td">{c.demand}</td></tr>)}</tbody>
                  </TableWrap>
                </div>
              </details>
              <p className="mt-5"><Link className="btn btn-primary" to="/run">Continue to run optimization</Link></p>
            </>
          )}
        </Panel>
      </div>
    </>
  )
}

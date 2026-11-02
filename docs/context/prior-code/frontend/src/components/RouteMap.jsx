import { useMemo } from 'react'
import L from 'leaflet'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { useEffect } from 'react'
import { ALGOS } from '../lib/algos'

// Haversine instances use lon/lat on OSM tiles; Euclidean ones use a plain planar canvas (no tiles).
const toLatLng = (inst, p) => [p.y, p.x]

function Fit({ points }) {
  const map = useMap()
  useEffect(() => {
    if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [24, 24] })
  }, [map, points])
  return null
}

export default function RouteMap({ instance, routes, algo, focus = null, height = 420, showLabels }) {
  const a = ALGOS[algo]
  const planar = instance.metric === 'euclidean'
  const byId = useMemo(() => Object.fromEntries(instance.customers.map((c) => [c.id, c])), [instance])
  const depot = { x: instance.depot.x, y: instance.depot.y }
  const stopInfo = useMemo(() => {
    const m = {}
    ;(routes || []).forEach((r, ri) => r.forEach((id, k) => { m[id] = { route: ri + 1, seq: k + 1 } }))
    return m
  }, [routes])
  const points = useMemo(() => [toLatLng(instance, depot), ...instance.customers.map((c) => toLatLng(instance, c))],
    [instance]) // eslint-disable-line react-hooks/exhaustive-deps
  const labels = showLabels ?? instance.customers.length <= 60
  const nonEmpty = (routes || []).map((r, i) => ({ r, i })).filter((x) => x.r.length)

  return (
    <div>
      <div style={{ height }} className="overflow-hidden rounded border border-rule" role="img"
        aria-label={`Map of ${nonEmpty.length} routes${a ? ` from ${a.label}` : ''}. A route table is available below.`}>
        <MapContainer crs={planar ? L.CRS.Simple : L.CRS.EPSG3857} minZoom={planar ? -6 : 2} zoomSnap={0.25}
          center={points[0]} zoom={planar ? 0 : 11} style={{ height: '100%', width: '100%' }} scrollWheelZoom>
          {!planar && <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />}
          <Fit points={points} />
          {a && nonEmpty.map(({ r, i }) => {
            const line = [toLatLng(instance, depot), ...r.map((id) => toLatLng(instance, byId[id])), toLatLng(instance, depot)]
            const dim = focus != null && focus !== i
            return (
              <Polyline key={i} positions={line}
                pathOptions={{ color: a.color, weight: dim ? 1.5 : focus === i ? 4.5 : 2.5, opacity: dim ? 0.25 : 0.95, dashArray: a.dash }}>
                <Tooltip sticky>Route {i + 1}: {r.length} stops</Tooltip>
              </Polyline>
            )
          })}
          {instance.customers.map((c) => {
            const info = stopInfo[c.id]
            const dim = focus != null && info && info.route - 1 !== focus
            return (
              <CircleMarker key={c.id} center={toLatLng(instance, c)} radius={6}
                pathOptions={{ color: '#1E2326', weight: 1, fillColor: info ? '#FFFFFF' : '#A33A2B', fillOpacity: dim ? 0.3 : 1, opacity: dim ? 0.3 : 1 }}>
                <Tooltip permanent={labels} direction="top" offset={[0, -4]} opacity={0.9}>
                  {labels ? c.id : `Customer ${c.id} · demand ${c.demand}${info ? ` · route ${info.route}, stop ${info.seq}` : ' · not served'}`}
                </Tooltip>
              </CircleMarker>
            )
          })}
          <CircleMarker center={toLatLng(instance, depot)} radius={9}
            pathOptions={{ color: '#1E2326', weight: 2, fillColor: '#1E2326', fillOpacity: 1 }}>
            <Tooltip permanent direction="right">Depot</Tooltip>
          </CircleMarker>
        </MapContainer>
      </div>
      <p className="mt-2 text-xs text-ink2">
        {planar
          ? 'Planar coordinates; segments are straight lines (Euclidean distance).'
          : 'Segments are straight lines between stops (great-circle distance), not road routes.'}
        {a && <> {a.label}: {a.dashLabel}.</>} Filled-white dot = served customer, red = unserved, black = depot.
      </p>
    </div>
  )
}

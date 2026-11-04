import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Notice, Panel, TableWrap } from './ui'

const REASON = {
  not_home: 'nobody home', refused: 'refused', wrong_address: 'wrong address', access_problem: 'no access',
  damaged: 'damaged', other: 'other',
}
const when = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : '—')

// Dispatcher view of P9: make a signed link per route for the driver app, revoke it, and see drivers' reports.
// Shown only for completed, feasible plans (the backend refuses links for anything else).
export default function DriverLinks({ plan, routes }) {
  const [links, setLinks] = useState([])
  const [reports, setReports] = useState({ events: [], photos: [] })
  const [fresh, setFresh] = useState(null) // the link just made: its URL is shown once
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(() => {
    api.listDriverLinks(plan.plan_id).then((l) => setLinks(Array.isArray(l) ? l : [])).catch(setError)
    api.stopReports(plan.plan_id).then((r) => setReports({ events: r?.events || [], photos: r?.photos || [] }))
      .catch(setError)
  }, [plan.plan_id])
  useEffect(() => { refresh() }, [refresh])

  async function create(routeIndex) {
    setBusy(true); setError(null)
    try { setFresh(await api.createDriverLink(plan.plan_id, { route_index: routeIndex })); refresh() } catch (e) { setError(e) } finally { setBusy(false) }
  }
  async function revoke(linkId) {
    setBusy(true); setError(null)
    try { await api.revokeDriverLink(linkId); if (fresh?.link_id === linkId) setFresh(null); refresh() } catch (e) { setError(e) } finally { setBusy(false) }
  }

  const latest = {}
  reports.events.forEach((e) => { latest[e.customer_id] = e })
  const photos = {}
  reports.photos.forEach((p) => { photos[p.customer_id] = (photos[p.customer_id] || 0) + 1 })
  return (
    <Panel title="Drivers" note="One signed link per route, valid 12 hours; reports do not change the plan">
      {error && <div className="mb-3"><Notice kind="error" title="Request failed">{error.message}</Notice></div>}
      {fresh && (
        <div className="mb-4 rounded-md border border-accent/30 bg-accent-soft p-3">
          <p className="text-xs font-medium">Link for route {fresh.route_index}, valid until {when(fresh.expires_at)}. Send it to the driver; it is shown only now.</p>
          <input readOnly aria-label="Driver link" className="input mt-2 font-mono text-xs" value={fresh.url} onFocus={(e) => e.target.select()} />
        </div>
      )}
      <TableWrap>
        <thead><tr className="text-left"><th>Route</th><th>Stops done</th><th>Links</th><th /></tr></thead>
        <tbody>{routes.map((r, i) => {
          if (!r.length) return null
          const doneCount = r.filter((cid) => latest[cid]).length
          const active = links.filter((l) => l.route_index === i && !l.revoked_at)
          return (
            <tr key={i} className="border-t border-rule">
              <td className="num py-1">{i}</td>
              <td className="num">{doneCount} of {r.length}</td>
              <td className="text-xs">{active.length ? active.map((l) => (
                <span key={l.link_id} className="mr-2">until {when(l.expires_at)} <button type="button" className="underline" disabled={busy}
                  onClick={() => revoke(l.link_id)} aria-label={`Revoke link for route ${i}`}>revoke</button></span>)) : 'none'}</td>
              <td className="text-right"><button type="button" className="btn" disabled={busy} onClick={() => create(i)}>Driver link for route {i}</button></td>
            </tr>
          )
        })}</tbody>
      </TableWrap>
      {reports.events.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2">Stop reports</h3>
          <TableWrap>
            <thead><tr className="text-left"><th>Customer</th><th>Route</th><th>Status</th><th>Reported</th><th>Photos</th></tr></thead>
            <tbody>{Object.values(latest).map((e) => (
              <tr key={e.customer_id} className="border-t border-rule">
                <td className="num py-1">{e.customer_id}</td><td className="num">{e.route_index}</td>
                <td>{e.status === 'failed' ? `failed (${REASON[e.reason] || e.reason}${e.note ? `: ${e.note}` : ''})` : e.status}</td>
                <td className="text-xs">{when(e.received_at)}</td><td className="num">{photos[e.customer_id] || 0}</td>
              </tr>))}</tbody>
          </TableWrap>
          <p className="mt-2 text-xs text-ink2">A failed stop is not replanned automatically; use the replan form below if needed.</p>
        </div>
      )}
    </Panel>
  )
}

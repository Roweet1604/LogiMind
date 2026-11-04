import { useCallback, useEffect, useRef, useState } from 'react'
import { getRoute, postPhoto } from './lib/api'
import { shrinkImage } from './lib/photo'
import { navUrl } from './lib/nav'
import { loadQueue, loadRoute, saveQueue, saveRoute, takeTokenFromLocation } from './lib/store'
import { flushQueue, makeReport, withQueued } from './lib/sync'

export const REASONS = {
  not_home: 'Nobody home', refused: 'Refused', wrong_address: 'Wrong address',
  access_problem: "Can't get access", damaged: 'Damaged', other: 'Other (add a note)',
}
export const RETRY_MS = 20000
const STATUS = {
  pending: ['bg-rule2 text-ink2', 'To do'], delivered: ['bg-ok-soft text-ok', 'Delivered'],
  failed: ['bg-err-soft text-err', 'Failed'],
}

const clock = (iso) => {
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) } catch { return iso }
}
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

function Screen({ title, children }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-3 p-6">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {children}
    </main>
  )
}

function Banner({ kind = 'warn', children }) {
  const cls = { warn: 'border-warn/30 bg-warn-soft text-warn', err: 'border-err/30 bg-err-soft text-err',
    info: 'border-accent/30 bg-accent-soft text-accent-dark' }[kind]
  return <div role="status" className={`rounded-md border px-4 py-3 text-base ${cls}`}>{children}</div>
}

function FailForm({ onSubmit, onCancel }) {
  const [reason, setReason] = useState(null)
  const [note, setNote] = useState('')
  const needsNote = reason === 'other' && !note.trim()
  return (
    <fieldset className="mt-3 rounded-md border border-rule bg-paper p-3">
      <legend className="px-1 text-base font-medium">Why did it fail?</legend>
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(REASONS).map(([k, label]) => (
          <button key={k} type="button" aria-pressed={reason === k} onClick={() => setReason(k)}
            className={`tap border ${reason === k ? 'border-err bg-err-soft text-err' : 'border-rule bg-white'}`}>{label}</button>
        ))}
      </div>
      {reason === 'other' && (
        <label className="mt-3 block text-base">Note
          <textarea className="mt-1 w-full rounded-md border border-rule bg-white p-3 text-base" rows={2} maxLength={500}
            value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button type="button" className="tap border border-rule bg-white" onClick={onCancel}>Back</button>
        <button type="button" className="tap bg-err text-white disabled:opacity-40" disabled={!reason || needsNote}
          onClick={() => onSubmit(reason, note)}>Report failed</button>
      </div>
    </fieldset>
  )
}

function StopCard({ stop, next, online, timeUnit, onReport, onPhoto, photoState }) {
  const [failing, setFailing] = useState(false)
  const [cls, label] = STATUS[stop.status] || STATUS.pending
  const url = navUrl(stop)
  const done = stop.status !== 'pending'
  return (
    <li className={`rounded-lg border bg-panel p-4 ${next ? 'border-accent ring-2 ring-accent/30' : 'border-rule'}`}
      aria-label={`Stop ${stop.seq}, customer ${stop.customer_id}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-ink2">Stop {stop.seq}{next && <span className="ml-2 font-medium text-accent">Next</span>}</p>
          <p className="text-xl font-semibold">Customer {stop.customer_id}</p>
          <p className="text-base text-ink2">
            {plural(stop.demand, 'unit')}
            {stop.due_time != null && <> · window {stop.ready_time}–{stop.due_time} {timeUnit}</>}
          </p>
        </div>
        <span className={`shrink-0 rounded-full px-3 py-1 text-sm font-medium ${cls}`}>
          {label}{stop.queued && ' · waiting to sync'}
        </span>
      </div>
      {stop.status === 'failed' && stop.reason && <p className="mt-1 text-base text-err">{REASONS[stop.reason] || stop.reason}</p>}
      <div className="mt-3 grid grid-cols-3 gap-2">
        {url
          ? <a className="tap border border-rule bg-white" href={url} target="_blank" rel="noopener noreferrer">Navigate</a>
          : <span className="tap border border-rule2 bg-rule2 text-sm text-ink2" title="This plan has no map coordinates">No map</span>}
        <button type="button" className={`tap ${done ? 'border border-rule bg-white' : 'bg-ok text-white'}`}
          onClick={() => { setFailing(false); onReport(stop.customer_id, 'delivered') }}>Delivered</button>
        <button type="button" className="tap border border-err/40 bg-white text-err" onClick={() => setFailing(true)}>Failed</button>
      </div>
      {failing && <FailForm onCancel={() => setFailing(false)}
        onSubmit={(reason, note) => { setFailing(false); onReport(stop.customer_id, 'failed', reason, note) }} />}
      <div className="mt-3">
        <label className={`tap w-full border border-rule ${online ? 'cursor-pointer bg-white' : 'bg-rule2 text-ink2'}`}>
          {stop.photos > 0 ? `Add another photo (${stop.photos} saved)` : 'Add proof-of-delivery photo'}
          <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="sr-only"
            disabled={!online || photoState === 'uploading'} aria-label={`Photo for customer ${stop.customer_id}`}
            onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onPhoto(stop.customer_id, f) }} />
        </label>
        {!online && <p className="mt-1 text-sm text-ink2">Photos need a connection; reports are saved offline.</p>}
        {photoState && photoState !== 'uploading' && <p className="mt-1 text-sm" role="status">{photoState}</p>}
        {photoState === 'uploading' && <p className="mt-1 text-sm text-ink2" role="status">Uploading photo…</p>}
      </div>
    </li>
  )
}

export default function App() {
  const [token] = useState(() => takeTokenFromLocation())
  const [route, setRoute] = useState(null)
  const [source, setSource] = useState(null) // 'live' | 'cache'
  const [savedAt, setSavedAt] = useState(null)
  const [fatal, setFatal] = useState(null) // 'expired' | 'unavailable'
  const [queue, setQueueState] = useState(() => (token ? loadQueue(token) : []))
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine !== false))
  const [syncNote, setSyncNote] = useState(null)
  const [photo, setPhoto] = useState({})
  const queueRef = useRef(queue)
  const syncing = useRef(false)

  const setQueue = useCallback((q) => { queueRef.current = q; setQueueState(q); saveQueue(token, q) }, [token])

  const load = useCallback(async () => {
    try {
      const r = await getRoute(token)
      setRoute(r); setSource('live'); setFatal(null); setOnline(true)
      saveRoute(token, r)
    } catch (err) {
      if (err.status === 401) { setFatal('expired'); return }
      if (err.status === 0) setOnline(false)
      const cached = loadRoute(token)
      if (cached) { setRoute(cached.route); setSavedAt(cached.savedAt); setSource('cache') } else setFatal('unavailable')
    }
  }, [token])

  const sync = useCallback(async () => {
    if (syncing.current || !queueRef.current.length) return
    syncing.current = true
    try {
      const res = await flushQueue(token, queueRef.current)
      if (res.synced.length || res.rejected.length) setOnline(true)
      // reports made while this flush ran stay queued behind the unsent ones
      const sent = new Set([...res.synced, ...res.rejected.map((r) => r.item)])
      setQueue(queueRef.current.filter((q) => !sent.has(q)))
      if (res.rejected.length) {
        setSyncNote(`${plural(res.rejected.length, 'report')} could not be saved: ${res.rejected.map((r) => r.error).join('; ')}`)
      }
      if (res.synced.length) await load()
    } finally { syncing.current = false }
  }, [token, load, setQueue])

  useEffect(() => { if (token) load().then(sync) }, [token, load, sync])
  // The phone can have a network while the server is unreachable (no "online" event follows), so queued
  // reports are also retried every 20 s until they are sent.
  useEffect(() => {
    if (!queue.length) return undefined
    const timer = setInterval(() => { sync() }, RETRY_MS)
    return () => clearInterval(timer)
  }, [queue.length, sync])
  useEffect(() => {
    const up = () => { setOnline(true); sync().then(load) }
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => { window.removeEventListener('online', up); window.removeEventListener('offline', down) }
  }, [sync, load])

  const report = (customerId, status, reason, note) => {
    setSyncNote(null)
    setQueue([...queueRef.current, makeReport(customerId, status, reason, note)])
    sync()
  }

  const upload = async (customerId, file) => {
    setPhoto((p) => ({ ...p, [customerId]: 'uploading' }))
    try {
      await postPhoto(token, customerId, await shrinkImage(file))
      setPhoto((p) => ({ ...p, [customerId]: 'Photo saved.' }))
      load()
    } catch (err) {
      const msg = err.status === 0 ? 'No connection: photo not sent. Try again when online.' : `Photo not saved: ${err.message}`
      setPhoto((p) => ({ ...p, [customerId]: msg }))
    }
  }

  if (!token) {
    return <Screen title="LogiMind Driver"><p className="text-lg">Open the link your dispatcher sent you to see your stops.</p></Screen>
  }
  if (fatal === 'expired') {
    return (
      <Screen title="Link no longer valid">
        <p className="text-lg">This driver link has expired or was revoked. Ask your dispatcher for a new link.</p>
        {queue.length > 0 && <Banner kind="err">{plural(queue.length, 'report')} on this phone {queue.length === 1 ? 'was' : 'were'} not sent. Tell your dispatcher which stops you completed.</Banner>}
      </Screen>
    )
  }
  if (fatal === 'unavailable') {
    return (
      <Screen title="Stops not available">
        <p className="text-lg">No connection, and no saved copy of the stop list on this phone yet.</p>
        <button type="button" className="tap bg-accent text-white" onClick={load}>Try again</button>
      </Screen>
    )
  }
  if (!route) return <Screen title="Loading your stops…" />

  const stops = withQueued(route.stops, queue)
  const done = stops.filter((s) => s.status !== 'pending').length
  const nextSeq = stops.find((s) => s.status === 'pending')?.seq
  return (
    <main className="mx-auto max-w-xl pb-10">
      <header className="sticky top-0 z-10 border-b border-rule bg-panel px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-sm text-ink2">{route.company}</p>
            <h1 className="text-xl font-semibold">Route {route.route_index + 1}{route.plan_name && <span className="font-normal text-ink2"> · {route.plan_name}</span>}</h1>
          </div>
          <span className={`rounded-full px-3 py-1 text-sm font-medium ${online ? 'bg-ok-soft text-ok' : 'bg-warn-soft text-warn'}`}>{online ? 'Online' : 'Offline'}</span>
        </div>
        <p className="mt-1 text-base" aria-live="polite">{done} of {stops.length} stops done · link valid until {clock(route.expires_at)}</p>
        {queue.length > 0 && (
          <div className="mt-2 flex items-center justify-between gap-2">
            <p className="text-base text-warn">{plural(queue.length, 'update')} waiting to sync</p>
            <button type="button" className="tap border border-rule bg-white px-4" onClick={() => sync()}>Sync now</button>
          </div>
        )}
      </header>
      <div className="space-y-3 px-4 pt-3">
        {source === 'cache' && <Banner>Offline copy saved at {clock(savedAt)}. Reports are kept on this phone and sent when you are back online.</Banner>}
        {route.superseded_by && <Banner kind="err">This route was replanned. Ask your dispatcher for the new link.</Banner>}
        {syncNote && <Banner kind="err">{syncNote}</Banner>}
        <ol className="space-y-3">
          {stops.map((s) => (
            <StopCard key={s.customer_id} stop={s} next={s.seq === nextSeq} online={online} timeUnit={route.time_unit}
              onReport={report} onPhoto={upload} photoState={photo[s.customer_id]} />
          ))}
        </ol>
      </div>
    </main>
  )
}

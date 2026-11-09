import { useCallback, useEffect, useRef, useState } from 'react'
import { getRoute, postPhoto } from './lib/api'
import { shrinkImage } from './lib/photo'
import { navUrl } from './lib/nav'
import { loadQueue, loadRoute, saveQueue, saveRoute, takeTokenFromLocation } from './lib/store'
import { flushQueue, makeReport, withQueued } from './lib/sync'
import { AlertIcon, CameraIcon, CheckIcon, ClockIcon, CloudIcon, CloudOffIcon, CrossIcon, NavigateIcon, SyncIcon } from './icons'

export const REASONS = {
  not_home: 'Nobody home', refused: 'Refused', wrong_address: 'Wrong address',
  access_problem: "Can't get access", damaged: 'Damaged', other: 'Other (add a note)',
}
export const RETRY_MS = 20000
// Stop status: colour + icon + word, never colour alone.
const STATUS = {
  pending: ['border-ink/20 bg-rule2 text-ink', 'To do', null], delivered: ['border-ok/40 bg-ok-soft text-ok', 'Delivered', CheckIcon],
  failed: ['border-err/40 bg-err-soft text-err', 'Failed', CrossIcon],
}

const clock = (iso) => {
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) } catch { return iso }
}
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

function Screen({ title, children }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-4 p-6">
      <p className="text-base font-semibold text-accent">LogiMind Driver</p>
      <h1 className="text-3xl font-bold">{title}</h1>
      {children}
    </main>
  )
}

function Banner({ kind = 'warn', children }) {
  const [cls, Icon] = {
    warn: ['border-warn/40 bg-warn-soft text-warn', ClockIcon], err: ['border-err/40 bg-err-soft text-err', AlertIcon],
    info: ['border-accent/40 bg-accent-soft text-accent-dark', null],
  }[kind]
  return (
    <div role="status" className={`flex items-start gap-3 rounded-md border-2 px-4 py-3 text-lg font-medium ${cls}`}>
      {Icon && <span className="mt-0.5"><Icon /></span>}<div>{children}</div>
    </div>
  )
}

function FailForm({ onSubmit, onCancel }) {
  const [reason, setReason] = useState(null)
  const [note, setNote] = useState('')
  const needsNote = reason === 'other' && !note.trim()
  return (
    <fieldset className="mt-4 rounded-md border-2 border-err/40 bg-paper p-3">
      <legend className="px-1 text-lg font-semibold">Why did it fail?</legend>
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(REASONS).map(([k, label]) => (
          <button key={k} type="button" aria-pressed={reason === k} onClick={() => setReason(k)}
            className={`tap border-2 text-base ${reason === k ? 'border-err bg-err text-white' : 'border-ink/25 bg-panel'}`}>
            {reason === k && <CheckIcon size={18} />}{label}
          </button>
        ))}
      </div>
      {reason === 'other' && (
        <label className="mt-3 block text-lg font-medium">Note
          <textarea className="mt-1 w-full rounded-md border-2 border-ink/25 bg-panel p-3 text-lg" rows={2} maxLength={500}
            value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button type="button" className="tap tap-secondary" onClick={onCancel}>Back</button>
        <button type="button" className="tap bg-err text-white disabled:opacity-40" disabled={!reason || needsNote}
          onClick={() => onSubmit(reason, note)}>Report failed</button>
      </div>
    </fieldset>
  )
}

function StopCard({ stop, next, online, timeUnit, onReport, onPhoto, photoState }) {
  const [failing, setFailing] = useState(false)
  const [cls, label, Icon] = STATUS[stop.status] || STATUS.pending
  const url = navUrl(stop)
  const done = stop.status !== 'pending'
  return (
    <li className={`rounded-lg border-2 bg-panel p-4 ${next ? 'border-accent shadow-[0_0_0_2px_theme(colors.accent.soft)]' : 'border-rule'}`}
      aria-label={`Stop ${stop.seq}, customer ${stop.customer_id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="whitespace-nowrap text-base font-medium text-ink2">
          Stop {stop.seq}{next && <span className="ml-2 rounded bg-accent px-2 py-0.5 text-sm font-bold uppercase tracking-wide text-white">Next</span>}
        </p>
        <span className={`inline-flex items-center gap-1 rounded-md border-2 px-2.5 py-0.5 text-base font-semibold ${cls}`}>
          {Icon && <Icon size={18} />}{label}{stop.queued && ' · waiting to sync'}
        </span>
      </div>
      <p className={`mt-1 ${next ? 'text-3xl' : 'text-2xl'} font-bold leading-tight`}>Customer {stop.customer_id}</p>
      <p className="mt-0.5 text-lg text-ink2">
        {plural(stop.demand, 'unit')}
        {stop.due_time != null && <> · window {stop.ready_time}–{stop.due_time} {timeUnit}</>}
      </p>
      {stop.status === 'failed' && stop.reason && <p className="mt-1 text-lg font-medium text-err">{REASONS[stop.reason] || stop.reason}</p>}
      <div className="mt-4 space-y-2">
        {url
          ? <a className={`tap w-full ${next ? 'tap-lg bg-accent text-white active:bg-accent-dark' : 'tap-secondary'}`} href={url} target="_blank" rel="noopener noreferrer"><NavigateIcon />Navigate</a>
          : <span className="tap w-full border-2 border-dashed border-ink/20 bg-rule2 text-base text-ink2" title="This plan has no map coordinates">No map</span>}
        <div className="grid grid-cols-2 gap-2">
          <button type="button" className={`tap ${next ? 'tap-lg' : ''} ${done ? 'tap-secondary' : 'bg-ok text-white active:brightness-90'}`}
            onClick={() => { setFailing(false); onReport(stop.customer_id, 'delivered') }}><CheckIcon />Delivered</button>
          <button type="button" className={`tap ${next ? 'tap-lg' : ''} border-2 border-err bg-panel text-err active:bg-err-soft`} onClick={() => setFailing(true)}><CrossIcon />Failed</button>
        </div>
      </div>
      {failing && <FailForm onCancel={() => setFailing(false)}
        onSubmit={(reason, note) => { setFailing(false); onReport(stop.customer_id, 'failed', reason, note) }} />}
      <div className="mt-2">
        <label className={`tap w-full border-2 text-base ${online ? 'cursor-pointer border-ink/25 bg-panel' : 'border-dashed border-ink/20 bg-rule2 text-ink2'}`}>
          <CameraIcon size={20} />
          {stop.photos > 0 ? `Add another photo (${stop.photos} saved)` : 'Add proof-of-delivery photo'}
          <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="sr-only"
            disabled={!online || photoState === 'uploading'} aria-label={`Photo for customer ${stop.customer_id}`}
            onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onPhoto(stop.customer_id, f) }} />
        </label>
        {!online && <p className="mt-1 text-base text-ink2">Photos need a connection; reports are saved offline.</p>}
        {photoState && photoState !== 'uploading' && <p className="mt-1 text-base font-medium" role="status">{photoState}</p>}
        {photoState === 'uploading' && <p className="mt-1 text-base text-ink2" role="status">Uploading photo…</p>}
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
    return <Screen title="Open your route link"><p className="text-xl">Open the link your dispatcher sent you to see your stops.</p></Screen>
  }
  if (fatal === 'expired') {
    return (
      <Screen title="Link no longer valid">
        <p className="text-xl">This driver link has expired or was revoked. Ask your dispatcher for a new link.</p>
        {queue.length > 0 && <Banner kind="err">{plural(queue.length, 'report')} on this phone {queue.length === 1 ? 'was' : 'were'} not sent. Tell your dispatcher which stops you completed.</Banner>}
      </Screen>
    )
  }
  if (fatal === 'unavailable') {
    return (
      <Screen title="Stops not available">
        <p className="text-xl">No connection, and no saved copy of the stop list on this phone yet.</p>
        <button type="button" className="tap tap-lg bg-accent text-white" onClick={load}><SyncIcon />Try again</button>
      </Screen>
    )
  }
  if (!route) return <Screen title="Loading your stops…" />

  const stops = withQueued(route.stops, queue)
  const done = stops.filter((s) => s.status !== 'pending').length
  const nextSeq = stops.find((s) => s.status === 'pending')?.seq
  // Display only: the phone can be online while the server is not answering (then the saved copy is shown).
  const connected = online && source !== 'cache'
  const connection = !online ? 'Offline' : source === 'cache' ? 'Server unreachable' : 'Online'
  return (
    <main className="mx-auto max-w-xl pb-10">
      <div className="sticky top-0 z-10">
      <header className="bg-nav px-4 pb-3 pt-3 text-white">
        <div className="flex items-center justify-between gap-3">
          <p className="min-w-0 truncate text-base text-nav-text">{route.company}</p>
          <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-md border-2 px-3 py-1 text-lg font-bold ${connected ? 'border-ok bg-ok-soft text-ok' : 'border-warn bg-warn-soft text-warn'}`}>
            {connected ? <CloudIcon size={20} /> : <CloudOffIcon size={20} />}{connection}
          </span>
        </div>
        <h1 className="mt-1 truncate text-2xl font-bold">Route {route.route_index + 1}{route.plan_name && <span className="text-lg font-normal text-nav-text"> · {route.plan_name}</span>}</h1>
        <p className="mt-2 text-lg" aria-live="polite">{done} of {stops.length} stops done · link valid until {clock(route.expires_at)}</p>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/15" aria-hidden="true">
          <div className="h-full rounded-full bg-accent-soft" style={{ width: `${stops.length ? (100 * done) / stops.length : 0}%` }} />
        </div>
      </header>
      {queue.length > 0 && (
        <div className="flex items-center justify-between gap-3 border-b-2 border-warn/40 bg-warn-soft px-4 py-2">
          <p className="flex items-center gap-2 text-lg font-semibold text-warn"><ClockIcon />{plural(queue.length, 'update')} waiting to sync</p>
          <button type="button" className="tap tap-secondary shrink-0 px-4" onClick={() => sync()}><SyncIcon size={20} />Sync now</button>
        </div>
      )}
      </div>
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

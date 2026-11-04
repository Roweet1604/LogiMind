// Offline queue for delivered/failed reports. Each report carries a client_event_id made when the driver
// tapped the button, so sending it twice is safe (the server answers the second time with the stored report).
import { postStatus } from './api'

export function newEventId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `e${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`
}

export function makeReport(customerId, status, reason = null, note = '') {
  return {
    customerId,
    body: { status, reason: status === 'failed' ? reason : null, note, client_event_id: newEventId(),
      occurred_at: new Date().toISOString() },
  }
}

// Send queued reports in order. Stops at the first one that cannot be sent now (no connection, link expired,
// rate limit, server error) and keeps it and everything after it. A report the server rejects for good
// (invalid, not on this route, conflict) is dropped and returned in `rejected`, so the driver is told.
export async function flushQueue(token, queue, send = postStatus) {
  const synced = []
  const rejected = []
  let i = 0
  for (; i < queue.length; i++) {
    const item = queue[i]
    try {
      await send(token, item.customerId, item.body)
      synced.push(item)
    } catch (err) {
      const s = err.status ?? 0
      if (s === 0 || s === 401 || s === 408 || s === 429 || s >= 500) break
      rejected.push({ item, error: err.message })
    }
  }
  return { remaining: queue.slice(i), synced, rejected, stoppedBy: i < queue.length ? 'unsent' : null }
}

// The status a stop should show: the newest queued report wins over the last one the server knows.
export function withQueued(stops, queue) {
  const last = {}
  queue.forEach((q) => { last[q.customerId] = q })
  return stops.map((s) => (last[s.customer_id]
    ? { ...s, status: last[s.customer_id].body.status, reason: last[s.customer_id].body.reason, queued: true }
    : { ...s, queued: false }))
}

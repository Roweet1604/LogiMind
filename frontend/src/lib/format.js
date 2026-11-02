// Null / NaN means "not available" and is shown as an em dash, never as 0.
export const isNum = (v) => typeof v === 'number' && Number.isFinite(v)

export function fmt(v, digits = 2) {
  return isNum(v) ? v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits }) : '—'
}

export function fmtInt(v) {
  return isNum(v) ? String(Math.round(v)) : '—'
}

export function fmtSeconds(v) {
  return isNum(v) ? `${v.toFixed(v < 10 ? 2 : 1)} s` : '—'
}

export function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('en-GB', { hour12: false, dateStyle: 'short', timeStyle: 'medium' })
}

export const SOLVER_STATUS_TEXT = {
  solved: 'Returned a solution',
  no_solution: 'No solution found',
  timeout_no_solution: 'Time limit reached before any solution',
  hard_timeout: 'Stopped: overran its time limit (no plan)',
  invalid_input: 'Rejected input',
  error: 'Solver error',
}

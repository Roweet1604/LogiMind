import { AlertTriangle, CheckCircle2, Clock, GitBranch, Info, Loader2, PencilLine, XCircle } from 'lucide-react'
import { ALGOS } from '../lib/algos'

export function PageHeader({ title, children, actions }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 max-w-3xl">
        <h1>{title}</h1>
        {children && <p className="mt-1 text-sm text-ink2">{children}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  )
}

// A working surface. Used for forms, maps and tables; plain text sections do not need one.
export function Panel({ title, note, actions, children, className = '' }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex flex-wrap items-baseline gap-x-3">
            {title && <h2>{title}</h2>}
            {note && <span className="text-xs text-ink2">{note}</span>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}

export function Section({ title, note, children, className = '' }) {
  return (
    <section className={`mb-8 ${className}`}>
      {title && (
        <div className="mb-3 flex flex-wrap items-baseline gap-x-3">
          <h2>{title}</h2>
          {note && <span className="text-xs text-ink2">{note}</span>}
        </div>
      )}
      {children}
    </section>
  )
}

// Aligned data row: hairline-separated cells in one block, not a grid of separate cards.
export function Stats({ items, cols = 4 }) {
  return (
    <dl className={`grid grid-cols-2 gap-px overflow-hidden rounded-md border border-rule bg-rule ${cols === 4 ? 'lg:grid-cols-4' : ''}`}>
      {items.map((s) => (
        <div key={s.label} className="bg-panel px-4 py-3">
          <dt className="text-xs text-ink2">{s.label}</dt>
          <dd className="num mt-0.5 text-lg font-semibold leading-tight">{s.value}</dd>
          {s.sub && <dd className="text-xs text-ink2">{s.sub}</dd>}
        </div>
      ))}
    </dl>
  )
}

export function Segmented({ value, onChange, options, label }) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex rounded-md border border-rule bg-paper p-1">
      {options.map(([k, text]) => (
        <button key={k} role="tab" aria-selected={value === k} onClick={() => onChange(k)} type="button"
          className={`rounded px-4 py-1.5 text-sm font-medium ${value === k ? 'bg-white text-ink shadow-panel' : 'text-ink2 hover:text-ink'}`}>{text}</button>
      ))}
    </div>
  )
}

// Notices carry an icon and a title, so the meaning never depends on the colour alone.
const NOTICE = {
  info: { icon: Info, cls: 'border-rule bg-sunken', iconCls: 'text-ink2' },
  warn: { icon: AlertTriangle, cls: 'border-warn/40 bg-warn-soft', iconCls: 'text-warn' },
  error: { icon: XCircle, cls: 'border-err/40 bg-err-soft', iconCls: 'text-err' },
  ok: { icon: CheckCircle2, cls: 'border-ok/40 bg-ok-soft', iconCls: 'text-ok' },
}

export function Notice({ kind = 'info', title, children, errors, icon }) {
  const { icon: DefaultIcon, cls, iconCls } = NOTICE[kind]
  const Icon = icon || DefaultIcon
  return (
    <div role={kind === 'error' ? 'alert' : 'status'} className={`flex gap-3 rounded-md border px-4 py-3 ${cls}`}>
      <Icon size={18} className={`mt-0.5 shrink-0 ${iconCls}`} aria-hidden="true" />
      <div className="min-w-0">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className="text-sm">{children}</div>}
        {errors?.length > 0 && <ul className="mt-1 list-disc pl-4 text-sm">{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>}
      </div>
    </div>
  )
}

export function Spinner({ label = 'Loading' }) {
  return (
    <span className="inline-flex items-center gap-2" role="status">
      <Loader2 size={16} className="animate-spin" aria-hidden="true" />{label}
    </span>
  )
}

export function Field({ label, hint, children, htmlFor }) {
  return (
    <label className="block" htmlFor={htmlFor}>
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink2">{hint}</span>}
    </label>
  )
}

export function NumberInput({ id, value, onChange, min, max, step = 1, ...rest }) {
  return (
    <input id={id} className="input num" type="number" value={value} min={min} max={max} step={step}
      onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))} {...rest} />
  )
}

export function AlgoTag({ algo }) {
  const a = ALGOS[algo]
  if (!a) return <span>{algo}</span>
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <svg width="24" height="8" aria-hidden="true">
        <line x1="1" y1="4" x2="23" y2="4" stroke={a.color} strokeWidth="3" strokeDasharray={a.dash} />
      </svg>
      <span className={`font-semibold ${a.textClass}`}>{a.label}</span>
    </span>
  )
}

// Status badges: colour + icon + word. Kinds: ok (validated/feasible), bad (infeasible/failed), warn (warning,
// e.g. fallback distances), timeout, busy (queued/running), replanned, draft (draft/synthetic/preliminary), neutral.
const BADGE = {
  ok: ['border-ok/30 bg-ok-soft text-ok', CheckCircle2],
  bad: ['border-err/30 bg-err-soft text-err', XCircle],
  warn: ['border-warn/30 bg-warn-soft text-warn', AlertTriangle],
  timeout: ['border-warn/30 bg-warn-soft text-warn', Clock],
  busy: ['border-rule bg-rule2 text-ink', Loader2],
  replanned: ['border-hybrid/30 bg-hybrid-soft text-hybrid', GitBranch],
  draft: ['border-dashed border-draft/60 bg-draft-soft text-draft', PencilLine],
  neutral: ['border-rule bg-rule2 text-ink2', null],
}
export function Badge({ kind = 'neutral', children, icon, size = 'sm' }) {
  const [cls, DefaultIcon] = BADGE[kind] || BADGE.neutral
  const Icon = icon === undefined ? DefaultIcon : icon
  const big = size === 'lg'
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded border font-medium ${big ? 'px-2.5 py-1 text-sm' : 'px-1.5 py-0.5 text-xs'} ${cls}`}>
      {Icon && <Icon size={big ? 16 : 13} aria-hidden="true" className={kind === 'busy' && Icon === Loader2 ? 'motion-safe:animate-spin' : ''} />}
      {children}
    </span>
  )
}

// Feasibility is decided only by the independent validator, never by the solver status.
export function FeasibilityBadge({ run }) {
  if (!run) return <Badge>no run</Badge>
  if (run.state === 'queued' || run.state === 'running') return <Badge kind="busy">{run.state}</Badge>
  if (run.state === 'failed') return <Badge kind="bad">run failed</Badge>
  const v = run.validation
  if (!v) return <Badge kind="bad">no solution</Badge>
  return v.feasible ? <Badge kind="ok">feasible</Badge> : <Badge kind="bad">infeasible</Badge>
}

export function EmptyState({ title, children }) {
  return (
    <div className="rounded-md border border-dashed border-rule bg-sunken px-6 py-10 text-center">
      <p className="text-base font-medium">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-md text-ink2">{children}</div>}
    </div>
  )
}

export function TableWrap({ children }) {
  return <div className="overflow-x-auto"><table className="tbl w-full border-collapse text-sm">{children}</table></div>
}

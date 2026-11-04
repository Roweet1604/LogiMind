import { BookOpen, Check, ClipboardList, FlaskConical, KeyRound, LayoutGrid, Play, Route as RouteIcon, Scale, SlidersHorizontal } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useApp } from '../state/AppContext'
import { useAuth } from '../state/AuthContext'
import { Badge } from './ui'

const FLOW = [
  { to: '/setup', label: 'Problem setup', icon: SlidersHorizontal },
  { to: '/run', label: 'Run optimization', icon: Play },
  { to: '/results', label: 'Route results', icon: RouteIcon },
  { to: '/compare', label: 'Compare algorithms', icon: Scale },
]
const MORE = [
  { to: '/benchmark', label: 'Benchmark lab', icon: FlaskConical },
  { to: '/methodology', label: 'Methodology', icon: BookOpen },
]

function Item({ to, label, icon: Icon, n }) {
  return (
    <NavLink to={to} end={to === '/'}
      className={({ isActive }) =>
        `flex items-center gap-3 whitespace-nowrap rounded-md px-3 py-2.5 text-sm font-medium ${isActive ? 'bg-white/10 text-white' : 'text-nav-text hover:bg-nav-hover hover:text-white'}`}>
      <Icon size={18} aria-hidden="true" />
      <span className="flex-1">{label}</span>
      {n && <span className="font-mono text-xs opacity-50">{n}</span>}
    </NavLink>
  )
}

// Progress through the workflow, derived from real state (instance loaded, completed runs).
function Stepper() {
  const { instance, runs } = useApp()
  const done = runs.filter((r) => r.state === 'completed')
  const complete = {
    '/setup': Boolean(instance),
    '/run': done.length > 0,
    '/results': done.length > 0,
    '/compare': done.some((r) => r.algorithm === 'ortools') && done.some((r) => r.algorithm === 'ga'),
  }
  const { pathname } = useLocation()
  return (
    <ol className="mb-6 flex flex-wrap gap-x-2 gap-y-2" aria-label="Workflow progress">
      {FLOW.map((s, i) => {
        const current = pathname === s.to
        return (
          <li key={s.to} className="flex items-center gap-2">
            <Link to={s.to} aria-current={current ? 'step' : undefined}
              className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm ${current ? 'border-accent bg-accent-soft font-semibold text-accent-dark' : 'border-rule bg-white text-ink2 hover:text-ink'}`}>
              <span className={`flex h-5 w-5 items-center justify-center rounded-full text-xs font-semibold ${complete[s.to] ? 'bg-accent text-white' : 'border border-rule text-ink2'}`}>
                {complete[s.to] ? <Check size={12} aria-label="done" /> : i + 1}
              </span>
              {s.label}
            </Link>
            {i < FLOW.length - 1 && <span className="hidden h-px w-4 bg-rule sm:block" aria-hidden="true" />}
          </li>
        )
      })}
    </ol>
  )
}

const OPS = [
  { to: '/plans', label: 'Plans', icon: ClipboardList },
  { to: '/login', label: 'API key', icon: KeyRound },
]
const RESEARCH_PATHS = [...FLOW, ...MORE.filter((m) => m.to === '/benchmark')].map((s) => s.to)

export default function Layout() {
  const { instance, health } = useApp()
  const { me } = useAuth()
  const { pathname } = useLocation()
  const inFlow = FLOW.some((s) => s.to === pathname)
  const researchOff = health.state === 'ok' && health.research === false && RESEARCH_PATHS.includes(pathname)
  return (
    <div className="min-h-screen md:flex">
      <aside className="bg-nav text-nav-text md:sticky md:top-0 md:flex md:h-screen md:w-64 md:shrink-0 md:flex-col">
        <div className="flex items-center gap-3 px-5 py-4 md:py-6">
          <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true" className="shrink-0">
            <rect width="28" height="28" rx="6" fill="#1E6B70" />
            <path d="M7 20 L12 9 L17 16 L21 8" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="7" cy="20" r="2" fill="#fff" /><circle cx="21" cy="8" r="2" fill="#fff" />
          </svg>
          <div>
            <p className="font-semibold leading-tight text-white">LogiMind</p>
            <p className="text-xs text-nav-text/70">Ops console</p>
          </div>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:gap-0.5 md:overflow-y-auto">
          <Item to="/" label="Overview" icon={LayoutGrid} />
          <p className="hidden px-3 pb-1 pt-5 text-xs font-medium text-nav-text/50 md:block">Operations</p>
          {OPS.map((i) => <Item key={i.to} {...i} />)}
          <p className="hidden px-3 pb-1 pt-5 text-xs font-medium text-nav-text/50 md:block">Research workflow (dev only)</p>
          {FLOW.map((i, k) => <Item key={i.to} {...i} n={k + 1} />)}
          <p className="hidden px-3 pb-1 pt-5 text-xs font-medium text-nav-text/50 md:block">Research</p>
          {MORE.map((i) => <Item key={i.to} {...i} />)}
        </nav>
        <div className="hidden border-t border-nav-line px-5 py-4 text-xs md:block">
          <p className="mb-1 text-nav-text/60">Tenant</p>
          <p className="mb-4 text-white">{me ? (me.tenant_name || me.tenant_id) : <span className="text-nav-text/70">Not signed in</span>}</p>
          <p className="mb-1 text-nav-text/60">Current research instance</p>
          {instance ? (
            <p className="break-all font-mono text-[12px] leading-snug text-white">{instance.instance_id}<span className="block text-nav-text/70">{instance.customers.length} customers · {instance.metric}</span></p>
          ) : <p className="text-nav-text/70">None selected</p>}
          <p className="mb-1 mt-4 text-nav-text/60">Backend</p>
          {health.state === 'ok' && <Badge kind="ok">connected</Badge>}
          {health.state === 'down' && <Badge kind="bad">unreachable</Badge>}
          {health.state === 'checking' && <Badge>checking</Badge>}
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-5 py-6 md:px-10 md:py-8">
        <div className="mx-auto max-w-[1600px]">
          {health.state === 'down' && (
            <div className="mb-5 rounded-md border border-err/40 bg-err-soft px-4 py-3" role="alert">
              Backend unreachable. Start it with <code className="font-mono">uvicorn app.main:app --port 8000</code> in <code className="font-mono">backend/</code>.
            </div>
          )}
          {researchOff && (
            <div className="mb-5 rounded-md border border-warn/40 bg-warn-soft px-4 py-3" role="status">
              The research pages are switched off on this backend (they have no tenants). Use{' '}
              <Link className="underline" to="/plans">Plans</Link> with an API key, or start the backend with{' '}
              <code className="font-mono">LOGIMIND_DEV_RESEARCH_ENDPOINTS=1</code> for local development.
            </div>
          )}
          {inFlow && <Stepper />}
          <Outlet />
        </div>
      </main>
    </div>
  )
}

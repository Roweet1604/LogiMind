import { BookOpen, Check, ClipboardList, FlaskConical, KeyRound, LayoutGrid, MessageSquare, PanelRightClose, PanelRightOpen, Play, Route as RouteIcon, Scale, SlidersHorizontal } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useApp } from '../state/AppContext'
import { useAuth } from '../state/AuthContext'
import CopilotChat, { CopilotProvider, ModelStatus, useCopilot } from './CopilotChat'
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
        `flex items-center gap-3 whitespace-nowrap rounded-md border-l-2 px-3 py-2 text-sm font-medium ${isActive ? 'border-accent bg-white/10 text-white' : 'border-transparent text-nav-text hover:bg-nav-hover hover:text-white'}`}>
      <Icon size={17} aria-hidden="true" />
      <span className="flex-1">{label}</span>
      {n && <span className="font-mono text-2xs text-nav-muted">{n}</span>}
    </NavLink>
  )
}

const Group = ({ children }) => <p className="hidden px-3 pb-1 pt-5 text-2xs font-semibold uppercase tracking-wider text-nav-muted md:block">{children}</p>

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
    <ol className="mb-5 flex flex-wrap gap-x-2 gap-y-2" aria-label="Workflow progress">
      {FLOW.map((s, i) => {
        const current = pathname === s.to
        return (
          <li key={s.to} className="flex items-center gap-2">
            <Link to={s.to} aria-current={current ? 'step' : undefined}
              className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm ${current ? 'border-accent bg-accent-soft font-semibold text-accent-dark' : 'border-rule bg-panel text-ink2 hover:text-ink'}`}>
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
  { to: '/copilot', label: 'Copilot', icon: MessageSquare },
]
const RESEARCH_PATHS = [...FLOW, ...MORE.filter((m) => m.to === '/benchmark')].map((s) => s.to)

function BackendStatus({ health }) {
  if (health.state === 'ok') return <Badge kind="ok">backend connected</Badge>
  if (health.state === 'down') return <Badge kind="bad">backend unreachable</Badge>
  return <Badge kind="busy">checking backend</Badge>
}

// Docked copilot: the same conversation as the /copilot page, beside whatever page is open.
function CopilotDock({ onClose }) {
  const { status } = useCopilot()
  const close = useRef(null)
  useEffect(() => { close.current?.focus() }, [])  // keyboard users land in the panel
  return (
    <aside id="copilot-dock" aria-label="Copilot panel" onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
      className="fixed inset-0 z-[1100] flex flex-col bg-panel lg:sticky lg:top-14 lg:z-auto lg:h-[calc(100vh-3.5rem)] lg:w-dock lg:shrink-0 lg:border-l lg:border-rule">
      <div className="flex items-center justify-between gap-2 border-b border-rule px-4 py-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2"><MessageSquare size={16} aria-hidden="true" />Copilot</h2>
          <div className="mt-1"><ModelStatus status={status} /></div>
        </div>
        <button ref={close} type="button" className="btn btn-ghost px-2" onClick={onClose} aria-label="Close the copilot panel (Esc)">
          <PanelRightClose size={18} aria-hidden="true" />
        </button>
      </div>
      <p className="border-b border-rule2 bg-sunken px-4 py-2 text-2xs text-ink2">
        The model reads your request only. Routes come from the solvers and are checked by the validator.
      </p>
      <div className="min-h-0 flex-1"><CopilotChat compact /></div>
    </aside>
  )
}

export default function Layout() {
  const { instance, health } = useApp()
  const { me, state } = useAuth()
  const { pathname } = useLocation()
  const [dock, setDock] = useState(false)
  const inFlow = FLOW.some((s) => s.to === pathname)
  const researchOff = health.state === 'ok' && health.research === false && RESEARCH_PATHS.includes(pathname)
  const showDock = dock && state === 'in' && pathname !== '/copilot'
  return (
    <CopilotProvider>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[1200] focus:rounded focus:bg-panel focus:px-3 focus:py-2">Skip to content</a>
      <div className="min-h-screen md:flex">
        <aside className="bg-nav text-nav-text md:sticky md:top-0 md:flex md:h-screen md:w-rail md:shrink-0 md:flex-col">
          <div className="flex h-14 items-center gap-3 border-b border-nav-line px-5">
            <svg width="26" height="26" viewBox="0 0 28 28" aria-hidden="true" className="shrink-0">
              <rect width="28" height="28" rx="6" className="fill-accent" />
              <path d="M7 20 L12 9 L17 16 L21 8" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="7" cy="20" r="2" fill="#fff" /><circle cx="21" cy="8" r="2" fill="#fff" />
            </svg>
            <div>
              <p className="font-semibold leading-tight text-white">LogiMind</p>
              <p className="text-2xs text-nav-muted">Dispatch console</p>
            </div>
          </div>
          <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 py-3 md:flex-1 md:flex-col md:gap-0.5 md:overflow-y-auto">
            <Item to="/" label="Overview" icon={LayoutGrid} />
            <Group>Operations</Group>
            {OPS.map((i) => <Item key={i.to} {...i} />)}
            <Group>Research workflow (dev only)</Group>
            {FLOW.map((i, k) => <Item key={i.to} {...i} n={k + 1} />)}
            <Group>Research</Group>
            {MORE.map((i) => <Item key={i.to} {...i} />)}
            <Group>Account</Group>
            <Item to="/login" label="API key" icon={KeyRound} />
          </nav>
          <div className="hidden border-t border-nav-line px-5 py-4 text-xs md:block">
            <p className="mb-1 text-nav-muted">Current research instance</p>
            {instance ? (
              <p className="break-all font-mono text-[12px] leading-snug text-white">{instance.instance_id}<span className="block text-nav-text">{instance.customers.length} customers · {instance.metric}</span></p>
            ) : <p className="text-nav-text">None selected</p>}
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-[1050] flex h-14 items-center justify-between gap-3 border-b border-rule bg-panel px-5 md:px-8">
            <div className="flex min-w-0 items-center gap-2 text-sm">
              <span className="text-ink2">Tenant</span>
              <span className="truncate font-medium">{me ? (me.tenant_name || me.tenant_id) : <Link className="link" to="/login">not signed in</Link>}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="hidden sm:inline-flex"><BackendStatus health={health} /></span>
              {state === 'in' && pathname !== '/copilot' && (
                <button type="button" className={`btn ${dock ? 'border-accent text-accent-dark' : ''}`} onClick={() => setDock((d) => !d)}
                  aria-expanded={dock} aria-controls="copilot-dock">
                  {dock ? <PanelRightClose size={16} aria-hidden="true" /> : <PanelRightOpen size={16} aria-hidden="true" />}Copilot
                </button>
              )}
            </div>
          </header>
          <div className="flex min-h-0 flex-1">
            <main id="main" className="min-w-0 flex-1 px-5 py-6 md:px-8">
              <div className="mx-auto max-w-[1600px]">
                {health.state === 'down' && (
                  <div className="mb-5 rounded-md border border-err/40 bg-err-soft px-4 py-3" role="alert">
                    Backend unreachable. Start it with <code>uvicorn app.main:app --port 8000</code> in <code>backend/</code>.
                  </div>
                )}
                {researchOff && (
                  <div className="mb-5 rounded-md border border-warn/40 bg-warn-soft px-4 py-3" role="status">
                    The research pages are switched off on this backend (they have no tenants). Use{' '}
                    <Link className="underline" to="/plans">Plans</Link> with an API key, or start the backend with{' '}
                    <code>LOGIMIND_DEV_RESEARCH_ENDPOINTS=1</code> for local development.
                  </div>
                )}
                {inFlow && <Stepper />}
                <Outlet />
              </div>
            </main>
            {showDock && <CopilotDock onClose={() => setDock(false)} />}
          </div>
        </div>
      </div>
    </CopilotProvider>
  )
}

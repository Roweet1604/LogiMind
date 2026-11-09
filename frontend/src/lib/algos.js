import { ENGINE_LINES } from '../../../design/tokens.js'

// Algorithm identity: colour AND dash pattern, so identity never depends on colour alone (design/tokens.js).
const line = (k) => ENGINE_LINES[k]
export const ALGOS = {
  ortools: { key: 'ortools', label: 'OR-Tools', ...line('ortools'), textClass: 'text-ortools', softClass: 'bg-ortools-soft' },
  ga: { key: 'ga', label: 'Genetic Algorithm', ...line('ga'), textClass: 'text-ga-text', softClass: 'bg-ga-soft' },
  // Plan engines (tenant API). The GA keeps its dashed orange; the hybrid has its own dash-dot slate and is labelled as a hybrid.
  ga_ls: { key: 'ga_ls', label: 'GA + local search', ...line('ga'), textClass: 'text-ga-text', softClass: 'bg-ga-soft' },
  hybrid: { key: 'hybrid', label: 'Hybrid (OR-Tools seed + GA)', ...line('hybrid'), textClass: 'text-hybrid', softClass: 'bg-hybrid-soft' },
}

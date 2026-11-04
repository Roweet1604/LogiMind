// Algorithm identity: colour AND dash pattern, so identity never depends on colour alone.
export const ALGOS = {
  ortools: { key: 'ortools', label: 'OR-Tools', color: '#2A5DA8', textClass: 'text-ortools', softClass: 'bg-ortools-soft', dash: undefined, dashLabel: 'solid line' },
  ga: { key: 'ga', label: 'Genetic Algorithm', color: '#C2641A', textClass: 'text-ga-text', softClass: 'bg-ga-soft', dash: '7 5', dashLabel: 'dashed line' },
  // Plan engines (tenant API). The GA keeps its dashed orange; the hybrid is labelled as a hybrid (dotted blue).
  ga_ls: { key: 'ga_ls', label: 'GA + local search', color: '#C2641A', textClass: 'text-ga-text', softClass: 'bg-ga-soft', dash: '7 5', dashLabel: 'dashed line' },
  hybrid: { key: 'hybrid', label: 'Hybrid (OR-Tools seed + GA)', color: '#2A5DA8', textClass: 'text-ortools', softClass: 'bg-ortools-soft', dash: '2 4', dashLabel: 'dotted line' },
}

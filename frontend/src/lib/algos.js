// Algorithm identity: colour AND dash pattern, so identity never depends on colour alone.
export const ALGOS = {
  ortools: { key: 'ortools', label: 'OR-Tools', color: '#2A5DA8', textClass: 'text-ortools', softClass: 'bg-ortools-soft', dash: undefined, dashLabel: 'solid line' },
  ga: { key: 'ga', label: 'Genetic Algorithm', color: '#C2641A', textClass: 'text-ga-text', softClass: 'bg-ga-soft', dash: '7 5', dashLabel: 'dashed line' },
}

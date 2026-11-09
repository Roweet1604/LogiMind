// LogiMind design tokens: the one place for colours, type, spacing and radii (decision 0025).
// Read by frontend/tailwind.config.js, driver/tailwind.config.js and frontend/src/lib/algos.js.
// Contrast of every text pair was checked (>= 4.5:1); see the decision record.

export const colors = {
  paper: '#F3F1EB',          // warm neutral page background
  panel: '#FFFFFF',          // working surfaces
  sunken: '#F8F7F3',         // table heads, inputs on paper
  ink: '#15191C',            // charcoal text
  ink2: '#596067',           // secondary text (5.6:1 on paper)
  rule: '#E2DED2',           // borders
  rule2: '#EEEBE2',          // inner dividers, neutral tint
  nav: { DEFAULT: '#14181B', text: '#C5CACD', muted: '#8A9196', hover: '#1F252A', line: '#2B3237' },
  accent: { DEFAULT: '#1E6B70', dark: '#165458', soft: '#DCEBEA' },   // the one action colour
  // Engine identity: colour AND line pattern (see ENGINE_LINES below).
  ortools: { DEFAULT: '#2A5DA8', soft: '#E4ECF7' },
  ga: { DEFAULT: '#C2641A', text: '#98490F', soft: '#F7E9DA' },
  hybrid: { DEFAULT: '#3B4651', soft: '#E6E9EC' },
  // Semantic status colours (always paired with an icon and a word).
  ok: { DEFAULT: '#2B6B3C', soft: '#E1EEE3' },
  warn: { DEFAULT: '#8A5F0E', soft: '#F6ECD3' },
  err: { DEFAULT: '#A53A2A', soft: '#F6E2DD' },
  draft: { DEFAULT: '#4A5560', soft: '#EDEAE2' },
  // Map marks
  map: { bg: '#ECE8DC', stop: '#1E2326', unserved: '#A33A2B' },
}

export const ENGINE_LINES = {
  ortools: { color: colors.ortools.DEFAULT, dash: undefined, dashLabel: 'solid line' },
  ga: { color: colors.ga.DEFAULT, dash: '7 5', dashLabel: 'dashed line' },
  hybrid: { color: colors.hybrid.DEFAULT, dash: '12 4 2 4', dashLabel: 'dash-dot line' },
}

export const fontFamily = {
  sans: ['"Inter Variable"', 'Inter', '"Segoe UI"', 'system-ui', 'sans-serif'],
  mono: ['"JetBrains Mono Variable"', 'ui-monospace', 'Consolas', 'monospace'],
}

// Size scale: 12 / 13 / 15 / 16 / 18 / 22 / 28 px. The console body is 15 px; the driver app body is 18 px.
export const fontSize = {
  '2xs': ['0.75rem', { lineHeight: '1rem' }],
  xs: ['0.8125rem', { lineHeight: '1.25rem' }],
  sm: ['0.9375rem', { lineHeight: '1.5rem' }],
  base: ['1rem', { lineHeight: '1.6rem' }],
  lg: ['1.125rem', { lineHeight: '1.6rem' }],
  xl: ['1.375rem', { lineHeight: '1.8rem' }],
  '2xl': ['1.75rem', { lineHeight: '2.2rem' }],
}

// Spacing follows Tailwind's 4 px grid; these are the named layout sizes used by both apps.
export const spacing = { rail: '15rem', dock: '26rem', routes: '22rem', tap: '3.5rem', 'tap-lg': '4rem' }

export const borderRadius = { DEFAULT: '6px', md: '6px', lg: '8px' }
export const boxShadow = { panel: '0 1px 2px rgba(21,25,28,0.05)', dock: '-1px 0 0 #E2DED2' }

export default { colors, fontFamily, fontSize, spacing, borderRadius, boxShadow }

// LogiMind design tokens, "Freight Yard" theme: the one place for colours, type, spacing and radii
// (decisions 0025 and 0027). Read by frontend/tailwind.config.js, driver/tailwind.config.js and
// frontend/src/lib/algos.js. Every text/background pair was checked (>= 4.5:1); the list is in decision 0027.
//
// Rule: the safety yellow (accent) is a BACKGROUND on light surfaces, always with ink text on it.
// It is a text/icon colour only on dark surfaces (nav, driver header, warning badges).

export const colors = {
  paper: '#EDEDEA',          // concrete grey page background
  panel: '#FFFFFF',          // panels and cards
  sunken: '#F6F6F3',         // table heads, quiet blocks
  ink: '#1A1A1A',            // text, strong dividers, focus ring on light surfaces
  ink2: '#55554F',           // muted text (6.4:1 on paper)
  rule: '#CFCFCA',           // borders
  rule2: '#E2E2DD',          // inner dividers, neutral tint
  nav: { DEFAULT: '#1A1A1A', text: '#D6D6D0', muted: '#A3A39B', hover: '#2A2A27', line: '#33332F' },
  // Safety yellow: action backgrounds (ink text on top), and text only on dark surfaces.
  accent: { DEFAULT: '#FFC400', dark: '#E5B000', soft: '#FFF1BF' },
  // Engine identity: colour AND line pattern (see ENGINE_LINES). Yellow is never a data line.
  ortools: { DEFAULT: '#1D4ED8', soft: '#E6ECFB' },
  ga: { DEFAULT: '#C2410C', text: '#9A3412', soft: '#FBEDE6' },
  hybrid: { DEFAULT: '#57606A', soft: '#ECEDEF' },
  // Status (always with an icon and a word):
  ok: { DEFAULT: '#166534', soft: '#EEF5EF' },             // feasible: green text on white, ink border
  warn: { DEFAULT: '#FFC400', soft: '#1A1A1A', body: '#EDEDEA' }, // warning: dark block, yellow title/text
  err: { DEFAULT: '#B42318', text: '#8F1D14', soft: '#FDECEA' },  // infeasible/timeout/failed: red
  draft: { DEFAULT: '#FFC400', soft: '#1A1A1A' },          // draft/synthetic/preliminary: warning style, dashed
  // Map
  map: { bg: '#E2E2DD', road: '#C9C9C3', stop: '#1A1A1A', unserved: '#B42318' },
}

export const ENGINE_LINES = {
  ortools: { color: colors.ortools.DEFAULT, dash: undefined, dashLabel: 'solid line' },
  ga: { color: colors.ga.DEFAULT, dash: '7 5', dashLabel: 'dashed line' },
  hybrid: { color: colors.hybrid.DEFAULT, dash: '12 4 2 4', dashLabel: 'dash-dot line' },
}

export const fontFamily = {
  sans: ['"IBM Plex Sans"', '"Segoe UI"', 'system-ui', 'sans-serif'],
  display: ['"Barlow Condensed"', '"Arial Narrow"', '"IBM Plex Sans"', 'sans-serif'],
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

// 4 px corners everywhere (pills too); no shadows beyond a hairline border.
export const borderRadius = { none: '0', sm: '4px', DEFAULT: '4px', md: '4px', lg: '4px', full: '4px' }
export const boxShadow = { panel: 'none', dock: 'none' }

export default { colors, fontFamily, fontSize, spacing, borderRadius, boxShadow }

/** Design tokens: warm paper canvas, white working surfaces, charcoal ink, one teal accent,
 *  and two fixed algorithm identity colours. Type scale is deliberately larger than Tailwind's default. */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#F3F1EB',
        panel: '#FFFFFF',
        ink: '#15191C',
        ink2: '#596067',
        rule: '#E2DED2',
        rule2: '#EEEBE2',
        nav: { DEFAULT: '#14181B', text: '#C5CACD', hover: '#1F252A', line: '#2B3237' },
        accent: { DEFAULT: '#1E6B70', dark: '#165458', soft: '#DCEBEA' },
        ortools: { DEFAULT: '#2A5DA8', soft: '#E4ECF7' },
        ga: { DEFAULT: '#C2641A', text: '#98490F', soft: '#F7E9DA' },
        ok: { DEFAULT: '#2B6B3C', soft: '#E1EEE3' },
        warn: { DEFAULT: '#8A5F0E', soft: '#F6ECD3' },
        err: { DEFAULT: '#A53A2A', soft: '#F6E2DD' },
      },
      fontFamily: {
        sans: ['"Inter Variable"', 'Inter', '"Segoe UI"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono Variable"', 'ui-monospace', 'Consolas', 'monospace'],
      },
      fontSize: {
        xs: ['0.8125rem', { lineHeight: '1.25rem' }],
        sm: ['0.9375rem', { lineHeight: '1.5rem' }],
        base: ['1rem', { lineHeight: '1.6rem' }],
        lg: ['1.125rem', { lineHeight: '1.6rem' }],
        xl: ['1.375rem', { lineHeight: '1.8rem' }],
        '2xl': ['1.75rem', { lineHeight: '2.2rem' }],
      },
      borderRadius: { DEFAULT: '6px', md: '6px', lg: '10px' },
      boxShadow: { panel: '0 1px 2px rgba(21,25,28,0.05)' },
    },
  },
  plugins: [],
}

/** Same tokens as the ops console: warm paper canvas, charcoal ink, one teal accent. Mobile-first. */
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
        accent: { DEFAULT: '#1E6B70', dark: '#165458', soft: '#DCEBEA' },
        ok: { DEFAULT: '#2B6B3C', soft: '#E1EEE3' },
        warn: { DEFAULT: '#8A5F0E', soft: '#F6ECD3' },
        err: { DEFAULT: '#A53A2A', soft: '#F6E2DD' },
      },
      fontFamily: { sans: ['"Inter Variable"', 'Inter', '"Segoe UI"', 'system-ui', 'sans-serif'] },
      borderRadius: { DEFAULT: '8px', md: '8px', lg: '12px' },
    },
  },
  plugins: [],
}

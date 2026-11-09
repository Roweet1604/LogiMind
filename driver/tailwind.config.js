/** Design tokens come from design/tokens.js (shared with the ops console; decision 0025). Mobile-first. */
import tokens from '../design/tokens.js'

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: tokens.colors,
      fontFamily: { sans: tokens.fontFamily.sans },
      spacing: tokens.spacing,
      borderRadius: { DEFAULT: '8px', md: '8px', lg: '12px' },
    },
  },
  plugins: [],
}

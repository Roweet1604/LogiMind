/** Design tokens come from design/tokens.js (shared with the ops console; decisions 0025, 0027). Mobile-first. */
import tokens from '../design/tokens.js'

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: tokens.colors,
      fontFamily: { sans: tokens.fontFamily.sans, display: tokens.fontFamily.display },
      spacing: tokens.spacing,
      borderRadius: tokens.borderRadius,
      boxShadow: tokens.boxShadow,
    },
  },
  plugins: [],
}

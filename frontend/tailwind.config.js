/** Design tokens come from design/tokens.js (shared with the driver app; decision 0025). */
import tokens from '../design/tokens.js'

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: tokens.colors,
      fontFamily: tokens.fontFamily,
      fontSize: tokens.fontSize,
      spacing: tokens.spacing,
      borderRadius: tokens.borderRadius,
      boxShadow: tokens.boxShadow,
    },
  },
  plugins: [],
}

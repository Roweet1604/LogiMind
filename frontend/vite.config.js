import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the FastAPI backend, so no CORS setup is needed in development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    fs: { allow: ['.', '../design'] }, // shared design tokens (decision 0025)
    proxy: { '/api': process.env.VITE_BACKEND_URL || 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: false,
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { manifest } from './pwa.manifest.js'

// Driver PWA. The service worker precaches the app shell so it opens offline; the stop list itself is
// cached by the app (src/lib/store.js), so the API is never served stale by the service worker.

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon-192.png', 'icon-512.png'],
      manifest,
      workbox: {
        globPatterns: ['**/*.{js,css,html,png,woff2}'],
        navigateFallback: 'index.html',
        navigateFallbackDenylist: [/^\/api\//],
      },
    }),
  ],
  server: {
    port: 5174,
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

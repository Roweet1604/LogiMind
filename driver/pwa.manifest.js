// Web app manifest (installable PWA). Kept in its own file so tests can check it without loading Vite.
export const manifest = {
  name: 'LogiMind Driver',
  short_name: 'Driver',
  description: 'Stop list, navigation and delivery reports for one route.',
  start_url: '/',
  scope: '/',
  display: 'standalone',
  orientation: 'portrait',
  background_color: '#F3F1EB',
  theme_color: '#1E6B70',
  icons: [
    { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
    { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
    { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
  ],
}

// Reading cloudflared's output for `npm run dev` (decision 0043). Pure functions, so they can be tested without
// cloudflared: node --test scripts/tunnel.test.mjs (also run by tests/test_dev_tunnel.py).
//
// A quick tunnel's address is taken ONLY from cloudflared's success banner:
//   |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
//   |  https://seasonal-deck-organisms-sf.trycloudflare.com                                      |
// Error lines also contain trycloudflare.com addresses (e.g. 'Post "https://api.trycloudflare.com/tunnel": context
// deadline exceeded'), which must never become the console link.

export const BANNER = /your quick tunnel has been created/i
// <words>.trycloudflare.com: at least two lowercase words joined by hyphens, e.g. seasonal-deck-organisms-sf.
const ADDRESS = /https:\/\/([a-z0-9]+(?:-[a-z0-9]+)+)\.trycloudflare\.com(?![a-z0-9.-])/g
// Cloudflare's own service names on trycloudflare.com; never a tunnel.
const RESERVED = new Set(['api', 'www'])
export const MAX_ATTEMPTS = 3

// The tunnel address from cloudflared's output so far (all chunks joined), or null. Only an address that comes
// after the success banner counts.
export function findTunnelAddress(text) {
  const banner = BANNER.exec(String(text))
  if (!banner) return null
  const after = String(text).slice(banner.index + banner[0].length)
  for (const m of after.matchAll(ADDRESS)) {
    if (!RESERVED.has(m[1])) return `https://${m[1]}.trycloudflare.com`
  }
  return null
}

// What a cloudflared line says about the attempt:
//   'quic-timeout'    the QUIC connection to Cloudflare's edge timed out (often UDP blocked): retry with http2
//   'request-failed'  cloudflared could not get a quick tunnel (e.g. api.trycloudflare.com timed out): retry
//   null              nothing that ends the attempt
export function classifyLine(line) {
  const s = String(line)
  if (/\bquic\b/i.test(s) && /timeout|timed out|deadline exceeded|no recent network activity/i.test(s)) return 'quic-timeout'
  if (/failed to (request|create) quick tunnel/i.test(s)) return 'request-failed'
  return null
}

// cloudflared arguments for one attempt.
export function tunnelArgs(port, protocol) {
  const args = ['tunnel', '--no-autoupdate']
  if (protocol) args.push('--protocol', protocol)
  args.push('--url', `http://localhost:${port}`)
  return args
}

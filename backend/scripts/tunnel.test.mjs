// node --test scripts/tunnel.test.mjs   (from backend/; also run by tests/test_dev_tunnel.py). Decision 0043.
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { classifyLine, findTunnelAddress, tunnelArgs } from './tunnel.mjs'

const BANNER_OUTPUT = [
  '2026-11-13T10:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...',
  '2026-11-13T10:00:02Z INF +--------------------------------------------------------------------------------------------+',
  '2026-11-13T10:00:02Z INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |',
  '2026-11-13T10:00:02Z INF |  https://seasonal-deck-organisms-sf.trycloudflare.com                                      |',
  '2026-11-13T10:00:02Z INF +--------------------------------------------------------------------------------------------+',
].join('\n')

// The output that produced https://logi-mind-ten.vercel.app/?api=https://api.trycloudflare.com (13 Nov 2026).
const REQUEST_FAILED = '2026-11-13T10:00:30Z ERR Error unmarshaling QuickTunnel response: error="failed to request quick ' +
  'Tunnel: Post \\"https://api.trycloudflare.com/tunnel\\": context deadline exceeded"\n' +
  'failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": context deadline exceeded'

const QUIC_TIMEOUT = '2026-11-13T10:00:20Z ERR Failed to dial a quic connection error="failed to dial to edge with quic: ' +
  'timeout: no recent network activity" connIndex=0 event=0 ip=198.41.192.7'

test('takes the address from the success banner', () => {
  assert.equal(findTunnelAddress(BANNER_OUTPUT), 'https://seasonal-deck-organisms-sf.trycloudflare.com')
})

test('a failed tunnel request gives no address (api.trycloudflare.com in the error text)', () => {
  assert.equal(findTunnelAddress(REQUEST_FAILED), null)
})

test('an address before the banner is ignored', () => {
  assert.equal(findTunnelAddress('INF see https://other-words-here.trycloudflare.com\nINF still starting'), null)
})

test('api.trycloudflare.com is rejected even after the banner', () => {
  const text = '|  Your quick Tunnel has been created! Visit it at:  |\n|  https://api.trycloudflare.com  |'
  assert.equal(findTunnelAddress(text), null)
  // and a real address after it is still found
  assert.equal(findTunnelAddress(`${text}\n|  https://calm-river-bend.trycloudflare.com  |`), 'https://calm-river-bend.trycloudflare.com')
})

test('only <words>.trycloudflare.com counts, not single names or other domains', () => {
  const banner = 'Your quick Tunnel has been created! Visit it at:\n'
  assert.equal(findTunnelAddress(`${banner}https://www.trycloudflare.com`), null)
  assert.equal(findTunnelAddress(`${banner}https://tunnel.trycloudflare.com`), null)
  assert.equal(findTunnelAddress(`${banner}https://calm-river.trycloudflare.com.evil.example`), null)
  assert.equal(findTunnelAddress(`${banner}https://calm-river.trycloudflare.community`), null)
  assert.equal(findTunnelAddress(`${banner}http://calm-river.trycloudflare.com`), null)
})

test('a banner split across output chunks is found once the pieces are joined', () => {
  const cut = BANNER_OUTPUT.indexOf('Tunnel has been') + 3
  assert.equal(findTunnelAddress(BANNER_OUTPUT.slice(0, cut)), null)
  assert.equal(findTunnelAddress(BANNER_OUTPUT), 'https://seasonal-deck-organisms-sf.trycloudflare.com')
  const half = BANNER_OUTPUT.indexOf('organisms')
  assert.equal(findTunnelAddress(BANNER_OUTPUT.slice(0, half)), null)
})

test('a failed request after an earlier attempt banner text still needs a new banner per run', () => {
  // dev.mjs keeps output per cloudflared run; a run with only the error has no banner
  assert.equal(findTunnelAddress(`${REQUEST_FAILED}\n${QUIC_TIMEOUT}`), null)
})

test('classifies failure lines', () => {
  assert.equal(classifyLine(REQUEST_FAILED.split('\n')[1]), 'request-failed')
  assert.equal(classifyLine(REQUEST_FAILED.split('\n')[0]), 'request-failed')
  assert.equal(classifyLine(QUIC_TIMEOUT), 'quic-timeout')
  assert.equal(classifyLine('ERR failed to dial to edge with quic: deadline exceeded'), 'quic-timeout')
  assert.equal(classifyLine('INF Registered tunnel connection connIndex=0 protocol=quic'), null)
  assert.equal(classifyLine(BANNER_OUTPUT.split('\n')[2]), null)
})

test('cloudflared arguments, with http2 after a QUIC timeout', () => {
  assert.deepEqual(tunnelArgs('8000', null), ['tunnel', '--no-autoupdate', '--url', 'http://localhost:8000'])
  assert.deepEqual(tunnelArgs('8000', 'http2'),
    ['tunnel', '--no-autoupdate', '--protocol', 'http2', '--url', 'http://localhost:8000'])
})

// Writes the PWA icons (public/icon-192.png, public/icon-512.png): a safety-yellow square with an ink "L",
// in the Freight Yard colours from design/tokens.js. Plain PNGs, no image library: node scripts/make-icons.mjs
import { writeFileSync } from 'node:fs'
import { deflateSync } from 'node:zlib'
import { colors } from '../../design/tokens.js'

const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
const CRC = Array.from({ length: 256 }, (_, n) => {
  let c = n
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
  return c >>> 0
})
const crc32 = (buf) => { let c = 0xffffffff; for (const b of buf) c = CRC[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0 }
const chunk = (type, data) => {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type), data])
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(body))
  return Buffer.concat([len, body, crc])
}

function icon(size) {
  const bg = rgb(colors.accent.DEFAULT), fg = rgb(colors.ink)
  // "L" inside the maskable safe zone (central 80%), same proportions as the previous icon.
  const s = size / 192
  const inL = (x, y) => (x >= 64 * s && x < 84 * s && y >= 55 * s && y < 140 * s) || (x >= 64 * s && x < 130 * s && y >= 120 * s && y < 140 * s)
  const rows = []
  for (let y = 0; y < size; y++) {
    const row = Buffer.alloc(1 + size * 3) // filter byte 0, then RGB
    for (let x = 0; x < size; x++) row.set(inL(x, y) ? fg : bg, 1 + x * 3)
    rows.push(row)
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4); ihdr[8] = 8; ihdr[9] = 2 // 8-bit RGB
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(Buffer.concat(rows))), chunk('IEND', Buffer.alloc(0))])
}

for (const size of [192, 512]) writeFileSync(new URL(`../public/icon-${size}.png`, import.meta.url), icon(size))
console.log('wrote public/icon-192.png and public/icon-512.png')

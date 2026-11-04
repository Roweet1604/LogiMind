// A small SYNTHETIC order set for trying the console without a file. Seeded, so it is the same every time.
// It is labelled "synthetic sample" in its name; it is not real customer data.
export function sampleOrders(n = 12, seed = 7) {
  let s = seed >>> 0
  const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2 ** 32 }
  const customers = Array.from({ length: n }, (_, i) => ({
    id: i + 1, x: Math.round(rnd() * 1000) / 10, y: Math.round(rnd() * 1000) / 10, demand: 1 + Math.floor(rnd() * 5),
  }))
  return { name: `synthetic sample (${n} orders, seed ${seed})`, customers }
}

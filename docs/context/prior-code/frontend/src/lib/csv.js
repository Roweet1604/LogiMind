// Parses a customers CSV: header row optional; columns id,x,y,demand.
// A row with id 0 is taken as the depot (demand ignored). Returns {depot, customers, errors}.
export function parseCustomersCsv(text) {
  const errors = []
  const customers = []
  let depot = null
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
  if (!lines.length) return { depot, customers, errors: ['The file is empty.'] }
  const split = (l) => l.split(/[,;\t]/).map((c) => c.trim())
  let start = 0
  let idx = { id: 0, x: 1, y: 2, demand: 3 }
  const first = split(lines[0])
  if (first.some((c) => c !== '' && Number.isNaN(Number(c)))) {
    const header = first.map((c) => c.toLowerCase())
    const need = ['id', 'x', 'y', 'demand']
    const missing = need.filter((n) => !header.includes(n))
    if (missing.length) return { depot, customers, errors: [`Header is missing column(s): ${missing.join(', ')}`] }
    idx = Object.fromEntries(need.map((n) => [n, header.indexOf(n)]))
    start = 1
  }
  for (let i = start; i < lines.length; i++) {
    const cells = split(lines[i])
    const [id, x, y, demand] = ['id', 'x', 'y', 'demand'].map((k) => Number(cells[idx[k]]))
    const row = i + 1
    if ([id, x, y, demand].some((n) => cells.length <= 3 || Number.isNaN(n))) {
      errors.push(`Row ${row}: needs four numeric values (id, x, y, demand).`)
      continue
    }
    if (!Number.isInteger(id)) { errors.push(`Row ${row}: id must be an integer.`); continue }
    if (id === 0) { depot = { x, y }; continue }
    customers.push({ id, x, y, demand })
  }
  if (!customers.length && !errors.length) errors.push('No customer rows found.')
  return { depot, customers, errors }
}

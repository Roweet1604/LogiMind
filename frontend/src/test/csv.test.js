import { parseCustomersCsv } from '../lib/csv'

test('parses header, depot row (id 0) and customers', () => {
  const r = parseCustomersCsv('id,x,y,demand\n0,77.5,12.9,0\n1,77.6,13.0,4\n2,77.7,13.1,6\n')
  expect(r.errors).toEqual([])
  expect(r.depot).toEqual({ x: 77.5, y: 12.9 })
  expect(r.customers).toEqual([{ id: 1, x: 77.6, y: 13.0, demand: 4 }, { id: 2, x: 77.7, y: 13.1, demand: 6 }])
})

test('accepts headerless, semicolon-separated files and any column order with header', () => {
  expect(parseCustomersCsv('1;1;2;3').customers).toHaveLength(1)
  const r = parseCustomersCsv('demand,y,x,id\n5,2,1,7')
  expect(r.customers[0]).toEqual({ id: 7, x: 1, y: 2, demand: 5 })
})

test('reports row-level problems instead of guessing', () => {
  const r = parseCustomersCsv('id,x,y,demand\n1,2,3\n2,a,3,4\n1.5,1,1,1')
  expect(r.errors).toHaveLength(3)
  expect(r.errors[0]).toMatch(/Row 2/)
  expect(r.customers).toHaveLength(0)
})

test('reports empty files and missing header columns', () => {
  expect(parseCustomersCsv('').errors[0]).toMatch(/empty/)
  expect(parseCustomersCsv('id,x,y\n1,2,3').errors[0]).toMatch(/demand/)
})

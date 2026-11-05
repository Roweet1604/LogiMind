import { render, screen } from '@testing-library/react'
import { DistanceSource } from '../pages/PlanDetail'

vi.mock('../components/RouteMap', () => ({ default: () => <div data-testid="map" /> }))

test('a fallback matrix is shown as a warning with the reason, never as road data', () => {
  render(<DistanceSource source={{
    provider: 'haversine_detour', requested: 'osrm', fallback: true,
    reason: 'OSRM not reachable at http://localhost:5000: ConnectError',
    label: 'FALLBACK estimate: straight line x 1.3 at 25 km/h (not road data): OSRM was not available',
  }} />)
  expect(screen.getByText('Fallback distances: not road data')).toBeInTheDocument()
  expect(screen.getByText(/OSRM not reachable at http:\/\/localhost:5000/)).toBeInTheDocument()
  expect(screen.getByText(/straight line x 1.3 at 25 km\/h/)).toBeInTheDocument()
})

test('a road matrix says where it came from and when', () => {
  render(<DistanceSource source={{
    provider: 'osrm', fallback: false, label: 'road network (OSRM, profile driving)', fetched_at: '2026-11-05T06:00:00+00:00', cache: 'hit',
  }} />)
  expect(screen.getByText('Distances and travel times')).toBeInTheDocument()
  expect(screen.getByText(/road network \(OSRM, profile driving\), fetched 2026-11-05T06:00:00\+00:00 \(from the cache\)/)).toBeInTheDocument()
  expect(screen.queryByText(/Fallback/)).not.toBeInTheDocument()
})

import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import ProblemSetup from './pages/ProblemSetup'
import RunOptimization from './pages/RunOptimization'
import RouteResults from './pages/RouteResults'
import Compare from './pages/Compare'
import BenchmarkLab from './pages/BenchmarkLab'
import Methodology from './pages/Methodology'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="setup" element={<ProblemSetup />} />
        <Route path="run" element={<RunOptimization />} />
        <Route path="results" element={<RouteResults />} />
        <Route path="compare" element={<Compare />} />
        <Route path="benchmark" element={<BenchmarkLab />} />
        <Route path="methodology" element={<Methodology />} />
        <Route path="*" element={<p>Page not found.</p>} />
      </Route>
    </Routes>
  )
}

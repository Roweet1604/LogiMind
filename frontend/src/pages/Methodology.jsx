import { PageHeader, Panel, TableWrap } from '../components/ui'

const P = ({ children }) => <p className="mb-3 max-w-3xl text-base text-ink last:mb-0">{children}</p>

export default function Methodology() {
  return (
    <>
      <PageHeader title="Methodology">What is being solved, how both algorithms are configured, how metrics are defined, and what this study cannot claim.</PageHeader>
      <div className="grid gap-6 xl:grid-cols-2">

      <Panel title="Problem model">
        <P>Capacitated VRP with one depot. Every customer has a positive integer demand and must be served exactly once by one vehicle. Each route starts and ends at the depot and its total demand must not exceed vehicle capacity. The fleet has a fixed number of identical vehicles; unused vehicles are allowed.</P>
        <P>Both algorithms receive the same instance object and the same distance matrix. Distances are straight-line: great-circle (haversine, km) for lat/lon coordinates, or Euclidean for planar ones. They are not road distances, and map lines are straight segments.</P>
      </Panel>

      <Panel title="Objective and cost model">
        <P>Estimated cost = fixed cost per used vehicle × vehicles used + cost per km × total distance. Both solvers minimise this same quantity. The values are synthetic cost units, not calibrated currency. Reported distance and cost are always recomputed by the shared evaluator from the distance matrix, never copied from a solver's own objective.</P>
      </Panel>

      <Panel title="OR-Tools configuration">
        <P>Routing model with a capacity dimension (and a time dimension when the instance has time windows). By default the first solution strategy and metaheuristic are chosen per problem type and time budget from our measured audit (decision 0005; for example SAVINGS + GUIDED_LOCAL_SEARCH for short CVRP runs, PARALLEL_CHEAPEST_INSERTION + TABU_SEARCH for short time-window runs); a user choice overrides this. Search is stopped by a wall-clock limit. Arc costs are scaled by 1000 and rounded to integers because OR-Tools requires integer costs; this introduces rounding of at most 0.0005 cost units per arc inside the solver only. The run's time budget is the total wall-clock time: OR-Tools' own limit covers only its search, so the model-build time is measured and subtracted from the search limit.</P>
      </Panel>

      <Panel title="Genetic algorithm configuration" className="xl:col-span-2">
        <TableWrap>
          <tbody>
            {[
              ['Representation', 'A permutation of all customers ("giant tour"), decoded into routes by an optimal capacity-respecting split (dynamic programme).'],
              ['Fitness', 'Estimated cost of the decoded routes, plus a large penalty per route beyond the fleet size.'],
              ['Selection', 'Tournament (size configurable).'],
              ['Crossover', 'Order crossover (OX), applied with the crossover rate.'],
              ['Mutation', 'Swap, inversion or relocate, chosen at random, applied with the mutation rate.'],
              ['Elitism', 'The best N chromosomes are copied unchanged into the next generation.'],
              ['Initial population', 'Random permutations, plus an optional fraction built with randomised nearest-neighbour tours (default 10%; set 0 for a purely random start).'],
              ['Constraints', 'Coverage and no-duplicates are guaranteed by the permutation. Capacity is guaranteed by the split. The fleet limit is penalised, then independently validated.'],
              ['Termination', 'Time limit, maximum generations, or stagnation. The comparison pages use the time limit only.'],
              ['Randomness', 'Seeded; every run records its seed and parameters. Repeat over several seeds and compare the distribution.'],
            ].map(([k, v]) => <tr key={k}><th scope="row" className="td w-40 text-left font-medium text-ink2">{k}</th><td className="td">{v}</td></tr>)}
          </tbody>
        </TableWrap>
      </Panel>

      <Panel title="Validation and metrics">
        <P>The validator does not trust either solver. It checks that all customers are served, none twice, no route exceeds capacity, no route lists the depot as a stop, and the number of non-empty routes does not exceed the fleet. A run with any violation is shown as infeasible. A run with no solution shows no metrics (a dash), never zero, and is counted but excluded from averages.</P>
        <P>Runtime is wall-clock time of the solve call on the backend machine, including model construction but excluding the one-off distance-matrix computation. Vehicles used counts non-empty routes. Statistics in the benchmark lab (mean, median, standard deviation) are over feasible runs only.</P>
      </Panel>

      <Panel title="Fair comparison rules">
        <P>Same instance, matrix, objective and fleet; the same total wall-clock budget for every run (set-up included for both algorithms); jobs run one at a time on a single worker so they do not compete for CPU. Because both algorithms run to the time limit, runtime reflects the budget; the informative comparison is solution quality at equal time, and how it changes with instance size.</P>
      </Panel>

      <Panel title="Limitations">
        <ul className="max-w-3xl list-disc space-y-1 pl-5 text-base">
          <li>CVRP only: no time windows, service times or multiple depots.</li>
          <li>Which algorithm wins depends on the time budget and the instance. For example, on a tight-capacity 50-customer instance the GA can lead at short budgets and OR-Tools at longer ones. Do not read a single run as a general ranking.</li>
          <li>Time-limited OR-Tools runs are not strictly repeatable: the result can differ slightly between runs, especially on tightly packed instances.</li>
          <li>The GA checks its clock between generations, so on very large instances with very small budgets it can overshoot the budget while building its first population.</li>
          <li>Straight-line distances; real road distances would change both solvers' results.</li>
          <li>Synthetic instances, one per size in the benchmark lab. A few instances cannot support a claim that one method is generally better.</li>
          <li>Wall-clock results depend on the machine and on other programs running on it.</li>
          <li>The split decoder does not enforce the fleet limit internally; very tight fleets can leave the GA with a reported violation.</li>
          <li>Public benchmark instances (such as CVRPLIB) are not yet imported, so no gap to best-known value is reported.</li>
        </ul>
      </Panel>
      </div>
    </>
  )
}

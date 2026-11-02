# 0006: Fleet repair, local search, hybrid solver and wall-clock guard (P3)

Date: 2 Nov 2026. Status: accepted (P3).

## Decision
- **Fleet repair (GA, on by default).** Each generation, if the best tour decodes into more routes than vehicles, the GA tries to empty its smallest routes: every customer of the route moves to its cheapest position in another route that has room and does not become later. This replaces the old "too many routes" branch of the time-window repair, which re-scored the whole giant tour up to 200 times per call and used about half the GA's evaluations on R101.
- **Local search (GA option, off by default).** `local_search=True` improves a share `ls_rate` (default 0.2) of the children with relocate, swap and intra-route 2-opt (first improvement, each customer's 10 nearest neighbours), and writes the routes back as the child's giant tour. It is the GA's own code (`app/solvers/local_search.py`); the GA module still never imports OR-Tools or the hybrid (tested).
- **Hybrid (`algorithm="hybrid"`, own module).** Inside one total budget: OR-Tools for `ortools_share` (default 0.5, not tuned) with the audited defaults for that sub-budget, then the GA for the rest, starting from the OR-Tools tour plus 4 mutated copies. Local search is on by default. If OR-Tools finds nothing, the GA runs unseeded and the result says so; if the GA phase fails, the result says so. It is always labelled "hybrid".
- **GA time check after every child** (was once per generation), so local search cannot push a run past its budget.
- **Wall-clock guard.** API runs (and the comparison experiment) execute in one long-lived worker process. A run that has not answered within 1.5 x time limit + 5 s is killed and reported as `hard_timeout` (no routes, no metrics, never a success); the next run starts a fresh worker. Worker start-up is not charged to any run.
- **ruff** is now in `backend/requirements.txt`; settings in `ruff.toml` (line length 120, rules E/F/W/I).

## Evidence
`experiments/results/compare_2026-11-02/` (raw.csv, report.md). 240 runs, one at a time, through the guard, on Rohit's laptop (Python 3.14.7, OR-Tools 9.15.6755, commit a527bd4 plus the uncommitted P3 code): 6 methods x 10 instances (Solomon C101, R101, RC101, R201, RC201; CVRPLIB A-n32-k5, A-n80-k10, X-n101-k25; synthetic CVRP n=50, n=100) x budgets 3 s and 10 s x 2 seeds (the team chose 2 seeds to keep the run near 26 min). No hard timeouts; the longest run took 10.07 s on a 10 s budget.

Mean gap to BKS over feasible runs (benchmark instances only), solved / runs:

| Method | CVRP 3 s | CVRP 10 s | VRPTW 3 s | VRPTW 10 s |
| --- | --- | --- | --- | --- |
| OR-Tools (audited defaults) | 10/10, 3.88% | 10/10, 3.07% | 10/10, 3.15% | 10/10, 2.61% |
| GA, P1 version (no fleet repair) | 10/10, 14.17% | 10/10, 8.91% | **8/10**, 133.94% | **9/10**, 93.35% |
| GA + fleet repair | 10/10, 14.17% | 10/10, 9.03% | 10/10, 94.57% | 10/10, 77.40% |
| GA + fleet repair + local search | 10/10, 3.58% | 10/10, 2.26% | 10/10, 13.89% | 10/10, 11.67% |
| Hybrid, seed only | 10/10, 4.14% | 10/10, 3.67% | 10/10, 3.54% | 10/10, 3.12% |
| Hybrid, seed + local search | 10/10, 3.46% | 10/10, 2.44% | 10/10, 3.54% | 10/10, 2.88% |

## Findings
- **The R101 weak spot is fixed in the GA itself.** The P1 GA was infeasible on R101 in 3 of 4 runs here (35 routes for 25 vehicles at 3 s). With fleet repair, every GA run on every instance is feasible (R101: 25 routes). The hybrid is also feasible on R101 (20 to 21 routes), because OR-Tools' seed already fits the fleet.
- **Local search is the component that matters for the GA**: on VRPTW it cuts the GA's gap from about 77 to 95% down to 12 to 14%, and on CVRP from 9 to 14% down to 2 to 4%.
- **CVRP: GA + local search was better than OR-Tools on average** (2.26% vs 3.07% at 10 s), mainly on X-n101-k25 and A-n80-k10 at 10 s and on the n=100 synthetic instance. It is not uniform: on the n=50 synthetic instance at 3 s it was clearly worse (5.7% vs 0.4% to the best observed), and its two seeds differed by 9.5 points there. Three benchmark instances and two seeds are too few to claim a general win.
- **VRPTW: OR-Tools stays best or tied.** The hybrid matched OR-Tools on most instances, was slightly better on R101 and RC201 at 10 s (2.15% vs 2.52%, 2.82% vs 3.54%), and worse on R201 at 10 s (6.09% vs 4.26%) and RC201 at 3 s (4.78% vs 2.82%), where half the budget was taken from OR-Tools.
- **The hybrid's GA phase rarely improves the OR-Tools seed**: seed only 0/20 runs at 3 s and 3/20 at 10 s; seed + local search 5/20 and 9/20. Most of the hybrid's result is OR-Tools' work with half the time. With an untuned 50/50 split, the hybrid is not a clear improvement over OR-Tools alone at these budgets. This is reported as a negative result, not hidden.
- OR-Tools repeats gave identical results (spread 0), as in P2.

## Limits
- 10 instances, 2 seeds, budgets 3 and 10 s, at most 100 customers, one laptop. `ortools_share` and `ls_rate` were not tuned (tuning on these same instances would bias the comparison); a tuning study on separate instances would belong in P5.
- The hybrid is not yet in the frontend (API only); the API experiment endpoint still compares OR-Tools vs GA only.

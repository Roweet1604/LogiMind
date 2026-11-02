# OR-Tools audit report

Generated 2026-11-02T09:47:49+00:00 from raw.csv (1728 runs).
Machine: AMD64 Family 23 Model 96 Stepping 1, AuthenticAMD, 16 logical CPUs, Windows-11-10.0.26300-SP0. Python 3.14.7, OR-Tools 9.15.6755. Git commit 309177e.

Notes: synthetic instances are generated (labelled `synthetic:<n>`), not real data. `gap to BKS` uses the published best-known values in experiments/benchmarks/bks.csv. `gap to best observed` is against the best distance found anywhere in this audit, NOT a best-known value. OR-Tools has no seed: repeats re-run the same configuration; their differences come from the time limit. Gaps are averaged over feasible runs only; the `solved` column shows how many runs gave a feasible plan.

## Recommended configuration per problem and budget

| Problem | Budget (s) | Class | First solution | Metaheuristic | Mean gap to best observed % | Mean gap to BKS % | Note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CVRP | 1 | short | SAVINGS | GUIDED_LOCAL_SEARCH | 4.10 | 5.69 |  |
| CVRP | 3 | medium | SAVINGS | GUIDED_LOCAL_SEARCH | 2.46 | 3.73 |  |
| CVRP | 10 | long | PATH_CHEAPEST_ARC | GUIDED_LOCAL_SEARCH | 0.99 | 3.08 |  |
| VRPTW | 1 | short | PARALLEL_CHEAPEST_INSERTION | TABU_SEARCH | 1.60 | 3.17 |  |
| VRPTW | 3 | medium | PARALLEL_CHEAPEST_INSERTION | TABU_SEARCH | 1.07 | 2.62 |  |
| VRPTW | 10 | long | LOCAL_CHEAPEST_INSERTION | GUIDED_LOCAL_SEARCH | 0.61 | 2.15 |  |

## CVRP: every configuration at every budget

Cell = solved runs / runs, mean gap to best observed %, mean gap to BKS % (benchmarks only).

| First solution | Metaheuristic | 1 s | 3 s | 10 s |
| --- | --- | --- | --- | --- |
| LOCAL_CHEAPEST_INSERTION | GREEDY_DESCENT | 18/18, 13.53, 10.59 | 18/18, 13.53, 10.59 | 18/18, 13.53, 10.59 |
| LOCAL_CHEAPEST_INSERTION | GUIDED_LOCAL_SEARCH | 18/18, 7.63, 7.79 | 18/18, 5.97, 4.90 | 18/18, 3.43, 3.27 |
| LOCAL_CHEAPEST_INSERTION | SIMULATED_ANNEALING | 18/18, 12.87, 9.76 | 18/18, 11.08, 9.76 | 18/18, 11.08, 9.76 |
| LOCAL_CHEAPEST_INSERTION | TABU_SEARCH | 18/18, 9.93, 8.06 | 18/18, 7.53, 7.36 | 18/18, 2.85, 4.83 |
| PARALLEL_CHEAPEST_INSERTION | GREEDY_DESCENT | 18/18, 11.72, 9.09 | 18/18, 11.72, 9.09 | 18/18, 11.72, 9.09 |
| PARALLEL_CHEAPEST_INSERTION | GUIDED_LOCAL_SEARCH | 18/18, 6.83, 6.18 | 18/18, 5.19, 4.32 | 18/18, 3.18, 3.65 |
| PARALLEL_CHEAPEST_INSERTION | SIMULATED_ANNEALING | 18/18, 9.94, 9.09 | 18/18, 9.94, 9.09 | 18/18, 9.94, 9.09 |
| PARALLEL_CHEAPEST_INSERTION | TABU_SEARCH | 18/18, 8.96, 4.92 | 18/18, 8.64, 4.43 | 18/18, 8.19, 3.75 |
| PATH_CHEAPEST_ARC | GREEDY_DESCENT | 18/18, 5.20, 5.87 | 18/18, 5.20, 5.87 | 18/18, 5.20, 5.87 |
| PATH_CHEAPEST_ARC | GUIDED_LOCAL_SEARCH | 18/18, 4.37, 5.26 | 18/18, 3.05, 4.35 | 18/18, 0.99, 3.08 |
| PATH_CHEAPEST_ARC | SIMULATED_ANNEALING | 18/18, 4.92, 5.87 | 18/18, 4.80, 5.87 | 18/18, 4.80, 5.87 |
| PATH_CHEAPEST_ARC | TABU_SEARCH | 18/18, 5.20, 5.87 | 18/18, 5.98, 5.87 | 18/18, 5.14, 5.41 |
| SAVINGS | GREEDY_DESCENT | 18/18, 4.68, 6.55 | 18/18, 4.68, 6.55 | 18/18, 4.68, 6.55 |
| SAVINGS | GUIDED_LOCAL_SEARCH | 18/18, 4.10, 5.69 | 18/18, 2.46, 3.73 | 17/17, 1.78, 2.94 |
| SAVINGS | SIMULATED_ANNEALING | 18/18, 4.54, 6.55 | 18/18, 4.54, 6.55 | 18/18, 4.54, 6.55 |
| SAVINGS | TABU_SEARCH | 18/18, 4.29, 5.96 | 18/18, 4.00, 5.53 | 18/18, 2.65, 4.74 |

## VRPTW: every configuration at every budget

Cell = solved runs / runs, mean gap to best observed %, mean gap to BKS % (benchmarks only).

| First solution | Metaheuristic | 1 s | 3 s | 10 s |
| --- | --- | --- | --- | --- |
| LOCAL_CHEAPEST_INSERTION | GREEDY_DESCENT | 18/18, 4.02, 5.66 | 18/18, 4.02, 5.66 | 18/18, 4.02, 5.66 |
| LOCAL_CHEAPEST_INSERTION | GUIDED_LOCAL_SEARCH | 18/18, 3.67, 5.30 | 18/18, 2.27, 3.86 | 18/18, 0.61, 2.15 |
| LOCAL_CHEAPEST_INSERTION | SIMULATED_ANNEALING | 18/18, 2.91, 4.50 | 18/18, 2.82, 4.42 | 18/18, 2.82, 4.42 |
| LOCAL_CHEAPEST_INSERTION | TABU_SEARCH | 18/18, 3.77, 5.40 | 18/18, 2.82, 4.43 | 18/18, 0.89, 2.44 |
| PARALLEL_CHEAPEST_INSERTION | GREEDY_DESCENT | 18/18, 3.76, 5.36 | 18/18, 3.76, 5.36 | 18/18, 3.76, 5.36 |
| PARALLEL_CHEAPEST_INSERTION | GUIDED_LOCAL_SEARCH | 18/18, 3.33, 4.93 | 18/18, 2.34, 3.92 | 18/18, 0.72, 2.27 |
| PARALLEL_CHEAPEST_INSERTION | SIMULATED_ANNEALING | 18/18, 3.34, 4.93 | 18/18, 3.27, 4.87 | 18/18, 2.43, 4.01 |
| PARALLEL_CHEAPEST_INSERTION | TABU_SEARCH | 18/18, 1.60, 3.17 | 18/18, 1.07, 2.62 | 18/18, 0.93, 2.48 |
| PATH_CHEAPEST_ARC | GREEDY_DESCENT | 12/18, 0.46, 1.93 | 12/18, 0.46, 1.93 | 12/18, 0.46, 1.93 |
| PATH_CHEAPEST_ARC | GUIDED_LOCAL_SEARCH | 12/18, 0.43, 1.90 | 12/18, 0.39, 1.85 | 12/18, 0.17, 1.62 |
| PATH_CHEAPEST_ARC | SIMULATED_ANNEALING | 12/18, 0.30, 1.76 | 12/18, 0.30, 1.76 | 12/18, 0.30, 1.76 |
| PATH_CHEAPEST_ARC | TABU_SEARCH | 12/18, 0.43, 1.90 | 12/18, 0.27, 1.72 | 12/18, 0.15, 1.61 |
| SAVINGS | GREEDY_DESCENT | 18/18, 2.67, 4.28 | 18/18, 2.67, 4.28 | 18/18, 2.67, 4.28 |
| SAVINGS | GUIDED_LOCAL_SEARCH | 18/18, 2.32, 3.92 | 18/18, 2.09, 3.67 | 18/18, 1.14, 2.70 |
| SAVINGS | SIMULATED_ANNEALING | 18/18, 2.60, 4.20 | 18/18, 2.08, 3.66 | 18/18, 1.74, 3.32 |
| SAVINGS | TABU_SEARCH | 18/18, 2.21, 3.80 | 18/18, 1.71, 3.28 | 18/18, 0.85, 2.40 |

## Timing anomalies (excluded from all statistics above and below)

Runs whose wall clock exceeded 1.5x their budget. They stay in raw.csv.

| Instance | First solution | Metaheuristic | Budget (s) | Repeat | Runtime (s) | Started (UTC) |
| --- | --- | --- | --- | --- | --- | --- |
| A:A-n32-k5 | SAVINGS | GUIDED_LOCAL_SEARCH | 10 | 0 | 1506.7 | 2026-11-02T07:42:20+00:00 |

## Failures (runs without a feasible plan)

| Instance | First solution | Metaheuristic | Budget (s) | Failed runs | OR-Tools status |
| --- | --- | --- | --- | --- | --- |
| solomon:R101 | PATH_CHEAPEST_ARC | GREEDY_DESCENT | 1 | 3 | FAIL_TIMEOUT |
| solomon:R101 | PATH_CHEAPEST_ARC | GREEDY_DESCENT | 3 | 3 | FAIL_TIMEOUT |
| solomon:R101 | PATH_CHEAPEST_ARC | GREEDY_DESCENT | 10 | 3 | FAIL_TIMEOUT |
| solomon:R101 | PATH_CHEAPEST_ARC | GUIDED_LOCAL_SEARCH | 1 | 3 | FAIL_TIMEOUT |
| solomon:R101 | PATH_CHEAPEST_ARC | GUIDED_LOCAL_SEARCH | 3 | 3 | FAIL_TIMEOUT |
| solomon:R101 | PATH_CHEAPEST_ARC | GUIDED_LOCAL_SEARCH | 10 | 3 | FAIL_TIMEOUT |
| solomon:R101 | PATH_CHEAPEST_ARC | SIMULATED_ANNEALING | 1 | 3 | FAIL_TIMEOUT |
| solomon:R101 | PATH_CHEAPEST_ARC | SIMULATED_ANNEALING | 3 | 3 | FAIL_TIMEOUT |
| solomon:R101 | PATH_CHEAPEST_ARC | SIMULATED_ANNEALING | 10 | 3 | FAIL_TIMEOUT |
| solomon:R101 | PATH_CHEAPEST_ARC | TABU_SEARCH | 1 | 3 | FAIL_TIMEOUT |
| solomon:R101 | PATH_CHEAPEST_ARC | TABU_SEARCH | 3 | 3 | FAIL_TIMEOUT |
| solomon:R101 | PATH_CHEAPEST_ARC | TABU_SEARCH | 10 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | GREEDY_DESCENT | 1 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | GREEDY_DESCENT | 3 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | GREEDY_DESCENT | 10 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | GUIDED_LOCAL_SEARCH | 1 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | GUIDED_LOCAL_SEARCH | 3 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | GUIDED_LOCAL_SEARCH | 10 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | SIMULATED_ANNEALING | 1 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | SIMULATED_ANNEALING | 3 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | SIMULATED_ANNEALING | 10 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | TABU_SEARCH | 1 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | TABU_SEARCH | 3 | 3 | FAIL_TIMEOUT |
| solomon:RC101 | PATH_CHEAPEST_ARC | TABU_SEARCH | 10 | 3 | FAIL_TIMEOUT |

## Run-to-run variation (same configuration, repeated)

Spread = (worst - best) / best distance over the feasible repeats, in %.

| Problem | Metaheuristic | Budget (s) | Groups | Mean spread % | Max spread % | Groups with spread 0 |
| --- | --- | --- | --- | --- | --- | --- |
| CVRP | GREEDY_DESCENT | 1 | 24 | 0.000 | 0.000 | 24 |
| CVRP | GREEDY_DESCENT | 3 | 24 | 0.000 | 0.000 | 24 |
| CVRP | GREEDY_DESCENT | 10 | 24 | 0.000 | 0.000 | 24 |
| CVRP | GUIDED_LOCAL_SEARCH | 1 | 24 | 0.006 | 0.098 | 22 |
| CVRP | GUIDED_LOCAL_SEARCH | 3 | 24 | 0.278 | 5.908 | 22 |
| CVRP | GUIDED_LOCAL_SEARCH | 10 | 24 | 0.000 | 0.000 | 24 |
| CVRP | SIMULATED_ANNEALING | 1 | 24 | 0.079 | 1.889 | 23 |
| CVRP | SIMULATED_ANNEALING | 3 | 24 | 0.000 | 0.000 | 24 |
| CVRP | SIMULATED_ANNEALING | 10 | 24 | 0.000 | 0.000 | 24 |
| CVRP | TABU_SEARCH | 1 | 24 | 0.025 | 0.592 | 23 |
| CVRP | TABU_SEARCH | 3 | 24 | 0.000 | 0.000 | 24 |
| CVRP | TABU_SEARCH | 10 | 24 | 0.000 | 0.000 | 24 |
| VRPTW | GREEDY_DESCENT | 1 | 22 | 0.000 | 0.000 | 22 |
| VRPTW | GREEDY_DESCENT | 3 | 22 | 0.000 | 0.000 | 22 |
| VRPTW | GREEDY_DESCENT | 10 | 22 | 0.000 | 0.000 | 22 |
| VRPTW | GUIDED_LOCAL_SEARCH | 1 | 22 | 0.085 | 1.879 | 21 |
| VRPTW | GUIDED_LOCAL_SEARCH | 3 | 22 | 0.012 | 0.255 | 21 |
| VRPTW | GUIDED_LOCAL_SEARCH | 10 | 22 | 0.050 | 0.753 | 19 |
| VRPTW | SIMULATED_ANNEALING | 1 | 22 | 0.000 | 0.000 | 22 |
| VRPTW | SIMULATED_ANNEALING | 3 | 22 | 0.000 | 0.000 | 22 |
| VRPTW | SIMULATED_ANNEALING | 10 | 22 | 0.000 | 0.000 | 22 |
| VRPTW | TABU_SEARCH | 1 | 22 | 0.077 | 1.690 | 21 |
| VRPTW | TABU_SEARCH | 3 | 22 | 0.000 | 0.000 | 22 |
| VRPTW | TABU_SEARCH | 10 | 22 | 0.000 | 0.000 | 22 |

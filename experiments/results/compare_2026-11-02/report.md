# Engine comparison and ablation (P3)

Generated 2026-11-02T11:04:54+00:00 from raw.csv (240 runs). Machine: AMD64 Family 23 Model 96 Stepping 1, AuthenticAMD, 16 logical CPUs. Python 3.14.7, OR-Tools 9.15.6755. Git commit a527bd4.

Equal-clock rule: every method gets the same total wall-clock budget on the same instance (the hybrid's OR-Tools phase is inside its budget). Gaps are averaged over feasible runs only; `solved` shows feasible runs / runs. `gap to BKS` uses published best-known values (benchmarks only); `gap to best observed` is against the best distance found in this experiment (not a best-known value). Synthetic instances are generated. OR-Tools has no seed: its repeats are re-runs.

Methods: `ortools` = OR-Tools (audited defaults); `ga_nofix` = GA, P1 version (no fleet repair); `ga` = GA + fleet repair; `ga_ls` = GA + fleet repair + local search; `hybrid_seed` = Hybrid: OR-Tools seed, no local search; `hybrid_seed_ls` = Hybrid: OR-Tools seed + local search.

## CVRP

Cell = solved / runs, mean gap to BKS %, mean gap to best observed %.

| Method | 3 s | 10 s |
| --- | --- | --- |
| ortools | 10/10, 3.88, 3.00 | 10/10, 3.07, 1.26 |
| ga_nofix | 10/10, 14.17, 16.91 | 10/10, 8.91, 9.66 |
| ga | 10/10, 14.17, 16.93 | 10/10, 9.03, 9.64 |
| ga_ls | 10/10, 3.58, 2.21 | 10/10, 2.26, 0.28 |
| hybrid_seed | 10/10, 4.14, 3.57 | 10/10, 3.67, 2.84 |
| hybrid_seed_ls | 10/10, 3.46, 3.08 | 10/10, 2.44, 2.07 |

## VRPTW

Cell = solved / runs, mean gap to BKS %, mean gap to best observed %.

| Method | 3 s | 10 s |
| --- | --- | --- |
| ortools | 10/10, 3.15, 0.75 | 10/10, 2.61, 0.23 |
| ga_nofix | 8/10, 133.94, 128.52 | 9/10, 93.35, 88.88 |
| ga | 10/10, 94.57, 89.96 | 10/10, 77.40, 73.28 |
| ga_ls | 10/10, 13.89, 11.18 | 10/10, 11.67, 9.01 |
| hybrid_seed | 10/10, 3.54, 1.13 | 10/10, 3.12, 0.72 |
| hybrid_seed_ls | 10/10, 3.54, 1.13 | 10/10, 2.88, 0.49 |

## Per instance: solved runs and mean routes used (vehicle limit in brackets)

| Instance | Budget (s) | ortools | ga_nofix | ga | ga_ls | hybrid_seed | hybrid_seed_ls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A:A-n32-k5 | 3 | 2/2, 5.0 (5) | 2/2, 5.0 (5) | 2/2, 5.0 (5) | 2/2, 5.0 (5) | 2/2, 5.0 (5) | 2/2, 5.0 (5) |
| A:A-n32-k5 | 10 | 2/2, 5.0 (5) | 2/2, 5.0 (5) | 2/2, 5.0 (5) | 2/2, 5.0 (5) | 2/2, 5.0 (5) | 2/2, 5.0 (5) |
| A:A-n80-k10 | 3 | 2/2, 10.0 (10) | 2/2, 10.0 (10) | 2/2, 10.0 (10) | 2/2, 10.0 (10) | 2/2, 10.0 (10) | 2/2, 10.0 (10) |
| A:A-n80-k10 | 10 | 2/2, 10.0 (10) | 2/2, 10.0 (10) | 2/2, 10.0 (10) | 2/2, 10.0 (10) | 2/2, 10.0 (10) | 2/2, 10.0 (10) |
| X:X-n101-k25 | 3 | 2/2, 26.0 (100) | 2/2, 27.5 (100) | 2/2, 27.5 (100) | 2/2, 28.0 (100) | 2/2, 26.0 (100) | 2/2, 28.0 (100) |
| X:X-n101-k25 | 10 | 2/2, 27.0 (100) | 2/2, 27.5 (100) | 2/2, 27.5 (100) | 2/2, 28.0 (100) | 2/2, 26.0 (100) | 2/2, 28.0 (100) |
| solomon:C101 | 3 | 2/2, 10.0 (25) | 2/2, 24.5 (25) | 2/2, 23.0 (25) | 2/2, 10.5 (25) | 2/2, 10.0 (25) | 2/2, 10.0 (25) |
| solomon:C101 | 10 | 2/2, 10.0 (25) | 2/2, 21.0 (25) | 2/2, 22.5 (25) | 2/2, 10.0 (25) | 2/2, 10.0 (25) | 2/2, 10.0 (25) |
| solomon:R101 | 3 | 2/2, 20.0 (25) | 0/2, 35.0 (25) | 2/2, 25.0 (25) | 2/2, 24.0 (25) | 2/2, 20.0 (25) | 2/2, 20.0 (25) |
| solomon:R101 | 10 | 2/2, 21.0 (25) | 1/2, 25.5 (25) | 2/2, 25.0 (25) | 2/2, 23.5 (25) | 2/2, 20.0 (25) | 2/2, 21.0 (25) |
| solomon:R201 | 3 | 2/2, 6.0 (25) | 2/2, 24.0 (25) | 2/2, 22.0 (25) | 2/2, 15.5 (25) | 2/2, 6.0 (25) | 2/2, 6.0 (25) |
| solomon:R201 | 10 | 2/2, 6.0 (25) | 2/2, 21.5 (25) | 2/2, 20.5 (25) | 2/2, 15.0 (25) | 2/2, 6.0 (25) | 2/2, 6.5 (25) |
| solomon:RC101 | 3 | 2/2, 17.0 (25) | 2/2, 25.0 (25) | 2/2, 25.0 (25) | 2/2, 20.5 (25) | 2/2, 17.0 (25) | 2/2, 17.0 (25) |
| solomon:RC101 | 10 | 2/2, 17.0 (25) | 2/2, 24.5 (25) | 2/2, 25.0 (25) | 2/2, 19.0 (25) | 2/2, 17.0 (25) | 2/2, 17.0 (25) |
| solomon:RC201 | 3 | 2/2, 6.0 (25) | 2/2, 24.0 (25) | 2/2, 23.0 (25) | 2/2, 17.0 (25) | 2/2, 6.0 (25) | 2/2, 6.0 (25) |
| solomon:RC201 | 10 | 2/2, 7.5 (25) | 2/2, 19.0 (25) | 2/2, 23.0 (25) | 2/2, 15.5 (25) | 2/2, 6.0 (25) | 2/2, 6.0 (25) |
| synthetic:100 | 3 | 2/2, 10.0 (14) | 2/2, 11.0 (14) | 2/2, 11.0 (14) | 2/2, 11.0 (14) | 2/2, 10.0 (14) | 2/2, 10.0 (14) |
| synthetic:100 | 10 | 2/2, 10.0 (14) | 2/2, 11.0 (14) | 2/2, 11.0 (14) | 2/2, 11.0 (14) | 2/2, 10.0 (14) | 2/2, 10.0 (14) |
| synthetic:50 | 3 | 2/2, 5.0 (8) | 2/2, 5.5 (8) | 2/2, 5.5 (8) | 2/2, 5.0 (8) | 2/2, 5.0 (8) | 2/2, 5.0 (8) |
| synthetic:50 | 10 | 2/2, 5.0 (8) | 2/2, 5.0 (8) | 2/2, 5.0 (8) | 2/2, 5.0 (8) | 2/2, 5.0 (8) | 2/2, 5.0 (8) |

## Did the GA phase improve the OR-Tools seed?

| Method | Budget (s) | Runs | Improved over seed |
| --- | --- | --- | --- |
| hybrid_seed | 3 | 20 | 0 |
| hybrid_seed | 10 | 20 | 3 |
| hybrid_seed_ls | 3 | 20 | 5 |
| hybrid_seed_ls | 10 | 20 | 9 |

## Hard timeouts and timing anomalies (excluded from the tables above)

None.

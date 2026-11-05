# Engine comparison and ablation (P3)

Generated 2026-11-05T06:55:36+00:00 from raw.csv (216 runs). Machine: AMD64 Family 23 Model 96 Stepping 1, AuthenticAMD, 16 logical CPUs. Python 3.14.7, OR-Tools 9.15.6755. Git commit 5598d08.

Equal-clock rule: every method gets the same total wall-clock budget on the same instance (the hybrid's OR-Tools phase is inside its budget). Gaps are averaged over feasible runs only; `solved` shows feasible runs / runs. `gap to BKS` uses published best-known values (benchmarks only); `gap to best observed` is against the best distance found in this experiment (not a best-known value). Synthetic instances are generated. OR-Tools has no seed: its repeats are re-runs.

Methods: `ortools` = OR-Tools (audited defaults); `ga_nofix` = GA, P1 version (no fleet repair); `ga` = GA + fleet repair; `ga_ls` = GA + fleet repair + local search; `hybrid_seed` = Hybrid: OR-Tools seed, no local search; `hybrid_seed_ls` = Hybrid: OR-Tools seed + local search.

## CVRP

Cell = solved / runs, mean gap to BKS %, mean gap to best observed %.

| Method | 3 s |
| --- | --- |
| ortools | 36/36, 4.88, 2.81 |
| ga_nofix | not run |
| ga | not run |
| ga_ls | 35/36, 2.84, 0.85 |
| hybrid_seed | not run |
| hybrid_seed_ls | 36/36, 3.53, 1.51 |

## VRPTW

Cell = solved / runs, mean gap to BKS %, mean gap to best observed %.

| Method | 3 s |
| --- | --- |
| ortools | 36/36, 4.51, 0.22 |
| ga_nofix | not run |
| ga | not run |
| ga_ls | 36/36, 15.74, 11.06 |
| hybrid_seed | not run |
| hybrid_seed_ls | 36/36, 4.66, 0.36 |

## Per instance: solved runs and mean routes used (vehicle limit in brackets)

| Instance | Budget (s) | ortools | ga_nofix | ga | ga_ls | hybrid_seed | hybrid_seed_ls |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A:A-n33-k5 | 3 | 3/3, 5.0 (5) | - | - | 3/3, 5.0 (5) | - | 3/3, 5.0 (5) |
| A:A-n37-k5 | 3 | 3/3, 5.0 (5) | - | - | 3/3, 5.0 (5) | - | 3/3, 5.0 (5) |
| A:A-n39-k6 | 3 | 3/3, 6.0 (6) | - | - | 3/3, 6.0 (6) | - | 3/3, 6.0 (6) |
| A:A-n45-k6 | 3 | 3/3, 6.0 (6) | - | - | 2/3, 6.3 (6) | - | 3/3, 6.0 (6) |
| A:A-n48-k7 | 3 | 3/3, 7.0 (7) | - | - | 3/3, 7.0 (7) | - | 3/3, 7.0 (7) |
| A:A-n53-k7 | 3 | 3/3, 7.0 (7) | - | - | 3/3, 7.0 (7) | - | 3/3, 7.0 (7) |
| A:A-n55-k9 | 3 | 3/3, 9.0 (9) | - | - | 3/3, 9.0 (9) | - | 3/3, 9.0 (9) |
| A:A-n63-k10 | 3 | 3/3, 10.0 (10) | - | - | 3/3, 10.0 (10) | - | 3/3, 10.0 (10) |
| A:A-n69-k9 | 3 | 3/3, 9.0 (9) | - | - | 3/3, 9.0 (9) | - | 3/3, 9.0 (9) |
| X:X-n106-k14 | 3 | 3/3, 14.0 (105) | - | - | 3/3, 14.0 (105) | - | 3/3, 14.0 (105) |
| X:X-n110-k13 | 3 | 3/3, 13.0 (109) | - | - | 3/3, 13.3 (109) | - | 3/3, 14.0 (109) |
| X:X-n120-k6 | 3 | 3/3, 6.0 (119) | - | - | 3/3, 6.0 (119) | - | 3/3, 6.0 (119) |
| solomon:C102 | 3 | 3/3, 10.0 (25) | - | - | 3/3, 11.0 (25) | - | 3/3, 10.0 (25) |
| solomon:C105 | 3 | 3/3, 10.0 (25) | - | - | 3/3, 10.3 (25) | - | 3/3, 10.0 (25) |
| solomon:C202 | 3 | 3/3, 3.0 (25) | - | - | 3/3, 6.3 (25) | - | 3/3, 3.0 (25) |
| solomon:C205 | 3 | 3/3, 3.0 (25) | - | - | 3/3, 6.0 (25) | - | 3/3, 3.0 (25) |
| solomon:R102 | 3 | 3/3, 18.0 (25) | - | - | 3/3, 21.0 (25) | - | 3/3, 18.0 (25) |
| solomon:R105 | 3 | 3/3, 15.0 (25) | - | - | 3/3, 20.7 (25) | - | 3/3, 15.0 (25) |
| solomon:R110 | 3 | 3/3, 13.0 (25) | - | - | 3/3, 14.7 (25) | - | 3/3, 14.3 (25) |
| solomon:R202 | 3 | 3/3, 6.0 (25) | - | - | 3/3, 14.0 (25) | - | 3/3, 6.0 (25) |
| solomon:RC102 | 3 | 3/3, 16.0 (25) | - | - | 3/3, 18.7 (25) | - | 3/3, 16.0 (25) |
| solomon:RC105 | 3 | 3/3, 17.0 (25) | - | - | 3/3, 19.3 (25) | - | 3/3, 17.0 (25) |
| solomon:RC202 | 3 | 3/3, 6.0 (25) | - | - | 3/3, 13.3 (25) | - | 3/3, 6.0 (25) |
| solomon:RC205 | 3 | 3/3, 7.0 (25) | - | - | 3/3, 14.0 (25) | - | 3/3, 7.0 (25) |

## Did the GA phase improve the OR-Tools seed?

| Method | Budget (s) | Runs | Improved over seed |
| --- | --- | --- | --- |
| hybrid_seed_ls | 3 | 72 | 31 |

## Hard timeouts and timing anomalies (excluded from the tables above)

None.

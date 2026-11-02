# 0005: OR-Tools defaults per problem type and budget class (P2 audit)

Date: 2 Nov 2026. Status: accepted (P2).

## Evidence
`experiments/results/ortools_audit_2026-11-02/` (raw.csv, report.md, manifest.json). 1728 runs, one at a time, on Rohit's laptop (AMD 16 logical CPUs, Windows 11, Python 3.14.7, OR-Tools 9.15.6755, commit 309177e):
4 first-solution strategies (PATH_CHEAPEST_ARC, SAVINGS, PARALLEL_CHEAPEST_INSERTION, LOCAL_CHEAPEST_INSERTION) x 4 metaheuristics (GREEDY_DESCENT, GUIDED_LOCAL_SEARCH, SIMULATED_ANNEALING, TABU_SEARCH) x budgets 1 / 3 / 10 s x 3 repeats, on 12 instances: Solomon C101, C201, R101, R201, RC101, RC201 (VRPTW); CVRPLIB A-n32-k5, A-n60-k9, A-n80-k10, X-n101-k25; synthetic CVRP n=50 and n=100 (generated, labelled).

## Decision
Selection rule, fixed in code before the results were read (`audit.recommend`): per problem type and budget, among configurations that produced a feasible plan in **every** run, take the lowest mean gap to the best distance observed in the audit. Budget classes: short <= 2 s, medium <= 6 s, long > 6 s.

| Problem | short (tested at 1 s) | medium (3 s) | long (10 s) |
| --- | --- | --- | --- |
| CVRP | SAVINGS + GUIDED_LOCAL_SEARCH | SAVINGS + GUIDED_LOCAL_SEARCH | PATH_CHEAPEST_ARC + GUIDED_LOCAL_SEARCH |
| VRPTW | PARALLEL_CHEAPEST_INSERTION + TABU_SEARCH | PARALLEL_CHEAPEST_INSERTION + TABU_SEARCH | LOCAL_CHEAPEST_INSERTION + GUIDED_LOCAL_SEARCH |

`solve_ortools` uses this table when no strategy is given; an explicit choice always wins. The run config records `budget_class` and `search_choice` (`audited_default`, `explicit` or `partly_audited_default`). The API now defaults to `null` (= audited default), and the UI offers "Audited default (by budget)" as the first option.

## Main findings (do not hide the budget dependence)
- **The old default fails on tight windows.** PATH_CHEAPEST_ARC found no solution for R101 and RC101 at every budget with every metaheuristic (72 failed runs, status FAIL_TIMEOUT). More time does not help: the start method gets stuck. Its averages on the other four Solomon instances look best, but only because the two hardest instances are missing from them (survivorship). The rule therefore excludes it.
- **Quality depends strongly on the budget, and the best configuration changes with it.** Mean gap to BKS for the chosen CVRP default (SAVINGS + GLS): 5.69% at 1 s, 3.73% at 3 s, 2.94% at 10 s (gap to BKS, benchmark instances only). LOCAL_CHEAPEST_INSERTION + GLS on VRPTW: 5.30%, 3.86%, 2.15%; it ranks 9th of the 12 always-feasible configurations at 1 s and 1st at 10 s, which is why the VRPTW default changes between classes. GREEDY_DESCENT stops at its first local optimum (mean 0.4 to 0.7 s), so more budget changes nothing. On CVRP, SIMULATED_ANNEALING gave identical mean gaps at 3 and 10 s for every start strategy.
- **Close calls.** At 10 s on CVRP, PATH_CHEAPEST_ARC + GLS wins on gap to best observed (0.99% vs 1.78%; SAVINGS has 17 runs here after the anomaly exclusion), but SAVINGS + GLS is better against the published BKS on the four benchmark instances (2.94% vs 3.08%). We kept the pre-declared rule. Differences under ~0.5 percentage point are within what this small sample can resolve.
- **Run-to-run variation.** OR-Tools routing has no seed parameter; repeats re-run the same configuration. Most repeat groups gave identical distances. The largest spread was 5.9% (CVRP, GLS, 3 s), and 0 to 1.9% elsewhere. Repeats can differ because the time limit cuts the search at a slightly different point.

## Limits
- At most 100 customers, 6 time-window instances, one laptop, budgets up to 10 s. Budgets above 10 s use the "long" entry without having been tested there. P5's selector should treat the budget as a feature rather than trust this table at other sizes.
- No synthetic time-window instances yet (the generator has no time windows; planned with the P5 dataset generator).
- **Interrupted run.** The audit was stopped once by Claude Code because the system was low on memory (after 308 runs) and resumed with `--resume`. Just before that stop, one run (A-n32-k5, SAVINGS + GLS, 10 s, repeat 0) took 1506.7 s; the machine had most likely frozen. It stays in raw.csv but is excluded from all statistics as a timing anomaly (> 1.5x budget) and listed in the report. The manifest's `created_at` is the resume time (the script overwrote it then; fixed since), as its `notes` field says.

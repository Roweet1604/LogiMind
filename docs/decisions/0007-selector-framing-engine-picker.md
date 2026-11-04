# 0007: Selector framing: build the engine picker (P5)

Date: 4 Nov 2026. Status: accepted (P5, decided unattended by Claude Code under the team's rule).

## Rule given by the team
If one engine wins 80% or more of the cases in the existing results, do not build an engine picker; build an OR-Tools-settings selector instead. Otherwise build the engine picker.

## Evidence (no new solver runs)
`experiments/selector_win_counts.py` on `experiments/results/compare_2026-11-02/raw.csv` (P3, 240 runs). Engines: OR-Tools (audited defaults), GA + fleet repair + local search (`ga_ls`), hybrid (`hybrid_seed_ls`, the hybrid's default). A case = instance x budget (10 instances x 3 s / 10 s = 20 cases). Score = mean distance over the 2 seeds, only if every run was feasible (all were). Engines within 0.01% of the best are tied. Output: `experiments/results/selector_2026-11-04/engine_wins_*`.

| Engine | wins or ties (of 20) | sole wins |
| --- | --- | --- |
| OR-Tools | 11 (55%) | 4 |
| GA + local search | 8 (40%) | 5 |
| Hybrid | 11 (55%) | 4 |
| (7 cases were ties) | | |

By problem: CVRP (10 cases) GA + LS wins or ties 7, OR-Tools 3, hybrid 4; VRPTW (10 cases) OR-Tools 8, hybrid 7, GA + LS 1. By budget: at 3 s OR-Tools 7 of 10, at 10 s GA + LS and hybrid 5 each, OR-Tools 4.

The OR-Tools audit (`ortools_audit_2026-11-02`) contains only OR-Tools runs, so it cannot count engine wins. Its per-case view (`ortools_best_setting_by_case.csv`) shows the best start/search pair changes with the instance and budget, and that 4 of 16 settings fail on R101 and RC101 at every budget; the audited defaults (0005) already avoid those failures.

## Decision
No engine reaches 80% (the best is 55%, counting ties as wins). **We build the engine picker** (OR-Tools vs hybrid vs GA + local search), with the time budget and time-window tightness as features. The OR-Tools-settings selector is not built in P5; the audited per-budget defaults stay in place.

## Caveats
20 cases, 2 seeds, one laptop. The win counts are close, so the picker can only be expected to beat "always OR-Tools" by a small margin, if at all; the evaluation reports this either way (see `docs/model_card_selector.md`).

## Outcome (added after the P5 dataset run, same day)
Dataset: 324 synthetic runs (10.2 min). Under leave-one-family-out CV, the served regret-tree model has a mean regret of 0.52%. The planned classifier has 0.94%, always-hybrid 0.63% and always-OR-Tools 1.34%. Under leave-one-size-out CV, the regret trees have 1.06% and always-hybrid 0.63%. So the selector is **not a proven improvement over always using the hybrid**. We serve the regret trees because they did best on the team's chosen CV (grouped by family). We chose them after seeing the results, and say so. Full details are in `docs/model_card_selector.md`.

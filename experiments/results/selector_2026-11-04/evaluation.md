# Selector evaluation (SYNTHETIC data, 324 runs, 108 cases)

Label = engine with the lowest distance among feasible runs (ties -> OR-Tools, then hybrid).
Regret = % extra distance over the best engine on the case. A failed choice (no feasible plan) is counted under 'Failed choices' and left out of the regret means.

Label counts: {'ortools': 61, 'ga_ls': 24, 'hybrid': 23}

## Leave-one-family-out CV (uniform / clustered / mixed)

| Strategy | Accuracy | Mean regret % | Max regret % | Failed choices |
| --- | --- | --- | --- | --- |
| selector | 0.472 | 0.94 | 7.27 | 0 |
| selector_regret_model | 0.426 | 0.52 | 5.87 | 0 |
| always_ortools | 0.565 | 1.34 | 11.75 | 0 |
| always_hybrid | 0.213 | 0.63 | 8.67 | 0 |
| always_ga_ls | 0.222 | 2.67 | 25.96 | 0 |
| random | 0.330 | 1.55 | - | 0 |
| oracle | 1.000 | 0.00 | 0.00 | 0 |

Per fold: clustered: acc 0.306, regret 1.02%; mixed: acc 0.528, regret 0.45%; uniform: acc 0.583, regret 1.34%

## Leave-one-size-out CV (20 / 50 / 80 customers)

| Strategy | Accuracy | Mean regret % | Max regret % | Failed choices |
| --- | --- | --- | --- | --- |
| selector | 0.500 | 0.93 | 12.97 | 0 |
| selector_regret_model | 0.389 | 1.06 | 15.49 | 0 |
| always_ortools | 0.565 | 1.34 | 11.75 | 0 |
| always_hybrid | 0.213 | 0.63 | 8.67 | 0 |
| always_ga_ls | 0.222 | 2.67 | 25.96 | 0 |
| random | 0.330 | 1.55 | - | 0 |
| oracle | 1.000 | 0.00 | 0.00 | 0 |

Per fold: 20: acc 0.667, regret 0.72%; 50: acc 0.333, regret 0.75%; 80: acc 0.500, regret 1.32%

## Feature importances (tree fitted on all cases)

demand_fill 0.60, depot_offset_rel 0.21, n_customers 0.11, nn_dist_cv 0.06, nn_dist_rel 0.02

Longest run: 3.00 s.

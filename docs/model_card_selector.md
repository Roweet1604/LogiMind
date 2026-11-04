# Model card: LogiMind engine selector (`engine=auto`), P5

Date: 4 Nov 2026. Code: `backend/app/selector/`. Evidence: `experiments/results/selector_2026-11-04/`.

## What it does
For one instance and one total time budget, it picks one of three engines: OR-Tools (audited defaults), the hybrid (OR-Tools seed + GA with local search, labelled as a hybrid), or the GA with local search. It does not create or change routes. The chosen engine's plan still goes through the independent validator. The reply gives the predicted extra distance for each engine and the tree rule behind the choice.

## Why an engine picker (decision 0007)
In the P3 comparison no engine won 80% or more of the cases (best: 55%, counting ties as wins), so under the team's rule we built the engine picker, not an OR-Tools-settings selector.

## Model
- Features (12, no solver calls; `features.py`): number of customers, budget, log budget, budget per customer, has time windows, mean window width / horizon, share of tight windows (< 20% of the horizon), service time / horizon, demand fill (total demand / fleet capacity), nearest-neighbour distance / mean depot distance (a clustering measure), its coefficient of variation, and depot offset from the customer centroid.
- **Served model: per-engine regret trees.** One regression tree per engine (depth 3, at least 4 cases per leaf, random_state 0) predicts that engine's regret. Regret = % extra distance over the best of the three engines on that case. The engine with the lowest predicted regret wins; ties go to OR-Tools, then the hybrid.
- Also evaluated: a decision-tree classifier that predicts the best engine (same depth). We planned to use it first. The regret trees were added **after** seeing the classifier's first CV result. Choosing between the two after looking at CV results makes the reported numbers somewhat optimistic.
- The model is trained from the committed CSV when it is first used (deterministic, a few milliseconds). No pickle is stored. If the CSV is missing, `engine=auto` uses OR-Tools and says so.

## Training data (SYNTHETIC)
- 108 cases = 54 synthetic instances x budgets 1 s and 3 s. The instances are 3 families (uniform, clustered, mixed) x sizes 20 / 50 / 80 x time-window tightness none / loose (40% of the horizon) / tight (10%) x 2 seeds, from our own generator (`generator.py`). They are not Solomon data.
- Each engine ran once per case. That is 324 runs, one at a time, through the wall-clock guard, with an equal total budget. They took 10.2 min against an estimate of 12.4 min. All 324 runs were feasible and none timed out. The longest took 3.00 s. Every row stores the seed, configuration, versions and git commit (`dataset_raw.csv`, `dataset_manifest.json`).
- Labels (best engine): OR-Tools 61, GA + LS 24, hybrid 23. OR-Tools was best on 29 of 36 tight-window cases. On plain CVRP at 3 s, GA + LS was best on 9 of 18.

## Evaluation (`evaluation.md`)
Leave-one-family-out CV (train on two families, test on the third). This is the main test.

| Strategy | Accuracy | Mean regret | Max regret |
| --- | --- | --- | --- |
| Regret trees (served) | 0.43 | **0.52%** | 5.87% |
| Classifier | 0.47 | 0.94% | 7.27% |
| Always OR-Tools | 0.56 | 1.34% | 11.75% |
| Always hybrid | 0.21 | 0.63% | 8.67% |
| Always GA + LS | 0.22 | 2.67% | 25.96% |
| Random (mean of 200 draws) | 0.33 | 1.55% | - |

Leave-one-size-out CV (train on two sizes, test on the third): regret trees 1.06%, classifier 0.93%, always hybrid 0.63%, always OR-Tools 1.34%.

## Honest reading
- The selector **is not a proven improvement**. It beats "always hybrid" by only 0.11 points of regret on the family split, and it is worse than "always hybrid" on the size split. Both learned models beat "always OR-Tools" and random on regret in both splits.
- Accuracy is a poor guide here. The hybrid is rarely the single best engine but is almost always close, so "always hybrid" has low accuracy and low regret.
- The trees did not use the budget feature: the same instance gets the same choice at 1 s and 3 s. With only two budgets, the data cannot show how the choice depends on the budget. P2 showed that the best OR-Tools settings do change with the budget.
- The most important features are demand fill and depot offset. In this generator, demand fill mostly stands in for time-window tightness, because tight instances get a larger fleet.

## Limits and intended use
- Trained only on synthetic instances: up to 80 customers, budgets 1 to 3 s, one seed per engine and case, one laptop (AMD, Windows 11, Python 3.14.7, OR-Tools 9.15.6755). For an instance outside the training range, the explanation adds a caution.
- Not checked on Solomon or CVRPLIB instances, or on real orders.
- Use: a default for `engine=auto` that can be explained. Do not use it to claim that one engine is better. Fair comparisons stay in the P3/P10 benchmark runs.
- Next: more seeds, budgets of 1/3/10 s and sizes up to 100+. Then re-run `experiments/selector_dataset.py` and `selector_train_eval.py`, and keep the served model only if it still beats "always hybrid".

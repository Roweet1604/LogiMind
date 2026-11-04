# P7 replanning experiment (SYNTHETIC data)

Run: `python experiments/replan_experiment.py` on 4 Nov 2026, Rohit's laptop (Python 3.14.7, OR-Tools 9.15.6755). Estimated 2.7 min, took 2.1 min. Runs went one at a time through the wall-clock guard. Raw rows: `raw.csv`; settings: `manifest.json`; log: `run.log`.

Set-up: 6 synthetic instances (uniform / clustered / mixed x no windows / loose windows, 40 customers, seed 11). Each got a base plan from OR-Tools (2 s, all feasible). The first third of every route counts as completed and stays frozen. Events: breakdown of the busiest vehicle, a failed delivery (retry) of its next stop, and an urgent order. Each event was replanned with OR-Tools warm (current plan as the initial assignment) and cold, at 0.5 s and 2 s. Then an urgent order before dispatch (nothing frozen) was replanned with the GA + local search, seeded with the current plan and unseeded. One seed throughout.

## Results
- **96 of 96 replans were feasible** (validator + frozen-stop check), with 0 frozen-stop violations. OR-Tools accepted the warm start in 36 of 36 runs.
- Distance, warm vs cold (mean % difference, negative = warm shorter; 6 instances per cell):

| Engine / event | 0.5 s | 2 s |
| --- | --- | --- |
| OR-Tools, breakdown | -2.61% (warm better 5, cold better 1) | +0.22% (2 / 2) |
| OR-Tools, failed delivery | -4.95% (5 / 0) | -0.45% (2 / 1) |
| OR-Tools, urgent order | -5.33% (6 / 0) | -2.01% (5 / 0) |
| GA + LS, urgent order before dispatch | -2.19% (5 / 1) | -0.41% (3 / 2) |

- **Stability:** with a warm start, fewer unfinished stops change vehicle. For OR-Tools at 0.5 s the mean was 0 to 11 stops warm vs 7 to 16 cold. For the GA this count is not meaningful, because GA routes are given to vehicles in order.
- **Time from disruption to a validated plan** is about the time budget (0.5 s or 2 s), because both engines use their whole budget. OR-Tools found its first feasible solution in 6 to 9 ms, so a much shorter budget would still give a feasible plan. That was not measured for quality.

## Reading
- Warm start clearly helps at short budgets (0.5 s) and makes no clear difference at 2 s. **Negative result:** for breakdowns at 2 s, warm was slightly worse on average (+0.22%).
- 6 instances, 40 customers, one seed, one laptop: indicative only. These numbers must not be quoted as general results.

# LogiMind progress

Last updated: 4 Nov 2026, P5 done (unattended session). Current phase: **P6 in progress** (see the end of this file for the full handoff).

## Done and verified
### Phase 0
- `docs/context/` assembled and committed; baseline read and audited; CLAUDE.md, PLAN.md, decision records 0001 and 0002.
### Phase 1 (time windows + public benchmarks)
- **Baseline migrated** unchanged to `backend/`, `frontend/`, `experiments/` (own commit). Verified: 54 backend tests and 13 frontend tests passed right after the copy.
- **Time windows in the model:** ready/due/service times per customer, depot opening hours, `time_per_distance`. Plain CVRP ids unchanged (tested against ids from the untouched baseline).
- **Validator 1.1:** late stops and late depot returns, with total lateness. **Metrics:** time-window violations, lateness, waiting, route durations; new CSV columns.
- **OR-Tools:** hard time windows (Time dimension, conservative integer rounding).
- **GA:** lateness penalty in the split + repair move (latest customer, or a customer from the shortest route when there are too many routes) + due-time seeding.
- **API:** time-window fields on `POST /api/instances`; `GET /api/benchmarks`, `POST /api/benchmarks/{set}/{name}`.
- **Benchmarks:** parsers for Solomon/Homberger text and TSPLIB CVRP files and `.sol` solutions. `fetch_benchmarks.py` downloads from CVRPLIB (2 Nov 2026): all 56 Solomon, all 27 Set A, and the 10 smallest Set X instances. `bks.csv` holds 93 best-known values with source URL and date. Files are not committed (see SOURCES.md, decision 0004).
- **Verified against CVRPLIB:** all 93 published best-known solutions pass our validator, and our recomputed distance equals the published cost exactly (max difference 0.0).
- **Tests:** backend **90 passed** (54 baseline + 36 new, incl. 3 that use the downloaded files), run on 2 Nov 2026 with Python 3.14.7 / OR-Tools 9.15.6755. Frontend 13 passed (baseline, unchanged since).
- `experiments/run_benchmarks.py` smoke run works (10 customers, 1 s).
- **Re-verified in a new session (2 Nov 2026):** backend 90 passed (4 library deprecation warnings), frontend 13 passed, benchmark smoke run OK. No code changed; P1 was not redone.

### Phase 2 (OR-Tools audit)
- **Audit tool:** `backend/app/benchmarks/audit.py` (grid, per-run rows, analysis) and `experiments/ortools_audit.py` (CLI with `--estimate-only`, `--resume`, `--analyze-only`). Runs strictly one at a time. Every row stores configuration, budget, repeat, OR-Tools status, build/search time, gap to BKS (benchmarks only), Python/OR-Tools/NumPy versions, machine and git commit.
- **OR-Tools has no seed parameter**, so "seeds" are repeats of the same configuration (recorded in every row as `seed_note`).
- **Full grid run:** 4 start strategies x 4 metaheuristics x 1/3/10 s x 3 repeats on 12 instances (6 Solomon, 4 CVRPLIB, 2 synthetic CVRP) = 1728 runs. Results committed in `experiments/results/ortools_audit_2026-11-02/` (raw.csv, report.md, summary/variation/recommendations CSVs, manifest).
- **Interrupted once:** Claude Code stopped the audit after 308 runs because the system was low on memory; it was resumed with `--resume`. One run (A-n32-k5, SAVINGS + GLS, 10 s) took 1506.7 s just before the stop (machine most likely frozen); it is kept in raw.csv but excluded from statistics as a timing anomaly and listed in the report. Manifest `created_at` is the resume time (noted in the manifest; script fixed).
- **Findings** (details in docs/decisions/0005): the old default PATH_CHEAPEST_ARC fails on R101 and RC101 at every budget and metaheuristic (72 failed runs); quality depends strongly on budget (chosen CVRP default: gap to BKS 5.69% at 1 s, 3.73% at 3 s, 2.94% at 10 s) and the best configuration changes with the budget; run-to-run spread is mostly 0, max 5.9%.
- **Audited defaults** per problem type (CVRP / VRPTW) and budget class (short <= 2 s, medium <= 6 s, long) are now used by `solve_ortools` when no strategy is given; the run config records `budget_class` and `search_choice`. API default is now `null` (= audited default); UI has an "Audited default (by budget)" option; Methodology text updated. With the default, R101 is solved (tested).
- **Tests (2 Nov 2026, Python 3.14.7 / OR-Tools 9.15.6755):** backend **106 passed** (90 + 16 new in `tests/test_ortools_audit.py`), frontend **13 passed**.

### Phase 3 (hybrid, local search, equal-clock comparison, guard)
- **GA weak spot fixed:** new fleet repair (empties the smallest routes when there are more routes than vehicles, without making any stop later). R101 with the GA alone: before 28 to 30 routes for 25 vehicles (infeasible); now 25 routes, feasible in every run (tested). The GA also gets about twice as many generations, because the old expensive repair branch is no longer needed.
- **Local search** (relocate, swap, intra-route 2-opt) as a switchable GA option (`local_search`, `ls_rate`, `ls_neighbours`); GA's own code, still no OR-Tools import in the GA (tested). GA now checks the clock after every child.
- **Hybrid** (`algorithm="hybrid"`, `app/solvers/hybrid.py`): OR-Tools for half the budget, then the GA seeded with the OR-Tools tour (+4 mutated copies) for the rest; labelled "hybrid"; unseeded or failed phases are reported. Available through the API (`POST /api/runs`, `hybrid` params); not in the UI yet.
- **Wall-clock guard** (`app/services/guard.py`): API runs execute in a worker process; a run past 1.5 x time limit + 5 s is killed and reported as `hard_timeout` (no plan). Tested with a deliberately frozen solver. UI shows the new status text.
- **Comparison + ablation:** `experiments/compare_engines.py`; 240 runs (6 methods x 10 instances x 3/10 s x 2 seeds, team chose the reduced size), results in `experiments/results/compare_2026-11-02/`. No hard timeouts; longest run 10.07 s on a 10 s budget. Findings (docs/decisions/0006): local search is what makes the GA competitive; on CVRP, GA + local search beat OR-Tools on average (2.26% vs 3.07% gap to BKS at 10 s) but not on every instance; on VRPTW OR-Tools stays best or tied; the hybrid's GA phase rarely improves the OR-Tools seed (0 to 9 of 20 runs), so with the untuned 50/50 split the hybrid is **not** a clear improvement over OR-Tools alone.
- **ruff** added (`ruff.toml`, requirements); `python -m ruff check .` passes (17 import-order fixes, 10 long lines wrapped).
- **Tests (2 Nov 2026, Python 3.14.7 / OR-Tools 9.15.6755):** backend **123 passed** (106 + 17 new in `tests/test_hybrid.py`), frontend **15 passed** (13 + 2 new tests for the "Audited default" option).

### Phase 5 (engine selector), 4 Nov 2026, unattended session
- **Win counts** from the P3 results (`experiments/selector_win_counts.py`, 20 cases): OR-Tools wins or ties 55%, the hybrid 55%, GA + LS 40%. No engine reaches 80%, so we built the **engine picker** (decision 0007).
- **Features** (`backend/app/selector/features.py`): budget, time-window tightness, size, demand fill, clustering. **Generator** (`generator.py`): uniform / clustered / mixed families with no / loose / tight windows. All output is labelled synthetic.
- **Dataset**: estimate 12.4 min, actual 10.2 min. 324 runs, one at a time through the guard; all feasible, no timeouts. Stored in `experiments/results/selector_2026-11-04/`; training copy in `backend/app/selector/data/training_cases.csv`.
- **Evaluation** (leave-one-family-out CV): the served regret trees have 0.52% mean regret; classifier 0.94%, always-hybrid 0.63%, always-OR-Tools 1.34%, random 1.55%. Leave-one-size-out: regret trees 1.06%, always-hybrid 0.63%. **This is not a proven improvement over always using the hybrid** (negative result, in `docs/model_card_selector.md`).
- **API**: `POST /api/plans` with `engine=auto` returns the choice with an explanation (predicted regret per engine plus the tree rule). `GET /api/plans/{id}` returns the plan; the validator's verdict is in `feasible`.
- **Tests**: 18 new in `tests/test_selector.py`. Full backend suite passed (P5 files only; see the P6 entries for later counts).

## First solver observations from P1 (5 s, one seed, Rohit's laptop; indicative only, do not quote; superseded for OR-Tools by the P2 audit)
| Instance | OR-Tools (default) | GA (with repair) |
| --- | --- | --- |
| C101 (BKS 827.3) | 827.3, 0.0% gap | feasible, +161.8%, 22 routes vs 10 |
| R101 (BKS 1637.7) | **no solution** with PATH_CHEAPEST_ARC; PARALLEL_CHEAPEST_INSERTION +1.3%, SAVINGS +2.5% | **infeasible**: 30 routes, only 25 vehicles |
| RC201 (BKS 1261.8) | +2.5% | feasible, +199% |
| A-n32-k5 (BKS 784) | +1.5% | +5.9% |
| X-n101-k25 (BKS 27591) | +5.7% | +8.1% |

## Not done / not verified
- Gehring-Homberger instances not downloaded (parser supports them; `--sets homberger`).
- GA alone (no local search) is still far from OR-Tools on time-window instances (77 to 95% gap); with local search 12 to 14%. The hybrid's OR-Tools share (0.5) and the GA's ls_rate (0.2) are untuned.
- Hybrid not in the frontend yet (API only); the API experiment endpoint still compares OR-Tools vs GA only.
- P3 comparison used 2 seeds and 10 instances; too few to claim a general winner on CVRP.
- Audit evidence covers at most 100 customers, budgets up to 10 s and one laptop; budgets above 10 s use the "long" defaults untested.
- No synthetic time-window instances yet (generator has no time windows; P5 dataset generator).
- Frontend does not show time windows yet (no UI change in P1).
- Team answers still missing: weeks remaining, review dates, workstream owners, pilot data, mentor deliverables (docs/decisions/0002).
- Docker and Ollama not installed yet (needed before P4/P6 and P8).

## Known quirks
- Instance ids hash coordinates as given: `10` and `10.0` give different ids (baseline behaviour, kept so old ids stay valid). The API always sends floats.

## Next steps
1. Team: fill in the open answers in docs/decisions/0002 (weeks remaining decides the cut line).
2. P4 (distance provider: haversine + self-hosted OSRM, flagged fallback) needs Docker; P5 (selector) can start without it. The selector's dataset should include GA + local search and the hybrid as candidates and treat the budget as a feature.
3. Close memory-heavy programs before long benchmark runs (the P2 audit was stopped once for low memory).

## Restart commands
See CLAUDE.md "Commands". In a new session: read CLAUDE.md, PLAN.md and PROGRESS.md, run the backend tests and report the real result.

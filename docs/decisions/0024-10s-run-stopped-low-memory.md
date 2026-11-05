# 0024: The 10 s held-out run was stopped (low memory); reported as PARTIAL

Date: 5 Nov 2026 (unattended session). Status: **blocker, open.**

## What happened
The planned 10 s run on the 24 held-out instances (216 runs: 3 engines x 3 repeats, estimate 36 min) started at 07:22 UTC. After **134 of 216 runs** (about 22 minutes; the log's last progress line is "130/216 runs, 1302 s elapsed"), Claude Code stopped the background command because the laptop was critically low on memory. This is the same kind of stop as the P2 audit's interruption (PROGRESS, Phase 2). The run itself did not fail; free memory a little later was 3.2 GB of 15.4 GB. The session rules say not to restart a run stopped this way on its own, so it was **not restarted**.

## What exists
`experiments/results/heldout_10s_2026-11-05/raw.csv` has 134 complete rows (rows are written as each run ends). The run went repeat by repeat, so **every one of the 24 instances has at least one complete repeat for all three engines**: 21 instances have 2 repeats (A-n69-k9 has 2 for two engines and 1 for the third), and X-n106-k14, X-n110-k13 and X-n120-k6 have 1.

**Timing anomaly found in it:** the last stored run (A-n69-k9, GA + local search, seed 1, started 07:44:37 UTC) reports a runtime of 2412.4 s for a 10 s budget: the machine stalled or slept during it, most likely the same memory pressure. All other 133 runs took 10.00 to 10.01 s. Runs longer than the guard's hard limit (1.5 x budget + 5 s) are now left out of every statistic and listed in the report (section 1.7), the rule already used for the P2 audit's 1506 s run. After that, A-n69-k9 has 2 OR-Tools repeats and 1 each for the GA and the hybrid at 10 s.

## Decision
- Report the 10 s results as **PARTIAL / PRELIMINARY**, generated automatically: `p10_report.py` compares the rows with `planned_runs` in the manifest and prints a banner with the repeat counts; the "does it hold at 10 s" verdicts carry the same warning. Per-instance means use the repeats that exist; the Wilcoxon test is over instances, so all 24 still enter it, but with less averaging.
- The selector out-of-distribution test uses these runs too and says so.
- Nothing from the partial run is presented as final in the deck.

## To finish (when memory allows; about 14 min)
Close other programs, then from the repository root:
```
python experiments/compare_engines.py --out experiments/results/heldout_10s_2026-11-05 --resume --methods ortools ga_ls hybrid_seed_ls --budgets 10 --seeds 3 --instances <the 24 keys in decision 0022>
python experiments/selector_heldout_eval.py
python experiments/p10_report.py
```
The PARTIAL banners disappear by themselves once all 216 rows exist.

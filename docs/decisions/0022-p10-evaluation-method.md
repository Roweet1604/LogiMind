# 0022: P10 evaluation method (held-out set, statistics, compute cap)

Date: 5 Nov 2026 (unattended session)

## Finding that forced a new set
All 10 instances of the stored P3 comparison (`experiments/results/compare_2026-11-02/`) are also P2 audit instances (`ortools_audit_2026-11-02`), and the audit chose OR-Tools' default settings. Comparing engines on them favours OR-Tools. The P3 tables are kept, labelled "tuning overlap".

## Decision
- **Held-out set:** 24 benchmark instances not used in the audit or any tuning: Solomon C102, C105, C202, C205, R102, R105, R110, R202, RC102, RC105, RC202, RC205 and CVRPLIB A-n33-k5, A-n37-k5, A-n39-k6, A-n45-k6, A-n48-k7, A-n53-k7, A-n55-k9, A-n63-k10, A-n69-k9, X-n106-k14, X-n110-k13, X-n120-k6. Chosen by hand to spread over Solomon classes and CVRPLIB sizes, before any result was seen.
- **Engines:** the three the platform serves (`ortools` audited defaults, `ga_ls`, `hybrid_seed_ls`). The ablation variants stay in P3.
- **Budget and repeats:** 3 s total wall clock per run, 3 repeats, one run at a time through the guard (`experiments/compare_engines.py`). Estimate 11 min, actual 650 s. 10 s on the held-out set would have taken about 36 min and broke the 25-min cap for new compute; it is listed as NOT RUN.
- **Statistics:** per instance, the mean gap over feasible repeats; two-sided Wilcoxon signed-rank test per engine pair (SciPy, `zero_method="wilcox"`), for all instances and per problem type; Holm correction over the 9 tests; differences of at most 0.01 percentage points are reported as ties. Mean, median, IQR, range, repeat SD and runtime are reported per engine.
- **Report generation:** `experiments/p10_report.py` reads only stored files and writes `docs/report/` (Markdown, CSV tables, SVG figures without a plotting dependency). The narrative numbers are filled in from the tables by the script, not typed.
- **Copilot:** no numbers, because no real model was run (Ollama not installed; eval set still DRAFT).

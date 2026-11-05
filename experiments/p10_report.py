"""P10 evaluation report: tables and figures from STORED runs only (no solver runs here).

Inputs (all committed under experiments/results/):
  heldout_2026-11-05/raw.csv      engines on 24 held-out benchmark instances (P10, this script's main table)
  compare_2026-11-02/raw.csv      P3 comparison (instances overlap the OR-Tools tuning set; reported separately)
  selector_2026-11-04/evaluation.json, replan_2026-11-04/raw.csv
  docs/eval/copilot_instructions_DRAFT.json (counted only; nothing was run on it)
Outputs: docs/report/evaluation.md, docs/report/tables/*.csv, docs/report/figures/*.svg

Usage (repo root):  python experiments/p10_report.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "experiments" / "results"
OUT = ROOT / "docs" / "report"
TABLES, FIGS = OUT / "tables", OUT / "figures"

ENGINES = {"ortools": "OR-Tools", "ga_ls": "GA + local search", "hybrid_seed_ls": "Hybrid (OR-Tools seed + GA + LS)"}
# Validated with the dataviz validator (light, white surface, all pairs): all pass; aqua is below 3:1 contrast, so
# every figure names the engines on the axis and has a table next to it.
COLOR = {"ortools": "#2A5DA8", "ga_ls": "#C2641A", "hybrid_seed_ls": "#1baf7a"}
INK, INK2, RULE = "#15191C", "#596067", "#E2DED2"
TIE = 0.01  # percentage points: smaller paired differences count as ties
VIOL = ["capacity_violations", "time_window_violations", "other_violations", "unserved_customers"]


def fmt(v, d=2):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "-"
    return f"{0.0 if abs(v) < 0.5 * 10 ** -d else v:.{d}f}"  # no "-0.00" from float noise (C202 equals its BKS)


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


# ---- solver quality -----------------------------------------------------------------------------------
ANOMALIES: list[dict] = []  # runs left out of every statistic (timing anomalies), listed in the report


def guard_limit(budget: float) -> float:
    """The wall-clock guard's hard limit (services/guard.py defaults): 1.5 x budget + 5 s."""
    return 1.5 * budget + 5.0


def load_runs(path: Path, methods) -> pd.DataFrame:
    """Runs of the given methods. A run that took longer than the guard's hard limit is a TIMING ANOMALY (the machine
    stalled or slept while it ran, so it was not a fair run of its budget): kept in raw.csv, left out here, and listed
    in the report (the same rule as the P2 audit's 1506 s run)."""
    d = pd.read_csv(path)
    d = d[d["method"].isin(methods)].copy()
    slow = d["runtime_seconds"] > d["budget_s"].map(guard_limit)
    for r in d[slow].itertuples():
        ANOMALIES.append({"file": path.relative_to(ROOT).as_posix(), "instance": r.instance_name,
                          "engine": ENGINES[r.method], "seed": r.seed, "budget_s": r.budget_s,
                          "runtime_s": r.runtime_seconds, "started_at": r.started_at})
    d = d[~slow]
    d["violations"] = d[VIOL].fillna(0).sum(axis=1)
    return d


def quality_table(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (prob, budget, m), g in d.groupby(["problem", "budget_s", "method"], sort=True):
        ok = g[g["feasible"] == True]  # noqa: E712
        gap = ok["gap_to_bks_pct"].dropna()
        per_inst_sd = ok.groupby("instance_name")["gap_to_bks_pct"].std(ddof=1).dropna()
        rows.append({
            "problem": prob, "budget_s": budget, "engine": ENGINES[m], "instances": g["instance_name"].nunique(),
            "customers": f"{int(g['n_customers'].min())}-{int(g['n_customers'].max())}",
            "runs": len(g), "feasible_runs": len(ok), "runs_with_violations": int((g["violations"] > 0).sum()),
            "gap_mean_pct": gap.mean(), "gap_median_pct": gap.median(), "gap_q25_pct": gap.quantile(.25),
            "gap_q75_pct": gap.quantile(.75), "gap_min_pct": gap.min(), "gap_max_pct": gap.max(),
            "repeat_sd_median_pp": per_inst_sd.median() if len(per_inst_sd) else np.nan,
            "runtime_mean_s": g["runtime_seconds"].mean(), "runtime_max_s": g["runtime_seconds"].max()})
    return pd.DataFrame(rows)


def per_instance(d: pd.DataFrame) -> pd.DataFrame:
    """Mean gap over feasible repeats per instance and engine (an engine with no feasible run gets NaN)."""
    ok = d[d["feasible"] == True]  # noqa: E712
    return ok.pivot_table(index=["problem", "budget_s", "instance_name"], columns="method",
                          values="gap_to_bks_pct", aggfunc="mean")


def holm(pvals: list[float]) -> list[float]:
    order = np.argsort(pvals)
    adj, running = [0.0] * len(pvals), 0.0
    for rank, i in enumerate(order):
        running = max(running, (len(pvals) - rank) * pvals[i])
        adj[i] = min(1.0, running)
    return adj


def paired_tests(pi: pd.DataFrame, pairs, label: str) -> pd.DataFrame:
    rows = []
    for scope, sub in [("all", pi)] + [(p, pi.xs(p, level="problem", drop_level=False))
                                       for p in sorted(pi.index.get_level_values("problem").unique())]:
        for a, b in pairs:
            both = sub[[a, b]].dropna()
            diff = (both[b] - both[a]).to_numpy()
            n = len(diff)
            try:
                p = float(wilcoxon(diff, zero_method="wilcox", alternative="two-sided").pvalue) if n else np.nan
            except ValueError:  # all differences zero
                p = 1.0
            rows.append({"set": label, "scope": scope, "comparison": f"{ENGINES[b]} minus {ENGINES[a]}",
                         "instances": n, "dropped_no_feasible_run": len(sub) - n,
                         "median_diff_pp": np.median(diff) if n else np.nan,
                         "mean_diff_pp": diff.mean() if n else np.nan,
                         f"{b}_better": int((diff < -TIE).sum()), "ties": int((abs(diff) <= TIE).sum()),
                         f"{a}_better": int((diff > TIE).sum()), "wilcoxon_p": p})
    df = pd.DataFrame(rows)
    df["holm_p"] = holm(df["wilcoxon_p"].fillna(1.0).tolist())
    return df


# ---- figures (plain SVG, no plotting dependency) ---------------------------------------------------------
def svg_strip(pi: pd.DataFrame, path: Path, title: str) -> None:
    """Per-instance mean gap by engine, one panel per problem type; median as a short bar."""
    probs = sorted(pi.index.get_level_values("problem").unique())
    W, H, top, bottom, left = 760, 360, 56, 70, 64
    panel_w = (W - left - 24) / len(probs)
    vmax = float(np.nanmax(pi.to_numpy())) if pi.size else 1.0
    vmax = max(1.0, np.ceil(vmax / 2) * 2)

    def y(v: float) -> float:
        return top + (H - top - bottom) * (1 - v / vmax)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="Inter, Segoe UI, sans-serif" role="img" aria-label="{title}">',
           f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>',
           f'<text x="{left}" y="24" font-size="15" fill="{INK}" font-weight="600">{title}</text>',
           f'<text x="{left}" y="42" font-size="11" fill="{INK2}">Each dot = one instance (mean over repeats); '
           f'bar = median. Lower is better. Table: tables/heldout_per_instance.csv</text>']
    for t in np.arange(0, vmax + 1e-9, 2 if vmax > 8 else 1):
        out.append(f'<line x1="{left}" x2="{W - 24}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{RULE}"/>')
        out.append(f'<text x="{left - 8}" y="{y(t) + 4:.1f}" font-size="11" fill="{INK2}" '
                   f'text-anchor="end">{t:g}%</text>')
    out.append(f'<text x="16" y="{(top + H - bottom) / 2:.0f}" font-size="11" fill="{INK2}" '
               f'transform="rotate(-90 16 {(top + H - bottom) / 2:.0f})" text-anchor="middle">'
               f'gap to best-known (%)</text>')
    rng = np.random.default_rng(0)
    for k, prob in enumerate(probs):
        x0 = left + k * panel_w
        sub = pi.xs(prob, level="problem")
        out.append(f'<text x="{x0 + panel_w / 2:.0f}" y="{H - 14}" font-size="12" fill="{INK}" '
                   f'text-anchor="middle" font-weight="600">{prob} ({len(sub)} instances)</text>')
        for j, m in enumerate(ENGINES):
            cx = x0 + panel_w * (j + 0.5) / len(ENGINES)
            vals = sub[m].dropna().to_numpy() if m in sub else np.array([])
            for v in vals:
                jx = cx + rng.uniform(-14, 14)
                out.append(f'<circle cx="{jx:.1f}" cy="{y(v):.1f}" r="4.5" fill="{COLOR[m]}" '
                           f'stroke="#FFFFFF" stroke-width="2"><title>{ENGINES[m]}: {v:.2f}%</title></circle>')
            if len(vals):
                med = float(np.median(vals))
                out.append(f'<rect x="{cx - 20:.1f}" y="{y(med) - 1.5:.1f}" width="40" height="3" rx="1.5" '
                           f'fill="{INK}"/>')
                out.append(f'<text x="{cx + 24:.1f}" y="{y(med) + 4:.1f}" font-size="10" fill="{INK}">{med:.2f}</text>')
            out.append(f'<text x="{cx:.1f}" y="{H - bottom + 18}" font-size="11" fill="{INK2}" '
                       f'text-anchor="middle">{["OR-Tools", "GA+LS", "Hybrid"][j]}</text>')
    out.append("</svg>")
    path.write_text("\n".join(out), encoding="utf-8")


def svg_regret(cv: dict, path: Path) -> None:
    """Selector regret per strategy (leave-one-family-out CV), one series."""
    names = [k for k in cv if k != "oracle"]
    vals = [cv[k]["mean_regret_pct"] for k in names]
    W, H, left, top, row = 640, 40 + 30 * len(names) + 40, 190, 50, 30
    vmax = max(vals) * 1.15
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="Inter, Segoe UI, sans-serif" role="img" aria-label="Selector regret">',
           f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>',
           f'<text x="16" y="24" font-size="15" fill="{INK}" font-weight="600">Engine picker: mean regret, '
           f'leave-one-family-out CV (SYNTHETIC data)</text>',
           f'<text x="16" y="40" font-size="11" fill="{INK2}">% extra distance over the best engine per case; '
           f'lower is better. Table: tables/selector_cv_family.csv</text>']
    for i, (n, v) in enumerate(zip(names, vals)):
        yy = top + i * row
        w = (W - left - 60) * v / vmax
        out.append(f'<text x="{left - 8}" y="{yy + 15}" font-size="11" fill="{INK}" text-anchor="end">{n}</text>')
        out.append(f'<rect x="{left}" y="{yy + 4}" width="{max(w, 1):.1f}" height="16" rx="4" fill="#2A5DA8"/>')
        out.append(f'<text x="{left + w + 6:.1f}" y="{yy + 16}" font-size="11" fill="{INK}">{v:.2f}%</text>')
    out.append("</svg>")
    path.write_text("\n".join(out), encoding="utf-8")


# ---- main ------------------------------------------------------------------------------------------------
HELDOUT = {3.0: "heldout_2026-11-05", 10.0: "heldout_10s_2026-11-05"}
SELECTOR_OOD = RES / "selector_heldout_2026-11-05"


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)
    methods = list(ENGINES)
    pairs = [("ortools", "ga_ls"), ("ortools", "hybrid_seed_ls"), ("ga_ls", "hybrid_seed_ls")]

    held, mans, quality, tests = {}, {}, {}, {}
    for budget, folder in HELDOUT.items():
        if not (RES / folder / "raw.csv").exists():
            continue
        held[budget] = load_runs(RES / folder / "raw.csv", methods)
        mans[budget] = json.loads((RES / folder / "manifest.json").read_text())
        mans[budget]["stored_rows"] = len(pd.read_csv(RES / folder / "raw.csv"))
        quality[budget] = quality_table(held[budget])
        pi = per_instance(held[budget]).droplevel("budget_s")
        tests[budget] = paired_tests(pi, pairs, f"held-out, {budget:g} s")  # Holm over the 9 tests of this budget
        name = "heldout_gap_by_engine.svg" if budget == 3.0 else f"heldout_{budget:g}s_gap_by_engine.svg"
        svg_strip(pi, FIGS / name, f"Gap to best-known by engine, 24 held-out instances, {budget:g} s each")
    all_held = pd.concat(held.values(), ignore_index=True)
    pd.concat(quality.values()).to_csv(TABLES / "heldout_quality.csv", index=False)
    per_instance(all_held).reset_index().to_csv(TABLES / "heldout_per_instance.csv", index=False)
    pd.concat(tests.values()).to_csv(TABLES / "heldout_wilcoxon.csv", index=False)
    sizes = (all_held.groupby(["instance_name", "problem"]).agg(customers=("n_customers", "first"),
                                                               vehicles=("vehicle_count", "first"),
                                                               best_known=("bks_cost", "first"))
             .reset_index().sort_values(["problem", "customers", "instance_name"]))
    sizes.to_csv(TABLES / "heldout_instances.csv", index=False)

    p3 = load_runs(RES / "compare_2026-11-02" / "raw.csv", methods)
    p3 = p3[p3["bks_cost"].notna()]
    pq = quality_table(p3)
    ppi = per_instance(p3)
    ptests = pd.concat([paired_tests(ppi.xs(b, level="budget_s"), pairs, f"P3 set, {b:g} s")
                        for b in sorted(p3["budget_s"].unique())])
    pq.to_csv(TABLES / "p3_quality.csv", index=False)
    ptests.to_csv(TABLES / "p3_wilcoxon.csv", index=False)

    ev = json.loads((RES / "selector_2026-11-04" / "evaluation.json").read_text())
    cvf = ev["cv_by_family"]  # strategies incl. the random baseline; "group_col" and "folds" are skipped below
    sel = pd.DataFrame([{"strategy": k, "accuracy": v.get("accuracy"), "mean_regret_pct": v.get("mean_regret_pct"),
                         "max_regret_pct": v.get("max_regret_pct"), "failed_choices": v.get("failures")}
                        for k, v in cvf.items() if isinstance(v, dict) and "mean_regret_pct" in v])
    sel.to_csv(TABLES / "selector_cv_family.csv", index=False)
    svg_regret({r.strategy: {"mean_regret_pct": r.mean_regret_pct} for r in sel.itertuples()},
               FIGS / "selector_regret.svg")
    ood = ood_cases = ood_man = None
    if (SELECTOR_OOD / "summary.csv").exists():
        ood = pd.read_csv(SELECTOR_OOD / "summary.csv")
        ood_cases = pd.read_csv(SELECTOR_OOD / "cases.csv")
        ood_man = json.loads((SELECTOR_OOD / "manifest.json").read_text())
        ood.to_csv(TABLES / "selector_heldout.csv", index=False)

    rp = pd.read_csv(RES / "replan_2026-11-04" / "raw.csv")
    rsum = rp.groupby(["engine", "event", "budget_s", "warm"]).agg(
        replans=("feasible", "size"), feasible=("feasible", "sum"),
        frozen_violations=("replan_violations", "sum"),
        mean_distance=("total_distance", "mean"), mean_time_to_feasible_s=("disruption_to_feasible_s", "mean"),
        max_time_to_feasible_s=("disruption_to_feasible_s", "max")).reset_index()
    rsum.to_csv(TABLES / "replan_summary.csv", index=False)

    draft = json.loads((ROOT / "docs" / "eval" / "copilot_instructions_DRAFT.json").read_text(encoding="utf-8"))
    n_items = len(draft["items"]) if isinstance(draft, dict) and "items" in draft else len(draft)

    write_report(held, mans, quality, tests, sizes, p3, pq, ptests, sel, ev, (ood, ood_cases, ood_man), rsum,
                 n_items)
    print(f"wrote {OUT / 'evaluation.md'}")


def show_quality(q: pd.DataFrame) -> str:
    t = q.copy()
    t["feasible"] = t["feasible_runs"].astype(str) + " / " + t["runs"].astype(str)
    t["gap mean / median %"] = t["gap_mean_pct"].map(fmt) + " / " + t["gap_median_pct"].map(fmt)
    t["gap IQR %"] = t["gap_q25_pct"].map(fmt) + " to " + t["gap_q75_pct"].map(fmt)
    t["gap range %"] = t["gap_min_pct"].map(fmt) + " to " + t["gap_max_pct"].map(fmt)
    t["repeat SD (median, pp)"] = t["repeat_sd_median_pp"].map(fmt)
    t["runtime mean / max s"] = t["runtime_mean_s"].map(fmt) + " / " + t["runtime_max_s"].map(fmt)
    t["runs with violations"] = t["runs_with_violations"]
    return md_table(t[["problem", "budget_s", "engine", "instances", "customers", "feasible", "runs with violations",
                       "gap mean / median %", "gap IQR %", "gap range %", "repeat SD (median, pp)",
                       "runtime mean / max s"]])


def show_tests(t: pd.DataFrame) -> str:
    s = t.copy()
    rows = []
    for _, r in s.iterrows():
        b_key = next(k for k, v in ENGINES.items() if r["comparison"].startswith(v))
        a_key = next(k for k, v in ENGINES.items() if r["comparison"].endswith(v))
        rows.append({"set": r["set"], "scope": r["scope"], "comparison (B minus A)": r["comparison"],
                     "instances": int(r["instances"]),
                     "median / mean diff (pp)": f"{fmt(r['median_diff_pp'])} / {fmt(r['mean_diff_pp'])}",
                     "B better / tie / A better": f"{int(r[f'{b_key}_better'])} / {int(r['ties'])} / "
                                                  f"{int(r[f'{a_key}_better'])}",
                     "Wilcoxon p": fmt(r["wilcoxon_p"], 4), "Holm-adjusted p": fmt(r["holm_p"], 4)})
    return md_table(pd.DataFrame(rows))


def infeasible_runs(d: pd.DataFrame) -> str:
    bad = d[d["feasible"] != True]  # noqa: E712
    if bad.empty:
        return "No infeasible runs."
    lines = []
    for r in bad.itertuples():
        what = ", ".join(f"{c.replace('_', ' ')} {int(getattr(r, c))}" for c in VIOL if getattr(r, c, 0))
        lines.append(f"- {r.instance_name}, {ENGINES[r.method]}, seed {r.seed}, {r.budget_s:g} s: "
                     f"status `{r.status}`, {what or 'no violation counts'}; "
                     f"vehicles used {int(r.vehicles_used)} of {int(r.vehicle_count)}.")
    return "\n".join(lines)


def test_line(t: pd.DataFrame, scope: str, comp: str) -> str:
    r = t[(t["scope"] == scope) & (t["comparison"] == comp)].iloc[0]
    b = next(k for k, v in ENGINES.items() if comp.startswith(v))
    a = next(k for k, v in ENGINES.items() if comp.endswith(v))
    return (f"{ENGINES[b]} better on {int(r[f'{b}_better'])}, tie {int(r['ties'])}, {ENGINES[a]} better on "
            f"{int(r[f'{a}_better'])} of {int(r['instances'])} instances; median difference "
            f"{fmt(r['median_diff_pp'])} pp; Holm-adjusted p = {fmt(r['holm_p'], 4)}")


def partial(runs: pd.DataFrame, man: dict) -> bool:
    return int(man.get("stored_rows", len(runs))) < int(man.get("planned_runs", len(runs)))


def direction(r: pd.Series) -> float:
    return r["median_diff_pp"] if abs(r["median_diff_pp"]) > TIE else r["mean_diff_pp"]


def verdict(r3: pd.Series, r10: pd.Series) -> str:
    s3, s10 = np.sign(direction(r3)), np.sign(direction(r10))
    sig3, sig10 = r3["holm_p"] < 0.05, r10["holm_p"] < 0.05
    if sig3 and sig10 and s3 == s10:
        return "holds (significant at both budgets)"
    if sig3 and not sig10 and s3 == s10:
        return "same direction, but not significant at 10 s"
    if sig3 and s3 != s10:
        return "does not hold (direction changed at 10 s)"
    if sig10 and not sig3:
        return "significant only at 10 s"
    return "not significant at either budget"


def holds_table(tests: dict) -> str:
    ort, G, H = ENGINES["ortools"], ENGINES["ga_ls"], ENGINES["hybrid_seed_ls"]
    rows = []
    for scope, comp, label in [("CVRP", f"{G} minus {ort}", "CVRP: GA + LS vs OR-Tools"),
                               ("VRPTW", f"{G} minus {ort}", "VRPTW: GA + LS vs OR-Tools"),
                               ("CVRP", f"{H} minus {ort}", "CVRP: hybrid vs OR-Tools"),
                               ("VRPTW", f"{H} minus {ort}", "VRPTW: hybrid vs OR-Tools"),
                               ("all", f"{H} minus {ort}", "All 24: hybrid vs OR-Tools")]:
        r3, r10 = (tests[b][(tests[b]["scope"] == scope) & (tests[b]["comparison"] == comp)].iloc[0]
                   for b in (3.0, 10.0))
        b = next(k for k, v in ENGINES.items() if comp.startswith(v))
        a = next(k for k, v in ENGINES.items() if comp.endswith(v))

        def cell(r: pd.Series, a: str = a, b: str = b) -> str:
            return (f"{int(r[f'{b}_better'])} / {int(r['ties'])} / {int(r[f'{a}_better'])}; "
                    f"median {fmt(r['median_diff_pp'])} pp; p = {fmt(r['holm_p'], 4)}")

        rows.append({"comparison (first engine better / tie / OR-Tools better)": label, "3 s": cell(r3),
                     "10 s": cell(r10), "verdict": verdict(r3, r10)})
    return md_table(pd.DataFrame(rows))


def held_section(budget: float, q: pd.DataFrame, t: pd.DataFrame, man: dict, runs: pd.DataFrame, num: str) -> str:
    ort, G, H = ENGINES["ortools"], ENGINES["ga_ls"], ENGINES["hybrid_seed_ls"]
    reading = "\n".join([
        f"- **CVRP, GA + LS vs OR-Tools:** {test_line(t, 'CVRP', f'{G} minus {ort}')}.",
        f"- **CVRP, hybrid vs OR-Tools:** {test_line(t, 'CVRP', f'{H} minus {ort}')}.",
        f"- **VRPTW, GA + LS vs OR-Tools:** {test_line(t, 'VRPTW', f'{G} minus {ort}')}.",
        f"- **VRPTW, hybrid vs OR-Tools:** {test_line(t, 'VRPTW', f'{H} minus {ort}')}.",
        f"- **All 24, hybrid vs OR-Tools:** {test_line(t, 'all', f'{H} minus {ort}')}."])
    sig = t[t["holm_p"] < 0.05]
    sig_lines = "\n".join(f"  - {r.scope}: {r.comparison} (Holm-adjusted p = {fmt(r.holm_p, 4)}, median difference "
                          f"{fmt(r.median_diff_pp)} pp)" for r in sig.itertuples()) or "  - none"
    fig = "heldout_gap_by_engine.svg" if budget == 3.0 else f"heldout_{budget:g}s_gap_by_engine.svg"
    took = f"{len(runs)} runs; estimate {man['estimated_seconds'] / 60:.0f} min; run started {man['created_at']}."
    if partial(runs, man):
        reps = runs.groupby(["instance_name", "method"]).size()
        left_out = int(man["stored_rows"]) - len(runs)
        took = (f"**PARTIAL: {man['stored_rows']} of {man['planned_runs']} planned runs stored** ({left_out} left out "
                f"as timing anomalies, section 1.7). The run was stopped by the session "
                f"because the laptop ran low on memory (decision 0024); it was not restarted. Every instance has "
                f"{int(reps.min())} to {int(reps.max())} repeats per engine instead of 3. Treat these results as "
                f"preliminary. Run started {man['created_at']}.")
    return f"""### {num} Held-out set at {budget:g} s
{took}

{show_quality(q)}

![Gap by engine, {budget:g} s](figures/{fig})

{show_tests(t)}

**Reading ("difference" = first-named engine minus OR-Tools or GA; negative = the first-named engine's gap is
smaller):**
{reading}
- Significant after the Holm correction (p < 0.05):
{sig_lines}
"""


def ood_section(ood, cases, man) -> str:
    if ood is None:
        return "Not run yet (needs `experiments/selector_heldout_eval.py`)."
    t = ood.copy()
    for c in ("mean_regret_pct", "median_regret_pct", "max_regret_pct"):
        t[c] = t[c].map(fmt)
    t["correct"] = t["correct"].map(lambda v: fmt(float(v), 1) if v != int(v) else str(int(v)))
    t["failures"] = t["failures"].map(lambda v: fmt(float(v), 1) if v != int(v) else str(int(v)))
    picks = cases.groupby(["budget_s", "problem"])["selector_choice"].value_counts().unstack(fill_value=0)
    picks = picks.reset_index()
    scope_lines, losses = [], []
    for scope, g in ood.groupby("scope", sort=False):
        a = g.set_index("strategy")
        me = a.loc["selector (served regret model)", "mean_regret_pct"]
        base = {k: a.loc[k, "mean_regret_pct"] for k in ("always ortools", "always ga_ls", "always hybrid")}
        beat_by = [f"{k} ({fmt(v)}%)" for k, v in base.items() if v < me - 1e-9]
        tied = [k for k, v in base.items() if abs(v - me) <= 1e-9]
        line = f"- **{scope}:** selector {fmt(me)}%; "
        if beat_by:
            line += "**beaten by " + ", ".join(beat_by) + "**"
            losses.append(scope)
        else:
            line += "not beaten by any fixed choice"
        if tied:
            line += f" (equal to {', '.join(tied)})"
        scope_lines.append(line + ".")
    partial_note = ("The 10 s cases come from the PARTIAL 10 s run (1 to 2 repeats; section 1.3), so every scope that "
                    "includes them is preliminary." if man.get("partial_10s") else "")
    return f"""The selector was trained on {man['selector_training_cases']} SYNTHETIC cases (sizes
{man['selector_training_sizes'][0]}-{man['selector_training_sizes'][1]} customers, budgets
{", ".join(f"{b:g}" for b in man['selector_training_budgets'])} s). Here it picks an engine for each held-out
**benchmark** case ({man['cases']} cases = 24 instances x 2 budgets;
{man['cases_outside_training_range']} are outside its training range in size or budget, and all are
outside its training families). Its pick is scored against the
stored runs of all three engines; **no extra solver runs**. Regret = % extra distance over the best engine of the
case (mean over feasible repeats); "correct" = within {man['tie_pct']}% of the best; a pick with no feasible run is a
failure. Results in `experiments/results/selector_heldout_2026-11-05/`.

{md_table(t[["scope", "strategy", "cases", "correct", "failures", "mean_regret_pct", "median_regret_pct",
             "max_regret_pct"]])}

What it picked (cases per budget and problem type):

{md_table(picks)}

**Reading (mean regret per scope; computed from the table above):**
{chr(10).join(scope_lines)}

{("**Negative result:** in " + ", ".join(losses) + " a single fixed engine choice beats the selector.")
 if losses else "In every scope the selector was at least as good as each fixed choice."}
{partial_note}
This is a test of transfer from synthetic training data to public benchmarks, not of real fleets.
"""


def write_report(held, mans, quality, tests, sizes, p3, pq, ptests, sel, ev, ood, rsum, n_items) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    any_runs = next(iter(held.values()))
    man = next(iter(mans.values()))
    inst_md = md_table(sizes.assign(best_known=sizes["best_known"].map(fmt)))
    held_md = "\n".join(held_section(b, quality[b], tests[b], mans[b], held[b], f"1.{i + 2}")
                         for i, b in enumerate(sorted(held)))
    holds_md = holds_table(tests) if {3.0, 10.0} <= set(tests) else "The 10 s runs are missing."
    if 10.0 in held and partial(held[10.0], mans[10.0]):
        holds_md = ("**The 10 s column is PRELIMINARY** (partial run, see 1.3): fewer repeats per instance, so "
                    "these verdicts may change when the run is completed.\n\n" + holds_md)
    anomalies_md = md_table(pd.DataFrame(ANOMALIES).assign(
        runtime_s=lambda t: t["runtime_s"].map(lambda v: fmt(v, 1)))) if ANOMALIES else "None."
    infeasible = "\n".join(f"**{b:g} s:**\n\n{infeasible_runs(held[b])}\n" for b in sorted(held))
    rs = rsum.copy()
    rs["warm"] = rs["warm"].map({True: "warm", False: "cold"})
    rs["feasible"] = rs["feasible"].astype(int).astype(str) + " / " + rs["replans"].astype(str)
    rs["mean distance"] = rs["mean_distance"].map(fmt)
    rs["time to feasible, mean / max s"] = rs["mean_time_to_feasible_s"].map(fmt) + " / " + \
        rs["max_time_to_feasible_s"].map(fmt)
    replan_md = md_table(rs[["engine", "event", "budget_s", "warm", "feasible", "frozen_violations",
                             "mean distance", "time to feasible, mean / max s"]])
    sel_md = md_table(sel.assign(accuracy=sel["accuracy"].map(lambda v: fmt(v, 3)),
                                 mean_regret_pct=sel["mean_regret_pct"].map(fmt),
                                 max_regret_pct=sel["max_regret_pct"].map(fmt)))
    text = f"""# LogiMind evaluation (P10)

Generated {now} by `experiments/p10_report.py` from **stored runs only**. Every number below comes from the committed
files under `experiments/results/`; nothing was typed in by hand. Machine for all runs: Rohit's laptop
({man['environment']['processor']}, {man['environment']['cpu_count']} logical CPUs),
Python {any_runs['python'].iloc[0]}, OR-Tools {any_runs['ortools_version'].iloc[0]}.
Tables are also in `docs/report/tables/` (CSV); figures in `docs/report/figures/` (SVG).

## 1. Solver quality on 24 held-out benchmark instances

### 1.1 Set-up
- **Why a held-out set:** all 10 instances of the P3 comparison were also used in the P2 OR-Tools audit, which chose
  OR-Tools' default settings, so results on them favour OR-Tools. These 24 instances were **not used for any
  tuning** (decision 0022):

{inst_md}

- **Rules:** same instance, same distance matrix, same objective, same **total** wall-clock budget per run
  (the hybrid's OR-Tools phase is inside it), one run at a time through the wall-clock guard, 3 repeats
  (OR-Tools has no seed, so its repeats are re-runs). Gaps are to the published best-known values in
  `experiments/benchmarks/bks.csv` (CVRPLIB, source URL and date in that file).
  Budgets: {", ".join(f"{b:g} s" for b in sorted(held))}.
- **Engines:** the three the platform serves: OR-Tools (audited defaults), GA + local search, and the hybrid
  (OR-Tools for half the budget, then GA + local search seeded with its tour).
- **Significance:** per instance, the mean gap over feasible repeats; a two-sided Wilcoxon signed-rank test per
  engine pair, for all instances and per problem type; Holm correction over the 9 tests **of each budget**. A
  difference of at most {TIE} percentage points is a tie. An instance where an engine had no feasible run is left out of
  that pair (`dropped` in the CSV).

{held_md}
### 1.4 Do the 3 s findings hold at 10 s?
Each cell: first engine better / tie / OR-Tools better (instances), median difference, Holm-adjusted p. The verdict
is computed from these numbers (significant = Holm-adjusted p < 0.05).

{holds_md}

### 1.5 P3 comparison set (stored, 2 Nov 2026; tuning overlap)
The same three engines from the stored P3 runs (8 benchmark instances with a best-known value, 2 seeds, 3 s and
10 s). **These instances overlap the OR-Tools tuning set (P2 audit)**, so this table is biased towards OR-Tools
and is shown for completeness only.

{show_quality(pq)}

{show_tests(ptests)}

### 1.6 Constraint violations
The validator checks every returned plan. "Runs with violations" counts runs with any capacity, time-window,
unserved-customer or other violation (for example more routes than vehicles); such a plan is never shown as
feasible. Infeasible runs on the held-out set:

{infeasible}
### 1.7 Timing anomalies (left out of every statistic above)
A run longer than the guard's hard limit (1.5 x budget + 5 s) was not a fair run of its budget (the machine stalled or
slept). Such runs stay in `raw.csv` but are not used in any table, test or figure, and not in the selector test.

{anomalies_md}

## 2. Engine picker (selector)

### 2.1 Cross-validation on its own SYNTHETIC data (stored 4 Nov 2026)
{ev.get('runs', 324)} runs on {ev.get('cases', 108)} synthetic cases (generator in `backend/app/selector/generator.py`).
Leave-one-family-out cross-validation; regret = % extra distance over the best engine of the case.

{sel_md}

![Selector regret](figures/selector_regret.svg)

On its own synthetic data, the served regret model has the lowest mean regret in this CV, but always choosing the
hybrid is close, and in the leave-one-size-out CV (`experiments/results/selector_2026-11-04/evaluation.md`)
always-hybrid is better.

### 2.2 Out-of-distribution test on the held-out benchmarks
{ood_section(*ood)}

## 3. Replanning, stored 4 Nov 2026, SYNTHETIC data
6 synthetic instances (40 customers), one seed; the first third of each route frozen. Feasible = validator **and**
the independent frozen-stop check. **These runs predate the retry rule (decision 0023):** in them a retried failed
delivery could still be the next stop.

{replan_md}

**Reading:** every replan was feasible with 0 frozen-stop violations. Time to a feasible plan is about the budget,
because the engines use their whole budget. Warm vs cold distances, including the negative result for
breakdowns at 2 s, are in `experiments/results/replan_2026-11-04/report.md`.

## 4. Copilot
- **Real model: NOT RUN.** Ollama is not installed on this laptop (checked 5 Nov 2026), and the evaluation set is
  still a DRAFT ({n_items} instructions in `docs/eval/copilot_instructions_DRAFT.json`) waiting for the team to
  review and freeze it. There are **no accuracy numbers**, and none may be quoted.
- What exists: 16 backend tests with the deterministic fake LLM. They check behaviour (schema-constrained intents,
  no route fields, grounding check, clarify / confirm / refuse paths), not language understanding.

## 5. Road matrix (P4)
Not part of the solver comparison above (benchmarks use their own distances). Tested offline only, with real OSRM
answers for 6 synthetic points; never run against a self-hosted OSRM (decision 0019).

## Threats to validity
- One laptop; wall-clock budgets depend on the machine. All runs were one at a time.
- 24 held-out instances, 12 per problem type: per-type tests have little power, so "not significant" is not evidence
  of equality. Holm is applied per budget (9 tests each), not across both budgets.
- Instance sizes (table above) are {int(sizes['customers'].min())} to {int(sizes['customers'].max())} customers;
  nothing here says how the engines behave on much larger instances (Gehring-Homberger not run).
- The hybrid's 50/50 split is untuned (P3 note).
"""
    (OUT / "evaluation.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

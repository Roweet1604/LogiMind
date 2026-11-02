"""CSV export and aggregation of experiment records."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.services.runner import RunRecord

METRIC_COLS = ["total_distance", "estimated_cost", "runtime_seconds", "vehicles_used"]


def records_to_dataframe(records: list[RunRecord]) -> pd.DataFrame:
    return pd.DataFrame([r.to_row() for r in records])


def write_raw_csv(records: list[RunRecord], path: Path) -> pd.DataFrame:
    df = records_to_dataframe(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """Per (size, algorithm): run counts and mean/median/std over FEASIBLE runs only.

    Infeasible or failed runs are counted but excluded from the statistics, so
    they can neither flatter nor distort an average.
    """
    rows = []
    for (n, algo), g in df.groupby(["n_customers", "algorithm"]):
        ok = g[g["feasible"] == True]  # noqa: E712  (pandas boolean/None column)
        row = {"n_customers": n, "algorithm": algo, "runs": len(g), "feasible_runs": len(ok)}
        for col in METRIC_COLS:
            s = ok[col].astype(float)
            row[f"{col}_mean"] = s.mean() if len(s) else float("nan")
            row[f"{col}_median"] = s.median() if len(s) else float("nan")
            row[f"{col}_std"] = s.std(ddof=1) if len(s) > 1 else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)

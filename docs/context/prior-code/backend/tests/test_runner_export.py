import json
import math
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from app.services.export import summarize, write_raw_csv
from app.services.generator import generate_instance
from app.services.runner import environment_info, run_algorithm

ROOT = Path(__file__).resolve().parents[2]


def test_both_algorithms_share_instance_and_schema():
    inst = generate_instance(10, seed=3)
    a = run_algorithm(inst, "ortools", {"time_limit_s": 1})
    b = run_algorithm(inst, "ga", {"seed": 0, "population_size": 30, "max_generations": 30})
    assert a.result.instance_id == b.result.instance_id == inst.instance_id
    assert a.to_row().keys() == b.to_row().keys()
    assert a.validation.feasible and b.validation.feasible
    # shared evaluator => distance recomputed from the same matrix
    assert a.metrics.distance_unit == b.metrics.distance_unit == "km"


def test_unknown_algorithm_raises():
    with pytest.raises(ValueError):
        run_algorithm(generate_instance(5, seed=1), "simulated_annealing")


def test_csv_export_contains_real_rows(tmp_path):
    inst = generate_instance(8, seed=1)
    recs = [run_algorithm(inst, "ortools", {"time_limit_s": 1}),
            run_algorithm(inst, "ga", {"seed": 1, "population_size": 20, "max_generations": 10})]
    df = write_raw_csv(recs, tmp_path / "raw.csv")
    back = pd.read_csv(tmp_path / "raw.csv")
    assert len(back) == 2 and set(back["algorithm"]) == {"ortools", "ga"}
    assert back["total_distance"].gt(0).all() and back["seed"].notna().sum() == 1
    assert df.shape == back.shape


def test_summary_excludes_infeasible_runs():
    df = pd.DataFrame([
        dict(n_customers=10, algorithm="ga", feasible=True, total_distance=100.0, estimated_cost=150.0, runtime_seconds=1.0, vehicles_used=1),
        dict(n_customers=10, algorithm="ga", feasible=True, total_distance=120.0, estimated_cost=170.0, runtime_seconds=1.0, vehicles_used=1),
        dict(n_customers=10, algorithm="ga", feasible=False, total_distance=1.0, estimated_cost=1.0, runtime_seconds=1.0, vehicles_used=1),
        dict(n_customers=10, algorithm="ortools", feasible=None, total_distance=math.nan, estimated_cost=math.nan, runtime_seconds=1.0, vehicles_used=math.nan),
    ])
    s = summarize(df).set_index("algorithm")
    assert s.loc["ga", "runs"] == 3 and s.loc["ga", "feasible_runs"] == 2
    assert s.loc["ga", "total_distance_mean"] == pytest.approx(110.0)
    assert math.isnan(s.loc["ortools", "total_distance_mean"]) and s.loc["ortools", "feasible_runs"] == 0


def test_environment_info_has_versions():
    env = environment_info()
    assert env["ortools"] != "not installed" and "python" in env


def test_benchmark_script_end_to_end(tmp_path):
    out = tmp_path / "bench"
    subprocess.run([sys.executable, str(ROOT / "experiments" / "run_benchmarks.py"), "--sizes", "8",
                    "--ga-seeds", "2", "--time-budget", "1", "--out", str(out)], check=True, capture_output=True)
    raw = pd.read_csv(out / "raw.csv")
    assert len(raw) == 3 and (raw["algorithm"] == "ga").sum() == 2
    assert sorted(raw.loc[raw.algorithm == "ga", "seed"]) == [0, 1]
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["runs"] == 3 and "ortools" in manifest["environment"]
    assert (out / "summary.csv").exists() and any((out / "instances").iterdir())

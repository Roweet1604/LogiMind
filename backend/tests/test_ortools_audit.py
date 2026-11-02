"""P2 audit: grid planning, per-run records and the analysis rules."""
import math

import pandas as pd
import pytest
from app.benchmarks import audit as A


def test_budget_classes():
    assert A.budget_class(1) == "short" and A.budget_class(2) == "short"
    assert A.budget_class(3) == "medium" and A.budget_class(6) == "medium"
    assert A.budget_class(10) == "long" and A.budget_class(600) == "long"


def test_plan_jobs_covers_full_grid_with_repeats_outermost():
    jobs = A.plan_jobs(["synthetic:5", "synthetic:6"], ["SAVINGS", "PATH_CHEAPEST_ARC"],
                       ["GREEDY_DESCENT", "GUIDED_LOCAL_SEARCH"], [1, 3], repeats=2)
    assert len(jobs) == 2 * 2 * 2 * 2 * 2
    assert len({A.job_key(j) for j in jobs}) == len(jobs)
    half = len(jobs) // 2
    assert {j.repeat for j in jobs[:half]} == {0} and {j.repeat for j in jobs[half:]} == {1}


def test_estimate_charges_full_budget_to_time_bound_metaheuristics():
    jobs = A.plan_jobs(["synthetic:5"], ["SAVINGS"], ["GREEDY_DESCENT", "TABU_SEARCH"], [3], repeats=1)
    assert A.estimate_seconds(jobs, greedy_s=1.0) == 1.0 + 3.0


def test_synthetic_instance_is_labelled_and_reproducible():
    a, problem = A.load_audit_instance("synthetic:12")
    b, _ = A.load_audit_instance("synthetic:12")
    assert problem == "CVRP" and a.source == "synthetic" and a.instance_id == b.instance_id


def test_run_records_config_repeat_and_versions(tmp_path):
    jobs = A.plan_jobs(["synthetic:8"], ["PARALLEL_CHEAPEST_INSERTION"], ["GREEDY_DESCENT"], [0.5], repeats=1)
    rows = list(A.iter_runs(jobs, tmp_path))
    assert len(rows) == 1
    r = rows[0]
    assert r["algorithm"] == "ortools" and r["feasible"] is True
    assert r["first_solution"] == "PARALLEL_CHEAPEST_INSERTION" and r["metaheuristic"] == "GREEDY_DESCENT"
    assert r["budget_s"] == 0.5 and r["repeat"] == 0 and "no seed" in r["seed_note"]
    assert r["ortools_version"] and r["python"] and r["platform"]
    assert math.isnan(r["gap_to_bks_pct"])  # synthetic: no best-known value, none invented


def test_resume_skips_finished_runs(tmp_path):
    jobs = A.plan_jobs(["synthetic:8"], ["SAVINGS"], ["GREEDY_DESCENT"], [0.5], repeats=2)
    raw = tmp_path / "raw.csv"
    pd.DataFrame([{"instance_key": "synthetic:8", "first_solution": "SAVINGS", "metaheuristic": "GREEDY_DESCENT",
                   "budget_s": 0.5, "repeat": 0}]).to_csv(raw, index=False)
    left = list(A.iter_runs(jobs, tmp_path, A.done_keys(raw)))
    assert [r["repeat"] for r in left] == [1]


def _row(key, fs, mh, budget, rep, dist, feasible, problem="VRPTW", bks=math.nan):
    return {"instance_key": key, "problem": problem, "first_solution": fs, "metaheuristic": mh, "budget_s": budget,
            "repeat": rep, "total_distance": dist, "feasible": feasible, "runtime_seconds": budget,
            "gap_to_bks_pct": (100 * (dist - bks) / bks if feasible and not math.isnan(bks) else math.nan)}


@pytest.fixture
def toy_raw():
    rows = []
    for rep in range(2):
        # "FAST" never solves instance i2 -> must not be recommended, even though its gap on i1 is best.
        rows.append(_row("i1", "FAST", "GD", 1.0, rep, 100.0, True, bks=100.0))
        rows.append(_row("i2", "FAST", "GD", 1.0, rep, math.nan, None))
        rows.append(_row("i1", "SAFE", "GD", 1.0, rep, 110.0 + rep, True, bks=100.0))
        rows.append(_row("i2", "SAFE", "GD", 1.0, rep, 50.0, True))
    return pd.DataFrame(rows)


def test_summary_counts_failures_and_averages_feasible_runs_only(toy_raw):
    s = A.summarize_configs(toy_raw).set_index("first_solution")
    assert s.loc["FAST", "runs"] == 4 and s.loc["FAST", "feasible_runs"] == 2
    assert s.loc["FAST", "instances_always_solved"] == 1
    assert s.loc["FAST", "mean_gap_best_observed_pct"] == 0.0
    assert s.loc["SAFE", "mean_gap_bks_pct"] == pytest.approx(10.5)


def test_recommend_requires_every_run_solved(toy_raw):
    rec = A.recommend(A.summarize_configs(toy_raw))
    assert list(rec["first_solution"]) == ["SAFE"]


def test_recommend_says_so_when_nothing_solves_everything(toy_raw):
    only_fast = toy_raw[toy_raw["first_solution"] == "FAST"]
    rec = A.recommend(A.summarize_configs(only_fast))
    assert rec.iloc[0]["first_solution"] == "" and "no configuration" in rec.iloc[0]["note"]


def test_timing_anomaly_is_excluded_from_statistics(toy_raw):
    frozen = _row("i1", "FAST", "GD", 1.0, 2, 90.0, True, bks=100.0)
    frozen["runtime_seconds"] = 500.0  # e.g. the machine froze during the run
    df = pd.concat([toy_raw, pd.DataFrame([frozen])], ignore_index=True)
    assert len(A.timing_anomalies(df)) == 1
    s = A.summarize_configs(df).set_index("first_solution")
    assert s.loc["FAST", "runs"] == 4  # the anomalous run is not counted ...
    assert s.loc["FAST", "mean_gap_best_observed_pct"] == 0.0  # ... nor used as the best observed (90)


def test_repeat_variation_spread(toy_raw):
    v = A.repeat_variation(toy_raw).set_index(["instance_key", "first_solution"])
    assert v.loc[("i1", "SAFE"), "spread_pct"] == pytest.approx(100 * 1 / 110)
    assert v.loc[("i1", "FAST"), "spread_pct"] == 0.0
    assert math.isnan(v.loc[("i2", "FAST"), "spread_pct"])  # no feasible repeats -> no spread claimed


# ---- audited defaults in the solver (decision 0005) ----
from app.benchmarks import catalog  # noqa: E402
from app.main import app  # noqa: E402
from app.services.runner import run_algorithm  # noqa: E402
from app.solvers.ortools_solver import AUDITED_DEFAULTS, default_search, solve_ortools  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tests.test_api import wait_run  # noqa: E402
from tests.test_time_windows import line_instance  # noqa: E402


def test_defaults_cover_every_problem_and_budget_class():
    assert set(AUDITED_DEFAULTS) == {(p, c) for p in ("CVRP", "VRPTW") for c in ("short", "medium", "long")}
    # The baseline default failed on tight time windows; it must not be a time-window default.
    assert all(fs != "PATH_CHEAPEST_ARC" for (p, _), (fs, _) in AUDITED_DEFAULTS.items() if p == "VRPTW")
    assert default_search(False, 1) == AUDITED_DEFAULTS[("CVRP", "short")]
    assert default_search(True, 30) == AUDITED_DEFAULTS[("VRPTW", "long")]


def test_solver_records_audited_default(tiny):
    res = solve_ortools(tiny, time_limit_s=0.5)
    assert res.config["search_choice"] == "audited_default" and res.config["budget_class"] == "short"
    assert (res.config["first_solution_strategy"], res.config["local_search_metaheuristic"]) == \
        AUDITED_DEFAULTS[("CVRP", "short")]


def test_explicit_choice_wins_over_default():
    res = solve_ortools(line_instance(), time_limit_s=0.5, first_solution="SAVINGS", metaheuristic="GREEDY_DESCENT")
    assert res.config["search_choice"] == "explicit"
    assert res.config["first_solution_strategy"] == "SAVINGS"
    part = solve_ortools(line_instance(), time_limit_s=0.5, metaheuristic="GREEDY_DESCENT")
    assert part.config["search_choice"] == "partly_audited_default"
    assert part.config["first_solution_strategy"] == AUDITED_DEFAULTS[("VRPTW", "short")][0]


def test_api_uses_audited_default_or_the_explicit_choice():
    client = TestClient(app)
    inst = client.post("/api/instances/generate", json={"n_customers": 6, "seed": 1}).json()
    for ortools, choice, fs in (({}, "audited_default", AUDITED_DEFAULTS[("CVRP", "short")][0]),
                                ({"first_solution": "LOCAL_CHEAPEST_INSERTION", "metaheuristic": "GREEDY_DESCENT"},
                                 "explicit", "LOCAL_CHEAPEST_INSERTION")):
        r = client.post("/api/runs", json={"instance_id": inst["instance_id"], "algorithm": "ortools",
                                           "time_limit_s": 0.5, "ortools": ortools})
        assert r.status_code == 202, r.text
        run = wait_run(client, r.json()["run_id"])
        assert run["state"] == "completed" and run["validation"]["feasible"] is True
        cfg = run["result"]["config"]
        assert cfg["search_choice"] == choice and cfg["first_solution_strategy"] == fs


@pytest.mark.skipif(not catalog.data_file("solomon", "R101").exists(), reason="benchmark files not downloaded")
def test_default_solves_r101_where_the_old_default_found_nothing():
    inst = catalog.load_instance("solomon", "R101")
    rec = run_algorithm(inst, "ortools", {"time_limit_s": 1})
    assert rec.validation is not None and rec.validation.feasible
    old = run_algorithm(inst, "ortools", {"time_limit_s": 1, "first_solution": "PATH_CHEAPEST_ARC",
                                          "metaheuristic": "GUIDED_LOCAL_SEARCH"})
    assert old.result.status == "timeout_no_solution" and old.validation is None

"""P3: fleet repair, local search, seeding, the hybrid solver and the wall-clock guard."""
import random
import time

import pytest
from app.benchmarks import catalog
from app.main import create_app
from app.models import result as R
from app.models.problem import Customer, Instance
from app.services.generator import generate_instance
from app.services.guard import GuardedWorker
from app.services.runner import RunRecord, run_algorithm
from app.solvers import hybrid as H
from app.solvers.genetic_algorithm import GAConfig, _Problem, solve_ga
from app.solvers.local_search import fleet_repair, local_search, objective, route_eval
from fastapi.testclient import TestClient

from tests.test_api import wait_run


def frozen_solver(instance, algorithm, config) -> RunRecord:  # top level: the worker process imports it
    time.sleep(60)
    raise AssertionError("should have been stopped")


def windows_instance() -> Instance:
    """6 customers, generous windows, 3 vehicles: easy, so any sane search is on time."""
    cs = [Customer(i, float(x), float(y), 2, ready_time=0, due_time=500, service_time=5)
          for i, (x, y) in enumerate([(10, 0), (12, 3), (-8, 4), (-10, -2), (3, -12), (6, -9)], start=1)]
    return Instance(depot_x=0.0, depot_y=0.0, customers=cs, vehicle_count=3, vehicle_capacity=6,
                    metric="euclidean", fixed_vehicle_cost=0.0, cost_per_distance=1.0, depot_due_time=1000.0,
                    name="tw6")


def check_routes(p, routes):
    flat = sorted(c for r in routes for c in r)
    assert flat == list(range(1, p.n + 1))
    assert all(sum(p.demand[c] for c in r) <= p.cap for r in routes)


# ---- route tools ----
def test_local_search_never_worsens_and_keeps_every_customer():
    p = _Problem(generate_instance(30, seed=3, metric="euclidean"))
    rng = random.Random(0)
    for _ in range(5):
        perm = list(range(1, p.n + 1))
        rng.shuffle(perm)
        _, routes = p.split(perm)
        before = objective(p, routes)
        after_routes, moves = local_search(p, routes, rng)
        check_routes(p, after_routes)
        assert objective(p, after_routes) <= before + 1e-9
        assert moves > 0  # a random tour always has something to improve


def test_local_search_respects_its_deadline():
    p = _Problem(generate_instance(60, seed=1, metric="euclidean"))
    _, routes = p.split(list(range(1, p.n + 1)))
    t0 = time.perf_counter()
    local_search(p, routes, random.Random(0), deadline=t0 + 0.05)
    assert time.perf_counter() - t0 < 0.5


def test_fleet_repair_empties_a_route_without_adding_lateness():
    p = _Problem(windows_instance())
    routes = [[1], [2], [3], [4], [5, 6]]  # 5 routes, 3 vehicles
    fixed = fleet_repair(p, routes)
    check_routes(p, fixed)
    assert len(fixed) <= p.vehicles
    assert sum(route_eval(p, r)[1] for r in fixed) == 0.0


def test_fleet_repair_gives_up_cleanly_when_capacity_forbids_it():
    p = _Problem(windows_instance())
    p.vehicles = 1  # 12 units of demand cannot fit one vehicle of 6
    routes = [[1, 2, 3], [4, 5, 6]]
    assert sorted(map(sorted, fleet_repair(p, routes))) == [[1, 2, 3], [4, 5, 6]]


# ---- GA ----
def test_ga_uses_initial_tours_and_rejects_bad_ones():
    inst = windows_instance()
    res = solve_ga(inst, GAConfig(population_size=10, max_generations=5), initial_tours=[[1, 2, 3, 4, 5, 6]])
    assert res.status == R.SOLVED and res.diagnostics["seeded_tours"] == 1
    bad = solve_ga(inst, GAConfig(population_size=10, max_generations=5), initial_tours=[[1, 1, 2, 3, 4, 5]])
    assert bad.status == R.ERROR and "exactly once" in bad.message


def test_ga_with_local_search_records_its_work():
    inst = generate_instance(25, seed=2, metric="euclidean")
    rec = run_algorithm(inst, "ga", {"seed": 1, "population_size": 20, "max_generations": 15,
                                      "local_search": True, "ls_rate": 0.5})
    d = rec.result.diagnostics
    assert rec.validation.feasible and d["local_search_calls"] > 0 and d["local_search_moves"] > 0
    assert rec.result.config["local_search"] is True


def test_ga_stops_inside_a_generation_when_time_is_up():
    inst = generate_instance(80, seed=5, metric="euclidean")
    res = solve_ga(inst, GAConfig(population_size=400, max_generations=10**6, stagnation_generations=None,
                                  time_limit_s=0.3, local_search=True, ls_rate=1.0))
    assert res.status == R.SOLVED and res.diagnostics["stop_reason"] == "time_limit"
    assert res.runtime_seconds < 1.5  # initial population + one child at most past the limit


@pytest.mark.skipif(not catalog.data_file("solomon", "R101").exists(), reason="benchmark files not downloaded")
def test_ga_is_feasible_on_r101_with_fleet_repair():
    """P1 weak spot: 30 routes for 25 vehicles at 5 s. With fleet repair it must fit the fleet."""
    inst = catalog.load_instance("solomon", "R101")
    rec = run_algorithm(inst, "ga", {"seed": 0, "time_limit_s": 5, "max_generations": 10**9,
                                      "stagnation_generations": None})
    assert rec.validation.feasible
    assert sum(1 for r in rec.result.routes if r) <= inst.vehicle_count


# ---- hybrid ----
def test_hybrid_is_labelled_seeded_within_budget_and_not_worse_than_its_seed():
    inst = generate_instance(30, seed=4, metric="euclidean")
    rec = run_algorithm(inst, "hybrid", {"time_limit_s": 1.0, "seed": 2})
    r, d = rec.result, rec.result.diagnostics
    assert r.algorithm == "hybrid" and r.status == R.SOLVED and rec.validation.feasible
    assert d["seeded"] is True and d["ga_phase"]["seeded_tours"] == 5
    assert rec.metrics.total_distance <= d["ortools_phase"]["seed_distance"] + 1e-6
    assert r.runtime_seconds < 1.0 + 0.5  # equal-clock: OR-Tools phase + GA phase share ONE budget
    assert r.config["ortools_share"] == 0.5 and r.config["local_search"] is True


def test_hybrid_reports_an_unseeded_run_honestly(monkeypatch):
    def nothing(instance, **kw):
        return R.SolveResult(instance.instance_id, "ortools", R.NO_SOLUTION, 0.01, None,
                             {"first_solution_strategy": "X", "local_search_metaheuristic": "Y"},
                             message="no solution")
    monkeypatch.setattr(H, "solve_ortools", nothing)
    rec = run_algorithm(windows_instance(), "hybrid", {"time_limit_s": 0.5})
    assert rec.result.diagnostics["seeded"] is False and "unseeded" in rec.result.message
    assert rec.validation.feasible  # the GA still produced a plan, and the validator checked it


def test_hybrid_rejects_bad_config():
    inst = windows_instance()
    assert run_algorithm(inst, "hybrid", {"ortools_share": 1.5}).result.status == R.INVALID_INPUT
    assert run_algorithm(inst, "hybrid", {"ga": {"time_limit_s": 3}}).result.status == R.INVALID_INPUT
    assert run_algorithm(inst, "hybrid", {"nonsense": 1}).result.status == R.INVALID_INPUT


def test_ga_module_still_does_not_import_the_hybrid_or_ortools():
    import ast
    import inspect

    from app.solvers import genetic_algorithm
    from app.solvers import local_search as ls
    for mod in (genetic_algorithm, ls):
        names = {n.module for n in ast.walk(ast.parse(inspect.getsource(mod))) if isinstance(n, ast.ImportFrom)}
        assert not any("ortools" in (m or "") or "hybrid" in (m or "") for m in names)


# ---- wall-clock guard ----
def test_guard_stops_a_frozen_run_and_reports_a_timeout():
    worker = GuardedWorker(target=frozen_solver, factor=1.0, grace_s=1.0)
    try:
        inst = windows_instance()
        # Start the worker before the clock: spawning it (imports OR-Tools, FastAPI, ...) can take
        # many seconds on a loaded laptop and is not part of what the guard measures.
        worker._ensure_worker()
        proc = worker._proc
        t0 = time.perf_counter()
        rec = worker.run(inst, "ortools", {"time_limit_s": 0.5})
        waited = time.perf_counter() - t0
        assert rec.result.status == R.HARD_TIMEOUT and rec.result.routes is None
        assert rec.validation is None and rec.metrics is None  # never shown as a plan
        assert "wall-clock guard" in rec.result.message
        assert rec.result.diagnostics["hard_limit_s"] == 1.5  # 1.0 x 0.5 + 1.0
        # Not stopped before the hard limit (small allowance for the OS timer), and stopped long
        # before the frozen solver's 60 s sleep would end (generous margin for a busy machine).
        assert 1.5 - 0.05 <= waited < 30
        assert not proc.is_alive()  # the frozen worker was really killed
        assert worker.restarts == 1
    finally:
        worker.close()


def test_guard_passes_normal_runs_through_and_recovers_after_a_timeout():
    worker = GuardedWorker()
    try:
        inst = windows_instance()
        rec = worker.run(inst, "ortools", {"time_limit_s": 0.5})
        assert rec.result.status == R.SOLVED and rec.validation.feasible
        worker._kill()  # simulate a killed worker: the next run must start a fresh one
        rec2 = worker.run(inst, "ga", {"seed": 1, "max_generations": 5, "population_size": 10})
        assert rec2.result.status == R.SOLVED
    finally:
        worker.close()


def test_api_runs_the_hybrid(tmp_path):
    client = TestClient(create_app(tmp_path))
    inst = client.post("/api/instances/generate", json={"n_customers": 8, "seed": 3}).json()
    r = client.post("/api/runs", json={"instance_id": inst["instance_id"], "algorithm": "hybrid", "time_limit_s": 1,
                                       "hybrid": {"ortools_share": 0.3, "local_search": False}})
    assert r.status_code == 202, r.text
    run = wait_run(client, r.json()["run_id"])
    assert run["state"] == "completed" and run["result"]["algorithm"] == "hybrid"
    assert run["validation"]["feasible"] is True
    cfg = run["result"]["config"]
    assert cfg["ortools_share"] == 0.3 and cfg["local_search"] is False and "seed" not in cfg["ga"]


# ---- comparison / ablation planning (experiments/compare_engines.py) ----
def test_compare_jobs_give_every_method_the_same_budget():
    from app.benchmarks import compare as C
    jobs = C.plan_jobs(["synthetic:5"], list(C.METHODS), [3.0], seeds=2)
    assert len(jobs) == len(C.METHODS) * 2
    for _, method, budget, seed in jobs:
        algorithm, cfg = C.job_config(method, budget, seed)
        assert cfg["time_limit_s"] == 3.0
        assert ("seed" in cfg) == (algorithm != "ortools")  # OR-Tools has no seed
    assert C.job_config("ga_nofix", 3.0, 0)[1]["fleet_repair"] is False
    assert C.job_config("hybrid_seed", 3.0, 0)[1]["local_search"] is False
    assert C.job_config("hybrid_seed_ls", 3.0, 0)[1]["local_search"] is True


def test_compare_summary_counts_hard_timeouts_and_keeps_them_out_of_averages():
    import pandas as pd
    from app.benchmarks import compare as C
    rows = [
        {"instance_key": "i", "problem": "CVRP", "method": "ga", "budget_s": 1.0, "seed": 0, "status": "solved",
         "feasible": True, "total_distance": 100.0, "runtime_seconds": 1.0, "gap_to_bks_pct": float("nan")},
        {"instance_key": "i", "problem": "CVRP", "method": "ga", "budget_s": 1.0, "seed": 1, "status": "hard_timeout",
         "feasible": None, "total_distance": float("nan"), "runtime_seconds": 6.5, "gap_to_bks_pct": float("nan")},
    ]
    s = C.summarize(pd.DataFrame(rows)).iloc[0]
    assert s["hard_timeouts"] == 1 and s["runs"] == 1 and s["feasible_runs"] == 1

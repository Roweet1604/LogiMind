import math
import random

import pytest

from app.evaluation.validator import TOO_MANY_VEHICLES, validate_routes
from app.models import result as R
from app.models.problem import Customer, Instance
from app.services.generator import generate_instance
from app.services.runner import run_algorithm
from app.solvers.genetic_algorithm import GAConfig, _Problem, mutate, order_crossover, solve_ga
from app.solvers.ortools_solver import solve_ortools


def test_ortools_finds_hand_checked_optimum(tiny):
    res = solve_ortools(tiny, time_limit_s=1)
    assert res.status == R.SOLVED and res.algorithm == "ortools"
    rec = run_algorithm(tiny, "ortools", {"time_limit_s": 1})
    assert rec.validation.feasible
    assert rec.metrics.total_distance == pytest.approx(24)


def test_ga_finds_hand_checked_optimum(tiny):
    rec = run_algorithm(tiny, "ga", {"seed": 3, "population_size": 30, "max_generations": 60})
    assert rec.result.status == R.SOLVED and rec.validation.feasible
    assert rec.metrics.total_distance == pytest.approx(24)


def test_ga_same_seed_is_reproducible():
    inst = generate_instance(15, seed=2)
    cfg = dict(seed=11, population_size=40, max_generations=40, stagnation_generations=None)
    a, b = solve_ga(inst, GAConfig(**cfg)), solve_ga(inst, GAConfig(**cfg))
    assert a.routes == b.routes
    assert a.diagnostics["best_fitness"] == b.diagnostics["best_fitness"]


def test_ga_records_seed_and_config():
    inst = generate_instance(10, seed=2)
    res = solve_ga(inst, GAConfig(seed=5, population_size=20, max_generations=5))
    assert res.seed == 5 and res.config["population_size"] == 20
    assert res.diagnostics["stop_reason"] in {"max_generations", "stagnation", "time_limit"}


def test_ga_covers_each_customer_once_on_larger_instance():
    inst = generate_instance(40, seed=4)
    res = solve_ga(inst, GAConfig(seed=1, population_size=40, max_generations=30))
    served = sorted(c for r in res.routes for c in r)
    assert served == [c.id for c in inst.customers]
    assert validate_routes(inst, res.routes).feasible


def test_ga_time_limit_respected():
    inst = generate_instance(30, seed=4)
    res = solve_ga(inst, GAConfig(seed=1, max_generations=10**9, stagnation_generations=None, time_limit_s=0.5))
    assert res.diagnostics["stop_reason"] == "time_limit" and res.runtime_seconds < 2.0


def test_ga_does_not_import_ortools():
    import ast
    import app.solvers.genetic_algorithm as ga
    tree = ast.parse(open(ga.__file__).read())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("ortools" in m for m in imported)


def test_crossover_and_mutation_keep_permutation():
    rng = random.Random(0)
    p1, p2 = list(range(1, 21)), random.Random(1).sample(range(1, 21), 20)
    for _ in range(50):
        child = order_crossover(p1, p2, rng)
        assert sorted(child) == p1
        mutate(child, rng)
        assert sorted(child) == p1


def test_split_never_exceeds_capacity():
    inst = generate_instance(30, seed=9)
    p = _Problem(inst)
    perm = list(range(1, 31))
    random.Random(2).shuffle(perm)
    _, routes = p.split(perm)
    assert all(sum(p.demand[c] for c in r) <= p.cap for r in routes)
    assert sorted(c for r in routes for c in r) == sorted(perm)


def test_invalid_input_reported_not_crashed():
    bad = Instance(0, 0, [Customer(1, 1, 1, -2)], vehicle_count=1, vehicle_capacity=5)
    assert solve_ortools(bad).status == R.INVALID_INPUT
    assert solve_ga(bad).status == R.INVALID_INPUT
    rec = run_algorithm(bad, "ga", {})
    assert rec.metrics is None and rec.validation is None


def test_invalid_ga_config_reported():
    inst = generate_instance(5, seed=1)
    assert solve_ga(inst, GAConfig(population_size=1)).status == R.INVALID_INPUT
    assert run_algorithm(inst, "ga", {"bogus": 1}).result.status == R.INVALID_INPUT


@pytest.fixture
def packing_infeasible() -> Instance:
    # total demand 18 <= fleet capacity 20 passes the quick check, but three
    # demand-6 customers cannot fit in two capacity-10 vehicles.
    return Instance(0, 0, [Customer(i, i, 0, 6) for i in (1, 2, 3)], vehicle_count=2, vehicle_capacity=10,
                    metric="euclidean")


def test_ortools_reports_no_solution_when_packing_infeasible(packing_infeasible):
    rec = run_algorithm(packing_infeasible, "ortools", {"time_limit_s": 1})
    assert rec.result.status in {R.NO_SOLUTION, R.TIMEOUT_NO_SOLUTION}
    assert rec.metrics is None
    row = rec.to_row()
    assert math.isnan(row["total_distance"]) and row["feasible"] is None   # not 0


def test_ga_infeasible_fleet_is_caught_by_validator(packing_infeasible):
    rec = run_algorithm(packing_infeasible, "ga", {"seed": 1, "population_size": 10, "max_generations": 5})
    assert rec.validation is not None and not rec.validation.feasible
    assert TOO_MANY_VEHICLES in {v.type for v in rec.validation.violations}


def test_ortools_total_runtime_respects_budget_and_records_build_time():
    inst = generate_instance(300, seed=3)
    inst.distance_matrix()
    res = solve_ortools(inst, time_limit_s=2)
    assert res.status == R.SOLVED
    assert res.runtime_seconds <= 2.6            # build time is inside the budget, not added to it
    d = res.diagnostics
    assert d["build_seconds"] > 0 and d["search_limit_s"] < 2.0
    assert d["build_seconds"] + d["search_limit_s"] == pytest.approx(2.0, abs=0.01)

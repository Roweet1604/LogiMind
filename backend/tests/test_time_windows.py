"""Time windows (CVRPTW): model, validator, metrics, both solvers and the API."""
import pytest
from app.evaluation.metrics import compute_metrics
from app.evaluation.validator import (
    DEPOT_RETURN_LATE,
    TIME_WINDOW_VIOLATED,
    route_schedule,
    validate_routes,
)
from app.main import app
from app.models import result as R
from app.models.problem import Customer, Instance, InstanceValidationError
from app.services.generator import generate_instance
from app.solvers.genetic_algorithm import GAConfig, _Problem, repair_time_windows, solve_ga
from app.solvers.ortools_solver import solve_ortools
from fastapi.testclient import TestClient


def line_instance(**kw) -> Instance:
    """Customers on a line; with one vehicle the only on-time order is 1, 2, 3.

    1 at x=10, window [0, 15]; 2 at x=20, window [0, 25]; 3 at x=5, window [40, 60].
    Route 1,2,3: starts 10, 20, 40 (waits 5 at customer 3), back at 45; distance 40.
    """
    args = dict(
        depot_x=0.0, depot_y=0.0,
        # float coordinates: like the baseline, the id hashes 10 and 10.0 differently
        customers=[Customer(1, 10.0, 0.0, 1, ready_time=0, due_time=15),
                   Customer(2, 20.0, 0.0, 1, ready_time=0, due_time=25),
                   Customer(3, 5.0, 0.0, 1, ready_time=40, due_time=60)],
        vehicle_count=1, vehicle_capacity=10, metric="euclidean",
        fixed_vehicle_cost=0.0, cost_per_distance=1.0, depot_due_time=100.0, name="line")
    args.update(kw)
    return Instance(**args)


# ---- model ------------------------------------------------------------------
def test_plain_cvrp_ids_are_unchanged_from_the_baseline(tiny):
    # values computed with the untouched route-optimization v3 code
    assert tiny.instance_id == "inst-d15bbec8d3"
    assert generate_instance(50, seed=7006).instance_id == "inst-506a52b698"
    assert not tiny.has_time_windows


def test_time_windows_change_the_id_and_survive_a_round_trip():
    inst = line_instance()
    plain = line_instance(customers=[Customer(c.id, c.x, c.y, c.demand) for c in inst.customers],
                          depot_due_time=None)
    assert inst.has_time_windows and not plain.has_time_windows
    assert inst.instance_id != plain.instance_id
    back = Instance.from_dict(inst.to_dict())
    assert back.instance_id == inst.instance_id == back.compute_id()
    assert back.customers == inst.customers and back.depot_due_time == 100.0


@pytest.mark.parametrize("change, message", [
    (dict(customers=[Customer(1, 10, 0, 1, ready_time=20, due_time=10)]), "due_time must be"),
    (dict(customers=[Customer(1, 10, 0, 1, service_time=-1)]), "service_time must be"),
    (dict(customers=[Customer(1, 10, 0, 1, due_time=5)]), "cannot be reached"),
    (dict(customers=[Customer(1, 10, 0, 1)], depot_due_time=15.0), "return before depot_due_time"),
    (dict(depot_ready_time=50.0, depot_due_time=10.0), "depot_due_time must be"),
    (dict(time_per_distance=0.0), "time_per_distance must be"),
])
def test_bad_time_data_is_rejected(change, message):
    inst = line_instance(**change)
    with pytest.raises(InstanceValidationError) as exc:
        inst.validate()
    assert any(message in e for e in exc.value.errors)


def test_travel_time_scales_distance():
    inst = line_instance(time_per_distance=2.0, depot_due_time=None,
                         customers=[Customer(1, 10, 0, 1, due_time=30)])
    assert inst.travel_time_matrix()[0][1] == pytest.approx(20.0)
    inst.validate()


# ---- validator and metrics ------------------------------------------------------
def test_on_time_route_waits_and_is_feasible():
    inst = line_instance()
    v = validate_routes(inst, [[1, 2, 3]])
    assert v.feasible and v.total_lateness == 0
    s = route_schedule(inst, [1, 2, 3])
    assert s.starts == [10, 20, 40] and s.waiting == pytest.approx(5) and s.end_time == pytest.approx(45)
    m = compute_metrics(inst, [[1, 2, 3]], v)
    assert m.total_distance == pytest.approx(40)
    assert m.total_waiting == pytest.approx(5) and m.route_durations == [pytest.approx(45)]
    assert m.time_window_violations == 0 and m.other_violations == 0


def test_late_stops_are_reported_with_their_lateness():
    inst = line_instance()
    v = validate_routes(inst, [[3, 1, 2]])  # 3 at 40, 1 at 45 (30 late), 2 at 55 (30 late)
    assert not v.feasible
    assert v.count(TIME_WINDOW_VIOLATED) == 2
    assert v.total_lateness == pytest.approx(60)
    m = compute_metrics(inst, [[3, 1, 2]], v)
    assert m.time_window_violations == 2 and m.other_violations == 0 and m.total_lateness == pytest.approx(60)


def test_late_return_to_the_depot_is_a_violation():
    inst = Instance(depot_x=0, depot_y=0,
                    customers=[Customer(1, 10, 0, 1, service_time=10), Customer(2, -10, 0, 1, service_time=10)],
                    vehicle_count=2, vehicle_capacity=10, depot_due_time=45.0)
    inst.validate()  # each customer alone fits: 10 + 10 + 10 = 30
    v = validate_routes(inst, [[1, 2], []])  # back at 60
    assert v.count(DEPOT_RETURN_LATE) == 1 and v.total_lateness == pytest.approx(15)
    assert validate_routes(inst, [[1], [2]]).feasible


def test_plain_cvrp_validation_ignores_time(tiny):
    v = validate_routes(tiny, [[1, 2], [3, 4]])
    m = compute_metrics(tiny, [[1, 2], [3, 4]], v)
    assert v.feasible and m.total_lateness == 0 and m.route_durations == []


# ---- solvers ------------------------------------------------------------------------
def test_ortools_respects_time_windows():
    inst = line_instance()
    res = solve_ortools(inst, time_limit_s=1)
    assert res.status == R.SOLVED and res.config["time_windows"] is True
    assert [r for r in res.routes if r] == [[1, 2, 3]]
    assert validate_routes(inst, res.routes).feasible


def test_ortools_reports_no_solution_honestly():
    # one vehicle cannot be at x=10 and x=-10 at the same moment
    inst = Instance(depot_x=0, depot_y=0,
                    customers=[Customer(1, 10, 0, 1, ready_time=10, due_time=10),
                               Customer(2, -10, 0, 1, ready_time=10, due_time=10)],
                    vehicle_count=1, vehicle_capacity=10, depot_due_time=100.0)
    inst.validate()
    res = solve_ortools(inst, time_limit_s=1)
    assert res.status in (R.NO_SOLUTION, R.TIMEOUT_NO_SOLUTION) and res.routes is None


def test_ga_finds_the_on_time_order():
    inst = line_instance()
    res = solve_ga(inst, GAConfig(population_size=10, max_generations=50, seed=1))
    assert res.status == R.SOLVED
    assert [r for r in res.routes if r] == [[1, 2, 3]]
    assert validate_routes(inst, res.routes).feasible
    assert {"repair_calls", "repair_improvements", "best_lateness"} <= set(res.diagnostics)
    assert res.diagnostics["best_lateness"] == 0


def test_ga_split_penalises_lateness():
    p = _Problem(line_instance(vehicle_count=3))
    on_time = p.fitness([1, 2, 3])
    assert on_time == pytest.approx(40)
    # [3, 1, 2] in one route is 60 time units late; the split must avoid or pay for it
    assert p.fitness([3, 1, 2]) > on_time


def test_repair_moves_the_latest_customer():
    import random
    # Large fleet: the split keeps [3, 1, 2] as one late route only if lateness is cheap.
    p = _Problem(line_instance(vehicle_count=3, fixed_vehicle_cost=1000.0), lateness_weight=1.0)
    _, routes = p.split([3, 1, 2])
    assert routes == [[3, 1, 2]]
    before = p.fitness([3, 1, 2])
    fixed, after, used = repair_time_windows(p, [3, 1, 2], random.Random(0))
    assert after < before and used >= 2
    assert sorted(fixed) == [1, 2, 3]


def test_repair_also_fixes_too_many_routes():
    import random
    # One vehicle and heavy lateness: the split dodges lateness with an extra route.
    p = _Problem(line_instance(), lateness_weight=1000.0)
    _, routes = p.split([3, 1, 2])
    assert len(routes) > p.vehicles
    fixed, after, _ = repair_time_windows(p, [3, 1, 2], random.Random(0))
    assert fixed == [1, 2, 3] and after == pytest.approx(40)


def test_ga_rejects_bad_time_settings():
    res = solve_ga(line_instance(), GAConfig(lateness_weight=-1))
    assert res.status == R.INVALID_INPUT
    res = solve_ga(line_instance(), GAConfig(nn_seed_fraction=0.8, due_seed_fraction=0.5))
    assert res.status == R.INVALID_INPUT


# ---- API --------------------------------------------------------------------------
def test_api_accepts_and_returns_time_windows():
    client = TestClient(app)
    body = {"name": "tw", "metric": "euclidean", "depot_x": 0, "depot_y": 0, "depot_due_time": 100,
            "customers": [{"id": 1, "x": 10, "y": 0, "demand": 1, "ready_time": 0, "due_time": 15},
                          {"id": 2, "x": 20, "y": 0, "demand": 1, "due_time": 25, "service_time": 2}],
            "vehicle_count": 1, "vehicle_capacity": 5}
    r = client.post("/api/instances", json=body)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["has_time_windows"] is True and d["depot"]["due_time"] == 100
    assert d["customers"][1]["service_time"] == 2


def test_api_rejects_unreachable_time_window():
    client = TestClient(app)
    body = {"metric": "euclidean", "depot_x": 0, "depot_y": 0,
            "customers": [{"id": 1, "x": 10, "y": 0, "demand": 1, "due_time": 5}],
            "vehicle_count": 1, "vehicle_capacity": 5}
    r = client.post("/api/instances", json=body)
    assert r.status_code == 422
    assert any("cannot be reached" in e for e in r.json()["detail"]["errors"])

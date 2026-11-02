import pytest
from app.evaluation import validator as V
from app.evaluation.metrics import compute_metrics, route_distance
from app.evaluation.validator import validate_routes


def kinds(res):
    return {v.type for v in res.violations}


def test_good_solution_is_feasible(tiny):
    res = validate_routes(tiny, [[1, 2], [3, 4]])
    assert res.feasible and res.violations == [] and res.route_loads == [4, 4]


def test_unserved_customer_detected(tiny):
    res = validate_routes(tiny, [[1, 2], [3]])
    assert not res.feasible and res.unserved == [4] and V.UNSERVED_CUSTOMER in kinds(res)


def test_duplicate_visit_detected(tiny):
    res = validate_routes(tiny, [[1, 2], [2, 3, 4]])
    assert res.duplicated == [2] and V.DUPLICATE_VISIT in kinds(res)


def test_capacity_violation_detected(tiny):
    res = validate_routes(tiny, [[1, 2, 3], [4]])  # load 6 > 4
    assert V.CAPACITY_EXCEEDED in kinds(res) and not res.feasible


def test_unknown_customer_and_depot_as_stop(tiny):
    res = validate_routes(tiny, [[1, 2, 99], [0, 3, 4]])
    assert {V.UNKNOWN_CUSTOMER, V.DEPOT_AS_STOP} <= kinds(res)


def test_too_many_vehicles(tiny):
    res = validate_routes(tiny, [[1], [2], [3], [4]])
    assert V.TOO_MANY_VEHICLES in kinds(res)


def test_route_distance_hand_checked(tiny):
    assert route_distance(tiny, [1, 2]) == pytest.approx(12)   # 3 + 4 + 5
    assert route_distance(tiny, []) == 0.0


def test_metrics_and_cost_model(tiny):
    tiny.fixed_vehicle_cost, tiny.cost_per_distance = 10.0, 2.0
    routes = [[1, 2], [3, 4]]
    m = compute_metrics(tiny, routes, validate_routes(tiny, routes))
    assert m.total_distance == pytest.approx(24)
    assert m.vehicles_used == 2
    assert m.estimated_cost == pytest.approx(10 * 2 + 2 * 24)
    assert m.unserved_customers == 0 and m.capacity_violations == 0


def test_metrics_count_violations(tiny):
    routes = [[1, 2, 3], [2]]
    m = compute_metrics(tiny, routes, validate_routes(tiny, routes))
    assert m.unserved_customers == 1 and m.capacity_violations == 1 and m.other_violations >= 1

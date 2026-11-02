import math

import pytest

from app.models.problem import Customer, Instance, InstanceValidationError
from app.services.generator import generate_instance


def make(customers, **kw):
    base = dict(depot_x=0, depot_y=0, vehicle_count=2, vehicle_capacity=10)
    base.update(kw)
    return Instance(customers=customers, **base)


def errors_of(inst):
    with pytest.raises(InstanceValidationError) as e:
        inst.validate()
    return " | ".join(e.value.errors)


def test_valid_instance_passes(tiny):
    tiny.validate()


def test_negative_and_zero_demand_rejected():
    assert "positive integer" in errors_of(make([Customer(1, 1, 1, -3)]))
    assert "positive integer" in errors_of(make([Customer(1, 1, 1, 0)]))


def test_invalid_capacity_and_fleet():
    assert "vehicle_capacity" in errors_of(make([Customer(1, 1, 1, 1)], vehicle_capacity=0))
    assert "vehicle_count" in errors_of(make([Customer(1, 1, 1, 1)], vehicle_count=0))


def test_duplicate_and_reserved_ids():
    assert "duplicate customer id 1" in errors_of(make([Customer(1, 1, 1, 1), Customer(1, 2, 2, 1)]))
    assert "reserved" in errors_of(make([Customer(0, 1, 1, 1)]))


def test_demand_above_capacity_and_fleet_capacity():
    assert "exceeds vehicle capacity" in errors_of(make([Customer(1, 1, 1, 11)]))
    msg = errors_of(make([Customer(i, i, i, 10) for i in range(1, 4)]))  # 30 > 2*10
    assert "fleet capacity" in msg


def test_empty_nonfinite_and_bad_latlon():
    assert "no customers" in errors_of(make([]))
    assert "finite" in errors_of(make([Customer(1, math.nan, 0, 1)]))
    assert "latitude" in errors_of(make([Customer(1, 10, 95, 1)], metric="haversine"))


def test_from_dict_malformed():
    with pytest.raises(InstanceValidationError):
        Instance.from_dict({"customers": []})


def test_roundtrip_and_stable_id(tiny):
    again = Instance.from_dict(tiny.to_dict())
    assert again.instance_id == tiny.instance_id
    assert again.distance_matrix().tolist() == tiny.distance_matrix().tolist()


def test_distance_matrix_hand_values(tiny):
    m = tiny.distance_matrix()
    assert m[0][1] == pytest.approx(3) and m[1][2] == pytest.approx(4) and m[2][0] == pytest.approx(5)


def test_haversine_one_degree_latitude_is_about_111km():
    inst = make([Customer(1, 0.0, 1.0, 1)], metric="haversine")
    assert inst.distance_matrix()[0][1] == pytest.approx(111.19, abs=0.1)


def test_generator_reproducible_and_valid():
    a, b, c = generate_instance(30, seed=7), generate_instance(30, seed=7), generate_instance(30, seed=8)
    assert a.instance_id == b.instance_id != c.instance_id
    a.validate()
    assert generate_instance(20, seed=1, metric="euclidean").metric == "euclidean"

"""Benchmark parsers, the best-known-solutions table and (when downloaded) the real files."""
import datetime as dt
import math

import pytest
from app.benchmarks import catalog
from app.benchmarks.formats import (
    BenchmarkFormatError,
    parse_solomon,
    parse_solution,
    parse_tsplib_cvrp,
)
from app.evaluation.metrics import compute_metrics
from app.evaluation.validator import validate_routes
from app.main import app
from app.models.problem import Customer, Instance
from fastapi.testclient import TestClient

# Small made-up files in the official layouts (not real benchmark data).
SOLOMON_TEXT = """T1

VEHICLE
NUMBER     CAPACITY
  2         10

CUSTOMER
CUST NO.  XCOORD.   YCOORD.    DEMAND   READY TIME  DUE DATE   SERVICE   TIME

    0      40         50          0          0        100          0
    1      45         50          3          0         50          5
    2      40         55          4         10         60          5
"""

TSPLIB_TEXT = """NAME : T-n4-k2
COMMENT : test
TYPE : CVRP
DIMENSION : 4
EDGE_WEIGHT_TYPE : EUC_2D
CAPACITY : 10
NODE_COORD_SECTION
 1 0 0
 2 3 4
 3 6 8
 4 0 5
DEMAND_SECTION
1 0
2 3
3 4
4 5
DEPOT_SECTION
 1
 -1
EOF
"""


def test_parse_solomon():
    inst = parse_solomon(SOLOMON_TEXT)
    inst.validate()
    assert inst.name == "T1" and inst.metric == "euclidean_trunc1" and inst.has_time_windows
    assert (inst.vehicle_count, inst.vehicle_capacity) == (2, 10)
    assert inst.depot_due_time == 100 and inst.fixed_vehicle_cost == 0
    assert inst.customers[1] == Customer(2, 40, 55, 4, ready_time=10, due_time=60, service_time=5)


def test_parse_tsplib_renumbers_customers_without_the_depot():
    inst = parse_tsplib_cvrp(TSPLIB_TEXT)
    inst.validate()
    assert inst.metric == "euclidean_nint" and not inst.has_time_windows
    assert inst.vehicle_count == 2  # from "-k2"
    assert [c.id for c in inst.customers] == [1, 2, 3]
    assert inst.distance_matrix()[0][1] == 5  # (0,0) -> (3,4)
    assert parse_tsplib_cvrp(TSPLIB_TEXT, vehicle_count=3).vehicle_count == 3


@pytest.mark.parametrize("text, message", [
    (TSPLIB_TEXT.replace("EUC_2D", "GEO"), "only EUC_2D"),
    (TSPLIB_TEXT.replace("T-n4-k2", "T-n4"), "vehicle count"),
    (TSPLIB_TEXT.replace(" 1\n -1", " 1\n 2\n -1"), "one depot"),
])
def test_parse_tsplib_errors(text, message):
    with pytest.raises(BenchmarkFormatError, match=message):
        parse_tsplib_cvrp(text)


def test_parse_solution():
    routes, cost = parse_solution("Route #1: 1 3\nRoute #2: 2\nCost 25.5\n")
    assert routes == [[1, 3], [2]] and cost == 25.5
    with pytest.raises(BenchmarkFormatError):
        parse_solution("Cost 3")


def test_distance_conventions():
    base = dict(depot_x=0, depot_y=0, vehicle_count=1, vehicle_capacity=5)
    trunc = Instance(customers=[Customer(1, 1, 1, 1)], metric="euclidean_trunc1", **base)
    assert trunc.distance_matrix()[0][1] == pytest.approx(1.4)       # 1.414.. -> 1.4
    nint = Instance(customers=[Customer(1, 1, 2, 1), Customer(2, 2.5, 0, 1)], metric="euclidean_nint", **base)
    assert nint.distance_matrix()[0][1] == 2 and nint.distance_matrix()[0][2] == 3  # 2.236 -> 2, 2.5 -> 3


def test_gap_pct():
    assert catalog.gap_pct(110, 100) == pytest.approx(10)
    with pytest.raises(ValueError):
        catalog.gap_pct(1, 0)


def test_bks_table_has_provenance_for_every_row():
    bks = catalog.load_bks()
    assert len([b for b in bks.values() if b.set == "solomon"]) == 56
    for name, b in bks.items():
        assert b.set in catalog.SETS, name
        assert b.cost > 0 and b.routes > 0 and b.n_customers > 0, name
        assert b.source_url.startswith("https://galgos.inf.puc-rio.br/cvrplib/"), name
        dt.date.fromisoformat(b.retrieved_on)
        assert b.distance_convention and b.routes_rule, name


def test_benchmark_names_cannot_be_paths():
    assert catalog.re_safe_name("A-n32-k5") and catalog.re_safe_name("C1_2_1")
    assert not catalog.re_safe_name("../secret") and not catalog.re_safe_name("a/b")


def test_api_lists_benchmarks_and_404s_unknown_ones():
    client = TestClient(app)
    rows = client.get("/api/benchmarks").json()
    assert any(r["instance"] == "C101" for r in rows)
    assert client.post("/api/benchmarks/nope/C101").status_code == 404
    assert client.post("/api/benchmarks/solomon/..%2Fx").status_code == 404


# ---- real files (only when downloaded with experiments/benchmarks/fetch_benchmarks.py) ----
DOWNLOADED = [(n, b) for n, b in sorted(catalog.load_bks().items())
              if catalog.data_file(b.set, n).exists() and catalog.data_file(b.set, n, solution=True).exists()]
needs_data = pytest.mark.skipif(not DOWNLOADED, reason="benchmark files not downloaded")


@needs_data
def test_every_best_known_solution_is_feasible_and_matches_its_cost():
    """Checks parsers, distance conventions and the validator against CVRPLIB at once."""
    for name, b in DOWNLOADED:
        inst = catalog.load_instance(b.set, name)
        inst.validate()
        routes, cost = catalog.load_solution(b.set, name)
        v = validate_routes(inst, routes)
        m = compute_metrics(inst, routes, v)
        assert v.feasible, (name, [x.detail for x in v.violations][:3])
        assert math.isclose(m.total_distance, b.cost, abs_tol=0.051), (name, m.total_distance, b.cost)


@needs_data
def test_route_rules_per_set():
    for name, b in DOWNLOADED:
        inst = catalog.load_instance(b.set, name)
        if catalog.SETS[b.set].routes_rule == "free":
            assert inst.vehicle_count == len(inst.customers), name
        elif catalog.SETS[b.set].routes_rule == "fixed":
            assert inst.vehicle_count == b.routes, name


@needs_data
def test_api_loads_a_downloaded_benchmark_with_its_best_known_value():
    name, b = DOWNLOADED[0]
    r = TestClient(app).post(f"/api/benchmarks/{b.set}/{name}")
    assert r.status_code == 201, r.text
    assert r.json()["best_known"]["cost"] == b.cost

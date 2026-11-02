import io
import time

import pandas as pd
import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        c.data_dir = tmp_path
        yield c


def wait_run(client, run_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/runs/{run_id}").json()
        if r["state"] in ("completed", "failed"):
            return r
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def wait_experiment(client, exp_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        e = client.get(f"/api/experiments/{exp_id}").json()
        if e["state"] != "running":
            return e
        time.sleep(0.2)
    raise AssertionError("experiment did not finish")


def gen(client, n=8, seed=1, **kw):
    r = client.post("/api/instances/generate", json={"n_customers": n, "seed": seed, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["environment"]["ortools"]


def test_generate_is_reproducible_and_listed(client):
    a, b = gen(client, 10, 5), gen(client, 10, 5)
    assert a["instance_id"] == b["instance_id"]
    assert len(client.get("/api/instances").json()) == 1
    assert client.get(f"/api/instances/{a['instance_id']}").json()["customers"] == a["customers"]


def test_generate_bounds_validated(client):
    assert client.post("/api/instances/generate", json={"n_customers": 0}).status_code == 422
    r = client.post("/api/instances/generate", json={"n_customers": 5, "demand_min": 9, "demand_max": 2})
    assert r.status_code == 422


def test_register_instance_rejects_bad_domain_data_with_reasons(client):
    body = {"depot_x": 0, "depot_y": 0, "vehicle_count": 1, "vehicle_capacity": 5, "metric": "euclidean",
            "customers": [{"id": 1, "x": 1, "y": 1, "demand": -2}, {"id": 1, "x": 2, "y": 2, "demand": 9}]}
    r = client.post("/api/instances", json=body)
    assert r.status_code == 422
    errors = " | ".join(r.json()["detail"]["errors"])
    assert "positive integer" in errors and "duplicate" in errors and "exceeds vehicle capacity" in errors


def test_register_instance_rejects_wrong_shape(client):
    assert client.post("/api/instances", json={"customers": "nope"}).status_code == 422


def test_register_valid_instance(client):
    body = {"depot_x": 0, "depot_y": 0, "vehicle_count": 2, "vehicle_capacity": 4, "metric": "euclidean",
            "fixed_vehicle_cost": 0, "customers": [{"id": 1, "x": 3, "y": 0, "demand": 2},
                                                   {"id": 2, "x": 3, "y": 4, "demand": 2}]}
    r = client.post("/api/instances", json=body)
    assert r.status_code == 201 and r.json()["instance_id"].startswith("inst-")


def test_unknown_instance_and_run_404(client):
    assert client.get("/api/instances/nope").status_code == 404
    assert client.get("/api/runs/nope").status_code == 404
    assert client.post("/api/runs", json={"instance_id": "nope", "algorithm": "ga"}).status_code == 404
    assert client.get("/api/experiments/nope").status_code == 404


def test_run_contract_rejects_bad_algorithm_and_time(client):
    inst = gen(client)
    assert client.post("/api/runs", json={"instance_id": inst["instance_id"], "algorithm": "sa"}).status_code == 422
    r = client.post("/api/runs", json={"instance_id": inst["instance_id"], "algorithm": "ortools",
                                       "time_limit_s": 100000})
    assert r.status_code == 422


def test_ortools_run_lifecycle(client):
    inst = gen(client)
    r = client.post("/api/runs", json={"instance_id": inst["instance_id"], "algorithm": "ortools", "time_limit_s": 1})
    assert r.status_code == 202 and r.json()["state"] == "queued"
    run = wait_run(client, r.json()["run_id"])
    assert run["state"] == "completed" and run["result"]["status"] == "solved"
    assert run["validation"]["feasible"] is True
    assert run["metrics"]["total_distance"] > 0 and run["metrics"]["distance_unit"] == "km"
    m = client.get(f"/api/runs/{run['run_id']}/metrics").json()
    assert m["feasible"] is True and m["solver_status"] == "solved"


def test_ga_run_records_seed_and_config(client):
    inst = gen(client)
    r = client.post("/api/runs", json={"instance_id": inst["instance_id"], "algorithm": "ga",
                                       "ga": {"seed": 4, "population_size": 20, "max_generations": 10}})
    run = wait_run(client, r.json()["run_id"])
    assert run["result"]["seed"] == 4 and run["result"]["config"]["population_size"] == 20
    assert run["validation"]["feasible"] is True


def test_infeasible_instance_is_reported_not_faked(client):
    body = {"depot_x": 0, "depot_y": 0, "vehicle_count": 2, "vehicle_capacity": 10, "metric": "euclidean",
            "customers": [{"id": i, "x": i, "y": 0, "demand": 6} for i in (1, 2, 3)]}
    inst = client.post("/api/instances", json=body).json()
    r = client.post("/api/runs", json={"instance_id": inst["instance_id"], "algorithm": "ortools", "time_limit_s": 1})
    run = wait_run(client, r.json()["run_id"])
    assert run["result"]["status"] in ("no_solution", "timeout_no_solution")
    assert run["metrics"] is None and run["validation"] is None and run["row"]["total_distance"] is None
    assert client.get("/api/runs/export").text.splitlines()[1]  # row exists, blank metrics


def test_experiment_runs_both_algorithms_and_exports_csv(client):
    inst = gen(client, 8, 2)
    r = client.post("/api/experiments", json={"instance_id": inst["instance_id"], "time_budget_s": 1,
                                              "ga_seeds": 2, "ga": {"population_size": 20}})
    assert r.status_code == 202 and r.json()["runs"] == 3
    exp = wait_experiment(client, r.json()["experiment_id"])
    assert exp["state"] == "completed"
    assert {s["algorithm"] for s in exp["summary"]} == {"ortools", "ga"}
    ga_seeds = sorted(x["row"]["seed"] for x in exp["runs"] if x["algorithm"] == "ga")
    assert ga_seeds == [0, 1]
    raw = pd.read_csv(io.StringIO(client.get(f"/api/experiments/{exp['experiment_id']}/export").text))
    assert len(raw) == 3 and set(raw["instance_id"]) == {inst["instance_id"]} and raw["total_distance"].gt(0).all()
    summ = pd.read_csv(io.StringIO(client.get(f"/api/experiments/{exp['experiment_id']}/export?kind=summary").text))
    assert set(summ["algorithm"]) == {"ortools", "ga"}
    assert client.get(f"/api/experiments/{exp['experiment_id']}/export?kind=bad").status_code == 422


def test_runs_persist_across_restart(tmp_path):
    with TestClient(create_app(tmp_path)) as c1:
        inst = gen(c1)
        rid = c1.post("/api/runs", json={"instance_id": inst["instance_id"], "algorithm": "ga",
                                         "ga": {"population_size": 10, "max_generations": 5}}).json()["run_id"]
        wait_run(c1, rid)
    with TestClient(create_app(tmp_path)) as c2:
        assert c2.get(f"/api/runs/{rid}").json()["state"] == "completed"
        assert len(c2.get("/api/instances").json()) == 1


def test_experiment_listing_has_summary(client):
    inst = gen(client, 8, 3)
    exp_id = client.post("/api/experiments", json={"instance_id": inst["instance_id"], "time_budget_s": 1,
                                                   "ga_seeds": 1}).json()["experiment_id"]
    wait_experiment(client, exp_id)
    listing = client.get("/api/experiments").json()
    assert len(listing) == 1 and listing[0]["experiment_id"] == exp_id
    assert listing[0]["n_customers"] == 8 and listing[0]["time_budget_s"] == 1
    assert {s["algorithm"] for s in listing[0]["summary"]} == {"ortools", "ga"}

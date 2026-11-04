"""P6b: authenticated, tenant-scoped POST /api/plans and GET /api/plans/{id}."""
import time

import pytest
from app.db.keys import create_tenant, issue_key
from app.db.models import AuditLog
from app.db.session import admin_session
from app.main import create_app
from app.selector.dataset import ENGINES
from fastapi.testclient import TestClient
from sqlalchemy import select

TINY = {"name": "plan-test", "metric": "euclidean", "depot_x": 0, "depot_y": 0, "vehicle_count": 2,
        "vehicle_capacity": 4, "fixed_vehicle_cost": 0,
        "customers": [{"id": 1, "x": 3, "y": 0, "demand": 2}, {"id": 2, "x": 3, "y": 4, "demand": 2},
                      {"id": 3, "x": -3, "y": 0, "demand": 2}, {"id": 4, "x": -3, "y": -4, "demand": 2}]}


@pytest.fixture
def setup(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as c:
        with admin_session(app.state.db) as s:
            a, b = create_tenant(s, "A"), create_tenant(s, "B")
            _, ka = issue_key(s, a.id)
            _, kb = issue_key(s, b.id)
            s.commit()
        yield c, app, {"X-API-Key": ka}, {"X-API-Key": kb}, a.id


def wait_plan(c, plan_id, headers, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        p = c.get(f"/api/plans/{plan_id}", headers=headers).json()
        if p["state"] in ("completed", "failed"):
            return p
        time.sleep(0.1)
    raise AssertionError("plan did not finish")


def test_plans_require_a_valid_key(setup):
    c, *_ = setup
    body = {"instance": TINY, "engine": "ortools", "time_limit_s": 1}
    assert c.post("/api/plans", json=body).status_code == 401
    assert c.post("/api/plans", json=body, headers={"X-API-Key": "lm_00_bad"}).status_code == 401
    assert c.get("/api/plans/plan-x").status_code == 401


def test_auto_plan_is_validated_explained_and_audited(setup):
    c, app, ha, hb, tenant_a = setup
    r = c.post("/api/plans", json={"instance": TINY, "engine": "auto", "time_limit_s": 1}, headers=ha)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["engine"] in ENGINES and body["selection"]["explanation"]
    p = wait_plan(c, body["plan_id"], ha)
    assert p["state"] == "completed" and p["status"] == "solved" and p["feasible"] is True
    assert p["result"]["validation"]["validator_version"]
    assert p["selection"]["engine"] == body["engine"] and p["requested_engine"] == "auto"
    with admin_session(app.state.db) as s:
        actions = [a.action for a in s.scalars(select(AuditLog).where(AuditLog.tenant_id == tenant_a))]
    assert actions == ["plan.create", "plan.completed"]


def test_other_tenant_cannot_read_a_plan(setup):
    c, app, ha, hb, _ = setup
    plan_id = c.post("/api/plans", json={"instance": TINY, "engine": "ortools", "time_limit_s": 0.5},
                     headers=ha).json()["plan_id"]
    wait_plan(c, plan_id, ha)
    assert c.get(f"/api/plans/{plan_id}", headers=hb).status_code == 404  # same answer as "no such plan"
    assert c.get(f"/api/plans/{plan_id}", headers=ha).status_code == 200


def test_invalid_plans_are_rejected(setup):
    c, app, ha, *_ = setup
    too_big = {**TINY, "customers": [{**TINY["customers"][0], "demand": 99}]}
    assert c.post("/api/plans", json={"instance": too_big, "engine": "auto"}, headers=ha).status_code == 422
    assert c.post("/api/plans", json={"instance": TINY, "engine": "magic"}, headers=ha).status_code == 422
    assert c.post("/api/plans", json={"instance": TINY, "time_limit_s": 0}, headers=ha).status_code == 422


def test_openapi_documents_plans_with_api_key_security(setup):
    c, *_ = setup
    spec = c.get("/openapi.json").json()
    assert "/api/plans" in spec["paths"] and "/api/plans/{plan_id}" in spec["paths"]
    assert "APIKeyHeader" in spec["components"]["securitySchemes"]
    assert spec["paths"]["/api/plans"]["post"]["security"]


def test_explicit_engine_is_used_and_labelled(setup):
    c, app, ha, *_ = setup
    r = c.post("/api/plans", json={"instance": TINY, "engine": "ga", "time_limit_s": 0.5}, headers=ha)
    assert r.status_code == 202 and r.json()["engine"] == "ga_ls"
    assert r.json()["selection"]["method"] == "requested"
    p = wait_plan(c, r.json()["plan_id"], ha)
    assert p["feasible"] is True and p["result"]["solve"]["algorithm"] == "ga"

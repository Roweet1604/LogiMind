"""P7 replanning: each event type end to end through POST /api/plans/{id}/replan, frozen stops, warm start,
time to a feasible plan, tenant isolation, and the independent frozen-stop check."""
import pytest
from app.db.keys import create_tenant, issue_key
from app.db.models import Plan
from app.db.session import admin_session, tenant_session
from app.evaluation.validator import route_schedule, validate_routes
from app.main import create_app
from app.models.problem import Customer, Instance
from app.replan.events import FailedDelivery, ReplanError, VehicleBreakdown, apply_event, check_replan
from app.selector.generator import generate_family_instance
from app.solvers.ortools_solver import solve_ortools
from fastapi.testclient import TestClient

from tests.test_plans_api import TINY, wait_plan


def body_of(inst):
    return {"name": inst.name, "metric": inst.metric, "distance_unit": inst.distance_unit,
            "depot_x": inst.depot_x, "depot_y": inst.depot_y, "vehicle_count": inst.vehicle_count,
            "vehicle_capacity": inst.vehicle_capacity, "fixed_vehicle_cost": inst.fixed_vehicle_cost,
            "depot_due_time": inst.depot_due_time,
            "customers": [{"id": c.id, "x": c.x, "y": c.y, "demand": c.demand, "ready_time": c.ready_time,
                           "due_time": c.due_time, "service_time": c.service_time} for c in inst.customers]}


TW = generate_family_instance("uniform", 15, "loose", seed=3)  # synthetic, time windows
CVRP = generate_family_instance("clustered", 15, "none", seed=3)  # synthetic, no time windows


@pytest.fixture
def env(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as c:
        with admin_session(app.state.db) as s:
            a, b = create_tenant(s, "A"), create_tenant(s, "B")
            _, ka = issue_key(s, a.id)
            _, kb = issue_key(s, b.id)
            s.commit()
        yield c, app, {"X-API-Key": ka}, {"X-API-Key": kb}, a.id


def make_plan(c, h, inst=TW, engine="ortools", t=1):
    plan_id = c.post("/api/plans", json={"instance": body_of(inst) if not isinstance(inst, dict) else inst,
                                         "engine": engine, "time_limit_s": t}, headers=h).json()["plan_id"]
    p = wait_plan(c, plan_id, h)
    assert p["feasible"] is True
    return p


def replan(c, h, plan_id, event, **kw):
    r = c.post(f"/api/plans/{plan_id}/replan", json={"event": event, "time_limit_s": 1, **kw}, headers=h)
    return r


def used(routes):
    return [v for v, r in enumerate(routes) if r]


def assert_feasible_replan(p, frozen):
    assert p["state"] == "completed" and p["feasible"] is True, p.get("result", {}).get("replan_violations")
    assert p["result"]["validation"]["feasible"] and p["result"]["replan_violations"] == []
    routes = p["result"]["routes"]
    for v, prefix in frozen.items():
        assert routes[int(v)][:len(prefix)] == prefix
    t = p["replan"]["timing"]
    assert t["disruption_to_feasible_s"] is not None and t["disruption_to_feasible_s"] > 0
    assert t["disruption_to_feasible_s"] >= t["solver_seconds"]
    return routes


def test_vehicle_breakdown_freezes_completed_stops_and_reassigns_the_rest(env):
    c, app, ha, *_ = env
    parent = make_plan(c, ha)
    routes = parent["result"]["solve"]["routes"]
    v0, v1 = used(routes)[:2]
    done = {str(v0): 2, str(v1): 1}
    now = route_schedule(TW, routes[v0][:2]).starts[-1]  # the time vehicle v0 started its 2nd stop
    r = replan(c, ha, parent["plan_id"], {"type": "vehicle_breakdown", "vehicle": v0, "completed": done, "now": now})
    assert r.status_code == 202, r.text
    assert r.json()["replan"]["blocked"] == [v0]
    p = wait_plan(c, r.json()["plan_id"], ha)
    new = assert_feasible_replan(p, {v0: routes[v0][:2], v1: routes[v1][:1]})
    assert new[v0] == routes[v0][:2]  # broken vehicle: nothing after its completed stops
    assert sorted(x for r_ in new for x in r_) == sorted(cu.id for cu in TW.customers)
    assert p["parent_plan_id"] == parent["plan_id"] and p["event"]["type"] == "vehicle_breakdown"
    assert p["replan"]["timing"]["warm_start_result"] in ("used", "not given") or \
        p["replan"]["timing"]["warm_start_result"].startswith("rejected")


@pytest.mark.parametrize("retry", [True, False])
def test_failed_delivery_retry_or_drop(env, retry):
    c, app, ha, *_ = env
    parent = make_plan(c, ha, CVRP)
    routes = parent["result"]["solve"]["routes"]
    v = used(routes)[0]
    failed = routes[v][1]
    r = replan(c, ha, parent["plan_id"], {"type": "failed_delivery", "customer_id": failed, "retry": retry,
                                          "completed": {str(v): 1}})
    assert r.status_code == 202, r.text
    p = wait_plan(c, r.json()["plan_id"], ha)
    new = assert_feasible_replan(p, {v: routes[v][:1]})
    served = {x for r_ in new for x in r_}
    if retry:
        assert failed in served and p["replan"]["dropped_customers"] == []
    else:
        assert failed not in served and p["replan"]["dropped_customers"] == [failed]
        assert failed not in {cu["id"] for cu in c.get(f"/api/plans/{p['plan_id']}", headers=ha).json()
                              ["result"]["validation"]["unserved"]}  # dropped from the instance, not unserved
        assert len(served) == len(CVRP.customers) - 1


def test_urgent_order_is_served_with_ortools_warm_start(env):
    c, app, ha, *_ = env
    parent = make_plan(c, ha)
    routes = parent["result"]["solve"]["routes"]
    v = used(routes)[0]
    urgent = {"id": 999, "x": 52.0, "y": 48.0, "demand": 1, "ready_time": 0, "due_time": 900, "service_time": 10}
    r = replan(c, ha, parent["plan_id"], {"type": "urgent_order", "customer": urgent, "completed": {str(v): 1}})
    p = wait_plan(c, r.json()["plan_id"], ha)
    new = assert_feasible_replan(p, {v: routes[v][:1]})
    assert 999 in {x for r_ in new for x in r_}
    assert p["result"]["solve"]["algorithm"] == "ortools"


def test_urgent_order_with_ga_seeded_from_the_current_plan(env):
    c, app, ha, *_ = env
    parent = make_plan(c, ha, CVRP)
    urgent = {"id": 999, "x": 50.0, "y": 60.0, "demand": 1}
    r = replan(c, ha, parent["plan_id"], {"type": "urgent_order", "customer": urgent}, engine="ga")
    assert r.status_code == 202, r.text
    p = wait_plan(c, r.json()["plan_id"], ha)
    new = assert_feasible_replan(p, {})
    assert 999 in {x for r_ in new for x in r_}
    assert p["result"]["solve"]["algorithm"] == "ga"
    assert p["result"]["solve"]["config"]["initial_tours"] == 1
    assert p["replan"]["warm_start"] == "current plan (adjusted)"


def test_ga_refuses_frozen_stops_and_bad_events_are_422(env):
    c, app, ha, *_ = env
    parent = make_plan(c, ha, CVRP)
    pid = parent["plan_id"]
    routes = parent["result"]["solve"]["routes"]
    v = used(routes)[0]
    urgent = {"type": "urgent_order", "customer": {"id": 999, "x": 1, "y": 1, "demand": 1}, "completed": {str(v): 1}}
    r = replan(c, ha, pid, urgent, engine="ga")
    assert r.status_code == 422 and "frozen" in r.json()["detail"]
    bad = [{"type": "vehicle_breakdown", "vehicle": 99},
           {"type": "vehicle_breakdown", "vehicle": 0, "completed": {"0": 999}},
           {"type": "failed_delivery", "customer_id": 12345},
           {"type": "failed_delivery", "customer_id": routes[v][0], "completed": {str(v): 1}},
           {"type": "urgent_order", "customer": {"id": routes[v][0], "x": 1, "y": 1, "demand": 1}},
           {"type": "teleport"}]
    for event in bad:
        assert replan(c, ha, pid, event).status_code == 422, event


def test_infeasible_replan_is_reported_not_hidden(env):
    c, app, ha, *_ = env
    parent = make_plan(c, ha, TINY)  # 2 vehicles, each exactly full
    routes = parent["result"]["solve"]["routes"]
    v = used(routes)[0]
    r = replan(c, ha, parent["plan_id"], {"type": "vehicle_breakdown", "vehicle": v, "completed": {str(v): 1}})
    p = wait_plan(c, r.json()["plan_id"], ha)
    assert p["state"] == "completed" and p["feasible"] is False
    assert p["replan"]["timing"]["disruption_to_feasible_s"] is None
    assert p["status"] in ("no_solution", "timeout_no_solution")
    assert p["result"]["routes"] is None


def test_only_completed_feasible_plans_can_be_replanned(env):
    c, app, ha, hb, tenant_a = env
    with tenant_session(app.state.db, tenant_a) as s:
        s.add(Plan(id="plan-failed", tenant_id=tenant_a, instance=TW.to_dict(), requested_engine="ortools",
                   engine="ortools", time_limit_s=1.0, state="failed"))
        s.commit()
    r = replan(c, ha, "plan-failed", {"type": "vehicle_breakdown", "vehicle": 0})
    assert r.status_code == 409


def test_replan_is_tenant_isolated(env):
    c, app, ha, hb, _ = env
    parent = make_plan(c, ha, CVRP)
    event = {"type": "vehicle_breakdown", "vehicle": used(parent["result"]["solve"]["routes"])[0]}
    assert replan(c, hb, parent["plan_id"], event).status_code == 404  # B cannot replan A's plan
    assert replan(c, {}, parent["plan_id"], event).status_code == 401
    r = replan(c, ha, parent["plan_id"], event)
    child = wait_plan(c, r.json()["plan_id"], ha)
    assert child["feasible"] is True
    assert c.get(f"/api/plans/{child['plan_id']}", headers=hb).status_code == 404
    assert replan(c, hb, child["plan_id"], event).status_code == 404
    actions = [a["action"] for a in c.get("/api/audit", headers=ha).json()]
    assert "plan.replan" in actions and "plan.replanned" in actions
    assert c.get("/api/audit", headers=hb).json() == []


# ---- unit level: solver hooks and the independent check ---------------------------------------------
def test_ortools_keeps_frozen_prefixes_and_blocked_vehicles():
    base = solve_ortools(CVRP, time_limit_s=0.5).routes
    v = used(base)[0]
    frozen = [r[:1] for r in base]
    res = solve_ortools(CVRP, time_limit_s=0.5, frozen=frozen, blocked=[v], initial_routes=None)
    assert res.status == "solved"
    assert res.routes[v] == frozen[v]
    for w, prefix in enumerate(frozen):
        assert res.routes[w][:len(prefix)] == prefix
    assert validate_routes(CVRP, res.routes).feasible
    assert res.diagnostics["warm_start"] == "not given" and res.diagnostics["first_solution_s"] is not None
    assert res.config["search_choice"].startswith("replan_override")  # audited SAVINGS cannot extend locks


def test_ortools_warm_start_used_or_rejected_and_says_so():
    base = solve_ortools(CVRP, time_limit_s=0.5).routes
    ok = solve_ortools(CVRP, time_limit_s=0.5, initial_routes=base)
    assert ok.diagnostics["warm_start"] == "used" and ok.status == "solved"
    overloaded = [[c for r in base for c in r]] + [[] for _ in base[1:]]  # one route with everything
    bad = solve_ortools(CVRP, time_limit_s=0.5, initial_routes=overloaded)
    assert bad.diagnostics["warm_start"].startswith("rejected") and bad.status == "solved"


def test_check_replan_catches_changed_frozen_stops_busy_broken_vehicle_and_early_stops():
    routes = solve_ortools(TW, time_limit_s=0.5).routes
    v = used(routes)[0]
    setup = apply_event(TW, routes, VehicleBreakdown(type="vehicle_breakdown", vehicle=v, completed={v: 1}))
    moved = [list(r) for r in setup.warm_routes]
    other = next(w for w in used(routes) if w != v)
    moved[other] = moved[v][:1] + moved[other]  # frozen stop of v moved to another vehicle
    moved[v] = []
    problems = check_replan(moved, setup)
    assert any("completed stops" in p for p in problems)
    busy = [list(r) for r in routes]  # broken vehicle still has its unfinished stops
    assert any("broke down" in p for p in check_replan(busy, setup))
    # Hand-checked: route [1, 2, 3]; at now=4.5 customer 1 starts at 4.5, customer 2 arrives at 5.5 > due 5.
    small = Instance(depot_x=0, depot_y=0, vehicle_count=1, vehicle_capacity=10, metric="euclidean",
                     fixed_vehicle_cost=0, customers=[Customer(1, 1, 0, 1, 0.0, 100.0), Customer(2, 2, 0, 1, 0.0, 5.0),
                                                      Customer(3, 3, 0, 1, 0.0, 100.0)])
    assert validate_routes(small, [[1, 2, 3]]).feasible
    later = apply_event(small, [[1, 2, 3]], FailedDelivery(type="failed_delivery", customer_id=3, now=4.5))
    assert any("current time applied" in p for p in check_replan([[1, 2, 3]], later))
    on_time = apply_event(small, [[1, 2, 3]], FailedDelivery(type="failed_delivery", customer_id=3, now=0.5))
    assert check_replan([[1, 2, 3]], on_time) == []
    with pytest.raises(ReplanError, match="before the current time"):  # customer 2 can no longer be served
        apply_event(small, [[1, 2, 3]], FailedDelivery(type="failed_delivery", customer_id=3, now=6))
    with pytest.raises(ReplanError):
        apply_event(TW, routes, FailedDelivery(type="failed_delivery", customer_id=routes[v][0], completed={v: 1}))

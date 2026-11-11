"""A replan of a replanned plan keeps the earlier disruptions: a broken vehicle stays broken, completed stops
stay completed (in place), and a retried delivery keeps the retry rule."""
from app.evaluation.validator import route_schedule

from tests.test_plans_api import wait_plan
from tests.test_replan import CVRP, TW, assert_feasible_replan, body_of, env, make_plan, replan, used  # noqa: F401


def test_second_replan_keeps_the_broken_vehicle_and_its_completed_stops(env):  # noqa: F811
    c, app, ha, *_ = env
    parent = make_plan(c, ha, inst=CVRP)
    routes = parent["result"]["solve"]["routes"]
    v0, v1 = used(routes)[:2]
    first = replan(c, ha, parent["plan_id"], {"type": "vehicle_breakdown", "vehicle": v0,
                                              "completed": {str(v0): 1}})
    assert first.status_code == 202, first.text
    child = wait_plan(c, first.json()["plan_id"], ha)
    child_routes = assert_feasible_replan(child, {v0: routes[v0][:1]})
    assert child_routes[v0] == routes[v0][:1]

    # A second disruption on the replanned plan; the client does not repeat the earlier breakdown.
    target = next(cid for v, r in enumerate(child_routes) if v != v0 for cid in r)
    second = replan(c, ha, child["plan_id"], {"type": "failed_delivery", "customer_id": target, "retry": False})
    assert second.status_code == 202, second.text
    rec = second.json()["replan"]
    assert v0 in rec["blocked"], rec
    assert rec["frozen"][v0] == routes[v0][:1], rec
    grand = wait_plan(c, second.json()["plan_id"], ha)
    grand_routes = assert_feasible_replan(grand, {v0: routes[v0][:1]})
    assert grand_routes[v0] == routes[v0][:1]  # still broken: no new stops
    assert any("earlier" in n for n in grand["replan"]["notes"]), grand["replan"]["notes"]


def test_second_replan_keeps_completed_stops_the_client_forgot(env):  # noqa: F811
    c, app, ha, *_ = env
    parent = make_plan(c, ha, inst=CVRP)
    routes = parent["result"]["solve"]["routes"]
    v0, v1 = used(routes)[:2]
    first = replan(c, ha, parent["plan_id"], {"type": "vehicle_breakdown", "vehicle": v0,
                                              "completed": {str(v1): 2}})
    child = wait_plan(c, first.json()["plan_id"], ha)
    child_routes = assert_feasible_replan(child, {v1: routes[v1][:2]})
    # second replan says nothing about v1's two delivered stops
    urgent = {"id": 999, "x": 1.0, "y": 1.0, "demand": 1}
    second = replan(c, ha, child["plan_id"], {"type": "urgent_order", "customer": urgent})
    assert second.status_code == 202, second.text
    rec = second.json()["replan"]
    assert rec["frozen"][v1] == child_routes[v1][:2] and v0 in rec["blocked"], rec  # constraints, not luck
    grand = wait_plan(c, second.json()["plan_id"], ha)
    grand_routes = assert_feasible_replan(grand, {v1: child_routes[v1][:2]})
    assert grand_routes[v0] == []


def test_second_replan_keeps_the_retry_rule(env):  # noqa: F811
    c, app, ha, *_ = env
    parent = make_plan(c, ha, inst=TW)
    routes = parent["result"]["solve"]["routes"]
    v0 = next(v for v, r in enumerate(routes) if len(r) >= 4)
    failed = routes[v0][1]
    now = route_schedule(TW, routes[v0][:1]).starts[-1]
    first = replan(c, ha, parent["plan_id"], {"type": "failed_delivery", "customer_id": failed, "retry": True,
                                              "completed": {str(v0): 1}, "now": now})
    assert first.status_code == 202, first.text
    child = wait_plan(c, first.json()["plan_id"], ha)
    assert_feasible_replan(child, {v0: routes[v0][:1]})
    other = next(v for v, r in enumerate(child["result"]["routes"]) if v != v0 and r)
    second = replan(c, ha, child["plan_id"], {"type": "vehicle_breakdown", "vehicle": other,
                                              "completed": {str(v0): 1}, "now": now})
    assert second.status_code == 202, second.text
    grand = wait_plan(c, second.json()["plan_id"], ha)
    assert grand["result"]["replan_violations"] == []
    assert failed in grand["replan"]["retry"]
    for v, r in enumerate(grand["result"]["routes"]):
        n = len(grand["replan"]["frozen"][v])
        if len(r) - n > 1:
            assert r[n] != failed  # the retried customer is still not a route's next stop

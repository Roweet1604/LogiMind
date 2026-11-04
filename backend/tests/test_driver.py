"""P9 driver access: signed per-route links, stop list, delivered/failed reports, proof-of-delivery photos.
Most tests try to break the link: other routes, other plans, other tenants, tampered/expired/revoked tokens."""
import json
import uuid

import pytest
from app.db.models import AuditLog, Plan, PodPhoto, StopEvent
from app.db.session import admin_session
from app.driver.links import LinkClaims, LinkSigner, _b64, secret_from_env
from app.evaluation.validator import validate_routes
from app.models.problem import Customer, Instance
from sqlalchemy import select

from tests.conftest import T0
from tests.test_plans_api import TINY, wait_plan

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def tiny_instance(metric="euclidean") -> Instance:
    pts = [(1, 3, 0), (2, 3, 4), (3, -3, 0), (4, -3, -4)]
    if metric == "haversine":  # lon/lat near a fictional depot
        pts = [(cid, 77.20 + x / 100, 28.60 + y / 100) for cid, x, y in pts]
    return Instance(depot_x=77.20 if metric == "haversine" else 0, depot_y=28.60 if metric == "haversine" else 0,
                    customers=[Customer(cid, x, y, 2) for cid, x, y in pts], vehicle_count=2, vehicle_capacity=4,
                    metric=metric, fixed_vehicle_cost=0, name="driver-test")


def add_plan(app, tenant_id, routes=((1, 2), (3, 4)), metric="euclidean", feasible=None, parent=None) -> str:
    """Store a completed plan whose routes went through the real validator (no solver run needed)."""
    inst = tiny_instance(metric)
    routes = [list(r) for r in routes]
    v = validate_routes(inst, routes)
    result = {"solve": {"status": "solved", "routes": routes}, "validation": v.to_dict()}
    if feasible is not None:
        result["validation"]["feasible"] = feasible
    pid = f"plan-{uuid.uuid4().hex[:12]}"
    with admin_session(app.state.db) as s:
        s.add(Plan(id=pid, tenant_id=tenant_id, instance=inst.to_dict(), requested_engine="ortools", engine="ortools",
                   time_limit_s=1, state="completed", result=result, parent_id=parent))
        s.commit()
    return pid


def link(env, plan_id, route_index=0, headers=None, **kw):
    r = env["c"].post(f"/api/plans/{plan_id}/driver-links", json={"route_index": route_index, **kw},
                      headers=headers or env["ha"])
    assert r.status_code == 201, r.text
    return r.json()


def drv(token):
    return {"X-Driver-Token": token}


def report(c, token, cid, status="delivered", **kw):
    body = {"status": status, "client_event_id": kw.pop("eid", uuid.uuid4().hex), **kw}
    return c.post(f"/api/driver/stops/{cid}/status", json=body, headers=drv(token))


def test_links_need_a_key_and_a_feasible_plan_of_the_callers_tenant(env):
    c, pid = env["c"], add_plan(env["app"], env["a"])
    assert c.post(f"/api/plans/{pid}/driver-links", json={"route_index": 0}).status_code == 401
    assert c.post(f"/api/plans/{pid}/driver-links", json={"route_index": 0}, headers=env["hb"]).status_code == 404
    assert c.get(f"/api/plans/{pid}/driver-links", headers=env["hb"]).status_code == 404
    assert c.post(f"/api/plans/{pid}/driver-links", json={"route_index": 2}, headers=env["ha"]).status_code == 422
    assert c.post(f"/api/plans/{pid}/driver-links", json={"route_index": 0, "ttl_minutes": 2000},
                  headers=env["ha"]).status_code == 422
    bad = add_plan(env["app"], env["a"], feasible=False)
    r = c.post(f"/api/plans/{bad}/driver-links", json={"route_index": 0}, headers=env["ha"])
    assert r.status_code == 409 and "feasible" in r.json()["detail"]  # never handed out as a working route
    empty = add_plan(env["app"], env["a"], routes=((1, 2, 3, 4), ()), feasible=True)
    assert c.post(f"/api/plans/{empty}/driver-links", json={"route_index": 1}, headers=env["ha"]).status_code == 422
    out = link(env, pid, 1, label="Van 2")
    assert out["url"].endswith("/#t=" + out["token"]) and out["expires_at"].startswith("2027-01-15T")
    listed = c.get(f"/api/plans/{pid}/driver-links", headers=env["ha"]).json()
    assert [(x["link_id"], x["label"]) for x in listed] == [(out["link_id"], "Van 2")] and "token" not in listed[0]


def test_driver_sees_only_its_route_in_order(env):
    c, pid = env["c"], add_plan(env["app"], env["a"], routes=((2, 1), (3, 4)))
    r = c.get("/api/driver/route", headers=drv(link(env, pid, 0)["token"]))
    assert r.status_code == 200, r.text
    view = r.json()
    assert [(s["seq"], s["customer_id"], s["status"]) for s in view["stops"]] == [(1, 2, "pending"), (2, 1, "pending")]
    assert view["company"] == "Acme Couriers" and view["superseded_by"] is None
    assert view["stops"][0]["lat"] is None and view["coordinates"].startswith("planar")
    geo = add_plan(env["app"], env["a"], metric="haversine")
    stop = c.get("/api/driver/route", headers=drv(link(env, geo, 1)["token"])).json()["stops"][0]
    assert (stop["lat"], stop["lon"]) == (pytest.approx(28.60), pytest.approx(77.17))  # customer 3: lon/lat order
    child = add_plan(env["app"], env["a"], parent=pid)
    assert c.get("/api/driver/route", headers=drv(link(env, pid, 0)["token"])).json()["superseded_by"] == child


def test_a_link_for_one_route_cannot_read_or_change_another_route(env):
    c, app, pid = env["c"], env["app"], add_plan(env["app"], env["a"])
    token = link(env, pid, 0)["token"]
    # customers 3 and 4 are on route 1: same 404 as a customer that does not exist
    assert report(c, token, 3).status_code == 404
    assert report(c, token, 99).status_code == 404
    files = {"file": ("p.png", PNG, "image/png")}
    assert c.post("/api/driver/stops/4/photo", files=files, headers=drv(token)).status_code == 404
    # rewriting the claims to route 1 breaks the signature
    prefix, body, mac = token.split(".")
    claims = json.loads(__import__("base64").urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    forged = f"{prefix}.{_b64(json.dumps({**claims, 'r': 1}, separators=(',', ':'), sort_keys=True).encode())}.{mac}"
    assert c.get("/api/driver/route", headers=drv(forged)).status_code == 401
    assert report(c, forged, 3).status_code == 401
    # even a correctly signed token is refused when it disagrees with the link's record (route, plan, tenant)
    signer = app.state.driver.signer
    for change in ({"route_index": 1}, {"plan_id": add_plan(app, env["a"])}, {"tenant_id": env["b"]}):
        fields = {"link_id": claims["l"], "tenant_id": claims["t"], "plan_id": claims["p"], "route_index": claims["r"],
                  "expires": claims["e"], **change}
        assert c.get("/api/driver/route", headers=drv(signer.sign(LinkClaims(**fields)))).status_code == 401
    # a token signed with another secret
    other = LinkSigner(b"x" * 32).sign(LinkClaims(claims["l"], claims["t"], claims["p"], 0, claims["e"]))
    assert c.get("/api/driver/route", headers=drv(other)).status_code == 401
    for junk in ("", "dl1.abc", "dl1.e30." + mac, "Bearer " + token):
        assert c.get("/api/driver/route", headers=drv(junk)).status_code == 401
    assert report(c, token, 1).status_code == 200  # its own route still works
    with admin_session(app.state.db) as s:
        assert [e.customer_id for e in s.scalars(select(StopEvent))] == [1]


def test_tokens_and_api_keys_do_not_cross_over_and_tenants_stay_apart(env):
    c, app = env["c"], env["app"]
    pa, pb = add_plan(app, env["a"]), add_plan(app, env["b"])  # same customer ids 1..4 in both
    ta, tb = link(env, pa, 0)["token"], link(env, pb, 0, headers=env["hb"])["token"]
    assert c.get("/api/driver/route", headers=env["ha"]).status_code == 401  # an API key is not a driver token
    assert c.get(f"/api/plans/{pa}", headers={"X-API-Key": ta}).status_code == 401  # nor the other way round
    assert c.get("/api/plans", headers={"X-API-Key": ta}).status_code == 401
    assert report(c, tb, 1, "failed", reason="not_home").status_code == 200
    a_view = c.get("/api/driver/route", headers=drv(ta)).json()
    assert a_view["company"] == "Acme Couriers" and a_view["stops"][0]["status"] == "pending"
    assert c.get(f"/api/plans/{pa}/stop-reports", headers=env["ha"]).json()["events"] == []
    assert len(c.get(f"/api/plans/{pb}/stop-reports", headers=env["hb"]).json()["events"]) == 1
    assert c.get(f"/api/plans/{pb}/stop-reports", headers=env["ha"]).status_code == 404
    link_b = c.get(f"/api/plans/{pb}/driver-links", headers=env["hb"]).json()[0]["link_id"]
    assert c.delete(f"/api/driver-links/{link_b}", headers=env["ha"]).status_code == 404  # cannot revoke B's link
    assert c.get("/api/driver/route", headers=drv(tb)).status_code == 200


def test_expired_and_revoked_links_are_refused(env):
    c, pid = env["c"], add_plan(env["app"], env["a"])
    short = link(env, pid, 0, ttl_minutes=5)
    assert c.get("/api/driver/route", headers=drv(short["token"])).status_code == 200
    env["now"][0] = T0 + 5 * 60  # exactly at the expiry time
    r = c.get("/api/driver/route", headers=drv(short["token"]))
    assert r.status_code == 401 and "expired" in r.json()["detail"]
    env["now"][0] = T0
    other = link(env, pid, 1)
    assert c.delete(f"/api/driver-links/{other['link_id']}", headers=env["ha"]).json()["revoked_at"]
    r = report(env["c"], other["token"], 3)
    assert r.status_code == 401 and "revoked" in r.json()["detail"]


def test_stop_reports_validate_reasons_and_resends_are_idempotent(env):
    c, app, pid = env["c"], env["app"], add_plan(env["app"], env["a"])
    token = link(env, pid, 0)["token"]
    assert report(c, token, 1, "failed").status_code == 422  # a failure needs a reason
    assert report(c, token, 1, "failed", reason="lost_in_space").status_code == 422
    assert report(c, token, 1, "failed", reason="other").status_code == 422  # "other" needs a note
    assert report(c, token, 1, "delivered", reason="refused").status_code == 422
    assert report(c, token, 1, eid="bad id!").status_code == 422
    first = report(c, token, 1, "failed", reason="not_home", eid="evt-0001", occurred_at="2027-01-15T08:00:00Z")
    assert first.status_code == 200 and first.json()["duplicate"] is False
    again = report(c, token, 1, "failed", reason="not_home", eid="evt-0001")
    assert again.json()["duplicate"] is True and again.json()["event_id"] == first.json()["event_id"]
    assert report(c, token, 2, "delivered", eid="evt-0001").status_code == 409  # reused id, different update
    assert report(c, token, 1, "delivered", eid="evt-0002").status_code == 200  # retried later, delivered
    stops = {s["customer_id"]: s for s in c.get("/api/driver/route", headers=drv(token)).json()["stops"]}
    assert stops[1]["status"] == "delivered" and stops[2]["status"] == "pending"
    events = c.get(f"/api/plans/{pid}/stop-reports", headers=env["ha"]).json()["events"]
    assert [(e["status"], e["reason"]) for e in events] == [("failed", "not_home"), ("delivered", None)]
    assert events[0]["occurred_at"].startswith("2027-01-15T08:00")
    with admin_session(app.state.db) as s:
        actions = [a.action for a in s.scalars(select(AuditLog).where(AuditLog.tenant_id == env["a"]))]
        assert actions == ["driver_link.create", "stop.failed", "stop.delivered"]
        assert s.get(Plan, pid).result["solve"]["routes"] == [[1, 2], [3, 4]]  # a report never changes the plan


def test_photos_are_checked_stored_safely_and_tenant_scoped(env):
    c, app, pid = env["c"], env["app"], add_plan(env["app"], env["a"])
    token = link(env, pid, 0)["token"]
    r = c.post("/api/driver/stops/1/photo", files={"file": ("../../evil.png", PNG, "text/html")}, headers=drv(token))
    assert r.status_code == 201, r.text
    photo = r.json()
    assert photo["content_type"] == "image/png" and photo["size_bytes"] == len(PNG)
    stored = list((env["dir"] / "pod").rglob("*"))
    files = [p for p in stored if p.is_file()]
    assert [p.name for p in files] == [f"{photo['photo_id']}.png"] and files[0].parent.name == env["a"]
    assert not (env["dir"].parent / "evil.png").exists()
    got = c.get(f"/api/photos/{photo['photo_id']}", headers=env["ha"])
    assert got.status_code == 200 and got.content == PNG and got.headers["x-content-type-options"] == "nosniff"
    assert c.get(f"/api/photos/{photo['photo_id']}", headers=env["hb"]).status_code == 404
    assert c.get(f"/api/photos/{photo['photo_id']}", headers=drv(token)).status_code == 401
    up = lambda data, name="x.jpg", ctype="image/jpeg": c.post(  # noqa: E731
        "/api/driver/stops/1/photo", files={"file": (name, data, ctype)}, headers=drv(token))
    assert up(b"<html>not an image</html>").status_code == 422  # declared type and name are ignored
    assert up(b"").status_code == 422
    assert up(JPEG + b"\x00" * (3 * 1024 * 1024)).status_code == 413
    for _ in range(4):
        assert up(JPEG).status_code == 201
    assert up(JPEG).status_code == 409  # at most 5 per stop
    assert c.get("/api/driver/route", headers=drv(token)).json()["stops"][0]["photos"] == 5
    with admin_session(app.state.db) as s:
        assert len(s.scalars(select(PodPhoto)).all()) == 5
    assert len(c.get(f"/api/plans/{pid}/stop-reports", headers=env["ha"]).json()["photos"]) == 5


def test_link_for_a_real_solver_plan(env):
    c = env["c"]
    pid = c.post("/api/plans", json={"instance": TINY, "engine": "ortools", "time_limit_s": 0.5},
                 headers=env["ha"]).json()["plan_id"]
    plan = wait_plan(c, pid, env["ha"])
    assert plan["feasible"] is True
    routes = plan["result"]["solve"]["routes"]
    r = next(i for i, route in enumerate(routes) if route)
    view = c.get("/api/driver/route", headers=drv(link(env, pid, r)["token"])).json()
    assert [s["customer_id"] for s in view["stops"]] == routes[r]


def test_link_secret_from_the_environment(monkeypatch):
    monkeypatch.setenv("LOGIMIND_DRIVER_LINK_SECRET", "too-short")
    with pytest.raises(ValueError):
        secret_from_env()
    monkeypatch.setenv("LOGIMIND_DRIVER_LINK_SECRET", "s" * 40)
    assert secret_from_env() == b"s" * 40
    monkeypatch.delenv("LOGIMIND_DRIVER_LINK_SECRET")
    assert len(secret_from_env()) == 32 and secret_from_env() != secret_from_env()

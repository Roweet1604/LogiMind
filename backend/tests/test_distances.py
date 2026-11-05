"""P4: distance providers, batching, size limits, cache, flagged fallback, and travel times feeding
time windows and ETAs. OSRM answers are REAL recorded answers (tests/fixtures/osrm, decision 0019)
replayed offline; the points are synthetic."""
import json
import time
from pathlib import Path

import httpx
import numpy as np
import pytest
from app.db.keys import create_tenant, issue_key
from app.db.models import AuditLog
from app.db.session import admin_session
from app.distances.base import MatrixError, MatrixTooLarge, RoadMatrix
from app.distances.cache import MatrixCache
from app.distances.haversine import HaversineProvider, great_circle_km
from app.distances.osrm import OsrmProvider, ReplayTransport
from app.distances.service import DistanceService, DistanceSourceError, describe
from app.evaluation.validator import route_schedule, validate_routes
from app.main import create_app
from app.models.problem import Customer, Instance, InstanceValidationError
from fastapi.testclient import TestClient
from sqlalchemy import select

FIXTURE = Path(__file__).parent / "fixtures" / "osrm" / "bengaluru_6_points.json"
REC = json.loads(FIXTURE.read_text(encoding="utf-8"))
POINTS = [tuple(p) for p in REC["points"]]
URL = "http://osrm.test:5000"


def osrm(max_table=100, max_nodes=250, fixture=REC):
    replay = ReplayTransport(fixture)
    return OsrmProvider(URL, max_table=max_table, max_nodes=max_nodes, transport=replay), replay


def raw_single(points):
    """The recorded one-request answer for these points, straight from the fixture (m and s)."""
    coords = ";".join(f"{x:g},{y:g}" for x, y in points)
    body = REC["responses"][f"/table/v1/driving/{coords}?annotations=distance,duration"]["body"]
    return np.array(body["distances"]), np.array(body["durations"])


def down_transport():
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)
    return httpx.MockTransport(refuse)


def bengaluru(n_customers=4, **kw) -> Instance:
    (dx, dy), rest = POINTS[0], POINTS[1:1 + n_customers]
    return Instance(dx, dy, [Customer(i, x, y, 1, **kw) for i, (x, y) in enumerate(rest, start=1)],
                    vehicle_count=2, vehicle_capacity=10, metric="haversine", fixed_vehicle_cost=0.0, name="blr")


# ---- providers -------------------------------------------------------------------------------
def test_osrm_replays_a_real_answer_with_units_converted_and_direction_kept():
    prov, replay = osrm()
    m = prov.matrix(POINTS)
    d, t = raw_single(POINTS)
    assert len(replay.calls) == 1 and m.provenance["requests"] == 1 and m.provider == "osrm"
    assert np.allclose(m.distances_km, np.round(d / 1000, 3)) and np.allclose(m.durations_s, np.round(t, 1))
    assert m.distances_km[0, 1] != m.distances_km[1, 0]  # one-way streets: the matrix is not symmetric
    assert (m.distances_km >= great_circle_km(POINTS) - 1e-3).all()  # roads are never shorter than a straight line
    assert m.provenance["osrm_url"] == URL and "road network" in m.provenance["label"]


def test_batched_requests_give_exactly_the_single_request_matrix():
    prov, replay = osrm(max_table=4)
    assert prov.blocks(6) == [(a, b) for a in ([0, 1], [2, 3], [4, 5]) for b in ([0, 1], [2, 3], [4, 5])]
    m = prov.matrix(POINTS)
    assert len(replay.calls) == 9 and m.provenance["requests"] == 9
    for call in replay.calls:  # never more locations per request than the server allows
        assert len(call.split("/")[-1].split("?")[0].split(";")) <= 4
    single, _ = osrm()
    full = single.matrix(POINTS)
    assert np.array_equal(m.distances_km, full.distances_km) and np.array_equal(m.durations_s, full.durations_s)


def test_matrix_size_limit_is_enforced_before_any_request():
    prov, replay = osrm(max_nodes=5)
    with pytest.raises(MatrixTooLarge):
        prov.matrix(POINTS)
    assert replay.calls == []
    with pytest.raises(DistanceSourceError, match="matrix-size limit"):
        DistanceService(prov, max_nodes=5).matrix(POINTS, "osrm")
    with pytest.raises(DistanceSourceError, match="matrix-size limit"):  # applies to the estimate too
        DistanceService(None, max_nodes=5).matrix(POINTS, "estimate")


def test_unrecorded_requests_fail_loudly():
    with pytest.raises(RuntimeError, match="not in the recorded fixture"):
        osrm()[0].matrix([POINTS[0], (77.0, 13.0)])


def test_haversine_estimate_is_labelled_and_uses_the_detour_factor_and_speed():
    m = HaversineProvider(detour_factor=1.4, speed_kmh=20).matrix(POINTS)
    gc = great_circle_km(POINTS)
    assert np.allclose(m.distances_km, np.round(gc * 1.4, 3))
    assert np.allclose(m.durations_s, np.round(m.distances_km / 20 * 3600, 1), atol=0.1)
    assert "not road data" in m.provenance["label"]
    with pytest.raises(ValueError):
        HaversineProvider(detour_factor=0.9)


# ---- cache ---------------------------------------------------------------------------------
def test_cache_persists_across_restarts_and_skips_the_server(tmp_path):
    prov, replay = osrm()
    first = DistanceService(prov, cache=MatrixCache(tmp_path / "c.sqlite")).matrix(POINTS, "osrm")
    assert first.provenance["cache"] == "miss" and len(replay.calls) == 1
    prov2, replay2 = osrm()  # a "restarted" server process with a new cache object on the same file
    again = DistanceService(prov2, cache=MatrixCache(tmp_path / "c.sqlite")).matrix(POINTS, "osrm")
    assert replay2.calls == [] and again.provenance["cache"] == "hit"
    assert again.digest() == first.digest() and again.provenance["fetched_at"] == first.provenance["fetched_at"]
    stale = DistanceService(osrm()[0], cache=MatrixCache(tmp_path / "c.sqlite", max_age_days=-1))
    assert stale.matrix(POINTS, "osrm").provenance["cache"] == "miss"  # too old: asked again


def test_fallback_is_flagged_with_the_reason_and_never_cached(tmp_path):
    cache = MatrixCache(tmp_path / "c.sqlite")
    down = DistanceService(OsrmProvider(URL, transport=down_transport()), cache=cache).matrix(POINTS, "osrm")
    p = down.provenance
    assert p["fallback"] is True and p["requested"] == "osrm" and p["provider"] == "haversine_detour"
    assert "not reachable" in p["reason"] and p["label"].startswith("FALLBACK")
    assert len(cache) == 0
    unset = DistanceService(None).matrix(POINTS, "osrm").provenance
    assert unset["fallback"] is True and "LOGIMIND_OSRM_URL" in unset["reason"]
    chosen = DistanceService(None).matrix(POINTS, "estimate").provenance
    assert chosen["fallback"] is False and chosen["requested"] == "estimate"  # asked for, still labelled
    assert "not road data" in chosen["label"]


def test_unroutable_pair_or_error_answer_falls_back_and_says_why():
    broken = json.loads(json.dumps(REC))
    key = next(k for k in broken["responses"] if k.count(";") == 5 and "sources" not in k)  # the 6-point request
    broken["responses"][key]["body"]["durations"][2][3] = None
    p = DistanceService(osrm(fixture=broken)[0]).matrix(POINTS, "osrm").provenance
    assert p["fallback"] is True and "no road route from point 2 to point 3" in p["reason"]
    broken["responses"][key] = {"status": 400, "body": {"code": "TooBig", "message": "Too many table coordinates"}}
    p = DistanceService(osrm(fixture=broken)[0]).matrix(POINTS, "osrm").provenance
    assert p["fallback"] is True and "TooBig" in p["reason"]


# ---- the instance uses the matrix for distances AND travel times ------------------------------------
def test_road_matrix_changes_identity_and_survives_storage():
    inst = bengaluru()
    plain_id = inst.instance_id
    DistanceService(osrm()[0]).attach(inst, "osrm")
    assert inst.instance_id != plain_id
    back = Instance.from_dict(json.loads(json.dumps(inst.to_dict())))
    assert back.instance_id == inst.instance_id == back.compute_id()
    assert np.array_equal(back.distance_matrix(), inst.distance_matrix())
    assert np.array_equal(back.travel_time_matrix(), inst.travel_time_matrix())
    inst.set_road_matrix(None)
    assert inst.instance_id == plain_id  # ids without a road matrix are unchanged


def test_travel_times_come_from_the_matrix_in_the_instance_time_unit():
    inst = DistanceService(osrm()[0]).attach(bengaluru(), "osrm")
    d, t = raw_single(POINTS[:5])
    assert np.allclose(inst.distance_matrix(), np.round(d / 1000, 3))
    assert np.allclose(inst.travel_time_matrix(), np.round(t, 1) / 60)  # default unit: minutes
    inst.time_unit = "s"
    inst._tmatrix = None
    assert np.allclose(inst.travel_time_matrix(), np.round(t, 1))
    sched = route_schedule(inst, [1, 2])
    assert sched.starts[0] == pytest.approx(round(t[0][1], 1))  # first stop: depot -> 1 by road, in seconds


def test_road_travel_times_decide_time_window_feasibility():
    """The same window is reachable at the straight-line default (1 min/km) but not at road speed."""
    d, t = raw_single(POINTS[:5])
    due = round(t[0][1] / 60) - 2  # minutes; below the road time, above the straight-line time
    straight = bengaluru(due_time=None)
    straight.customers[0] = Customer(1, *POINTS[1], 1, due_time=due)
    straight.validate()
    assert great_circle_km(POINTS[:2])[0, 1] < due
    road = Instance.from_dict(straight.to_dict())
    DistanceService(osrm()[0]).attach(road, "osrm")
    with pytest.raises(InstanceValidationError, match="cannot be reached before due_time"):
        road.validate()
    # and the validator applies it to routes: on time with the straight line, late by road
    assert validate_routes(straight, [[1, 2, 3, 4]]).feasible
    assert not validate_routes(road, [[1, 2, 3, 4]]).feasible


def test_road_matrix_rules():
    inst = bengaluru()
    m = osrm()[0].matrix(POINTS)
    for change, msg in ((dict(distance_unit="mi"), "distance_unit"), (dict(time_unit="fortnight"), "time_unit")):
        bad = Instance.from_dict(inst.to_dict() | change)
        bad.set_road_matrix(m)
        with pytest.raises(InstanceValidationError, match=msg):
            bad.validate()
    far = bengaluru()
    far.customers[0] = Customer(1, 77.0, 13.0, 1)
    far.set_road_matrix(m)
    with pytest.raises(InstanceValidationError, match="no entry for node"):
        far.validate()
    with pytest.raises(DistanceSourceError, match="lon/lat"):
        DistanceService(None).attach(Instance(0, 0, [Customer(1, 3, 4, 1)], 1, 5), "osrm")
    with pytest.raises(MatrixError):
        RoadMatrix([POINTS[0]], np.array([[-1.0]]), np.array([[0.0]]))


# ---- API ---------------------------------------------------------------------------------------
def body_of(inst: Instance, source: str) -> dict:
    d = inst.to_dict()
    return {"engine": "ortools", "time_limit_s": 1, "distance_source": source,
            "instance": {"name": "blr", "metric": "haversine", "depot_x": d["depot"]["x"], "depot_y": d["depot"]["y"],
                         "vehicle_count": 2, "vehicle_capacity": 10, "fixed_vehicle_cost": 0,
                         "customers": [{"id": c["id"], "x": c["x"], "y": c["y"], "demand": 1}
                                       for c in d["customers"]]}}


def client_for(tmp_path, service):
    app = create_app(tmp_path, distances=service)
    c = TestClient(app)
    with admin_session(app.state.db) as s:
        t = create_tenant(s, "A")
        _, key = issue_key(s, t.id)
        s.commit()
    return c, app, {"X-API-Key": key}, t.id


def wait(c, pid, h):
    end = time.time() + 60
    while time.time() < end:
        p = c.get(f"/api/plans/{pid}", headers=h).json()
        if p["state"] in ("completed", "failed"):
            return p
        time.sleep(0.1)
    raise AssertionError("plan did not finish")


def test_api_plan_on_road_matrix_is_validated_with_road_numbers_and_says_so(tmp_path):
    prov, replay = osrm()
    c, app, h, _ = client_for(tmp_path, DistanceService(prov, cache=MatrixCache(tmp_path / "m.sqlite")))
    r = c.post("/api/plans", json=body_of(bengaluru(), "osrm"), headers=h)
    assert r.status_code == 202, r.text
    assert r.json()["distance_source"]["provider"] == "osrm" and r.json()["distance_source"]["fallback"] is False
    p = wait(c, r.json()["plan_id"], h)
    assert p["feasible"] is True and p["distance_source"]["provider"] == "osrm"
    d, t = raw_single(POINTS[:5])
    km = np.round(d / 1000, 3)
    expected = sum(km[0][r[0]] + sum(km[a][b] for a, b in zip(r, r[1:])) + km[r[-1]][0]
                   for r in p["result"]["solve"]["routes"] if r)
    assert p["result"]["metrics"]["total_distance"] == pytest.approx(expected, abs=1e-6)  # road km, not straight
    etas = c.get(f"/api/plans/{p['plan_id']}/etas", headers=h).json()
    assert "road network" in etas["time_model"] and etas["time_per_distance"] is None
    first = next(s for s in etas["stops"] if s["seq"] == 1)
    assert first["planned_start"] == pytest.approx(round(t[0][first["customer_id"]], 1) / 60, abs=1e-3)
    calls = len(replay.calls)
    c.post("/api/plans", json=body_of(bengaluru(), "osrm"), headers=h)  # same points: from the cache
    assert len(replay.calls) == calls
    assert c.get("/api/health").json()["distances"]["osrm_configured"] is True


def test_api_fallback_is_flagged_on_the_plan_list_and_audit(tmp_path):
    c, app, h, tenant = client_for(tmp_path, DistanceService(OsrmProvider(URL, transport=down_transport())))
    r = c.post("/api/plans", json=body_of(bengaluru(), "osrm"), headers=h)
    src = r.json()["distance_source"]
    assert src["fallback"] is True and "not reachable" in src["reason"] and src["provider"] == "haversine_detour"
    p = wait(c, r.json()["plan_id"], h)
    assert p["distance_source"]["fallback"] is True and p["feasible"] is True  # a plan, honestly labelled
    row = c.get("/api/plans", headers=h).json()[0]
    assert row["distance_fallback"] is True and row["distance_provider"] == "haversine_detour"
    with admin_session(app.state.db) as s:
        created = s.scalars(select(AuditLog).where(AuditLog.action == "plan.create")).one()
    assert created.detail["distance_fallback"] is True
    etas = c.get(f"/api/plans/{p['plan_id']}/etas", headers=h).json()
    assert "FALLBACK" in etas["time_model"]


def test_api_default_is_unchanged_and_bad_requests_are_422(tmp_path):
    c, app, h, _ = client_for(tmp_path, DistanceService(None, max_nodes=3))
    r = c.post("/api/plans", json=body_of(bengaluru(), "straight_line"), headers=h)
    p = wait(c, r.json()["plan_id"], h)
    assert "road_matrix" not in p["instance"] and p["distance_source"]["provider"] == "straight_line"
    assert describe(p["instance"])["travel_times"] == "distance x time_per_distance"
    assert c.post("/api/plans", json=body_of(bengaluru(), "estimate"), headers=h).status_code == 422  # 5 > 3 points
    xy = body_of(bengaluru(), "osrm")
    xy["instance"]["metric"] = "euclidean"
    assert c.post("/api/plans", json=xy, headers=h).status_code == 422


def test_urgent_order_extends_the_road_matrix_for_the_replan(tmp_path):
    prov, replay = osrm()
    c, app, h, _ = client_for(tmp_path, DistanceService(prov))
    parent = wait(c, c.post("/api/plans", json=body_of(bengaluru(), "osrm"), headers=h).json()["plan_id"], h)
    lon, lat = POINTS[5]
    r = c.post(f"/api/plans/{parent['plan_id']}/replan", headers=h, json={
        "engine": "ortools", "time_limit_s": 1,
        "event": {"type": "urgent_order", "customer": {"id": 99, "x": lon, "y": lat, "demand": 1}}})
    assert r.status_code == 202, r.text
    assert r.json()["distance_source"]["provider"] == "osrm"
    child = wait(c, r.json()["plan_id"], h)
    assert child["feasible"] is True and len(child["instance"]["road_matrix"]["points"]) == 6
    assert any(99 in route for route in child["result"]["routes"])

"""P9 ETA notifications: ETAs from the plan's schedule, templates, explicit opt-in, the stub sender and its log,
messages after driver reports, and tenant isolation."""
import logging
import uuid

import pytest
from app.db.models import NotificationLog, Plan
from app.db.session import admin_session
from app.evaluation.validator import route_schedule, validate_routes
from app.messaging.senders import StubSender, mask, sender_from_env
from app.messaging.templates import REASON_TEXT, TEMPLATES, render
from app.models.problem import Customer, Instance
from sqlalchemy import select

from tests.test_driver import add_plan, link, report

SHIFT = "2027-01-15T08:00:00+05:30"


def store(app, tenant_id, inst, routes):
    v = validate_routes(inst, routes)
    assert v.feasible
    pid = f"plan-{uuid.uuid4().hex[:12]}"
    with admin_session(app.state.db) as s:
        s.add(Plan(id=pid, tenant_id=tenant_id, instance=inst.to_dict(), requested_engine="ortools", engine="ortools",
                   time_limit_s=1, state="completed", result={"solve": {"status": "solved", "routes": routes},
                                                              "validation": v.to_dict()}))
        s.commit()
    return pid


def contact(env, cid, opt_in=True, address="+919812345678", channel="sms", headers=None):
    return env["c"].put(f"/api/contacts/{cid}", json={"channel": channel, "address": address, "opt_in": opt_in},
                        headers=headers or env["ha"])


def stub(env) -> StubSender:
    return env["app"].state.notifications.sender


def test_etas_follow_the_plans_own_schedule(env):
    c, pid = env["c"], add_plan(env["app"], env["a"])  # routes [1,2] and [3,4]; legs 3 then 4 (time = distance)
    body = c.get(f"/api/plans/{pid}/etas", params={"shift_start": SHIFT}, headers=env["ha"]).json()
    got = {(s["route_index"], s["customer_id"]): (s["planned_start"], s["eta"]) for s in body["stops"]}
    assert got[(0, 1)] == (3.0, "2027-01-15T08:03:00+05:30") and got[(0, 2)] == (7.0, "2027-01-15T08:07:00+05:30")
    assert got[(1, 3)][0] == 3.0 and body["clock_times"] is True and "not live traffic" in body["method"]
    assert body["time_model"].startswith("default assumption: 1.0 min per km")  # said plainly, not hidden
    plain = c.get(f"/api/plans/{pid}/etas", headers=env["ha"]).json()
    assert plain["clock_times"] is False and all(s["eta"] is None for s in plain["stops"])
    # time windows: arriving early means waiting, exactly as the validator's schedule says
    inst = Instance(depot_x=0, depot_y=0, vehicle_count=1, vehicle_capacity=10, metric="euclidean",
                    customers=[Customer(1, 3, 0, 1, ready_time=10, service_time=2), Customer(2, 3, 4, 1)],
                    fixed_vehicle_cost=0, name="tw")
    tw = store(env["app"], env["a"], inst, [[1, 2]])
    stops = c.get(f"/api/plans/{tw}/etas", params={"shift_start": SHIFT}, headers=env["ha"]).json()["stops"]
    assert [s["planned_start"] for s in stops] == route_schedule(inst, [1, 2]).starts == [10.0, 16.0]
    assert stops[1]["eta"] == "2027-01-15T08:16:00+05:30"
    assert c.get(f"/api/plans/{tw}/etas", headers=env["ha"]).json()["time_model"].startswith("from the plan")


def test_messages_go_only_to_opted_in_customers_and_everything_is_logged(env):
    c, pid = env["c"], add_plan(env["app"], env["a"])
    assert contact(env, 1, opt_in=True).json()["address"] == "+91********78"  # masked in every response
    assert contact(env, 2, opt_in=False).status_code == 200
    contact(env, 3, opt_in=True, channel="email", address="asha@example.com")
    r = c.post(f"/api/plans/{pid}/notify-etas", json={"shift_start": SHIFT}, headers=env["ha"])
    assert r.status_code == 200, r.text
    out = r.json()
    status = {x["customer_id"]: x["status"] for x in out["results"]}
    assert status == {1: "sent_stub", 2: "skipped_no_opt_in", 3: "sent_stub", 4: "skipped_no_contact"}
    assert out["provider"] == "stub" and out["counts"] == {"sent_stub": 2, "skipped_no_opt_in": 1,
                                                           "skipped_no_contact": 1}
    sent = {m["to"]: m["text"] for m in stub(env).sent}
    assert set(sent) == {"+919812345678", "asha@example.com"}  # never the customer who did not opt in
    assert sent["+919812345678"] == ("Acme Couriers: your delivery is planned for around 08:03 today. This is an "
                                     "estimate from our route plan and can change.")
    logged = c.get("/api/notifications", params={"plan_id": pid}, headers=env["ha"]).json()
    assert len(logged) == 4
    by = {x["customer_id"]: x for x in logged}
    assert by[2]["message"] is None and by[2]["recipient"] == "+91********78"  # no text kept for unsent ones
    assert by[3]["recipient"] == "a***@example.com" and "08:03" in by[3]["message"]
    with admin_session(env["app"].state.db) as s:
        assert all("9812345678" not in (n.recipient or "") for n in s.scalars(select(NotificationLog)))
    # a second call does not message the same customers again, unless asked
    again = c.post(f"/api/plans/{pid}/notify-etas", json={"shift_start": SHIFT}, headers=env["ha"]).json()
    assert {x["customer_id"]: x["status"] for x in again["results"]}[1] == "skipped_already_sent"
    assert len(stub(env).sent) == 2
    forced = c.post(f"/api/plans/{pid}/notify-etas", json={"shift_start": SHIFT, "resend": True, "route_index": 0},
                    headers=env["ha"]).json()
    assert [x["customer_id"] for x in forced["results"]] == [1, 2] and len(stub(env).sent) == 3


def test_opting_out_stops_messages_and_is_recorded(env):
    c, pid = env["c"], add_plan(env["app"], env["a"])
    first = contact(env, 1, opt_in=True).json()
    assert first["opt_in"] is True and first["opt_in_at"] and first["opt_out_at"] is None
    out = contact(env, 1, opt_in=False).json()
    assert out["opt_in"] is False and out["opt_out_at"]
    r = c.post(f"/api/plans/{pid}/notify-etas", json={"shift_start": SHIFT, "route_index": 0}, headers=env["ha"])
    assert {x["customer_id"]: x["status"] for x in r.json()["results"]}[1] == "skipped_no_opt_in"
    assert stub(env).sent == []
    listed = c.get("/api/contacts", headers=env["ha"]).json()
    assert [(x["customer_id"], x["opt_in"]) for x in listed] == [(1, False)]


def test_driver_reports_trigger_delivered_and_failed_messages(env, caplog):
    c, pid = env["c"], add_plan(env["app"], env["a"])
    contact(env, 1)
    contact(env, 2)
    token = link(env, pid, 0)["token"]
    with caplog.at_level(logging.INFO, logger="logimind.messaging"):
        assert report(c, token, 1).status_code == 200
        assert report(c, token, 2, "failed", reason="not_home").status_code == 200
    texts = [m["text"] for m in stub(env).sent]
    assert texts == ["Acme Couriers: your delivery has been completed. Thank you.",
                     "Acme Couriers: we could not complete your delivery today (nobody was available). We will "
                     "contact you to arrange a new time."]
    assert any("not sent; no provider" in r.getMessage() and "9812345678" not in r.getMessage()
               for r in caplog.records)
    # reported stops get no ETA afterwards
    res = c.post(f"/api/plans/{pid}/notify-etas", json={"shift_start": SHIFT, "route_index": 0},
                 headers=env["ha"]).json()["results"]
    assert {x["status"] for x in res} == {"skipped_already_reported"}


def test_a_failing_sender_is_logged_and_never_undoes_a_drivers_report(env):
    c, pid = env["c"], add_plan(env["app"], env["a"])
    contact(env, 1)
    stub(env).fail_with = "provider unavailable (simulated)"
    token = link(env, pid, 0)["token"]
    assert report(c, token, 1).status_code == 200
    assert c.get("/api/driver/route", headers={"X-Driver-Token": token}).json()["stops"][0]["status"] == "delivered"
    logged = c.get("/api/notifications", headers=env["ha"]).json()
    assert [(x["status"], x["error"]) for x in logged] == [("failed", "provider unavailable (simulated)")]


def test_notifications_are_tenant_scoped(env):
    c, app = env["c"], env["app"]
    pa = add_plan(app, env["a"])
    contact(env, 1, address="+911111111111")
    contact(env, 1, address="+912222222222", headers=env["hb"])  # same customer id, other tenant
    assert c.post(f"/api/plans/{pa}/notify-etas", json={"shift_start": SHIFT}, headers=env["hb"]).status_code == 404
    assert c.get(f"/api/plans/{pa}/etas", headers=env["hb"]).status_code == 404
    c.post(f"/api/plans/{pa}/notify-etas", json={"shift_start": SHIFT, "route_index": 0}, headers=env["ha"])
    assert [m["to"] for m in stub(env).sent] == ["+911111111111"]  # A's contact, never B's
    assert c.get("/api/notifications", headers=env["hb"]).json() == []
    assert [x["address"] for x in c.get("/api/contacts", headers=env["hb"]).json()] == ["+91********22"]
    assert c.get(f"/api/notifications?plan_id={pa}", headers=env["hb"]).json() == []


def test_requests_are_validated(env, monkeypatch):
    c, app = env["c"], env["app"]
    pid = add_plan(app, env["a"])
    assert contact(env, 1, address="12345").status_code == 422
    assert contact(env, 1, channel="email", address="not-an-email").status_code == 422
    assert contact(env, 1, channel="fax").status_code == 422
    assert c.post(f"/api/plans/{pid}/notify-etas", json={}, headers=env["ha"]).status_code == 422
    assert c.post(f"/api/plans/{pid}/notify-etas", json={"shift_start": "2027-01-15T08:00:00"},
                  headers=env["ha"]).status_code == 422  # no time zone
    assert c.post(f"/api/plans/{pid}/notify-etas", json={"shift_start": SHIFT, "route_index": 5},
                  headers=env["ha"]).status_code == 422
    bad = add_plan(app, env["a"], feasible=False)
    assert c.post(f"/api/plans/{bad}/notify-etas", json={"shift_start": SHIFT}, headers=env["ha"]).status_code == 409
    inst = Instance(depot_x=0, depot_y=0, vehicle_count=1, vehicle_capacity=10,
                    customers=[Customer(1, 3, 0, 1, service_time=1)], fixed_vehicle_cost=0, time_unit="units")
    odd = store(app, env["a"], inst, [[1]])
    odd_etas = c.get(f"/api/plans/{odd}/etas", params={"shift_start": SHIFT}, headers=env["ha"]).json()
    assert odd_etas["clock_times"] is False
    r = c.post(f"/api/plans/{odd}/notify-etas", json={"shift_start": SHIFT}, headers=env["ha"])
    assert r.status_code == 422 and "clock unit" in r.json()["detail"]
    assert c.get("/api/contacts").status_code == 401
    monkeypatch.setenv("LOGIMIND_NOTIFY_PROVIDER", "twilio")
    with pytest.raises(ValueError, match="only 'stub'"):
        sender_from_env()


def test_templates_fill_every_field():
    for name, fields in {"eta": {"company": "Acme", "eta_time": "08:03"}, "delivered": {"company": "Acme"},
                         "failed": {"company": "Acme", "reason": REASON_TEXT["refused"]}}.items():
        text = render(name, **fields)
        assert "$" not in text and text.startswith("Acme:")
    assert set(TEMPLATES) == {"eta", "delivered", "failed"}
    with pytest.raises(KeyError):
        render("eta", company="Acme")  # a missing field never produces a half-filled message
    assert mask("+919812345678") == "+91********78" and mask("asha@example.com") == "a***@example.com"

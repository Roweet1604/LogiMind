"""P6d wired: webhook endpoints + signed delivery on plan completion (fake sender), rate limit, audit log."""
import json
import time

import pytest
from app.db.keys import create_tenant, issue_key
from app.db.session import admin_session
from app.main import create_app
from app.services.ratelimit import RateLimiter
from app.services.webhooks import SIGNATURE_HEADER, FakeSender, verify_signature
from fastapi.testclient import TestClient

from tests.test_plans_api import TINY, wait_plan

HOOK = "https://hooks.example.invalid/logimind"


@pytest.fixture
def setup(tmp_path):
    app = create_app(tmp_path)
    sender = FakeSender()
    app.state.notifier.sender = sender
    app.state.notifier.backoff_s = (0.0, 0.0, 0.0)
    with TestClient(app) as c:
        with admin_session(app.state.db) as s:
            a, b = create_tenant(s, "A"), create_tenant(s, "B")
            _, ka = issue_key(s, a.id)
            _, kb = issue_key(s, b.id)
            s.commit()
        yield c, app, sender, {"X-API-Key": ka}, {"X-API-Key": kb}


def test_plan_completion_sends_a_signed_webhook_and_records_it(setup):
    c, app, sender, ha, hb = setup
    r = c.post("/api/webhooks", json={"url": HOOK, "events": ["plan.completed"]}, headers=ha)
    assert r.status_code == 201, r.text
    hook = r.json()
    secret = hook["secret"]
    assert secret.startswith("whsec_")
    assert "secret" not in c.get("/api/webhooks", headers=ha).json()[0]  # shown once only
    plan_id = c.post("/api/plans", json={"instance": TINY, "engine": "ortools", "time_limit_s": 0.5},
                     headers=ha).json()["plan_id"]
    wait_plan(c, plan_id, ha)
    app.state.notifier.drain()
    assert len(sender.calls) == 1
    call = sender.calls[0]
    assert call["url"] == HOOK and call["headers"]["LogiMind-Event"] == "plan.completed"
    assert verify_signature(secret, call["body"], call["headers"][SIGNATURE_HEADER])
    data = json.loads(call["body"])["data"]
    assert data["plan_id"] == plan_id and data["feasible"] is True and data["status"] == "solved"
    deliveries = c.get(f"/api/webhooks/{hook['webhook_id']}/deliveries", headers=ha).json()
    assert deliveries[0]["delivered"] and deliveries[0]["attempts"] == 1
    actions = [a["action"] for a in c.get("/api/audit", headers=ha).json()]
    assert actions[:3] == ["webhook.delivered", "plan.completed", "plan.create"]
    assert "webhook.create" in actions
    # Tenant B sees none of A's webhooks, deliveries or audit rows.
    assert c.get("/api/webhooks", headers=hb).json() == []
    assert c.get(f"/api/webhooks/{hook['webhook_id']}/deliveries", headers=hb).status_code == 404
    assert c.delete(f"/api/webhooks/{hook['webhook_id']}", headers=hb).status_code == 404
    assert c.get("/api/audit", headers=hb).json() == []


def test_failed_delivery_is_retried_then_recorded_as_failed(setup):
    c, app, sender, ha, _ = setup
    sender.script = [500, ConnectionError("refused"), 503, 502]
    hook = c.post("/api/webhooks", json={"url": HOOK}, headers=ha).json()
    plan_id = c.post("/api/plans", json={"instance": TINY, "engine": "ortools", "time_limit_s": 0.5},
                     headers=ha).json()["plan_id"]
    wait_plan(c, plan_id, ha)
    app.state.notifier.drain()
    d = c.get(f"/api/webhooks/{hook['webhook_id']}/deliveries", headers=ha).json()
    assert len(d) == 1 and not d[0]["delivered"] and d[0]["attempts"] == 4 and d[0]["last_status"] == 502
    assert c.get("/api/audit", headers=ha).json()[0]["action"] == "webhook.failed"


def test_events_filter_and_deactivation(setup):
    c, app, sender, ha, _ = setup
    hook = c.post("/api/webhooks", json={"url": HOOK, "events": ["plan.failed"]}, headers=ha).json()
    p1 = c.post("/api/plans", json={"instance": TINY, "engine": "ortools", "time_limit_s": 0.5}, headers=ha).json()
    wait_plan(c, p1["plan_id"], ha)
    app.state.notifier.drain()
    assert sender.calls == []  # subscribed only to plan.failed
    assert c.delete(f"/api/webhooks/{hook['webhook_id']}", headers=ha).json()["active"] is False


@pytest.mark.parametrize("url", ["ftp://example.com/x", "not a url", "http://127.0.0.1/x", "http://10.0.0.5/x",
                                 "http://localhost:8000/x", "http://169.254.169.254/latest", "http://[::1]/x"])
def test_unsafe_webhook_urls_are_refused(setup, url):
    c, app, sender, ha, _ = setup
    assert c.post("/api/webhooks", json={"url": url}, headers=ha).status_code == 422


def test_rate_limit_returns_429_with_retry_after_per_key(setup):
    c, app, sender, ha, hb = setup
    app.state.ratelimiter = RateLimiter(per_minute=60, burst=2, clock=time.monotonic)
    codes = [c.get("/api/audit", headers=ha).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = c.get("/api/audit", headers=ha)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert c.get("/api/audit", headers=hb).status_code == 200  # other key, own bucket
    assert c.get("/api/audit").status_code == 401  # no key: rejected before the limiter

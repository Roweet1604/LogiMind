"""Local demo mode (decision 0029): off by default, localhost only, never in Docker, normal keys keep working."""
import time
from pathlib import Path

import pytest
from app.db.keys import create_tenant, issue_key
from app.db.models import Tenant
from app.db.session import admin_session
from app.demo import DEMO_TENANT_ID, DEMO_TENANT_NAME, demo_from_env, is_loopback
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
LOCAL = {"base_url": "http://localhost:8000", "client": ("127.0.0.1", 50000)}


def local_client(app):
    return TestClient(app, **LOCAL)


def wait_all(c, headers, n, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        plans = c.get("/api/plans", headers=headers).json()
        if len(plans) == n and all(p["state"] in ("completed", "failed") for p in plans):
            return plans
        time.sleep(0.2)
    raise AssertionError("demo plans did not finish")


def test_demo_mode_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGIMIND_DEMO_MODE", raising=False)
    app = create_app(tmp_path)
    with local_client(app) as c:
        assert c.get("/api/health").json()["demo_mode"] is False
        r = c.get("/api/demo/session")
        assert r.status_code == 404 and "api_key" not in r.text
        with admin_session(app.state.db) as s:
            assert s.get(Tenant, DEMO_TENANT_ID) is None  # nothing is created when it is off


@pytest.mark.parametrize("env, on", [
    ({}, False),
    ({"LOGIMIND_DEMO_MODE": "1"}, False),                                      # bind host unknown: refused
    ({"LOGIMIND_DEMO_MODE": "1", "LOGIMIND_BIND_HOST": "0.0.0.0"}, False),
    ({"LOGIMIND_DEMO_MODE": "1", "LOGIMIND_BIND_HOST": "192.168.1.5"}, False),
    ({"LOGIMIND_DEMO_MODE": "true", "LOGIMIND_BIND_HOST": "127.0.0.1"}, False),  # only the exact value 1
    ({"LOGIMIND_DEMO_MODE": "0", "LOGIMIND_BIND_HOST": "127.0.0.1"}, False),
    ({"LOGIMIND_DEMO_MODE": "1", "LOGIMIND_BIND_HOST": "127.0.0.1"}, True),
    ({"LOGIMIND_DEMO_MODE": "1", "LOGIMIND_BIND_HOST": "localhost"}, True),
    ({"LOGIMIND_DEMO_MODE": "1", "LOGIMIND_BIND_HOST": "::1"}, True),
])
def test_demo_mode_needs_the_flag_and_a_loopback_bind_host(env, on):
    state = demo_from_env(env)
    assert state.enabled is on and state.reason


def test_env_switch_refused_for_a_public_bind_host_creates_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIMIND_DEMO_MODE", "1")
    monkeypatch.setenv("LOGIMIND_BIND_HOST", "0.0.0.0")
    app = create_app(tmp_path)
    with local_client(app) as c:
        assert c.get("/api/demo/session").status_code == 404
        assert c.get("/api/health").json()["demo_mode"] is False


def test_loopback_helper():
    assert is_loopback("127.0.0.1") and is_loopback("[::1]") and is_loopback("localhost")
    assert not is_loopback("0.0.0.0") and not is_loopback("testclient") and not is_loopback(None)


def test_demo_tenant_gets_validated_synthetic_plans_and_a_working_key(tmp_path):
    app = create_app(tmp_path, demo=True)
    with local_client(app) as c:
        assert c.get("/api/health").json()["demo_mode"] is True
        r = c.get("/api/demo/session")
        assert r.status_code == 200
        body = r.json()
        assert body["demo"] is True and body["tenant_name"] == DEMO_TENANT_NAME == "Demo Fleet (synthetic)"
        h = {"X-API-Key": body["api_key"]}
        assert c.get("/api/whoami", headers=h).json()["tenant_id"] == DEMO_TENANT_ID
        plans = wait_all(c, h, 3)
        assert all("synthetic" in p["name"] for p in plans)
        for p in plans:
            full = c.get(f"/api/plans/{p['plan_id']}", headers=h).json()
            assert full["instance"]["source"] == "synthetic"
            # The validator's verdict, not a label: every demo plan must really be feasible.
            assert full["state"] == "completed" and full["feasible"] is True, full.get("result")
        assert any(c_.get("due_time") is not None for p in plans
                   for c_ in c.get(f"/api/plans/{p['plan_id']}", headers=h).json()["instance"]["customers"])


def test_demo_key_is_refused_to_requests_not_from_this_computer(tmp_path):
    app = create_app(tmp_path, demo=True)
    with TestClient(app) as remote:  # default client host "testclient", Host "testserver"
        assert remote.get("/api/demo/session").status_code == 403
    with TestClient(app, base_url="http://localhost:8000", client=("192.168.1.20", 50000)) as lan:
        assert lan.get("/api/demo/session").status_code == 403
    with local_client(app) as c:
        assert c.get("/api/demo/session", headers={"Host": "evil.example:8000"}).status_code == 403  # DNS rebinding
        assert c.get("/api/demo/session", headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 403  # proxied
        assert c.get("/api/demo/session", headers={"Host": "localhost:5173"}).status_code == 200  # Vite dev proxy


def test_restart_reuses_the_tenant_and_rotates_the_key(tmp_path):
    app1 = create_app(tmp_path, demo=True, worker="external")  # nothing solves: only setup is checked
    with local_client(app1) as c:
        old = c.get("/api/demo/session").json()["api_key"]
    app2 = create_app(tmp_path, demo=True, worker="external")
    with local_client(app2) as c:
        new = c.get("/api/demo/session").json()["api_key"]
        assert new != old
        assert c.get("/api/whoami", headers={"X-API-Key": old}).status_code == 401  # earlier start's key revoked
        h = {"X-API-Key": new}
        assert len(c.get("/api/plans", headers=h).json()) == 3  # plans queued once, not again
    with admin_session(app2.state.db) as s:
        assert len(s.scalars(select(Tenant).where(Tenant.name == DEMO_TENANT_NAME)).all()) == 1


def test_normal_keys_and_tenant_isolation_still_hold_in_demo_mode(tmp_path):
    app = create_app(tmp_path, demo=True, worker="external")
    with local_client(app) as c:
        with admin_session(app.state.db) as s:
            t = create_tenant(s, "Acme Couriers")
            _, key = issue_key(s, t.id)
            s.commit()
        ha = {"X-API-Key": key}
        hd = {"X-API-Key": c.get("/api/demo/session").json()["api_key"]}
        assert c.get("/api/whoami", headers=ha).json()["tenant_name"] == "Acme Couriers"
        assert c.get("/api/plans", headers=ha).json() == []  # the demo plans are not visible to another tenant
        demo_plan = c.get("/api/plans", headers=hd).json()[0]["plan_id"]
        assert c.get(f"/api/plans/{demo_plan}", headers=ha).status_code == 404
        assert c.get("/api/whoami", headers={"X-API-Key": "lm_00_bad"}).status_code == 401


def test_docker_compose_never_turns_demo_mode_on():
    for path in [ROOT / "docker-compose.yml", ROOT / ".env.example", ROOT / "backend" / "Dockerfile"]:
        text = path.read_text(encoding="utf-8")
        assert "LOGIMIND_DEMO_MODE" not in text, path
    # The API container listens on 0.0.0.0, which demo mode refuses even if someone sets the flag.
    assert '"--host", "0.0.0.0"' in (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

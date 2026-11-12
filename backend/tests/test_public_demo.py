"""Public demo for the hosted deployment (decision 0039): needs both flags, hands out only the synthetic demo key,
other tenants stay isolated; plus the deploy plumbing (/health, FRONTEND_URL in CORS)."""
from app.db.keys import create_tenant, issue_key
from app.db.session import admin_session
from app.demo import DEMO_TENANT_ID, demo_from_env
from app.main import create_app
from fastapi.testclient import TestClient


def test_public_demo_needs_both_flags():
    assert demo_from_env({"LOGIMIND_PUBLIC_DEMO": "1"}).enabled is False  # demo mode itself not requested
    assert demo_from_env({"LOGIMIND_DEMO_MODE": "1", "LOGIMIND_PUBLIC_DEMO": "true",
                          "LOGIMIND_BIND_HOST": "0.0.0.0"}).enabled is False  # only the exact value 1
    state = demo_from_env({"LOGIMIND_DEMO_MODE": "1", "LOGIMIND_PUBLIC_DEMO": "1", "LOGIMIND_BIND_HOST": "0.0.0.0"})
    assert state.enabled is True and state.public is True and "PUBLIC" in state.reason
    local = demo_from_env({"LOGIMIND_DEMO_MODE": "1", "LOGIMIND_BIND_HOST": "127.0.0.1"})
    assert local.enabled is True and local.public is False


def test_public_demo_hands_the_demo_key_to_remote_callers_only_for_the_demo_tenant(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIMIND_DEMO_MODE", "1")
    monkeypatch.setenv("LOGIMIND_PUBLIC_DEMO", "1")
    monkeypatch.setenv("LOGIMIND_BIND_HOST", "0.0.0.0")
    app = create_app(tmp_path)
    with admin_session(app.state.db) as s:
        other = create_tenant(s, "Acme Couriers")
        _, other_key = issue_key(s, other.id, "test")
        s.commit()
    with TestClient(app, base_url="https://logimind-api.onrender.com",
                    headers={"X-Forwarded-For": "203.0.113.9"}) as c:
        r = c.get("/api/demo/session")
        assert r.status_code == 200 and "public" in r.json()["note"]
        h = {"X-API-Key": r.json()["api_key"]}
        assert c.get("/api/whoami", headers=h).json()["tenant_id"] == DEMO_TENANT_ID
        assert c.get("/api/whoami", headers={"X-API-Key": other_key}).json()["tenant_id"] == other.id
        assert c.get("/api/plans", headers={"X-API-Key": other_key}).json() == []  # demo plans stay in the demo tenant
        demo_plan = c.get("/api/plans", headers=h).json()[0]["plan_id"]
        assert c.get(f"/api/plans/{demo_plan}", headers={"X-API-Key": other_key}).status_code == 404


def test_health_and_frontend_url_cors(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://logimind.vercel.app/")
    app = create_app(tmp_path)
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}
        ok = c.get("/health", headers={"Origin": "https://logimind.vercel.app"})
        assert ok.headers.get("access-control-allow-origin") == "https://logimind.vercel.app"
        bad = c.get("/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in bad.headers


def test_frontend_url_is_read_from_the_backend_env_file(tmp_path, monkeypatch):
    import app.main as main
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("FRONTEND_URL=https://from-file.vercel.app\n", encoding="utf-8")
    monkeypatch.setattr(main, "BACKEND_ENV", dotenv)
    with TestClient(main.create_app(tmp_path / "data")) as c:
        r = c.get("/health", headers={"Origin": "https://from-file.vercel.app"})
        assert r.headers.get("access-control-allow-origin") == "https://from-file.vercel.app"

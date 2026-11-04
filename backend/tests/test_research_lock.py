"""The research endpoints have no tenants, so they are OFF unless the dev-only setting is on (decision 0011)."""
import pytest
from app.main import create_app
from fastapi.testclient import TestClient

RESEARCH = [("get", "/api/instances"), ("post", "/api/instances"), ("post", "/api/instances/generate"),
            ("get", "/api/instances/inst-x"), ("get", "/api/benchmarks"), ("post", "/api/benchmarks/solomon/C101"),
            ("get", "/api/runs"), ("post", "/api/runs"), ("get", "/api/runs/export"), ("get", "/api/runs/run-x"),
            ("get", "/api/runs/run-x/metrics"), ("get", "/api/experiments"), ("post", "/api/experiments"),
            ("get", "/api/experiments/exp-x"), ("get", "/api/experiments/exp-x/export")]


def test_research_endpoints_are_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGIMIND_DEV_RESEARCH_ENDPOINTS", raising=False)
    app = create_app(tmp_path)
    assert app.state.legacy_open is False
    with TestClient(app) as c:
        for method, path in RESEARCH:
            r = getattr(c, method)(path, **({"json": {}} if method == "post" else {}))
            assert r.status_code == 403, (method, path, r.status_code)
            assert "research endpoints are disabled" in r.json()["detail"]
        assert c.get("/api/health").status_code == 200  # health stays open


@pytest.mark.parametrize("value", ["0", "true", "yes", ""])
def test_only_the_exact_dev_value_turns_them_on(tmp_path, monkeypatch, value):
    monkeypatch.setenv("LOGIMIND_DEV_RESEARCH_ENDPOINTS", value)
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/api/instances").status_code == 403


def test_dev_setting_turns_them_on(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIMIND_DEV_RESEARCH_ENDPOINTS", "1")
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/api/instances").status_code == 200
    with TestClient(create_app(tmp_path, legacy_open=False)) as c:  # explicit argument wins
        assert c.get("/api/instances").status_code == 403


def test_openapi_labels_them_dev_only(tmp_path):
    with TestClient(create_app(tmp_path, legacy_open=False)) as c:
        spec = c.get("/openapi.json").json()
    assert spec["paths"]["/api/runs"]["post"]["tags"] == ["research (dev only, off by default)"]

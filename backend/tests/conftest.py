import os
import tempfile

# Keep the module-level `app` in app.main from writing into the repo during tests.
os.environ.setdefault("ROUTEOPT_DATA_DIR", tempfile.mkdtemp(prefix="routeopt_test_"))
# The research-endpoint tests run in dev mode; tests/test_research_lock.py checks that it is OFF by default.
os.environ.setdefault("LOGIMIND_DEV_RESEARCH_ENDPOINTS", "1")
# Tests never talk to a real model: the copilot tests inject the deterministic FakeLLM.
os.environ.setdefault("LOGIMIND_LLM_PROVIDER", "none")
# Test clients poll plans many times a second; the rate limiter has its own tests with small limits.
os.environ.setdefault("LOGIMIND_RATE_PER_MIN", "1000000")
os.environ.setdefault("LOGIMIND_RATE_BURST", "100000")
# API tests run the queue's worker loop in a thread of the test app (the same code as the worker process);
# tests/test_jobs.py also runs real worker PROCESSES, including a crash and a restart.
os.environ.setdefault("LOGIMIND_WORKER", "inline")

import pytest
from app.models.problem import Customer, Instance


@pytest.fixture
def tiny() -> Instance:
    """4 customers, capacity 4, 2 vehicles, no fixed cost, Euclidean.
    Hand-checked optimum: {1,2} and {3,4} = (3+4+5) + (3+4+5) = 24.
    """
    return Instance(
        depot_x=0, depot_y=0,
        customers=[Customer(1, 3, 0, 2), Customer(2, 3, 4, 2), Customer(3, -3, 0, 2), Customer(4, -3, -4, 2)],
        vehicle_count=2, vehicle_capacity=4, metric="euclidean",
        fixed_vehicle_cost=0.0, cost_per_distance=1.0, name="tiny")


T0 = 1_800_000_000.0  # fixed clock for driver-link expiry tests (no real clock checks)


@pytest.fixture
def env(tmp_path):
    """App with two tenants (Acme Couriers, Beta Freight), their API keys and a settable clock (P9 tests)."""
    from app.db.keys import create_tenant, issue_key
    from app.db.session import admin_session
    from app.main import create_app
    from fastapi.testclient import TestClient

    now = [T0]
    app = create_app(tmp_path, clock=lambda: now[0])
    with TestClient(app) as c:
        with admin_session(app.state.db) as s:
            a, b = create_tenant(s, "Acme Couriers"), create_tenant(s, "Beta Freight")
            _, ka = issue_key(s, a.id)
            _, kb = issue_key(s, b.id)
            s.commit()
        yield {"c": c, "app": app, "now": now, "a": a.id, "b": b.id, "ha": {"X-API-Key": ka},
               "hb": {"X-API-Key": kb}, "dir": tmp_path}

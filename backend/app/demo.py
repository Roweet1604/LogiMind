"""Local demo mode (decision 0029): a ready "Demo Fleet (synthetic)" tenant the ops console signs in to by itself.

OFF unless BOTH are set (start-dev.bat sets them; Docker Compose never does):
  LOGIMIND_DEMO_MODE=1            exactly "1"
  LOGIMIND_BIND_HOST=127.0.0.1    the host uvicorn listens on; must be a loopback address (127.0.0.1, ::1, localhost)

When on, start-up creates the demo tenant if it is missing, revokes the demo keys of earlier starts, issues a new
key that is kept in memory only (never written to disk or the log), and, if the tenant has no plans yet, queues
three plans on a small SYNTHETIC data set. The plans go through the normal queue, solvers and validator.
GET /api/demo/session hands the key out only to a request that comes from this machine (see `request_is_local`).
Normal API-key sign-in is unchanged.
"""
from __future__ import annotations

import ipaddress
import os
import random
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.keys import Principal, issue_key
from app.db.models import ApiKey, Plan, Tenant, utcnow
from app.db.session import admin_session, tenant_session
from app.models.problem import Customer, Instance

DEMO_TENANT_ID = "ten-demo-local"
DEMO_TENANT_NAME = "Demo Fleet (synthetic)"
DEMO_KEY_LABEL = "demo mode (in memory only)"
LOCAL_NAMES = {"localhost", "127.0.0.1", "::1"}


@dataclass
class DemoState:
    enabled: bool
    reason: str
    key: str = ""


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    host = host.strip().strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def demo_from_env(env: dict[str, str] | None = None) -> DemoState:
    """Whether demo mode may run. Requested (exact "1") AND a loopback bind host, or it stays off with the reason."""
    env = os.environ if env is None else env
    if env.get("LOGIMIND_DEMO_MODE", "") != "1":
        return DemoState(False, "LOGIMIND_DEMO_MODE is not 1")
    bind = env.get("LOGIMIND_BIND_HOST", "")
    if not is_loopback(bind):
        return DemoState(False, f"refused: LOGIMIND_BIND_HOST must be a loopback address, not {bind or '(unset)'!r}")
    return DemoState(True, f"on (bound to {bind})")


def request_is_local(request: Request) -> bool:
    """The caller, the socket the server answered on and the Host header must all be this machine, and no proxy
    may have forwarded the request. The Host check stops a web page on another site from reading the key through
    DNS rebinding; the Vite dev proxy keeps the browser's Host (localhost:5173)."""
    if any(h in request.headers for h in ("x-forwarded-for", "forwarded", "x-real-ip")):
        return False
    client = request.client.host if request.client else None
    server = request.scope.get("server")
    host_header = request.headers.get("host", "")
    hostname = host_header.rsplit(":", 1)[0] if not host_header.startswith("[") else host_header[1:].split("]")[0]
    return (is_loopback(client) and server is not None and is_loopback(server[0])
            and hostname.lower() in LOCAL_NAMES)


def _orders(rng: random.Random, n: int) -> list[tuple[float, float, int]]:
    """n synthetic stops (lon, lat, demand) within about 8 km of central Bengaluru. Not real addresses."""
    return [(round(77.5946 + rng.uniform(-0.07, 0.07), 5), round(12.9716 + rng.uniform(-0.07, 0.07), 5),
             rng.randint(1, 4)) for _ in range(n)]


def demo_instances() -> list[tuple[Instance, str, float]]:
    """(instance, engine, time budget s) for the three demo plans. Seeded, so every start builds the same data."""
    rng = random.Random(2026)
    common = dict(depot_x=77.5946, depot_y=12.9716, metric="haversine", source="synthetic", fixed_vehicle_cost=50.0)
    morning = Instance(customers=[Customer(i + 1, x, y, d) for i, (x, y, d) in enumerate(_orders(rng, 12))],
                       vehicle_count=3, vehicle_capacity=12, name="Morning deliveries (synthetic demo)", **common)
    # Two-hour delivery windows from 08:00 (minute 0); 25 km/h = 2.4 min per km; 5 minutes per stop.
    windowed = []
    for i, (x, y, d) in enumerate(_orders(rng, 15)):
        start = 60 * rng.randint(0, 4)
        windowed.append(Customer(i + 1, x, y, d, ready_time=start, due_time=start + 120, service_time=5))
    afternoon = Instance(customers=windowed, vehicle_count=4, vehicle_capacity=15, time_per_distance=2.4,
                         depot_due_time=480, name="Afternoon slots with time windows (synthetic demo)", **common)
    express = Instance(customers=[Customer(i + 1, x, y, d) for i, (x, y, d) in enumerate(_orders(rng, 10))],
                       vehicle_count=2, vehicle_capacity=14, name="Express run (synthetic demo)", **common)
    return [(morning, "ortools", 2.0), (afternoon, "auto", 2.0), (express, "ga", 2.0)]


def setup_demo(factory: sessionmaker[Session], plans) -> str:
    """Creates the demo tenant if missing, rotates its in-memory key and queues the demo plans once.
    Returns the new plaintext key (the caller keeps it in memory only)."""
    with admin_session(factory) as s:
        if s.get(Tenant, DEMO_TENANT_ID) is None:
            s.add(Tenant(id=DEMO_TENANT_ID, name=DEMO_TENANT_NAME))
            s.flush()
        for old in s.scalars(select(ApiKey).where(ApiKey.tenant_id == DEMO_TENANT_ID, ApiKey.label == DEMO_KEY_LABEL,
                                                  ApiKey.revoked_at.is_(None))):
            old.revoked_at = utcnow()
        row, key = issue_key(s, DEMO_TENANT_ID, DEMO_KEY_LABEL)
        s.commit()
    who = Principal(DEMO_TENANT_ID, row.id)
    with tenant_session(factory, DEMO_TENANT_ID) as s:
        has_plans = s.scalars(select(Plan.id).limit(1)).first() is not None
    if not has_plans:
        for inst, engine, budget in demo_instances():
            plans.submit(who, inst, engine, budget)
    return key

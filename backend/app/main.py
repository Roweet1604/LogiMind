"""FastAPI app. Run from backend/:  uvicorn app.main:app --reload --port 8000

Environment variables
  ROUTEOPT_DATA_DIR            where instances/runs/experiments JSON are stored
                               (default ../experiments/results/api_data)
  ROUTEOPT_CORS_ORIGINS        comma-separated allowed origins (default http://localhost:5173)
  ROUTEOPT_MAX_TIME_LIMIT_S    cap on per-run time limits (default 300)
  LOGIMIND_DATABASE_URL        tenant database (default: SQLite file logimind.db in the data dir);
                               migrated to the Alembic head on start-up
  LOGIMIND_RATE_PER_MIN        requests per minute per API key (default 60), LOGIMIND_RATE_BURST (default 20)
  LOGIMIND_DEV_RESEARCH_ENDPOINTS  "1" turns on /api/instances, /api/runs, /api/experiments, /api/benchmarks
                               (no tenants; local development only; OFF by default)
  LOGIMIND_LLM_PROVIDER        copilot model: "ollama" (default; used only if Ollama answers) or "none"
  LOGIMIND_OLLAMA_URL / LOGIMIND_OLLAMA_MODEL   default http://localhost:11434 / llama3.2:3b
  LOGIMIND_WEBHOOK_ALLOW_PRIVATE  "1" allows webhook URLs on localhost/private addresses (dev only; off)
  LOGIMIND_DRIVER_LINK_SECRET  signs driver links (>= 32 chars). Unset: a random per-process secret, so links
                               stop working on restart (development only)
  LOGIMIND_DRIVER_APP_URL      base URL of the driver PWA used in driver links (default http://localhost:5174)
  LOGIMIND_NOTIFY_PROVIDER     customer messages: "stub" only (logs, never sends; no paid provider exists)
  LOGIMIND_OSRM_URL            self-hosted OSRM, e.g. http://localhost:5000 (unset: distance_source="osrm" uses
                               the flagged fallback). LOGIMIND_OSRM_PROFILE (driving), LOGIMIND_OSRM_MAX_TABLE (100),
                               LOGIMIND_OSRM_TIMEOUT_S (10), LOGIMIND_MATRIX_MAX_NODES (250),
                               LOGIMIND_MATRIX_CACHE_DAYS (30; cache file matrix_cache.sqlite in the data dir)
  LOGIMIND_DETOUR_FACTOR / LOGIMIND_FALLBACK_SPEED_KMH   straight-line estimate (1.3 / 25 km/h; assumptions)
  LOGIMIND_WORKER              "external" (default): solver jobs wait in the database queue for a worker process
                               (python -m app.jobs.worker). "inline": the API runs the same worker loop in a thread
                               (development and tests only). See app/jobs/worker.py for the worker's settings.
  LOGIMIND_DEMO_MODE / LOGIMIND_BIND_HOST  "1" + a loopback host: local demo tenant with synthetic plans and
                               console auto sign-in (app/demo.py, decision 0029). OFF by default; never in Compose.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.copilot import router as copilot_router
from app.api.demo import router as demo_router
from app.api.driver import router as driver_router
from app.api.notifications import router as notifications_router
from app.api.platform import router as platform_router
from app.api.routes import legacy_open_from_env, router
from app.copilot.agent import Copilot
from app.copilot.llm import llm_from_env
from app.db.migrate import upgrade_to_head
from app.db.session import make_engine, make_session_factory
from app.demo import DemoState, demo_from_env, setup_demo
from app.distances.service import DistanceService, distance_service_from_env
from app.driver.links import LinkSigner, secret_from_env
from app.driver.service import DriverService
from app.jobs.queue import JobQueue
from app.jobs.worker import worker_from_env
from app.messaging.senders import sender_from_env
from app.messaging.service import NotificationService
from app.services.notify import WebhookNotifier
from app.services.plans import PlanService
from app.services.ratelimit import RateLimiter
from app.services.store import Store
from app.services.webhooks import HttpxSender


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    if app.state.worker is not None:  # inline worker: stop its loop; its thread then stops the solver process
        app.state.worker.close()


def create_app(data_dir: Path | None = None, legacy_open: bool | None = None, clock=None,
               distances: DistanceService | None = None, worker: str | None = None,
               demo: bool | None = None) -> FastAPI:
    """demo: None reads LOGIMIND_DEMO_MODE / LOGIMIND_BIND_HOST (app/demo.py); True/False override it (tests)."""
    default_dir = Path(__file__).resolve().parents[2] / "experiments" / "results" / "api_data"
    app = FastAPI(title="LogiMind API", version="0.2.0", lifespan=_lifespan,
                  description="Route planning with OR-Tools, GA and hybrid engines. Tenant endpoints "
                              "(plans, imports, webhooks, audit) need an `X-API-Key` header.")
    origins = os.environ.get("ROUTEOPT_CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins],
                       allow_methods=["*"], allow_headers=["*"])
    explicit_dir = data_dir is not None
    data_dir = Path(data_dir or os.environ.get("ROUTEOPT_DATA_DIR", default_dir))
    url = (None if explicit_dir else os.environ.get("LOGIMIND_DATABASE_URL")) or \
        f"sqlite:///{(data_dir / 'logimind.db').as_posix()}"
    upgrade_to_head(url)
    app.state.db = make_session_factory(make_engine(url))
    app.state.queue = JobQueue(app.state.db)
    app.state.store = Store(data_dir, app.state.queue)
    app.state.legacy_open = legacy_open_from_env() if legacy_open is None else legacy_open
    app.state.ratelimiter = RateLimiter()
    app.state.notifier = WebhookNotifier(app.state.db, HttpxSender())
    app.state.distances = distances or distance_service_from_env(data_dir)
    app.state.plans = PlanService(app.state.db, app.state.queue, app.state.distances)
    app.state.worker_mode = (worker or os.environ.get("LOGIMIND_WORKER", "external")).strip().lower()
    if app.state.worker_mode not in ("external", "inline"):
        raise ValueError(f"LOGIMIND_WORKER must be 'external' or 'inline', not {app.state.worker_mode!r}")
    app.state.worker = None
    if app.state.worker_mode == "inline":  # development and tests: the same loop, in a thread of this process
        app.state.worker = worker_from_env(app.state.db, app.state.notifier, queue=app.state.queue).start_thread()
    clock_opts = {"clock": clock} if clock is not None else {}
    app.state.notifications = NotificationService(app.state.db, sender_from_env(), **clock_opts)
    app.state.driver = DriverService(app.state.db, data_dir, LinkSigner(secret_from_env()),
                                     on_stop_event=app.state.notifications.on_stop_event, **clock_opts)
    app.state.demo = demo_from_env() if demo is None else DemoState(demo, "set by the caller")
    if demo is None and os.environ.get("LOGIMIND_DEMO_MODE"):
        logging.getLogger("logimind.demo").warning("demo mode: %s", app.state.demo.reason)
    if app.state.demo.enabled:
        app.state.demo.key = setup_demo(app.state.db, app.state.plans)
    app.include_router(router)
    app.state.copilot = Copilot(app.state.plans, llm_from_env())
    app.include_router(platform_router)
    app.include_router(copilot_router)
    app.include_router(driver_router)
    app.include_router(notifications_router)
    app.include_router(demo_router)
    return app


app = create_app()

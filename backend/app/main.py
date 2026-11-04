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
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.copilot import router as copilot_router
from app.api.platform import router as platform_router
from app.api.routes import legacy_open_from_env, router
from app.copilot.agent import Copilot
from app.copilot.llm import llm_from_env
from app.db.migrate import upgrade_to_head
from app.db.session import make_engine, make_session_factory
from app.services.notify import WebhookNotifier
from app.services.plans import PlanService
from app.services.ratelimit import RateLimiter
from app.services.store import Store
from app.services.webhooks import HttpxSender


def create_app(data_dir: Path | None = None, legacy_open: bool | None = None) -> FastAPI:
    default_dir = Path(__file__).resolve().parents[2] / "experiments" / "results" / "api_data"
    app = FastAPI(title="LogiMind API", version="0.2.0",
                  description="Route planning with OR-Tools, GA and hybrid engines. Tenant endpoints "
                              "(plans, imports, webhooks, audit) need an `X-API-Key` header.")
    origins = os.environ.get("ROUTEOPT_CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins],
                       allow_methods=["*"], allow_headers=["*"])
    explicit_dir = data_dir is not None
    data_dir = Path(data_dir or os.environ.get("ROUTEOPT_DATA_DIR", default_dir))
    app.state.store = Store(data_dir)
    url = (None if explicit_dir else os.environ.get("LOGIMIND_DATABASE_URL")) or \
        f"sqlite:///{(data_dir / 'logimind.db').as_posix()}"
    upgrade_to_head(url)
    app.state.db = make_session_factory(make_engine(url))
    app.state.legacy_open = legacy_open_from_env() if legacy_open is None else legacy_open
    app.state.ratelimiter = RateLimiter()
    app.state.notifier = WebhookNotifier(app.state.db, HttpxSender())
    app.state.plans = PlanService(app.state.db, app.state.store, app.state.notifier)
    app.include_router(router)
    app.state.copilot = Copilot(app.state.plans, llm_from_env())
    app.include_router(platform_router)
    app.include_router(copilot_router)
    return app


app = create_app()

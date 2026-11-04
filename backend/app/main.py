"""FastAPI app. Run from backend/:  uvicorn app.main:app --reload --port 8000

Environment variables
  ROUTEOPT_DATA_DIR            where instances/runs/experiments JSON are stored
                               (default ../experiments/results/api_data)
  ROUTEOPT_CORS_ORIGINS        comma-separated allowed origins (default http://localhost:5173)
  ROUTEOPT_MAX_TIME_LIMIT_S    cap on per-run time limits (default 300)
  LOGIMIND_DATABASE_URL        tenant database (default: SQLite file logimind.db in the data dir);
                               migrated to the Alembic head on start-up
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.db.migrate import upgrade_to_head
from app.db.session import make_engine, make_session_factory
from app.services.plans import PlanService
from app.services.store import Store


def create_app(data_dir: Path | None = None) -> FastAPI:
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
    app.state.plans = PlanService(app.state.db, app.state.store)
    app.include_router(router)
    return app


app = create_app()

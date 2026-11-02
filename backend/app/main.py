"""FastAPI app. Run from backend/:  uvicorn app.main:app --reload --port 8000

Environment variables
  ROUTEOPT_DATA_DIR            where instances/runs/experiments JSON are stored (default ../experiments/results/api_data)
  ROUTEOPT_CORS_ORIGINS        comma-separated allowed origins (default http://localhost:5173)
  ROUTEOPT_MAX_TIME_LIMIT_S    cap on per-run time limits (default 300)
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.services.store import Store


def create_app(data_dir: Path | None = None) -> FastAPI:
    default_dir = Path(__file__).resolve().parents[2] / "experiments" / "results" / "api_data"
    app = FastAPI(title="Route Optimization: OR-Tools vs GA", version="0.1.0")
    origins = os.environ.get("ROUTEOPT_CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.store = Store(data_dir or Path(os.environ.get("ROUTEOPT_DATA_DIR", default_dir)))
    app.include_router(router)
    return app


app = create_app()
